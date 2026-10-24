import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import URL


def secret(name: str) -> str:
    path = os.environ.get(name)
    if not path:
        raise RuntimeError(f"Required secret file binding missing: {name}")
    value = Path(path).read_text().strip()
    if not value:
        raise RuntimeError(f"Empty secret file: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str | URL = field(repr=False)
    redis_url: str
    redis_password: str = field(repr=False)
    identities: dict[str, str] = field(repr=False)
    source_revision: str
    executor_image: str = "acc-f1-executor:local"
    lease_seconds: int = 15
    timeout_seconds: int = 30
    max_attempts: int = 2
    auth_mode: str = 'synthetic'
    oidc_issuer: str = ''
    oidc_audience: str = ''
    oidc_owner: str = ''
    oidc_jwks_file: str = ''
    web_origin: str = ''

    @classmethod
    def load(cls, *, identities_required=True):
        identities = json.loads(secret("F1_IDENTITIES_FILE")) if identities_required else {}
        if identities_required and set(identities) != {"owner", "operator", "agent"}:
            raise RuntimeError("Exactly three synthetic role bindings required")
        if identities_required and (any(len(v) < 32 for v in identities.values()) or len(set(identities.values())) != 3):
            raise RuntimeError("Distinct high-entropy role credentials required")
        revision = os.environ.get("F1_SOURCE_REVISION", "")
        if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
            raise RuntimeError("Exact Git SHA required")
        url = URL.create("postgresql+psycopg", username=os.environ.get("F1_DB_USER", "f1_app"),
                         password=secret("F1_DB_PASSWORD_FILE"),
                         host=os.environ.get("F1_DB_HOST", "db"),
                         port=int(os.environ.get("F1_DB_PORT", "5432")), database="f1")
        mode = os.environ.get('F1_AUTH_MODE', 'synthetic')
        if mode not in {'synthetic', 'oidc'}:
            raise RuntimeError('unknown_auth_mode')
        return cls(url, os.environ.get("F1_REDIS_URL", "redis://redis:6379/0"),
                   secret("F1_REDIS_PASSWORD_FILE"), identities, revision,
                   os.environ.get("F1_EXECUTOR_IMAGE", "acc-f1-executor:local"),
                   auth_mode=mode, oidc_issuer=os.environ.get('F1_OIDC_ISSUER', ''),
                   oidc_audience=os.environ.get('F1_OIDC_AUDIENCE', ''),
                   oidc_owner=os.environ.get('F1_OIDC_OWNER', ''),
                   oidc_jwks_file=os.environ.get('F1_OIDC_JWKS_FILE', ''),
                   web_origin=os.environ.get('F1_WEB_ORIGIN', ''))
