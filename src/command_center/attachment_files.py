"""Bounded Telegram-only download capability for checked attachment references."""
from hashlib import sha256
import json
import re

from .store import Denied
from .telegram_attachments import validate, MAX_BYTES
from .telegram_transport import ConfiguredTelegramHTTP, TelegramHTTPError, redact_http_logs
from .telegram_voice_files import TelegramVoiceFiles


class AttachmentFiles:
    def __init__(self, client, *, approved_connection):
        if not isinstance(client, ConfiguredTelegramHTTP) or approved_connection != client.approved:
            raise Denied('attachment_exact_connection_required')
        self.client = client

    def download(self, intent):
        validate(intent, self.client.sensitive)
        client = self.client
        client.check_enabled()
        redact_http_logs()
        try:
            base = 'https://api.telegram.org/'
            with client.client.stream('POST', base + 'bot' + client._token + '/getFile',
                    json={'file_id': intent['file_id']}, headers={'Accept-Encoding': 'identity'}) as response:
                envelope = json.loads(TelegramVoiceFiles._bounded(response, 4096))
            info = envelope.get('result') if envelope.get('ok') is True else None
            if (not isinstance(info, dict) or any(info.get(k) != intent[k] for k in
                    ('file_id', 'file_unique_id', 'file_size'))):
                raise Denied('attachment_file_binding_changed')
            path = info.get('file_path')
            folder = 'photos' if intent['media'] == 'photo' else 'documents'
            if not isinstance(path, str) or not re.fullmatch(folder + r'/[A-Za-z0-9_-]{1,160}(?:\.[A-Za-z0-9_-]{1,16})?', path):
                raise Denied('attachment_file_path_invalid')
            client.check_enabled()
            with client.client.stream('GET', base + 'file/bot' + client._token + '/' + path,
                    headers={'Accept-Encoding': 'identity'}) as response:
                data = TelegramVoiceFiles._bounded(response, min(intent['file_size'], MAX_BYTES))
            client.check_enabled()
            if len(data) != intent['file_size']:
                raise Denied('attachment_file_size_changed')
            return data, sha256(data).hexdigest()
        except (Denied, TelegramHTTPError):
            raise
        except Exception:
            raise TelegramHTTPError('attachment_download_failed', True) from None
