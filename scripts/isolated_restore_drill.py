"""Restore encrypted synthetic PG backup into a different, networkless container.
This proves cloud isolation of the drill, NOT offsite custody or disaster RPO/RTO.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from psycopg import sql

from command_center.recovery import dump_database, seal, unseal
from command_center.store import ZERO, canonical, digest
from command_center.worker import docker

IMAGE = 'postgres:16-bookworm@sha256:d81f7b51697014367236d07ec58b54153fc28f828b72bf247fe5c7487520bcb0'


def run(*args, data=None):
    result = subprocess.run(['docker', '--host=unix:///var/run/docker.sock', *args],
                            input=data, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('isolated_drill_command_failed')
    return result.stdout


def main():
    started = time.monotonic()
    key = bytes.fromhex(Path('.runtime/secrets/backup_key').read_text().strip())
    archive = seal(dump_database('acc-f1-db-1'), key)
    Path('.runtime/isolated-backup.enc').write_bytes(archive)
    name = 'acc-f1-restore-' + uuid4().hex
    try:
        run('run', '--detach', '--name', name, '--network', 'none',
            '--memory', '512m', '--cpus', '0.5', '--pids-limit', '128',
            '--tmpfs', '/var/lib/postgresql/data:size=128m',
            '--env', 'POSTGRES_USER=f1_admin', '--env', 'POSTGRES_DB=restore_drill',
            '--env', 'POSTGRES_HOST_AUTH_METHOD=trust', IMAGE)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            check = docker('exec', name, 'pg_isready', '-U', 'f1_admin', '-d', 'restore_drill')
            if check.returncode == 0:
                # pg_isready also succeeds during initdb's temporary server.
                state = docker('exec', name, 'cat', '/proc/1/comm')
                if state.returncode == 0 and state.stdout.strip() == b'postgres':
                    try:
                        run('exec', name, 'psql', '-X', '-U', 'f1_admin', '-d', 'restore_drill', '-Atc', 'SELECT 1')
                        break
                    except RuntimeError:
                        pass
            time.sleep(.3)
        else:
            raise RuntimeError('isolated_restore_database_not_ready')
        # Separate instance, no network/host ports. Local trust is confined to this
        # disposable drill and never applied to the primary PostgreSQL service.
        run('exec', '-i', name, 'pg_restore', '-U', 'f1_admin', '-d', 'restore_drill',
            '--exit-on-error', '--no-owner', '--no-acl', data=unseal(archive, key))

        def query(statement):
            return run('exec', name, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U',
                       'f1_admin', '-d', 'restore_drill', '-Atc', statement).decode().strip()

        parent = query('SELECT digest FROM audit ORDER BY sequence DESC LIMIT 1')
        event = {'kind': 'isolated_restore_interlock', 'actor': 'recovery', 'task_id': None,
                 'time': datetime.now(timezone.utc).isoformat(), 'revision': os.environ['F1_SOURCE_REVISION']}
        event_literal = sql.Literal(canonical(event)).as_string()
        hash_literal = sql.Literal(digest({'previous': parent, 'event': event})).as_string()
        parent_literal = sql.Literal(parent).as_string()
        query("BEGIN; UPDATE control SET halted=true,recovery=true,epoch=epoch+1; "
              "UPDATE approvals SET revoked=true; "
              "UPDATE tasks SET state='RECONCILING' WHERE state NOT IN "
              "('SUCCEEDED','FAILED','CANCELLED','SECURITY_BLOCKED'); "
              f"INSERT INTO audit(event,previous,digest) VALUES ({event_literal}::jsonb,{parent_literal},{hash_literal}); COMMIT;")
        status = json.loads(query("SELECT json_build_object('halted',halted,'recovery',recovery) FROM control WHERE id=1"))
        if not status['halted'] or not status['recovery']:
            raise RuntimeError('isolated_restore_not_interlocked')
        if int(query("SELECT count(*) FROM approvals WHERE NOT revoked")):
            raise RuntimeError('isolated_restore_approval_rearmed')
        rows = json.loads(query('SELECT json_agg(r ORDER BY sequence) FROM (SELECT sequence,event,previous,digest FROM audit) r'))
        previous = ZERO
        for row in rows:
            if row['previous'] != previous or row['digest'] != digest({'previous': previous, 'event': row['event']}):
                raise RuntimeError('isolated_restored_audit_invalid')
            previous = row['digest']
        metadata = json.loads(run('inspect', name))[0]
        ports = metadata['NetworkSettings']['Ports'] or {}
        if metadata['HostConfig']['NetworkMode'] != 'none' or any(ports.values()):
            raise RuntimeError('isolated_restore_network_not_closed')
        result = {'revision': os.environ['F1_SOURCE_REVISION'], 'status': 'PASS',
                  'duration_seconds': round(time.monotonic() - started, 3),
                  'different_container': True, 'network': 'none', 'recovery_interlock': True,
                  'audit_rows_verified': len(rows), 'offsite_custody_verified': False,
                  'rpo_rto_proven': False}
        Path('.runtime/isolated-restore.json').write_text(json.dumps(result, indent=2) + '\n')
        print('Encrypted backup → different networkless PostgreSQL container → interlock/audit: PASS')
    finally:
        docker('rm', '--force', name)


if __name__ == '__main__':
    main()
