"""Read-only SQLite fixtures and fake local Docker; no VPS or provider access."""
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from command_center.runtime_ledger import RuntimeLedger
from command_center.worker import Runner

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('recovery_readonly', ROOT / 'infra/vps/inspect_first_recovery.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / 'ledger.sqlite'
    view = RuntimeLedger(path)
    task = {'id': probe.TASK_ID, 'fence': 1, 'revision': probe.EXPECTED_SOURCE}
    view.register(task, Runner.name(task), 30)
    view.phase(task['id'], 1, 'DONE')
    view.watchdog()
    view.worker_beat(probe.EXPECTED_SOURCE)
    return path, view


def files(folder):
    return {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in folder.iterdir()}


def test_read_only_runtime_uses_existing_verifier_without_constructor_or_mutation(ledger, monkeypatch):
    path, _ = ledger
    before = files(path.parent)
    monkeypatch.setattr(RuntimeLedger, '__init__', lambda *a, **kw: pytest.fail('constructor mutates runtime'))
    result = probe.runtime_snapshot(path, 1)
    assert all(result[k] for k in ('parent_run_done', 'parent_revision_matches', 'container_name_matches',
                                   'watchdog_fresh', 'worker_fresh', 'audit_chain_verified'))
    assert result['unresolved_runs'] == 0
    assert files(path.parent) == before
    with probe.read_only_ledger(path) as view:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            view.phase(probe.TASK_ID, 1, 'UNCERTAIN')
    assert files(path.parent) == before


@pytest.mark.parametrize('change', ['uncertain', 'other_run', 'wrong_revision', 'wrong_name', 'stale_watchdog', 'stale_worker'])
def test_runtime_problems_remain_visible_and_are_never_reconciled(ledger, change):
    path, view = ledger
    if change == 'uncertain':
        view.phase(probe.TASK_ID, 1, 'UNCERTAIN')
    elif change == 'other_run':
        view.register({'id': 'a' * 36, 'fence': 1, 'revision': probe.EXPECTED_SOURCE}, 'PUBLIC_FIXTURE', 30)
    else:
        with view.tx() as db:
            if change == 'wrong_revision':
                db.execute('UPDATE runs SET revision=?', ('d' * 40,))
            elif change == 'wrong_name':
                db.execute('UPDATE runs SET name=?', ('not-the-fixed-container',))
            elif change == 'stale_watchdog':
                db.execute('UPDATE monitor SET heartbeat=0')
            else:
                db.execute('UPDATE worker_monitor SET heartbeat=0')
    before = files(path.parent)
    result = probe.runtime_snapshot(path, 1)
    flag = {'uncertain': 'parent_run_done', 'wrong_revision': 'parent_revision_matches',
            'wrong_name': 'container_name_matches', 'stale_watchdog': 'watchdog_fresh',
            'stale_worker': 'worker_fresh'}.get(change)
    if change == 'other_run':
        assert result['unresolved_runs'] == 1
    else:
        assert result[flag] is False
    assert files(path.parent) == before


@pytest.mark.parametrize('change', ['missing', 'symlink', 'public', 'hardlink', 'corrupt_chain', 'wal', 'wrong_fence'])
def test_unknown_or_unsafe_runtime_is_blocked_without_file_repairs(ledger, tmp_path, change):
    path, view = ledger
    if change == 'missing':
        path = tmp_path / 'absent.sqlite'
    elif change == 'symlink':
        alias = tmp_path / 'alias.sqlite'
        alias.symlink_to(path)
        path = alias
    elif change == 'public':
        path.chmod(0o644)
    elif change == 'hardlink':
        (tmp_path / 'alias.sqlite').hardlink_to(path)
    elif change == 'corrupt_chain':
        with view.tx() as db:
            db.execute("UPDATE evidence SET digest='corrupt'")
    elif change == 'wal':
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA journal_mode=WAL')
    before = files(tmp_path)
    with pytest.raises(Exception):
        probe.runtime_snapshot(path, 2 if change == 'wrong_fence' else 1)
    assert files(tmp_path) == before


class Docker:
    mode = 'rootless-required'

    def __init__(self, result=None, *, healthy=True):
        self.result, self.healthy, self.calls = result, healthy, []

    def preflight(self):
        self.calls.append(('info',))
        if not self.healthy:
            raise RuntimeError('PRIVATE_DAEMON_ERROR_MUST_NOT_BE_PRINTED')
        return {'rootless_verified': True}

    def call(self, *args):
        self.calls.append(args)
        return self.result or SimpleNamespace(returncode=0, stdout=b'')


def test_container_absence_requires_healthy_rootless_daemon_and_exact_all_state_filter():
    backend = Docker()
    assert probe.container_snapshot(backend, 7)['parent_container_absent'] is True
    assert backend.calls == [('info',), ('ps', '-a', '--filter',
        'name=^/acc-f1-' + probe.TASK_ID + '-7$', '--format', '{{.Names}}')]
    backend = Docker(healthy=False)
    with pytest.raises(RuntimeError):
        probe.container_snapshot(backend, 7)
    assert backend.calls == [('info',)]


@pytest.mark.parametrize('result', [SimpleNamespace(returncode=1, stdout=b''),
    SimpleNamespace(returncode=0, stdout=b'PRIVATE_UNEXPECTED_DOCKER_OUTPUT'),
    SimpleNamespace(returncode=0, stdout=b'x' * 1025)])
def test_container_query_errors_are_not_absence(result):
    with pytest.raises(ValueError):
        probe.container_snapshot(Docker(result), 1)


def test_existing_container_is_reported_and_never_stopped():
    backend = Docker(SimpleNamespace(returncode=0, stdout=('acc-f1-' + probe.TASK_ID + '-1\n').encode()))
    assert probe.container_snapshot(backend, 1)['parent_container_absent'] is False
    assert len(backend.calls) == 2


def test_cli_rejects_untrusted_arguments_without_echoing_or_touching_services():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, str(ROOT / 'infra/vps/inspect_first_recovery.py'),
        '--token', 'PRIVATE_ARGUMENT_MUST_NOT_BE_ECHOED'], capture_output=True, timeout=10)
    assert result.returncode == 2
    assert b'PRIVATE_ARGUMENT' not in result.stdout + result.stderr


def test_section_errors_are_redacted_and_never_indicate_recovery_consent(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('PRIVATE_ERROR_MUST_NOT_BE_PRINTED')
    monkeypatch.setattr(probe, 'database_snapshot', fail)
    report = probe.inspect(SimpleNamespace(settings=SimpleNamespace(source_revision=probe.EXPECTED_SOURCE)),
                           config_loader=fail)
    assert report['status'] == 'BLOCKED' and report['recovery_authority_verified'] is False
    assert report['paid_recovery_authorized'] is report['token_issued'] is False
    assert 'PRIVATE_ERROR' not in json.dumps(report)
    assert set(report['blockers']) == {'database_inspection_failed', 'parent_fence_unavailable', 'profile_inspection_failed'}


def test_diagnostic_imports_against_the_actual_installed_322186d_library(tmp_path):
    import io
    import os
    import subprocess
    import sys
    import tarfile
    archive = subprocess.check_output(['git', 'archive', '322186dc180257c618d8b159c78faa6e5bbf0b43', 'src'],
                                     cwd=ROOT, timeout=10)
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(tmp_path, filter='data')
    result = subprocess.run([sys.executable, str(ROOT / 'infra/vps/inspect_first_recovery.py'), '--help'],
        env={**os.environ, 'PYTHONPATH': str(tmp_path / 'src')}, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    assert b'local read-only' in result.stdout
