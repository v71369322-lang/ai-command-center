"""Fixed Bot API client; real use requires a protected, exact approved connection."""
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import stat
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .store import Denied, canonical, digest
from .telegram_menu import keyboard
from .telegram_project_picker import allowed_markup


class TelegramConnection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    mode: Literal['disabled', 'http_mock', 'live'] = 'disabled'
    owner_id: int = Field(gt=0, lt=2**52)
    bot_id: int = Field(gt=0, lt=2**52)
    source_revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    token_file: str


def private_read(path, limit):
    """Consume a bound credential/configuration, never discover or display it."""
    path = Path(path)
    if not path.is_absolute() or path.parent.is_symlink():
        raise Denied('telegram_private_file_required')
    parent = path.parent.stat()
    if parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
        raise Denied('telegram_private_directory_required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > limit):
            raise Denied('telegram_private_file_required')
        return stream.read(limit + 1)


def connection(path):
    try:
        return TelegramConnection.model_validate_json(private_read(path, 4096))
    except Exception:
        raise Denied('telegram_connection_invalid_or_unavailable') from None


class TelegramHTTPError(Exception):
    def __init__(self, code, retryable=False, retry_after=0):
        super().__init__(code)
        self.retryable = retryable
        self.retry_after = retry_after


class BotCredentialFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        scrubbed = re.sub(r'https?://api\.telegram\.org/[^\s\"\']+',
                          'https://api.telegram.org/[redacted]', message)
        scrubbed = re.sub(r'(?<![0-9])[0-9]{1,20}(?::|%3[Aa])[A-Za-z0-9_-]{30,128}', '[redacted-bot-credential]', scrubbed)
        if scrubbed != message:
            record.msg, record.args = scrubbed, ()
            record.exc_info, record.exc_text = None, None
        return True


def redact_http_logs():
    # Origin logger filters cover httpx; handler filters also cover dynamically
    # created httpcore children and test/host logging configurations.
    filter_ = BotCredentialFilter()
    for name in ('httpx', 'httpcore'):
        logger = logging.getLogger(name)
        if not any(isinstance(f, BotCredentialFilter) for f in logger.filters):
            logger.addFilter(filter_)
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, BotCredentialFilter) for f in handler.filters):
            handler.addFilter(filter_)


class ConfiguredTelegramHTTP:
    def __init__(self, config_file, approved_connection, revision, *, transport=None):
        self.config_file, self.approved, self.revision = config_file, approved_connection, revision
        self.config = connection(config_file)
        self.mode, self.owner, self.bot_id = self.config.mode, self.config.owner_id, self.config.bot_id
        if (self.mode == 'disabled' or self.config.source_revision != revision
                or approved_connection != digest(self.config.model_dump())):
            raise Denied('telegram_exact_connection_authorization_required')
        if ((self.mode == 'http_mock' and not isinstance(transport, httpx.MockTransport))
                or (self.mode == 'live' and transport is not None)):
            raise Denied('telegram_transport_mode_mismatch')
        self._token = self._read_token()
        redact_http_logs()
        self.client = httpx.Client(transport=transport, follow_redirects=False, timeout=25,
                                   trust_env=self.mode == 'live', limits=httpx.Limits(max_connections=2))

    def _read_token(self):
        try:
            value = private_read(self.config.token_file, 256).decode().strip()
            if not re.fullmatch(str(self.bot_id) + r':[A-Za-z0-9_-]{30,128}', value):
                raise ValueError()
            return value
        except Exception:
            raise Denied('telegram_token_binding_invalid_or_unavailable') from None

    def check_enabled(self):
        current = connection(self.config_file)
        if digest(current.model_dump()) != self.approved or current != self.config:
            raise Denied('telegram_connection_revoked_or_changed')
        if not hmac.compare_digest(self._read_token(), self._token):
            raise Denied('telegram_credential_rotated_restart_required')

    def sensitive(self, value):
        return self._token in value

    def validate(self, method, body):
        if not isinstance(body, dict) or len(canonical(body).encode()) > 8192 or self.sensitive(canonical(body)):
            raise Denied('telegram_request_scope_invalid')
        valid = False
        if method in {'getMe', 'getWebhookInfo'}:
            valid = body == {}
        elif method == 'getUpdates':
            valid = (set(body) == {'offset', 'limit', 'timeout', 'allowed_updates'}
                and type(body['offset']) is int and 0 <= body['offset'] < 2**53
                and type(body['limit']) is int and 1 <= body['limit'] <= 20
                and type(body['timeout']) is int and 0 <= body['timeout'] <= 20
                and body['allowed_updates'] == ['message', 'callback_query'])
        elif method == 'sendMessage':
            from .telegram_control import allowed_markup as resume_markup
            from .telegram_experiment_authorize import allowed_markup as experiment_markup
            from .telegram_planning_authorize import allowed_markup as planning_markup
            from .telegram_plan_acceptance import allowed_markup as content_markup
            from .telegram_code_generation import allowed_markup as generation_markup
            from .telegram_coding_approval import allowed_markup as coding_markup
            valid = (not set(body) - {'chat_id', 'text', 'reply_markup'}
                and type(body.get('chat_id')) is int and body['chat_id'] == self.owner
                and isinstance(body.get('text'), str) and 1 <= len(body['text']) <= 4096)
            markup = body.get('reply_markup')
            # Only this exact read-only menu is added; arbitrary reply keyboards,
            # contact/location requests, Web Apps and URLs remain forbidden.
            if (markup is not None and canonical(markup) != canonical(keyboard())
                    and not allowed_markup(markup) and not resume_markup(markup)
                    and not experiment_markup(markup) and not planning_markup(markup)
                    and not content_markup(markup) and not coding_markup(markup) and not generation_markup(markup)):
                valid = valid and (isinstance(markup, dict) and set(markup) == {'inline_keyboard'})
                rows = markup.get('inline_keyboard') if isinstance(markup, dict) else None
                valid = valid and isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], list) and len(rows[0]) == 1
                button = rows[0][0] if valid else None
                valid = valid and (isinstance(button, dict) and set(button) == {'text', 'callback_data'}
                    and isinstance(button['text'], str) and 1 <= len(button['text']) <= 100
                    and isinstance(button['callback_data'], str)
                    and bool(re.fullmatch(r'tg:[A-Za-z0-9_-]{32}', button['callback_data'])))
        elif method == 'answerCallbackQuery':
            valid = (set(body) == {'callback_query_id'} and isinstance(body['callback_query_id'], str)
                     and 1 <= len(body['callback_query_id']) <= 128)
        if not valid:
            raise Denied('telegram_method_or_scope_forbidden')

    def call(self, method, body):
        redact_http_logs()
        self.check_enabled()
        if getattr(self, 'runtime_guard', None):
            self.runtime_guard()
        self.validate(method, body)
        url = 'https://api.telegram.org/bot' + self._token + '/' + method
        try:
            with self.client.stream('POST', url, json=body) as response:
                data = bytearray()
                for chunk in response.iter_bytes(chunk_size=8192):
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise TelegramHTTPError('telegram_response_too_large')
                if response.status_code != 200:
                    retry_after = 0
                    retryable = response.status_code >= 500
                    if response.status_code == 429:
                        try:
                            retry_after = json.loads(data)['parameters']['retry_after']
                            retryable = type(retry_after) is int and 1 <= retry_after <= 30
                        except (KeyError, TypeError, ValueError):
                            retryable = False
                    raise TelegramHTTPError('telegram_http_' + str(response.status_code), retryable,
                                            retry_after if retryable and response.status_code == 429 else 0)
                value = json.loads(data)
                if not isinstance(value, dict) or value.get('ok') is not True or 'result' not in value:
                    raise TelegramHTTPError('telegram_response_invalid')
                self.check_enabled()
                if getattr(self, 'runtime_guard', None):
                    self.runtime_guard()
                return value['result']
        except Denied:
            raise
        except TelegramHTTPError:
            raise
        except Exception:
            # A URL-bearing httpx exception must never escape to logs/tracebacks.
            raise TelegramHTTPError('telegram_network_or_response_uncertain', True) from None

    def verify_bot(self):
        me = self.call('getMe', {})
        if not isinstance(me, dict) or type(me.get('id')) is not int or me['id'] != self.bot_id or me.get('is_bot') is not True:
            raise Denied('telegram_bot_identity_mismatch')
        webhook = self.call('getWebhookInfo', {})
        if not isinstance(webhook, dict) or webhook.get('url') != '':
            raise Denied('telegram_existing_webhook_requires_owner_review')
        return {'mode': self.mode, 'bot_id': self.bot_id, 'owner_id': self.owner,
                'connection_digest': self.approved, 'live_verified': self.mode == 'live'}

    def close(self):
        self.client.close()

    def __repr__(self):
        return '<ConfiguredTelegramHTTP credential=redacted>'


def token_fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()
