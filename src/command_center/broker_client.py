"""Worker transport has no Docker or database credential dependency."""
import os
from pathlib import Path

import httpx


class BrokerClient:
    def __init__(self, socket, token):
        self.socket, self.token = socket, token

    @classmethod
    def from_env(cls):
        return cls(os.environ.get('F1_BROKER_SOCKET', '/run/f1-broker/runtime.sock'),
                   Path(os.environ['F1_BROKER_TOKEN_FILE']).read_text().strip())

    def request(self, message):
        with httpx.Client(transport=httpx.HTTPTransport(uds=self.socket), timeout=5) as client:
            response = client.post('http://runtime/rpc', json=message,
                                   headers={'Authorization': 'Bearer ' + self.token})
            if response.status_code != 200:
                raise RuntimeError('runtime_request_denied')
            return response.json()
