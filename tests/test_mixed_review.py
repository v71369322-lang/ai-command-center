from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from command_center.mixed_inbox import multiple_requests, request_markers
from command_center.mixed_review import (items_for, keyboard, allowed_markup, parse_callback,
                                        PROPOSED, ACCEPTED)
from command_center.models import Audit, Control, TelegramInbox, TelegramDelivery
from command_center.personal_inbox import records, collect_reminders
from command_center.project_inbox import history, inbox
from command_center.store import Denied
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_requests import captured_text
from command_center.telegram_voice_requests import transcription_contract
from command_center.telegram_voice_transcripts import propose, PROPOSED as VOICE_PROPOSED
from command_center.telegram_voice_transcripts import preview
from test_calendar_dialogue import setup as setup
from test_telegram_bridge import OWNER, message
from test_telegram_task_status import authority
from test_telegram_voice_requests import voice, transcript_callback

NOW = datetime(2026, 11, 26, 8, tzinfo=timezone.utc)
SCHEDULE = {'configured': True, 'timezone': 'Europe/Moscow'}
TEXT = 'Задача: проверить коробку по кондитерской. Отдельная идея по автосервису: список закупок. Напомни завтра в 11 позвонить.'


@pytest.mark.parametrize('corrected', [False, True])
def test_suspect_negation_is_warned_without_rewriting_owner_words(corrected):
    value = 'Встречу с Анной на переноси.'
    shown = preview(value, corrected=corrected)
    assert value in shown and 'Возможно, распознавание потеряло отрицание' in shown
    assert 'Встречу с Анной не переноси.' not in shown
    assert 'Возможно, распознавание потеряло отрицание' not in preview('Встречу не переноси.')


def test_literal_spans_cover_source_and_only_explicit_dates_are_resolved():
    items = items_for(TEXT, NOW, SCHEDULE, NOW)
    assert len(items) == 3
    assert ''.join(TEXT[x['start']:x['end']] for x in items) == TEXT
    assert [x['document']['category'] for x in items] == ['task', 'idea', 'reminder']
    assert [x['project_id'] for x in items] == ['vanilla-sugar', 'lnauto', None]
    assert [x['document']['due_at'] for x in items] == [None, None, '2026-11-27T11:00:00+03:00']


@pytest.mark.parametrize('field', ['reference', 'transcript'])
def test_real_public_long_probe_keeps_ambiguous_tail_without_save_button(field):
    case = json.loads((Path(__file__).parent / 'fixtures/mvp_long_voice_public.json').read_text(encoding='utf-8'))
    items = items_for(case[field], NOW, SCHEDULE, NOW)
    assert len(items) == 3
    assert [bool(x['document']) for x in items] == [True, True, False]
    assert case[field][items[-1]['start']:items[-1]['end']].startswith('Напомни')


@pytest.mark.parametrize('text', [
    'Отдельная идея: коробка.', 'Не задача: новая коробка.',
    'Не запиши идея: коробка. Задача: склад.',
    'Задача: прочитать «Идея: коробка».',
])
def test_overlapping_quoted_and_negated_labels_do_not_create_extra_items(text):
    assert not multiple_requests(text)


@pytest.mark.parametrize('text,flags', [
    ('Запиши встречу завтра в 15:00. Идея: коробка.', [False, True]),
    ('Важный контекст. Задача: склад. Идея: коробка.', [False, True, True]),
    ('Задача: склад идея: коробка', [True, True]),
    ('Задача: склад. Напомни в пятницу позвонить.', [True, False]),
    ('Задача: склад. Напомни завтра в 11 позвонить. Встречу на переноси.', [True, False]),
])
def test_uncertain_context_is_retained_without_action(text, flags):
    items = items_for(text, NOW, SCHEDULE, NOW)
    assert [bool(x['document']) for x in items] == flags
    assert ''.join(text[x['start']:x['end']] for x in items) == text


def test_bounds_and_quote_offsets():
    assert items_for(' '.join(['Задача: склад.'] * 9), NOW, SCHEDULE, NOW) == []
    value = 'Заметка: «Задача: пример». Идея: коробка.'
    assert [value[i:i+5] for i in request_markers(value)] == ['Замет', 'Идея:']
    assert items_for(TEXT, NOW, {'configured': False, 'timezone': 'Europe/Moscow'}, NOW)[-1]['document'] is None


@pytest.mark.parametrize('token', [None, '', 'mi:bad:1', 'mi:00000000-0000-0000-0000-000000000000:9'])
def test_callback_contract_rejects_invalid_values(token):
    with pytest.raises(Denied):
        parse_callback(token)


def test_exact_bounded_markup_rejects_extra_access_and_changed_labels():
    items = items_for(TEXT, NOW, SCHEDULE, NOW)
    markup = keyboard('00000000-0000-0000-0000-000000000000', items)
    assert allowed_markup(markup)
    markup['inline_keyboard'][0][0]['url'] = 'https://example.com'
    assert not allowed_markup(markup)
    del markup['inline_keyboard'][0][0]['url']
    markup['inline_keyboard'][0][0]['text'] = 'Execute shell'
    assert not allowed_markup(markup)


def review(store):
    with store.transaction() as tx:
        return tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == PROPOSED)
                         .order_by(Audit.sequence.desc()).limit(1)).event


def click(service, fake, proposal, item, uid, *, deliver=True):
    if deliver:
        while service.deliver_one():
            pass
    index = next((i for i, body in enumerate(fake.sent, 1) if any(
        button.get('callback_data') == f"mi:{proposal['proposal_id']}:{item}"
        for row in body.get('reply_markup', {}).get('inline_keyboard', []) for button in row)), 1)
    return {'update_id': uid, 'callback_query': {'id': 'mixed-fixture',
        'from': {'id': OWNER, 'is_bot': False}, 'data': f"mi:{proposal['proposal_id']}:{item}",
        'message': {'message_id': index, 'chat': {'id': OWNER, 'type': 'private'}}}}


def test_integration_three_records_need_real_clicks_and_survive_parent_archive(setup, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, provider = setup
    before = authority(store)
    source = service.receive(message(1, TEXT))
    proposal = review(store)
    with store.transaction() as tx:
        assert not records(service, tx)
        assert captured_text(tx, tx.get(TelegramInbox, source['inbox_id'])) == TEXT
    for item, uid in [(1, 2), (2, 3), (3, 4), (1, 5)]:
        event = click(service, fake, proposal, item, uid)
        service.receive(event)
        service.receive(event)
    with store.transaction() as tx:
        saved = records(service, tx)
        assert set(saved) == {service.profile + ':' + str(i) for i in (2, 3, 4)}
        assert [saved[service.profile + ':' + str(i)]['category'] for i in (2, 3, 4)] == ['task', 'idea', 'reminder']
        assignments, _ = history(tx)
        assert assignments[service.profile + ':2']['project_id'] == 'vanilla-sugar'
        assert assignments[service.profile + ':3']['project_id'] == 'lnauto'
        assert len(list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == ACCEPTED)))) == 3
        for i, item in enumerate(proposal['items'], 2):
            assert captured_text(tx, tx.get(TelegramInbox, service.profile + ':' + str(i))) == TEXT[item['start']:item['end']]
    service.receive(message(6, '/archive_request 1'))
    service.receive(message(7, 'Готово №2'))
    restarted = TelegramBridge(store, service.client, OWNER, calendar_writer=service.calendar_writer)
    with store.transaction() as tx:
        saved = records(restarted, tx)
        assert len(saved) == 3 and saved[service.profile + ':2']['status'] == 'done'
    assert len(inbox(store, 'owner')['requests']) >= 2
    due = datetime.fromisoformat(saved[service.profile + ':4']['due_at'])
    monkeypatch.setattr(store, 'now', lambda tx: due + timedelta(seconds=1))
    with store.transaction() as tx:
        assert len(collect_reminders(restarted, tx)) == 1
    with store.transaction() as tx:
        assert collect_reminders(restarted, tx) == []
    assert authority(store) == before and provider['calls'] == [] and provider['writes'] == 0


@pytest.mark.parametrize('change', ['expired', 'epoch', 'halted', 'recovery', 'revision', 'schedule'])
def test_integration_changed_context_cannot_use_old_card(setup, store, monkeypatch, change):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, _ = setup
    service.receive(message(1, TEXT))
    proposal = review(store)
    event = click(service, fake, proposal, 1, 2)
    if change == 'expired':
        now = datetime.fromisoformat(proposal['expires_at'])
        monkeypatch.setattr(store, 'now', lambda tx: now)
    elif change in {'epoch', 'halted', 'recovery'}:
        with store.transaction() as tx:
            c = tx.get(Control, 1)
            setattr(c, change, c.epoch + 1 if change == 'epoch' else True)
    elif change == 'revision':
        store.settings = replace(store.settings, source_revision='b' * 40)
    else:
        monkeypatch.setattr('command_center.mixed_review.schedule_pin', lambda tx: {'configured': True, 'timezone': 'UTC'})
    service.receive(event)
    with store.transaction() as tx:
        assert not records(service, tx)
        assert not tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == ACCEPTED))


@pytest.mark.parametrize('change', ['unobserved', 'wrong_message', 'wrong_owner', 'markup', 'source', 'archive'])
def test_integration_forged_or_stale_source_is_rejected_atomically(setup, store, monkeypatch, change):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, _ = setup
    service.receive(message(1, TEXT))
    proposal = review(store)
    event = click(service, fake, proposal, 1, 2, deliver=change != 'unobserved')
    if change == 'wrong_message':
        event['callback_query']['message']['message_id'] += 100
    elif change == 'wrong_owner':
        event['callback_query']['from']['id'] += 1
    elif change in {'markup', 'source', 'archive'}:
        with store.transaction() as tx:
            if change == 'markup':
                d = tx.get(TelegramDelivery, proposal['delivery_id'])
                d.body = dict(d.body, reply_markup={})
            else:
                row = tx.get(TelegramInbox, proposal['source_id'])
                if change == 'archive':
                    row.state = 'ARCHIVED'
                else:
                    row.intent = {'kind': 'capture', 'text': 'Changed source'}
    with pytest.raises(Denied):
        service.receive(event)
    with store.transaction() as tx:
        assert not records(service, tx)
        assert not tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == ACCEPTED))


def test_integration_concurrent_owner_clicks_make_one_record(setup, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, _ = setup
    service.receive(message(1, TEXT))
    proposal = review(store)
    events = [click(service, fake, proposal, 1, uid) for uid in (2, 3)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(service.receive, events))
    with store.transaction() as tx:
        assert len(records(service, tx)) == 1
        assert len(list(tx.scalars(select(Audit).where(Audit.event['kind'].as_string() == ACCEPTED)))) == 1


def test_integration_refresh_has_new_binding_and_no_duplicate_across_cards(setup, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, _ = setup
    service.receive(message(1, TEXT))
    original = review(store)
    service.receive(click(service, fake, original, 1, 2))
    now = datetime.fromisoformat(original['expires_at'])
    monkeypatch.setattr(store, 'now', lambda tx: now)
    service.receive(click(service, fake, original, 'r', 3))
    refreshed = review(store)
    assert refreshed['proposal_id'] != original['proposal_id']
    service.receive(click(service, fake, original, 2, 4))
    service.receive(click(service, fake, refreshed, 1, 5))
    with store.transaction() as tx:
        assert len(records(service, tx)) == 1
    service.receive(click(service, fake, refreshed, 2, 6))
    with store.transaction() as tx:
        assert len(records(service, tx)) == 2


def test_integration_unsupported_meeting_tail_cannot_be_saved_via_forged_slot(setup, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, provider = setup
    service.receive(message(1, 'Запиши встречу завтра в 15:00. Идея: коробка.'))
    proposal = review(store)
    service.receive(click(service, fake, proposal, 1, 2))
    with store.transaction() as tx:
        assert not records(service, tx)
    assert provider['writes'] == 0 and provider['calls'] == []


def test_integration_reviewed_voice_keeps_raw_and_saves_only_selected_literal_span(setup, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, provider = setup
    raw = service.receive(voice(duration=64))
    case = json.loads((Path(__file__).parent / 'fixtures/mvp_long_voice_public.json').read_text(encoding='utf-8'))
    value = case['transcript']
    offered = propose(service, raw['inbox_id'], {'audio_sha256': 'a' * 64, 'language': 'ru',
        'text': value, 'duration_seconds': 63.88}, transcription_contract({'kind': 'voice_request'}, 'a' * 64))
    service.receive(transcript_callback(service, fake, offered['proposal_id'], uid=2))
    proposal = review(store)
    service.receive(click(service, fake, proposal, 1, 3))
    with store.transaction() as tx:
        assert len(records(service, tx)) == 1
        assert captured_text(tx, tx.get(TelegramInbox, service.profile + ':3')) == value[:proposal['items'][0]['end']]
        assert tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == VOICE_PROPOSED)).event['text'] == value
    assert provider['calls'] == [] and provider['writes'] == 0
