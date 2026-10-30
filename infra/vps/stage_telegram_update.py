"""Stage a Telegram candidate; apply requires separate exact local approval.

The local operator first builds the pinned source and uses ordinary deployment
prepare WITHOUT Telegram in a new private directory. This tool adds only a
candidate binding. Generic deployment preflight remains fail-closed until a
separately approved binding transition has actually occurred.
"""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import stat
import time

from command_center.deployment import Deployment, Engine, image_check, load_bundle, source_check
from command_center.deployment_profile import atomic_json, checksum, render, validate_manifest, validate_profile
from command_center.store import digest
from command_center.telegram_transport import TelegramConnection, connection, private_read

BASE_REVISION = '316dc1615dea224bcf4bd595d87048d19820bd21'
TARGET_REVISION = 'b2e71fe073f3109e639dac43496884905ce86d9f'
RELEASES = {
    'first-experiment-recovery': ('322186dc180257c618d8b159c78faa6e5bbf0b43',
                                  'bf91c05c754ad41e7f89223ec8d05c02c9007de1'),
    'f34': (BASE_REVISION, TARGET_REVISION),
    'telegram-resume': (TARGET_REVISION, 'bdc8cbcdcf3fe2377fa6cc08250c331d35f99f82'),
    'telegram-mobile': (TARGET_REVISION, 'd932baafce53c0748396abfc019cf81b931ebfec'),
    'first-experiment': ('d932baafce53c0748396abfc019cf81b931ebfec',
                         '0d44f31fe9e37045ed410751cbac7020c59b669a'),
    'first-experiment-readiness': ('d932baafce53c0748396abfc019cf81b931ebfec',
                                 '5a70a48e57d75eceac0526fe8abcf70d57489b8b'),
    'first-experiment-status': ('d932baafce53c0748396abfc019cf81b931ebfec',
                              '185e6e32a60f8b5d62ed7046648560844a6eb19d'),
    'first-experiment-notifications': ('d932baafce53c0748396abfc019cf81b931ebfec',
                                     '8bab523f6f6e50a8a63e13a094f7fccf59ca889f'),
    'first-experiment-cancel': ('d932baafce53c0748396abfc019cf81b931ebfec',
                                'a5d867cb734a4954926a4e77c71e6f5be217057c'),
    'first-experiment-prepare': ('d932baafce53c0748396abfc019cf81b931ebfec',
                                 '7467df292cf990e1b86496a88ed8818d9ada4a28'),
    'first-experiment-authorize': ('d932baafce53c0748396abfc019cf81b931ebfec',
                                   '2822320569ca442ff5579140875ec074e1058898'),
    'first-experiment-github-capability': ('d932baafce53c0748396abfc019cf81b931ebfec',
                                          '322186dc180257c618d8b159c78faa6e5bbf0b43'),
}


def release_pair(release):
    if type(release) is not str or release not in RELEASES:
        raise ValueError('exact_release_profile_required')
    return RELEASES[release]


def integration_transition(old, new, release):
    if release == 'first-experiment-recovery':
        before, after = old.get('first_experiment', {}), new.get('first_experiment', {})
        if (not before or not after or before.get('telegram_readiness') is not True
                or 'recovery' in before or after.get('telegram_readiness') is not True
                or after.get('recovery') != 'f2.2-recovery-1'):
            raise ValueError('explicit_one_call_recovery_transition_required')
    elif release in {'first-experiment', 'first-experiment-readiness', 'first-experiment-status',
                   'first-experiment-notifications', 'first-experiment-cancel', 'first-experiment-prepare', 'first-experiment-authorize',
                   'first-experiment-github-capability'}:
        if ('first_experiment' in old or 'first_experiment' not in new
                or 'recovery' in new['first_experiment']):
            raise ValueError('explicit_first_experiment_binding_required')
        if bool(new['first_experiment'].get('telegram_readiness')) != (release != 'first-experiment'):
            raise ValueError('exact_readiness_profile_required')
    elif 'first_experiment' in old or 'first_experiment' in new:
        raise ValueError('first_experiment_release_required')


def candidate(previous, disabled, config, approved_previous, *, release='f34'):
    """Pure transformation: no daemon, credential, file or permission changes."""
    base_revision, target_revision = release_pair(release)
    if checksum(previous) != approved_previous:
        raise ValueError('previous_bundle_not_approved')
    old, new = previous['manifest'], disabled['manifest']
    validate_manifest(old)
    validate_manifest(new)
    validate_profile(previous['compose'], old)
    validate_profile(disabled['compose'], new)
    if old['revision'] != base_revision or new['revision'] != target_revision:
        raise ValueError('exact_source_revisions_required')
    integration_transition(old, new, release)
    fields = ('migration_hash', 'database_image', 'redis_image', 'data_root',
              'control_uid', 'execution_uid', 'owner_login')
    if any(old.get(k) != new.get(k) for k in fields):
        raise ValueError('separate_scope_or_migration_required')
    if 'telegram' not in old or 'telegram' in new:
        raise ValueError('live_to_disabled_preparation_required')
    scope = old['telegram']
    if (config.mode != 'live' or config.source_revision != base_revision
            or config.token_file != '/run/telegram/token'
            or digest(config.model_dump()) != scope['connection_digest']
            or config.bot_id != scope['bot_id'] or config.owner_id != scope['owner_id']):
        raise ValueError('active_telegram_binding_changed')
    staged = TelegramConnection.model_validate({**config.model_dump(), 'source_revision': target_revision})
    bundle = copy.deepcopy(disabled)
    bundle['manifest']['telegram'] = {**scope, 'connection_digest': digest(staged.model_dump())}
    bundle['compose'] = render(disabled['compose'], bundle['manifest'])
    validate_profile(bundle['compose'], bundle['manifest'])
    return bundle, staged


def stage(active_directory, disabled_directory, output, approved_previous, *, release='f34'):
    base_revision, target_revision = release_pair(release)
    previous, disabled = load_bundle(active_directory), load_bundle(disabled_directory)
    root = Path(previous['manifest']['data_root'])
    if os.getuid() != previous['manifest']['control_uid']:
        raise ValueError('dedicated_control_user_required')
    state = json.loads(private_read(root / 'deployment.json', 32768))
    if (state.get('phase') != 'VERIFIED' or state.get('bundle') != approved_previous
            or state.get('revision') != base_revision
            or Path(state.get('directory', '')).resolve() != Path(active_directory).resolve()):
        raise ValueError('verified_predecessor_changed')
    live_config = root / 'telegram/connection.json'
    config = connection(live_config)
    bundle, staged = candidate(previous, disabled, config, approved_previous, release=release)
    source_check(disabled['manifest'])
    for uid, images in (
        (bundle['manifest']['control_uid'], {k: v for k, v in bundle['manifest']['images'].items()
                                           if k not in {'executor', 'coding'}}),
        (bundle['manifest']['execution_uid'], {k: v for k, v in bundle['manifest']['images'].items()
                                             if k in {'executor', 'coding'}}),
    ):
        engine = Engine(uid)
        engine.preflight()
        image_check(engine, images, target_revision)
    if 'first_experiment' in bundle['manifest']:
        from command_center.deployment_integrations import check_binding
        check_binding(bundle['manifest'])
    output = Path(output)
    parent = output.parent.lstat()
    if (not output.is_absolute() or output.exists() or output.is_symlink()
            or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077
            or output.resolve().is_relative_to(root.resolve())
            or output.resolve().is_relative_to(Path(bundle['manifest']['source_root']).resolve())):
        raise ValueError('new_private_candidate_directory_required')
    # Recheck both mutable inputs after potentially slow local image inspection.
    if connection(live_config) != config or json.loads(private_read(root / 'deployment.json', 32768)) != state:
        raise ValueError('predecessor_changed_during_preparation')
    output.mkdir(mode=0o700)
    plan = {'schema': 1, 'state': 'STAGED_NOT_ACTIVATED', 'release': release, 'revision': target_revision,
            'expected_previous': approved_previous, 'candidate_bundle': checksum(bundle),
            'previous_connection': digest(config.model_dump()),
            'candidate_connection': digest(staged.model_dump()), 'prepared_at': int(time.time()),
            'deployment_authorized': False, 'live_binding_modified': False, 'go_live': False}
    atomic_json(output / 'bundle.json', bundle)
    atomic_json(output / 'compose.json', bundle['compose'])
    atomic_json(output / 'connection.candidate.json', staged.model_dump())
    atomic_json(output / 'preparation.json', plan)
    return plan


def apply_candidate(active_directory, candidate_directory, approved_previous, approved_candidate, approved_until, *, release='f34'):
    """Explicit local operator action; never invoked by staging or the mailbox.

    Unknown results preserve activation.json and prohibit retry. Existing
    Deployment owns task quiescing, encrypted backup, update and postcheck.
    """
    base_revision, target_revision = release_pair(release)

    def deadline():
        now = int(time.time())
        if type(approved_until) is not int or not now < approved_until <= now + 3600:
            raise ValueError('fresh_bounded_update_approval_required')

    deadline()
    directory = Path(candidate_directory)
    previous, target = load_bundle(active_directory), load_bundle(directory)
    old, new = previous['manifest'], target['manifest']
    if checksum(previous) != approved_previous or checksum(target) != approved_candidate:
        raise ValueError('exact_bundle_approvals_required')
    if old['revision'] != base_revision or new['revision'] != target_revision:
        raise ValueError('exact_source_revisions_required')
    integration_transition(old, new, release)
    if any(old.get(k) != new.get(k) for k in ('migration_hash', 'database_image', 'redis_image',
                                             'data_root', 'control_uid', 'execution_uid', 'owner_login')):
        raise ValueError('separate_scope_or_migration_required')
    if os.getuid() != old['control_uid']:
        raise ValueError('dedicated_control_user_required')
    root = Path(old['data_root'])
    journal = directory / 'activation.json'
    if journal.exists() or journal.is_symlink():
        raise ValueError('existing_activation_requires_reconciliation')
    if directory.resolve().is_relative_to(root.resolve()):
        raise ValueError('candidate_must_be_outside_active_state')
    live_config = root / 'telegram/connection.json'
    original = connection(live_config)
    staged = connection(directory / 'connection.candidate.json')
    if (original.source_revision != base_revision or original.mode != 'live'
            or original.token_file != '/run/telegram/token'
            or digest(original.model_dump()) != old.get('telegram', {}).get('connection_digest')
            or staged.model_dump() != {**original.model_dump(), 'source_revision': target_revision}
            or new.get('telegram') != {**old['telegram'], 'connection_digest': digest(staged.model_dump())}):
        raise ValueError('exact_candidate_binding_required')
    controller = Deployment(previous, active_directory)
    lock = os.open(root / 'deployment.lock', os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(private_read(root / 'deployment.json', 32768))
        if (state.get('phase') != 'VERIFIED' or state.get('bundle') != approved_previous
                or Path(state.get('directory', '')).resolve() != Path(active_directory).resolve()
                or connection(live_config) != original):
            raise ValueError('verified_predecessor_changed')
        controller.preflight()
        source_check(new)
        if 'first_experiment' in new:
            from command_center.deployment_integrations import check_binding
            check_binding(new)
        for uid, names in ((new['control_uid'], {'api', 'worker', 'broker'}),
                           (new['execution_uid'], {'executor', 'coding'})):
            engine = Engine(uid)
            engine.preflight()
            image_check(engine, {k: new['images'][k] for k in names}, target_revision)
        deadline()
        # Recheck after the potentially slow image/source preflight, under the lock.
        if connection(live_config) != original or json.loads(private_read(root / 'deployment.json', 32768)) != state:
            raise ValueError('predecessor_changed_during_preparation')
        atomic_json(directory / 'connection.previous.json', original.model_dump())
        record = {'expected_previous': approved_previous, 'target': approved_candidate, 'release': release,
                  'phase': 'PAUSING_TELEGRAM', 'approved_until': approved_until, 'go_live': False}
        atomic_json(journal, record)
        controller.pause_telegram()
        atomic_json(live_config, staged.model_dump())
        atomic_json(journal, {**record, 'phase': 'BINDING_ACTIVE'})
    finally:
        os.close(lock)
    deadline()
    # Admission may have an uncertain result even before Deployment writes INTENT.
    # Never infer "no effects" solely from the old deployment.json still existing.
    atomic_json(journal, {**record, 'phase': 'DEPLOYMENT_ATTEMPTED'})
    result = Deployment(target, directory).apply('update', approved_candidate, expected_previous=approved_previous)
    atomic_json(journal, {**record, 'phase': 'VERIFIED', 'checks': result})
    return result


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid preparation arguments; values not displayed\n')
    parser = SafeParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'apply'])
    parser.add_argument('--release', choices=tuple(RELEASES), default='f34')
    parser.add_argument('--active-bundle', required=True)
    parser.add_argument('--disabled-bundle')
    parser.add_argument('--output', required=True)
    parser.add_argument('--approved-previous', required=True)
    parser.add_argument('--approved-candidate')
    parser.add_argument('--approved-until', type=int)
    args = parser.parse_args()
    try:
        if args.action == 'stage':
            if not args.disabled_bundle:
                parser.error('disabled bundle required for stage')
            result = stage(args.active_bundle, args.disabled_bundle, args.output, args.approved_previous, release=args.release)
        else:
            result = apply_candidate(args.active_bundle, args.output, args.approved_previous,
                                     args.approved_candidate, args.approved_until, release=args.release)
        print(json.dumps(result))
    except Exception:
        parser.exit(1, 'telegram_candidate_unconfirmed; inspect output; do not overwrite or retry blindly\n')


if __name__ == '__main__':
    main()
