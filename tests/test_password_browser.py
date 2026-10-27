"""Real UI/API/session over explicit loopback HTTP; not a Safari or MFA proof."""
from dataclasses import replace
import json
import socket
import threading
import time

from playwright.sync_api import sync_playwright
import uvicorn

from command_center.api import create_app
from command_center.password_auth import document


def test_password_mobile_login_stop_logout(settings, store, tmp_path):
    password = 'public-browser-password-fixture-only'
    path = tmp_path / 'owner.json'
    path.write_text(json.dumps(document('owner', password)))
    path.chmod(0o600)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
    config = replace(settings, auth_mode='password', owner_password_file=str(path),
                     web_origin=origin, password_loopback_http=True)
    server = uvicorn.Server(uvicorn.Config(create_app(config), log_level='critical', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(.05)
        assert server.started
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                context = browser.new_context(viewport={'width': 390, 'height': 844})
                context.route('**/*', lambda r: r.continue_() if r.request.url.startswith(origin + '/') else r.abort())
                page = context.new_page()
                page.goto(origin)
                page.get_by_label('Логин', exact=True).fill('owner')
                page.get_by_label('Пароль', exact=True).fill('wrong')
                page.get_by_role('button', name='Войти', exact=True).click()
                page.get_by_role('alert').wait_for()
                assert page.get_by_label('Пароль', exact=True).input_value() == ''
                page.get_by_label('Пароль', exact=True).fill(password)
                page.get_by_role('button', name='Войти', exact=True).click()
                page.get_by_role('heading', name='Управление', exact=True).wait_for()
                assert page.get_by_label('Пароль', exact=True).input_value() == ''
                assert page.get_by_text('Подписанное MFA-подтверждение тестового IdP', exact=True).count() == 0
                page.get_by_role('button', name='Аварийная остановка', exact=True).click()
                page.get_by_text('Запуски остановлены', exact=True).wait_for()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.get_by_role('button', name='Выйти', exact=True).click()
                page.get_by_role('heading', name='Управление', exact=True).wait_for(state='detached')
                assert context.request.get(origin + '/api/state').status == 401
                context.close()
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
