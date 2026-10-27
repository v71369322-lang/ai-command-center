import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('prepare_channel', Path(__file__).parents[1] / 'prepare_channel.py')
channel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(channel)


def test_exact_source_handoff(tmp_path):
    tmp_path.chmod(0o700)
    packet = tmp_path / 'source.json'
    channel.pack(Path(__file__).resolve().parents[3], packet)
    channel.hydrate(packet, tmp_path / 'checkout')
    assert channel.git(tmp_path / 'checkout', 'rev-parse', 'HEAD').decode().strip() == channel.REVISION
    assert channel.git(tmp_path / 'checkout', 'status', '--porcelain') == b''
    with pytest.raises(ValueError, match='destination_exists'):
        channel.hydrate(packet, tmp_path / 'checkout')


@pytest.mark.parametrize('attack', ['revision', 'data', 'type', 'duplicate'])
def test_source_tampering_rejected(tmp_path, attack):
    packet = tmp_path / 'source.json'
    channel.pack(Path(__file__).resolve().parents[3], packet)
    value = json.loads(packet.read_bytes())
    if attack == 'revision':
        value['revision'] = 'a' * 40
    elif attack == 'data':
        value['objects'][0]['data'] = 'YWJj'
    elif attack == 'type':
        value['objects'][0]['type'] = 'shell'
    else:
        value['objects'].append(value['objects'][0])
    with pytest.raises(ValueError):
        channel.validate(json.dumps(value).encode())


def test_symlink_packet_rejected(tmp_path):
    packet = tmp_path / 'symlink'
    packet.symlink_to(tmp_path / 'missing')
    with pytest.raises(OSError):
        channel.hydrate(packet, tmp_path / 'checkout')
