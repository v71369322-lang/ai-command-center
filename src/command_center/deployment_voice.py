"""Exact optional speech-service release binding, never an arbitrary executor."""
from datetime import datetime
import os
from pathlib import Path
import re
import stat

from .offline_speech import MODEL_FILES, verify_model
from .store import digest
from .telegram_transport import private_read
from .voice_profile import VoiceProfile

PROFILE = '/run/voice/profile.json'
MODEL = '/models/whisper-base'


def validate_binding(m):
    voice = m['voice']
    if ('telegram' not in m or any(k in m for k in ('planning', 'first_experiment'))
            or not isinstance(voice, dict)
            or set(voice) != {'image', 'profile_directory', 'profile_digest', 'model_directory', 'model_manifest'}
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', voice.get('image', ''))
            or not re.fullmatch(r'[a-f0-9]{64}', voice.get('profile_digest', ''))
            or not isinstance(voice.get('model_manifest'), dict)
            or set(voice['model_manifest']) != set(MODEL_FILES)
            or any(not re.fullmatch(r'[a-f0-9]{64}', value) for value in voice['model_manifest'].values())):
        raise ValueError('voice_release_binding_invalid')
    for key in ('profile_directory', 'model_directory'):
        path = Path(voice[key])
        if (not path.is_absolute() or '..' in path.parts
                or not path.is_relative_to(Path(m['data_root']) / 'voice')):
            raise ValueError('voice_private_artifact_path_required')


def check_binding(m):
    validate_binding(m)
    voice = m['voice']
    root = Path(m['data_root'])
    for key in ('profile_directory', 'model_directory'):
        for path in (Path(voice[key]), *Path(voice[key]).parents):
            if path == root:
                break
            info = path.lstat()
            if path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError('voice_artifact_parent_custody_changed')
    profile = VoiceProfile.model_validate_json(private_read(Path(voice['profile_directory']) / 'profile.json', 8192))
    if (not profile.enabled or digest(profile.model_dump()) != voice['profile_digest']
            or profile.source_revision != m['revision']
            or profile.connection_digest != m['telegram']['connection_digest']
            or profile.connection_file != '/run/telegram/connection.json'
            or profile.model_directory != MODEL or profile.model_manifest != voice['model_manifest']):
        raise ValueError('voice_exact_profile_required')
    since = datetime.fromisoformat(profile.since)
    if since.tzinfo is None or since.utcoffset() is None:
        raise ValueError('voice_cutover_timezone_required')
    model = Path(voice['model_directory'])
    for path in (model, *(model / name for name in MODEL_FILES)):
        info = path.lstat()
        if (path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) if path == model else
                        stat.S_ISREG(info.st_mode) and info.st_nlink == 1)):
            raise ValueError('voice_model_custody_changed')
    verify_model(model, voice['model_manifest'])
    return profile


def service(m):
    validate_binding(m)
    voice = m['voice']
    return {
        'image': voice['image'], 'user': '0:0', 'restart': 'no',
        'entrypoint': ['python', '-m', 'command_center.voice_worker'],
        'command': ['run', '--config', PROFILE, '--approved-profile', voice['profile_digest']],
        'environment': {'F1_SOURCE_REVISION': m['revision'], 'F1_DB_USER': 'f1_app', 'F1_DB_HOST': 'db',
            'F1_DB_PASSWORD_FILE': '/run/secrets/db_password', 'HF_HUB_OFFLINE': '1',
            'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1', 'TRANSFORMERS_OFFLINE': '1', 'OMP_NUM_THREADS': '1'},
        'secrets': ['db_password'],
        'volumes': [
            {'type': 'bind', 'source': str(Path(m['data_root']) / 'telegram'),
             'target': '/run/telegram', 'read_only': True},
            {'type': 'bind', 'source': voice['profile_directory'], 'target': '/run/voice', 'read_only': True},
            {'type': 'bind', 'source': voice['model_directory'], 'target': MODEL, 'read_only': True}],
        'networks': {'control': None, 'telegram-access': None},
        'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
        'mem_limit': '1g', 'cpus': 1, 'pids_limit': 64,
        'tmpfs': ['/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777'],  # nosec B108
        'stop_grace_period': '95s', 'depends_on': {'db': {'condition': 'service_healthy'}},
        'logging': {'driver': 'local', 'options': {'max-size': '1m', 'max-file': '2'}},
    }


def check_runtime(m, metadata):
    expected = service(m)
    state, host = metadata['State'], metadata['HostConfig']
    config = metadata['Config']
    if (not state['Running'] or metadata['Image'] != m['voice']['image']
            or config['User'] != '0:0' or config.get('Entrypoint') != expected['entrypoint']
            or config.get('Cmd') != expected['command'] or not host['ReadonlyRootfs']
            or host.get('Privileged') or host.get('CapAdd') or host.get('Devices')
            or host.get('CapDrop') != ['ALL'] or host.get('Memory') != 1024**3
            or host.get('NanoCpus') != 10**9 or host.get('PidsLimit') != 64
            or host.get('RestartPolicy', {}).get('Name') not in {'no', ''}
            or host.get('PortBindings')
            or host.get('PidMode') or host.get('IpcMode') not in {'private', ''}
            or set(host.get('SecurityOpt') or []) not in ({'no-new-privileges'}, {'no-new-privileges:true'})
            or set(metadata['NetworkSettings']['Networks']) != {'acc-f23_control', 'acc-f23_telegram-access'}):
        raise ValueError('voice_runtime_boundary_changed')
    mounts = {(v['Source'], v['Destination'], v['RW']) for v in metadata['Mounts']
              if v.get('Type') != 'tmpfs'}
    wanted = {(v['source'], v['target'], False) for v in expected['volumes']}
    wanted.add((str(Path(m['data_root']) / 'secrets/db_password'), '/run/secrets/db_password', False))
    if mounts != wanted:
        raise ValueError('voice_runtime_mount_changed')
    env = dict(value.split('=', 1) for value in config.get('Env', []))
    if (any(env.get(k) != v for k, v in expected['environment'].items())
            or any(k.startswith(('F2_', 'F21_')) or k.startswith('F1_') and k not in expected['environment']
                   or k.upper().endswith('_PROXY') or k in {'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN', 'SSL_CERT_FILE',
                                                          'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE'} for k in env)):
        raise ValueError('voice_runtime_environment_changed')


def heartbeat_check_code(m):
    profile = digest({'owner': m['telegram']['owner_id'], 'bot_id': m['telegram']['bot_id'], 'mode': 'live'})
    return ('from datetime import datetime;from sqlalchemy import select;'
            'from command_center.models import Audit;from command_center.config import Settings;'
            'from command_center.store import Store;'
            's=Store(Settings.load());'
            'exec(' + repr(
                "with s.transaction() as tx:\n"
                " row=tx.scalar(select(Audit).where(Audit.event['kind'].as_string()=="
                "'telegram_voice_worker_heartbeat',Audit.event['profile'].as_string()==" + repr(profile)
                + ").order_by(Audit.sequence.desc()).limit(1))\n"
                " assert row is not None\n"
                " e=row.event\n"
                " assert e['revision']==" + repr(m['revision']) + "\n"
                " assert e['profile_digest']==" + repr(m['voice']['profile_digest']) + "\n"
                " assert e['model_fingerprint']==" + repr(digest(m['voice']['model_manifest'])) + "\n"
                " assert 0 <= (s.now(tx)-datetime.fromisoformat(e['time'])).total_seconds() <= 45\n"
                " assert e['state']=='PAUSED' and e['paid_api'] is False\n") + ')')
