"""Pinned rootless broker attestation for an explicitly installed planning host."""
import hashlib
import json
import os
import re
from pathlib import Path
import socket
import time

from pydantic import Field

from .planning_profile import load
from .request_planning import HEX, Strict, _unique
from .store import Denied, digest
from .telegram_transport import private_read

BROKER_COMMAND = ['uvicorn', 'command_center.runtime_broker:create_broker_app', '--factory',
                  '--uds', '/run/f1-broker/runtime.sock', '--no-access-log']


class HostDeclaration(Strict):
    source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    container_name: str = Field(pattern=r'^acc-(?:f1|f23)-runtime-broker-1$')
    image_id: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    endpoint: str = Field(pattern=r'^unix:///(?:var/run/docker\.sock|run/user/[0-9]+/docker\.sock)$')
    ledger_path: str = Field(min_length=1, max_length=300)
    metadata_digest: str = Field(pattern=HEX)


def public_environment(config):
    names = {'PATH', 'PYTHONPATH', 'F1_SOURCE_REVISION', 'F1_RUNTIME_MODE', 'F1_RUNTIME_SOCKET'}
    return {k: v for item in config.get('Env', []) for k, _, v in [item.partition('=')] if k in names}


def metadata_document(info):
    """Only policy-relevant metadata; never return or hash environment credential values."""
    config, host = info['Config'], info['HostConfig']
    return {'image': info['Image'], 'user': config['User'],
        'working_dir': config.get('WorkingDir'), 'command': config.get('Cmd'),
        'entrypoint': config.get('Entrypoint'),
        'environment': public_environment(config),
        'policy': {k: host.get(k) for k in ('ReadonlyRootfs', 'Privileged', 'CapDrop', 'CapAdd',
            'SecurityOpt', 'Memory', 'NanoCpus', 'PidsLimit', 'NetworkMode', 'PidMode', 'IpcMode',
            'UsernsMode', 'Devices', 'DeviceRequests', 'PortBindings')},
        'mounts': sorted([{'source': m['Source'], 'target': m['Destination'], 'rw': m['RW']}
                          for m in info.get('Mounts', [])], key=lambda v: (v['target'], v['source']))}


class PlanningHost:
    def __init__(self, declaration_file, approved_sha256):
        self.path, self.pin = declaration_file, approved_sha256
        self.declaration = self._load()
        self.attested = False
        self.container_id = None

    def _load(self):
        try:
            raw = private_read(self.path, 16384)
            if hashlib.sha256(raw).hexdigest() != self.pin:
                raise ValueError()
            return HostDeclaration.model_validate(json.loads(raw, object_pairs_hook=_unique))
        except (OSError, ValueError, Denied):
            raise Denied('planning_host_declaration_invalid') from None

    def current(self, store, ledger, backend):
        declaration = self._load()
        profile = load()
        if (declaration != self.declaration or profile is None or profile.runtime is None
                or profile.runtime.binding_digest != digest(declaration.model_dump())
                or profile.runtime.source_revision != declaration.source_revision
                or declaration.source_revision != store.settings.source_revision
                or backend.mode != 'rootless-required' or backend.endpoint != declaration.endpoint
                or not Path(declaration.ledger_path).is_absolute()
                or Path(declaration.ledger_path).resolve() != ledger.path.resolve()):
            raise Denied('planning_host_binding_changed')
        return profile

    def preflight(self, store, ledger, backend):
        self.attested = False
        self.container_id = None
        self.current(store, ledger, backend)
        proof = backend.preflight()
        if proof.get('mode') != 'rootless-required' or proof.get('rootless_verified') is not True:
            raise Denied('planning_rootless_required')
        try:
            result = backend.call('inspect', self.declaration.container_name)
            if result.returncode or len(result.stdout) > 262144:
                raise ValueError()
            info = json.loads(result.stdout)[0]
            config, host = info['Config'], info['HostConfig']
            environment = public_environment(config)
            if (not re.fullmatch('[a-f0-9]{64}', info['Id'])
                    or info.get('Name') != '/' + self.declaration.container_name
                    or info['Image'] != self.declaration.image_id
                    or not info['State']['Running'] or info['State'].get('OOMKilled')
                    or config['Hostname'] != socket.gethostname()
                    or config['User'].split(':')[0] != str(os.geteuid())
                    or config.get('WorkingDir') != '/app' or config.get('Entrypoint') not in (None, [])
                    or environment.get('F1_SOURCE_REVISION') != self.declaration.source_revision
                    or environment.get('PYTHONPATH') != '/app/src'
                    or any(item.partition('=')[0] in {'LD_PRELOAD', 'LD_LIBRARY_PATH', 'PYTHONHOME'}
                           for item in config.get('Env', []))
                    or config.get('Cmd') != BROKER_COMMAND
                    or not host['ReadonlyRootfs'] or host['Privileged'] or host.get('CapAdd')
                    or host.get('CapDrop') != ['ALL'] or 'no-new-privileges:true' not in host.get('SecurityOpt', [])
                    or any('unconfined' in v or v == 'label=disable' for v in host.get('SecurityOpt', []))
                    or host.get('NetworkMode') == 'host' or str(host.get('NetworkMode', '')).startswith('container:')
                    or any(host.get(k) == 'host' for k in ('PidMode', 'IpcMode', 'UsernsMode'))
                    or host.get('Devices') or host.get('DeviceRequests') or host.get('PortBindings')
                    or not 0 < host['Memory'] <= 256 * 1024 * 1024
                    or not 0 < host['NanoCpus'] <= 1_000_000_000 or not 0 < host['PidsLimit'] <= 128
                    or any(m['Destination'] == '/' or any(m['Destination'] == base or
                           m['Destination'].startswith(base + '/') for base in ('/app', '/usr', '/bin', '/lib', '/sbin'))
                           for m in info.get('Mounts', []))
                    or digest(metadata_document(info)) != self.declaration.metadata_digest):
                raise ValueError()
            image = backend.call('image', 'inspect', self.declaration.image_id)
            if image.returncode or len(image.stdout) > 262144:
                raise ValueError()
            image = json.loads(image.stdout)[0]
            image_environment = dict(item.split('=', 1) for item in image['Config'].get('Env', []))
            code_environment_changed = any((k == 'PATH' or k.startswith(('PYTHON', 'LD_')))
                and image_environment.get(k) != v for item in config.get('Env', []) for k, _, v in [item.partition('=')])
            if (image['Id'] != self.declaration.image_id or image['Config']['Labels'].get(
                    'org.opencontainers.image.revision') != self.declaration.source_revision
                    or code_environment_changed):
                raise ValueError()
        except (ValueError, KeyError, TypeError, IndexError):
            raise Denied('planning_broker_image_or_policy_unverified') from None
        self.attested = True
        self.container_id = info['Id']
        ledger.record('planning_host_attested', revision=self.declaration.source_revision,
                      container_id=self.container_id, image_id=self.declaration.image_id,
                      binding_digest=digest(self.declaration.model_dump()))

    def guard(self, binding, store, ledger, backend, limits, task):
        try:
            profile = self.current(store, ledger, backend)
            ledger.verify()
            row = ledger.get(task['id'], task['fence'])
            return bool(self.attested and binding == profile.runtime.model_dump()
                and row['kind'] == 'planning_http' and not row['returned'] and row['phase'] == 'ACTIVE'
                and row['revision'] == store.settings.source_revision and time.time() < row['deadline']
                and ledger.watchdog_ready(limits.watchdog_seconds)
                and ledger.worker_fresh(store.settings.source_revision, limits.heartbeat_seconds))
        except (Denied, ValueError, OSError):
            return False
