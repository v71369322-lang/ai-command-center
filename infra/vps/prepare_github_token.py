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
from command_center.store import Denied, digest

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
TOKEN_READS = {('GET', TOKEN_REPOSITORIES), ('GET', REPO), ('GET', REPO + '/branches/main')}
STAGES = {'identity', 'token_request', 'token_response', 'candidate_store', 'repository_enumeration',
          'repository_metadata', 'branch_metadata', 'repository_validation', 'final_checks', 'final_store', 'complete'}
SAFE_ERRORS = {
    'exact_operator_revision_required', 'operator_source_changed', 'private_path_outside_source_required',
    'private_parent_required', 'dedicated_unprivileged_operator_required', 'existing_attempt_requires_inspection',
    'app_key_mode_required', 'rsa_app_key_required', 'fresh_owner_deadline_required', 'exact_plan_approval_required',
    'github_endpoint_or_scope_forbidden', 'github_http_rejected', 'github_response_too_large', 'github_response_invalid',
    'github_app_identity_or_permissions', 'github_installation_identity_or_permissions',
    'installation_token_format_or_size', 'installation_token_permissions', 'installation_token_response_scope',
    'installation_token_expiry', 'installation_token_repository_scope', 'first_experiment_repository_preflight',
    'token_preparation_requires_inspection', 'operator_arguments_invalid', 'plan_does_not_consume_approval',
    'candidate_binding_invalid', 'candidate_expired', 'inspect_arguments_forbidden', 'private_attempt_required',
    'github_timeout', 'github_transport_failed', 'local_io_failed', 'operator_check_failed',
}


def safe_error(error):
    if isinstance(error, (Blocked, Denied)) and str(error) in SAFE_ERRORS:
        return str(error)
    if isinstance(error, httpx.TimeoutException):
        return 'github_timeout'
    if isinstance(error, httpx.TransportError):
        return 'github_transport_failed'
    if isinstance(error, json.JSONDecodeError):
        return 'github_response_invalid'
    if isinstance(error, OSError):
        return 'local_io_failed'
    return 'operator_check_failed'


class Blocked(Exception):
    """Only fixed codes may cross the CLI boundary; never provider text/credentials."""


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error repeats untrusted argument values.
        raise Blocked('operator_arguments_invalid')


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
    def __init__(self, *, transport=None, read_only=False):
        self.read_only, self.events = read_only, []
        self.client = httpx.Client(transport=transport, follow_redirects=False, timeout=10,
                                  trust_env=transport is None, limits=httpx.Limits(max_connections=1))

    def call(self, method, path, credential, body=None):
        if ((method, path) not in (TOKEN_READS if self.read_only else ALLOWED)
                or (method == 'POST' and body != REQUEST)
                or (method == 'GET' and body is not None)):
            raise Blocked('github_endpoint_or_scope_forbidden')
        event = {'method': method, 'endpoint': path, 'http_status': None}
        self.events.append(event)
        headers = {'Authorization': 'Bearer ' + credential, 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2026-03-10'}
        with self.client.stream(method, 'https://api.github.com' + path, headers=headers, json=body) as response:
            event['http_status'] = response.status_code
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


def repository_checks(metadata, branch):
    """Only fixed booleans, never names/values from an arbitrary response."""
    from command_center.coding.first_experiment import BASE_SHA
    permissions, commit = metadata.get('permissions'), branch.get('commit')
    return {
        'repository_id_matches': type(metadata.get('id')) is int and metadata['id'] == REPOSITORY_ID,
        'repository_name_matches': metadata.get('full_name') == REPOSITORY,
        'not_archived': metadata.get('archived') is False, 'not_disabled': metadata.get('disabled') is False,
        'permissions_present': isinstance(permissions, dict),
        'admin_false': isinstance(permissions, dict) and permissions.get('admin') is False,
        'push_true': isinstance(permissions, dict) and permissions.get('push') is True,
        'main_name_matches': branch.get('name') == 'main', 'main_protected': branch.get('protected') is True,
        'baseline_matches': isinstance(commit, dict) and commit.get('sha') == BASE_SHA,
    }


def verify_repository(github, token, journal, checkpoint):
    checkpoint('repository_enumeration')
    repositories = github.call('GET', TOKEN_REPOSITORIES, token)
    count, rows = repositories.get('total_count'), repositories.get('repositories')
    journal['enumeration_checks'] = {
        'count_is_one': type(count) is int and count == 1, 'target_only': one_repository(rows),
    }
    if not all(journal['enumeration_checks'].values()):
        raise Blocked('installation_token_repository_scope')
    journal['token_repository_count_verified'] = True
    checkpoint('repository_metadata')
    metadata = github.call('GET', REPO, token)
    checkpoint('branch_metadata')
    branch = github.call('GET', REPO + '/branches/main', token)
    journal['repository_checks'] = repository_checks(metadata, branch)
    checkpoint('repository_validation')
    # Keep the runtime's existing strict permissions/baseline guard unchanged.
    validate_repository(metadata, branch, REPOSITORY, REPOSITORY_ID)


def prepare(key_file, output_directory, revision, approved_plan, approved_until, *, transport=None):
    deadline(approved_until)
    key, output, report = describe(key_file, output_directory, revision)
    if approved_plan != report['plan_digest']:
        raise Blocked('exact_plan_approval_required')
    output.mkdir(mode=0o700)  # Atomic reservation: crash/replay/concurrency never mint again in this attempt.
    journal = {**report, 'approved_until': approved_until, 'phase': 'INTENT', 'token_request_attempted': False,
               'application_configuration_changed': False, 'repository_changes': False, 'paid_calls': 0,
               'installation_repository_count_verified': False, 'token_repository_count_verified': False,
               'diagnostic_version': 2, 'stage': 'identity', 'http_events': []}
    new_file(output / 'receipt.json', json.dumps(journal, sort_keys=True).encode())
    github = None
    try:
        github = GitHub(transport=transport)
        def checkpoint(stage):
            journal.update(stage=stage, http_events=github.events)
            atomic_json(output / 'receipt.json', journal)
        issued = int(time.time())
        assertion = jwt.encode({'iat': issued - 60, 'exp': issued + 300, 'iss': str(APP_ID)}, key, algorithm='RS256')
        identity(github, assertion)
        deadline(approved_until)
        check_source(revision)
        journal.update(phase='TOKEN_REQUEST_INTENT', token_request_attempted=True)
        checkpoint('token_request')  # Durable BEFORE the only credential-creation POST.
        response = github.call('POST', TOKEN_ENDPOINT, assertion, REQUEST)
        checkpoint('token_response')
        token, expires_at = token_metadata(response)
        journal.update(phase='TOKEN_RECEIVED_NOT_STORED', expires_at=expires_at,
                       token_sha256=hashlib.sha256(token.encode()).hexdigest(), token_response_binding_verified=True)
        checkpoint('candidate_store')
        new_file(output / 'candidate.token', token.encode())
        journal['phase'] = 'TOKEN_CANDIDATE_STORED'
        verify_repository(github, token, journal, checkpoint)
        checkpoint('final_checks')
        deadline(approved_until)
        check_source(revision)
        token_metadata(response)  # Check remaining lifetime again after reads.
        checkpoint('final_store')
        new_file(output / 'installation.token', token.encode())
        journal.update(phase='TOKEN_STORED_NOT_CONNECTED', token_repository_count_verified=True,
                       repository_binding_and_baseline_verified=True)
        checkpoint('complete')
        return journal
    except Exception as error:
        # Partial/unknown credentials may exist upstream or in the private file.
        # Never retry, overwrite, echo a body/exception, or claim automatic revocation.
        journal.update(phase='REQUIRES_INSPECTION_NO_RETRY', error_code=safe_error(error),
                       http_events=github.events if github else [])
        atomic_json(output / 'receipt.json', journal)
        raise Blocked(journal['error_code']) from None
    finally:
        if github:
            github.client.close()


def inspection_file(path):
    """Metadata only; never open a token in offline inspection."""
    try:
        info = path.lstat()
        return {'present': True, 'regular': stat.S_ISREG(info.st_mode), 'uid': info.st_uid,
                'mode': oct(stat.S_IMODE(info.st_mode)), 'bytes': info.st_size, 'links': info.st_nlink}
    except FileNotFoundError:
        return {'present': False}


def inspect_attempt(output_directory, revision, *, probe=False, transport=None):
    check_source(revision)
    output = private_path(output_directory)
    info = output.lstat()
    if (os.geteuid() == 0 or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise Blocked('private_attempt_required')
    stream, metadata = _open_private(output / 'receipt.json', os.geteuid(), 16384)
    with stream:
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise Blocked('private_attempt_required')
        receipt = json.loads(stream.read(16385))
    if not isinstance(receipt, dict):
        raise Blocked('candidate_binding_invalid')
    phases = {'INTENT', 'TOKEN_REQUEST_INTENT', 'TOKEN_RECEIVED_NOT_STORED', 'TOKEN_CANDIDATE_STORED',
              'TOKEN_STORED_NOT_CONNECTED', 'REQUIRES_INSPECTION_NO_RETRY'}
    report = {
        'phase': 'OFFLINE_INSPECTION', 'observed_phase': receipt.get('phase') if receipt.get('phase') in phases else 'UNKNOWN',
        'stage': receipt.get('stage') if receipt.get('stage') in STAGES else 'UNRECORDED',
        'error_code': receipt.get('error_code') if receipt.get('error_code') in SAFE_ERRORS else 'UNRECORDED',
        'legacy_receipt': receipt.get('diagnostic_version') != 2,
        'candidate_file': inspection_file(output / 'candidate.token'),
        'installation_file': inspection_file(output / 'installation.token'),
        'token_request_attempted': receipt.get('token_request_attempted') is True,
        'application_configuration_changed': False, 'repository_changes': False,
        'files_changed': False, 'token_issued_by_inspection': False, 'external_calls': 0,
        'credential_value_read': False, 'paid_calls': 0,
    }
    report['observed_error_code'] = report['error_code']
    report['observed_stage'] = report['stage']
    events = receipt.get('http_events', [])
    report['recorded_http_events'] = [
        {k: event.get(k) for k in ('method', 'endpoint', 'http_status')}
        for event in events if isinstance(event, dict)
        and (event.get('method'), event.get('endpoint')) in ALLOWED
        and (event.get('http_status') is None or type(event.get('http_status')) is int
             and 100 <= event['http_status'] <= 599)
    ] if isinstance(events, list) else []
    for name, keys in (('repository_checks', repository_checks({}, {}).keys()),
                       ('enumeration_checks', ('count_is_one', 'target_only'))):
        checks = receipt.get(name)
        if isinstance(checks, dict):
            report['recorded_' + name] = {key: checks[key] for key in keys if type(checks.get(key)) is bool}
    if not probe:
        return report
    # Existing response-bound credential only. Legacy lost credentials cannot be recovered or re-issued here.
    expected = {'app_id': APP_ID, 'installation_id': INSTALLATION_ID, 'repository_id': REPOSITORY_ID,
                'repository': REPOSITORY, 'permissions': PERMISSIONS}
    if (type(receipt.get('diagnostic_version')) is not int or receipt['diagnostic_version'] != 2
            or receipt.get('action') != 'prepare_fixed_experiment_installation_token'
            or receipt.get('token_response_binding_verified') is not True
            or any(type(receipt.get(k)) is not int for k in ('app_id', 'installation_id', 'repository_id'))
            or any(receipt.get(k) != v for k, v in expected.items())
            or not isinstance(receipt.get('token_sha256'), str)
            or not re.fullmatch('[a-f0-9]{64}', receipt['token_sha256'])):
        raise Blocked('candidate_binding_invalid')
    try:
        expiry = datetime.fromisoformat(receipt['expires_at'].replace('Z', '+00:00'))
        if expiry.tzinfo is None or not time.time() < expiry.timestamp() <= time.time() + 3660:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise Blocked('candidate_expired') from None
    stream, metadata = _open_private(output / 'candidate.token', os.geteuid(), 1024, minimum=16)
    with stream:
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise Blocked('candidate_binding_invalid')
        raw = stream.read(1025)
    if len(raw) != metadata.st_size or hashlib.sha256(raw).hexdigest() != receipt['token_sha256']:
        raise Blocked('candidate_binding_invalid')
    token = raw.decode('ascii')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{16,1024}', token):
        raise Blocked('candidate_binding_invalid')
    report['credential_value_read'] = True
    github = GitHub(transport=transport, read_only=True)
    def checkpoint(stage):
        report['stage'] = stage  # Read-only: never update original receipt, files or authority.
    try:
        verify_repository(github, token, report, checkpoint)
        if time.time() >= expiry.timestamp():
            raise Blocked('candidate_expired')
        check_source(revision)
        report.update(phase='READ_ONLY_PROBE_PASSED', probe_ok=True, error_code=None)
    except Exception as error:
        report.update(phase='READ_ONLY_PROBE_BLOCKED', probe_ok=False, error_code=safe_error(error))
    finally:
        report.update(http_events=github.events, external_calls=len(github.events))
        github.client.close()
    return report


def main():
    parser = Arguments(description=__doc__)
    parser.add_argument('action', choices=('plan', 'prepare', 'inspect'), nargs='?', default='plan')
    parser.add_argument('--key-file')
    parser.add_argument('--output-directory', required=True)
    parser.add_argument('--operator-revision', required=True)
    parser.add_argument('--approved-plan')
    parser.add_argument('--approved-until', type=int)
    parser.add_argument('--probe', action='store_true')
    try:
        args = parser.parse_args()
        if args.action == 'inspect':
            if args.key_file is not None or args.approved_plan is not None or args.approved_until is not None:
                raise Blocked('inspect_arguments_forbidden')
            report = inspect_attempt(args.output_directory, args.operator_revision, probe=args.probe)
        elif args.key_file is None or args.probe:
            raise Blocked('operator_arguments_invalid')
        elif args.action == 'plan':
            if args.approved_plan is not None or args.approved_until is not None:
                raise Blocked('plan_does_not_consume_approval')
            report = {**describe(args.key_file, args.output_directory, args.operator_revision)[2],
                      'phase': 'OFFLINE_PLAN_NOT_AUTHORIZED', 'external_calls': 0}
        else:
            report = prepare(args.key_file, args.output_directory, args.operator_revision,
                             args.approved_plan, args.approved_until)
        print(json.dumps(report, sort_keys=True))
        if args.probe and not report.get('probe_ok'):
            raise SystemExit(2)
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': 'inspect_existing_attempt_before_retry',
                          'error_code': safe_error(error),
                          'application_configuration_changed': False, 'paid_calls': 0}))
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
