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


def git_advertisement(main_sha=BASE_SHA):
    def packet(value):
        return ('%04x' % (len(value) + 4)).encode() + value
    return (packet(b'# service=git-receive-pack\n') + b'0000'
            + packet(main_sha.encode() + b' refs/heads/main\0report-status delete-refs\n') + b'0000')


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
        self.git_status, self.git_body = 403, None

    def handle(self, request):
        if request.url.host == 'github.com':
            import base64
            assert request.method == 'GET' and request.url.raw_path.decode() == operator.GIT_DISCOVERY
            assert request.headers['Authorization'] == 'Basic ' + base64.b64encode(('x-access-token:' + TOKEN).encode()).decode()
            assert not request.content
            self.calls.append(('GET', operator.GIT_DISCOVERY))
            return httpx.Response(self.git_status, content=self.git_body or b'Forbidden',
                headers={'content-type': 'application/x-git-receive-pack-advertisement'})
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
def test_wrong_remote_scope_never_promotes_credential_or_retries(fixture, rsa_key, attack):
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
    assert (output / 'candidate.token').exists() == (attack in {
        'scope_count', 'scope_extra', 'scope_id_float', 'scope_name',
        'repository_id', 'repository_admin', 'unprotected', 'base'})
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


@pytest.mark.parametrize('invalid', ['action', 'deadline', 'unknown_argument'])
def test_argument_parser_never_repeats_mistakenly_pasted_values(fixture, monkeypatch, capsys, invalid):
    key, output = fixture
    argv = ['tool', '--key-file', str(key), '--output-directory', str(output), '--operator-revision', REVISION]
    if invalid == 'action':
        argv.insert(1, TOKEN)
    elif invalid == 'deadline':
        argv += ['--approved-until', TOKEN]
    else:
        argv += ['--unknown', TOKEN]
    monkeypatch.setattr(sys, 'argv', argv)
    monkeypatch.setattr(httpx, 'Client', lambda **k: pytest.fail('invalid arguments cannot construct a client'))
    with pytest.raises(SystemExit) as error:
        operator.main()
    result = capsys.readouterr()
    assert error.value.code == 2 and json.loads(result.out)['status'] == 'BLOCKED'
    assert TOKEN not in result.out + result.err and str(key) not in result.out + result.err
    assert result.err == '' and not output.exists()


def failed_candidate(fixture, rsa_key):
    fake = FakeGitHub(rsa_key.public_key())
    fake.after = lambda path: (_ for _ in ()).throw(httpx.ReadTimeout('PUBLIC_RESPONSE_LOSS')) if (
        path == operator.TOKEN_REPOSITORIES) else None
    with pytest.raises(operator.Blocked):
        run(fixture, fake)
    return fake


def files_snapshot(output):
    return {p.name: p.read_bytes() for p in output.iterdir()}


def test_valid_token_survives_later_http_rejection_without_exposing_provider_body(fixture, rsa_key, caplog):
    caplog.set_level(logging.DEBUG)
    key, output = fixture
    fake = FakeGitHub(rsa_key.public_key())
    def handler(request):
        result = fake.handle(request)
        if request.url.path == operator.REPO + '/branches/main':
            return httpx.Response(403, json={'message': TOKEN + str(key) + 'PRIVATE_PROVIDER_TEXT'})
        return result
    plan = operator.describe(key, output, REVISION)[2]['plan_digest']
    with pytest.raises(operator.Blocked):
        operator.prepare(key, output, REVISION, plan, NOW + 300, transport=httpx.MockTransport(handler))
    receipt = json.loads((output / 'receipt.json').read_text())
    assert receipt['phase'] == 'REQUIRES_INSPECTION_NO_RETRY'
    assert receipt['stage'] == 'branch_metadata' and receipt['error_code'] == 'github_http_rejected'
    assert receipt['http_events'][-1]['http_status'] == 403
    assert receipt['token_repository_count_verified'] is True
    assert (output / 'candidate.token').read_text() == TOKEN
    assert not (output / 'installation.token').exists()
    assert TOKEN not in json.dumps(receipt) + caplog.text
    assert 'PRIVATE_PROVIDER_TEXT' not in json.dumps(receipt) + caplog.text
    assert sum(m == 'POST' for m, _ in fake.calls) == 1


@pytest.mark.parametrize('problem', ['missing_permissions', 'admin_true', 'no_push', 'unprotected', 'wrong_base'])
def test_real_shape_guard_failure_has_boolean_diagnostics_and_no_promotion(fixture, rsa_key, problem):
    fake = FakeGitHub(rsa_key.public_key())
    def mutate(path, row):
        if path == operator.REPO:
            if problem == 'missing_permissions':
                row.pop('permissions')
            elif problem == 'admin_true':
                row['permissions']['admin'] = True
            elif problem == 'no_push':
                row['permissions']['push'] = False
        if path == operator.REPO + '/branches/main':
            if problem == 'unprotected':
                row['protected'] = False
            elif problem == 'wrong_base':
                row['commit']['sha'] = 'f' * 40
    fake.mutate = mutate
    with pytest.raises(operator.Blocked):
        run(fixture, fake)
    output = fixture[1]
    receipt = json.loads((output / 'receipt.json').read_text())
    assert receipt['error_code'] == ('github_http_rejected' if problem == 'no_push' else 'first_experiment_repository_preflight')
    assert receipt['stage'] == ('git_discovery' if problem == 'no_push' else 'repository_validation')
    field = {'missing_permissions': 'permissions_present', 'admin_true': 'admin_false', 'no_push': 'push_true',
             'unprotected': 'main_protected', 'wrong_base': 'baseline_matches'}[problem]
    assert receipt['repository_checks'][field] is False
    assert (output / 'candidate.token').exists() and not (output / 'installation.token').exists()


@pytest.mark.parametrize('push', [False, None])
def test_app_token_uses_git_discovery_without_forging_metadata_push(fixture, rsa_key, push):
    fake = FakeGitHub(rsa_key.public_key())
    fake.git_status, fake.git_body = 200, git_advertisement()
    def mutate(path, row):
        if path == operator.REPO:
            if push is None:
                row['permissions'].pop('push')
            else:
                row['permissions']['push'] = False
    fake.mutate = mutate
    result = run(fixture, fake)
    assert result['phase'] == 'TOKEN_STORED_NOT_CONNECTED'
    assert result['repository_checks']['push_true'] is False
    assert result['git_discovery']['main_sha'] == BASE_SHA
    assert result['repository_binding_and_baseline_verified'] is True
    assert (fixture[1] / 'installation.token').read_text() == TOKEN
    assert sum(method == 'POST' for method, _ in fake.calls) == 1
    assert fake.calls[-1] == ('GET', operator.GIT_DISCOVERY)
    assert TOKEN not in json.dumps(result)


@pytest.mark.parametrize('case', ['bad_main', 'html', 'redirect', 'forbidden'])
def test_failed_git_discovery_retains_candidate_without_final_file(fixture, rsa_key, case):
    fake = FakeGitHub(rsa_key.public_key())
    fake.git_status = {'redirect': 302, 'forbidden': 403}.get(case, 200)
    fake.git_body = b'<html>ok</html>' if case == 'html' else git_advertisement('f' * 40 if case == 'bad_main' else BASE_SHA)
    def mutate(path, row):
        if path == operator.REPO:
            row['permissions']['push'] = False
    fake.mutate = mutate
    with pytest.raises(operator.Blocked):
        run(fixture, fake)
    output = fixture[1]
    receipt = json.loads((output / 'receipt.json').read_text())
    assert receipt['phase'] == 'REQUIRES_INSPECTION_NO_RETRY'
    assert (output / 'candidate.token').read_text() == TOKEN
    assert not (output / 'installation.token').exists()
    assert sum(method == 'POST' for method, _ in fake.calls) == 1
    report = operator.inspect_attempt(output, REVISION)
    assert report['recorded_http_events'][-1]['endpoint'] == operator.GIT_DISCOVERY
    assert report['recorded_http_events'][-1]['http_status'] == fake.git_status
    assert TOKEN not in json.dumps(receipt) + json.dumps(report)


def test_read_only_probe_can_verify_legacy_push_false_without_promoting_or_issuing(fixture, rsa_key):
    fake = failed_candidate(fixture, rsa_key)
    fake.after = None
    fake.git_status, fake.git_body = 200, git_advertisement()
    def mutate(path, row):
        if path == operator.REPO:
            row['permissions']['push'] = False
    fake.mutate = mutate
    fake.calls.clear()
    before = files_snapshot(fixture[1])
    result = operator.inspect_attempt(fixture[1], REVISION, probe=True, transport=httpx.MockTransport(fake.handle))
    assert result['phase'] == 'READ_ONLY_PROBE_PASSED'
    assert result['repository_checks']['push_true'] is False
    assert result['git_discovery']['main_sha'] == BASE_SHA
    assert result['external_calls'] == 4 and all(method == 'GET' for method, _ in fake.calls)
    assert files_snapshot(fixture[1]) == before
    assert not (fixture[1] / 'installation.token').exists()


def test_offline_inspection_never_opens_credential_or_constructs_client(fixture, rsa_key, monkeypatch):
    failed_candidate(fixture, rsa_key)
    key, output = fixture
    key.unlink()  # No App private key is needed for inspection.
    before = files_snapshot(output)
    original = operator._open_private
    def read(path, *args, **kwargs):
        assert Path(path).name == 'receipt.json', 'offline inspection cannot read a credential value'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(operator, '_open_private', read)
    monkeypatch.setattr(operator, 'GitHub', lambda **k: pytest.fail('offline inspection cannot construct HTTP'))
    report = operator.inspect_attempt(output, REVISION)
    assert report['phase'] == 'OFFLINE_INSPECTION' and report['credential_value_read'] is False
    assert report['stage'] == 'repository_enumeration' and report['error_code'] == 'github_timeout'
    assert report['recorded_http_events'][-1]['http_status'] is None
    assert report['candidate_file']['present'] is True
    assert report['files_changed'] is report['token_issued_by_inspection'] is False and report['external_calls'] == 0
    assert files_snapshot(output) == before and TOKEN not in json.dumps(report)


def test_read_only_probe_reuses_bound_candidate_without_new_issue_or_promotion(fixture, rsa_key):
    fake = failed_candidate(fixture, rsa_key)
    output = fixture[1]
    before = files_snapshot(output)
    fake.after = None
    fake.calls.clear()
    report = operator.inspect_attempt(output, REVISION, probe=True, transport=httpx.MockTransport(fake.handle))
    assert report['phase'] == 'READ_ONLY_PROBE_PASSED' and report['probe_ok'] is True
    assert report['observed_phase'] == 'REQUIRES_INSPECTION_NO_RETRY'
    assert report['observed_error_code'] == 'github_timeout' and report['error_code'] is None
    assert fake.calls == [('GET', operator.TOKEN_REPOSITORIES), ('GET', operator.REPO),
                          ('GET', operator.REPO + '/branches/main')]
    assert report['external_calls'] == 3 and report['token_issued_by_inspection'] is False
    assert files_snapshot(output) == before and not (output / 'installation.token').exists()
    assert TOKEN not in json.dumps(report)


@pytest.mark.parametrize('failure', ['http_403', 'scope_changed', 'permissions_absent', 'expiry_during_probe'])
def test_probe_failure_is_diagnostic_only_and_preserves_all_original_files(fixture, rsa_key, monkeypatch, failure):
    fake = failed_candidate(fixture, rsa_key)
    output = fixture[1]
    before = files_snapshot(output)
    fake.after = None
    fake.calls.clear()
    def handler(request):
        response = fake.handle(request)
        if failure == 'http_403':
            return httpx.Response(403, json={'message': TOKEN + 'DO_NOT_ECHO'})
        row = response.json()
        if failure == 'scope_changed' and request.url.raw_path.decode() == operator.TOKEN_REPOSITORIES:
            row['total_count'] = 2
        if failure == 'permissions_absent' and request.url.path == operator.REPO:
            row.pop('permissions')
        if failure == 'expiry_during_probe' and request.url.path == operator.REPO + '/branches/main':
            monkeypatch.setattr(operator.time, 'time', lambda: NOW + 3601)
        return httpx.Response(200, json=row)
    report = operator.inspect_attempt(output, REVISION, probe=True, transport=httpx.MockTransport(handler))
    assert report['phase'] == 'READ_ONLY_PROBE_BLOCKED' and report['probe_ok'] is False
    assert report['error_code'] == {'http_403': 'github_http_rejected', 'scope_changed': 'installation_token_repository_scope',
        'permissions_absent': 'first_experiment_repository_preflight', 'expiry_during_probe': 'candidate_expired'}[failure]
    assert all(method == 'GET' for method, _ in fake.calls)
    assert files_snapshot(output) == before and not (output / 'installation.token').exists()
    assert TOKEN not in json.dumps(report) and 'DO_NOT_ECHO' not in json.dumps(report)


def test_read_only_client_cannot_issue_or_authenticate_as_app():
    github = operator.GitHub(read_only=True, transport=httpx.MockTransport(lambda request: pytest.fail('no HTTP')))
    try:
        for method, path, body in [('POST', operator.TOKEN_ENDPOINT, operator.REQUEST), ('GET', '/app', None)]:
            with pytest.raises(operator.Blocked):
                github.call(method, path, TOKEN, body)
        assert github.events == []
    finally:
        github.client.close()


@pytest.mark.parametrize('tamper', ['digest', 'contents', 'symlink', 'hardlink', 'mode', 'expiry', 'response_binding',
                                  'id_float', 'permissions'])
def test_inspection_rejects_unbound_unsafe_or_expired_candidate_before_http(fixture, rsa_key, monkeypatch, tamper):
    failed_candidate(fixture, rsa_key)
    output = fixture[1]
    candidate = output / 'candidate.token'
    receipt_path = output / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if tamper == 'digest':
        receipt['token_sha256'] = '0' * 64
    elif tamper == 'contents':
        candidate.write_text('PUBLIC_REPLACEMENT_NOT_THE_BOUND_TOKEN')
    elif tamper == 'symlink':
        candidate.unlink()
        candidate.symlink_to(fixture[0])
    elif tamper == 'hardlink':
        os.link(candidate, output / 'other.token')
    elif tamper == 'mode':
        candidate.chmod(0o644)
    elif tamper == 'expiry':
        receipt['expires_at'] = datetime.fromtimestamp(NOW - 1, timezone.utc).isoformat()
    elif tamper == 'response_binding':
        receipt['token_response_binding_verified'] = False
    elif tamper == 'id_float':
        receipt['repository_id'] = float(operator.REPOSITORY_ID)
    else:
        receipt['permissions']['administration'] = 'write'
    receipt_path.write_text(json.dumps(receipt))
    def metadata_snapshot():
        # Reads may update kernel atime; content/authority/inode/mode must stay unchanged.
        return {p.name: (s.st_ino, s.st_size, s.st_mode, s.st_mtime_ns, s.st_ctime_ns)
                for p in output.iterdir() for s in [p.lstat()]}
    before = metadata_snapshot()
    monkeypatch.setattr(operator, 'GitHub', lambda **k: pytest.fail('binding/custody before HTTP'))
    with pytest.raises((operator.Blocked, ValueError, OSError)):
        operator.inspect_attempt(output, REVISION, probe=True)
    assert before == metadata_snapshot()


def test_legacy_receipt_is_observed_without_fabricating_diagnostics_or_reissuing(fixture, monkeypatch):
    output = fixture[1]
    output.mkdir(mode=0o700)
    receipt = {'phase': 'REQUIRES_INSPECTION_NO_RETRY', 'token_request_attempted': True,
               'expires_at': '2026-10-30T04:06:33+00:00', 'operator_revision': REVISION}
    path = output / 'receipt.json'
    path.write_text(json.dumps(receipt))
    path.chmod(0o600)
    before = path.read_bytes()
    monkeypatch.setattr(operator, 'GitHub', lambda **k: pytest.fail('legacy token was not retained'))
    report = operator.inspect_attempt(output, REVISION)
    assert report['legacy_receipt'] is True and report['candidate_file']['present'] is False
    assert report['error_code'] == report['stage'] == 'UNRECORDED' and report['external_calls'] == 0
    with pytest.raises(operator.Blocked, match='candidate_binding_invalid'):
        operator.inspect_attempt(output, REVISION, probe=True)
    assert path.read_bytes() == before


def test_untrusted_exception_text_never_becomes_a_public_diagnostic(fixture, monkeypatch):
    key, output = fixture
    def fail(*a, **k):
        raise operator.Blocked(TOKEN + str(key))
    monkeypatch.setattr(operator, 'identity', fail)
    with pytest.raises(operator.Blocked):
        run(fixture, FakeGitHub(None))
    receipt = (output / 'receipt.json').read_text()
    assert json.loads(receipt)['error_code'] == 'operator_check_failed'
    assert TOKEN not in receipt and str(key) not in receipt


def test_inspect_cli_needs_no_key_or_approval_and_probe_flags_cannot_escape_scope(fixture, rsa_key, monkeypatch, capsys):
    failed_candidate(fixture, rsa_key)
    key, output = fixture
    key.unlink()
    argv = ['tool', 'inspect', '--output-directory', str(output), '--operator-revision', REVISION]
    monkeypatch.setattr(sys, 'argv', argv)
    monkeypatch.setattr(operator, 'GitHub', lambda **k: pytest.fail('inspect default is offline'))
    operator.main()
    assert json.loads(capsys.readouterr().out)['phase'] == 'OFFLINE_INSPECTION'
    monkeypatch.setattr(sys, 'argv', argv + ['--approved-plan', '0' * 64])
    with pytest.raises(SystemExit) as error:
        operator.main()
    result = json.loads(capsys.readouterr().out)
    assert error.value.code == 2 and result['error_code'] == 'inspect_arguments_forbidden'
