"""Explicit trusted Responses planning adapter; no production dispatch or automatic activation."""
import hashlib
import json
import os
import re

from sqlalchemy import select

from .coding.gateway import Gateway, Uncertain
from .planning_admission import PlanningQuote, validate_review
from .planning_approval import CONFIRMATION, check_financial_room
from .planning_gateway import KEY, PlanningGateway
from .planning_profile import load
from .planning_task import check_context
from .models import Audit, TelegramInbox
from .project_inbox import check_content
from .request_planning import _unique
from .store import Denied, digest
from .telegram_transport import private_read
from .telegram_planning_authorize import CONSUMED, ISSUED, observed_delivery


class LivePlanningConfig:
    """Gateway accounting view whose hash is exactly the reviewed operator profile."""
    mode = 'live'
    trust_env = False
    first_experiment = None
    synthetic_repository = ''
    openai_secret_ref = 'planning-openai'

    def __init__(self, profile):
        self.profile = profile

    def model_dump(self):
        return self.profile.model_dump()

    @property
    def tariff(self):
        return self.profile.tariff

    @property
    def daily_nano_rub(self):
        return self.profile.daily_nano_rub

    @property
    def monthly_nano_rub(self):
        return self.profile.monthly_nano_rub

    def connected(self):
        return self.profile.runtime is not None


class PlanningCredentials:
    def __init__(self, profile):
        self.profile = profile

    def get(self, reference):
        try:
            if reference != self.profile.runtime.credential_ref:
                raise ValueError()
            raw = private_read(os.environ['F1_PLANNING_OPENAI_KEY_FILE'], 1024)
            if len(raw) > 1024 or hashlib.sha256(raw).hexdigest() != self.profile.runtime.credential_sha256:
                raise ValueError()
            token = raw.decode('ascii').strip()
            if not re.fullmatch(r'[A-Za-z0-9_-]{16,1024}', token):
                raise ValueError()
            return token
        except (OSError, KeyError, ValueError, AttributeError, Denied):
            raise Denied('planning_credential_binding_invalid') from None


class LivePlanningGateway(PlanningGateway):
    operation_scope = 'saved-request-live-planning.v1'

    def __init__(self, store, *, runtime_guard):
        profile = load()
        if (profile is None or profile.runtime is None or not callable(runtime_guard)
                or profile.runtime.source_revision != store.settings.source_revision):
            raise Denied('planning_live_binding_required')
        self.profile = profile
        Gateway.__init__(self, store, LivePlanningConfig(profile), credentials=PlanningCredentials(profile))
        # A trusted host integration must independently attest this exact binding.
        self.runtime_guard = lambda: runtime_guard(profile.runtime.model_dump()) is True

    def authorize(self, *args, **kwargs):
        raise Denied('planning_observed_review_required')

    def _current_profile(self):
        current = load()
        if current is None or digest(current.model_dump()) != digest(self.config.model_dump()):
            raise Denied('planning_live_profile_changed')
        return current

    def _guard(self):
        if not self.runtime_guard or self.runtime_guard() is not True:
            raise Denied('planning_runtime_authority_lost')

    def authority(self, session, task_id, fence):
        profile = self._current_profile()
        self._guard()
        task, document = Gateway.f1_authority(self, session, task_id, fence)
        snapshot = check_context(self.store, session, task.payload)
        try:
            quote = PlanningQuote.model_validate(document['review'])
            validate_review('owner', profile, snapshot, quote, task_id=task.id, task_version=task.version,
                now=int(self.store.now(session).timestamp()), expected_quote_digest=document['review_digest'])
            if (document.get('scope') != self.operation_scope or document.get('mode') != 'live'
                    or document.get('confirmation') != CONFIRMATION or document.get('max_calls') != 1
                    or document.get('budget') != quote.maximum_nano_rub or document.get('model') != quote.model
                    or document.get('request_id') != snapshot.request_id
                    or document.get('context_digest') != snapshot.binding
                    or document.get('runtime_binding') != profile.runtime.model_dump()
                    or document.get('secret_refs') != [profile.runtime.credential_ref]
                    or document.get('business_execution') is not False):
                raise ValueError()
        except (ValueError, KeyError, AttributeError):
            raise Denied('planning_live_grant_changed') from None
        try:
            self._observed_consent(session, task, document, snapshot)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise Denied('planning_observed_consent_changed') from None
        return task, document

    def _observed_consent(self, session, task, document, snapshot):
        profile = snapshot.request_id.rsplit(':', 1)[0]
        used = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == CONSUMED,
            Audit.event['actor'].as_string() == 'owner', Audit.event['task_id'].as_string() == task.id,
            Audit.event['profile'].as_string() == profile,
            Audit.event['review_digest'].as_string() == document['review_digest']).limit(1))
        if used is None:
            raise Denied('planning_observed_consent_required')
        issued = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == ISSUED,
            Audit.event['actor'].as_string() == 'owner', Audit.event['task_id'].as_string() == task.id,
            Audit.event['profile'].as_string() == profile,
            Audit.event['card'].as_string() == used.event['card']).limit(1))
        row = session.get(TelegramInbox, used.event['inbox_id'])
        if (issued is None or issued.sequence >= used.sequence or issued.event.get('review') != document['review']
                or issued.event.get('review_digest') != document['review_digest']
                or issued.event.get('revision') != self.store.settings.source_revision
                or row is None or row.state != 'DONE' or row.profile != profile or not isinstance(row.intent, dict)
                or row.fingerprint != digest(row.intent) or row.intent.get('kind') != 'plan_authorize_confirm'
                or row.intent.get('card') != used.event['card']):
            raise Denied('planning_observed_consent_changed')
        received = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_update_received',
            Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == profile,
            Audit.event['update_id'].as_string() == row.id.rsplit(':', 1)[1],
            Audit.event['intent_hash'].as_string() == row.fingerprint,
            Audit.event['revision'].as_string() == self.store.settings.source_revision).limit(1))
        if received is None:
            raise Denied('planning_observed_consent_changed')
        observed_delivery(session, issued.event, row.intent, profile, issued.event['owner_id'])

    def request(self, task_id, fence, key, kind, method, path, body=None, *, query=None, reconcile=False):
        # Reject all non-planning scope and stale authority before reading a provider key.
        self.endpoint(kind, path, method)
        if key != KEY or query is not None or reconcile:
            raise Denied('planning_request_scope')
        with self.store.transaction() as session:
            task, document = self.authority(session, task_id, fence)
            self.admit_provider_request(task, document, body, [])
        return super().request(task_id, fence, key, kind, method, path, body, query=query, reconcile=reconcile)

    def _reserve(self, session, task_id, document, amount):
        check_financial_room(self.store, self._current_profile(), session, task_id, document['budget'], amount=amount)

    def default_pricing_required(self):
        return True

    def during_external_io(self):
        self._guard()

    def decode_external_json(self, raw):
        check_content(self.store, raw.decode('utf-8'))
        return json.loads(raw, object_pairs_hook=_unique)

    def validate_external_data(self, data, token):
        pending = [data]
        while pending:
            value = pending.pop()
            if isinstance(value, str):
                if token in value:
                    raise Uncertain('credential_echo_blocked')
                check_content(self.store, value)
            elif isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)

    def before_external_io(self, task_id, fence):
        self._guard()
        self._current_profile()
        # Recheck private-file identity after durable INTENT; never send a cached old key
        # if the installed binding was removed/rotated during admission.
        self.credentials.get(self.config.openai_secret_ref)
        if not self.store.pulse(task_id, fence):
            raise Denied('external_authority_lost')
        with self.store.transaction() as session:
            _, document = self.authority(session, task_id, fence)
            check_financial_room(self.store, self.profile, session, task_id, document['budget'], amount=0)

    def status(self, task_id):
        return {**super().status(task_id), 'production_dispatch_enabled': False}
