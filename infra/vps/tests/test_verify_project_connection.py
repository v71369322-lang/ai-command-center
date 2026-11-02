import importlib.util
from pathlib import Path
import sys
import json


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "infra/vps"))
SPEC = importlib.util.spec_from_file_location(
    "verify_project_connection", ROOT / "infra/vps/verify_project_connection.py"
)
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


def test_repository_checks_are_fixed_and_complete():
    metadata = {
        "id": operator.REPOSITORY_ID,
        "full_name": operator.REPOSITORY,
        "default_branch": "main",
        "archived": False,
        "disabled": False,
        "permissions": {"admin": False, "push": True},
    }
    branch = {
        "name": "main",
        "commit": {"sha": "a" * 40},
        "protection": {
            "enabled": True,
            "required_status_checks": {"enforcement_level": "everyone", "contexts": ["offline", "synthetic"]},
        },
    }
    checks = operator.repository_checks(metadata, branch, "a" * 40)
    assert all(checks.values())
    assert set(checks) == {
        "repository_id",
        "repository_name",
        "default_branch",
        "active",
        "admin_false",
        "write_capability",
        "branch_name",
        "baseline",
        "protection_enabled",
        "protection_everyone",
        "offline_required",
        "synthetic_required",
    }


def test_repository_checks_identify_each_missing_guard():
    checks = operator.repository_checks({}, {}, "a" * 40)
    assert not any(checks.values())


def test_protected_branch_accepts_exact_receive_pack_advertisement():
    metadata = {
        "id": operator.REPOSITORY_ID,
        "full_name": operator.REPOSITORY,
        "default_branch": "main",
        "archived": False,
        "disabled": False,
        "permissions": {"admin": False, "push": False},
    }
    branch = {
        "name": "main",
        "commit": {"sha": "a" * 40},
        "protection": {
            "enabled": True,
            "required_status_checks": {"enforcement_level": "everyone", "contexts": ["offline", "synthetic"]},
        },
    }
    discovery = {
        "service": "git-receive-pack",
        "repository": operator.REPOSITORY,
        "main_sha": "a" * 40,
        "refs_count": 1,
    }
    checks = operator.repository_checks(metadata, branch, "a" * 40, discovery)
    assert all(checks.values())
    assert (
        operator.repository_checks(metadata, branch, "a" * 40, discovery | {"main_sha": "b" * 40})[
            "write_capability"
        ]
        is False
    )


def test_error_codes_do_not_leak_exception_text():
    assert operator.error_code(operator.Blocked("repository_preflight_invalid")) == (
        "repository_preflight_invalid"
    )
    assert operator.error_code(RuntimeError("secret provider response")) == "operator_check_failed"


def test_inspect_returns_only_fixed_receipt_fields(tmp_path, monkeypatch):
    output = tmp_path / "attempt"
    output.mkdir(mode=0o700)
    receipt = {
        "stage": "requires_inspection_no_retry",
        "error_code": "fixed",
        "token_request_attempted": True,
        "secret": "hidden",
        "repository_checks": {"baseline": False, "unknown": True},
        "http_events": [{"method": "GET", "endpoint": "/app", "http_status": 200, "body": "hidden"}],
    }
    path = output / "receipt.json"
    path.write_text(json.dumps(receipt))
    path.chmod(0o600)
    monkeypatch.setattr(operator.github_token, "check_source", lambda revision: None)
    monkeypatch.setattr(operator.github_token, "private_path", lambda value: Path(value))
    result = operator.inspect(output, "a" * 40)
    assert result["repository_checks"] == {"baseline": False}
    assert result["http_events"] == [{"method": "GET", "endpoint": "/app", "http_status": 200}]
    assert "secret" not in result and result["external_calls"] == 0
