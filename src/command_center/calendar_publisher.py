"""Single-effect calendar publisher composed with durable sync state."""

import httpx

from .calendar_sync import publication_plan, record_outcome


class CalendarPublisher:
    def __init__(self, store, client):
        if not callable(getattr(client, 'call', None)):
            raise ValueError('calendar_publisher_client_required')
        self.store, self.client = store, client

    def publish(self, draft_id, operation_id):
        plan = publication_plan(self.store, draft_id)
        try:
            response = self.client.call(plan['request'])
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            return record_outcome(self.store, draft_id, plan['request_hash'], operation_id,
                                  'failed', error_code=f'http_{status}')
        except (httpx.TimeoutException, httpx.TransportError):
            return record_outcome(self.store, draft_id, plan['request_hash'], operation_id, 'unknown')
        return record_outcome(self.store, draft_id, plan['request_hash'], operation_id, 'synced', response)
