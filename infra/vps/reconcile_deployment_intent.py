#!/usr/bin/env python3
"""Reconcile one exact local deployment INTENT without changing runtime services."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import time

from command_center.deployment import Deployment
from command_center.deployment_profile import checksum, validate_manifest


def private_file(path, owner):
    info = path.stat()
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != owner
            or info.st_mode & 0o077 or info.st_size > 1024 * 1024):
        raise ValueError('release_custody_invalid')


def exact_bundle(directory, approved):
    directory = Path(directory)
    owner = os.getuid()
    info = directory.stat()
    if (directory.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid != owner
            or info.st_mode & 0o077):
        raise ValueError('release_custody_invalid')
    private_file(directory / 'bundle.json', owner)
    private_file(directory / 'compose.json', owner)
    bundle = json.loads((directory / 'bundle.json').read_text())
    if checksum(bundle) != approved:
        raise ValueError('exact_release_authorization_required')
    validate_manifest(bundle['manifest'])
    if json.loads((directory / 'compose.json').read_text()) != bundle['compose']:
        raise ValueError('rendered_profile_changed')
    return bundle


def reconcile(directory, approved, approved_until):
    now = int(time.time())
    if (type(approved_until) is not int or not now < approved_until <= now + 3600
            or not re.fullmatch('[a-f0-9]{64}', approved)):
        raise ValueError('fresh_exact_reconciliation_approval_required')
    bundle = exact_bundle(directory, approved)
    deployment = Deployment(bundle, directory)
    result = deployment.reconcile_intent(approved)
    return {
        'status': 'EXACT_DEPLOYMENT_INTENT_RECONCILED',
        'bundle': approved,
        'revision': bundle['manifest']['revision'],
        'runtime_changed': False,
        'binding_changed': False,
        'task_admission_resumed': False,
        'paid_calls': 0,
        'checks': result,
    }


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid reconciliation arguments; values not displayed\n')

    parser = SafeParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--approved-bundle', required=True)
    parser.add_argument('--approved-until', type=int, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(reconcile(args.bundle, args.approved_bundle, args.approved_until), sort_keys=True))
    except Exception as error:
        print(json.dumps({
            'status': 'BLOCKED_REQUIRES_INSPECTION',
            'error_type': type(error).__name__,
            'runtime_changed': False,
            'binding_changed': False,
            'task_admission_resumed': False,
            'paid_calls': 0,
        }, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
