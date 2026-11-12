"""Fixed F2 entry point, read-only image; sandbox writes only /work."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from command_center.coding.contract import CodingRequest  # noqa: E402
from command_center.coding.verification import replay  # noqa: E402


def main():
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError('coding_input_limit')
    job = json.loads(raw)
    if 'payload' in job:
        from command_center.coding.isolated_entry import execute
        from command_center.isolated_coding import KIND
        if (set(job) != {'operation_id', 'fence', 'mode', 'payload'}
                or job['mode'] not in {'agent', 'verify'} or job['payload'].get('kind') != KIND):
            raise ValueError('isolated_job_invalid')
        result = execute(job['payload'], Path('/work/repository'))
        print(json.dumps({'operation_id': job['operation_id'], 'fence': job['fence'], 'result': result}))
        return
    task = CodingRequest.model_validate(job['coding']).model_dump()
    if job['mode'] == 'agent':
        if task['provider'] != 'mock':
            raise ValueError('provider_not_authorized')
        from command_center.coding.agent import execute
        result = execute({**job, 'coding': task}, Path('/work/repository'))
    elif job['mode'] == 'external_iteration':
        from command_center.coding.external_execution import apply_proposals
        result = apply_proposals({**job, 'coding': task}, Path('/work/repository'))
    elif job['mode'] == 'verify':
        result = replay(job['result'], job['operation_id'], job['fence'], task, Path('/work/verification'))
    else:
        raise ValueError('unknown_coding_stage')
    print(json.dumps({'operation_id': job['operation_id'], 'fence': job['fence'], 'result': result}, sort_keys=True))


if __name__ == '__main__':
    main()
