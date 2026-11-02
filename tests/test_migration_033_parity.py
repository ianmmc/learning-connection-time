"""#1038 (#1022 T4): migration 033 and the ORM declare the same four tables.

The schema invariant from PR #641: a table declared twice (migration DDL for a migrated DB, the
models for a fresh `create_all()` DB) must be declared identically, or the two kinds of database
diverge, on CI only. Each test builds the tables BOTH ways and compares the catalog:
  - columns: type, length, precision/scale, nullability, default presence
  - every constraint by name AND body (`pg_get_constraintdef`: PK columns, CHECK expressions)
  - every index by name AND definition (`pg_indexes.indexdef`)
  - table comments (`obj_description`)
(#1062: the first version compared CHECK constraints by name only and never looked at indexes.)

Isolation is by SCHEMA, not database (#1063): two throwaway schemas on the governance Postgres,
`search_path` set per connection, dropped in `finally`. That needs only CREATE on the database,
which the governance user has locally (owner) and in CI (the service container's superuser), so the
test runs in the `govdb` CI job rather than only on a developer's machine. The governance DB's own
tables are never touched; the live LCT DB is never connected to. Skips when Postgres is down. The
connections are DETACHED from the pool: `SET search_path` is session state and leaked into later
tests on the first CI run.
"""
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

pytestmark = [pytest.mark.govdb, pytest.mark.integration]

TABLES = ("ccd_school_staffing", "lea_school_staffing", "lea_band_staffing", "lea_grade_teacher_fte")
MIGRATION = (Path(__file__).resolve().parents[1]
             / "infrastructure/database/migrations/033_ccd_school_staffing.sql")


def _shape(conn, schema: str) -> dict:
    """Everything that decides which rows a table accepts and how it is reached, keyed so the two
    schemas compare directly. The schema name itself is stripped from index definitions."""
    cols = conn.execute(text(
        "SELECT table_name, column_name, data_type, character_maximum_length, numeric_precision, "
        "numeric_scale, is_nullable, column_default IS NOT NULL "
        "FROM information_schema.columns WHERE table_schema = :s ORDER BY 1, 2"), {"s": schema}).all()
    cons = conn.execute(text(
        "SELECT c.relname, k.conname, k.contype, pg_get_constraintdef(k.oid) "
        "FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid "
        "JOIN pg_namespace n ON n.oid = k.connamespace WHERE n.nspname = :s ORDER BY 1, 2"), {"s": schema}).all()
    idx = conn.execute(text(
        "SELECT tablename, indexname, replace(indexdef, :s || '.', '') "
        "FROM pg_indexes WHERE schemaname = :s ORDER BY 1, 2"), {"s": schema}).all()
    comments = conn.execute(text(
        "SELECT c.relname, obj_description(c.oid, 'pg_class') FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = :s AND c.relkind = 'r' "
        "ORDER BY 1"), {"s": schema}).all()
    return {"columns": [tuple(r) for r in cols], "constraints": [tuple(r) for r in cons],
            "indexes": [tuple(r) for r in idx], "comments": [tuple(r) for r in comments]}


@pytest.fixture
def scratch_schemas():
    """Yield a function that makes a fresh throwaway schema and returns a connection whose
    search_path is that schema. Every schema made is dropped afterwards, whatever happened."""
    from infrastructure.acquisition.common import db as gdb
    try:
        engine = gdb.get_engine()
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except OperationalError as e:
        pytest.skip(f"governance Postgres unavailable: {e}")
    made, conns = [], []

    def make(tag: str):
        name = f"scratch_1038_{tag}_{uuid.uuid4().hex[:8]}"
        conn = engine.connect()
        # SET search_path is SESSION state: a pooled connection would carry it (pointing at a dropped
        # schema) into the next test's gov_session, which then fails with InvalidSchemaName (seen in
        # CI on the first run: every govdb test after this file errored). Detach, so this DBAPI
        # connection is closed, never returned to the pool.
        conn.detach()
        conns.append(conn)
        conn.execute(text(f'CREATE SCHEMA "{name}"'))
        conn.commit()
        made.append(name)
        conn.execute(text(f'SET search_path TO "{name}"'))
        return name, conn
    try:
        yield make
    finally:
        for c in conns:
            c.rollback()
            c.execute(text("RESET search_path"))
            c.commit()
        with engine.begin() as c:
            for name in made:
                c.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        for c in conns:
            c.close()


def _apply_migration(conn):
    conn.exec_driver_sql(MIGRATION.read_text())
    conn.commit()


def _create_all(conn):
    from infrastructure.database.models import Base
    Base.metadata.create_all(conn, tables=[Base.metadata.tables[t] for t in TABLES])
    conn.commit()


def test_migration_033_and_models_declare_the_same_tables(scratch_schemas):
    mig_name, mig = scratch_schemas("mig")
    orm_name, orm = scratch_schemas("orm")
    _apply_migration(mig)
    _create_all(orm)
    a, b = _shape(mig, mig_name), _shape(orm, orm_name)
    assert {r[0] for r in a["columns"]} == set(TABLES)
    for part in ("columns", "constraints", "indexes", "comments"):
        assert a[part] == b[part], part
    # the comparison must have seen the things it claims to compare
    assert any(k[2] == "c" for k in a["constraints"]), "no CHECK constraint compared"
    assert any(k[2] == "p" for k in a["constraints"]), "no PRIMARY KEY compared"
    assert any("idx_ccd_school_staffing_lea" == i[1] for i in a["indexes"]), "the leaid index was not compared"
    assert sum(1 for c in a["comments"] if c[1]) == 2, "the two table comments were not compared"


def test_migration_033_is_idempotent(scratch_schemas):
    name, conn = scratch_schemas("idem")
    _apply_migration(conn)
    before = _shape(conn, name)
    _apply_migration(conn)          # IF NOT EXISTS throughout: a second apply is a no-op
    assert _shape(conn, name) == before and {r[0] for r in before["columns"]} == set(TABLES)
