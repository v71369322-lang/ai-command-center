"""Offline, sealed review package; deliberately grants no activation authority."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .deployment import load_bundle
from .deployment_profile import atomic_json, checksum, validate_manifest, validate_profile
from .request_planning import _unique
from .telegram_transport import private_read

FILES = {'previous.json', 'candidate.json', 'plan.json'}
FIXED = ('migration_hash', 'database_image', 'redis_image', 'control_uid',
         'execution_uid', 'data_root', 'owner_login')
BLOCKERS = ['exact_built_source_and_images_required',
            'live_rootless_host_acceptance_required',
            'fresh_operator_tariff_funding_and_data_sharing_evidence_required',
            'private_profile_host_and_credential_identity_required',
            'exact_deployment_authorization_required']
PRECHECK = ['verified_deployment_and_activation_match_predecessor',
            'clean_target_source_and_all_image_labels_match_revision',
            'rootless_cgroup_v2_systemd_and_private_file_custody',
            'normal_stop_and_telegram_intake_quiesced',
            'no_active_f1_tasks_unresolved_financial_actions_or_runtime_runs',
            'existing_backup_and_schema_compatibility_checks']
POSTCHECK = ['existing_deployment_postcheck_and_watchdog_worker_readiness',
             'actual_broker_image_source_metadata_and_rootless_host_attestation',
             'deployment_and_activation_journals_verified',
             'owner_resume_then_plan_prepare_without_provider_io',
             'separate_observed_plan_authorize_before_any_paid_call']


def plan(previous, candidate, predecessor_pin, candidate_pin):
    """Validate both existing release contracts, then describe a blocked transition."""
    for bundle, pin in ((previous, predecessor_pin), (candidate, candidate_pin)):
        if (not re.fullmatch('[a-f0-9]{64}', pin) or checksum(bundle) != pin
                or set(bundle) != {'manifest', 'compose'}):
            raise ValueError('exact_bundle_pin_required')
        validate_manifest(bundle['manifest'])
        validate_profile(bundle['compose'], bundle['manifest'])
    old, new = previous['manifest'], candidate['manifest']
    if old['revision'] == new['revision']:
        raise ValueError('distinct_target_revision_required')
    if any(old.get(k) != new.get(k) for k in FIXED):
        raise ValueError('separate_migration_or_scope_review_required')
    if ('first_experiment' in old or 'first_experiment' in new
            or 'telegram' not in old or 'telegram' not in new
            or any(old['telegram'][k] != new['telegram'][k] for k in ('mode', 'owner_id', 'bot_id'))):
        raise ValueError('same_owner_telegram_without_external_integration_required')
    return {'schema': 1, 'purpose': 'planning-release-review.v1',
            'status': 'BLOCKED_NOT_ACTIVATABLE', 'activation_authorized': False,
            'paid_calls_authorized': False, 'previous_bundle': predecessor_pin,
            'candidate_bundle': candidate_pin, 'previous_revision': old['revision'],
            'target_revision': new['revision'], 'images': new['images'],
            'planning_pins': ({k: v for k, v in new['planning'].items() if k.endswith(('_sha256', '_digest'))}
                              if 'planning' in new else None),
            'migration_hash': new['migration_hash'], 'blockers': BLOCKERS.copy(),
            'preconditions': PRECHECK.copy(), 'postconditions': POSTCHECK.copy(),
            'activation_mechanism': 'existing_prepare_inspect_exact_approval_update_postcheck',
            'failure_policy': 'halt_preserve_unknown_no_retry_no_blind_rollback'}


def prepare(previous_directory, candidate_directory, output, predecessor_pin, candidate_pin):
    previous, candidate = load_bundle(previous_directory), load_bundle(candidate_directory)
    review = plan(previous, candidate, predecessor_pin, candidate_pin)
    output = Path(output)
    parent = output.parent.stat()
    if (not output.is_absolute() or '..' in output.parts or output.is_symlink()
            or output.parent.resolve() != output.parent or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
        raise ValueError('private_canonical_output_parent_required')
    # Exclusive mkdir; interrupted writes cannot have a valid completion seal.
    output.mkdir(mode=0o700)
    documents = {'previous.json': previous, 'candidate.json': candidate, 'plan.json': review}
    for name, value in documents.items():
        atomic_json(output / name, value)
    seal = {'schema': 1, 'files': {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                                 for name in sorted(FILES)}}
    atomic_json(output / 'seal.json', seal)
    return checksum(seal)


def verify(directory, approved_seal):
    """Out-of-band pin required: a seal alone is integrity, not authorization/signature."""
    directory = Path(directory)
    if set(p.name for p in directory.iterdir()) != FILES | {'seal.json'}:
        raise ValueError('release_package_inventory_changed')
    seal = json.loads(private_read(directory / 'seal.json', 16384), object_pairs_hook=_unique)
    if (not re.fullmatch('[a-f0-9]{64}', approved_seal) or checksum(seal) != approved_seal
            or set(seal) != {'schema', 'files'} or seal['schema'] != 1 or set(seal['files']) != FILES):
        raise ValueError('release_package_seal_changed')
    documents = {}
    for name in sorted(FILES):
        raw = private_read(directory / name, 2 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != seal['files'][name]:
            raise ValueError('release_package_file_changed')
        documents[name] = json.loads(raw, object_pairs_hook=_unique)
    previous, candidate = documents['previous.json'], documents['candidate.json']
    expected = plan(previous, candidate, checksum(previous), checksum(candidate))
    if documents['plan.json'] != expected:
        raise ValueError('release_package_plan_changed')
    return expected
