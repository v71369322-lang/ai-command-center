"""Fixed-revision source handoff. No shell input, credentials or install action."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

REVISION = '53565cc2ca232fb2cf6d6552a3ae04b462d92956'
MAX_PACKET = 8 * 1024 * 1024


def git(directory, *args, data=None):
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(directory), 'LANG': 'C.UTF-8',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    return subprocess.check_output(['git', '-C', str(directory), *args],
                                   input=data, env=env, stderr=subprocess.DEVNULL,
                                   timeout=30)


def pack(directory, output):
    rows = git(directory, 'ls-tree', '-rt', REVISION).decode().splitlines()
    objects = {REVISION: 'commit', git(directory, 'rev-parse', REVISION + '^{tree}').decode().strip(): 'tree'}
    for row in rows:
        mode, kind, oid = row.split('\t', 1)[0].split()
        if mode not in {'100644', '100755', '040000'} or kind not in {'tree', 'blob'}:
            raise ValueError('unsupported_source_entry')
        objects[oid] = kind
    packet = {'revision': REVISION, 'objects': [
        {'id': oid, 'type': kind, 'data': base64.b64encode(git(directory, 'cat-file', kind, oid)).decode()}
        for oid, kind in sorted(objects.items())]}
    raw = json.dumps(packet).encode()
    if len(raw) > MAX_PACKET:
        raise ValueError('source_packet_too_large')
    Path(output).write_bytes(raw)


def validate(raw):
    if len(raw) > MAX_PACKET:
        raise ValueError('source_packet_too_large')
    packet = json.loads(raw)
    if set(packet) != {'revision', 'objects'} or packet['revision'] != REVISION:
        raise ValueError('unapproved_revision')
    if not isinstance(packet['objects'], list) or not 1 <= len(packet['objects']) <= 5000:
        raise ValueError('invalid_object_count')
    result = []
    seen = set()
    for item in packet['objects']:
        if set(item) != {'id', 'type', 'data'} or item['type'] not in {'commit', 'tree', 'blob'}:
            raise ValueError('invalid_object')
        data = base64.b64decode(item['data'], validate=True)
        oid = hashlib.sha1(item['type'].encode() + b' ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if item['id'] != oid or oid in seen or (item['type'] == 'commit' and oid != REVISION):
            raise ValueError('source_object_mismatch')
        seen.add(oid)
        result.append((oid, item['type'], data))
    if REVISION not in seen:
        raise ValueError('source_commit_missing')
    return result


def hydrate(packet_file, destination):
    # Snapshot a bounded regular file, never a symlink/device/FIFO or live Git repo.
    fd = os.open(packet_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_PACKET:
            raise ValueError('invalid_packet_file')
        objects = validate(stream.read(MAX_PACKET + 1))
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('source_destination_exists')
    # Private parent belongs to acc-control. Runner cannot alter the checkout.
    if destination.parent.stat().st_uid != os.getuid() or destination.parent.stat().st_mode & 0o077:
        raise ValueError('source_parent_not_private')
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        git(directory, 'init', '--quiet', '--template=')
        for oid, kind, data in objects:
            actual = git(directory, 'hash-object', '-w', '-t', kind, '--stdin', data=data).decode().strip()
            if actual != oid:
                raise ValueError('git_object_mismatch')
        Path(directory, '.git/shallow').write_text(REVISION + '\n')
        git(directory, 'fsck', '--strict', '--no-reflogs', REVISION)
        git(directory, '-c', 'core.hooksPath=/dev/null', 'checkout', '--detach', REVISION)
        if git(directory, 'status', '--porcelain').strip():
            raise ValueError('unclean_source')
        os.rename(directory, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['pack', 'hydrate'])
    parser.add_argument('input')
    parser.add_argument('output')
    args = parser.parse_args()
    (pack if args.action == 'pack' else hydrate)(args.input, args.output)


if __name__ == '__main__':
    main()
