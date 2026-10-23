"""Real container API/worker smoke; secrets never printed or included in evidence."""
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx


def main():
    token = json.loads(Path('.runtime/secrets/identities.json').read_text())['owner']
    headers = {'Authorization': 'Bearer ' + token}
    started = time.monotonic()
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=5) as client:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if client.get('/api/state', headers=headers).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('container_api_not_ready')
        request = {'kind': 'approved_render', 'values': {'message': 'container smoke'}}
        response = client.post('/api/simulator/commands', json=request,
                               headers={**headers, 'Idempotency-Key': 'smoke-' + str(uuid4())})
        if response.status_code != 201:
            raise RuntimeError('container_admission_failed')
        task = response.json()
        if task['state'] != 'WAITING_APPROVAL':
            raise RuntimeError('approval_gate_missing')
        response = client.post('/api/tasks/' + task['id'] + '/approve',
                               json={'version': task['version'], 'seconds': 120}, headers=headers)
        if response.status_code != 200:
            raise RuntimeError('container_approval_failed')
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            response = client.get('/api/state', headers=headers)
            if response.status_code != 200:
                raise RuntimeError('container_state_unavailable')
            current = next(t for t in response.json()['tasks'] if t['id'] == task['id'])
            if current['state'] == 'SUCCEEDED':
                break
            time.sleep(1)
        else:
            raise RuntimeError('container_worker_did_not_verify')
        expected = '# Synthetic result\n\n- message: container smoke\n'
        if current['artifact'] != expected or current['artifact_hash'] != hashlib.sha256(expected.encode()).hexdigest():
            raise RuntimeError('container_artifact_mismatch')
        health = client.get('/api/health', headers=headers).json()
        if health['postgres'] != 'healthy' or health['redis'] != 'healthy':
            raise RuntimeError('container_dependencies_unhealthy')
        if client.get('/').status_code != 200:
            raise RuntimeError('container_web_missing')
        if client.get('/api/state').status_code != 401:
            raise RuntimeError('anonymous_access_not_blocked')
    evidence = {'revision': os.environ['F1_SOURCE_REVISION'], 'status': 'PASS',
                'duration_seconds': round(time.monotonic() - started, 3),
                'components': ['container API', 'PostgreSQL', 'Outbox', 'Redis',
                               'container worker', 'isolated executor', 'verifier', 'static web'],
                'artifact_hash': current['artifact_hash']}
    Path('.runtime/container-smoke.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('Container API/worker + approval + verifier + closed web smoke: PASS')


if __name__ == '__main__':
    main()
