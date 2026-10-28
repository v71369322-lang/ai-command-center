"""Source-only rollout checks; no Docker, SSH, credentials or host changes."""
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('F32_SOURCE_REPOSITORY', ROOT.parents[1]))


def load(name):
    spec = importlib.util.spec_from_file_location('f32_' + name, ROOT / ('f32/' + name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


channel, readiness = load('prepare_channel'), load('verify_release')


def read(revision, name):
    return channel.git(SOURCE, 'show', revision + ':' + name)


def test_readiness_reproduces_exact_packet_and_has_no_host_claims(tmp_path):
    result = readiness.report(SOURCE, channel)
    packet = tmp_path / 'source.json'
    channel.pack(SOURCE, packet)
    assert result['revision'] == '316dc1615dea224bcf4bd595d87048d19820bd21'
    assert result['packet_sha256'] == hashlib.sha256(packet.read_bytes()).hexdigest()
    assert result['packet_bytes'] == packet.stat().st_size <= channel.MAX_PACKET
    assert result['git_objects'] <= 5000
    assert result['migration_required'] and not result['generic_update_allowed']
    assert result['telegram_default'] == 'disabled' and result['bundle_digest'] is None
    assert all(result[name] is False for name in ('image_ids_verified', 'host_rootless_verified',
                                                'vps_contacted', 'live_calls_enabled', 'baseline_observed_on_vps'))
    assert result['expected_previous_bundle'] == '1e151b2953b6debb4bb05096fba20aa6c740665015f31479a50fd25c6ef80106'
    for name in ('telegram_requests', 'telegram_bridge', 'telegram_transition'):
        assert 'src/command_center/' + name + '.py' in result['required_files_sha256']


def test_readiness_rejects_unapproved_source(monkeypatch):
    monkeypatch.setattr(channel, 'REVISION', 'a' * 40)
    with pytest.raises(ValueError, match='unapproved_application'):
        readiness.report(SOURCE, channel)


@pytest.mark.parametrize('condition,code', [('lock', 'dependency_mismatch'), ('schema', 'unknown_schema')])
def test_readiness_rejects_changed_dependency_or_schema(condition, code):
    def modified(revision, name):
        data = read(revision, name)
        changed = 'requirements.lock' if condition == 'lock' else 'src/command_center/models.py'
        return data + b'\nchanged\n' if revision == readiness.APPROVED and name == changed else data
    with pytest.raises(ValueError, match=code):
        readiness.compatibility(modified)


def test_readiness_rejects_missing_source_history(monkeypatch):
    def missing(*args):
        raise subprocess.CalledProcessError(1, ['git', 'merge-base'])
    monkeypatch.setattr(channel, 'git', missing)
    with pytest.raises(ValueError, match='source_history_or_required_file_missing'):
        readiness.report(SOURCE, channel)


def test_readiness_rejects_missing_implementation(monkeypatch):
    original = channel.git
    def missing(directory, *args, **kwargs):
        if args == ('show', readiness.APPROVED + ':src/command_center/telegram_requests.py'):
            raise subprocess.CalledProcessError(1, ['git', 'show'])
        return original(directory, *args, **kwargs)
    monkeypatch.setattr(channel, 'git', missing)
    with pytest.raises(ValueError, match='source_history_or_required_file_missing'):
        readiness.report(SOURCE, channel)


def test_cloud_checks_cannot_start_delivery_without_explicit_marker():
    workflow = (ROOT.parents[1] / '.github/workflows/f32-telegram-prepare.yml').read_text()
    assert 'runs-on: ubuntu-24.04' in workflow
    assert 'needs: verify' in workflow
    assert "if: contains(github.event.head_commit.message, '[run-f32]')" in workflow
    assert 'runs-on: [acc-bootstrap-only]' in workflow
    assert 'contents: read' in workflow and 'contents: write' not in workflow
    assert workflow.count('ref: ' + readiness.APPROVED) == 2
