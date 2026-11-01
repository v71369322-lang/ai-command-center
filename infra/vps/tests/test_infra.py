"""Offline semantic and negative checks; never starts Docker or contacts a server."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location('infra_' + name, ROOT / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


validator = module('validate')
probe = module('read_only_probe')


def config():
    return json.loads((ROOT / 'compose.control-plane.json').read_text())


def test_template_is_valid_but_never_deployable():
    assert validator.validate(config())['status'] == 'PASS_TEMPLATE_ONLY'
    with pytest.raises(validator.Invalid, match='not_deployable'):
        validator.validate(config(), require_deployable=True)


@pytest.mark.parametrize('field,value', [
    ('privileged', True), ('network_mode', 'host'), ('pid', 'host'),
    ('devices', ['/dev/kvm']), ('cap_add', ['SYS_ADMIN']), ('group_add', ['docker']),
    ('volumes', ['/var/run/docker.sock:/var/run/docker.sock']),
    ('ports', ['0.0.0.0:8000:8000']), ('user', '0:0'), ('read_only', False),
    ('cpus', 0), ('mem_limit', None), ('pids_limit', -1),
    ('image', 'app:latest'), ('restart', 'always'), ('env_file', ['.env']),
    ('logging', {'driver': 'json-file'}), ('tmpfs', ['/tmp']),
    ('entrypoint', ['sh', '-c', 'unsafe']), ('command', ['sh', '-c', 'unsafe']),
    ('mem_limit', '128g'), ('ports', ['[::]:8000:8000']),
])
def test_dangerous_api_configuration_rejected(field, value):
    candidate = deepcopy(config())
    candidate['services']['api'][field] = value
    with pytest.raises(validator.Invalid):
        validator.validate(candidate)


def test_worker_or_admin_secret_cannot_be_added():
    candidate = config()
    candidate['services']['worker'] = {'volumes': ['/var/run/docker.sock:/var/run/docker.sock']}
    with pytest.raises(validator.Invalid):
        validator.validate(candidate)
    candidate = config()
    candidate['services']['api']['secrets'].append('db_admin_password')
    with pytest.raises(validator.Invalid):
        validator.validate(candidate)


def test_database_is_not_public():
    candidate = config()
    candidate['services']['db']['ports'] = ['5432:5432']
    with pytest.raises(validator.Invalid):
        validator.validate(candidate)


def test_indirect_host_volume_or_external_network_is_rejected():
    for section, value in [
        ('volumes', {'pgdata': {'driver_opts': {'type': 'none', 'device': '/', 'o': 'bind'}}}),
        ('networks', {'control': {'internal': True}, 'frontend': {'external': True}}),
        ('include', ['unapproved-compose.yaml']),
    ]:
        candidate = config()
        candidate[section] = value
        with pytest.raises(validator.Invalid):
            validator.validate(candidate)
    candidate = config()
    candidate['networks']['control']['internal'] = False
    with pytest.raises(validator.Invalid):
        validator.validate(candidate)


def test_probe_inventory_does_not_touch_secrets_or_execute_with_files_only(tmp_path, monkeypatch):
    (tmp_path / 'etc').mkdir()
    (tmp_path / 'proc').mkdir()
    (tmp_path / 'etc/os-release').write_text('ID=ubuntu\nVERSION_ID="24.04"\nSECRET=not-for-output\n')
    (tmp_path / 'proc/meminfo').write_text('MemTotal: 8388608 kB\nMemAvailable: 4000000 kB\n')
    monkeypatch.setattr(probe, 'command', lambda _: pytest.fail('must not execute'))
    result = probe.inventory(tmp_path, commands=False)
    assert result['os'] == {'ID': 'ubuntu', 'VERSION_ID': '24.04'}
    assert 'not-for-output' not in json.dumps(result)
    assert result['readiness'] == 'UNVERIFIED'


def test_probe_commands_are_fixed_local_read_only():
    assert set(probe.COMMANDS) == {'kernel', 'packages', 'listeners', 'services', 'package_audit'}
    assert all(args[0] in {'uname', 'dpkg-query', 'ss', 'systemctl', 'dpkg'} for args in probe.COMMANDS.values())
    assert probe.COMMANDS['services'][1] == 'is-active'
    assert probe.COMMANDS['package_audit'] == ['dpkg', '--audit']


def test_failed_probe_does_not_publish_command_errors(monkeypatch):
    monkeypatch.setattr(probe.shutil, 'which', lambda _: '/allowed/tool')
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired('sensitive-metadata', 5)
    monkeypatch.setattr(probe.subprocess, 'run', fail)
    assert probe.command('packages') == {'state': 'unavailable'}


def test_probe_rejects_remote_or_mutating_arguments():
    result = subprocess.run([sys.executable, str(ROOT / 'read_only_probe.py'), '--host', 'forbidden.invalid'],
                            capture_output=True, timeout=5)
    assert result.returncode == 2


def test_launcher_design_never_grants_raw_socket_or_host_mounts():
    policy = json.loads((ROOT / 'templates/launcher-policy.json').read_text())
    assert policy['status'] == 'DESIGN_NOT_IMPLEMENTED'
    assert policy['transport'] == 'local-unix-typed-broker-no-raw-docker-api'
    assert not policy['host_mounts'] and not policy['privileged']
    assert policy['concurrency'] == 1 and policy['network'] == 'none'
    assert not policy['automatic_resume_after_uncertainty']


def test_firewall_and_vpn_remain_non_applicable_templates():
    firewall = (ROOT / 'templates/host-firewall.nft.example').read_text()
    assert '__VERIFIED_VPN_UDP_PORT__' in firewall
    assert 'flush ruleset' not in firewall
    vpn = (ROOT / 'templates/tailnet-policy.hujson.example').read_text()
    assert '__OWNER_IDENTITY__' in vpn and '__AUTHORIZED_CLOUD_IDENTITY__' in vpn
    assert '"*:*"' not in vpn and 'autogroup:internet' not in vpn
