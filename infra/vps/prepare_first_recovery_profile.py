"""Offline disabled recovery draft. No provider, database, token or deployment action.

plan reads protected inputs only. prepare writes a new private directory pinned
by the plan digest. Neither operation supplies owner consent or fresh evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from command_center.coding.first_experiment import (CAP, CONTEXT_TOKENS, EXPERIMENT_ID, MODEL,
    OUTPUT_TOKENS, RECOVERY_ID, REQUIRED, quote)
from command_center.coding.integration_config import IntegrationConfig
from command_center.coding.recovery import RECOVERY_CAP, RecoveryExperiment
from command_center.deployment_integrations import CREDENTIAL_TARGETS, _open_private
from command_center.store import digest

ROOT = Path(__file__).resolve().parents[2]
TASK_ID = '938e838d-54d4-470d-ad71-5c6a49a42c7d'
REPOSITORY = 'v71369322-lang/acc-f2-synthetic-first'
REPOSITORY_ID = 1438229730
MAX_INSPECTION_AGE = 300


class DraftError(Exception):
    """Fixed public codes only; never wrap untrusted exception or input text."""


def reject(condition, code):
    if condition:
        raise DraftError(code)


def build_draft(config, inspection, now):
    reject(not isinstance(inspection, dict), 'inspection_required')
    try:
        checked = datetime.fromisoformat(inspection['checked_at_utc'])
        age = (now - checked).total_seconds()
    except (KeyError, TypeError, ValueError):
        raise DraftError('fresh_inspection_required') from None
    reject(not 0 <= age <= MAX_INSPECTION_AGE, 'fresh_inspection_required')
    true_flags = ('read_only', 'source_matches_installed')
    false_flags = ('provider_credential_values_read', 'response_text_printed', 'task_restarted',
        'application_mutations_requested', 'runtime_mutations_requested', 'token_issued',
        'deployment_authorized', 'paid_recovery_authorized', 'recovery_authority_verified')
    reject(inspection.get('schema') != 1 or type(inspection.get('schema')) is not int
        or inspection.get('scope') != 'fixed_parent_local_read_only' or inspection.get('task_id') != TASK_ID
        or any(inspection.get(k) is not True for k in true_flags)
        or any(inspection.get(k) is not False for k in false_flags)
        or any(type(inspection.get(k)) is not int or inspection[k] != 0 for k in ('provider_calls', 'paid_calls')),
        'read_only_inspection_scope_required')
    blockers = inspection.get('blockers')
    reject(blockers not in ([], ['profile_evidence_missing_or_expired'])
        or inspection.get('status') != ('BLOCKED' if blockers else 'LOCAL_OBSERVATIONS_COMPLETE'),
        'inspection_has_unresolved_blockers')
    db, runtime, container, profile = (inspection.get(k, {}) for k in ('database', 'runtime', 'container', 'profile'))
    reject(any(not isinstance(item, dict) for item in (db, runtime, container, profile)), 'inspection_sections_required')
    parent_flags = ('state_failed', 'reason_matches', 'fixed_payload_matches', 'owner_matches', 'attempts_is_one',
        'synthetic_reserve_zero', 'failure_matches', 'grant_self_digest_matches', 'grant_source_matches',
        'grant_mode_live', 'all_actions_closed', 'saved_response_failure_matches',
        'audit_chain_verified', 'action_ledger_verified')
    reject(db.get('task_id') != TASK_ID or any(db.get(k) is not True for k in parent_flags)
        or type(db.get('fence')) is not int or not 0 < db['fence'] < 2**63
        or type(db.get('openai_count')) is not int or db['openai_count'] != 1
        or type(db.get('reserved_nano_rub')) is not int or db['reserved_nano_rub'] != 0
        or db.get('recovery_authority_verified') is not False
        or not isinstance(db.get('grant_digest'), str) or not re.fullmatch('[a-f0-9]{64}', db['grant_digest']),
        'closed_parent_observations_required')
    actions = db.get('actions')
    reject(not isinstance(actions, list) or not 1 <= len(actions) <= 64
        or type(db.get('action_count')) is not int or db['action_count'] != len(actions)
        or any(not isinstance(a, dict) or a.get('kind') not in {'openai', 'github', 'github_git'}
            or a.get('state') != 'COMPLETE' or type(a.get('reserved_nano_rub')) is not int
            or a['reserved_nano_rub'] != 0 or type(a.get('actual_nano_rub')) is not int
            or a['actual_nano_rub'] < 0 or a['kind'] != 'openai' and a['actual_nano_rub'] != 0 for a in actions),
        'closed_action_observations_required')
    reject(sum(a['kind'] == 'openai' for a in actions) != 1
        or sum(a['actual_nano_rub'] for a in actions) != db.get('actual_nano_rub'), 'action_accounting_mismatch')
    reject(any(runtime.get(k) is not True for k in ('audit_chain_verified', 'parent_run_done',
        'parent_revision_matches', 'container_name_matches', 'watchdog_fresh', 'worker_fresh'))
        or type(runtime.get('unresolved_runs')) is not int or runtime['unresolved_runs'] != 0
        or container.get('rootless_preflight_verified') is not True or container.get('parent_container_absent') is not True,
        'closed_runtime_observations_required')
    config_hash = digest(config.model_dump())
    reject(profile.get('profile_hash') != config_hash or profile.get('matches_original_grant') is not True
        or db.get('grant_profile_hash') != config_hash, 'original_profile_pin_changed')
    first, tariff = config.first_experiment, config.tariff
    reject(config.mode != 'live' or config.live_authorized is not True or not first
        or first.id != EXPERIMENT_ID or isinstance(first, RecoveryExperiment)
        or first.repository_id != REPOSITORY_ID or config.synthetic_repository != REPOSITORY
        or config.credential_files != {config.openai_secret_ref: CREDENTIAL_TARGETS['openai_key_file'],
            config.github_secret_ref: CREDENTIAL_TARGETS['github_token_file']}
        or config.openai_secret_ref == config.github_secret_ref, 'fixed_original_profile_required')
    reject(not tariff or not tariff.confirmed or tariff.model != MODEL or tariff.context_tokens != CONTEXT_TOKENS
        or tariff.max_output_tokens != OUTPUT_TOKENS or max(config.daily_nano_rub, config.monthly_nano_rub) > CAP,
        'original_tariff_scope_required')
    actual, budget, reservation = db.get('actual_nano_rub'), db.get('grant_budget_nano_rub'), tariff.maximum()
    reject(type(actual) is not int or actual < 0 or type(budget) is not int or not 0 < budget <= CAP
        or not 0 < reservation <= min(RECOVERY_CAP, config.daily_nano_rub, config.monthly_nano_rub)
        or actual + reservation > budget, 'one_call_cumulative_budget_required')
    try:
        quoted = quote(first.payment_rub_per_usd_upper, first.extra_rub_upper, calls=1)
    except Exception:
        raise DraftError('original_payment_terms_required') from None
    reject(not 0 < quoted['max_nano_rub'] <= reservation, 'payment_quote_exceeds_reservation')
    result = config.model_copy(deep=True)
    result.mode, result.live_authorized, result.budget_evidence = 'disabled', False, ''
    fields = first.model_dump(exclude={'id', 'evidence', 'existing_credit_usd'})
    result.first_experiment = RecoveryExperiment(**fields, original_task_id=TASK_ID,
        original_grant_digest=db['grant_digest'], existing_credit_usd=None, evidence={})
    result.tariff.confirmed = False
    result.tariff.evidence = 'Historical tariff copied into disabled draft; fresh verification required'
    # Roundtrip through strict parsing. No references or credentials supplied by the inspection.
    document = {**result.model_dump(), 'credential_files': result.credential_files}
    result = IntegrationConfig.model_validate(document)
    return result, {'schema': 1, 'state': 'RECOVERY_DRAFT_DISABLED_NOT_CONNECTED',
        'experiment_id': RECOVERY_ID, 'original_task_id': TASK_ID, 'original_grant_digest': db['grant_digest'],
        'source_profile_hash': config_hash, 'draft_profile_hash': digest(result.model_dump()),
        'prior_actual_nano_rub': actual, 'one_call_reservation_nano_rub': reservation,
        'cumulative_max_nano_rub': actual + reservation, 'original_budget_nano_rub': budget,
        'max_calls': 1, 'max_repairs': 0, 'requires_fresh_evidence': list(REQUIRED),
        'provider_calls': 0, 'paid_calls': 0, 'provider_credential_values_read': False,
        'recovery_authority_verified': False, 'deployment_authorized': False, 'paid_recovery_authorized': False}


def private_path(value):
    path = Path(value)
    reject(not path.is_absolute() or str(path) != value or path.resolve() != path or path.is_relative_to(ROOT),
           'private_path_outside_operator_required')
    parent = path.parent.lstat()
    reject(not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
           or stat.S_IMODE(parent.st_mode) != 0o700, 'private_parent_required')
    return path


def read_json(path, maximum):
    stream, before = _open_private(path, os.geteuid(), maximum)
    with stream:
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    reject((before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
        (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != before.st_size, 'input_changed')
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def check_operator(revision):
    reject(os.geteuid() == 0, 'dedicated_unprivileged_operator_required')
    reject(not isinstance(revision, str) or not re.fullmatch('[a-f0-9]{40}', revision), 'exact_operator_revision_required')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    for args, expected in [(('rev-parse', 'HEAD'), revision), (('status', '--porcelain'), '')]:
        result = subprocess.run(['git', '--no-replace-objects', '-C', str(ROOT), *args],
            env=env, capture_output=True, timeout=10, check=False)
        reject(result.returncode != 0 or result.stdout.decode().strip() != expected, 'operator_source_changed')


def prepare(source_profile, inspection_file, output_directory, revision, *, plan_digest=None, write=False):
    check_operator(revision)
    profile, inspection, output = map(private_path, (source_profile, inspection_file, output_directory))
    reject(output.exists() or output.is_symlink(), 'existing_draft_requires_inspection')
    reject(any((parent / '.git').exists() for parent in output.parents)
        or output.is_relative_to('/home/acc-control/f30/state')
        or output.is_relative_to('/home/acc-control/first-experiment-github-capability-release')
        or output.is_relative_to('/home/acc-control/telegram-mobile-release'), 'new_non_live_directory_required')
    value, source_sha = read_json(profile, 16384)
    observed, inspection_sha = read_json(inspection, 65536)
    draft, summary = build_draft(IntegrationConfig.model_validate(value), observed, datetime.now(timezone.utc))
    scope = {'operator_revision': revision, 'source_profile': str(profile), 'inspection_file': str(inspection),
        'output_directory': str(output), 'source_sha256': source_sha, 'inspection_sha256': inspection_sha,
        'draft_profile_hash': summary['draft_profile_hash']}
    summary.update(operator_revision=revision, source_sha256=source_sha, inspection_sha256=inspection_sha,
                   plan_digest=digest(scope), files_created=False)
    if write:
        reject(plan_digest != summary['plan_digest'], 'exact_draft_plan_required')
        check_operator(revision)
        reject(read_json(profile, 16384)[1] != source_sha or read_json(inspection, 65536)[1] != inspection_sha,
               'input_changed_before_write')
        # Slow source/file inspection must not carry an expired observation into a new draft.
        build_draft(IntegrationConfig.model_validate(value), observed, datetime.now(timezone.utc))
        output.mkdir(mode=0o700)
        documents = {'profile.disabled.json': {**draft.model_dump(), 'credential_files': draft.credential_files},
                     'preparation.json': {**summary, 'files_created': True}}
        # Exclusive writes retain any partial result for inspection; never overwrite/retry it.
        for name, body in documents.items():
            fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(body, stream, sort_keys=True, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
        summary['files_created'] = True
    return summary


def main():
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid draft arguments; values not displayed\n')
    parser = Parser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'prepare'))
    for name in ('source-profile', 'inspection-file', 'output-directory', 'operator-revision'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--plan-digest')
    args = parser.parse_args()
    try:
        reject(args.action == 'plan' and args.plan_digest is not None, 'plan_digest_not_consumed_by_plan')
        result = prepare(args.source_profile, args.inspection_file, args.output_directory,
            args.operator_revision, plan_digest=args.plan_digest, write=args.action == 'prepare')
    except Exception as error:
        result = {'state': 'BLOCKED', 'error_code': str(error) if isinstance(error, DraftError) else 'draft_inputs_or_environment_invalid',
            'provider_calls': 0, 'paid_calls': 0, 'files_created': None if args.action == 'prepare' else False,
            'paid_recovery_authorized': False,
            'partial_output_may_require_inspection': args.action == 'prepare'}
    print(json.dumps(result, sort_keys=True))
    return 2 if result.get('state') == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
