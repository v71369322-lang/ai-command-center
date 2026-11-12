"""Owner acceptance of pinned plan content. Never task, spending or execution approval."""
from datetime import datetime
from typing import Literal

from pydantic import Field
from sqlalchemy import select

from .models import Audit
from .project_inbox import owner
from .project_setup import binding as setup_binding, records as setup_records, review as setup_review
from .project_setup import read_locked as setup_read
from .request_plan_store import MAX_PROPOSALS, _records, read_locked as plan_read
from .request_planning import HEX, REQUEST, Strict, _context
from .store import Denied, canonical, digest

EVENT = 'saved_request_plan_content_accepted'
MAX_ACCEPTANCES = 100
FLAGS = {'execution_authorized': False, 'paid_calls_authorized': False,
         'task_created': False, 'coding_prepared': False, 'provider_evidence_verified': False,
         'external_checks_performed': False, 'publication_authorized': False}


class AcceptanceRequest(Strict):
    request_id: str = Field(pattern=REQUEST)
    expected_snapshot_digest: str = Field(pattern=HEX)


class Reference(Strict):
    schema_version: Literal[1] = 1
    scope: Literal['PLAN_CONTENT_ONLY'] = 'PLAN_CONTENT_ONLY'
    request_id: str = Field(pattern=REQUEST)
    request_fingerprint: str = Field(pattern=HEX)
    context_digest: str = Field(pattern=HEX)
    source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    control_epoch: int = Field(ge=0)
    assignment_version: int = Field(ge=1, le=1000)
    project_id: Literal['command-center'] = 'command-center'
    repository: Literal['v71369322-lang/ai-command-center'] = 'v71369322-lang/ai-command-center'
    declared_repository_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    setup_version: int = Field(ge=1, le=500)
    setup_digest: str = Field(pattern=HEX)
    plan_version: int = Field(ge=1, le=MAX_PROPOSALS)
    proposal_id: str = Field(pattern=HEX)
    plan_document_digest: str = Field(pattern=HEX)
    origin: Literal['owner_authored', 'owner_supplied_unverified']


def _current(store, session, request_id):
    context = _context(store, session, request_id)
    if context.project_id != 'command-center':
        raise Denied('plan_acceptance_command_center_only')
    plan = plan_read(store, session, request_id)
    setup = setup_read(store, session, 'command-center')
    if (plan['state'] != 'CURRENT' or plan['version'] != plan['latest_version']
            or plan['proposal']['disposition'] != 'ready_for_review' or plan['proposal']['questions']
            or setup['version'] == 0 or not setup['review']['ready_for_operator_review']):
        raise Denied('plan_acceptance_not_ready')
    event, document = _records(session)[plan['proposal_id']]
    reference = Reference(request_id=request_id, request_fingerprint=context.request_fingerprint,
        context_digest=context.binding, source_revision=context.source_revision,
        control_epoch=context.control_epoch, assignment_version=context.assignment_version,
        declared_repository_revision=setup['draft']['repository_revision'],
        setup_version=setup['version'], setup_digest=setup['draft_digest'],
        plan_version=plan['version'], proposal_id=plan['proposal_id'],
        plan_document_digest=event['document_digest'], origin=document.origin)
    return reference.model_dump(), plan['proposal']


def _history(store, session):
    rows = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)
                           .order_by(Audit.sequence).limit(MAX_ACCEPTANCES + 1)).all()
    if len(rows) > MAX_ACCEPTANCES:
        raise Denied('plan_acceptance_capacity')
    drafts = _records(session) if rows else {}
    # Verify setup history once under this Control transaction, not once per
    # acceptance receipt. This is local to the read, never a trusted-prefix cache.
    setups = setup_records(store, session)[2] if rows else {}
    result = {}
    for row in rows:
        try:
            event = row.event
            ref = Reference.model_validate(event['reference']).model_dump()
            pin = digest(ref)
            draft, document = drafts[ref['proposal_id']]
            setup = setups[('command-center', ref['setup_version'])]
            if (set(event) != {'kind', 'actor', 'task_id', 'time', 'revision', 'reference', 'snapshot_digest', 'flags'}
                    or event['actor'] != 'owner' or event['task_id'] is not None
                    or event['revision'] != ref['source_revision']
                    or event['snapshot_digest'] != pin or pin in result
                    or canonical(event['reference']) != canonical(ref)
                    or canonical(event['flags']) != canonical(FLAGS)
                    or datetime.fromisoformat(event['time']).tzinfo is None
                    or draft['document_digest'] != ref['plan_document_digest']
                    or draft['version'] != ref['plan_version']
                    or document.request_id != ref['request_id']
                    or document.context_digest != ref['context_digest']
                    or document.assignment_version != ref['assignment_version']
                    or document.revision != ref['source_revision']
                    or document.project_id != 'command-center' or document.origin != ref['origin']
                    or document.proposal.disposition != 'ready_for_review' or document.proposal.questions
                    or setup_binding('command-center', setup) != ref['setup_digest']
                    or setup['repository_revision'] != ref['declared_repository_revision']
                    or not setup_review(setup)['ready_for_operator_review']):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise Denied('plan_acceptance_integrity') from None
        result[pin] = {'reference': ref, 'snapshot_digest': pin, 'accepted_at': event['time'], **FLAGS}
    return result


def preview(store, role, request_id):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return preview_locked(store, session, request_id)


def preview_locked(store, session, request_id):
    """Trusted composition under an already checked F1 Control transaction."""
    _history(store, session)
    reference, proposal = _current(store, session, request_id)
    return {'reference': reference, 'snapshot_digest': digest(reference), 'proposal': proposal,
            'stored': False, **FLAGS}


def accept(store, role, request):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return accept_locked(store, session, request)


def accept_locked(store, session, request):
    """Trusted composition only; no public caller may supply a Session."""
    try:
        request = AcceptanceRequest.model_validate(request.model_dump() if isinstance(request, AcceptanceRequest) else request)
    except ValueError:
        raise Denied('plan_acceptance_request_invalid') from None
    history = _history(store, session)
    reference, _ = _current(store, session, request.request_id)
    pin = digest(reference)
    if pin != request.expected_snapshot_digest:
        raise Denied('plan_acceptance_snapshot_changed')
    if pin in history:
        return history[pin]
    if len(history) >= MAX_ACCEPTANCES:
        raise Denied('plan_acceptance_capacity')
    store.audit(session, EVENT, 'owner', reference=reference, snapshot_digest=pin, flags=FLAGS)
    return _history(store, session)[pin]


def read(store, role, request_id):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return read_locked(store, session, request_id)


def read_locked(store, session, request_id):
    context = _context(store, session, request_id)
    if context.project_id != 'command-center':
        raise Denied('plan_acceptance_command_center_only')
    records = [r for r in _history(store, session).values() if r['reference']['request_id'] == request_id]
    if not records:
        return {'state': 'MISSING', 'receipt': None, **FLAGS}
    receipt = records[-1]
    try:
        reference, _ = _current(store, session, request_id)
        current = digest(reference) == receipt['snapshot_digest']
    except Denied as error:
        if str(error) != 'plan_acceptance_not_ready':
            raise
        current = False
    return {'state': 'CURRENT' if current else 'STALE', 'receipt': receipt, **FLAGS}
