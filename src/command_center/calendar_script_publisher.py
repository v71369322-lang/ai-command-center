"""Opt-in create publisher reusing existing confirmed draft and sync authority."""
from uuid import NAMESPACE_URL, uuid5

from .calendar_sync import claim_script_publication, record_outcome
from .google_script_calendar_write import ScriptWriteHTTP
from .store import Denied


def publish(store, client, draft_id, operation_id):
    if not isinstance(client, ScriptWriteHTTP):
        raise Denied('calendar_write_trusted_transport_required')
    plan = claim_script_publication(store, draft_id, operation_id,
        client.profile.calendar_id, client.profile.key_fingerprint)
    if plan['action'] == 'none':
        return plan['state']
    try:
        event = (client.create if plan['action'] == 'create' else client.lookup)(draft_id, plan['document'])
    except Denied:
        # Even a provider error can follow a committed insert. Keep UNKNOWN.
        return plan['state']
    if event is None:
        # ABSENT during read reconciliation never silently authorizes another POST.
        return plan['state']
    outcome_id = str(uuid5(NAMESPACE_URL, 'acc:calendar-script-outcome:' + draft_id))
    return record_outcome(store, draft_id, plan['request_hash'], outcome_id, 'synced', event)
