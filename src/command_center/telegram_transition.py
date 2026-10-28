"""Exact, local 4cc6ec4 -> Telegram-schema transition. No live connection or SSH.

The generic updater continues to reject schema changes. This operator command
first installs the code with Telegram DISABLED; live binding is a later, separate
exact-bundle update. Migration response loss never triggers a DDL retry.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from sqlalchemy import URL, select, text

from .config import Settings, secret
from .deployment import Deployment, load_bundle
from .deployment_profile import PROJECT, atomic_json, checksum, services
from .models import Audit
from .recovery import unseal
from .runtime_policy import RuntimeBackend
from .store import Denied, Store, digest
from .telegram_migration import ADDED, CORE, TelegramMigration, fingerprints, row_query

OLD_REVISION = '4cc6ec46bf461d65958f013bb23ac2234b9a7fd3'
OLD_SCHEMA = 'fde2dffdff0dacd1e1b46e97a747962c5b5a44f9cbd2076c969efd3f8d03378a'
NEW_SCHEMA = '4039930b4d9b11fe7bf0aad046bcb47b29397a25aa41a6b878145ed60056276a'
JOB = PROJECT + '-telegram-migration'


def protected_bytes(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > limit):
            raise ValueError('telegram_transition_file_custody_invalid')
        return stream.read(limit + 1)


def migration_job(store, action, approved=None, key=None, directory=None, runtime=None, *, container=PROJECT + '-db-1'):
    """Fixed trusted maintenance operations; never reachable from agent or API."""
    migration = TelegramMigration(store, runtime=runtime)
    if action == 'plan':
        return migration.plan()
    if action == 'abort':
        with store.transaction() as session:
            migration._plan(session)  # No added table or application session may exist.
            store.audit(session, 'telegram_transition_aborted_before_ddl', 'migration_operator')
        return {'unmigrated': True}
    if not approved or len(approved) != 64 or any(c not in '0123456789abcdef' for c in approved):
        raise ValueError('telegram_transition_plan_required')
    archive = Path(directory) / ('before-telegram-' + approved + '.enc')
    if action == 'apply':
        return migration.apply(approved, container, archive, key)
    if action != 'verify':
        raise ValueError('telegram_transition_action_forbidden')
    raw = protected_bytes(archive, 96 * 1024 * 1024)
    backup = json.loads(unseal(raw, key))
    plan = backup['plan']
    if digest(plan) != approved or plan['revision'] != store.settings.source_revision:
        raise Denied('telegram_transition_backup_plan_mismatch')
    with store.transaction() as session:
        migration.preconditions(session)
        migration.check_schema(session, ADDED)
        receipt = session.execute(select(Audit).where(
            Audit.event['kind'].as_string() == 'telegram_schema_migrated',
            Audit.event['plan_digest'].as_string() == approved,
            Audit.event['revision'].as_string() == store.settings.source_revision,
        )).scalar_one_or_none()
        if (receipt is None or receipt.event.get('restore_verified') is not True
                or receipt.event.get('deployment_authorized') is not False
                or receipt.event.get('backup_sha256') != hashlib.sha256(raw).hexdigest()
                or str(session.scalar(text('SELECT system_identifier FROM pg_control_system()'))) != plan['cluster']):
            raise Denied('telegram_transition_migration_receipt_unverified')
        current = fingerprints(session)
        if any(current[m.__tablename__] != plan['preserved'][m.__tablename__] for m in CORE if m is not Audit):
            raise Denied('telegram_transition_preserved_state_changed')
        prefix = session.execute(row_query(Audit).where(
            text('t.sequence <= :anchor')),
            {'anchor': plan['anchor']['sequence']}).scalars().all()
        if digest(prefix) != plan['preserved']['audit']:
            raise Denied('telegram_transition_audit_prefix_changed')
        return {'migration_verified': True, 'plan_digest': approved, 'live_enabled': False}


class TelegramTransition:
    def __init__(self, deployment):
        self.current = deployment
        self.root = deployment.root
        self.journal = self.root / 'telegram-transition.json'

    @contextmanager
    def locked(self, approval):
        if approval != checksum(self.current.bundle) or 'telegram' in self.current.m:
            raise ValueError('telegram_transition_exact_disabled_bundle_required')
        self.current.preflight()
        fd = os.open(self.root / 'deployment.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.current.engine.run('ps', '-aq', '--filter', 'name=^' + JOB + '$').strip():
                raise ValueError('telegram_transition_maintenance_job_unresolved')
            yield
        finally:
            os.close(fd)

    def job(self, action, approved=None):
        backup = self.root / 'backups/telegram'
        backup.mkdir(mode=0o700, exist_ok=True)
        if backup.is_symlink() or backup.stat().st_uid != os.getuid() or backup.stat().st_mode & 0o077:
            raise ValueError('telegram_transition_backup_directory_invalid')
        args = ['run', '--rm', '--name', JOB, '--network', PROJECT + '_control', '--read-only',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user=0:0',
                '--memory=256m', '--cpus=.5', '--pids-limit=64', '--tmpfs=/tmp:size=16m',
                '--log-driver=local', '--log-opt=max-size=1m', '--log-opt=max-file=2']
        env = {'F1_DB_HOST': 'db', 'F1_DB_PASSWORD_FILE': '/run/secrets/db_admin_password',
               'F1_SOURCE_REVISION': self.current.m['revision']}
        mounts = [(self.root / 'secrets/db_admin_password', '/run/secrets/db_admin_password', True)]
        if action in {'apply', 'verify'}:
            mounts += [(self.root / 'secrets/backup_key', '/run/secrets/backup_key', True),
                       (backup, '/var/lib/telegram-backups', action == 'verify')]
        if action == 'apply':
            mounts.append((Path(self.current.engine.endpoint.removeprefix('unix://')), '/var/run/docker.sock', False))
        for name, value in env.items():
            args += ['--env', name + '=' + value]
        for source, target, readonly in mounts:
            args += ['--mount', f'type=bind,src={source},dst={target}' + (',readonly' if readonly else '')]
        args += [self.current.m['images']['broker'], 'python', '-m', 'command_center.telegram_transition',
                 'job', '--job-action', action]
        if approved:
            args += ['--approved-plan', approved]
        return json.loads(self.current.engine.run(*args))

    def stage(self, approval, previous_approval):
        with self.locked(approval):
            if self.journal.exists():
                completed = json.loads(protected_bytes(self.journal, 96 * 1024))
                if completed.get('phase') != 'ABORTED_BEFORE_DDL' or completed.get('target') != approval:
                    raise ValueError('telegram_transition_exists_reconcile_instead')
                history = self.root / 'telegram-transition-history'
                history.mkdir(mode=0o700, exist_ok=True)
                if history.is_symlink() or history.stat().st_uid != os.getuid() or history.stat().st_mode & 0o077:
                    raise ValueError('telegram_transition_history_custody_invalid')
                path = history / (checksum(completed) + '.json')
                if path.exists():
                    if json.loads(protected_bytes(path, 96 * 1024)) != completed:
                        raise ValueError('telegram_transition_history_changed')
                else:
                    atomic_json(path, completed)
            previous = json.loads(protected_bytes(self.root / 'deployment.json', 32768))
            old_bundle = load_bundle(previous['directory'])
            old = Deployment(old_bundle, previous['directory'], self.current.engine, self.current.execution)
            m, before = self.current.m, old.m
            if (previous.get('phase') != 'VERIFIED' or previous['bundle'] != previous_approval
                    or checksum(old_bundle) != previous_approval or before['revision'] != OLD_REVISION
                    or previous.get('revision') != OLD_REVISION or before['migration_hash'] != OLD_SCHEMA
                    or previous.get('migration_hash') != OLD_SCHEMA or m['migration_hash'] != NEW_SCHEMA
                    or any(m[k] != before[k] for k in ('data_root', 'control_uid', 'execution_uid',
                                                      'database_image', 'redis_image'))
                    or m.get('owner_login') != before.get('owner_login') or not m.get('owner_login')):
                raise ValueError('telegram_transition_baseline_or_scope_mismatch')
            old.preflight()
            old.quiesce()
            old.backup()
            journal = {'phase': 'STAGING', 'previous': previous, 'target': approval,
                       'revision': m['revision'], 'issued_at': datetime.now(timezone.utc).isoformat()}
            atomic_json(self.journal, journal)
            atomic_json(self.root / 'deployment.json', {**previous, 'phase': 'TELEGRAM_MIGRATION_PENDING',
                                                       'target_bundle': approval})
            old.compose('stop', *sorted(services(before) - {'db', 'redis'}))
            plan = self.job('plan')
            atomic_json(self.journal, {**journal, 'phase': 'PLAN_READY', **plan})
            return {'state': 'AWAITING_EXACT_MIGRATION_APPROVAL', **plan, 'go_live': False,
                    'approval_expires_at': (datetime.fromisoformat(journal['issued_at']) + timedelta(minutes=15)).isoformat()}

    def pending(self, *, allow_unstaged=False):
        value = json.loads(protected_bytes(self.journal, 96 * 1024))
        state = json.loads(protected_bytes(self.root / 'deployment.json', 32768))
        staged = (state.get('phase') == 'TELEGRAM_MIGRATION_PENDING'
                  and state.get('target_bundle') == value['target'] and state['bundle'] == value['previous']['bundle'])
        untouched = allow_unstaged and value['phase'] == 'STAGING' and state == value['previous']
        if (value['target'] != checksum(self.current.bundle) or value['revision'] != self.current.m['revision']
                or not (staged or untouched)):
            raise ValueError('telegram_transition_receipt_mismatch')
        return value

    def apply(self, approval, approved_plan):
        with self.locked(approval):
            value = self.pending()
            if value['phase'] != 'PLAN_READY' or value.get('plan_digest') != approved_plan:
                raise ValueError('telegram_transition_exact_plan_or_reconciliation_required')
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(value['issued_at'])).total_seconds()
            if not 0 <= age <= 900:
                raise ValueError('telegram_transition_plan_approval_expired')
            value['phase'] = 'MIGRATING'
            atomic_json(self.journal, value)
            self.job('apply', approved_plan)
            value['phase'] = 'MIGRATED'
            atomic_json(self.journal, value)
            return self.finish(value)

    def reconcile(self, approval):
        with self.locked(approval):
            state = json.loads(protected_bytes(self.root / 'deployment.json', 32768))
            journal = json.loads(protected_bytes(self.journal, 96 * 1024))
            if (state.get('phase') == 'VERIFIED' and state.get('bundle') == approval
                    and state.get('revision') == self.current.m['revision']
                    and state.get('migration_hash') == NEW_SCHEMA
                    and journal['target'] == approval and journal['revision'] == self.current.m['revision']
                    and journal['phase'] in {'STARTING', 'VERIFIED'}
                    and state.get('telegram_migration_plan') == journal['plan_digest']
                    and state.get('previous_bundle') == journal['previous']['bundle']):
                result = self.current.postcheck()
                atomic_json(self.journal, {**journal, 'phase': 'VERIFIED'})
                return {**result, 'telegram_schema_verified': True, 'telegram_live_enabled': False}
            value = self.pending()
            if value['phase'] not in {'MIGRATING', 'MIGRATED', 'STARTING'}:
                raise ValueError('telegram_transition_not_ambiguous')
            self.current.compose('stop', *sorted(services(self.current.m) - {'db', 'redis'}))
            return self.finish(value)  # Verification only; never replays apply.

    def finish(self, value):
        self.job('verify', value['plan_digest'])
        value['phase'] = 'STARTING'
        atomic_json(self.journal, value)
        self.current.compose('up', '-d', '--no-build', '--pull', 'never')
        deadline = time.monotonic() + 30
        while True:
            try:
                result = self.current.postcheck()
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.5)
        m = self.current.m
        atomic_json(self.root / 'deployment.json', {
            'phase': 'VERIFIED', 'bundle': value['target'], 'revision': m['revision'],
            'migration_hash': m['migration_hash'], 'database_image': m['database_image'],
            'previous_bundle': value['previous']['bundle'], 'directory': str(self.current.directory.resolve()),
            'checks': result, 'telegram_migration_plan': value['plan_digest']})
        atomic_json(self.journal, {**value, 'phase': 'VERIFIED'})
        return {**result, 'telegram_schema_verified': True, 'telegram_live_enabled': False}

    def abort(self, approval):
        with self.locked(approval):
            value = self.pending(allow_unstaged=True)
            self.current.compose('stop', *sorted(services(self.current.m) - {'db', 'redis'}))
            self.job('abort')  # Cannot succeed after any Telegram table exists.
            previous = value['previous']
            old = Deployment(load_bundle(previous['directory']), previous['directory'],
                             self.current.engine, self.current.execution)
            old.preflight()
            atomic_json(self.root / 'deployment.json', previous)
            result = old._boot_locked()
            atomic_json(self.journal, {**value, 'phase': 'ABORTED_BEFORE_DDL'})
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'apply', 'reconcile', 'abort', 'job'])
    parser.add_argument('--bundle')
    parser.add_argument('--approved-bundle')
    parser.add_argument('--approved-previous')
    parser.add_argument('--approved-plan')
    parser.add_argument('--job-action', choices=['plan', 'apply', 'verify', 'abort'])
    args = parser.parse_args()
    store = None
    try:
        if args.action == 'job':
            url = URL.create('postgresql+psycopg', username='f1_admin', password=secret('F1_DB_PASSWORD_FILE'),
                             host='db', database='f1')
            # Unused Redis field; this trusted job only connects to PostgreSQL.
            settings = Settings(database_url=url, redis_url='', redis_password='', identities={},  # nosec B106
                                source_revision=os.environ['F1_SOURCE_REVISION'])
            store = Store(settings)
            key = (bytes.fromhex(protected_bytes('/run/secrets/backup_key', 128).decode().strip())
                   if args.job_action in {'apply', 'verify'} else None)
            result = migration_job(store, args.job_action, args.approved_plan, key,
                                   '/var/lib/telegram-backups', RuntimeBackend())
        else:
            if not args.bundle or not args.approved_bundle:
                raise ValueError('telegram_transition_explicit_release_required')
            transition = TelegramTransition(Deployment(load_bundle(args.bundle), args.bundle))
            if args.action == 'stage':
                result = transition.stage(args.approved_bundle, args.approved_previous)
            elif args.action == 'apply':
                result = transition.apply(args.approved_bundle, args.approved_plan)
            else:
                result = getattr(transition, args.action)(args.approved_bundle)
        print(json.dumps(result, sort_keys=True))
    except Exception:
        parser.exit(1, 'telegram_transition_unconfirmed; inspect local receipts; do not repeat DDL or edit deployment state\n')
    finally:
        if store:
            store.engine.dispose()


if __name__ == '__main__':
    main()
