import importlib.util
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import pytest

from command_center.project_connections import PERMISSIONS, REPOSITORIES


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    'register_project_connection', ROOT / 'infra/vps/register_project_connection.py')
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


def manifest(**changes):
    value = {
        'project_id': 'command-center',
        'repository': REPOSITORIES['command-center'],
        'repository_id': 1430664079,
        'installation_id': 176497504,
        'default_branch': 'main',
        'baseline_sha': 'a' * 40,
        'permissions': dict(PERMISSIONS),
        'repository_selection': 'selected',
        'repository_count_verified': True,
        'binding_verified': True,
        'branch_protection_verified': True,
        'read_only_probe_verified': True,
    }
    return value | changes


@pytest.fixture
def evidence_file(tmp_path, monkeypatch):
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    path = private / 'connection.json'
    path.write_text(json.dumps(manifest()), encoding='utf-8')
    path.chmod(0o600)
    monkeypatch.setattr(operator, 'ROOT', tmp_path / 'source')
    monkeypatch.setattr(operator.os, 'geteuid', lambda: os.getuid())
    monkeypatch.setattr(operator, 'check_source', lambda revision, expected=None: 'f' * 64)
    return path


def test_offline_plan_binds_private_evidence_without_store(evidence_file, monkeypatch):
    monkeypatch.setattr(operator, 'Store', lambda settings: pytest.fail('store accessed'))
    operation = str(uuid4())
    _, result = operator.describe(evidence_file, '1' * 40, operation)
    assert result['project_id'] == 'command-center'
    assert result['repository'] == 'v71369322-lang/ai-command-center'
    assert result['state'] == 'OFFLINE_PLAN_NOT_AUTHORIZED'
    assert result['external_calls'] == 0 and result['credential_values_read'] is False
    assert result['execution_enabled'] is result['paid_ai_enabled'] is False
    assert result['merge_enabled'] is result['deployment_enabled'] is False
    assert len(result['evidence_sha256']) == len(result['plan_digest']) == 64


def test_apply_requires_exact_fresh_plan_and_records_disabled_connection(
        evidence_file, monkeypatch):
    operation = str(uuid4())
    _, plan = operator.describe(evidence_file, '1' * 40, operation)
    called = []
    monkeypatch.setattr(operator.Settings, 'load', lambda: type(
        'Settings', (), {'source_revision': '1' * 40})())
    monkeypatch.setattr(operator, 'Store', lambda settings: 'store')
    monkeypatch.setattr(operator, 'register', lambda store, role, value, op, provenance: (
        called.append((store, role, value, op, provenance)) or {
            'project_id': value['project_id'], 'repository': value['repository'],
            'repository_id': value['repository_id'], 'baseline_sha': value['baseline_sha'],
            'state': 'VERIFIED_DISABLED', 'execution_enabled': False,
            'paid_ai_enabled': False, 'merge_enabled': False, 'deployment_enabled': False,
        }))
    result = operator.apply(evidence_file, '1' * 40, operation, plan['source_digest'],
                            plan['plan_digest'],
                            int(time.time()) + 300)
    assert result['status'] == 'PROJECT_CONNECTION_REGISTERED_DISABLED'
    assert result['state'] == 'VERIFIED_DISABLED'
    assert result['execution_enabled'] is result['paid_ai_enabled'] is False
    assert result['merge_enabled'] is result['deployment_enabled'] is False
    assert called == [('store', 'owner', manifest(), operation, {
        'evidence_sha256': plan['evidence_sha256'],
        'operator_revision': '1' * 40,
        'plan_digest': plan['plan_digest'],
    })]


def test_apply_requires_runtime_binding_to_operator_revision(evidence_file, monkeypatch):
    operation = str(uuid4())
    _, plan = operator.describe(evidence_file, '1' * 40, operation)
    monkeypatch.setattr(operator.Settings, 'load', lambda: type(
        'Settings', (), {'source_revision': '2' * 40})())
    monkeypatch.setattr(operator, 'Store', lambda settings: pytest.fail('store accessed'))
    with pytest.raises(operator.Blocked, match='runtime_binding_revision_mismatch'):
        operator.apply(evidence_file, '1' * 40, operation, plan['source_digest'],
                       plan['plan_digest'],
                       int(time.time()) + 300)


@pytest.mark.parametrize('approved,seconds,error', [
    ('bad', 300, 'exact_plan_approval_required'),
    ('plan', -1, 'fresh_owner_deadline_required'),
    ('plan', 700, 'fresh_owner_deadline_required'),
])
def test_apply_rejects_bad_authority_before_store(
        evidence_file, monkeypatch, approved, seconds, error):
    operation = str(uuid4())
    _, plan = operator.describe(evidence_file, '1' * 40, operation)
    approved = plan['plan_digest'] if approved == 'plan' else approved
    monkeypatch.setattr(operator, 'Store', lambda settings: pytest.fail('store accessed'))
    with pytest.raises(operator.Blocked, match=error):
        operator.apply(evidence_file, '1' * 40, operation, plan['source_digest'], approved,
                       int(time.time()) + seconds)


@pytest.mark.parametrize('change', [
    {'repository': 'v71369322-lang/other'},
    {'repository_count_verified': False},
    {'branch_protection_verified': False},
    {'permissions': {'contents': 'write'}},
])
def test_evidence_rejects_wrong_project_or_incomplete_verification(
        evidence_file, change):
    evidence_file.write_text(json.dumps(manifest(**change)), encoding='utf-8')
    with pytest.raises(operator.Blocked, match='manifest_invalid'):
        operator.describe(evidence_file, '1' * 40, str(uuid4()))


def test_evidence_requires_private_mode_and_canonical_operation(evidence_file):
    evidence_file.chmod(0o644)
    with pytest.raises(operator.Blocked, match='evidence_file_mode_required'):
        operator.describe(evidence_file, '1' * 40, str(uuid4()))
    evidence_file.chmod(0o600)
    with pytest.raises(operator.Blocked, match='operation_invalid'):
        operator.describe(evidence_file, '1' * 40, '0' * 36)


def test_inspect_verifies_audit_provenance_without_external_calls(monkeypatch):
    operation = str(uuid4())
    provenance = {'evidence_sha256': 'a' * 64, 'operator_revision': '1' * 40,
                  'plan_digest': 'b' * 64}
    event = {'manifest': manifest(), 'provenance': provenance}

    class FakeStore:
        @contextmanager
        def transaction(self):
            yield 'session'

        def check_audit(self, session):
            assert session == 'session'

    monkeypatch.setattr(operator, 'check_source', lambda revision, expected=None: 'f' * 64)
    monkeypatch.setattr(operator.Settings, 'load', lambda: type(
        'Settings', (), {'source_revision': '1' * 40})())
    monkeypatch.setattr(operator, 'Store', lambda settings: FakeStore())
    monkeypatch.setattr(operator, 'history', lambda session: ({}, {operation: event}))
    monkeypatch.setattr(operator, 'receipt', lambda value: {
        'project_id': 'command-center', 'state': 'VERIFIED_DISABLED',
        'execution_enabled': False, 'paid_ai_enabled': False,
        'merge_enabled': False, 'deployment_enabled': False})
    result = operator.inspect('1' * 40, operation, 'f' * 64)
    assert result['status'] == 'PROJECT_CONNECTION_REGISTRATION_VERIFIED'
    assert result['provenance'] == provenance and result['external_calls'] == 0
    assert result['execution_enabled'] is result['paid_ai_enabled'] is False


def test_source_digest_allows_gitless_container_and_rejects_tampering(monkeypatch):
    value = operator.runtime_source_digest()
    monkeypatch.setattr(operator.subprocess, 'run', lambda *args, **kwargs:
                        pytest.fail('git accessed'))
    assert operator.check_source('1' * 40, value) == value
    with pytest.raises(operator.Blocked, match='operator_source_changed'):
        operator.check_source('1' * 40, '0' * 64)
