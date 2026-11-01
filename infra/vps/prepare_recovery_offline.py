"""One local inspection + disabled draft session. Never build, connect or deploy.

Real use needs separate owner authorization on brain1 for the exact operator and
bounded window. A timestamp is only the operator's assertion, not F1 consent.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import time

import prepare_first_recovery_profile as profile
from command_center.deployment import Engine, image_check, load_bundle, source_check
from command_center.deployment_integrations import _configuration
from command_center.deployment_profile import atomic_json, checksum
from command_center.local_docker import environment
from command_center.store import digest
from command_center.telegram_transport import private_read

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = Path('/home/acc-control/first-experiment-github-capability-release/integration-preparation/candidate')
STATE = Path('/home/acc-control/f30/state')
OUTPUT = Path('/home/acc-control/first-experiment-recovery-offline')
REVISION = '322186dc180257c618d8b159c78faa6e5bbf0b43'
BUNDLE = 'ac6462b47f69a3cbc967ac2c9dd62064d6b3dc7813503d34782e1dd1830d094d'
BROKER = 'acc-f23-runtime-broker-1'
SAFE_BLOCKERS = {'installed_source_changed', 'parent_requires_review', 'database_inspection_failed',
    'runtime_requires_review', 'runtime_inspection_failed', 'parent_container_present',
    'container_inspection_failed', 'parent_fence_unavailable', 'original_profile_changed',
    'profile_evidence_missing_or_expired', 'profile_inspection_failed', 'broker_environment_unavailable'}


class Blocked(Exception):
    pass


def require(condition, code):
    if not condition:
        raise Blocked(code)


def window(until):
    now = int(time.time())
    require(type(until) is int and now < until <= now + 3600, 'fresh_local_preparation_window_required')


def host_check():
    require(os.geteuid() == 1000 and socket.gethostname().split('.')[0] == 'brain1', 'dedicated_control_host_required')


@contextmanager
def predecessor_lock():
    fd = os.open(STATE / 'deployment.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(fd)
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid == os.geteuid()
            and not meta.st_mode & 0o077 and meta.st_nlink == 1, 'existing_private_deployment_lock_required')
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def predecessor():
    journal = json.loads(private_read(STATE / 'deployment.json', 32768))
    require(all(journal.get(k) == v for k, v in {'phase': 'VERIFIED', 'revision': REVISION,
        'bundle': BUNDLE, 'directory': str(ACTIVE)}.items()), 'verified_predecessor_changed')
    bundle = load_bundle(ACTIVE)
    m = bundle['manifest']
    require(checksum(bundle) == BUNDLE and m['revision'] == REVISION and m['data_root'] == str(STATE)
        and m['control_uid'] == 1000 and m['execution_uid'] == 1001, 'exact_active_bundle_required')
    source_check(m)
    binding = m.get('first_experiment', {})
    require(binding.get('telegram_readiness') is True and 'recovery' not in binding, 'original_first_binding_required')
    raw, config = _configuration(binding['config_file'], os.geteuid())  # Config only, never provider key files.
    require(hashlib.sha256(raw).hexdigest() == binding.get('config_sha256')
        and digest(config.model_dump()) == binding.get('profile_hash'), 'original_profile_pin_changed')
    return bundle, config, digest(journal)


def expected_mounts(bundle):
    service = bundle['compose']['services']['runtime-broker']
    mounts = {(v['source'], v['target'], not v.get('read_only', False)) for v in service['volumes']}
    for item in service.get('secrets', []):
        source = item if isinstance(item, str) else item['source']
        target = source if isinstance(item, str) else (item.get('target') or source)
        destination = target if target.startswith('/') else '/run/secrets/' + target
        mounts.add((bundle['compose']['secrets'][source]['file'], destination, False))
    return mounts


def broker_binding(engine, bundle, target=BROKER):
    rows = engine.json('inspect', target)
    require(isinstance(rows, list) and len(rows) == 1, 'exact_running_broker_required')
    row, m = rows[0], bundle['manifest']
    cfg, state, host = (row.get(k, {}) for k in ('Config', 'State', 'HostConfig'))
    labels = cfg.get('Labels') or {}
    require(row.get('Name') == '/' + BROKER and isinstance(row.get('Id'), str)
        and len(row['Id']) == 64 and all(c in '0123456789abcdef' for c in row['Id'])
        and row.get('Image') == m['images']['broker'] and state.get('Running') is True
        and state.get('Restarting') is False and host.get('Privileged') is False
        and host.get('ReadonlyRootfs') is True and cfg.get('WorkingDir') == '/app'
        and labels.get('com.docker.compose.project') == 'acc-f23'
        and labels.get('com.docker.compose.service') == 'runtime-broker', 'exact_running_broker_required')
    env = cfg.get('Env') or []
    for key, value in {'F1_SOURCE_REVISION': REVISION, 'PYTHONPATH': '/app/src',
        'F1_RUNTIME_MODE': 'rootless-required', 'F1_DB_USER': 'f1_runtime',
        'F2_INTEGRATION_CONFIG_FILE': '/run/f2/config.json',
        'F2_INTEGRATION_CONFIG_SHA256': m['first_experiment']['config_sha256']}.items():
        require([v for v in env if v.startswith(key + '=')] == [key + '=' + value], 'broker_environment_changed')
    require(not any(v.startswith(('PYTHONHOME=', 'PYTHONUSERBASE=')) for v in env), 'broker_environment_changed')
    allowed_tmpfs = {v.split(':', 1)[0] for v in bundle['compose']['services']['runtime-broker'].get('tmpfs', [])}
    require(set(host.get('Tmpfs') or {}) <= allowed_tmpfs
        and all(m.get('Target') in allowed_tmpfs for m in (host.get('Mounts') or []) if m.get('Type') == 'tmpfs'),
        'broker_mounts_changed')
    actual = set()
    for mount in row.get('Mounts', []):
        if mount.get('Type') == 'tmpfs' and mount.get('Destination') in allowed_tmpfs:
            continue
        require(mount.get('Type') == 'bind' and type(mount.get('RW')) is bool, 'broker_mounts_changed')
        actual.add((mount['Source'], mount['Destination'], mount['RW']))
    require(actual == expected_mounts(bundle), 'broker_mounts_changed')
    return row['Id']


def run_inspection(engine, container, program):
    # Exit2 is an expected blocked local report (e.g. expired profile evidence).
    # stderr and unexpected stdout are never written to a log or echoed.
    result = subprocess.run(['docker', '--host=' + engine.endpoint, 'exec', '-i', container, 'python', '-B'],
        env=environment(), input=program, capture_output=True, timeout=60, check=False)
    require(result.returncode in {0, 2} and len(result.stdout) <= 65536, 'inspection_process_failed')
    value = json.loads(result.stdout)
    require(isinstance(value, dict) and value.get('status') ==
        ('LOCAL_OBSERVATIONS_COMPLETE' if result.returncode == 0 else 'BLOCKED'), 'inspection_exit_contract_changed')
    return value


def minimal_report(value):
    # Persist only fields consumed and validated by build_draft. Ignore arbitrary
    # nested extras, stdout metadata and stderr, even from an unexpected process.
    keys = ('schema', 'task_id', 'checked_at_utc', 'scope', 'read_only', 'provider_credential_values_read',
        'response_text_printed', 'provider_calls', 'paid_calls', 'task_restarted', 'application_mutations_requested',
        'runtime_mutations_requested', 'token_issued', 'deployment_authorized', 'paid_recovery_authorized',
        'recovery_authority_verified', 'source_matches_installed', 'status', 'blockers')
    result = {k: value[k] for k in keys}
    sections = {
        'database': ('task_id', 'fence', 'state_failed', 'reason_matches', 'fixed_payload_matches', 'owner_matches',
            'attempts_is_one', 'synthetic_reserve_zero', 'failure_matches', 'grant_digest', 'grant_self_digest_matches',
            'grant_source_matches', 'grant_profile_hash', 'grant_mode_live', 'grant_budget_nano_rub', 'action_count',
            'openai_count', 'all_actions_closed', 'actual_nano_rub', 'reserved_nano_rub', 'saved_response_failure_matches',
            'audit_chain_verified', 'action_ledger_verified', 'recovery_authority_verified'),
        'runtime': ('audit_chain_verified', 'parent_run_done', 'parent_revision_matches', 'container_name_matches',
            'unresolved_runs', 'watchdog_fresh', 'worker_fresh'),
        'container': ('rootless_preflight_verified', 'parent_container_absent'),
        'profile': ('profile_hash', 'matches_original_grant')}
    for name, fields in sections.items():
        result[name] = {k: value[name][k] for k in fields}
    result['database']['actions'] = [{k: a[k] for k in ('kind', 'state', 'actual_nano_rub', 'reserved_nano_rub')}
                                     for a in value['database']['actions']]
    return result


def output_check(output):
    output = Path(output)
    parent = output.parent.lstat()
    require(output.is_absolute() and output.resolve() == output and not output.exists() and not output.is_symlink()
        and stat.S_ISDIR(parent.st_mode) and parent.st_uid == os.geteuid() and not parent.st_mode & 0o022
        and not output.is_relative_to(ROOT) and not output.is_relative_to(STATE)
        and not output.is_relative_to(ACTIVE.parent.parent)
        and not any((p / '.git').exists() for p in output.parents), 'new_private_workspace_required')
    return output


def prepare(revision, approved_until, *, output=OUTPUT, engine=None):
    host_check()
    window(approved_until)
    profile.check_operator(revision)
    output = output_check(output)
    receipt = {'schema': 1, 'state': 'OFFLINE_PREPARATION_INTENT', 'operator_revision': revision,
        'operator_asserted_until': approved_until, 'expected_previous': BUNDLE, 'expected_revision': REVISION,
        'provider_calls': 0, 'paid_calls': 0, 'token_issued': False, 'deployment_authorized': False,
        'paid_recovery_authorized': False, 'recovery_authority_verified': False}
    with predecessor_lock():
        bundle, config, journal = predecessor()
        engine = engine or Engine(1000)
        engine.preflight()
        image_check(engine, {'broker': bundle['manifest']['images']['broker']}, REVISION)
        container = broker_binding(engine, bundle)
        program = (ROOT / 'infra/vps/inspect_first_recovery.py').read_bytes()
        require(0 < len(program) <= 65536, 'inspection_program_size_invalid')
        profile.check_operator(revision)
        window(approved_until)
        output.mkdir(mode=0o700)
        receipt.update(state='INSPECTION_ATTEMPTED', broker_id=container,
                       inspection_program_sha256=hashlib.sha256(program).hexdigest())
        atomic_json(output / 'session.json', receipt)
        try:
            observed = run_inspection(engine, container, program)
            # Validate first, then minimize, then validate the exact object to be saved.
            profile.build_draft(config, observed, datetime.now(timezone.utc))
            observed = minimal_report(observed)
            profile.build_draft(config, observed, datetime.now(timezone.utc))
            window(approved_until)
            require(predecessor()[2] == journal and broker_binding(engine, bundle, container) == container,
                    'predecessor_changed_during_inspection')
            atomic_json(output / 'inspection.json', observed)
            receipt['state'] = 'DISABLED_DRAFT_PREPARATION_ATTEMPTED'
            atomic_json(output / 'session.json', receipt)
            args = (bundle['manifest']['first_experiment']['config_file'], str(output / 'inspection.json'),
                    str(output / 'draft'), revision)
            plan = profile.prepare(*args)
            window(approved_until)
            prepared = profile.prepare(*args, plan_digest=plan['plan_digest'], write=True)
            window(approved_until)
            require(predecessor()[2] == journal and broker_binding(engine, bundle, container) == container,
                    'predecessor_changed_during_preparation')
            receipt.update(state='RECOVERY_OFFLINE_DRAFT_PREPARED', draft_plan_digest=prepared['plan_digest'],
                draft_profile_hash=prepared['draft_profile_hash'], original_grant_digest=prepared['original_grant_digest'],
                prior_actual_nano_rub=prepared['prior_actual_nano_rub'],
                one_call_reservation_nano_rub=prepared['one_call_reservation_nano_rub'],
                cumulative_max_nano_rub=prepared['cumulative_max_nano_rub'], max_calls=1, max_repairs=0, draft_disabled=True)
            atomic_json(output / 'session.json', receipt)
            return receipt
        except Exception:
            # Keep intent/partial draft for inspection, never clean or replay it.
            receipt['failed_at'] = receipt['state']
            receipt['state'] = 'BLOCKED_REQUIRES_INSPECTION'
            raw_blockers = observed.get('blockers', []) if isinstance(locals().get('observed'), dict) else []
            raw_blockers = raw_blockers if isinstance(raw_blockers, list) else []
            receipt['inspection_blockers'] = [v for v in raw_blockers if isinstance(v, str) and v in SAFE_BLOCKERS]

            try:
                atomic_json(output / 'session.json', receipt)
            except OSError:
                pass  # Existing intent/pending file already prevents replay.
            raise


def main():
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid offline preparation arguments; values not displayed\n')
    parser = Parser(description=__doc__)
    parser.add_argument('--operator-revision', required=True)
    parser.add_argument('--approved-until', required=True, type=int)
    args = parser.parse_args()
    try:
        result = prepare(args.operator_revision, args.approved_until)
    except Exception as error:
        result = {'state': 'BLOCKED', 'error_code': str(error) if isinstance(error, Blocked) else 'offline_preparation_failed',
            'provider_calls': 0, 'paid_calls': 0, 'paid_recovery_authorized': False,
            'partial_output_may_require_inspection': True}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['state'] == 'RECOVERY_OFFLINE_DRAFT_PREPARED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
