"""Single-leader polling process. No schema bootstrap and no executor/Docker access."""
import argparse
from contextlib import contextmanager
import json
import os
import re
import signal
import threading
import time

from sqlalchemy import inspect, text, URL

from .config import Settings, secret
from .store import Denied, Store, digest
from .telegram_bridge import TelegramBridge
from .telegram_transport import ConfiguredTelegramHTTP, TelegramHTTPError, connection


def service_settings():
    """Only the application DB binding; no Redis, API-owner or admin credentials."""
    revision = os.environ.get('F1_SOURCE_REVISION', '')
    if (os.environ.get('F1_DB_USER', 'f1_app') != 'f1_app'
            or not re.fullmatch(r'[a-f0-9]{40}', revision)):
        raise Denied('telegram_nonadmin_pinned_database_binding_required')
    url = URL.create('postgresql+psycopg', username='f1_app', password=secret('F1_DB_PASSWORD_FILE'),
                     host=os.environ.get('F1_DB_HOST', 'db'), port=int(os.environ.get('F1_DB_PORT', '5432')),
                     database='f1')
    return Settings(database_url=url, redis_url='', redis_password='', identities={}, source_revision=revision)  # nosec B106: unused Redis field; no Redis URL or connection


class TelegramService:
    def __init__(self, store, client, *, poll_seconds=10, max_failures=3):
        if not isinstance(client, ConfiguredTelegramHTTP) or not 0 <= poll_seconds <= 20 or not 1 <= max_failures <= 3:
            raise ValueError('telegram_service_limits_invalid')
        self.store, self.client = store, client
        self.poll_seconds, self.max_failures = poll_seconds, max_failures
        self.bridge = TelegramBridge(store, client, client.owner)
        self._leader, self._pid = None, None
        self._stop = None
        self._heartbeat_at = None
        raw = digest({'bot': client.bot_id, 'mode': client.mode})[:16]
        self._key = int(raw, 16) % (2**63 - 1)

    def event(self, kind, **details):
        with self.store.transaction() as session:
            self.store.check_audit(session)
            self.store.audit(session, kind, 'telegram_service', profile=self.bridge.profile,
                             mode=self.client.mode, **details)

    def guard(self):
        if self._stop is not None and self._stop.is_set():
            raise Denied('telegram_service_stopping')
        if self._leader is None:
            raise Denied('telegram_leadership_required')
        value = self._leader.execute(text("SELECT pg_backend_pid() AS pid, EXISTS(SELECT 1 FROM pg_locks "
            "WHERE locktype='advisory' AND pid=pg_backend_pid() AND granted "
            "AND classid=:high AND objid=:low AND objsubid=1) AS held"),
            {'high': self._key >> 32, 'low': self._key & 0xffffffff}).mappings().one()
        self._leader.commit()
        if value['pid'] != self._pid or not value['held']:
            raise Denied('telegram_leadership_lost')

    def heartbeat(self):
        now = time.monotonic()
        if self._heartbeat_at is None or now - self._heartbeat_at >= 15:
            self.guard()
            self.event('telegram_service_heartbeat', bot_id=self.client.bot_id,
                       connection_digest=self.client.approved)
            self._heartbeat_at = now

    @contextmanager
    def leader(self):
        with self.store.engine.connect() as conn:
            held = conn.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': self._key})
            conn.commit()
            if not held:
                raise Denied('telegram_another_poller_active')
            self._leader, self._pid = conn, conn.scalar(text('SELECT pg_backend_pid()'))
            conn.commit()
            self.client.runtime_guard = self.guard
            try:
                yield
            finally:
                self.client.runtime_guard = None
                self._leader = None
                try:
                    conn.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': self._key})
                    conn.commit()
                except Exception:
                    conn.invalidate()  # Server disconnect releases session locks.

    def run(self, stop=None, *, max_cycles=None):
        stop = stop or threading.Event()
        self._stop = stop
        if max_cycles is not None and (type(max_cycles) is not int or not 1 <= max_cycles <= 1000):
            raise ValueError('telegram_cycle_limit_invalid')
        with self.leader():
            if not all(inspect(self.store.engine).has_table(t) for t in
                       ('telegram_inbox', 'telegram_cards', 'telegram_deliveries')):
                raise Denied('telegram_reviewed_migration_required')
            with self.store.transaction() as session:
                self.store.check_audit(session)
            self.client.verify_bot()
            self.event('telegram_service_started', bot_id=self.client.bot_id, connection_digest=self.client.approved)
            cycles, failures = 0, 0
            try:
                while not stop.is_set() and (max_cycles is None or cycles < max_cycles):
                    self.guard()
                    try:
                        self.bridge.poll_once(timeout=self.poll_seconds)
                        self.heartbeat()
                        failures = 0
                        cycles += 1
                    except TelegramHTTPError as error:
                        failures += 1
                        self.event('telegram_poll_failed', code=str(error), consecutive=failures)
                        if not error.retryable or failures >= self.max_failures:
                            raise Denied('telegram_poll_retry_limit_or_permanent_failure') from None
                        if stop.wait(max(min(2**failures, 30), error.retry_after)):
                            break
                        continue
                    except Denied:
                        if stop.is_set():
                            break
                        raise
                    if stop.wait(.5):
                        break
            finally:
                self.event('telegram_service_stopped', completed_cycles=cycles)
            return {'mode': self.client.mode, 'completed_cycles': cycles, 'live_verified': self.client.mode == 'live'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'run'])
    parser.add_argument('--config', required=True)
    parser.add_argument('--approved-connection')
    args = parser.parse_args()
    client = None
    store = None
    try:
        config = connection(args.config)
        if args.action == 'inspect':
            print(json.dumps({'mode': config.mode, 'owner_id': config.owner_id, 'bot_id': config.bot_id,
                              'revision': config.source_revision, 'connection_digest': digest(config.model_dump()),
                              'credentials_tested': False, 'network_contacted': False}))
            return
        store = Store(service_settings())
        client = ConfiguredTelegramHTTP(args.config, args.approved_connection, store.settings.source_revision)
        service = TelegramService(store, client)
        stop = threading.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.set())
        print(json.dumps(service.run(stop)))
    except Exception:
        # No traceback containing credential-bearing URLs or secret-file values.
        parser.exit(1, 'telegram_service_failed_closed; inspect protected configuration and audit\n')
    finally:
        if client:
            client.close()
        if store:
            store.engine.dispose()


if __name__ == '__main__':
    main()
