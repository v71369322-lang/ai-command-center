"""Real browser on loopback. Public synthetic login fixture, NOT real MFA proof."""
from dataclasses import replace
import json
from pathlib import Path
import socket
import threading
import time
from uuid import uuid4

from playwright.sync_api import sync_playwright
import uvicorn

from command_center.api import create_app
from command_center.worker import Runner
from command_center.runtime_broker import RuntimeBroker
from command_center.runtime_ledger import RuntimeLedger
from command_center.runtime_policy import RuntimeBackend, RuntimeLimits


def test_T01_T13_mobile_browser_real_synthetic_flow(settings, store, queue, tmp_path):
    identities = {role: f'public-browser-{role}-fixture-not-a-runtime-secret' for role in ('owner','operator','agent')}
    app = create_app(replace(settings, identities=identities))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={'width':390,'height':844})
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith('http://127.0.0.1:') else route.abort())
            page = context.new_page()
            page.goto(f'http://127.0.0.1:{sock.getsockname()[1]}')
            page.get_by_label('Тестовый credential').fill(identities['owner'])
            page.get_by_role('button', name='Войти / обновить', exact=True).click()
            page.get_by_role('button', name='Создать безопасную задачу', exact=True).click()
            page.get_by_role('heading', name='READY', exact=True).wait_for()
            store.dispatch(queue)
            message = json.loads(queue.rpop('f1:work'))
            Runner(store).execute(store.claim(message['task_id']))
            page.get_by_role('button', name='Войти / обновить', exact=True).click()
            page.get_by_role('heading', name='SUCCEEDED', exact=True).wait_for()
            assert page.get_by_text('- message: synthetic only', exact=False).count() >= 1
            attack = '<img src=x onerror="window.f1Injected=true">'
            malicious = store.create('owner', str(uuid4()), {
                'kind': 'render', 'values': {'markup': attack}, 'cost': 0, 'dependency': None})
            Runner(store).execute(store.claim(malicious['id']))
            page.get_by_role('button', name='Войти / обновить', exact=True).click()
            page.get_by_text('- markup: ' + attack, exact=False).wait_for()
            assert page.evaluate('window.f1Injected === undefined')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert page.locator('img').count() == 0
            page.get_by_role('button', name='Запустить тестового разработчика', exact=True).click()
            page.get_by_role('heading', name='READY', exact=True).wait_for()
            coding_task = next(t for t in store.snapshot()['tasks'] if t['payload']['kind'] == 'coding_synthetic')
            ledger = RuntimeLedger(tmp_path / 'browser-runtime.sqlite')
            ledger.watchdog()
            service = RuntimeBroker(store, ledger, RuntimeBackend(mode='cloud-rootful-test'), RuntimeLimits())
            try:
                service.submit(coding_task['id'], settings.source_revision)
                service.last_future.result(timeout=30)
            finally:
                service.pool.shutdown(wait=True)
            page.get_by_role('button', name='Войти / обновить', exact=True).click()
            page.get_by_text('Проверка 1: найдена ошибка, выполнено исправление', exact=True).wait_for()
            page.get_by_text('Проверка 2: пройдена', exact=True).wait_for()
            page.get_by_role('button', name='Открыть подготовленный PR', exact=True).click()
            page.get_by_role('heading', name='Подготовленный PR', exact=True).wait_for()
            assert page.get_by_text('Mock-режим: PR не опубликован в GitHub. Реальный AI не подключён.', exact=True).count() == 1
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            Path('.runtime').mkdir(exist_ok=True)
            page.screenshot(path='.runtime/mobile.png', full_page=True)
            page.get_by_role('button', name='Выйти', exact=True).click()
            assert page.get_by_label('Тестовый credential').input_value() == ''
            context.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
