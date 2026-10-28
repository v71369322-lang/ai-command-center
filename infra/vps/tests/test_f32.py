"""Offline guards for preparing a disabled Telegram update, never installation."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('F32_SOURCE_REPOSITORY', ROOT.parents[1]))
spec = importlib.util.spec_from_file_location('f32_channel', ROOT / 'f32/prepare_channel.py')
channel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(channel)


def test_telegram_update_exact_source(tmp_path):
    tmp_path.chmod(0o700)
    packet = tmp_path / 'packet.json'
    channel.pack(SOURCE, packet)
    channel.hydrate(packet, tmp_path / 'source')
    assert channel.REVISION == 'a994de96c2f9656f1d766a849e63a6836e21ef65'
    assert channel.git(tmp_path / 'source', 'rev-parse', 'HEAD').decode().strip() == channel.REVISION
    assert channel.git(tmp_path / 'source', 'status', '--porcelain') == b''


@pytest.mark.parametrize('attack', ['revision', 'object', 'duplicate', 'type'])
def test_telegram_update_rejects_source_tampering(tmp_path, attack):
    packet = tmp_path / 'packet.json'
    channel.pack(SOURCE, packet)
    p = json.loads(packet.read_bytes())
    if attack == 'revision':
        p['revision'] = '4cc6ec46bf461d65958f013bb23ac2234b9a7fd3'
    elif attack == 'object':
        p['objects'][0]['data'] = base64.b64encode(b'not approved').decode()
    elif attack == 'duplicate':
        p['objects'].append(p['objects'][0])
    else:
        p['objects'][0]['type'] = 'shell'
    with pytest.raises(ValueError):
        channel.validate(json.dumps(p).encode())


def test_telegram_update_keeps_state_and_cannot_install():
    p = (ROOT / 'f32/prepare_fixed_release.sh').read_text()
    assert 'init-state' not in p
    assert '--data-root /home/acc-control/f30/state' in p
    assert '--owner-password-origin http://127.0.0.1:18000 --password-loopback-http' in p
    assert 'cmp requirements.lock /home/acc-control/f31/source/requirements.lock' in p
    assert 'deployment install' not in p and 'deployment update' not in p
    assert 'tools=/home/acc-control/f30/tools' in p
    assert 'base=/home/acc-control/f32' in p


def test_telegram_update_bootstrap_hashes_and_no_old_overwrite():
    p = (ROOT / 'f32/enable_prepare_channel.sh').read_text()
    for digest, name in re.findall(r'^([a-f0-9]{64})  (.+)$', p, re.M):
        assert hashlib.sha256((ROOT / 'f32' / name).read_bytes()).hexdigest() == digest
    assert '/home/acc-control/f30' not in p
    assert 'acc-telegram-prepare-fixed.service' in p
    assert 'acc-prepare-fixed.service" /etc/systemd/system/acc-prepare-fixed.service' not in p


def test_telegram_preparation_is_bound_to_verified_password_receipt():
    p = (ROOT / 'f32/prepare_fixed_release.sh').read_text()
    assert '1e151b2953b6debb4bb05096fba20aa6c740665015f31479a50fd25c6ef80106' in p
    assert '4cc6ec46bf461d65958f013bb23ac2234b9a7fd3' in p
    assert 'a994de96c2f9656f1d766a849e63a6836e21ef65' in p
    assert '--telegram-connection-digest' not in p
    assert 'telegram_transition' not in p
