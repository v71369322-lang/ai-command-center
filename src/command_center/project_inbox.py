"""Project labels for saved owner requests, never execution grants."""
import re

from sqlalchemy import select

from .models import Audit, TelegramInbox
from .store import Denied, digest
from .telegram_requests import captured_text
from .project_catalog import PROJECTS as CATALOG, IDS

PROJECTS = tuple((item['id'], item['label']) for item in CATALOG)
EVENT = 'project_request_classified'
MAX_CHANGES = 1000


def owner(role):
    if role != 'owner':
        raise Denied('owner_required')


def history(session):
    events = session.execute(select(Audit).where(Audit.event['kind'].as_string() == EVENT)
                             .order_by(Audit.sequence).limit(MAX_CHANGES + 1)).scalars().all()
    if len(events) > MAX_CHANGES:
        raise Denied('project_assignment_history_limit')
    latest, operations = {}, {}
    for record in events:
        event = record.event
        if not {'request_id', 'project_id', 'request_fingerprint', 'version', 'operation_id', 'input_hash'} <= set(event):
            raise Denied('project_assignment_history_invalid')
        rid, operation = event.get('request_id'), event.get('operation_id')
        if (not isinstance(rid, str) or not re.fullmatch(r'[a-f0-9]{64}:[0-9]{1,16}', rid)
                or event.get('project_id') is not None and (
                    not isinstance(event['project_id'], str) or event['project_id'] not in IDS)):
            raise Denied('project_assignment_history_invalid')
        previous = latest.get(rid)
        if (event.get('actor') != 'owner'
                or type(event.get('version')) is not int or event['version'] != (previous['version'] if previous else 0) + 1
                or not isinstance(operation, str) or not re.fullmatch(r'[a-f0-9-]{36}', operation)
                or operation in operations or not re.fullmatch(r'[a-f0-9]{64}', str(event.get('request_fingerprint')))
                or event.get('input_hash') != digest({'request_id': rid, 'project_id': event.get('project_id'),
                                                     'expected_version': event['version'] - 1})):
            raise Denied('project_assignment_history_invalid')
        latest[rid], operations[operation] = event, event
    return latest, operations


def checked_text(store, session, row):
    value = captured_text(session, row)
    check_content(store, value)
    return value


def check_content(store, value):
    """Shared saved-request/proposal screen, not a universal secret detector."""
    known = [*store.settings.identities.values(), store.settings.redis_password, store.settings.database_url.password]
    if (any(secret and secret in value for secret in known)
            or re.search(r'PRIVATE KEY|\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\b[0-9]{6,20}:[A-Za-z0-9_-]{30,128}', value)):
        raise Denied('project_request_sensitive_content')


def inbox(store, role, project='all'):
    owner(role)
    if project not in IDS | {'all', 'unassigned'}:
        raise Denied('unknown_project')
    with store.transaction() as session:
        store.check_audit(session)
        latest, _ = history(session)
        rows = session.execute(select(TelegramInbox).where(TelegramInbox.state == 'NEEDS_PLANNING')
                               .order_by(TelegramInbox.created_at.desc(), TelegramInbox.id.desc()).limit(1001)).scalars().all()
        if len(rows) > 1000:
            raise Denied('project_request_capacity')
        counts = dict.fromkeys(['unassigned', *[key for key, _ in PROJECTS]], 0)
        result = []
        for row in rows:
            value = checked_text(store, session, row)
            assigned = latest.get(row.id)
            if assigned and assigned['request_fingerprint'] != row.fingerprint:
                raise Denied('project_request_binding_changed')
            pid = assigned['project_id'] if assigned else None
            key = pid or 'unassigned'
            counts[key] += 1
            if (project == 'all' or key == project) and len(result) < 50:
                result.append({'id': row.id, 'text': value, 'state': 'NEEDS_PLANNING', 'project_id': pid,
                               'assignment_version': assigned['version'] if assigned else 0})
        from .project_connections import statuses
        connections = statuses(session)
        return {'projects': [{'id': key, 'label': label, 'execution_connected': False,
                              'connection_state': connections.get(key, {}).get('state', 'DISCONNECTED')}
                             for key, label in PROJECTS],
                'requests': result, 'counts': counts, 'total_pending': len(rows), 'filter': project,
                'ai_planning_connected': False}


def classify(store, role, request_id, project_id, expected_version, operation_id, *, _scope_installer=None):
    owner(role)
    if project_id is not None and (not isinstance(project_id, str) or project_id not in IDS):
        raise Denied('unknown_project')
    if type(expected_version) is not int or not 0 <= expected_version <= 1000:
        raise Denied('invalid_assignment_version')
    with store.transaction() as session:
        store.check_audit(session)
        row = session.get(TelegramInbox, request_id)
        if row is None:
            raise Denied('saved_request_not_found')
        checked_text(store, session, row)
        latest, operations = history(session)
        fingerprint = digest({'request_id': request_id, 'project_id': project_id, 'expected_version': expected_version})
        previous = operations.get(operation_id)
        if previous:
            if previous['input_hash'] != fingerprint or previous['request_fingerprint'] != row.fingerprint:
                raise Denied('project_assignment_idempotency_conflict')
            if _scope_installer:
                _scope_installer(session, previous)
            return receipt(previous)
        current = latest.get(row.id)
        if current and current['request_fingerprint'] != row.fingerprint:
            raise Denied('project_request_binding_changed')
        if expected_version != (current['version'] if current else 0):
            raise Denied('project_assignment_stale_version')
        if len(operations) >= MAX_CHANGES:
            raise Denied('project_assignment_history_limit')
        event = {'request_id': row.id, 'request_fingerprint': row.fingerprint, 'project_id': project_id,
                 'version': expected_version + 1, 'operation_id': operation_id, 'input_hash': fingerprint}
        store.audit(session, EVENT, 'owner', **event)
        if _scope_installer:
            _scope_installer(session, event)
        return receipt(event)


def receipt(event):
    return {key: event[key] for key in ('request_id', 'project_id', 'version', 'operation_id')} | {'execution_started': False}
