"""A waiting F1 planning task; no model call, external grant, or production dispatch."""
from .project_inbox import owner
from .request_planning import PlanningContext, _context
from .store import Denied, canonical

KIND = 'saved_request_plan'


def payload(snapshot):
    if not isinstance(snapshot, PlanningContext):
        raise Denied('planning_context_invalid')
    return {'kind': KIND, 'planning': snapshot.model_dump(), 'cost': 1}


def validate_payload(value):
    try:
        if not isinstance(value, dict) or set(value) != {'kind', 'planning', 'cost'} or value['kind'] != KIND:
            raise ValueError()
        snapshot = PlanningContext.model_validate(value['planning'])
        if type(value['cost']) is not int or canonical(payload(snapshot)) != canonical(value):
            raise ValueError()
        return snapshot
    except (ValueError, KeyError, TypeError):
        raise Denied('planning_task_scope_invalid') from None


def check_context(store, session, value):
    snapshot = validate_payload(value)
    store.check_audit(session)
    if _context(store, session, snapshot.request_id).binding != snapshot.binding:
        raise Denied('planning_context_changed')
    return snapshot


def create_task(store, role, snapshot):
    owner(role)
    value = payload(snapshot)
    # One operation per exact context; terminal/unknown outcomes never create a new attempt.
    key = request_key(snapshot)
    return store.create(role, key, value)


def request_key(snapshot):
    return 'plan-v1:' + snapshot.request_id + ':' + snapshot.binding
