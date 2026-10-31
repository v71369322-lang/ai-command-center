"""Bounded owner-supplied advisory drafts in the existing append-only F1 audit."""
from typing import Literal
from datetime import datetime
from uuid import UUID
import re

from pydantic import Field, ValidationError
from sqlalchemy import select

from .coding.http_contract import Usage
from .models import Audit
from .project_inbox import check_content, owner
from .request_planning import HEX, REQUEST, Plan, PlanningContext, Strict, Step, Text, _context, _review_response, limits
from .store import Denied, canonical, digest

EVENT = 'saved_request_plan_draft'
MAX_PROPOSALS = 100
MAX_DOCUMENT_BYTES = 32768
OPERATION = r'^[a-f0-9]{8}-[a-f0-9]{4}-[45][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$'


class ManualContent(Strict):
    summary: Text
    steps: list[Step] = Field(min_length=1, max_length=8)
    questions: list[Text] = Field(max_length=5)


class ManualRequest(Strict):
    request_id: str = Field(pattern=REQUEST)
    expected_context_digest: str = Field(pattern=HEX)
    expected_assignment_version: int = Field(ge=1, le=1000)
    expected_setup_version: int = Field(ge=0, le=500)
    expected_setup_digest: str = Field(pattern=HEX)
    expected_plan_version: int = Field(ge=0, le=MAX_PROPOSALS)
    draft: ManualContent


class ManualSaveRequest(ManualRequest):
    operation_id: str = Field(pattern=OPERATION.replace('[45]', '4'))


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


class ManualDocument(Strict):
    schema_version: Literal[2]
    request_id: str = Field(pattern=REQUEST)
    context_digest: str = Field(pattern=HEX)
    project_id: Literal['command-center', 'vanilla-sugar', 'lnauto', 'capital-lab']
    assignment_version: int = Field(ge=1, le=1000)
    revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    proposal: Plan
    setup_version: int = Field(ge=0, le=500)
    setup_digest: str = Field(pattern=HEX)
    operation_id: str = Field(pattern=OPERATION)
    input_digest: str = Field(pattern=HEX)
    origin: Literal['owner_authored']
    provider_evidence_verified: Literal[False]
    execution_authorized: Literal[False]


def manual_input(document, version):
    return ManualRequest(request_id=document.request_id, expected_context_digest=document.context_digest,
        expected_assignment_version=document.assignment_version, expected_setup_version=document.setup_version,
        expected_setup_digest=document.setup_digest, expected_plan_version=version - 1,
        draft=ManualContent(summary=document.proposal.summary, steps=document.proposal.steps,
                            questions=document.proposal.questions)).model_dump()


def identity(document):
    if document.get('origin') == 'owner_authored':
        return digest({'origin': document['origin'], 'operation_id': document['operation_id']})
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
            if type(raw.get('schema_version')) is not int or raw['schema_version'] not in {1, 2}:
                raise ValueError()
            document = (ManualDocument if raw['schema_version'] == 2 else Document).model_validate(raw)
            normalized = document.model_dump()
            if isinstance(document, Document):
                limits(document.model, document.context_tokens, document.max_output_tokens)
                usage = document.usage
                if (usage.total_tokens != usage.input_tokens + usage.output_tokens
                        or usage.input_tokens > document.context_tokens or usage.output_tokens > document.max_output_tokens):
                    raise ValueError()
            else:
                operation = UUID(document.operation_id)
                if (set(event) != {'kind','actor','task_id','time','revision','proposal_id','request_id','version','document','document_digest'}
                        or datetime.fromisoformat(event['time']).tzinfo is None
                        or not re.fullmatch(r'[a-f0-9]{40}', document.revision)
                        or str(operation) != document.operation_id or operation.version not in {4,5}
                        or document.input_digest != digest(manual_input(document, event['version']))):
                    raise ValueError()
            if (canonical(normalized) != canonical(raw) or event.get('actor') != 'owner'
                    or event.get('task_id') is not None or event.get('revision') != document.revision
                    or event.get('request_id') != document.request_id
                    or event.get('document_digest') != digest(raw)
                    or event.get('proposal_id') != identity(raw) or event['proposal_id'] in result
                    or type(event.get('version')) is not int
                    or event['version'] != versions.get(document.request_id, 0) + 1
                    or document.proposal.context_digest != document.context_digest
                    or document.project_id is None and not document.proposal.questions):
                raise ValueError()
        except (Denied, ValueError, KeyError, TypeError):
            raise Denied('planning_draft_integrity') from None
        result[event['proposal_id']] = (event, document)
        versions[document.request_id] = event['version']
    return result


def _screen(store, document):
    plan = document.proposal
    provider = [document.model, document.response_id] if isinstance(document, Document) else []
    for value in [*provider, plan.summary, *plan.questions,
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
        return _save_locked(store, session, snapshot, data, model, context_tokens=context_tokens,
                            max_output_tokens=max_output_tokens, _scope_installer=_scope_installer)


def _save_locked(store, session, snapshot, data, model, *, context_tokens, max_output_tokens, _scope_installer=None):
    """Trusted composition under an already checked Control transaction."""
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
    setup_state = 'NOT_RECORDED'
    if isinstance(document, ManualDocument):
        from .project_setup import read_locked as setup_read
        setup = setup_read(store, session, document.project_id, selected=document.setup_version)
        if setup['draft_digest'] != document.setup_digest:
            raise Denied('planning_draft_integrity')
        matches = setup['latest_version'] == document.setup_version
        setup_state = 'CURRENT' if current and matches else 'STALE'
        current = current and matches
    return {**common, 'state': 'CURRENT' if current else 'STALE', 'proposal_id': event['proposal_id'],
            'origin': document.origin, 'project_id': snapshot.project_id, 'version': event['version'],
            'setup_reference_state': setup_state,
            'latest_version': latest_version,
            'proposal': document.proposal.model_dump() if current else None}
