"""Bounded owner-supplied advisory drafts in the existing append-only F1 audit."""
from typing import Literal

from pydantic import Field, ValidationError
from sqlalchemy import select

from .coding.http_contract import Usage
from .models import Audit
from .project_inbox import check_content, owner
from .request_planning import HEX, REQUEST, Plan, PlanningContext, Strict, _context, _review_response, limits
from .store import Denied, canonical, digest

EVENT = 'saved_request_plan_draft'
MAX_PROPOSALS = 100
MAX_DOCUMENT_BYTES = 32768


class Document(Strict):
    schema_version: Literal[1]
    request_id: str = Field(pattern=REQUEST)
    context_digest: str = Field(pattern=HEX)
    project_id: Literal['command-center', 'vanilla-sugar', 'lnauto', 'capital-lab'] | None
    assignment_version: int = Field(ge=0, le=1000)
    revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    proposal: Plan
    model: str = Field(pattern=r'^[A-Za-z0-9._:-]{1,100}$')
    response_id: str = Field(pattern=r'^resp_[A-Za-z0-9_-]{1,128}$')
    usage: Usage
    context_tokens: int
    max_output_tokens: int
    origin: Literal['owner_supplied_unverified']
    provider_evidence_verified: Literal[False]
    execution_authorized: Literal[False]


def identity(document):
    return digest({key: document[key] for key in ('request_id', 'context_digest', 'response_id', 'origin')})


def _records(session):
    rows = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)
                           .order_by(Audit.sequence).limit(MAX_PROPOSALS + 1)).all()
    if len(rows) > MAX_PROPOSALS:
        raise Denied('planning_draft_capacity')
    result = {}
    versions = {}
    for row in rows:
        event = row.event
        raw = event.get('document')
        try:
            if not isinstance(raw, dict) or len(canonical(raw).encode()) > MAX_DOCUMENT_BYTES:
                raise ValueError()
            document = Document.model_validate(raw)
            normalized = document.model_dump()
            limits(document.model, document.context_tokens, document.max_output_tokens)
            usage = document.usage
            if (canonical(normalized) != canonical(raw) or event.get('actor') != 'owner'
                    or event.get('task_id') is not None or event.get('revision') != document.revision
                    or event.get('request_id') != document.request_id
                    or event.get('document_digest') != digest(raw)
                    or event.get('proposal_id') != identity(raw) or event['proposal_id'] in result
                    or type(event.get('version')) is not int
                    or event['version'] != versions.get(document.request_id, 0) + 1
                    or document.proposal.context_digest != document.context_digest
                    or document.project_id is None and not document.proposal.questions
                    or usage.total_tokens != usage.input_tokens + usage.output_tokens
                    or usage.input_tokens > document.context_tokens or usage.output_tokens > document.max_output_tokens):
                raise ValueError()
        except (Denied, ValueError, KeyError, TypeError):
            raise Denied('planning_draft_integrity') from None
        result[event['proposal_id']] = (event, document)
        versions[document.request_id] = event['version']
    return result


def _screen(store, document):
    plan = document.proposal
    for value in [document.model, document.response_id, plan.summary, *plan.questions,
                  *[value for step in plan.steps for value in [step.description, *step.acceptance]]]:
        try:
            if '\x00' in value:
                raise ValueError()
            value.encode('utf-8')
        except ValueError:
            raise Denied('planning_draft_text_invalid') from None
        check_content(store, value)


def save(store, role, snapshot, data, model, *, context_tokens, max_output_tokens, _scope_installer=None):
    """Trusted owner import only. Does not attest provider origin, billing, or execution."""
    owner(role)
    if not isinstance(snapshot, PlanningContext):
        raise Denied('planning_context_invalid')
    with store.transaction() as session:
        store.check_audit(session)
        reviewed = _review_response(store, session, snapshot, data, model, context_tokens=context_tokens,
                                    max_output_tokens=max_output_tokens)
        try:
            document = Document(schema_version=1, request_id=snapshot.request_id, context_digest=snapshot.binding,
                project_id=snapshot.project_id, assignment_version=snapshot.assignment_version,
                revision=snapshot.source_revision, proposal=Plan.model_validate(reviewed['proposal']),
                model=reviewed['model'], response_id=reviewed['response_id'], usage=Usage.model_validate(reviewed['usage']),
                context_tokens=context_tokens, max_output_tokens=max_output_tokens,
                origin='owner_supplied_unverified', provider_evidence_verified=False, execution_authorized=False)
        except ValidationError:
            raise Denied('planning_draft_invalid') from None
        _screen(store, document)
        raw = document.model_dump()
        if len(canonical(raw).encode()) > MAX_DOCUMENT_BYTES:
            raise Denied('planning_draft_size')
        records = _records(session)
        pid = identity(raw)
        previous = records.get(pid)
        if previous:
            if canonical(previous[0]['document']) != canonical(raw):
                raise Denied('planning_draft_idempotency_conflict')
            version = previous[0]['version']
        else:
            if len(records) >= MAX_PROPOSALS:
                raise Denied('planning_draft_capacity')
            version = sum(value[1].request_id == snapshot.request_id for value in records.values()) + 1
            store.audit(session, EVENT, 'owner', proposal_id=pid, request_id=snapshot.request_id, version=version,
                        document=raw, document_digest=digest(raw))
        receipt = {'proposal_id': pid, 'request_id': snapshot.request_id, 'context_digest': snapshot.binding,
                   'version': version, 'stored': True, 'origin': 'owner_supplied_unverified', 'provider_evidence_verified': False,
                   'execution_authorized': False, 'task_created': False}
        if _scope_installer:
            _scope_installer(session, receipt)
        return receipt


def read(store, role, request_id, *, version=None):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return read_locked(store, session, request_id, version=version)


def read_locked(store, session, request_id, *, version=None):
    """Caller owns checked F1 transaction; used by the private-owner Telegram reader."""
    if version is not None and (type(version) is not int or not 1 <= version <= MAX_PROPOSALS):
        raise Denied('planning_draft_version_invalid')
    snapshot = _context(store, session, request_id)
    records = [value for value in _records(session).values() if value[1].request_id == request_id]
    common = {'request_id': request_id, 'execution_authorized': False, 'task_created': False,
              'provider_evidence_verified': False}
    latest_version = records[-1][0]['version'] if records else 0
    selected = [value for value in records if version is None or value[0]['version'] == version]
    if not selected:
        return {**common, 'state': 'MISSING_VERSION' if version else 'MISSING', 'proposal_id': None,
                'proposal': None, 'version': version, 'latest_version': latest_version}
    event, document = selected[-1]
    _screen(store, document)  # Recheck current known credentials, including after rotation.
    current = document.context_digest == snapshot.binding
    if current and (document.project_id != snapshot.project_id or document.assignment_version != snapshot.assignment_version
                    or document.revision != snapshot.source_revision):
        raise Denied('planning_draft_integrity')
    return {**common, 'state': 'CURRENT' if current else 'STALE', 'proposal_id': event['proposal_id'],
            'origin': document.origin, 'project_id': snapshot.project_id, 'version': event['version'],
            'latest_version': latest_version,
            'proposal': document.proposal.model_dump() if current else None}
