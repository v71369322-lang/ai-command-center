#!/usr/bin/env python3
"""Apply one exact staged Telegram candidate after its predecessor is reconciled."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import time

from command_center.deployment import Deployment, Engine, image_check, load_bundle, source_check
from command_center.deployment_profile import PROJECT, atomic_json, checksum
from command_center.store import digest
from command_center.telegram_transport import connection

from reconcile_deployment_intent import exact_bundle


def deadline(value):
    now = int(time.time())
    if type(value) is not int or not now < value <= now + 3600:
        raise ValueError('fresh_bounded_update_approval_required')


def validate_transition(old, target, old_digest, target_digest):
    before, after = old['manifest'], target['manifest']
    if checksum(old) != old_digest or checksum(target) != target_digest:
        raise ValueError('exact_bundle_approvals_required')
    fixed = ('migration_hash', 'database_image', 'redis_image', 'data_root',
             'control_uid', 'execution_uid', 'owner_login')
    if any(before.get(key) != after.get(key) for key in fixed):
        raise ValueError('separate_scope_or_migration_required')
    if ('telegram' not in before or 'telegram' not in after
            or 'first_experiment' in after
            or target['compose']['services']['telegram'].get('mem_limit') != '256m'
            or str(target['compose']['services']['watchdog'].get('mem_limit')) != '268435456'):
        raise ValueError('telegram_memory_candidate_scope_invalid')
    for key in ('mode', 'owner_id', 'bot_id'):
        if before['telegram'][key] != after['telegram'][key]:
            raise ValueError('telegram_identity_changed')
    return before, after


class ReconciledUpdate(Deployment):
    """The exact predecessor poller was already stopped before binding activation."""

    def pause_telegram(self):
        if self.engine.run('ps', '-q', '--filter', 'name=^' + PROJECT + '-telegram-1$').strip():
            raise ValueError('predecessor_telegram_stop_unconfirmed')


def apply(previous_directory, candidate_directory, approved_previous, approved_candidate,
          approved_until):
    deadline(approved_until)
    if not all(re.fullmatch('[a-f0-9]{64}', value)
               for value in (approved_previous, approved_candidate)):
        raise ValueError('exact_bundle_approvals_required')
    previous = exact_bundle(previous_directory, approved_previous)
    target = load_bundle(candidate_directory)
    old, new = validate_transition(
        previous, target, approved_previous, approved_candidate)
    root = Path(old['data_root'])
    state_file = root / 'deployment.json'
    live_file = root / 'telegram/connection.json'
    directory = Path(candidate_directory)
    activation = directory / 'activation.json'
    if activation.exists() or activation.is_symlink():
        raise ValueError('existing_activation_requires_reconciliation')
    preparation = json.loads((directory / 'preparation.json').read_text())
    if (preparation.get('state') != 'STAGED_NOT_ACTIVATED'
            or preparation.get('candidate_bundle') != approved_candidate
            or preparation.get('expected_incomplete_predecessor') != approved_previous
            or preparation.get('external_ai_profile_enabled') is not False):
        raise ValueError('candidate_preparation_changed')
    original = connection(live_file)
    staged = connection(directory / 'connection.candidate.json')
    if (digest(original.model_dump()) != old['telegram']['connection_digest']
            or staged.model_dump() != {**original.model_dump(), 'source_revision': new['revision']}
            or digest(staged.model_dump()) != new['telegram']['connection_digest']):
        raise ValueError('exact_candidate_binding_required')

    controller = Deployment(previous, previous_directory)
    controller.preflight()
    source_check(new)
    for uid, names in ((new['control_uid'], {'api', 'worker', 'broker'}),
                       (new['execution_uid'], {'executor', 'coding'})):
        engine = Engine(uid)
        engine.preflight()
        image_check(engine, {key: new['images'][key] for key in names}, new['revision'])
    deadline(approved_until)

    record = {'schema': 1, 'phase': 'PREPARED', 'previous': approved_previous,
              'target': approved_candidate, 'approved_until': approved_until,
              'task_admission_resumed': False, 'paid_calls': 0}
    lock = os.open(root / 'deployment.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(state_file.read_text())
        if (state.get('phase') != 'VERIFIED' or state.get('bundle') != approved_previous
                or Path(state.get('directory', '')).resolve() != Path(previous_directory).resolve()
                or connection(live_file) != original):
            raise ValueError('verified_predecessor_changed')
        atomic_json(activation, record)
        controller.compose('stop', 'telegram')
        if controller.engine.run(
                'ps', '-q', '--filter', 'name=^' + PROJECT + '-telegram-1$').strip():
            raise ValueError('predecessor_telegram_stop_unconfirmed')
        atomic_json(directory / 'connection.previous.json', original.model_dump())
        atomic_json(live_file, staged.model_dump())
        atomic_json(activation, {**record, 'phase': 'BINDING_ACTIVE'})
    finally:
        os.close(lock)

    deadline(approved_until)
    atomic_json(activation, {**record, 'phase': 'DEPLOYMENT_ATTEMPTED'})
    result = ReconciledUpdate(target, directory).apply(
        'update', approved_candidate, expected_previous=approved_previous)
    atomic_json(activation, {**record, 'phase': 'VERIFIED', 'checks': result})
    return {'status': 'TELEGRAM_MEMORY_FIX_APPLIED', 'bundle': approved_candidate,
            'revision': new['revision'], 'task_admission_resumed': False,
            'paid_calls': 0, 'checks': result}


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid update arguments; values not displayed\n')

    parser = SafeParser(description=__doc__)
    parser.add_argument('--previous', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--approved-previous', required=True)
    parser.add_argument('--approved-candidate', required=True)
    parser.add_argument('--approved-until', type=int, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(apply(args.previous, args.candidate, args.approved_previous,
                               args.approved_candidate, args.approved_until), sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED_REQUIRES_INSPECTION',
                          'error_type': type(error).__name__, 'paid_calls': 0}, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
