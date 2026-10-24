"""Trusted external action gateway. Durable intent always precedes network I/O."""
import json
import re
from uuid import uuid4

import httpx
from sqlalchemy import select

from ..models import Approval, Audit, Control, ExternalAction, ExternalGrant
from ..store import Denied, digest
from .integration_config import FileCredentials, IntegrationConfig
from .spec import BASE_SHA


class Uncertain(Denied):
    pass


class Gateway:
    def __init__(self, store, config=None, *, transport=None, credentials=None):
        self.store, self.config = store, config or IntegrationConfig.load()
        if self.config.mode == 'http_mock' and not isinstance(transport, httpx.MockTransport):
            raise Denied('http_mock_transport_required')
        if self.config.mode != 'http_mock' and transport is not None:
            raise Denied('transport_override_forbidden')
        self.client = httpx.Client(transport=transport, follow_redirects=False, timeout=8,
                                   trust_env=self.config.mode != 'http_mock')
        self.credentials = credentials or FileCredentials(self.config)
        self.runtime_guard = None

    def close(self):
        self.client.close()

    def authorize(self, actor, task_id, version, *, budget_nano_rub, seconds=120):
        if actor != 'owner':
            raise Denied('owner_required')
        c = self.config
        if not c.connected() or not c.synthetic_repository:
            raise Denied('integration_not_connected')
        if not c.tariff or not c.tariff.confirmed or not c.daily_nano_rub or not c.monthly_nano_rub:
            raise Denied('budget_unconfirmed')
        if type(budget_nano_rub) is not int or not 0 < budget_nano_rub <= c.monthly_nano_rub:
            raise Denied('invalid_task_budget')
        view = self.store.get(task_id)
        if view['payload'].get('coding', {}).get('provider') != 'openai':
            raise Denied('not_external_coding_task')
        # The F1 approval remains the sole grant of task execution authority.
        # ExternalGrant only narrows it with immutable financial/endpoint scope.
        self.store.approve(actor, task_id, version, seconds)
        with self.store.transaction() as s:
            self.store.check_audit(s)
            task = self.store.task(s, task_id)
            self.store.check_task_revision(s, task)
            if task.version != version or task.state != 'READY' or s.get(ExternalGrant, task_id):
                raise Denied('external_grant_conflict')
            document = {'task_version': version, 'payload_hash': task.payload_hash,
                        'revision': self.store.settings.source_revision, 'base_sha': BASE_SHA,
                        'config_hash': digest(c.model_dump()), 'budget': budget_nano_rub,
                        'repository': c.synthetic_repository, 'model': c.tariff.model,
                        'max_calls': task.payload['coding']['max_iterations'],
                        'secret_refs': [c.openai_secret_ref, c.github_secret_ref]}
            seal = digest(document)
            s.add(ExternalGrant(task_id=task_id, document=document, digest=seal))
            self.store.audit(s, 'external_scope_approved', actor, task_id, grant_digest=seal)
        return {'authorized': True, 'task_id': task_id, 'budget_nano_rub': budget_nano_rub,
                'mode': c.mode, 'repository': c.synthetic_repository}

    def authority(self, s, task_id, fence):
        c = self.config
        if not c.connected():
            raise Denied('integration_not_connected')
        self.store.check_audit(s)
        task, control = self.store.task(s, task_id), s.get(Control, 1)
        self.store.check_task_revision(s, task)
        approval, grant = s.get(Approval, task_id), s.get(ExternalGrant, task_id)
        now = self.store.now(s)
        if (control.halted or control.recovery or task.state != 'RUNNING' or task.fence != fence
                or task.epoch != control.epoch or task.lease_until <= now or not approval or not approval.used
                or approval.revoked or approval.expires_at <= now or approval.task_version != task.version
                or approval.payload_hash != task.payload_hash or approval.epoch != control.epoch or not grant):
            raise Denied('external_authority_lost')
        doc = grant.document
        if (digest(doc) != grant.digest or doc['payload_hash'] != digest(task.payload)
                or doc['task_version'] != task.version or doc['revision'] != self.store.settings.source_revision
                or doc['config_hash'] != digest(c.model_dump()) or doc['base_sha'] != BASE_SHA):
            raise Denied('external_scope_changed')
        anchored = any(a.event.get('grant_digest') == grant.digest for a in s.execute(
            select(Audit).where(Audit.event['task_id'].astext == task_id)).scalars())
        if not anchored:
            raise Denied('external_grant_unanchored')
        return task, doc

    def endpoint(self, kind, path, method):
        c = self.config
        if kind == 'openai' and path == '/v1/responses' and method == 'POST':
            return 'https://api.openai.com' + path, c.openai_secret_ref
        prefix = '/repos/' + c.synthetic_repository
        if not c.synthetic_repository or not path.startswith(prefix + '/'):
            raise Denied('external_repository_forbidden')
        relative = path[len(prefix):]
        allowed = (method == 'GET' and (
            relative == '/git/ref/heads/main' or relative == '/pulls'
            or re.fullmatch(r'/git/(?:blobs|trees|commits)/[a-f0-9]{40}', relative)
            or re.fullmatch(r'/git/ref/heads/f2/task-[a-f0-9-]{36}-[1-9][0-9]*', relative))) or (
                method == 'POST' and relative in {'/git/blobs', '/git/trees', '/git/commits', '/git/refs', '/pulls'})
        if kind != 'github' or not allowed:
            raise Denied('external_endpoint_forbidden')
        return 'https://api.github.com' + path, c.github_secret_ref

    def _reserve(self, s, task_id, doc, amount):
        c = self.config
        rows = s.execute(select(ExternalAction)).scalars().all()
        now = self.store.now(s)
        day, month = now.strftime('%Y-%m-%d'), now.strftime('%Y-%m')
        task_total = sum(r.actual + r.reserved for r in rows if r.task_id == task_id)
        pending = sum(r.reserved for r in rows)  # Including disputed costs from earlier periods.
        daily = pending + sum(r.actual for r in rows if r.evidence.get('settled_day') == day)
        monthly = pending + sum(r.actual for r in rows if r.evidence.get('settled_month') == month)
        if (task_total + amount > doc['budget'] or daily + amount > c.daily_nano_rub
                or monthly + amount >= c.monthly_nano_rub * 9 // 10):
            raise Denied('external_budget_limit')

    def request(self, task_id, fence, key, kind, method, path, body=None, *, query=None, reconcile=False):
        url, secret_ref = self.endpoint(kind, path, method)
        if not self.config.connected():
            raise Denied('integration_not_connected')
        if self.config.mode == 'live' and self.runtime_guard is None:
            raise Denied('runtime_guard_required')
        if self.runtime_guard and not self.runtime_guard():
            raise Denied('runtime_authority_lost')
        token = self.credentials.get(secret_ref)
        encoded = json.dumps(body, sort_keys=True, separators=(',', ':'))
        if len(encoded.encode()) > 16384 or token in encoded:
            raise Denied('external_input_boundary')
        fingerprint = digest({'kind': kind, 'method': method, 'path': path, 'body': body, 'query': query})
        opkey = task_id + ':' + key
        if len(opkey) > 200:
            raise Denied('external_key_limit')
        if not self.store.pulse(task_id, fence):
            raise Denied('external_authority_lost')
        with self.store.transaction() as s:
            task, doc = self.authority(s, task_id, fence)
            if kind == 'github':
                from .spec import branch_name
                branch = branch_name(task_id, fence)
                if '/git/ref/heads/f2/' in path and not path.endswith('/' + branch):
                    raise Denied('external_branch_forbidden')
                if method == 'POST':
                    plan = task.coding_evidence.get('publication_plan', {})
                    if plan.get(key) != fingerprint:
                        raise Denied('unverified_publication_plan')
                    anchored = any(a.event.get('evidence_hash') == digest(task.coding_evidence) for a in s.execute(
                        select(Audit).where(Audit.event['task_id'].astext == task_id)).scalars())
                    if not anchored:
                        raise Denied('publication_plan_unanchored')
                    if path.endswith('/git/refs') and body.get('ref') != 'refs/heads/' + branch:
                        raise Denied('protected_branch_write_forbidden')
                    if path.endswith('/pulls') and (body.get('head') != branch or body.get('base') != 'main'
                                                   or body.get('draft') is not True):
                        raise Denied('pull_request_scope_forbidden')
                if path.endswith('/pulls') and method == 'GET' and query != {
                        'head': self.config.synthetic_repository.split('/')[0] + ':' + branch,
                        'base': 'main', 'state': 'open'}:
                    raise Denied('external_pr_query_scope')
            old = s.execute(select(ExternalAction).where(ExternalAction.key == opkey)).scalar_one_or_none()
            if old:
                if old.request_hash != fingerprint:
                    raise Denied('external_idempotency_conflict')
                if old.state == 'COMPLETE':
                    return old.evidence['response']
                raise Uncertain('reconciliation_required')
            if reconcile and method != 'GET':
                raise Denied('reconciliation_cannot_write_remote')
            count = s.execute(select(ExternalAction).where(ExternalAction.task_id == task_id)).scalars().all()
            if len(count) >= 64:
                raise Denied('external_call_limit')
            amount = 0
            if kind == 'openai':
                tariff = self.config.tariff
                if not tariff or not tariff.confirmed or body.get('model') != doc['model']:
                    raise Denied('tariff_or_model_unconfirmed')
                from .http_contract import request_document
                try:
                    context = json.loads(body['input'][1]['content'])
                    if (body != request_document(context, tariff.model, tariff.max_output_tokens)
                            or context['base_sha'] != doc['base_sha']):
                        raise ValueError('changed_request')
                except (ValueError, KeyError, TypeError, IndexError):
                    raise Denied('provider_request_contract') from None
                if sum(r.kind == 'openai' for r in count) >= doc['max_calls']:
                    raise Denied('external_iteration_limit')
                amount = tariff.maximum()
                self._reserve(s, task_id, doc, amount)
            action = ExternalAction(id=str(uuid4()), task_id=task_id, key=opkey, kind=kind,
                                    request_hash=fingerprint, state='INTENT', reserved=amount,
                                    actual=0, created_at=self.store.now(s), evidence={})
            s.add(action)
            self.store.audit(s, 'external_intent', 'gateway', task_id, action_id=action.id,
                             request_hash=fingerprint, kind=kind, reserved_nano_rub=amount)
            action_id = action.id
        # No DB transaction is held during I/O. Intent/reservation is already durable.
        try:
            headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}
            with self.client.stream(method, url, json=body, params=query, headers=headers,
                                    follow_redirects=False, timeout=8) as response:
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        raise Uncertain('external_output_limit')
                if token.encode() in raw:
                    raise Uncertain('credential_echo_blocked')
                if response.status_code not in {200, 201}:
                    raise Uncertain('external_http_' + str(response.status_code))
                data = json.loads(raw)
                request_id = response.headers.get('x-request-id', response.headers.get('x-github-request-id', ''))
                if not re.fullmatch(r'[A-Za-z0-9_-]{0,128}', request_id) or token in request_id:
                    raise Uncertain('invalid_request_identifier')
            with self.store.transaction() as s:
                self.store.check_audit(s)
                operation = s.get(ExternalAction, action_id)
                evidence = {'response': data, 'request_id': request_id}
                if kind == 'openai':
                    # Financial settlement requires documented, bounded usage. Bad/missing usage stays reserved.
                    from .http_contract import ResponseEnvelope
                    parsed = ResponseEnvelope.model_validate(data)
                    if (parsed.model != self.config.tariff.model or parsed.usage.total_tokens !=
                            parsed.usage.input_tokens + parsed.usage.output_tokens):
                        raise Uncertain('provider_model_or_usage_mismatch')
                    usage = parsed.usage.model_dump()
                    price = self.config.tariff.cost(usage['input_tokens'], usage['output_tokens'])
                    operation.actual, operation.reserved = price, 0
                    now = self.store.now(s)
                    evidence.update(settled_day=now.strftime('%Y-%m-%d'), settled_month=now.strftime('%Y-%m'),
                                    response_id=data.get('id'), usage=usage)
                operation.state, operation.evidence = 'COMPLETE', evidence
                self.store.audit(s, 'external_response', 'gateway', task_id, action_id=action_id,
                                 response_hash=digest(data), actual_nano_rub=operation.actual,
                                 request_id=request_id)
            with self.store.transaction() as s:
                self.authority(s, task_id, fence)  # Cancellation/revocation during I/O never grants continuation.
            if self.runtime_guard and not self.runtime_guard():
                raise Denied('runtime_authority_lost')
            return data
        except Exception as error:
            # Even PG loss leaves the pre-I/O INTENT intact. Never auto-release disputed reserves.
            try:
                with self.store.transaction() as s:
                    self.store.check_audit(s)
                    operation = s.get(ExternalAction, action_id)
                    if operation.state != 'COMPLETE':
                        operation.state = 'UNCERTAIN'
                    self.store.audit(s, 'external_interrupted', 'gateway', task_id, action_id=action_id)
            except Exception:
                pass
            if isinstance(error, Denied):
                raise
            raise Uncertain('external_outcome_unconfirmed') from None

    def resolve_read_evidence(self, task_id, fence, key, expected_hash, data):
        """Only reconciler's independently read exact remote object can close a write intent."""
        with self.store.transaction() as s:
            self.authority(s, task_id, fence)
            row = s.execute(select(ExternalAction).where(ExternalAction.key == task_id + ':' + key)).scalar_one()
            if row.request_hash != expected_hash or row.kind != 'github' or row.state == 'COMPLETE':
                raise Denied('reconciliation_mismatch')
            row.state, row.evidence = 'COMPLETE', {'response': data, 'reconciled': True}
            self.store.audit(s, 'external_reconciled', 'gateway', task_id, action_id=row.id,
                             response_hash=digest(data))

    def status(self, task_id):
        with self.store.transaction() as s:
            self.store.check_audit(s)
            task = self.store.task(s, task_id)
            rows = s.execute(select(ExternalAction).where(ExternalAction.task_id == task_id)).scalars().all()
            grant = s.get(ExternalGrant, task_id)
            return {**self.config.public(), 'description': 'Исправить сумму положительных чисел',
                    'task_state': task.state, 'budget_nano_rub': grant.document['budget'] if grant else None,
                    'actual_nano_rub': sum(r.actual for r in rows),
                    'uncertain_nano_rub': sum(r.reserved for r in rows),
                    'calls': sum(r.kind == 'openai' for r in rows),
                    'result_uncertain': any(r.state in {'INTENT', 'UNCERTAIN'} for r in rows),
                    'permission': bool(grant),
                    'actions': [{'id': r.id, 'kind': r.kind, 'state': r.state,
                                 'request_id': r.evidence.get('request_id')} for r in rows]}

    def reconcile_usage(self, actor, action_id, input_tokens, output_tokens, evidence_reference):
        """Explicit owner attestation of independently obtained provider billing evidence.
        No network, retry, task resumption or permission extension is performed.
        """
        if actor != 'owner' or not evidence_reference or not self.config.tariff:
            raise Denied('owner_billing_evidence_required')
        with self.store.transaction() as s:
            self.store.check_audit(s)
            row = s.get(ExternalAction, action_id)
            if not row or row.kind != 'openai' or row.state not in {'INTENT', 'UNCERTAIN'}:
                raise Denied('billing_reconciliation_mismatch')
            grant = s.get(ExternalGrant, row.task_id)
            if not grant or grant.document['config_hash'] != digest(self.config.model_dump()):
                raise Denied('billing_tariff_changed')
            price = self.config.tariff.cost(input_tokens, output_tokens)
            now = self.store.now(s)
            row.actual, row.reserved, row.state = price, 0, 'SETTLED'
            row.evidence = {**row.evidence, 'evidence_hash': digest(evidence_reference),
                            'classification': 'OWNER_BILLING_ATTESTATION',
                            'settled_day': now.strftime('%Y-%m-%d'), 'settled_month': now.strftime('%Y-%m'),
                            'usage': {'input_tokens': input_tokens, 'output_tokens': output_tokens}}
            self.store.audit(s, 'billing_reconciled', actor, row.task_id, action_id=row.id,
                             actual_nano_rub=price, evidence_hash=digest(evidence_reference))
            return {'settled': True, 'actual_nano_rub': price, 'task_resumed': False}
