"""Shared preparation stages through the existing private durable query path."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from sqlalchemy import select

from command_center.models import TelegramDelivery
from command_center.request_preparation import read
from command_center.store import Denied, canonical
from command_center.telegram_bridge import TelegramBridge
from test_project_inbox import capture
from test_request_preparation import matrix
from test_request_review_telegram import live_guard_bridge as live_guard_bridge
from test_telegram_bridge import message, OWNER
from test_telegram_service import configured as configured, update
from test_telegram_task_status import bridge as bridge, response, authority, service_reply_id


def test_stages_counts_filters_and_navigation_share_the_pg_reader(store, bridge):
    matrix(store)
    service, _ = bridge
    before = authority(store)
    text = response(service, message(30, "/queue"))
    assert "Найдено: 6 из 6" in text and "Страница 1/2" in text
    assert "Уточнить вопросы: 1" in text and "Сверить задачу и подключения: 1" in text
    assert "/queue all all 2" in text and "Это стадии подготовки, не разрешение запуска" in text
    second = response(service, message(31, "/queue all all 2"))
    assert "Страница 2/2" in second and "/queue all all 1" in second
    filtered = response(service, message(32, "/queue lnauto answer_questions"))
    assert "Найдено: 1 из 6" in filtered and "Запрос №5" in filtered and "/review 5" in filtered
    assert "Запрос №1" not in filtered and "Запрос №6" not in filtered
    assert read(store, "owner", project="lnauto", stage="answer_questions")["total_matching"] == 1
    assert authority(store) == before


@pytest.mark.parametrize(
    "command",
    [
        "/queue unknown",
        "/queue all execute",
        "/queue all all 0",
        "/queue all all 01",
        "/queue all all 201",
        "/queue all all 1 extra",
        "/queue\n/stop",
    ],
)
def test_malformed_commands_never_capture_a_request_or_change_admission(store, bridge, command):
    before = store.snapshot()
    with pytest.raises(Denied):
        bridge[0].receive(message(1, command))
    assert store.snapshot() == before


def test_duplicate_keeps_snapshot_but_new_command_observes_current_queue(store, bridge):
    capture(store)
    service, _ = bridge
    old = response(service, message(2, "/queue"))
    capture(store, uid=3)
    assert response(service, message(2, "/queue")) == old
    new = response(service, message(4, "/queue"))
    assert "Найдено: 1 из 1" in old and "Найдено: 2 из 2" in new


def test_foreign_profile_requests_and_counts_are_not_returned(store, bridge):
    capture(store, value="Public owner-one text")
    service, _ = bridge
    other = TelegramBridge(store, service.client, OWNER + 1)
    other.receive(message(1, "Public owner-two text", owner=OWNER + 1, chat=OWNER + 1))
    result = other.receive(message(2, "/queue", owner=OWNER + 1, chat=OWNER + 1))
    with store.transaction() as session:
        text = session.get(TelegramDelivery, service_reply_id(other, result["inbox_id"])).body["text"]
    assert "Найдено: 1 из 1" in text and "owner-two" in text and "owner-one" not in text


@pytest.mark.parametrize("attack", ["sender", "group", "forward"])
def test_private_owner_guards_remain_required(store, live_guard_bridge, attack):
    service, fake = live_guard_bridge
    value = update(1, "/queue")
    if attack == "sender":
        value["message"]["from"]["id"] += 1
    elif attack == "group":
        value["message"]["chat"]["type"] = "group"
    else:
        value["message"]["forward_origin"] = {"type": "user"}
    before = authority(store)
    with pytest.raises(Denied):
        service.receive(value)
    assert authority(store) == before and fake.calls == []


def test_parallel_duplicate_produces_one_durable_reply(store, bridge):
    capture(store)
    service, _ = bridge
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: service.receive(message(2, "/queue")), range(2)))
    assert values[0] == values[1]
    with store.transaction() as session:
        rows = list(
            session.scalars(
                select(TelegramDelivery).where(
                    TelegramDelivery.id == service_reply_id(service, values[0]["inbox_id"])
                )
            )
        )
        assert len(rows) == 1


def test_empty_missing_page_and_unicode_size_are_safe(store, bridge):
    service, _ = bridge
    assert "В этом разделе запросов пока нет" in response(service, message(1, "/queue"))
    for uid in range(2, 7):
        capture(store, uid=uid, value="<b>/stop</b> " + "🚀" * 400)
    text = response(service, message(7, "/queue"))
    assert (
        "<b>/stop</b>" in text
        and len(text) <= 4096
        and len(canonical({"chat_id": OWNER, "text": text}).encode()) <= 8192
    )
    assert "Страницы уже нет" in response(service, message(8, "/queue all all 3"))


def test_queued_reply_is_screened_again_after_known_credential_rotation(store, live_guard_bridge):
    service, fake = live_guard_bridge
    marker = "PUBLIC_QUEUE_MARKER_NOW_A_KNOWN_SYNTHETIC_CREDENTIAL"
    service.receive(update(1, marker))
    service.receive(update(2, "/queue"))
    assert service.deliver_one()["state"] == "SENT"
    store.settings = replace(store.settings, identities={**store.settings.identities, "agent": marker})
    before = len(fake.sent)
    with pytest.raises(Denied, match="sensitive_content"):
        service.deliver_one()
    assert len(fake.sent) == before
