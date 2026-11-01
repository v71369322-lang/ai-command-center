"""Human-readable manual drafts, strict owner scope and atomic durable replies."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from command_center.models import TelegramInbox
from command_center.request_plan_store import read
from command_center.store import Denied
from command_center.telegram_bridge import TelegramBridge
from test_manual_plan import configured as configured_request, events
from test_project_inbox import capture
from test_telegram_bridge import message, OWNER
from test_telegram_task_status import bridge as bridge, response, authority
from test_request_review_telegram import live_guard_bridge as live_guard_bridge
from test_telegram_service import configured as configured, update


def command(version=0):
    return (
        f"/draft_plan 1 1 1 {version}\nКратко: Изменить форму\nШаг: Описать поля\n"
        "Готово: Перечень полей проверен\nВопрос: Нужно ли второе поле?"
    )


def test_copyable_template_save_read_edit_and_shared_origin(store, bridge, client, headers):
    rid = configured_request(store)
    service, _ = bridge
    before = authority(store)
    template = response(service, message(2, "/plan_edit 1"))
    assert template.startswith("/draft_plan 1 1 1 0\n")
    with pytest.raises(Denied, match="replace_template"):
        service.receive(message(3, template))
    edited = (
        template.replace("[опишите цель]", "Изменить форму")
        .replace("[опишите шаг]", "Описать поля")
        .replace("[проверяемый результат]", "Поля проверены")
    )
    assert "версия 1" in response(service, message(3, edited))
    assert "Автор: владелец" in response(service, message(4, "/plan 1"))
    value = client.get(
        "/api/project-inbox/review", params={"request_id": rid}, headers=headers["owner"]
    ).json()
    assert value["plan"]["origin"] == "owner_authored" and value["checks"][3]["state"] == "DECLARED_MATCH"
    assert value["execution_authorized"] is value["provider_called"] is False
    assert "версия 2" in response(service, message(5, command(1)))
    assert read(store, "owner", rid)["version"] == 2
    assert authority(store) == before


def test_stale_plan_version_returns_a_conflict_without_overwrite(store, bridge):
    configured_request(store)
    service, _ = bridge
    response(service, message(2, command()))
    assert "сведения изменились" in response(service, message(3, command()))
    assert len(events(store)) == 1


@pytest.mark.parametrize(
    "value",
    [
        "/plan_edit",
        "/plan_edit 01",
        "/plan_edit 1 extra",
        "/draft_plan 1 1 1",
        "/draft_plan 1 1 1 0\nКратко: x\nГотово: y",
        "/draft_plan 1 1 1 0\nКратко: x\nШаг: y",
        "/draft_plan 1 1 1 0\nКратко: x\nШаг: y\nГотово: z\n/stop",
        "/draft_plan 1 1 1 101\nКратко: x\nШаг: y\nГотово: z",
    ],
)
def test_malformed_commands_never_become_captured_requests_or_plans(store, bridge, value):
    before = store.snapshot()
    with pytest.raises(Denied):
        bridge[0].receive(message(1, value))
    assert store.snapshot() == before


def test_unknown_and_unassigned_templates_do_not_create_a_plan(store, bridge):
    service, _ = bridge
    assert "не найден" in response(service, message(1, "/plan_edit 999"))
    capture(store, uid=2)
    assert "Сначала выберите проект" in response(service, message(3, "/plan_edit 2"))
    assert events(store) == []


def test_parallel_duplicate_command_saves_one_document_and_returns_one_receipt(store, bridge):
    rid = configured_request(store)
    service, _ = bridge
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: service.receive(message(2, command())), range(2)))
    assert result[0] == result[1] and len(events(store)) == 1 and read(store, "owner", rid)["version"] == 1


def test_reply_failure_rolls_back_plan_and_replay_finishes_once(store, bridge, monkeypatch):
    rid = configured_request(store)
    service, _ = bridge
    original = service.finish

    def fail(*a, **k):
        raise RuntimeError("public manual reply failure")

    monkeypatch.setattr(service, "finish", fail)
    with pytest.raises(RuntimeError):
        service.receive(message(2, command()))
    assert events(store) == []
    with store.transaction() as session:
        assert session.get(TelegramInbox, service.profile + ":2").state == "RECEIVED"
    monkeypatch.setattr(service, "finish", original)
    assert "версия 1" in response(service, message(2, command()))
    assert read(store, "owner", rid)["version"] == 1


@pytest.mark.parametrize("attack", ["sender", "group", "forward"])
def test_existing_private_owner_guards_apply_to_manual_writes(store, live_guard_bridge, attack):
    service, _ = live_guard_bridge
    value = update(1, command())
    if attack == "sender":
        value["message"]["from"]["id"] += 1
    elif attack == "group":
        value["message"]["chat"]["type"] = "group"
    else:
        value["message"]["forward_origin"] = {"type": "user"}
    before = authority(store)
    with pytest.raises(Denied):
        service.receive(value)
    assert events(store) == [] and authority(store) == before


def test_source_change_cannot_replay_a_pending_manual_write(store, bridge, monkeypatch):
    configured_request(store)
    service, _ = bridge
    original = service._apply_pending
    monkeypatch.setattr(
        service, "_apply_pending", lambda *a: (_ for _ in ()).throw(RuntimeError("public crash"))
    )
    with pytest.raises(RuntimeError):
        service.receive(message(2, command()))
    monkeypatch.setattr(service, "_apply_pending", original)
    from command_center.store import Store

    changed = Store(replace(store.settings, source_revision="b" * 40))
    try:
        other = TelegramBridge(changed, service.client, OWNER)
        with pytest.raises(Denied):
            other.receive(message(2, command()))
        assert events(store) == []
    finally:
        changed.engine.dispose()


def test_command_words_inside_step_text_do_not_change_admission(store, bridge):
    rid = configured_request(store)
    service, _ = bridge
    before = authority(store)
    response(service, message(2, command().replace("Описать поля", "/stop")))
    assert read(store, "owner", rid)["proposal"]["steps"][0]["description"] == "/stop"
    assert authority(store) == before


def test_revocation_before_reply_rolls_back_the_manual_document(
    store, live_guard_bridge, configured, monkeypatch
):
    from command_center.project_inbox import classify
    from command_center.project_setup import save as save_setup
    from test_project_setup import full
    from uuid import uuid4

    service, fake = live_guard_bridge
    rid = service.receive(update(1, "Public configured manual request"))["inbox_id"]
    classify(store, "owner", rid, "lnauto", 0, str(uuid4()))
    save_setup(store, "owner", "lnauto", 0, full(), str(uuid4()))
    path, config = configured
    original = service.finish

    def revoke(*args, **kwargs):
        path.write_text(config.model_copy(update={"mode": "disabled"}).model_dump_json())
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "finish", revoke)
    with pytest.raises(Denied, match="revoked_or_changed"):
        service.receive(update(2, command()))
    assert events(store) == [] and fake.calls == []
