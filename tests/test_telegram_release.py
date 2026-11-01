"""Public fake token, protected files and zero-network provisioning."""
import json

import pytest

from command_center.store import Denied
from command_center.telegram_release import binding, preflight, provision

PUBLIC = '123456789:' + 'PUBLIC_SYNTHETIC_FIXTURE_NOT_REAL_12345'
REVISION = 'a' * 40


def test_offline_provision_protects_files_and_never_enables_live(tmp_path):
    path = tmp_path / 'telegram'
    result = provision(path, REVISION, 1234567, PUBLIC)
    assert result['api_contacted'] is False and result['live_enabled'] is False
    assert PUBLIC not in json.dumps(result)
    assert path.stat().st_mode & 0o077 == 0
    assert all(p.stat().st_mode & 0o077 == 0 for p in path.iterdir())
    manifest = {'data_root': str(tmp_path), 'revision': REVISION,
                'telegram': binding(tmp_path, REVISION, result['connection_digest'])}
    preflight(manifest)
    with pytest.raises(ValueError, match='new_private_directory'):
        provision(path, REVISION, 1234567, PUBLIC)
    assert (path / 'token').read_text() == PUBLIC


@pytest.mark.parametrize('change', ['revision', 'digest', 'owner', 'token', 'permissions', 'link'])
def test_changed_binding_or_credential_blocks_release_without_http(tmp_path, change):
    path = tmp_path / 'telegram'
    result = provision(path, REVISION, 1234567, PUBLIC)
    manifest = {'data_root': str(tmp_path), 'revision': REVISION,
                'telegram': binding(tmp_path, REVISION, result['connection_digest'])}
    if change == 'revision':
        manifest['revision'] = 'b' * 40
    elif change == 'digest':
        manifest['telegram']['connection_digest'] = 'b' * 64
    elif change == 'owner':
        manifest['telegram']['owner_id'] += 1
    elif change == 'token':
        (path / 'token').write_text('987654321:' + 'PUBLIC_SYNTHETIC_DIFFERENT_FIXTURE_12345')
    elif change == 'permissions':
        (path / 'token').chmod(0o644)
    else:
        (path / 'token').rename(path / 'other')
        (path / 'token').symlink_to(path / 'other')
    with pytest.raises((ValueError, Denied, OSError)):
        preflight(manifest)


@pytest.mark.parametrize('owner,revision,token', [(0, REVISION, PUBLIC), (123, 'main', PUBLIC), (123, REVISION, 'invalid')])
def test_invalid_input_creates_no_partial_directory(tmp_path, owner, revision, token):
    path = tmp_path / 'telegram'
    with pytest.raises(ValueError):
        provision(path, revision, owner, token)
    assert not path.exists()


def test_cli_unknown_arguments_do_not_echo_a_credential(monkeypatch, capsys):
    import sys
    from command_center.telegram_release import main

    monkeypatch.setattr(sys, 'argv', ['provision', '--unexpected', PUBLIC])
    with pytest.raises(SystemExit):
        main()
    output = capsys.readouterr()
    assert PUBLIC not in output.out + output.err


def test_cli_requires_an_interactive_terminal(tmp_path, monkeypatch, capsys):
    import sys
    from command_center.telegram_release import main

    monkeypatch.setattr(sys, 'argv', ['provision', '--directory', str(tmp_path / 'telegram'),
                                    '--revision', REVISION, '--owner-id', '1234567'])
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: False)
    with pytest.raises(SystemExit):
        main()
    assert not (tmp_path / 'telegram').exists()
    assert PUBLIC not in capsys.readouterr().err
