"""One bounded first experiment; public facts never imply live permission."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Literal

from pydantic import Field

from ..store import Denied
from .financial_types import NANO_RUB, Strict
from .spec import BASE_SHA

EXPERIMENT_ID = 'f2.2-first-live'
RECOVERY_ID = 'f2.2-recovery-1'
MODEL = 'gpt-5.4-mini-2026-03-17'
MODEL_SOURCE = 'https://developers.openai.com/api/docs/models/gpt-5.4-mini'
PRICE_SOURCE = 'https://developers.openai.com/api/docs/pricing'
FX_SOURCE = 'https://www.cbr.ru/currency_base/daily/?UniDbQuery.Posted=True&UniDbQuery.To=24.10.2026'
CHECKED_ON = '2026-10-24'
USD_INPUT_PER_MILLION = Decimal('0.75')
USD_OUTPUT_PER_MILLION = Decimal('4.50')
CBR_RUB_PER_USD = Decimal('80.5381')
CONTEXT_TOKENS, OUTPUT_TOKENS, CALLS = 400_000, 2048, 2
CAP = 100 * NANO_RUB
REQUIRED = ('model_access', 'current_price', 'payment_bound', 'openai_credential',
            'github_app', 'repository', 'runtime', 'dry_run', 'existing_funding')


def quote(rub_per_usd=CBR_RUB_PER_USD, extra_rub=Decimal(0), *, calls=CALLS):
    if type(calls) is not int or calls not in {1, CALLS}:
        raise ValueError('invalid_call_bound')
    rate, extra = Decimal(rub_per_usd), Decimal(extra_rub)
    if not rate.is_finite() or not extra.is_finite() or rate <= 0 or extra < 0:
        raise ValueError('invalid_payment_bound')
    per_call = (CONTEXT_TOKENS * USD_INPUT_PER_MILLION + OUTPUT_TOKENS * USD_OUTPUT_PER_MILLION) / 1_000_000
    usd = per_call * calls
    rub = usd * rate + extra
    return {'max_usd': str(usd), 'max_rub': str(rub),
            'max_nano_rub': int((rub * NANO_RUB).to_integral_value(rounding=ROUND_CEILING)),
            'cbr_rub_per_usd': str(CBR_RUB_PER_USD), 'conversion_rub_per_usd': str(rate),
            'extra_rub': str(extra), 'within_100_rub': rub <= 100,
            'is_provider_hard_cap': False}


REQUEST_KEY = 'first-experiment-f2-2'
RECOVERY_REQUEST_KEY = 'first-experiment-f2-2-recovery'


def request_key(experiment_id=EXPERIMENT_ID):
    if experiment_id not in {EXPERIMENT_ID, RECOVERY_ID}:
        raise Denied('unknown_experiment_scope')
    return REQUEST_KEY if experiment_id == EXPERIMENT_ID else RECOVERY_REQUEST_KEY


def task_payload(experiment_id=EXPERIMENT_ID):
    """One immutable request shared by the API and read-only owner views."""
    from .contract import CodingRequest, payload
    request_key(experiment_id)
    calls = 1 if experiment_id == RECOVERY_ID else CALLS
    return payload(CodingRequest(provider='openai', experiment_id=experiment_id, max_iterations=calls,
                                 max_units=calls, max_tokens=4096, max_seconds=30))


def create_task(store, actor, *, _scope_installer=None, experiment_id=EXPERIMENT_ID):
    """The same fixed, waiting F1 request for API and Telegram; no provider grant."""
    if actor != 'owner':
        raise Denied('owner_required')
    if experiment_id == RECOVERY_ID:
        from .integration_config import IntegrationConfig
        from .recovery import RecoveryExperiment
        config = IntegrationConfig.load()
        if not isinstance(config.first_experiment, RecoveryExperiment):
            raise Denied('recovery_profile_required')
        def install(session, task):
            config.first_experiment.verify_parent(store, session, config)
            if _scope_installer:
                _scope_installer(session, task)
        return store.create(actor, request_key(experiment_id), task_payload(experiment_id), _scope_installer=install)
    return store.create(actor, request_key(experiment_id), task_payload(experiment_id), _scope_installer=_scope_installer)


class Evidence(Strict):
    reference: str = Field(min_length=1, max_length=300)
    expires_at: str = Field(min_length=20, max_length=40)

    def current(self, now):
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            return expiry.tzinfo is not None and expiry > now
        except ValueError:
            return False


class FirstExperiment(Strict):
    id: Literal['f2.2-first-live'] = EXPERIMENT_ID
    model: Literal['gpt-5.4-mini-2026-03-17'] = MODEL
    # These are verified upper-bound payment terms, NOT the CBR reference quote.
    payment_rub_per_usd_upper: str | None = None
    extra_rub_upper: str | None = None
    existing_credit_usd: str | None = None
    repository_id: int | None = Field(default=None, gt=0, strict=True)
    evidence: dict[str, Evidence] = Field(default_factory=dict)

    @property
    def call_limit(self):
        return CALLS

    @property
    def budget_cap(self):
        return CAP

    def report(self, now=None):
        now = now or datetime.now(timezone.utc)
        terms = None
        if self.payment_rub_per_usd_upper is not None and self.extra_rub_upper is not None:
            try:
                terms = quote(self.payment_rub_per_usd_upper, self.extra_rub_upper, calls=self.call_limit)
            except (ValueError, InvalidOperation):
                pass
        gates = {key: key in self.evidence and self.evidence[key].current(now) for key in REQUIRED}
        gates['payment_bound'] = gates['payment_bound'] and terms is not None and terms['within_100_rub']
        gates['repository'] = gates['repository'] and self.repository_id is not None
        try:
            funding = Decimal(self.existing_credit_usd) if self.existing_credit_usd is not None else Decimal('-1')
            gates['existing_funding'] = gates['existing_funding'] and funding.is_finite() and funding >= Decimal(quote(calls=self.call_limit)['max_usd'])
        except (ValueError, InvalidOperation):
            gates['existing_funding'] = False
        return {'id': self.id, 'task': 'Реализовать сумму положительных чисел в calculator.py',
                'model': self.model, 'base_sha': BASE_SHA, 'max_calls': self.call_limit, 'max_repairs': self.call_limit - 1,
                'max_output_tokens_per_call': OUTPUT_TOKENS, 'max_budget_nano_rub': self.budget_cap,
                'service_tier': 'default', 'checked_on': CHECKED_ON,
                'price': {'input_usd_per_million': str(USD_INPUT_PER_MILLION),
                          'output_usd_per_million': str(USD_OUTPUT_PER_MILLION)},
                'sources': {'model': MODEL_SOURCE, 'price': PRICE_SOURCE, 'fx': FX_SOURCE},
                'reference_quote': quote(calls=self.call_limit), 'payment_quote': terms, 'gates': gates,
                'final_owner_confirmation': False, 'ready_for_final_confirmation': all(gates.values()),
                'live_started': False, 'repository_id': self.repository_id}

    def validate_scope(self, config, coding, budget, now, *, final_confirmation=False):
        if (coding.get('experiment_id') != self.id or coding.get('provider') != 'openai'
                or coding['base_sha'] != BASE_SHA or coding['max_iterations'] > self.call_limit
                or coding['max_units'] > self.call_limit or budget > self.budget_cap):
            raise Denied('first_experiment_scope_or_budget')
        if not config.tariff or config.tariff.model != self.model or config.tariff.max_output_tokens > OUTPUT_TOKENS:
            raise Denied('first_experiment_tariff_mismatch')
        if config.mode == 'live':
            status = self.report(now)
            if not status['ready_for_final_confirmation']:
                raise Denied('first_experiment_preconditions_missing')
            if not final_confirmation:
                raise Denied('first_experiment_final_confirmation_required')
            if config.daily_nano_rub > CAP or config.monthly_nano_rub > CAP:
                raise Denied('first_experiment_global_budget')
            if config.tariff.context_tokens != CONTEXT_TOKENS:
                raise Denied('first_experiment_context_bound')
            rate = Decimal(self.payment_rub_per_usd_upper)
            need_input = int((USD_INPUT_PER_MILLION * rate * 1000).to_integral_value(rounding=ROUND_CEILING))
            need_output = int((USD_OUTPUT_PER_MILLION * rate * 1000).to_integral_value(rounding=ROUND_CEILING))
            if config.tariff.input_nano_rub < need_input or config.tariff.output_nano_rub < need_output:
                raise Denied('first_experiment_underpriced_profile')
            # Fixed extra costs must be conservatively included, once per allowed call.
            extra = int((Decimal(self.extra_rub_upper) * NANO_RUB / self.call_limit).to_integral_value(rounding=ROUND_CEILING))
            if config.tariff.fixed_nano_rub < extra or config.tariff.maximum() * self.call_limit > self.budget_cap:
                raise Denied('first_experiment_total_cost_bound')


def validate_repository_identity(metadata, branch, expected_name, expected_id):
    permissions = metadata.get('permissions')
    if (type(expected_id) is not int or type(metadata.get('id')) is not int or metadata.get('id') != expected_id
            or metadata.get('full_name') != expected_name or metadata.get('archived') is not False
            or metadata.get('disabled') is not False or not isinstance(permissions, dict)
            or permissions.get('admin') is not False
            or branch.get('name') != 'main' or branch.get('protected') is not True
            or branch.get('commit', {}).get('sha') != BASE_SHA):
        raise Denied('first_experiment_repository_preflight')


def validate_repository(metadata, branch, expected_name, expected_id, *, git_discovery=None):
    from .git_capability import valid_discovery
    validate_repository_identity(metadata, branch, expected_name, expected_id)
    permissions = metadata['permissions']
    if git_discovery is not None:
        if not valid_discovery(git_discovery, expected_name, BASE_SHA):
            raise Denied('first_experiment_repository_preflight')
    elif permissions.get('push') is not True:
        raise Denied('first_experiment_repository_preflight')
