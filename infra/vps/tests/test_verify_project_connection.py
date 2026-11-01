import importlib.util
from pathlib import Path
import sys


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
        "push_true",
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


def test_error_codes_do_not_leak_exception_text():
    assert operator.error_code(operator.Blocked("repository_preflight_invalid")) == (
        "repository_preflight_invalid"
    )
    assert operator.error_code(RuntimeError("secret provider response")) == "operator_check_failed"
