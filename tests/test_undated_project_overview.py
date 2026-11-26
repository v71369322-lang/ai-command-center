from datetime import date

import pytest
from sqlalchemy import select

from command_center.models import Audit
from command_center.personal_inbox import parse, select_view, CREATED, REMINDER
from test_personal_inbox import personal as personal, snapshot
from test_telegram_bridge import message
from test_telegram_task_status import response, authority
from test_telegram_service import configured as configured


@pytest.mark.parametrize('text,expected', [
    ('Мои планы', {'action': 'list', 'category': 'task', 'undated': True}),
    ('Напомни, что я планировал', {'action': 'list', 'category': 'task', 'undated': True}),
    ('Что отложено', {'action': 'list', 'category': 'task', 'status': 'deferred'}),
    ('Что отложено по кондитерской', {'action': 'list', 'category': 'task',
                                    'project_id': 'vanilla-sugar', 'status': 'deferred'}),
    ('Планы по ванили и сахару', {'action': 'list', 'category': 'task',
                                'project_id': 'vanilla-sugar', 'undated': True}),
    ('Планы по ванилисахару', {'action': 'list', 'category': 'task',
                             'project_id': 'vanilla-sugar', 'undated': True}),
    ('Идеи по автосервису', {'action': 'list', 'category': 'idea', 'project_id': 'lnauto'}),
    ('Дела без срока по неизвестному', {'action': 'unknown_list_project'}),
    ('Планы по без проекта', {'action': 'list', 'category': 'task', 'project_id': None, 'undated': True}),
])
def test_read_only_natural_project_and_undated_queries(text, expected):
    assert parse(text) == expected


@pytest.mark.parametrize('text,title', [('Планирую проверить вентиляцию в кондитерской',
    'проверить вентиляцию в кондитерской'), ('Я планирую обсудить закупки', 'обсудить закупки'),
    ('На потом: разобрать документы', 'разобрать документы')])
def test_explicit_plans_are_deferred_without_a_guessed_date(text, title):
    assert parse(text) == {'action': 'create', 'category': 'task', 'title': title, 'status': 'deferred'}


def test_combined_filters_and_timezone_date_boundary():
    items = [{'id': 'a', 'category': 'task', 'status': 'deferred', 'due_at': None},
             {'id': 'b', 'category': 'task', 'status': 'done', 'due_at': None},
             {'id': 'c', 'category': 'idea', 'status': 'active', 'due_at': None},
             {'id': 'd', 'category': 'task', 'status': 'active', 'due_at': None},
             {'id': 'e', 'category': 'reminder', 'status': 'active', 'due_at': '2026-11-27T00:30:00+03:00'}]
    assigned = {'a': {'project_id': 'vanilla-sugar'}, 'b': {'project_id': 'vanilla-sugar'},
                'c': {'project_id': 'lnauto'}, 'd': {'project_id': 'lnauto'}}
    assert select_view(items, assigned, 'task', project_id='vanilla-sugar', status='deferred', undated=True) == [items[0]]
    assert select_view(items, assigned, 'reminder', through=date(2026, 11, 26), timezone='UTC') == [items[4]]
    assert select_view(items, assigned, 'reminder', through=date(2026, 11, 26), timezone='Europe/Moscow') == []


def test_project_overview_keeps_undated_plans_and_never_schedules_notifications(personal, store):
    bridge, _ = personal
    before = authority(store)
    response(bridge, message(1, 'Планирую проверить вентиляцию в кондитерской'))
    response(bridge, message(2, 'Проверить автосервис'))
    response(bridge, message(3, 'Идея: подарочные сертификаты для автосервиса'))
    data = snapshot(bridge)
    assert data[bridge.profile + ':1']['status'] == 'deferred'
    assert all(item['due_at'] is None for item in data.values())
    overview = response(bridge, message(4, 'Что отложено по кондитерской'))
    assert 'вентиляцию' in overview and 'без срока' in overview and 'отложена' in overview
    assert 'автосервис' not in overview and 'сертификаты' not in overview
    ideas = response(bridge, message(5, 'Идеи по автосервису'))
    assert 'сертификаты' in ideas and 'вентиляцию' not in ideas
    response(bridge, message(6, 'Готово №1'))
    assert 'вентиляцию' not in response(bridge, message(7, 'Мои планы'))
    assert 'не распознан' in response(bridge, message(8, 'Планы по неизвестному'))
    assert authority(store) == before
    with store.transaction() as session:
        assert len(list(session.scalars(select(Audit).where(Audit.event['kind'].as_string() == CREATED)))) == 3
        assert not session.scalar(select(Audit).where(Audit.event['kind'].as_string() == REMINDER))


def test_configured_polling_reloads_project_plans_from_same_store(configured, store, monkeypatch):
    from test_telegram_service import FakeBot, client_for, update
    from command_center.telegram_service import TelegramService
    monkeypatch.setenv('F1_ASSISTANT_ONLY', '1')
    fake = FakeBot()
    client = client_for(configured, fake)
    before = authority(store)
    try:
        fake.updates = [update(1, 'На потом: проверить вентиляцию в кондитерской')]
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        fake.updates = [update(2, 'Планы по кондитерской')]
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        assert 'Дела без срока' in fake.sent[-1]['text']
        assert 'вентиляцию' in fake.sent[-1]['text'] and 'отложена' in fake.sent[-1]['text']
        assert authority(store) == before
    finally:
        client.close()
