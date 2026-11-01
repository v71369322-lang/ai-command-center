"""Manual plan authoring through actual Chromium/HTTP/PG, never a provider."""

from uuid import uuid4

from playwright.sync_api import expect
import pytest

from command_center.manual_plan import save
from command_center.project_inbox import classify
from command_center.project_setup import patch
from command_center.request_plan_store import read
from test_manual_plan import configured, request as manual_request, draft, events
from test_request_review_mobile import open_review
from test_telegram_mobile import mobile, login
from test_telegram_task_status import authority


def editor(page):
    _, review = open_review(page)
    return review, review.get_by_role("region", name="Редактор ручного плана", exact=True)


def fill(form, summary="Согласовать форму", questions=""):
    form.get_by_label("Цель ручного плана", exact=True).fill(summary)
    form.get_by_label("Описание шага 1", exact=True).fill("Описать поля формы")
    form.get_by_label("Критерии шага 1 (до 3 строк)", exact=True).fill(
        "Поля перечислены\nКритерий проверки согласован"
    )
    form.get_by_label("Вопросы к плану (до 5 строк)", exact=True).fill(questions)


def preview(form):
    form.get_by_role("button", name="Предпросмотр ручного плана", exact=True).click()
    expect(form.get_by_role("region", name="Предпросмотр ручного плана", exact=True)).to_be_visible()


@pytest.mark.parametrize("width", [320, 390])
def test_mobile_preview_save_edit_and_clear_questions_without_authority(settings, store, width):
    rid = configured(store)
    before = authority(store)
    marker = '<img src=x onerror="window.manualPlanInjected=true">'
    with mobile(settings, width) as (page, _):
        login(page)
        review, form = editor(page)
        expect(form.get_by_role("button", name="Сохранить ручной план", exact=True)).to_be_disabled()
        fill(form, marker, "Нужно ли второе поле?")
        form.get_by_role("button", name="Добавить шаг", exact=True).click()
        form.get_by_label("Описание шага 2", exact=True).fill("Согласовать результат")
        form.get_by_label("Критерии шага 2 (до 3 строк)", exact=True).fill("Результат описан")
        preview(form)
        assert events(store) == []
        form.get_by_role("button", name="Сохранить ручной план", exact=True).click()
        expect(review.get_by_text("Предложение плана, версия 1", exact=True)).to_be_visible()
        expect(review.get_by_text("Автор — владелец.", exact=False)).to_be_visible()
        assert read(store, "owner", rid)["proposal"]["questions"] == ["Нужно ли второе поле?"]
        expect(
            review.get_by_text(
                "Соответствие плана настройкам: версии черновиков совпадают; внешняя проверка ещё нужна.",
                exact=True,
            )
        ).to_be_visible()
        assert review.locator("img").count() == 0 and page.evaluate("window.manualPlanInjected === undefined")
        form = review.get_by_role("region", name="Редактор ручного плана", exact=True)
        form.get_by_label("Цель ручного плана", exact=True).fill("Уточнённая цель")
        form.get_by_label("Вопросы к плану (до 5 строк)", exact=True).fill("")
        form.get_by_role("button", name="Убрать шаг 2", exact=True).click()
        preview(form)
        form.get_by_role("button", name="Сохранить ручной план", exact=True).click()
        expect(review.get_by_text("Предложение плана, версия 2", exact=True)).to_be_visible()
        assert read(store, "owner", rid)["proposal"]["questions"] == []
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        box = review.get_by_role("button", name="Сохранить ручной план", exact=True).bounding_box()
        assert box and box["height"] >= 44
        if width == 390:
            review.screenshot(path=".runtime/manual-plan-mobile.png")
        page.get_by_role("button", name="Выйти", exact=True).click()
        expect(review).to_have_count(0)
    assert authority(store) == before


@pytest.mark.parametrize("change", ["plan", "setup", "assignment"])
def test_stale_save_never_overwrites_newer_conditions_and_requires_readback(settings, store, change):
    rid = configured(store)
    with mobile(settings) as (page, _):
        login(page)
        review, form = editor(page)
        fill(form)
        preview(form)
        if change == "plan":
            save(
                store,
                "owner",
                manual_request(store, rid, {**draft(), "summary": "REMOTE_MANUAL_MARKER"}),
                str(uuid4()),
            )
        elif change == "setup":
            patch(store, "owner", "lnauto", 1, "deployment_target", "updated-stage", str(uuid4()))
        else:
            classify(store, "owner", rid, "capital-lab", 1, str(uuid4()))
        form.get_by_role("button", name="Сохранить ручной план", exact=True).click()
        expect(form.get_by_role("alert")).to_contain_text("Сохранение не подтверждено")
        expect(form.get_by_role("button", name="Сохранить ручной план", exact=True)).to_be_disabled()
        assert len(events(store)) == (1 if change == "plan" else 0)
        form.get_by_role("button", name="Загрузить текущий план", exact=True).click()
        if change == "assignment":
            expect(review.get_by_role("alert")).to_contain_text("Обзор недоступен")
        elif change == "setup":
            expect(review.get_by_text("LNAuto: настройки версии 2", exact=True)).to_be_visible()
        else:
            expect(review.get_by_label("Цель ручного плана", exact=True)).to_have_value(
                "REMOTE_MANUAL_MARKER"
            )


def test_lost_save_response_is_reconciled_without_a_second_post(settings, store):
    rid = configured(store)
    with mobile(settings) as (page, _):
        login(page)
        review, form = editor(page)
        fill(form)
        preview(form)
        posts = []

        def lose(route):
            posts.append(route.request.method)
            assert route.fetch().status == 200
            route.fulfill(status=503, json={"detail": "private lost response fixture"})

        page.route("**/api/project-inbox/plan", lose)
        form.get_by_role("button", name="Сохранить ручной план", exact=True).click()
        expect(form.get_by_role("alert")).to_be_visible()
        assert read(store, "owner", rid)["version"] == 1 and posts == ["POST"]
        assert page.get_by_text("private lost response fixture", exact=False).count() == 0
        form.get_by_role("button", name="Загрузить текущий план", exact=True).click()
        expect(review.get_by_text("Предложение плана, версия 1", exact=True)).to_be_visible()
        assert posts == ["POST"] and len(events(store)) == 1


def test_save_refreshes_checkpoint_without_automatically_resuming_admission(settings, store):
    configured(store)
    store.halt("owner")
    with mobile(settings) as (page, _):
        login(page)
        review, form = editor(page)
        fill(form)
        preview(form)
        form.get_by_role("button", name="Сохранить ручной план", exact=True).click()
        expect(review.get_by_text("Предложение плана, версия 1", exact=True)).to_be_visible()
        assert store.snapshot()["halted"] is True
        page.get_by_role("button", name="Снять обычную остановку для новых задач", exact=True).click()
        expect(page.get_by_text("Контур допускает синтетические задачи", exact=True)).to_be_visible()
        assert store.snapshot()["tasks"] == []


@pytest.mark.parametrize("kind", ["preview", "save"])
def test_logout_aborts_pending_manual_request_and_clears_editor(settings, store, kind):
    configured(store)
    with mobile(settings) as (page, _):
        login(page)
        review, form = editor(page)
        fill(form)
        if kind == "save":
            preview(form)
        path = "**/api/project-inbox/plan" + ("/preview" if kind == "preview" else "")
        pending = []
        page.route(path, lambda route: pending.append(route))
        name = "Предпросмотр ручного плана" if kind == "preview" else "Сохранить ручной план"
        form.get_by_role("button", name=name, exact=True).click()
        expect(form.get_by_role("status")).to_be_visible()
        with page.expect_event("requestfailed", predicate=lambda r: "/project-inbox/plan" in r.url):
            page.get_by_role("button", name="Выйти", exact=True).click()
        assert len(pending) == 1 and events(store) == []
        expect(review).to_have_count(0)


@pytest.mark.parametrize("corruption", ["authority", "context"])
def test_untrusted_preview_response_cannot_enable_save(settings, store, corruption):
    configured(store)
    with mobile(settings) as (page, _):
        login(page)
        _, form = editor(page)
        fill(form)

        def change(route):
            value = route.fetch().json()
            if corruption == "authority":
                value["execution_authorized"] = True
            else:
                value["proposal"]["context_digest"] = "0" * 64
            route.fulfill(status=200, json=value)

        page.route("**/api/project-inbox/plan/preview", change)
        form.get_by_role("button", name="Предпросмотр ручного плана", exact=True).click()
        expect(form.get_by_role("alert")).to_contain_text("Предпросмотр не подтверждён")
        expect(form.get_by_role("button", name="Сохранить ручной план", exact=True)).to_be_disabled()
        expect(form.get_by_label("Цель ручного плана", exact=True)).to_be_enabled()
        assert events(store) == []
