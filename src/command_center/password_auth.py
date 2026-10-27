"""Single-owner password verifier. Provision offline; never accept hashes via API."""
import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from urllib.parse import urlsplit

ITERATIONS = 600_000


def document(username, password):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', username) or not 15 <= len(password) <= 128:
        raise ValueError('username_3_to_64_ascii_and_password_15_to_128_required')
    salt = secrets.token_bytes(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS)
    return {'schema': 1, 'username': username, 'algorithm': 'pbkdf2-sha256',
            'iterations': ITERATIONS, 'salt': base64.b64encode(salt).decode(),
            'hash': base64.b64encode(value).decode()}


def load(path):
    if not Path(path).is_absolute():
        raise ValueError('absolute_password_file_required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_size > 2048):
            raise ValueError('protected_password_file_required')
        value = json.loads(stream.read(2049))
    if (set(value) != {'schema', 'username', 'algorithm', 'iterations', 'salt', 'hash'}
            or value['schema'] != 1 or value['algorithm'] != 'pbkdf2-sha256'
            or type(value['iterations']) is not int or value['iterations'] != ITERATIONS
            or not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', value['username'])
            or len(base64.b64decode(value['salt'], validate=True)) != 16
            or len(base64.b64decode(value['hash'], validate=True)) != 32):
        raise ValueError('invalid_password_document')
    return value


def verify(value, username, password):
    calculated = hashlib.pbkdf2_hmac('sha256', password.encode(),
                                   base64.b64decode(value['salt']), ITERATIONS)
    valid = hmac.compare_digest(calculated, base64.b64decode(value['hash']))
    return hmac.compare_digest(username.encode(), value['username'].encode()) and valid


def origin_valid(origin, allow_loopback_http=False):
    try:
        url = urlsplit(origin)
        if (origin != f'{url.scheme}://{url.netloc}' or url.username or url.password
                or not url.hostname or url.port == 0):
            return False
        return url.scheme == 'https' or (allow_loopback_http and url.scheme == 'http'
                                         and url.hostname in {'127.0.0.1', 'localhost', '::1'})
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description='Create a private owner verifier; no password CLI argument.')
    parser.add_argument('--file', required=True)
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty():
        raise ValueError('interactive_terminal_required')
    path = Path(args.file)
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError('new_absolute_password_file_required')
    parent = path.parent.stat()
    if parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
        raise ValueError('private_parent_required')
    password = getpass.getpass('Owner password (15–128 characters): ')
    if password != getpass.getpass('Repeat password: '):
        raise ValueError('passwords_do_not_match')
    value = document(args.username, password)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream)
    print('Private owner verifier created; password and verifier not displayed.')


if __name__ == '__main__':
    main()
