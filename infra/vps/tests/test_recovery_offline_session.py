"""One protected local session using fake Docker; no VPS or provider calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from command_center.coding.integration_config import IntegrationConfig
from command_center.deployment_profile import checksum
from command_center.store import digest
from test_recovery_disabled_profile import inputs
from test_recovery_disabled_profile import no_remote_authority as no_remote_authority

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('offline_session', ROOT / 'infra/vps/prepare_recovery_offline.py')
session = importlib.util.module_from_spec(spec)
previous = list(sys.path)
try:
    sys.path.insert(0, str(ROOT / 'infra/vps'))
    spec.loader.exec_module(session)
finally:
    sys.path[:] = previous


@pytest.fixture
def local(tmp_path, monkeypatch):
    state, active = tmp_path / 'state', tmp_path / 'active'
    state.mkdir(mode=0o700)
    active.mkdir(mode=0o700)
    (state / 'deployment.lock').touch(mode=0o600)
    config, report = inputs()
    now = datetime.now(timezone.utc)
    for item in config.first_experiment.evidence.values():
        item.expires_at = (now + timedelta(hours=1)).isoformat()
    report['checked_at_utc'] = now.isoformat()
    profile_hash = digest(config.model_dump())
    report['profile']['profile_hash'] = report['database']['grant_profile_hash'] = profile_hash
    source = tmp_path / 'original.json'
    source.write_text(json.dumps({**config.model_dump(), 'credential_files': config.credential_files}))
    source.chmod(0o600)
    binding = {'config_file': str(source), 'config_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'profile_hash': profile_hash, 'telegram_readiness': True}
    bundle = {'manifest': {'revision': session.REVISION, 'data_root': str(state), 'control_uid': 1000,
        'execution_uid': 1001, 'images': {'broker': 'sha256:' + 'b' * 64}, 'first_experiment': binding},
        'compose': {'services': {'runtime-broker': {'volumes': [{'type': 'bind', 'source': str(source),
            'target': '/run/f2/config.json', 'read_only': True}], 'secrets': ['db_runtime_password'],
            'tmpfs': ['/tmp:mode=1777']}},
            'secrets': {'db_runtime_password': {'file': str(state / 'db-secret-not-read')}}}}
    journal = {'phase': 'VERIFIED', 'revision': session.REVISION, 'bundle': checksum(bundle), 'directory': str(active)}
    (state / 'deployment.json').write_text(json.dumps(journal))
    (state / 'deployment.json').chmod(0o600)
    monkeypatch.setattr(session, 'STATE', state)
    monkeypatch.setattr(session, 'ACTIVE', active)
    monkeypatch.setattr(session, 'BUNDLE', checksum(bundle))
    # The actual old release directory encloses ACTIVE on brain1. Keep the fixture
    # output outside its corresponding ancestor so the same boundary applies.
    output_parent = tmp_path / 'work'
    output_parent.mkdir(mode=0o700)
    monkeypatch.setattr(session, 'ACTIVE', active / 'preparation' / 'candidate')
    journal['directory'] = str(session.ACTIVE)
    (state / 'deployment.json').write_text(json.dumps(journal))
    monkeypatch.setattr(session, 'host_check', lambda: None)
    monkeypatch.setattr(session.profile, 'check_operator', lambda revision: None)
    monkeypatch.setattr(session, 'load_bundle', lambda path: deepcopy(bundle))
    monkeypatch.setattr(session, 'source_check', lambda manifest: None)
    container = {'Id': 'a' * 64, 'Name': '/' + session.BROKER, 'Image': bundle['manifest']['images']['broker'],
        'State': {'Running': True, 'Restarting': False}, 'HostConfig': {'Privileged': False, 'ReadonlyRootfs': True,
            'Tmpfs': {'/tmp': 'mode=1777'}}, 'Mounts': [{'Type': 'bind', 'Source': src, 'Destination': dst, 'RW': rw}
            for src, dst, rw in session.expected_mounts(bundle)],
        'Config': {'WorkingDir': '/app', 'Labels': {'com.docker.compose.project': 'acc-f23',
            'com.docker.compose.service': 'runtime-broker'}, 'Env': [
            'F1_SOURCE_REVISION=' + session.REVISION, 'PYTHONPATH=/app/src', 'F1_RUNTIME_MODE=rootless-required',
            'F1_DB_USER=f1_runtime', 'F2_INTEGRATION_CONFIG_FILE=/run/f2/config.json',
            'F2_INTEGRATION_CONFIG_SHA256=' + binding['config_sha256']]}}
    calls = []
    class Docker:
        endpoint = 'unix:///run/user/1000/docker.sock'
        def preflight(self):
            calls.append(('preflight',))
        def json(self, *args):
            calls.append(args)
            if args[:2] == ('image', 'inspect'):
                return [{'Id': bundle['manifest']['images']['broker'], 'Config': {'Labels': {
                    'org.opencontainers.image.revision': session.REVISION}}}]
            assert args[0] == 'inspect' and args[1] in {session.BROKER, 'a' * 64}
            return [deepcopy(container)]
    def run(engine, target, program):
        assert target == container['Id']
        assert program == (ROOT / 'infra/vps/inspect_first_recovery.py').read_bytes()
        calls.append(('exec-inspection', target))
        return deepcopy(report)
    monkeypatch.setattr(session, 'run_inspection', run)
    return SimpleNamespace(config=config, report=report, bundle=bundle, container=container, engine=Docker(),
        source=source, state=state, output=output_parent / 'offline', calls=calls)


def invoke(local, **kwargs):
    return session.prepare('f' * 40, int(session.time.time()) + 500,
                           output=local.output, engine=local.engine, **kwargs)


def test_one_session_records_inspection_and_only_disabled_draft_without_touching_live_inputs(local):
    old = local.source.read_bytes(), (local.state / 'deployment.json').read_bytes()
    result = invoke(local)
    assert result['state'] == 'RECOVERY_OFFLINE_DRAFT_PREPARED'
    assert result['max_calls'] == 1 and result['max_repairs'] == 0 and result['draft_disabled'] is True
    assert result['paid_calls'] == 0 and result['paid_recovery_authorized'] is False
    stored = IntegrationConfig.model_validate_json((local.output / 'draft/profile.disabled.json').read_bytes())
    assert stored.mode == 'disabled' and not stored.connected() and not stored.first_experiment.evidence
    assert local.output.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in local.output.rglob('*.json'))
    assert len([c for c in local.calls if c[0] == 'exec-inspection']) == 1
    assert old == (local.source.read_bytes(), (local.state / 'deployment.json').read_bytes())
    before = deepcopy(local.calls)
    with pytest.raises(session.Blocked, match='workspace'):
        invoke(local)
    assert local.calls == before


def test_expired_profile_only_is_expected_but_old_evidence_is_not_refreshed(local):
    local.report.update(status='BLOCKED', blockers=['profile_evidence_missing_or_expired'])
    assert invoke(local)['state'] == 'RECOVERY_OFFLINE_DRAFT_PREPARED'
    cfg = IntegrationConfig.model_validate_json((local.output / 'draft/profile.disabled.json').read_bytes())
    assert not cfg.first_experiment.evidence and cfg.first_experiment.existing_credit_usd is None


def test_unknown_extra_output_is_never_saved_to_any_artifact(local):
    local.report['private_extra'] = 'PRIVATE_VALUE_MUST_NOT_BE_SAVED'
    local.report['database']['extra'] = 'PRIVATE_VALUE_MUST_NOT_BE_SAVED'
    local.report['profile']['evidence_reference'] = 'PRIVATE_VALUE_MUST_NOT_BE_SAVED'
    invoke(local)
    assert all(b'PRIVATE_VALUE' not in p.read_bytes() for p in local.output.rglob('*.json'))


@pytest.mark.parametrize('change', ['image', 'name', 'stopped', 'privileged', 'writable', 'env_duplicate',
    'python_home', 'source_env', 'extra_mount', 'config_mount_rw', 'shadow_tmpfs', 'wrong_label'])
def test_wrong_or_modified_broker_is_rejected_before_exec_and_files(local, change):
    c = local.container
    if change == 'image':
        c['Image'] = 'sha256:' + 'c' * 64
    elif change == 'name':
        c['Name'] = '/some-other-container'
    elif change == 'stopped':
        c['State']['Running'] = False
    elif change == 'privileged':
        c['HostConfig']['Privileged'] = True
    elif change == 'writable':
        c['HostConfig']['ReadonlyRootfs'] = False
    elif change == 'env_duplicate':
        c['Config']['Env'].append('F1_SOURCE_REVISION=' + session.REVISION)
    elif change == 'python_home':
        c['Config']['Env'].append('PYTHONHOME=/tmp/unsafe')
    elif change == 'source_env':
        c['Config']['Env'][0] = 'F1_SOURCE_REVISION=' + 'c' * 40
    elif change == 'extra_mount':
        c['Mounts'].append({'Type': 'bind', 'Source': '/tmp/unsafe', 'Destination': '/app', 'RW': True})
    elif change == 'config_mount_rw':
        next(m for m in c['Mounts'] if m['Destination'] == '/run/f2/config.json')['RW'] = True
    elif change == 'shadow_tmpfs':
        c['HostConfig']['Tmpfs']['/app'] = 'mode=1777'
    else:
        c['Config']['Labels']['com.docker.compose.service'] = 'api'
    with pytest.raises(session.Blocked):
        invoke(local)
    assert not local.output.exists()
    assert not any(c[0] == 'exec-inspection' for c in local.calls)


def test_changed_profile_before_run_is_rejected_without_any_docker_call(local):
    local.source.write_bytes(local.source.read_bytes() + b'\n')
    with pytest.raises(session.Blocked, match='profile_pin'):
        invoke(local)
    assert not local.calls and not local.output.exists()


def test_exclusive_deployment_lock_prevents_racing_apply(local):
    with (local.state / 'deployment.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            invoke(local)
    assert not local.output.exists() and not local.calls


@pytest.mark.parametrize('failure', ['timeout', 'bad_report', 'uncertain_parent', 'invalid_blockers', 'deadline', 'journal_race', 'broker_race'])
def test_unknown_failure_retains_receipt_and_never_replays_or_cleans_up(local, monkeypatch, failure):
    original = session.run_inspection
    def fail(*args):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(['PRIVATE_ERROR_VALUE'], 60)
        value = original(*args)
        if failure == 'bad_report':
            value['database']['grant_digest'] = 'PRIVATE_ERROR_VALUE'
        elif failure == 'uncertain_parent':
            value.update(status='BLOCKED', blockers=['runtime_requires_review'])
        elif failure == 'invalid_blockers':
            value['blockers'] = None
        elif failure == 'deadline':
            monkeypatch.setattr(session, 'window', lambda until: session.require(False, 'window_expired'))
        elif failure == 'journal_race':
            journal = json.loads((local.state / 'deployment.json').read_bytes())
            journal['phase'] = 'INTENT'
            (local.state / 'deployment.json').write_text(json.dumps(journal))
        else:
            local.container['Id'] = 'd' * 64
        return value
    monkeypatch.setattr(session, 'run_inspection', fail)
    with pytest.raises(Exception):
        invoke(local)
    receipt = json.loads((local.output / 'session.json').read_bytes())
    assert receipt['state'] == 'BLOCKED_REQUIRES_INSPECTION'
    assert receipt['paid_recovery_authorized'] is False
    assert not (local.output / 'draft').exists()
    assert all(b'PRIVATE_ERROR' not in p.read_bytes() for p in local.output.rglob('*.json'))
    calls = deepcopy(local.calls)
    with pytest.raises(Exception):
        invoke(local)
    assert local.calls == calls


def test_exec_uses_immutable_id_local_socket_and_allows_only_documented_exit_codes(monkeypatch):
    calls = []
    def fake(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=2, stdout=b'{"status":"BLOCKED"}', stderr=b'PRIVATE_ERROR_MUST_NOT_BE_LOGGED')
    monkeypatch.setattr(session.subprocess, 'run', fake)
    monkeypatch.setenv('DOCKER_HOST', 'tcp://not-used:2375')
    engine = SimpleNamespace(endpoint='unix:///run/user/1000/docker.sock')
    assert session.run_inspection(engine, 'a' * 64, b'PUBLIC_PROGRAM') == {'status': 'BLOCKED'}
    args, values = calls[0]
    assert args == ['docker', '--host=unix:///run/user/1000/docker.sock', 'exec', '-i', 'a' * 64, 'python', '-B']
    assert values['input'] == b'PUBLIC_PROGRAM' and values['timeout'] == 60
    assert 'DOCKER_HOST' not in values['env']


@pytest.mark.parametrize('until', [None, True, 0, -1, 9_999_999_999])
def test_invalid_window_blocks_before_local_file_or_service_work(until):
    with pytest.raises(session.Blocked, match='window'):
        session.window(until)


def test_cli_never_echoes_unknown_values_or_claims_a_live_action():
    result = subprocess.run([sys.executable, str(ROOT / 'infra/vps/prepare_recovery_offline.py'),
        '--unrecognized', 'PRIVATE_INPUT_MUST_NOT_BE_ECHOED'], capture_output=True, timeout=10)
    assert result.returncode == 2 and b'PRIVATE_INPUT' not in result.stdout + result.stderr


@pytest.mark.parametrize('failure', ['journal', 'deadline', 'write_outcome'])
def test_failure_after_draft_creation_keeps_disabled_result_and_blocks_replay(local, monkeypatch, failure):
    original = session.profile.prepare
    def fail_after_write(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get('write'):
            if failure == 'journal':
                doc = json.loads((local.state / 'deployment.json').read_bytes())
                doc['phase'] = 'INTENT'
                (local.state / 'deployment.json').write_text(json.dumps(doc))
            elif failure == 'deadline':
                monkeypatch.setattr(session, 'window', lambda until: session.require(False, 'window_expired'))
            else:
                raise OSError('PRIVATE_WRITE_OUTCOME')
        return result
    monkeypatch.setattr(session.profile, 'prepare', fail_after_write)
    with pytest.raises(Exception):
        invoke(local)
    result = IntegrationConfig.model_validate_json((local.output / 'draft/profile.disabled.json').read_bytes())
    assert result.mode == 'disabled' and result.live_authorized is False and not result.connected()
    receipt = json.loads((local.output / 'session.json').read_bytes())
    assert receipt['state'] == 'BLOCKED_REQUIRES_INSPECTION'
    assert receipt['failed_at'] == 'DISABLED_DRAFT_PREPARATION_ATTEMPTED'
    assert all(b'PRIVATE_WRITE' not in p.read_bytes() for p in local.output.rglob('*.json'))
    before = deepcopy(local.calls)
    with pytest.raises(Exception):
        invoke(local)
    assert local.calls == before


@pytest.mark.parametrize('rc,stdout', [(1, b'PRIVATE_PROCESS_OUTPUT'),
    (0, b'{"status":"BLOCKED"}'), (2, b'{"status":"LOCAL_OBSERVATIONS_COMPLETE"}'),
    (0, b'x' * 65537), (0, b'not json')])
def test_exec_unknown_status_size_or_json_is_rejected(monkeypatch, rc, stdout):
    monkeypatch.setattr(session.subprocess, 'run', lambda *args, **kwargs:
        SimpleNamespace(returncode=rc, stdout=stdout, stderr=b'PRIVATE_ERROR_OUTPUT'))
    with pytest.raises(Exception):
        session.run_inspection(SimpleNamespace(endpoint='unix:///run/user/1000/docker.sock'),
                               'a' * 64, b'PUBLIC_PROGRAM')
