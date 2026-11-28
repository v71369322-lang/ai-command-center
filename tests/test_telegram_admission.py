"""Offline failure boundaries; fake SQL errors are not live PG acceptance."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from command_center.models import Control
from command_center.store import Store, Denied
from command_center.telegram_service import TelegramStore, failure_code


def fixture(code='57014', query='control', params=True):
    store = object.__new__(TelegramStore)
    store.engine = SimpleNamespace(dialect=postgresql.dialect())
    statement = select(Control).where(Control.id == 1).with_for_update().compile(dialect=store.engine.dialect)
    error = OperationalError(str(statement) if query == 'control' else 'PRIVATE SQL',
                             statement.params if params else {'id_1': 2},
                             SimpleNamespace(sqlstate=code))
    return store, error


@pytest.mark.parametrize('code', ['57014', '55P03'])
def test_retry_entry_only_and_close_failed_sessions(monkeypatch, code):
    store, error = fixture(code)
    entered, closed, sleeps, bodies = [], [], [], []
    @contextmanager
    def original(_):
        entered.append(1)
        try:
            if len(entered) < 3:
                raise error
            yield 'session'
        finally:
            closed.append(1)
    monkeypatch.setattr(Store, 'transaction', original)
    monkeypatch.setattr('command_center.maintenance_admission.time.sleep', sleeps.append)
    with store.transaction() as session:
        assert session == 'session'
        bodies.append(1)
    assert len(entered) == len(closed) == 3
    assert bodies == [1] and sleeps == [1, 1]


@pytest.mark.parametrize('stage', ['body', 'commit'])
def test_body_or_commit_timeout_never_replayed(monkeypatch, stage):
    store, error = fixture()
    entries = []
    @contextmanager
    def original(_):
        entries.append(1)
        yield 'session'
        if stage == 'commit':
            raise error
    monkeypatch.setattr(Store, 'transaction', original)
    with pytest.raises(OperationalError):
        with store.transaction():
            if stage == 'body':
                raise error
    assert entries == [1]


@pytest.mark.parametrize('code,query,params,count', [
    ('57014', 'control', True, 5), ('55P03', 'control', True, 5),
    ('08006', 'control', True, 1), ('57014', 'other', True, 1),
    ('57014', 'control', False, 1)])
def test_exhaustion_and_unrelated_errors_fail_closed(monkeypatch, code, query, params, count):
    store, error = fixture(code, query, params)
    entries = []
    @contextmanager
    def original(_):
        entries.append(1)
        raise error
        yield
    monkeypatch.setattr(Store, 'transaction', original)
    monkeypatch.setattr('command_center.maintenance_admission.time.sleep', lambda _: None)
    with pytest.raises(OperationalError):
        with store.transaction():
            pytest.fail('entry must not succeed')
    assert len(entries) == count


def test_failure_codes_do_not_export_error_details():
    store, error = fixture()
    assert failure_code(error, store) == 'telegram_service_admission_timeout'
    _, other = fixture(query='other')
    for value, binding in [(other, store), (RuntimeError('PRIVATE TOKEN'), store),
                           (Denied('PRIVATE POLICY'), store), (error, None)]:
        assert failure_code(value, binding) == 'telegram_service_failed_closed'
