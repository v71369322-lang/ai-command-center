"""Pinned isolated-coding specification; no repository, executor or provider I/O."""
from datetime import datetime
from pathlib import PurePosixPath

from pydantic import Field, field_validator
from sqlalchemy import select

from .models import Audit
from .plan_acceptance import Reference, _history as acceptances, read_locked as acceptance_read
from .project_inbox import owner, check_content
from .request_planning import HEX, REQUEST, Strict
from .store import Denied, canonical, digest

EVENT = 'saved_request_coding_specification_prepared'
MAX_PREPARATIONS = 100
FLAGS = {'execution_authorized': False, 'task_created': False, 'paid_calls_authorized': False,
         'repository_access_verified': False, 'runtime_bound': False, 'verification_performed': False,
         'publication_authorized': False, 'provider_called': False}


class CodingScope(Strict):
    allowed_files: list[str] = Field(min_length=1, max_length=8)
    test_files: list[str] = Field(min_length=1, max_length=8)
    max_seconds: int = Field(default=60, ge=1, le=120)
    max_iterations: int = Field(default=1, ge=1, le=2)
    max_diff_bytes: int = Field(default=16384, ge=1024, le=32768)

    @field_validator('allowed_files', 'test_files')
    @classmethod
    def paths(cls, values, info):
        if len(values) != len(set(values)):
            raise ValueError('unique_relative_python_paths_required')
        for value in values:
            path = PurePosixPath(value)
            if (not 1 <= len(value) <= 180 or not value.isascii()
                    or any(not (c.isalnum() or c in '_/.') for c in value)
                    or str(path) != value or path.is_absolute()
                    or any(p.startswith('.') or p == '__pycache__' for p in path.parts)
                    or not value.endswith('.py')
                    or not value.startswith(('src/command_center/', 'tests/'))
                    or info.field_name == 'test_files' and not value.startswith('tests/test_')):
                raise ValueError('bounded_relative_python_path_required')
        return sorted(values)


class CodingPreparationRequest(Strict):
    request_id: str = Field(pattern=REQUEST)
    expected_acceptance_digest: str = Field(pattern=HEX)
    scope: CodingScope


class CodingPreparationSave(CodingPreparationRequest):
    expected_spec_digest: str = Field(pattern=HEX)


def specification(reference, scope):
    return {'schema_version': 1, 'purpose': 'isolated-coding-preparation.v1',
        'state': 'PREPARED_NOT_RUNNABLE', 'acceptance_reference': reference,
        'acceptance_digest': digest(reference), 'scope': scope.model_dump(),
        'isolation': {'network': 'none', 'credentials': False, 'host_paths': False,
                      'base_read_only': True, 'workspace': 'ephemeral', 'runtime_mode': 'rootless-required',
                      'non_root_required': True, 'privileged': False, 'cap_drop': ['ALL'],
                      'no_new_privileges': True, 'memory_mib': 256, 'millicpus': 500, 'pids_limit': 64},
        'verification_commands': [['ruff', 'check', '--', *scope.allowed_files],
                                  ['python', '-m', 'pytest', '--', *scope.test_files]],
        'blocking_checks': ['repository_capability', 'exact_workspace_snapshot', 'trusted_runtime_binding',
                            'F1_task_and_approval', 'independent_verifier', 'publication_if_requested'], **FLAGS}


def history(store, session):
    rows = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == EVENT)
                           .order_by(Audit.sequence).limit(MAX_PREPARATIONS + 1)).all()
    if len(rows) > MAX_PREPARATIONS:
        raise Denied('coding_preparation_capacity')
    accepted = acceptances(store, session) if rows else {}
    result = {}
    for row in rows:
        try:
            e = row.event
            spec = e['specification']
            ref = Reference.model_validate(spec['acceptance_reference']).model_dump()
            scope = CodingScope.model_validate(spec['scope'])
            for path in [*scope.allowed_files, *scope.test_files]:
                check_content(store, path)
            pin = digest(spec)
            if (set(e) != {'kind', 'actor', 'task_id', 'time', 'revision', 'specification', 'spec_digest'}
                    or e['actor'] != 'owner' or e['task_id'] is not None
                    or e['revision'] != ref['source_revision'] or e['spec_digest'] != pin or pin in result
                    or datetime.fromisoformat(e['time']).tzinfo is None
                    or accepted[spec['acceptance_digest']]['reference'] != ref
                    or canonical(spec) != canonical(specification(ref, scope))):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise Denied('coding_preparation_integrity') from None
        result[pin] = {'specification': spec, 'spec_digest': pin, 'prepared_at': e['time'], **FLAGS}
    return result


def preview_locked(store, session, request):
    request = CodingPreparationRequest.model_validate(request.model_dump() if isinstance(request, CodingPreparationRequest) else request)
    accepted = acceptance_read(store, session, request.request_id)
    if (accepted['state'] != 'CURRENT'
            or accepted['receipt']['snapshot_digest'] != request.expected_acceptance_digest):
        raise Denied('coding_preparation_current_acceptance_required')
    for path in [*request.scope.allowed_files, *request.scope.test_files]:
        check_content(store, path)
    spec = specification(accepted['receipt']['reference'], request.scope)
    return {'specification': spec, 'spec_digest': digest(spec), 'stored': False, **FLAGS}


def prepare_locked(store, session, request):
    request = CodingPreparationSave.model_validate(request.model_dump() if isinstance(request, CodingPreparationSave) else request)
    value = preview_locked(store, session, CodingPreparationRequest.model_validate(
        request.model_dump(exclude={'expected_spec_digest'})))
    if value['spec_digest'] != request.expected_spec_digest:
        raise Denied('coding_preparation_snapshot_changed')
    records = history(store, session)
    if value['spec_digest'] in records:
        return records[value['spec_digest']]
    if len(records) >= MAX_PREPARATIONS:
        raise Denied('coding_preparation_capacity')
    store.audit(session, EVENT, 'owner', specification=value['specification'], spec_digest=value['spec_digest'])
    return history(store, session)[value['spec_digest']]


def preview(store, role, request):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        history(store, session)
        return preview_locked(store, session, request)


def prepare(store, role, request):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return prepare_locked(store, session, request)


def read_locked(store, session, request_id):
    accepted = acceptance_read(store, session, request_id)
    records = [r for r in history(store, session).values()
               if r['specification']['acceptance_reference']['request_id'] == request_id]
    if not records:
        return {'state': 'MISSING', 'preparation': None, **FLAGS}
    result = records[-1]
    current = accepted['state'] == 'CURRENT' and (
        accepted['receipt']['snapshot_digest'] == result['specification']['acceptance_digest'])
    return {'state': 'PREPARED_NOT_RUNNABLE' if current else 'STALE', 'preparation': result, **FLAGS}


def read(store, role, request_id):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return read_locked(store, session, request_id)
