"""Networkless Ubuntu proof of distinct OS users; synthetic backend, NOT deployment."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from command_center.operations_channel import Channel, Layout, canonical, checksum
import enroll

ROOT = Path('/var/lib/acc-operations')
POLICY = Path('/etc/acc-operations/policy.json')
OLD, NEW = 'a' * 64, 'b' * 64


class SyntheticBackend:
    def prepare(self, request):
        return request

    def execute(self, request, prepared):
        if request != prepared:
            raise ValueError('synthetic_binding_changed')
        count = ROOT / 'private/synthetic_executions'
        count.write_text(str(int(count.read_text()) + 1 if count.exists() else 1))


def role(uid, args, *, wait=True):
    options = dict(user=uid, group=uid, extra_groups=[], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': '/opt/proof/src',
                        'PYTHONDONTWRITEBYTECODE': '1', 'HOME': '/nonexistent'})
    command = ['/usr/bin/python3', *args]
    if wait:
        return subprocess.run(command, **options, check=False, timeout=30)
    return subprocess.Popen(command, **options)


def installation_lifecycle():
    """Real root filesystem/UID/key lifecycle; systemd and baseline are synthetic."""
    if os.getuid() != 0:
        raise ValueError('test_root_required')
    fixture = Path('/var/lib/enrollment-proof')
    fixture.mkdir(mode=0o755)
    fixture.chmod(0o755)
    enroll.LIB, enroll.ETC, enroll.STATE = (fixture / name for name in ('lib', 'etc', 'state'))
    enroll.SYSTEMD = fixture / 'units'
    enroll.SYSTEMD.mkdir(mode=0o755)
    enroll.BASE_STATE = fixture / 'baseline.json'
    enroll.DEPENDENCY_LOCK = fixture / 'requirements.lock'
    enroll.TOOLS = '/usr/bin/python3'
    if enroll.inspect_enrollment()['phase'] != 'NOT_INSTALLED':
        raise ValueError('test_empty_inspection')
    # An incomplete filesystem must not be reported as installed or repaired.
    enroll.LIB.mkdir(mode=0o700)
    if enroll.inspect_enrollment()['phase'] != 'PARTIAL_OR_UNVERIFIED':
        raise ValueError('test_partial_inspection')
    enroll.LIB.rmdir()
    source = Path('/run/synthetic-source')
    source.mkdir(mode=0o700)
    os.chown(source, 2000, 2000)
    generated = role(2000, [__file__, 'source'])
    if generated.returncode:
        raise ValueError('test_source_creation')
    sha = generated.stdout.decode().strip()
    files = enroll.package(source, sha)
    enroll.DEPENDENCY_LOCK.write_bytes(files['requirements.lock'])
    enroll.BASE_STATE.write_bytes(canonical({'phase': 'VERIFIED', 'bundle': OLD}))
    scope = dict(schema=1, duration_seconds=3600, max_operations=32, max_updates=0,
                 base_bundle=OLD, releases={OLD: {'directory': '/home/acc-control/old/bundle', 'revision': 'c' * 40}})
    real_run, manager_calls = subprocess.run, []
    def manager(argv, **kwargs):
        if argv[0] == 'systemctl':
            manager_calls.append(tuple(argv))
            return SimpleNamespace(returncode=3 if 'is-active' in argv else 0)
        return real_run(argv, **kwargs)
    subprocess.run = manager
    old_mask = os.umask(0o077)
    try:
        enrolled = enroll.install(files, scope, sha)
        if enrolled['services_started'] or enrolled['runner_registered']:
            raise ValueError('test_install_activated_services')
        key = enroll.STATE / 'private/receipt.key'
        before = key.stat().st_mtime_ns
        read_program = 'import sys;open(sys.argv[1],"rb").read(1);print("READABLE")'
        readable = role(1000, ['-c', read_program, str(enroll.LIB / 'source/src/command_center/coding/spec.py')])
        if readable.returncode or readable.stdout.strip() != b'READABLE':
            raise ValueError('test_umask_077_blocks_public_package')
        # Inspection must never open the key or invoke any external command.
        real_open, real_path_open, real_popen = os.open, Path.open, subprocess.Popen
        def guarded_open(path, *args, **kwargs):
            if str(path) == str(key):
                raise AssertionError('test_inspection_read_private_key')
            return real_open(path, *args, **kwargs)
        def guarded_path_open(path, *args, **kwargs):
            if path == key:
                raise AssertionError('test_inspection_read_private_key')
            return real_path_open(path, *args, **kwargs)
        def no_process(*args, **kwargs):
            raise AssertionError('test_inspection_started_process')
        os.open, Path.open, subprocess.Popen = guarded_open, guarded_path_open, no_process
        try:
            inspected = enroll.inspect_enrollment()
        finally:
            os.open, Path.open, subprocess.Popen = real_open, real_path_open, real_popen
        if (inspected['phase'] != 'FILES_PRESENT_RUNTIME_UNVERIFIED' or not inspected['policy_active']
                or inspected['runtime_checked'] or inspected['credentials_read'] or inspected['changes_host']):
            raise ValueError('test_metadata_inspection')
        original_time = enroll.time.time
        enroll.time.time = lambda: enrolled['expires_at'] + 1
        try:
            if enroll.inspect_enrollment().get('policy_active') is not False:
                raise ValueError('test_expired_policy')
        finally:
            enroll.time.time = original_time
        try:
            enroll.install(files, scope, sha)
        except ValueError as error:
            if str(error) != 'existing_channel_requires_reconciliation':
                raise
        else:
            raise ValueError('test_install_replaced_existing_state')
        after = json.loads((enroll.ETC / 'enrollment.json').read_bytes())
        if after != enrolled or key.stat().st_mtime_ns != before:
            raise ValueError('test_repeat_reset_key_or_policy')
        key.chmod(0o644)
        if enroll.inspect_enrollment()['phase'] != 'PARTIAL_OR_UNVERIFIED':
            raise ValueError('test_inspection_accepted_public_key_file')
        key.chmod(0o600)
        if manager_calls != [('systemctl', 'is-active', '--quiet', 'acc-gh-runner.service'),
                              ('systemctl', 'daemon-reload')]:
            raise ValueError('test_unexpected_service_operation')
        print(json.dumps({'status': 'PASS', 'root_install_umask_077': True, 'inspection_read_only': True,
                          'repeat_preserved_key_and_expiry': True, 'systemd': 'synthetic',
                          'services_started': False, 'vps_test': False}))
    finally:
        os.umask(old_mask)
        subprocess.run = real_run


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == 'install-lifecycle':
            installation_lifecycle()
        elif sys.argv[1] == 'operator':
            if os.getuid() != 1000:
                raise ValueError('test_operator_identity')
            print(json.dumps(Channel(Layout(ROOT, POLICY, runner_uid=2000),
                                     lambda _: SyntheticBackend()).drain()))
        elif sys.argv[1] == 'denied':
            if os.getuid() != 2000:
                raise ValueError('test_runner_identity')
            cases = [(ROOT / 'private/receipt.key', 'rb'), (POLICY, 'wb'),
                     (ROOT / 'receipts/forged.json', 'wb'), (Path('/run/user/1000/docker.sock'), 'rb')]
            for path, mode in cases:
                try:
                    with open(path, mode):
                        pass
                except PermissionError:
                    continue
                raise ValueError('test_runner_privilege_leak')
            print('DENIED_AS_EXPECTED')
        elif sys.argv[1] == 'count':
            print((ROOT / 'private/synthetic_executions').read_text())
        elif sys.argv[1] == 'source':
            if os.getuid() != 2000:
                raise ValueError('test_source_identity')
            source = Path('/run/synthetic-source')
            names = ['src/command_center/__init__.py', 'src/command_center/deployment.py',
                     'src/command_center/operations_channel.py', 'src/command_center/coding/__init__.py',
                     'src/command_center/coding/spec.py', 'requirements.lock',
                     'infra/vps/operations/submit.py', 'infra/vps/operations/inbox.mount.template']
            names += ['infra/vps/operations/' + name for name in enroll.UNITS]
            for name in names:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# synthetic data, never executed\n')
                path.chmod(0o644)
            def git(*args):
                return subprocess.check_output(['/usr/bin/git', '-C', str(source), *args],
                                               stderr=subprocess.DEVNULL, timeout=10)
            git('init', '--quiet', '--template=')
            git('add', '.')
            git('-c', 'user.name=Synthetic Test', '-c', 'user.email=synthetic@example.invalid',
                'commit', '-qm', 'synthetic source')
            print(git('rev-parse', 'HEAD').decode().strip())
        else:
            raise ValueError('test_action')
        return
    if os.getuid() != 0:
        raise ValueError('test_root_fixture_required')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '24.04':
        raise ValueError('test_ubuntu_release')
    source = Path('/run/synthetic-source')
    source.mkdir(mode=0o700)
    os.chown(source, 2000, 2000)
    generated = role(2000, [__file__, 'source'])
    if generated.returncode:
        raise ValueError('test_source_creation')
    sha = generated.stdout.decode().strip()
    planned = subprocess.run(['/usr/bin/python3', '-I', '/opt/proof/enroll.py', '--source', str(source),
                              '--approved-source', sha, '--catalog-file', '/opt/proof/catalog.json'],
                             env={'PATH': '/usr/bin:/bin', 'HOME': '/'},
                             capture_output=True, check=False, timeout=60)
    if planned.returncode or json.loads(planned.stdout).get('changes_host') is not False:
        raise ValueError('test_root_enrollment_plan_with_restricted_path')
    for name, mode, gid in [('inbox', 0o2770, 2000), ('receipts', 0o2750, 2000), ('private', 0o700, 1000)]:
        path = ROOT / name
        path.mkdir(mode=mode)
        path.chmod(mode)
        os.chown(path, 1000, gid)
    key = Ed25519PrivateKey.generate()
    # Open the private key as its future owner; root never needs DAC_OVERRIDE.
    encoded = base64.b64encode(key.private_bytes_raw()).decode()
    create = ('import base64,os,sys;p=sys.argv[1];'
              'fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);'
              'os.write(fd,base64.b64decode(sys.stdin.buffer.read()));os.close(fd)')
    result = subprocess.run(['/usr/bin/python3', '-c', create, str(ROOT / 'private/receipt.key')],
                            input=encoded.encode(), user=1000, group=1000, extra_groups=[],
                            capture_output=True, check=False, timeout=10)
    if result.returncode:
        raise ValueError('test_key_creation')
    generated_key = subprocess.run(['/usr/sbin/runuser', '-u', 'acc-control', '--', '/usr/bin/python3',
                                    '-c', enroll.KEY_PROGRAM, str(ROOT / 'private/enrollment-test.key')],
                                   env={'PATH': '/usr/bin:/bin', 'HOME': '/'},
                                   capture_output=True, check=False, timeout=20)
    if generated_key.returncode or len(base64.b64decode(generated_key.stdout.strip(), validate=True)) != 32:
        raise ValueError('test_root_enrollment_key_generation')
    now = int(time.time())
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode()
    policy = dict(schema=1, issued_at=now - 5, expires_at=now + 600, max_operations=8, max_updates=1,
                  receipt_public_key=public, releases={
                      OLD: {'directory': '/home/acc-control/old/bundle', 'revision': 'c' * 40},
                      NEW: {'directory': '/home/acc-control/new/bundle', 'revision': 'd' * 40}})
    POLICY.write_bytes(canonical(policy))
    POLICY.chmod(0o644)
    runtime = Path('/run/user/1000')
    runtime.mkdir(parents=True)
    (runtime / 'docker.sock').write_text('synthetic inaccessible socket placeholder')
    runtime.chmod(0o700)
    os.chown(runtime, 1000, 1000)
    denied = role(2000, [__file__, 'denied'])
    if denied.returncode or denied.stdout.strip() != b'DENIED_AS_EXPECTED':
        raise ValueError('test_runner_access_boundary')
    request = dict(schema=1, operation_id=str(uuid4()), policy_digest=checksum(policy), action='update',
                   target_bundle=NEW, expected_bundle=OLD, issued_at=now, expires_at=now + 120)
    request_file = Path('/run/submission.json')
    request_file.write_bytes(canonical({'request': request, 'receipt_public_key': public}))
    request_file.chmod(0o644)
    producer = role(2000, ['/opt/proof/submit.py', '--request-file', str(request_file), '--publish'], wait=False)
    try:
        inbox = ROOT / 'inbox' / (request['operation_id'] + '.json')
        deadline = time.monotonic() + 10
        # Root cannot read acc-control's group-restricted inbox: use the runner.
        exists = 'import os,sys;p=sys.argv[1];sys.exit(not(os.path.isfile(p) and os.stat(p).st_nlink==1))'
        while role(2000, ['-c', exists, str(inbox)]).returncode:
            if time.monotonic() > deadline:
                raise ValueError('test_publication_timeout')
            time.sleep(.02)
        applied = role(1000, [__file__, 'operator'])
        if applied.returncode:
            raise ValueError('test_operator_failed')
        stdout, _ = producer.communicate(timeout=20)
        if producer.returncode or json.loads(stdout)['receipt']['state'] != 'SUCCEEDED':
            raise ValueError('test_signed_receipt_roundtrip')
        repeated = role(2000, ['/opt/proof/submit.py', '--request-file', str(request_file), '--publish'])
        count = role(1000, [__file__, 'count'])
        if repeated.returncode or count.returncode or count.stdout.strip() != b'1':
            raise ValueError('test_duplicate_execution')
        print(json.dumps({'status': 'PASS', 'ubuntu': '24.04', 'actual_uids': [1000, 2000],
                          'root_enrollment_plan': True, 'root_enrollment_key_generation': True,
                          'runner_private_key_policy_receipts_runtime_denied': True,
                          'signed_roundtrip': True, 'duplicate_executions': 0,
                          'backend': 'synthetic', 'vps_test': False}))
    finally:
        if producer.poll() is None:
            producer.kill()
            producer.wait(timeout=5)


if __name__ == '__main__':
    main()
