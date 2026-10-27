"""Explicit cloud bootstrap; separate admin credentials, never called by API."""

from sqlalchemy import text
from psycopg import sql
import os
from pathlib import Path

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
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS coding_evidence JSONB NOT NULL DEFAULT '{}'::jsonb"))
        exists = connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname='f1_app'")).first()
        if not exists:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE ROLE f1_app LOGIN PASSWORD {}").format(sql.Literal(password)))
        connection.execute(text("GRANT USAGE ON SCHEMA public TO f1_app"))
        connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON control, tasks, approvals, outbox, owner_sessions TO f1_app"))
        connection.execute(text("GRANT SELECT, INSERT ON audit TO f1_app"))
        connection.execute(text('GRANT SELECT,INSERT,UPDATE ON external_grants,external_actions TO f1_app'))
        connection.execute(text('GRANT SELECT,INSERT,UPDATE ON telegram_inbox,telegram_deliveries,telegram_cards TO f1_app'))
        connection.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO f1_app"))
        # Runtime policy service: no grant creation, payload edits, or owner sessions.
        runtime_binding = os.environ.get('F1_RUNTIME_PASSWORD_FILE')
        if runtime_binding:
            runtime_password = Path(runtime_binding).read_text().strip()
            exists = connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname='f1_runtime'")).first()
            if not exists:
                with connection.connection.driver_connection.cursor() as cursor:
                    cursor.execute(sql.SQL("CREATE ROLE f1_runtime LOGIN PASSWORD {}").format(sql.Literal(runtime_password)))
            connection.execute(text('ALTER ROLE f1_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT'))
            inherited = connection.execute(text("SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='f1_runtime')")).first()
            if inherited:
                raise RuntimeError('unexpected_runtime_role_membership')
            connection.execute(text('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM f1_runtime'))
            connection.execute(text('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM f1_runtime'))
            connection.execute(text('GRANT USAGE ON SCHEMA public TO f1_runtime'))
            connection.execute(text('GRANT SELECT ON control,tasks,approvals,outbox,audit TO f1_runtime'))
            connection.execute(text('GRANT UPDATE(halted,recovery,epoch,actual,reserved) ON control TO f1_runtime'))
            connection.execute(text('GRANT UPDATE(state,fence,lease_until,attempts,reserved,artifact,artifact_hash,reason,coding_evidence) ON tasks TO f1_runtime'))
            connection.execute(text('GRANT UPDATE(used) ON approvals TO f1_runtime'))
            connection.execute(text('GRANT INSERT,UPDATE ON outbox TO f1_runtime'))
            connection.execute(text('GRANT INSERT ON audit TO f1_runtime'))
            connection.execute(text('GRANT SELECT ON external_grants TO f1_runtime'))
            connection.execute(text('GRANT SELECT,INSERT,UPDATE ON external_actions TO f1_runtime'))
            connection.execute(text('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO f1_runtime'))
    print("Schema 001 initialized; restricted application role granted. No credentials printed.")


if __name__ == "__main__":
    main()
