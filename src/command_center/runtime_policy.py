"""Fixed, bounded runtime policy. No arbitrary Docker request forwarding."""
from dataclasses import dataclass
import json
import os
import re
import subprocess

from .local_docker import environment


@dataclass(frozen=True)
class RuntimeLimits:
    cpu: float = .5
    memory_mib: int = 128
    pids: int = 32
    disk_mib: int = 16
    output_kib: int = 64
    wall_seconds: int = 30
    heartbeat_seconds: int = 10
    min_free_mib: int = 256
    log_mib: int = 1
    log_files: int = 2
    file_kib: int = 64
    stop_attempts: int = 2
    watchdog_seconds: int = 10

    def __post_init__(self):
        bounds = {'cpu': (.1, 1), 'memory_mib': (32, 256), 'pids': (8, 64), 'disk_mib': (1, 32),
                  'output_kib': (1, 64), 'wall_seconds': (1, 120), 'heartbeat_seconds': (1, 30),
                  'min_free_mib': (256, 65536), 'log_mib': (1, 4), 'log_files': (1, 3),
                  'file_kib': (1, 128), 'stop_attempts': (1, 3), 'watchdog_seconds': (1, 30)}
        for key, (low, high) in bounds.items():
            value = getattr(self, key)
            if isinstance(value, bool) or (key != 'cpu' and type(value) is not int) or not low <= value <= high:
                raise ValueError('unsafe_runtime_limit:' + key)

    @classmethod
    def load(cls):
        values = {}
        for key in cls.__dataclass_fields__:
            raw = os.environ.get('F1_LIMIT_' + key.upper())
            if raw is not None:
                values[key] = float(raw) if key == 'cpu' else int(raw)
        return cls(**values)


class RuntimeBackend:
    def __init__(self, endpoint=None, mode=None):
        self.endpoint = endpoint or os.environ.get('F1_RUNTIME_SOCKET', 'unix:///var/run/docker.sock')
        self.mode = mode or os.environ.get('F1_RUNTIME_MODE', 'rootless-required')
        if not re.fullmatch(r'unix:///(?:var/run/docker\.sock|run/user/[0-9]+/docker\.sock)', self.endpoint):
            raise ValueError('unapproved_runtime_endpoint')
        if self.mode not in {'rootless-required', 'cloud-rootful-test'}:
            raise ValueError('unapproved_runtime_mode')

    def call(self, *args, timeout=10, **kwargs):
        return subprocess.run(['docker', '--host=' + self.endpoint, *args], env=environment(),
                              capture_output=True, timeout=timeout, **kwargs)

    def preflight(self):
        result = self.call('info', '--format', '{{json .}}')
        if result.returncode:
            raise RuntimeError('runtime_unavailable')
        info = json.loads(result.stdout)
        options = info.get('SecurityOptions', [])
        if self.mode == 'rootless-required' and not any('rootless' in str(v) for v in options):
            raise RuntimeError('rootless_not_verified')
        if self.mode == 'rootless-required' and (info.get('CgroupVersion') != '2' or info.get('CgroupDriver') != 'systemd'):
            raise RuntimeError('rootless_cgroup_delegation_not_verified')
        return {'mode': self.mode, 'rootless_verified': any('rootless' in str(v) for v in options)}
