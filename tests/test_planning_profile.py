"""Pinned evidence configuration is closed by default and contains no credentials."""
import hashlib
import json

import pytest

from command_center.planning_profile import load
from command_center.store import Denied
from test_planning_admission import profile as profile


@pytest.fixture
def bound(tmp_path, profile, monkeypatch):
    directory = tmp_path / 'private'
    directory.mkdir(mode=0o700)
    path = directory / 'planning.json'
    raw = profile.model_dump_json().encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    monkeypatch.setenv('F1_PLANNING_PROFILE_FILE', str(path))
    monkeypatch.setenv('F1_PLANNING_PROFILE_SHA256', hashlib.sha256(raw).hexdigest())
    return path, raw, directory


def test_default_disabled(monkeypatch):
    monkeypatch.delenv('F1_PLANNING_PROFILE_FILE', raising=False)
    monkeypatch.delenv('F1_PLANNING_PROFILE_SHA256', raising=False)
    assert load() is None


def test_exact_pinned_profile(bound, profile):
    assert load() == profile


@pytest.mark.parametrize('change', ['pin_missing', 'path_missing', 'pin_invalid', 'changed', 'symlink',
    'file_mode', 'directory_mode', 'hardlink', 'oversize', 'directory', 'duplicate', 'credentials'])
def test_unsafe_or_ambiguous_profile_rejected(bound, monkeypatch, change):
    path, raw, directory = bound
    if change == 'pin_missing':
        monkeypatch.delenv('F1_PLANNING_PROFILE_SHA256')
    elif change == 'path_missing':
        monkeypatch.delenv('F1_PLANNING_PROFILE_FILE')
    elif change == 'pin_invalid':
        monkeypatch.setenv('F1_PLANNING_PROFILE_SHA256', 'invalid')
    elif change == 'changed':
        path.write_bytes(raw + b' ')
    elif change == 'symlink':
        target = directory / 'target'
        path.rename(target)
        path.symlink_to(target)
    elif change == 'hardlink':
        (directory / 'link').hardlink_to(path)
    elif change == 'file_mode':
        path.chmod(0o644)
    elif change == 'directory_mode':
        directory.chmod(0o755)
    elif change == 'directory':
        monkeypatch.setenv('F1_PLANNING_PROFILE_FILE', str(directory))
    else:
        if change == 'oversize':
            raw = b' ' * 16385
        elif change == 'duplicate':
            raw = raw[:-1] + b',"schema_version":1}'
        else:
            data = json.loads(raw)
            data['credential_files'] = {'openai': '/not/a/credential'}
            raw = json.dumps(data).encode()
        path.write_bytes(raw)
        monkeypatch.setenv('F1_PLANNING_PROFILE_SHA256', hashlib.sha256(raw).hexdigest())
    with pytest.raises(Denied, match='planning_profile_invalid_or_unavailable'):
        load()
