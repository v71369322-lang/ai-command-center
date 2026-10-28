#!/usr/bin/python3
"""Offline, root-approved enrollment; default plan does not install or contact VPS.

Run only on the host, after separate approval of source SHA and catalog digest.
Never execute this script as root from a runner-writable file: first snapshot
it and verify the separately reviewed SHA-256, as with F32 bootstrap.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import resource
import selectors
import signal
import socket
import stat
import subprocess
import time

LIB = Path('/usr/local/lib/acc-operations')
ETC = Path('/etc/acc-operations')
STATE = Path('/var/lib/acc-operations')
UNITS = ('acc-operations.service', 'acc-operations.timer', 'acc-operations-runner.service')
MOUNT_UNIT = r'var-lib-acc\x2doperations-inbox.mount'
TOOLS = '/home/acc-control/f30/tools/bin/python'
BASE_STATE = Path('/home/acc-control/f30/state/deployment.json')
KEY_PROGRAM = '''import base64,os,sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
k=Ed25519PrivateKey.generate()
fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:
 f.write(k.private_bytes_raw());f.flush();os.fsync(f.fileno())
print(base64.b64encode(k.public_key().public_bytes_raw()).decode())
'''


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def catalog(value):
    if (not isinstance(value, dict) or set(value) != {'schema', 'duration_seconds', 'max_operations',
            'max_updates', 'base_bundle', 'releases'} or type(value['schema']) is not int or value['schema'] != 1
            or any(type(value[k]) is not int for k in ('duration_seconds', 'max_operations', 'max_updates'))
            or not 60 <= value['duration_seconds'] <= 7 * 86400
            or not 1 <= value['max_operations'] <= 256 or not 0 <= value['max_updates'] <= 10
            or not isinstance(value['base_bundle'], str) or not re.fullmatch('[a-f0-9]{64}', value['base_bundle'])
            or not isinstance(value['releases'], dict) or value['base_bundle'] not in value['releases']
            or not 1 <= len(value['releases']) <= 16):
        raise ValueError('catalog_scope')
    for digest, item in value['releases'].items():
        if (not re.fullmatch('[a-f0-9]{64}', digest) or not isinstance(item, dict)
                or set(item) != {'directory', 'revision'} or not isinstance(item['revision'], str)
                or not re.fullmatch('[a-f0-9]{40}', item['revision']) or not isinstance(item['directory'], str)
                or not re.fullmatch(r'/home/acc-control/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+', item['directory'])):
            raise ValueError('catalog_release')
    return value


def read_catalog(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > 16384:
            raise ValueError('catalog_file')
        raw = stream.read(16385)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('catalog_duplicate_key')
            result[key] = value
        return result
    return catalog(json.loads(raw, object_pairs_hook=pairs))


def git(source, *args):
    # Git parses the runner's repository as the runner, never as root. Neither
    # Git configuration nor Python from acc-control executes with root rights.
    command = ['git', '--no-replace-objects', '-c', 'safe.directory=*', '-C', str(source), *args]
    if os.getuid() == 0:
        command = ['runuser', '-u', 'acc-gh-runner', '--', *command]
    env = {
        'PATH': '/usr/bin:/bin', 'HOME': '/var/lib/acc-gh-runner', 'LANG': 'C.UTF-8',
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1',
        'GIT_PAGER': 'cat', 'GIT_ALLOW_PROTOCOL': '', 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'}
    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               start_new_session=True, preexec_fn=limits)
    output = bytearray()
    deadline = time.monotonic() + 30
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise ValueError('git_read_timeout')
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    if process.wait(timeout=max(.1, deadline - time.monotonic())):
                        raise ValueError('git_read_failed')
                    return bytes(output)
                output.extend(chunk)
                if len(output) > 8 * 1024 * 1024:
                    raise ValueError('git_output_limit')
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        process.stdout.close()


def package(source, revision):
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('exact_source_revision_required')
    commit = git(source, 'cat-file', 'commit', revision)
    if hashlib.sha1(b'commit ' + str(len(commit)).encode() + b'\0' + commit, usedforsecurity=False).hexdigest() != revision:
        raise ValueError('source_commit_changed')
    root = commit.splitlines()[0].decode().removeprefix('tree ')
    rows = git(source, 'ls-tree', '-rt', revision).decode().splitlines()
    if not re.fullmatch('[a-f0-9]{40}', root) or len(rows) > 4096:
        raise ValueError('source_tree_invalid')
    tree_ids = {root}
    for row in rows:
        header, _ = row.split('\t', 1)
        _, kind, oid = header.split()
        if kind == 'tree':
            tree_ids.add(oid)
    for oid in tree_ids:
        raw = git(source, 'cat-file', 'tree', oid)
        if (len(raw) > 1024 * 1024 or hashlib.sha1(
                b'tree ' + str(len(raw)).encode() + b'\0' + raw, usedforsecurity=False).hexdigest() != oid):
            raise ValueError('source_tree_changed')
    result = {}
    for row in rows:
        header, name = row.split('\t', 1)
        mode, kind, oid = header.split()
        wanted = (bool(re.fullmatch(r'src/command_center/(?:[a-z_][a-z0-9_]*/)*[a-z_][a-z0-9_]*\.py', name))
                  or name in {'infra/vps/operations/' + unit for unit in UNITS}
                  or name in {'infra/vps/operations/submit.py', 'infra/vps/operations/inbox.mount.template',
                              'requirements.lock'})
        if not wanted:
            continue
        if mode != '100644' or kind != 'blob':
            raise ValueError('source_entry_type')
        raw = git(source, 'cat-file', 'blob', oid)
        if (len(raw) > 1024 * 1024 or hashlib.sha1(
                b'blob ' + str(len(raw)).encode() + b'\0' + raw, usedforsecurity=False).hexdigest() != oid):
            raise ValueError('source_blob_changed')
        result[name] = raw
    required = {'src/command_center/operations_channel.py', 'src/command_center/deployment.py', 'requirements.lock',
                'infra/vps/operations/submit.py',
                'infra/vps/operations/inbox.mount.template',
                'src/command_center/__init__.py'} | {'infra/vps/operations/' + unit for unit in UNITS}
    if not required <= result.keys() or len(result) > 128 or sum(map(len, result.values())) > 8 * 1024 * 1024:
        raise ValueError('source_package_incomplete')
    return result


def install(files, scope, revision):
    if os.getuid() != 0 or socket.gethostname().split('.')[0] != 'brain1':
        raise ValueError('explicit_host_administrator_required')
    control, execution, runner = (pwd.getpwnam(name) for name in ('acc-control', 'acc-exec', 'acc-gh-runner'))
    if (control.pw_uid != 1000 or execution.pw_uid != 1001 or runner.pw_uid in {0, 1000, 1001}
            or runner.pw_gid in {0, control.pw_gid, execution.pw_gid}):
        raise ValueError('host_roles_changed')
    if os.getgrouplist(runner.pw_name, runner.pw_gid) != [runner.pw_gid]:
        raise ValueError('runner_supplementary_groups_require_review')
    for target in (LIB, ETC, STATE, *(Path('/etc/systemd/system') / unit for unit in (*UNITS, MOUNT_UNIT))):
        if target.exists() or target.is_symlink():
            raise ValueError('existing_channel_requires_reconciliation')
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'acc-gh-runner.service'], check=False).returncode == 0:
        raise ValueError('one_job_runner_still_active')
    if Path('/var/lib/acc-gh-runner/runner/.runner').exists():
        raise ValueError('existing_runner_registration_requires_review')
    state = json.loads(BASE_STATE.read_bytes())
    if state.get('phase') != 'VERIFIED' or state.get('bundle') != scope['base_bundle']:
        raise ValueError('host_baseline_changed')
    if files['requirements.lock'] != Path('/home/acc-control/f32/source/requirements.lock').read_bytes():
        raise ValueError('operator_dependencies_require_separate_review')
    if not Path('/usr/bin/openssl').is_file():
        raise ValueError('system_openssl_required')
    LIB.mkdir(mode=0o755)
    ETC.mkdir(mode=0o755)
    STATE.mkdir(mode=0o755)
    for name, mode, gid in [('inbox', 0o2770, runner.pw_gid), ('receipts', 0o2750, runner.pw_gid),
                            ('private', 0o700, control.pw_gid)]:
        path = STATE / name
        path.mkdir(mode=mode)
        os.chown(path, control.pw_uid, gid)
        path.chmod(mode)
    for name, raw in files.items():
        if name.startswith('src/'):
            target = LIB / 'source' / name
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o444)
        elif name.endswith('/submit.py'):
            target = LIB / 'submit.py'
            target.write_bytes(raw)
            target.chmod(0o444)
        elif name.endswith('/inbox.mount.template'):
            target = Path('/etc/systemd/system') / MOUNT_UNIT
            target.write_bytes(raw.replace(b'__RUNNER_GID__', str(runner.pw_gid).encode()))
            target.chmod(0o644)
        elif name != 'requirements.lock':
            target = Path('/etc/systemd/system') / Path(name).name
            target.write_bytes(raw)
            target.chmod(0o644)
    public = subprocess.check_output(['runuser', '-u', 'acc-control', '--', TOOLS, '-c', KEY_PROGRAM,
                                     str(STATE / 'private/receipt.key')], env={
        'PATH': '/usr/bin:/bin', 'HOME': '/home/acc-control', 'PYTHONNOUSERSITE': '1'},
        stderr=subprocess.DEVNULL, timeout=30).decode().strip()
    if len(base64.b64decode(public, validate=True)) != 32:
        raise ValueError('receipt_key_generation_unconfirmed')
    now = int(time.time())
    policy = dict(schema=1, issued_at=now, expires_at=now + scope['duration_seconds'],
                  max_operations=scope['max_operations'], max_updates=scope['max_updates'],
                  receipt_public_key=public, releases=scope['releases'])
    (ETC / 'policy.json').write_bytes(canonical(policy))
    (ETC / 'policy.json').chmod(0o644)
    enrollment = dict(source_revision=revision, policy_digest=hashlib.sha256(canonical(policy)).hexdigest(),
                      receipt_public_key=public, expires_at=policy['expires_at'],
                      installed=True, services_started=False, runner_registered=False)
    (ETC / 'enrollment.json').write_bytes(canonical(enrollment))
    (ETC / 'enrollment.json').chmod(0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=30)
    return enrollment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--approved-source', required=True)
    parser.add_argument('--catalog-file', required=True)
    parser.add_argument('--approved-catalog')
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    try:
        scope = read_catalog(args.catalog_file)
        digest = hashlib.sha256(canonical(scope)).hexdigest()
        files = package(args.source, args.approved_source)
        if args.install:
            if args.approved_catalog != digest:
                raise ValueError('exact_catalog_approval_required')
            result = install(files, scope, args.approved_source)
        else:
            result = dict(source_revision=args.approved_source, catalog_digest=digest, files=len(files),
                          max_updates=scope['max_updates'], changes_host=False, services_started=False)
        print(json.dumps(result, sort_keys=True))
    except Exception:
        parser.exit(1, 'operations_enrollment_unconfirmed; inspect existing files; do not overwrite or retry blindly\n')


if __name__ == '__main__':
    main()
