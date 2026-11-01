"""Owner calendar drafts; provider synchronization is deliberately separate."""

import re
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from .models import Audit
from .store import Denied, digest

CREATED = 'owner_calendar_draft_created'
CONFIRMED = 'owner_calendar_draft_confirmed'
CANCELLED = 'owner_calendar_draft_cancelled'
EVENTS = (CREATED, CONFIRMED, CANCELLED)
MAX_DRAFTS = 500
MAX_RESULTS = 20


def _uuid(value, error='calendar_reference_invalid'):
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise Denied(error) from None
    if str(parsed) != value:
        raise Denied(error)
    return value


def _instant(value):
    if not isinstance(value, str) or len(value) > 40:
        raise Denied('calendar_draft_invalid')
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise Denied('calendar_draft_invalid') from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise Denied('calendar_draft_invalid')
    return result


def validate(document):
    """Validate the deterministic result of a future text/voice parser."""
    required = {'title', 'start', 'end', 'timezone', 'note', 'telegram_reminder_minutes'}
    if (not isinstance(document, dict) or set(document) != required
            or not isinstance(document['title'], str)
            or not 1 <= len(document['title'].strip()) <= 120
            or document['title'] != document['title'].strip()
            or not isinstance(document['note'], str) or len(document['note']) > 1000
            or not isinstance(document['timezone'], str) or len(document['timezone']) > 64
            or type(document['telegram_reminder_minutes']) is not int
            or not 5 <= document['telegram_reminder_minutes'] <= 1440):
        raise Denied('calendar_draft_invalid')
    try:
        zone = ZoneInfo(document['timezone'])
    except ZoneInfoNotFoundError:
        raise Denied('calendar_timezone_invalid') from None
    start, end = _instant(document['start']), _instant(document['end'])
    if (start >= end or end - start > timedelta(hours=24)
            or start.astimezone(zone).isoformat() != document['start']
            or end.astimezone(zone).isoformat() != document['end']):
        raise Denied('calendar_draft_invalid')
    return document


def _history(session):
    rows = session.scalars(select(Audit).where(
        Audit.event['kind'].as_string().in_(EVENTS),
        Audit.event['actor'].as_string() == 'owner',
    ).order_by(Audit.sequence).limit(MAX_DRAFTS * 3 + 1)).all()
    if len(rows) > MAX_DRAFTS * 3:
        raise Denied('calendar_history_limit')
    return rows


def _states(session):
    result = {}
    for row in _history(session):
        event = row.event
        draft_id = _uuid(event.get('draft_id'), 'calendar_history_invalid')
        if event['kind'] == CREATED:
            document = validate(event.get('document'))
            if (draft_id in result or event.get('document_hash') != digest(document)
                    or not re.fullmatch(r'[a-f0-9]{64}', event.get('source_hash', ''))):
                raise Denied('calendar_history_invalid')
            result[draft_id] = {'id': draft_id, 'state': 'DRAFT', 'version': 1,
                                'document': document, 'external_sync': False}
        else:
            current = result.get(draft_id)
            expected = 'CONFIRMED_LOCAL' if event['kind'] == CONFIRMED else 'CANCELLED'
            if (not current or current['state'] != 'DRAFT' or event.get('version') != 2
                    or event.get('document_hash') != digest(current['document'])):
                raise Denied('calendar_history_invalid')
            current.update(state=expected, version=2)
    return result


def create(store, role, document, operation_id, source_hash):
    """Create one local draft. No provider action or task is produced."""
    if role != 'owner':
        raise Denied('owner_required')
    document = validate(document)
    _uuid(operation_id, 'calendar_operation_invalid')
    if not isinstance(source_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', source_hash):
        raise Denied('calendar_source_invalid')
    fingerprint = digest({'document': document, 'source_hash': source_hash})
    with store.transaction() as session:
        store.check_audit(session)
        rows = _history(session)
        duplicate = next((row for row in rows if row.event.get('operation_id') == operation_id), None)
        if duplicate:
            if duplicate.event.get('input_hash') != fingerprint:
                raise Denied('calendar_idempotency_conflict')
            return _states(session)[duplicate.event['draft_id']]
        if sum(row.event['kind'] == CREATED for row in rows) >= MAX_DRAFTS:
            raise Denied('calendar_history_limit')
        draft_id = str(uuid4())
        store.audit(session, CREATED, 'owner', draft_id=draft_id, version=1,
                    document=document, document_hash=digest(document), source_hash=source_hash,
                    operation_id=operation_id, input_hash=fingerprint)
        return _states(session)[draft_id]


def decide(store, role, draft_id, expected_version, operation_id, confirm):
    """Record local confirmation/cancellation without authorizing Google access."""
    if role != 'owner':
        raise Denied('owner_required')
    _uuid(draft_id)
    _uuid(operation_id, 'calendar_operation_invalid')
    if type(expected_version) is not int or type(confirm) is not bool:
        raise Denied('calendar_decision_invalid')
    fingerprint = digest({'draft_id': draft_id, 'version': expected_version, 'confirm': confirm})
    with store.transaction() as session:
        store.check_audit(session)
        rows = _history(session)
        duplicate = next((row for row in rows if row.event.get('operation_id') == operation_id), None)
        if duplicate:
            if duplicate.event.get('input_hash') != fingerprint:
                raise Denied('calendar_idempotency_conflict')
            return _states(session)[draft_id]
        current = _states(session).get(draft_id)
        if not current or current['state'] != 'DRAFT' or current['version'] != expected_version:
            raise Denied('calendar_draft_stale_or_terminal')
        store.audit(session, CONFIRMED if confirm else CANCELLED, 'owner', draft_id=draft_id,
                    version=expected_version + 1, document_hash=digest(current['document']),
                    operation_id=operation_id, input_hash=fingerprint,
                    provider_action_created=False)
        return _states(session)[draft_id]


def list_drafts(store, role, limit=10):
    if role != 'owner':
        raise Denied('owner_required')
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise Denied('calendar_limit_invalid')
    with store.transaction() as session:
        store.check_audit(session)
        values = list(_states(session).values())
        return list(reversed(values[-limit:]))
