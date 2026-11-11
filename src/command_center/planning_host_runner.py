"""Broker-owned bounded HTTP operation; no executor container or credential handoff."""
from threading import Event, Thread
import time

from sqlalchemy import select

from .live_planning_gateway import LivePlanningGateway
from .models import ExternalAction
from .store import Denied


class PlanningHostRunner:
    def __init__(self, store, ledger, backend, limits, host):
        self.store, self.ledger, self.backend, self.limits, self.host = store, ledger, backend, limits, host

    def execute(self, task):
        stop, revoked = Event(), Event()
        gateway, pulse = None, None
        failed = False
        try:
            self.host.preflight(self.store, self.ledger, self.backend)
            with self.ledger.launch_lock():
                row = self.ledger.get(task['id'], task['fence'])
                if (row['kind'] != 'planning_http' or row['phase'] != 'INTENT'
                        or row['deadline'] <= time.time() or not self.ledger.watchdog_ready(self.limits.watchdog_seconds)
                        or not self.ledger.worker_fresh(self.store.settings.source_revision, self.limits.heartbeat_seconds)):
                    raise Denied('planning_runtime_admission_revoked')
                self.ledger.phase(task['id'], task['fence'], 'ACTIVE')

            def guard(binding):
                return not revoked.is_set() and self.host.guard(binding, self.store, self.ledger,
                                                               self.backend, self.limits, task)

            def heartbeat():
                while not stop.wait(min(1, self.limits.heartbeat_seconds / 3)):
                    try:
                        if not self.store.pulse(task['id'], task['fence']):
                            raise Denied('planning_lease_revoked')
                        self.ledger.beat(task['id'], task['fence'])
                    except Exception:
                        revoked.set()
                        try:
                            self.ledger.phase(task['id'], task['fence'], 'UNCERTAIN')
                        except Exception:
                            pass
                        return

            pulse = Thread(target=heartbeat, daemon=True)
            pulse.start()
            gateway = LivePlanningGateway(self.store, runtime_guard=guard)
            gateway.perform(task['id'], task['fence'])
        except Exception:
            failed = True
        finally:
            stop.set()
            if pulse:
                pulse.join(timeout=5)
            closed = False
            try:
                if gateway:
                    gateway.close()
                if pulse is None or not pulse.is_alive():
                    self.ledger.planning_returned(task['id'], task['fence'])
                    closed = True
            except Exception:
                pass
            try:
                if failed:
                    with self.store.transaction() as session:
                        self.store.check_audit(session)
                        actions = session.scalars(select(ExternalAction).where(ExternalAction.task_id == task['id'])).all()
                        if gateway:
                            gateway.check_ledger(session, actions)
                        unknown = any(a.state != 'COMPLETE' for a in actions)
                    self.store.abort(task['id'], task['fence'], 'planning_operation_stopped', closed and not unknown,
                                     usage_unknown=unknown)
                state = self.store.get(task['id'])['state']
                self.ledger.phase(task['id'], task['fence'], 'DONE' if closed and state in
                    {'SUCCEEDED', 'FAILED', 'CANCELLED'} else 'UNCERTAIN')
            except Exception:
                self.ledger.phase(task['id'], task['fence'], 'UNCERTAIN')
