"""Protected Linux custody and an ephemeral loopback Google callback.

No listener, grant, file or connection is created merely by importing this module.
"""
import os
import secrets
import stat
import time
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .google_calendar_access import CalendarAccess, PersonalCalendarHTTP
from .google_calendar_oauth import (
    CalendarTokenProvider, DesktopAuthorization, seal_credentials,
)
from .store import Denied, digest


class CalendarCredentialFiles:
    """One private POSIX directory, held open and exclusively locked until close.

    Operator provisions a dedicated32-byte calendar.key (0600) in directory0700.
    No key generation, permission relaxation or reuse of backup keys is implicit.
    """
    def __init__(self, directory):
        self._fd = None
        try:
            import fcntl
            path = Path(directory)
            if not path.is_absolute() or path.resolve() != path:
                raise ValueError()
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self._fd = fd
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError()
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.key = self._read('calendar.key', 32)
            if len(self.key) != 32:
                raise ValueError()
        except Exception:
            self.close()
            raise Denied('google_private_custody_unavailable') from None

    def __repr__(self):
        return '<CalendarCredentialFiles credentials=redacted>'

    def _read(self, name, limit):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._fd)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or info.st_size > limit):
                raise ValueError()
            return stream.read(limit + 1)

    def load(self):
        try:
            return self._read('calendar.enc', 16384)
        except Exception:
            raise Denied('google_private_archive_unavailable') from None

    def save(self, archive):
        name = '.calendar-' + secrets.token_hex(16)
        try:
            if not isinstance(archive, bytes) or not 64 <= len(archive) <= 16384:
                raise ValueError()
            # Refuse a pre-existing unsafe target, rather than replacing it.
            try:
                self._read('calendar.enc', 16384)
            except FileNotFoundError:
                pass
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self._fd)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(archive)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, 'calendar.enc', src_dir_fd=self._fd, dst_dir_fd=self._fd)
            os.fsync(self._fd)
        except Exception:
            raise Denied('google_private_archive_commit_failed') from None
        finally:
            try:
                os.unlink(name, dir_fd=self._fd)
            except (FileNotFoundError, TypeError):
                pass

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class CalendarLoopback:
    """Ephemeral IPv4 localhost listener. No public/admin endpoint or request log."""
    def __init__(self, client_id, *, clock=time.monotonic):
        self._clock = clock
        self._deadline = clock() + 300
        self._query = None
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(1)
                # Socket read timeouts alone reset with every byte. Enforce an
                # absolute request deadline against a trickling local client.
                self._timer = threading.Timer(1, self.expire)
                self._timer.daemon = True
                self._timer.start()

            def expire(self):
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            def finish(self):
                self._timer.cancel()
                try:
                    super().finish()
                except OSError:
                    pass

            def do_GET(self):
                try:
                    uri = urlsplit(self.path)
                except ValueError:
                    self.reply(400)
                    return
                if (len(self.path) > 4096 or uri.scheme or uri.netloc or uri.fragment
                        or uri.path != '/oauth/google/callback'
                        or self.headers.get_all('Host') != [parent.host]
                        or self.headers.get('Content-Length') not in (None, '0')
                        or self.headers.get('Transfer-Encoding') is not None):
                    self.reply(400)
                    return
                try:
                    query = parse_qs(uri.query, keep_blank_values=True, max_num_fields=12)
                    # State is checked before acknowledging or exposing the query.
                    import hmac
                    values = query.get('state', [])
                    if len(values) != 1 or not hmac.compare_digest(values[0], parent.attempt._state):
                        raise ValueError()
                    parent._query = query
                except (ValueError, TypeError):
                    self.reply(400)
                    return
                # This acknowledges receipt only, not token exchange or persistence.
                self.reply(200)

            def reply(self, code):
                body = b'Callback received. Return to the operator.' if code == 200 else b'Invalid callback.'
                self.send_response(code)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()
                self.wfile.write(body)

        class Server(HTTPServer):
            def handle_error(self, request, client_address):
                # A malformed request must not produce a callback traceback/log.
                pass

        self._server = Server(('127.0.0.1', 0), Handler)
        self.host = '127.0.0.1:' + str(self._server.server_port)
        try:
            self.attempt = DesktopAuthorization(client_id,
                'http://' + self.host + '/oauth/google/callback', clock=clock)
        except Exception:
            self.close()
            raise

    @property
    def authorization_url(self):
        return self.attempt.authorization_url

    def wait(self, oauth, *, now):
        try:
            while self._query is None and self._clock() < self._deadline:
                self._server.timeout = min(1, self._deadline - self._clock())
                self._server.handle_request()
            if self._query is None:
                raise Denied('google_oauth_callback_timeout')
            return self.attempt.complete(self._query, oauth, now=now())
        finally:
            self.close()

    def close(self):
        self._server.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def connection_binding(profile, approved_profile, client_id, revision):
    profile = CalendarAccess.model_validate(profile.model_dump())
    if (not profile.enabled or profile.source_revision != revision
            or digest(profile.model_dump()) != approved_profile):
        raise Denied('google_exact_connection_required')
    return digest({'profile': profile.model_dump(), 'client_id': client_id})


def complete_connection(listener, oauth, files, profile, approved_profile, revision, *, now=time.time):
    """Persist an explicitly approved connection; does not create a calendar/event."""
    binding = connection_binding(profile, approved_profile, oauth._client_id, revision)
    credentials = listener.wait(oauth, now=lambda: int(now()))
    files.save(seal_credentials(credentials, files.key, binding))
    return {'status': 'CREDENTIALS_STORED', 'connection_binding': binding,
            'calendar_id_verified': False, 'event_created': False}


def connected_calendar(profile, approved_profile, revision, oauth, files):
    """Caller retains files/oauth lifetime; existing publication approval still required."""
    binding = connection_binding(profile, approved_profile, oauth._client_id, revision)
    provider = CalendarTokenProvider(oauth, files.key, binding, files.load, files.save)
    return PersonalCalendarHTTP(profile, approved_profile, provider)
