"""Closed HTTP-mock planning backend on the existing F1 authority and money ledger."""
import hashlib
from typing import Literal

import httpx
from pydantic import Field, ValidationError
from sqlalchemy import select

from .coding.financial_types import Strict, NANO_RUB
from .coding.gateway import Gateway, UNRESOLVED_ACTION_STATES
from .coding.integration_config import Tariff
from .models import ExternalAction, ExternalGrant, Task
from .planning_task import KIND, check_context
from .project_inbox import owner
from .request_plan_store import _save_locked
from .request_planning import request_document
from .store import Denied, canonical, digest

SCOPE = 'saved-request-plan.v1'
CONFIRMATION = 'AUTHORIZE_SAVED_REQUEST_PLANNING_HTTP_MOCK'
KEY = 'planning/v1'


class PlanningConfig(Strict):
    # There is intentionally no live mode, config-file loader, or credential binding.
    mode: Literal['disabled', 'http_mock'] = 'disabled'
    enabled: bool = False
    tariff: Tariff | None = None
    daily_nano_rub: int = Field(default=0, ge=0, le=100 * NANO_RUB)
    monthly_nano_rub: int = Field(default=0, ge=0, le=100 * NANO_RUB)
    budget_evidence: str = Field(default='', max_length=300)
    openai_secret_ref: Literal['planning-http-mock'] = 'planning-http-mock'

    @property
    def first_experiment(self):
        return None

    @property
    def synthetic_repository(self):
        return ''

    def connected(self):
        return self.mode == 'http_mock' and self.enabled and bool(self.budget_evidence)


class MockCredentials:
    def get(self, reference):
        if reference != 'planning-http-mock':
            raise Denied('planning_credential_scope')
        return 'PUBLIC_PLANNING_HTTP_MOCK_ONLY'


class PlanningGateway(Gateway):
    operation_scope = SCOPE

    def __init__(self, store, config=None, *, transport=None):
        config = config or PlanningConfig()
        if not isinstance(config, PlanningConfig) or not config.connected() or not isinstance(transport, httpx.MockTransport):
            raise Denied('planning_http_mock_only')
        super().__init__(store, config, transport=transport, credentials=MockCredentials())

    def authorize(self, actor, task_id, version, *, budget_nano_rub, seconds=120,
                  confirmation, expected_config_hash):
        owner(actor)
        try:
            c = PlanningConfig.model_validate(self.config.model_dump())
        except ValidationError:
            raise Denied('planning_approval_scope_or_budget') from None
        if (not c.connected() or confirmation != CONFIRMATION or expected_config_hash != digest(c.model_dump())
                or not c.tariff or not c.tariff.confirmed or type(seconds) is not int or not 1 <= seconds <= 120
                or type(budget_nano_rub) is not int
                or not 0 < c.tariff.maximum() <= budget_nano_rub <= min(c.daily_nano_rub, c.monthly_nano_rub)):
            raise Denied('planning_approval_scope_or_budget')

        def install(session, task):
            self.store.check_audit(session)
            self.store.check_task_revision(session, task)
            if digest(self.config.model_dump()) != expected_config_hash:
                raise Denied('planning_approval_profile_changed')
            if task.state != 'READY' or task.version != version or session.get(ExternalGrant, task_id):
                raise Denied('external_grant_conflict')
            snapshot = check_context(self.store, session, task.payload)
            bound = session.scalar(select(ExternalGrant).where(
                ExternalGrant.document['scope'].as_string() == SCOPE,
                ExternalGrant.document['request_id'].as_string() == snapshot.request_id,
                ExternalGrant.document['context_digest'].as_string() == snapshot.binding).limit(1))
            if bound:
                raise Denied('planning_context_already_bound')
            # Changing project/context is not a way to retry an unresolved call for the same request.
            rows = session.scalars(select(ExternalAction).join(Task, Task.id == ExternalAction.task_id)
                .where(Task.payload['kind'].as_string() == KIND,
                       Task.payload['planning']['request_id'].as_string() == snapshot.request_id)).all()
            self.check_ledger(session, rows)
            if any(row.state in UNRESOLVED_ACTION_STATES for row in rows):
                raise Denied('planning_request_outcome_unresolved')
            document = {'scope': SCOPE, 'mode': 'http_mock', 'task_version': version,
                        'payload_hash': task.payload_hash, 'revision': self.store.settings.source_revision,
                        'config_hash': digest(c.model_dump()), 'budget': budget_nano_rub,
                        'model': c.tariff.model, 'max_calls': 1, 'request_id': snapshot.request_id,
                        'context_digest': snapshot.binding, 'secret_refs': [c.openai_secret_ref],
                        'confirmation': CONFIRMATION}
            seal = digest(document)
            session.add(ExternalGrant(task_id=task_id, document=document, digest=seal))
            self.store.audit(session, 'external_scope_approved', actor, task_id, grant_digest=seal)
        self.store.approve(actor, task_id, version, seconds, _scope_installer=install)
        return {'authorized': True, 'task_id': task_id, 'mode': 'http_mock', 'scope': SCOPE,
                'budget_nano_rub': budget_nano_rub, 'live_supported': False}

    def authority(self, session, task_id, fence):
        task, document = self.f1_authority(session, task_id, fence)
        snapshot = check_context(self.store, session, task.payload)
        c = self.config
        if (document.get('scope') != SCOPE or document.get('mode') != 'http_mock'
                or document.get('confirmation') != CONFIRMATION or document.get('max_calls') != 1
                or document.get('request_id') != snapshot.request_id or document.get('context_digest') != snapshot.binding
                or not c.tariff or not c.tariff.confirmed or document.get('model') != c.tariff.model
                or document.get('secret_refs') != [c.openai_secret_ref]):
            raise Denied('planning_external_scope_changed')
        return task, document

    def endpoint(self, kind, path, method):
        if kind != 'openai' or method != 'POST' or path != '/v1/responses':
            raise Denied('planning_endpoint_forbidden')
        return 'https://api.openai.com/v1/responses', self.config.openai_secret_ref

    def request(self, task_id, fence, key, kind, method, path, body=None, *, query=None, reconcile=False):
        if key != KEY or query is not None or reconcile:
            raise Denied('planning_request_scope')
        return super().request(task_id, fence, key, kind, method, path, body)

    def admit_provider_request(self, task, document, body, count):
        from .planning_task import validate_payload
        snapshot = validate_payload(task.payload)
        tariff = self.config.tariff
        expected = request_document(snapshot, tariff.model, context_tokens=tariff.context_tokens,
                                    max_output_tokens=tariff.max_output_tokens)
        if canonical(body) != canonical(expected):
            raise Denied('planning_provider_request_contract')
        if any(row.kind == 'openai' for row in count):
            raise Denied('planning_single_call_limit')
        return tariff.maximum()

    def perform(self, task_id, fence):
        """Explicit planning operation; production dispatch requires a separate trusted host integration."""
        with self.store.transaction() as session:
            task, _ = self.authority(session, task_id, fence)
            snapshot = check_context(self.store, session, task.payload)
        tariff = self.config.tariff
        body = request_document(snapshot, tariff.model, context_tokens=tariff.context_tokens,
                                max_output_tokens=tariff.max_output_tokens)
        data = self.request(task_id, fence, KEY, 'openai', 'POST', '/v1/responses', body)
        artifact = canonical({'operation': self.operation_scope, 'mode': self.config.mode, 'request_id': snapshot.request_id,
                              'context_digest': snapshot.binding, 'business_execution': False})
        checksum = hashlib.sha256(artifact.encode()).hexdigest()
        receipt = None

        def compose(session, task):
            nonlocal receipt
            self.authority(session, task_id, fence)
            action = session.scalar(select(ExternalAction).where(ExternalAction.key == task_id + ':' + KEY))
            self.check_ledger(session, [action] if action else [])
            if not action or action.state != 'COMPLETE' or digest(action.evidence.get('response')) != digest(data):
                raise Denied('planning_response_not_anchored')
            receipt = _save_locked(self.store, session, snapshot, data, tariff.model,
                context_tokens=tariff.context_tokens, max_output_tokens=tariff.max_output_tokens)
            task.coding_evidence = {'planning_result': receipt, 'mode': self.config.mode}
            self.store.audit(session, 'planning_proposal_bound', 'gateway', task_id,
                             action_id=action.id, proposal_id=receipt['proposal_id'], artifact_hash=checksum)
            self.authority(session, task_id, fence)  # Slow result writes must not carry stale consent forward.
        self.store.finish(task_id, fence, artifact, checksum, actual_cost=1, _scope_installer=compose)
        return receipt

    def status(self, task_id):
        with self.store.transaction() as session:
            self.store.check_audit(session)
            task = self.store.task(session, task_id)
            if task.payload.get('kind') != KIND:
                raise Denied('planning_task_scope_invalid')
            rows = session.scalars(select(ExternalAction).where(ExternalAction.task_id == task_id)).all()
            self.check_ledger(session, rows)
            return {'mode': self.config.mode, 'live_supported': self.config.mode == 'live', 'task_state': task.state,
                    'calls': len(rows), 'actual_nano_rub': sum(row.actual for row in rows),
                    'uncertain_nano_rub': sum(row.reserved for row in rows),
                    'result_uncertain': any(row.state in UNRESOLVED_ACTION_STATES for row in rows),
                    'financial_values_are_mock': self.config.mode == 'http_mock'}
