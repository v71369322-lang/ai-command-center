"""Local protected bindings for an explicitly approved Telegram release; no HTTP."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import sys
import warnings

from .store import digest
from .telegram_transport import TelegramConnection, connection, private_read


def binding(root, revision, approved):
    config = connection(Path(root) / 'telegram/connection.json')
    if (config.mode != 'live' or config.source_revision != revision
            or config.token_file != '/run/telegram/token' or digest(config.model_dump()) != approved):
        raise ValueError('telegram_release_exact_connection_required')
    return {'mode': config.mode, 'bot_id': config.bot_id, 'owner_id': config.owner_id,
            'connection_digest': approved}


def preflight(manifest):
    expected = manifest['telegram']
    if binding(manifest['data_root'], manifest['revision'], expected['connection_digest']) != expected:
        raise ValueError('telegram_release_scope_changed')
    value = private_read(Path(manifest['data_root']) / 'telegram/token', 256)
    if not re.fullmatch(str(expected['bot_id']).encode() + rb':[A-Za-z0-9_-]{30,128}', value.strip()):
        raise ValueError('telegram_release_credential_binding_invalid')


def provision(directory, revision, owner_id, token):
    """Protected offline provisioning. No API call, existing-file replacement or activation."""
    if not re.fullmatch(r'[0-9]{1,20}:[A-Za-z0-9_-]{30,128}', token):
        raise ValueError('telegram_credential_format_invalid')
    # Fixed in-container file reference, not a credential literal.
    config = TelegramConnection(mode='live', owner_id=owner_id, bot_id=int(token.split(':', 1)[0]),  # nosec B106
                                source_revision=revision, token_file='/run/telegram/token')
    path = Path(directory)
    parent = path.parent.stat()
    if (not path.is_absolute() or path.parent.is_symlink() or path.exists() or path.is_symlink()
            or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
        raise ValueError('telegram_new_private_directory_required')
    path.mkdir(mode=0o700)
    for name, value in [('token', token), ('connection.json', config.model_dump_json())]:
        fd = os.open(path / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    for directory in (path, path.parent):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {'connection_digest': digest(config.model_dump()), 'bot_id': config.bot_id,
            'owner_id': owner_id, 'revision': revision, 'api_contacted': False, 'live_enabled': False}


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid telegram provisioning arguments; values not displayed\n')

    parser = SafeParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--owner-id', type=int, required=True)
    args = parser.parse_args()
    try:
        if not sys.stdin.isatty():
            raise ValueError('interactive_terminal_required')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            token = getpass.getpass('Telegram bot token (hidden; never sent to chat): ')
        print(json.dumps(provision(args.directory, args.revision, args.owner_id, token)))
    except Exception:
        parser.exit(1, 'telegram_provision_unconfirmed; inspect private directory; no API call or activation performed\n')


if __name__ == '__main__':
    main()
