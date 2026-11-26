"""Mixed-source preservation and a reviewed, deterministic MVP journey."""
from datetime import timedelta, timezone
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from command_center.calendar_drafts import list_drafts
from command_center.mixed_inbox import multiple_requests
from command_center.models import Audit, TelegramInbox
from command_center.personal_inbox import records, collect_reminders, CREATED
from command_center.project_inbox import history
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_requests import captured_text
from command_center.telegram_voice_requests import transcription_contract
from command_center.telegram_voice_transcripts import propose, PROPOSED
from test_calendar_dialogue import setup as setup
from test_telegram_bridge import OWNER, message
from test_telegram_calendar import callback
from test_telegram_task_status import authority
from test_telegram_voice_corrections import reply, corrected
from test_telegram_voice_requests import voice, transcript_callback


@pytest.mark.parametrize('text', [
    'Запиши задачу проверить упаковку. Отдельная идея по автосервису: список. Напомни завтра в 11 позвонить.',
    'запиши задачу проверить упаковку отдельная идея по автосервису список напомни завтра в 11 позвонить',
    'Задача: проверить упаковку. Идея: список закупок.',
    'Задача: проверить упаковку идея: список закупок',
    'Запиши задачу проверить упаковку и запиши задачу проверить склад.',
    'Запиши встречу завтра в 15:00 на 30 минут. Идея: новая коробка.',
    'Напомни завтра в 11 позвонить. Добавь встречу завтра в 15:00.',
])
def test_explicit_mixed_intents_are_held_even_without_asr_punctuation(text):
    assert multiple_requests(text)


@pytest.mark.parametrize('text', [
    'Запиши задачу проверить упаковку тортов без срока.',
    'Напомни завтра в 11 позвонить поставщику.',
    'Идея: коробка с двумя отделениями.',
    'Сохрани заметку: фраза «напомни мне» есть в инструкции.',
    'Запиши задачу проверить склад. Не добавь встречу.',
    'Заметка: он сказал "запиши задачу проверить склад".',
])
def test_single_or_quoted_or_negated_creation_is_not_a_batch(text):
    assert not multiple_requests(text)


@pytest.mark.parametrize('field', ['reference', 'transcript'])
def test_actual_public_minute_fixture_is_held(field):
    case = json.loads((Path(__file__).parent / 'fixtures/mvp_long_voice_public.json').read_text(encoding='utf-8'))
    assert multiple_requests(case[field])


def test_text_mixed_request_stays_intact_without_personal_or_calendar_effects(setup, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, _, provider = setup
    value = 'Запиши встречу завтра в 15:00 на 30 минут. Идея: новая коробка.'
    before = authority(store)
    result = service.receive(message(1, value))
    assert service.receive(message(1, value)) == result
    assert result['state'] == 'NEEDS_PLANNING' and result['task_id'] is None
    assert not list_drafts(store, 'owner') and provider['calls'] == []
    with store.transaction() as tx:
        row = tx.get(TelegramInbox, result['inbox_id'])
        assert captured_text(tx, row) == value
        assert not records(service, tx)
        held = list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == 'personal_mixed_request_held')))
        assert len(held) == 1
    assert authority(store) == before


def test_reviewed_voice_then_individual_task_idea_reminder_and_calendar_journey(setup, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, provider = setup
    before = authority(store)
    raw = 'Запиши задачу проверить упаковку. Отдельная идея: список закупок. Встречу на переноси.'
    edited = raw.replace('на переноси', 'не переноси')
    original = service.receive(voice(duration=64))
    contract = transcription_contract({'kind': 'voice_request'}, 'a' * 64)
    proposal = propose(service, original['inbox_id'], {'audio_sha256': 'a' * 64, 'language': 'ru',
        'text': raw, 'duration_seconds': 63.88}, contract)
    service.receive(reply(service, fake, proposal, value=edited, uid=2))
    edit = corrected(store)
    service.receive(transcript_callback(service, fake, proposal['proposal_id'], uid=3))
    with store.transaction() as tx:
        assert not records(service, tx)
    accepted = transcript_callback(service, fake, edit['proposal_id'], uid=4)
    result = service.receive(accepted)
    service.receive(accepted)
    with store.transaction() as tx:
        assert captured_text(tx, tx.get(TelegramInbox, result['inbox_id'])) == edited
        assert tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == PROPOSED)).event['text'] == raw
        assert not records(service, tx)
    assert provider['calls'] == [] and not list_drafts(store, 'owner')
    with store.transaction() as tx:
        now = store.now(tx)
    due = (now + timedelta(minutes=5)).astimezone(timezone(timedelta(hours=3)))
    service.receive(message(5, 'Задача: проверить упаковку по кондитерской'))
    service.receive(message(6, 'Идея: новый комплект по автосервису'))
    service.receive(message(7, f'Напомни {due:%Y-%m-%d} в {due:%H:%M} тест сценария'))
    service.receive(message(8, 'Готово №5'))
    with store.transaction() as tx:
        items = records(service, tx)
        assert len(items) == 3
        task, idea, reminder = [items[service.profile + ':' + str(n)] for n in (5, 6, 7)]
        assert task['status'] == 'done' and task['due_at'] is None
        assert idea['category'] == 'idea' and idea['due_at'] is None
        assert reminder['category'] == 'reminder' and reminder['due_at'] == due.strftime('%Y-%m-%dT%H:%M:00+03:00')
        assignments, _ = history(tx)
        assert assignments[service.profile + ':5']['project_id'] == 'vanilla-sugar'
        assert assignments[service.profile + ':6']['project_id'] == 'lnauto'
        assert len(list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == CREATED)))) == 3
    service.receive(message(9, 'Запиши мне завтра встречу.'))
    assert not list_drafts(store, 'owner') and provider['calls'] == []
    service.receive(message(10, 'В 15:00 на 30 минут'))
    assert len(list_drafts(store, 'owner')) == 1 and provider['calls'] == []
    service.receive(callback(service, fake, uid=11))
    service.receive(callback(service, fake, uid=12))
    assert provider['writes'] == 1 and provider['calls'] == ['create']
    monkeypatch.setattr(store, 'now', lambda session: now + timedelta(minutes=6))
    with store.transaction() as tx:
        assert len(collect_reminders(service, tx)) == 1
    restarted = TelegramBridge(store, service.client, OWNER, calendar_writer=service.calendar_writer)
    with store.transaction() as tx:
        assert collect_reminders(restarted, tx) == []
    while restarted.deliver_one():
        pass
    assert sum('Напоминание №7:' in body.get('text', '') for body in fake.sent) == 1
    assert authority(store) == before
