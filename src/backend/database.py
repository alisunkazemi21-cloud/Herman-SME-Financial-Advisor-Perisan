from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


class AccessDenied(PermissionError):
    pass


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        with psycopg.connect(dsn) as c:
            unsafe = c.execute("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE "
                "(rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb) "
                "AND pg_has_role(current_user,oid,'MEMBER'))").fetchone()[0]
            owner = c.execute("SELECT pg_get_userbyid(nspowner)=current_user FROM pg_namespace "
                              "WHERE nspname='herman'").fetchone()
            if unsafe or owner is None or owner[0]:
                raise ValueError("runtime requires a migrated schema and a non-owner, unprivileged role")

    def authenticate(self, token: str) -> UUID:
        if not 32 <= len(token) <= 256:
            raise AccessDenied("اعتبار دسترسی نامعتبر است")
        digest = hashlib.sha256(token.encode()).hexdigest()
        with psycopg.connect(self.dsn) as connection:
            user_id = connection.execute("SELECT herman.authenticate(%s)", (digest,)).fetchone()[0]
        if user_id is None:
            raise AccessDenied("اعتبار دسترسی نامعتبر یا منقضی است")
        return user_id

    @contextmanager
    def transaction(self, user_id: UUID, business_id: UUID | None = None,
                    write: bool = False, reviewer: bool = False) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            connection.execute("SELECT set_config('herman.user_id',%s,true)", (str(user_id),))
            if business_id is not None:
                connection.execute("SELECT set_config('herman.business_id',%s,true)", (str(business_id),))
                role = connection.execute("SELECT herman.member_role(%s) AS role", (business_id,)).fetchone()["role"]
                allowed = {"owner", "reviewer"} if reviewer else {"owner", "editor", "reviewer"}
                if role is None or ((write or reviewer) and role not in allowed):
                    raise AccessDenied("عضویت یا نقش مجاز برای این بیزینس ندارید")
            yield connection


def migrate(admin_dsn: str, runtime_role: str = "herman_app") -> None:
    """Apply the versioned schema under a migration lock; login password is provisioned separately."""
    with psycopg.connect(admin_dsn) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(48732001)")
        existing = connection.execute("SELECT to_regclass('herman.schema_migrations')").fetchone()[0]
        if existing is None:
            connection.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        versions = {row[0] for row in connection.execute("SELECT version FROM herman.schema_migrations")}
        if not versions <= {1, 2} or 1 not in versions:
            raise ValueError("unsupported database schema version")
        if 2 not in versions:
            connection.execute(Path(__file__).with_name("migration_002.sql").read_text(encoding="utf-8"))
        if connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (runtime_role,)).fetchone() is None:
            connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS").format(
                sql.Identifier(runtime_role)))
        unsafe = connection.execute(
            "SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb FROM pg_roles WHERE rolname=%s",
            (runtime_role,)).fetchone()[0]
        owns_schema = connection.execute(
            "SELECT pg_get_userbyid(nspowner)=%s FROM pg_namespace WHERE nspname='herman'",
            (runtime_role,)).fetchone()[0]
        if unsafe or owns_schema:
            raise ValueError("runtime role must be unprivileged and must not own the schema")
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA herman TO {}").format(sql.Identifier(runtime_role)))
        tables = ["businesses", "warehouses", "documents", "items", "unit_conversions", "records", "approvals",
                  "stock_counts", "stock_movements", "recipes", "recipe_lines", "fulfillments",
                  "analysis_runs", "audit_events", "idempotency_keys"]
        for table in tables:
            connection.execute(sql.SQL("GRANT SELECT, INSERT ON herman.{} TO {}").format(
                sql.Identifier(table), sql.Identifier(runtime_role)))
        connection.execute(sql.SQL("REVOKE INSERT ON herman.businesses FROM {}").format(sql.Identifier(runtime_role)))
        for function in ("user_id()", "business_id()", "member_role(uuid)", "authenticate(text)",
                         "create_business(text,text,text)", "list_businesses()"):
            connection.execute(sql.SQL("GRANT EXECUTE ON FUNCTION herman." + function + " TO {}").format(
                sql.Identifier(runtime_role)))
