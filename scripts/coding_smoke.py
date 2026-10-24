"""Actual container API → Outbox → Redis → worker → broker → two sandboxes."""
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx


def main():
    token = json.loads(Path('.runtime/secrets/identities.json').read_text())['owner']
    headers = {'Authorization': 'Bearer ' + token}
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=5) as client:
        response = client.post('/api/coding/tasks', json={},
                               headers={**headers, 'Idempotency-Key': 'f2-smoke-' + str(uuid4())})
        response.raise_for_status()
        task_id = response.json()['id']
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            state = client.get('/api/state', headers=headers)
            state.raise_for_status()
            task = next(t for t in state.json()['tasks'] if t['id'] == task_id)
            if task['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'UNCERTAIN'}:
                break
            time.sleep(.5)
        if task['state'] != 'SUCCEEDED':
            raise RuntimeError('coding_container_cycle_not_verified:' + task['state'])
        coding = task['coding']
        if [r['checks']['passed'] for r in coding['test_runs']] != [False, True]:
            raise RuntimeError('repair_cycle_not_proven')
        draft = client.get('/api/tasks/' + task_id + '/pull-request', headers=headers)
        draft.raise_for_status()
        if draft.json()['published'] or draft.json()['url'] is not None:
            raise RuntimeError('unexpected_real_publication')
        Path('.runtime/coding-smoke.json').write_text(json.dumps({
            'revision': os.environ['F1_SOURCE_REVISION'], 'task_id': task_id, 'status': 'PASS',
            'provider': 'mock', 'publication': 'mock', 'base_sha': coding['base_sha'],
            'final_sha': coding['final_sha'], 'test_runs': coding['test_runs'],
            'verification_digest': coding['verification_digest']}, indent=2) + '\n')
    print('F2 container coding → failed checks → repair → independent replay → mock PR: PASS')


if __name__ == '__main__':
    main()
