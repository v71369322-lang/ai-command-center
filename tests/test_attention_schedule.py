from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from command_center.attention_schedule import (activity, collect, configure, current,
                                                delivery_health, telegram_reply)
from command_center.models import Audit, Control, TelegramDelivery
from command_center.store import Denied
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from test_telegram_bridge import BotHTTP, OWNER


def document(**changes):
    return {'enabled': True, 'timezone': 'UTC', 'report_times': ['08:00', '14:00', '21:00'],
            'quiet_start': '23:00', 'quiet_end': '08:00'} | changes


def test_schedule_is_versioned_idempotent_and_owner_only(store):
    operation = str(uuid4())
    first = configure(store, 'owner', document(), 0, operation)
    assert first['version'] == 1 and first['enabled'] is True
    assert configure(store, 'owner', document(), 0, operation) == first
    with pytest.raises(Denied, match='idempotency_conflict'):
        configure(store, 'owner', document(enabled=False), 0, operation)
    with pytest.raises(Denied, match='stale_version'):
        configure(store, 'owner', document(enabled=False), 0, str(uuid4()))
    with pytest.raises(Denied, match='owner_required'):
        configure(store, 'operator', document(), 1, str(uuid4()))


@pytest.mark.parametrize('change', [
    {'timezone': 'Not/AZone'}, {'report_times': []}, {'report_times': ['08:00', '08:00']},
    {'report_times': ['25:00']}, {'quiet_start': '08:00', 'quiet_end': '08:00'},
])
def test_invalid_schedule_never_writes_audit(store, change):
    with pytest.raises(Denied):
        configure(store, 'owner', document(**change), 0, str(uuid4()))
    with store.transaction() as session:
        assert current(session) == {'version': 0, 'configured': False, 'enabled': False}


def test_due_report_is_queued_once_and_contains_only_bounded_summary(store, monkeypatch):
    configure(store, 'owner', document(), 0, str(uuid4()))
    monkeypatch.setattr(store, 'now', lambda session: datetime(2026, 10, 31, 14, 5, tzinfo=timezone.utc))
    client = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    bridge = TelegramBridge(store, client, OWNER)
    try:
        with store.transaction() as session:
            first = collect(bridge, session)
        with store.transaction() as session:
            assert collect(bridge, session) == first
            rows = session.scalars(select(TelegramDelivery)).all()
            assert len(rows) == 1 and rows[0].state == 'NEW'
            assert rows[0].body['chat_id'] == OWNER
            assert 'Просмотр ничего не запускает' in rows[0].body['text']
            assert len(rows[0].body['text']) < 4096
    finally:
        client.close()


def test_quiet_hours_and_disabled_schedule_do_not_queue(store, monkeypatch):
    configure(store, 'owner', document(report_times=['23:00']), 0, str(uuid4()))
    monkeypatch.setattr(store, 'now', lambda session: datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc))
    client = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    bridge = TelegramBridge(store, client, OWNER)
    try:
        with store.transaction() as session:
            assert collect(bridge, session) is None
            assert session.scalar(select(TelegramDelivery)) is None
        configure(store, 'owner', document(enabled=False, report_times=['14:00']), 1, str(uuid4()))
        with store.transaction() as session:
            assert collect(bridge, session) is None
    finally:
        client.close()


def test_unchanged_later_slot_is_audited_once_without_duplicate_delivery(store, monkeypatch):
    configure(store, 'owner', document(report_times=['08:00', '14:00']), 0, str(uuid4()))
    clock = [datetime(2026, 10, 31, 8, 5, tzinfo=timezone.utc)]
    monkeypatch.setattr(store, 'now', lambda session: clock[0])
    client = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    bridge = TelegramBridge(store, client, OWNER)
    try:
        with store.transaction() as session:
            assert collect(bridge, session) is not None
        clock[0] = datetime(2026, 10, 31, 14, 5, tzinfo=timezone.utc)
        with store.transaction() as session:
            assert collect(bridge, session) is None
        with store.transaction() as session:
            assert collect(bridge, session) is None
            assert len(session.scalars(select(TelegramDelivery)).all()) == 1
            events = [row.event for row in session.scalars(select(Audit)).all()
                      if row.event['kind'] == 'owner_attention_report_suppressed']
            assert len(events) == 1 and events[0]['reason'] == 'unchanged'
            recent = activity(session)
            assert [item['outcome'] for item in recent] == ['suppressed', 'queued']
            assert recent[0]['delivery_state'] is None and recent[1]['delivery_state'] == 'NEW'
    finally:
        client.close()


def test_activity_reports_uncertain_delivery_without_message_body(store, monkeypatch):
    configure(store, 'owner', document(report_times=['14:00']), 0, str(uuid4()))
    monkeypatch.setattr(store, 'now', lambda session: datetime(
        2026, 10, 31, 14, 5, tzinfo=timezone.utc))
    client = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    bridge = TelegramBridge(store, client, OWNER)
    try:
        with store.transaction() as session:
            delivery_id = collect(bridge, session)
            session.get(TelegramDelivery, delivery_id).state = 'UNCERTAIN'
        with store.transaction() as session:
            value = activity(session, 1)
            assert value == [{'sequence': value[0]['sequence'], 'slot': '2026-10-31T14:00',
                              'outcome': 'queued', 'delivery_state': 'UNCERTAIN',
                              'schedule_version': 1, 'critical_quiet_bypass': False}]
            assert 'результат доставки неизвестен' in telegram_reply(session)
            assert 'text' not in value[0] and 'profile' not in value[0] and 'delivery_id' not in value[0]
            assert delivery_health(session) == {
                'state': 'uncertain', 'action_required': True,
                'last_slot': value[0]['slot']}
        with pytest.raises(Denied, match='activity_limit_invalid'):
            with store.transaction() as session:
                activity(session, 21)
    finally:
        client.close()


def test_critical_due_report_can_bypass_quiet_hours_with_audit_receipt(store, monkeypatch):
    configure(store, 'owner', document(report_times=['23:00']), 0, str(uuid4()))
    with store.transaction() as session:
        session.get(Control, 1).recovery = True
    monkeypatch.setattr(store, 'now', lambda session: datetime(
        2026, 10, 31, 23, 30, tzinfo=timezone.utc))
    client = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    bridge = TelegramBridge(store, client, OWNER)
    try:
        with store.transaction() as session:
            delivery = collect(bridge, session)
            row = session.get(TelegramDelivery, delivery)
            assert row.body['text'].startswith('Критическое изменение AI Commander')
            notice = next(row.event for row in session.scalars(select(Audit)).all()
                          if row.event['kind'] == 'owner_attention_critical_queued')
            assert notice['critical_quiet_bypass'] is True
    finally:
        client.close()


def test_new_critical_transition_notifies_once_and_recurrence_notifies_again(store, monkeypatch):
    configure(store, 'owner', document(report_times=['21:00']), 0, str(uuid4()))
    monkeypatch.setattr(store, 'now', lambda session: datetime(
        2026, 10, 31, 10, 0, tzinfo=timezone.utc))
    client = MockTelegramHTTP(httpx.MockTransport(BotHTTP()))
    bridge = TelegramBridge(store, client, OWNER)
    try:
        # Establish a normal observation without sending anything.
        with store.transaction() as session:
            assert collect(bridge, session) is None
            session.get(Control, 1).recovery = True
        with store.transaction() as session:
            first = collect(bridge, session)
            assert first is not None
            assert collect(bridge, session) is None
            assert len(session.scalars(select(TelegramDelivery)).all()) == 1
        # Observing recovery completion rearms a later recurrence of the same state.
        with store.transaction() as session:
            session.get(Control, 1).recovery = False
        with store.transaction() as session:
            assert collect(bridge, session) is None
            session.get(Control, 1).recovery = True
        with store.transaction() as session:
            second = collect(bridge, session)
            assert second != first
            recent = activity(session)
            assert [item['outcome'] for item in recent] == ['critical', 'critical']
            assert all(item['critical_quiet_bypass'] is False for item in recent)
            observations = [row for row in session.scalars(select(Audit)).all()
                            if row.event['kind'] == 'owner_attention_observed']
            assert len(observations) == 4
    finally:
        client.close()


def test_owner_can_configure_schedule_through_api(client, headers):
    empty = client.get('/api/attention/schedule', headers=headers['owner'])
    assert empty.status_code == 200 and empty.json() == {
        'version': 0, 'configured': False, 'enabled': False}
    payload = document() | {'expected_version': 0, 'operation_id': str(uuid4())}
    saved = client.post('/api/attention/schedule', headers=headers['owner'], json=payload)
    assert saved.status_code == 200 and saved.json()['version'] == 1
    assert client.get('/api/attention', headers=headers['owner']).json()['reminders_connected'] is True
    assert client.get('/api/attention/schedule', headers=headers['operator']).status_code == 409
    assert client.post('/api/attention/schedule', headers=headers['agent'], json=payload).status_code == 409
