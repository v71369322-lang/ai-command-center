"""Offline checkpoint for the next mobile/project release; never touches a host."""

import json
from pathlib import Path
import subprocess

BASE = '322186dc180257c618d8b159c78faa6e5bbf0b43'
TARGET = 'c3619ea0b94efcc0f0acae462bebefd3c4808eea'
PROTECTED = ('src/command_center/models.py', 'requirements.lock', 'uv.lock', 'Dockerfile',
             'Dockerfile.executor', 'compose.yaml', 'web/package-lock.json')
REQUIRED = ('src/command_center/telegram_voice_requests.py',
            'src/command_center/telegram_voice_transcripts.py',
            'src/command_center/telegram_system.py', 'src/command_center/project_connections.py',
            'src/command_center/project_repair_control.py')


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, check=False)


def inspect(root):
    root = Path(root).resolve()
    if git(root, 'merge-base', '--is-ancestor', BASE, TARGET).returncode:
        raise RuntimeError('release_target_not_descendant')
    if git(root, 'rev-parse', '--verify', TARGET + '^{commit}').returncode:
        raise RuntimeError('release_target_missing')
    changed = []
    for name in PROTECTED:
        old, new = git(root, 'show', f'{BASE}:{name}'), git(root, 'show', f'{TARGET}:{name}')
        if old.returncode or new.returncode:
            raise RuntimeError('protected_file_missing')
        if old.stdout != new.stdout:
            changed.append(name)
    missing = [name for name in REQUIRED if git(root, 'cat-file', '-e', f'{TARGET}:{name}').returncode]
    if changed or missing:
        raise RuntimeError('release_boundary_changed')
    return {'schema': 1, 'status': 'OFFLINE_RELEASE_CHECKPOINT', 'base_revision': BASE,
            'target_revision': TARGET, 'protected_files_unchanged': True,
            'required_features_present': True, 'external_calls': 0, 'paid_calls': 0,
            'deployment_started': False, 'live_binding_modified': False,
            'blockers': ['live_bundle_reconciliation_required', 'exact_operator_profile_not_prepared',
                         'rootless_images_not_built_for_target', 'vps_postcheck_not_run']}


if __name__ == '__main__':
    print(json.dumps(inspect(Path(__file__).resolve().parents[1]), sort_keys=True))
