"""Explicit first-experiment deployment bindings; no credentials or authority issued."""
import hashlib
import os
from pathlib import Path
import re
import stat

from .coding.first_experiment import CALLS, CAP, CONTEXT_TOKENS, MODEL, OUTPUT_TOKENS
from .coding.integration_config import IntegrationConfig
from .store import digest

CONFIG_TARGET = '/run/f2/config.json'
CREDENTIAL_TARGETS = {'openai_key_file': '/run/f2/openai.key',
                      'github_token_file': '/run/f2/github.token'}
BINDING_KEYS = {'config_file', 'config_sha256', 'profile_hash', *CREDENTIAL_TARGETS}


def validate_binding(manifest):
    binding = manifest.get('first_experiment')
    if (not isinstance(binding, dict) or set(binding) not in (BINDING_KEYS, BINDING_KEYS | {'telegram_readiness'})
            or 'telegram_readiness' in binding and binding['telegram_readiness'] is not True):
        raise ValueError('first_experiment_binding_invalid')
    if any(not isinstance(binding[k], str) or not re.fullmatch('[a-f0-9]{64}', binding[k])
           for k in ('config_sha256', 'profile_hash')):
        raise ValueError('first_experiment_config_pin_required')
    paths = []
    for name in ('config_file', *CREDENTIAL_TARGETS):
        value = binding[name]
        if not isinstance(value, str) or '\0' in value:
            raise ValueError('first_experiment_private_path_required')
        path = Path(value)
        if (not path.is_absolute() or str(path) != value or '..' in path.parts
                or path.resolve() != path or path.is_relative_to(Path(manifest['source_root']))):
            raise ValueError('first_experiment_private_path_required')
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise ValueError('first_experiment_separate_files_required')


def _open_private(path, uid, maximum, minimum=1):
    path = Path(path)
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != uid or parent.st_mode & 0o077:
        raise ValueError('first_experiment_private_parent_required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != uid or metadata.st_mode & 0o077
                or metadata.st_nlink != 1 or not minimum <= metadata.st_size <= maximum):
            raise ValueError('first_experiment_private_file_required')
        return os.fdopen(fd, 'rb'), metadata
    except Exception:
        os.close(fd)
        raise


def _configuration(path, uid):
    stream, before = _open_private(path, uid, 16384)
    with stream:
        raw = stream.read(16385)
        after = os.fstat(stream.fileno())
    if ((before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != before.st_size):
        raise ValueError('first_experiment_config_changed')
    try:
        config = IntegrationConfig.model_validate_json(raw)
    except Exception:
        raise ValueError('first_experiment_config_invalid') from None
    if (config.mode != 'live' or not config.first_experiment or not config.first_experiment.repository_id
            or not config.synthetic_repository or not config.budget_evidence
            or not config.tariff or not config.tariff.confirmed
            or config.tariff.model != MODEL or config.tariff.context_tokens != CONTEXT_TOKENS
            or config.tariff.max_output_tokens != OUTPUT_TOKENS
            or not config.tariff.input_nano_rub or not config.tariff.output_nano_rub
            or not 0 < config.tariff.maximum() * CALLS <= min(config.daily_nano_rub, config.monthly_nano_rub, CAP)
            or max(config.daily_nano_rub, config.monthly_nano_rub) > CAP):
        raise ValueError('first_experiment_deployment_scope_invalid')
    if (config.openai_secret_ref == config.github_secret_ref
            or config.credential_files != {config.openai_secret_ref: CREDENTIAL_TARGETS['openai_key_file'],
                                          config.github_secret_ref: CREDENTIAL_TARGETS['github_token_file']}):
        raise ValueError('first_experiment_credential_references_invalid')
    return raw, config


def check_binding(manifest):
    """Read only the config, and stat credentials through protected descriptors."""
    validate_binding(manifest)
    binding, uid = manifest['first_experiment'], manifest['control_uid']
    raw, config = _configuration(binding['config_file'], uid)
    if (hashlib.sha256(raw).hexdigest() != binding['config_sha256']
            or digest(config.model_dump()) != binding['profile_hash']):
        raise ValueError('first_experiment_config_pin_changed')
    # Never read the OpenAI key or installation-token values during prepare/preflight.
    identities = set()
    for name in CREDENTIAL_TARGETS:
        stream, metadata = _open_private(binding[name], uid, 1024, minimum=16)
        stream.close()
        identities.add((metadata.st_dev, metadata.st_ino))
    if len(identities) != len(CREDENTIAL_TARGETS):
        raise ValueError('first_experiment_separate_files_required')
    return config


def prepare_binding(manifest, config_file, openai_key_file, github_token_file, *, telegram_readiness=False):
    binding = dict(config_file=str(config_file), config_sha256='0' * 64, profile_hash='0' * 64,
                   openai_key_file=str(openai_key_file), github_token_file=str(github_token_file))
    if telegram_readiness:
        binding['telegram_readiness'] = True
    candidate = {**manifest, 'first_experiment': binding}
    validate_binding(candidate)
    raw, config = _configuration(config_file, manifest['control_uid'])
    binding.update(config_sha256=hashlib.sha256(raw).hexdigest(), profile_hash=digest(config.model_dump()))
    check_binding(candidate)
    return binding


def mounts(manifest, service):
    if ('first_experiment' not in manifest or service not in {'api', 'runtime-broker', 'telegram'}
            or service == 'telegram' and ('telegram' not in manifest
                or not manifest['first_experiment'].get('telegram_readiness'))):
        return []
    binding = manifest['first_experiment']
    result = [{'type': 'bind', 'source': binding['config_file'], 'target': CONFIG_TARGET, 'read_only': True}]
    if service == 'runtime-broker':
        result += [{'type': 'bind', 'source': binding[name], 'target': target, 'read_only': True}
                   for name, target in CREDENTIAL_TARGETS.items()]
    return result
