"""F2.3 release-policy/failure tests. Fake daemons are NOT rootless host evidence."""
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from command_center.deployment import Deployment, Engine, initialize_state, load_bundle
from command_center.deployment_profile import atomic_json, checksum, render, validate_manifest, validate_profile
from command_center.recovery import seal


@pytest.fixture
def external_release(release, tmp_path):
    from command_center.coding.first_experiment import CAP, FirstExperiment, MODEL
    from command_center.coding.integration_config import IntegrationConfig, Tariff
    from command_center.deployment_integrations import CREDENTIAL_TARGETS, prepare_binding
    original, _ = release
    manifest = copy.deepcopy(original['manifest'])
    manifest.update(control_uid=os.getuid(), execution_uid=os.getuid() + 1)
    private = tmp_path / 'external-private'
    private.mkdir(mode=0o700)
    config = IntegrationConfig(mode='live', live_authorized=False,
        synthetic_repository='fixture/acc-f2-synthetic-deployment', budget_evidence='PUBLIC_FIXTURE_ONLY',
        daily_nano_rub=CAP, monthly_nano_rub=CAP, first_experiment=FirstExperiment(repository_id=725000001),
        tariff=Tariff(model=MODEL, input_nano_rub=67500, output_nano_rub=405000,
                      context_tokens=400000, max_output_tokens=2048, confirmed=True, evidence='PUBLIC_FIXTURE_ONLY'),
        credential_files={'openai': CREDENTIAL_TARGETS['openai_key_file'],
                          'github-installation-token': CREDENTIAL_TARGETS['github_token_file']})
    config_file = private / 'config.json'
    config_file.write_text(json.dumps({**config.model_dump(), 'credential_files': config.credential_files}))
    config_file.chmod(0o600)
    paths = {'config_file': config_file}
    for name in CREDENTIAL_TARGETS:
        path = private / name
        path.write_text('PUBLIC_SYNTHETIC_FIXTURE_' + name)
        path.chmod(0o600)
        paths[name] = path
    manifest['first_experiment'] = prepare_binding(manifest, **paths)
    profile = render(original['compose'], manifest)
    return manifest, profile, paths


def test_external_profile_is_opt_in_pinned_and_secrets_only_reach_broker(external_release, release):
    from command_center.deployment_integrations import CONFIG_TARGET, CREDENTIAL_TARGETS, check_binding
    from command_center.coding.contract import CodingRequest
    from command_center.store import Denied
    from datetime import datetime, timezone
    manifest, profile, _ = external_release
    config = check_binding(manifest)
    assert not config.live_authorized
    assert not config.first_experiment.report()['ready_for_final_confirmation']
    with pytest.raises(Denied, match='first_experiment_preconditions_missing'):
        config.first_experiment.validate_scope(config,
            CodingRequest(provider='openai', experiment_id=config.first_experiment.id).model_dump(),
            config.tariff.maximum() * 2, datetime.now(timezone.utc), final_confirmation=True)
    for name, service in profile['services'].items():
        destinations = {v['target'] for v in service.get('volumes', [])}
        assert (CONFIG_TARGET in destinations) == (name in {'api', 'runtime-broker'})
        assert bool(destinations & set(CREDENTIAL_TARGETS.values())) == (name == 'runtime-broker')
        assert ('gateway-access' in service['networks']) == (name == 'runtime-broker')
        if name in {'api', 'runtime-broker'}:
            assert service['environment']['F2_INTEGRATION_CONFIG_SHA256'] == manifest['first_experiment']['config_sha256']
    assert 'first_experiment' not in release[0]['manifest']
    assert 'gateway-access' not in release[0]['compose']['networks']
    assert load_bundle(release[1]) == release[0]


@pytest.mark.parametrize('attack', [None, 'key', 'writable', 'missing_pin', 'wrong_pin', 'gateway_network'])
def test_mobile_profile_shares_only_pinned_readonly_config(external_release, attack):
    from command_center.deployment_integrations import CONFIG_TARGET, mounts
    manifest, profile, _ = external_release
    manifest['first_experiment']['telegram_readiness'] = True
    manifest['telegram'] = {'mode': 'live', 'owner_id': 1234567, 'bot_id': 123456789,
                            'connection_digest': 'c' * 64}
    profile = render(profile, manifest)
    telegram = profile['services']['telegram']
    if attack == 'key':
        telegram['volumes'].append(mounts(manifest, 'runtime-broker')[-1])
    elif attack == 'writable':
        telegram['volumes'][-1]['read_only'] = False
    elif attack == 'missing_pin':
        telegram['environment'].pop('F2_INTEGRATION_CONFIG_SHA256')
    elif attack == 'wrong_pin':
        telegram['environment']['F2_INTEGRATION_CONFIG_SHA256'] = '0' * 64
    elif attack == 'gateway_network':
        telegram['networks']['gateway-access'] = None
    if attack:
        with pytest.raises(ValueError, match='telegram_service_boundary_changed'):
            validate_profile(profile, manifest)
    else:
        validate_profile(profile, manifest)
        assert mounts(manifest, 'telegram') == mounts(manifest, 'api')
        assert telegram['volumes'][-1]['target'] == CONFIG_TARGET
        assert telegram['secrets'] == ['db_password']
        assert set(telegram['networks']) == {'control', 'telegram-access'}
        assert not mounts({k: v for k, v in manifest.items() if k != 'telegram'}, 'telegram')


def test_legacy_external_telegram_bundle_remains_without_ai_config(external_release):
    from command_center.deployment_integrations import mounts
    manifest, profile, _ = external_release
    manifest['telegram'] = {'mode': 'live', 'owner_id': 1234567, 'bot_id': 123456789,
                            'connection_digest': 'c' * 64}
    profile = render(profile, manifest)
    validate_profile(profile, manifest)
    assert mounts(manifest, 'telegram') == []
    assert not any(k.startswith('F2_') for k in profile['services']['telegram']['environment'])


@pytest.mark.parametrize('flag', [False, 'true', 1, None])
def test_mobile_profile_flag_must_be_explicit_true(external_release, flag):
    manifest, profile, _ = external_release
    manifest['first_experiment']['telegram_readiness'] = flag
    with pytest.raises(ValueError, match='first_experiment_binding_invalid'):
        render(profile, manifest)


def test_mobile_prepare_requires_config_before_docker():
    from command_center.deployment import prepare
    with pytest.raises(ValueError, match='first_experiment_config_required'):
        prepare('/unused', '/unused/new', 1000, 1001, '/unused/state', first_experiment_telegram_readiness=True)


@pytest.mark.parametrize('attack', ['worker_key', 'api_key', 'watchdog_config', 'wrong_target', 'writable_key',
                                   'extra_mount', 'worker_egress', 'api_gateway_network', 'extra_network',
                                   'internal_egress', 'missing_pin', 'wrong_pin', 'worker_pin', 'extra_selector'])
def test_external_profile_cannot_expand_mount_network_or_environment_scope(external_release, attack):
    from command_center.deployment_integrations import mounts
    manifest, original, _ = external_release
    profile = copy.deepcopy(original)
    if attack in {'worker_key', 'api_key'}:
        name = 'worker' if attack == 'worker_key' else 'api'
        profile['services'][name]['volumes'].append(mounts(manifest, 'runtime-broker')[-1])
    elif attack == 'watchdog_config':
        profile['services']['watchdog']['volumes'].append(mounts(manifest, 'api')[0])
    elif attack in {'wrong_target', 'writable_key', 'extra_mount'}:
        service = profile['services']['runtime-broker']
        if attack == 'wrong_target':
            service['volumes'][-1]['target'] = '/run/other-token'
        elif attack == 'writable_key':
            service['volumes'][-1]['read_only'] = False
        else:
            service['volumes'].append({'type': 'bind', 'source': '/etc', 'target': '/host', 'read_only': True})
    elif attack in {'worker_egress', 'api_gateway_network'}:
        profile['services']['worker' if attack == 'worker_egress' else 'api']['networks']['gateway-access'] = None
    elif attack == 'extra_network':
        profile['networks']['extra-access'] = {'internal': False}
    elif attack == 'internal_egress':
        profile['networks']['gateway-access']['internal'] = True
    else:
        env = profile['services']['api']['environment']
        if attack == 'missing_pin':
            env.pop('F2_INTEGRATION_CONFIG_SHA256')
        elif attack == 'wrong_pin':
            env['F2_INTEGRATION_CONFIG_SHA256'] = '0' * 64
        elif attack == 'worker_pin':
            profile['services']['worker']['environment']['F2_INTEGRATION_CONFIG_SHA256'] = '0' * 64
        else:
            env['F21_OPERATOR_OVERRIDE'] = '1'
    with pytest.raises(ValueError):
        validate_profile(profile, manifest)


@pytest.mark.parametrize('attack', ['config_changed', 'config_mode', 'key_mode', 'key_missing', 'key_symlink',
                                   'key_hardlink', 'empty_key', 'app_private_key_size', 'parent_public',
                                   'same_path', 'wrong_hash', 'wrong_profile_hash'])
def test_external_binding_rechecks_private_custody_and_full_config_pin(external_release, attack):
    from command_center.deployment_integrations import check_binding
    manifest, _, paths = external_release
    if attack == 'config_changed':
        paths['config_file'].write_text(paths['config_file'].read_text() + '\n')
    elif attack in {'config_mode', 'key_mode'}:
        paths['config_file' if attack == 'config_mode' else 'openai_key_file'].chmod(0o644)
    elif attack == 'key_missing':
        paths['github_token_file'].unlink()
    elif attack == 'key_symlink':
        paths['github_token_file'].unlink()
        paths['github_token_file'].symlink_to(paths['openai_key_file'])
    elif attack == 'key_hardlink':
        paths['github_token_file'].unlink()
        os.link(paths['openai_key_file'], paths['github_token_file'])
    elif attack in {'empty_key', 'app_private_key_size'}:
        paths['github_token_file'].write_text('' if attack == 'empty_key' else 'X' * 1675)
    elif attack == 'parent_public':
        paths['config_file'].parent.chmod(0o755)
    elif attack == 'same_path':
        manifest['first_experiment']['github_token_file'] = str(paths['openai_key_file'])
    else:
        manifest['first_experiment']['config_sha256' if attack == 'wrong_hash' else 'profile_hash'] = '0' * 64
    with pytest.raises((ValueError, OSError)):
        check_binding(manifest)


@pytest.mark.parametrize('attack', ['mock', 'missing_experiment', 'missing_repo_id', 'missing_tariff',
                                   'unconfirmed_tariff', 'wrong_model', 'wrong_context', 'wrong_output',
                                   'zero_rate', 'over_budget', 'under_capacity', 'wrong_reference', 'same_alias'])
def test_external_prepare_does_not_admit_other_modes_or_unbounded_profiles(external_release, attack):
    from command_center.deployment_integrations import prepare_binding
    manifest, _, paths = external_release
    config = json.loads(paths['config_file'].read_text())
    if attack == 'mock':
        config['mode'] = 'http_mock'
    elif attack == 'missing_experiment':
        config['first_experiment'] = None
    elif attack == 'missing_repo_id':
        config['first_experiment']['repository_id'] = None
    elif attack == 'missing_tariff':
        config['tariff'] = None
    elif attack == 'unconfirmed_tariff':
        config['tariff']['confirmed'] = False
    elif attack in {'wrong_model', 'wrong_context', 'wrong_output', 'zero_rate'}:
        key, value = {'wrong_model': ('model', 'other'), 'wrong_context': ('context_tokens', 8192),
                      'wrong_output': ('max_output_tokens', 4096), 'zero_rate': ('input_nano_rub', 0)}[attack]
        config['tariff'][key] = value
    elif attack == 'over_budget':
        config['daily_nano_rub'] *= 2
    elif attack == 'under_capacity':
        config['daily_nano_rub'] = 1
    elif attack == 'wrong_reference':
        config['credential_files']['openai'] = '/run/secrets/db_runtime_password'
    else:
        config['openai_secret_ref'] = config['github_secret_ref']
    paths['config_file'].write_text(json.dumps(config))
    with pytest.raises(ValueError):
        prepare_binding(manifest, **paths)


def test_external_prepare_never_reads_key_values_or_creates_authority(external_release, monkeypatch):
    import httpx
    from command_center import deployment_integrations as integration
    from command_center.coding.integration_config import FileCredentials
    from command_center.coding.gateway import Gateway
    from command_center.store import Store
    manifest, _, paths = external_release
    def forbidden(*args, **kwargs):
        pytest.fail('prepare attempted credentials/network/authority action')
    for owner, method in ((httpx, 'Client'), (Gateway, '__init__'), (Store, '__init__'),
                          (Store, 'approve'), (Gateway, 'authorize'), (FileCredentials, 'get')):
        monkeypatch.setattr(owner, method, forbidden)
    original = integration._open_private
    checked = []
    class MetadataOnly:
        def __init__(self, stream):
            self.stream = stream
        def read(self, *args):
            forbidden()
        def close(self):
            self.stream.close()
    def guarded(path, *args, **kwargs):
        stream, metadata = original(path, *args, **kwargs)
        if Path(path) != paths['config_file']:
            checked.append(Path(path))
            stream = MetadataOnly(stream)
        return stream, metadata
    monkeypatch.setattr(integration, '_open_private', guarded)
    binding = integration.prepare_binding(manifest, **paths)
    assert binding == manifest['first_experiment']
    assert set(checked) == {paths['openai_key_file'], paths['github_token_file']}


def test_partial_external_prepare_flags_fail_before_daemon_access(monkeypatch):
    from command_center.deployment import prepare
    def forbidden(*args, **kwargs):
        pytest.fail('partial bindings reached Docker')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(ValueError, match='first_experiment_all_bindings_required'):
        prepare('/unused', '/unused/new', 1000, 1001, '/unused/state', first_experiment_config='/unused/config')


def test_external_preflight_rechecks_pin_before_images_database_or_start(external_release, monkeypatch):
    import command_center.deployment as module
    manifest, profile, paths = external_release
    paths['config_file'].write_text(paths['config_file'].read_text() + '\n')
    engine = FakeEngine()
    engine.preflight = lambda: None
    controller = Deployment({'manifest': manifest, 'compose': profile}, paths['config_file'].parent, engine, engine)
    monkeypatch.setattr(module, 'source_check', lambda manifest: None)
    def forbidden(*args, **kwargs):
        pytest.fail('changed config reached later runtime checks')
    monkeypatch.setattr(module, 'image_check', forbidden)
    with pytest.raises(ValueError, match='first_experiment_config_pin_changed'):
        controller.preflight()
    assert engine.calls == []


@pytest.mark.parametrize('telegram,attack', [(t, a) for t in (False, True)
    for a in (None, 'worker_key', 'broker_writable', 'api_missing_config', 'wrong_pin')]
    + [(True, a) for a in ('telegram_missing_config', 'telegram_writable_config', 'telegram_key')])
def test_external_postcheck_validates_actual_mounts_and_running_config(external_release, monkeypatch, telegram, attack):
    from command_center.coding.integration_config import IntegrationConfig
    from command_center.deployment_integrations import CONFIG_TARGET, check_binding, mounts
    manifest, profile, paths = external_release
    if telegram:
        manifest['first_experiment']['telegram_readiness'] = True
        manifest['telegram'] = {'mode': 'live', 'owner_id': 1234567, 'bot_id': 123456789,
                                'connection_digest': 'c' * 64}
        profile = render(profile, manifest)
    config = check_binding(manifest)
    class InspectedEngine(FakeEngine):
        def json(self, *args):
            assert args[0] == 'inspect'
            name = args[1].removeprefix('acc-f23-').removesuffix('-1')
            actual = [{'Source': v['source'], 'Destination': v['target'], 'RW': False}
                      for v in mounts(manifest, name)]
            if attack == 'worker_key' and name == 'worker':
                v = mounts(manifest, 'runtime-broker')[-1]
                actual.append({'Source': v['source'], 'Destination': v['target'], 'RW': False})
            if attack == 'broker_writable' and name == 'runtime-broker':
                actual[-1]['RW'] = True
            if attack == 'api_missing_config' and name == 'api':
                actual = []
            if name == 'telegram':
                if attack == 'telegram_missing_config':
                    actual = []
                elif attack == 'telegram_writable_config':
                    actual[0]['RW'] = True
                elif attack == 'telegram_key':
                    v = mounts(manifest, 'runtime-broker')[-1]
                    actual.append({'Source': v['source'], 'Destination': v['target'], 'RW': False})
            return [{'State': {'Running': True}, 'Mounts': actual}]
        def run(self, *args, **kwargs):
            if args[:1] == ('exec',) and args[1] in {'acc-f23-api-1', 'acc-f23-runtime-broker-1', 'acc-f23-telegram-1'}:
                with monkeypatch.context() as scope:
                    scope.setenv('F2_INTEGRATION_CONFIG_FILE', CONFIG_TARGET)
                    scope.setenv('F2_INTEGRATION_CONFIG_SHA256',
                                 '0' * 64 if attack == 'wrong_pin' else manifest['first_experiment']['config_sha256'])
                    scope.setattr(IntegrationConfig, 'load', lambda: config)
                    exec(compile(args[-1], 'fake_container_config_check.py', 'exec'), {})
            return super().run(*args, **kwargs)
    engine = InspectedEngine()
    controller = Deployment({'manifest': manifest, 'compose': profile}, paths['config_file'].parent, engine, engine)
    monkeypatch.setattr(controller, 'tool', lambda code: b'')  # Explicitly fake DB for this policy test.
    if attack:
        with pytest.raises((ValueError, AssertionError)):
            controller.postcheck()
    else:
        assert controller.postcheck()['state'] == 'CLOSED_SYNTHETIC_SERVICES_RUNNING'
        assert sum(c[:1] == ('exec',) and c[1] in {'acc-f23-api-1', 'acc-f23-runtime-broker-1', 'acc-f23-telegram-1'}
                   for c in engine.calls) == (3 if telegram else 2)


@pytest.mark.parametrize('telegram', [False, True])
def test_prepare_cli_propagates_only_explicit_binding_paths(monkeypatch, capsys, telegram):
    import sys
    import command_center.deployment as module
    calls = []
    monkeypatch.setattr(module, 'prepare', lambda *args, **kwargs: calls.append((args, kwargs)) or 'a' * 64)
    monkeypatch.setattr(sys, 'argv', ['deployment', 'prepare', '--source', '/source', '--bundle', '/new',
        '--control-uid', '1000', '--execution-uid', '1001', '--data-root', '/state',
        '--first-experiment-config', '/private/config', '--openai-key-file', '/private/openai',
        '--github-token-file', '/private/github'] + (['--first-experiment-telegram-readiness'] if telegram else []))
    module.main()
    assert json.loads(capsys.readouterr().out)['bundle_digest'] == 'a' * 64
    assert calls[0][1] == dict(owner_password_origin=None, password_loopback_http=False,
        telegram_connection_digest=None, first_experiment_config='/private/config',
        openai_key_file='/private/openai', github_token_file='/private/github',
        first_experiment_telegram_readiness=telegram)


@pytest.mark.parametrize('arguments', [['--first-experiment-config', '/private/config'],
                                    ['--first-experiment-telegram-readiness']])
def test_non_prepare_cli_cannot_silently_ignore_integration_binding(monkeypatch, arguments):
    import sys
    import command_center.deployment as module
    monkeypatch.setattr(sys, 'argv', ['deployment', 'update', '--bundle', '/unused'] + arguments)
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2


def test_external_binding_cannot_point_inside_build_context_or_accept_secret_input_error(external_release):
    from command_center.deployment_integrations import check_binding, prepare_binding
    manifest, _, paths = external_release
    manifest['source_root'] = str(paths['config_file'].parent)
    with pytest.raises(ValueError, match='first_experiment_private_path_required'):
        check_binding(manifest)
    manifest['source_root'] = '/synthetic/source'
    marker = 'PUBLIC_SYNTHETIC_CREDENTIAL_DO_NOT_ECHO'
    paths['config_file'].write_text(json.dumps({'invalid': marker}))
    with pytest.raises(ValueError, match='first_experiment_config_invalid') as error:
        prepare_binding(manifest, **paths)
    assert marker not in str(error.value)


@pytest.fixture
def release(tmp_path):
    root = tmp_path / 'state'
    initialize_state(root)
    source = Path(__file__).resolve().parents[1]
    env = dict(os.environ, F1_SOURCE_REVISION='a' * 40, F1_DOCKER_GID='0')
    result = subprocess.run(['docker', 'compose', '--profile', 'worker', '-f', str(source / 'compose.yaml'), 'config', '--format', 'json'],
                            capture_output=True, env=env, check=True)
    base = json.loads(result.stdout)
    m = dict(schema=1, revision='a' * 40, control_uid=1000, execution_uid=1001, data_root=str(root),
             source_root=str(source), images={k: 'sha256:' + str(i) * 64 for i, k in enumerate(
                 ('api', 'worker', 'broker', 'executor', 'coding'), 1)},
             database_image=base['services']['db']['image'], redis_image=base['services']['redis']['image'],
             migration_hash='b' * 64)
    directory = tmp_path / 'release'
    directory.mkdir(mode=0o700)
    bundle = {'manifest': m, 'compose': render(base, m)}
    atomic_json(directory / 'bundle.json', bundle)
    atomic_json(directory / 'compose.json', bundle['compose'])
    return bundle, directory


def test_password_profile_is_explicit_and_api_only(release):
    original, _ = release
    m = copy.deepcopy(original['manifest'])
    m['owner_login'] = {'origin': 'http://127.0.0.1:18000', 'loopback_http': True}
    # Use the same normalized source compose used by the existing fixture.
    source = Path(__file__).resolve().parents[1]
    env = dict(os.environ, F1_SOURCE_REVISION='a' * 40, F1_DOCKER_GID='0')
    base = json.loads(subprocess.check_output(['docker', 'compose', '--profile', 'worker', '-f',
        str(source / 'compose.yaml'), 'config', '--format', 'json'], env=env))
    p = render(base, m)
    assert p['services']['api']['environment']['F1_AUTH_MODE'] == 'password'
    assert p['services']['api']['ports'][0]['host_ip'] == '127.0.0.1'
    for name, service in p['services'].items():
        mounted = any(v['target'] == '/run/owner/password.json' for v in service.get('volumes', []))
        assert mounted == (name == 'api')
    bad = copy.deepcopy(p)
    bad['services']['api']['environment']['F1_WEB_ORIGIN'] = 'http://evil.invalid'
    with pytest.raises(ValueError, match='password_login_binding_changed'):
        validate_profile(bad, m)
    m['owner_login']['origin'] = 'http://public.example'
    with pytest.raises(ValueError, match='password_origin_invalid'):
        validate_manifest(m)


def telegram_release(release):
    bundle, _ = release
    m = copy.deepcopy(bundle['manifest'])
    m['telegram'] = {'mode': 'live', 'owner_id': 1234567, 'bot_id': 123456789,
                     'connection_digest': 'c' * 64}
    env = dict(os.environ, F1_SOURCE_REVISION='a' * 40, F1_DOCKER_GID='0')
    base = json.loads(subprocess.check_output(['docker', 'compose', '--profile', 'worker', '-f',
        str(Path(m['source_root']) / 'compose.yaml'), 'config', '--format', 'json'], env=env))
    return m, render(base, m)


def test_telegram_profile_is_explicit_db_only_and_default_stays_closed(release):
    m, profile = telegram_release(release)
    service = profile['services']['telegram']
    assert service['secrets'] == ['db_password'] and service['restart'] == 'no'
    assert not service.get('ports') and not service.get('privileged')
    assert all('docker.sock' not in v['source'] for v in service['volumes'])
    assert set(service['environment']) == {'F1_SOURCE_REVISION', 'F1_DB_USER', 'F1_DB_HOST', 'F1_DB_PASSWORD_FILE'}
    assert json.loads(profile['services']['api']['environment']['F1_TELEGRAM_SCOPE']) == m['telegram']
    assert 'telegram' not in release[0]['compose']['services']


@pytest.mark.parametrize('attack', ['socket', 'ports', 'network', 'secrets', 'cpu', 'memory', 'pids', 'restart', 'command', 'scope'])
def test_telegram_profile_rejects_extra_authority_and_unbounded_resources(release, attack):
    m, p = telegram_release(release)
    t = p['services']['telegram']
    if attack == 'socket':
        t['volumes'].append({'source': '/var/run/docker.sock', 'target': '/var/run/docker.sock'})
    elif attack == 'ports':
        t['ports'] = ['8001:8001']
    elif attack == 'network':
        t['networks']['access'] = None
    elif attack == 'secrets':
        t['secrets'].append('db_admin_password')
    elif attack == 'cpu':
        t['cpus'] = 4
    elif attack == 'memory':
        t['mem_limit'] = '8g'
    elif attack == 'pids':
        t['pids_limit'] = 99999
    elif attack == 'restart':
        t['restart'] = 'always'
    elif attack == 'command':
        t['command'] = ['sh']
    else:
        p['services']['api']['environment']['F1_TELEGRAM_SCOPE'] = '{}'
    with pytest.raises(ValueError):
        validate_profile(p, m)


def test_telegram_release_rejects_mock_or_extra_manifest_scope(release):
    m, _ = telegram_release(release)
    for value in ({**m['telegram'], 'mode': 'http_mock'}, {**m['telegram'], 'endpoint': 'https://other.invalid'}):
        with pytest.raises(ValueError, match='telegram_release_binding_invalid'):
            validate_manifest({**m, 'telegram': value})


def test_disabling_telegram_stops_previous_poller_and_blocks_unconfirmed_stop(release, tmp_path):
    m, old_profile = telegram_release(release)
    directory = tmp_path / 'telegram-old'
    directory.mkdir(mode=0o700)
    old = {'manifest': m, 'compose': old_profile}
    atomic_json(directory / 'bundle.json', old)
    atomic_json(directory / 'compose.json', old_profile)
    atomic_json(Path(m['data_root']) / 'deployment.json', {
        'phase': 'VERIFIED', 'bundle': checksum(old), 'directory': str(directory)})

    class StubbornEngine(FakeEngine):
        def run(self, *args, **kwargs):
            super().run(*args, **kwargs)
            return b'container-still-running' if args[0] == 'ps' else b''

    engine = StubbornEngine()
    target, target_dir = release
    controller = Deployment(target, target_dir, engine, engine)
    with pytest.raises(ValueError, match='stop_unconfirmed'):
        controller.pause_telegram()
    assert str(directory / 'compose.json') in engine.calls[0] and engine.calls[0][-2:] == ('stop', 'telegram')
    assert not any('up' in c for c in engine.calls)


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.fail = False

    def run(self, *args, **kwargs):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError('daemon_unavailable')
        return b''


@pytest.fixture
def operator(release, monkeypatch):
    bundle, directory = release
    engine = FakeEngine()
    deployment = Deployment(bundle, directory, engine, FakeEngine())
    monkeypatch.setattr(deployment, 'preflight', lambda **kwargs: None)
    monkeypatch.setattr(deployment, 'postcheck', lambda: {'go_live': False})
    monkeypatch.setattr(deployment, 'tool', lambda code: engine.run('maintenance', code))
    monkeypatch.setattr(deployment, 'quiesce', lambda: engine.run('quiesce'))
    monkeypatch.setattr(deployment, 'backup', lambda: engine.run('encrypted_backup'))
    return deployment


def mark_current(deployment, *, phase='VERIFIED', previous='old'):
    value = {'phase': phase, 'bundle': 'current', 'migration_hash': deployment.m['migration_hash'],
             'database_image': deployment.m['database_image'], 'previous_bundle': previous}
    atomic_json(deployment.root / 'deployment.json', value)
    return value


@pytest.mark.parametrize('change', ['bundle', 'pending', 'missing', 'malformed'])
def test_remote_update_predecessor_is_checked_before_any_effect(operator, change):
    previous = mark_current(operator)
    previous['bundle'] = 'c' * 64
    expected = 'c' * 64
    if change == 'bundle':
        previous['bundle'] = 'd' * 64
    elif change == 'pending':
        previous['phase'] = 'INTENT'
    elif change == 'malformed':
        expected = 'main'
    atomic_json(operator.root / 'deployment.json', previous)
    if change == 'missing':
        (operator.root / 'deployment.json').unlink()
    with pytest.raises(ValueError, match='expected_previous_release_changed'):
        operator.apply('update', checksum(operator.bundle), expected_previous=expected)
    assert operator.engine.calls == []


def test_remote_update_exact_predecessor_uses_existing_backup_and_interlock(operator):
    previous = mark_current(operator)
    previous['bundle'] = 'c' * 64
    atomic_json(operator.root / 'deployment.json', previous)
    operator.apply('update', checksum(operator.bundle), expected_previous='c' * 64)
    calls = operator.engine.calls
    assert calls[0] == ('quiesce',) and calls[1] == ('encrypted_backup',)
    receipt = json.loads((operator.root / 'deployment.json').read_text())
    assert receipt['phase'] == 'VERIFIED' and receipt['previous_bundle'] == 'c' * 64


@pytest.mark.parametrize('change', ['none', 'predecessor', 'pending', 'owner_login', 'migration',
                                   'data_root', 'control_uid', 'catalog_revision', 'telegram_owner'])
def test_host_channel_enforces_owner_scope_and_ready_prepared_release(release, monkeypatch, change):
    import command_center.deployment as deployment_module
    import command_center.operations_channel as operations
    before = copy.deepcopy(release[0])
    target = copy.deepcopy(before)
    for value in (before, target):
        value['manifest']['data_root'] = '/home/acc-control/f30/state'
    target['manifest']['revision'] = 'd' * 40
    if change == 'owner_login':
        target['manifest']['owner_login'] = {'origin': 'http://127.0.0.1:18000', 'loopback_http': True}
    elif change == 'migration':
        target['manifest']['migration_hash'] = 'f' * 64
    elif change == 'data_root':
        target['manifest']['data_root'] = '/home/acc-control/other-state'
    elif change == 'control_uid':
        target['manifest']['control_uid'] = 0
    elif change == 'telegram_owner':
        before['manifest']['telegram'] = {'mode': 'live', 'owner_id': 12, 'bot_id': 34}
        target['manifest']['telegram'] = {'mode': 'live', 'owner_id': 56, 'bot_id': 34}
    active = dict(phase='INTENT' if change == 'pending' else 'VERIFIED',
                  bundle=checksum(before), directory='/home/acc-control/old/bundle')
    request = dict(action='update', target_bundle=checksum(target), expected_bundle=active['bundle'])
    if change == 'predecessor':
        request['expected_bundle'] = 'e' * 64
    policy = {'releases': {request['target_bundle']: dict(directory='/home/acc-control/new/bundle',
                         revision='f' * 40 if change == 'catalog_revision' else target['manifest']['revision'])}}
    monkeypatch.setattr(operations, 'protected_read', lambda *args, **kwargs: operations.canonical(active))
    monkeypatch.setattr(deployment_module, 'load_bundle', lambda p:
                        before if p == active['directory'] else target)
    monkeypatch.setattr(Deployment, 'preflight', lambda self: None)
    backend = operations.HostBackend(policy)
    if change == 'none':
        prepared = backend.prepare(request)
        assert prepared.bundle == target
        invoked = []
        monkeypatch.setattr(prepared, 'apply', lambda *args, **kwargs: invoked.append((args, kwargs)))
        backend.execute(request, prepared)
        assert invoked == [(('update', request['target_bundle']), {'expected_previous': request['expected_bundle']})]
    else:
        with pytest.raises(operations.Blocked):
            backend.prepare(request)


def test_profile_closed_and_normalizes_with_real_compose(release):
    bundle, directory = release
    result = subprocess.run(['docker', 'compose', '-f', str(directory / 'compose.json'), 'config', '--format', 'json'],
                            capture_output=True, check=True)
    p = json.loads(result.stdout)
    assert set(p['services']) == {'db', 'redis', 'api', 'worker', 'runtime-broker', 'watchdog'}
    assert p['services']['api']['environment']['F1_AUTH_MODE'] == 'oidc'
    assert p['services']['api']['environment']['F1_OIDC_OWNER'] == ''
    assert 'build' not in p['services']['api']
    assert p['volumes']['pgdata']['name'] == 'acc-f23-pgdata'
    assert load_bundle(directory) == bundle


@pytest.mark.parametrize('attack', ['public', 'privileged', 'socket', 'host_mount', 'host_network',
                                   'synthetic_auth', 'rootful', 'integration', 'wrong_image', 'secret_scope', 'egress'])
def test_profile_rejects_boundary_changes(release, attack):
    bundle, _ = release
    p = copy.deepcopy(bundle['compose'])
    api = p['services']['api']
    if attack == 'public':
        api['ports'][0]['host_ip'] = '0.0.0.0'
    elif attack == 'privileged':
        api['privileged'] = True
    elif attack == 'socket':
        api['volumes'].append({'source': '/var/run/docker.sock', 'target': '/var/run/docker.sock'})
    elif attack == 'host_mount':
        api['volumes'].append({'source': '/etc', 'target': '/host', 'read_only': True})
    elif attack == 'host_network':
        api['network_mode'] = 'host'
    elif attack == 'synthetic_auth':
        api['environment']['F1_AUTH_MODE'] = 'synthetic'
    elif attack == 'rootful':
        p['services']['watchdog']['environment']['F1_RUNTIME_MODE'] = 'cloud-rootful-test'
    elif attack == 'integration':
        api['environment']['F2_INTEGRATION_CONFIG_FILE'] = '/host/live.json'
    elif attack == 'wrong_image':
        api['image'] = 'alpine:latest'
    elif attack == 'secret_scope':
        api['secrets'].append({'source': 'db_admin_password'})
    else:
        api['networks'] = {'unapproved': None}
    with pytest.raises(ValueError):
        validate_profile(p, bundle['manifest'])


@pytest.mark.parametrize('field,value', [('control_uid', 0), ('execution_uid', 1000), ('revision', 'main'),
                                       ('database_image', 'postgres:latest'), ('data_root', '../state')])
def test_manifest_rejects_unpinned_or_privileged(release, field, value):
    m = copy.deepcopy(release[0]['manifest'])
    m[field] = value
    with pytest.raises(ValueError):
        validate_manifest(m)


def test_secret_initialization_never_overwrites_or_prints(tmp_path, capsys):
    root = tmp_path / 'state'
    initialize_state(root)
    contents = (root / 'secrets/db_password').read_bytes()
    assert (root.stat().st_mode & 0o777) == 0o700
    assert all((p.stat().st_mode & 0o777) == 0o600 for p in (root / 'secrets').iterdir())
    with pytest.raises(FileExistsError):
        initialize_state(root)
    assert contents == (root / 'secrets/db_password').read_bytes()
    assert not capsys.readouterr().out


def test_bundle_tamper_and_symlink_rejected(release, tmp_path):
    _, directory = release
    atomic_json(directory / 'compose.json', {})
    with pytest.raises(ValueError, match='profile_changed'):
        load_bundle(directory)
    link = tmp_path / 'alias'
    link.symlink_to(directory)
    with pytest.raises(ValueError, match='custody'):
        load_bundle(link)


def test_install_is_bounded_and_halted(operator):
    result = operator.apply('install', checksum(operator.bundle))
    assert result == {'go_live': False}
    commands = str(operator.engine.calls)
    assert 'halt' in commands and 'command_center.admin' in commands
    assert 'pull' in commands and 'never' in commands
    assert 'down' not in commands and 'volume rm' not in commands
    assert json.loads((operator.root / 'deployment.json').read_text())['phase'] == 'VERIFIED'


def test_wrong_consent_cannot_start_any_command(operator):
    with pytest.raises(ValueError, match='authorization'):
        operator.apply('install', 'old-digest')
    assert not operator.engine.calls


def test_boot_cannot_race_update_lock(operator):
    state = mark_current(operator)
    state['bundle'] = checksum(operator.bundle)
    atomic_json(operator.root / 'deployment.json', state)
    with (operator.root / 'deployment.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            operator.boot()
    assert not operator.engine.calls


def test_restart_policy_cannot_bypass_boot_interlock(release):
    p = release[0]['compose']
    for name in ('api', 'worker', 'runtime-broker', 'watchdog'):
        assert p['services'][name]['restart'] == 'no'


def test_update_preflight_rejects_modified_bind_source(release, monkeypatch):
    import command_center.deployment as module
    bundle, directory = release
    engine = FakeEngine()
    engine.preflight = lambda: None
    deployment = Deployment(bundle, directory, engine, engine)
    monkeypatch.setattr(os, 'getuid', lambda: 1000)
    monkeypatch.setattr(module, 'image_check', lambda *args: None)
    def changed(_):
        raise ValueError('source_checkout_changed')
    monkeypatch.setattr(module, 'source_check', changed)
    with pytest.raises(ValueError, match='source_checkout_changed'):
        deployment.preflight(fresh=False)


def test_update_quiesce_backup_before_any_stop(operator):
    mark_current(operator)
    operator.apply('update', checksum(operator.bundle))
    commands = operator.engine.calls
    assert commands[0] == ('quiesce',) and commands[1] == ('encrypted_backup',)
    assert 'stop' in commands[2]
    assert not any('command_center.admin' in str(c) for c in commands)


@pytest.mark.parametrize('fault', ['cancel_uncertain', 'backup_failure'])
def test_update_cannot_stop_services_if_safe_checkpoint_fails(operator, monkeypatch, fault):
    mark_current(operator)
    def fail():
        raise ValueError(fault)
    monkeypatch.setattr(operator, 'quiesce' if fault == 'cancel_uncertain' else 'backup', fail)
    with pytest.raises(ValueError, match=fault):
        operator.apply('update', checksum(operator.bundle))
    assert not any('stop' in c for c in operator.engine.calls)
    assert json.loads((operator.root / 'deployment.json').read_text())['phase'] == 'VERIFIED'


@pytest.mark.parametrize('change', ['schema', 'major'])
def test_database_changes_are_not_automatic(operator, change):
    old = mark_current(operator)
    old['migration_hash' if change == 'schema' else 'database_image'] = 'different'
    atomic_json(operator.root / 'deployment.json', old)
    with pytest.raises(ValueError, match='migration_plan'):
        operator.apply('update', checksum(operator.bundle))
    assert not operator.engine.calls


def test_failed_rollout_is_durable_and_not_blindly_retried(operator, monkeypatch):
    def fail(*args):
        raise RuntimeError('lost_daemon_response')
    monkeypatch.setattr(operator, 'compose', fail)
    with pytest.raises(RuntimeError):
        operator.apply('install', checksum(operator.bundle))
    assert json.loads((operator.root / 'deployment.json').read_text())['phase'] == 'INTENT'
    with pytest.raises(ValueError, match='investigation'):
        operator.apply('update', checksum(operator.bundle))


@pytest.mark.parametrize('phase', ['VERIFIED', 'INTENT'])
def test_rollback_only_exact_predecessor_without_database_restore(operator, phase):
    mark_current(operator, phase=phase, previous=checksum(operator.bundle))
    operator.apply('rollback', checksum(operator.bundle))
    assert 'pg_restore' not in str(operator.engine.calls)
    assert 'command_center.admin' not in str(operator.engine.calls)


def test_rollback_other_release_denied(operator):
    mark_current(operator, previous='different')
    with pytest.raises(ValueError, match='predecessor'):
        operator.apply('rollback', checksum(operator.bundle))
    assert not operator.engine.calls


@pytest.mark.parametrize('corruption', ['ciphertext', 'wrong_key', 'checksum'])
def test_corrupt_backup_never_reaches_restore_runtime(release, corruption):
    bundle, directory = release
    engine = FakeEngine()
    deployment = Deployment(bundle, directory, engine)
    key = bytes.fromhex((deployment.root / 'secrets/backup_key').read_text())
    payload = json.dumps({'schema': 1, 'dump_sha256': 'incorrect'}).encode() + b'\n' + b'dump'
    archive = bytearray(seal(payload, key))
    if corruption == 'ciphertext':
        archive[-1] ^= 1
    if corruption == 'wrong_key':
        (deployment.root / 'secrets/backup_key').write_text('00' * 32)
    path = deployment.root / 'backups/test.enc'
    path.write_bytes(archive)
    with pytest.raises(Exception):
        deployment.restore_check(path)
    assert not engine.calls


@pytest.mark.parametrize('rootless,cgroup,memory', [(False, '2', True), (True, '1', True), (True, '2', False)])
def test_runtime_preflight_fails_closed(monkeypatch, rootless, cgroup, memory):
    engine = Engine(1000)
    monkeypatch.setattr(Path, 'stat', lambda self: SimpleNamespace(st_mode=0o140600, st_uid=1000))
    monkeypatch.setattr(engine, 'json', lambda *args: {'SecurityOptions': ['name=rootless'] if rootless else [],
        'CgroupVersion': cgroup, 'MemoryLimit': memory, 'PidsLimit': True, 'CpuCfsQuota': True})
    with pytest.raises(ValueError, match='cgroup'):
        engine.preflight()


def test_bootstrap_plan_defaults_no_mutation_and_capacity_floor():
    path = Path(__file__).resolve().parents[1] / 'infra/vps/bootstrap_f23.py'
    spec = importlib.util.spec_from_file_location('f23bootstrap', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    p = module.plan('1:1.2.3-1~ubuntu.24.04~noble', '1.2', '1.2', '1.2')
    assert p['network_changes'] is False and p['rootless_users'] == 2
    with pytest.raises(ValueError, match='versions'):
        module.plan('', '', '', '')
    with pytest.raises(ValueError, match='capacity'):
        module.capacity_gate(2, 8192, 20000)
    module.capacity_gate(4, 7600, 20000)
    with pytest.raises(ValueError, match='authorization'):
        module.apply(p, 'no-permission')
