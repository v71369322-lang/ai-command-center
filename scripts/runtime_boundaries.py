"""Inspect only owned cloud containers; publish booleans/digests, never env values."""
import json
import os
from pathlib import Path

from command_center.worker import docker


def main():
    evidence = {'revision': os.environ['F1_SOURCE_REVISION'], 'status': 'PASS'}
    for service in ('api', 'worker'):
        result = docker('inspect', 'acc-f1-' + service + '-1')
        if result.returncode:
            raise RuntimeError('missing_runtime_container')
        info = json.loads(result.stdout)[0]
        host, config = info['HostConfig'], info['Config']
        mounts = {item['Destination'] for item in info['Mounts']}
        if (config['User'].split(':')[0] == '0' or host['Privileged'] or not host['ReadonlyRootfs']
                or host['CapDrop'] != ['ALL'] or 'no-new-privileges:true' not in host['SecurityOpt']
                or config['Labels']['org.opencontainers.image.revision'] != os.environ['F1_SOURCE_REVISION']
                or not info['State']['Running'] or '/run/secrets/db_admin_password' in mounts):
            raise RuntimeError('runtime_boundary_mismatch')
        if service == 'api':
            ports = info['NetworkSettings']['Ports'].get('8000/tcp') or []
            if '/var/run/docker.sock' in mounts or not ports or any(p['HostIp'] != '127.0.0.1' for p in ports):
                raise RuntimeError('api_runtime_exposed')
        elif '/run/secrets/identities' in mounts or '/var/run/docker.sock' not in mounts:
            raise RuntimeError('worker_credential_boundary_mismatch')
        evidence[service] = {'image_id': info['Image'], 'non_root': True, 'read_only_root': True,
                             'admin_db_secret_mounted': False,
                             'docker_socket_mounted': service == 'worker',
                             'owner_credentials_mounted': service == 'api'}
    Path('.runtime/container-boundaries.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('Runtime API/worker permissions, secret mounts and loopback binding: PASS')


if __name__ == '__main__':
    main()
