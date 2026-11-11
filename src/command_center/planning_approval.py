"""Client-free reviewed planning approval, composed with the existing locked F1 action.

Internal trusted-call boundary only. Telegram authentication and live runtime/key
bindings are intentionally absent; the production broker still rejects this kind.
"""
from datetime import datetime, timezone

from sqlalchemy import select

from .coding.gateway import Gateway, UNRESOLVED_ACTION_STATES
from .models import ExternalAction, ExternalGrant, Task
from .planning_admission import PlanningProfile, prepare_review, validate_review
from .planning_task import KIND, check_context
from .project_inbox import owner
from .store import Denied, digest

CONFIRMATION = 'AUTHORIZE_EXACT_SAVED_REQUEST_LIVE_PLANNING'


class PlanningApproval:
    def __init__(self, store, profile):
        self.store = store
        self.profile = profile

    def _profile(self):
        try:
            return PlanningProfile.model_validate(self.profile.model_dump())
        except (ValueError, AttributeError):
            raise Denied('planning_profile_invalid') from None

    def prepare(self, actor, task_id, version, *, seconds=120):
        owner(actor)
        with self.store.transaction() as session:
            self.store.check_audit(session)
            task = self.store.task(session, task_id)
            self.store.check_task_revision(session, task)
            if task.state != 'WAITING_APPROVAL' or task.version != version:
                raise Denied('planning_task_not_waiting')
            snapshot = check_context(self.store, session, task.payload)
            return prepare_review(actor, self._profile(), snapshot, task_id=task_id,
                task_version=version, now=int(self.store.now(session).timestamp()), seconds=seconds)

    def authorize(self, actor, quote, *, expected_quote_digest, confirmation):
        owner(actor)
        if confirmation != CONFIRMATION:
            raise Denied('planning_exact_confirmation_required')
        # Parse once, then validate against current evidence under the F1 lock.
        from .planning_admission import PlanningQuote
        try:
            quote = PlanningQuote.model_validate(quote.model_dump())
            deadline = datetime.fromtimestamp(quote.expires_at, timezone.utc)
        except (ValueError, AttributeError, OverflowError, OSError):
            raise Denied('planning_review_invalid') from None

        def install(session, task):
            self.store.check_audit(session)
            self.store.check_task_revision(session, task)
            profile = self._profile()
            snapshot = check_context(self.store, session, task.payload)
            current = validate_review(actor, profile, snapshot, quote, task_id=task.id,
                task_version=task.version, now=int(self.store.now(session).timestamp()),
                expected_quote_digest=expected_quote_digest)
            if task.state != 'READY' or session.get(ExternalGrant, task.id):
                raise Denied('external_grant_conflict')
            bound = session.scalar(select(ExternalGrant).where(
                ExternalGrant.document['request_id'].as_string() == snapshot.request_id,
                ExternalGrant.document['context_digest'].as_string() == snapshot.binding).limit(1))
            if bound:
                raise Denied('planning_context_already_bound')
            prior = session.scalars(select(ExternalAction).join(Task, Task.id == ExternalAction.task_id)
                .where(Task.payload['kind'].as_string() == KIND,
                       Task.payload['planning']['request_id'].as_string() == snapshot.request_id)).all()
            Gateway.check_ledger(session, prior)
            if any(row.state in UNRESOLVED_ACTION_STATES for row in prior):
                raise Denied('planning_request_outcome_unresolved')
            document = {'scope': profile.purpose, 'mode': 'live', 'task_version': task.version,
                'payload_hash': task.payload_hash, 'revision': self.store.settings.source_revision,
                'config_hash': current.profile_digest, 'budget': current.maximum_nano_rub,
                'model': current.model, 'max_calls': 1, 'request_id': snapshot.request_id,
                'context_digest': snapshot.binding, 'review': current.model_dump(),
                'review_digest': expected_quote_digest, 'confirmation': CONFIRMATION,
                'secret_refs': [], 'business_execution': False}
            rows = Gateway.check_budget(self.store, profile, session, task.id, document, document['budget'])
            # Funding evidence may predate a settlement. With only day-level settlement
            # anchors, count that entire UTC day conservatively, plus all disputed reserves.
            evidence_day = datetime.fromtimestamp(profile.evidence.observed_at, timezone.utc).strftime('%Y-%m-%d')
            committed = sum(row.reserved + (row.actual if (
                not row.evidence.get('settled_day') or row.evidence['settled_day'] >= evidence_day) else 0)
                for row in rows)
            if committed + document['budget'] > profile.available_nano_rub:
                raise Denied('planning_funding_limit')
            seal = digest(document)
            session.add(ExternalGrant(task_id=task.id, document=document, digest=seal))
            self.store.audit(session, 'external_scope_approved', actor, task.id,
                             grant_digest=seal, review_digest=expected_quote_digest)
            # A slow hook must not extend the displayed consent/profile deadline.
            validate_review(actor, self._profile(), snapshot, quote, task_id=task.id,
                task_version=task.version, now=int(self.store.now(session).timestamp()),
                expected_quote_digest=expected_quote_digest)

        self.store.approve(actor, quote.task_id, quote.task_version, 120,
                          _scope_installer=install, _deadline=deadline)
        return {'authorized': True, 'task_id': quote.task_id, 'review_digest': expected_quote_digest,
                'maximum_nano_rub': quote.maximum_nano_rub, 'expires_at': quote.expires_at,
                'provider_called': False, 'runtime_dispatch_enabled': False,
                'business_execution': False}
