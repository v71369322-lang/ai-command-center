#!/usr/bin/env python3
"""Prepare a bounded Telegram/watchdog memory candidate without deployment."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import stat
import time

from command_center.deployment import Engine, image_check, load_bundle, source_check
from command_center.deployment_profile import atomic_json, checksum, render
from command_center.store import digest
from command_center.telegram_transport import TelegramConnection, connection, private_read

from reconcile_deployment_intent import exact_bundle


def candidate(previous, disabled, active, previous_digest, previous_revision, target_revision):
    if checksum(previous) != previous_digest:
        raise ValueError('exact_predecessor_required')
    old, new = previous['manifest'], disabled['manifest']
    if old.get('revision') != previous_revision or new.get('revision') != target_revision:
        raise ValueError('exact_revisions_required')
    fixed = ('migration_hash', 'database_image', 'redis_image', 'data_root',
             'control_uid', 'execution_uid', 'owner_login')
    if any(old.get(key) != new.get(key) for key in fixed):
        raise ValueError('separate_scope_or_migration_required')
    if 'telegram' not in old or 'telegram' in new or 'first_experiment' in new:
        raise ValueError('disabled_non_ai_target_required')
    scope = old['telegram']
    if (active.mode != 'live' or active.source_revision != previous_revision
            or active.token_file != '/run/telegram/token'
            or digest(active.model_dump()) != scope['connection_digest']
            or active.owner_id != scope['owner_id'] or active.bot_id != scope['bot_id']):
        raise ValueError('active_telegram_binding_changed')
    staged = TelegramConnection.model_validate({**active.model_dump(),
                                                 'source_revision': target_revision})
    bundle = copy.deepcopy(disabled)
    bundle['manifest']['telegram'] = {**scope, 'connection_digest': digest(staged.model_dump())}
    bundle['compose'] = render(disabled['compose'], bundle['manifest'])
    services = bundle['compose']['services']
    if (services['telegram'].get('mem_limit') != '256m'
            or str(services['watchdog'].get('mem_limit')) != '268435456'):
        raise ValueError('exact_memory_profile_required')
    return bundle, staged


def prepare(previous_directory, disabled_directory, output, approved_previous,
            previous_revision, target_revision):
    if (not re.fullmatch('[a-f0-9]{64}', approved_previous)
            or not all(re.fullmatch('[a-f0-9]{40}', value)
                       for value in (previous_revision, target_revision))):
        raise ValueError('exact_approval_and_revisions_required')
    previous = exact_bundle(previous_directory, approved_previous)
    disabled = load_bundle(disabled_directory)
    old = previous['manifest']
    if os.getuid() != old['control_uid']:
        raise ValueError('dedicated_control_user_required')
    root = Path(old['data_root'])
    state = json.loads(private_read(root / 'deployment.json', 32768))
    if (state.get('phase') != 'VERIFIED' or state.get('bundle') != approved_previous
            or state.get('revision') != previous_revision
            or Path(state.get('directory', '')).resolve() != Path(previous_directory).resolve()):
        raise ValueError('verified_predecessor_changed')
    live_file = root / 'telegram/connection.json'
    active = connection(live_file)
    bundle, staged = candidate(previous, disabled, active, approved_previous,
                               previous_revision, target_revision)
    source_check(bundle['manifest'])
    for uid, names in ((bundle['manifest']['control_uid'], {'api', 'worker', 'broker'}),
                       (bundle['manifest']['execution_uid'], {'executor', 'coding'})):
        engine = Engine(uid)
        engine.preflight()
        image_check(engine, {key: bundle['manifest']['images'][key] for key in names},
                    target_revision)
    output = Path(output)
    parent = output.parent.stat()
    if (not output.is_absolute() or output.exists() or output.is_symlink()
            or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or parent.st_mode & 0o077 or output.resolve().is_relative_to(root.resolve())):
        raise ValueError('new_private_candidate_directory_required')
    if (connection(live_file) != active
            or json.loads(private_read(root / 'deployment.json', 32768)) != state):
        raise ValueError('predecessor_changed_during_preparation')
    output.mkdir(mode=0o700)
    plan = {'schema': 1, 'state': 'STAGED_NOT_ACTIVATED',
            'revision': target_revision, 'expected_incomplete_predecessor': approved_previous,
            'candidate_bundle': checksum(bundle), 'prepared_at': int(time.time()),
            'telegram_memory_bytes': 268435456, 'watchdog_memory_bytes': 268435456,
            'external_ai_profile_enabled': False, 'deployment_authorized': False,
            'task_admission_resumed': False, 'paid_calls': 0}
    atomic_json(output / 'bundle.json', bundle)
    atomic_json(output / 'compose.json', bundle['compose'])
    atomic_json(output / 'connection.candidate.json', staged.model_dump())
    atomic_json(output / 'preparation.json', plan)
    return plan


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid candidate preparation arguments; values not displayed\n')

    parser = SafeParser(description=__doc__)
    parser.add_argument('--previous', required=True)
    parser.add_argument('--disabled', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--approved-previous', required=True)
    parser.add_argument('--previous-revision', required=True)
    parser.add_argument('--target-revision', required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.previous, args.disabled, args.output, args.approved_previous,
                         args.previous_revision, args.target_revision)
        print(json.dumps({'status': 'RUNTIME_MEMORY_CANDIDATE_PREPARED_NOT_APPLIED',
                          **result}, sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED_REQUIRES_INSPECTION',
                          'error_type': type(error).__name__, 'paid_calls': 0}, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
