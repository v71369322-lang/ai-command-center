"""Narrow Chromium viewport with real owner API and PostgreSQL; no live services."""
from pathlib import Path

from playwright.sync_api import expect
import pytest

from test_project_inbox import capture
from test_telegram_mobile import mobile, login


@pytest.mark.parametrize('width', [320, 390])
def test_mobile_owner_assigns_filters_and_clears_without_starting_tasks(settings, store, width):
    value = '<img src=x onerror="window.projectInjected=true">' + 'x' * 600
    capture(store, value=value)
    with mobile(settings, width) as (page, _):
        assert page.get_by_role('region', name='Проекты и запросы', exact=True).count() == 0
        login(page)
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        expect(panel.get_by_text('Не распределены: 1.', exact=False)).to_be_visible()
        panel.get_by_text('Текст запроса', exact=True).click()
        expect(panel.get_by_text(value, exact=True)).to_be_visible()
        assert panel.locator('img').count() == 0 and page.evaluate('window.projectInjected === undefined')
        panel.get_by_label('Проект запроса №1', exact=True).select_option('vanilla-sugar')
        panel.get_by_role('button', name='Сохранить проект', exact=True).click()
        expect(panel.get_by_text('Проект сохранён. Выполнение не запускалось.', exact=True)).to_be_visible()
        expect(panel.get_by_label('Проект запроса №1', exact=True)).to_have_value('vanilla-sugar')
        panel.get_by_label('Показать запросы', exact=True).select_option('lnauto')
        expect(panel.get_by_text('В этом разделе запросов пока нет.', exact=True)).to_be_visible()
        panel.get_by_label('Показать запросы', exact=True).select_option('vanilla-sugar')
        expect(panel.get_by_label('Проект запроса №1', exact=True)).to_have_value('vanilla-sugar')
        panel.get_by_label('Проект запроса №1', exact=True).select_option('')
        panel.get_by_role('button', name='Сохранить проект', exact=True).click()
        expect(panel.get_by_text('В этом разделе запросов пока нет.', exact=True)).to_be_visible()
        panel.get_by_label('Показать запросы', exact=True).select_option('unassigned')
        expect(panel.get_by_label('Проект запроса №1', exact=True)).to_have_value('')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        box = panel.get_by_label('Проект запроса №1', exact=True).bounding_box()
        assert box and box['height'] >= 44 and box['width'] >= 44
        if width == 390:
            panel.screenshot(path=str(Path('.runtime/project-inbox-mobile.png')))
        assert store.snapshot()['tasks'] == []
        page.get_by_role('button', name='Выйти', exact=True).click()
        expect(panel).to_have_count(0)
        assert page.get_by_text(value, exact=True).count() == 0


def test_mobile_uncertain_save_requires_reload_and_keeps_control_panel(settings, store):
    capture(store)
    with mobile(settings) as (page, _):
        page.route('**/api/project-inbox/assign', lambda route: route.fulfill(status=503, json={'detail': 'do not echo private errors'}))
        login(page)
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        panel.get_by_label('Проект запроса №1', exact=True).select_option('lnauto')
        panel.get_by_role('button', name='Сохранить проект', exact=True).click()
        expect(panel.get_by_role('alert')).to_contain_text('Сохранение не подтверждено')
        expect(panel.get_by_role('button', name='Сохранить проект')).to_be_disabled()
        assert page.get_by_text('do not echo private errors', exact=False).count() == 0
        expect(page.get_by_role('heading', name='Управление', exact=True)).to_be_visible()
        page.unroute('**/api/project-inbox/assign')
        panel.get_by_role('button', name='Обновить очередь проектов', exact=True).click()
        expect(panel.get_by_label('Проект запроса №1', exact=True)).to_have_value('')


def test_mobile_rejects_false_connected_or_unknown_project_data(settings, store):
    with mobile(settings) as (page, _):
        page.route('**/api/project-inbox?*', lambda route: route.fulfill(status=200, json={
            'ai_planning_connected': True, 'projects': [{'id': 'unexpected-crm', 'execution_connected': True}],
            'requests': [], 'counts': {}, 'total_pending': 0, 'filter': 'all'}))
        login(page)
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        expect(panel.get_by_role('alert')).to_be_visible()
        assert panel.get_by_text('В этом разделе запросов пока нет.', exact=True).count() == 0
        assert page.get_by_text('unexpected-crm', exact=False).count() == 0


def test_mobile_project_data_hidden_from_operator(settings, store):
    capture(store, value='Private owner classification fixture')
    with mobile(settings) as (page, _):
        login(page, 'operator')
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        expect(panel.get_by_role('alert')).to_be_visible()
        assert panel.locator('.project-request').count() == 0


def test_mobile_assignment_refreshes_control_checkpoint_but_requires_explicit_resume(settings, store):
    capture(store)
    store.halt('owner')
    with mobile(settings) as (page, _):
        login(page)
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        panel.get_by_label('Проект запроса №1', exact=True).select_option('lnauto')
        panel.get_by_role('button', name='Сохранить проект', exact=True).click()
        expect(panel.get_by_text('Проект сохранён. Выполнение не запускалось.', exact=True)).to_be_visible()
        assert store.snapshot()['halted'] is True
        page.get_by_role('button', name='Снять обычную остановку для новых задач', exact=True).click()
        expect(page.get_by_text('Контур допускает синтетические задачи', exact=True)).to_be_visible()
        assert store.snapshot()['tasks'] == []
