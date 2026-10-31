from command_center.attention import summary
from command_center.models import Control, Task
from command_center.store import Denied
from test_project_inbox import body, capture
from command_center.project_inbox import classify

import pytest


def test_owner_attention_summary_is_read_only_and_prioritized(store):
    capture(store, 801, 'Unassigned synthetic request')
    assigned = capture(store, 802, 'Assigned synthetic request')
    classify(store, 'owner', **body(assigned, 'lnauto'))
    with store.transaction() as session:
        control = session.get(Control, 1)
        control.halted = True
        failed = session.query(Task).first()
        if failed:
            failed.state = 'FAILED'
    before = store.snapshot()
    result = summary(store, 'owner')
    assert result['task_admission_halted'] is True and result['execution_started'] is False
    assert result['project_counts']['unassigned'] == 1
    assert result['project_counts']['lnauto'] == 1
    assert result['total_pending_requests'] == 2
    assert [item['code'] for item in result['items'][:2]] == [
        'CONTROL_HALTED', 'REQUEST_UNASSIGNED']
    assert result['reminders_connected'] is False and result['ai_planning_connected'] is False
    assert store.snapshot() == before


def test_attention_requires_owner(store):
    with pytest.raises(Denied, match='owner_required'):
        summary(store, 'operator')


@pytest.mark.parametrize('role,status', [('anonymous', 401), ('operator', 409), ('agent', 409)])
def test_attention_route_requires_owner(client, headers, role, status):
    assert client.get('/api/attention', headers=headers.get(role, {})).status_code == status
