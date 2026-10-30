"""Real API/PG in Chromium; no external repositories, servers or provider calls."""
from playwright.sync_api import expect
import pytest

from command_center.project_connections import connection_plan
from test_project_inbox import capture
from test_telegram_mobile import mobile, login
from test_telegram_task_status import authority


@pytest.mark.parametrize('width', [320, 390])
def test_mobile_owner_can_inspect_each_connection_plan_without_starting_work(settings, store, width):
    before = authority(store)
    with mobile(settings, width) as (page, _):
        calls = []
        page.on('request', lambda request: calls.append(request.url) if '/connection-plan' in request.url else None)
        login(page)
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        expect(panel.get_by_text('В этом разделе запросов пока нет.', exact=True)).to_be_visible()
        assert calls == []
        for label, name in [('AI Commander', 'ai-command-center'), ('Ваниль и Сахар', 'Vanilla-Sugar-CRM'),
                            ('LNAuto', 'LNAuto'), ('Capital Lab', 'Capital-Lab')]:
            summary = panel.get_by_text('Подключение: ' + label, exact=True)
            box = summary.bounding_box()
            assert box and box['height'] >= 44
            summary.click()
            plan = panel.get_by_role('region', name='План подключения: ' + label, exact=True)
            expect(plan.get_by_text('v71369322-lang/' + name, exact=True)).to_be_visible()
            expect(plan.get_by_text('Репозиторий: не проверено.', exact=True)).to_be_visible()
            expect(plan.get_by_text('Доставка на сервер: не проверено.', exact=True)).to_be_visible()
            setup = plan.get_by_role('region', name='Черновик подключения: ' + label, exact=True)
            expect(setup.get_by_role('button', name='Сохранить черновик', exact=True)).to_be_disabled()
            assert setup.get_by_role('button', name='Подключить', exact=True).count() == 0
            if width == 390 and label == 'LNAuto':
                plan.screenshot(path='.runtime/project-connection-mobile.png')
            summary.click()
            expect(plan).to_have_count(0)
        assert len(calls) == 4
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.get_by_role('button', name='Выйти', exact=True).click()
        expect(panel).to_have_count(0)
        assert authority(store) == before


@pytest.mark.parametrize('corruption', ['connected', 'project', 'component', 'repository', 'scope',
                                         'actions', 'checked_at', 'external'])
def test_bad_plan_is_hidden_and_assignment_still_works(settings, store, corruption):
    capture(store)
    data = connection_plan('owner', 'lnauto')
    if corruption == 'connected':
        data['execution_connected'] = True
    elif corruption == 'project':
        data['project_id'] = 'capital-lab'
    elif corruption == 'component':
        data['components'][0]['state'] = 'VERIFIED'
    elif corruption == 'repository':
        data['expected_repository'] = '<img src=x onerror="window.injected=true">'
    elif corruption == 'actions':
        data['actions_enabled'] = ['deploy']
    elif corruption == 'checked_at':
        data['checked_at'] = '2026-10-30T12:00:00Z'
    elif corruption == 'external':
        data['external_checks_performed'] = True
    else:
        data['scope'] = 'LIVE'
    with mobile(settings) as (page, _):
        page.route('**/api/projects/lnauto/connection-plan', lambda route: route.fulfill(status=200, json=data))
        login(page)
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        panel.get_by_text('Подключение: LNAuto', exact=True).click()
        plan = panel.get_by_role('region', name='План подключения: LNAuto', exact=True)
        expect(plan.get_by_role('alert')).to_be_visible()
        assert plan.get_by_text('Репозиторий: не проверено.', exact=True).count() == 0
        assert plan.locator('img').count() == 0
        panel.get_by_label('Проект запроса №1', exact=True).select_option('lnauto')
        panel.get_by_role('button', name='Сохранить проект', exact=True).click()
        expect(panel.get_by_text('Проект сохранён. Выполнение не запускалось.', exact=True)).to_be_visible()
        assert store.snapshot()['tasks'] == []


def test_plan_service_failure_can_be_retried_and_logout_hides_the_plan(settings, store):
    with mobile(settings) as (page, _):
        path = '**/api/projects/lnauto/connection-plan'
        page.route(path, lambda route: route.fulfill(status=503, json={'detail': 'private server error'}))
        login(page)
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        panel.get_by_text('Подключение: LNAuto', exact=True).click()
        plan = panel.get_by_role('region', name='План подключения: LNAuto', exact=True)
        expect(plan.get_by_role('alert')).to_be_visible()
        assert page.get_by_text('private server error', exact=False).count() == 0
        page.unroute(path)
        plan.get_by_role('button', name='Повторить загрузку плана', exact=True).click()
        expect(plan.get_by_text('v71369322-lang/LNAuto', exact=True)).to_be_visible()
        page.get_by_role('button', name='Выйти', exact=True).click()
        expect(plan).to_have_count(0)
        login(page)
        expect(panel).to_be_visible()
        assert panel.get_by_role('region', name='План подключения: LNAuto', exact=True).count() == 0


def test_logout_aborts_pending_plan_and_new_login_gets_a_fresh_view(settings, store):
    with mobile(settings) as (page, _):
        path = '**/api/projects/lnauto/connection-plan'
        pending = []
        page.route(path, lambda route: pending.append(route))
        login(page)
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        panel.get_by_text('Подключение: LNAuto', exact=True).click()
        plan = panel.get_by_role('region', name='План подключения: LNAuto', exact=True)
        expect(plan.get_by_role('status')).to_have_text('Загружаем план подключения…')
        with page.expect_event('requestfailed', predicate=lambda request: request.url.endswith('/lnauto/connection-plan')):
            page.get_by_role('button', name='Выйти', exact=True).click()
        assert len(pending) == 1
        expect(plan).to_have_count(0)
        page.unroute(path)
        login(page)
        panel.get_by_text('Подключение: LNAuto', exact=True).click()
        expect(plan.get_by_text('v71369322-lang/LNAuto', exact=True)).to_be_visible()
