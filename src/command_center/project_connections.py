"""Durable, evidence-bound repository connections; no network client lives here."""

import re

from sqlalchemy import select

from .models import Audit
from .project_catalog import IDS
from .store import Denied, digest

EVENT = 'project_connection_verified'
MAX_EVENTS = 100
PERMISSIONS = {'contents': 'write', 'pull_requests': 'write', 'metadata': 'read'}


def validate(manifest):
    required = {'project_id', 'repository', 'repository_id', 'installation_id', 'default_branch',
                'baseline_sha', 'permissions', 'repository_selection', 'repository_count_verified',
                'binding_verified', 'branch_protection_verified', 'read_only_probe_verified'}
    if (not isinstance(manifest, dict) or set(manifest) != required
            or manifest.get('project_id') not in IDS
            or not isinstance(manifest.get('repository'), str)
            or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}', manifest['repository'])
            or '..' in manifest['repository']
            or type(manifest.get('repository_id')) is not int or manifest['repository_id'] <= 0
            or type(manifest.get('installation_id')) is not int or manifest['installation_id'] <= 0
            or not re.fullmatch(r'[A-Za-z0-9._/-]{1,120}', str(manifest.get('default_branch', '')))
            or '..' in manifest['default_branch'] or manifest['default_branch'].startswith('/')
            or not re.fullmatch(r'[a-f0-9]{40}', str(manifest.get('baseline_sha', '')))
            or manifest.get('permissions') != PERMISSIONS
            or manifest.get('repository_selection') != 'selected'
            or manifest.get('repository_count_verified') is not True
            or manifest.get('binding_verified') is not True
            or manifest.get('branch_protection_verified') is not True
            or manifest.get('read_only_probe_verified') is not True):
        raise Denied('project_connection_manifest_invalid')
    return manifest


def history(session):
    rows = session.execute(select(Audit).where(Audit.event['kind'].as_string() == EVENT)
                           .order_by(Audit.sequence).limit(MAX_EVENTS + 1)).scalars().all()
    if len(rows) > MAX_EVENTS:
        raise Denied('project_connection_history_limit')
    latest, operations = {}, {}
    for row in rows:
        event = row.event
        manifest, operation = event.get('manifest'), event.get('operation_id')
        validate(manifest)
        if (event.get('actor') != 'owner' or event.get('manifest_hash') != digest(manifest)
                or not isinstance(operation, str) or not re.fullmatch(r'[a-f0-9-]{36}', operation)
                or operation in operations):
            raise Denied('project_connection_history_invalid')
        latest[manifest['project_id']] = event
        operations[operation] = event
    return latest, operations


def register(store, role, manifest, operation_id):
    """Record already verified operator evidence; this function performs no probe."""
    if role != 'owner':
        raise Denied('owner_required')
    validate(manifest)
    if not isinstance(operation_id, str) or not re.fullmatch(r'[a-f0-9-]{36}', operation_id):
        raise Denied('project_connection_operation_invalid')
    with store.transaction() as session:
        store.check_audit(session)
        latest, operations = history(session)
        previous = operations.get(operation_id)
        if previous:
            if previous['manifest_hash'] != digest(manifest):
                raise Denied('project_connection_idempotency_conflict')
            return receipt(previous)
        current = latest.get(manifest['project_id'])
        if current and current['manifest'] != manifest:
            raise Denied('project_connection_replacement_requires_disconnect')
        if len(operations) >= MAX_EVENTS:
            raise Denied('project_connection_history_limit')
        event = {'manifest': manifest, 'manifest_hash': digest(manifest), 'operation_id': operation_id,
                 'execution_enabled': False, 'paid_ai_enabled': False, 'merge_enabled': False,
                 'deployment_enabled': False}
        store.audit(session, EVENT, 'owner', **event)
        return receipt(event)


def receipt(event):
    manifest = event['manifest']
    return {'project_id': manifest['project_id'], 'state': 'VERIFIED_DISABLED',
            'repository': manifest['repository'], 'repository_id': manifest['repository_id'],
            'baseline_sha': manifest['baseline_sha'], 'execution_enabled': False,
            'paid_ai_enabled': False, 'merge_enabled': False, 'deployment_enabled': False}


def statuses(session):
    latest, _ = history(session)
    return {project_id: receipt(event) for project_id, event in latest.items()}
