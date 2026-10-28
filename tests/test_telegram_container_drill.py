"""Contracts of the explicit cloud test adapter; no host/rootless claim."""
import importlib
import json
from pathlib import Path

import pytest

from test_deployment import release as release

from command_center.deployment import migration_hash
from command_center.telegram_transition import OLD_REVISION, OLD_SCHEMA


@pytest.fixture
def drill(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    return importlib.import_module('telegram_transition_smoke')


def test_fixture_is_exact_legacy_commit_without_remote_credentials(drill, tmp_path):
    destination = tmp_path / 'old-source'
    drill.old_source_fixture(Path(__file__).resolve().parents[1], destination)
    assert drill.git(destination, 'rev-parse', 'HEAD').decode().strip() == OLD_REVISION
    assert drill.git(destination, 'status', '--porcelain') == b''
    assert drill.git(destination, 'remote') == b''
    assert migration_hash(destination) == OLD_SCHEMA
    with pytest.raises(FileExistsError):
        drill.old_source_fixture(Path(__file__).resolve().parents[1], destination)


def test_rootful_runtime_translation_cannot_mutate_production_profile(drill, release):
    bundle, directory = release
    before = json.dumps(bundle, sort_keys=True)
    engine = drill.DrillEngine()
    engine.register(directory, bundle['compose'], 18033)
    physical = json.loads((directory / 'cloud-runtime.json').read_text())
    assert json.dumps(bundle, sort_keys=True) == before
    assert physical['services']['api']['ports'][0]['host_ip'] == '127.0.0.1'
    assert physical['services']['runtime-broker']['environment']['F1_RUNTIME_MODE'] == 'cloud-rootful-test'
    assert bundle['compose']['services']['runtime-broker']['environment']['F1_RUNTIME_MODE'] == 'rootless-required'
    assert not physical['services']['api'].get('privileged')


def test_reply_loss_is_injected_after_job_returns_and_verify_has_no_extra_group(drill, monkeypatch):
    calls = []

    def actual_return(self, *args, **kwargs):
        calls.append(args)
        return b'{}'

    monkeypatch.setattr(drill.CloudEngine, 'run', actual_return)
    engine = drill.DrillEngine()
    args = ('run', '--name', drill.JOB, 'pinned-test-image', 'python', '-m',
            'command_center.telegram_transition', 'job', '--job-action')
    with pytest.raises(RuntimeError, match='after_real_migration_commit'):
        engine.run(*args, 'apply')
    assert len(calls) == 1 and engine.apply_count == 1 and '--group-add' in calls[0]
    assert '-c' in calls[0] and drill.RUNTIME_HOOK in calls[0]
    assert engine.run(*args, 'verify') == b'{}'
    assert engine.apply_count == 1 and '--group-add' not in calls[1]
