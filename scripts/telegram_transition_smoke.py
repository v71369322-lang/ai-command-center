"""Real old/new containers and maintenance jobs; explicitly CLOUD ROOTFUL TEST.

Only local owned acc-f23 resources and public synthetic credentials. This is
not SSH, a production deploy, host-rootless evidence or a real Telegram call.
"""
import copy
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from uuid import uuid4

import httpx

from command_center.deployment import Deployment, initialize_state, migration_hash
from command_center.deployment_profile import PROJECT, atomic_json, checksum, render
from command_center.local_docker import environment, run as docker
from command_center.password_auth import document
from command_center.telegram_transition import JOB, OLD_REVISION, TelegramTransition
from deployment_smoke import CloudEngine, wait

PUBLIC_PASSWORD = 'public-transition-drill-password-not-real'
RUNTIME_HOOK = ('from command_center import telegram_transition as m;'
                'from command_center.runtime_policy import RuntimeBackend;'
                'm.RuntimeBackend=lambda:RuntimeBackend(mode="cloud-rootful-test");m.main()')
TAGS = {'api': 'acc-f1-app:local', 'worker': 'acc-f1-worker:local', 'broker': 'acc-f1-broker:local',
        'executor': 'acc-f1-executor:local', 'coding': 'acc-f2-executor:local'}


def git(directory, *args, data=None):
    env = {'PATH': os.defpath, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    return subprocess.check_output(['git', '-C', str(directory), *args], input=data,
                                   stderr=subprocess.DEVNULL, env=env, timeout=30)


def old_source_fixture(repository, destination):
    """Reconstruct only the known baseline Git objects, no remote or worktree."""
    rows = git(repository, 'ls-tree', '-rt', OLD_REVISION).decode().splitlines()
    objects = {OLD_REVISION: 'commit', git(repository, 'rev-parse', OLD_REVISION + '^{tree}').decode().strip(): 'tree'}
    for row in rows:
        mode, kind, oid = row.split('\t', 1)[0].split()
        if mode not in {'100644', '100755', '040000'} or kind not in {'blob', 'tree'}:
            raise ValueError('unsupported_baseline_fixture')
        objects[oid] = kind
    if len(objects) > 5000:
        raise ValueError('baseline_fixture_limit')
    destination.mkdir(mode=0o700)
    git(destination, 'init', '--quiet', '--template=')
    total = 0
    for oid, kind in sorted(objects.items()):
        raw = git(repository, 'cat-file', kind, oid)
        total += len(raw)
        if total > 8 * 1024 * 1024:
            raise ValueError('baseline_fixture_limit')
        if git(destination, 'hash-object', '-w', '-t', kind, '--stdin', data=raw).decode().strip() != oid:
            raise ValueError('baseline_fixture_hash_mismatch')
    (destination / '.git/shallow').write_text(OLD_REVISION + '\n')
    git(destination, 'fsck', '--strict', '--no-reflogs', OLD_REVISION)
    git(destination, '-c', 'core.hooksPath=/dev/null', 'checkout', '--detach', OLD_REVISION)
    if git(destination, 'status', '--porcelain'):
        raise ValueError('baseline_fixture_not_clean')


class DrillEngine(CloudEngine):
    endpoint = 'unix:///var/run/docker.sock'

    def __init__(self):
        self.profiles = {}
        self.apply_count = 0
        self.lose_apply_response = True

    def preflight(self):
        info = self.json('info', '--format', '{{json .}}')
        if not all(info.get(k) for k in ('MemoryLimit', 'PidsLimit', 'CpuCfsQuota')):
            raise ValueError('cloud_resource_limits_unavailable')

    def register(self, directory, profile, port):
        runtime = copy.deepcopy(profile)
        for name, service in runtime['services'].items():
            service['restart'] = 'no'
            if name != 'db':
                service['user'] = f'{os.getuid()}:{os.getgid()}'
            if name in {'runtime-broker', 'watchdog'}:
                service['group_add'] = [str(os.stat('/var/run/docker.sock').st_gid)]
                service['environment']['F1_RUNTIME_MODE'] = 'cloud-rootful-test'
                next(v for v in service['volumes'] if v['target'] == '/var/run/docker.sock')['source'] = '/var/run/docker.sock'
        runtime['services']['api']['ports'][0]['published'] = str(port)
        physical = directory / 'cloud-runtime.json'
        atomic_json(physical, runtime)
        self.profiles[str(directory / 'compose.json')] = str(physical)

    def run(self, *args, **kwargs):
        args = list(args)
        if args[0] == 'compose':
            position = args.index('-f') + 1
            args[position] = self.profiles[args[position]]
        is_job = 'command_center.telegram_transition' in args and 'job' in args
        apply = is_job and args[args.index('--job-action') + 1] == 'apply'
        if is_job:
            position = args.index('command_center.telegram_transition')
            args[position - 1:position + 1] = ['-c', RUNTIME_HOOK]
            if apply:
                args[1:1] = ['--group-add', str(os.stat('/var/run/docker.sock').st_gid)]
        result = super().run(*args, **kwargs)
        if apply:
            self.apply_count += 1
            if self.lose_apply_response:
                self.lose_apply_response = False
                raise RuntimeError('synthetic_reply_loss_after_real_migration_commit')
        return result


class Execution(DrillEngine):
    def run(self, *args, **kwargs):
        if args == ('ps', '-aq'):
            args = (*args, '--filter', 'label=acc.scope=f1')
        return super().run(*args, **kwargs)


def old_images(source, engine):
    result = {}
    for key in TAGS:
        tag = 'acc-transition-old-' + key + ':4cc6ec4'
        existing = docker('image', 'inspect', tag)
        if existing.returncode:
            args = ['build', '--build-arg', 'F1_SOURCE_REVISION=' + OLD_REVISION, '-q', '-t', tag]
            if key == 'executor':
                args += ['-f', str(source / 'Dockerfile.executor')]
            else:
                args += ['--target', 'app' if key == 'api' else key]
                if os.environ.get('F1_BUILD_CA_FILE'):
                    args += ['--secret', 'id=proxy_ca,src=' + os.environ['F1_BUILD_CA_FILE']]
            engine.run(*args, str(source), timeout=300)
        image = engine.json('image', 'inspect', tag)[0]
        if image['Config']['Labels']['org.opencontainers.image.revision'] != OLD_REVISION:
            raise ValueError('baseline_image_not_pinned')
        result[key] = image['Id']
    return result


def bundle(source, root, images, revision, origin, engine):
    env = environment()
    env.update(F1_SOURCE_REVISION=revision, F1_DOCKER_GID='0')
    raw = subprocess.check_output(['docker', '--host=unix:///var/run/docker.sock', 'compose',
                                   '--profile', 'worker', '-f', str(source / 'compose.yaml'),
                                   'config', '--format', 'json'], env=env)
    base = json.loads(raw)
    m = dict(schema=1, revision=revision, images=images, database_image=base['services']['db']['image'],
             redis_image=base['services']['redis']['image'], migration_hash=migration_hash(source),
             control_uid=os.getuid(), execution_uid=os.getuid() + 1, data_root=str(root), source_root=str(source),
             owner_login={'origin': origin, 'loopback_http': True})
    value = {'manifest': m, 'compose': render(base, m)}
    directory = root / ('bundle-' + revision[:12])
    directory.mkdir(mode=0o700)
    atomic_json(directory / 'bundle.json', value)
    atomic_json(directory / 'compose.json', value['compose'])
    engine.register(directory, value['compose'], int(origin.rsplit(':', 1)[1]))
    return Deployment(value, directory, engine, Execution())


def request(client, path, body=None):
    if body is None:
        response = client.get('/api/' + path)
    else:
        csrf = client.get('/api/auth/csrf')
        csrf.raise_for_status()
        response = client.post('/api/' + path, json=body,
                               headers={'X-CSRF-Token': csrf.json()['csrf_token'], 'Idempotency-Key': uuid4().hex})
    response.raise_for_status()
    return response.json()


def login(client):
    response = client.post('/api/auth/login', json={'username': 'owner', 'password': PUBLIC_PASSWORD})
    response.raise_for_status()


def state_response(client, expected_status, *, seconds=10):
    """Safe GET readiness only; never repeat writes or retry an HTTP verdict."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            response = client.get('/api/state', timeout=max(.001, deadline - time.monotonic()))
        except httpx.TransportError:
            if time.monotonic() >= deadline:
                raise RuntimeError('transition_api_transport_not_ready') from None
            time.sleep(.1)
            continue
        if response.status_code != expected_status:
            raise ValueError('transition_api_state_http_status')
        return response


def resume(client):
    csrf = client.get('/api/auth/csrf').json()['csrf_token']
    state = request(client, 'state')
    response = client.post('/api/control/resume', json={k: state[k] for k in ('epoch', 'checkpoint_digest')},
                           headers={'X-CSRF-Token': csrf})
    response.raise_for_status()


def task(client, message):
    created = request(client, 'simulator/commands', {'kind': 'render', 'values': {'message': message}})

    def finished():
        value = next(v for v in request(client, 'state')['tasks'] if v['id'] == created['id'])
        if value['state'] in {'FAILED', 'CANCELLED', 'SECURITY_BLOCKED', 'RECONCILING'}:
            raise ValueError('transition_task_' + value['state'] + ':' + str(value['reason']))
        if value['state'] != 'SUCCEEDED':
            raise ValueError('transition_task_waiting')
        return value
    return wait(finished)


def main():
    source = Path.cwd()
    revision = git(source, 'rev-parse', 'HEAD').decode().strip()
    if git(source, 'status', '--porcelain'):
        raise ValueError('clean_source_required')
    if shutil.disk_usage(source).free < 8 * 1024**3:
        raise ValueError('transition_drill_requires_8gib_free_no_guard_relaxation')
    engine = DrillEngine()
    for args in [('ps', '-aq', '--filter', 'label=com.docker.compose.project=' + PROJECT),
                 ('volume', 'ls', '-q', '--filter', 'name=^' + PROJECT + '-pgdata$'),
                 ('ps', '-aq', '--filter', 'name=^' + JOB + '$')]:
        if engine.run(*args).strip():
            raise ValueError('preexisting_transition_resources_reconcile_instead')
    with (source / '.runtime/transition-drill.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run_drill(source, revision, engine)


def run_drill(source, revision, engine):
    root = source / '.runtime' / ('telegram-transition-drill-' + uuid4().hex)
    initialize_state(root)
    old_source = root / 'baseline-source'
    old_source_fixture(source, old_source)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        origin = 'http://127.0.0.1:' + str(listener.getsockname()[1])
    atomic_json(root / 'secrets/owner_password', document('owner', PUBLIC_PASSWORD))
    old = bundle(old_source, root, old_images(old_source, engine), OLD_REVISION, origin, engine)
    images = {key: engine.json('image', 'inspect', tag)[0]['Id'] for key, tag in TAGS.items()}
    current = bundle(source, root, images, revision, origin, engine)
    created = False
    try:
        created = True
        old.apply('install', checksum(old.bundle))
        # API containers are deliberately replaced below. Preserve the cookies
        # for the old-session rejection check, but never reuse the old TCP peer.
        with httpx.Client(base_url=origin, headers={'Origin': origin}, trust_env=False, timeout=10,
                          limits=httpx.Limits(max_keepalive_connections=0)) as client:
            state_response(client, 401)  # Running containers need not be serving HTTP yet.
            login(client)
            resume(client)
            original = task(client, 'before actual Telegram schema transition')
            transition = TelegramTransition(current)
            approval = checksum(current.bundle)
            plan = transition.stage(approval, checksum(old.bundle))
            try:
                transition.apply(approval, plan['plan_digest'])
            except RuntimeError as error:
                if str(error) != 'synthetic_reply_loss_after_real_migration_commit':
                    raise
            else:
                raise ValueError('reply_loss_not_injected')
            pending = json.loads((root / 'deployment.json').read_text())
            if pending['phase'] != 'TELEGRAM_MIGRATION_PENDING' or engine.apply_count != 1:
                raise ValueError('ambiguous_commit_was_not_durable')
            transition.reconcile(approval)
            if engine.apply_count != 1:
                raise ValueError('migration_replayed')
            state_response(client, 401)  # Preserve the old cookie; require its actual rejection.
            login(client)
            snapshot = state_response(client, 200).json()
            preserved = next(v for v in snapshot['tasks'] if v['id'] == original['id'])
            if not snapshot['halted'] or preserved['artifact_hash'] != original['artifact_hash']:
                raise ValueError('state_not_preserved_or_auto_resumed')
            status = request(client, 'telegram/status')
            if status['mode'] != 'disabled' or status['live_connected']:
                raise ValueError('telegram_unexpectedly_activated')
            if request(client, 'telegram/requests')['requests']:
                raise ValueError('telegram_inbox_not_empty')
            resume(client)
            after = task(client, 'after actual Telegram schema transition')
            request(client, 'control/stop', {})
            current.compose('stop')
            current.boot()
            wait(current.postcheck)
            snapshot = state_response(client, 200).json()
            if not snapshot['halted'] or any(
                    next(v for v in snapshot['tasks'] if v['id'] == t['id'])['artifact_hash'] != t['artifact_hash']
                    for t in (original, after)):
                raise ValueError('boot_lost_state_or_resumed_work')
            try:
                old.apply('rollback', checksum(old.bundle))
            except ValueError as error:
                if str(error) != 'database_change_requires_separate_migration_plan':
                    raise
            else:
                raise ValueError('schema_rollback_not_blocked')
        report = {'status': 'PASS', 'mode': 'CLOUD_ROOTFUL_TEST_ONLY', 'revision': revision,
                  'baseline_revision': OLD_REVISION, 'actual_maintenance_container': True,
                  'actual_ddl_restore_and_reply_loss': True, 'migration_apply_count': engine.apply_count,
                  'preserved_task': original['id'], 'new_task': after['id'], 'password_preserved': True,
                  'old_session_rejected': True, 'boot_kept_admission_halted': True,
                  'live_telegram_contacted': False, 'vps_contacted': False, 'rootless_host_verified': False}
        atomic_json(source / '.runtime/telegram-transition-container.json', report)
        print('Old password release → actual migration/restore container → reply loss → reconciliation once → new task → boot/preservation: PASS (CLOUD ROOTFUL TEST ONLY)')
    finally:
        if created:
            # Fresh owned synthetic project only, never a host/operator cleanup.
            current.compose('down')
            engine.run('volume', 'rm', PROJECT + '-pgdata')


if __name__ == '__main__':
    main()
