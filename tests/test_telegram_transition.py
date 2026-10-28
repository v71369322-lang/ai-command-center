"""Real isolated legacy PG + restore; fake host orchestration is explicitly scoped."""
import copy
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from test_deployment import release as release
from test_telegram_migration import isolated_pg as isolated_pg, legacy as legacy, KEY

from command_center.deployment import Deployment, migration_hash
from command_center.deployment_profile import atomic_json, checksum, render
from command_center.runtime_policy import RuntimeBackend
from command_center.telegram_migration import fingerprints
from command_center.telegram_transition import TelegramTransition, OLD_SCHEMA, NEW_SCHEMA, OLD_REVISION, migration_job


@pytest.fixture
def transition(release, legacy, tmp_path, monkeypatch):
    admin, container, _ = legacy
    original, directory = release
    base = copy.deepcopy(original['compose'])
    old_m = {**original['manifest'], 'revision': OLD_REVISION, 'migration_hash': OLD_SCHEMA,
             'owner_login': {'origin': 'http://127.0.0.1:18000', 'loopback_http': True}}
    # Render expects normalized source services; already-rendered fields are
    # overwritten by render, including immutable images and secret mounts.
    old = {'manifest': old_m, 'compose': render(base, old_m)}
    old_dir = tmp_path / 'old'
    old_dir.mkdir(mode=0o700)
    atomic_json(old_dir / 'bundle.json', old)
    atomic_json(old_dir / 'compose.json', old['compose'])
    target_m = {**old_m, 'revision': admin.settings.source_revision, 'migration_hash': NEW_SCHEMA}
    target = {'manifest': target_m, 'compose': render(base, target_m)}
    atomic_json(directory / 'bundle.json', target)
    atomic_json(directory / 'compose.json', target['compose'])
    root = tmp_path / 'state'
    old_state = {'phase': 'VERIFIED', 'bundle': checksum(old), 'revision': OLD_REVISION,
                 'migration_hash': OLD_SCHEMA, 'database_image': old_m['database_image'],
                 'directory': str(old_dir), 'previous_bundle': None}
    atomic_json(root / 'deployment.json', old_state)
    calls = []

    class Engine:
        endpoint = 'unix:///var/run/docker.sock'

        def run(self, *args, **kwargs):
            calls.append(args)
            return b''

    engine = Engine()
    current = Deployment(target, directory, engine, engine)
    monkeypatch.setattr(Deployment, 'preflight', lambda self, **kw: None)
    monkeypatch.setattr(Deployment, 'quiesce', lambda self: calls.append(('quiesce',)))
    monkeypatch.setattr(Deployment, 'backup', lambda self: calls.append(('backup',)))
    monkeypatch.setattr(Deployment, 'postcheck', lambda self: {'go_live': False})
    monkeypatch.setattr(Deployment, '_boot_locked', lambda self: {'go_live': False, 'admission_halted': True})
    result = TelegramTransition(current)
    copies = tmp_path / 'copies'
    copies.mkdir(mode=0o700)

    def actual_job(action, approved=None):
        calls.append(('job', action))
        return migration_job(admin, action, approved, KEY, copies,
                             RuntimeBackend(mode='cloud-rootful-test'), container=container)

    result.job = actual_job
    return result, admin, calls, old_state


def state(transition):
    return json.loads((transition.root / 'deployment.json').read_text())


def test_real_migration_transitions_only_after_independent_restore_and_keeps_admission_halted(transition):
    t, admin, calls, before = transition
    approval = checksum(t.current.bundle)
    with pytest.raises(ValueError, match='migration_plan'):
        t.current.apply('update', approval)
    assert not calls
    plan = t.stage(approval, before['bundle'])
    assert state(t)['phase'] == 'TELEGRAM_MIGRATION_PENDING'
    effects = [c for c in calls if c[0] != 'ps']
    assert effects[:2] == [('quiesce',), ('backup',)]
    with admin.transaction() as session:
        baseline = fingerprints(session)
    result = t.apply(approval, plan['plan_digest'])
    assert result['telegram_schema_verified'] and not result['telegram_live_enabled']
    assert state(t)['phase'] == 'VERIFIED' and state(t)['migration_hash'] == NEW_SCHEMA
    with admin.transaction() as session:
        after = fingerprints(session)
        assert {k: v for k, v in after.items() if k != 'audit'} == {k: v for k, v in baseline.items() if k != 'audit'}
    assert calls.count(('job', 'apply')) == 1 and ('job', 'verify') in calls


def test_response_loss_is_reconciled_without_replaying_ddl(transition):
    t, _, calls, before = transition
    approval = checksum(t.current.bundle)
    plan = t.stage(approval, before['bundle'])
    job = t.job

    def lost(action, approved=None):
        result = job(action, approved)
        if action == 'apply':
            raise OSError('synthetic response loss after commit')
        return result

    t.job = lost
    with pytest.raises(OSError):
        t.apply(approval, plan['plan_digest'])
    assert state(t)['phase'] == 'TELEGRAM_MIGRATION_PENDING'
    with pytest.raises(ValueError, match='reconciliation_required'):
        t.apply(approval, plan['plan_digest'])
    assert t.reconcile(approval)['telegram_schema_verified']
    assert calls.count(('job', 'apply')) == 1


def test_wrong_approval_or_plan_cannot_run_ddl(transition):
    t, _, calls, before = transition
    approval = checksum(t.current.bundle)
    with pytest.raises(ValueError, match='exact_disabled_bundle'):
        t.stage('0' * 64, before['bundle'])
    assert not calls
    plan = t.stage(approval, before['bundle'])
    with pytest.raises(ValueError, match='exact_plan'):
        t.apply(approval, '0' * 64)
    assert ('job', 'apply') not in calls and plan['database_modified'] is False


def test_abort_before_ddl_preserves_old_release_and_never_drops_schema(transition):
    t, _, calls, before = transition
    approval = checksum(t.current.bundle)
    t.stage(approval, before['bundle'])
    assert t.abort(approval)['admission_halted']
    assert state(t) == before and ('job', 'apply') not in calls


def test_ambiguous_precommit_failure_cannot_be_mistaken_for_migrated_state(transition):
    t, _, _, before = transition
    approval = checksum(t.current.bundle)
    plan = t.stage(approval, before['bundle'])
    job = t.job

    def unavailable(action, approved=None):
        if action == 'apply':
            raise OSError('synthetic maintenance connection unavailable')
        return job(action, approved)

    t.job = unavailable
    with pytest.raises(OSError):
        t.apply(approval, plan['plan_digest'])
    with pytest.raises(FileNotFoundError):
        t.reconcile(approval)
    assert state(t)['phase'] == 'TELEGRAM_MIGRATION_PENDING'
    assert t.abort(approval)['admission_halted']


def test_cannot_abort_after_migration_committed(transition):
    t, _, _, before = transition
    approval = checksum(t.current.bundle)
    plan = t.stage(approval, before['bundle'])
    job = t.job

    def lost(action, approved=None):
        result = job(action, approved)
        if action == 'apply':
            raise OSError('lost')
        return result

    t.job = lost
    with pytest.raises(OSError):
        t.apply(approval, plan['plan_digest'])
    with pytest.raises(Exception, match='tables_exist'):
        t.abort(approval)
    assert state(t)['phase'] == 'TELEGRAM_MIGRATION_PENDING'


@pytest.mark.parametrize('change', ['database', 'owner', 'source', 'live'])
def test_transition_rejects_unapproved_scope(transition, change):
    t, _, calls, before = transition
    if change == 'database':
        t.current.m['database_image'] = 'different'
    elif change == 'owner':
        t.current.m['owner_login'] = None
    elif change == 'source':
        t.current.m['migration_hash'] = 'f' * 64
    else:
        t.current.m['telegram'] = {'mode': 'live'}
    with pytest.raises(ValueError):
        t.stage(checksum(t.current.bundle), before['bundle'])
    assert all(c[0] == 'ps' for c in calls)


def test_corrupt_backup_blocks_reconciliation_after_commit(transition, tmp_path):
    t, _, _, before = transition
    approval = checksum(t.current.bundle)
    plan = t.stage(approval, before['bundle'])
    job = t.job

    def lost(action, approved=None):
        value = job(action, approved)
        if action == 'apply':
            raise OSError('lost reply')
        return value

    t.job = lost
    with pytest.raises(OSError):
        t.apply(approval, plan['plan_digest'])
    archive = tmp_path / 'copies' / ('before-telegram-' + plan['plan_digest'] + '.enc')
    raw = bytearray(archive.read_bytes())
    raw[-1] ^= 1
    archive.write_bytes(raw)
    with pytest.raises(InvalidTag):
        t.reconcile(approval)
    assert state(t)['phase'] == 'TELEGRAM_MIGRATION_PENDING'


def test_expired_plan_cannot_change_schema_and_can_be_aborted(transition):
    t, _, calls, before = transition
    approval = checksum(t.current.bundle)
    plan = t.stage(approval, before['bundle'])
    journal = json.loads(t.journal.read_text())
    atomic_json(t.journal, {**journal, 'issued_at': '2000-01-01T00:00:00+00:00'})
    with pytest.raises(ValueError, match='approval_expired'):
        t.apply(approval, plan['plan_digest'])
    assert ('job', 'apply') not in calls
    t.abort(approval)
    new = t.stage(approval, before['bundle'])
    assert new['plan_digest'] != plan['plan_digest']
    assert list((t.root / 'telegram-transition-history').glob('*.json'))


def test_final_receipt_write_loss_does_not_repeat_migration(transition, monkeypatch):
    import command_center.telegram_transition as module

    t, _, calls, before = transition
    approval = checksum(t.current.bundle)
    plan = t.stage(approval, before['bundle'])
    actual = module.atomic_json

    def lost(path, value):
        if path == t.journal and value['phase'] == 'VERIFIED':
            raise OSError('local final journal write lost')
        return actual(path, value)

    monkeypatch.setattr(module, 'atomic_json', lost)
    with pytest.raises(OSError):
        t.apply(approval, plan['plan_digest'])
    assert state(t)['phase'] == 'VERIFIED'
    monkeypatch.setattr(module, 'atomic_json', actual)
    assert t.reconcile(approval)['telegram_schema_verified']
    assert calls.count(('job', 'apply')) == 1


def test_known_schema_hash_cannot_silently_expand_with_future_models():
    assert migration_hash(Path(__file__).resolve().parents[1]) == NEW_SCHEMA


def test_unresolved_maintenance_container_blocks_stage_before_mutation(transition, monkeypatch):
    t, _, calls, before = transition
    real = t.current.engine.run

    def busy(*args, **kwargs):
        return b'uncertain-job-id' if args[0] == 'ps' else real(*args, **kwargs)

    monkeypatch.setattr(t.current.engine, 'run', busy)
    with pytest.raises(ValueError, match='job_unresolved'):
        t.stage(checksum(t.current.bundle), before['bundle'])
    assert not calls and state(t) == before


def test_publicly_readable_transition_receipt_is_not_trusted(transition):
    t, _, calls, before = transition
    approval = checksum(t.current.bundle)
    plan = t.stage(approval, before['bundle'])
    t.journal.chmod(0o644)
    with pytest.raises(ValueError, match='custody_invalid'):
        t.apply(approval, plan['plan_digest'])
    assert ('job', 'apply') not in calls
