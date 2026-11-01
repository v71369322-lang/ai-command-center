"""Private real files, pure profiles and fake daemons; NOT VPS acceptance."""

import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

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


def test_recovery_adds_one_transition_without_retargeting_existing_eleven_releases():
    previous = {
        'f34': ('316dc1615dea224bcf4bd595d87048d19820bd21', 'b2e71fe073f3109e639dac43496884905ce86d9f'),
        'telegram-resume': ('b2e71fe073f3109e639dac43496884905ce86d9f', 'bdc8cbcdcf3fe2377fa6cc08250c331d35f99f82'),
        'telegram-mobile': ('b2e71fe073f3109e639dac43496884905ce86d9f', 'd932baafce53c0748396abfc019cf81b931ebfec'),
        'first-experiment': ('d932baafce53c0748396abfc019cf81b931ebfec', '0d44f31fe9e37045ed410751cbac7020c59b669a'),
        'first-experiment-readiness': ('d932baafce53c0748396abfc019cf81b931ebfec', '5a70a48e57d75eceac0526fe8abcf70d57489b8b'),
        'first-experiment-status': ('d932baafce53c0748396abfc019cf81b931ebfec', '185e6e32a60f8b5d62ed7046648560844a6eb19d'),
        'first-experiment-notifications': ('d932baafce53c0748396abfc019cf81b931ebfec', '8bab523f6f6e50a8a63e13a094f7fccf59ca889f'),
        'first-experiment-cancel': ('d932baafce53c0748396abfc019cf81b931ebfec', 'a5d867cb734a4954926a4e77c71e6f5be217057c'),
        'first-experiment-prepare': ('d932baafce53c0748396abfc019cf81b931ebfec', '7467df292cf990e1b86496a88ed8818d9ada4a28'),
        'first-experiment-authorize': ('d932baafce53c0748396abfc019cf81b931ebfec', '2822320569ca442ff5579140875ec074e1058898'),
    }
    previous['first-experiment-github-capability'] = (
        'd932baafce53c0748396abfc019cf81b931ebfec', '322186dc180257c618d8b159c78faa6e5bbf0b43')
    assert {key: staging.RELEASES[key] for key in previous} == previous
    assert set(staging.RELEASES) - set(previous) == {'first-experiment-recovery'}
    assert staging.release_pair('first-experiment-recovery') == (
        previous['first-experiment-github-capability'][1], 'bf91c05c754ad41e7f89223ec8d05c02c9007de1')
    assert staging.release_pair('first-experiment-github-capability') == (
        previous['telegram-mobile'][1], '322186dc180257c618d8b159c78faa6e5bbf0b43')


@pytest.fixture(params=["f34", "telegram-resume", "telegram-mobile", "first-experiment", "first-experiment-readiness", "first-experiment-status", "first-experiment-notifications", "first-experiment-cancel", "first-experiment-prepare", "first-experiment-authorize", "first-experiment-github-capability", "first-experiment-recovery"])
def prepared(tmp_path, monkeypatch, request):
    base_revision, target_revision = staging.release_pair(request.param)
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    (root / "telegram").mkdir(mode=0o700)
    (root / "deployment.lock").touch(mode=0o600)
    config = TelegramConnection(
        mode="live",
        owner_id=1234567,
        bot_id=123456789,
        source_revision=base_revision,
        token_file="/run/telegram/token",
    )
    atomic_json(root / "telegram/connection.json", config.model_dump())
    env = dict(os.environ, F1_SOURCE_REVISION=target_revision, F1_DOCKER_GID="0")
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
        revision=base_revision,
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
    target["revision"] = target_revision
    target["source_root"] = str(tmp_path / "new-source")
    if request.param in {"first-experiment", "first-experiment-readiness", "first-experiment-status", "first-experiment-notifications", "first-experiment-cancel", "first-experiment-prepare", "first-experiment-authorize", "first-experiment-github-capability", "first-experiment-recovery"}:
        from command_center.coding.first_experiment import CAP, FirstExperiment, MODEL
        from command_center.coding.integration_config import IntegrationConfig, Tariff
        from command_center.deployment_integrations import prepare_binding
        private = tmp_path / "external-private"
        private.mkdir(mode=0o700)
        external = IntegrationConfig(mode="live", live_authorized=False,
            synthetic_repository="fixture/acc-f2-synthetic-stage", budget_evidence="PUBLIC_FIXTURE_ONLY",
            daily_nano_rub=CAP, monthly_nano_rub=CAP, first_experiment=FirstExperiment(repository_id=725000001),
            tariff=Tariff(model=MODEL, input_nano_rub=67500, output_nano_rub=405000, context_tokens=400000,
                          max_output_tokens=2048, confirmed=True, evidence="PUBLIC_FIXTURE_ONLY"),
            credential_files={"openai": "/run/f2/openai.key", "github-installation-token": "/run/f2/github.token"})
        config_file = private / "config.json"
        atomic_json(config_file, {**external.model_dump(), "credential_files": external.credential_files})
        key_files = []
        for name in ("openai", "github"):
            path = private / name
            path.write_text("PUBLIC_SYNTHETIC_FIXTURE_" + name)
            path.chmod(0o600)
            key_files.append(path)
        target["first_experiment"] = prepare_binding(target, config_file, *key_files,
            telegram_readiness=request.param != "first-experiment")
    if request.param == 'first-experiment-recovery':
        from command_center.coding.recovery import RecoveryExperiment
        # The installed predecessor already has its own immutable first profile.
        m['first_experiment'] = copy.deepcopy(target['first_experiment'])
        previous = {'manifest': m, 'compose': render(base, m)}
        recovery_file = private / 'recovery.json'
        external.first_experiment = RecoveryExperiment(repository_id=725000001,
            original_task_id='938e838d-54d4-470d-ad71-5c6a49a42c7d', original_grant_digest='c' * 64)
        atomic_json(recovery_file, {**external.model_dump(), 'credential_files': external.credential_files})
        target['first_experiment'] = prepare_binding(target, recovery_file, *key_files, telegram_readiness=True)
    disabled = {"manifest": target, "compose": render(base, target)}
    old_dir, new_dir = tmp_path / "active", tmp_path / "disabled"
    for folder, bundle in [(old_dir, previous), (new_dir, disabled)]:
        folder.mkdir(mode=0o700)
        atomic_json(folder / "bundle.json", bundle)
        atomic_json(folder / "compose.json", bundle["compose"])
    state = dict(
        phase="VERIFIED", revision=base_revision, bundle=checksum(previous), directory=str(old_dir)
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


def release_for(prepared):
    pair = (prepared[0]["manifest"]["revision"], prepared[1]["manifest"]["revision"])
    return next(name for name, allowed in staging.RELEASES.items() if pair == allowed)


def closed_source(previous):
    """Restore this fixture's closed input before rendering a different manifest."""
    base = copy.deepcopy(previous["compose"])
    base["services"].pop("telegram", None)
    base["services"]["api"]["environment"].pop("F1_TELEGRAM_SCOPE", None)
    return base


@pytest.mark.parametrize("prepared", ["first-experiment", "first-experiment-readiness", "first-experiment-status", "first-experiment-notifications", "first-experiment-cancel", "first-experiment-prepare", "first-experiment-authorize", "first-experiment-github-capability"], indirect=True)
def test_first_experiment_requires_explicit_new_binding(prepared):
    previous, disabled, config, *_ = prepared
    unbound = copy.deepcopy(disabled)
    unbound["manifest"].pop("first_experiment")
    unbound["compose"] = render(closed_source(previous), unbound["manifest"])
    with pytest.raises(ValueError, match="explicit_first_experiment_binding_required"):
        staging.candidate(previous, unbound, config, checksum(previous), release=release_for(prepared))


@pytest.mark.parametrize("prepared", ["first-experiment", "first-experiment-readiness", "first-experiment-status", "first-experiment-notifications", "first-experiment-cancel", "first-experiment-prepare", "first-experiment-authorize", "first-experiment-github-capability"], indirect=True)
def test_readiness_flag_cannot_be_added_or_removed_under_another_release(prepared):
    previous, disabled, config, *_ = prepared
    changed = copy.deepcopy(disabled)
    binding = changed["manifest"]["first_experiment"]
    if binding.pop("telegram_readiness", None) is None:
        binding["telegram_readiness"] = True
    changed["compose"] = render(changed["compose"], changed["manifest"])
    with pytest.raises(ValueError, match="exact_readiness_profile_required"):
        staging.candidate(previous, changed, config, checksum(previous), release=release_for(prepared))


@pytest.mark.parametrize("prepared", ["first-experiment"], indirect=True)
@pytest.mark.parametrize("release", ["f34", "telegram-resume", "telegram-mobile"])
def test_legacy_release_cannot_inherit_integration_binding(prepared, release):
    previous, disabled, config, *_ = prepared
    old, new = copy.deepcopy(previous), copy.deepcopy(disabled)
    old_revision, new_revision = staging.release_pair(release)
    old["manifest"]["revision"], new["manifest"]["revision"] = old_revision, new_revision
    # Rendering profiles does not require real files or credentials.
    for bundle in (old, new):
        bundle["compose"] = render(closed_source(previous), bundle["manifest"])
    with pytest.raises(ValueError, match="first_experiment_release_required"):
        staging.candidate(old, new, config, checksum(old), release=release)


@pytest.mark.parametrize("prepared", ["first-experiment"], indirect=True)
def test_stage_rejects_changed_config_before_creating_candidate(prepared, tmp_path):
    previous, disabled, _, old_dir, new_dir, root, _ = prepared
    path = Path(disabled["manifest"]["first_experiment"]["config_file"])
    path.write_bytes(path.read_bytes() + b"\n")
    before = (root / "telegram/connection.json").read_bytes()
    output = tmp_path / "candidate"
    with pytest.raises(ValueError, match="first_experiment_config_pin_changed"):
        staging.stage(old_dir, new_dir, output, checksum(previous), release="first-experiment")
    assert not output.exists()
    assert (root / "telegram/connection.json").read_bytes() == before


def test_stage_keeps_live_binding_and_state_and_never_reads_token(prepared, tmp_path):
    previous, disabled, config, old_dir, new_dir, root, calls = prepared
    before = {p: p.read_bytes() for p in (root / "deployment.json", root / "telegram/connection.json")}
    output = tmp_path / "candidate"
    result = staging.stage(old_dir, new_dir, output, checksum(previous), release=release_for(prepared))
    assert result["state"] == "STAGED_NOT_ACTIVATED"
    assert result["deployment_authorized"] is result["live_binding_modified"] is result["go_live"] is False
    assert {p: p.read_bytes() for p in before} == before
    assert not (root / "telegram/token").exists()
    assert connection(root / "telegram/connection.json") == config
    candidate = load_bundle(output)
    assert checksum(candidate) == result["candidate_bundle"]
    assert candidate["manifest"]["images"] == disabled["manifest"]["images"]
    # Re-rendering a validated disabled profile is identical to normalized-source rendering.
    env = dict(os.environ, F1_SOURCE_REVISION=disabled["manifest"]["revision"], F1_DOCKER_GID="0")
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
    assert ("source", disabled["manifest"]["revision"]) in calls
    assert sum(call[0] == "images" for call in calls) == 2
    assert (output.stat().st_mode & 0o777) == 0o700
    assert all((p.stat().st_mode & 0o777) == 0o600 for p in output.iterdir())
    assert connection(output / "connection.candidate.json").source_revision == disabled["manifest"]["revision"]
    # Staging must NOT bypass the production binding/source guard.
    with pytest.raises(ValueError, match="exact_connection"):
        binding(root, disabled["manifest"]["revision"], candidate["manifest"]["telegram"]["connection_digest"])


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
        staging.candidate(previous, changed, config, checksum(previous), release=release_for(prepared))


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
        previous["compose"] = render(closed_source(previous), previous["manifest"])
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
        staging.candidate(previous, disabled, config, approved, release=release_for(prepared))


@pytest.mark.parametrize("change", ["revision", "phase", "bundle"])
def test_staging_refuses_changed_deployment(prepared, tmp_path, change):
    previous, _, _, old_dir, new_dir, root, _ = prepared
    state = json.loads((root / "deployment.json").read_text())
    state[change] = "INTENT" if change == "phase" else "a" * (40 if change == "revision" else 64)
    atomic_json(root / "deployment.json", state)
    with pytest.raises(ValueError, match="predecessor_changed"):
        staging.stage(old_dir, new_dir, tmp_path / "candidate", checksum(previous), release=release_for(prepared))
    assert not (tmp_path / "candidate").exists()


def test_image_inspection_race_is_rejected_before_output(prepared, tmp_path, monkeypatch):
    previous, _, config, old_dir, new_dir, root, _ = prepared

    def changed(*args):
        atomic_json(root / "telegram/connection.json", {**config.model_dump(), "owner_id": 7654321})

    monkeypatch.setattr(staging, "image_check", changed)
    with pytest.raises(ValueError, match="during_preparation"):
        staging.stage(old_dir, new_dir, tmp_path / "candidate", checksum(previous), release=release_for(prepared))
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
        staging.stage(old_dir, new_dir, output, checksum(previous), release=release_for(prepared))


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
        staging.stage(old_dir, new_dir, output, checksum(previous), release=release_for(prepared))
    assert (output / "bundle.json").is_file()
    assert (root / "telegram/connection.json").read_bytes() == original
    with pytest.raises(ValueError, match="private_candidate"):
        staging.stage(old_dir, new_dir, output, checksum(previous), release=release_for(prepared))


@pytest.fixture
def activation(prepared, tmp_path, monkeypatch):
    previous, disabled, config, old_dir, new_dir, root, calls = prepared
    output = tmp_path / "candidate"
    plan = staging.stage(old_dir, new_dir, output, checksum(previous), release=release_for(prepared))
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
            assert connection(root / "telegram/connection.json").source_revision == disabled["manifest"]["revision"]
            assert json.loads((output / "activation.json").read_text())["phase"] == "DEPLOYMENT_ATTEMPTED"
            assert action == "update" and approval == plan["candidate_bundle"]
            assert expected_previous == checksum(previous)
            events.append("existing-deployment-apply")
            if failure["at"] == "apply":
                raise OSError("synthetic unknown deployment result")
            state = json.loads((root / "deployment.json").read_text())
            atomic_json(
                root / "deployment.json",
                {**state, "revision": disabled["manifest"]["revision"], "bundle": approval, "directory": str(output)},
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
        release=release_for(prepared),
    )
    arguments.update(overrides)
    return staging.apply_candidate(**arguments)


@pytest.mark.parametrize("prepared", ["first-experiment"], indirect=True)
def test_activation_rechecks_config_pin_before_pause_or_journal(activation):
    prepared, output, _, events, _ = activation
    binding = prepared[1]["manifest"]["first_experiment"]
    path = Path(binding["config_file"])
    path.write_bytes(path.read_bytes() + b"\n")
    before = (prepared[5] / "telegram/connection.json").read_bytes()
    with pytest.raises(ValueError, match="first_experiment_config_pin_changed"):
        invoke_activation(activation)
    assert events == ["preflight-old"]
    assert not (output / "activation.json").exists()
    assert (prepared[5] / "telegram/connection.json").read_bytes() == before


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
        ("pause", "PAUSING_TELEGRAM", "old"),
        ("apply", "DEPLOYMENT_ATTEMPTED", "new"),
    ],
)
def test_uncertainty_preserves_phase_and_never_retries_or_rolls_back(activation, at, phase, revision):
    prepared, output, _, events, failure = activation
    failure["at"] = at
    with pytest.raises(OSError):
        invoke_activation(activation)
    assert json.loads((output / "activation.json").read_text())["phase"] == phase
    assert connection(prepared[5] / "telegram/connection.json").source_revision == prepared[0 if revision == "old" else 1]["manifest"]["revision"]
    with pytest.raises(ValueError, match="existing_activation"):
        invoke_activation(activation)
    assert events.count("pause-old") == 1
    assert events.count("existing-deployment-apply") == int(at == "apply")


def test_profile_never_infers_a_new_transition_from_manifests(prepared, tmp_path):
    previous, disabled, config, old_dir, new_dir, root, _ = prepared
    before = (root / "telegram/connection.json").read_bytes()
    for wrong in set(staging.RELEASES) - {release_for(prepared)}:
        with pytest.raises(ValueError, match="exact_source_revisions_required"):
            staging.candidate(previous, disabled, config, checksum(previous), release=wrong)
        expected = ("verified_predecessor_changed" if staging.release_pair(wrong)[0] != previous["manifest"]["revision"]
                    else "exact_source_revisions_required")
        with pytest.raises(ValueError, match=expected):
            staging.stage(old_dir, new_dir, tmp_path / "other", checksum(previous), release=wrong)
    assert (root / "telegram/connection.json").read_bytes() == before
    assert not (tmp_path / "other").exists()


def test_wrong_apply_profile_does_not_pause_or_write_journal(activation):
    prepared, output, _, events, _ = activation
    for wrong in set(staging.RELEASES) - {release_for(prepared)}:
        with pytest.raises(ValueError, match="exact_source_revisions_required"):
            invoke_activation(activation, release=wrong)
    assert events == [] and not (output / "activation.json").exists()


@pytest.mark.parametrize("value", [None, True, "", "latest", "main", "f34; unsafe"])
def test_unknown_profile_is_rejected_before_loading_any_path(value):
    with pytest.raises(ValueError, match="exact_release_profile_required"):
        staging.stage("/not-loaded", "/not-loaded", "/not-created", "a" * 64, release=value)


@pytest.mark.parametrize("profile", [None, "f34", "telegram-resume", "telegram-mobile", "first-experiment", "first-experiment-readiness", "first-experiment-status", "first-experiment-notifications", "first-experiment-cancel", "first-experiment-prepare", "first-experiment-authorize", "first-experiment-github-capability"])
@pytest.mark.parametrize("action", ["stage", "apply"])
def test_cli_uses_explicit_profile_and_preserves_legacy_default(monkeypatch, profile, action, capsys):
    argv = ["tool", action, "--active-bundle", "/active", "--disabled-bundle", "/disabled",
            "--output", "/candidate", "--approved-previous", "a" * 64]
    if action == "apply":
        argv += ["--approved-candidate", "b" * 64, "--approved-until", "10100"]
    if profile:
        argv += ["--release", profile]
    seen = []
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(staging, "stage" if action == "stage" else "apply_candidate",
                        lambda *args, **kw: seen.append(kw["release"]) or {"mock": True})
    staging.main()
    assert seen == [profile or "f34"]
    assert json.loads(capsys.readouterr().out) == {"mock": True}


@pytest.mark.parametrize("window", [None, "0", "not-a-time"])
@pytest.mark.parametrize("profile", [None, "telegram-mobile"])
def test_prepare_script_missing_or_expired_scope_denied_before_host_access(window, profile):
    env = {"PATH": os.environ["PATH"]}
    if profile:
        env["ACC_TELEGRAM_RELEASE"] = profile
    if window is not None:
        env["ACC_PREPARE_APPROVED_UNTIL"] = window
    result = subprocess.run(["bash", str(ROOT / "infra/vps/prepare_telegram_resume.sh")],
                            env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode and "PREPARATION_APPROVAL_MISSING_OR_EXPIRED" in result.stderr
    assert not result.stdout


@pytest.mark.parametrize("revision", ["", "main", "x" * 40])
@pytest.mark.parametrize("profile", [None, "telegram-mobile"])
def test_prepare_script_requires_exact_operator_revision_before_host_access(revision, profile):
    env = {"PATH": os.environ["PATH"], "ACC_PREPARE_APPROVED_UNTIL": str(int(time.time()) + 60),
           "ACC_OPERATOR_REVISION": revision}
    if profile:
        env["ACC_TELEGRAM_RELEASE"] = profile
    result = subprocess.run(["bash", str(ROOT / "infra/vps/prepare_telegram_resume.sh")],
                            env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode and "EXACT_OPERATOR_REVISION_REQUIRED" in result.stderr
    assert not result.stdout


def test_prepare_shell_syntax_and_default_new_profile_rejection(prepared):
    subprocess.run(["bash", "-n", str(ROOT / "infra/vps/prepare_telegram_resume.sh")], check=True)
    if release_for(prepared) != "f34":
        previous, disabled, config, *_ = prepared
        with pytest.raises(ValueError, match="exact_source_revisions_required"):
            staging.candidate(previous, disabled, config, checksum(previous))


@pytest.mark.parametrize("name", ["src/command_center/models.py", "src/command_center/admin.py",
    "requirements.lock", "uv.lock", "Dockerfile", "Dockerfile.executor", "compose.yaml", "web/package-lock.json"])
@pytest.mark.parametrize("profile", ["telegram-resume", "telegram-mobile"])
def test_pinned_resume_release_has_no_schema_dependency_or_boundary_change(name, profile):
    old, new = staging.release_pair(profile)
    blobs = [subprocess.check_output(["git", "show", f"{sha}:{name}"], cwd=ROOT) for sha in (old, new)]
    assert blobs[0] == blobs[1]


@pytest.mark.parametrize("profile", [None, "telegram-resume", "telegram-mobile"])
def test_prepare_selector_matches_pinned_profile_before_any_host_access(profile):
    # Execute only the real validation/selection prefix, stopping BEFORE host
    # identity, files, Git or Docker access. This is not a full script/VPS proof.
    script = (ROOT / "infra/vps/prepare_telegram_resume.sh").read_text()
    prefix, _ = script.split('if [ "$(id -u)" != 1000 ]', 1)
    probe = prefix + '\nprintf "%s\\n" "$release" "$application" "$base" "$marker"\n'
    env = {"PATH": os.environ["PATH"], "ACC_PREPARE_APPROVED_UNTIL": str(int(time.time()) + 60),
           "ACC_OPERATOR_REVISION": "a" * 40}
    if profile is not None:
        env["ACC_TELEGRAM_RELEASE"] = profile
    result = subprocess.run(["bash", "-s"], input=probe, env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and not result.stderr
    selected = profile or "telegram-resume"
    assert result.stdout.splitlines() == [selected, staging.release_pair(selected)[1],
        f"/home/acc-control/{selected}-release", selected.upper().replace("-", "_") + "_CANDIDATE_PREPARED_NOT_APPLIED"]


@pytest.mark.parametrize("profile", ["", "latest", "main", "f34", "telegram-mobile; unsafe", "a" * 40])
def test_prepare_unknown_profile_denied_without_host_access_or_input_echo(profile):
    env = {"PATH": os.environ["PATH"], "ACC_PREPARE_APPROVED_UNTIL": str(int(time.time()) + 60),
           "ACC_OPERATOR_REVISION": "a" * 40, "ACC_TELEGRAM_RELEASE": profile}
    result = subprocess.run(["bash", str(ROOT / "infra/vps/prepare_telegram_resume.sh")],
                            env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode and result.stderr.strip() == "EXACT_TELEGRAM_RELEASE_REQUIRED"
    assert not result.stdout


def test_prepare_overlong_approval_does_not_gain_host_access():
    env = {"PATH": os.environ["PATH"], "ACC_PREPARE_APPROVED_UNTIL": str(int(time.time()) + 10800),
           "ACC_OPERATOR_REVISION": "a" * 40, "ACC_TELEGRAM_RELEASE": "telegram-mobile"}
    result = subprocess.run(["bash", str(ROOT / "infra/vps/prepare_telegram_resume.sh")],
                            env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode and result.stderr.strip() == "PREPARATION_APPROVAL_MISSING_OR_EXPIRED"
    assert not result.stdout


@pytest.mark.parametrize('prepared', ['first-experiment-recovery'], indirect=True)
@pytest.mark.parametrize('change', ['missing_old', 'old_recovery', 'old_no_readiness',
                                    'missing_new', 'new_no_marker', 'wrong_marker', 'new_no_readiness'])
def test_recovery_requires_explicit_first_to_recovery_transition(prepared, change):
    old, new = copy.deepcopy(prepared[0]['manifest']), copy.deepcopy(prepared[1]['manifest'])
    if change == 'missing_old':
        old.pop('first_experiment')
    elif change == 'old_recovery':
        old['first_experiment']['recovery'] = 'f2.2-recovery-1'
    elif change == 'old_no_readiness':
        old['first_experiment'].pop('telegram_readiness')
    elif change == 'missing_new':
        new.pop('first_experiment')
    elif change == 'new_no_marker':
        new['first_experiment'].pop('recovery')
    elif change == 'wrong_marker':
        new['first_experiment']['recovery'] = 'arbitrary-retry'
    else:
        new['first_experiment'].pop('telegram_readiness')
    with pytest.raises(ValueError, match='explicit_one_call_recovery_transition_required'):
        staging.integration_transition(old, new, 'first-experiment-recovery')
