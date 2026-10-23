"""Trusted operator toolbox: PostgreSQL custom dumps, AES-GCM, isolated restore.
Local files are test evidence ONLY, not proof of independent offsite custody.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import Settings
from .models import Approval, Control, Task
from .store import Store, TERMINAL

MAGIC = b"ACC-F1-BACKUP-v1\x00"


def seal(dump: bytes, key: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, dump, MAGIC)


def unseal(archive: bytes, key: bytes) -> bytes:
    if not archive.startswith(MAGIC):
        raise ValueError("invalid_backup_format")
    start = len(MAGIC)
    return AESGCM(key).decrypt(archive[start:start+12], archive[start+12:], MAGIC)


def enter_recovery(store):
    with store.transaction() as s:
        control = s.get(Control, 1)
        control.halted = True
        control.recovery = True
        control.epoch += 1
        for approval in s.query(Approval).all():
            approval.revoked = True
        for task in s.query(Task).all():
            if task.state not in TERMINAL:
                task.state = "RECONCILING"
        store.audit(s, "restored_execution_interlock", "recovery", epoch=control.epoch)


def dump_database(container):
    command = ["docker", "--host=unix:///var/run/docker.sock", "exec", container,
               "pg_dump", "--format=custom", "--no-owner", "--username=f1_admin", "--dbname=f1"]
    result = subprocess.run(command, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError("pg_dump_failed")
    if len(result.stdout) > 64 * 1024 * 1024:
        raise RuntimeError("synthetic_backup_size_limit")
    return result.stdout


def restore_database(container, target, dump, settings):
    if not re.fullmatch(r"f1_restore_[a-z0-9_]{1,40}", target):
        raise ValueError("Only a NEW f1_restore_* database is allowed; never overwrite f1")
    prefix = ["docker", "--host=unix:///var/run/docker.sock", "exec", "-i", container]
    created = subprocess.run(prefix + ["createdb", "-U", "f1_admin", target], capture_output=True, timeout=20)
    if created.returncode:
        raise RuntimeError("restore_target_must_be_new")
    restored = subprocess.run(prefix + ["pg_restore", "-U", "f1_admin", "-d", target,
                                        "--exit-on-error", "--no-owner"], input=dump,
                              capture_output=True, timeout=60)
    if restored.returncode:
        raise RuntimeError("pg_restore_failed_target_quarantined")
    from dataclasses import replace
    restored_store = Store(replace(settings, database_url=settings.database_url.set(database=target)))
    enter_recovery(restored_store)
    restored_store.checkpoint()
    return restored_store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["backup", "restore", "checkpoint", "verify-checkpoint"])
    parser.add_argument("--file", required=True)
    parser.add_argument("--key-file")
    parser.add_argument("--container", default="acc-f1-db-1")
    parser.add_argument("--target")
    args = parser.parse_args()
    settings = Settings.load()
    store = Store(settings)
    if args.mode == "checkpoint":
        data = json.dumps(store.checkpoint(), sort_keys=True).encode()
    elif args.mode == "verify-checkpoint":
        anchor = json.loads(Path(args.file).read_text())
        with store.transaction() as s:
            store.check_audit(s, anchor)
        print("Checkpoint verified against current journal; independent custody NOT established by this command.")
        return
    else:
        if not args.key_file:
            parser.error("--key-file is required")
        key = bytes.fromhex(Path(args.key_file).read_text().strip())
        if args.mode == "backup":
            data = seal(dump_database(args.container), key)
        else:
            if not args.target:
                parser.error("--target f1_restore_* is required")
            restored = restore_database(args.container, args.target, unseal(Path(args.file).read_bytes(), key), settings)
            print(json.dumps({"target": args.target, "recovery_interlock": restored.snapshot()["recovery"]}))
            return
    fd = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    print("Evidence written without overwrite. Transfer to separately authorized protected custody is required.")


if __name__ == "__main__":
    main()
