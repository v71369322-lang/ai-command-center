from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from command_center.models import Audit, TelegramInbox
from command_center.personal_inbox import records, collect_reminders, CREATED
from command_center.telegram_requests import captured_text
from command_center.telegram_voice_requests import transcription_contract
from command_center.telegram_voice_transcripts import propose
from test_calendar_dialogue import setup as setup
from test_telegram_bridge import message
from test_mixed_review import review, click
from test_telegram_task_status import authority
from test_telegram_voice_requests import voice, transcript_callback


def test_reviewed_spoken_minutes_are_not_delivered_at_the_whole_hour(setup, store, monkeypatch):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, provider = setup
    before = authority(store)
    raw = 'Задача: склад. Напомни послезавтра в 9 часов 15 минут позвонить Анне.'
    source = service.receive(message(1, raw))
    offered = review(store)
    assert offered['items'][1]['document']['due_at'].endswith('T09:15:00+03:00')
    service.receive(click(service, fake, offered, 2, 2))
    with store.transaction() as tx:
        saved = records(service, tx)
        assert len(saved) == 1
        record = saved[service.profile + ':2']
        assert record['title'] == 'позвонить Анне'
        assert captured_text(tx, tx.get(TelegramInbox, source['inbox_id'])) == raw
        assert '9 часов 15 минут' in captured_text(tx, tx.get(TelegramInbox, record['id']))
    due = datetime.fromisoformat(record['due_at'])
    monkeypatch.setattr(store, 'now', lambda tx: due.replace(minute=0))
    with store.transaction() as tx:
        assert collect_reminders(service, tx) == []
    monkeypatch.setattr(store, 'now', lambda tx: due + timedelta(seconds=1))
    with store.transaction() as tx:
        assert len(collect_reminders(service, tx)) == 1
    assert provider['calls'] == [] and authority(store) == before


@pytest.mark.parametrize('clock,expected', [('9 часов 15 минут', '09:15'), ('9 часов 75 минут', None)])
def test_owner_approved_voice_preserves_spoken_clock_or_refuses_it(setup, store, monkeypatch, clock, expected):
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    service, fake, provider = setup
    before = authority(store)
    raw = f'Напомни послезавтра в {clock} позвонить Анне.'
    source = service.receive(voice(duration=5))
    contract = transcription_contract({'kind': 'voice_request'}, 'a' * 64)
    offered = propose(service, source['inbox_id'], {'audio_sha256': 'a' * 64,
        'language': 'ru', 'text': raw, 'duration_seconds': 5.0}, contract)
    service.receive(transcript_callback(service, fake, offered['proposal_id'], uid=2))
    with store.transaction() as tx:
        saved = records(service, tx)
        if expected:
            record = saved[service.profile + ':2']
            assert record['due_at'].endswith('T'+expected+':00+03:00')
            assert record['title'] == 'позвонить Анне'
            assert captured_text(tx, tx.get(TelegramInbox, record['id'])) == raw
        else:
            assert not saved and not tx.scalar(select(Audit).where(Audit.event['kind'].as_string() == CREATED))
    assert provider['calls'] == [] and authority(store) == before
