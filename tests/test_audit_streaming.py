"""Full historical validation remains mandatory; no trusted-prefix cache."""
import pytest
from sqlalchemy import select, text

from command_center.models import Audit
from command_center.store import Denied


def test_streaming_checks_multiple_batches_and_anchor_without_orm_entities(store):
    with store.transaction() as tx:
        for n in range(600):
            store.audit(tx, 'public_fixture', 'system', number=n)
    anchor = store.checkpoint()
    with store.transaction() as tx:
        assert store.check_audit(tx, anchor)
        assert not any(isinstance(v, Audit) for v in tx.identity_map.values())
    with store.transaction() as tx:
        store.audit(tx, 'public_fixture', 'system', number=601)
    with store.transaction() as tx:
        assert store.check_audit(tx, anchor)
    with pytest.raises(Denied, match='checkpoint_mismatch'):
        with store.transaction() as tx:
            store.check_audit(tx, {**anchor, 'digest': 'f' * 64})
    with pytest.raises(Denied, match='checkpoint_missing_or_rollback'):
        with store.transaction() as tx:
            store.check_audit(tx, {**anchor, 'sequence': anchor['sequence'] + 100})


@pytest.mark.parametrize('position', [1, 257, 599])
def test_historical_corruption_at_any_batch_is_detected(store, admin, position):
    with store.transaction() as tx:
        for n in range(600):
            store.audit(tx, 'public_fixture', 'system', number=n)
    with admin.transaction() as tx:
        sequence = tx.scalar(select(Audit.sequence).order_by(Audit.sequence).offset(position).limit(1))
        tx.execute(text("UPDATE audit SET digest=repeat('f',64) WHERE sequence=:sequence"), {'sequence': sequence})
    with pytest.raises(Denied, match='audit_integrity_failure'):
        with store.transaction() as tx:
            store.check_audit(tx)
