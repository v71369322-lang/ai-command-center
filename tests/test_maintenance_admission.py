from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from command_center.models import Control
from command_center.maintenance_admission import bounded_entry


def fixture(query='control'):
    store = SimpleNamespace(engine=SimpleNamespace(dialect=postgresql.dialect()))
    statement = select(Control).where(Control.id == 1).with_for_update().compile(dialect=store.engine.dialect)
    error = OperationalError(str(statement) if query == 'control' else 'SELECT audit',
                             statement.params, SimpleNamespace(sqlstate='57014'))
    return store, error


def test_only_entry_retries_and_resources_close():
    store, error = fixture()
    calls, closed = [], []
    @contextmanager
    def original(_):
        calls.append(1)
        try:
            if len(calls) < 3:
                raise error
            yield 'session'
        finally:
            closed.append(1)
    with bounded_entry(store, original, delay=0) as session:
        assert session == 'session'
    assert len(calls) == len(closed) == 3


@pytest.mark.parametrize('query', ['control', 'audit'])
def test_body_is_never_replayed(query):
    store, error = fixture(query)
    calls = []
    @contextmanager
    def original(_):
        calls.append(1)
        yield 'session'
    with pytest.raises(OperationalError):
        with bounded_entry(store, original, delay=0):
            raise error
    assert len(calls) == 1


@pytest.mark.parametrize('query,expected', [('control', 5), ('audit', 1)])
def test_bounded_and_unknown_errors_fatal(query, expected):
    store, error = fixture(query)
    calls = []
    @contextmanager
    def original(_):
        calls.append(1)
        raise error
        yield
    with pytest.raises(OperationalError):
        with bounded_entry(store, original, delay=0):
            pytest.fail('must not enter')
    assert len(calls) == expected

