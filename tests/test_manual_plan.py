"""Owner-authored drafts share real PG/audit history; they never emulate an AI bill."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4, uuid5, NAMESPACE_URL

from fastapi.testclient import TestClient
import httpx
import pytest

from command_center.api import create_app
from command_center.coding.integration_config import FileCredentials, IntegrationConfig
from command_center.manual_plan import references, preview, save
from command_center.project_inbox import classify
from command_center.project_setup import patch
from command_center.request_plan_store import EVENT, ManualRequest, read
from command_center.request_planning import context
from command_center.request_review import read as review
from command_center.store import Denied, Store
from test_project_inbox import capture
from test_request_plan_store import persist, events
from test_request_planning import response, state
from test_request_review import configured
from test_telegram_task_status import authority
from test_telegram_readiness import ledger
from test_owner_password import password_config as password_config, login


def draft():
    return {
        "summary": "Согласовать поля формы",
        "steps": [
            {
                "description": "Описать изменение",
                "acceptance": ["Поля перечислены", "Проверка результата описана"],
            }
        ],
        "questions": [],
    }


def request(store, rid, value=None):
    with store.transaction() as session:
        store.check_audit(session)
        _, _, _, ref = references(store, session, rid)
    return ManualRequest(**ref, draft=value or draft())


def test_preview_save_edit_shared_review_history_and_restart_without_authority(
    store, client, headers, settings
):
    rid = configured(store)
    body = request(store, rid)
    before = authority(store), ledger(store)
    p = client.post("/api/project-inbox/plan/preview", headers=headers["owner"], json=body.model_dump())
    assert p.status_code == 200 and p.json()["stored"] is False and events(store) == []
    operation = str(uuid4())
    value = client.post(
        "/api/project-inbox/plan",
        headers=headers["owner"],
        json={**body.model_dump(), "operation_id": operation},
    ).json()
    assert value["version"] == 1 and value["origin"] == "owner_authored" and value["provider_called"] is False
    record = events(store)[0].event["document"]
    assert record["schema_version"] == 2 and not {"model", "response_id", "usage"} & set(record)
    assert save(store, "owner", body, operation) == value and len(events(store)) == 1
    current = read(store, "owner", rid)
    assert current["state"] == current["setup_reference_state"] == "CURRENT"
    assert current["origin"] == "owner_authored" and current["provider_evidence_verified"] is False
    view = review(store, "owner", rid)
    assert view["checks"][3]["state"] == "DECLARED_MATCH" and view["execution_ready"] is False
    assert view["plan"]["setup_binding_verified"] is False
    second = request(
        store, rid, {**draft(), "summary": "Обновлённая цель", "questions": ["Какое поле обязательно?"]}
    )
    save(store, "owner", second, str(uuid4()))
    assert read(store, "owner", rid, version=1)["proposal"]["summary"] == draft()["summary"]
    assert review(store, "owner", rid)["plan"]["state"] == "NEEDS_CLARIFICATION"
    restarted = Store(settings)
    try:
        assert read(restarted, "owner", rid)["version"] == 2
    finally:
        restarted.engine.dispose()
    assert (authority(store), ledger(store)) == before


def test_legacy_provider_manual_and_new_provider_drafts_share_versions_without_promoting_origin(store):
    rid = configured(store)
    snapshot = context(store, "owner", rid)
    persist(store, snapshot)
    old = deepcopy(events(store)[0].event)
    value = request(store, rid)
    assert save(store, "owner", value, str(uuid4()))["version"] == 2
    data = response(snapshot)
    data["id"] += "_new"
    assert persist(store, snapshot, data)["version"] == 3
    assert events(store)[0].event == old
    assert read(store, "owner", rid, version=2)["origin"] == "owner_authored"
    assert read(store, "owner", rid)["origin"] == "owner_supplied_unverified"
    assert review(store, "owner", rid)["checks"][3]["state"] == "NOT_CHECKED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_context_digest", "0" * 64),
        ("expected_assignment_version", 2),
        ("expected_setup_version", 0),
        ("expected_setup_digest", "0" * 64),
        ("expected_plan_version", 1),
    ],
)
def test_stale_reference_fields_cannot_save_or_preview(store, field, value):
    rid = configured(store)
    original = request(store, rid)
    changed = ManualRequest.model_validate({**original.model_dump(), field: value})
    before = state(store)
    for action in [
        lambda: preview(store, "owner", changed),
        lambda: save(store, "owner", changed, str(uuid4())),
    ]:
        with pytest.raises(Denied, match="context_changed"):
            action()
    assert state(store) == before


@pytest.mark.parametrize("change", ["setup", "assignment", "halt", "source"])
def test_saved_manual_plan_becomes_stale_when_bound_conditions_change(store, change):
    rid = configured(store)
    body = request(store, rid)
    save(store, "owner", body, str(uuid4()))
    reader = store
    if change == "setup":
        patch(store, "owner", "lnauto", 1, "deployment_target", "other-stage", str(uuid4()))
    elif change == "assignment":
        classify(store, "owner", rid, "capital-lab", 1, str(uuid4()))
    elif change == "halt":
        store.halt("owner")
    else:
        reader = Store(replace(store.settings, source_revision="b" * 40))
    try:
        current = read(reader, "owner", rid)
        assert current["state"] == current["setup_reference_state"] == "STALE" and current["proposal"] is None
        with pytest.raises(Denied, match="context_changed"):
            save(reader, "owner", body, str(uuid4()))
    finally:
        if reader is not store:
            reader.engine.dispose()


def test_parallel_writers_have_one_winner_and_reused_operation_cannot_change_content_or_request(store):
    rid = configured(store)
    body = request(store, rid)

    def write(_):
        try:
            return save(store, "owner", body, str(uuid4()))
        except Denied as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(write, range(2)))
    assert sum(isinstance(v, dict) for v in values) == 1 and len(events(store)) == 1
    operation = events(store)[0].event["document"]["operation_id"]
    with pytest.raises(Denied, match="idempotency_conflict"):
        save(
            store,
            "owner",
            ManualRequest.model_validate({**body.model_dump(), "draft": {**draft(), "summary": "Changed"}}),
            operation,
        )
    other = capture(store, uid=2)
    classify(store, "owner", other, "lnauto", 0, str(uuid4()))
    with pytest.raises(Denied, match="idempotency_conflict"):
        save(store, "owner", request(store, other), operation)


def test_manual_save_has_no_provider_io_and_hook_failure_rolls_back(store, monkeypatch):
    rid = configured(store)
    body = request(store, rid)
    operation = str(uuid4())
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: pytest.fail("no provider client"))
    monkeypatch.setattr(FileCredentials, "get", lambda *a: pytest.fail("no credentials"))
    monkeypatch.setattr(IntegrationConfig, "load", lambda *a: pytest.fail("no profile"))
    before = state(store)

    def reject(*args):
        raise RuntimeError("public atomic hook fixture")

    with pytest.raises(RuntimeError):
        save(store, "owner", body, operation, _scope_installer=reject)
    assert state(store) == before
    save(store, "owner", body, operation)
    assert len(events(store)) == 1


@pytest.mark.parametrize("role,status", [("anonymous", 401), ("operator", 409), ("agent", 409)])
def test_manual_routes_require_owner(client, store, headers, role, status):
    body = request(store, configured(store)).model_dump()
    supplied = headers.get(role, {})
    assert client.post("/api/project-inbox/plan/preview", headers=supplied, json=body).status_code == status
    assert (
        client.post(
            "/api/project-inbox/plan", headers=supplied, json={**body, "operation_id": str(uuid4())}
        ).status_code
        == status
    )


@pytest.mark.parametrize(
    "attack",
    [
        "origin",
        "model",
        "usage",
        "execution_authorized",
        "empty_steps",
        "empty_acceptance",
        "questions",
        "boolean_version",
        "v5",
    ],
)
def test_invalid_and_authority_expanding_inputs_are_rejected_without_echo(client, store, headers, attack):
    body = {**request(store, configured(store)).model_dump(), "operation_id": str(uuid4())}
    if attack in {"origin", "model", "usage", "execution_authorized"}:
        body[attack] = "UNTRUSTED_INPUT_MARKER"
    elif attack == "empty_steps":
        body["draft"]["steps"] = []
    elif attack == "empty_acceptance":
        body["draft"]["steps"][0]["acceptance"] = []
    elif attack == "questions":
        body["draft"]["questions"] = ["x"] * 6
    elif attack == "boolean_version":
        body["expected_plan_version"] = False
    else:
        body["operation_id"] = str(uuid5(NAMESPACE_URL, "public fixture"))
    result = client.post("/api/project-inbox/plan", headers=headers["owner"], json=body)
    assert (
        result.status_code == 422 and result.json() == {"detail": "invalid_request"} and events(store) == []
    )


@pytest.mark.parametrize("field", ["summary", "description", "acceptance", "questions"])
def test_sensitive_plan_text_is_rejected_before_persistence(client, store, headers, field):
    body = {**request(store, configured(store)).model_dump(), "operation_id": str(uuid4())}
    marker = "-----BEGIN PRIVATE KEY----- public rejected fixture"
    if field == "summary":
        body["draft"]["summary"] = marker
    elif field == "description":
        body["draft"]["steps"][0]["description"] = marker
    elif field == "acceptance":
        body["draft"]["steps"][0]["acceptance"] = [marker]
    else:
        body["draft"]["questions"] = [marker]
    result = client.post("/api/project-inbox/plan", headers=headers["owner"], json=body)
    assert result.status_code == 409 and "BEGIN" not in result.text and events(store) == []


def test_generic_state_redacts_manual_and_provider_content_for_both_human_roles(store, client, headers):
    rid = configured(store)
    persist(store, context(store, "owner", rid))
    save(store, "owner", request(store, rid), str(uuid4()))
    for role in ["owner", "operator"]:
        values = [
            v["event"]
            for v in client.get("/api/state", headers=headers[role]).json()["events"]
            if v["event"]["kind"] == EVENT
        ]
        assert values == [{"kind": EVENT, "details_redacted": True}] * 2
    assert draft()["summary"] in str(store.snapshot()["events"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_digest", "0" * 64),
        ("origin", "verified_provider"),
        ("usage", {}),
        ("schema_version", 2.0),
        ("provider_evidence_verified", True),
        ("context_digest", "0" * 64),
    ],
)
def test_valid_audit_chain_with_malformed_manual_record_is_not_read(store, field, value):
    rid = configured(store)
    save(store, "owner", request(store, rid), str(uuid4()))
    original = deepcopy(events(store)[0].event["document"])
    from command_center.request_plan_store import identity, manual_input, ManualDocument
    from command_center.store import digest

    original["operation_id"] = str(uuid4())
    original["input_digest"] = digest(request(store, rid).model_dump())
    assert digest(manual_input(ManualDocument.model_validate(original), 2)) == original["input_digest"]
    pid = identity(original)
    original[field] = value

    with store.transaction() as session:
        store.audit(
            session,
            EVENT,
            "owner",
            request_id=rid,
            proposal_id=pid,
            version=2,
            document=original,
            document_digest=digest(original),
        )
    with pytest.raises(Denied, match="integrity"):
        read(store, "owner", rid)


def test_password_csrf_origin_and_revocation_apply_to_plan_writes(store, password_config):
    body = request(store, configured(store)).model_dump()
    with TestClient(create_app(password_config), base_url="https://testserver") as client:
        csrf = login(client).json()["csrf_token"]
        assert client.post("/api/project-inbox/plan/preview", json=body).status_code == 403
        bad = {"Origin": "https://evil.invalid", "X-CSRF-Token": csrf}
        assert client.post("/api/project-inbox/plan/preview", json=body, headers=bad).status_code == 403
        good = {"Origin": "https://testserver", "X-CSRF-Token": csrf}
        assert client.post("/api/project-inbox/plan/preview", json=body, headers=good).status_code == 200
        assert client.post("/api/auth/revoke-all", headers=good).status_code == 200
        assert (
            client.post(
                "/api/project-inbox/plan", headers=good, json={**body, "operation_id": str(uuid4())}
            ).status_code
            == 401
        )


def test_shared_capacity_keeps_duplicate_receipts_but_blocks_new_manual_and_provider_versions(
    store, monkeypatch
):
    import command_center.manual_plan as writer
    import command_center.request_plan_store as history

    monkeypatch.setattr(writer, "MAX_PROPOSALS", 1)
    monkeypatch.setattr(history, "MAX_PROPOSALS", 1)
    rid = configured(store)
    body = request(store, rid)
    operation = str(uuid4())
    first = save(store, "owner", body, operation)
    assert save(store, "owner", body, operation) == first
    next_body = request(store, rid)
    for action in [
        lambda: preview(store, "owner", next_body),
        lambda: save(store, "owner", next_body, str(uuid4())),
        lambda: persist(store, context(store, "owner", rid)),
    ]:
        with pytest.raises(Denied, match="capacity"):
            action()
    assert len(events(store)) == 1


def test_manual_drafts_are_screened_again_when_known_credentials_change(store):
    marker = "PUBLIC_MANUAL_PLAN_MARKER_NOW_A_SYNTHETIC_KNOWN_CREDENTIAL"
    rid = configured(store)
    body = request(store, rid, {**draft(), "summary": marker})
    save(store, "owner", body, str(uuid4()))
    changed = Store(replace(store.settings, identities={**store.settings.identities, "agent": marker}))
    try:
        with pytest.raises(Denied, match="sensitive_content"):
            read(changed, "owner", rid)
        with pytest.raises(Denied, match="sensitive_content"):
            review(changed, "owner", rid)
    finally:
        changed.engine.dispose()


def test_oversized_unicode_plan_cannot_preview_or_persist(store):
    rid = configured(store)
    value = {
        "summary": "🚀" * 300,
        "steps": [{"description": "🚀" * 300, "acceptance": ["🚀" * 300] * 3}] * 8,
        "questions": [],
    }
    body = request(store, rid, value)
    for action in [lambda: preview(store, "owner", body), lambda: save(store, "owner", body, str(uuid4()))]:
        with pytest.raises(Denied, match="size"):
            action()
    assert events(store) == []


def test_unassigned_request_requires_project_selection_before_a_manual_plan(store):
    rid = capture(store)
    before = state(store)
    with pytest.raises(Denied, match="project_required"):
        request(store, rid)
    assert state(store) == before


@pytest.mark.parametrize("attack", ["extra_permission", "naive_time", "task", "actor"])
def test_manual_record_envelope_with_valid_chain_must_remain_metadata_only(store, attack):
    from command_center.request_plan_store import identity
    from command_center.store import digest

    rid = configured(store)
    save(store, "owner", request(store, rid), str(uuid4()))
    raw = deepcopy(events(store)[0].event["document"])
    raw["operation_id"] = str(uuid4())
    raw["input_digest"] = digest(request(store, rid).model_dump())
    kwargs = {
        "request_id": rid,
        "proposal_id": identity(raw),
        "version": 2,
        "document": raw,
        "document_digest": digest(raw),
    }
    if attack == "extra_permission":
        kwargs["execution_authorized"] = True
    elif attack == "naive_time":
        kwargs["time"] = "2026-10-31T07:00:00"
    with store.transaction() as session:
        store.audit(
            session,
            EVENT,
            "operator" if attack == "actor" else "owner",
            task="1" * 32 if attack == "task" else None,
            **kwargs,
        )
    with pytest.raises(Denied, match="integrity"):
        read(store, "owner", rid)


def test_manual_setup_reference_must_exist_in_protected_history(store):
    from command_center.request_plan_store import identity, ManualDocument, manual_input
    from command_center.store import digest

    rid = configured(store)
    save(store, "owner", request(store, rid), str(uuid4()))
    raw = deepcopy(events(store)[0].event["document"])
    raw["operation_id"] = str(uuid4())
    raw["setup_digest"] = "0" * 64
    raw["input_digest"] = digest(manual_input(ManualDocument.model_validate(raw), 2))
    with store.transaction() as session:
        store.audit(
            session,
            EVENT,
            "owner",
            request_id=rid,
            proposal_id=identity(raw),
            version=2,
            document=raw,
            document_digest=digest(raw),
        )
    with pytest.raises(Denied, match="integrity"):
        read(store, "owner", rid)
