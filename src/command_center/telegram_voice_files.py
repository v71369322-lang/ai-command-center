"""Explicit voice-download capability over an existing approved Bot connection."""

from hashlib import sha256
import json
import re

from .store import Denied, digest
from .telegram_transport import ConfiguredTelegramHTTP, TelegramHTTPError, redact_http_logs
from .telegram_voice_requests import MAX_BYTES, parse_message


class TelegramVoiceFiles:
    def __init__(self, client, *, approved_connection):
        if (not isinstance(client, ConfiguredTelegramHTTP)
                or approved_connection != client.approved):
            raise Denied('voice_exact_connection_required')
        self.client = client

    def download(self, intent):
        # Reuse the intake limits instead of admitting arbitrary file references.
        if not isinstance(intent, dict) or intent.get('kind') != 'voice_request':
            raise Denied('voice_download_intent_invalid')
        reference = intent.get('file_id')
        if (not isinstance(reference, str) or not 1 <= len(reference) <= 256
                or digest(reference) != intent.get('file_ref_hash')
                or self.client.sensitive(reference)):
            raise Denied('voice_download_intent_invalid')
        client = self.client
        redact_http_logs()
        client.check_enabled()
        try:
            # No generic getFile method is added to the bot's command transport.
            base = 'https://api.telegram.org/'
            with client.client.stream('POST', base + 'bot' + client._token + '/getFile',
                                      json={'file_id': reference},
                                      headers={'Accept-Encoding': 'identity'}) as response:
                metadata = self._bounded(response, 4096)
            envelope = json.loads(metadata)
            info = envelope.get('result') if envelope.get('ok') is True else None
            if not isinstance(info, dict):
                raise Denied('voice_file_metadata_invalid')
            checked = parse_message({'voice': {
                'file_id': info.get('file_id'), 'file_unique_id': info.get('file_unique_id'),
                'file_size': info.get('file_size'), 'duration': intent.get('duration_seconds'),
                'mime_type': intent.get('mime_type')}}, client.sensitive)
            if checked != intent:
                raise Denied('voice_file_binding_changed')
            path = info.get('file_path')
            if (not isinstance(path, str)
                    or not re.fullmatch(r'voice/[A-Za-z0-9_-]{1,160}\.(?:oga|ogg|mp3|m4a)', path)):
                raise Denied('voice_file_path_invalid')
            client.check_enabled()
            with client.client.stream('GET', base + 'file/bot' + client._token + '/' + path,
                                      headers={'Accept-Encoding': 'identity'}) as response:
                audio = self._bounded(response, min(intent['file_size'], MAX_BYTES))
            client.check_enabled()
            if len(audio) != intent['file_size']:
                raise Denied('voice_file_size_changed')
            return audio, sha256(audio).hexdigest()
        except (Denied, TelegramHTTPError):
            raise
        except Exception:
            # Never expose credential-bearing request URLs or provider bodies.
            raise TelegramHTTPError('voice_download_failed', True) from None

    @staticmethod
    def _bounded(response, limit):
        if response.status_code != 200 or response.headers.get('content-encoding', 'identity') != 'identity':
            raise TelegramHTTPError('voice_file_http_rejected')
        value = bytearray()
        for chunk in response.iter_bytes(chunk_size=8192):
            value.extend(chunk)
            if len(value) > limit:
                raise Denied('voice_file_response_too_large')
        return bytes(value)
