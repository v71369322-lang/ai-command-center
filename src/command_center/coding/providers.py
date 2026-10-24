"""Provider-neutral edits; no credentials are ever copied into a coding workspace."""
from dataclasses import dataclass
import json
import time
from typing import Protocol

import httpx

from .spec import FIRST, CORRECT


class ProviderUnavailable(RuntimeError):
    def __init__(self, uncertain=False):
        super().__init__('provider_unavailable')
        self.uncertain = uncertain


@dataclass(frozen=True)
class Proposal:
    changes: dict[str, str]
    tokens: int
    units: int


class CodingProvider(Protocol):
    noninteractive: bool
    def propose(self, context: dict) -> Proposal: ...


class MockProvider:
    noninteractive = True
    def __init__(self, scenario='normal'):
        self.scenario, self.calls = scenario, 0

    def propose(self, context):
        self.calls += 1
        if self.scenario == 'unavailable':
            raise ProviderUnavailable()
        if self.scenario == 'slow':
            time.sleep(10)
        if self.scenario == 'escape_attempt':
            return Proposal({'../outside.py': 'not written'}, 10, 1)
        source = FIRST if self.calls == 1 or self.scenario == 'always_fail' else CORRECT
        # Synthetic accounting units; NOT provider-billed tokens/RUB.
        return Proposal({'calculator.py': source}, len(source.encode()), 1)


class ResponsesProvider:
    """Official /v1/responses structured-output adapter; not enabled by F2 task policy.
    Future paid activation requires a separate verified rights/pricing/budget grant.
    Tests use httpx.MockTransport, never a real key or network request.
    """
    noninteractive = True

    def __init__(self, *, model, token, authorized=False, client=None, max_output_tokens=512, seconds=15):
        if not 32 <= max_output_tokens <= 4096 or not 1 <= seconds <= 30:
            raise ValueError('unsafe_provider_limits')
        self.model, self.token, self.authorized = model, token, authorized
        self.client = client
        self.output_tokens, self.seconds = max_output_tokens, seconds

    def propose(self, context):
        if not self.authorized or not self.token:
            raise PermissionError('paid_provider_not_authorized')
        prompt = json.dumps(context, sort_keys=True)
        if len(prompt.encode()) > 8192:
            raise ValueError('provider_input_limit')
        schema = {'type': 'object', 'properties': {'source': {'type': 'string'}},
                  'required': ['source'], 'additionalProperties': False}
        client = self.client or httpx.Client(follow_redirects=False)
        try:
            response = client.post('https://api.openai.com/v1/responses', timeout=self.seconds, follow_redirects=False,
                                   headers={'Authorization': 'Bearer ' + self.token},
                                   json={'model': self.model, 'input': prompt, 'store': False,
                                         'max_output_tokens': self.output_tokens,
                                         'text': {'format': {'type': 'json_schema', 'name': 'coding_edit',
                                                             'strict': True, 'schema': schema}}})
            if response.status_code != 200:
                raise ProviderUnavailable(uncertain=response.status_code >= 500)
            if len(response.content) > 65536:
                raise ProviderUnavailable(uncertain=True)
            result = response.json()
            if result.get('status') != 'completed':
                raise ProviderUnavailable(uncertain=True)
            texts = [part['text'] for item in result['output'] if item.get('type') == 'message'
                     for part in item.get('content', []) if part.get('type') == 'output_text']
            data = json.loads(''.join(texts))
            usage = result['usage']
            if (type(usage['input_tokens']) is not int or type(usage['output_tokens']) is not int
                    or usage['input_tokens'] < 0 or not 0 <= usage['output_tokens'] <= self.output_tokens
                    or not isinstance(data['source'], str)):
                raise ProviderUnavailable(uncertain=True)
            return Proposal({'calculator.py': data['source']}, usage['input_tokens'] + usage['output_tokens'], 1)
        except httpx.RequestError:
            # No retry: charges/results may already exist. Keep reservation until reconciliation.
            raise ProviderUnavailable(uncertain=True) from None
        except (ValueError, KeyError, TypeError):
            raise ProviderUnavailable(uncertain=True) from None
        finally:
            if self.client is None:
                client.close()
