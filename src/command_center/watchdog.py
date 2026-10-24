"""Separate process, no worker dependency. Same host/runtime remains a shared failure domain."""
import os
import argparse
import time

from .config import Settings
from .models import Control
from .runtime_ledger import RuntimeLedger
from .runtime_policy import RuntimeBackend, RuntimeLimits
from .store import Store
from .store import Denied
from .worker import Runner


class Watchdog:
    def __init__(self, store, ledger, backend, limits=None):
        backend.preflight()
        self.store, self.ledger = store, ledger
        self.limits = limits or RuntimeLimits()
        self.runner = Runner(store, backend, self.limits)
        self.last_worker_state = None
        self.started_at = time.monotonic()

    def emergency(self, row, reason):
        self.ledger.record('watchdog_emergency', task_id=row['id'], fence=row['fence'], reason=reason)
        self.ledger.stop_attempt(row['id'], row['fence'])
        if row['phase'] == 'INTENT':
            # An absent container with an in-flight create is NOT proof of no effect.
            self.ledger.phase(row['id'], row['fence'], 'UNCERTAIN')
        try:
            with self.ledger.launch_lock(blocking=False):
                self.ledger.phase(row['id'], row['fence'], 'STOPPING')
                confirmed = self.runner.stop(row['name'])
        except BlockingIOError:
            self.runner.stop(row['name'])
            confirmed = False
        if not row['observed']:
            confirmed = False
        self.ledger.record('watchdog_stop_result', task_id=row['id'], fence=row['fence'], confirmed=confirmed)
        self.ledger.phase(row['id'], row['fence'], 'STOPPED' if confirmed else 'UNCERTAIN')
        try:
            self.store.abort(row['id'], row['fence'], 'watchdog_' + reason, confirmed)
            if confirmed:
                self.ledger.phase(row['id'], row['fence'], 'DONE')
            with self.store.transaction() as session:
                session.get(Control, 1).halted = True
                self.store.check_audit(session)
                self.store.audit(session, 'watchdog_stop', 'watchdog', row['id'], confirmed=confirmed, reason=reason)
        except Exception:
            # Durable local evidence survives missing PG; no authority to resume.
            self.ledger.watchdog(False)

    def tick(self):
        self.ledger.verify()
        worker_alive = self.ledger.worker_fresh(self.store.settings.source_revision, self.limits.heartbeat_seconds)
        if worker_alive != self.last_worker_state and (worker_alive or time.monotonic() - self.started_at > 5):
            self.ledger.record('worker_online' if worker_alive else 'worker_heartbeat_missing')
            if not worker_alive:
                try:
                    with self.store.transaction() as session:
                        self.store.check_audit(session)
                        self.store.audit(session, 'worker_heartbeat_missing', 'watchdog')
                except Exception:
                    pass
            self.last_worker_state = worker_alive
        healthy = True
        for row in self.ledger.runs():
            reason = None
            now = time.time()
            try:
                snapshot = self.store.snapshot()
                task = self.store.get(row['id'])
                with self.store.transaction() as session:
                    current = self.store.task(session, row['id'])
                    lost = current.lease_until is None or current.lease_until <= self.store.now(session)
                if snapshot['halted'] or snapshot['recovery'] or task['state'] in {'CANCEL_REQUESTED', 'CANCELLED', 'RECONCILING', 'SECURITY_BLOCKED'}:
                    reason = 'revoked_or_cancelled'
                elif task['fence'] != row['fence'] or lost:
                    reason = 'lease_or_fence_lost'
            except Exception:
                reason = 'database_or_audit_unavailable'
            if now >= row['deadline']:
                reason = 'wall_deadline'
            if now - row['heartbeat'] > self.limits.heartbeat_seconds or now < row['heartbeat']:
                reason = 'worker_heartbeat_lost'
            if row['phase'] in {'UNCERTAIN', 'STOPPED', 'STOPPING'}:
                reason = 'outcome_uncertain'
            if reason:
                healthy = False
                if row['stops'] < self.limits.stop_attempts:
                    try:
                        self.emergency(row, reason)
                    except Exception:
                        self.ledger.phase(row['id'], row['fence'], 'UNCERTAIN')
                        self.ledger.record('watchdog_stop_unconfirmed', task_id=row['id'], fence=row['fence'])
        self.ledger.watchdog(healthy)

    def reconcile_confirmed(self, task_id, fence):
        """Trusted operator only; does NOT resume or grant another attempt."""
        row = self.ledger.get(task_id, fence)
        if not row['observed'] or row['phase'] not in {'UNCERTAIN', 'STOPPED'}:
            raise Denied('manual_investigation_required')
        with self.ledger.launch_lock(blocking=False):
            if not self.runner.stop(row['name']):
                raise Denied('runtime_stop_unconfirmed')
            self.store.abort(task_id, fence, 'verified_no_effect', True)
            with self.store.transaction() as session:
                session.get(Control, 1).halted = True
                self.store.check_audit(session)
                self.store.audit(session, 'runtime_operator_reconciled', 'operator', task_id, fence=fence)
            self.ledger.phase(task_id, fence, 'DONE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reconcile-task')
    parser.add_argument('--fence', type=int)
    args = parser.parse_args()
    settings = Settings.load(identities_required=False)
    watchdog = Watchdog(Store(settings), RuntimeLedger(os.environ['F1_RUNTIME_LEDGER']), RuntimeBackend(), RuntimeLimits.load())
    if args.reconcile_task:
        if not args.fence or args.fence < 1:
            parser.error('exact positive --fence required')
        watchdog.reconcile_confirmed(args.reconcile_task, args.fence)
        print('Runtime absence verified; admission remains halted; no task resumed.')
        return
    while True:
        try:
            watchdog.tick()
        except Exception:
            watchdog.ledger.watchdog(False)
        time.sleep(.5)


if __name__ == '__main__':
    main()
