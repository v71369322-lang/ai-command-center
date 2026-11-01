"""Owner-authored plans: existing audit storage, no provider envelope or authority."""
import re

from .project_inbox import owner
from .project_setup import read_locked as setup_read
from .request_plan_store import (EVENT, MAX_PROPOSALS, MAX_DOCUMENT_BYTES, OPERATION,
    ManualDocument, ManualRequest, _records, _screen, identity)
from .request_planning import Plan, _context
from .store import Denied, canonical, digest


def references(store, session, request_id):
    context = _context(store, session, request_id)
    if context.project_id is None:
        raise Denied('manual_plan_project_required')
    setup = setup_read(store, session, context.project_id)
    records = _records(session)
    version = sum(d.request_id == request_id for _, d in records.values())
    return context, setup, records, {'request_id': request_id, 'expected_context_digest': context.binding,
        'expected_assignment_version': context.assignment_version, 'expected_setup_version': setup['version'],
        'expected_setup_digest': setup['draft_digest'], 'expected_plan_version': version}


def checked(store, session, request):
    if not isinstance(request, ManualRequest):
        raise Denied('manual_plan_input_invalid')
    context, setup, records, current = references(store, session, request.request_id)
    if any(request.model_dump()[key] != value for key, value in current.items()):
        raise Denied('manual_plan_context_changed')
    proposal = Plan(context_digest=context.binding,
        disposition='needs_clarification' if request.draft.questions else 'ready_for_review',
        **request.draft.model_dump())
    return context, setup, records, proposal


def document(store, request, context, proposal, operation):
    result = ManualDocument(schema_version=2, request_id=context.request_id, context_digest=context.binding,
        project_id=context.project_id, assignment_version=context.assignment_version, revision=context.source_revision,
        proposal=proposal, setup_version=request.expected_setup_version, setup_digest=request.expected_setup_digest,
        operation_id=operation, input_digest=digest(request.model_dump()), origin='owner_authored',
        provider_evidence_verified=False, execution_authorized=False)
    _screen(store, result)
    if len(canonical(result.model_dump()).encode()) > MAX_DOCUMENT_BYTES:
        raise Denied('planning_draft_size')
    return result


def receipt(event):
    raw = event['document']
    return {'proposal_id': event['proposal_id'], 'request_id': raw['request_id'], 'version': event['version'],
            'scope': 'MANUAL_PLAN_DRAFT_ONLY',
            'operation_id': raw['operation_id'], 'context_digest': raw['context_digest'],
            'origin': 'owner_authored', 'stored': True, 'provider_evidence_verified': False,
            'execution_authorized': False, 'task_created': False, 'provider_called': False}


def preview(store, role, request):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        context, _, records, proposal = checked(store, session, request)
        if len(records) >= MAX_PROPOSALS:
            raise Denied('planning_draft_capacity')
        document(store, request, context, proposal, '00000000-0000-4000-8000-000000000000')
        return {'scope': 'MANUAL_PLAN_DRAFT_ONLY', 'request_id': request.request_id,
                'proposal': proposal.model_dump(), 'preview_digest': digest(request.model_dump()),
                'stored': False, 'provider_called': False, 'execution_authorized': False, 'task_created': False}


def save(store, role, request, operation_id, *, _scope_installer=None):
    owner(role)
    if not isinstance(request, ManualRequest) or not isinstance(operation_id, str) or not re.fullmatch(OPERATION, operation_id):
        raise Denied('manual_plan_input_invalid')
    with store.transaction() as session:
        store.check_audit(session)
        records = _records(session)
        pid = identity({'origin': 'owner_authored', 'operation_id': operation_id})
        prior = records.get(pid)
        if prior:
            event, stored = prior
            _screen(store, stored)
            if not isinstance(stored, ManualDocument) or stored.input_digest != digest(request.model_dump()):
                raise Denied('manual_plan_idempotency_conflict')
        else:
            context, _, records, proposal = checked(store, session, request)
            if len(records) >= MAX_PROPOSALS:
                raise Denied('planning_draft_capacity')
            value = document(store, request, context, proposal, operation_id)
            raw = value.model_dump()
            event = {'proposal_id': pid, 'request_id': request.request_id,
                     'version': request.expected_plan_version + 1, 'document': raw, 'document_digest': digest(raw)}
            store.audit(session, EVENT, 'owner', **event)
        result = receipt(event)
        if _scope_installer:
            _scope_installer(session, result)
        return result
