"""Versioned project setup drafts in F1 audit. Declarations never grant access."""
from datetime import datetime
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from .models import Audit
from .project_connections import REPOSITORIES
from .project_inbox import IDS, PROJECTS, check_content, owner
from .store import Denied, canonical, digest

ProjectId = Literal['command-center', 'vanilla-sugar', 'lnauto', 'capital-lab']
EVENT = 'project_setup_draft_changed'
MAX_EVENTS = 500
MAX_DRAFT_BYTES = 12288
FIELDS = ('repository_revision', 'verification_kind', 'delivery_kind', 'deployment_target', 'acceptance')
CHECKS = ('repository_binding', 'isolated_verification', 'deployment_binding', 'separate_task_authorization')
OPERATION = r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$'


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Draft(Strict):
    repository_revision: str | None = Field(default=None, pattern=r'^[a-f0-9]{40}$')
    verification_kind: Literal['not_selected', 'python', 'node', 'python_node'] = 'not_selected'
    delivery_kind: Literal['not_selected', 'manual_review', 'pipeline_review'] = 'not_selected'
    deployment_target: str | None = Field(default=None, pattern=r'^[a-z][a-z0-9-]{0,47}$')
    acceptance: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=8)

    @field_validator('repository_revision', 'deployment_target')
    @classmethod
    def exact_reference(cls, value, info):
        pattern = r'[a-f0-9]{40}' if info.field_name == 'repository_revision' else r'[a-z][a-z0-9-]{0,47}'
        if value is not None and not re.fullmatch(pattern, value):
            raise ValueError('exact reference required')
        return value

    @field_validator('acceptance')
    @classmethod
    def plain_criteria(cls, values):
        if any(value != value.strip() or any(ord(c) < 32 for c in value) or len(value.encode()) > 400 for value in values):
            raise ValueError('bounded plain acceptance criteria required')
        return values


class PreviewRequest(Strict):
    expected_version: int = Field(ge=0, le=MAX_EVENTS)
    draft: Draft


class SaveRequest(PreviewRequest):
    operation_id: str = Field(pattern=OPERATION)


class RestoreRequest(Strict):
    expected_version: int = Field(ge=0, le=MAX_EVENTS)
    target_version: int = Field(ge=0, le=MAX_EVENTS)
    target_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    operation_id: str = Field(pattern=OPERATION)


def project(project_id):
    if not isinstance(project_id, str) or project_id not in IDS:
        raise Denied('unknown_project')


def version(value):
    if type(value) is not int or not 0 <= value <= MAX_EVENTS:
        raise Denied('project_setup_version_invalid')


def _draft(store, value):
    try:
        parsed = Draft.model_validate(value)
        raw = parsed.model_dump()
        if len(canonical(raw).encode()) > MAX_DRAFT_BYTES:
            raise ValueError()
        for item in (parsed.repository_revision, parsed.deployment_target, *parsed.acceptance):
            if item:
                check_content(store, item)
        return raw
    except (ValidationError, ValueError, TypeError):
        raise Denied('project_setup_draft_invalid') from None


def binding(project_id, draft):
    return digest({'project_id': project_id, 'draft': draft})


def review(draft):
    missing = [key for key in FIELDS if draft[key] in (None, 'not_selected', [])]
    return {'filled': len(FIELDS) - len(missing), 'total': len(FIELDS), 'missing_fields': missing,
            'ready_for_operator_review': not missing, 'execution_ready': False,
            'blocking_checks': list(CHECKS)}


def _resolve(store, action, previous, snapshots):
    base = {'action', 'project_id', 'expected_version'}
    kind = action.get('action')
    extra = {'save': {'draft'}, 'patch': {'field', 'value'}, 'clear': {'field'},
             'restore': {'target_version', 'target_digest'}}.get(kind)
    if extra is None or set(action) != base | extra:
        raise Denied('project_setup_action_invalid')
    project(action['project_id'])
    version(action['expected_version'])
    if kind == 'save':
        return _draft(store, action['draft'])
    if kind == 'restore':
        target = action['target_version']
        version(target)
        old = Draft().model_dump() if target == 0 else snapshots.get((action['project_id'], target))
        if old is None or action['target_digest'] != binding(action['project_id'], old):
            raise Denied('project_setup_restore_target_changed')
        return _draft(store, old)
    field = action['field']
    if not isinstance(field, str) or field not in FIELDS:
        raise Denied('project_setup_field_invalid')
    return _draft(store, {**previous, field: action['value'] if kind == 'patch' else Draft().model_dump()[field]})


def records(store, session):
    rows = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)
                           .order_by(Audit.sequence).limit(MAX_EVENTS + 1)).all()
    if len(rows) > MAX_EVENTS:
        raise Denied('project_setup_history_capacity')
    latest, operations, snapshots = {}, {}, {}
    for row in rows:
        event = row.event
        try:
            pid, v, op = event['project_id'], event['version'], event['operation_id']
            project(pid)
            version(v)
            uid = UUID(op)
            previous = latest.get(pid)
            prior_version = previous['version'] if previous else 0
            prior = previous['draft'] if previous else Draft().model_dump()
            action = event['input']
            raw = _draft(store, event['draft'])
            if (set(event) != {'kind', 'actor', 'task_id', 'time', 'revision', 'schema', 'project_id', 'version',
                              'operation_id', 'input', 'input_hash', 'draft', 'draft_digest'}
                    or event.get('actor') != 'owner' or event.get('task_id') is not None
                    or not isinstance(event.get('time'), str) or datetime.fromisoformat(event['time']).tzinfo is None
                    or type(event.get('schema')) is not int or event['schema'] != 1
                    or not isinstance(event.get('revision'), str) or len(event['revision']) != 40
                    or any(c not in '0123456789abcdef' for c in event['revision'])
                    or str(uid) != op or uid.version not in {4, 5} or op in operations
                    or v != prior_version + 1 or not isinstance(action, dict)
                    or action.get('project_id') != pid or action.get('expected_version') != prior_version
                    or event['input_hash'] != digest(action) or event['draft_digest'] != binding(pid, raw)
                    or canonical(event['draft']) != canonical(raw)
                    or canonical(_resolve(store, action, prior, snapshots)) != canonical(raw)):
                raise ValueError()
            latest[pid], operations[op], snapshots[(pid, v)] = event, event, raw
        except (Denied, ValueError, TypeError, KeyError, AttributeError):
            raise Denied('project_setup_history_invalid') from None
    return latest, operations, snapshots


def _view(project_id, latest, snapshots, selected=None):
    current = latest.get(project_id)
    current_version = current['version'] if current else 0
    selected = current_version if selected is None else selected
    version(selected)
    raw = Draft().model_dump() if selected == 0 else snapshots.get((project_id, selected))
    if raw is None:
        raise Denied('project_setup_version_missing')
    versions = sorted((v for pid, v in snapshots if pid == project_id), reverse=True)[:9]
    history = [{'version': v, 'draft_digest': binding(project_id, snapshots[(project_id, v)])} for v in versions]
    history.append({'version': 0, 'draft_digest': binding(project_id, Draft().model_dump())})
    return {'schema': 1, 'scope': 'SETUP_DRAFT_ONLY', 'project_id': project_id, 'label': dict(PROJECTS)[project_id],
            'expected_repository': REPOSITORIES[project_id], 'version': selected, 'latest_version': current_version,
            'state': 'CURRENT' if selected == current_version else 'HISTORICAL',
            'draft': raw, 'draft_digest': binding(project_id, raw), 'review': review(raw), 'history': history,
            'execution_connected': False, 'external_checks_performed': False, 'actions_enabled': []}


def read_locked(store, session, project_id, *, selected=None):
    project(project_id)
    latest, _, snapshots = records(store, session)
    return _view(project_id, latest, snapshots, selected)


def read(store, role, project_id, *, selected=None):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return read_locked(store, session, project_id, selected=selected)


def catalog(store, role):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        latest, _, snapshots = records(store, session)
        return {'schema': 1, 'scope': 'SETUP_DRAFT_ONLY', 'projects': [
            {k: v for k, v in _view(pid, latest, snapshots).items()
             if k in {'project_id', 'label', 'expected_repository', 'version', 'review'}} for pid, _ in PROJECTS],
            'execution_connected': False, 'external_checks_performed': False, 'actions_enabled': []}


def preview(store, role, project_id, expected_version, draft):
    owner(role)
    project(project_id)
    version(expected_version)
    raw = _draft(store, draft)
    with store.transaction() as session:
        store.check_audit(session)
        current = read_locked(store, session, project_id)
        if current['version'] != expected_version:
            raise Denied('project_setup_stale_version')
        return {'schema': 1, 'scope': 'SETUP_DRAFT_ONLY', 'project_id': project_id, 'base_version': expected_version,
                'draft': raw, 'proposed_digest': binding(project_id, raw), 'review': review(raw),
                'changed_fields': [key for key in FIELDS if raw[key] != current['draft'][key]],
                'stored': False, 'execution_connected': False, 'external_checks_performed': False, 'actions_enabled': []}


def receipt(event):
    return {key: event[key] for key in ('project_id', 'version', 'draft_digest', 'operation_id')} | {
        'scope': 'SETUP_DRAFT_ONLY', 'stored': True, 'execution_started': False, 'external_checks_performed': False}


def _mutate(store, role, action, operation_id, *, _scope_installer=None):
    owner(role)
    project(action['project_id'])
    version(action['expected_version'])
    try:
        uid = UUID(operation_id)
        if str(uid) != operation_id or uid.version not in {4, 5}:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Denied('project_setup_operation_invalid') from None
    with store.transaction() as session:
        store.check_audit(session)
        latest, operations, snapshots = records(store, session)
        prior = operations.get(operation_id)
        if prior:
            if prior['input_hash'] != digest(action):
                raise Denied('project_setup_idempotency_conflict')
            result = receipt(prior)
        else:
            previous = latest.get(action['project_id'])
            v = previous['version'] if previous else 0
            if v != action['expected_version']:
                raise Denied('project_setup_stale_version')
            raw = _resolve(store, action, previous['draft'] if previous else Draft().model_dump(), snapshots)
            if len(operations) >= MAX_EVENTS:
                raise Denied('project_setup_history_capacity')
            event = {'schema': 1, 'project_id': action['project_id'], 'version': v + 1,
                     'operation_id': operation_id, 'input': action, 'input_hash': digest(action),
                     'draft': raw, 'draft_digest': binding(action['project_id'], raw)}
            store.audit(session, EVENT, 'owner', **event)
            result = receipt(event)
        if _scope_installer:
            _scope_installer(session, result)
        return result


def save(store, role, project_id, expected_version, draft, operation_id, *, _scope_installer=None):
    owner(role)
    project(project_id)
    raw = _draft(store, draft)
    return _mutate(store, role, {'action': 'save', 'project_id': project_id,
        'expected_version': expected_version, 'draft': raw}, operation_id, _scope_installer=_scope_installer)


def patch(store, role, project_id, expected_version, field, value, operation_id, *, clear=False, _scope_installer=None):
    action = {'action': 'clear' if clear else 'patch', 'project_id': project_id,
              'expected_version': expected_version, 'field': field}
    if not clear:
        action['value'] = value
    return _mutate(store, role, action, operation_id, _scope_installer=_scope_installer)


def restore(store, role, project_id, expected_version, target_version, target_digest, operation_id, *, _scope_installer=None):
    return _mutate(store, role, {'action': 'restore', 'project_id': project_id, 'expected_version': expected_version,
        'target_version': target_version, 'target_digest': target_digest}, operation_id, _scope_installer=_scope_installer)
