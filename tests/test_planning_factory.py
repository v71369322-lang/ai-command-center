"""Production factory composition with synthetic host metadata and mocked daemons."""
import hashlib
import os

import pytest

from command_center.planning_admission import PlanningProfile
from command_center.planning_host import HostDeclaration, configured_host
from command_center.runtime_broker import create_broker_app
from command_center.store import Denied, digest
from test_planning_host import host_setup as host_setup
from test_live_planning_gateway import prepared as prepared
from test_telegram_planning_authorize import profile as profile
from test_telegram_readiness import bridge as bridge
from test_telegram_service import configured as configured


def clear(monkeypatch):
    for k in list(os.environ):
        if k.startswith('F1_PLANNING_'):
            monkeypatch.delenv(k)


def test_no_configuration_is_disabled(monkeypatch):
    clear(monkeypatch)
    assert configured_host() is None


@pytest.mark.parametrize('name', ['PROFILE_FILE', 'PROFILE_SHA256', 'HOST_FILE', 'HOST_SHA256',
                                 'OPENAI_KEY_FILE', 'ENABLED'])
def test_partial_or_unknown_factory_configuration_stops_before_store(monkeypatch, name):
    clear(monkeypatch)
    monkeypatch.setenv('F1_PLANNING_' + name, 'unreviewed')
    monkeypatch.setattr('command_center.runtime_broker.Store', lambda *a: pytest.fail('store before config validation'))
    with pytest.raises(Denied, match='planning_installed_binding_invalid'):
        create_broker_app()


@pytest.fixture
def installed(host_setup, tmp_path, monkeypatch):
    from command_center import deployment_planning as binding
    value = host_setup
    directory = value.path.parent
    key_directory = tmp_path / 'installed-key'
    key_directory.mkdir(mode=0o700)
    key = key_directory / 'openai.key'
    value.prepared.key.rename(key)
    value.prepared.key = key
    host = HostDeclaration.model_validate({**value.declaration.model_dump(),
        'attestation_endpoint': 'unix:///run/user/1001/docker.sock'})
    raw = host.model_dump_json().encode()
    value.path.write_bytes(raw)
    profile = PlanningProfile.model_validate({**value.prepared.config.model_dump(),
        'runtime': {**value.prepared.config.runtime.model_dump(), 'binding_digest': digest(host.model_dump())}})
    value.prepared.save(profile)
    value.prepared.config = profile
    for name, path in (('PROFILE', directory / 'profile.json'), ('HOST', value.path), ('KEY', key)):
        monkeypatch.setattr(binding, name, str(path))
    monkeypatch.setenv('F1_PLANNING_HOST_FILE', str(value.path))
    monkeypatch.setenv('F1_PLANNING_HOST_SHA256', hashlib.sha256(raw).hexdigest())
    monkeypatch.setenv('F1_PLANNING_OPENAI_KEY_FILE', str(key))
    control = type(value.backend)()
    control.endpoint = host.attestation_endpoint

    def inspector(endpoint, mode):
        assert endpoint == host.attestation_endpoint and mode == 'rootless-required'
        return control

    monkeypatch.setattr('command_center.runtime_policy.RuntimeBackend', inspector)
    monkeypatch.setattr('command_center.runtime_broker.RuntimeBackend', lambda: value.backend)
    monkeypatch.setattr('command_center.runtime_broker.Settings.load', lambda **k: value.store.settings)
    monkeypatch.setattr('command_center.runtime_broker.Store', lambda s: value.store)
    monkeypatch.setattr('command_center.runtime_broker.RuntimeLedger', lambda p: value.ledger)
    monkeypatch.setattr('command_center.runtime_broker.broker', lambda s: None)
    token = tmp_path / 'public-broker-token'
    token.write_text('PUBLIC_SYNTHETIC_BROKER_TOKEN')
    monkeypatch.setenv('F1_RUNTIME_LEDGER', str(value.ledger.path))
    monkeypatch.setenv('F1_BROKER_TOKEN_FILE', str(token))
    return value, control


def test_factory_attests_control_daemon_without_ai_or_task_authority(installed):
    value, control = installed
    before = value.store.get(value.task_id)
    app = create_broker_app()
    runtime = app.state.runtime
    try:
        assert runtime.planning_host.attested
        assert runtime.backend is value.backend
        assert any(call[0] == 'inspect' for call in control.calls)
        assert value.backend.calls == [('preflight',)]
        assert value.prepared.constructor_calls == 0 and not value.prepared.calls
        assert value.store.get(value.task_id) == before
    finally:
        runtime.pool.shutdown(wait=True)


def test_unconfigured_factory_still_denies_planning_before_claim(installed, monkeypatch):
    value, _ = installed
    clear(monkeypatch)
    before = value.store.get(value.task_id)
    app = create_broker_app()
    runtime = app.state.runtime
    try:
        assert runtime.planning_host is None
        with pytest.raises(Denied, match='planning_runtime_not_connected'):
            runtime.submit(value.task_id, value.store.settings.source_revision)
        assert value.store.get(value.task_id) == before
        assert not value.backend.calls and not value.prepared.calls
    finally:
        runtime.pool.shutdown(wait=True)


@pytest.mark.parametrize('attack', ['control_rootless', 'control_image', 'control_policy',
                                   'profile_path', 'key_path', 'host_pin', 'extra_file', 'expired',
                                   'key_mode', 'key_symlink'])
def test_factory_refuses_unverified_installation(installed, monkeypatch, attack):
    value, control = installed
    if attack == 'control_rootless':
        control.verified = False
    elif attack == 'control_image':
        control.info['Image'] = 'sha256:' + 'f' * 64
    elif attack == 'control_policy':
        control.info['HostConfig']['Privileged'] = True
    elif attack in {'profile_path', 'key_path'}:
        monkeypatch.setenv('F1_PLANNING_' + ('PROFILE_FILE' if attack == 'profile_path' else 'OPENAI_KEY_FILE'), '/unreviewed')
    elif attack == 'host_pin':
        monkeypatch.setenv('F1_PLANNING_HOST_SHA256', 'f' * 64)
    elif attack == 'extra_file':
        (value.path.parent / 'unexpected').touch()
    elif attack == 'key_mode':
        value.prepared.key.chmod(0o644)
    elif attack == 'key_symlink':
        value.prepared.key.unlink()
        value.prepared.key.symlink_to(value.path)
    else:
        monkeypatch.setattr('command_center.planning_host.time.time', lambda: 2**40)
    with pytest.raises((Denied, ValueError, RuntimeError)):
        create_broker_app()
    assert value.prepared.constructor_calls == 0 and not value.prepared.calls
