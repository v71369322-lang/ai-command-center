"""Private-owner Telegram review of shared request/setup/plan state."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select

from command_center.models import TelegramDelivery
from command_center.project_setup import patch
from command_center.request_planning import context
from command_center.store import Denied, canonical
from command_center.telegram_bridge import TelegramBridge
from test_request_review import configured as configured_request
from test_request_plan_store import persist
from test_telegram_bridge import message, OWNER
from test_telegram_task_status import bridge as bridge, response, authority, service_reply_id
from test_telegram_service import configured as configured, update, FakeBot, client_for


@pytest.fixture
def live_guard_bridge(store, configured):
    fake = FakeBot()
    client = client_for(configured, fake)
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


def test_review_summarizes_same_versions_and_navigation_without_changing_authority(store, bridge):
    rid = configured_request(store)
    persist(store, context(store, 'owner', rid))
    store.halt('owner')
    before = authority(store)
    text = response(bridge[0], message(2, '/review 1'))
    assert 'Подготовка запроса №1' in text and 'Проект: LNAuto' in text and 'Настройки: черновик заполнен' in text
    assert 'План: устарел' in text and 'Приём запусков: новые запуски остановлены' in text
    assert '/request 1' in text and '/plan 1' in text and '/setup lnauto (версия 1)' in text
    assert 'Разрешение на выполнение и расходы не выдано' in text and 'не обращается к AI' in text
    assert authority(store) == before


def test_duplicate_review_keeps_observed_snapshot_and_new_query_observes_new_setup(store, bridge):
    configured_request(store)
    service, _ = bridge
    first = response(service, message(2, '/review 1'))
    patch(store, 'owner', 'lnauto', 1, 'deployment_target', 'new-staging', str(uuid4()))
    before = authority(store)
    assert response(service, message(2, '/review 1')) == first
    current = response(service, message(3, '/review 1'))
    assert '(версия 1)' in first and '(версия 2)' in current
    assert authority(store) == before


@pytest.mark.parametrize('value', ['/review', '/review -1', '/review 01', '/review 9007199254740992',
    '/review 1 extra', '/review 1 2', '/review 1\n/stop'])
def test_bad_references_never_become_saved_requests_or_commands(store, bridge, value):
    before = authority(store), store.snapshot()['events']
    with pytest.raises(Denied):
        bridge[0].receive(message(1, value))
    assert (authority(store), store.snapshot()['events']) == before


@pytest.mark.parametrize('attack', ['sender', 'group', 'forward'])
def test_review_keeps_existing_owner_and_private_chat_guards(store, live_guard_bridge, attack):
    service, fake = live_guard_bridge
    data = update(1, '/review 1')
    if attack == 'sender':
        data['message']['from']['id'] += 1
    elif attack == 'group':
        data['message']['chat']['type'] = 'group'
    else:
        data['message']['forward_origin'] = {'type': 'user'}
    before = authority(store)
    with pytest.raises(Denied):
        service.receive(data)
    assert fake.calls == [] and authority(store) == before


def test_foreign_profile_reference_returns_no_request_or_setup_content(store, bridge):
    configured_request(store)
    service, _ = bridge
    other = TelegramBridge(store, service.client, OWNER+1)
    data = message(2, '/review 1')
    data['message']['from']['id'] = data['message']['chat']['id'] = OWNER+1
    result = other.receive(data)
    with store.transaction() as session:
        reply = session.get(TelegramDelivery, service_reply_id(other, result['inbox_id'])).body['text']
    assert 'не найден' in reply and 'Public review request' not in reply and 'lnauto' not in reply


def test_parallel_duplicate_queries_make_one_reply_and_no_task(store, bridge):
    configured_request(store)
    service, _ = bridge
    before = authority(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _:service.receive(message(2, '/review 1')), range(2)))
    assert values[0] == values[1]
    with store.transaction() as session:
        rows = list(session.scalars(select(TelegramDelivery).where(TelegramDelivery.id == service_reply_id(service, values[0]['inbox_id']))))
        assert len(rows) == 1
    assert authority(store) == before


def test_plain_unicode_preview_fits_transport_and_does_not_interpret_markup(store, bridge):
    service, _ = bridge
    service.receive(message(1, '<b>/stop</b> ' + '🚀'*400))
    before = authority(store)
    text = response(service, message(2, '/review 1'))
    assert '<b>/stop</b>' in text and 'Проект: не выбран' in text
    assert len(text) <= 4096 and len(canonical({'chat_id':OWNER,'text':text}).encode()) <= 8192
    assert authority(store) == before


def test_known_credential_rotation_blocks_queued_review_before_http(store, live_guard_bridge):
    service, fake = live_guard_bridge
    marker = 'PUBLIC_REVIEW_MARKER_NOW_A_SYNTHETIC_KNOWN_CREDENTIAL'
    service.receive(update(1, marker))
    service.receive(update(2, '/review 1'))
    assert service.deliver_one()['state'] == 'SENT'
    service.store.settings = replace(store.settings, identities={**store.settings.identities,'agent':marker})
    before = len(fake.sent)
    with pytest.raises(Denied, match='sensitive_content'):
        service.deliver_one()
    assert len(fake.sent) == before
