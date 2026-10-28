#!/usr/bin/python3
"""Unprivileged mailbox producer, stdlib + system OpenSSL; no runtime/secret access.

Default is validation only. --publish requires the installed host mailbox.
The host operator is the authority; client validation cannot grant permissions.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
from uuid import UUID, uuid4

ROOT = Path('/var/lib/acc-operations')
LIMIT = 16384


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def parse(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicate_json')
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))


def validate(value):
    if not isinstance(value, dict) or set(value) != {'request', 'receipt_public_key'}:
        raise ValueError('submission_schema')
    r = value['request']
    if (not isinstance(r, dict) or set(r) != {'schema', 'operation_id', 'policy_digest', 'action',
            'target_bundle', 'expected_bundle', 'issued_at', 'expires_at'}
            or type(r['schema']) is not int or r['schema'] != 1
            or r['action'] not in ('status', 'update')
            or any(not isinstance(r[k], str) or not re.fullmatch('[a-f0-9]{64}', r[k])
                   for k in ('policy_digest', 'target_bundle', 'expected_bundle'))
            or any(type(r[k]) is not int for k in ('issued_at', 'expires_at'))
            or not 0 < r['expires_at'] - r['issued_at'] <= 900):
        raise ValueError('submission_scope')
    op = UUID(r['operation_id'])
    if op.version != 4 or str(op) != r['operation_id']:
        raise ValueError('submission_id')
    same = r['target_bundle'] == r['expected_bundle']
    if same != (r['action'] == 'status') or len(base64.b64decode(value['receipt_public_key'], validate=True)) != 32:
        raise ValueError('submission_binding')
    return value


def read(path, *, owner=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if (not stat.S_ISREG(meta.st_mode) or meta.st_size > LIMIT or meta.st_nlink != 1
                or (owner is not None and (meta.st_uid != owner or meta.st_mode & 0o022))):
            raise ValueError('submission_file')
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('submission_size')
    return parse(raw)


def verify(envelope, submission):
    if not isinstance(envelope, dict) or set(envelope) != {'receipt', 'signature'}:
        raise ValueError('receipt_schema')
    public = base64.b64decode(submission['receipt_public_key'], validate=True)
    signature = base64.b64decode(envelope['signature'], validate=True)
    if len(public) != 32 or len(signature) != 64:
        raise ValueError('receipt_key_or_signature')
    body = canonical(envelope['receipt'])
    # RFC 8410 SubjectPublicKeyInfo for Ed25519, using standard OpenSSL to verify.
    der = bytes.fromhex('302a300506032b6570032100') + public
    with tempfile.TemporaryDirectory(prefix='acc-receipt-') as directory:
        directory = Path(directory)
        for name, raw in [('public.der', der), ('signature', signature), ('body', body)]:
            (directory / name).write_bytes(raw)
        result = subprocess.run(['/usr/bin/openssl', 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
                                 '-inkey', str(directory / 'public.der'), '-rawin', '-in', str(directory / 'body'),
                                 '-sigfile', str(directory / 'signature')], capture_output=True, check=False,
                                env={'PATH': '/usr/bin:/bin', 'OPENSSL_CONF': '/dev/null'}, timeout=10)
    if result.returncode:
        raise ValueError('receipt_signature')
    record, request = envelope['receipt'], submission['request']
    if (record.get('request_hash') != hashlib.sha256(canonical(request)).hexdigest()
            or any(record.get(k) != request[k] for k in
                   ('operation_id', 'policy_digest', 'action', 'target_bundle', 'expected_bundle'))
            or record.get('state') not in {'SUCCEEDED', 'REJECTED', 'UNCERTAIN'}):
        raise ValueError('receipt_binding')
    return record


def submit(submission, *, root=ROOT, timeout=900, root_uid=0, control_uid=1000):
    validate(submission)
    request = submission['request']
    # Fixed host layout. Neither the root-owned mailbox nor receipt directory
    # may be writable by the runner. No private directory is opened here.
    for path, owner, forbidden in [(root, root_uid, 0o022), (root / 'receipts', control_uid, 0o027),
                                    (root / 'inbox', control_uid, 0o007)]:
        meta = path.lstat()
        if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != owner or meta.st_mode & forbidden:
            raise ValueError('mailbox_custody')
    name = request['operation_id'] + '.json'
    receipt = root / 'receipts' / name
    if not receipt.exists():
        temp = root / 'inbox' / ('.request-' + uuid4().hex)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        os.fchmod(fd, 0o644)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(canonical(request))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp, root / 'inbox' / name, follow_symlinks=False)
            except FileExistsError:
                pass
        finally:
            temp.unlink(missing_ok=True)
    deadline = time.monotonic() + timeout
    while not receipt.exists():
        if time.monotonic() >= deadline:
            raise ValueError('receipt_unconfirmed_no_retry')
        time.sleep(2)
    envelope = read(receipt, owner=control_uid)
    record = verify(envelope, submission)
    return envelope, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-file', required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    try:
        submission = validate(read(args.request_file))
        if args.publish:
            import pwd
            runner = pwd.getpwnam('acc-gh-runner')
            if os.getuid() != runner.pw_uid or runner.pw_uid in {0, 1000, 1001}:
                raise ValueError('runner_identity')
            envelope, record = submit(submission)
            print(json.dumps(envelope, sort_keys=True))
            if record['state'] != 'SUCCEEDED':
                raise ValueError('operation_not_verified')
        else:
            print(json.dumps({'valid': True, 'host_contacted': False,
                              'operation_id': submission['request']['operation_id']}))
    except Exception:
        parser.exit(1, 'operations_submission_unconfirmed; retain operation ID; do not create a blind retry\n')


if __name__ == '__main__':
    main()
