"""One-shot operator preparation for the fixed experiment; never run by the runtime.

Default `plan` is offline. `prepare` needs a reviewed plan, exact clean operator
revision and fresh owner deadline. Real use requires separate owner authorization.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt

from command_center.coding.first_experiment import validate_repository
from command_center.deployment_integrations import _open_private
from command_center.deployment_profile import atomic_json
from command_center.store import digest

ROOT = Path(__file__).resolve().parents[2]
APP_ID, INSTALLATION_ID, ACCOUNT_ID, REPOSITORY_ID = 5524444, 176497504, 346751364, 1438229730
OWNER, APP_SLUG = 'v71369322-lang', 'acc-first-v71369322'
REPOSITORY = OWNER + '/acc-f2-synthetic-first'
PERMISSIONS = {'contents': 'write', 'pull_requests': 'write', 'metadata': 'read'}
APP_INSTALLATION = f'/app/installations/{INSTALLATION_ID}'
REPO = '/repos/' + REPOSITORY
TOKEN_ENDPOINT = APP_INSTALLATION + '/access_tokens'
TOKEN_REPOSITORIES = '/installation/repositories?per_page=2&page=1'
REQUEST = {'repository_ids': [REPOSITORY_ID], 'permissions': PERMISSIONS}
ALLOWED = {('GET', '/app'), ('GET', APP_INSTALLATION), ('GET', REPO + '/installation'),
           ('POST', TOKEN_ENDPOINT), ('GET', TOKEN_REPOSITORIES), ('GET', REPO), ('GET', REPO + '/branches/main')}


class Blocked(Exception):
    """Only fixed codes may cross the CLI boundary; never provider text/credentials."""


def check_source(revision):
    if not isinstance(revision, str) or not re.fullmatch('[a-f0-9]{40}', revision):
        raise Blocked('exact_operator_revision_required')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    for args, expected in [(('rev-parse', 'HEAD'), revision), (('status', '--porcelain'), '')]:
        result = subprocess.run(['git', '-C', str(ROOT), *args], env=env,
                                capture_output=True, check=True, timeout=10)
        if result.stdout.decode().strip() != expected:
            raise Blocked('operator_source_changed')


def private_path(value):
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path or path.is_relative_to(ROOT):
        raise Blocked('private_path_outside_source_required')
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise Blocked('private_parent_required')
    return path


def describe(key_file, output_directory, revision):
    check_source(revision)
    if os.geteuid() == 0:
        raise Blocked('dedicated_unprivileged_operator_required')
    key_file, output = private_path(key_file), private_path(output_directory)
    if os.path.lexists(output):
        raise Blocked('existing_attempt_requires_inspection')
    stream, metadata = _open_private(key_file, os.geteuid(), 16384, minimum=1024)
    with stream:
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise Blocked('app_key_mode_required')
        key = serialization.load_pem_private_key(stream.read(16385), password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or not 2048 <= key.key_size <= 4096:
        raise Blocked('rsa_app_key_required')
    public = key.public_key().public_bytes(serialization.Encoding.DER,
                                         serialization.PublicFormat.SubjectPublicKeyInfo)
    public_hash = hashlib.sha256(public).hexdigest()
    scope = {'schema': 1, 'action': 'prepare_fixed_experiment_installation_token',
             'operator_revision': revision, 'app_id': APP_ID, 'installation_id': INSTALLATION_ID,
             'repository_id': REPOSITORY_ID, 'repository': REPOSITORY, 'permissions': PERMISSIONS,
             'key_public_spki_sha256': public_hash, 'key_file': str(key_file), 'output_directory': str(output)}
    public_scope = {k: v for k, v in scope.items() if k not in {'key_file', 'output_directory'}}
    return key, output, {**public_scope, 'plan_digest': digest(scope)}


def deadline(until):
    if type(until) is not int or not time.time() < until <= time.time() + 600:
        raise Blocked('fresh_owner_deadline_required')


def new_file(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class GitHub:
    def __init__(self, *, transport=None):
        self.client = httpx.Client(transport=transport, follow_redirects=False, timeout=10,
                                  trust_env=transport is None, limits=httpx.Limits(max_connections=1))

    def call(self, method, path, credential, body=None):
        if ((method, path) not in ALLOWED or (method == 'POST' and body != REQUEST)
                or (method == 'GET' and body is not None)):
            raise Blocked('github_endpoint_or_scope_forbidden')
        headers = {'Authorization': 'Bearer ' + credential, 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2026-03-10'}
        with self.client.stream(method, 'https://api.github.com' + path, headers=headers, json=body) as response:
            if response.status_code != (201 if method == 'POST' else 200):
                raise Blocked('github_http_rejected')
            data = bytearray()
            for chunk in response.iter_bytes(chunk_size=8192):
                data.extend(chunk)
                if len(data) > 65536:
                    raise Blocked('github_response_too_large')
            result = json.loads(data)
        if not isinstance(result, dict):
            raise Blocked('github_response_invalid')
        return result


def identity(github, assertion):
    app = github.call('GET', '/app', assertion)
    if (type(app.get('id')) is not int or app['id'] != APP_ID or app.get('slug') != APP_SLUG
            or type(app.get('owner', {}).get('id')) is not int or app['owner']['id'] != ACCOUNT_ID
            or app.get('owner', {}).get('login') != OWNER
            or app.get('permissions') != PERMISSIONS):
        raise Blocked('github_app_identity_or_permissions')
    for path in (APP_INSTALLATION, REPO + '/installation'):
        row = github.call('GET', path, assertion)
        if (type(row.get('id')) is not int or row['id'] != INSTALLATION_ID
                or type(row.get('app_id')) is not int or row['app_id'] != APP_ID
                or type(row.get('account', {}).get('id')) is not int or row['account']['id'] != ACCOUNT_ID
                or row.get('account', {}).get('login') != OWNER
                or row.get('permissions') != PERMISSIONS or row.get('repository_selection') != 'selected'
                or 'suspended_at' not in row or row['suspended_at'] is not None):
            raise Blocked('github_installation_identity_or_permissions')


def one_repository(rows):
    return (isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict)
            and type(rows[0].get('id')) is int and rows[0]['id'] == REPOSITORY_ID
            and rows[0].get('full_name') == REPOSITORY)


def token_metadata(response):
    token = response.get('token')
    # GitHub also issues longer ghs_APPID_JWT tokens. Do not assume 40 chars,
    # decode opaque tokens, truncate, or exceed the existing runtime size cap.
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{16,1024}', token):
        raise Blocked('installation_token_format_or_size')
    if response.get('permissions') != PERMISSIONS:
        raise Blocked('installation_token_permissions')
    if response.get('repository_selection') != 'selected' or not one_repository(response.get('repositories')):
        raise Blocked('installation_token_response_scope')
    expiry = datetime.fromisoformat(response['expires_at'].replace('Z', '+00:00'))
    if expiry.tzinfo is None or not 900 <= expiry.timestamp() - time.time() <= 3660:
        raise Blocked('installation_token_expiry')
    return token, expiry.isoformat()


def prepare(key_file, output_directory, revision, approved_plan, approved_until, *, transport=None):
    deadline(approved_until)
    key, output, report = describe(key_file, output_directory, revision)
    if approved_plan != report['plan_digest']:
        raise Blocked('exact_plan_approval_required')
    output.mkdir(mode=0o700)  # Atomic reservation: crash/replay/concurrency never mint again in this attempt.
    journal = {**report, 'approved_until': approved_until, 'phase': 'INTENT', 'token_request_attempted': False,
               'application_configuration_changed': False, 'repository_changes': False, 'paid_calls': 0,
               'installation_repository_count_verified': False, 'token_repository_count_verified': False}
    new_file(output / 'receipt.json', json.dumps(journal, sort_keys=True).encode())
    github = None
    try:
        github = GitHub(transport=transport)
        issued = int(time.time())
        assertion = jwt.encode({'iat': issued - 60, 'exp': issued + 300, 'iss': str(APP_ID)}, key, algorithm='RS256')
        identity(github, assertion)
        deadline(approved_until)
        check_source(revision)
        journal.update(phase='TOKEN_REQUEST_INTENT', token_request_attempted=True)
        atomic_json(output / 'receipt.json', journal)  # Durable BEFORE the only credential-creation POST.
        response = github.call('POST', TOKEN_ENDPOINT, assertion, REQUEST)
        token, expires_at = token_metadata(response)
        journal.update(phase='TOKEN_RECEIVED_NOT_STORED', expires_at=expires_at)
        atomic_json(output / 'receipt.json', journal)
        repositories = github.call('GET', TOKEN_REPOSITORIES, token)
        if (type(repositories.get('total_count')) is not int or repositories['total_count'] != 1
                or not one_repository(repositories.get('repositories'))):
            raise Blocked('installation_token_repository_scope')
        metadata = github.call('GET', REPO, token)
        branch = github.call('GET', REPO + '/branches/main', token)
        validate_repository(metadata, branch, REPOSITORY, REPOSITORY_ID)
        deadline(approved_until)
        check_source(revision)
        token_metadata(response)  # Check remaining lifetime again after reads.
        new_file(output / 'installation.token', token.encode())
        journal.update(phase='TOKEN_STORED_NOT_CONNECTED', token_repository_count_verified=True,
                       repository_binding_and_baseline_verified=True)
        atomic_json(output / 'receipt.json', journal)
        return journal
    except Exception:
        # Partial/unknown credentials may exist upstream or in the private file.
        # Never retry, overwrite, echo a body/exception, or claim automatic revocation.
        journal['phase'] = 'REQUIRES_INSPECTION_NO_RETRY'
        atomic_json(output / 'receipt.json', journal)
        raise Blocked('token_preparation_requires_inspection') from None
    finally:
        if github:
            github.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'prepare'), nargs='?', default='plan')
    parser.add_argument('--key-file', required=True)
    parser.add_argument('--output-directory', required=True)
    parser.add_argument('--operator-revision', required=True)
    parser.add_argument('--approved-plan')
    parser.add_argument('--approved-until', type=int)
    args = parser.parse_args()
    try:
        if args.action == 'plan':
            if args.approved_plan is not None or args.approved_until is not None:
                raise Blocked('plan_does_not_consume_approval')
            report = {**describe(args.key_file, args.output_directory, args.operator_revision)[2],
                      'phase': 'OFFLINE_PLAN_NOT_AUTHORIZED', 'external_calls': 0}
        else:
            report = prepare(args.key_file, args.output_directory, args.operator_revision,
                             args.approved_plan, args.approved_until)
        print(json.dumps(report, sort_keys=True))
    except Exception:
        print(json.dumps({'status': 'BLOCKED', 'reason': 'inspect_existing_attempt_before_retry',
                          'application_configuration_changed': False, 'paid_calls': 0}))
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
