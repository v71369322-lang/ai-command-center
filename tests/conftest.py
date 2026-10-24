from dataclasses import replace
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from command_center.api import create_app
from command_center.config import Settings
from command_center.store import Store
from command_center.worker import broker


@pytest.fixture(scope="session")
def settings():
    return Settings.load()


@pytest.fixture(scope="session")
def admin(settings):
    password = Path(".runtime/secrets/db_admin_password").read_text().strip()
    return Store(replace(settings, database_url=settings.database_url.set(username="f1_admin", password=password)))


@pytest.fixture
def store(settings, admin):
    with admin.engine.begin() as c:
        c.execute(text("TRUNCATE approvals, outbox, tasks, audit, control, owner_sessions RESTART IDENTITY CASCADE"))
    admin.initialize()
    result = Store(settings)
    yield result
    result.engine.dispose()


@pytest.fixture
def queue(settings):
    result = broker(settings)
    result.delete("f1:work")
    yield result
    result.delete("f1:work")
    result.close()


@pytest.fixture
def client(settings, store):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def headers(settings):
    class Redacted(str):
        def __repr__(self):
            return "<redacted>"
    return {role: {"Authorization": Redacted("Bearer " + value)} for role, value in settings.identities.items()}


def wait_ready(check, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except Exception:
            pass
        time.sleep(.2)
    raise AssertionError("service_not_ready")
