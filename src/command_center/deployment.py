"""Future authorized LOCAL rootless deployment. No SSH or external API client.

prepare/inspect are non-deploying. install/update/rollback require an exact bundle
digest and local operator authorization. No command removes volumes or restores
over the authoritative database. External integrations and owner access stay shut.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import secrets
import shutil
import stat
import subprocess
import time
from uuid import uuid4

from psycopg import sql

from .deployment_profile import PROJECT, SECRETS, SERVICES, atomic_json, checksum, render, validate_manifest, validate_profile
from .local_docker import environment
from .recovery import seal, unseal
from .runtime_ledger import RuntimeLedger


def initialize_state(root):
    root = Path(root)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError('absolute_private_state_required')
    root.mkdir(mode=0o700)  # never replace existing secrets or state
    for directory in ('secrets', 'backups', 'broker-socket', 'runtime-ledger', 'identity'):
        (root / directory).mkdir(mode=0o700)
    for name in SECRETS | {'backup_key'}:
        value = (json.dumps({r: secrets.token_urlsafe(32) for r in ('owner', 'operator', 'agent')})
                 if name == 'identities' else secrets.token_hex(32) if name == 'backup_key' else secrets.token_urlsafe(32))
        fd = os.open(root / 'secrets' / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as file:
            file.write(value)
    atomic_json(root / 'identity/public-jwks.json', {'keys': []})


class Engine:
    def __init__(self, uid):
        self.uid = uid
        self.endpoint = f'unix:///run/user/{uid}/docker.sock'

    def run(self, *args, data=None, timeout=120):
        result = subprocess.run(['docker', '--host=' + self.endpoint, *args], env=environment(),
                                input=data, capture_output=True, timeout=timeout, check=False)
        if result.returncode:
            # Docker stderr can contain mounted secret names, queries or daemon data.
            raise RuntimeError('local_runtime_command_failed:' + args[0])
        return result.stdout

    def json(self, *args):
        return json.loads(self.run(*args))

    def preflight(self):
        path = Path(self.endpoint.removeprefix('unix://'))
        metadata = path.stat()
        if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != self.uid:
            raise ValueError('rootless_socket_identity_invalid')
        info = self.json('info', '--format', '{{json .}}')
        options = info.get('SecurityOptions', [])
        if (not any('rootless' in v for v in options) or info.get('CgroupVersion') != '2'
                or not all(info.get(k) for k in ('MemoryLimit', 'PidsLimit', 'CpuCfsQuota'))):
            raise ValueError('rootless_cgroup_limits_required')


def migration_hash(source):
    return checksum({p: hashlib.sha256((source / 'src/command_center' / p).read_bytes()).hexdigest()
                     for p in ('models.py', 'admin.py')})


def source_check(m):
    source = Path(m['source_root'])
    for args, expected in [(('rev-parse', 'HEAD'), m['revision']), (('status', '--porcelain'), '')]:
        result = subprocess.run(['git', '-C', str(source), *args], capture_output=True, check=True, timeout=10)
        if result.stdout.decode().strip() != expected:
            raise ValueError('source_checkout_changed')
    if migration_hash(source) != m['migration_hash']:
        raise ValueError('migration_source_changed')


def image_check(engine, images, revision):
    for image in set(images.values()):
        rows = engine.json('image', 'inspect', image)
        if len(rows) != 1 or rows[0]['Id'] != image or (rows[0]['Config'].get('Labels') or {}).get(
                'org.opencontainers.image.revision') != revision:
            raise ValueError('release_image_revision_mismatch')


def prepare(source, directory, control_uid, execution_uid, data_root):
    source = Path(source).resolve()
    engine = Engine(control_uid)
    # config does not start containers. Keep all input paths in the exact checkout.
    env = environment()
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    env.update(F1_SOURCE_REVISION=revision, F1_RUNTIME_UID=str(control_uid), F1_RUNTIME_GID=str(control_uid),
               F1_DOCKER_GID='0')
    result = subprocess.run(['docker', '--host=' + engine.endpoint, 'compose', '--profile', 'worker', '-f', str(source / 'compose.yaml'),
                             'config', '--format', 'json'], env=env, capture_output=True, check=True)
    base = json.loads(result.stdout)
    tags = {'api': 'acc-f1-app:local', 'worker': 'acc-f1-worker:local', 'broker': 'acc-f1-broker:local',
            'executor': 'acc-f1-executor:local', 'coding': 'acc-f2-executor:local'}
    images = {key: engine.json('image', 'inspect', tag)[0]['Id'] for key, tag in tags.items()}
    manifest = dict(schema=1, revision=revision, images=images, database_image=base['services']['db']['image'],
                    redis_image=base['services']['redis']['image'], migration_hash=migration_hash(source),
                    control_uid=control_uid, execution_uid=execution_uid, data_root=str(Path(data_root).resolve()),
                    source_root=str(source))
    source_check(manifest)
    image_check(engine, images, revision)
    bundle = {'manifest': manifest, 'compose': render(base, manifest)}
    directory = Path(directory)
    directory.mkdir(mode=0o700)  # never overwrite an existing release
    atomic_json(directory / 'bundle.json', bundle)
    atomic_json(directory / 'compose.json', bundle['compose'])
    return checksum(bundle)


def load_bundle(directory):
    directory = Path(directory)
    for path in (directory, directory / 'bundle.json', directory / 'compose.json'):
        if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
            raise ValueError('release_custody_invalid')
    bundle = json.loads((directory / 'bundle.json').read_text())
    validate_manifest(bundle['manifest'])
    validate_profile(bundle['compose'], bundle['manifest'])
    if json.loads((directory / 'compose.json').read_text()) != bundle['compose']:
        raise ValueError('rendered_profile_changed')
    return bundle


class Deployment:
    def __init__(self, bundle, directory, engine=None, execution=None):
        self.bundle, self.m, self.directory = bundle, bundle['manifest'], Path(directory)
        self.engine = engine or Engine(self.m['control_uid'])
        self.execution = execution or Engine(self.m['execution_uid'])
        self.root = Path(self.m['data_root'])

    def compose(self, *args):
        return self.engine.run('compose', '--project-name', PROJECT, '-f', str(self.directory / 'compose.json'), *args)

    def preflight(self, *, fresh=False):
        if os.getuid() != self.m['control_uid']:
            raise ValueError('dedicated_control_user_required')
        self.engine.preflight()
        self.execution.preflight()
        image_check(self.engine, {k: v for k, v in self.m['images'].items() if k not in {'executor', 'coding'}}, self.m['revision'])
        image_check(self.execution, {k: v for k, v in self.m['images'].items() if k in {'executor', 'coding'}}, self.m['revision'])
        if fresh:
            source_check(self.m)
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 8000))
        for name in (*SECRETS, 'backup_key'):
            path = self.root / 'secrets' / name
            info = path.stat()
            if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('protected_secret_binding_required')
        if (self.root.stat().st_mode & 0o077) or self.root.is_symlink():
            raise ValueError('private_data_directory_required')
        self.compose('config', '--quiet')

    def tool(self, code):
        # Explicit trusted maintenance job, not a coding executor. Never gets a socket.
        args = ['run', '--rm', '--network', PROJECT + '_control', '--read-only', '--cap-drop=ALL',
                '--security-opt=no-new-privileges', '--user=0:0', '--memory=256m', '--cpus=.5', '--pids-limit=64',
                '--tmpfs=/tmp:rw,nosuid,nodev,size=16m']
        env = dict(F1_DB_USER='f1_admin', F1_DB_HOST='db', F1_DB_PASSWORD_FILE='/run/secrets/db_admin_password',
                   F1_APP_PASSWORD_FILE='/run/secrets/db_password', F1_RUNTIME_PASSWORD_FILE='/run/secrets/db_runtime_password',
                   F1_IDENTITIES_FILE='/run/secrets/identities', F1_REDIS_PASSWORD_FILE='/run/secrets/redis_password',
                   F1_REDIS_URL='redis://redis:6379/0', F1_SOURCE_REVISION=self.m['revision'])
        for key, value in env.items():
            args += ['--env', key + '=' + value]
        for name in SECRETS - {'broker_token'}:
            args += ['--mount', f'type=bind,src={self.root}/secrets/{name},dst=/run/secrets/{name},readonly']
        return self.engine.run(*args, self.m['images']['api'], 'python', '-c', code)

    def quiesce(self):
        self.tool("from command_center.config import Settings;from command_center.store import Store;"
                  "Store(Settings.load()).halt('owner')")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            raw = self.tool("from command_center.config import Settings;from command_center.store import Store;"
                            "s=Store(Settings.load());s.checkpoint();"
                            "print(sum(t['state'] in {'RUNNING','CANCEL_REQUESTED','RECONCILING'} for t in s.snapshot()['tasks']))")
            if raw.strip() == b'0':
                ledger = RuntimeLedger(self.root / 'runtime-ledger/ledger.sqlite')
                ledger.verify()
                if not ledger.runs():
                    # Control-plane absence is insufficient: prove no external jobs remain.
                    active = self.execution.run('ps', '-aq')
                    if active.strip():
                        raise ValueError('execution_runtime_not_empty')
                    return
            time.sleep(.5)
        raise ValueError('unresolved_execution_blocks_update')

    def backup(self):
        checkpoint = json.loads(self.tool('import json;from command_center.config import Settings;'
            'from command_center.store import Store;print(json.dumps(Store(Settings.load()).checkpoint()))'))
        dump = self.engine.run('exec', PROJECT + '-db-1', 'pg_dump', '-U', 'f1_admin', '-d', 'f1', '-Fc', '--no-owner')
        if not dump or len(dump) > 64 * 1024 * 1024:
            raise ValueError('synthetic_backup_size_limit')
        payload = {'schema': 1, 'bundle': checksum(self.bundle), 'created_at': datetime.now(timezone.utc).isoformat(),
                   'checkpoint': checkpoint, 'dump_sha256': hashlib.sha256(dump).hexdigest()}
        key = bytes.fromhex((self.root / 'secrets/backup_key').read_text().strip())
        archive = seal(json.dumps(payload).encode() + b'\n' + dump, key)
        directory = self.root / 'backups'
        directory.mkdir(mode=0o700, exist_ok=True)
        if (sum(p.stat().st_size for p in directory.iterdir() if p.is_file()) + len(archive) > 256 * 1024 * 1024
                or shutil.disk_usage(directory).free < 1024 * 1024 * 1024):
            raise ValueError('backup_quota_or_disk_reserve')
        path = directory / ('backup_' + uuid4().hex + '.enc')
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as file:
            file.write(archive)
            file.flush()
            os.fsync(file.fileno())
        self.verify_backup(path)
        atomic_json(directory / 'latest.json', {**payload, 'file': path.name, 'offsite_verified': False})
        return path

    def verify_backup(self, path):
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > 65 * 1024 * 1024:
            raise ValueError('backup_file_invalid')
        key = bytes.fromhex((self.root / 'secrets/backup_key').read_text().strip())
        header, dump = unseal(path.read_bytes(), key).split(b'\n', 1)
        manifest = json.loads(header)
        if manifest['schema'] != 1 or hashlib.sha256(dump).hexdigest() != manifest['dump_sha256']:
            raise ValueError('backup_checksum_invalid')
        return manifest, dump

    def backup_status(self):
        receipt = json.loads((self.root / 'backups/latest.json').read_text())
        if Path(receipt['file']).name != receipt['file']:
            raise ValueError('backup_receipt_path_invalid')
        manifest, _ = self.verify_backup(self.root / 'backups' / receipt['file'])
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(manifest['created_at'])).total_seconds()
        return {'state': 'VERIFIED_LOCAL' if 0 <= age <= 900 else 'STALE_OR_CLOCK_ERROR',
                'age_seconds': age, 'offsite_verified': False, 'rpo_proven': False}

    def restore_check(self, path):
        """Always a new, networkless tmpfs target. No restore-over-primary API."""
        manifest, dump = self.verify_backup(path)
        name = PROJECT + '-restore-' + uuid4().hex
        try:
            self.engine.run('run', '-d', '--name', name, '--network=none', '--memory=512m', '--cpus=.5',
                            '--pids-limit=128', '--tmpfs=/var/lib/postgresql/data:size=128m',
                            '--env=POSTGRES_USER=f1_admin', '--env=POSTGRES_DB=restore_drill',
                            '--env=POSTGRES_HOST_AUTH_METHOD=trust', self.m['database_image'])
            deadline = time.monotonic() + 30
            while True:
                try:
                    if self.engine.run('exec', name, 'cat', '/proc/1/comm').strip() == b'postgres':
                        self.engine.run('exec', name, 'pg_isready', '-U', 'f1_admin', '-d', 'restore_drill')
                        break
                except RuntimeError:
                    pass
                if time.monotonic() > deadline:
                    raise ValueError('restore_target_not_ready')
                time.sleep(.3)
            self.engine.run('exec', '-i', name, 'pg_restore', '-U', 'f1_admin', '-d', 'restore_drill',
                            '--exit-on-error', '--no-owner', '--no-acl', data=dump)

            def query(statement):
                return self.engine.run('exec', name, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U',
                                       'f1_admin', '-d', 'restore_drill', '-Atc', statement).decode().strip()

            rows = json.loads(query('SELECT json_agg(r ORDER BY sequence) FROM '
                                    '(SELECT sequence,event,previous,digest FROM audit) r'))
            previous, anchored = '0' * 64, False
            for row in rows:
                if row['previous'] != previous or row['digest'] != checksum({'previous': previous, 'event': row['event']}):
                    raise ValueError('restored_audit_invalid')
                if row['sequence'] == manifest['checkpoint']['sequence']:
                    anchored = row['digest'] == manifest['checkpoint']['digest']
                previous = row['digest']
            if not anchored:
                raise ValueError('restored_checkpoint_missing')
            # This target can never execute jobs, even if later inspected on a network.
            query("BEGIN; UPDATE control SET halted=true,recovery=true,epoch=epoch+1; "
                  "UPDATE approvals SET revoked=true; UPDATE owner_sessions SET revoked=true; "
                  "UPDATE tasks SET state='RECONCILING' WHERE state NOT IN "
                  "('SUCCEEDED','FAILED','CANCELLED','SECURITY_BLOCKED','CANCEL_REQUESTED'); COMMIT;")
            event = {'kind': 'deployment_isolated_restore_interlock', 'actor': 'recovery', 'task_id': None,
                     'time': datetime.now(timezone.utc).isoformat(), 'revision': self.m['revision']}
            query(sql.SQL('INSERT INTO audit(event,previous,digest) VALUES ({}::jsonb,{},{});').format(
                sql.Literal(json.dumps(event)), sql.Literal(previous),
                sql.Literal(checksum({'previous': previous, 'event': event}))).as_string())
            if query('SELECT halted AND recovery FROM control WHERE id=1') != 't':
                raise ValueError('restore_interlock_missing')
            metadata = self.engine.json('inspect', name)[0]
            if metadata['HostConfig']['NetworkMode'] != 'none' or metadata['HostConfig'].get('PortBindings'):
                raise ValueError('restore_isolation_invalid')
            return {'restore': 'VERIFIED_DISPOSABLE', 'primary_modified': False, 'audit_anchor_verified': True,
                    'offsite_verified': False, 'rpo_rto_proven': False}
        finally:
            self.engine.run('rm', '--force', name)

    def boot(self):
        self.preflight()
        state = json.loads((self.root / 'deployment.json').read_text())
        if state.get('phase') != 'VERIFIED' or state['bundle'] != checksum(self.bundle):
            raise ValueError('boot_only_verified_release')
        self.compose('up', '-d', '--no-build', '--pull', 'never', '--wait', 'db', 'redis')
        # A reboot is not consent to resume cancelled/uncertain work.
        self.tool("from command_center.config import Settings;from command_center.store import Store;"
                  "Store(Settings.load()).halt('owner')")
        self.compose('up', '-d', '--no-build', '--pull', 'never')
        return {'state': 'BOOTED_ADMISSION_HALTED', 'go_live': False}

    def postcheck(self):
        # Does not require an owner assertion or manufacture a session/MFA claim.
        self.tool('from command_center.config import Settings;from command_center.store import Store;'
                  'from command_center.worker import broker;s=Settings.load();Store(s).checkpoint();assert broker(s).ping()')
        for name in SERVICES:
            metadata = self.engine.json('inspect', PROJECT + '-' + name + '-1')[0]
            if not metadata['State']['Running']:
                raise ValueError('service_not_running:' + name)
        self.engine.run('exec', PROJECT + '-watchdog-1', 'python', '-c',
            'import os;from command_center.runtime_ledger import RuntimeLedger;'
            'l=RuntimeLedger(os.environ["F1_RUNTIME_LEDGER"]);l.verify();assert l.watchdog_ready()')
        return {'state': 'CLOSED_SYNTHETIC_SERVICES_RUNNING', 'owner_mfa_verified': False,
                'rootless_execution_smoke_verified': False, 'offsite_verified': False, 'go_live': False}

    def apply(self, action, approval):
        if action not in {'install', 'update', 'rollback'} or approval != checksum(self.bundle):
            raise ValueError('exact_release_authorization_required')
        self.preflight(fresh=action == 'install')
        lock = os.open(self.root / 'deployment.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state_file = self.root / 'deployment.json'
            previous = json.loads(state_file.read_text()) if state_file.exists() else None
            if previous and previous.get('phase') != 'VERIFIED' and not (
                    action == 'rollback' and previous.get('phase') == 'INTENT'):
                raise ValueError('incomplete_deployment_requires_investigation')
            if (action == 'install') != (previous is None):
                raise ValueError('installation_state_mismatch')
            if action == 'install' and self.engine.run('volume', 'ls', '-q', '--filter', 'name=^acc-f23-pgdata$').strip():
                raise ValueError('existing_data_volume_requires_investigation')
            if previous and (previous['migration_hash'] != self.m['migration_hash']
                             or previous['database_image'] != self.m['database_image']):
                raise ValueError('database_change_requires_separate_migration_plan')
            if action == 'rollback' and previous['previous_bundle'] != checksum(self.bundle):
                raise ValueError('only_verified_predecessor_rollback_allowed')
            if previous:
                self.quiesce()
                self.backup()
                self.compose('stop', 'api', 'worker', 'runtime-broker', 'watchdog')
            intent = {'phase': 'INTENT', 'bundle': checksum(self.bundle), 'revision': self.m['revision'],
                      'migration_hash': self.m['migration_hash'], 'database_image': self.m['database_image'],
                      'previous_bundle': previous['bundle'] if previous and previous['phase'] == 'VERIFIED' else None,
                      'directory': str(self.directory.resolve())}
            atomic_json(state_file, intent)
            self.compose('up', '-d', '--no-build', '--pull', 'never', '--wait', 'db', 'redis')
            if action == 'install':
                self.tool('from command_center.admin import main;main()')
                self.tool("from command_center.config import Settings;from command_center.store import Store;"
                          "Store(Settings.load()).halt('owner')")
            # Never automatically resume admission, approvals or in-flight tasks.
            self.compose('up', '-d', '--no-build', '--pull', 'never')
            deadline = time.monotonic() + 30
            while True:
                try:
                    result = self.postcheck()
                    break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.5)
            atomic_json(state_file, {**intent, 'phase': 'VERIFIED', 'checks': result})
            return result
        finally:
            os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init-state', 'prepare', 'inspect', 'boot', 'install', 'update', 'rollback', 'backup', 'backup-status', 'verify-backup', 'restore-check', 'postcheck'])
    parser.add_argument('--bundle')
    parser.add_argument('--active-state')
    parser.add_argument('--source', default='.')
    parser.add_argument('--data-root')
    parser.add_argument('--control-uid', type=int)
    parser.add_argument('--execution-uid', type=int)
    parser.add_argument('--approved-bundle')
    parser.add_argument('--backup-file')
    args = parser.parse_args()
    if args.action == 'init-state':
        initialize_state(args.data_root)
        print('Private synthetic state initialized; no external credentials generated or displayed.')
        return
    if args.active_state:
        if args.action not in {'boot', 'backup', 'backup-status'} or args.bundle:
            parser.error('active-state only selects a verified boot/backup release')
        state_path = Path(args.active_state) / 'deployment.json'
        if state_path.is_symlink() or state_path.stat().st_uid != os.getuid() or state_path.stat().st_mode & 0o077:
            raise ValueError('active_state_custody_invalid')
        state = json.loads(state_path.read_text())
        if state['phase'] != 'VERIFIED':
            raise ValueError('active_state_incomplete')
        args.bundle = state['directory']
    if not args.bundle:
        parser.error('--bundle required')
    if args.action == 'prepare':
        if None in (args.control_uid, args.execution_uid, args.data_root):
            parser.error('prepare requires both UIDs and data root')
        print(json.dumps({'bundle_digest': prepare(args.source, args.bundle, args.control_uid, args.execution_uid, args.data_root)}))
        return
    bundle = load_bundle(args.bundle)
    if args.active_state and (bundle['manifest']['data_root'] != str(Path(args.active_state).resolve())
                             or checksum(bundle) != state['bundle']):
        raise ValueError('active_state_release_mismatch')
    deployment = Deployment(bundle, args.bundle)
    if args.action == 'inspect':
        print(json.dumps({'bundle_digest': checksum(bundle), 'revision': bundle['manifest']['revision'],
                          'changes_host': False, 'go_live': False}))
    elif args.action in {'install', 'update', 'rollback'}:
        print(json.dumps(deployment.apply(args.action, args.approved_bundle)))
    elif args.action == 'boot':
        print(json.dumps(deployment.boot()))
    else:
        deployment.preflight()
        if args.action == 'backup':
            print(json.dumps({'file': str(deployment.backup()), 'offsite_verified': False}))
        elif args.action == 'backup-status':
            print(json.dumps(deployment.backup_status()))
        elif args.action == 'verify-backup':
            print(json.dumps(deployment.verify_backup(args.backup_file)[0]))
        elif args.action == 'restore-check':
            print(json.dumps(deployment.restore_check(args.backup_file)))
        else:
            print(json.dumps(deployment.postcheck()))


if __name__ == '__main__':
    main()
