"""Optional read-only Calendar custody, pinned to the Telegram owner and release."""
import hashlib
import os
from pathlib import Path

from .google_script_calendar import ScriptRuntimeConfig
from .store import digest
from .telegram_transport import private_read

CONFIG = '/run/calendar/connection.json'
KEY = '/run/calendar/calendar.key'
WRITE_CONFIG = '/run/calendar/write-connection.json'
WRITE_KEY = '/run/calendar/write.key'


def validate_binding(m):
    binding = m['calendar_script']
    if (m.get('assistant_only') is not True or 'telegram' not in m
            or not isinstance(binding, dict)
            or set(binding) not in ({'directory', 'profile', 'config_sha256'},
                                   {'directory', 'profile', 'config_sha256', 'write'})):
        raise ValueError('calendar_assistant_binding_required')
    config = ScriptRuntimeConfig.model_validate({'profile': binding['profile'], 'key_file': KEY})
    profile = config.profile
    directory = Path(binding['directory'])
    if (not profile.enabled or profile.source_revision != m['revision']
            or profile.owner_id != m['telegram']['owner_id']
            or not directory.is_absolute() or '..' in directory.parts
            or not directory.is_relative_to(Path(m['data_root']) / 'calendar')
            or binding['config_sha256'] != digest(config.model_dump())):
        raise ValueError('calendar_exact_release_binding_required')
    if 'write' in binding:
        validate_write(m)
    return config


def validate_write(m):
    from .google_script_calendar_write import ScriptWriteConfig
    binding = m['calendar_script']['write']
    if not isinstance(binding, dict) or set(binding) != {'directory', 'profile', 'config_sha256'}:
        raise ValueError('calendar_write_exact_binding_required')
    config = ScriptWriteConfig.model_validate({'profile': binding['profile'], 'key_file': WRITE_KEY})
    p = config.profile
    directory = Path(binding['directory'])
    read = m['calendar_script']['profile']
    if (not p.enabled or not p.create_enabled or p.owner_id != m['telegram']['owner_id']
            or p.source_revision != m['revision'] or binding['config_sha256'] != digest(config.model_dump())
            or not directory.is_absolute() or '..' in directory.parts
            or not directory.is_relative_to(Path(m['data_root']) / 'calendar')
            or str(directory) == m['calendar_script']['directory']
            or p.calendar_id == 'primary' or p.deployment_id == read['deployment_id']
            or p.key_fingerprint == read['key_fingerprint'] or p.connection_id == read['connection_id']):
        raise ValueError('calendar_write_exact_binding_required')
    return config


def check_binding(m):
    config = validate_binding(m)
    directory = Path(m['calendar_script']['directory'])
    root = Path(m['data_root'])
    for parent in (directory, *directory.parents):
        info = parent.lstat()
        if parent.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('calendar_private_parent_required')
        if parent == root:
            break
    actual = ScriptRuntimeConfig.model_validate_json(private_read(directory / 'connection.json', 8192))
    key = private_read(directory / 'calendar.key', 32)
    if (actual != config or len(key) != 32
            or hashlib.sha256(key).hexdigest() != config.profile.key_fingerprint):
        raise ValueError('calendar_custody_changed')
    if 'write' in m['calendar_script']:
        write = validate_write(m)
        parent = Path(m['calendar_script']['write']['directory'])
        for item in (parent, *parent.parents):
            info = item.lstat()
            if item.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('calendar_private_parent_required')
            if item == root:
                break
        from .google_script_calendar_write import ScriptWriteConfig
        actual = ScriptWriteConfig.model_validate_json(private_read(parent / 'connection.json', 8192))
        key = private_read(parent / 'calendar.key', 32)
        if actual != write or len(key) != 32 or hashlib.sha256(key).hexdigest() != write.profile.key_fingerprint:
            raise ValueError('calendar_write_custody_changed')
    return config


def mounts(m):
    validate_binding(m)
    # Separate exact files: do not expose other contents of the custody directory.
    result = [{'type': 'bind', 'source': str(Path(m['calendar_script']['directory']) / name),
             'target': target, 'read_only': True}
            for name, target in [('connection.json', CONFIG), ('calendar.key', KEY)]]
    if 'write' in m['calendar_script']:
        result += [{'type': 'bind', 'source': str(Path(m['calendar_script']['write']['directory']) / name),
                    'target': target, 'read_only': True}
                   for name, target in [('connection.json', WRITE_CONFIG), ('calendar.key', WRITE_KEY)]]
    return result


def arguments(m):
    config = validate_binding(m)
    result = ['--calendar-script-config', CONFIG, '--approved-calendar', digest(config.model_dump())]
    if 'write' in m['calendar_script']:
        result += ['--calendar-write-config', WRITE_CONFIG, '--approved-calendar-write',
                   digest(validate_write(m).model_dump())]
    return result
