from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .spec import BASE_SHA, OBJECTIVE, PLAN, REPOSITORY


class CodingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    repository: Literal['f2-synthetic-sum'] = REPOSITORY
    objective: Literal['sum_positive_v1'] = OBJECTIVE
    base_sha: str = Field(default=BASE_SHA, pattern='^[a-f0-9]{40}$')
    provider: Literal['mock', 'openai'] = 'mock'
    experiment_id: Literal['f2.2-first-live'] | None = None
    max_iterations: int = Field(default=2, ge=1, le=3, strict=True)
    max_units: int = Field(default=2, ge=1, le=3, strict=True)
    max_tokens: int = Field(default=2048, ge=64, le=4096, strict=True)
    max_seconds: int = Field(default=15, ge=1, le=120, strict=True)
    scenario: Literal['normal', 'unavailable', 'always_fail', 'escape_attempt', 'pin_change', 'slow'] = 'normal'


def payload(request: CodingRequest):
    if request.base_sha != BASE_SHA:
        raise ValueError('synthetic_source_pin_mismatch')
    return {'kind': 'coding_synthetic', 'coding': request.model_dump(), 'cost': request.max_units}


def validate_payload(value):
    if set(value) != {'kind', 'coding', 'cost'} or value['kind'] != 'coding_synthetic':
        raise ValueError('invalid_coding_scope')
    validated = payload(CodingRequest.model_validate(value['coding']))
    if type(value['cost']) is not int or value != validated:
        raise ValueError('coding_budget_scope_mismatch')
    return validated


def template():
    return {'repository': REPOSITORY, 'objective': OBJECTIVE, 'base_sha': BASE_SHA,
            'provider': 'mock', 'real_ai_connected': False, 'plan': PLAN,
            'allowed_files': ['calculator.py']}
