"""Networkless Ubuntu proof of distinct OS users; synthetic backend, NOT deployment."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from command_center.operations_channel import Channel, Layout, canonical, checksum

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


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == 'operator':
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
        else:
            raise ValueError('test_action')
        return
    if os.getuid() != 0:
        raise ValueError('test_root_fixture_required')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '24.04':
        raise ValueError('test_ubuntu_release')
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
                          'runner_private_key_policy_receipts_runtime_denied': True,
                          'signed_roundtrip': True, 'duplicate_executions': 0,
                          'backend': 'synthetic', 'vps_test': False}))
    finally:
        if producer.poll() is None:
            producer.kill()
            producer.wait(timeout=5)


if __name__ == '__main__':
    main()
