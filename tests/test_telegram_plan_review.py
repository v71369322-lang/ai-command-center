"""Private-owner paginated advisory readback; PostgreSQL + fake Bot API only."""
from copy import deepcopy
import json
import re

import pytest
from sqlalchemy import select

from command_center.models import TelegramDelivery
from command_center.project_inbox import classify
from command_center.request_plan_store import save
from command_center.request_planning import context
from command_center.store import Denied, canonical
from command_center.telegram_bridge import TelegramBridge
from uuid import uuid4
from test_request_planning import snapshot as snapshot, response as model_response, change_plan, MODEL, LIMITS
from test_request_plan_store import events
from test_telegram_bridge import message, OWNER
from test_telegram_task_status import bridge as bridge, response, authority, service_reply_id
from test_telegram_readiness import ledger
from test_telegram_service import configured as configured, update as configured_update, FakeBot, client_for


@pytest.fixture
def configured_bridge(store, configured):
    fake = FakeBot()
    client = client_for(configured, fake)
    yield TelegramBridge(store, client, client.owner), fake
    client.close()


def persist(store, snapshot, data=None):
    return save(store, 'owner', snapshot, data or model_response(snapshot), MODEL, **LIMITS)


def test_missing_draft_is_honest_and_does_not_generate_or_create_any_task(snapshot, bridge, store):
    before = authority(store), ledger(store)
    text = response(bridge[0], message(2, '/plan 1'))
    assert 'пока не сохранён' in text and 'ещё не подключено' in text
    assert events(store) == [] and (authority(store), ledger(store)) == before


def test_readback_is_explicitly_unverified_advice_and_never_an_execution_grant(snapshot, bridge, store):
    persist(store, snapshot)
    before = authority(store), ledger(store)
    value = response(bridge[0], message(2, '/plan 1'))
    assert 'Черновик 1' in value and 'Проект: LNAuto' in value
    assert 'Источник AI-ответа не подтверждён' in value and 'не разрешение на действия' in value
    assert 'Предложение изменения формы' in value and 'Критерий готовности' in value
    assert 'Работа по реальной бизнес-задаче не выполнялась' in value
    assert (authority(store), ledger(store)) == before


def test_long_unicode_plan_pages_are_complete_bounded_and_version_pinned(snapshot, bridge, store):
    data = model_response(snapshot)
    values = [str(i) + ':' + '🚀' * 297 for i in range(7)]
    def fill(plan):
        plan['summary'] = values[0]
        plan['steps'] = [{'description': values[i], 'acceptance': [values[i + 1]]} for i in (1, 3, 5)]
    change_plan(data, fill)
    # Keep the public fixture's nested JSON compact; no real billed usage is asserted.
    part = data['output'][-1]['content'][0]
    part['text'] = json.dumps(json.loads(part['text']), ensure_ascii=False)
    persist(store, snapshot, data)
    service, _ = bridge
    page = response(service, message(2, '/plan 1'))
    total = int(re.search(r'Страница 1/([0-9]+)', page)[1])
    assert total > 1
    new = model_response(snapshot)
    new['id'] += '_second'
    change_plan(new, lambda p: p.update(summary='SECOND_DRAFT_MARKER'))
    persist(store, snapshot, new)
    pages = [page]
    for index in range(2, total + 1):
        assert f'/plan 1 1 {index}' in pages[-1]
        pages.append(response(service, message(index + 1, f'/plan 1 1 {index}')))
    assert all('Черновик 1' in p and 'SECOND_DRAFT_MARKER' not in p for p in pages)
    assert all(sum(value in p for p in pages) == 1 for value in values)
    assert all(len(p) <= 4096 and len(canonical({'chat_id': OWNER, 'text': p}).encode()) <= 8192 for p in pages)
    assert 'Далее:' not in pages[-1]
    assert 'SECOND_DRAFT_MARKER' in response(service, message(100, '/plan 1'))


def test_nonexistent_version_or_page_never_falls_back_silently(snapshot, bridge, store):
    persist(store, snapshot)
    assert 'черновик не найден' in response(bridge[0], message(2, '/plan 1 2 1'))
    assert 'Открыть: /plan 1 1 1' in response(bridge[0], message(3, '/plan 1 1 50'))


@pytest.mark.parametrize('attack', ['sender', 'group', 'forward', 'foreign_profile'])
def test_private_owner_and_current_telegram_profile_are_required(snapshot, bridge, store, attack):
    persist(store, snapshot)
    update = message(2, '/plan 1')
    service, fake = bridge
    if attack == 'sender':
        update['message']['from']['id'] += 1
    elif attack == 'group':
        update['message']['chat']['type'] = 'group'
    elif attack == 'forward':
        update['message']['forward_origin'] = {'type': 'user'}
    else:
        service = TelegramBridge(store, service.client, OWNER + 1)
        result = service.receive(message(2, '/plan 1', owner=OWNER + 1, chat=OWNER + 1))
        with store.transaction() as session:
            row = session.get(TelegramDelivery, service_reply_id(service, result['inbox_id']))
            assert row.body['chat_id'] == OWNER + 1
            value = row.body['text']
        assert 'Запрос не найден' in value and 'Предложение изменения формы' not in value
        return
    with pytest.raises(Denied, match='owner_private_chat_required'):
        service.receive(update)
    assert fake.sent == []


@pytest.mark.parametrize('command', ['/plan -1', '/plan 01', '/plan １', '/plan 1 0 1', '/plan 1 1 0',
    '/plan 1 1 51', '/plan 1 101 1', '/plan 1 1', '/plan 1 1 1 extra', '/plan ' + str(2**53)])
def test_malformed_plan_command_is_not_captured_or_executed(bridge, store, command):
    before = authority(store), ledger(store)
    with pytest.raises(Denied, match='plan_reference_invalid'):
        bridge[0].receive(message(99, command))
    assert (authority(store), ledger(store)) == before


def test_new_query_after_stop_hides_old_body_without_resuming(snapshot, bridge, store):
    persist(store, snapshot)
    store.halt('owner')
    before = authority(store), ledger(store)
    text = response(bridge[0], message(2, '/plan 1'))
    assert 'устарел' in text and 'Предложение изменения формы' not in text
    assert 'Новые запуски остановлены' in text and (authority(store), ledger(store)) == before


def test_lost_delivery_and_duplicate_update_do_not_resend_or_import_again(snapshot, bridge, store):
    persist(store, snapshot)
    service, fake = bridge
    while service.deliver_one():
        pass
    update = message(2, '/plan 1')
    first = service.receive(update)
    fake.fail = True
    assert service.deliver_one()['state'] == 'UNCERTAIN'
    restarted = TelegramBridge(store, service.client, OWNER)
    assert restarted.receive(deepcopy(update)) == first
    assert restarted.deliver_one() is None and len(events(store)) == 1
    with store.transaction() as session:
        assert len(list(session.scalars(select(TelegramDelivery).where(TelegramDelivery.state == 'UNCERTAIN')))) == 1


def test_prompt_markup_and_shell_remain_plain_advisory_text(snapshot, bridge, store):
    data = model_response(snapshot)
    value = '<b>Proposal only</b> /stop; curl https://untrusted.invalid; spend money'
    change_plan(data, lambda p: p.update(summary=value))
    persist(store, snapshot, data)
    before = authority(store), ledger(store)
    assert value in response(bridge[0], message(2, '/plan 1'))
    while bridge[0].deliver_one():
        pass
    body = bridge[1].sent[-1]
    assert 'parse_mode' not in body and 'reply_markup' not in body
    assert (authority(store), ledger(store)) == before


def test_configured_bot_service_delivers_readback_with_existing_transport_limits(configured_bridge, store):
    service, fake = configured_bridge
    rid = service.receive(configured_update(1, 'Public imported planning request'))['inbox_id']
    classify(store, 'owner', rid, 'lnauto', 0, str(uuid4()))
    current = context(store, 'owner', rid)
    persist(store, current)
    before = authority(store), ledger(store)
    service.receive(configured_update(2, '/plan 1'))
    while service.deliver_one():
        pass
    assert 'Источник AI-ответа не подтверждён' in fake.sent[-1]['text']
    assert 'Предложение изменения формы' in fake.sent[-1]['text']
    assert 'reply_markup' not in fake.sent[-1]
    assert (authority(store), ledger(store)) == before
