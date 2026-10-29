"""Real private files/RSA + strict HTTP mock; no live credential or GitHub call."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest

from command_center.coding.first_experiment import BASE_SHA
from command_center.coding.gateway import Gateway
from command_center.store import Store

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('github_token_operator', ROOT / 'infra/vps/prepare_github_token.py')
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)
REVISION, NOW = 'a' * 40, 1793289600
TOKEN = 'ghs_5524444.PUBLIC_SYNTHETIC_TOKEN_ONLY.fake_signature'


@pytest.fixture(autouse=True)
def no_live_http(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request',
                        lambda *a, **k: pytest.fail('operator tests never use live HTTP'))


@pytest.fixture(scope='module')
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def fixture(tmp_path, monkeypatch, rsa_key):
    def forbidden(*a, **k):
        pytest.fail('no runtime database, gateway or real transport')
    monkeypatch.setattr(Store, '__init__', forbidden)
    monkeypatch.setattr(Gateway, '__init__', forbidden)
    monkeypatch.setattr(operator.time, 'time', lambda: NOW)
    monkeypatch.setattr(operator, 'check_source', lambda revision: None if revision == REVISION else
                        (_ for _ in ()).throw(operator.Blocked('fixture wrong source')))
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    key = private / 'app.pem'
    key.write_bytes(rsa_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                         serialization.NoEncryption()))
    key.chmod(0o600)
    output = private / 'attempt'
    return key, output


class FakeGitHub:
    def __init__(self, public_key):
        self.public_key, self.calls, self.after, self.mutate = public_key, [], None, None

    def handle(self, request):
        assert request.url.scheme == 'https' and request.url.host == 'api.github.com'
        path = request.url.raw_path.decode()
        method = request.method
        assert (method, path) in operator.ALLOWED
        self.calls.append((method, path))
        auth = request.headers['Authorization'].removeprefix('Bearer ')
        assert request.headers['X-GitHub-Api-Version'] == '2026-03-10'
        if path in {'/app', operator.APP_INSTALLATION, operator.REPO + '/installation', operator.TOKEN_ENDPOINT}:
            claims = jwt.decode(auth, self.public_key, algorithms=['RS256'],
                                options={'verify_exp': False, 'verify_iat': False})
            assert claims == {'iat': NOW - 60, 'exp': NOW + 300, 'iss': str(operator.APP_ID)}
        else:
            assert auth == TOKEN
        account = {'id': operator.ACCOUNT_ID, 'login': operator.OWNER}
        installation = {'id': operator.INSTALLATION_ID, 'app_id': operator.APP_ID, 'account': account,
                        'permissions': deepcopy(operator.PERMISSIONS), 'repository_selection': 'selected',
                        'suspended_at': None}
        repo = {'id': operator.REPOSITORY_ID, 'full_name': operator.REPOSITORY, 'archived': False,
                'disabled': False, 'permissions': {'admin': False, 'push': True}}
        replies = {
            '/app': {'id': operator.APP_ID, 'slug': operator.APP_SLUG, 'owner': account,
                     'permissions': deepcopy(operator.PERMISSIONS)},
            operator.APP_INSTALLATION: installation,
            operator.REPO + '/installation': deepcopy(installation),
            operator.TOKEN_ENDPOINT: {'token': TOKEN, 'permissions': deepcopy(operator.PERMISSIONS),
                'repository_selection': 'selected', 'repositories': [deepcopy(repo)],
                'expires_at': datetime.fromtimestamp(NOW + 3600, timezone.utc).isoformat()},
            operator.TOKEN_REPOSITORIES: {'total_count': 1, 'repositories': [deepcopy(repo)]},
            operator.REPO: repo,
            operator.REPO + '/branches/main': {'name': 'main', 'protected': True, 'commit': {'sha': BASE_SHA}},
        }
        if method == 'POST':
            assert json.loads(request.content) == operator.REQUEST
        else:
            assert not request.content
        reply = replies[path]
        if self.mutate:
            self.mutate(path, reply)
        if self.after:
            self.after(path)
        return httpx.Response(201 if method == 'POST' else 200, json=reply)


def run(fixture, fake, **kwargs):
    key, output = fixture
    plan = operator.describe(key, output, REVISION)[2]
    return operator.prepare(key, output, REVISION, plan['plan_digest'], NOW + 300,
                            transport=httpx.MockTransport(fake.handle), **kwargs)


def test_plan_is_offline_no_files_or_authority(fixture, monkeypatch):
    monkeypatch.setattr(httpx, 'Client', lambda **k: pytest.fail('offline plan cannot create a client'))
    key, output = fixture
    report = operator.describe(key, output, REVISION)[2]
    assert report['repository_id'] == operator.REPOSITORY_ID and len(report['plan_digest']) == 64
    assert 'key_file' not in report and 'output_directory' not in report
    assert not output.exists()


def test_one_shot_token_is_scoped_verified_private_and_unconnected(fixture, rsa_key, caplog):
    caplog.set_level(logging.DEBUG)
    fake = FakeGitHub(rsa_key.public_key())
    report = run(fixture, fake)
    key, output = fixture
    assert report['phase'] == 'TOKEN_STORED_NOT_CONNECTED'
    assert report['token_repository_count_verified'] is True
    assert report['installation_repository_count_verified'] is False
    assert report['repository_changes'] is report['application_configuration_changed'] is False
    assert report['paid_calls'] == 0
    assert fake.calls == [('GET', '/app'), ('GET', operator.APP_INSTALLATION),
        ('GET', operator.REPO + '/installation'), ('POST', operator.TOKEN_ENDPOINT),
        ('GET', operator.TOKEN_REPOSITORIES), ('GET', operator.REPO), ('GET', operator.REPO + '/branches/main')]
    assert (output / 'installation.token').read_text() == TOKEN
    assert output.stat().st_mode & 0o777 == 0o700
    for file in output.iterdir():
        assert file.stat().st_uid == os.geteuid() and file.stat().st_mode & 0o777 == 0o600
    receipt = (output / 'receipt.json').read_text()
    assert json.loads(receipt) == report
    assert TOKEN not in receipt + caplog.text + json.dumps(report) and 'PRIVATE KEY' not in receipt + caplog.text
    before = deepcopy(fake.calls), receipt, key.read_bytes()
    with pytest.raises(operator.Blocked, match='existing_attempt'):
        run(fixture, fake)
    assert (deepcopy(fake.calls), (output / 'receipt.json').read_text(), key.read_bytes()) == before


@pytest.mark.parametrize('attack', ['plan', 'source', 'expired', 'too_long', 'none', 'float'])
def test_missing_or_changed_exact_approval_does_not_start_network_or_write(fixture, monkeypatch, attack):
    key, output = fixture
    plan = operator.describe(key, output, REVISION)[2]['plan_digest']
    revision, until = REVISION, NOW + 300
    if attack == 'plan':
        plan = '0' * 64
    if attack == 'source':
        revision = 'b' * 40
    if attack in {'expired', 'too_long', 'none', 'float'}:
        until = {'expired': NOW, 'too_long': NOW + 601, 'none': None, 'float': NOW + 10.0}[attack]
    monkeypatch.setattr(httpx, 'Client', lambda **k: pytest.fail('must reject before HTTP'))
    with pytest.raises(operator.Blocked):
        operator.prepare(key, output, revision, plan, until)
    assert not output.exists()


@pytest.mark.parametrize('change', ['key', 'output_path', 'key_path'])
def test_reviewed_plan_is_bound_to_key_identity_and_both_paths(fixture, monkeypatch, change):
    key, output = fixture
    plan = operator.describe(key, output, REVISION)[2]['plan_digest']
    if change == 'key':
        replacement = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key.write_bytes(replacement.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    elif change == 'output_path':
        output = output.with_name('another-attempt')
    else:
        other = key.with_name('another-key.pem')
        other.write_bytes(key.read_bytes())
        other.chmod(0o600)
        key = other
    monkeypatch.setattr(httpx, 'Client', lambda **k: pytest.fail('changed plan cannot issue a token'))
    with pytest.raises(operator.Blocked, match='exact_plan'):
        operator.prepare(key, output, REVISION, plan, NOW + 300)
    assert not output.exists()


@pytest.mark.parametrize('attack', ['key_mode', 'key_readonly', 'parent_mode', 'key_symlink', 'key_hardlink', 'output_symlink',
                                  'output_exists', 'noncanonical', 'source_directory', 'root'])
def test_unsafe_custody_rejected_before_network(fixture, monkeypatch, attack):
    key, output = fixture
    if attack == 'key_mode':
        key.chmod(0o644)
    elif attack == 'key_readonly':
        key.chmod(0o400)
    elif attack == 'parent_mode':
        key.parent.chmod(0o755)
    elif attack in {'key_symlink', 'key_hardlink'}:
        other = key.with_name('other.pem')
        if attack == 'key_symlink':
            other.symlink_to(key)
        else:
            os.link(key, other)
        key = other
    elif attack == 'output_symlink':
        output.symlink_to(key.parent, target_is_directory=True)
    elif attack == 'output_exists':
        output.mkdir(mode=0o700)
    elif attack == 'noncanonical':
        output = str(key.parent) + '/../private/new'
    elif attack == 'source_directory':
        monkeypatch.setattr(operator, 'ROOT', key.parent)
    elif attack == 'root':
        monkeypatch.setattr(operator.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(httpx, 'Client', lambda **k: pytest.fail('custody first'))
    with pytest.raises((operator.Blocked, ValueError)):
        operator.describe(key, output, REVISION)


@pytest.mark.parametrize('attack', ['app', 'app_permissions', 'installation', 'suspended', 'all_repos',
    'token_permissions', 'token_selection', 'token_repo_missing', 'token_repo_extra',
    'token_size', 'token_newline', 'token_expired', 'token_long_life', 'scope_count',
    'scope_extra', 'scope_id_float', 'scope_name', 'repository_id', 'repository_admin', 'unprotected', 'base'])
def test_wrong_remote_scope_never_persists_credential_or_retries(fixture, rsa_key, attack):
    fake = FakeGitHub(rsa_key.public_key())
    def mutate(path, row):
        if path == '/app':
            if attack == 'app':
                row['id'] += 1
            if attack == 'app_permissions':
                row['permissions']['administration'] = 'write'
        if path == operator.REPO + '/installation':
            if attack == 'installation':
                row['id'] += 1
            if attack == 'suspended':
                row['suspended_at'] = '2026-10-29T00:00:00Z'
            if attack == 'all_repos':
                row['repository_selection'] = 'all'
        if path == operator.TOKEN_ENDPOINT:
            if attack == 'token_permissions':
                row['permissions']['issues'] = 'write'
            if attack == 'token_selection':
                row['repository_selection'] = 'all'
            if attack == 'token_repo_missing':
                row.pop('repositories')
            if attack == 'token_repo_extra':
                row['repositories'].append(deepcopy(row['repositories'][0]))
            if attack == 'token_size':
                row['token'] = 'a' * 1025
            if attack == 'token_newline':
                row['token'] += '\n'
            if attack in {'token_expired', 'token_long_life'}:
                row['expires_at'] = datetime.fromtimestamp(NOW + (0 if attack == 'token_expired' else 7200),
                                                          timezone.utc).isoformat()
        if path == operator.TOKEN_REPOSITORIES:
            if attack == 'scope_count':
                row['total_count'] = 2
            if attack == 'scope_extra':
                row['repositories'].append(deepcopy(row['repositories'][0]))
            if attack == 'scope_id_float':
                row['repositories'][0]['id'] = float(operator.REPOSITORY_ID)
            if attack == 'scope_name':
                row['repositories'][0]['full_name'] = 'fixture/other'
        if path == operator.REPO:
            if attack == 'repository_id':
                row['id'] += 1
            if attack == 'repository_admin':
                row['permissions']['admin'] = True
        if path == operator.REPO + '/branches/main':
            if attack == 'unprotected':
                row['protected'] = False
            if attack == 'base':
                row['commit']['sha'] = 'f' * 40
    fake.mutate = mutate
    with pytest.raises(operator.Blocked):
        run(fixture, fake)
    output = fixture[1]
    assert not (output / 'installation.token').exists()
    receipt = json.loads((output / 'receipt.json').read_text())
    assert receipt['phase'] == 'REQUIRES_INSPECTION_NO_RETRY'
    assert sum(method == 'POST' for method, _ in fake.calls) <= 1
    before = deepcopy(fake.calls)
    with pytest.raises(operator.Blocked):
        run(fixture, fake)
    assert fake.calls == before and TOKEN not in json.dumps(receipt)


@pytest.mark.parametrize('loss', ['post_timeout', 'get_timeout', 'late_deadline', 'changed_source', 'lost_local_commit'])
def test_partial_remote_or_local_outcome_is_never_blindly_retried(fixture, rsa_key, monkeypatch, loss):
    fake = FakeGitHub(rsa_key.public_key())
    def after(path):
        if loss == 'post_timeout' and path == operator.TOKEN_ENDPOINT:
            raise httpx.ReadTimeout('PUBLIC_FIXTURE_LOSS_DO_NOT_ECHO')
        if path == operator.TOKEN_REPOSITORIES:
            if loss == 'get_timeout':
                raise httpx.ReadTimeout('PUBLIC_FIXTURE_LOSS_DO_NOT_ECHO')
            if loss == 'late_deadline':
                monkeypatch.setattr(operator.time, 'time', lambda: NOW + 301)
            if loss == 'changed_source':
                monkeypatch.setattr(operator, 'check_source', lambda r: (_ for _ in ()).throw(ValueError('fixture change')))
    fake.after = after
    original = operator.atomic_json
    def commit(path, row):
        if loss == 'lost_local_commit' and row['phase'] == 'TOKEN_STORED_NOT_CONNECTED':
            raise OSError('PUBLIC_FIXTURE_LOSS_DO_NOT_ECHO')
        original(path, row)
    monkeypatch.setattr(operator, 'atomic_json', commit)
    with pytest.raises(operator.Blocked):
        run(fixture, fake)
    output = fixture[1]
    receipt = json.loads((output / 'receipt.json').read_text())
    assert receipt['phase'] == 'REQUIRES_INSPECTION_NO_RETRY' and receipt['token_request_attempted']
    assert (output / 'installation.token').exists() == (loss == 'lost_local_commit')
    assert TOKEN not in json.dumps(receipt)
    before = deepcopy(fake.calls)
    # Restore fixture clock/source, as a new invocation would do; existing attempt still blocks.
    monkeypatch.setattr(operator.time, 'time', lambda: NOW)
    monkeypatch.setattr(operator, 'check_source', lambda r: None)
    with pytest.raises(operator.Blocked, match='existing_attempt'):
        run(fixture, fake)
    assert fake.calls == before


def test_concurrent_invocations_reserve_one_attempt_and_issue_one_token(fixture, rsa_key):
    key, output = fixture
    plan = operator.describe(key, output, REVISION)[2]['plan_digest']
    fake = FakeGitHub(rsa_key.public_key())
    def invoke(_):
        try:
            return operator.prepare(key, output, REVISION, plan, NOW + 300,
                                    transport=httpx.MockTransport(fake.handle))['phase']
        except (operator.Blocked, FileExistsError):
            return 'BLOCKED'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, range(2)))
    assert sorted(results) == ['BLOCKED', 'TOKEN_STORED_NOT_CONNECTED']
    assert sum(method == 'POST' for method, _ in fake.calls) == 1


def test_deadline_expiring_during_identity_checks_prevents_post(fixture, rsa_key, monkeypatch):
    fake = FakeGitHub(rsa_key.public_key())
    def after(path):
        if path == operator.REPO + '/installation':
            monkeypatch.setattr(operator.time, 'time', lambda: NOW + 301)
    fake.after = after
    with pytest.raises(operator.Blocked):
        run(fixture, fake)
    assert all(method == 'GET' for method, _ in fake.calls)
    assert not json.loads((fixture[1] / 'receipt.json').read_text())['token_request_attempted']


@pytest.mark.parametrize('path', ['https://evil.invalid', '/installation/token', operator.REPO + '/merges',
                                operator.REPO + '/git/refs', operator.REPO + '/pulls'])
def test_client_rejects_every_non_preparation_endpoint_before_http(path):
    github = operator.GitHub(transport=httpx.MockTransport(lambda request: pytest.fail('forbidden HTTP')))
    try:
        with pytest.raises(operator.Blocked):
            github.call('POST', path, TOKEN, {})
    finally:
        github.client.close()


@pytest.mark.parametrize('failure', ['redirect', 'server_error', 'invalid_json', 'oversized'])
def test_http_failures_do_not_follow_redirect_or_retry(fixture, failure):
    key, output = fixture
    calls = []
    def handle(request):
        calls.append(request.url)
        if failure == 'redirect':
            return httpx.Response(302, headers={'Location': 'https://evil.invalid'})
        if failure == 'server_error':
            return httpx.Response(503, text='PRIVATE_PROVIDER_TEXT')
        return httpx.Response(200, content=b'x' * (65537 if failure == 'oversized' else 5))
    plan = operator.describe(key, output, REVISION)[2]['plan_digest']
    with pytest.raises(operator.Blocked):
        operator.prepare(key, output, REVISION, plan, NOW + 300, transport=httpx.MockTransport(handle))
    assert len(calls) == 1 and json.loads((output / 'receipt.json').read_text())['token_request_attempted'] is False


def test_source_check_rejects_dirty_wrong_head_and_injected_git_environment(tmp_path, monkeypatch):
    repo = tmp_path / 'git'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL).decode().strip()
    git('init')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-m', 'fixture')
    monkeypatch.setattr(operator, 'ROOT', repo)
    monkeypatch.setenv('GIT_DIR', '/not-the-approved-repo')
    revision = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                                      env={k: v for k, v in os.environ.items() if k != 'GIT_DIR'}).decode().strip()
    operator.check_source(revision)
    with pytest.raises(operator.Blocked):
        operator.check_source('b' * 40)
    (repo / 'untracked').write_text('fixture')
    with pytest.raises(operator.Blocked):
        operator.check_source(revision)


def test_cli_default_is_offline_and_errors_are_redacted(fixture, monkeypatch, capsys):
    key, output = fixture
    argv = ['tool', '--key-file', str(key), '--output-directory', str(output), '--operator-revision', REVISION]
    monkeypatch.setattr(sys, 'argv', argv)
    monkeypatch.setattr(httpx, 'Client', lambda **k: pytest.fail('offline CLI'))
    operator.main()
    assert json.loads(capsys.readouterr().out)['phase'] == 'OFFLINE_PLAN_NOT_AUTHORIZED'
    monkeypatch.setattr(sys, 'argv', argv + ['--approved-plan', '0' * 64])
    with pytest.raises(SystemExit) as error:
        operator.main()
    result = capsys.readouterr()
    assert error.value.code == 2 and 'BLOCKED' in result.out
    assert str(key) not in result.out + result.err and 'PRIVATE KEY' not in result.out + result.err


def test_cli_never_echoes_provider_or_credential_errors(fixture, rsa_key, monkeypatch, capsys):
    key, output = fixture
    plan = operator.describe(key, output, REVISION)[2]['plan_digest']
    monkeypatch.setattr(sys, 'argv', ['tool', 'prepare', '--key-file', str(key), '--output-directory', str(output),
        '--operator-revision', REVISION, '--approved-plan', plan, '--approved-until', str(NOW + 300)])
    fake = FakeGitHub(rsa_key.public_key())
    fake.after = lambda path: (_ for _ in ()).throw(httpx.ReadTimeout(TOKEN + str(key) + 'PRIVATE KEY'))
    original = operator.GitHub
    monkeypatch.setattr(operator, 'GitHub', lambda **k: original(transport=httpx.MockTransport(fake.handle)))
    with pytest.raises(SystemExit) as error:
        operator.main()
    result = capsys.readouterr()
    assert error.value.code == 2 and json.loads(result.out)['status'] == 'BLOCKED'
    assert TOKEN not in result.out + result.err and str(key) not in result.out + result.err
    assert 'PRIVATE KEY' not in result.out + result.err and 'Traceback' not in result.err
