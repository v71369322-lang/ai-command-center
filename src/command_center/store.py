import hashlib
import json
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session

from .config import Settings
from .models import Approval, Audit, Base, Control, Outbox, Task

ZERO = "0" * 64
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "SECURITY_BLOCKED"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Denied(Exception):
    pass


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        if not str(settings.database_url).startswith("postgresql"):
            raise RuntimeError("PostgreSQL is mandatory")
        self.engine = create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True,
                                    connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000 -c lock_timeout=3000"})

    def initialize(self):
        """Explicit bootstrap command only; API never creates schema."""
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as s, s.begin():
            if s.get(Control, 1) is None:
                s.add(Control(id=1))
                s.flush()
                self.audit(s, "bootstrap", "system")

    @contextmanager
    def transaction(self):
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            # Single-owner F1: one global admission lock also serializes audit chain.
            session.execute(select(Control).where(Control.id == 1).with_for_update()).scalar_one()
            yield session

    @staticmethod
    def now(s):
        return s.execute(text("SELECT clock_timestamp()")).scalar_one()

    def audit(self, s, kind, actor, task=None, **details):
        previous = s.execute(select(Audit).order_by(Audit.sequence.desc()).limit(1)).scalar_one_or_none()
        event = {"kind": kind, "actor": actor, "task_id": task,
                 "time": self.now(s).isoformat(), "revision": self.settings.source_revision, **details}
        parent = previous.digest if previous else ZERO
        s.add(Audit(event=event, previous=parent, digest=digest({"previous": parent, "event": event})))
        s.flush()

    @staticmethod
    def task(s, task_id):
        task = s.get(Task, task_id)
        if task is None:
            raise Denied("task_not_found")
        return task

    def create(self, actor, key, payload):
        if actor not in {"owner", "operator"}:
            raise Denied("role_forbidden")
        if payload.get("kind") not in {"render", "approved_render"}:
            raise Denied("unknown_action")
        known_secrets = [*self.settings.identities.values(), self.settings.redis_password,
                         self.settings.database_url.password]
        encoded = canonical(payload) + key
        if any(value and value in encoded for value in known_secrets):
            raise Denied("secret_content_forbidden")
        scoped_key = actor + ":" + key
        fingerprint = digest(payload)
        with self.transaction() as s:
            control = s.get(Control, 1)
            previous = s.execute(select(Task).where(Task.request_key == scoped_key)).scalar_one_or_none()
            if previous:
                if previous.payload_hash != fingerprint:
                    raise Denied("idempotency_conflict")
                return self.view(previous)
            if control.halted or control.recovery:
                raise Denied("control_blocked")
            if s.execute(select(func.count()).select_from(Task).where(Task.state.not_in(TERMINAL))).scalar_one() >= 100:
                raise Denied("pending_task_limit")
            if s.execute(text("SELECT pg_database_size(current_database())")).scalar_one() > 64 * 1024 * 1024:
                raise Denied("database_resource_limit")
            dependency = payload.get("dependency")
            if dependency:
                self.task(s, dependency)
            task = Task(id=str(uuid4()), request_key=scoped_key, payload_hash=fingerprint,
                        payload=payload, state="WAITING_APPROVAL" if payload["kind"] == "approved_render"
                        else "READY", version=1, epoch=control.epoch, owner_role=actor,
                        created_at=self.now(s), dependency=dependency, attempts=0, fence=0, reserved=0)
            s.add(task)
            s.flush()
            self.audit(s, "task_created", actor, task.id, payload_hash=fingerprint)
            if task.state == "READY":
                s.add(Outbox(id=str(uuid4()), task_id=task.id))
            return self.view(task)

    def approve(self, actor, task_id, version, seconds=120):
        if actor != "owner":
            raise Denied("owner_required")
        with self.transaction() as s:
            control = s.get(Control, 1)
            task = self.task(s, task_id)
            if (control.halted or control.recovery or task.epoch != control.epoch
                    or task.version != version or task.state != "WAITING_APPROVAL"):
                raise Denied("stale_or_ineligible_approval")
            old = s.get(Approval, task_id)
            if old:
                s.delete(old)
                s.flush()
            expires_at = self.now(s) + timedelta(seconds=seconds)
            s.add(Approval(task_id=task.id, task_version=task.version, payload_hash=task.payload_hash,
                           epoch=control.epoch, expires_at=expires_at,
                           used=False, revoked=False))
            task.state = "READY"
            s.add(Outbox(id=str(uuid4()), task_id=task.id))
            self.audit(s, "approved", actor, task.id, version=version,
                       payload_hash=task.payload_hash, epoch=control.epoch, expires_at=expires_at.isoformat())
            return self.view(task)

    def cancel(self, actor, task_id, revoke=False):
        if actor not in {"owner", "operator"} or (revoke and actor != "owner"):
            raise Denied("role_forbidden")
        with self.transaction() as s:
            task = self.task(s, task_id)
            if actor == "operator" and task.owner_role != actor:
                raise Denied("not_task_owner")
            approval = s.get(Approval, task_id)
            if approval:
                approval.revoked = True
            if task.state not in TERMINAL:
                task.state = "CANCEL_REQUESTED" if task.state in {"RUNNING", "VERIFYING", "RECONCILING"} else "CANCELLED"
                task.version += 1
            self.audit(s, "approval_revoked" if revoke else "cancel_requested", actor, task.id)
            return self.view(task)

    def dispatch(self, broker):
        with self.transaction() as s:
            control = s.get(Control, 1)
            if control.halted or control.recovery:
                return 0
            events = s.execute(select(Outbox).where(Outbox.sent_at.is_(None)).limit(100)).scalars().all()
            for event in events:
                # Publish before marking; a crash can redeliver. PG claim is authoritative.
                broker.lpush("f1:work", canonical({"event_id": event.id, "task_id": event.task_id}))
                event.sent_at = self.now(s)
            return len(events)

    def claim(self, task_id):
        with self.transaction() as s:
            control = s.get(Control, 1)
            task = self.task(s, task_id)
            self.check_audit(s)
            if control.halted or control.recovery or task.epoch != control.epoch or task.state != "READY":
                return None
            active = s.execute(select(Task).where(Task.state.in_(["RUNNING", "VERIFYING", "CANCEL_REQUESTED", "RECONCILING"]))).first()
            if active:
                return None
            if task.dependency and self.task(s, task.dependency).state != "SUCCEEDED":
                return None
            if task.attempts >= self.settings.max_attempts:
                task.state, task.reason = "FAILED", "attempt_limit"
                self.audit(s, "attempt_limit", "policy", task.id)
                return None
            if task.payload["kind"] == "approved_render":
                a = s.get(Approval, task.id)
                if (not a or a.used or a.revoked or a.expires_at <= self.now(s)
                        or a.task_version != task.version or a.payload_hash != task.payload_hash
                        or a.epoch != control.epoch):
                    task.state = "WAITING_APPROVAL"
                    self.audit(s, "approval_rejected", "policy", task.id)
                    return None
            charge = task.payload["cost"]
            committed = control.actual + control.reserved
            if charge and (committed + charge > control.budget_limit - control.protected
                           or max(committed, control.forecast) + charge >= control.budget_limit * 9 // 10):
                task.state, task.reason = "FAILED", "budget_limit"
                self.audit(s, "budget_blocked", "policy", task.id)
                return None
            if task.payload["kind"] == "approved_render":
                a.used = True
            control.reserved += charge
            task.reserved = charge
            task.attempts += 1
            task.fence += 1
            task.lease_until = self.now(s) + timedelta(seconds=self.settings.lease_seconds)
            task.state = "RUNNING"
            self.audit(s, "claimed", "worker", task.id, fence=task.fence, reserved=charge)
            return self.view(task)

    def pulse(self, task_id, fence):
        with self.transaction() as s:
            task, control = self.task(s, task_id), s.get(Control, 1)
            if (control.halted or control.recovery or task.state != "RUNNING" or task.fence != fence
                    or task.epoch != control.epoch or task.lease_until <= self.now(s)):
                return False
            a = s.get(Approval, task.id)
            if a and (a.revoked or a.expires_at <= self.now(s) or a.task_version != task.version):
                task.state = "CANCEL_REQUESTED"
                return False
            task.lease_until = self.now(s) + timedelta(seconds=self.settings.lease_seconds)
            return True

    def finish(self, task_id, fence, artifact, artifact_hash):
        with self.transaction() as s:
            task, control = self.task(s, task_id), s.get(Control, 1)
            if (control.halted or control.recovery or task.fence != fence or task.state != "RUNNING"
                    or task.lease_until <= self.now(s) or task.epoch != control.epoch):
                raise Denied("stale_result")
            a = s.get(Approval, task.id)
            if a and (a.revoked or a.expires_at <= self.now(s) or a.task_version != task.version):
                raise Denied("stale_approval")
            task.artifact, task.artifact_hash = artifact, artifact_hash
            task.state = "SUCCEEDED"
            control.reserved -= task.reserved
            control.actual += task.reserved
            task.reserved = 0
            self.audit(s, "verified", "verifier", task.id, fence=fence, artifact_hash=artifact_hash)

    def abort(self, task_id, fence, reason, stopped):
        with self.transaction() as s:
            task, control = self.task(s, task_id), s.get(Control, 1)
            if task.fence != fence or task.state in TERMINAL:
                return
            if not stopped:
                task.state = "RECONCILING"
                control.halted = True
            elif task.state == "CANCEL_REQUESTED" or control.halted:
                task.state = "CANCELLED"
            else:
                task.state = "FAILED"
            task.reason = reason
            if stopped:
                control.reserved -= task.reserved
                task.reserved = 0
            self.audit(s, "execution_stopped" if stopped else "outcome_uncertain", "worker", task.id, reason=reason)

    def recover(self):
        """Mark expired runs uncertain. Never replay them automatically."""
        with self.transaction() as s:
            expired = s.execute(select(Task).where(Task.state.in_(["RUNNING", "CANCEL_REQUESTED"]),
                                                   Task.lease_until <= self.now(s))).scalars().all()
            for task in expired:
                # Cancellation is an irreversible intent, not a retryable run failure.
                if task.state != "CANCEL_REQUESTED":
                    task.state = "RECONCILING"
                if task.reason != "expired_lease":
                    self.audit(s, "reconciliation_required", "worker", task.id, fence=task.fence)
                task.reason = "expired_lease"
            # Reconstruct lost transport at a bounded interval; never grow Outbox per poll.
            for task in s.execute(select(Task).where(Task.state == "READY")).scalars():
                if task.dependency and self.task(s, task.dependency).state != "SUCCEEDED":
                    continue
                latest = s.execute(select(Outbox).where(Outbox.task_id == task.id)).scalars().all()
                if not latest:
                    s.add(Outbox(id=str(uuid4()), task_id=task.id))
                elif all(event.sent_at and event.sent_at + timedelta(seconds=5) <= self.now(s) for event in latest):
                    latest[0].sent_at = None
            return [self.view(t) for t in expired]

    def reconciliation_tasks(self):
        with self.transaction() as s:
            return [self.view(t) for t in s.execute(select(Task).where(Task.state.in_(["RECONCILING", "CANCEL_REQUESTED"]))).scalars()]

    def halt(self, actor):
        if actor != "owner":
            raise Denied("owner_required")
        with self.transaction() as s:
            control = s.get(Control, 1)
            control.halted = True
            control.epoch += 1
            for approval in s.execute(select(Approval)).scalars():
                approval.revoked = True
            for task in s.execute(select(Task).where(Task.state.not_in(TERMINAL))).scalars():
                task.state = "CANCEL_REQUESTED" if task.state in {"RUNNING", "RECONCILING", "CANCEL_REQUESTED"} else "CANCELLED"
                task.version += 1
            self.audit(s, "kill_switch", actor, epoch=control.epoch)

    def resume(self, actor, epoch, checkpoint_digest):
        if actor != "owner":
            raise Denied("owner_required")
        with self.transaction() as s:
            self.check_audit(s)
            c = s.get(Control, 1)
            last = s.execute(select(Audit).order_by(Audit.sequence.desc()).limit(1)).scalar_one()
            if c.recovery or not c.halted or c.epoch != epoch or last.digest != checkpoint_digest:
                raise Denied("stale_or_recovery_resume")
            active = s.execute(select(Task).where(Task.state.in_([
                "RUNNING", "VERIFYING", "RECONCILING", "CANCEL_REQUESTED", "SECURITY_BLOCKED"]))).first()
            if active:
                raise Denied("unreconciled_resume")
            for task in s.execute(select(Task).where(Task.state.not_in(TERMINAL))).scalars():
                task.state = "CANCELLED"
                task.version += 1
            for approval in s.execute(select(Approval)).scalars():
                approval.revoked = True
            c.halted = False
            c.epoch += 1
            self.audit(s, "normal_stop_resumed", actor, epoch=c.epoch)

    def security_trip(self, task_id, fence):
        with self.transaction() as s:
            task = self.task(s, task_id)
            if task.fence != fence:
                raise Denied("stale_security_report")
            control = s.get(Control, 1)
            control.halted = True
            control.recovery = True
            control.epoch += 1
            task.state = "SECURITY_BLOCKED"
            task.reason = "isolation_policy_mismatch"
            self.audit(s, "isolation_compromise", "policy", task.id, fence=fence)

    def retry(self, actor, task_id):
        if actor != "owner":
            raise Denied("owner_required")
        with self.transaction() as s:
            task, control = self.task(s, task_id), s.get(Control, 1)
            if (control.halted or control.recovery or task.state != "FAILED" or task.reserved
                    or task.attempts >= self.settings.max_attempts or task.reason != "verified_no_effect"):
                raise Denied("retry_not_safe")
            task.version += 1
            task.state = "WAITING_APPROVAL" if task.payload["kind"] == "approved_render" else "READY"
            if task.state == "READY":
                s.add(Outbox(id=str(uuid4()), task_id=task.id))
            self.audit(s, "retry_authorized", actor, task.id)
            return self.view(task)

    def checkpoint(self):
        with self.transaction() as s:
            self.check_audit(s)
            last = s.execute(select(Audit).order_by(Audit.sequence.desc()).limit(1)).scalar_one()
            return {"sequence": last.sequence, "digest": last.digest, "revision": self.settings.source_revision}

    def check_audit(self, s, anchor=None):
        previous, seen = ZERO, False
        for row in s.execute(select(Audit).order_by(Audit.sequence)
                             .execution_options(yield_per=256)).scalars():
            if row.previous != previous or row.digest != digest({"previous": previous, "event": row.event}):
                raise Denied("audit_integrity_failure")
            previous = row.digest
            if anchor and row.sequence == anchor["sequence"]:
                if row.digest != anchor["digest"]:
                    raise Denied("checkpoint_mismatch")
                seen = True
        if anchor and not seen:
            raise Denied("checkpoint_missing_or_rollback")
        return True

    def snapshot(self):
        with self.transaction() as s:
            c = s.get(Control, 1)
            self.check_audit(s)
            used = max(c.actual + c.reserved, c.forecast)
            return {"halted": c.halted, "recovery": c.recovery, "epoch": c.epoch,
                    "checkpoint_digest": s.execute(select(Audit.digest).order_by(Audit.sequence.desc()).limit(1)).scalar_one(),
                    "budget": {"synthetic": True, "actual": c.actual, "reserved": c.reserved,
                               "forecast": c.forecast, "uncertain": sum(t.reserved for t in s.execute(select(Task).where(Task.state.in_(["RECONCILING", "SECURITY_BLOCKED", "CANCEL_REQUESTED"]))).scalars()), "limit": c.budget_limit,
                               "threshold": 100 if used >= c.budget_limit else 90 if used >= c.budget_limit * .9
                               else 70 if used >= c.budget_limit * .7 else 0},
                    "tasks": [self.view(t) for t in s.execute(select(Task).order_by(Task.created_at.desc()).limit(100)).scalars()],
                    "events": [{"sequence": e.sequence, "event": e.event, "digest": e.digest}
                               for e in s.execute(select(Audit).order_by(Audit.sequence.desc()).limit(100)).scalars()]}

    def get(self, task_id):
        with self.transaction() as s:
            return self.view(self.task(s, task_id))

    @staticmethod
    def view(t):
        return {"id": t.id, "operation_id": t.id, "state": t.state, "version": t.version,
                "epoch": t.epoch, "payload": t.payload, "payload_hash": t.payload_hash,
                "fence": t.fence, "attempts": t.attempts, "artifact": t.artifact,
                "artifact_hash": t.artifact_hash, "reason": t.reason}
