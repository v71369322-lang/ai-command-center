"""Explicit private planning bindings. No key reads or provider I/O."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .deployment_profile import absolute
from .planning_admission import PlanningProfile
from .planning_host import HostDeclaration
from .request_planning import _unique
from .store import Denied, digest
from .telegram_transport import private_read

PROFILE = '/run/planning/profile.json'
HOST = '/run/planning/host.json'
KEY = '/run/planning-key/openai.key'
PINS = {'profile_sha256', 'host_sha256', 'profile_digest', 'host_digest', 'credential_sha256'}


def validate_binding(m):
    binding = m.get('planning')
    if ('telegram' not in m or 'first_experiment' in m or not isinstance(binding, dict)
            or set(binding) != PINS | {'profile_directory', 'key_directory'}):
        raise ValueError('planning_release_scope_invalid')
    if any(not isinstance(binding[k], str) or not re.fullmatch('[a-f0-9]{64}', binding[k]) for k in PINS):
        raise ValueError('planning_exact_pins_required')
    paths = [Path(absolute(binding[k])) for k in ('profile_directory', 'key_directory')]
    roots = [Path(m[k]) for k in ('source_root', 'data_root')]
    if (any(p.resolve() != p or any(p.is_relative_to(root) or root.is_relative_to(p) for root in roots) for p in paths)
            or paths[0].is_relative_to(paths[1]) or paths[1].is_relative_to(paths[0])):
        raise ValueError('planning_separate_private_directories_required')


def private_directory(path, uid, inventory):
    path = Path(path)
    info = path.lstat()
    if (path.resolve() != path or not stat.S_ISDIR(info.st_mode) or info.st_uid != uid
            or info.st_mode & 0o077 or {p.name for p in path.iterdir()} != inventory):
        raise ValueError('planning_private_directory_inventory_invalid')


def documents(m):
    b, uid = m['planning'], m['control_uid']
    private_directory(b['profile_directory'], uid, {'profile.json', 'host.json'})
    private_directory(b['key_directory'], uid, {'openai.key'})
    try:
        raw = private_read(Path(b['profile_directory']) / 'profile.json', 16384)
        host_raw = private_read(Path(b['profile_directory']) / 'host.json', 16384)
        if max(len(raw), len(host_raw)) > 16384:
            raise ValueError()
        profile = PlanningProfile.model_validate(json.loads(raw, object_pairs_hook=_unique))
        host = HostDeclaration.model_validate(json.loads(host_raw, object_pairs_hook=_unique))
    except (OSError, ValueError, Denied, RecursionError):
        # Pydantic validation errors can contain operator input. Never echo it.
        raise ValueError('planning_private_documents_invalid') from None
    if (profile.runtime is None or profile.runtime.source_revision != m['revision']
            or profile.runtime.binding_digest != digest(host.model_dump())
            or host.source_revision != m['revision'] or host.image_id != m['images']['broker']
            or host.container_name != 'acc-f23-runtime-broker-1'
            or host.endpoint != 'unix:///var/run/docker.sock'
            or host.attestation_endpoint != f'unix:///run/user/{uid}/docker.sock'
            or host.ledger_path != '/var/lib/f1-runtime/ledger.sqlite'):
        raise ValueError('planning_source_image_host_binding_invalid')
    pins = {'profile_sha256': hashlib.sha256(raw).hexdigest(),
            'host_sha256': hashlib.sha256(host_raw).hexdigest(),
            'profile_digest': digest(profile.model_dump()), 'host_digest': digest(host.model_dump()),
            'credential_sha256': profile.runtime.credential_sha256}
    return profile, host, pins


def check_binding(m):
    validate_binding(m)
    profile, host, pins = documents(m)
    if any(m['planning'][k] != v for k, v in pins.items()):
        raise ValueError('planning_private_binding_changed')
    if not profile.evidence.observed_at <= time.time() < profile.evidence.expires_at:
        raise ValueError('planning_operator_evidence_expired')
    # Inspect only the descriptor metadata. Key bytes are read by the guarded gateway
    # after exact task authority, never during prepare, startup or postcheck.
    key_metadata(Path(m['planning']['key_directory']) / 'openai.key', m['control_uid'])
    return profile, host


def key_metadata(path, uid):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                or info.st_mode & 0o077 or info.st_nlink != 1 or not 16 <= info.st_size <= 1024):
            raise ValueError('planning_private_key_metadata_invalid')
    finally:
        os.close(fd)


def prepare_binding(m, profile_directory, key_directory):
    binding = {**dict.fromkeys(PINS, '0' * 64), 'profile_directory': str(profile_directory),
               'key_directory': str(key_directory)}
    candidate = {**m, 'planning': binding}
    validate_binding(candidate)
    _, _, pins = documents(candidate)
    binding.update(pins)
    check_binding(candidate)
    return binding


def environment(m, service):
    if 'planning' not in m or service not in {'telegram', 'runtime-broker'}:
        return {}
    b = m['planning']
    env = {'F1_PLANNING_PROFILE_FILE': PROFILE, 'F1_PLANNING_PROFILE_SHA256': b['profile_sha256']}
    if service == 'runtime-broker':
        env.update(F1_PLANNING_HOST_FILE=HOST, F1_PLANNING_HOST_SHA256=b['host_sha256'],
                   F1_PLANNING_OPENAI_KEY_FILE=KEY)
    return env


def mounts(m, service):
    if 'planning' not in m or service not in {'telegram', 'runtime-broker'}:
        return []
    b = m['planning']
    result = [{'type': 'bind', 'source': b['profile_directory'], 'target': '/run/planning', 'read_only': True}]
    if service == 'runtime-broker':
        result += [{'type': 'bind', 'source': b['key_directory'], 'target': '/run/planning-key', 'read_only': True},
                   {'type': 'bind', 'source': f'/run/user/{m["control_uid"]}/docker.sock',
                    'target': f'/run/user/{m["control_uid"]}/docker.sock', 'read_only': True}]
    return result


def check_runtime(m, service, metadata, composed):
    """Measure installed custody/scope; do not equate a rendered file with runtime."""
    b = m['planning']
    sources = [Path(b[k]) for k in ('profile_directory', 'key_directory')]
    sources.append(Path(f'/run/user/{m["control_uid"]}/docker.sock'))
    targets = [Path('/run/planning'), Path('/run/planning-key'), sources[-1]]

    def related(path, sensitive):
        path = Path(path)
        return any(path.is_relative_to(p) or p.is_relative_to(path) for p in sensitive)

    actual = {(v['Source'], v['Destination'], v['RW']) for v in metadata.get('Mounts', [])
              if related(v['Source'], sources) or related(v['Destination'], targets)}
    expected = {(v['source'], v['target'], not v['read_only']) for v in mounts(m, service)}
    env = {k: v for item in metadata['Config'].get('Env', []) for k, _, v in [item.partition('=')]
           if k.startswith('F1_PLANNING_')}
    if actual != expected or env != environment(m, service):
        raise ValueError('planning_runtime_mount_or_environment_mismatch')
    expected_networks = {'acc-f23_' + k for k in composed['networks']}
    if set(metadata.get('NetworkSettings', {}).get('Networks', {})) != expected_networks:
        raise ValueError('planning_runtime_network_mismatch')
