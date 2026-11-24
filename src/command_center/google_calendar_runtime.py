"""Explicit opt-in runtime custody, bound to one Telegram owner/source revision."""
import json
from contextlib import contextmanager

from pydantic import BaseModel, ConfigDict, Field

from .google_calendar_access import CalendarAccess
from .google_calendar_oauth import CalendarOAuthHTTP
from .google_calendar_setup import CalendarCredentialFiles, connected_calendar
from .store import Denied, digest
from .telegram_transport import private_read


class CalendarRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    profile: CalendarAccess
    client_id: str = Field(pattern=r'^[A-Za-z0-9._-]{20,170}\.apps\.googleusercontent\.com$')
    custody_directory: str


@contextmanager
def calendar_runtime(config_file, approved_config, revision, owner):
    """Opening this context performs no Google HTTP, no binding or grant creation."""
    try:
        config = CalendarRuntimeConfig.model_validate_json(private_read(config_file, 8192))
        if (digest(config.model_dump()) != approved_config or not config.profile.enabled
                or config.profile.source_revision != revision or config.profile.owner_id != owner):
            raise ValueError()
    except Exception:
        raise Denied('google_calendar_runtime_exact_approval_required') from None
    with CalendarCredentialFiles(config.custody_directory) as files:
        try:
            # Dedicated protected OAuth client material, never an environment value.
            client = json.loads(files._read('oauth-client.json', 4096))
            if (not isinstance(client, dict) or set(client) != {'client_id', 'client_secret'}
                    or client['client_id'] != config.client_id):
                raise ValueError()
            oauth = CalendarOAuthHTTP(config.client_id, client['client_secret'])
        except Exception:
            raise Denied('google_calendar_runtime_client_unavailable') from None
        try:
            calendar = connected_calendar(config.profile, digest(config.profile.model_dump()), revision, oauth, files)
            try:
                yield calendar
            finally:
                calendar.close()
        finally:
            oauth.close()
