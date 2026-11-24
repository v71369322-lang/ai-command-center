import httpx
import pytest
from datetime import datetime
from sqlalchemy import text, select

from command_center.google_calendar_access import CalendarAccess, PersonalCalendarHTTP
from command_center.models import Audit
from command_center.store import Denied, digest
from command_center.telegram_agenda import parse, render
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from test_telegram_bridge import BotHTTP, OWNER, message
from test_telegram_task_status import authority, response


@pytest.fixture
def agenda(store):
    calls = []
    mode = {'value': 'ok'}
    def handler(request):
        calls.append(request)
        # Acquiring the admission lock proves Google HTTP is outside its DB tx.
        with store.engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '500ms'"))
            connection.execute(text('SELECT id FROM control WHERE id=1 FOR UPDATE'))
        if mode['value'] == 'timeout':
            raise httpx.ReadTimeout('private provider detail', request=request)
        if mode['value'] == 'stop':
            store.halt('owner')
        return httpx.Response(200, json={'items': [{'id': 'one', 'status': 'confirmed',
            'summary': 'Планёрка', 'start': {'dateTime': '2026-11-25T09:00:00+03:00'}}]})
    profile = CalendarAccess(enabled=True, source_revision=store.settings.source_revision,
                              owner_id=OWNER, calendar_id='a' * 32 + '@group.calendar.google.com')
    calendar = PersonalCalendarHTTP(profile, digest(profile.model_dump()), lambda: 'fixture-access-token-123',
                                    transport=httpx.MockTransport(handler))
    bot = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    bridge = TelegramBridge(store, bot, OWNER, calendar=calendar)
    yield bridge, calls, mode
    calendar.close()
    bot.close()


@pytest.mark.parametrize('phrase,period', [('Что у меня завтра?', 'tomorrow'),
    ('расписание на сегодня', 'today'), ('/agenda неделя', 'week')])
def test_natural_agenda_aliases(phrase, period):
    assert parse(phrase) == {'kind': 'calendar_agenda', 'period': period}
    assert parse('Идея нового проекта') is None
    with pytest.raises(Denied):
        parse('/agenda 100000')


def test_owner_agenda_uses_get_and_replays_snapshot_without_grants(agenda, store, monkeypatch):
    service, calls, _ = agenda
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    before = authority(store)
    update = message(1, 'что у меня завтра')
    first = response(service, update)
    assert 'Планёрка' in first and 'Основной календарь Google' in first
    assert response(service, update) == first
    assert len(calls) == 1 and calls[0].method == 'GET'
    assert calls[0].url.path.endswith('/primary/events')
    assert authority(store) == before
    with store.transaction() as session:
        event = session.scalar(select(Audit).where(Audit.event['kind'].as_string() ==
                                                   'telegram_google_agenda_read')).event
        assert event['events_changed'] is False and event['model_called'] is False
        assert 'Планёрка' not in str(event)


def test_other_owner_cannot_read_schedule(agenda):
    service, calls, _ = agenda
    with pytest.raises(Denied):
        service.receive(message(1, '/agenda', owner=999))
    assert calls == []


def test_stop_prevents_google_contact(agenda, store):
    service, calls, _ = agenda
    store.halt('owner')
    assert 'на паузе' in response(service, message(1, '/agenda'))
    assert calls == []


def test_stop_during_read_discards_calendar_contents(agenda):
    service, calls, mode = agenda
    mode['value'] = 'stop'
    reply = response(service, message(1, '/agenda'))
    assert 'Режим работы изменился' in reply and 'Планёрка' not in reply
    assert len(calls) == 1


def test_provider_failure_is_a_safe_reply_without_retry(agenda):
    service, calls, mode = agenda
    mode['value'] = 'timeout'
    result = response(service, message(1, '/agenda'))
    assert 'Не удалось' in result and 'private provider detail' not in result
    assert response(service, message(1, '/agenda')) == result
    assert len(calls) == 1


def test_unconfigured_is_explicit_and_does_not_capture_a_task(agenda, store):
    service, calls, _ = agenda
    service.calendar = None
    before = authority(store)
    assert 'ещё не подключён' in response(service, message(1, 'расписание на сегодня'))
    assert calls == [] and authority(store) == before


def test_wrong_owner_or_revision_connection_rejected_before_use(agenda, store):
    service, calls, _ = agenda
    with pytest.raises(Denied):
        TelegramBridge(store, service.client, OWNER + 1, calendar=service.calendar)
    assert calls == []


def test_week_query_is_bounded_to_seven_days(agenda):
    service, calls, _ = agenda
    response(service, message(1, 'расписание на неделю'))
    params = calls[0].url.params
    first, last = datetime.fromisoformat(params['timeMin']), datetime.fromisoformat(params['timeMax'])
    assert (last - first).days == 7
    assert params['timeZone'] == 'Europe/Moscow'


def test_agenda_render_is_bounded_plain_text_and_honest_about_partial_data():
    value = {'timezone': 'Europe/Moscow', 'truncated': True, 'events': [
        {'summary': 'x' * 1000, 'start': {'date': '2026-11-25'}}] * 20}
    result = render(value)
    assert len(result) < 3000 and 'весь день' in result and 'часть событий' in result
    assert 'не учитываются' in result
    value['events'] = [{'summary': 'unknown', 'start': {}}]
    assert 'неполные записи' in render(value)
