"""Non-activating planning candidate preparation using existing release contracts."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .deployment import Engine, image_check, load_bundle, source_check
from .deployment_profile import atomic_json, checksum, render, validate_manifest, validate_profile
from .deployment_planning import PINS, check_binding, key_metadata, private_directory, validate_binding
from .planning_admission import PlanningProfile
from .planning_host import BROKER_COMMAND, HostDeclaration, metadata_document
from .planning_release import FIXED, plan
from .request_planning import _unique
from .store import digest
from .telegram_transport import TelegramConnection, connection, private_read


def raw_pin(value):
    # Exactly the serialization used by atomic_json, not model_dump_json.
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def expected_metadata(manifest, compose, image):
    """Prediction only. Actual Docker inspection must still match at startup/postcheck."""
    service, config = compose['services']['runtime-broker'], image['Config']
    command = config.get('Cmd') if service.get('command') is None else service['command']
    if (image['Id'] != manifest['images']['broker'] or (config.get('Labels') or {}).get(
            'org.opencontainers.image.revision') != manifest['revision']
            or config.get('WorkingDir') != '/app' or config.get('Entrypoint') not in (None, [])
            or command != BROKER_COMMAND
            or service.get('entrypoint') not in (None, [])
            or service.get('working_dir', '/app') != '/app'):
        raise ValueError('planning_exact_broker_image_required')
    env = dict(item.split('=', 1) for item in config.get('Env', []))
    if (env.get('PYTHONPATH') != '/app/src' or not env.get('PATH')
            or any(k in env for k in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'PYTHONHOME'))):
        raise ValueError('planning_broker_interpreter_policy_invalid')
    if any((k == 'PATH' or k.startswith(('PYTHON', 'LD_'))) and env.get(k) != str(v)
           for k, v in service['environment'].items()):
        raise ValueError('planning_broker_interpreter_override_forbidden')
    env.update(service['environment'])
    if (env.get('F1_RUNTIME_MODE') != 'rootless-required'
            or env.get('F1_RUNTIME_SOCKET', 'unix:///var/run/docker.sock') != 'unix:///var/run/docker.sock'):
        raise ValueError('planning_execution_endpoint_override_forbidden')
    memory = str(service['mem_limit']).lower()
    memory = int(memory[:-1]) * {'m': 1024**2, 'g': 1024**3}[memory[-1]] if memory[-1] in 'mg' else int(memory)
    tmpfs = dict(item.split(':', 1) for item in service.get('tmpfs', []))
    if (not 0 < memory <= 256 * 1024**2 or not 0 < float(service['cpus']) <= 1
            # Fixed in-container tmpfs target; no host temporary file is created.
            or not 0 < service['pids_limit'] <= 128 or set(tmpfs) != {'/tmp'}):  # nosec B108
        raise ValueError('planning_broker_bounds_required')
    mounts = [{'Source': v['source'], 'Destination': v['target'], 'RW': not v.get('read_only', False)}
              for v in service['volumes']]
    for secret in service['secrets']:
        name = secret['source'] if isinstance(secret, dict) else secret
        if isinstance(secret, dict) and secret.get('target') not in (None, name, '/run/secrets/' + name):
            raise ValueError('planning_secret_target_override_forbidden')
        mounts.append({'Source': compose['secrets'][name]['file'],
                       'Destination': '/run/secrets/' + name, 'RW': False})
    return metadata_document({'Image': image['Id'], 'Config': {
        'User': service['user'], 'WorkingDir': config['WorkingDir'],
        'Cmd': BROKER_COMMAND, 'Entrypoint': config.get('Entrypoint'),
        'Env': [k + '=' + str(v) for k, v in env.items()]},
        'HostConfig': {'ReadonlyRootfs': service['read_only'], 'Privileged': False,
            'CapDrop': service['cap_drop'], 'CapAdd': None, 'SecurityOpt': service['security_opt'],
            'Memory': memory, 'NanoCpus': int(float(service['cpus']) * 1_000_000_000),
            'PidsLimit': service['pids_limit'], 'NetworkMode': 'acc-f23_control',
            'PidMode': '', 'IpcMode': 'private', 'UsernsMode': '', 'Devices': None,
            'DeviceRequests': None, 'PortBindings': {}, 'Tmpfs': tmpfs},
        'NetworkSettings': {'Networks': {'acc-f23_' + k: {} for k in service['networks']}}, 'Mounts': mounts})


def assemble(previous, disabled, active, operator, image, output, key_directory,
             previous_pin, disabled_pin, credential_sha256, *, now):
    for bundle, pin in ((previous, previous_pin), (disabled, disabled_pin)):
        if not re.fullmatch('[a-f0-9]{64}', pin) or checksum(bundle) != pin:
            raise ValueError('planning_exact_input_bundles_required')
        validate_manifest(bundle['manifest'])
        validate_profile(bundle['compose'], bundle['manifest'])
    before, target = previous['manifest'], deepcopy(disabled['manifest'])
    if (any(before.get(k) != target.get(k) for k in FIXED)
            or before['revision'] == target['revision'] or 'telegram' not in before
            or any(k in target for k in ('telegram', 'planning', 'first_experiment'))
            or 'first_experiment' in before):
        raise ValueError('planning_disabled_target_or_transition_invalid')
    operator = PlanningProfile.model_validate(operator.model_dump())
    if (operator.runtime is not None or type(now) is not int
            or not operator.evidence.observed_at <= now < operator.evidence.expires_at
            or not re.fullmatch('[a-f0-9]{64}', credential_sha256)):
        raise ValueError('planning_fresh_unbound_operator_evidence_required')
    scope = before['telegram']
    if (active.mode != 'live' or active.source_revision != before['revision']
            or active.token_file != '/run/telegram/token'
            or digest(active.model_dump()) != scope['connection_digest']
            or any(getattr(active, k) != scope[k] for k in ('mode', 'owner_id', 'bot_id'))):
        raise ValueError('planning_exact_previous_connection_required')
    staged = TelegramConnection.model_validate({**active.model_dump(), 'source_revision': target['revision']})
    target['telegram'] = {**scope, 'connection_digest': digest(staged.model_dump())}
    target['planning'] = {**dict.fromkeys(PINS, '0' * 64),
                          'profile_directory': str(Path(output) / 'planning-profile'),
                          'key_directory': str(key_directory)}
    validate_binding(target)
    compose = render(disabled['compose'], target)
    metadata = expected_metadata(target, compose, image)
    host = HostDeclaration(source_revision=target['revision'], container_name='acc-f23-runtime-broker-1',
        image_id=target['images']['broker'], endpoint='unix:///var/run/docker.sock',
        attestation_endpoint=f'unix:///run/user/{target["control_uid"]}/docker.sock',
        ledger_path='/var/lib/f1-runtime/ledger.sqlite', metadata_digest=digest(metadata))
    profile = PlanningProfile.model_validate({**operator.model_dump(), 'runtime': {
        'source_revision': target['revision'], 'binding_digest': digest(host.model_dump()),
        'credential_sha256': credential_sha256}})
    target['planning'].update(profile_sha256=raw_pin(profile.model_dump()), host_sha256=raw_pin(host.model_dump()),
        profile_digest=digest(profile.model_dump()), host_digest=digest(host.model_dump()), credential_sha256=credential_sha256)
    candidate = {'manifest': target, 'compose': render(disabled['compose'], target)}
    if digest(expected_metadata(target, candidate['compose'], image)) != host.metadata_digest:
        raise ValueError('planning_metadata_hash_cycle_detected')
    review = plan(previous, candidate, previous_pin, checksum(candidate))
    return candidate, profile, host, staged, metadata, review


def read_json(path, limit=32768):
    return json.loads(private_read(path, limit), object_pairs_hook=_unique)


def capability(bundle):
    m = bundle['manifest']
    if 'planning' not in m:
        raise ValueError('planning_binding_required')
    return {'purpose': 'planning-control-access.v1', 'candidate_bundle': checksum(bundle),
        'source_revision': m['revision'], 'service': 'runtime-broker',
        'socket': f'/run/user/{m["control_uid"]}/docker.sock', 'docker_api_administrative': True,
        'egress_network': 'acc-f23_planning-access', 'credential_ref': 'planning-openai',
        'key_directory': m['planning']['key_directory'], 'paid_calls_authorized': False}


def predecessor(previous, directory, pin):
    root = Path(previous['manifest']['data_root'])
    receipt = read_json(root / 'deployment.json')
    activation = read_json(Path(directory) / 'activation.json')
    active = connection(root / 'telegram/connection.json')
    if (receipt.get('phase') != 'VERIFIED' or receipt.get('bundle') != pin
            or receipt.get('revision') != previous['manifest']['revision']
            or Path(receipt.get('directory', '')).resolve() != Path(directory).resolve()
            or activation.get('phase') != 'VERIFIED' or activation.get('target') != pin):
        raise ValueError('planning_verified_predecessor_required')
    return receipt, activation, active


def prepare(previous_directory, disabled_directory, output, operator_file, operator_pin,
            key_directory, credential_sha256, previous_pin, disabled_pin):
    previous, disabled = load_bundle(previous_directory), load_bundle(disabled_directory)
    target, output = disabled['manifest'], Path(output)
    if os.getuid() != target['control_uid']:
        raise ValueError('planning_dedicated_control_user_required')
    parent = output.parent.stat()
    if (not output.is_absolute() or output.resolve() != output or output.exists() or output.is_symlink()
            or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
        raise ValueError('planning_new_private_candidate_directory_required')
    raw = private_read(operator_file, 16384)
    if not re.fullmatch('[a-f0-9]{64}', operator_pin) or hashlib.sha256(raw).hexdigest() != operator_pin:
        raise ValueError('planning_exact_operator_profile_required')
    try:
        if len(raw) > 16384:
            raise ValueError()
        operator = PlanningProfile.model_validate(json.loads(raw, object_pairs_hook=_unique))
    except (ValueError, RecursionError):
        raise ValueError('planning_operator_profile_invalid') from None
    original = predecessor(previous, previous_directory, previous_pin)
    private_directory(key_directory, os.getuid(), {'openai.key'})
    key_metadata(Path(key_directory) / 'openai.key', os.getuid())
    source_check(target)
    broker_image = None
    for uid, names in ((target['control_uid'], {'api', 'worker', 'broker'}),
                       (target['execution_uid'], {'executor', 'coding'})):
        engine = Engine(uid)
        engine.preflight()
        image_check(engine, {k: target['images'][k] for k in names}, target['revision'])
        if uid == target['control_uid']:
            broker_image = engine.json('image', 'inspect', target['images']['broker'])[0]
    candidate, profile, host, staged, metadata, review = assemble(previous, disabled, original[2], operator,
        broker_image, output, key_directory, previous_pin, disabled_pin, credential_sha256, now=int(time.time()))
    source_check(target)
    if (predecessor(previous, previous_directory, previous_pin) != original
            or private_read(operator_file, 16384) != raw):
        raise ValueError('planning_inputs_changed_during_preparation')
    output.mkdir(mode=0o700)
    (output / 'planning-profile').mkdir(mode=0o700)
    documents = {'previous.json': previous, 'disabled.json': disabled, 'bundle.json': candidate,
        'compose.json': candidate['compose'], 'connection.candidate.json': staged.model_dump(),
        'broker.expected.json': metadata, 'planning-profile/profile.json': profile.model_dump(),
        'planning-profile/host.json': host.model_dump()}
    for name, value in documents.items():
        atomic_json(output / name, value)
    check_binding(candidate['manifest'])
    receipt = {'schema': 1, 'state': 'STAGED_NOT_ACTIVATED', 'previous_bundle': previous_pin,
        'disabled_bundle': disabled_pin, 'candidate_bundle': checksum(candidate),
        'operator_profile_sha256': operator_pin, 'review': review,
        'files': {name: raw_pin(value) for name, value in documents.items()},
        'deployment_authorized': False, 'access_expansion_authorized': False,
        'task_admission_resumed': False, 'paid_calls': 0}
    atomic_json(output / 'preparation.json', receipt)  # completion marker, never an activation journal
    return {'status': 'PLANNING_CANDIDATE_PREPARED_NOT_APPLIED', 'candidate_bundle': checksum(candidate),
            'preparation_digest': checksum(receipt), 'task_admission_resumed': False, 'paid_calls': 0}


def inspect(directory, candidate_pin, preparation_pin):
    directory = Path(directory)
    receipt = read_json(directory / 'preparation.json')
    if (set(receipt) != {'schema', 'state', 'previous_bundle', 'disabled_bundle', 'candidate_bundle',
            'operator_profile_sha256', 'review', 'files', 'deployment_authorized',
            'access_expansion_authorized', 'task_admission_resumed', 'paid_calls'}
            or receipt['schema'] != 1 or not re.fullmatch('[a-f0-9]{64}', candidate_pin)
            or not re.fullmatch('[a-f0-9]{64}', preparation_pin) or checksum(receipt) != preparation_pin
            or receipt.get('state') != 'STAGED_NOT_ACTIVATED'
            or receipt.get('candidate_bundle') != candidate_pin
            or any(receipt.get(k) is not False for k in ('deployment_authorized', 'access_expansion_authorized', 'task_admission_resumed'))
            or receipt.get('paid_calls') != 0):
        raise ValueError('planning_exact_preparation_required')
    expected = {'previous.json', 'disabled.json', 'bundle.json', 'compose.json', 'connection.candidate.json',
                'broker.expected.json', 'planning-profile/profile.json', 'planning-profile/host.json'}
    present = {p.name for p in directory.iterdir()}
    fixed = {'previous.json', 'disabled.json', 'bundle.json', 'compose.json', 'connection.candidate.json',
             'broker.expected.json', 'planning-profile', 'preparation.json'}
    if set(receipt.get('files', {})) != expected or present - {'activation.json', 'connection.previous.json'} != fixed:
        raise ValueError('planning_candidate_inventory_changed')
    for name, pin in receipt['files'].items():
        if hashlib.sha256(private_read(directory / name, 2 * 1024 * 1024)).hexdigest() != pin:
            raise ValueError('planning_candidate_file_changed')
    candidate = load_bundle(directory)
    if (checksum(candidate) != candidate_pin or directory.resolve() != directory
            or candidate['manifest']['planning']['profile_directory'] != str(directory / 'planning-profile')):
        raise ValueError('planning_exact_candidate_required')
    _, host = check_binding(candidate['manifest'])
    previous = read_json(directory / 'previous.json', 2 * 1024 * 1024)
    disabled = read_json(directory / 'disabled.json', 2 * 1024 * 1024)
    validate_manifest(disabled['manifest'])
    validate_profile(disabled['compose'], disabled['manifest'])
    if (checksum(disabled) != receipt['disabled_bundle']
            or {k: v for k, v in candidate['manifest'].items() if k not in {'telegram', 'planning'}} != disabled['manifest']):
        raise ValueError('planning_disabled_target_changed')
    if receipt['review'] != plan(previous, candidate, receipt['previous_bundle'], candidate_pin):
        raise ValueError('planning_review_changed')
    staged = connection(directory / 'connection.candidate.json')
    if (staged.source_revision != candidate['manifest']['revision']
            or staged.mode != 'live' or staged.token_file != '/run/telegram/token'
            or any(getattr(staged, k) != candidate['manifest']['telegram'][k] for k in ('mode', 'owner_id', 'bot_id'))
            or digest(staged.model_dump()) != candidate['manifest']['telegram']['connection_digest']
            or digest(read_json(directory / 'broker.expected.json')) != host.metadata_digest):
        raise ValueError('planning_candidate_binding_changed')
    phase = None
    if 'connection.previous.json' in present:
        original = connection(directory / 'connection.previous.json')
        if (original.model_dump() != {**staged.model_dump(), 'source_revision': previous['manifest']['revision']}
                or digest(original.model_dump()) != previous['manifest']['telegram']['connection_digest']):
            raise ValueError('planning_previous_connection_changed')
    if 'activation.json' in present:
        activation = read_json(directory / 'activation.json')
        phase = activation.get('phase')
        if (phase not in {'PREPARED', 'BINDING_ACTIVE', 'DEPLOYMENT_ATTEMPTED', 'VERIFIED'}
                or activation.get('purpose') != 'planning-activation.v1'
                or activation.get('previous') != receipt['previous_bundle'] or activation.get('target') != candidate_pin
                or activation.get('preparation_digest') != preparation_pin
                or activation.get('control_capability') != digest(capability(candidate))
                or activation.get('task_admission_resumed') is not False or activation.get('paid_calls') != 0):
            raise ValueError('planning_activation_journal_scope_changed')
    return {'status': 'PLANNING_CANDIDATE_INTEGRITY_VERIFIED_NOT_ACTIVATED' if phase is None else
            'PLANNING_CANDIDATE_INTEGRITY_VERIFIED_ACTIVATION_JOURNAL_PRESENT', 'activation_phase': phase,
            'candidate_bundle': candidate_pin, 'deployment_authorized': False, 'paid_calls': 0}
