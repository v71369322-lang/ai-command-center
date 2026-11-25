"""Opt-in signed create/get transport, separate from the read-only bridge."""
import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from contextlib import contextmanager

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .calendar_drafts import validate, _uuid
from .google_calendar_contract import verify_event
from .google_script_calendar import ScriptCalendarHTTP, ScriptCalendarProfile, envelope
from .store import Denied, digest
from .telegram_transport import private_read

PROTOCOL = 'jarvis-calendar-create-v1'
REQUEST = 'JARVIS_CALENDAR_CREATE_REQUEST_V1'
RESPONSE = 'JARVIS_CALENDAR_CREATE_RESPONSE_V1'


class ScriptWriteProfile(ScriptCalendarProfile):
    """A separate exact grant; the existing agenda profile never grants writes."""
    calendar_id: str = Field(pattern=r'^[a-zA-Z0-9_.@-]{1,256}$')
    calendar_label: str = Field(min_length=1, max_length=100)
    create_enabled: StrictBool = False


class ScriptWriteHTTP:
    def __init__(self, profile, approved, key, *, transport=None, clock=time.time):
        self.profile = ScriptWriteProfile.model_validate(profile.model_dump())
        if not self.profile.create_enabled or digest(self.profile.model_dump()) != approved:
            raise Denied('calendar_write_exact_profile_required')
        read = ScriptCalendarProfile.model_validate({k: v for k, v in self.profile.model_dump().items()
            if k in ScriptCalendarProfile.model_fields})
        self._http = ScriptCalendarHTTP(read, digest(read.model_dump()), key, transport=transport, clock=clock)
        self._clock, self._closed = clock, False

    def __repr__(self):
        return '<ScriptWriteHTTP credentials=redacted>'

    def _call(self, action, draft_id, document):
        if self._closed:
            raise Denied('calendar_write_connection_closed')
        _uuid(draft_id)
        document = validate(document)
        if document['timezone'] != self.profile.timezone:
            raise Denied('calendar_write_timezone_mismatch')
        request = {'protocol': PROTOCOL, 'connection': self.profile.connection_id,
            'calendar_id': self.profile.calendar_id,
            'nonce': secrets.token_hex(16), 'issued_at': int(self._clock()), 'action': action,
            'draft_id': draft_id, 'document_hash': digest(document), 'document': document}
        try:
            return asyncio.run(self._request(request))
        except Exception:
            # A failed response is not evidence that insertion did not happen.
            raise Denied('calendar_write_result_unknown') from None

    async def _request(self, request):
        # No retry of a write, including redirects/timeouts/provider errors.
        async with asyncio.timeout(12):
            async with httpx.AsyncClient(transport=self._http._transport, follow_redirects=False,
                                         trust_env=False, timeout=5) as client:
                signed = await self._http._read(client, 'POST', self._http._url,
                    envelope(request, self._http._key, REQUEST))
                if (not isinstance(signed, dict) or set(signed) != {'payload', 'signature'}
                        or not isinstance(signed['payload'], str) or len(signed['payload']) > 16000
                        or not isinstance(signed['signature'], str)):
                    raise ValueError()
                signature = hmac.new(self._http._key.encode(),
                    (RESPONSE + '\n' + signed['payload']).encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(signature, signed['signature']):
                    raise ValueError()
                result = json.loads(base64.b64decode(signed['payload'], validate=True))
                if (not isinstance(result, dict) or set(result) != {'protocol', 'connection', 'nonce',
                        'issued_at', 'action', 'draft_id', 'document_hash', 'calendar_id', 'status', 'event'}
                        or any(result.get(k) != request[k] for k in
                               ('protocol', 'connection', 'nonce', 'action', 'draft_id', 'document_hash', 'calendar_id'))
                        or type(result['issued_at']) is not int
                        or abs(self._clock() - result['issued_at']) > 60):
                    raise ValueError()
                if result['status'] == 'ABSENT' and request['action'] == 'get' and result['event'] is None:
                    return None
                if result['status'] != 'FOUND':
                    raise ValueError()
                event = result['event']
                if not isinstance(event, dict) or event.get('id') != request['draft_id'].replace('-', ''):
                    raise ValueError()
                verify_event(event, request['draft_id'], request['document'])
                if event.get('description') != request['document']['note']:
                    raise ValueError()
                return event

    def create(self, draft_id, document):
        return self._call('create', draft_id, document)

    def lookup(self, draft_id, document):
        return self._call('get', draft_id, document)

    def close(self):
        self._closed = True
        self._http.close()


class ScriptWriteConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    profile: ScriptWriteProfile
    key_file: str


@contextmanager
def script_write_runtime(path, approved, revision, owner):
    try:
        config = ScriptWriteConfig.model_validate_json(private_read(path, 8192))
        if (digest(config.model_dump()) != approved or config.profile.source_revision != revision
                or config.profile.owner_id != owner):
            raise ValueError()
        key = private_read(config.key_file, 32)
        if len(key) != 32:
            raise ValueError()
        client = ScriptWriteHTTP(config.profile, digest(config.profile.model_dump()), key.hex())
    except Exception:
        raise Denied('calendar_write_runtime_exact_connection_required') from None
    try:
        yield client
    finally:
        client.close()
