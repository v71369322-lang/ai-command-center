"""One separately authorized recovery; never reopen or reuse the first pilot grant."""
from typing import Literal

from pydantic import Field
from sqlalchemy import select

from ..models import Audit, ExternalAction, ExternalGrant, Task
from ..store import Denied, digest
from .first_experiment import CAP, EXPERIMENT_ID, RECOVERY_ID, REQUEST_KEY, FirstExperiment, task_payload
from .http_contract import decode_response
from .spec import BASE_SHA

RECOVERY_CAP = 34_786_800_000


class RecoveryExperiment(FirstExperiment):
    id: Literal['f2.2-recovery-1'] = RECOVERY_ID
    original_task_id: str = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    original_grant_digest: str = Field(pattern=r'^[a-f0-9]{64}$')

    @property
    def call_limit(self):
        return 1

    @property
    def budget_cap(self):
        return RECOVERY_CAP

    def report(self, now=None):
        result = super().report(now)
        result['gates']['payment_bound'] = (result['gates']['payment_bound'] and
            result['payment_quote']['max_nano_rub'] <= RECOVERY_CAP)
        result['ready_for_final_confirmation'] = all(result['gates'].values())
        return {**result, 'recovery_of': self.original_task_id, 'parent_state_verified': False}

    def validate_scope(self, config, coding, budget, now, *, final_confirmation=False):
        super().validate_scope(config, coding, budget, now, final_confirmation=final_confirmation)
        if budget > config.tariff.maximum() or config.tariff.maximum() > RECOVERY_CAP:
            raise Denied('recovery_one_call_budget')

    def verify_parent(self, store, session, config):
        from .gateway import Gateway
        store.check_audit(session)
        parent = session.get(Task, self.original_task_id)
        grant = session.get(ExternalGrant, self.original_task_id)
        expected = task_payload()
        if (not parent or not grant or parent.request_key != 'owner:' + REQUEST_KEY
                or parent.owner_role != 'owner' or parent.state != 'FAILED'
                or parent.attempts != 1 or parent.reserved != 0
                or parent.reason != 'external_coding_blocked' or parent.payload != expected
                or parent.payload_hash != digest(expected)
                or not isinstance(parent.coding_evidence, dict)
                or parent.coding_evidence.get('stage') != 'external_stopped'
                or parent.coding_evidence.get('failure') != 'provider_or_verifier_contract_rejected'
                or type(parent.coding_evidence.get('iteration')) is not int or parent.coding_evidence['iteration'] != 1
                or {'agent_result', 'test_runs', 'independent_proof', 'publication_plan', 'pr'} & set(parent.coding_evidence)):
            raise Denied('recovery_parent_ineligible')
        doc = grant.document
        if not isinstance(doc, dict):
            raise Denied('recovery_parent_grant_invalid')
        created = session.scalar(select(Audit).where(
            Audit.event['kind'].as_string() == 'task_created',
            Audit.event['task_id'].as_string() == parent.id).order_by(Audit.sequence).limit(1))
        approved = session.scalar(select(Audit).where(
            Audit.event['kind'].as_string() == 'external_scope_approved',
            Audit.event['actor'].as_string() == 'owner',
            Audit.event['task_id'].as_string() == parent.id,
            Audit.event['revision'].as_string() == doc.get('revision'),
            Audit.event['grant_digest'].as_string() == grant.digest).limit(1))
        failure = session.scalar(select(Audit).where(
            Audit.event['kind'].as_string() == 'coding_external_stopped',
            Audit.event['actor'].as_string() == 'coding_pipeline',
            Audit.event['task_id'].as_string() == parent.id,
            Audit.event['revision'].as_string() == doc.get('revision'),
            Audit.event['evidence_hash'].as_string() == digest(parent.coding_evidence),
            Audit.event['fence'].as_integer() == parent.fence).limit(1))
        stopped = session.scalar(select(Audit).where(
            Audit.event['kind'].as_string() == 'execution_stopped',
            Audit.event['actor'].as_string() == 'worker',
            Audit.event['task_id'].as_string() == parent.id,
            Audit.event['reason'].as_string() == 'external_coding_blocked',
            Audit.event['revision'].as_string() == doc.get('revision')).limit(1))
        if (grant.digest != self.original_grant_digest or digest(doc) != grant.digest
                or doc.get('experiment_id') != EXPERIMENT_ID or doc.get('mode') != config.mode
                or doc.get('payload_hash') != parent.payload_hash or doc.get('base_sha') != BASE_SHA
                or doc.get('repository') != config.synthetic_repository or doc.get('repository_id') != self.repository_id
                or doc.get('model') != self.model or not created or not approved or not failure or not stopped
                or doc.get('task_version') != parent.version
                or type(doc.get('max_calls')) is not int or doc['max_calls'] != 2
                or created.event.get('actor') != 'owner' or created.event.get('payload_hash') != parent.payload_hash
                or created.event.get('revision') != doc.get('revision')
                or doc.get('revision') == store.settings.source_revision
                or config.mode == 'live' and doc.get('final_confirmation') is not True):
            raise Denied('recovery_parent_grant_invalid')
        actions = session.scalars(select(ExternalAction).where(
            ExternalAction.task_id == parent.id).order_by(ExternalAction.id)).all()
        Gateway.check_ledger(session, actions)
        if (not 1 <= len(actions) <= 64 or any(a.state != 'COMPLETE' or a.reserved != 0 or a.actual < 0
                                             or not isinstance(a.evidence, dict) for a in actions)
                or any(a.kind not in {'openai', 'github', 'github_git'} for a in actions)
                or any(a.kind != 'openai' and (a.evidence.get('method') != 'GET' or a.actual != 0) for a in actions)):
            raise Denied('recovery_parent_outcome_unresolved')
        paid = [a for a in actions if a.kind == 'openai']
        if len(paid) != 1 or paid[0].key != parent.id + ':ai/1' or paid[0].evidence.get('method') != 'POST':
            raise Denied('recovery_parent_call_count')
        try:
            decode_response(paid[0].evidence['response'], self.model)
        except ValueError as error:
            if str(error) != 'synthetic_language_scope_violation':
                raise Denied('recovery_parent_failure_mismatch') from None
        except (KeyError, TypeError):
            raise Denied('recovery_parent_failure_mismatch') from None
        else:
            raise Denied('recovery_parent_failure_mismatch')
        actual = sum(a.actual for a in actions)
        if (type(doc.get('budget')) is not int or not config.tariff
                or config.tariff.maximum() > RECOVERY_CAP
                or actual + config.tariff.maximum() > min(CAP, doc['budget'])):
            raise Denied('recovery_cumulative_budget')
        return {'task_id': parent.id, 'grant_digest': grant.digest,
                'source_revision': doc['revision'], 'actual_nano_rub': actual,
                'actions_hash': digest([Gateway.action_digest(a) for a in actions])}
