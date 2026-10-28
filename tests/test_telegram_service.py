"""Real PG and transport protocol, but ONLY public mock credentials/HTTP."""

from dataclasses import replace
import json
import logging
import threading

import httpx
import pytest
from sqlalchemy import select, text

from command_center.models import TelegramInbox, TelegramDelivery, Audit
from command_center.store import Denied, digest
from command_center.telegram_bridge import TelegramBridge
from command_center.telegram_service import TelegramService
from command_center.telegram_transport import ConfiguredTelegramHTTP, TelegramConnection, TelegramHTTPError

OWNER, BOT = 1234567, 123456789
PUBLIC_TOKEN = str(BOT) + ":" + "PUBLIC_FIXTURE_NOT_AN_ACTUAL_KEY_12345"


class FakeBot:
    def __init__(self):
        self.calls, self.updates, self.sent = [], [], []
        self.bot_id, self.webhook, self.failure = BOT, "", None
        self.after = None

    def __call__(self, request):
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        self.calls.append((method, body))
        assert request.url.host == "api.telegram.org"
        if method == "getMe":
            result = {"id": self.bot_id, "is_bot": True, "first_name": "Public fixture bot"}
        elif method == "getWebhookInfo":
            result = {"url": self.webhook, "has_custom_certificate": False, "pending_update_count": 0}
        elif method == "getUpdates":
            if self.failure:
                return httpx.Response(self.failure, json={"ok": False})
            result = [v for v in self.updates if v["update_id"] >= body["offset"]]
        elif method == "answerCallbackQuery":
            result = True
        else:
            assert method == "sendMessage"
            self.sent.append(body)
            result = {
                "message_id": len(self.sent),
                "date": 1700000000,
                "chat": {"id": OWNER, "type": "private"},
            }
        if self.after:
            self.after(method)
        return httpx.Response(200, json={"ok": True, "result": result})


def update(uid, value):
    return {
        "update_id": uid,
        "message": {
            "message_id": uid + 100,
            "date": 1700000000,
            "from": {"id": OWNER, "is_bot": False, "first_name": "Public fixture owner"},
            "chat": {"id": OWNER, "type": "private"},
            "text": value,
        },
    }


@pytest.fixture
def configured(tmp_path, settings):
    secret = tmp_path / "token"
    secret.write_text(PUBLIC_TOKEN)
    secret.chmod(0o600)
    config = TelegramConnection(
        mode="http_mock",
        owner_id=OWNER,
        bot_id=BOT,
        source_revision=settings.source_revision,
        token_file=str(secret),
    )
    path = tmp_path / "connection.json"
    path.write_text(config.model_dump_json())
    path.chmod(0o600)
    return path, config


def client_for(configured, fake, revision=None):
    path, config = configured
    return ConfiguredTelegramHTTP(
        str(path),
        digest(config.model_dump()),
        revision or config.source_revision,
        transport=httpx.MockTransport(fake),
    )


def test_real_service_heartbeat_is_visible_only_until_service_stops(configured, store):
    from command_center.telegram_health import status

    _, config = configured
    fake = FakeBot()
    client = client_for(configured, fake)
    approved = json.dumps({'mode': config.mode, 'bot_id': config.bot_id, 'owner_id': config.owner_id,
                           'connection_digest': digest(config.model_dump())})
    service = TelegramService(store, client, poll_seconds=0)
    real_heartbeat = service.heartbeat
    seen = []

    def observe():
        real_heartbeat()
        seen.append(status(store, approved))

    service.heartbeat = observe
    try:
        service.run(max_cycles=1)
        assert seen[0]['status'] == 'polling' and seen[0]['live_connected'] is False
        assert status(store, approved)['status'] == 'stopped'
    finally:
        client.close()


@pytest.mark.parametrize(
    "attack", ["approval", "revision", "disabled", "live_mock", "permissions", "symlink"]
)
def test_connection_fails_closed_before_http(configured, settings, attack, tmp_path):
    path, config = configured
    approved, revision = digest(config.model_dump()), settings.source_revision
    if attack == "approval":
        approved = "0" * 64
    if attack == "revision":
        revision = "a" * 40
    if attack in {"disabled", "live_mock"}:
        config = config.model_copy(update={"mode": "disabled" if attack == "disabled" else "live"})
        path.write_text(config.model_dump_json())
        approved = digest(config.model_dump())
    if attack == "permissions":
        path.chmod(0o644)
    if attack == "symlink":
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    fake = FakeBot()
    with pytest.raises(Denied):
        ConfiguredTelegramHTTP(str(path), approved, revision, transport=httpx.MockTransport(fake))
    assert fake.calls == []


@pytest.mark.parametrize(
    "method,body",
    [
        ("deleteWebhook", {}),
        ("sendMessage/../getMe", {}),
        ("sendMessage", {"chat_id": 999, "text": "outside owner scope"}),
        ("sendMessage", {"chat_id": OWNER, "text": PUBLIC_TOKEN}),
        (
            "sendMessage",
            {
                "chat_id": OWNER,
                "text": "safe",
                "reply_markup": {"inline_keyboard": [[{"text": "x", "url": "https://invalid.example"}]]},
            },
        ),
        ("getUpdates", {"offset": 0, "limit": 20, "timeout": 0, "allowed_updates": ["*"]}),
    ],
)
def test_method_and_secret_boundaries(configured, method, body):
    fake = FakeBot()
    client = client_for(configured, fake)
    try:
        with pytest.raises(Denied):
            client.call(method, body)
        assert fake.calls == []
    finally:
        client.close()


@pytest.mark.parametrize("bad", ["identity", "webhook"])
def test_bot_identity_and_existing_webhook_require_review(configured, store, bad):
    fake = FakeBot()
    fake.bot_id = 999 if bad == "identity" else BOT
    fake.webhook = "https://invalid.example/existing" if bad == "webhook" else ""
    client = client_for(configured, fake)
    try:
        with pytest.raises(Denied):
            TelegramService(store, client).run(max_cycles=1)
        assert not any(m == "getUpdates" for m, _ in fake.calls)
    finally:
        client.close()


@pytest.mark.parametrize("bad", ["redirect", "oversized", "lost"])
def test_http_failure_never_exposes_token_or_follows_redirect(configured, caplog, bad):
    calls = []

    def reply(request):
        calls.append(request.url.host)
        if bad == "redirect":
            return httpx.Response(302, headers={"Location": "https://invalid.example/"})
        if bad == "oversized":
            return httpx.Response(200, content=b"x" * 65537)
        raise httpx.ReadTimeout("lost response " + PUBLIC_TOKEN, request=request)

    client = client_for(configured, reply)
    try:
        with caplog.at_level(logging.DEBUG), pytest.raises(TelegramHTTPError) as error:
            client.call("getMe", {})
        assert PUBLIC_TOKEN not in str(error.value) + repr(client) + caplog.text
        assert calls == ["api.telegram.org"]
    finally:
        client.close()


def test_config_revocation_and_rotation_block_next_call(configured):
    fake = FakeBot()
    client = client_for(configured, fake)
    path, config = configured
    try:
        path.write_text(config.model_copy(update={"mode": "disabled"}).model_dump_json())
        with pytest.raises(Denied, match="revoked"):
            client.call("getMe", {})
        path.write_text(config.model_dump_json())
        from pathlib import Path

        Path(config.token_file).write_text(str(BOT) + ":" + "R" * 35)
        with pytest.raises(Denied, match="rotated"):
            client.call("getMe", {})
        assert fake.calls == []
    finally:
        client.close()


def test_poller_restart_duplicate_update_and_readonly_profile(configured, store):
    fake = FakeBot()
    fake.updates = [update(1, "Синтетический запрос через постоянный обработчик")]
    client = client_for(configured, fake)
    try:
        assert TelegramService(store, client, poll_seconds=0).run(max_cycles=1)["completed_cycles"] == 1
        assert TelegramService(store, client, poll_seconds=0).run(max_cycles=1)["completed_cycles"] == 1
        assert len(fake.sent) == 1 and store.snapshot()["tasks"] == []
        with store.transaction() as session:
            assert session.scalar(select(TelegramInbox)).state == "NEEDS_PLANNING"
    finally:
        client.close()


def test_only_one_poller_and_lost_advisory_lock_prevents_http(configured, store):
    fake = FakeBot()
    client = client_for(configured, fake)
    other = client_for(configured, fake)
    service = TelegramService(store, client)
    try:
        with service.leader():
            with pytest.raises(Denied, match="another_poller"):
                TelegramService(store, other).run(max_cycles=1)
            service._leader.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": service._key})
            service._leader.commit()
            with pytest.raises(Denied, match="leadership_lost"):
                client.call("getMe", {})
        assert fake.calls == []
    finally:
        client.close()
        other.close()


def test_pending_intent_resumes_without_remote_redelivery(configured, store, monkeypatch):
    fake = FakeBot()
    client = client_for(configured, fake)
    bridge = TelegramBridge(store, client, OWNER)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                bridge, "_apply_pending", lambda *args: (_ for _ in ()).throw(RuntimeError("crash"))
            )
            with pytest.raises(RuntimeError):
                bridge.receive(update(1, "Saved before process crash"))
        assert fake.updates == []
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        with store.transaction() as session:
            assert session.scalar(select(TelegramInbox)).state == "NEEDS_PLANNING"
        assert len(fake.sent) == 1
    finally:
        client.close()


def test_profile_is_stable_across_revision_and_old_pending_fails_closed(configured, store, monkeypatch):
    fake = FakeBot()
    client = client_for(configured, fake)
    try:
        bridge = TelegramBridge(store, client, OWNER)
        before = bridge.profile
        with monkeypatch.context() as patch:
            patch.setattr(
                bridge, "_apply_pending", lambda *args: (_ for _ in ()).throw(RuntimeError("crash"))
            )
            with pytest.raises(RuntimeError):
                bridge.receive(update(1, "/demo previous source"))
        path, config = configured
        new = config.model_copy(update={"source_revision": "a" * 40})
        path.write_text(new.model_dump_json())
        fresh = client_for((path, new), fake)
        new_store = type(store)(replace(store.settings, source_revision="a" * 40))
        try:
            next_bridge = TelegramBridge(new_store, fresh, OWNER)
            assert next_bridge.profile == before
            with pytest.raises(Denied, match="source_revision_changed"):
                next_bridge.resume_pending()
            assert new_store.snapshot()["tasks"] == []
        finally:
            fresh.close()
            new_store.engine.dispose()
    finally:
        client.close()


@pytest.mark.parametrize("status,expected", [(401, 1), (503, 3)])
def test_read_retries_are_bounded(configured, store, monkeypatch, status, expected):
    fake = FakeBot()
    fake.failure = status
    client = client_for(configured, fake)
    stop = threading.Event()
    monkeypatch.setattr(stop, "wait", lambda *_: False)
    try:
        with pytest.raises(Denied, match="retry_limit"):
            TelegramService(store, client, poll_seconds=0).run(stop, max_cycles=1)
        assert sum(method == "getUpdates" for method, _ in fake.calls) == expected
    finally:
        client.close()


def test_shutdown_during_poll_does_not_execute_message(configured, store):
    fake = FakeBot()
    fake.updates = [update(1, "/demo do not execute")]
    stop = threading.Event()
    fake.after = lambda method: stop.set() if method == "getUpdates" else None
    client = client_for(configured, fake)
    try:
        assert TelegramService(store, client, poll_seconds=0).run(stop, max_cycles=1)["completed_cycles"] == 0
        assert store.snapshot()["tasks"] == [] and fake.sent == []
    finally:
        client.close()


def test_audit_corruption_prevents_even_handshake(configured, store, admin):
    with admin.transaction() as session:
        session.execute(text("UPDATE audit SET digest=repeat('f',64)"))
    fake = FakeBot()
    client = client_for(configured, fake)
    try:
        with pytest.raises(Denied, match="audit_integrity"):
            TelegramService(store, client).run(max_cycles=1)
        assert fake.calls == []
    finally:
        client.close()


def test_uncertain_send_is_not_repeated_by_poller_restart(configured, store, admin):
    fake = FakeBot()

    def lose(request):
        result = fake(request)
        if request.url.path.endswith("/sendMessage"):
            raise httpx.ReadTimeout("response lost")
        return result

    client = client_for(configured, lose)
    fake.updates = [update(1, "Save request")]
    try:
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        assert len(fake.sent) == 1
        with admin.transaction() as session:
            assert session.scalar(select(TelegramDelivery)).state == "UNCERTAIN"
            assert session.scalar(
                select(Audit).where(Audit.event["kind"].as_string() == "telegram_service_started")
            )
    finally:
        client.close()


@pytest.mark.parametrize("lost_ack", [False, True])
def test_complete_service_approval_execution_and_notification(configured, store, queue, lost_ack):
    from command_center.worker import Runner

    fake = FakeBot()

    def handle(request):
        result = fake(request)
        if lost_ack and request.url.path.endswith("/answerCallbackQuery"):
            raise httpx.ReadTimeout("callback receipt lost")
        return result

    client = client_for(configured, handle)
    try:
        fake.updates = [update(1, "/demo service end-to-end demo")]
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        task = store.snapshot()["tasks"][0]
        assert task["state"] == "WAITING_APPROVAL"
        callback_data = fake.sent[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        fake.updates = [
            {
                "update_id": 2,
                "callback_query": {
                    "id": "public-callback-receipt",
                    "chat_instance": "public-chat-instance",
                    "from": {"id": OWNER, "is_bot": False, "first_name": "Public fixture owner"},
                    "message": {
                        "message_id": 1,
                        "date": 1700000000,
                        "chat": {"id": OWNER, "type": "private"},
                    },
                    "data": callback_data,
                },
            }
        ]
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        assert store.get(task["id"])["state"] == "READY"
        store.dispatch(queue)
        event = json.loads(queue.rpop("f1:work"))
        Runner(store).execute(store.claim(event["task_id"]))
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        assert store.get(task["id"])["state"] == "SUCCEEDED"
        assert sum("Результат независимо проверен" in msg["text"] for msg in fake.sent) == 1
        assert sum(method == "answerCallbackQuery" for method, _ in fake.calls) == 1
        with store.transaction() as session:
            ack = session.scalar(
                select(Audit).where(Audit.event["kind"].as_string() == "telegram_callback_ack_result")
            )
            assert ack.event["state"] == ("UNCERTAIN" if lost_ack else "ACKNOWLEDGED")
    finally:
        client.close()


def test_lost_leader_during_http_cannot_apply_received_command(configured, store):
    fake = FakeBot()
    fake.updates = [update(1, "/demo do not execute after lease loss")]
    client = client_for(configured, fake)
    service = TelegramService(store, client, poll_seconds=0)
    fake.after = lambda method: service._leader.invalidate() if method == "getUpdates" else None
    try:
        with pytest.raises(Denied, match="leadership_lost"):
            service.run(max_cycles=1)
        assert store.snapshot()["tasks"] == [] and fake.sent == []
    finally:
        client.close()


def test_inactivity_reset_does_not_skip_new_random_lower_update_ids(configured, store, admin):
    fake = FakeBot()
    client = client_for(configured, fake)
    try:
        TelegramBridge(store, client, OWNER).receive(update(1000000, "old request"))
        with admin.transaction() as session:
            session.execute(text("UPDATE telegram_inbox SET created_at=clock_timestamp()-interval '8 days'"))
        fake.updates = [update(3, "new lower update ID after inactivity")]
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        offsets = [body["offset"] for method, body in fake.calls if method == "getUpdates"]
        assert offsets == [0, 4]
        with store.transaction() as session:
            assert len(session.scalars(select(TelegramInbox)).all()) == 2
    finally:
        client.close()


@pytest.mark.parametrize("delay,expected_calls", [(3, 3), (300, 1), ("invalid", 1)])
def test_rate_limit_delay_is_respected_or_service_stops(
    configured, store, monkeypatch, delay, expected_calls
):
    fake = FakeBot()

    def limit(request):
        if request.url.path.endswith("/getUpdates"):
            fake.calls.append(("getUpdates", json.loads(request.content)))
            return httpx.Response(429, json={"ok": False, "parameters": {"retry_after": delay}})
        return fake(request)

    client = client_for(configured, limit)
    stop, waits = threading.Event(), []
    monkeypatch.setattr(stop, "wait", lambda seconds: waits.append(seconds) or False)
    try:
        with pytest.raises(Denied, match="retry_limit"):
            TelegramService(store, client, poll_seconds=0).run(stop, max_cycles=1)
        assert sum(method == "getUpdates" for method, _ in fake.calls) == expected_calls
        if delay == 3:
            assert waits == [3, 4]
    finally:
        client.close()


def test_expired_pending_callback_is_rejected_without_stalling_restart(configured, store, monkeypatch):
    from datetime import timedelta
    from command_center.models import Approval

    fake = FakeBot()
    client = client_for(configured, fake)
    fake.updates = [update(1, "/demo pending callback")]
    try:
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        task = store.snapshot()["tasks"][0]
        token = fake.sent[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        callback = {
            "update_id": 2,
            "callback_query": {
                "id": "public-callback",
                "chat_instance": "public-instance",
                "from": {"id": OWNER, "is_bot": False, "first_name": "Public fixture owner"},
                "message": {"message_id": 1, "date": 1700000000, "chat": {"id": OWNER, "type": "private"}},
                "data": token,
            },
        }
        bridge = TelegramBridge(store, client, OWNER)
        with monkeypatch.context() as patch:
            patch.setattr(
                bridge, "_apply_pending", lambda *args: (_ for _ in ()).throw(RuntimeError("crash"))
            )
            with pytest.raises(RuntimeError):
                bridge.receive(callback)
        real_now = store.now
        monkeypatch.setattr(store, "now", lambda session: real_now(session) + timedelta(seconds=300))
        fake.updates = []
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        with store.transaction() as session:
            pending = session.scalar(select(TelegramInbox).where(TelegramInbox.id.endswith(":2")))
            assert pending.state == "REJECTED" and session.get(Approval, task["id"]) is None
        assert store.get(task["id"])["state"] == "WAITING_APPROVAL"
    finally:
        client.close()


def test_bot_token_in_message_is_not_saved_or_forwarded(configured, store):
    fake = FakeBot()
    fake.updates = [update(1, PUBLIC_TOKEN)]
    client = client_for(configured, fake)
    try:
        TelegramService(store, client, poll_seconds=0).run(max_cycles=1)
        with store.transaction() as session:
            row = session.scalar(select(TelegramInbox))
            assert row.state == "REJECTED" and PUBLIC_TOKEN not in json.dumps(row.intent)
        assert fake.sent == [] and store.snapshot()["tasks"] == []
    finally:
        client.close()



def test_service_entrypoint_needs_no_api_owner_or_redis_keys(settings, tmp_path, monkeypatch):
    from command_center.telegram_service import service_settings
    path = tmp_path / "public-db-binding"
    path.write_text("public-database-fixture-not-a-real-key")
    monkeypatch.setenv("F1_DB_PASSWORD_FILE", str(path))
    monkeypatch.setenv("F1_DB_USER", "f1_app")
    monkeypatch.setenv("F1_SOURCE_REVISION", settings.source_revision)
    monkeypatch.delenv("F1_IDENTITIES_FILE", raising=False)
    monkeypatch.delenv("F1_REDIS_PASSWORD_FILE", raising=False)
    result = service_settings()
    assert result.identities == {} and result.redis_password == "" and result.redis_url == ""
    assert result.database_url.username == "f1_app"
    monkeypatch.setenv("F1_DB_USER", "f1_admin")
    with pytest.raises(Denied, match="nonadmin"):
        service_settings()
