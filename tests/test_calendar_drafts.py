from uuid import uuid4

import pytest

from command_center.calendar_drafts import create, decide, list_drafts, validate
from command_center.store import Denied, digest
from test_telegram_task_status import authority


def document(**changes):
    value = {'title': 'Созвон по первому проекту',
             'start': '2026-11-03T15:00:00+05:00',
             'end': '2026-11-03T15:30:00+05:00',
             'timezone': 'Asia/Almaty', 'note': 'Сверить готовность Telegram.',
             'telegram_reminder_minutes': 30}
    value.update(changes)
    return value


def test_local_draft_confirmation_is_idempotent_and_creates_no_task(store):
    before = authority(store)
    operation = str(uuid4())
    source = digest({'telegram_update': 'fixture'})
    first = create(store, 'owner', document(), operation, source)
    assert create(store, 'owner', document(), operation, source) == first
    assert first['state'] == 'DRAFT' and first['external_sync'] is False
    confirmed = decide(store, 'owner', first['id'], 1, str(uuid4()), True)
    assert confirmed['state'] == 'CONFIRMED_LOCAL'
    assert confirmed['external_sync'] is False
    assert authority(store) == before


def test_cancelled_or_confirmed_draft_cannot_be_decided_twice(store):
    draft = create(store, 'owner', document(), str(uuid4()), digest('source'))
    decide(store, 'owner', draft['id'], 1, str(uuid4()), False)
    with pytest.raises(Denied, match='stale_or_terminal'):
        decide(store, 'owner', draft['id'], 1, str(uuid4()), True)
    assert list_drafts(store, 'owner')[0]['state'] == 'CANCELLED'


@pytest.mark.parametrize('change,error', [
    ({'title': ''}, 'calendar_draft_invalid'),
    ({'start': '2026-11-03T15:00:00'}, 'calendar_draft_invalid'),
    ({'end': '2026-11-05T15:30:00+05:00'}, 'calendar_draft_invalid'),
    ({'timezone': 'Mars/Olympus'}, 'calendar_timezone_invalid'),
    ({'telegram_reminder_minutes': True}, 'calendar_draft_invalid'),
])
def test_invalid_documents_fail_before_write(store, change, error):
    before = authority(store)
    with pytest.raises(Denied, match=error):
        create(store, 'owner', document(**change), str(uuid4()), digest('source'))
    assert authority(store) == before


def test_idempotency_conflict_and_owner_scope_fail_closed(store):
    operation = str(uuid4())
    create(store, 'owner', document(), operation, digest('source'))
    with pytest.raises(Denied, match='idempotency_conflict'):
        create(store, 'owner', document(title='Другое'), operation, digest('source'))
    with pytest.raises(Denied, match='owner_required'):
        list_drafts(store, 'operator')


def test_validate_requires_exact_local_offset_for_named_timezone():
    with pytest.raises(Denied, match='calendar_draft_invalid'):
        validate(document(start='2026-11-03T15:00:00+00:00'))
