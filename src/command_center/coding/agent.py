"""Bounded autonomous edit/test/repair loop. Executor has no host/API credentials."""
import json
from pathlib import Path
import subprocess
import sys
import time

from .providers import MockProvider, ProviderUnavailable
from .spec import BASE_SHA, PLAN
from .workspace import Workspace


def check(root, seconds):
    checker = Path(__file__).with_name('checks.py')
    result = subprocess.run([sys.executable, '-I', '-B', str(checker), str(root)],
                            capture_output=True, timeout=max(.1, min(seconds, 3)))
    if result.returncode or len(result.stdout) > 2048:
        raise ValueError('acceptance_runner_failed')
    return json.loads(result.stdout)


def execute(job, root):
    task = job['coding']
    if task['provider'] != 'mock':
        raise PermissionError('provider_not_authorized')
    workspace = Workspace(root, job['operation_id'], job['fence'], task['base_sha'])
    provider = MockProvider(task['scenario'])
    started, tokens, units, history = time.monotonic(), 0, 0, []
    status = 'attempt_limit'
    try:
        for attempt in range(1, task['max_iterations'] + 1):
            remaining = task['max_seconds'] - (time.monotonic() - started)
            if remaining <= 0:
                status = 'time_limit'
                break
            if units + 1 > task['max_units']:
                status = 'budget_limit'
                break
            if task['scenario'] == 'pin_change':
                workspace.repo.refs[b'refs/heads/main'] = b'0' * 40
            workspace.check_pin()
            proposal = provider.propose({'objective': 'sum_positive_v1', 'base_sha': BASE_SHA,
                                         'attempt': attempt, 'source': (workspace.root / 'calculator.py').read_text(),
                                         'previous_checks': history[-1]['checks'] if history else None})
            tokens += proposal.tokens
            units += proposal.units
            if tokens > task['max_tokens'] or units > task['max_units']:
                status = 'budget_limit'
                break
            workspace.apply(proposal.changes)
            commit = workspace.commit()
            remaining = task['max_seconds'] - (time.monotonic() - started)
            if remaining <= 0:
                status = 'time_limit'
                break
            checks = check(workspace.root, remaining)
            history.append({'attempt': attempt, 'commit': commit, 'checks': checks})
            if checks['passed']:
                status = 'ready_for_verification'
                break
    except ProviderUnavailable:
        status = 'provider_unavailable'
    except (ValueError, OSError, subprocess.TimeoutExpired):
        status = 'scope_or_execution_blocked'
    result = {'status': status, 'plan': PLAN, 'history': history,
              'usage': {'tokens': tokens, 'units': units, 'synthetic': True}}
    if status == 'ready_for_verification':
        result['git'] = workspace.export()
    workspace.repo.close()
    return result
