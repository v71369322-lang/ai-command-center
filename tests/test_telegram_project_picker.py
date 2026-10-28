"""Issued project selection, actual PostgreSQL and strict HTTP mocks only."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from command_center.models import Audit, TelegramDelivery, TelegramInbox
from command_center.project_inbox import classify, inbox, EVENT as ASSIGNED
from command_center.store import Denied, Store, digest
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_project_picker import EVENT, keyboard, parse_callback
from test_telegram_service import FakeBot, OWNER, client_for, update
from test_telegram_service import configured as configured
from test_telegram_task_status import authority


@pytest.fixture
def bridge(store, configured):
    fake = FakeBot()
    client = client_for(configured, fake)
    yield TelegramBridge(store, client, OWNER), fake
    client.close()


def callback(service, fake, uid=2, pid="lnauto", version=0, number=1):
    while service.deliver_one():
        pass
    data = f"pj:{number}:{version}:{pid or 'none'}"
    matches = [
        i
        for i, body in enumerate(fake.sent, 1)
        if any(
            button.get("callback_data") == data
            for row in body.get("reply_markup", {}).get("inline_keyboard", [])
            for button in row
        )
    ]
    return {
        "update_id": uid,
        "callback_query": {
            "id": "public-picker-" + str(uid),
            "from": {"id": OWNER, "is_bot": False},
            "data": data,
            "message": {"message_id": matches[-1], "chat": {"id": OWNER, "type": "private"}},
        },
    }


def assignments(store):
    with store.transaction() as session:
        return len(
            session.execute(select(Audit).where(Audit.event["kind"].as_string() == ASSIGNED)).scalars().all()
        )


@pytest.mark.parametrize("pid", ["command-center", "vanilla-sugar", "lnauto", "capital-lab", None])
def test_published_choice_reuses_classifier_and_preserves_capture_and_authority(bridge, store, pid):
    service, fake = bridge
    result = service.receive(update(1, "Public saved request"))
    before = authority(store)
    choice = callback(service, fake, pid=pid)
    assert len(choice["callback_query"]["data"].encode()) <= 64
    service.receive(choice)
    row = inbox(store, "owner")["requests"][0]
    assert row["project_id"] == pid and row["assignment_version"] == 1
    with store.transaction() as session:
        capture = session.get(TelegramInbox, result["inbox_id"])
        assert capture.intent == {"kind": "capture", "text": "Public saved request"}
        assert capture.state == "NEEDS_PLANNING" and capture.task_id is None
    assert assignments(store) == 1 and authority(store) == before


def test_stale_button_does_not_overwrite_web_and_fresh_card_can_be_used(bridge, store):
    service, fake = bridge
    result = service.receive(update(1, "Public request"))
    old = callback(service, fake)
    classify(store, "owner", result["inbox_id"], "vanilla-sugar", 0, str(uuid4()))
    service.receive(old)
    while service.deliver_one():
        pass
    assert "карточка устарела" in fake.sent[-1]["text"]
    assert inbox(store, "owner")["requests"][0]["project_id"] == "vanilla-sugar"
    assert assignments(store) == 1
    service.receive(update(3, "/request 1"))
    service.receive(callback(service, fake, uid=4, version=1))
    assert inbox(store, "owner")["requests"][0]["project_id"] == "lnauto"
    assert inbox(store, "owner")["requests"][0]["assignment_version"] == 2


def test_concurrent_duplicate_and_restart_apply_one_assignment(bridge, store):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.receive, [choice, choice]))
    restarted = TelegramBridge(store, service.client, OWNER)
    assert results[0] == results[1] == restarted.receive(choice)
    assert assignments(store) == 1
    while restarted.deliver_one():
        pass
    assert len(fake.sent) == 2


def test_crash_before_reply_rolls_back_and_restart_finishes_once(bridge, store, monkeypatch):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    with monkeypatch.context() as patch:
        patch.setattr(service, "finish", lambda *args: (_ for _ in ()).throw(RuntimeError("crash")))
        with pytest.raises(RuntimeError, match="crash"):
            service.receive(choice)
    assert assignments(store) == 0
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.resume_pending()
    assert assignments(store) == 1
    restarted.receive(choice)
    assert assignments(store) == 1


@pytest.mark.parametrize("attack", ["sender", "group", "forward", "message", "request", "project", "version"])
def test_forged_or_misbound_choice_cannot_assign(bridge, store, attack):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    query = choice["callback_query"]
    if attack == "sender":
        query["from"]["id"] += 1
    elif attack == "group":
        query["message"]["chat"]["type"] = "group"
    elif attack == "forward":
        query["message"]["forward_origin"] = {"type": "user"}
    elif attack == "message":
        query["message"]["message_id"] += 99
    elif attack == "request":
        query["data"] = "pj:999:0:lnauto"
    elif attack == "project":
        query["data"] = "pj:1:0:crm-secret"
    else:
        query["data"] = "pj:1:1:lnauto"
    with pytest.raises(Denied):
        service.receive(choice)
    assert assignments(store) == 0 and store.snapshot()["tasks"] == []


def test_lost_send_receipt_is_not_treated_as_published(bridge, store):
    service, fake = bridge
    service.receive(update(1, "Public request"))

    def lost(method):
        if method == "sendMessage":
            raise httpx.ReadTimeout("synthetic loss")

    fake.after = lost
    assert service.deliver_one()["state"] == "UNCERTAIN"
    choice = callback(service, fake)
    with pytest.raises(Denied, match="not_issued"):
        service.receive(choice)
    assert assignments(store) == 0 and service.deliver_one() is None


def test_observed_lookalike_without_issue_anchor_cannot_authorize_choice(bridge, store, admin):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    with admin.transaction() as session:
        event = session.execute(select(Audit).where(Audit.event["kind"].as_string() == EVENT)).scalar_one()
        # Preserve a valid audit chain while modelling an unbound transport record.
        # A generic queued/observed message is not an issued project picker.
        delivery = session.get(TelegramDelivery, event.event["delivery_id"])
        copy = TelegramDelivery(
            id="f" * 64, profile=service.profile, state="SENT", message_id=999, body=deepcopy(delivery.body)
        )
        session.add(copy)
        admin.audit(
            session, "telegram_delivery_queued", "system", delivery_id=copy.id, request_hash=digest(copy.body)
        )
        admin.audit(
            session, "telegram_delivery_observed", "system", delivery_id=copy.id, state="SENT", message_id=999
        )
    choice["callback_query"]["message"]["message_id"] = 999
    with pytest.raises(Denied, match="not_issued"):
        service.receive(choice)
    assert assignments(store) == 0


def test_changed_source_rejects_old_picker_even_when_profile_is_stable(bridge, store, configured):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    path, config = configured
    new_config = config.model_copy(update={"source_revision": "c" * 40})
    path.write_text(new_config.model_dump_json())
    changed = Store(replace(store.settings, source_revision=new_config.source_revision))
    client = client_for((path, new_config), fake)
    try:
        upgraded = TelegramBridge(changed, client, OWNER)
        assert upgraded.profile == service.profile
        with pytest.raises(Denied, match="not_issued"):
            upgraded.receive(choice)
        assert assignments(changed) == 0
    finally:
        client.close()
        changed.engine.dispose()


def test_second_binding_check_failure_rolls_back_classification(bridge, store, monkeypatch):
    import command_center.telegram_project_picker as picker

    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    original, calls = picker.verify, []

    def revoked(*args):
        calls.append(1)
        if len(calls) == 2:
            raise Denied("picker_revoked_synthetic")
        original(*args)

    monkeypatch.setattr(picker, "verify", revoked)
    with pytest.raises(Denied, match="revoked_synthetic"):
        service.receive(choice)
    assert assignments(store) == 0


@pytest.mark.parametrize("attack", ["url", "callback", "rows", "label", "extra"])
def test_transport_rejects_modified_picker_before_http(bridge, attack):
    service, fake = bridge
    markup = keyboard("1", 0)
    button = markup["inline_keyboard"][0][0]
    if attack == "url":
        button["url"] = "https://invalid.example"
    elif attack == "callback":
        button["callback_data"] = "pj:999:0:command-center"
    elif attack == "rows":
        markup["inline_keyboard"].pop()
    elif attack == "label":
        button["text"] = "Untrusted tool output"
    else:
        markup["resize_keyboard"] = True
    with pytest.raises(Denied, match="method_or_scope"):
        service.client.call(
            "sendMessage", {"chat_id": OWNER, "text": "Public picker", "reply_markup": markup}
        )
    assert fake.calls == []


def test_callback_byte_limit_and_parser_bounds():
    markup = keyboard(str(2**53 - 1), 1000)
    for row in markup["inline_keyboard"]:
        assert len(row[0]["callback_data"].encode()) <= 64
        assert parse_callback(row[0]["callback_data"])["version"] == 1000
    for value in ["pj:01:0:lnauto", "pj:1:1001:lnauto", f"pj:{2**53}:0:lnauto", "pj:1:0:lnauto\n/stop"]:
        with pytest.raises(Denied):
            parse_callback(value)


def test_halt_allows_metadata_choice_without_resuming_execution(bridge, store):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    store.halt("owner")
    before = authority(store)
    service.receive(choice)
    assert inbox(store, "owner")["requests"][0]["project_id"] == "lnauto"
    assert authority(store) == before


def test_revoked_connection_blocks_choice_before_assignment(bridge, store, configured):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    path, config = configured
    path.write_text(config.model_copy(update={"mode": "disabled"}).model_dump_json())
    with pytest.raises(Denied, match="revoked_or_changed"):
        service.receive(choice)
    assert assignments(store) == 0


def test_lost_assignment_reply_does_not_undo_or_repeat_assignment(bridge, store):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    service.receive(choice)

    def lost(method):
        if method == "sendMessage":
            raise httpx.ReadTimeout("synthetic reply loss")

    fake.after = lost
    assert service.deliver_one()["state"] == "UNCERTAIN"
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.recover()
    restarted.receive(choice)
    assert assignments(store) == 1 and restarted.deliver_one() is None
    assert len(fake.sent) == 2


def test_another_profile_message_is_not_a_picker_for_this_profile(bridge, store):
    from command_center.telegram_bridge import MockTelegramHTTP

    service, _ = bridge
    service.receive(update(1, "Public current-profile request"))
    other_fake = FakeBot()
    client = MockTelegramHTTP(httpx.MockTransport(other_fake))
    try:
        other = TelegramBridge(store, client, OWNER)
        assert other.profile != service.profile
        other.receive(update(1, "Public other-profile request"))
        choice = callback(other, other_fake)
        with pytest.raises(Denied, match="not_issued"):
            service.receive(choice)
        assert assignments(store) == 0
    finally:
        client.close()


def test_corrupt_audit_is_not_converted_to_a_stale_card_receipt(bridge, store, admin):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    with admin.transaction() as session:
        row = session.execute(select(Audit).where(Audit.event["kind"].as_string() == EVENT)).scalar_one()
        row.digest = "0" * 64
    with pytest.raises(Denied):
        service.receive(choice)
    assert assignments(store) == 0


def test_known_secret_rotation_blocks_use_of_saved_text(bridge, store):
    service, fake = bridge
    service.receive(update(1, "Public request"))
    choice = callback(service, fake)
    changed = Store(replace(store.settings, redis_password="Public request"))
    try:
        current = TelegramBridge(changed, service.client, OWNER)
        with pytest.raises(Denied, match="secret_content"):
            current.receive(choice)
        assert assignments(changed) == 0
    finally:
        changed.engine.dispose()


@pytest.mark.parametrize("value", ["Ж" * 1000, "\x01" * 1100])
def test_large_readback_keeps_full_text_and_picker_within_transport_limits(bridge, store, value):
    from command_center.store import canonical

    service, fake = bridge
    service.receive(update(1, value))
    store.halt("owner")
    service.receive(update(2, "/request 1"))
    while service.deliver_one():
        pass
    assert any(value in body["text"] for body in fake.sent)
    assert all(len(canonical(body).encode()) <= 8192 for body in fake.sent)
    if "\x01" in value:
        assert len(fake.sent) == 3
        assert fake.sent[-1]["text"].startswith("Выберите проект запроса №1")
    before = authority(store)
    service.receive(callback(service, fake, uid=3))
    assert inbox(store, "owner")["requests"][0]["project_id"] == "lnauto"
    assert authority(store) == before


def test_poll_callback_is_acknowledged_once_and_reply_is_durable(bridge, store):
    service, fake = bridge
    fake.updates = [update(1, "Public request")]
    service.poll_once()
    choice = callback(service, fake)
    fake.updates = [choice]
    service.poll_once()
    restarted = TelegramBridge(store, service.client, OWNER)
    restarted.receive(choice)
    restarted.poll_once()
    assert assignments(store) == 1
    assert sum(method == "answerCallbackQuery" for method, _ in fake.calls) == 1
    assert len(fake.sent) == 2 and "Выбор проекта сохранён" in fake.sent[-1]["text"]
