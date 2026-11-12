"""Private, offline operator evidence to an unbound profile. Never grants authority."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from .deployment_profile import atomic_json, checksum
from .planning_admission import OperatorEvidence, PlanningProfile
from .request_planning import Strict, _unique
from .store import Denied, digest
from .telegram_transport import private_read

Number = Annotated[str, StringConstraints(pattern=r'^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,12})?$', max_length=22)]
Reference = Annotated[str, StringConstraints(min_length=1, max_length=300, pattern=r'\S')]


class OperatorInput(Strict):
    purpose: Literal['planning-profile-evidence.v1']
    reviewed: Literal[True]
    model: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._:-]+$')
    pricing_currency: Literal['USD']
    usd_input_upper_per_million: Number
    usd_output_upper_per_million: Number
    usd_fixed_upper_per_request: Number
    rub_per_usd_upper: Number
    pricing_evidence: Reference
    fx_evidence: Reference
    available_rub: Number
    per_plan_limit_rub: Number
    daily_limit_rub: Number
    monthly_limit_rub: Number
    context_tokens: int = Field(ge=8192, le=10_000_000)
    max_output_tokens: int = Field(ge=32, le=4096)
    evidence: OperatorEvidence

    @field_validator('reviewed', mode='before')
    @classmethod
    def explicit_review(cls, value):
        if value is not True:
            raise ValueError('explicit_parameter_review_required')
        return value

    @model_validator(mode='before')
    @classmethod
    def metadata_only(cls, value):
        def contains_credential(item):
            if isinstance(item, str):
                return bool(re.search(r'(^|[^A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{16,}', item))
            if isinstance(item, dict):
                return any(contains_credential(k) or contains_credential(v) for k, v in item.items())
            if isinstance(item, list):
                return any(contains_credential(v) for v in item)
            return False
        if contains_credential(value):
            raise ValueError('operator_metadata_contains_credential_shape')
        return value


def template():
    value = dict.fromkeys(OperatorInput.model_fields)
    value.update(purpose='planning-profile-evidence.v1', reviewed=False,
                 pricing_currency='USD', context_tokens=8192, max_output_tokens=4096,
                 evidence=dict.fromkeys(OperatorEvidence.model_fields))
    return value


def convert(data, *, now):
    """Rates round up per token; available money and all owner ceilings round down."""
    try:
        reviewed = OperatorInput.model_validate(data)
        if (type(now) is not int or not reviewed.evidence.observed_at <= now < reviewed.evidence.expires_at):
            raise ValueError()
        with localcontext() as context:
            context.prec = 100
            fx = Decimal(reviewed.rub_per_usd_upper)
            if fx <= 0:
                raise ValueError()
            def up(value, divisor=1):
                return int((Decimal(value) * fx * Decimal(10**9) / divisor).to_integral_value(rounding=ROUND_CEILING))
            def down(value):
                return int((Decimal(value) * Decimal(10**9)).to_integral_value(rounding=ROUND_FLOOR))
            ceilings = {k: down(getattr(reviewed, k)) for k in (
                'available_rub', 'per_plan_limit_rub', 'daily_limit_rub', 'monthly_limit_rub')}
            if any(not 0 < amount <= 100 * 10**9 for amount in ceilings.values()):
                raise ValueError()
            evidence_digest = digest(reviewed.model_dump())
            profile = PlanningProfile.model_validate({
                'tariff': {'model': reviewed.model, 'input_nano_rub': up(reviewed.usd_input_upper_per_million, 10**6),
                    'output_nano_rub': up(reviewed.usd_output_upper_per_million, 10**6),
                    'fixed_nano_rub': up(reviewed.usd_fixed_upper_per_request),
                    'context_tokens': reviewed.context_tokens, 'max_output_tokens': reviewed.max_output_tokens,
                    'confirmed': True, 'evidence': 'operator-review:' + evidence_digest},
                'evidence': reviewed.evidence.model_dump(), 'available_nano_rub': ceilings['available_rub'],
                'daily_nano_rub': ceilings['daily_limit_rub'], 'monthly_nano_rub': ceilings['monthly_limit_rub']})
            if profile.tariff.maximum() > ceilings['per_plan_limit_rub']:
                raise ValueError()
        conversion = {'purpose': 'planning-profile-conversion.v1', 'input_digest': evidence_digest,
            'pricing_evidence': reviewed.pricing_evidence, 'fx_evidence': reviewed.fx_evidence,
            'usd_input_upper_per_million': reviewed.usd_input_upper_per_million,
            'usd_output_upper_per_million': reviewed.usd_output_upper_per_million,
            'usd_fixed_upper_per_request': reviewed.usd_fixed_upper_per_request,
            'rub_per_usd_upper': reviewed.rub_per_usd_upper, 'rounding': 'rates_up_limits_down',
            'ceilings_nano_rub': ceilings, 'maximum_nano_rub': profile.tariff.maximum(),
            'runtime_bound': False, 'deployment_authorized': False, 'paid_calls_authorized': False}
        return profile, conversion
    except (ValueError, TypeError, ArithmeticError):
        raise ValueError('planning_reviewed_operator_inputs_invalid') from None


def read_input(path):
    try:
        path = Path(path)
        if path.name != 'operator-evidence.json':
            raise ValueError()
        raw = private_read(path, 16384)
        if len(raw) > 16384:
            raise ValueError()
        return raw, json.loads(raw, object_pairs_hook=_unique)
    except (OSError, ValueError, Denied, RecursionError):
        raise ValueError('planning_private_operator_input_invalid') from None


def inspect_input(path):
    _, data = read_input(path)
    try:
        OperatorInput.model_validate(data)
    except ValidationError as error:
        # Include neither input values, validation context, messages nor arbitrary
        # user-supplied field names (a secret could itself be a JSON key).
        issues = [{'field': str(e['loc'][0]) if e['loc'] and e['loc'][0] in OperatorInput.model_fields else 'unrecognized_field',
                   'code': e['type']} for e in error.errors(include_input=False, include_context=False, include_url=False)]
        return {'status': 'OPERATOR_INPUT_INCOMPLETE_OR_INVALID', 'issues': issues, 'paid_calls_authorized': False}
    profile, _ = convert(data, now=int(time.time()))
    return {'status': 'REVIEWED_OPERATOR_INPUT_VALID_NOT_AUTHORITY', 'model': profile.tariff.model,
            'maximum_nano_rub': profile.tariff.maximum(), 'paid_calls_authorized': False}


def profile_pin(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def prepare(path, approved_input, output):
    if os.name != 'posix' or os.geteuid() < 1000:
        raise ValueError('dedicated_unprivileged_profile_operator_required')
    raw, data = read_input(path)
    if not re.fullmatch('[a-f0-9]{64}', approved_input) or hashlib.sha256(raw).hexdigest() != approved_input:
        raise ValueError('planning_exact_operator_input_required')
    profile, conversion = convert(data, now=int(time.time()))
    output = Path(output)
    parent = output.parent.stat()
    source_root = Path(__file__).resolve().parents[2]
    if (not output.is_absolute() or output.resolve() != output or output.is_symlink()
            or output.is_relative_to(source_root) or source_root.is_relative_to(output)
            or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o077):
        raise ValueError('planning_new_private_profile_directory_required')
    if private_read(path, 16384) != raw:
        raise ValueError('planning_operator_input_changed')
    output.mkdir(mode=0o700)  # exclusive; never replaces evidence or a prior profile
    documents = {'operator-evidence.json': data, 'profile.json': profile.model_dump(), 'conversion.json': conversion}
    for name, value in documents.items():
        atomic_json(output / name, value)
    receipt = {'purpose': 'planning-operator-profile-preparation.v1', 'input_raw_sha256': approved_input,
               'files': {name: profile_pin(value) for name, value in documents.items()},
               'runtime_bound': False, 'deployment_authorized': False, 'paid_calls_authorized': False}
    atomic_json(output / 'creation.json', receipt)
    return {'status': 'OPERATOR_PROFILE_PREPARED_NOT_INSTALLED', 'profile_sha256': receipt['files']['profile.json'],
            'creation_digest': checksum(receipt), 'maximum_nano_rub': profile.tariff.maximum(),
            'runtime_bound': False, 'paid_calls_authorized': False}


def inspect_profile(directory, approved_creation):
    directory = Path(directory)
    if {p.name for p in directory.iterdir()} != {'operator-evidence.json', 'profile.json', 'conversion.json', 'creation.json'}:
        raise ValueError('planning_operator_profile_inventory_changed')
    receipt = json.loads(private_read(directory / 'creation.json', 16384), object_pairs_hook=_unique)
    if (not re.fullmatch('[a-f0-9]{64}', approved_creation) or checksum(receipt) != approved_creation
            or set(receipt) != {'purpose', 'input_raw_sha256', 'files', 'runtime_bound', 'deployment_authorized', 'paid_calls_authorized'}
            or receipt['purpose'] != 'planning-operator-profile-preparation.v1'
            or any(receipt[k] is not False for k in ('runtime_bound', 'deployment_authorized', 'paid_calls_authorized'))
            or set(receipt['files']) != {'operator-evidence.json', 'profile.json', 'conversion.json'}):
        raise ValueError('planning_exact_operator_creation_required')
    documents = {}
    for name, pin in receipt['files'].items():
        raw = private_read(directory / name, 16384)
        if hashlib.sha256(raw).hexdigest() != pin:
            raise ValueError('planning_operator_profile_file_changed')
        documents[name] = json.loads(raw, object_pairs_hook=_unique)
    profile, conversion = convert(documents['operator-evidence.json'], now=int(time.time()))
    if (documents['profile.json'] != profile.model_dump() or documents['conversion.json'] != conversion
            or not re.fullmatch('[a-f0-9]{64}', receipt['input_raw_sha256'])):
        raise ValueError('planning_operator_conversion_changed')
    return {'status': 'OPERATOR_PROFILE_VERIFIED_NOT_INSTALLED', 'profile_sha256': receipt['files']['profile.json'],
            'maximum_nano_rub': profile.tariff.maximum(), 'runtime_bound': False, 'paid_calls_authorized': False}
