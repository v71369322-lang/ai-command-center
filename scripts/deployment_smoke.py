"""Cloud-only rootful TEST adaptation of the F2.3 profile, never VPS installation.

The production controller remains rootless-only. This drill proves service
wiring, closed auth, persistence and restore; it cannot prove host rootless,
systemd, AppArmor, cgroup delegation, VPN/MFA or independent backup custody.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from uuid import uuid4

import httpx

from command_center.deployment import Deployment, initialize_state, migration_hash
from command_center.deployment_profile import atomic_json, render
from command_center.local_docker import environment, run as docker


class CloudEngine:
    def run(self, *args, data=None, timeout=120):
        # Production namespace-root maps to the control user's host UID. The
        # cloud rootful TEST daemon needs that host UID explicitly for 0600 files.
        args = [f'--user={os.getuid()}:{os.getgid()}' if v == '--user=0:0' else v for v in args]
        result = docker(*args, input=data, timeout=timeout)
        if result.returncode:
            diagnostic = next((code for token, code in [
                (b'Connection refused', 'database_tcp_not_ready'),
                (b'Permission denied', 'private_file_permission'),
                (b'No space left', 'cloud_disk_full'),
                (b'password authentication failed', 'database_binding_rejected')]
                if token in result.stderr), 'redacted_runtime_failure')
            raise RuntimeError('cloud_deployment_drill_command_failed:' + args[0] + ':' + diagnostic)
        return result.stdout

    def json(self, *args):
        return json.loads(self.run(*args))


def require(condition):
    if not condition:
        raise ValueError('cloud_deployment_expectation_failed')


def wait(check, seconds=40):
    deadline = time.monotonic() + seconds
    while True:
        try:
            return check()
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(.5)


def main():
    source = Path.cwd()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain']):
        raise ValueError('clean_source_required')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 18000))
    engine = CloudEngine()
    if engine.run('ps', '-aq', '--filter', 'label=com.docker.compose.project=acc-f23').strip():
        raise ValueError('previous_drill_containers_present_do_not_overwrite')
    if engine.run('volume', 'ls', '-q', '--filter', 'name=^acc-f23-pgdata$').strip():
        raise ValueError('previous_drill_volume_present_do_not_overwrite')
    root = source / '.runtime' / ('f23-drill-' + uuid4().hex)
    initialize_state(root)
    env = environment()
    env.update(F1_SOURCE_REVISION=revision, F1_DOCKER_GID='0')
    result = subprocess.run(['docker', 'compose', '--profile', 'worker', '-f', 'compose.yaml', 'config', '--format', 'json'],
                            env=env, capture_output=True, check=True)
    base = json.loads(result.stdout)
    tags = {'api': 'acc-f1-app:local', 'worker': 'acc-f1-worker:local', 'broker': 'acc-f1-broker:local',
            'executor': 'acc-f1-executor:local', 'coding': 'acc-f2-executor:local'}
    images = {k: engine.json('image', 'inspect', tag)[0]['Id'] for k, tag in tags.items()}
    for image in images.values():
        if engine.json('image', 'inspect', image)[0]['Config']['Labels']['org.opencontainers.image.revision'] != revision:
            raise ValueError('drill_image_revision_mismatch')
    m = dict(schema=1, revision=revision, images=images, database_image=base['services']['db']['image'],
             redis_image=base['services']['redis']['image'], migration_hash=migration_hash(source),
             control_uid=1000, execution_uid=1001, data_root=str(root), source_root=str(source))
    production = render(base, m)
    p = json.loads(json.dumps(production))
    # Explicit test profile, never passed to Deployment.apply or load_bundle.
    for name, service in p['services'].items():
        service['restart'] = 'no'
        if name != 'db':
            service['user'] = f'{os.getuid()}:{os.getgid()}'
        if name in {'runtime-broker', 'watchdog'}:
            service['group_add'] = [str(os.stat('/var/run/docker.sock').st_gid)]
            service['environment']['F1_RUNTIME_MODE'] = 'cloud-rootful-test'
            next(v for v in service['volumes'] if v['target'] == '/var/run/docker.sock')['source'] = '/var/run/docker.sock'
    p['services']['api']['ports'][0]['published'] = '18000'
    atomic_json(root / 'compose.json', p)
    deployment = Deployment({'manifest': m, 'compose': production}, root, engine, engine)
    try:
        deployment.compose('up', '-d', '--no-build', '--pull', 'never', '--wait', 'db', 'redis')
        deployment.tool('from command_center.admin import main;main()')
        deployment.compose('up', '-d', '--no-build', '--pull', 'never')
        wait(deployment.postcheck)
        with httpx.Client(base_url='http://127.0.0.1:18000', timeout=5) as client:
            def closed_access():
                require(client.get('/').status_code == 200)
                require(client.get('/api/state').status_code == 401)
                denied = client.post('/api/auth/exchange', json={'assertion': 'synthetic-unconfigured-identity-assertion'})
                require(denied.status_code == 403 and denied.json()['detail'] == 'https_required')
            wait(closed_access)
        code = ('import json;from command_center.config import Settings;from command_center.store import Store;'
                "print(json.dumps(Store(Settings.load()).create('owner','f23-cloud-smoke',{'kind':'render','values':{'test':'synthetic'}})))")
        task = json.loads(deployment.tool(code))

        def succeeded():
            value = json.loads(deployment.tool('import json;from command_center.config import Settings;'
                'from command_center.store import Store;print(json.dumps(Store(Settings.load()).get(' + repr(task['id']) + ')))'))
            require(value['state'] == 'SUCCEEDED')
            require(bool(value['artifact_hash']))
            return value
        evidence = wait(succeeded)
        deployment.quiesce()
        backup = deployment.backup()
        restored = deployment.restore_check(backup)
        deployment.compose('stop', 'api', 'worker', 'runtime-broker', 'watchdog')
        deployment.compose('up', '-d', '--no-build', '--pull', 'never')
        wait(deployment.postcheck)
        require(wait(succeeded)['artifact_hash'] == evidence['artifact_hash'])
        deployment.compose('restart')
        wait(deployment.postcheck)
        require(wait(succeeded)['artifact_hash'] == evidence['artifact_hash'])
        report = {'revision': revision, 'mode': 'CLOUD_ROOTFUL_TEST_ONLY', 'task_verified': True,
                  'closed_auth': True, 'persistent_recreate_and_restart': True, 'restore': restored,
                  'rootless_host_verified': False, 'systemd_boot_verified': False, 'vps_contacted': False}
        atomic_json(source / '.runtime/f23-deployment-smoke.json', report)
        print('F2.3 closed profile → synthetic task → encrypted backup/restore → persistent recreate/restart: PASS')
    finally:
        # Only resources this fresh, explicitly owned test created. Never a host/operator command.
        deployment.compose('down')
        engine.run('volume', 'rm', 'acc-f23-pgdata')


if __name__ == '__main__':
    main()
