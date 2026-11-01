"""Real bundled UI with intercepted synthetic HTTP; no DB, VPS or live API."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright


@pytest.mark.parametrize(('width', 'font_size'), [(390, 16), (320, 32)])
def test_mobile_control_buttons_fit_with_large_text(width, font_size):
    dist = Path('web/dist').resolve()
    assert (dist / 'index.html').is_file(), 'Build web before running browser tests'
    state = {
        'epoch': 1, 'checkpoint_digest': 'synthetic', 'halted': False,
        'recovery': False, 'tasks': [], 'events': [], 'budget': {},
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': width, 'height': 844})

            def respond(route):
                url = urlsplit(route.request.url)
                assert url.netloc == 'mobile.test', 'Unexpected external request'
                responses = {
                    '/api/auth/mode': {'mode': 'synthetic'},
                    '/api/state': state,
                    '/api/health': {'status': 'synthetic'},
                    '/api/experiments/first': None,
                    '/api/simulator/commands': {'id': 'synthetic'},
                }
                if url.path in responses:
                    route.fulfill(content_type='application/json',
                                  body=json.dumps(responses[url.path]))
                elif url.path.startswith('/api/'):
                    # Unrelated panels load independently; a missing optional API
                    # must not invalidate the control-layout assertion.
                    route.fulfill(status=404, content_type='application/json', body='{}')
                else:
                    file = (dist / url.path.lstrip('/')).resolve() if url.path != '/' else dist / 'index.html'
                    assert file.is_relative_to(dist) and file.is_file()
                    route.fulfill(path=str(file))

            page.route('**/*', respond)
            page.goto('https://mobile.test/')
            page.get_by_role('button', name='Войти / обновить', exact=True).click()
            page.get_by_role('heading', name='Управление', exact=True).wait_for()
            page.add_style_tag(content=f':root {{ font-size: {font_size}px; }}')
            button = page.get_by_role('button', name='Создать задачу с подтверждением', exact=True)
            assert button.is_visible() and button.is_enabled()
            for candidate in page.get_by_role('button').all():
                assert candidate.evaluate('''element => {
                    const box = element.getBoundingClientRect();
                    const parent = element.parentElement.getBoundingClientRect();
                    return box.left >= parent.left && box.right <= parent.right
                        && element.scrollWidth <= element.clientWidth + 1
                        && box.height >= 44;
                }'''), candidate.inner_text()
            # The existing action still calls its original endpoint and payload.
            with page.expect_request('**/api/simulator/commands') as request:
                button.click()
            assert request.value.post_data_json['kind'] == 'approved_render'
        finally:
            browser.close()
