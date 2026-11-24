"""Authenticated read-only Apps Script transport; no OAuth tokens or event writes."""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .store import Denied, digest
from .telegram_transport import private_read

PROTOCOL = 'jarvis-agenda-v1'


class ScriptCalendarProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    enabled: StrictBool = False
    owner_id: int = Field(strict=True, gt=0, lt=2**52, repr=False)
    source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    deployment_id: str = Field(pattern=r'^[A-Za-z0-9_-]{20,200}$')
    connection_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    key_fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    timezone: str = Field(default='Europe/Moscow', pattern=r'^Europe/Moscow$')


def envelope(value, key, purpose):
    payload = base64.b64encode(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).decode()
    return {'payload': payload, 'signature': hmac.new(key.encode(),
        (purpose + '\n' + payload).encode(), hashlib.sha256).hexdigest()}


class _ContentURLFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        clean = re.sub(r'https://script\.googleusercontent\.com/[^\s\"\']+',
                       'https://script.googleusercontent.com/[redacted]', message)
        if clean != message:
            record.msg, record.args = clean, ()
            record.exc_info, record.exc_text = None, None
        return True


def _instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError()
    return parsed


class ScriptCalendarHTTP:
    def __init__(self, profile, approved, key, *, transport=None, clock=time.time, sleep=None):
        self.profile = ScriptCalendarProfile.model_validate(profile.model_dump())
        if (not self.profile.enabled or digest(self.profile.model_dump()) != approved
                or not isinstance(key, str) or not re.fullmatch('[a-f0-9]{64}', key)
                or hashlib.sha256(bytes.fromhex(key)).hexdigest() != self.profile.key_fingerprint
                or (transport is not None and not isinstance(transport, httpx.MockTransport))):
            raise Denied('google_script_exact_connection_required')
        self._key, self._clock, self._sleep = key, clock, sleep
        self._transport, self._closed = transport, False
        self._url = 'https://script.google.com/macros/s/' + self.profile.deployment_id + '/exec'
        logger = logging.getLogger('httpx')
        if not any(isinstance(item, _ContentURLFilter) for item in logger.filters):
            logger.addFilter(_ContentURLFilter())

    def __repr__(self):
        return '<ScriptCalendarHTTP credentials=redacted>'

    async def _read(self, client, method, url, body=None):
        async with client.stream(method, url, json=body) as response:
            if response.status_code in {502, 503, 504}:
                raise httpx.TransportError('google_script_temporarily_unavailable')
            if method == 'POST' and response.status_code in {302, 303}:
                target = response.headers.get('location', '')
                parsed = urlsplit(target)
                if (len(target) > 8192 or parsed.scheme != 'https'
                        or parsed.netloc != 'script.googleusercontent.com'
                        or parsed.path != '/macros/echo' or parsed.fragment):
                    raise ValueError()
                # ContentService redirects to a one-time content URL. Do not
                # forward the signed request body/headers or follow further hops.
                return await self._read(client, 'GET', target)
            if response.status_code != 200:
                raise ValueError()
            data = bytearray()
            async for chunk in response.aiter_bytes(8192):
                data.extend(chunk)
                if len(data) > 65536:
                    raise ValueError()
            return json.loads(data)

    def _verify(self, signed, request):
        if (not isinstance(signed, dict) or set(signed) != {'payload', 'signature'}
                or not isinstance(signed['payload'], str) or len(signed['payload']) > 60000
                or not isinstance(signed['signature'], str)
                or not re.fullmatch('[a-f0-9]{64}', signed['signature'])):
            raise ValueError()
        expected = hmac.new(self._key.encode(), ('JARVIS_CALENDAR_RESPONSE_V1\n' + signed['payload']).encode(),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signed['signature']):
            raise ValueError()
        result = json.loads(base64.b64decode(signed['payload'], validate=True))
        if (not isinstance(result, dict) or set(result) != {'protocol', 'connection', 'nonce', 'issued_at',
                'start', 'end', 'timezone', 'events', 'truncated'}
                or any(result.get(name) != request[name] for name in ('protocol', 'connection', 'nonce', 'start', 'end'))
                or type(result['issued_at']) is not int or abs(self._clock() - result['issued_at']) > 60
                or result['timezone'] != self.profile.timezone or type(result['truncated']) is not bool
                or not isinstance(result['events'], list) or len(result['events']) > 50):
            raise ValueError()
        for event in result['events']:
            if (not isinstance(event, dict) or set(event) != {'summary', 'start', 'end'}
                    or not isinstance(event['summary'], str) or len(event['summary']) > 120):
                raise ValueError()
            event['summary'].encode('utf-8')
            for field in ('start', 'end'):
                moment = event[field]
                if not isinstance(moment, dict):
                    raise ValueError()
                if set(moment) == {'dateTime'}:
                    _instant(moment['dateTime'])
                elif set(moment) == {'date'}:
                    datetime.strptime(moment['date'], '%Y-%m-%d')
                else:
                    raise ValueError()
        return {'events': result['events'], 'timezone': result['timezone'], 'start': request['start'],
                'end': request['end'], 'truncated': result['truncated'], 'source': 'Google Calendar'}

    def agenda(self, start, end):
        if self._closed:
            raise Denied('google_script_calendar_closed')
        try:
            first, last = _instant(start), _instant(end)
            if not 0 < (last - first).total_seconds() <= 7 * 86400:
                raise ValueError()
        except Exception:
            raise Denied('google_agenda_interval_invalid') from None
        try:
            # This adapter is called by the synchronous Telegram poller. A fresh
            # async client per call avoids cross-loop connection reuse and lets
            # one total timeout cancel slow headers/bodies as well as retries.
            return asyncio.run(self._agenda(start, end))
        except Exception:
            raise Denied('google_script_calendar_unavailable') from None

    async def _agenda(self, start, end):
        async with asyncio.timeout(12):
            async with httpx.AsyncClient(transport=self._transport, follow_redirects=False,
                                         trust_env=False, timeout=5) as client:
                for attempt in range(2):
                    request = {'protocol': PROTOCOL, 'connection': self.profile.connection_id,
                        'nonce': secrets.token_hex(16), 'issued_at': int(self._clock()), 'start': start, 'end': end}
                    try:
                        signed = await self._read(client, 'POST', self._url,
                            envelope(request, self._key, 'JARVIS_CALENDAR_REQUEST_V1'))
                        return self._verify(signed, request)
                    except httpx.TransportError:
                        if attempt:
                            raise
                        if self._sleep is not None:
                            self._sleep(.25)
                        else:
                            await asyncio.sleep(.25)

    def close(self):
        self._closed, self._key = True, ''


class ScriptRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    profile: ScriptCalendarProfile
    key_file: str


@contextmanager
def script_calendar_runtime(path, approved, revision, owner):
    try:
        config = ScriptRuntimeConfig.model_validate_json(private_read(path, 8192))
        if (digest(config.model_dump()) != approved or config.profile.source_revision != revision
                or config.profile.owner_id != owner or not config.profile.enabled):
            raise ValueError()
        key = private_read(config.key_file, 32)
        if len(key) != 32:
            raise ValueError()
        client = ScriptCalendarHTTP(config.profile, digest(config.profile.model_dump()), key.hex())
    except Exception:
        raise Denied('google_script_runtime_exact_connection_required') from None
    try:
        yield client
    finally:
        client.close()
