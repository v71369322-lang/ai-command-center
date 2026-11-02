#!/usr/bin/env python3
"""Record one pre-verified project connection without network or execution access."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from command_center.config import Settings
from command_center.project_connections import (
    OPERATION, REPOSITORIES, history, receipt, register, validate,
)
from command_center.store import Denied, Store, digest


ROOT = Path(__file__).resolve().parents[2]
MAX_EVIDENCE_BYTES = 32768
MAX_SOURCE_BYTES = 16 * 1024 * 1024
SAFE_ERRORS = {
    'dedicated_unprivileged_operator_required', 'evidence_file_invalid',
    'evidence_file_outside_source_required', 'evidence_file_mode_required',
    'evidence_parent_invalid', 'exact_operator_revision_required',
    'operator_arguments_invalid', 'operator_check_failed', 'operator_source_changed',
    'runtime_binding_revision_mismatch',
    'project_connection_manifest_invalid', 'project_connection_operation_invalid',
    'project_connection_provenance_invalid',
    'exact_plan_approval_required', 'fresh_owner_deadline_required',
    'project_connection_idempotency_conflict',
    'project_connection_replacement_requires_disconnect',
    'project_connection_history_invalid', 'project_connection_history_limit',
    'project_connection_registration_missing', 'project_connection_provenance_mismatch',
}


class Blocked(Exception):
    """Fixed public failure codes only; evidence contents never cross the CLI boundary."""


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise Blocked('operator_arguments_invalid')


def safe_error(error):
    if isinstance(error, (Blocked, Denied)) and str(error) in SAFE_ERRORS:
        return str(error)
    return 'operator_check_failed'


def operator_identity(uid=None, uid_map=None, rootless_enabled=None):
    uid = os.geteuid() if uid is None else uid
    if uid != 0:
        return True
    enabled = os.environ.get('F1_ROOTLESS_OPERATOR') == '1' if rootless_enabled is None else rootless_enabled
    if not enabled:
        return False
    try:
        value = Path('/proc/self/uid_map').read_text() if uid_map is None else uid_map
        rows = [[int(part) for part in line.split()] for line in value.splitlines()]
    except (OSError, ValueError):
        return False
    return (bool(rows) and all(len(row) == 3 and row[1] > 0 and row[2] > 0 for row in rows)
            and rows[0][0] == 0)


def runtime_source_digest():
    files = [Path(__file__).resolve()]
    files.extend(sorted((ROOT / 'src/command_center').rglob('*.py')))
    value = hashlib.sha256()
    total = 0
    for path in files:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise Blocked('operator_source_changed')
        raw = path.read_bytes()
        total += len(raw)
        if total > MAX_SOURCE_BYTES:
            raise Blocked('operator_source_changed')
        relative = path.relative_to(ROOT).as_posix().encode()
        value.update(len(relative).to_bytes(4, 'big'))
        value.update(relative)
        value.update(stat.S_IMODE(metadata.st_mode).to_bytes(4, 'big'))
        value.update(len(raw).to_bytes(8, 'big'))
        value.update(raw)
    return value.hexdigest()


def check_source(revision, expected_digest=None):
    if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise Blocked('exact_operator_revision_required')
    digest_value = runtime_source_digest()
    if expected_digest is not None:
        if (not isinstance(expected_digest, str)
                or not re.fullmatch(r'[a-f0-9]{64}', expected_digest)
                or digest_value != expected_digest):
            raise Blocked('operator_source_changed')
        return digest_value
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    try:
        for arguments, expected in ((('rev-parse', 'HEAD'), revision), (('status', '--porcelain'), '')):
            result = subprocess.run(
                ['git', '-C', str(ROOT), *arguments], env=environment, capture_output=True,
                check=True, timeout=10,
            )
            if result.stdout.decode().strip() != expected:
                raise Blocked('operator_source_changed')
    except (OSError, subprocess.SubprocessError):
        raise Blocked('operator_check_failed') from None
    return digest_value


def evidence(value):
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path or path.is_relative_to(ROOT):
        raise Blocked('evidence_file_outside_source_required')
    try:
        parent = path.parent.lstat()
    except OSError:
        raise Blocked('evidence_parent_invalid') from None
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise Blocked('evidence_parent_invalid')
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
                raise Blocked('evidence_file_mode_required')
            if not 2 <= metadata.st_size <= MAX_EVIDENCE_BYTES:
                raise Blocked('evidence_file_invalid')
            raw = stream.read(MAX_EVIDENCE_BYTES + 1)
    except Blocked:
        raise
    except OSError:
        raise Blocked('evidence_file_invalid') from None
    try:
        manifest = json.loads(raw)
        validate(manifest)
    except (UnicodeDecodeError, json.JSONDecodeError, Denied):
        raise Blocked('project_connection_manifest_invalid') from None
    if manifest['repository'] != REPOSITORIES[manifest['project_id']]:
        raise Blocked('project_connection_manifest_invalid')
    return manifest, hashlib.sha256(raw).hexdigest()


def describe(evidence_file, operator_revision, operation_id, source_digest=None):
    source_digest = check_source(operator_revision, source_digest)
    if not operator_identity():
        raise Blocked('dedicated_unprivileged_operator_required')
    if not isinstance(operation_id, str) or not OPERATION.fullmatch(operation_id):
        raise Blocked('project_connection_operation_invalid')
    manifest, evidence_sha256 = evidence(evidence_file)
    scope = {
        'schema': 1, 'action': 'register_project_connection',
        'operator_revision': operator_revision, 'operation_id': operation_id,
        'source_digest': source_digest,
        'evidence_file': str(evidence_file), 'evidence_sha256': evidence_sha256,
        'manifest': manifest,
    }
    return manifest, {
        'schema': 1, 'action': scope['action'], 'operator_revision': operator_revision,
        'source_digest': source_digest,
        'operation_id': operation_id, 'project_id': manifest['project_id'],
        'repository': manifest['repository'], 'repository_id': manifest['repository_id'],
        'baseline_sha': manifest['baseline_sha'], 'evidence_sha256': evidence_sha256,
        'plan_digest': digest(scope), 'state': 'OFFLINE_PLAN_NOT_AUTHORIZED',
        'external_calls': 0, 'credential_values_read': False,
        'execution_enabled': False, 'paid_ai_enabled': False,
        'merge_enabled': False, 'deployment_enabled': False,
        'repository_changes': False, 'application_configuration_changed': False,
    }


def deadline(approved_until):
    now = time.time()
    if type(approved_until) is not int or not now < approved_until <= now + 600:
        raise Blocked('fresh_owner_deadline_required')


def apply(evidence_file, operator_revision, operation_id, source_digest, approved_plan, approved_until):
    deadline(approved_until)
    manifest, report = describe(evidence_file, operator_revision, operation_id, source_digest)
    if not isinstance(approved_plan, str) or approved_plan != report['plan_digest']:
        raise Blocked('exact_plan_approval_required')
    deadline(approved_until)
    check_source(operator_revision, source_digest)
    provenance = {
        'evidence_sha256': report['evidence_sha256'],
        'operator_revision': operator_revision,
        'plan_digest': report['plan_digest'],
    }
    settings = Settings.load()
    if settings.source_revision != operator_revision:
        raise Blocked('runtime_binding_revision_mismatch')
    result = register(Store(settings), 'owner', manifest, operation_id, provenance)
    return {
        **report, **result, 'status': 'PROJECT_CONNECTION_REGISTERED_DISABLED',
        'state': result['state'], 'approved_until': approved_until,
    }


def inspect(operator_revision, operation_id, source_digest):
    check_source(operator_revision, source_digest)
    if not isinstance(operation_id, str) or not OPERATION.fullmatch(operation_id):
        raise Blocked('project_connection_operation_invalid')
    settings = Settings.load()
    if settings.source_revision != operator_revision:
        raise Blocked('runtime_binding_revision_mismatch')
    store = Store(settings)
    with store.transaction() as session:
        store.check_audit(session)
        _, operations = history(session)
        event = operations.get(operation_id)
        if event is None:
            raise Blocked('project_connection_registration_missing')
        provenance = event.get('provenance')
        if not isinstance(provenance, dict) or provenance.get('operator_revision') != operator_revision:
            raise Blocked('project_connection_provenance_mismatch')
        result = receipt(event)
    return {**result, 'status': 'PROJECT_CONNECTION_REGISTRATION_VERIFIED',
            'operation_id': operation_id, 'provenance': provenance,
            'external_calls': 0, 'credential_values_read': False,
            'repository_changes': False, 'application_configuration_changed': False}


def main():
    parser = Arguments(description=__doc__)
    parser.add_argument('action', choices=('plan', 'apply', 'inspect'))
    parser.add_argument('--evidence-file')
    parser.add_argument('--operator-revision', required=True)
    parser.add_argument('--operation-id', required=True)
    parser.add_argument('--source-digest')
    parser.add_argument('--approved-plan')
    parser.add_argument('--approved-until', type=int)
    try:
        args = parser.parse_args()
        if args.action == 'inspect':
            if (args.evidence_file is not None or args.approved_plan is not None
                    or args.approved_until is not None):
                raise Blocked('operator_arguments_invalid')
            if args.source_digest is None:
                raise Blocked('operator_arguments_invalid')
            result = inspect(args.operator_revision, args.operation_id, args.source_digest)
        elif args.evidence_file is None:
            raise Blocked('operator_arguments_invalid')
        elif args.action == 'plan':
            if args.approved_plan is not None or args.approved_until is not None:
                raise Blocked('operator_arguments_invalid')
            if args.source_digest is not None:
                raise Blocked('operator_arguments_invalid')
            _, result = describe(args.evidence_file, args.operator_revision, args.operation_id)
        else:
            if args.source_digest is None:
                raise Blocked('operator_arguments_invalid')
            result = apply(args.evidence_file, args.operator_revision, args.operation_id,
                           args.source_digest,
                           args.approved_plan, args.approved_until)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(json.dumps({
            'status': 'BLOCKED', 'error_code': safe_error(error), 'external_calls': 0,
            'credential_values_read': False, 'execution_enabled': False,
            'paid_ai_enabled': False, 'merge_enabled': False, 'deployment_enabled': False,
            'repository_changes': False, 'application_configuration_changed': False,
        }, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
