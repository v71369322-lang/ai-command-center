from types import SimpleNamespace

import pytest
from sqlalchemy import insert

from command_center.coding.gateway import Gateway
from command_center.models import Audit
from command_center.store import Denied, ZERO, digest


def test_ledger_projects_only_matching_anchors_and_preserves_latest(store, admin):
    row = SimpleNamespace(id='action', task_id='task', key='key', kind='openai',
                          request_hash='a' * 64, state='COMPLETE', reserved=0,
                          actual=1, evidence={})
    # Synthetic history deliberately exceeds the maintenance container budget
    # when loaded as ORM objects. Never put it in a production database.
    with admin.engine.begin() as tx:
        for start in range(0, 20000, 200):
            tx.execute(insert(Audit), [{'event': {'kind': 'unrelated', 'padding': 'x' * 12000},
                                       'previous': ZERO, 'digest': digest({'i': i})}
                                      for i in range(start, start + 200)])
        for value in ['old', Gateway.action_digest(row)]:
            tx.execute(insert(Audit), {'event': {'action_id': row.id, 'ledger_digest': value},
                                      'previous': ZERO, 'digest': digest({'anchor': value})})
    with store.transaction() as tx:
        Gateway.check_ledger(tx, iter([row]))
        assert not any(isinstance(item, Audit) for item in tx.identity_map.values())
        row.actual = 2
        with pytest.raises(Denied, match='external_ledger_integrity_failure'):
            Gateway.check_ledger(tx, [row])
        with pytest.raises(Denied, match='external_ledger_integrity_failure'):
            Gateway.check_ledger(tx, [SimpleNamespace(**{**row.__dict__, 'id': 'missing'})])


def test_empty_ledger_does_not_read_history():
    Gateway.check_ledger(None, [])
