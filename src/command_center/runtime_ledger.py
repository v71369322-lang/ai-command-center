"""Durable local runtime evidence; same-host custody, never an offsite proof."""
from contextlib import contextmanager
import hashlib
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import time


class RuntimeLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            if self.path.is_symlink():
                raise ValueError('runtime_ledger_symlink_forbidden') from None
        with self.tx() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS runs(
                id TEXT PRIMARY KEY, fence INTEGER, name TEXT, phase TEXT,
                deadline REAL, heartbeat REAL, revision TEXT, stops INTEGER DEFAULT 0,
                observed INTEGER NOT NULL DEFAULT 0)''')
            db.execute('CREATE TABLE IF NOT EXISTS monitor(id INTEGER PRIMARY KEY, heartbeat REAL, healthy INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS worker_monitor(id INTEGER PRIMARY KEY, heartbeat REAL, revision TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS evidence(seq INTEGER PRIMARY KEY, event TEXT, previous TEXT, digest TEXT)')
            if 'observed' not in {r[1] for r in db.execute('PRAGMA table_info(runs)')}:
                db.execute('ALTER TABLE runs ADD COLUMN observed INTEGER NOT NULL DEFAULT 0')
            columns = {r[1] for r in db.execute('PRAGMA table_info(runs)')}
            if 'kind' not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN kind TEXT NOT NULL DEFAULT 'container'")
            if 'returned' not in columns:
                db.execute('ALTER TABLE runs ADD COLUMN returned INTEGER NOT NULL DEFAULT 0')

    @contextmanager
    def launch_lock(self, blocking=True):
        fd = os.open(str(self.path) + '.launch-lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            yield
        finally:
            os.close(fd)

    @contextmanager
    def tx(self):
        with sqlite3.connect(self.path, timeout=3) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db

    @staticmethod
    def event(db, kind, **fields):
        last = db.execute('SELECT digest FROM evidence ORDER BY seq DESC LIMIT 1').fetchone()
        parent = last[0] if last else '0' * 64
        value = json.dumps({'kind': kind, 'time': time.time(), **fields}, sort_keys=True)
        checksum = hashlib.sha256((parent + value).encode()).hexdigest()
        db.execute('INSERT INTO evidence(event,previous,digest) VALUES(?,?,?)', (value, parent, checksum))

    def record(self, kind, **fields):
        with self.tx() as db:
            self.event(db, kind, **fields)

    def watchdog(self, healthy=True):
        with self.tx() as db:
            db.execute('INSERT OR REPLACE INTO monitor VALUES(1,?,?)', (time.time(), int(healthy)))

    def watchdog_ready(self, ttl=10):
        with self.tx() as db:
            row = db.execute('SELECT * FROM monitor WHERE id=1').fetchone()
            return bool(row and row['healthy'] and 0 <= time.time() - row['heartbeat'] <= ttl)

    def register(self, task, name, seconds, *, kind='container'):
        if kind not in {'container', 'planning_http'}:
            raise ValueError('unknown_runtime_kind')
        with self.tx() as db:
            if db.execute("SELECT 1 FROM runs WHERE phase != 'DONE'").fetchone():
                raise ValueError('runtime_admission_blocked')
            if db.execute('SELECT 1 FROM runs WHERE id=? AND fence>=?', (task['id'], task['fence'])).fetchone():
                raise ValueError('runtime_replay')
            db.execute('INSERT OR REPLACE INTO runs(id,fence,name,phase,deadline,heartbeat,revision,stops,observed,kind,returned) VALUES(?,?,?,?,?,?,?,0,0,?,0)',
                       (task['id'], task['fence'], name, 'INTENT', time.time() + seconds,
                        time.time(), task['revision'], kind))
            self.event(db, 'launch_registered', task_id=task['id'], fence=task['fence'], revision=task['revision'], operation_kind=kind)

    def planning_returned(self, task_id, fence):
        """Only trusted runner calls this after its HTTP client and pulse thread have closed."""
        with self.tx() as db:
            row = db.execute('SELECT kind,returned FROM runs WHERE id=? AND fence=?', (task_id, fence)).fetchone()
            if not row or row['kind'] != 'planning_http':
                raise ValueError('planning_runtime_required')
            if not row['returned']:
                db.execute('UPDATE runs SET returned=1 WHERE id=? AND fence=?', (task_id, fence))
                self.event(db, 'planning_operation_returned', task_id=task_id, fence=fence)

    def runs(self):
        with self.tx() as db:
            return [dict(r) for r in db.execute("SELECT * FROM runs WHERE phase != 'DONE'")]

    def get(self, task_id, fence):
        with self.tx() as db:
            row = db.execute('SELECT * FROM runs WHERE id=? AND fence=?', (task_id, fence)).fetchone()
            if not row:
                raise ValueError('unknown_runtime_run')
            return dict(row)

    def phase(self, task_id, fence, phase):
        with self.tx() as db:
            row = db.execute('SELECT phase FROM runs WHERE id=? AND fence=?', (task_id, fence)).fetchone()
            if not row:
                raise ValueError('unknown_runtime_run')
            if row[0] in {'STOPPING', 'UNCERTAIN', 'DONE'} and phase == 'ACTIVE':
                raise ValueError('runtime_revoked')
            db.execute('UPDATE runs SET phase=?,observed=CASE WHEN ?=1 THEN 1 ELSE observed END WHERE id=? AND fence=?',
                       (phase, int(phase == 'ACTIVE'), task_id, fence))
            self.event(db, 'runtime_' + phase.lower(), task_id=task_id, fence=fence)

    def next_stage(self, task_id, fence):
        # Caller holds launch_lock and has proved previous container absent.
        with self.tx() as db:
            row = db.execute('SELECT * FROM runs WHERE id=? AND fence=?', (task_id, fence)).fetchone()
            if not row or row['phase'] != 'ACTIVE' or not row['observed'] or row['deadline'] <= time.time():
                raise ValueError('runtime_stage_revoked')
            db.execute("UPDATE runs SET phase='INTENT',observed=0 WHERE id=? AND fence=?", (task_id, fence))
            self.event(db, 'verification_launch_intent', task_id=task_id, fence=fence)

    def beat(self, task_id, fence):
        with self.tx() as db:
            db.execute("UPDATE runs SET heartbeat=? WHERE id=? AND fence=? AND phase IN ('INTENT','ACTIVE')",
                       (time.time(), task_id, fence))

    def worker_beat(self, revision):
        with self.tx() as db:
            db.execute('INSERT OR REPLACE INTO worker_monitor VALUES(1,?,?)', (time.time(), revision))

    def worker_fresh(self, revision, ttl):
        with self.tx() as db:
            row = db.execute('SELECT * FROM worker_monitor WHERE id=1').fetchone()
            return bool(row and row['revision'] == revision and 0 <= time.time() - row['heartbeat'] <= ttl)

    def stop_attempt(self, task_id, fence):
        with self.tx() as db:
            db.execute('UPDATE runs SET stops=stops+1 WHERE id=? AND fence=?', (task_id, fence))
            self.event(db, 'stop_attempt', task_id=task_id, fence=fence)

    def verify(self):
        parent = '0' * 64
        kinds, returned = {}, set()
        with self.tx() as db:
            for row in db.execute('SELECT * FROM evidence ORDER BY seq'):
                if row['previous'] != parent or row['digest'] != hashlib.sha256((parent + row['event']).encode()).hexdigest():
                    raise ValueError('runtime_evidence_corrupt')
                parent = row['digest']
                event = json.loads(row['event'])
                key = (event.get('task_id'), event.get('fence'))
                if event['kind'] == 'launch_registered':
                    kinds[key] = event.get('operation_kind', 'container')
                elif event['kind'] == 'planning_operation_returned':
                    returned.add(key)
            columns = {r[1] for r in db.execute('PRAGMA table_info(runs)')}
            if ('kind' in columns) != ('returned' in columns):
                raise ValueError('runtime_operation_schema_incomplete')
            projection = 'kind,returned' if 'kind' in columns else "'container' AS kind,0 AS returned"
            for row in db.execute('SELECT id,fence,' + projection + ' FROM runs'):
                key = (row['id'], row['fence'])
                if (row['kind'] != kinds.get(key) or row['returned'] != int(key in returned)
                        or row['kind'] not in {'container', 'planning_http'}):
                    raise ValueError('runtime_operation_evidence_corrupt')
        return parent
