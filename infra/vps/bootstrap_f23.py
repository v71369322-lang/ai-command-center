"""Future local Ubuntu bootstrap. Default: plan only. Never SSH/scans a server.

Run only after host audit and separate host-change permission. Docker versions
must be selected from the official apt repository after audit, not invented here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess

FINGERPRINT = '9DC858229FC7DD38854AE2D88D81803C0EBFCD88'
PACKAGES = ['ca-certificates', 'curl', 'gnupg', 'uidmap', 'dbus-user-session', 'slirp4netns',
            'fuse-overlayfs', 'acl', 'python3', 'python3-venv', 'git', 'nftables', 'wireguard-tools']


def capacity_gate(cpu, memory_mib, free_mib):
    if cpu < 4 or memory_mib < 7168 or free_mib < 15360:
        raise ValueError('host_capacity_below_preparation_floor')


def plan(docker_version, containerd_version, buildx_version, compose_version):
    versions = [docker_version, containerd_version, buildx_version, compose_version]
    if any(not value or any(c not in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.:~+-' for c in value)
           for value in versions):
        raise ValueError('confirmed_apt_versions_required')
    return {'os': 'ubuntu-24.04', 'accounts': ['acc-control', 'acc-exec'], 'system_packages': PACKAGES,
            'docker_packages': ['docker-ce=' + docker_version, 'docker-ce-cli=' + docker_version,
                                'docker-ce-rootless-extras=' + docker_version, 'containerd.io=' + containerd_version,
                                'docker-buildx-plugin=' + buildx_version, 'docker-compose-plugin=' + compose_version],
            'official_key': 'https://download.docker.com/linux/ubuntu/gpg', 'fingerprint': FINGERPRINT,
            'rootful_daemon': 'masked-before-package-install', 'rootless_users': 2,
            'network_changes': False, 'openai_or_github_credentials': False}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def run(*args):
    result = subprocess.run(args, capture_output=True, check=False, timeout=300)
    if result.returncode:
        raise RuntimeError('host_setup_failed:' + args[0])
    return result.stdout


def write_new(path, text, mode=0o644):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    with os.fdopen(fd, 'w') as file:
        file.write(text)


def apply(p, authorization):
    if authorization != digest(p) or os.geteuid() != 0:
        raise ValueError('exact_host_plan_and_admin_authorization_required')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '24.04':
        raise ValueError('ubuntu_2404_required')
    if not Path('/run/systemd/system').is_dir():
        raise ValueError('real_systemd_host_required')
    memory = next(int(line.split()[1]) // 1024 for line in Path('/proc/meminfo').read_text().splitlines()
                  if line.startswith('MemTotal:'))
    capacity_gate(os.cpu_count() or 0, memory, shutil.disk_usage('/').free // 1024 // 1024)
    for account in p['accounts']:
        try:
            pwd.getpwnam(account)
        except KeyError:
            continue
        raise ValueError('account_exists_investigate_before_setup')
    # Never disable an existing daemon or disturb unrelated projects.
    if Path('/var/run/docker.sock').exists() or Path('/var/lib/docker').exists():
        raise ValueError('existing_rootful_runtime_requires_separate_review')
    run('apt-get', 'update')
    run('apt-get', 'install', '-y', '--no-install-recommends', *p['system_packages'])
    key = Path('/etc/apt/keyrings/acc-docker.asc')
    key.parent.mkdir(mode=0o755, exist_ok=True)
    if p['official_key'] != 'https://download.docker.com/linux/ubuntu/gpg':
        raise ValueError('official_key_endpoint_required')
    public_key = run('curl', '--fail', '--silent', '--show-error', '--proto', '=https', '--tlsv1.2',
                     '--max-time', '20', '--max-filesize', '32768', p['official_key'])
    if len(public_key) > 32768:
        raise ValueError('official_public_key_oversized')
    # Verify bytes via stdin before they become apt trust. No curl|shell.
    result = subprocess.run(['gpg', '--batch', '--show-keys', '--with-colons'], input=public_key,
                            capture_output=True, check=True, timeout=10)
    fingerprints = [line.split(':')[9] for line in result.stdout.decode().splitlines() if line.startswith('fpr:')]
    if not fingerprints or fingerprints[0] != FINGERPRINT:
        raise ValueError('docker_signing_key_changed_review_required')
    write_new(key, public_key.decode())
    architecture = run('dpkg', '--print-architecture').decode().strip()
    if architecture != 'amd64':
        raise ValueError('unverified_architecture')
    write_new('/etc/apt/sources.list.d/acc-docker.list',
              'deb [arch=amd64 signed-by=/etc/apt/keyrings/acc-docker.asc] https://download.docker.com/linux/ubuntu noble stable\n')
    run('systemctl', 'mask', 'docker.service', 'docker.socket')
    run('apt-get', 'update')
    run('apt-get', 'install', '-y', '--no-install-recommends', *p['docker_packages'])
    for account in p['accounts']:
        run('useradd', '--create-home', '--shell', '/bin/bash', account)
        uid = pwd.getpwnam(account).pw_uid
        # Ubuntu useradd allocates subordinate IDs; refusal is safer than guessing ranges.
        for file in ('/etc/subuid', '/etc/subgid'):
            if not any(line.startswith(account + ':') and int(line.split(':')[2]) >= 65536
                       for line in Path(file).read_text().splitlines()):
                raise ValueError('subordinate_id_mapping_unavailable')
        run('loginctl', 'enable-linger', account)
        run('systemctl', 'start', f'user@{uid}.service')
        run('runuser', '-u', account, '--', 'env', f'XDG_RUNTIME_DIR=/run/user/{uid}',
            f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus', 'dockerd-rootless-setuptool.sh', 'install')
    control, execution = (pwd.getpwnam(account) for account in p['accounts'])
    override = Path(execution.pw_dir) / '.config/systemd/user/docker.service.d'
    override.mkdir(mode=0o700, parents=True, exist_ok=True)
    content = ('[Service]\nExecStartPost=/usr/bin/setfacl -m u:' + str(control.pw_uid) + ':--x %t\n'
               'ExecStartPost=/usr/bin/setfacl -m u:' + str(control.pw_uid) + ':rw %t/docker.sock\n')
    write_new(override / 'control-access.conf', content, 0o600)
    for path in (override.parent.parent, override.parent, override, override / 'control-access.conf'):
        os.chown(path, execution.pw_uid, execution.pw_gid)
    for command in [('daemon-reload',), ('restart', 'docker.service')]:
        run('runuser', '-u', 'acc-exec', '--', 'env', f'XDG_RUNTIME_DIR=/run/user/{execution.pw_uid}',
            f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{execution.pw_uid}/bus', 'systemctl', '--user', *command)
    print(json.dumps({'state': 'HOST_SETUP_REQUIRES_POSTCHECK', 'control_uid': control.pw_uid,
                      'execution_uid': execution.pw_uid, 'firewall_changed': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('docker-version', 'containerd-version', 'buildx-version', 'compose-version'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--approved-plan')
    args = parser.parse_args()
    p = plan(args.docker_version, args.containerd_version, args.buildx_version, args.compose_version)
    if args.approved_plan:
        apply(p, args.approved_plan)
    else:
        print(json.dumps({'plan': p, 'digest': digest(p), 'host_changed': False}, indent=2))


if __name__ == '__main__':
    main()
