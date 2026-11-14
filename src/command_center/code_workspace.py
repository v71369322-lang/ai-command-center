"""Exact offline source capsule for AI proposals. No key, network or execution grant."""
from datetime import datetime

from pydantic import Field
from sqlalchemy import select

from .coding_preparation import history as preparations, read_locked as preparation_read
from .isolated_coding import MAX_BYTES, Snapshot, snapshot_files
from .models import Audit
from .plan_acceptance import preview_locked as plan_preview
from .project_inbox import owner, check_content
from .request_planning import HEX, REQUEST, Strict, _context
from .store import Denied, canonical, digest

EVENT = 'code_generation_workspace_prepared'
KIND = 'saved_request_code'
MAX_RECORDS = 100


class WorkspaceRequest(Strict):
    request_id: str = Field(pattern=REQUEST)
    expected_spec_digest: str = Field(pattern=HEX)
    snapshot: Snapshot


class WorkspaceSave(WorkspaceRequest):
    expected_workspace_digest: str = Field(pattern=HEX)


def validate(seed):
    from .coding_preparation import CodingScope, specification
    from .plan_acceptance import Reference
    from .request_planning import Plan, PlanningContext
    try:
        if (set(seed) != {'schema_version', 'specification', 'spec_digest', 'snapshot', 'context', 'plan'}
                or type(seed['schema_version']) is not int or seed['schema_version'] != 1
                or len(canonical(seed).encode()) > MAX_BYTES):
            raise ValueError()
        spec = seed['specification']
        ref = Reference.model_validate(spec['acceptance_reference']).model_dump()
        scope = CodingScope.model_validate(spec['scope'])
        context = PlanningContext.model_validate(seed['context'])
        plan = Plan.model_validate(seed['plan'])
        if (canonical(spec) != canonical(specification(ref, scope)) or digest(spec) != seed['spec_digest']
                or canonical(context.model_dump()) != canonical(seed['context'])
                or canonical(plan.model_dump()) != canonical(seed['plan'])
                or context.binding != ref['context_digest'] or context.request_id != ref['request_id']
                or context.project_id != 'command-center' or context.halted or context.recovery
                or context.source_revision != ref['source_revision'] or plan.context_digest != context.binding
                or plan.disposition != 'ready_for_review' or plan.questions
                or not any(not p.startswith('tests/') for p in scope.allowed_files)
                or seed['snapshot']['objects'] != sorted(seed['snapshot']['objects'], key=canonical)):
            raise ValueError()
        files = snapshot_files(seed['snapshot'], ref['declared_repository_revision'],
                               [*scope.allowed_files, *scope.test_files])
        if any('\x00' in value or value and not value.endswith('\n') for value in files.values()):
            raise ValueError()
        return files
    except (ValueError, KeyError, TypeError):
        raise Denied('code_workspace_invalid') from None


def history(store, session):
    rows = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)
                           .order_by(Audit.sequence).limit(MAX_RECORDS + 1)).all()
    if len(rows) > MAX_RECORDS:
        raise Denied('code_workspace_capacity')
    known = preparations(store, session) if rows else {}
    result = {}
    for row in rows:
        e = row.event
        try:
            seed = e['workspace']
            files = validate(seed)
            for value in [*files.values(), seed['context']['text'], canonical(seed['plan'])]:
                check_content(store, value)
            pin = digest(seed)
            if (set(e) != {'kind', 'actor', 'task_id', 'time', 'revision', 'workspace', 'workspace_digest'}
                    or e['actor'] != 'owner' or e['task_id'] is not None
                    or e['revision'] != seed['context']['source_revision']
                    or e['workspace_digest'] != pin or pin in result
                    or known[seed['spec_digest']]['specification'] != seed['specification']
                    or datetime.fromisoformat(e['time']).tzinfo is None):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise Denied('code_workspace_integrity') from None
        result[pin] = seed
    return result


def check_current(store, session, seed):
    validate(seed)
    ref = seed['specification']['acceptance_reference']
    current = preparation_read(store, session, ref['request_id'])
    if (current['state'] != 'PREPARED_NOT_RUNNABLE'
            or current['preparation']['spec_digest'] != seed['spec_digest']
            or canonical(current['preparation']['specification']) != canonical(seed['specification'])
            or canonical(_context(store, session, ref['request_id']).model_dump()) != canonical(seed['context'])
            or canonical(plan_preview(store, session, ref['request_id'])['proposal']) != canonical(seed['plan'])):
        raise Denied('code_workspace_stale')


def preview_locked(store, session, request):
    request = WorkspaceRequest.model_validate(request)
    current = preparation_read(store, session, request.request_id)
    if (current['state'] != 'PREPARED_NOT_RUNNABLE'
            or current['preparation']['spec_digest'] != request.expected_spec_digest):
        raise Denied('code_workspace_current_preparation_required')
    seed = {'schema_version': 1, 'specification': current['preparation']['specification'],
            'spec_digest': request.expected_spec_digest,
            'snapshot': {'objects': sorted(request.snapshot.model_dump()['objects'], key=canonical)},
            'context': _context(store, session, request.request_id).model_dump(),
            'plan': plan_preview(store, session, request.request_id)['proposal']}
    files = validate(seed)
    for value in [*files.values(), canonical(seed)]:
        check_content(store, value)
    return {'workspace': seed, 'workspace_digest': digest(seed), 'provider_called': False,
            'execution_authorized': False, 'paid_calls_authorized': False}


def preview(store, role, request):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return preview_locked(store, session, request)


def prepare(store, role, request):
    owner(role)
    request = WorkspaceSave.model_validate(request)
    with store.transaction() as session:
        store.check_audit(session)
        value = preview_locked(store, session, request.model_dump(exclude={'expected_workspace_digest'}))
        if value['workspace_digest'] != request.expected_workspace_digest:
            raise Denied('code_workspace_review_changed')
        records = history(store, session)
        if value['workspace_digest'] not in records:
            if len(records) >= MAX_RECORDS:
                raise Denied('code_workspace_capacity')
            store.audit(session, EVENT, 'owner', workspace=value['workspace'], workspace_digest=value['workspace_digest'])
        return value


def payload(seed):
    validate(seed)
    return {'kind': KIND, 'workspace': seed, 'workspace_digest': digest(seed), 'cost': 1}


def validate_payload(value):
    try:
        if (set(value) != {'kind', 'workspace', 'workspace_digest', 'cost'}
                or canonical(value) != canonical(payload(value['workspace']))):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise Denied('code_generation_task_invalid') from None


def check_task(store, session, value):
    validate_payload(value)
    records = history(store, session)
    if canonical(records.get(value['workspace_digest'])) != canonical(value['workspace']):
        raise Denied('code_workspace_not_registered')
    check_current(store, session, value['workspace'])


def create_locked(store, session, request_id, expected_workspace_digest=None):
    records = history(store, session)
    selected = [(pin, seed) for pin, seed in records.items() if seed['context']['request_id'] == request_id]
    if not selected:
        raise Denied('code_workspace_required')
    pin, seed = selected[-1]
    if expected_workspace_digest is not None and pin != expected_workspace_digest:
        raise Denied('code_workspace_review_changed')
    check_current(store, session, seed)
    return store._create_locked(session, 'owner', 'code-generation-v1:' + pin, payload(seed))
