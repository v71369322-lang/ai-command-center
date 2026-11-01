"""Durable Google Calendar synchronization state without credential access."""

import re
from uuid import UUID

from sqlalchemy import select

from .calendar_drafts import get_draft_locked
from .google_calendar_contract import insert_request, reconciliation_request, verify_event
from .models import Audit
from .store import Denied, digest

BINDING = 'owner_google_calendar_binding_changed'
PREPARED = 'google_calendar_sync_prepared'
UNKNOWN = 'google_calendar_sync_unknown'
SYNCED = 'google_calendar_sync_completed'
REJECTED = 'google_calendar_sync_rejected'
SYNC_EVENTS = (PREPARED, UNKNOWN, SYNCED, REJECTED)
MAX_BINDINGS = 100
MAX_SYNCS = 500


def _uuid(value, error):
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise Denied(error) from None
    if str(parsed) != value:
        raise Denied(error)
    return value


def _bindings(session):
    rows = session.scalars(select(Audit).where(
        Audit.event['kind'].as_string() == BINDING,
        Audit.event['actor'].as_string() == 'owner').order_by(Audit.sequence).limit(MAX_BINDINGS + 1)).all()
    if len(rows) > MAX_BINDINGS:
        raise Denied('google_calendar_binding_history_limit')
    return rows


def _validate_binding(document):
    if (not isinstance(document, dict)
            or set(document) != {'enabled', 'calendar_id', 'credential_fingerprint'}
            or type(document['enabled']) is not bool
            or not isinstance(document['calendar_id'], str) or not 1 <= len(document['calendar_id']) <= 256
            or any(char in document['calendar_id'] for char in '\r\n\x00')
            or not isinstance(document['credential_fingerprint'], str)
            or not re.fullmatch(r'[a-f0-9]{64}', document['credential_fingerprint'])):
        raise Denied('google_calendar_binding_invalid')
    return document


def current_binding(session):
    rows = _bindings(session)
    if not rows:
        return {'configured': False, 'enabled': False, 'version': 0}
    event = rows[-1].event
    document = _validate_binding(event.get('binding'))
    if event.get('version') != len(rows) or event.get('binding_hash') != digest(document):
        raise Denied('google_calendar_binding_history_invalid')
    return {'configured': True, 'version': event['version'], **document}


def configure_binding(store, role, document, expected_version, operation_id):
    """Store only non-secret binding metadata; OAuth credentials remain external."""
    if role != 'owner':
        raise Denied('owner_required')
    document = _validate_binding(document)
    _uuid(operation_id, 'google_calendar_operation_invalid')
    fingerprint = digest({'binding': document, 'expected_version': expected_version})
    with store.transaction() as session:
        store.check_audit(session)
        rows = _bindings(session)
        duplicate = next((row for row in rows if row.event.get('operation_id') == operation_id), None)
        if duplicate:
            if duplicate.event.get('input_hash') != fingerprint:
                raise Denied('google_calendar_idempotency_conflict')
            return current_binding(session)
        state = current_binding(session)
        if type(expected_version) is not int or state['version'] != expected_version:
            raise Denied('google_calendar_binding_stale_version')
        store.audit(session, BINDING, 'owner', version=expected_version + 1, binding=document,
                    binding_hash=digest(document), operation_id=operation_id, input_hash=fingerprint,
                    credential_value_stored=False)
        return {'configured': True, 'version': expected_version + 1, **document}


def _sync_rows(session, draft_id=None):
    query = select(Audit).where(Audit.event['kind'].as_string().in_(SYNC_EVENTS))
    if draft_id is not None:
        query = query.where(Audit.event['draft_id'].as_string() == draft_id)
    rows = session.scalars(query.order_by(Audit.sequence).limit(MAX_SYNCS + 1)).all()
    if len(rows) > MAX_SYNCS:
        raise Denied('google_calendar_sync_history_limit')
    return rows


def sync_state(session, draft_id):
    _uuid(draft_id, 'calendar_reference_invalid')
    rows = _sync_rows(session, draft_id)
    if not rows:
        return {'state': 'NOT_PREPARED', 'draft_id': draft_id}
    first = rows[0].event
    if (first['kind'] != PREPARED or not re.fullmatch(r'[a-f0-9]{64}', first.get('request_hash', ''))
            or not re.fullmatch(r'[a-f0-9]{64}', first.get('document_hash', ''))
            or type(first.get('binding_version')) is not int):
        raise Denied('google_calendar_sync_history_invalid')
    state = {'state': 'PREPARED', 'draft_id': draft_id, 'request_hash': first['request_hash'],
             'document_hash': first['document_hash'], 'binding_version': first['binding_version']}
    for row in rows[1:]:
        event = row.event
        if event.get('request_hash') != state['request_hash']:
            raise Denied('google_calendar_sync_history_invalid')
        if event['kind'] == UNKNOWN and state['state'] == 'PREPARED':
            state['state'] = 'UNKNOWN'
        elif event['kind'] == SYNCED and state['state'] in {'PREPARED', 'UNKNOWN'}:
            if (not re.fullmatch(r'[a-z0-9]{5,1024}', event.get('event_id', ''))
                    or not isinstance(event.get('etag_hash'), str)
                    or not re.fullmatch(r'[a-f0-9]{64}', event['etag_hash'])):
                raise Denied('google_calendar_sync_history_invalid')
            state.update(state='SYNCED', event_id=event['event_id'])
        elif event['kind'] == REJECTED and state['state'] == 'PREPARED':
            if not re.fullmatch(r'[a-z0-9_]{3,80}', event.get('error_code', '')):
                raise Denied('google_calendar_sync_history_invalid')
            state.update(state='FAILED', error_code=event['error_code'])
        else:
            raise Denied('google_calendar_sync_history_invalid')
    return state


def prepare_sync(store, role, draft_id, operation_id):
    """Prepare one exact provider request; does not call Google or read a token."""
    if role != 'owner':
        raise Denied('owner_required')
    _uuid(draft_id, 'calendar_reference_invalid')
    _uuid(operation_id, 'google_calendar_operation_invalid')
    with store.transaction() as session:
        store.check_audit(session)
        duplicate = next((row for row in _sync_rows(session) if row.event.get('operation_id') == operation_id), None)
        if duplicate:
            if duplicate.event.get('draft_id') != draft_id:
                raise Denied('google_calendar_idempotency_conflict')
            return sync_state(session, draft_id)
        if sync_state(session, draft_id)['state'] != 'NOT_PREPARED':
            raise Denied('google_calendar_sync_already_started')
        draft = get_draft_locked(session, draft_id)
        binding = current_binding(session)
        if draft['state'] != 'CONFIRMED_LOCAL' or not binding.get('enabled'):
            raise Denied('google_calendar_sync_not_eligible')
        request = insert_request(binding['calendar_id'], draft_id, draft['document'])
        request_hash = digest(request)
        store.audit(session, PREPARED, 'owner', draft_id=draft_id, operation_id=operation_id,
                    request_hash=request_hash, document_hash=request['document_hash'],
                    binding_version=binding['version'], binding_hash=digest({
                        key: binding[key] for key in ('enabled', 'calendar_id', 'credential_fingerprint')}),
                    external_call_performed=False, credential_value_read=False)
        return sync_state(session, draft_id)


def record_outcome(store, draft_id, request_hash, operation_id, outcome, response=None, error_code=None):
    """Record publisher evidence; UNKNOWN requires reconciliation before any retry."""
    _uuid(draft_id, 'calendar_reference_invalid')
    _uuid(operation_id, 'google_calendar_operation_invalid')
    if outcome not in {'unknown', 'synced', 'failed'} or not re.fullmatch(r'[a-f0-9]{64}', request_hash or ''):
        raise Denied('google_calendar_outcome_invalid')
    with store.transaction() as session:
        store.check_audit(session)
        duplicate = next((row for row in _sync_rows(session) if row.event.get('operation_id') == operation_id), None)
        if duplicate:
            if (duplicate.event.get('draft_id') != draft_id
                    or duplicate.event.get('request_hash') != request_hash):
                raise Denied('google_calendar_idempotency_conflict')
            return sync_state(session, draft_id)
        state = sync_state(session, draft_id)
        if state['state'] not in {'PREPARED', 'UNKNOWN'} or state['request_hash'] != request_hash:
            raise Denied('google_calendar_outcome_stale')
        if outcome == 'unknown':
            if state['state'] != 'PREPARED' or response is not None or error_code is not None:
                raise Denied('google_calendar_outcome_stale')
            store.audit(session, UNKNOWN, 'calendar_publisher', draft_id=draft_id,
                        request_hash=request_hash, operation_id=operation_id,
                        retry_permitted=False, reconciliation_required=True)
        elif outcome == 'synced':
            if error_code is not None:
                raise Denied('google_calendar_outcome_invalid')
            draft = get_draft_locked(session, draft_id)
            verified = verify_event(response, draft_id, draft['document'])
            store.audit(session, SYNCED, 'calendar_publisher', draft_id=draft_id,
                        request_hash=request_hash, operation_id=operation_id,
                        event_id=verified['event_id'], etag_hash=digest(response['etag']),
                        document_hash=verified['document_hash'])
        else:
            if (state['state'] != 'PREPARED' or response is not None
                    or not isinstance(error_code, str) or not re.fullmatch(r'[a-z0-9_]{3,80}', error_code)):
                raise Denied('google_calendar_outcome_invalid')
            store.audit(session, REJECTED, 'calendar_publisher', draft_id=draft_id,
                        request_hash=request_hash, operation_id=operation_id,
                        error_code=error_code, retry_permitted=False)
        return sync_state(session, draft_id)


def reconciliation_plan(store, role, draft_id):
    if role != 'owner':
        raise Denied('owner_required')
    with store.transaction() as session:
        store.check_audit(session)
        state = sync_state(session, draft_id)
        binding = current_binding(session)
        if state['state'] != 'UNKNOWN' or not binding.get('enabled'):
            raise Denied('google_calendar_reconciliation_not_required')
        return {'request': reconciliation_request(binding['calendar_id'], draft_id),
                'request_hash': state['request_hash'], 'external_call_performed': False}


def publication_plan(store, draft_id):
    """Reconstruct the exact prepared request without reading OAuth credentials."""
    with store.transaction() as session:
        store.check_audit(session)
        state = sync_state(session, draft_id)
        binding = current_binding(session)
        draft = get_draft_locked(session, draft_id)
        if state['state'] != 'PREPARED' or not binding.get('enabled'):
            raise Denied('google_calendar_publication_not_prepared')
        request = insert_request(binding['calendar_id'], draft_id, draft['document'])
        if (state['binding_version'] != binding['version'] or state['document_hash'] != digest(draft['document'])
                or state['request_hash'] != digest(request)):
            raise Denied('google_calendar_publication_context_changed')
        return {'request': request, 'request_hash': state['request_hash'], 'draft_id': draft_id}
