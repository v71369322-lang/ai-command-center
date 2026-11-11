"""Offline live-planning review contract. Never creates authority or provider I/O."""
from typing import Literal
from uuid import UUID

from pydantic import Field, ValidationError, model_validator

from .coding.financial_types import NANO_RUB
from .coding.integration_config import Tariff
from .project_inbox import owner
from .request_planning import HEX, PlanningContext, Strict, request_document
from .store import Denied, digest


class OperatorEvidence(Strict):
    # References to operator-reviewed evidence, never credentials or provider balances.
    account: str = Field(min_length=1, max_length=300, pattern=r'\S')
    model: str = Field(min_length=1, max_length=300, pattern=r'\S')
    funding: str = Field(min_length=1, max_length=300, pattern=r'\S')
    data_sharing: str = Field(min_length=1, max_length=300, pattern=r'\S')
    observed_at: int = Field(ge=0)
    expires_at: int = Field(ge=1)

    @model_validator(mode='after')
    def bounded(self):
        if not 0 < self.expires_at - self.observed_at <= 86400:
            raise ValueError('bounded_evidence_window_required')
        return self


class PlanningProfile(Strict):
    schema_version: Literal[1] = 1
    purpose: Literal['saved-request-live-planning.v1'] = 'saved-request-live-planning.v1'
    project_id: Literal['command-center'] = 'command-center'
    tariff: Tariff
    evidence: OperatorEvidence
    available_nano_rub: int = Field(gt=0, le=100 * NANO_RUB)
    daily_nano_rub: int = Field(gt=0, le=100 * NANO_RUB)
    monthly_nano_rub: int = Field(gt=0, le=100 * NANO_RUB)

    @model_validator(mode='after')
    def bounded(self):
        if (not self.tariff.confirmed or not self.tariff.evidence.strip()
                or not 0 < self.tariff.maximum() <= min(
                    self.available_nano_rub, self.daily_nano_rub, self.monthly_nano_rub)):
            raise ValueError('confirmed_bounded_tariff_required')
        return self


class PlanningQuote(Strict):
    purpose: Literal['saved-request-live-planning.v1']
    task_id: str
    task_version: int = Field(ge=1)
    request_id: str
    context_digest: str = Field(pattern=HEX)
    source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    profile_digest: str = Field(pattern=HEX)
    provider_request_digest: str = Field(pattern=HEX)
    model: str
    maximum_nano_rub: int = Field(gt=0)
    issued_at: int = Field(ge=0)
    expires_at: int = Field(ge=1)
    max_calls: Literal[1] = 1
    execution_authorized: Literal[False] = False


def _quote(profile, snapshot, task_id, task_version, issued_at, expires_at):
    # Revalidate nested mutable Tariff values; frozen outer models alone are insufficient.
    try:
        profile = PlanningProfile.model_validate(profile.model_dump())
        snapshot = PlanningContext.model_validate(snapshot.model_dump())
        if str(UUID(task_id, version=4)) != task_id:
            raise ValueError()
        if (snapshot.halted or snapshot.recovery or snapshot.project_id != profile.project_id
                or type(issued_at) is not int or type(expires_at) is not int
                or not profile.evidence.observed_at <= issued_at < expires_at <= profile.evidence.expires_at
                or not 0 < expires_at - issued_at <= 120):
            raise ValueError()
        tariff = profile.tariff
        body = request_document(snapshot, tariff.model, context_tokens=tariff.context_tokens,
                                max_output_tokens=tariff.max_output_tokens)
        return PlanningQuote(purpose=profile.purpose, task_id=task_id, task_version=task_version,
            request_id=snapshot.request_id, context_digest=snapshot.binding,
            source_revision=snapshot.source_revision, profile_digest=digest(profile.model_dump()),
            provider_request_digest=digest(body), model=tariff.model,
            maximum_nano_rub=tariff.maximum(), issued_at=issued_at, expires_at=expires_at)
    except (ValueError, TypeError, AttributeError):
        raise Denied('planning_review_scope_invalid') from None


def prepare_review(actor, profile, snapshot, *, task_id, task_version, now, seconds=120):
    """Pure review material. No DB, HTTP client, credential read, approval or reservation."""
    owner(actor)
    if type(now) is not int or type(seconds) is not int or not 1 <= seconds <= 120:
        raise Denied('planning_review_window_invalid')
    return _quote(profile, snapshot, task_id, task_version, now, now + seconds)


def validate_review(actor, profile, snapshot, quote, *, task_id, task_version, now,
                    expected_quote_digest):
    """Check exact review against current inputs; caller still needs transactional F1 authority.

    A digest is a binding, not proof of an owner click. A future Telegram callback must
    authenticate the owner and use Store.approve/ExternalGrant and the shared ledger.
    This function must never be treated as a replacement for those checks.
    """
    owner(actor)
    try:
        quote = PlanningQuote.model_validate(quote.model_dump())
    except (ValidationError, AttributeError):
        raise Denied('planning_review_changed') from None
    if (type(now) is not int or not quote.issued_at <= now < quote.expires_at
            or digest(quote.model_dump()) != expected_quote_digest):
        raise Denied('planning_review_changed_or_expired')
    current = _quote(profile, snapshot, task_id, task_version, quote.issued_at, quote.expires_at)
    if current != quote:
        raise Denied('planning_review_changed')
    return current
