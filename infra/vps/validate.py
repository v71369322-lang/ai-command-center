"""Offline preparation-template validation. Never starts services or contacts a host."""
import argparse
import json
from pathlib import Path
import re


class Invalid(ValueError):
    pass


def validate(config, *, require_deployable=False):
    def need(condition, message):
        if not condition:
            raise Invalid(message)

    meta = config.get('x-f1-preparation', {})
    need(set(config) == {'name', 'x-f1-preparation', 'services', 'networks', 'volumes', 'secrets'}, 'unexpected_top_level')
    need(config.get('name') == 'acc-f1-lab', 'unexpected_project')
    need(meta.get('deployable') is False and meta.get('blockers'), 'preparation_gate_missing')
    need(re.fullmatch('[a-f0-9]{40}', meta.get('source_baseline', '')), 'source_baseline_missing')
    need(not require_deployable, 'not_deployable: unresolved infrastructure gates')
    services = config.get('services', {})
    need(set(services) == {'api', 'db', 'redis'}, 'unexpected_service_or_launcher')
    need(config.get('networks') == {'control': {'internal': True}, 'frontend': {}}, 'unexpected_network_definition')
    need(config.get('volumes') == {'pgdata': {}}, 'external_or_host_volume')
    for name, service in services.items():
        common = {'image', 'environment', 'secrets', 'volumes', 'networks', 'mem_limit', 'cpus',
                  'pids_limit', 'restart', 'logging'}
        expected_fields = {
            'db': common | {'healthcheck'},
            'redis': common | {'user', 'read_only', 'cap_drop', 'security_opt', 'command', 'tmpfs'},
            'api': (common - {'volumes'}) | {'user', 'read_only', 'cap_drop', 'security_opt', 'command',
                                            'ports', 'tmpfs', 'depends_on'}}
        # Redis has no environment: password remains a mounted file.
        expected_fields['redis'].remove('environment')
        need(set(service) == expected_fields[name], 'unapproved_service_field')
        image = service.get('image', '')
        need(bool(re.fullmatch(r'.+@sha256:[a-f0-9]{64}', image)) or
             (name == 'api' and image == '${F1_API_IMAGE:?digest-pinned-image-required}'), 'unpinned_image')
        need(not any(k in service for k in ('privileged', 'devices', 'group_add', 'network_mode', 'pid',
                                             'ipc', 'cap_add', 'build', 'extends', 'env_file')), 'unsafe_service_option')
        need(service.get('restart') == 'no', 'automatic_restart_not_approved')
        expected_limits = {'db': ('1g', 1, 128), 'redis': ('128m', .25, 32), 'api': ('256m', .5, 64)}
        need(type(service.get('cpus')) in {int, float} and type(service.get('pids_limit')) is int
             and (service.get('mem_limit'), service.get('cpus'), service.get('pids_limit')) == expected_limits[name],
             'resource_profile_mismatch')
        log = service.get('logging', {})
        need(log.get('driver') == 'local' and log.get('options') ==
             {'max-size': '10m', 'max-file': '3'}, 'unbounded_logs')
        allowed_mounts = {'db': ['pgdata:/var/lib/postgresql/data'],
                          'redis': ['../../deploy/redis.sh:/redis.sh:ro'], 'api': []}
        need(service.get('volumes', []) == allowed_mounts[name],
             'arbitrary_mount')
        need(service.get('ports', []) == (['127.0.0.1:8000:8000'] if name == 'api' else []), 'exposed_port')
        need(set(service.get('networks', [])) == ({'control', 'frontend'} if name == 'api' else {'control'}),
             'unexpected_network')
        if name != 'db':
            need(service.get('user') == '10001:10001' and service.get('read_only') is True
                 and service.get('cap_drop') == ['ALL']
                 and service.get('security_opt') == ['no-new-privileges:true'], 'runtime_privileges')
            need(service.get('tmpfs') == ['/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777'], 'unbounded_tmpfs')
        environment = service.get('environment', {})
        need(all(not any(term in key for term in ('DOCKER_HOST', 'TOKEN', 'PRIVATE_KEY'))
                 and ('PASSWORD' not in key or key.endswith('_FILE')) for key in environment), 'inline_secret_or_socket')
        need(set(service.get('secrets', [])) == {
            'db': {'db_admin_password'}, 'redis': {'redis_password'},
            'api': {'db_password', 'redis_password', 'identities'}}[name], 'secret_scope')
    expected = {n: {'file': '/etc/ai-command-center/f1/secrets/' + p} for n, p in {
        'db_admin_password': 'db_admin_password', 'db_password': 'db_password',
        'redis_password': 'redis_password', 'identities': 'identities.json'}.items()}
    need(config.get('secrets') == expected, 'unapproved_secret_path')
    need(services['redis']['command'] == ['sh', '/redis.sh'], 'unapproved_redis_entrypoint')
    need(services['api']['command'] == ['uvicorn', 'command_center.api:create_app', '--factory', '--host',
                                      '0.0.0.0', '--port', '8000', '--no-access-log'], 'unapproved_api_command')
    need(services['db']['healthcheck'] == {'test': ['CMD-SHELL', 'pg_isready -U f1_admin -d f1'],
         'interval': '5s', 'timeout': '2s', 'retries': 12}, 'unapproved_health_command')
    return {'status': 'PASS_TEMPLATE_ONLY', 'deployable': False, 'gates': meta['blockers']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--require-deployable', action='store_true')
    args = parser.parse_args()
    try:
        result = validate(json.loads(args.file.read_text()), require_deployable=args.require_deployable)
    except (Invalid, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f'INVALID: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
