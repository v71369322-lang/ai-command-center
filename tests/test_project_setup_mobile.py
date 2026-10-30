"""Mobile project setup: real HTTP/PG, no external project access or execution."""
from uuid import uuid4

from playwright.sync_api import expect
import pytest

from command_center.project_setup import patch, read
from test_project_inbox import capture
from test_telegram_mobile import mobile, login
from test_telegram_task_status import authority


def open_setup(page):
    panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
    panel.get_by_text('Подключение: LNAuto', exact=True).click()
    form = panel.get_by_role('region', name='Черновик подключения: LNAuto', exact=True)
    expect(form.get_by_text('Версия черновика: 0.', exact=False)).to_be_visible()
    return panel, form


def fill(form, *, acceptance='Public criterion'):
    form.get_by_label('Версия кода (полный SHA коммита)', exact=True).fill('a' * 40)
    form.get_by_label('Тип среды проверки', exact=True).select_option('python_node')
    form.get_by_label('Способ проверки доставки', exact=True).select_option('pipeline_review')
    form.get_by_label('Метка сервера', exact=True).fill('lnauto-staging')
    form.get_by_label('Критерии результата (до 8 строк)', exact=True).fill(acceptance)


@pytest.mark.parametrize('width', [320, 390])
def test_mobile_full_preview_save_inspect_history_restore_and_logout(settings, store, width):
    before = authority(store)
    value = '<img src=x onerror="window.projectSetupInjected=true">'
    with mobile(settings, width) as (page, _):
        login(page)
        panel, form = open_setup(page)
        expect(form.get_by_role('button', name='Сохранить черновик', exact=True)).to_be_disabled()
        fill(form, acceptance=value)
        form.get_by_role('button', name='Проверить черновик', exact=True).click()
        expect(form.get_by_role('region', name='Предпросмотр черновика', exact=True)).to_contain_text('заполнено 5 из 5')
        assert read(store, 'owner', 'lnauto')['version'] == 0
        form.get_by_role('button', name='Сохранить черновик', exact=True).click()
        expect(form.get_by_text('Черновик сохранён. Подключения и выполнение не включены.', exact=True)).to_be_visible()
        assert read(store, 'owner', 'lnauto')['version'] == 1
        expect(panel.get_by_role('region', name='Подготовка подключений', exact=True)).to_contain_text('LNAuto: черновик 1, заполнено 5 из 5.')
        assert form.locator('img').count() == 0 and page.evaluate('window.projectSetupInjected === undefined')
        form.get_by_role('button', name='Версия 0', exact=True).click()
        expect(form.get_by_label('Метка сервера', exact=True)).to_be_disabled()
        form.get_by_role('button', name='Восстановить версию 0 как новый черновик', exact=True).click()
        expect(form.get_by_text('Версия черновика: 2.', exact=False)).to_be_visible()
        assert read(store, 'owner', 'lnauto')['draft']['acceptance'] == []
        form.get_by_role('button', name='Версия 1', exact=True).click()
        form.get_by_role('button', name='Восстановить версию 1 как новый черновик', exact=True).click()
        expect(form.get_by_text('Версия черновика: 3.', exact=False)).to_be_visible()
        expect(form.get_by_label('Критерии результата (до 8 строк)', exact=True)).to_have_value(value)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        box = form.get_by_role('button', name='Проверить черновик', exact=True).bounding_box()
        assert box and box['height'] >= 44
        if width == 390:
            form.screenshot(path='.runtime/project-setup-mobile.png')
        page.get_by_role('button', name='Выйти', exact=True).click()
        expect(form).to_have_count(0)
        assert authority(store) == before


def test_preview_failure_allows_editing_but_a_stale_save_requires_reload(settings, store):
    with mobile(settings) as (page, _):
        login(page)
        _, form = open_setup(page)
        fill(form)
        patch(store, 'owner', 'lnauto', 0, 'deployment_target', 'other-staging', str(uuid4()))
        form.get_by_role('button', name='Проверить черновик', exact=True).click()
        expect(form.get_by_role('alert')).to_contain_text('Предпросмотр не подтверждён')
        expect(form.get_by_label('Метка сервера', exact=True)).to_be_enabled()
        expect(form.get_by_role('button', name='Сохранить черновик', exact=True)).to_be_disabled()
        form.get_by_role('button', name='Загрузить сохранённый черновик', exact=True).click()
        expect(form.get_by_text('Версия черновика: 1.', exact=False)).to_be_visible()
        fill(form)
        form.get_by_role('button', name='Проверить черновик', exact=True).click()
        expect(form.get_by_role('region', name='Предпросмотр черновика', exact=True)).to_be_visible()
        patch(store, 'owner', 'lnauto', 1, 'deployment_target', 'newest-staging', str(uuid4()))
        form.get_by_role('button', name='Сохранить черновик', exact=True).click()
        expect(form.get_by_role('alert')).to_contain_text('Сохранение не подтверждено')
        expect(form.get_by_role('button', name='Сохранить черновик', exact=True)).to_be_disabled()
        assert read(store, 'owner', 'lnauto')['draft']['deployment_target'] == 'newest-staging'
        form.get_by_role('button', name='Загрузить сохранённый черновик', exact=True).click()
        expect(form.get_by_label('Метка сервера', exact=True)).to_have_value('newest-staging')


def test_lost_save_response_is_reconciled_by_read_without_second_write(settings, store):
    with mobile(settings) as (page, _):
        login(page)
        _, form = open_setup(page)
        fill(form)
        form.get_by_role('button', name='Проверить черновик', exact=True).click()
        expect(form.get_by_role('button', name='Сохранить черновик', exact=True)).to_be_enabled()
        calls = []
        path = '**/api/projects/lnauto/setup'
        def lost(route):
            if route.request.method == 'POST':
                calls.append('POST')
                assert route.fetch().status == 200
                route.fulfill(status=503, json={'detail': 'private response lost fixture'})
            else:
                route.continue_()
        page.route(path, lost)
        form.get_by_role('button', name='Сохранить черновик', exact=True).click()
        expect(form.get_by_role('alert')).to_contain_text('Сохранение не подтверждено')
        assert read(store, 'owner', 'lnauto')['version'] == 1 and calls == ['POST']
        assert page.get_by_text('private response lost fixture', exact=False).count() == 0
        page.unroute(path)
        form.get_by_role('button', name='Загрузить сохранённый черновик', exact=True).click()
        expect(form.get_by_text('Версия черновика: 1.', exact=False)).to_be_visible()
        assert calls == ['POST']


@pytest.mark.parametrize('corruption', ['connected', 'ready', 'project', 'enum_array'])
def test_malformed_setup_hides_editor_but_not_assignment(settings, store, corruption):
    capture(store)
    data = read(store, 'owner', 'lnauto')
    if corruption == 'connected':
        data['execution_connected'] = True
    elif corruption == 'ready':
        data['review']['execution_ready'] = True
    elif corruption == 'project':
        data['project_id'] = 'capital-lab'
    else:
        data['draft']['verification_kind'] = ['python']
    with mobile(settings) as (page, _):
        page.route('**/api/projects/lnauto/setup', lambda route: route.fulfill(status=200, json=data))
        login(page)
        panel = page.get_by_role('region', name='Проекты и запросы', exact=True)
        panel.get_by_text('Подключение: LNAuto', exact=True).click()
        form = panel.get_by_role('region', name='Черновик подключения: LNAuto', exact=True)
        expect(form.get_by_role('alert')).to_be_visible()
        assert form.get_by_label('Метка сервера', exact=True).count() == 0
        panel.get_by_label('Проект запроса №1', exact=True).select_option('lnauto')
        panel.get_by_role('button', name='Сохранить проект', exact=True).click()
        expect(panel.get_by_text('Проект сохранён. Выполнение не запускалось.', exact=True)).to_be_visible()
        assert store.snapshot()['tasks'] == []
