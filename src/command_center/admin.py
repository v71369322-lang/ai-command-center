"""Explicit cloud bootstrap; separate admin credentials, never called by API."""

from sqlalchemy import text
from psycopg import sql

from .config import Settings, secret
from .store import Store


def main():
    settings = Settings.load()
    if settings.database_url.username != "f1_admin":
        raise RuntimeError("Bootstrap requires explicit admin binding")
    store = Store(settings)
    store.initialize()
    password = secret("F1_APP_PASSWORD_FILE")
    with store.engine.begin() as connection:
        exists = connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname='f1_app'")).first()
        if not exists:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE ROLE f1_app LOGIN PASSWORD {}").format(sql.Literal(password)))
        connection.execute(text("GRANT USAGE ON SCHEMA public TO f1_app"))
        connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON control, tasks, approvals, outbox TO f1_app"))
        connection.execute(text("GRANT SELECT, INSERT ON audit TO f1_app"))
        connection.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO f1_app"))
    print("Schema 001 initialized; restricted application role granted. No credentials printed.")


if __name__ == "__main__":
    main()
