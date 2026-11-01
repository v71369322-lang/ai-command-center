"""Prepare bounded repair plans without starting an agent or publishing a branch."""

from .project_catalog import BY_ID
from .project_connections import statuses
from .project_inbox import checked_text, history as assignment_history
from .models import TelegramInbox
from .store import Denied, digest


def prepare_locked(store, session, request_id):
    row = session.get(TelegramInbox, request_id)
    if row is None:
        raise Denied('saved_request_not_found')
    text = checked_text(store, session, row)
    assignments, _ = assignment_history(session)
    assigned = assignments.get(request_id)
    if not assigned or assigned['request_fingerprint'] != row.fingerprint:
        raise Denied('project_assignment_required')
    project_id = assigned['project_id']
    if project_id is None:
        raise Denied('project_assignment_required')
    connection = statuses(session).get(project_id)
    if not connection:
        raise Denied('project_connection_required')
    plan = {'kind': 'project_repair_plan', 'project_id': project_id,
            'request_id': request_id, 'request_fingerprint': row.fingerprint,
            'assignment_version': assigned['version'], 'repository': connection['repository'],
            'repository_id': connection['repository_id'], 'base_sha': connection['baseline_sha'],
            'objective_hash': digest(text), 'stages': ['read_only_analysis', 'isolated_edit',
                'project_tests', 'independent_verification', 'draft_pr'],
            'publication': {'draft_pr': True, 'merge': False, 'deploy': False},
            'authority': {'execution': False, 'paid_ai': False, 'repository_write': False},
            'limits': {'max_changed_files': 20, 'max_repairs': 1, 'max_seconds': 900}}
    return plan | {'plan_hash': digest(plan), 'project_boundary': BY_ID[project_id]['boundary']}


def prepare(store, role, request_id):
    if role != 'owner':
        raise Denied('owner_required')
    with store.transaction() as session:
        store.check_audit(session)
        return prepare_locked(store, session, request_id)
