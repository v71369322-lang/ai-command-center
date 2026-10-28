"""Private real files, pure profiles and fake daemons; NOT VPS acceptance."""

import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest

from command_center.deployment import load_bundle
from command_center.deployment_profile import atomic_json, checksum, render
from command_center.store import digest
from command_center.telegram_release import binding
from command_center.telegram_transport import TelegramConnection, connection

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("update_staging", ROOT / "infra/vps/stage_telegram_update.py")
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    (root / "telegram").mkdir(mode=0o700)
    (root / "deployment.lock").touch(mode=0o600)
    config = TelegramConnection(
        mode="live",
        owner_id=1234567,
        bot_id=123456789,
        source_revision=staging.BASE_REVISION,
        token_file="/run/telegram/token",
    )
    atomic_json(root / "telegram/connection.json", config.model_dump())
    env = dict(os.environ, F1_SOURCE_REVISION=staging.TARGET_REVISION, F1_DOCKER_GID="0")
    base = json.loads(
        subprocess.check_output(
            [
                "docker",
                "--host=unix:///var/run/docker.sock",
                "compose",
                "--profile",
                "worker",
                "-f",
                str(ROOT / "compose.yaml"),
                "config",
                "--format",
                "json",
            ],
            env=env,
        )
    )
    m = dict(
        schema=1,
        revision=staging.BASE_REVISION,
        control_uid=os.getuid(),
        execution_uid=os.getuid() + 1,
        data_root=str(root),
        source_root=str(tmp_path / "old-source"),
        images={
            key: "sha256:" + str(i) * 64
            for i, key in enumerate(("api", "worker", "broker", "executor", "coding"), 1)
        },
        database_image=base["services"]["db"]["image"],
        redis_image=base["services"]["redis"]["image"],
        migration_hash="b" * 64,
        owner_login={"origin": "http://127.0.0.1:18000", "loopback_http": True},
    )
    m["telegram"] = dict(
        mode="live",
        owner_id=config.owner_id,
        bot_id=config.bot_id,
        connection_digest=digest(config.model_dump()),
    )
    previous = {"manifest": m, "compose": render(base, m)}
    target = copy.deepcopy(m)
    target.pop("telegram")
    target["revision"] = staging.TARGET_REVISION
    target["source_root"] = str(tmp_path / "new-source")
    disabled = {"manifest": target, "compose": render(base, target)}
    old_dir, new_dir = tmp_path / "active", tmp_path / "disabled"
    for folder, bundle in [(old_dir, previous), (new_dir, disabled)]:
        folder.mkdir(mode=0o700)
        atomic_json(folder / "bundle.json", bundle)
        atomic_json(folder / "compose.json", bundle["compose"])
    state = dict(
        phase="VERIFIED", revision=staging.BASE_REVISION, bundle=checksum(previous), directory=str(old_dir)
    )
    atomic_json(root / "deployment.json", state)
    calls = []

    class Engine:
        def __init__(self, uid):
            self.uid = uid

        def preflight(self):
            calls.append(("preflight", self.uid))

    monkeypatch.setattr(staging, "Engine", Engine)
    monkeypatch.setattr(staging, "source_check", lambda m: calls.append(("source", m["revision"])))
    monkeypatch.setattr(
        staging, "image_check", lambda e, images, rev: calls.append(("images", e.uid, set(images), rev))
    )
    return previous, disabled, config, old_dir, new_dir, root, calls


def test_stage_keeps_live_binding_and_state_and_never_reads_token(prepared, tmp_path):
    previous, disabled, config, old_dir, new_dir, root, calls = prepared
    before = {p: p.read_bytes() for p in (root / "deployment.json", root / "telegram/connection.json")}
    output = tmp_path / "candidate"
    result = staging.stage(old_dir, new_dir, output, checksum(previous))
    assert result["state"] == "STAGED_NOT_ACTIVATED"
    assert result["deployment_authorized"] is result["live_binding_modified"] is result["go_live"] is False
    assert {p: p.read_bytes() for p in before} == before
    assert not (root / "telegram/token").exists()
    assert connection(root / "telegram/connection.json") == config
    candidate = load_bundle(output)
    assert checksum(candidate) == result["candidate_bundle"]
    assert candidate["manifest"]["images"] == disabled["manifest"]["images"]
    # Re-rendering a validated disabled profile is identical to normalized-source rendering.
    env = dict(os.environ, F1_SOURCE_REVISION=staging.TARGET_REVISION, F1_DOCKER_GID="0")
    base = json.loads(
        subprocess.check_output(
            [
                "docker",
                "--host=unix:///var/run/docker.sock",
                "compose",
                "--profile",
                "worker",
                "-f",
                str(ROOT / "compose.yaml"),
                "config",
                "--format",
                "json",
            ],
            env=env,
        )
    )
    assert candidate["compose"] == render(base, candidate["manifest"])
    assert ("source", staging.TARGET_REVISION) in calls
    assert sum(call[0] == "images" for call in calls) == 2
    assert (output.stat().st_mode & 0o777) == 0o700
    assert all((p.stat().st_mode & 0o777) == 0o600 for p in output.iterdir())
    assert connection(output / "connection.candidate.json").source_revision == staging.TARGET_REVISION
    # Staging must NOT bypass the production binding/source guard.
    with pytest.raises(ValueError, match="exact_connection"):
        binding(root, staging.TARGET_REVISION, candidate["manifest"]["telegram"]["connection_digest"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("migration_hash", "c" * 64),
        ("database_image", "postgres:16-bookworm@sha256:" + "d" * 64),
        ("redis_image", "redis:7-bookworm@sha256:" + "e" * 64),
        ("data_root", "/tmp/unapproved-state"),
        ("control_uid", 2000),
        ("execution_uid", 2001),
        ("owner_login", {"origin": "http://127.0.0.1:18001", "loopback_http": True}),
    ],
)
def test_candidate_rejects_scope_and_schema_changes(prepared, field, value):
    previous, disabled, config, *_ = prepared
    changed = copy.deepcopy(disabled)
    changed["manifest"][field] = value
    changed["compose"] = render(disabled["compose"], changed["manifest"])
    with pytest.raises(ValueError, match="scope_or_migration"):
        staging.candidate(previous, changed, config, checksum(previous))


@pytest.mark.parametrize(
    "change", ["approval", "old_source", "new_source", "live_target", "owner", "token_ref", "mock"]
)
def test_candidate_rejects_unapproved_source_or_binding(prepared, change):
    previous, disabled, config, *_ = prepared
    previous, disabled = copy.deepcopy(previous), copy.deepcopy(disabled)
    approved = checksum(previous)
    if change == "approval":
        approved = "a" * 64
    elif change == "old_source":
        previous["manifest"]["revision"] = "a" * 40
        previous["compose"] = render(disabled["compose"], previous["manifest"])
        approved = checksum(previous)
    elif change == "new_source":
        disabled["manifest"]["revision"] = "a" * 40
        disabled["compose"] = render(disabled["compose"], disabled["manifest"])
    elif change == "live_target":
        disabled["manifest"]["telegram"] = previous["manifest"]["telegram"]
        disabled["compose"] = render(disabled["compose"], disabled["manifest"])
    else:
        fields = config.model_dump()
        fields.update(
            {"owner_id": 7654321}
            if change == "owner"
            else {"token_file": "/host/private-key"}
            if change == "token_ref"
            else {"mode": "http_mock"}
        )
        config = TelegramConnection.model_validate(fields)
    expected = {
        "approval": "previous_bundle_not_approved",
        "old_source": "exact_source_revisions_required",
        "new_source": "exact_source_revisions_required",
        "live_target": "live_to_disabled_preparation_required",
    }.get(change, "active_telegram_binding_changed")
    with pytest.raises(ValueError, match=expected):
        staging.candidate(previous, disabled, config, approved)


@pytest.mark.parametrize("change", ["revision", "phase", "bundle"])
def test_staging_refuses_changed_deployment(prepared, tmp_path, change):
    previous, _, _, old_dir, new_dir, root, _ = prepared
    state = json.loads((root / "deployment.json").read_text())
    state[change] = "INTENT" if change == "phase" else "a" * (40 if change == "revision" else 64)
    atomic_json(root / "deployment.json", state)
    with pytest.raises(ValueError, match="predecessor_changed"):
        staging.stage(old_dir, new_dir, tmp_path / "candidate", checksum(previous))
    assert not (tmp_path / "candidate").exists()


def test_image_inspection_race_is_rejected_before_output(prepared, tmp_path, monkeypatch):
    previous, _, config, old_dir, new_dir, root, _ = prepared

    def changed(*args):
        atomic_json(root / "telegram/connection.json", {**config.model_dump(), "owner_id": 7654321})

    monkeypatch.setattr(staging, "image_check", changed)
    with pytest.raises(ValueError, match="during_preparation"):
        staging.stage(old_dir, new_dir, tmp_path / "candidate", checksum(previous))
    assert not (tmp_path / "candidate").exists()


@pytest.mark.parametrize("destination", ["existing", "symlink", "state", "source", "public_parent"])
def test_output_cannot_overwrite_or_escape_private_staging(prepared, tmp_path, destination):
    previous, disabled, _, old_dir, new_dir, root, _ = prepared
    output = tmp_path / "candidate"
    if destination == "existing":
        output.mkdir()
    elif destination == "symlink":
        output.symlink_to(tmp_path / "absent")
    elif destination == "state":
        output = root / "candidate"
    elif destination == "source":
        source = Path(disabled["manifest"]["source_root"])
        source.mkdir(mode=0o700)
        output = source / "candidate"
    else:
        folder = tmp_path / "public"
        folder.mkdir(mode=0o755)
        folder.chmod(0o755)
        output = folder / "candidate"
    with pytest.raises(ValueError, match="private_candidate"):
        staging.stage(old_dir, new_dir, output, checksum(previous))


def test_partial_output_is_not_overwritten_on_retry(prepared, tmp_path, monkeypatch):
    previous, _, _, old_dir, new_dir, root, _ = prepared
    original = (root / "telegram/connection.json").read_bytes()
    atomic = staging.atomic_json

    def fail(path, value):
        if path.name == "compose.json":
            raise OSError("synthetic disk failure")
        atomic(path, value)

    monkeypatch.setattr(staging, "atomic_json", fail)
    output = tmp_path / "candidate"
    with pytest.raises(OSError):
        staging.stage(old_dir, new_dir, output, checksum(previous))
    assert (output / "bundle.json").is_file()
    assert (root / "telegram/connection.json").read_bytes() == original
    with pytest.raises(ValueError, match="private_candidate"):
        staging.stage(old_dir, new_dir, output, checksum(previous))


@pytest.fixture
def activation(prepared, tmp_path, monkeypatch):
    previous, _, config, old_dir, new_dir, root, calls = prepared
    output = tmp_path / "candidate"
    plan = staging.stage(old_dir, new_dir, output, checksum(previous))
    events = []
    failure = {"at": None}

    class Controller:
        def __init__(self, bundle, directory):
            self.bundle, self.directory = bundle, directory

        def preflight(self):
            assert connection(root / "telegram/connection.json") == config
            events.append("preflight-old")
            if failure["at"] == "race":
                state = json.loads((root / "deployment.json").read_text())
                atomic_json(root / "deployment.json", {**state, "phase": "INTENT"})

        def pause_telegram(self):
            assert connection(root / "telegram/connection.json") == config
            events.append("pause-old")
            if failure["at"] == "pause":
                raise OSError("synthetic stop uncertainty")

        def apply(self, action, approval, *, expected_previous):
            assert connection(root / "telegram/connection.json").source_revision == staging.TARGET_REVISION
            assert json.loads((output / "activation.json").read_text())["phase"] == "DEPLOYMENT_ATTEMPTED"
            assert action == "update" and approval == plan["candidate_bundle"]
            assert expected_previous == checksum(previous)
            events.append("existing-deployment-apply")
            if failure["at"] == "apply":
                raise OSError("synthetic unknown deployment result")
            state = json.loads((root / "deployment.json").read_text())
            atomic_json(
                root / "deployment.json",
                {**state, "revision": staging.TARGET_REVISION, "bundle": approval, "directory": str(output)},
            )
            return {"state": "CLOSED_SYNTHETIC_SERVICES_RUNNING", "go_live": False}

    monkeypatch.setattr(staging, "Deployment", Controller)
    monkeypatch.setattr(staging.time, "time", lambda: 10000)
    return prepared, output, plan, events, failure


def invoke_activation(activation, **overrides):
    prepared, output, plan, _, _ = activation
    previous, _, _, old_dir, *_ = prepared
    arguments = dict(
        active_directory=old_dir,
        candidate_directory=output,
        approved_previous=checksum(previous),
        approved_candidate=plan["candidate_bundle"],
        approved_until=10100,
    )
    arguments.update(overrides)
    return staging.apply_candidate(**arguments)


def test_activation_pauses_before_binding_and_delegates_existing_interlocks(activation):
    prepared, output, _, events, _ = activation
    original = prepared[2]
    result = invoke_activation(activation)
    assert result["go_live"] is False
    assert events == ["preflight-old", "pause-old", "existing-deployment-apply"]
    assert connection(output / "connection.previous.json") == original
    assert json.loads((output / "activation.json").read_text())["phase"] == "VERIFIED"
    with pytest.raises(ValueError, match="existing_activation"):
        invoke_activation(activation)
    assert events.count("existing-deployment-apply") == 1


@pytest.mark.parametrize("until", [None, 9999, 10000, 13601, True])
def test_activation_requires_fresh_finite_approval(activation, until):
    _, output, _, events, _ = activation
    with pytest.raises(ValueError, match="bounded_update_approval"):
        invoke_activation(activation, approved_until=until)
    assert events == [] and not (output / "activation.json").exists()


@pytest.mark.parametrize("argument", ["approved_previous", "approved_candidate"])
def test_activation_requires_both_exact_digests(activation, argument):
    _, output, _, events, _ = activation
    with pytest.raises(ValueError, match="exact_bundle_approvals"):
        invoke_activation(activation, **{argument: "a" * 64})
    assert events == [] and not (output / "activation.json").exists()


def test_activation_rejects_tampered_staged_binding(activation):
    _, output, _, events, _ = activation
    config = connection(output / "connection.candidate.json").model_dump()
    atomic_json(output / "connection.candidate.json", {**config, "owner_id": 7654321})
    with pytest.raises(ValueError, match="exact_candidate_binding"):
        invoke_activation(activation)
    assert events == [] and not (output / "activation.json").exists()


def test_activation_respects_existing_deployment_lock(activation):
    prepared, output, _, events, _ = activation
    with (prepared[5] / "deployment.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            invoke_activation(activation)
    assert events == [] and not (output / "activation.json").exists()


def test_activation_race_stops_before_pausing(activation):
    _, output, _, events, failure = activation
    failure["at"] = "race"
    with pytest.raises(ValueError, match="during_preparation"):
        invoke_activation(activation)
    assert events == ["preflight-old"] and not (output / "activation.json").exists()


@pytest.mark.parametrize(
    "at,phase,revision",
    [
        ("pause", "PAUSING_TELEGRAM", staging.BASE_REVISION),
        ("apply", "DEPLOYMENT_ATTEMPTED", staging.TARGET_REVISION),
    ],
)
def test_uncertainty_preserves_phase_and_never_retries_or_rolls_back(activation, at, phase, revision):
    prepared, output, _, events, failure = activation
    failure["at"] = at
    with pytest.raises(OSError):
        invoke_activation(activation)
    assert json.loads((output / "activation.json").read_text())["phase"] == phase
    assert connection(prepared[5] / "telegram/connection.json").source_revision == revision
    with pytest.raises(ValueError, match="existing_activation"):
        invoke_activation(activation)
    assert events.count("pause-old") == 1
    assert events.count("existing-deployment-apply") == int(at == "apply")
