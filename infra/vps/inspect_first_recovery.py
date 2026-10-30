"""Fixed, local read-only recovery inspection inside the installed broker.

Run on a real host only after separate authorization. No task creation, grant,
provider request, token refresh, container mutation or runtime reconciliation.
Compatible with installed322186d: recovery authority is checked by the new
application later, never granted by this diagnostic.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from command_center.coding.first_experiment import MODEL, REQUIRED, task_payload
from command_center.coding.gateway import Gateway
from command_center.coding.http_contract import decode_response
from command_center.coding.integration_config import IntegrationConfig
from command_center.config import Settings
from command_center.models import ExternalAction, ExternalGrant, Task
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeBackend, RuntimeLimits
from command_center.store import Store, digest
from command_center.worker import Runner

TASK_ID = '938e838d-54d4-470d-ad71-5c6a49a42c7d'
EXPECTED_SOURCE = '322186dc180257c618d8b159c78faa6e5bbf0b43'
LEDGER = '/var/lib/f1-runtime/ledger.sqlite'
ACTION_STATES = {'INTENT', 'UNCERTAIN', 'SETTLED', 'COMPLETE'}


def sha(value):
    return value if isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) else None


def database_snapshot(store):
    # Do NOT use Store.transaction(): its SELECT FOR UPDATE is a write lock.
    with Session(store.engine) as session, session.begin():
        session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        store.check_audit(session)
        task, grant = session.get(Task, TASK_ID), session.get(ExternalGrant, TASK_ID)
        if task is None or grant is None:
            raise ValueError('parent_missing')
        rows = session.scalars(select(ExternalAction).where(ExternalAction.task_id == TASK_ID)
                               .order_by(ExternalAction.id).limit(65)).all()
        if len(rows) > 64:
            raise ValueError('action_limit')
        Gateway.check_ledger(session, rows)
        doc = grant.document
        evidence = task.coding_evidence or {}
        source_failure = False
        ai = [row for row in rows if row.kind == 'openai']
        if len(ai) == 1 and ai[0].state == 'COMPLETE':
            try:
                decode_response(ai[0].evidence.get('response'), MODEL)
            except ValueError as error:
                source_failure = str(error) == 'synthetic_language_scope_violation'
            except Exception:
                pass  # Provider text, exception text and model source never cross this boundary.
        return {'task_id': TASK_ID, 'fence': task.fence,
            'state_failed': task.state == 'FAILED', 'reason_matches': task.reason == 'external_coding_blocked',
            'fixed_payload_matches': task.payload == task_payload() and task.payload_hash == digest(task_payload()),
            'owner_matches': task.owner_role == 'owner', 'attempts_is_one': task.attempts == 1,
            'synthetic_reserve_zero': task.reserved == 0,
            'failure_matches': evidence.get('stage') == 'external_stopped'
                and evidence.get('failure') == 'provider_or_verifier_contract_rejected',
            'grant_digest': sha(grant.digest), 'grant_self_digest_matches': digest(doc) == grant.digest,
            'grant_source_matches': doc.get('revision') == EXPECTED_SOURCE,
            'grant_profile_hash': sha(doc.get('config_hash')), 'grant_mode_live': doc.get('mode') == 'live',
            'grant_budget_nano_rub': doc.get('budget') if type(doc.get('budget')) is int else None,
            'action_count': len(rows), 'openai_count': len(ai),
            'all_actions_closed': all(row.state == 'COMPLETE' and row.reserved == 0 for row in rows),
            'actual_nano_rub': sum(row.actual for row in rows),
            'reserved_nano_rub': sum(row.reserved for row in rows),
            'actions': [{'kind': row.kind if row.kind in {'openai', 'github', 'github_git'} else 'UNEXPECTED',
                         'state': row.state if row.state in ACTION_STATES else 'UNEXPECTED',
                         'actual_nano_rub': row.actual, 'reserved_nano_rub': row.reserved} for row in rows],
            'saved_response_failure_matches': source_failure,
            'audit_chain_verified': True, 'action_ledger_verified': True,
            'recovery_authority_verified': False}


@contextmanager
def read_only_ledger(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('runtime_path')
    # No constructor: RuntimeLedger.__init__ creates/migrates files. Reject WAL
    # before sqlite opens it, avoiding creation of shared-memory sidecar files.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_mode & 0o077
                or meta.st_uid != os.geteuid() or not 100 <= meta.st_size <= 32 * 2**20):
            raise ValueError('runtime_file')
        header = stream.read(100)
        if header[:16] != b'SQLite format 3\0' or header[18:20] != b'\x01\x01':
            raise ValueError('runtime_read_only_journal_unsupported')
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3, isolation_level=None) as db:
            if path.stat().st_ino != meta.st_ino or path.stat().st_dev != meta.st_dev:
                raise ValueError('runtime_file_changed')
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            class View(RuntimeLedger):
                def __init__(self):
                    pass

                @contextmanager
                def tx(self):
                    yield db
            yield View()
            db.rollback()


def runtime_snapshot(path, fence):
    limits = RuntimeLimits.load()
    with read_only_ledger(path) as view:
        chain = view.verify()
        row = view.get(TASK_ID, fence)
        name = Runner.name({'id': TASK_ID, 'fence': fence})
        result = {'audit_chain_verified': True, 'audit_head': chain,
            'parent_run_done': row['phase'] == 'DONE', 'parent_revision_matches': row['revision'] == EXPECTED_SOURCE,
            'container_name_matches': row['name'] == name, 'unresolved_runs': len(view.runs()),
            'watchdog_fresh': view.watchdog_ready(limits.watchdog_seconds),
            'worker_fresh': view.worker_fresh(EXPECTED_SOURCE, limits.heartbeat_seconds)}
    return result


def container_snapshot(backend, fence):
    if backend.mode != 'rootless-required':
        raise ValueError('rootless_mode_required')
    health = backend.preflight()  # Existing local Unix socket + rootless/cgroup/systemd checks.
    if health.get('rootless_verified') is not True:
        raise ValueError('rootless_unverified')
    name = Runner.name({'id': TASK_ID, 'fence': fence})
    result = backend.call('ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.Names}}')
    if result.returncode or len(result.stdout) > 1024:
        raise ValueError('container_list_failed')
    names = result.stdout.decode().splitlines()
    if names not in ([], [name]):
        raise ValueError('container_list_unexpected')
    return {'rootless_preflight_verified': True, 'parent_container_absent': not names}


def inspect(store, *, ledger_path=LEDGER, backend=None, config_loader=IntegrationConfig.load, now=None):
    now = now or datetime.now(timezone.utc)
    report = {'schema': 1, 'task_id': TASK_ID, 'checked_at_utc': now.isoformat(),
        'scope': 'fixed_parent_local_read_only', 'read_only': True, 'provider_credential_values_read': False,
        'response_text_printed': False, 'provider_calls': 0, 'paid_calls': 0,
        'task_restarted': False, 'application_mutations_requested': False, 'runtime_mutations_requested': False,
        'token_issued': False, 'deployment_authorized': False, 'paid_recovery_authorized': False,
        'recovery_authority_verified': False, 'source_matches_installed': store.settings.source_revision == EXPECTED_SOURCE}
    blockers = []
    if not report['source_matches_installed']:
        blockers.append('installed_source_changed')
    try:
        report['database'] = db = database_snapshot(store)
        flags = ('state_failed', 'reason_matches', 'fixed_payload_matches', 'owner_matches', 'attempts_is_one',
                 'synthetic_reserve_zero', 'failure_matches', 'grant_self_digest_matches',
                 'grant_source_matches', 'grant_mode_live', 'all_actions_closed', 'saved_response_failure_matches')
        if not all(db[key] for key in flags) or db['openai_count'] != 1:
            blockers.append('parent_requires_review')
    except Exception:
        blockers.append('database_inspection_failed')
    db = report.get('database', {})
    fence = db.get('fence')
    if type(fence) is int and 0 < fence < 2**63:
        try:
            report['runtime'] = runtime = runtime_snapshot(ledger_path, fence)
            if not all(runtime[key] for key in ('parent_run_done', 'parent_revision_matches',
                       'container_name_matches', 'watchdog_fresh', 'worker_fresh')) or runtime['unresolved_runs']:
                blockers.append('runtime_requires_review')
        except Exception:
            blockers.append('runtime_inspection_failed')
        try:
            report['container'] = container = container_snapshot(backend or RuntimeBackend(), fence)
            if not container['parent_container_absent']:
                blockers.append('parent_container_present')
        except Exception:
            blockers.append('container_inspection_failed')
    else:
        blockers.append('parent_fence_unavailable')
    try:
        config = config_loader()
        report['profile'] = {'profile_hash': digest(config.model_dump()),
            'matches_original_grant': digest(config.model_dump()) == db.get('grant_profile_hash'),
            'evidence_current': {key: bool(config.first_experiment and key in config.first_experiment.evidence
                and config.first_experiment.evidence[key].current(now)) for key in REQUIRED},
            'token_validity_verified': False, 'provider_access_verified': False}
        if not report['profile']['matches_original_grant']:
            blockers.append('original_profile_changed')
        if not all(report['profile']['evidence_current'].values()):
            blockers.append('profile_evidence_missing_or_expired')
    except Exception:
        blockers.append('profile_inspection_failed')
    report.update(status='BLOCKED' if blockers else 'LOCAL_OBSERVATIONS_COMPLETE', blockers=sorted(set(blockers)),
        next_step='review_fresh_build_token_profile_and_exact_approvals')
    return report


def main():
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid inspection arguments; values not displayed\n')
    Parser(description=__doc__).parse_args()
    store = None
    try:
        store = Store(Settings.load(identities_required=False))
        result = inspect(store)
    except Exception:
        result = {'status': 'BLOCKED', 'blockers': ['broker_environment_unavailable'],
                  'provider_calls': 0, 'paid_calls': 0, 'paid_recovery_authorized': False,
                  'response_text_printed': False}
    finally:
        if store is not None:
            store.engine.dispose()
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'LOCAL_OBSERVATIONS_COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
