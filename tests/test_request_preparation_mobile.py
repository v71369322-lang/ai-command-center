"""Real Chromium/API/PG stage filtering, old-page navigation and edit readback."""

from uuid import uuid4

from playwright.sync_api import expect
import pytest

from command_center.manual_plan import save
from command_center.request_plan_store import read
from test_manual_plan import request as manual_request, draft
from test_project_inbox import capture
from test_request_preparation import matrix
from test_request_review import configured
from test_telegram_mobile import mobile, login
from test_telegram_task_status import authority


def panel(page):
    page.get_by_text("Стадии подготовки запросов", exact=True).click()
    return page.get_by_role("region", name="Стадии подготовки запросов", exact=True)


@pytest.mark.parametrize("width", [320, 390])
def test_stage_overview_loads_once_on_open_and_manual_edit_moves_request(settings, store, width):
    ids = matrix(store)
    before = authority(store)
    with mobile(settings, width) as (page, _):
        reads = []
        page.on(
            "request",
            lambda req: reads.append(req.url) if "/api/project-inbox/preparation?" in req.url else None,
        )
        login(page)
        assert reads == []
        box = panel(page)
        expect(box.get_by_text("Найдено: 6 из 6. Страница 1/1.", exact=True)).to_be_visible()
        assert len(reads) == 1
        counts = box.get_by_role("list", name="Количество запросов по стадиям")
        expect(counts.get_by_text("Уточнить вопросы: 1", exact=True)).to_be_visible()
        box.get_by_label("Проект в обзоре подготовки", exact=True).select_option("lnauto")
        box.get_by_label("Стадия подготовки", exact=True).select_option("answer_questions")
        expect(box.get_by_role("heading", name="Запрос №5", exact=True)).to_be_visible()
        assert box.get_by_role("heading", name="Запрос №6", exact=True).count() == 0
        box.get_by_text("Подготовка запроса №5", exact=True).click()
        form = box.get_by_role("region", name="Редактор ручного плана", exact=True)
        form.get_by_label("Вопросы к плану (до 5 строк)", exact=True).fill("")
        form.get_by_role("button", name="Предпросмотр ручного плана", exact=True).click()
        expect(form.get_by_role("region", name="Предпросмотр ручного плана", exact=True)).to_be_visible()
        form.get_by_role("button", name="Сохранить ручной план", exact=True).click()
        expect(box.get_by_text("На этой стадии запросов пока нет.", exact=True)).to_be_visible()
        assert read(store, "owner", ids[4])["proposal"]["questions"] == []
        box.get_by_label("Стадия подготовки", exact=True).select_option("verify_scope")
        expect(box.get_by_role("heading", name="Запрос №5", exact=True)).to_be_visible()
        expect(box.get_by_role("heading", name="Запрос №6", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        button = box.get_by_role("button", name="Обновить стадии подготовки", exact=True).bounding_box()
        assert button and button["height"] >= 44
        if width == 390:
            box.screenshot(path=".runtime/request-preparation-mobile.png")
        page.get_by_role("button", name="Выйти", exact=True).click()
        expect(box).to_have_count(0)
    assert authority(store) == before


def test_page_two_opens_an_older_request_and_queue_changes_require_restart(settings, store):
    ids = [capture(store, uid=i) for i in range(1, 13)]
    with mobile(settings) as (page, _):
        login(page)
        box = panel(page)
        expect(box.get_by_text("Найдено: 12 из 12. Страница 1/2.", exact=True)).to_be_visible()
        box.get_by_role("button", name="Следующая страница подготовки", exact=True).click()
        expect(box.get_by_text("Найдено: 12 из 12. Страница 2/2.", exact=True)).to_be_visible()
        box.get_by_text("Подготовка запроса №1", exact=True).click()
        expect(box.get_by_text("Выберите проект для запроса.", exact=True)).to_be_visible()
        capture(store, uid=30)
        box.get_by_role("button", name="Предыдущая страница подготовки", exact=True).click()
        expect(box.get_by_role("alert")).to_be_visible()
        assert box.get_by_role("heading", name="Запрос №1", exact=True).count() == 0
        box.get_by_role("button", name="Обновить стадии подготовки", exact=True).click()
        expect(box.get_by_text("Найдено: 13 из 13. Страница 1/2.", exact=True)).to_be_visible()
    assert len(ids) == 12


@pytest.mark.parametrize("attack", ["authority", "context", "counts", "stage"])
def test_malformed_queue_response_hides_only_this_overview(settings, store, attack):
    matrix(store)
    with mobile(settings) as (page, _):
        login(page)

        def change(route):
            response = route.fetch()
            value = response.json()
            if attack == "authority":
                value["execution_authorized"] = True
            elif attack == "context":
                value["project"] = "capital-lab"
            elif attack == "counts":
                value["stage_counts"]["answer_questions"] = 999
            else:
                value["requests"][0]["stage"] = "select_project"
            route.fulfill(status=200, json=value)

        page.route("**/api/project-inbox/preparation?*", change)
        box = panel(page)
        expect(box.get_by_role("alert")).to_be_visible()
        assert box.get_by_role("heading", name="Запрос №6", exact=True).count() == 0
        assert page.get_by_role("button", name="Обновить очередь проектов", exact=True).is_enabled()
        page.unroute("**/api/project-inbox/preparation?*")
        box.get_by_role("button", name="Обновить стадии подготовки", exact=True).click()
        expect(box.get_by_text("Найдено: 6 из 6. Страница 1/1.", exact=True)).to_be_visible()


def test_logout_aborts_pending_overview_without_showing_late_response(settings, store):
    capture(store)
    with mobile(settings) as (page, _):
        login(page)
        pending = []
        page.route("**/api/project-inbox/preparation?*", lambda route: pending.append(route))
        box = panel(page)
        expect(box.get_by_text("Читаем стадии подготовки…", exact=True)).to_be_visible()
        assert len(pending) == 1
        page.get_by_role("button", name="Выйти", exact=True).click()
        expect(box).to_have_count(0)
        try:
            pending[0].continue_()
        except Exception:
            pass
        assert page.get_by_text("Найдено:", exact=False).count() == 0


def test_existing_queue_and_overview_editors_have_distinct_input_ids(settings, store):
    rid = configured(store)
    save(store, "owner", manual_request(store, rid), str(uuid4()))
    with mobile(settings) as (page, _):
        login(page)
        root = page.get_by_role("region", name="Проекты и запросы", exact=True)
        root.get_by_text("Подготовка запроса №1", exact=True).click()
        box = panel(page)
        box.get_by_text("Подготовка запроса №1", exact=True).click()
        forms = root.get_by_role("region", name="Редактор ручного плана", exact=True)
        expect(forms).to_have_count(2)
        labels = page.get_by_label("Цель ручного плана", exact=True)
        assert labels.count() == 2 and labels.nth(0).get_attribute("id") != labels.nth(1).get_attribute("id")
        box.get_by_label("Цель ручного плана", exact=True).fill("Distinct editor goal")
        assert root.get_by_label("Цель ручного плана", exact=True).nth(1).input_value() == draft()["summary"]
