"""Upgrade a disposable old F1 PG schema; never alter the shared test primary."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import time
from subprocess import CompletedProcess
from uuid import uuid4

from cryptography.exceptions import InvalidTag
import pytest
from sqlalchemy import inspect, select, text

from command_center.local_docker import run as docker
from command_center.models import Base, Control, OwnerSession, Audit, TelegramDelivery
from command_center.recovery import unseal
from command_center.store import Store, Denied
from command_center.runtime_policy import RuntimeBackend
from command_center.telegram_migration import TelegramMigration, CORE, POSTGRES, fingerprints

KEY = b"P" * 32  # Public synthetic fixture, never a real backup key.


@pytest.fixture(scope="module")
def isolated_pg(settings):
    suffix = uuid4().hex
    container, network = "acc-tg-migration-" + suffix, "acc-tg-migration-net-" + suffix

    def command(*args):
        result = docker(*args, timeout=60)
        assert result.returncode == 0, "isolated migration fixture command failed"
        return result.stdout

    command("network", "create", "--internal", network)
    try:
        command(
            "run",
            "-d",
            "--name",
            container,
            "--network",
            network,
            "--read-only",
            "--user=999:999",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory=512m",
            "--cpus=.5",
            "--pids-limit=128",
            "--tmpfs=/tmp:size=16m,uid=999,gid=999",
            "--tmpfs=/var/run/postgresql:size=8m,uid=999,gid=999,mode=0775",
            "--tmpfs=/var/lib/postgresql/data:size=128m,uid=999,gid=999,mode=0700",
            "--env=POSTGRES_USER=f1_admin",
            "--env=POSTGRES_DB=f1",
            "--env=POSTGRES_HOST_AUTH_METHOD=trust",
            POSTGRES,
        )
        info = json.loads(command("inspect", container))[0]
        address = info["NetworkSettings"]["Networks"][network]["IPAddress"]
        config = replace(
            settings,
            database_url=settings.database_url.set(
                host=address, port=5432, username="f1_admin", database="f1"
            ),
        )
        admin = Store(config)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                state = docker("exec", container, "cat", "/proc/1/comm", timeout=5)
                if state.returncode == 0 and state.stdout.strip() == b"postgres":
                    with admin.engine.begin() as conn:
                        conn.execute(text("CREATE ROLE f1_app NOLOGIN"))
                        conn.execute(text("CREATE ROLE f1_runtime NOLOGIN"))
                    break
                time.sleep(0.2)
            else:
                raise AssertionError("isolated old database not ready")
            yield admin, container
        finally:
            admin.engine.dispose()
    finally:
        docker("rm", "--force", container, timeout=15)
        docker("network", "rm", network, timeout=15)


@pytest.fixture
def legacy(isolated_pg):
    admin, container = isolated_pg
    Base.metadata.drop_all(admin.engine)
    Base.metadata.create_all(admin.engine, tables=[m.__table__ for m in CORE])
    with admin.engine.begin() as conn:
        conn.execute(Control.__table__.insert().values(id=1))
    old = Store(replace(admin.settings, source_revision="53565cc2ca232fb2cf6d6552a3ae04b462d92956"))
    with old.transaction() as session:
        old.audit(session, "bootstrap", "system")
    task = old.create(
        "owner",
        "preserved-task",
        {"kind": "approved_render", "values": {"legacy": "keep"}, "cost": 0, "dependency": None},
    )
    old.approve("owner", task["id"], task["version"])
    old.cancel("owner", task["id"])
    old.halt("owner")
    with old.transaction() as session:
        session.add(
            OwnerSession(
                token_hash="a" * 64,
                csrf_hash="b" * 64,
                assertion_hash="c" * 64,
                subject="synthetic owner",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        session.get(Control, 1).actual = 12
        session.get(Control, 1).uncertain = 3
    old.engine.dispose()
    return admin, container, task["id"]


def snapshot(admin):
    with admin.transaction() as session:
        return fingerprints(session)


def test_additive_migration_restores_backup_preserves_state_and_is_idempotent(legacy, tmp_path):
    admin, container, task_id = legacy
    migration = TelegramMigration(admin, runtime=RuntimeBackend(mode="cloud-rootful-test"))
    before = snapshot(admin)
    plan = migration.plan()
    assert snapshot(admin) == before and not inspect(admin.engine).has_table("telegram_inbox")
    archive = tmp_path / "before-telegram.enc"
    result = migration.apply(plan["plan_digest"], container, archive, KEY)
    assert result["state"] == "APPLIED" and result["restore_verified"]
    assert result["deployment_authorized"] is False and result["admission_halted"]
    assert archive.stat().st_mode & 0o077 == 0
    backup = json.loads(unseal(archive.read_bytes(), KEY))
    assert backup["plan"] == plan["plan"]
    after = snapshot(admin)
    assert {k: v for k, v in before.items() if k != "audit"} == {
        k: v for k, v in after.items() if k != "audit"
    }
    assert admin.get(task_id)["state"] == "CANCELLED"
    with admin.transaction() as session:
        old_audit = [
            row
            for row in session.execute(select(Audit).order_by(Audit.sequence)).scalars()
            if row.sequence <= plan["plan"]["anchor"]["sequence"]
        ]
        assert old_audit and old_audit[-1].digest == plan["plan"]["anchor"]["digest"]
        admin.check_audit(session)
        for table in ("telegram_inbox", "telegram_cards", "telegram_deliveries"):
            assert (
                session.scalar(text("SELECT has_table_privilege('f1_runtime', :t, 'SELECT')"), {"t": table})
                is False
            )
            assert (
                session.scalar(text("SELECT has_table_privilege('f1_app', :t, 'SELECT')"), {"t": table})
                is True
            )
            assert (
                session.scalar(text("SELECT has_table_privilege('f1_app', :t, 'DELETE')"), {"t": table})
                is False
            )
    assert migration.apply(plan["plan_digest"], container, archive, KEY)["state"] == "ALREADY_APPLIED"


def test_plan_change_or_wrong_database_cannot_start_ddl(legacy, tmp_path):
    admin, container, _ = legacy
    migration = TelegramMigration(admin, runtime=RuntimeBackend(mode="cloud-rootful-test"))
    plan = migration.plan()
    with pytest.raises(Denied, match="exact_plan"):
        migration.apply("0" * 64, container, tmp_path / "wrong.enc", KEY)
    with pytest.raises(Denied, match="database_mismatch"):
        migration.apply(plan["plan_digest"], "acc-f1-db-1", tmp_path / "wrong.enc", KEY)
    assert not (tmp_path / "wrong.enc").exists() and not inspect(admin.engine).has_table("telegram_inbox")


def test_corrupt_backup_is_rejected_before_ddl(legacy, tmp_path, monkeypatch):
    import command_center.telegram_migration as module

    admin, container, _ = legacy
    before = snapshot(admin)
    migration = TelegramMigration(admin, runtime=RuntimeBackend(mode="cloud-rootful-test"))
    monkeypatch.setattr(module, "seal", lambda *args: b"corrupt")
    with pytest.raises((InvalidTag, ValueError)):
        migration.apply(migration.plan()["plan_digest"], container, tmp_path / "bad.enc", KEY)
    assert not inspect(admin.engine).has_table("telegram_inbox") and snapshot(admin) == before


def test_ddl_failure_rolls_back_all_new_tables_and_preserves_legacy(legacy, tmp_path, monkeypatch):
    admin, container, _ = legacy
    before = snapshot(admin)
    migration = TelegramMigration(admin, runtime=RuntimeBackend(mode="cloud-rootful-test"))
    plan = migration.plan()
    monkeypatch.setattr(
        TelegramDelivery.__table__,
        "create",
        lambda *args, **kw: (_ for _ in ()).throw(RuntimeError("synthetic ddl failure")),
    )
    with pytest.raises(RuntimeError, match="synthetic ddl"):
        migration.apply(plan["plan_digest"], container, tmp_path / "before-failure.enc", KEY)
    assert snapshot(admin) == before
    assert not any(
        inspect(admin.engine).has_table(t)
        for t in ("telegram_inbox", "telegram_cards", "telegram_deliveries")
    )


@pytest.mark.parametrize("failure", ["running", "open_admission", "schema"])
def test_unsafe_baseline_is_blocked_without_mutation(legacy, failure):
    admin, _, task_id = legacy
    with admin.transaction() as session:
        if failure == "running":
            session.execute(text("UPDATE tasks SET state='CANCEL_REQUESTED' WHERE id=:id"), {"id": task_id})
        elif failure == "open_admission":
            session.get(Control, 1).halted = False
        else:
            session.execute(text("ALTER TABLE tasks ADD COLUMN unexpected text"))
    with pytest.raises(Denied, match="quiescence|unexpected_schema"):
        TelegramMigration(admin, runtime=RuntimeBackend(mode="cloud-rootful-test")).plan()
    assert not inspect(admin.engine).has_table("telegram_inbox")


def test_application_connections_must_be_stopped(legacy):
    admin, _, _ = legacy
    with admin.engine.begin() as conn:
        conn.execute(text("ALTER ROLE f1_app LOGIN"))
    app = Store(replace(admin.settings, database_url=admin.settings.database_url.set(username="f1_app")))
    try:
        with app.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            with pytest.raises(Denied, match="stop_application_connections"):
                TelegramMigration(admin, runtime=RuntimeBackend(mode="cloud-rootful-test")).plan()
    finally:
        app.engine.dispose()


def test_unconfirmed_restore_cleanup_blocks_migration(legacy, tmp_path):
    admin, container, _ = legacy
    runtime = RuntimeBackend(mode="cloud-rootful-test")
    real_call = runtime.call
    created = []

    def fail_stop(*args, **kwargs):
        if args[0] == "run":
            created.append(args[args.index("--name") + 1])
        if args[:2] == ("rm", "--force"):
            return CompletedProcess(args, 1, b"", b"synthetic stop refused")
        return real_call(*args, **kwargs)

    runtime.call = fail_stop
    migration = TelegramMigration(admin, runtime=runtime)
    before = snapshot(admin)
    try:
        with pytest.raises(Denied, match="cleanup_unconfirmed"):
            migration.apply(migration.plan()["plan_digest"], container, tmp_path / "cleanup.enc", KEY)
        assert snapshot(admin) == before and not inspect(admin.engine).has_table("telegram_inbox")
    finally:
        for name in created:
            real_call("rm", "--force", name, timeout=15)
