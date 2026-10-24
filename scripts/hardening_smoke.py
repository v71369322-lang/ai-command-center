"""Owned cloud-only worker SIGKILL drill; no SSH, real APIs or arbitrary targets."""
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx

from command_center.local_docker import run as docker


def require(result):
    if result.returncode:
        raise RuntimeError('owned_cloud_runtime_command_failed')
    return result.stdout


def main():
    builder = 'acc-f1-kill-drill-' + uuid4().hex
    image = 'acc-f1-kill-drill:' + uuid4().hex
    require(docker('create', '--name', builder, 'acc-f1-executor:local'))
    token = json.loads(Path('.runtime/secrets/identities.json').read_text())['owner']
    headers = {'Authorization': 'Bearer ' + token}
    try:
        command = 'ENTRYPOINT ' + json.dumps(['python', '-I', '-c', 'import sys,time;sys.stdin.read();time.sleep(60)'])
        require(docker('commit', '--change', command, builder, image))
        os.environ['F1_EXECUTOR_IMAGE'] = image
        require(docker('compose', '--profile', 'worker', 'up', '-d', '--no-build', '--force-recreate', 'runtime-broker', 'worker', timeout=60))
        with httpx.Client(base_url='http://127.0.0.1:8000', timeout=10, headers=headers) as client:
            response = client.post('/api/simulator/commands', json={'kind': 'render', 'values': {'drill': 'worker kill'}},
                                   headers={'Idempotency-Key': str(uuid4())})
            if response.status_code != 201:
                raise RuntimeError('kill_drill_admission_failed')
            task_id = response.json()['id']
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                state = client.get('/api/state').json()
                task = next(t for t in state['tasks'] if t['id'] == task_id)
                if task['state'] == 'RUNNING':
                    name = f"acc-f1-{task_id}-{task['fence']}"
                    check = docker('inspect', name)
                    if check.returncode == 0 and json.loads(check.stdout)[0]['State']['Running']:
                        break
                time.sleep(1)
            else:
                raise RuntimeError('kill_drill_container_not_running')
            require(docker('kill', 'acc-f1-worker-1'))
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                state = client.get('/api/state').json()
                task = next(t for t in state['tasks'] if t['id'] == task_id)
                events = [e['event'] for e in state['events']]
                if (task['state'] == 'FAILED' and state['halted'] and state['budget']['reserved'] == 0
                        and any(e['kind'] == 'watchdog_stop' for e in events)):
                    break
                time.sleep(1)
            else:
                raise RuntimeError('independent_watchdog_did_not_stop')
            if docker('inspect', name).returncode == 0:
                raise RuntimeError('orphan_container_remains')
            os.environ.pop('F1_EXECUTOR_IMAGE', None)
            require(docker('compose', '--profile', 'worker', 'up', '-d', '--no-build', '--force-recreate', 'runtime-broker', 'worker', timeout=60))
            state = client.get('/api/state').json()
            resumed = client.post('/api/control/resume', json={'epoch': state['epoch'], 'checkpoint_digest': state['checkpoint_digest']})
            if resumed.status_code != 200:
                raise RuntimeError('post_drill_resume_denied')
            if next(t for t in client.get('/api/state').json()['tasks'] if t['id'] == task_id)['state'] != 'FAILED':
                raise RuntimeError('failed_run_automatically_resumed')
        Path('.runtime/hardening-smoke.json').write_text(json.dumps({
            'revision': os.environ['F1_SOURCE_REVISION'], 'worker_sigkill': True,
            'independent_watchdog_stop': True, 'orphan_absent': True,
            'automatic_task_resume': False, 'runtime_mode': 'cloud-rootful-test',
            'rootless_host_verified': False}, indent=2) + '\n')
        print('Worker SIGKILL → independent watchdog → confirmed runtime absence → exact resume: PASS')
    finally:
        os.environ.pop('F1_EXECUTOR_IMAGE', None)
        docker('rm', '--force', builder)
        docker('image', 'rm', image)


if __name__ == '__main__':
    main()
