#!/usr/bin/env python3
"""Close one exact attempted memory activation after independent postcheck."""
import argparse
import json
import os
from pathlib import Path
import re
import time

from command_center.deployment import Deployment, load_bundle
from command_center.deployment_profile import atomic_json, checksum
from command_center.store import digest
from command_center.telegram_transport import connection, private_read


def reconcile(candidate_directory, approved_previous, approved_candidate, approved_until):
    now = int(time.time())
    if (type(approved_until) is not int or not now < approved_until <= now + 3600
            or not all(re.fullmatch('[a-f0-9]{64}', value)
                       for value in (approved_previous, approved_candidate))):
        raise ValueError('fresh_exact_reconciliation_approval_required')
    directory = Path(candidate_directory)
    bundle = load_bundle(directory)
    manifest = bundle['manifest']
    if checksum(bundle) != approved_candidate or os.getuid() != manifest['control_uid']:
        raise ValueError('exact_candidate_or_owner_required')
    preparation = json.loads(private_read(directory / 'preparation.json', 32768))
    activation = json.loads(private_read(directory / 'activation.json', 32768))
    if (preparation.get('state') != 'STAGED_NOT_ACTIVATED'
            or preparation.get('candidate_bundle') != approved_candidate
            or preparation.get('expected_incomplete_predecessor') != approved_previous
            or preparation.get('external_ai_profile_enabled') is not False
            or preparation.get('task_admission_resumed') is not False
            or preparation.get('paid_calls') != 0):
        raise ValueError('candidate_preparation_changed')
    if (activation.get('phase') != 'DEPLOYMENT_ATTEMPTED'
            or activation.get('previous') != approved_previous
            or activation.get('target') != approved_candidate
            or activation.get('task_admission_resumed') is not False
            or activation.get('paid_calls') != 0):
        raise ValueError('attempted_activation_receipt_required')
    root = Path(manifest['data_root'])
    state = json.loads(private_read(root / 'deployment.json', 32768))
    if (state.get('phase') != 'VERIFIED' or state.get('bundle') != approved_candidate
            or state.get('revision') != manifest['revision']
            or Path(state.get('directory', '')).resolve() != directory.resolve()):
        raise ValueError('verified_candidate_deployment_required')
    live = connection(root / 'telegram/connection.json')
    scope = manifest.get('telegram', {})
    if (live.source_revision != manifest['revision']
            or digest(live.model_dump()) != scope.get('connection_digest')):
        raise ValueError('candidate_binding_not_live')
    deployment = Deployment(bundle, directory)
    deployment.preflight()
    checks = deployment.postcheck()
    # Recheck mutable evidence after the potentially slow postcheck.
    if (json.loads(private_read(root / 'deployment.json', 32768)) != state
            or connection(root / 'telegram/connection.json') != live
            or json.loads(private_read(directory / 'activation.json', 32768)) != activation):
        raise ValueError('activation_evidence_changed_during_postcheck')
    atomic_json(directory / 'activation.json', {**activation, 'phase': 'VERIFIED',
                                                'checks': checks})
    return {'status': 'RUNTIME_MEMORY_ACTIVATION_RECONCILED',
            'bundle': approved_candidate, 'revision': manifest['revision'],
            'runtime_changed': False, 'binding_changed': False,
            'task_admission_resumed': False, 'paid_calls': 0, 'checks': checks}


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid activation reconciliation arguments; values not displayed\n')

    parser = SafeParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--approved-previous', required=True)
    parser.add_argument('--approved-candidate', required=True)
    parser.add_argument('--approved-until', type=int, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(reconcile(args.candidate, args.approved_previous,
                                   args.approved_candidate, args.approved_until), sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED_REQUIRES_INSPECTION',
                          'error_type': type(error).__name__, 'runtime_changed': False,
                          'binding_changed': False, 'task_admission_resumed': False,
                          'paid_calls': 0}, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
