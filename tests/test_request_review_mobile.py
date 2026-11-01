"""Real Chromium/API/PG review; no execution, external model or project access."""
from uuid import uuid4

from playwright.sync_api import expect
import pytest

from command_center.project_inbox import classify
from command_center.project_setup import save as save_setup, patch
from command_center.request_planning import context
from command_center.request_review import read
from test_project_inbox import capture
from test_project_setup import full
from test_request_plan_store import persist
from test_request_planning import response, change_plan
from test_request_review import configured
from test_telegram_mobile import mobile, login
from test_telegram_task_status import authority


def open_review(page):
    panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
    panel.get_by_text('Подготовка запроса №1', exact=True).click()
    review = panel.get_by_role('region', name='Подготовка запроса №1', exact=True)
    return panel, review


@pytest.mark.parametrize('width', [320, 390])
def test_mobile_request_project_setup_and_plan_review_without_execution(settings, store, width):
    rid = capture(store)
    before = authority(store)
    with mobile(settings, width) as (page, _):
        login(page)
        panel, review = open_review(page)
        expect(review.get_by_text('Выберите проект для запроса.', exact=True)).to_be_visible()
        panel.get_by_label('Проект запроса №1', exact=True).select_option('lnauto')
        panel.get_by_role('button', name='Сохранить проект', exact=True).click()
        expect(panel.get_by_text('Проект сохранён. Выполнение не запускалось.', exact=True)).to_be_visible()
        panel, review = open_review(page)
        expect(review.get_by_text('Заполните черновик подключения выбранного проекта выше.', exact=True)).to_be_visible()
        save_setup(store, 'owner', 'lnauto', 0, full(), str(uuid4()))
        review.get_by_role('button', name='Обновить обзор запроса', exact=True).click()
        expect(review.get_by_text('План запроса ещё не сохранён.', exact=False)).to_be_visible()
        snapshot = context(store, 'owner', rid)
        data = response(snapshot, questions=['Which public fields should change?'])
        injection = '<img src=x onerror="window.reviewInjected=true">'
        change_plan(data, lambda p:p.update(summary=injection))
        persist(store, snapshot, data)
        review.get_by_role('button', name='Обновить обзор запроса', exact=True).click()
        expect(review.get_by_text('Уточните вопросы предложения перед дальнейшей подготовкой.', exact=True)).to_be_visible()
        expect(review.get_by_text(injection, exact=True)).to_be_visible()
        expect(review.get_by_role('listitem').filter(has_text='Which public fields should change?')).to_be_visible()
        assert review.locator('img').count() == 0 and page.evaluate('window.reviewInjected === undefined')
        expect(review.get_by_text('Соответствие плана настройкам: не проверено.', exact=True)).to_be_visible()
        expect(review.get_by_text('Разрешение задачи и расходов: не выдано.', exact=True)).to_be_visible()
        expect(review.get_by_role('button', name='Сохранить ручной план', exact=True)).to_be_disabled()
        assert review.get_by_role('button', name='Запустить задачу', exact=True).count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        box = review.get_by_role('button', name='Обновить обзор запроса', exact=True).bounding_box()
        assert box and box['height'] >= 44
        if width == 390:
            review.screenshot(path='.runtime/request-review-mobile.png')
        page.get_by_role('button', name='Выйти', exact=True).click()
        expect(review).to_have_count(0)
        assert page.get_by_text(injection, exact=True).count() == 0
    assert authority(store) == before


def test_changed_assignment_hides_old_details_until_queue_is_reloaded(settings, store):
    rid = configured(store)
    persist(store, context(store, 'owner', rid))
    with mobile(settings) as (page, _):
        login(page)
        panel, review = open_review(page)
        expect(review.get_by_text('Предложение изменения формы', exact=True)).to_be_visible()
        classify(store, 'owner', rid, 'capital-lab', 1, str(uuid4()))
        review.get_by_role('button', name='Обновить обзор запроса', exact=True).click()
        expect(review.get_by_role('alert')).to_be_visible()
        assert review.get_by_text('Предложение изменения формы', exact=True).count() == 0
        panel.get_by_role('button', name='Обновить очередь проектов', exact=True).click()
        expect(panel.get_by_label('Проект запроса №1', exact=True)).to_have_value('capital-lab')
        panel, review = open_review(page)
        expect(review.get_by_text('Предложение плана: устарел.', exact=True)).to_be_visible()
        expect(review.get_by_text('Capital Lab: настройки версии 0', exact=True)).to_be_visible()


@pytest.mark.parametrize('corruption', ['ready', 'authorized', 'repository', 'plan_binding', 'check', 'next', 'project'])
def test_malformed_or_authority_claiming_reviews_are_hidden_without_breaking_queue(settings, store, corruption):
    rid = configured(store)
    value = read(store, 'owner', rid)
    if corruption == 'ready':
        value['execution_ready'] = True
    elif corruption == 'authorized':
        value['execution_authorized'] = True
    elif corruption == 'repository':
        value['project']['repository'] = 'other/production'
    elif corruption == 'plan_binding':
        value['plan']['setup_binding_verified'] = True
    elif corruption == 'check':
        value['checks'][4]['state'] = 'VERIFIED'
    elif corruption == 'next':
        value['next_step'] = 'deploy'
    else:
        value['project']['id'] = 'capital-lab'
    with mobile(settings) as (page, _):
        page.route('**/api/project-inbox/review?*', lambda route:route.fulfill(status=200, json=value))
        login(page)
        panel, review = open_review(page)
        expect(review.get_by_role('alert')).to_be_visible()
        assert review.get_by_role('heading', name='Готовность запроса', exact=True).count() == 0
        panel.get_by_label('Проект запроса №1', exact=True).select_option('capital-lab')
        panel.get_by_role('button', name='Сохранить проект', exact=True).click()
        expect(panel.get_by_text('Проект сохранён. Выполнение не запускалось.', exact=True)).to_be_visible()


def test_review_failure_can_be_reloaded_and_new_setup_is_observed(settings, store):
    rid = configured(store)
    with mobile(settings) as (page, _):
        path = '**/api/project-inbox/review?*'
        page.route(path, lambda route:route.fulfill(status=503, json={'detail':'private failure marker'}))
        login(page)
        _, review = open_review(page)
        expect(review.get_by_role('alert')).to_be_visible()
        assert page.get_by_text('private failure marker', exact=False).count() == 0
        patch(store, 'owner', 'lnauto', 1, 'deployment_target', 'updated-target', str(uuid4()))
        page.unroute(path)
        review.get_by_role('button', name='Обновить обзор запроса', exact=True).click()
        expect(review.get_by_text('LNAuto: настройки версии 2', exact=True)).to_be_visible()
        assert read(store, 'owner', rid)['project']['draft']['deployment_target'] == 'updated-target'


def test_logout_aborts_a_pending_review_and_does_not_restore_private_content(settings, store):
    configured(store)
    with mobile(settings) as (page, _):
        pending = []
        page.route('**/api/project-inbox/review?*', lambda route:pending.append(route))
        login(page)
        _, review = open_review(page)
        expect(review.get_by_role('status')).to_be_visible()
        with page.expect_event('requestfailed', predicate=lambda r:'/project-inbox/review?' in r.url):
            page.get_by_role('button', name='Выйти', exact=True).click()
        assert len(pending) == 1
        expect(review).to_have_count(0)
        page.unroute('**/api/project-inbox/review?*')
        login(page)
        assert page.get_by_role('region', name='Подготовка запроса №1', exact=True).count() == 0
