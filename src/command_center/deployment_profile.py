"""Local operator release bundles. Never imported by the API or coding agent."""
import hashlib
import json
import os
from pathlib import Path
import re

from .store import canonical

PROJECT = 'acc-f23'
SERVICES = {'db', 'redis', 'api', 'worker', 'runtime-broker', 'watchdog'}
IMAGE_KEYS = {'api', 'worker', 'broker', 'executor', 'coding'}
OWNER_VERIFIER_PATH = '/run/owner/password.json'
SECRETS = {'db_admin_password', 'db_password', 'db_runtime_password',
           'redis_password', 'identities', 'broker_token'}


def checksum(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def absolute(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or path.is_symlink():
        raise ValueError('absolute_non_symlink_path_required')
    return str(path)


def validate_manifest(m):
    if set(m) - {'owner_login', 'telegram'} != {'schema', 'revision', 'images', 'database_image', 'redis_image', 'migration_hash',
                  'control_uid', 'execution_uid', 'data_root', 'source_root'} or m['schema'] != 1:
        raise ValueError('release_schema_invalid')
    if 'telegram' in m:
        from .telegram_health import scope
        from .store import Denied
        try:
            binding = scope(canonical(m['telegram']))
            if binding['mode'] != 'live':
                raise ValueError('live_binding_required')
        except (Denied, ValueError, TypeError):
            raise ValueError('telegram_release_binding_invalid') from None
    if 'owner_login' in m:
        from .password_auth import origin_valid
        login = m['owner_login']
        if (not isinstance(login, dict) or set(login) != {'origin', 'loopback_http'}
                or type(login['loopback_http']) is not bool
                or not origin_valid(login['origin'], login['loopback_http'])):
            raise ValueError('password_origin_invalid')
    if not re.fullmatch('[a-f0-9]{40}', m['revision']) or not re.fullmatch('[a-f0-9]{64}', m['migration_hash']):
        raise ValueError('exact_revision_and_migration_required')
    if (set(m['images']) != IMAGE_KEYS or any(not re.fullmatch('sha256:[a-f0-9]{64}', v)
                                            for v in m['images'].values())):
        raise ValueError('immutable_local_image_ids_required')
    for key, prefix in [('database_image', 'postgres:16-'), ('redis_image', 'redis:7-')]:
        if not re.fullmatch(re.escape(prefix) + r'[a-z0-9.-]+@sha256:[a-f0-9]{64}', m[key]):
            raise ValueError('pinned_database_major_required')
    if (type(m['control_uid']) is not int or type(m['execution_uid']) is not int
            or min(m['control_uid'], m['execution_uid']) < 1000 or m['control_uid'] == m['execution_uid']):
        raise ValueError('separate_unprivileged_users_required')
    for key in ('data_root', 'source_root'):
        absolute(m[key])


def services(m):
    return SERVICES | ({'telegram'} if 'telegram' in m else set())


def telegram_service(m):
    """One fixed client process, not an arbitrary service or HTTP proxy."""
    return {
        'image': m['images']['api'], 'user': '0:0', 'restart': 'no',
        'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
        'command': ['python', '-m', 'command_center.telegram_service', 'run',
                    '--config', '/run/telegram/connection.json', '--approved-connection',
                    m['telegram']['connection_digest']],
        'environment': {'F1_SOURCE_REVISION': m['revision'], 'F1_DB_USER': 'f1_app', 'F1_DB_HOST': 'db',
                        'F1_DB_PASSWORD_FILE': '/run/secrets/db_password'},
        'secrets': ['db_password'],
        'volumes': [{'type': 'bind', 'source': str(Path(m['data_root']) / 'telegram'),
                     'target': '/run/telegram', 'read_only': True}],
        'networks': {'control': None, 'telegram-access': None},
        'mem_limit': '128m', 'cpus': .25, 'pids_limit': 32,
        # Compose syntax for a private bounded tmpfs, not a host tempfile operation.
        'tmpfs': ['/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777'], 'stop_grace_period': '30s',  # nosec B108
        'depends_on': {'db': {'condition': 'service_healthy'}},
        'logging': {'driver': 'local', 'options': {'max-size': '1m', 'max-file': '2'}},
    }


def render(base, m):
    validate_manifest(m)
    # Input is Docker Compose's normalized JSON from the pinned source checkout.
    profile = json.loads(json.dumps(base))
    if set(profile['services']) != SERVICES:
        raise ValueError('unexpected_source_services')
    root = Path(m['data_root'])
    profile.pop('x-bounded-logging', None)
    profile['name'] = PROJECT
    profile['volumes'] = {'pgdata': {'name': PROJECT + '-pgdata'}}
    profile['networks'] = {'control': {'internal': True}, 'access': {'internal': False}}
    profile['secrets'] = {k: {'file': str(root / 'secrets' / k)} for k in SECRETS}
    for name, service in profile['services'].items():
        service.pop('build', None)
        service.pop('profiles', None)
        service.pop('group_add', None)
        service.pop('container_name', None)
        # Applications must wait for the serialized boot interlock. Otherwise
        # Docker restarts a worker before the user service can halt admission.
        service['restart'] = 'unless-stopped' if name in {'db', 'redis'} else 'no'
        service['networks'] = {'control': None}
        service['logging'] = {'driver': 'local', 'options': {'max-size': '5m', 'max-file': '2'}}
        if name == 'db':
            service['image'] = m['database_image']
            service['volumes'] = [{'type': 'volume', 'source': 'pgdata', 'target': '/var/lib/postgresql/data'}]
            service['mem_limit'] = '1g'
            # initdb's temporary server accepts Unix sockets but not TCP; schema
            # initialization runs in a separate container and needs actual TCP.
            service['healthcheck']['test'] = ['CMD-SHELL', 'pg_isready -h 127.0.0.1 -U f1_admin -d f1']
            continue
        # UID 0 *inside the control user's rootless namespace* is the unprivileged
        # host control UID, so 0600 bind secrets remain readable without widening ACLs.
        # Host-root daemons are rejected, and no application receives a daemon socket.
        service['user'] = '0:0'
        service['cap_drop'] = ['ALL']
        service['security_opt'] = ['no-new-privileges:true']
        service['read_only'] = True
        if name == 'redis':
            service['image'] = m['redis_image']
            service['volumes'] = [{'type': 'bind', 'source': str(Path(m['source_root']) / 'deploy/redis.sh'),
                                   'target': '/redis.sh', 'read_only': True}]
            continue
        key = 'broker' if name in {'runtime-broker', 'watchdog'} else name
        service['image'] = m['images'][key]
        env = service['environment']
        env['F1_SOURCE_REVISION'] = m['revision']
        service['volumes'] = []
        if name == 'api':
            # Docker internal-only bridges do not reliably publish host ports.
            # This interface exposes only the pinned loopback binding; it is NOT
            # an egress firewall. External credentials/config remain absent.
            service['networks']['access'] = None
            env.update(F1_AUTH_MODE='oidc', F1_OIDC_ISSUER='', F1_OIDC_AUDIENCE='', F1_OIDC_OWNER='',
                       F1_WEB_ORIGIN='', F1_OIDC_JWKS_FILE='/run/identity/public-jwks.json')
            service['volumes'] = [{'type': 'bind', 'source': str(root / 'identity/public-jwks.json'),
                                   'target': '/run/identity/public-jwks.json', 'read_only': True}]
            if 'owner_login' in m:
                env.update(F1_AUTH_MODE='password', F1_WEB_ORIGIN=m['owner_login']['origin'],
                           F1_OWNER_PASSWORD_FILE=OWNER_VERIFIER_PATH,
                           F1_PASSWORD_LOOPBACK_HTTP='1' if m['owner_login']['loopback_http'] else '0')
                service['volumes'] = [{'type': 'bind', 'source': str(root / 'secrets/owner_password'),
                                      'target': OWNER_VERIFIER_PATH, 'read_only': True}]
            if 'telegram' in m:
                env['F1_TELEGRAM_SCOPE'] = canonical(m['telegram'])
            service['ports'] = [{'target': 8000, 'published': '8000', 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]
        if name in {'worker', 'runtime-broker'}:
            service['volumes'].append({'type': 'bind', 'source': str(root / 'broker-socket'),
                                      'target': '/run/f1-broker', 'read_only': name == 'worker'})
        if name in {'runtime-broker', 'watchdog'}:
            env.update(F1_RUNTIME_MODE='rootless-required', F1_EXECUTOR_IMAGE=m['images']['executor'],
                       F2_EXECUTOR_IMAGE=m['images']['coding'], F1_LIMIT_MIN_FREE_MIB='1024')
            service['volumes'] += [
                {'type': 'bind', 'source': f'/run/user/{m["execution_uid"]}/docker.sock', 'target': '/var/run/docker.sock'},
                {'type': 'bind', 'source': str(root / 'runtime-ledger'), 'target': '/var/lib/f1-runtime'}]
    if 'telegram' in m:
        profile['networks']['telegram-access'] = {'internal': False}
        profile['services']['telegram'] = telegram_service(m)
    validate_profile(profile, m)
    return profile


def validate_profile(p, m):
    if p['name'] != PROJECT or set(p['services']) != services(m) or not p['networks']['control']['internal']:
        raise ValueError('deployment_boundary_invalid')
    if p['secrets'] != {k: {'file': str(Path(m['data_root']) / 'secrets' / k)} for k in SECRETS}:
        raise ValueError('secret_source_changed')
    for name, s in p['services'].items():
        if name == 'telegram':
            if s != telegram_service(m) or p['networks'].get('telegram-access') != {'internal': False}:
                raise ValueError('telegram_service_boundary_changed')
            continue
        if s.get('restart') != ('unless-stopped' if name in {'db', 'redis'} else 'no'):
            raise ValueError('restart_bypasses_boot_interlock')
        expected_image = (m['database_image'] if name == 'db' else m['redis_image'] if name == 'redis'
                          else m['images']['broker' if name in {'runtime-broker', 'watchdog'} else name])
        if s['image'] != expected_image or set(s['networks']) != ({'control', 'access'} if name == 'api' else {'control'}):
            raise ValueError('service_image_or_network_changed')
        allowed_secrets = {'db': {'db_admin_password'}, 'redis': {'redis_password'},
                           'api': {'db_password', 'redis_password', 'identities'},
                           'worker': {'redis_password', 'broker_token'},
                           'runtime-broker': {'db_runtime_password', 'redis_password', 'broker_token'},
                           'watchdog': {'db_runtime_password', 'redis_password'}}
        if {v['source'] if isinstance(v, dict) else v for v in s['secrets']} != allowed_secrets[name]:
            raise ValueError('service_secret_scope_changed')
        if s.get('privileged') or s.get('network_mode') or s.get('pid') or s.get('devices') or s.get('cap_add'):
            raise ValueError('host_privilege_forbidden')
        if name != 'api' and s.get('ports'):
            raise ValueError('unexpected_port')
        if name == 'api' and s['ports'] != [{'target': 8000, 'published': '8000', 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]:
            raise ValueError('public_api_forbidden')
        if name != 'db' and (s.get('user') != '0:0' or s.get('cap_drop') != ['ALL'] or not s.get('read_only')):
            raise ValueError('rootless_service_policy')
        for mount in s.get('volumes', []):
            target = mount['target']
            if 'sock' in target and target == '/var/run/docker.sock':
                if name not in {'runtime-broker', 'watchdog'} or mount['source'] != f'/run/user/{m["execution_uid"]}/docker.sock':
                    raise ValueError('socket_scope_violation')
        root = Path(m['data_root'])
        allowed = {
            'db': {('pgdata', '/var/lib/postgresql/data', False)},
            'redis': {(str(Path(m['source_root']) / 'deploy/redis.sh'), '/redis.sh', True)},
            'api': {(str(root / 'identity/public-jwks.json'), '/run/identity/public-jwks.json', True)},
            'worker': {(str(root / 'broker-socket'), '/run/f1-broker', True)},
            'runtime-broker': {(str(root / 'broker-socket'), '/run/f1-broker', False),
                               (str(root / 'runtime-ledger'), '/var/lib/f1-runtime', False),
                               (f'/run/user/{m["execution_uid"]}/docker.sock', '/var/run/docker.sock', False)},
            'watchdog': {(str(root / 'runtime-ledger'), '/var/lib/f1-runtime', False),
                         (f'/run/user/{m["execution_uid"]}/docker.sock', '/var/run/docker.sock', False)}}
        actual = {(v['source'], v['target'], v.get('read_only', False)) for v in s.get('volumes', [])}
        if 'owner_login' in m:
            allowed['api'] = {(str(root / 'secrets/owner_password'), OWNER_VERIFIER_PATH, True)}
        if actual != allowed[name]:
            raise ValueError('unapproved_mount')
        env = s.get('environment', {})
        expected_scope = canonical(m['telegram']) if name == 'api' and 'telegram' in m else None
        if env.get('F1_TELEGRAM_SCOPE') != expected_scope:
            raise ValueError('telegram_api_scope_changed')
        if any(k.startswith(('F21_', 'F2_INTEGRATION')) for k in env):
            raise ValueError('external_integration_not_authorized')
        if name == 'api' and env.get('F1_AUTH_MODE') != ('password' if 'owner_login' in m else 'oidc'):
            raise ValueError('synthetic_owner_access_forbidden')
        if 'owner_login' in m and name == 'api':
            expected = {'F1_WEB_ORIGIN': m['owner_login']['origin'],
                        'F1_OWNER_PASSWORD_FILE': OWNER_VERIFIER_PATH,
                        'F1_PASSWORD_LOOPBACK_HTTP': '1' if m['owner_login']['loopback_http'] else '0'}
            if any(env.get(k) != v for k, v in expected.items()):
                raise ValueError('password_login_binding_changed')
        if name != 'api' and any(k.startswith(('F1_OWNER_PASSWORD', 'F1_PASSWORD_LOOPBACK')) for k in env):
            raise ValueError('password_outside_api')
        if name in {'runtime-broker', 'watchdog'} and env.get('F1_RUNTIME_MODE') != 'rootless-required':
            raise ValueError('rootful_runtime_forbidden')


def atomic_json(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('symlink_state_forbidden')
    temporary = path.with_name(path.name + '.pending')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump(value, file, sort_keys=True)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
