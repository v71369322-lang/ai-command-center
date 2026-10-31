"""A real PG batch queue agrees with individual reviews without granting work."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

from command_center.coding.integration_config import FileCredentials, IntegrationConfig
from command_center.manual_plan import save
from command_center.project_inbox import classify
from command_center.project_setup import patch, save as setup_save
from command_center.request_preparation import read, STAGES
from command_center.request_review import read as review
from command_center.store import Denied, Store
from test_manual_plan import request, draft
from test_project_inbox import capture
from test_project_setup import full
from test_request_planning import state
from test_telegram_task_status import authority


def matrix(store):
    ids = [capture(store, uid=i) for i in range(1, 7)]
    classify(store, "owner", ids[1], "vanilla-sugar", 0, str(uuid4()))
    for rid in ids[2:]:
        classify(store, "owner", rid, "lnauto", 0, str(uuid4()))
    setup_save(store, "owner", "lnauto", 0, full(), str(uuid4()))
    save(store, "owner", request(store, ids[3]), str(uuid4()))
    patch(store, "owner", "lnauto", 1, "acceptance", ["Updated public criterion"], str(uuid4()))
    save(store, "owner", request(store, ids[4], {**draft(), "questions": ["Which field?"]}), str(uuid4()))
    save(store, "owner", request(store, ids[5]), str(uuid4()))
    return ids


def test_all_stages_match_individual_reviews_and_remain_read_only(store, client, headers):
    ids = matrix(store)
    before = state(store), authority(store)
    response = client.get("/api/project-inbox/preparation", headers=headers["owner"])
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    value = response.json()
    assert (
        value["scope"] == "PREPARATION_QUEUE_ONLY" and value["total_pending"] == value["total_matching"] == 6
    )
    assert value["stage_counts"] == dict.fromkeys(STAGES, 1)
    assert value["project_counts"] == {
        "unassigned": 1,
        "command-center": 0,
        "vanilla-sugar": 1,
        "lnauto": 4,
        "capital-lab": 0,
    }
    for row in value["requests"]:
        assert row["stage"] == review(store, "owner", row["id"])["next_step"]
        assert row["plan_state"] == review(store, "owner", row["id"])["plan"]["state"]
    assert {r["id"] for r in value["requests"]} == set(ids)
    assert all(
        value[k] is False
        for k in (
            "execution_ready",
            "execution_authorized",
            "external_checks_performed",
            "provider_called",
            "task_created",
        )
    )
    assert value["actions_enabled"] == []
    assert read(store, "owner")["snapshot_digest"] == value["snapshot_digest"]
    assert (state(store), authority(store)) == before


def test_project_and_stage_filters_keep_counts_and_hide_unrelated_rows(store):
    matrix(store)
    result = read(store, "owner", project="lnauto", stage="answer_questions")
    assert result["total_matching"] == 1 and result["total_pending"] == 6
    assert len(result["requests"]) == 1 and result["requests"][0]["stage"] == "answer_questions"
    assert sum(result["stage_counts"].values()) == 4
    assert read(store, "owner", project="capital-lab")["requests"] == []
    assert read(store, "owner", project="unassigned")["stage_counts"]["select_project"] == 1


def test_stable_pagination_reaches_older_requests_without_duplicates(store):
    ids = {capture(store, uid=i) for i in range(1, 26)}
    first = read(store, "owner")
    assert first["pages"] == 3 and len(first["requests"]) == 10
    pages = [
        first,
        read(store, "owner", page=2, snapshot=first["snapshot_digest"]),
        read(store, "owner", page=3, snapshot=first["snapshot_digest"]),
    ]
    combined = [r["id"] for p in pages for r in p["requests"]]
    assert len(combined) == len(set(combined)) == 25 and set(combined) == ids
    assert len(pages[-1]["requests"]) == 5
    with pytest.raises(Denied, match="page_missing"):
        read(store, "owner", page=4)


@pytest.mark.parametrize("change", ["capture", "setup", "plan", "assignment", "halt", "source"])
def test_next_page_requires_the_same_snapshot_after_a_change(store, change):
    ids = matrix(store)
    before = read(store, "owner")["snapshot_digest"]
    reader = store
    if change == "capture":
        capture(store, uid=20)
    elif change == "setup":
        patch(store, "owner", "lnauto", 2, "acceptance", ["Another criterion"], str(uuid4()))
    elif change == "plan":
        save(store, "owner", request(store, ids[5]), str(uuid4()))
    elif change == "assignment":
        classify(store, "owner", ids[0], "capital-lab", 0, str(uuid4()))
    elif change == "halt":
        store.halt("owner")
    else:
        reader = Store(replace(store.settings, source_revision="b" * 40))
    try:
        with pytest.raises(Denied, match="queue_changed"):
            read(reader, "owner", snapshot=before)
        assert read(reader, "owner")["snapshot_digest"] != before
    finally:
        if reader is not store:
            reader.engine.dispose()


def test_database_query_count_is_bounded_independently_of_queue_length(store):
    statements = []

    def observed(*args):
        statements.append(args[2])

    def count():
        statements.clear()
        event.listen(store.engine, "before_cursor_execute", observed)
        try:
            read(store, "owner")
        finally:
            event.remove(store.engine, "before_cursor_execute", observed)
        return len(statements)

    capture(store)
    one = count()
    for uid in range(2, 24):
        capture(store, uid=uid)
    many = count()
    assert many == one and many <= 12


def test_queue_never_loads_provider_or_credentials_and_does_not_change_control(store, monkeypatch):
    matrix(store)
    before = state(store)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: pytest.fail("no HTTP"))
    monkeypatch.setattr(FileCredentials, "get", lambda *a: pytest.fail("no credentials"))
    monkeypatch.setattr(IntegrationConfig, "load", lambda *a: pytest.fail("no integration config"))
    read(store, "owner")
    assert state(store) == before


@pytest.mark.parametrize("role,status", [("anonymous", 401), ("operator", 409), ("agent", 409)])
def test_api_is_owner_only(client, headers, role, status):
    assert client.get("/api/project-inbox/preparation", headers=headers.get(role, {})).status_code == status


@pytest.mark.parametrize(
    "query", ["project=unknown", "stage=ready_to_execute", "page=0", "page=101", "snapshot=bad", "page=true"]
)
def test_bad_query_is_safe_and_never_echoed(client, headers, query):
    result = client.get("/api/project-inbox/preparation?" + query, headers=headers["owner"])
    assert result.status_code == 422 and result.json() == {"detail": "invalid_request"}


@pytest.mark.parametrize("damage", ["capture", "setup", "plan"])
def test_broken_history_never_returns_a_partial_or_empty_ready_queue(store, admin, damage):
    ids = matrix(store)
    if damage == "capture":
        with admin.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE telegram_inbox SET intent=jsonb_build_object('kind','capture','text','Changed') WHERE id=:id"
                ),
                {"id": ids[0]},
            )
    else:
        with store.transaction() as session:
            store.audit(
                session,
                "project_setup_draft_changed" if damage == "setup" else "saved_request_plan_draft",
                "owner",
            )
    with pytest.raises(Denied):
        read(store, "owner", project="lnauto", stage="verify_scope")


def test_known_credential_rotation_blocks_even_filtered_out_content(store):
    marker = "PUBLIC_PREPARATION_MARKER_NOW_A_KNOWN_SYNTHETIC_CREDENTIAL"
    capture(store, value=marker)
    other = Store(replace(store.settings, identities={**store.settings.identities, "agent": marker}))
    try:
        with pytest.raises(Denied, match="sensitive_content"):
            read(other, "owner", project="lnauto")
    finally:
        other.engine.dispose()


def test_capacity_is_fail_closed(store, monkeypatch):
    import command_center.request_preparation as module

    monkeypatch.setattr(module, "MAX_REQUESTS", 2)
    for uid in range(1, 4):
        capture(store, uid=uid)
    with pytest.raises(Denied, match="capacity"):
        read(store, "owner")


def test_batch_holds_the_same_control_lock_through_validation(store, admin, monkeypatch):
    import command_center.request_preparation as module

    capture(store)
    ready, release = Event(), Event()
    original = module._records

    def held(*args):
        result = original(*args)
        ready.set()
        if not release.wait(2):
            raise RuntimeError("public release timeout")
        return result

    monkeypatch.setattr(module, "_records", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(read, store, "owner")
        try:
            assert ready.wait(2)
            with pytest.raises(OperationalError) as error:
                with admin.engine.begin() as c:
                    c.execute(text("SELECT id FROM control WHERE id=1 FOR UPDATE NOWAIT"))
            assert error.value.orig.sqlstate == "55P03"
        finally:
            release.set()
        assert pending.result()["total_pending"] == 1


def test_tie_order_is_deterministic(store, admin):
    ids = [capture(store, uid=i) for i in range(1, 13)]
    with admin.engine.begin() as c:
        c.execute(text("UPDATE telegram_inbox SET created_at='2026-10-31T00:00:00Z'"))
    first = read(store, "owner")
    second = read(store, "owner", page=2, snapshot=first["snapshot_digest"])
    assert [r["id"] for r in first["requests"] + second["requests"]] == sorted(ids, reverse=True)


def test_batch_uses_earliest_matching_receive_anchor_like_individual_context(store):
    from command_center.request_planning import context
    from command_center.models import TelegramInbox

    rid = matrix(store)[5]
    before = context(store, "owner", rid)
    with store.transaction() as session:
        row = session.get(TelegramInbox, rid)
        store.audit(
            session,
            "telegram_update_received",
            "owner",
            profile=row.profile,
            update_id=rid.rsplit(":", 1)[1],
            intent_hash=row.fingerprint,
            revision="b" * 40,
        )
    assert context(store, "owner", rid) == before
    row = next(r for r in read(store, "owner")["requests"] if r["id"] == rid)
    assert row["plan_state"] == "CURRENT" and row["stage"] == "verify_scope"


def test_sensitive_manual_plan_blocks_the_batch_even_outside_selected_stage(store):
    marker = "PUBLIC_QUEUE_PLAN_MARKER_NOW_A_KNOWN_SYNTHETIC_CREDENTIAL"
    rid = matrix(store)[5]
    save(store, "owner", request(store, rid, {**draft(), "summary": marker}), str(uuid4()))
    changed = Store(replace(store.settings, identities={**store.settings.identities, "agent": marker}))
    try:
        with pytest.raises(Denied, match="sensitive_content"):
            read(changed, "owner", stage="select_project")
    finally:
        changed.engine.dispose()


def test_escaped_response_bytes_are_bounded_without_partial_pages(store):
    for uid in range(1, 11):
        capture(store, uid=uid, value="\x01" * 1200)
    with pytest.raises(Denied, match="queue_size"):
        read(store, "owner")
