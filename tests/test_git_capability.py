"""Strict discovery parser and real F1/PG transport; no live GitHub or credentials."""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from command_center.coding.contract import CodingRequest, payload
from command_center.coding.first_experiment import EXPERIMENT_ID, validate_repository
from command_center.coding.gateway import Gateway, Uncertain
from command_center.coding.git_capability import CONTENT_TYPE, advertisement, discovery_path
from command_center.coding.remote_publication import RemotePublisher
from command_center.coding.spec import BASE_SHA
from command_center.models import ExternalAction
from command_center.store import Denied
from f2_http_support import FakeHTTP, Credentials, git_advertisement
from test_first_experiment import experiment_config

REPO = "fixture/acc-f2-synthetic-test"


def test_complete_pkt_stream_produces_only_a_bound_projection():
    result = advertisement(git_advertisement(), CONTENT_TYPE, REPO)
    assert result["main_sha"] == BASE_SHA and result["refs_count"] == 1
    assert set(result) == {
        "schema",
        "repository",
        "service",
        "main_sha",
        "refs_count",
        "advertisement_sha256",
    }
    metadata = {
        "id": 1,
        "full_name": REPO,
        "archived": False,
        "disabled": False,
        "permissions": {"admin": False, "push": False},
    }
    branch = {"name": "main", "protected": True, "commit": {"sha": BASE_SHA}}
    with pytest.raises(Denied):
        validate_repository(metadata, branch, REPO, 1)
    validate_repository(metadata, branch, REPO, 1, git_discovery=result)
    metadata["permissions"].pop("push")
    validate_repository(metadata, branch, REPO, 1, git_discovery=result)


@pytest.mark.parametrize(
    "case",
    [
        "html",
        "content_type",
        "truncated",
        "extra_bytes",
        "wrong_service",
        "wrong_size",
        "delimiter",
        "missing_flush",
        "no_main",
        "duplicate_ref",
        "nul",
        "oversize",
        "bad_sha", "caps_newline", "caps_control",
    ],
)
def test_malformed_or_unbounded_discovery_is_rejected(case):
    data, typ = git_advertisement(), CONTENT_TYPE
    if case == "html":
        data = b"<html>ok</html>"
    if case == "content_type":
        typ = "text/plain"
    if case == "truncated":
        data = data[:-2]
    if case == "extra_bytes":
        data += b"0000"
    if case == "wrong_service":
        data = data.replace(b"git-receive-pack", b"git-upload-pack")
    if case == "wrong_size":
        data = b"ffff" + data[4:]
    if case == "delimiter":
        data = data[:31] + b"0001" + data[35:]
    if case == "missing_flush":
        data = data.replace(b"0000", b"0001", 1)
    if case == "no_main":
        data = data.replace(b"refs/heads/main", b"refs/heads/else")
    if case == "duplicate_ref":
        extra = BASE_SHA.encode() + b" refs/heads/main\n"
        data = data[:-4] + ("%04x" % (len(extra) + 4)).encode() + extra + b"0000"
    if case == "nul":
        data = data.replace(b"report-status", b"report\0status")
    if case == "oversize":
        data += b"x" * 65536
    if case == "bad_sha":
        data = data.replace(BASE_SHA.encode(), b"x" * 40)
    if case in {"caps_newline", "caps_control"}:
        start = data.index(BASE_SHA.encode()) - 4
        caps = b"report-status\n\n" if case == "caps_newline" else b"report-status\x01\n"
        record = BASE_SHA.encode() + b" refs/heads/main\0" + caps
        data = data[:start] + ("%04x" % (len(record) + 4)).encode() + record + b"0000"
    with pytest.raises(Denied, match="advertisement_invalid"):
        advertisement(data, typ, REPO)


@pytest.mark.parametrize(
    "change",
    [
        "id",
        "admin",
        "archived",
        "disabled",
        "name",
        "protection",
        "baseline",
        "proof_repo",
        "proof_base",
        "proof_schema",
        "proof_count",
        "proof_hash",
    ],
)
def test_git_discovery_cannot_override_identity_protection_or_typed_binding(change):
    metadata = {
        "id": 1,
        "full_name": REPO,
        "archived": False,
        "disabled": False,
        "permissions": {"admin": False, "push": False},
    }
    branch = {"name": "main", "protected": True, "commit": {"sha": BASE_SHA}}
    proof = advertisement(git_advertisement(), CONTENT_TYPE, REPO)
    if change == "id":
        metadata["id"] = True
    if change == "admin":
        metadata["permissions"]["admin"] = True
    if change == "archived":
        metadata["archived"] = True
    if change == "disabled":
        metadata["disabled"] = True
    if change == "name":
        metadata["full_name"] = REPO + "-other"
    if change == "protection":
        branch["protected"] = False
    if change == "baseline":
        branch["commit"]["sha"] = "f" * 40
    if change == "proof_repo":
        proof["repository"] += "-other"
    if change == "proof_base":
        proof["main_sha"] = "f" * 40
    if change == "proof_schema":
        proof["schema"] = True
    if change == "proof_count":
        proof["refs_count"] = True
    if change == "proof_hash":
        proof["advertisement_sha256"] = "x" * 64
    with pytest.raises(Denied, match="repository_preflight"):
        validate_repository(metadata, branch, REPO, 1, git_discovery=proof)


def first(store, backend=None):
    backend = backend or FakeHTTP()
    c = experiment_config()
    g = Gateway(store, c, transport=httpx.MockTransport(backend.handle), credentials=Credentials())
    waiting = store.create('owner', str(uuid4()), payload(CodingRequest(provider='openai', experiment_id=EXPERIMENT_ID)))
    g.authorize('owner', waiting['id'], waiting['version'], budget_nano_rub=c.tariff.maximum() * 2)
    return g, store.claim(waiting['id']), backend


def test_real_f1_discovery_uses_basic_auth_and_anchored_ledger_without_ai(store):
    g, task, fake = first(store)
    fake.push = False
    RemotePublisher(g, task).verify_repository()
    assert fake.ai_calls == 0 and fake.prs == [] and fake.branches == {}
    with store.transaction() as session:
        rows = list(session.scalars(select(ExternalAction)))
        g.check_ledger(session, rows)
        discovery = next(row for row in rows if row.kind == "github_git")
        assert discovery.state == "COMPLETE" and discovery.reserved == discovery.actual == 0
        assert discovery.evidence["request_id"] == "AB12:CDEF:0011"
        assert set(discovery.evidence["response"]) == {
            "schema",
            "repository",
            "service",
            "main_sha",
            "refs_count",
            "advertisement_sha256",
        }
        assert not any(value in json.dumps(discovery.evidence) for value in Credentials.values.values())
    g.close()


@pytest.mark.parametrize("case", ["redirect", "forbidden", "timeout", "html", "bad_packet", "stop", "created"])
def test_discovery_failures_cannot_continue_to_ai_or_publication(store, case):
    fake = FakeHTTP()
    fake.push = False
    original = fake.handle

    def handle(request):
        if request.url.host != "github.com":
            return original(request)
        if case == "timeout":
            raise httpx.ReadTimeout("public fixture loss")
        if case == "stop":
            store.halt("owner")
            return original(request)
        if case == "created":
            return httpx.Response(201, content=git_advertisement(), headers={"content-type": CONTENT_TYPE})
        return httpx.Response(
            {"redirect": 302, "forbidden": 403}.get(case, 200),
            content=b"<html>ok</html>" if case == "html" else b"0001",
            headers={"content-type": CONTENT_TYPE, "location": "https://example.invalid/"},
        )

    fake.handle = handle
    g, task, _ = first(store, fake)
    with pytest.raises((Denied, Uncertain)):
        RemotePublisher(g, task).verify_repository()
    assert fake.ai_calls == 0 and not fake.prs and not fake.branches
    with store.transaction() as session:
        rows = list(session.scalars(select(ExternalAction).where(ExternalAction.kind == "github_git")))
        assert len(rows) == 1
        assert rows[0].state == ("COMPLETE" if case == "stop" else "UNCERTAIN")
    g.close()


@pytest.mark.parametrize(
    "change", ["post", "host_path", "other_repo", "upload_pack", "query", "body", "no_experiment", "fence"]
)
def test_discovery_has_one_fixed_read_endpoint_and_existing_f1_scope(store, change):
    g, task, fake = first(store)
    method, path, body, query, fence = "GET", discovery_path(REPO), None, None, task["fence"]
    if change == "post":
        method = "POST"
    if change == "host_path":
        path = "https://example.invalid/"
    if change == "other_repo":
        path = discovery_path(REPO + "-other")
    if change == "upload_pack":
        path = path.replace("receive", "upload")
    if change == "query":
        query = {"service": "git-receive-pack"}
    if change == "body":
        body = {"ref": "refs/heads/main"}
    if change == "no_experiment":
        g.config = g.config.model_copy(update={"first_experiment": None})
    if change == "fence":
        fence += 1
    with pytest.raises(Denied):
        g.request(task["id"], fence, "discovery", "github_git", method, path, body, query=query)
    assert not fake.calls
    g.close()
