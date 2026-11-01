#!/usr/bin/env python3
"""Verify the fixed Command Center GitHub App binding and emit registration evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import jwt  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402

import prepare_github_token as github_token  # noqa: E402
from command_center.deployment_profile import atomic_json  # noqa: E402
from command_center.project_connections import PERMISSIONS, REPOSITORIES, validate  # noqa: E402
from command_center.store import digest  # noqa: E402

APP_ID, INSTALLATION_ID = 5524444, 176497504
REPOSITORY, REPOSITORY_ID = REPOSITORIES["command-center"], 1430664079
APP_SLUG, OWNER, ACCOUNT_ID = "acc-first-v71369322", "v71369322-lang", 346751364


class Blocked(Exception):
    pass


SAFE_ERRORS = {
    "app_identity_invalid",
    "installation_binding_invalid",
    "token_scope_invalid",
    "repository_preflight_invalid",
    "baseline_invalid",
    "existing_attempt_requires_inspection",
    "exact_plan_approval_required",
}


def error_code(error):
    value = str(error)
    return value if value in SAFE_ERRORS else "operator_check_failed"


def repository_checks(metadata, branch, baseline):
    protection = branch.get("protection", {})
    status = protection.get("required_status_checks", {})
    contexts = status.get("contexts", [])
    permissions = metadata.get("permissions", {})
    return {
        "repository_id": metadata.get("id") == REPOSITORY_ID,
        "repository_name": metadata.get("full_name") == REPOSITORY,
        "default_branch": metadata.get("default_branch") == "main",
        "active": metadata.get("archived") is False and metadata.get("disabled") is False,
        "admin_false": permissions.get("admin") is False,
        "push_true": permissions.get("push") is True,
        "branch_name": branch.get("name") == "main",
        "baseline": branch.get("commit", {}).get("sha") == baseline,
        "protection_enabled": protection.get("enabled") is True,
        "protection_everyone": status.get("enforcement_level") == "everyone",
        "offline_required": isinstance(contexts, list) and "offline" in contexts,
        "synthetic_required": isinstance(contexts, list) and "synthetic" in contexts,
    }


def configure():
    github_token.REPOSITORY, github_token.REPOSITORY_ID = REPOSITORY, REPOSITORY_ID
    github_token.REPO = "/repos/" + REPOSITORY
    github_token.GIT_DISCOVERY = github_token.discovery_path(REPOSITORY)
    github_token.REQUEST = {"repository_ids": [REPOSITORY_ID], "permissions": PERMISSIONS}
    github_token.ALLOWED = {
        ("GET", "/app"),
        ("GET", f"/app/installations/{INSTALLATION_ID}"),
        ("GET", github_token.REPO + "/installation"),
        ("POST", f"/app/installations/{INSTALLATION_ID}/access_tokens"),
        ("GET", "/installation/repositories?per_page=2&page=1"),
        ("GET", github_token.REPO),
        ("GET", github_token.REPO + "/branches/main"),
    }


def scope(key_file, output, revision, baseline):
    github_token.check_source(revision)
    if not re.fullmatch("[a-f0-9]{40}", baseline):
        raise Blocked("baseline_invalid")
    key_file, output = github_token.private_path(key_file), github_token.private_path(output)
    if os.path.lexists(output):
        raise Blocked("existing_attempt_requires_inspection")
    report = {
        "schema": 1,
        "action": "verify_project_connection",
        "operator_revision": revision,
        "project_id": "command-center",
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "installation_id": INSTALLATION_ID,
        "baseline_sha": baseline,
        "permissions": PERMISSIONS,
        "key_file": str(key_file),
        "output": str(output),
    }
    public = {k: v for k, v in report.items() if k not in {"key_file", "output"}}
    return key_file, output, {**public, "plan_digest": digest(report)}


def verify(key_file, output, revision, baseline, approved_plan, approved_until, transport=None):
    github_token.deadline(approved_until)
    key_file, output, report = scope(key_file, output, revision, baseline)
    if approved_plan != report["plan_digest"]:
        raise Blocked("exact_plan_approval_required")
    output.mkdir(mode=0o700)
    journal = {
        **report,
        "stage": "intent",
        "token_request_attempted": False,
        "http_events": [],
        "repository_changes": False,
        "application_configuration_changed": False,
        "paid_calls": 0,
    }
    atomic_json(output / "receipt.json", journal)
    client = github_token.GitHub(transport=transport)

    def checkpoint(stage):
        journal.update(stage=stage, http_events=client.events)
        atomic_json(output / "receipt.json", journal)

    try:
        key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
        now = int(time.time())
        assertion = jwt.encode(
            {"iat": now - 60, "exp": now + 300, "iss": str(APP_ID)}, key, algorithm="RS256"
        )
        app = client.call("GET", "/app", assertion)
        if (
            app.get("id"),
            app.get("slug"),
            app.get("owner", {}).get("id"),
            app.get("owner", {}).get("login"),
            app.get("permissions"),
        ) != (APP_ID, APP_SLUG, ACCOUNT_ID, OWNER, PERMISSIONS):
            raise Blocked("app_identity_invalid")
        installation_path = f"/app/installations/{INSTALLATION_ID}"
        for row in (
            client.call("GET", installation_path, assertion),
            client.call("GET", github_token.REPO + "/installation", assertion),
        ):
            if (
                row.get("id") != INSTALLATION_ID
                or row.get("app_id") != APP_ID
                or row.get("repository_selection") != "selected"
                or row.get("permissions") != PERMISSIONS
                or row.get("suspended_at") is not None
            ):
                raise Blocked("installation_binding_invalid")
        journal["token_request_attempted"] = True
        checkpoint("token_request_intent")
        response = client.call("POST", installation_path + "/access_tokens", assertion, github_token.REQUEST)
        token, _ = github_token.token_metadata(response)
        listed = client.call("GET", "/installation/repositories?per_page=2&page=1", token)
        if listed.get("total_count") != 1 or not github_token.one_repository(listed.get("repositories")):
            raise Blocked("token_scope_invalid")
        metadata = client.call("GET", github_token.REPO, token)
        branch = client.call("GET", github_token.REPO + "/branches/main", token)
        journal["repository_checks"] = repository_checks(metadata, branch, baseline)
        checkpoint("repository_preflight")
        if not all(journal["repository_checks"].values()):
            raise Blocked("repository_preflight_invalid")
        evidence = {
            "project_id": "command-center",
            "repository": REPOSITORY,
            "repository_id": REPOSITORY_ID,
            "installation_id": INSTALLATION_ID,
            "default_branch": "main",
            "baseline_sha": baseline,
            "permissions": PERMISSIONS,
            "repository_selection": "selected",
            "repository_count_verified": True,
            "binding_verified": True,
            "branch_protection_verified": True,
            "read_only_probe_verified": True,
        }
        validate(evidence)
        atomic_json(output / "connection-evidence.json", evidence)
        journal.update(
            stage="complete",
            evidence_sha256=hashlib.sha256((output / "connection-evidence.json").read_bytes()).hexdigest(),
        )
        atomic_json(output / "receipt.json", journal)
        return {
            **journal,
            "status": "PROJECT_CONNECTION_EVIDENCE_VERIFIED",
            "token_persisted": False,
            "external_calls": len(client.events),
        }
    except Exception as error:
        journal.update(
            stage="requires_inspection_no_retry", error_code=error_code(error), http_events=client.events
        )
        atomic_json(output / "receipt.json", journal)
        raise
    finally:
        client.client.close()


def main():
    configure()
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("plan", "verify"))
    p.add_argument("--key-file", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--operator-revision", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--approved-plan")
    p.add_argument("--approved-until", type=int)
    a = p.parse_args()
    try:
        if a.action == "plan":
            _, _, result = scope(a.key_file, a.output, a.operator_revision, a.baseline)
            result.update(status="OFFLINE_PLAN_NOT_AUTHORIZED", external_calls=0)
        else:
            result = verify(
                a.key_file, a.output, a.operator_revision, a.baseline, a.approved_plan, a.approved_until
            )
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "BLOCKED_REQUIRES_INSPECTION",
                    "error_code": error_code(error),
                    "repository_changes": False,
                    "application_configuration_changed": False,
                    "paid_calls": 0,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
