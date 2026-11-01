"""A deployment's byte pin includes credential references excluded from profile_hash."""
import hashlib
import json

import pytest

from command_center.coding.integration_config import IntegrationConfig


@pytest.fixture
def pinned(monkeypatch, tmp_path):
    path = tmp_path / 'config.json'
    raw = json.dumps({'mode': 'disabled', 'credential_files': {'openai': '/run/f2/openai.key'}}).encode()
    path.write_bytes(raw)
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_FILE', str(path))
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_SHA256', hashlib.sha256(raw).hexdigest())
    return path


def test_exact_pinned_bytes_load_without_opening_credentials(pinned):
    config = IntegrationConfig.load()
    assert config.mode == 'disabled' and config.credential_files == {'openai': '/run/f2/openai.key'}


@pytest.mark.parametrize('change', ['credential_reference', 'operator_flag', 'formatting'])
def test_pin_rejects_even_semantically_excluded_reference_or_format_changes(pinned, change):
    data = json.loads(pinned.read_bytes())
    if change == 'credential_reference':
        data['credential_files']['openai'] = '/run/secrets/db_runtime_password'
    elif change == 'operator_flag':
        data['live_authorized'] = True
    pinned.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValueError, match='integration_config_pin_changed'):
        IntegrationConfig.load()


@pytest.mark.parametrize('value', ['', 'G' * 64, 'a' * 63, '0' * 64])
def test_invalid_or_wrong_pin_fails_closed(pinned, monkeypatch, value):
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_SHA256', value)
    with pytest.raises(ValueError, match='integration_config_pin_changed'):
        IntegrationConfig.load()


def test_pin_without_selector_cannot_silently_fall_back_to_defaults(monkeypatch):
    monkeypatch.delenv('F2_INTEGRATION_CONFIG_FILE', raising=False)
    monkeypatch.setenv('F2_INTEGRATION_CONFIG_SHA256', 'a' * 64)
    with pytest.raises(ValueError, match='integration_config_pin_without_file'):
        IntegrationConfig.load()


def test_legacy_unpinned_operator_loader_stays_compatible(pinned, monkeypatch):
    monkeypatch.delenv('F2_INTEGRATION_CONFIG_SHA256')
    assert IntegrationConfig.load().mode == 'disabled'
