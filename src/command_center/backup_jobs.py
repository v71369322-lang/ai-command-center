"""Automated local encrypted backup jobs; external custody adapter boundary is explicit."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import fcntl
import json
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .config import Settings
from .recovery import dump_database, restore_database, seal, unseal
from .store import Store


class Repository(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...


class LocalRepository:
    """Append-only at application level; host admin can tamper. NOT offsite."""
    def __init__(self, directory, quota_mib=256):
        self.directory = Path(directory)
        if type(quota_mib) is not int or not 16 <= quota_mib <= 4096:
            raise ValueError('unsafe_backup_quota')
        self.quota = quota_mib * 1024 * 1024
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    def path(self, key):
        if not key or len(key) > 100 or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_.' for c in key):
            raise ValueError('invalid_repository_key')
        if key.startswith('.'):
            raise ValueError('invalid_repository_key')
        return self.directory / key

    def put(self, key, data):
        fd = os.open(self.directory / '.quota-lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._put(key, data)
        finally:
            os.close(fd)

    def _put(self, key, data):
        used = sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file())
        if used + len(data) > self.quota:
            raise ValueError('backup_repository_quota')
        fd = os.open(self.path(key), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def get(self, key):
        path = self.path(key)
        if path.is_symlink() or path.stat().st_size > 96 * 1024 * 1024:
            raise ValueError('backup_size_limit')
        return path.read_bytes()


class BackupJobs:
    def __init__(self, store, repository: Repository, key, state_dir, container='acc-f1-db-1'):
        if len(key) != 32:
            raise ValueError('aes256_key_required')
        self.store, self.repository, self.key, self.container = store, repository, key, container
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def audit(self, kind, **details):
        with self.store.transaction() as session:
            self.store.check_audit(session)
            self.store.audit(session, kind, 'backup_operator', **details)

    def backup(self):
        try:
            return self._backup()
        except Exception:
            try:
                self.audit('backup_failed')
            except Exception:
                pass
            raise

    def _backup(self):
        self.audit('backup_started')
        anchor = self.store.checkpoint()
        dump = dump_database(self.container)
        manifest = {'schema': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'revision': self.store.settings.source_revision, 'anchor': anchor,
                    'dump_sha256': hashlib.sha256(dump).hexdigest(),
                    'dump': base64.b64encode(dump).decode()}
        archive = seal(json.dumps(manifest, sort_keys=True).encode(), self.key)
        name = 'backup_' + uuid4().hex + '.enc'
        self.repository.put(name, archive)
        # Acknowledged repository write is verified by read-back+authentication.
        self.decode(self.repository.get(name))
        receipt = {'name': name, 'created_at': manifest['created_at'], 'anchor': anchor,
                   'archive_sha256': hashlib.sha256(archive).hexdigest(), 'offsite_verified': False}
        self.audit('backup_verified', archive_hash=receipt['archive_sha256'], checkpoint=anchor)
        pending = self.state_dir / ('receipt_' + uuid4().hex + '.json')
        fd = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(receipt, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(pending, self.state_dir / 'latest.json')
        return receipt

    def decode(self, archive):
        data = json.loads(unseal(archive, self.key))
        dump = base64.b64decode(data['dump'], validate=True)
        if data.get('schema') != 1 or len(dump) > 64 * 1024 * 1024 or hashlib.sha256(dump).hexdigest() != data['dump_sha256']:
            raise ValueError('backup_manifest_invalid')
        return data, dump

    def status(self, max_age_seconds=900, now=None):
        try:
            receipt = json.loads((self.state_dir / 'latest.json').read_text())
            archive = self.repository.get(receipt['name'])
            if hashlib.sha256(archive).hexdigest() != receipt['archive_sha256']:
                raise ValueError('backup_checksum_mismatch')
            manifest, _ = self.decode(archive)
            created = datetime.fromisoformat(manifest['created_at'])
            age = ((now or datetime.now(timezone.utc)) - created).total_seconds()
            return {'state': 'VERIFIED_LOCAL' if 0 <= age <= max_age_seconds else 'STALE_OR_CLOCK_ERROR',
                    'age_seconds': age, 'offsite_verified': False, 'rpo_proven': False}
        except FileNotFoundError:
            return {'state': 'MISSING', 'offsite_verified': False}
        except Exception:
            return {'state': 'CORRUPT_OR_UNAVAILABLE', 'offsite_verified': False}

    def restore(self, name, target, admin_settings):
        try:
            self.audit('restore_started')
            return self._restore(name, target, admin_settings)
        except Exception:
            try:
                self.audit('restore_failed')
            except Exception:
                pass
            raise

    def _restore(self, name, target, admin_settings):
        manifest, dump = self.decode(self.repository.get(name))
        restored = restore_database(self.container, target, dump, admin_settings)
        try:
            with restored.transaction() as session:
                restored.check_audit(session, manifest['anchor'])
            result = restored.snapshot()
            if not result['halted'] or not result['recovery']:
                raise ValueError('restore_interlock_missing')
            self.audit('restore_verified', target=target, checkpoint=manifest['anchor'])
            return {'state': 'VERIFIED_QUARANTINED', 'target': target, 'offsite_verified': False}
        finally:
            restored.engine.dispose()

    def checkpoint(self):
        anchor = self.store.checkpoint()
        name = 'checkpoint_' + uuid4().hex + '.json'
        self.repository.put(name, json.dumps(anchor, sort_keys=True).encode())
        self.audit('checkpoint_exported', checkpoint=anchor)
        return {'name': name, 'anchor': anchor, 'offsite_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['backup', 'status', 'checkpoint'])
    parser.add_argument('--repository', required=True)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--key-file', required=True)
    args = parser.parse_args()
    store = Store(Settings.load())
    jobs = BackupJobs(store, LocalRepository(args.repository),
                      bytes.fromhex(Path(args.key_file).read_text().strip()), args.state_dir)
    try:
        result = jobs.backup() if args.mode == 'backup' else jobs.status() if args.mode == 'status' else jobs.checkpoint()
    except Exception:
        try:
            jobs.audit('backup_job_failed', mode=args.mode)
        except Exception:
            pass
        parser.exit(1, 'backup_job_failed; no successful receipt created\n')
    print(json.dumps(result, indent=2))
    if args.mode == 'status' and result['state'] != 'VERIFIED_LOCAL':
        parser.exit(1)


if __name__ == '__main__':
    main()
