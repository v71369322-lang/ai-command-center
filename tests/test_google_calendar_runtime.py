import sys

import pytest

from command_center.google_calendar_access import CalendarAccess
from command_center.google_calendar_runtime import CalendarRuntimeConfig, calendar_runtime
from command_center.store import Denied, digest


def config(directory):
    return CalendarRuntimeConfig(profile=CalendarAccess(enabled=True, source_revision='a' * 40,
        owner_id=123, calendar_id='a' * 32 + '@group.calendar.google.com'),
        client_id='a' * 24 + '.apps.googleusercontent.com', custody_directory=str(directory))


@pytest.mark.parametrize('wrong', ['approval', 'owner', 'revision'])
def test_runtime_scope_checked_before_any_custody_access(monkeypatch, tmp_path, wrong):
    value = config(tmp_path)
    monkeypatch.setattr('command_center.google_calendar_runtime.private_read', lambda *args: value.model_dump_json())
    monkeypatch.setattr('command_center.google_calendar_runtime.CalendarCredentialFiles',
                        lambda *args: pytest.fail('must not read credentials'))
    with pytest.raises(Denied):
        with calendar_runtime('unused', 'wrong' if wrong == 'approval' else digest(value.model_dump()),
                              'b' * 40 if wrong == 'revision' else 'a' * 40,
                              124 if wrong == 'owner' else 123):
            pytest.fail('must not activate')


@pytest.mark.skipif(sys.platform == 'win32', reason='Linux custody')
def test_runtime_loads_protected_files_without_network_and_closes_lock(tmp_path):
    tmp_path.chmod(0o700)
    value = config(tmp_path)
    for name, body in [('calendar.key', b'k' * 32),
        ('runtime.json', value.model_dump_json().encode()),
        ('oauth-client.json', ('{"client_id":"' + value.client_id + '","client_secret":null}').encode())]:
        path = tmp_path / name
        path.write_bytes(body)
        path.chmod(0o600)
    # No archive is needed until an explicit agenda read. Context opening does
    # not contact Google, refresh credentials, or verify/create an event/calendar.
    with calendar_runtime(tmp_path / 'runtime.json', digest(value.model_dump()), 'a' * 40, 123) as client:
        assert client.profile.owner_id == 123
        assert not (tmp_path / 'calendar.enc').exists()
    with calendar_runtime(tmp_path / 'runtime.json', digest(value.model_dump()), 'a' * 40, 123):
        pass
