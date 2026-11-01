import importlib.util
import json
from pathlib import Path

import pytest

from command_center.deployment_profile import checksum

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    'reconcile_deployment_intent', ROOT / 'infra/vps/reconcile_deployment_intent.py')
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


def release(tmp_path):
    directory = tmp_path / 'release'
    directory.mkdir(mode=0o700)
    bundle = {
        'manifest': {
            'schema': 1, 'revision': 'a' * 40,
            'images': {key: 'sha256:' + str(index) * 64 for index, key in enumerate(
                ('api', 'worker', 'broker', 'executor', 'coding'), 1)},
            'database_image': 'postgres:16-bookworm@sha256:' + '6' * 64,
            'redis_image': 'redis:7-bookworm@sha256:' + '7' * 64,
            'migration_hash': '8' * 64, 'control_uid': 1000, 'execution_uid': 1001,
            'data_root': '/home/acc-control/f30/state',
            'source_root': '/home/acc-control/release/source',
        },
        # Deliberately opaque here: legacy exact bundles are runtime-proven rather
        # than reinterpreted by a newer profile validator.
        'compose': {'legacy': True},
    }
    for name, value in (('bundle.json', bundle), ('compose.json', bundle['compose'])):
        (directory / name).write_text(json.dumps(value))
        (directory / name).chmod(0o600)
    return directory, bundle


def test_reconcile_delegates_exact_bundle_without_rewriting_legacy_profile(tmp_path, monkeypatch):
    directory, bundle = release(tmp_path)
    approved = checksum(bundle)
    seen = []

    class FakeDeployment:
        def __init__(self, value, path):
            assert value == bundle and Path(path) == directory

        def reconcile_intent(self, value):
            seen.append(value)
            return {'state': 'CLOSED_SYNTHETIC_SERVICES_RUNNING', 'go_live': False}

    monkeypatch.setattr(operator, 'Deployment', FakeDeployment)
    monkeypatch.setattr(operator.os, 'getuid', lambda: directory.stat().st_uid)
    monkeypatch.setattr(operator.time, 'time', lambda: 1000)
    result = operator.reconcile(directory, approved, 1100)
    assert seen == [approved]
    assert result['status'] == 'EXACT_DEPLOYMENT_INTENT_RECONCILED'
    assert result['runtime_changed'] is False and result['paid_calls'] == 0


@pytest.mark.parametrize('change', ['digest', 'deadline', 'compose', 'mode'])
def test_reconcile_rejects_changed_scope_before_deployment(tmp_path, monkeypatch, change):
    directory, bundle = release(tmp_path)
    approved, until = checksum(bundle), 1100
    if change == 'digest':
        approved = 'f' * 64
    elif change == 'deadline':
        until = 1000
    elif change == 'compose':
        (directory / 'compose.json').write_text('{}')
    else:
        (directory / 'bundle.json').chmod(0o644)
    monkeypatch.setattr(operator.os, 'getuid', lambda: directory.stat().st_uid)
    monkeypatch.setattr(operator.time, 'time', lambda: 1000)
    monkeypatch.setattr(operator, 'Deployment', lambda *args: pytest.fail('deployment reached'))
    with pytest.raises(ValueError):
        operator.reconcile(directory, approved, until)
