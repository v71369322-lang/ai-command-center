"""Owner-scoped host maintenance mailbox; no shell, source upload or agent authority.

Installation is a separate administrator action. The runner has neither the
signing key nor runtime access. The trusted operator reuses Deployment.apply.
"""
import argparse
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import pwd
import re
import sqlite3
import stat
import time
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

MAX_FILE = 16384
MAX_ROWS = 4096
MAX_TTL = 900
ACTIONS = {'status', 'update'}
DIGEST = re.compile(r'[a-f0-9]{64}')
ZERO = '0' * 64


class Blocked(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def checksum(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Blocked('duplicate_json_key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Blocked('nonfinite_json')))
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise Blocked('invalid_json') from None


def protected_read(path, uid, *, private=False, limit=MAX_FILE):
    path = Path(path)
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != uid or parent.st_mode & 0o022:
        raise Blocked('file_parent_custody')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        m = os.fstat(stream.fileno())
        if (not stat.S_ISREG(m.st_mode) or m.st_uid != uid or m.st_nlink != 1
                or m.st_mode & (0o077 if private else 0o022) or m.st_size > limit):
            raise Blocked('file_custody')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise Blocked('file_limit')
    return raw


def valid_digest(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def validate_request(value):
    fields = {'schema', 'operation_id', 'policy_digest', 'action', 'target_bundle',
              'expected_bundle', 'issued_at', 'expires_at'}
    if not isinstance(value, dict) or set(value) != fields or type(value['schema']) is not int or value['schema'] != 1:
        raise Blocked('request_schema')
    try:
        op = UUID(value['operation_id'])
        if op.version != 4 or str(op) != value['operation_id']:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Blocked('request_id') from None
    if (not isinstance(value['action'], str) or value['action'] not in ACTIONS or not all(valid_digest(value[k]) for k in
            ('policy_digest', 'target_bundle', 'expected_bundle'))
            or any(type(value[k]) is not int for k in ('issued_at', 'expires_at'))
            or not 0 < value['expires_at'] - value['issued_at'] <= MAX_TTL):
        raise Blocked('request_scope')
    if value['action'] == 'status' and value['target_bundle'] != value['expected_bundle']:
        raise Blocked('status_scope')
    if value['action'] == 'update' and value['target_bundle'] == value['expected_bundle']:
        raise Blocked('no_change_update')
    return value


def validate_policy(value):
    fields = {'schema', 'issued_at', 'expires_at', 'max_operations', 'max_updates',
              'receipt_public_key', 'releases'}
    if not isinstance(value, dict) or set(value) != fields or type(value['schema']) is not int or value['schema'] != 1:
        raise Blocked('policy_schema')
    if (any(type(value[k]) is not int for k in ('issued_at', 'expires_at', 'max_operations', 'max_updates'))
            or not 0 < value['expires_at'] - value['issued_at'] <= 7 * 86400
            or not 1 <= value['max_operations'] <= 256 or not 0 <= value['max_updates'] <= 10):
        raise Blocked('policy_limits')
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(value['receipt_public_key'], validate=True))
    except (ValueError, TypeError):
        raise Blocked('policy_key') from None
    releases = value['releases']
    if not isinstance(releases, dict) or not 1 <= len(releases) <= 16:
        raise Blocked('policy_catalog')
    for digest, item in releases.items():
        if (not valid_digest(digest) or not isinstance(item, dict) or set(item) != {'directory', 'revision'}
                or not isinstance(item['revision'], str) or not re.fullmatch(r'[a-f0-9]{40}', item['revision'])
                or not isinstance(item['directory'], str)
                or not re.fullmatch(r'/home/acc-control/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+', item['directory'])):
            raise Blocked('policy_release')
    return value


@dataclass(frozen=True)
class Layout:
    root: Path
    policy: Path
    root_uid: int = 0
    control_uid: int = 1000
    runner_uid: int = -1

    @property
    def private(self):
        return self.root / 'private'

    def check(self, *, operator=True):
        entries = [(self.root, self.root_uid, 0o022),
                   (self.root / 'inbox', self.control_uid, 0o007),
                   (self.root / 'receipts', self.control_uid, 0o027)]
        if operator:
            entries.append((self.private, self.control_uid, 0o077))
        for p, uid, forbidden in entries:
            m = p.lstat()
            if not stat.S_ISDIR(m.st_mode) or m.st_uid != uid or m.st_mode & forbidden:
                raise Blocked('channel_directory_custody')


def atomic_receipt(directory, name, value):
    raw = canonical(value)
    temporary = directory / ('.receipt-' + uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    os.fchmod(fd, 0o640)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / name)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def signed_receipt(record, key):
    return {'receipt': record, 'signature': base64.b64encode(key.sign(canonical(record))).decode()}


def verify_receipt(envelope, request, public_key):
    try:
        if set(envelope) != {'receipt', 'signature'}:
            raise ValueError()
        record = envelope['receipt']
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
            base64.b64decode(envelope['signature'], validate=True), canonical(record))
        if (record['request_hash'] != checksum(request) or record['operation_id'] != request['operation_id']
                or record['policy_digest'] != request['policy_digest']
                or any(record[k] != request[k] for k in ('action', 'target_bundle', 'expected_bundle'))
                or record['state'] not in {'SUCCEEDED', 'REJECTED', 'UNCERTAIN'}):
            raise ValueError()
        return record
    except Exception:
        raise Blocked('receipt_unverified') from None


class Journal:
    def __init__(self, path):
        if path.exists() or path.is_symlink():
            m = path.lstat()
            if not stat.S_ISREG(m.st_mode) or m.st_uid != os.getuid() or m.st_mode & 0o077 or m.st_nlink != 1:
                raise Blocked('journal_custody')
        self.db = sqlite3.connect(path, timeout=2, isolation_level=None)
        os.chmod(path, 0o600)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,record TEXT NOT NULL);'
                             'CREATE TABLE IF NOT EXISTS audit(sequence INTEGER PRIMARY KEY,event TEXT NOT NULL,'
                             'previous TEXT NOT NULL,digest TEXT NOT NULL);')

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            records = self.verify()
            yield records
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def verify(self):
        previous, projection = ZERO, {}
        rows = self.db.execute('SELECT sequence,event,previous,digest FROM audit ORDER BY sequence').fetchall()
        if len(rows) > MAX_ROWS:
            raise Blocked('journal_limit')
        for expected, (sequence, raw, before, digest) in enumerate(rows, 1):
            record = strict_json(raw)
            if sequence != expected or before != previous or checksum({'previous': previous, 'record': record}) != digest:
                raise Blocked('journal_integrity')
            projection[record['operation_id']] = record
            previous = digest
        actual = {oid: strict_json(raw) for oid, raw in self.db.execute('SELECT id,record FROM operations')}
        if actual != projection:
            raise Blocked('journal_projection')
        return actual

    def save(self, record):
        row = self.db.execute('SELECT sequence,digest FROM audit ORDER BY sequence DESC LIMIT 1').fetchone()
        sequence, previous = (row[0] + 1, row[1]) if row else (1, ZERO)
        if sequence > MAX_ROWS:
            raise Blocked('journal_limit')
        raw = canonical(record).decode()
        self.db.execute('INSERT INTO audit VALUES (?,?,?,?)',
                        (sequence, raw, previous, checksum({'previous': previous, 'record': record})))
        self.db.execute('INSERT INTO operations VALUES (?,?) ON CONFLICT(id) DO UPDATE SET record=excluded.record',
                        (record['operation_id'], raw))


class HostBackend:
    """Only existing pinned, prepared bundles. No build, schema or credential operations."""
    def __init__(self, policy):
        self.policy = policy

    def prepare(self, request):
        from .deployment import Deployment, load_bundle
        from .deployment_profile import checksum as release_checksum
        item = self.policy['releases'][request['target_bundle']]
        bundle = load_bundle(item['directory'])
        m = bundle['manifest']
        if (release_checksum(bundle) != request['target_bundle'] or m['revision'] != item['revision']
                or m['control_uid'] != 1000 or m['execution_uid'] != 1001
                or m['data_root'] != '/home/acc-control/f30/state'):
            raise Blocked('release_scope')
        state = strict_json(protected_read(Path(m['data_root']) / 'deployment.json', 1000, private=True))
        if state.get('phase') != 'VERIFIED' or state.get('bundle') != request['expected_bundle']:
            raise Blocked('predecessor_changed_or_pending')
        before = load_bundle(state['directory'])
        if release_checksum(before) != state['bundle']:
            raise Blocked('predecessor_bundle_changed')
        for key in ('data_root', 'control_uid', 'execution_uid', 'migration_hash', 'database_image',
                    'redis_image', 'owner_login'):
            if m.get(key) != before['manifest'].get(key):
                raise Blocked('separate_owner_decision_required')
        old_tg, new_tg = before['manifest'].get('telegram'), m.get('telegram')
        if bool(old_tg) != bool(new_tg) or (old_tg and any(
                old_tg.get(k) != new_tg.get(k) for k in ('mode', 'owner_id', 'bot_id'))):
            raise Blocked('telegram_authority_change')
        deployment = Deployment(bundle, item['directory'])
        deployment.preflight()
        return deployment

    def execute(self, request, prepared):
        if request['action'] == 'update':
            prepared.apply('update', request['target_bundle'], expected_previous=request['expected_bundle'])
        else:
            fd = os.open(prepared.root / 'deployment.lock', os.O_RDWR | os.O_NOFOLLOW)
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                state = strict_json(protected_read(prepared.root / 'deployment.json', 1000, private=True))
                if state.get('phase') != 'VERIFIED' or state.get('bundle') != request['expected_bundle']:
                    raise Blocked('status_predecessor_changed')
                prepared.postcheck()
            finally:
                os.close(fd)


class Channel:
    def __init__(self, layout, backend_factory=HostBackend, clock=time.time):
        self.layout, self.backend_factory, self.clock = layout, backend_factory, clock

    def policy(self):
        return validate_policy(strict_json(protected_read(self.layout.policy, self.layout.root_uid)))

    def execute(self, request, journal, key):
        rhash, now = checksum(request), int(self.clock())
        with journal.transaction() as records:
            old = records.get(request['operation_id'])
            if old:
                if old['request_hash'] != rhash:
                    raise Blocked('operation_id_reused')
                return old
            record = dict(operation_id=request['operation_id'], request_hash=rhash,
                          policy_digest=request['policy_digest'], action=request['action'],
                          target_bundle=request['target_bundle'], expected_bundle=request['expected_bundle'],
                          state='REJECTED', code='request_denied', updated_at=now)
            try:
                policy = self.policy()
                if checksum(policy) != request['policy_digest']:
                    raise Blocked('policy_revoked_or_changed')
                if not policy['issued_at'] <= now < policy['expires_at'] or not request['issued_at'] <= now < request['expires_at']:
                    raise Blocked('authority_expired')
                if request['target_bundle'] not in policy['releases'] or request['expected_bundle'] not in policy['releases']:
                    raise Blocked('bundle_not_approved')
                used = [r for r in records.values() if r['policy_digest'] == request['policy_digest']]
                if len(used) >= policy['max_operations']:
                    raise Blocked('operation_limit')
                if request['action'] == 'update':
                    if any(r['action'] == 'update' and r['state'] in {'RUNNING', 'UNCERTAIN'} for r in records.values()):
                        raise Blocked('uncertain_update_requires_owner')
                    if sum(r['action'] == 'update' and r['state'] == 'SUCCEEDED' for r in used) >= policy['max_updates']:
                        raise Blocked('update_limit')
                backend = self.backend_factory(policy)
                prepared = backend.prepare(request)
                # Re-read after potentially slow preflight, immediately before durable admission.
                if checksum(self.policy()) != request['policy_digest'] or int(self.clock()) >= min(
                        request['expires_at'], policy['expires_at']):
                    raise Blocked('authority_changed_during_preflight')
            except Blocked as error:
                record['code'] = str(error)
                journal.save(record)
                return record
            except Exception:
                record['code'] = 'preflight_failed'
                journal.save(record)
                return record
            record.update(state='RUNNING', code='admitted')
            journal.save(record)
        # Intent is durable BEFORE the existing Deployment can alter any host state.
        try:
            backend.execute(request, prepared)
            state, code = 'SUCCEEDED', 'verified'
        except Exception:
            state, code = 'UNCERTAIN', 'operation_unconfirmed'
        with journal.transaction():
            record.update(state=state, code=code, updated_at=int(self.clock()))
            journal.save(record)
        return record

    def drain(self):
        self.layout.check()
        fd = os.open(self.layout.private / 'operator.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        journal = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            key = Ed25519PrivateKey.from_private_bytes(protected_read(
                self.layout.private / 'receipt.key', self.layout.control_uid, private=True, limit=32))
            policy = self.policy()
            if base64.b64encode(key.public_key().public_bytes_raw()).decode() != policy['receipt_public_key']:
                raise Blocked('receipt_key_mismatch')
            path = self.layout.private / 'journal.sqlite'
            marker = self.layout.private / 'journal.created'
            if marker.exists() and not path.exists():
                raise Blocked('journal_missing_requires_owner')
            journal = Journal(path)
            if not marker.exists():
                atomic_receipt(self.layout.private, 'journal.created', {'initialized': True})
            with journal.transaction() as records:
                for record in records.values():
                    if record['state'] == 'RUNNING':
                        journal.save({**record, 'state': 'UNCERTAIN', 'code': 'operator_interrupted',
                                      'updated_at': int(self.clock())})
            completed = 0
            with os.scandir(self.layout.root / 'inbox') as scan:
                entries = sorted(Path(entry.path) for entry in islice(scan, 65))
            if len(entries) > 64:
                raise Blocked('inbox_limit')
            for path in entries:
                if not re.fullmatch(r'[a-f0-9-]{36}\.json', path.name):
                    continue
                # The inbox intentionally accepts writes from the untrusted runner.
                handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(handle, 'rb') as stream:
                    m = os.fstat(stream.fileno())
                    if (not stat.S_ISREG(m.st_mode) or m.st_uid != self.layout.runner_uid
                            or m.st_nlink != 1 or m.st_size > MAX_FILE):
                        raise Blocked('request_file_custody')
                    raw = stream.read(MAX_FILE + 1)
                if len(raw) > MAX_FILE:
                    raise Blocked('request_file_limit')
                request = validate_request(strict_json(raw))
                if path.name != request['operation_id'] + '.json':
                    raise Blocked('request_filename')
                record = self.execute(request, journal, key)
                atomic_receipt(self.layout.root / 'receipts', path.name, signed_receipt(record, key))
                path.unlink()  # Removes only a leaf in the fixed mailbox, never a request-supplied path.
                completed += 1
            return {'processed': completed}
        finally:
            if journal is not None:
                journal.db.close()
            os.close(fd)


def publish(layout, request):
    validate_request(request)
    layout.check(operator=False)
    temporary = layout.root / 'inbox' / ('.request-' + uuid4().hex)
    target = layout.root / 'inbox' / (request['operation_id'] + '.json')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    os.fchmod(fd, 0o644)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(request))
            stream.flush()
            os.fsync(stream.fileno())
        # Never replace an intent with the same ID; retries read its signed receipt.
        os.link(temporary, target, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['drain', 'submit'])
    parser.add_argument('--request-file')
    parser.add_argument('--public-key')
    args = parser.parse_args()
    try:
        os.umask(0o027)
        runner = pwd.getpwnam('acc-gh-runner')
        if runner.pw_uid in {0, 1000, 1001}:
            raise Blocked('runner_role_invalid')
        layout = Layout(Path('/var/lib/acc-operations'), Path('/etc/acc-operations/policy.json'), runner_uid=runner.pw_uid)
        if args.action == 'drain':
            if os.getuid() != 1000:
                raise Blocked('operator_identity')
            print(json.dumps(Channel(layout).drain()))
        else:
            if os.getuid() != runner.pw_uid or not args.request_file or not args.public_key:
                raise Blocked('publisher_identity')
            with open(args.request_file, 'rb') as stream:
                raw = stream.read(MAX_FILE + 1)
            if len(raw) > MAX_FILE:
                raise Blocked('request_file_limit')
            request = validate_request(strict_json(raw))
            receipt = layout.root / 'receipts' / (request['operation_id'] + '.json')
            if not receipt.exists():
                try:
                    publish(layout, request)
                except FileExistsError:
                    pass  # Never rewrites a submitted intent.
            deadline = time.monotonic() + 900
            while not receipt.exists():
                if time.monotonic() >= deadline:
                    raise Blocked('receipt_unconfirmed_no_retry')
                time.sleep(2)
            record = verify_receipt(strict_json(protected_read(receipt, 1000)), request, args.public_key)
            print(json.dumps(record))
            if record['state'] != 'SUCCEEDED':
                raise Blocked('operation_not_verified')
    except Exception:
        parser.exit(1, 'operations_channel_blocked; inspect protected receipts; do not retry an update blindly\n')


if __name__ == '__main__':
    main()
