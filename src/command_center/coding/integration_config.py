"""Trusted, versioned operator configuration. No tariffs/models guessed by code."""
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Literal

from pydantic import Field, model_validator
from .financial_types import NANO_RUB as NANO_RUB, Strict
from .first_experiment import FirstExperiment


class Tariff(Strict):
    model: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._:-]+$')
    input_nano_rub: int = Field(ge=0, le=NANO_RUB)
    output_nano_rub: int = Field(ge=0, le=NANO_RUB)
    fixed_nano_rub: int = Field(default=0, ge=0, le=NANO_RUB)
    context_tokens: int = Field(ge=8192, le=10_000_000)
    max_output_tokens: int = Field(ge=32, le=4096)
    confirmed: bool = False
    evidence: str = Field(min_length=1, max_length=300)
    currency: Literal['RUB'] = 'RUB'

    def maximum(self):
        return self.context_tokens * self.input_nano_rub + self.max_output_tokens * self.output_nano_rub + self.fixed_nano_rub

    def cost(self, input_tokens, output_tokens):
        if (type(input_tokens) is not int or type(output_tokens) is not int
                or not 0 <= input_tokens <= self.context_tokens or not 0 <= output_tokens <= self.max_output_tokens):
            raise ValueError('usage_outside_confirmed_tariff')
        return input_tokens * self.input_nano_rub + output_tokens * self.output_nano_rub + self.fixed_nano_rub


class IntegrationConfig(Strict):
    mode: Literal['disabled', 'http_mock', 'live'] = 'disabled'
    live_authorized: bool = False
    synthetic_repository: str = ''
    base_branch: Literal['main'] = 'main'
    tariff: Tariff | None = None
    daily_nano_rub: int = Field(default=0, ge=0, le=10_000 * NANO_RUB)
    monthly_nano_rub: int = Field(default=0, ge=0, le=10_000 * NANO_RUB)
    openai_secret_ref: str = 'openai'
    github_secret_ref: str = 'github-installation-token'
    credential_files: dict[str, str] = Field(default_factory=dict, repr=False, exclude=True)
    budget_evidence: str = Field(default='', max_length=300)
    first_experiment: FirstExperiment | None = None

    @model_validator(mode='after')
    def scope(self):
        if self.synthetic_repository and not re.fullmatch(r'[A-Za-z0-9_-]+/acc-f2-synthetic-[A-Za-z0-9_-]+', self.synthetic_repository):
            raise ValueError('only_dedicated_synthetic_repository_allowed')
        return self

    @classmethod
    def load(cls):
        path = os.environ.get('F2_INTEGRATION_CONFIG_FILE')
        expected = os.environ.get('F2_INTEGRATION_CONFIG_SHA256')
        if not path:
            if expected is not None:
                raise ValueError('integration_config_pin_without_file')
            return cls()
        p = Path(path)
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 16384:
            raise ValueError('invalid_integration_config')
        descriptor = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 16384:
                raise ValueError('invalid_integration_config')
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError('invalid_integration_config')
        if expected is not None and (not re.fullmatch('[a-f0-9]{64}', expected)
                                     or hashlib.sha256(raw).hexdigest() != expected):
            raise ValueError('integration_config_pin_changed')
        return cls.model_validate_json(raw)

    def connected(self):
        return self.mode == 'http_mock' or (self.mode == 'live' and self.live_authorized
            and bool(self.budget_evidence) and self.openai_secret_ref in self.credential_files
            and self.github_secret_ref in self.credential_files)

    def public(self):
        result = {'connected': self.connected(), 'mode': self.mode,
                'state': 'integration_not_connected' if not self.connected() else (
                    'budget_unconfirmed' if not self.tariff or not self.tariff.confirmed else 'permission_required'),
                'repository': self.synthetic_repository, 'scope': ['calculator.py'],
                'model': self.tariff.model if self.tariff else None,
                'tariff_confirmed': bool(self.tariff and self.tariff.confirmed),
                'daily_nano_rub': self.daily_nano_rub, 'monthly_nano_rub': self.monthly_nano_rub}
        if self.first_experiment:
            result['first_experiment'] = self.first_experiment.report()
        return result


class FileCredentials:
    """Aliases resolve only in trusted gateway; never accept a path from a task."""
    def __init__(self, config):
        self.config = config

    def get(self, reference):
        path = self.config.credential_files.get(reference)
        if not path:
            raise PermissionError('credential_not_connected')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor) as file:
            metadata = os.fstat(file.fileno())
            if metadata.st_mode & 0o077 or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1024:
                raise PermissionError('unsafe_credential_binding')
            value = file.read(1025).strip()
        if not 16 <= len(value) <= 1024 or '\n' in value:
            raise PermissionError('invalid_credential_binding')
        return value
