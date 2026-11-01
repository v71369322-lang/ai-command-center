"""Real local mailbox/SQLite/signatures; simulated deployment backend, no VPS calls."""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from command_center.operations_channel import (
    Blocked, Channel, Journal, Layout, canonical, checksum, protected_read,
    publish, strict_json, validate_policy, validate_request, verify_receipt,
)

OLD, NEW, NOW = 'a' * 64, 'b' * 64, 1800000000
OPS = Path(__file__).resolve().parents[1] / 'operations'


def module(name):
    spec = importlib.util.spec_from_file_location('operations_' + name, OPS / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def mailbox(tmp_path):
    root = tmp_path / 'mailbox'
    root.mkdir(mode=0o755)
    for name, mode in [('inbox', 0o770), ('receipts', 0o750), ('private', 0o700)]:
        (root / name).mkdir(mode=mode)
        (root / name).chmod(mode)
    config = tmp_path / 'config'
    config.mkdir(mode=0o755)
    key = Ed25519PrivateKey.generate()
    private = root / 'private/receipt.key'
    private.write_bytes(key.private_bytes_raw())
    private.chmod(0o600)
    policy = {
        'schema': 1, 'issued_at': NOW - 60, 'expires_at': NOW + 3600,
        'max_operations': 16, 'max_updates': 1,
        'receipt_public_key': base64.b64encode(key.public_key().public_bytes_raw()).decode(),
        'releases': {OLD: {'directory': '/home/acc-control/f32/bundle-telegram', 'revision': 'c' * 40},
                     NEW: {'directory': '/home/acc-control/next/bundle', 'revision': 'd' * 40}},
    }
    path = config / 'policy.json'
    path.write_bytes(canonical(policy))
    path.chmod(0o644)
    # Test-only layout uses the local UID. Production CLI fixes distinct roles.
    layout = Layout(root, path, root_uid=os.getuid(), control_uid=os.getuid(), runner_uid=os.getuid())
    return layout, policy


def request(policy, *, action='update', **fields):
    return dict(schema=1, operation_id=str(uuid4()), policy_digest=checksum(policy), action=action,
                target_bundle=NEW if action == 'update' else OLD, expected_bundle=OLD,
                issued_at=NOW, expires_at=NOW + 120, **fields)


class Backend:
    def __init__(self):
        self.calls = []
        self.fail_prepare = False
        self.fail_execute = False
        self.hook = None

    def factory(self, _):
        return self

    def prepare(self, req):
        if self.fail_prepare:
            raise RuntimeError('DO-NOT-LOG:synthetic-secret')
        if self.hook:
            self.hook()
        return 'prepared'

    def execute(self, req, prepared):
        assert prepared == 'prepared'
        self.calls.append(req['operation_id'])
        if self.fail_execute:
            raise RuntimeError('DO-NOT-LOG:synthetic-secret')


def receipt(layout, policy, req):
    envelope = strict_json((layout.root / 'receipts' / (req['operation_id'] + '.json')).read_bytes())
    return verify_receipt(envelope, req, policy['receipt_public_key'])


def worker(mailbox, backend=None, clock=lambda: NOW):
    layout, _ = mailbox
    backend = backend or Backend()
    return Channel(layout, backend.factory, clock=clock), backend


def test_real_mailbox_signed_success_and_exact_replay(mailbox):
    layout, policy = mailbox
    req = request(policy)
    channel, backend = worker(mailbox)
    publish(layout, req)
    assert channel.drain() == {'processed': 1}
    first = receipt(layout, policy, req)
    assert first['state'] == 'SUCCEEDED' and first['code'] == 'verified'
    publish(layout, req)
    channel.drain()
    assert receipt(layout, policy, req) == first
    assert backend.calls == [req['operation_id']]


@pytest.mark.parametrize('field,value', [
    ('action', 'shell'), ('action', ['update']), ('operation_id', '../escape'),
    ('schema', True), ('target_bundle', 'main'), ('expected_bundle', 'https://evil.invalid'),
    ('policy_digest', 'x' * 64), ('issued_at', True), ('expires_at', NOW + 901),
])
def test_command_and_scope_injection_rejected(mailbox, field, value):
    req = request(mailbox[1])
    req[field] = value
    with pytest.raises(Blocked):
        validate_request(req)


@pytest.mark.parametrize('extra', ['command', 'env', 'url', 'source', 'mounts', 'sudo'])
def test_no_arbitrary_parameters(mailbox, extra):
    req = request(mailbox[1])
    req[extra] = 'anything'
    with pytest.raises(Blocked, match='schema'):
        validate_request(req)


@pytest.mark.parametrize('change,code', [
    ('policy', 'policy_revoked_or_changed'), ('expired', 'authority_expired'),
    ('future', 'authority_expired'), ('bundle', 'bundle_not_approved'),
    ('quota', 'update_limit'),
])
def test_authority_and_budget_fail_closed(mailbox, change, code):
    layout, policy = mailbox
    req = request(policy)
    if change == 'policy':
        policy['expires_at'] += 1
        layout.policy.write_bytes(canonical(policy))
    elif change == 'expired':
        req['issued_at'], req['expires_at'] = NOW - 200, NOW - 80
    elif change == 'future':
        req['issued_at'], req['expires_at'] = NOW + 1, NOW + 121
    elif change == 'bundle':
        req['target_bundle'] = 'f' * 64
    else:
        policy['max_updates'] = 0
        layout.policy.write_bytes(canonical(policy))
        req['policy_digest'] = checksum(policy)
    channel, backend = worker(mailbox)
    publish(layout, req)
    channel.drain()
    result = receipt(layout, policy, req)
    assert result['state'] == 'REJECTED' and result['code'] == code
    assert backend.calls == []


def test_reuse_id_with_changed_payload_preserves_signed_result(mailbox):
    layout, policy = mailbox
    req = request(policy)
    channel, backend = worker(mailbox)
    publish(layout, req)
    channel.drain()
    old = (layout.root / 'receipts' / (req['operation_id'] + '.json')).read_bytes()
    altered = {**req, 'expires_at': req['expires_at'] + 1}
    publish(layout, altered)
    with pytest.raises(Blocked, match='id_reused'):
        channel.drain()
    assert (layout.root / 'receipts' / (req['operation_id'] + '.json')).read_bytes() == old
    assert len(backend.calls) == 1


@pytest.mark.parametrize('stage', ['preflight', 'execute'])
def test_errors_never_disclose_exception_values(mailbox, stage, capsys):
    layout, policy = mailbox
    channel, backend = worker(mailbox)
    backend.fail_prepare = stage == 'preflight'
    backend.fail_execute = stage == 'execute'
    req = request(policy)
    publish(layout, req)
    channel.drain()
    result = receipt(layout, policy, req)
    assert result['state'] == ('REJECTED' if stage == 'preflight' else 'UNCERTAIN')
    assert 'synthetic-secret' not in json.dumps(result) + str(capsys.readouterr())


def test_uncertain_result_blocks_later_update_even_after_policy_renewal(mailbox):
    layout, policy = mailbox
    channel, backend = worker(mailbox)
    backend.fail_execute = True
    first = request(policy)
    publish(layout, first)
    channel.drain()
    backend.fail_execute = False
    policy['expires_at'] += 1
    layout.policy.write_bytes(canonical(policy))
    second = request(policy)
    publish(layout, second)
    channel.drain()
    assert receipt(layout, policy, second)['code'] == 'uncertain_update_requires_owner'
    assert len(backend.calls) == 1
    status = request(policy, action='status')
    publish(layout, status)
    channel.drain()
    assert receipt(layout, policy, status)['state'] == 'SUCCEEDED'


def test_real_process_kill_leaves_durable_uncertain_intent(mailbox):
    layout, policy = mailbox
    req = request(policy)
    publish(layout, req)
    pid = os.fork()
    if pid == 0:
        class Killed(Backend):
            def execute(self, *_):
                os.kill(os.getpid(), signal.SIGKILL)
        Channel(layout, Killed().factory, clock=lambda: NOW).drain()
        os._exit(99)
    _, status = os.waitpid(pid, 0)
    assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
    channel, backend = worker(mailbox)
    channel.drain()
    result = receipt(layout, policy, req)
    assert result['state'] == 'UNCERTAIN' and result['code'] == 'operator_interrupted'
    assert backend.calls == []


def test_revocation_during_preflight_has_no_effect(mailbox):
    layout, policy = mailbox
    channel, backend = worker(mailbox)
    backend.hook = lambda: layout.policy.write_bytes(canonical({**policy, 'expires_at': NOW + 2}))
    req = request(policy)
    publish(layout, req)
    channel.drain()
    assert receipt(layout, policy, req)['code'] == 'authority_changed_during_preflight'
    assert backend.calls == []


def test_expiry_during_preflight_has_no_effect(mailbox):
    layout, policy = mailbox
    clock = [NOW]
    channel, backend = worker(mailbox, clock=lambda: clock[0])
    backend.hook = lambda: clock.__setitem__(0, NOW + 200)
    req = request(policy)
    publish(layout, req)
    channel.drain()
    assert receipt(layout, policy, req)['state'] == 'REJECTED'
    assert backend.calls == []


def test_two_operators_cannot_admit_concurrent_updates(mailbox):
    layout, policy = mailbox
    entered, release = threading.Event(), threading.Event()
    backend = Backend()
    def hold():
        entered.set()
        assert release.wait(5)
    backend.hook = hold
    channel, _ = worker(mailbox, backend)
    publish(layout, request(policy))
    errors = []
    def run():
        try:
            channel.drain()
        except Exception as e:
            errors.append(type(e).__name__)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(BlockingIOError):
            Channel(layout, Backend().factory, clock=lambda: NOW).drain()
    finally:
        release.set()
        thread.join(5)
    assert not errors and len(backend.calls) == 1
    backend.hook = None
    next_req = request(policy)
    publish(layout, next_req)
    channel.drain()
    assert receipt(layout, policy, next_req)['code'] == 'update_limit'
    assert len(backend.calls) == 1


@pytest.mark.parametrize('attack', ['signature', 'result', 'request', 'key'])
def test_forged_receipts_are_rejected(mailbox, attack):
    layout, policy = mailbox
    channel, _ = worker(mailbox)
    req = request(policy)
    publish(layout, req)
    channel.drain()
    envelope = strict_json((layout.root / 'receipts' / (req['operation_id'] + '.json')).read_bytes())
    public = policy['receipt_public_key']
    if attack == 'signature':
        envelope['signature'] = base64.b64encode(b'x' * 64).decode()
    elif attack == 'result':
        envelope['receipt']['target_bundle'] = 'f' * 64
    elif attack == 'request':
        req['expires_at'] += 1
    else:
        public = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode()
    with pytest.raises(Blocked, match='receipt_unverified'):
        verify_receipt(envelope, req, public)


@pytest.mark.parametrize('attack', ['audit', 'projection', 'sqlite'])
def test_corrupt_journal_never_executes_next_request(mailbox, attack):
    layout, policy = mailbox
    channel, backend = worker(mailbox)
    publish(layout, request(policy, action='status'))
    channel.drain()
    path = layout.private / 'journal.sqlite'
    if attack == 'sqlite':
        path.write_bytes(b'corrupt')
    else:
        with sqlite3.connect(path) as db:
            if attack == 'audit':
                db.execute('UPDATE audit SET digest=?', ('e' * 64,))
            else:
                db.execute('DELETE FROM operations')
    publish(layout, request(policy))
    with pytest.raises((Blocked, sqlite3.DatabaseError)):
        channel.drain()
    assert len(backend.calls) == 1


@pytest.mark.parametrize('attack', ['policy_link', 'policy_write', 'key_public', 'inbox_link', 'request_fifo'])
def test_filesystem_boundary_rejected(mailbox, tmp_path, attack):
    layout, policy = mailbox
    channel, backend = worker(mailbox)
    req = request(policy)
    if attack == 'policy_link':
        original = layout.policy.read_bytes()
        layout.policy.unlink()
        other = tmp_path / 'other'
        other.write_bytes(original)
        layout.policy.symlink_to(other)
    elif attack == 'policy_write':
        layout.policy.chmod(0o666)
    elif attack == 'key_public':
        (layout.private / 'receipt.key').chmod(0o644)
    elif attack == 'inbox_link':
        (layout.root / 'inbox').rmdir()
        other = tmp_path / 'other-inbox'
        other.mkdir()
        (layout.root / 'inbox').symlink_to(other)
    else:
        os.mkfifo(layout.root / 'inbox' / (req['operation_id'] + '.json'))
    if attack != 'request_fifo':
        if attack != 'inbox_link':
            publish(layout, req)
    with pytest.raises((Blocked, OSError)):
        channel.drain()
    assert backend.calls == []


@pytest.mark.parametrize('attack', ['path', 'duration', 'updates', 'extra', 'empty', 'bool'])
def test_policy_cannot_expand_into_shell_or_unbounded_stage(mailbox, attack):
    policy = copy.deepcopy(mailbox[1])
    if attack == 'path':
        policy['releases'][NEW]['directory'] = '/home/acc-control/../root'
    elif attack == 'duration':
        policy['expires_at'] = policy['issued_at'] + 8 * 86400
    elif attack == 'updates':
        policy['max_updates'] = 1000
    elif attack == 'extra':
        policy['command'] = 'curl evil.invalid'
    elif attack == 'empty':
        policy['releases'] = {}
    else:
        policy['schema'] = True
    with pytest.raises(Blocked):
        validate_policy(policy)


def test_duplicate_json_nonfinite_and_receipt_custody(mailbox):
    for raw in [b'{"action":"status","action":"update"}', b'{"limit":NaN}']:
        with pytest.raises(Blocked):
            strict_json(raw)
    layout, _ = mailbox
    p = layout.root / 'receipts/test.json'
    p.write_text('{}')
    p.chmod(0o666)
    with pytest.raises(Blocked):
        protected_read(p, os.getuid())


def test_private_journal_is_not_a_runner_requirement(mailbox):
    layout, policy = mailbox
    # Producer only checks shared directories; it never reads the signing key.
    (layout.private / 'receipt.key').unlink()
    publish(layout, request(policy, action='status'))
    assert len(list((layout.root / 'inbox').iterdir())) == 1


def test_second_publish_cannot_replace_pending_intent(mailbox):
    layout, policy = mailbox
    req = request(policy)
    publish(layout, req)
    with pytest.raises(FileExistsError):
        publish(layout, {**req, 'expires_at': req['expires_at'] + 1})
    assert strict_json((layout.root / 'inbox' / (req['operation_id'] + '.json')).read_bytes()) == req


def test_runner_queue_quota_stops_before_backend(mailbox):
    layout, policy = mailbox
    for _ in range(65):
        publish(layout, request(policy, action='status'))
    channel, backend = worker(mailbox)
    with pytest.raises(Blocked, match='inbox_limit'):
        channel.drain()
    assert backend.calls == []


def test_existing_journal_projection_verifies_without_backend(mailbox):
    layout, policy = mailbox
    channel, _ = worker(mailbox)
    req = request(policy)
    publish(layout, req)
    channel.drain()
    journal = Journal(layout.private / 'journal.sqlite')
    try:
        with journal.transaction() as rows:
            assert rows[req['operation_id']]['state'] == 'SUCCEEDED'
    finally:
        journal.db.close()


def test_missing_journal_does_not_reset_replay_history(mailbox):
    layout, policy = mailbox
    channel, backend = worker(mailbox)
    publish(layout, request(policy, action='status'))
    channel.drain()
    (layout.private / 'journal.sqlite').unlink()
    publish(layout, request(policy))
    with pytest.raises(Blocked, match='journal_missing'):
        channel.drain()
    assert len(backend.calls) == 1


@pytest.mark.parametrize('forged', [False, True])
def test_stdlib_producer_verifies_with_real_system_openssl(mailbox, forged):
    layout, policy = mailbox
    channel, _ = worker(mailbox)
    req = request(policy)
    publish(layout, req)
    channel.drain()
    envelope = strict_json((layout.root / 'receipts' / (req['operation_id'] + '.json')).read_bytes())
    submission = {'request': req, 'receipt_public_key': policy['receipt_public_key']}
    producer = module('submit')
    producer.validate(submission)
    if forged:
        envelope['receipt']['state'] = 'REJECTED'
        with pytest.raises(ValueError, match='receipt_signature'):
            producer.verify(envelope, submission)
    else:
        assert producer.verify(envelope, submission)['state'] == 'SUCCEEDED'


def test_real_producer_mailbox_consumer_signed_roundtrip(mailbox):
    layout, policy = mailbox
    channel, backend = worker(mailbox)
    producer = module('submit')
    req = request(policy, action='status')
    submission = {'request': req, 'receipt_public_key': policy['receipt_public_key']}
    errors = []
    def consume():
        try:
            deadline = __import__('time').monotonic() + 5
            while not (layout.root / 'inbox' / (req['operation_id'] + '.json')).exists():
                assert __import__('time').monotonic() < deadline
                __import__('time').sleep(.01)
            # Producer's atomic publication briefly holds a second hardlink.
            while (layout.root / 'inbox' / (req['operation_id'] + '.json')).stat().st_nlink != 1:
                __import__('time').sleep(.01)
            channel.drain()
        except Exception as e:
            errors.append(type(e).__name__)
    thread = threading.Thread(target=consume)
    thread.start()
    try:
        envelope, result = producer.submit(submission, root=layout.root, timeout=5,
                                           root_uid=os.getuid(), control_uid=os.getuid())
        assert result['state'] == 'SUCCEEDED'
        verify_receipt(envelope, req, policy['receipt_public_key'])
    finally:
        thread.join(6)
    assert not errors and len(backend.calls) == 1


def test_producer_dry_run_is_a_real_unprivileged_subprocess(mailbox, tmp_path):
    _, policy = mailbox
    path = tmp_path / 'request.json'
    path.write_bytes(canonical({'request': request(policy), 'receipt_public_key': policy['receipt_public_key']}))
    result = subprocess.run([sys.executable, str(OPS / 'submit.py'), '--request-file', str(path)],
                            capture_output=True, check=True, timeout=10)
    assert json.loads(result.stdout)['host_contacted'] is False


@pytest.mark.parametrize('change', ['extra', 'time', 'updates', 'base', 'path', 'bool'])
def test_enrollment_catalog_rejects_extra_authority(mailbox, change):
    _, policy = mailbox
    value = dict(schema=1, duration_seconds=3600, max_operations=32, max_updates=1,
                 base_bundle=OLD, releases=copy.deepcopy(policy['releases']))
    if change == 'extra':
        value['sudo'] = True
    elif change == 'time':
        value['duration_seconds'] = 8 * 86400
    elif change == 'updates':
        value['max_updates'] = 100
    elif change == 'base':
        value['base_bundle'] = 'c' * 64
    elif change == 'path':
        value['releases'][OLD]['directory'] = '/root/anything'
    else:
        value['schema'] = True
    with pytest.raises(ValueError):
        module('enroll').catalog(value)


def test_enrollment_example_is_status_only_and_excludes_extra_repositories():
    value = module('enroll').read_catalog(OPS / 'catalog.example.json')
    assert value['max_updates'] == 0 and len(value['releases']) == 1
    assert value['base_bundle'] == '0ee8a6023296fdacfe632c2f364c488b2564db399bfd15af357812e41004d64b'


@pytest.fixture
def source_repository(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    paths = ['src/command_center/__init__.py', 'src/command_center/deployment.py',
             'src/command_center/operations_channel.py', 'src/command_center/coding/__init__.py',
             'src/command_center/coding/spec.py', 'infra/vps/operations/submit.py',
             'infra/vps/operations/inbox.mount.template', 'requirements.lock']
    paths += ['infra/vps/operations/' + name for name in module('enroll').UNITS]
    for name in paths:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('# synthetic package data\n')
        target.chmod(0o644)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.DEVNULL)
    git('init', '--quiet', '--template=')
    git('add', '.')
    git('-c', 'user.name=Synthetic Test', '-c', 'user.email=synthetic@example.invalid',
        'commit', '-qm', 'synthetic source snapshot')
    return source, git('rev-parse', 'HEAD').decode().strip()


def test_enrollment_packages_git_objects_not_mutable_worktree(source_repository):
    source, revision = source_repository
    target = source / 'src/command_center/operations_channel.py'
    target.write_text('raise RuntimeError("unreviewed worktree")\n')
    files = module('enroll').package(source, revision)
    assert files['src/command_center/operations_channel.py'] == b'# synthetic package data\n'
    assert files['src/command_center/coding/spec.py'] == b'# synthetic package data\n'
    assert len(files) == 11


def test_enrollment_bounds_git_output_before_copying_or_execution(source_repository):
    source, _ = source_repository
    (source / 'src/command_center/operations_channel.py').write_bytes(b'x' * (9 * 1024 * 1024))
    git = ['git', '-C', str(source)]
    subprocess.run([*git, 'add', '.'], check=True, capture_output=True)
    subprocess.run([*git, '-c', 'user.name=Synthetic Test', '-c', 'user.email=synthetic@example.invalid',
                    'commit', '-qm', 'oversized synthetic source'], check=True, capture_output=True)
    revision = subprocess.check_output([*git, 'rev-parse', 'HEAD']).decode().strip()
    with pytest.raises(ValueError, match='git_output_limit'):
        module('enroll').package(source, revision)


def test_root_git_uses_absolute_runuser_with_restricted_path(monkeypatch, source_repository):
    source, revision = source_repository
    enroll = module('enroll')
    calls = []
    def spawn(command, **kwargs):
        calls.append((command, kwargs['env']))
        assert command[0] == '/usr/sbin/runuser'
        assert os.access(command[0], os.X_OK)
        assert command[4:9] == ['/usr/bin/prlimit', '--as=268435456:268435456',
                                 '--cpu=30:30', '--fsize=8388608:8388608', '--']
        assert kwargs['env']['PATH'] == '/usr/bin:/bin'
        raise OSError('synthetic_stop_before_execution')
    monkeypatch.setattr(enroll.os, 'getuid', lambda: 0)
    monkeypatch.setattr(enroll.subprocess, 'Popen', spawn)
    with pytest.raises(OSError, match='synthetic_stop'):
        enroll.git(source, 'cat-file', 'commit', revision)
    assert len(calls) == 1


def test_enrollment_rejects_tampered_tree_before_install(source_repository, monkeypatch):
    source, revision = source_repository
    enroll = module('enroll')
    original = enroll.git
    def broken(directory, *args):
        if args[:2] == ('cat-file', 'tree'):
            return b'invalid tree'
        return original(directory, *args)
    monkeypatch.setattr(enroll, 'git', broken)
    with pytest.raises(ValueError, match='source_tree_changed'):
        enroll.package(source, revision)


def test_runner_unit_has_no_runtime_or_private_state_authority():
    unit = (OPS / 'acc-operations-runner.service').read_text()
    assert 'User=acc-gh-runner' in unit and 'Group=acc-gh-runner' in unit
    assert 'NoNewPrivileges=yes' in unit and 'CapabilityBoundingSet=\n' in unit
    assert 'InaccessiblePaths=-/run/user -/var/run/docker.sock -/run/docker.sock' in unit
    assert '/var/lib/acc-operations/private /etc/acc-operations' in unit
    assert 'ReadWritePaths=/var/lib/acc-operations/inbox\n' in unit
    assert 'ReadOnlyPaths=/var/lib/acc-gh-runner\n' in unit
    assert 'MemorySwapMax=0' in unit
    assert 'TemporaryFileSystem=/var/lib/acc-gh-runner/runner/_work:size=512M' in unit
    assert '--once' not in unit and 'ExecStart=/var/lib/acc-gh-runner/runner/run.sh\n' in unit


def test_workflow_cannot_start_vps_on_pr_or_ordinary_feature_push():
    text = (OPS.parents[2] / '.github/workflows/bounded-vps-operations.yml').read_text()
    assert 'branches: [ops/bounded-vps-requests]' in text
    assert 'pull_request_target' not in text and 'pull_request:' not in text
    assert "contains(github.event.head_commit.message, '[request-acc-operation]')" in text
    assert 'contents: read' in text and 'cancel-in-progress: false' in text
    assert 'runs-on: [acc-ops-mailbox]' in text
    assert '/usr/local/lib/acc-operations/submit.py' in text


def test_inspect_cli_needs_no_source_or_credentials():
    if os.getuid() == 0:
        pytest.skip('Root behavior is exercised in the isolated Ubuntu fixture')
    result = subprocess.run([sys.executable, '-I', str(OPS / 'enroll.py'), '--inspect'],
                            capture_output=True, check=False, timeout=10)
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output == {'status': 'UNCONFIRMED', 'phase': 'inspect', 'error_type': 'ValueError'}
    assert b'invalid enrollment arguments' not in result.stderr


def test_enrollment_parser_does_not_echo_accidental_credential():
    secret = 'synthetic-do-not-echo-value'
    result = subprocess.run([sys.executable, '-I', str(OPS / 'enroll.py'), '--unexpected', secret],
                            capture_output=True, check=False, timeout=10)
    assert result.returncode == 2
    assert secret.encode() not in result.stdout + result.stderr
    assert b'values not displayed' in result.stderr


def test_inspection_cannot_be_combined_with_install():
    result = subprocess.run([sys.executable, '-I', str(OPS / 'enroll.py'), '--inspect', '--install'],
                            capture_output=True, check=False, timeout=10)
    assert result.returncode == 2
    assert result.stdout == b''
