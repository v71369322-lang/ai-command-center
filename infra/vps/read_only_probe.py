"""Local-only read-only inventory. No SSH, network probes, secrets or config changes.
Run on a real host ONLY after separate authorization. Output is evidence, not PASS.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

COMMANDS = {
    'kernel': ['uname', '-r'],
    'packages': ['dpkg-query', '-W', '-f=${Package}\t${Version}\t${db:Status-Status}\n',
                 'openssh-server', 'docker.io', 'docker-ce', 'uidmap', 'nftables', 'wireguard-tools'],
    'listeners': ['ss', '-H', '-lntu'],
    'services': ['systemctl', 'is-active', 'ssh', 'docker', 'ufw'],
    'package_audit': ['dpkg', '--audit'],
}


def command(name):
    args = COMMANDS[name]
    if not shutil.which(args[0]):
        return {'state': 'missing_tool'}
    try:
        result = subprocess.run(args, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {'state': 'unavailable'}
    lines = result.stdout.decode(errors='replace').splitlines()
    if name == 'listeners':
        # Do not expose process command lines, usernames or interface addresses.
        ports = []
        for line in lines:
            fields = line.split()
            if len(fields) >= 5:
                port = fields[4].rsplit(':', 1)[-1]
                if port.isdigit():
                    ports.append({'transport': fields[0], 'port': int(port)})
        return {'exit_code': result.returncode, 'ports': ports[:128], 'truncated': len(ports) > 128}
    if name == 'package_audit':
        return {'exit_code': result.returncode, 'output_present': bool(lines)}
    return {'exit_code': result.returncode, 'lines': lines[:32]}


def inventory(root=Path('/'), *, commands=True):
    def read(path):
        try:
            return (root / path).read_text()[:16384]
        except (OSError, UnicodeError):
            return ''
    os_info = {}
    for line in read('etc/os-release').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            if key in {'ID', 'VERSION_ID', 'PRETTY_NAME'}:
                os_info[key] = value.strip('"')
    memory = {}
    for line in read('proc/meminfo').splitlines():
        key, _, value = line.partition(':')
        if key in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
            memory[key] = value.strip()
    disk = shutil.disk_usage(root)
    return {'schema': 1, 'scope': 'local_read_only_no_network', 'readiness': 'UNVERIFIED',
            'os': os_info, 'uid': os.getuid(), 'cpu_count': os.cpu_count(), 'memory': memory,
            'load': read('proc/loadavg').split()[:3],
            'root_disk_bytes': {'total': disk.total, 'free': disk.free},
            'cgroup_controllers': read('sys/fs/cgroup/cgroup.controllers').split(),
            'checks': {name: command(name) for name in COMMANDS} if commands else {}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files-only', action='store_true', help='Skip even local inventory commands')
    args = parser.parse_args()
    print(json.dumps(inventory(commands=not args.files_only), indent=2))


if __name__ == '__main__':
    main()
