"""Chromium mobile viewport + actual owner API/PG; no real Telegram or VPS."""

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import socket
import threading
import time

import httpx
import json
from playwright.sync_api import sync_playwright, expect
import pytest
import uvicorn

from command_center.api import create_app
from command_center.telegram_bridge import MockTelegramHTTP, TelegramBridge
from command_center.store import digest

OWNER = 1234567
PUBLIC = {role: f"public-telegram-browser-{role}-fixture-only" for role in ("owner", "operator", "agent")}


def capture(store, value):
    def no_http(request):
        raise AssertionError("Telegram HTTP must not be called by the inbox UI test")

    client = MockTelegramHTTP(httpx.MockTransport(no_http))
    try:
        return TelegramBridge(store, client, OWNER).receive(
            {
                "update_id": 1,
                "message": {
                    "message_id": 101,
                    "date": 1700000000,
                    "from": {"id": OWNER, "is_bot": False, "first_name": "Synthetic owner"},
                    "chat": {"id": OWNER, "type": "private"},
                    "text": value,
                },
            }
        )
    finally:
        client.close()


@contextmanager
def mobile(settings, width=390):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    app = create_app(replace(settings, identities=PUBLIC))
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                context = browser.new_context(viewport={"width": width, "height": 844})
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_() if route.request.url.startswith(origin + "/") else route.abort()
                    ),
                )
                page = context.new_page()
                page.goto(origin)
                expect(page.get_by_role("heading", name="Закрытый доступ", exact=True)).to_be_visible()
                yield page, context
                context.close()
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


def login(page, role="owner"):
    page.get_by_label("Тестовый credential").fill(PUBLIC[role])
    page.get_by_role("button", name="Войти / обновить", exact=True).click()
    page.get_by_role("heading", name="Управление", exact=True).wait_for()


@pytest.mark.parametrize("width", [320, 390])
def test_telegram_mobile_saved_requests_are_read_only_escaped_and_fit(settings, store, width):
    value = "Тестовый запрос\n" + '<img src=x onerror="window.telegramInjected=true">' + "x" * 700
    capture(store, value)
    with mobile(settings, width) as (page, _):
        assert page.get_by_role("region", name="Telegram", exact=True).count() == 0
        login(page)
        panel = page.get_by_role("region", name="Telegram", exact=True)
        expect(panel.get_by_text("Бот не подключён.", exact=True)).to_be_visible()
        expect(panel.get_by_text(value, exact=True)).to_have_count(1)
        expect(
            panel.get_by_text("Ожидает планирования. Выполнение не запускалось.", exact=True)
        ).to_have_count(1)
        assert panel.locator("img,input,textarea").count() == 0
        assert page.evaluate("window.telegramInjected === undefined")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        button = panel.get_by_role("button", name="Обновить Telegram", exact=True)
        box = button.bounding_box()
        assert box and box["height"] >= 44 and box["width"] >= 44
        button.click()
        expect(panel.get_by_text(value, exact=True)).to_have_count(1)
        assert store.snapshot()["tasks"] == []
        if width == 390:
            Path(".runtime").mkdir(exist_ok=True)
            panel.screenshot(path=".runtime/telegram-mobile.png")
        page.get_by_role("button", name="Выйти", exact=True).click()
        expect(panel).to_have_count(0)
        expect(page.get_by_text(value, exact=True)).to_have_count(0)


@pytest.mark.parametrize("status", [404, 503])
def test_telegram_http_failure_does_not_hide_control_panel_and_can_retry(settings, store, status):
    capture(store, "Синтетический запрос для повторной загрузки")
    with mobile(settings) as (page, _):
        page.route(
            "**/api/telegram/requests",
            lambda route: route.fulfill(
                status=status, json={"detail": "private backend details must not be rendered"}
            ),
        )
        login(page)
        panel = page.get_by_role("region", name="Telegram", exact=True)
        expect(panel.get_by_role("alert")).to_contain_text("Раздел Telegram недоступен")
        expect(page.get_by_role("heading", name="Управление", exact=True)).to_be_visible()
        assert page.get_by_text("private backend details", exact=False).count() == 0
        assert panel.get_by_text("Сохранённых запросов пока нет.", exact=True).count() == 0
        page.unroute("**/api/telegram/requests")
        panel.get_by_role("button", name="Обновить Telegram", exact=True).click()
        expect(panel.get_by_text("Синтетический запрос для повторной загрузки", exact=True)).to_be_visible()
        expect(panel.get_by_role("alert")).to_have_count(0)


@pytest.mark.parametrize("broken", ["status", "inbox"])
def test_telegram_unknown_state_is_not_shown_as_connected_or_empty(settings, store, broken):
    with mobile(settings) as (page, _):
        path, data = (
            ("status", {"mode": "live", "live_connected": True, "voice_enabled": True})
            if broken == "status"
            else (
                "requests",
                {
                    "requests": [{"id": "forged", "state": "SUCCEEDED", "text": "not verified"}],
                    "ai_planning_connected": False,
                },
            )
        )
        page.route("**/api/telegram/" + path, lambda route: route.fulfill(status=200, json=data))
        login(page)
        panel = page.get_by_role("region", name="Telegram", exact=True)
        expect(panel.get_by_role("alert")).to_be_visible()
        assert panel.get_by_text("Бот не подключён.", exact=True).count() == 0
        assert panel.get_by_text("Сохранённых запросов пока нет.", exact=True).count() == 0
        assert panel.get_by_text("not verified", exact=True).count() == 0


def test_telegram_owner_data_disappears_on_logout_and_operator_cannot_read(settings, store):
    capture(store, "Owner-only synthetic request")
    with mobile(settings) as (page, _):
        login(page)
        panel = page.get_by_role("region", name="Telegram", exact=True)
        expect(panel.get_by_text("Owner-only synthetic request", exact=True)).to_be_visible()
        pending = []
        page.route("**/api/telegram/requests", lambda route: pending.append(route))
        with page.expect_request("**/api/telegram/requests"):
            panel.get_by_role("button", name="Обновить Telegram", exact=True).click()
        page.get_by_role("button", name="Выйти", exact=True).click()
        expect(panel).to_have_count(0)
        assert page.get_by_text("Owner-only synthetic request", exact=True).count() == 0
        page.unroute("**/api/telegram/requests")
        login(page, "operator")
        expect(page.get_by_role("region", name="Telegram", exact=True).get_by_role("alert")).to_be_visible()
        assert page.get_by_text("Owner-only synthetic request", exact=True).count() == 0


@pytest.mark.parametrize('mode', ['http_mock', 'live'])
def test_mobile_displays_scoped_service_evidence_and_stop(settings, store, monkeypatch, mode):
    # Synthetic audit fixture validates presentation only, not real Bot API connectivity.
    approved = {'mode': mode, 'bot_id': 123456789, 'owner_id': OWNER, 'connection_digest': 'a' * 64}
    monkeypatch.setenv('F1_TELEGRAM_SCOPE', json.dumps(approved))
    profile = digest({'mode': mode, 'bot_id': approved['bot_id'], 'owner': OWNER})
    with store.transaction() as session:
        store.audit(session, 'telegram_service_heartbeat', 'telegram_service', profile=profile,
                    bot_id=approved['bot_id'], connection_digest=approved['connection_digest'])
    with mobile(settings, 320) as (page, _):
        login(page)
        panel = page.get_by_role('region', name='Telegram', exact=True)
        message = ('Тестовый HTTP-адаптер. Настоящий бот не подключён.' if mode == 'http_mock'
                   else 'Бот подключён; обработчик получает сообщения.')
        expect(panel.get_by_text(message, exact=True)).to_be_visible()
        assert panel.locator('input,textarea').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        with store.transaction() as session:
            store.audit(session, 'telegram_service_stopped', 'telegram_service', profile=profile)
        panel.get_by_role('button', name='Обновить Telegram', exact=True).click()
        expected = ('Тестовый HTTP-адаптер. Настоящий бот не подключён.' if mode == 'http_mock'
                    else 'Обработчик Telegram остановлен.')
        expect(panel.get_by_text(expected, exact=True)).to_be_visible()
