from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from command_center.personal_inbox import parse, project_hint, due_at, records, collect_reminders, CREATED, CHANGED
from command_center.models import Audit, Control, TelegramDelivery
from command_center.store import Denied
from command_center.telegram_bridge import TelegramBridge, MockTelegramHTTP
from test_telegram_bridge import BotHTTP, OWNER, message
from test_telegram_task_status import response, authority
from test_telegram_service import configured as configured


@pytest.mark.parametrize('text,category,title', [
    ('Купить упаковку для кондитерской', 'task', 'Купить упаковку для кондитерской'),
    ('Идея: новая подарочная коробка', 'idea', 'новая подарочная коробка'),
    ('Запиши мне идею: новый ассортимент', 'idea', 'новый ассортимент'),
    ('Сохрани заметку: обсудили закупки', 'note', 'обсудили закупки'),
    ('Напомни завтра в 11 позвонить поставщику', 'reminder', 'позвонить поставщику'),
    ('Напомни мне 2026-12-01 в 09:15 забрать заказ', 'reminder', 'забрать заказ'),
])
def test_natural_personal_phrases(text, category, title):
    result = parse(text)
    assert result['category'] == category and result['title'] == title


@pytest.mark.parametrize('text', ['Мы обсуждали купить упаковку', 'Не покупать упаковку',
    'Выполни shell-команду', 'переведи деньги', 'Привет', 'Идея:'])
def test_unknown_or_negated_text_is_not_invented_as_task(text):
    assert parse(text) is None


@pytest.mark.parametrize('text', ['Напомни завтра позвонить', 'Напомни в 11 позвонить',
    'Напомни завтра в 25:00 позвонить', 'Напомни завтра в 11:99 позвонить',
    'Напомни завтра в 11 или 12 позвонить', 'Напомни завтра в 11:00 и в 12:00 позвонить',
    'Напомни завтра в 11 если будет встреча'])
def test_ambiguous_reminder_requires_explicit_date_time(text):
    assert parse(text) == {'action': 'invalid_reminder'}


def test_relative_date_pinned_at_original_intake_and_no_past_invention():
    received = datetime(2026, 11, 26, 20, 59, tzinfo=timezone.utc)
    now = datetime(2026, 11, 26, 22, 0, tzinfo=timezone.utc)
    intent = parse('Напомни завтра в 11 позвонить')
    assert due_at(intent, received, 'Europe/Moscow', now) == '2026-11-27T11:00:00+03:00'
    with pytest.raises(ValueError):
        due_at(intent, received, 'Europe/Moscow', now + timedelta(days=2))


def test_only_one_explicit_project_hint_is_assigned():
    assert project_hint('Купить упаковку для кондитерской') == 'vanilla-sugar'
    assert project_hint('Проверить автосервис и кондитерскую') is None
    assert project_hint('Позвонить поставщику') is None


@pytest.fixture
def personal(store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    bridge = TelegramBridge(store, client, OWNER)
    yield bridge, fake
    client.close()


def snapshot(bridge):
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        return records(bridge, session)


def schedule(store):
    from command_center.attention_schedule import configure
    configure(store, 'owner', {'enabled': False, 'timezone': 'Europe/Moscow',
        'report_times': ['09:00'], 'quiet_start': '23:00', 'quiet_end': '08:00'}, 0, str(uuid4()))


def test_tasks_ideas_assignment_completion_reclassification_and_replay(personal, store):
    from command_center.project_inbox import inbox
    bridge, _ = personal
    before = authority(store)
    original = message(1, 'Купить упаковку для кондитерской')
    assert 'Задача сохранена' in response(bridge, original)
    bridge.receive(original)
    assert len(snapshot(bridge)) == 1
    item = next(iter(snapshot(bridge).values()))
    assert item['due_at'] is None
    assert inbox(store, 'owner')['requests'][0]['project_id'] == 'vanilla-sugar'
    assert 'Ваниль и Сахар' in response(bridge, message(2, 'Мои задачи'))
    assert 'Идея сохранена' in response(bridge, message(3, 'Идея: новая подарочная коробка'))
    assert 'Банк идей' in response(bridge, message(4, 'Мои идеи'))
    assert 'выполнена' in response(bridge, message(5, 'Готово №1'))
    assert 'Купить упаковку' not in response(bridge, message(6, 'Мои задачи'))
    assert 'Ничего не изменено' in response(bridge, message(7, 'Готово №1'))
    response(bridge, message(8, 'Это задача №3'))
    assert snapshot(bridge)[bridge.profile + ':3']['category'] == 'task'
    response(bridge, message(9, 'Раздел №1: автосервис'))
    assert next(r for r in inbox(store, 'owner')['requests'] if r['id'].endswith(':1'))['project_id'] == 'lnauto'
    assert authority(store) == before


def test_reminder_uses_durable_delivery_once_with_stop_guard_and_restart(personal, store, monkeypatch):
    bridge, fake = personal
    schedule(store)
    with store.transaction() as session:
        now = store.now(session)
    title_time = (now + timedelta(minutes=5)).astimezone(timezone(timedelta(hours=3)))
    value = f'Напомни {title_time:%Y-%m-%d} в {title_time:%H:%M} позвонить поставщику'
    assert 'В Google событие не создавалось' in response(bridge, message(1, value))
    with store.transaction() as session:
        assert collect_reminders(bridge, session) == []
    monkeypatch.setattr(store, 'now', lambda session: now + timedelta(minutes=6))
    with store.transaction() as session:
        control = session.get(Control, 1)
        control.halted = True
        assert collect_reminders(bridge, session) == []
        control.halted = False
    bridge.collect_results()
    replacement = TelegramBridge(store, bridge.client, OWNER)
    replacement.collect_results()
    with store.transaction() as session:
        rows = list(session.scalars(select(Audit).where(
            Audit.event['kind'].as_string() == 'personal_inbox_reminder_queued')))
        assert len(rows) == 1
        delivery = session.get(TelegramDelivery, rows[0].event['delivery_id'])
        assert delivery.state == 'NEW' and delivery.body['chat_id'] == OWNER
        assert 'позвонить поставщику' in delivery.body['text']
    while replacement.deliver_one():
        pass
    assert sum('Напоминание №' in item['text'] for item in fake.sent) == 1


def test_completed_reminder_does_not_fire(personal, store, monkeypatch):
    bridge, _ = personal
    schedule(store)
    with store.transaction() as session:
        now = store.now(session)
    at = (now + timedelta(minutes=5)).astimezone(timezone(timedelta(hours=3)))
    response(bridge, message(1, f'Напомни {at:%Y-%m-%d} в {at:%H:%M} позвонить'))
    response(bridge, message(2, 'Готово №1'))
    monkeypatch.setattr(store, 'now', lambda session: now + timedelta(minutes=6))
    with store.transaction() as session:
        assert collect_reminders(bridge, session) == []


@pytest.mark.parametrize('stop', [False, True])
def test_queued_reminder_is_suppressed_if_completed_or_stopped_before_http(personal, store, monkeypatch, stop):
    bridge, fake = personal
    schedule(store)
    with store.transaction() as session:
        now = store.now(session)
    at = (now + timedelta(minutes=5)).astimezone(timezone(timedelta(hours=3)))
    response(bridge, message(1, f'Напомни {at:%Y-%m-%d} в {at:%H:%M} позвонить'))
    while bridge.deliver_one():
        pass
    monkeypatch.setattr(store, 'now', lambda session: now + timedelta(minutes=6))
    with store.transaction() as session:
        queued = collect_reminders(bridge, session)
        assert len(queued) == 1
    if stop:
        with store.transaction() as session:
            session.get(Control, 1).halted = True
    else:
        response(bridge, message(2, 'Готово №1'))
    while bridge.deliver_one():
        pass
    assert not any('Напоминание №' in item['text'] for item in fake.sent)
    with store.transaction() as session:
        assert session.get(TelegramDelivery, queued[0]).state == 'CANCELLED'


def test_another_profile_cannot_complete_or_read_personal_record(personal, store):
    bridge, _ = personal
    response(bridge, message(1, 'Купить упаковку'))
    other = TelegramBridge(store, bridge.client, OWNER + 1)
    with store.transaction() as session:
        assert records(other, session) == {}
    value = message(2, 'Готово №1')
    value['message']['from']['id'] = OWNER + 1
    value['message']['chat']['id'] = OWNER + 1
    other.receive(value)
    assert snapshot(bridge)[bridge.profile + ':1']['status'] == 'active'


def test_reminder_errors_no_fake_success_and_foreign_reference(personal, store):
    bridge, _ = personal
    assert 'нужны точная дата' in response(bridge, message(1, 'Напомни завтра позвонить'))
    assert not snapshot(bridge)
    assert 'часовой пояс' in response(bridge, message(2, 'Напомни завтра в 11 позвонить'))
    assert not snapshot(bridge)
    assert 'не найдена' in response(bridge, message(3, 'Готово №999'))


def test_new_features_do_not_interpret_developer_inbox_by_default(store):
    fake = BotHTTP()
    client = MockTelegramHTTP(httpx.MockTransport(fake))
    try:
        bridge = TelegramBridge(store, client, OWNER)
        response(bridge, message(1, 'Купить упаковку'))
        assert not snapshot(bridge)
    finally:
        client.close()


def test_today_keeps_local_tasks_when_google_not_connected(personal):
    bridge, _ = personal
    response(bridge, message(1, 'Купить упаковку'))
    text = response(bridge, message(2, 'Что у меня сегодня?'))
    assert 'Google Calendar ещё не подключён' in text
    assert 'Личные задачи' in text and 'Купить упаковку' in text and 'без срока' in text


def test_corrupted_source_fails_closed(personal, store):
    bridge, _ = personal
    response(bridge, message(1, 'Купить упаковку'))
    from command_center.models import TelegramInbox
    with store.transaction() as session:
        session.get(TelegramInbox, bridge.profile + ':1').fingerprint = 'a' * 64
    with pytest.raises(Denied, match='source_changed'):
        snapshot(bridge)


def test_voice_waits_for_observed_confirmation_then_creates_one_personal_item(personal, store):
    from command_center.telegram_voice_transcripts import propose
    from command_center.telegram_voice_requests import transcription_contract
    from test_telegram_voice_requests import voice, transcript_callback
    bridge, fake = personal
    result = bridge.receive(voice())
    contract = transcription_contract({'kind': 'voice_request'}, 'a' * 64)
    proposal = propose(bridge, result['inbox_id'], {'audio_sha256': 'a' * 64, 'language': 'ru',
        'text': 'Идея: новая подарочная коробка', 'duration_seconds': 20.5}, contract)
    assert not snapshot(bridge)
    callback = transcript_callback(bridge, fake, proposal['proposal_id'])
    bridge.receive(callback)
    bridge.receive(callback)
    assert len(snapshot(bridge)) == 1
    assert next(iter(snapshot(bridge).values()))['category'] == 'idea'
    with store.transaction() as session:
        assert session.scalar(select(Audit).where(Audit.event['kind'].as_string() == CREATED))
        assert not session.scalar(select(Audit).where(Audit.event['kind'].as_string() == CHANGED))


def test_configured_transport_polling_saves_task_and_lists_it_without_external_ai(configured, store, monkeypatch):
    from test_telegram_service import FakeBot, client_for, update
    from command_center.telegram_service import TelegramService
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    fake = FakeBot()
    fake.updates = [update(1, 'Купить упаковку для кондитерской'), update(2, 'Мои задачи')]
    client = client_for(configured, fake)
    before = authority(store)
    try:
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        assert any('Задача сохранена' in b['text'] for b in fake.sent)
        assert any('Личные задачи' in b['text'] and 'Купить упаковку' in b['text'] for b in fake.sent)
        assert authority(store) == before
    finally:
        client.close()
