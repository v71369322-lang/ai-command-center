"""Actual runtime proof for the restriction-only assistant profile."""
from pathlib import Path


def check_runtime(m, name, metadata, service):
    if not m.get('assistant_only'):
        raise ValueError('assistant_profile_required')
    host, config = metadata['HostConfig'], metadata['Config']
    if (host.get('Privileged') or host.get('CapAdd') or host.get('Devices') or host.get('DeviceRequests')
            or host.get('PidMode') or host.get('IpcMode') not in {'private', ''}
            or host.get('UsernsMode') or any(
            'sock' in item.get('Destination', '') for item in metadata.get('Mounts', []))):
        raise ValueError('assistant_host_access_forbidden')
    if name not in {'api', 'telegram', 'voice'}:
        return
    expected_image = m['voice']['image'] if name == 'voice' else m['images']['api']
    env = dict(item.split('=', 1) for item in config.get('Env', []) if '=' in item)
    if (metadata['Image'] != expected_image or env.get('F1_ASSISTANT_ONLY') != '1'
            or env.get('F1_SOURCE_REVISION') != m['revision']
            or config['User'] != '0:0' or not host.get('ReadonlyRootfs')
            or set(host.get('CapDrop') or []) != {'ALL'}
            or 'no-new-privileges' not in ' '.join(host.get('SecurityOpt') or [])):
        raise ValueError('assistant_runtime_policy_changed')
    if any(key.startswith(('F2_', 'F21_', 'F1_PLANNING_', 'OPENAI_', 'GITHUB_')) for key in env):
        raise ValueError('assistant_provider_access_forbidden')
    memory = str(service['mem_limit']).lower()
    memory = int(memory[:-1]) * {'m': 1024**2, 'g': 1024**3}[memory[-1]] if memory[-1] in 'mg' else int(memory)
    if (host.get('Memory') != memory or host.get('NanoCpus') != int(float(service['cpus']) * 10**9)
            or host.get('PidsLimit') != service['pids_limit']
            or set(metadata['NetworkSettings']['Networks']) != {'acc-f23_' + k for k in service['networks']}
            or any(env.get(k) != str(v) for k, v in service['environment'].items())
            or any(k.startswith('F1_') and k not in service['environment'] for k in env)):
        raise ValueError('assistant_runtime_bounds_or_environment_changed')
    expected = {(v['source'], v['target'], False) for v in service.get('volumes', [])}
    for secret in service.get('secrets', []):
        key = secret['source'] if isinstance(secret, dict) else secret
        expected.add((str(Path(m['data_root']) / 'secrets' / key), '/run/secrets/' + key, False))
    actual = {(v['Source'], v['Destination'], v['RW']) for v in metadata.get('Mounts', [])
              if v.get('Type') != 'tmpfs'}
    if actual != expected:
        raise ValueError('assistant_runtime_mount_changed')
