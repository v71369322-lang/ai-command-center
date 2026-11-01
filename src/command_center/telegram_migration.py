"""Explicit additive migration; never installs code, drops data, or changes deployment receipts."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from sqlalchemy import func, inspect, select, text, UniqueConstraint

from .config import Settings
from .runtime_policy import RuntimeBackend
from .models import (Control, Task, Approval, Outbox, Audit, OwnerSession,
                     ExternalGrant, ExternalAction, TelegramInbox, TelegramDelivery, TelegramCard)
from .recovery import seal, unseal
from .store import Store, Denied, digest
from .telegram_transport import private_read

CORE = (Control, Task, Approval, Outbox, Audit, OwnerSession, ExternalGrant, ExternalAction)
ADDED = (TelegramInbox, TelegramDelivery, TelegramCard)
POSTGRES = 'postgres:16-bookworm@sha256:d81f7b51697014367236d07ec58b54153fc28f828b72bf247fe5c7487520bcb0'


def row_query(model):
    table = model.__table__.alias('t')
    return select(func.to_jsonb(table.table_valued())).order_by(*table.primary_key)


def fingerprints(session):
    session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    return {m.__tablename__: digest(session.execute(row_query(m)).scalars().all()) for m in CORE}


def command(runtime, *args, data=None):
    result = runtime.call(*args, input=data, timeout=60)
    if result.returncode:
        raise Denied('telegram_migration_local_database_command_failed')
    return result.stdout


def restored_fingerprints(dump, runtime):
    """Different, networkless, memory-backed instance. Never restore over primary."""
    name = 'acc-tg-restore-' + uuid4().hex
    def run(*args, data=None):
        return command(runtime, *args, data=data)
    try:
        run('run', '-d', '--pull=never', '--name', name, '--label=acc.scope=telegram-migration-restore',
                '--network=none', '--read-only', '--user=999:999',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=512m', '--cpus=.5',
                '--pids-limit=128', '--tmpfs=/tmp:size=16m,uid=999,gid=999',
                '--tmpfs=/var/run/postgresql:size=8m,uid=999,gid=999,mode=0775',
                '--tmpfs=/var/lib/postgresql/data:size=128m,uid=999,gid=999,mode=0700',
                '--env=POSTGRES_USER=f1_admin', '--env=POSTGRES_DB=f1',
                '--env=POSTGRES_HOST_AUTH_METHOD=trust', POSTGRES)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            ready = runtime.call('exec', name, 'cat', '/proc/1/comm', timeout=5)
            if ready.returncode == 0 and ready.stdout.strip() == b'postgres':
                sql = runtime.call('exec', name, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1',
                                   '-U', 'f1_admin', '-d', 'f1', '-c', 'SELECT 1', timeout=5)
                if sql.returncode == 0 and sql.stdout.strip() == b'1':
                    break
            time.sleep(.2)
        else:
            raise Denied('telegram_migration_restore_not_ready')
        run('exec', '-i', name, 'pg_restore', '-U', 'f1_admin', '-d', 'f1',
                '--exit-on-error', '--no-owner', '--no-acl', data=dump)
        result = {}
        for model in CORE:
            query = str(row_query(model).compile(compile_kwargs={'literal_binds': True}))
            data = run('exec', '--env=PGOPTIONS=-c timezone=UTC', name,
                           'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '-U', 'f1_admin', '-d', 'f1', '-c', query)
            result[model.__tablename__] = digest([json.loads(line) for line in data.decode().splitlines()])
        info = json.loads(run('inspect', name))[0]
        if (info['HostConfig']['NetworkMode'] != 'none' or info['HostConfig']['Privileged']
                or info['HostConfig']['CapDrop'] != ['ALL'] or not info['HostConfig']['ReadonlyRootfs']
                or info['Mounts'] or any((info['NetworkSettings']['Ports'] or {}).values())):
            raise Denied('telegram_migration_restore_isolation_invalid')
        return result
    finally:
        removed = runtime.call('rm', '--force', name, timeout=15)
        remaining = runtime.call('inspect', name, timeout=5)
        healthy = runtime.call('info', '--format={{.ServerVersion}}', timeout=5)
        if not (healthy.returncode == 0 and remaining.returncode != 0
                and (removed.returncode == 0 or b'No such container' in removed.stderr)):
            raise Denied('telegram_migration_restore_cleanup_unconfirmed')


class TelegramMigration:
    def __init__(self, store, runtime=None):
        if store.settings.database_url.username != 'f1_admin':
            raise Denied('telegram_migration_admin_binding_required')
        self.store = store
        self.runtime = runtime or RuntimeBackend(endpoint=f'unix:///run/user/{os.getuid()}/docker.sock')

    @staticmethod
    def check_schema(session, models):
        inspector = inspect(session.connection())
        dialect = session.connection().dialect
        for model in models:
            columns = inspector.get_columns(model.__tablename__)
            expected = model.__table__.columns
            if ({c['name'] for c in columns} != set(expected.keys())
                    or any(c['type'].compile(dialect=dialect) != expected[c['name']].type.compile(dialect=dialect)
                           or c['nullable'] != expected[c['name']].nullable for c in columns)):
                raise Denied('telegram_migration_unexpected_schema')
            table = model.__table__
            if inspector.get_pk_constraint(table.name)['constrained_columns'] != [c.name for c in table.primary_key]:
                raise Denied('telegram_migration_unexpected_primary_key')
            foreign = {(tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns']),
                        f.get('options', {}).get('ondelete')) for f in inspector.get_foreign_keys(table.name)}
            expected_foreign = {(tuple(f.column_keys), f.referred_table.name,
                                tuple(e.column.name for e in f.elements), f.ondelete) for f in table.foreign_key_constraints}
            unique = {tuple(v['column_names']) for v in inspector.get_unique_constraints(table.name)}
            expected_unique = {tuple(c.name for c in v.columns) for v in table.constraints if isinstance(v, UniqueConstraint)}
            if foreign != expected_foreign or unique != expected_unique:
                raise Denied('telegram_migration_unexpected_constraints')

    def preconditions(self, session):
        self.store.check_audit(session)
        control = session.get(Control, 1)
        if not control.halted or session.scalar(select(func.count()).select_from(Task).where(
                Task.state.in_(['RUNNING', 'CANCEL_REQUESTED', 'RECONCILING']))):
            raise Denied('telegram_migration_quiescence_required')
        sessions = session.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                                      "AND usename IN ('f1_app','f1_runtime')"))
        if sessions:
            raise Denied('telegram_migration_stop_application_connections_first')
        if not session.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='f1_app')")):
            raise Denied('telegram_migration_existing_app_role_required')
        self.check_schema(session, CORE)

    def _plan(self, session):
        self.preconditions(session)
        existing = set(inspect(session.connection()).get_table_names())
        if (existing - {m.__tablename__ for m in (*CORE, *ADDED)}
                or inspect(session.connection()).get_view_names()):
            raise Denied('telegram_migration_unexpected_database_objects')
        present = {m.__tablename__ for m in ADDED} & existing
        if present:
            raise Denied('telegram_migration_tables_exist_review_receipt_instead')
        head = session.execute(select(Audit).order_by(Audit.sequence.desc()).limit(1)).scalar_one()
        return {'migration': 'telegram_additive_v1', 'revision': self.store.settings.source_revision,
                'database': self.store.settings.database_url.database,
                'cluster': str(session.scalar(text('SELECT system_identifier FROM pg_control_system()'))),
                'anchor': {'sequence': head.sequence, 'digest': head.digest},
                'preserved': fingerprints(session), 'added_tables': [m.__tablename__ for m in ADDED]}

    def plan(self):
        with self.store.transaction() as session:
            plan = self._plan(session)
            return {'plan': plan, 'plan_digest': digest(plan), 'database_modified': False}

    def apply(self, approved_plan, container, backup_file, key):
        if (not re.fullmatch(r'[a-f0-9]{64}', approved_plan or '') or len(key) != 32
                or not re.fullmatch(r'acc-(?:f1-db-1|f23-db-1|tg-migration-[a-f0-9]{32})', container)):
            raise Denied('telegram_migration_scope_invalid')
        with self.store.transaction() as session:
            self.preconditions(session)
            previous = session.execute(select(Audit).where(
                Audit.event['kind'].as_string() == 'telegram_schema_migrated',
                Audit.event['plan_digest'].as_string() == approved_plan,
                Audit.event['revision'].as_string() == self.store.settings.source_revision)).scalar_one_or_none()
            if previous:
                self.check_schema(session, ADDED)
                return {'state': 'ALREADY_APPLIED', 'plan_digest': approved_plan, 'admission_halted': True}
            plan = self._plan(session)
            if digest(plan) != approved_plan:
                raise Denied('telegram_migration_exact_plan_required')
            self.runtime.preflight()
            cluster = command(self.runtime, 'exec', container, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1',
                              '-U', 'f1_admin', '-d', 'f1', '-c', 'SELECT system_identifier FROM pg_control_system()')
            if cluster.decode().strip() != plan['cluster'] or plan['database'] != 'f1':
                raise Denied('telegram_migration_backup_database_mismatch')
            dump = command(self.runtime, 'exec', container, 'pg_dump', '--format=custom', '--no-owner', '-U', 'f1_admin', '-d', 'f1')
            if len(dump) > 64 * 1024 * 1024:
                raise Denied('telegram_migration_backup_limit')
            manifest = {'plan': plan, 'dump_sha256': hashlib.sha256(dump).hexdigest(),
                        'dump': base64.b64encode(dump).decode()}
            archive = seal(json.dumps(manifest, sort_keys=True).encode(), key)
            path = Path(backup_file)
            if not path.is_absolute() or path.parent.is_symlink():
                raise Denied('telegram_migration_private_backup_path_required')
            parent = path.parent.stat()
            if parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
                raise Denied('telegram_migration_private_backup_directory_required')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as file:
                file.write(archive)
                file.flush()
                os.fsync(file.fileno())
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            checked = json.loads(unseal(private_read(path, 96 * 1024 * 1024), key))
            decoded = base64.b64decode(checked['dump'], validate=True)
            if (checked['plan'] != plan or hashlib.sha256(decoded).hexdigest() != checked['dump_sha256']
                    or restored_fingerprints(decoded, self.runtime) != plan['preserved']):
                raise Denied('telegram_migration_backup_or_restore_mismatch')
            for model in ADDED:
                model.__table__.create(session.connection(), checkfirst=False)
            session.execute(text('REVOKE ALL ON telegram_inbox,telegram_cards,telegram_deliveries FROM PUBLIC'))
            session.execute(text('GRANT SELECT,INSERT,UPDATE ON telegram_inbox,telegram_cards,telegram_deliveries TO f1_app'))
            if session.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='f1_runtime')")):
                session.execute(text('REVOKE ALL ON telegram_inbox,telegram_cards,telegram_deliveries FROM f1_runtime'))
            self.check_schema(session, ADDED)
            if fingerprints(session) != plan['preserved']:
                raise Denied('telegram_migration_existing_data_changed')
            receipt = {'state': 'APPLIED', 'plan_digest': approved_plan, 'backup_sha256': hashlib.sha256(archive).hexdigest(),
                       'preserved': plan['preserved'], 'restore_verified': True, 'admission_halted': True,
                       'offsite_verified': False, 'deployment_authorized': False}
            self.store.audit(session, 'telegram_schema_migrated', 'migration_operator', **receipt)
            return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'apply'])
    parser.add_argument('--approved-plan')
    parser.add_argument('--container')
    parser.add_argument('--backup-file')
    parser.add_argument('--key-file')
    args = parser.parse_args()
    store = None
    try:
        store = Store(Settings.load())
        migration = TelegramMigration(store)
        if args.action == 'plan':
            result = migration.plan()
        else:
            if not all((args.approved_plan, args.container, args.backup_file, args.key_file)):
                raise Denied('telegram_migration_explicit_scope_required')
            key = bytes.fromhex(private_read(args.key_file, 128).decode().strip())
            result = migration.apply(args.approved_plan, args.container, args.backup_file, key)
        print(json.dumps(result, sort_keys=True))
    except Exception:
        parser.exit(1, 'telegram_migration_failed_closed; no deployment or destructive rollback performed\n')
    finally:
        if store:
            store.engine.dispose()


if __name__ == '__main__':
    main()
