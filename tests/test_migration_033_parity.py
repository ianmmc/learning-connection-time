"""#1038 (#1022 T4): migration 033 and the ORM declare the same four tables.

The schema invariant from PR #641: a table declared twice (migration DDL for a migrated DB, the
models for a fresh `create_all()` DB) must be declared identically, or the two kinds of database
diverge. Each test builds the tables BOTH ways in throwaway databases on the local Postgres server
and compares information_schema: columns (type, length, precision, nullability, default presence),
primary keys and CHECK constraint names. The live LCT database is never touched.
"""
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

TABLES = ("ccd_school_staffing", "lea_school_staffing", "lea_band_staffing", "lea_grade_teacher_fte")
MIGRATION = (Path(__file__).resolve().parents[1]
             / "infrastructure/database/migrations/033_ccd_school_staffing.sql")


def _shape(engine):
    with engine.connect() as c:
        cols = c.execute(text(
            "SELECT table_name, column_name, data_type, character_maximum_length, numeric_precision, "
            "numeric_scale, is_nullable, column_default IS NOT NULL "
            "FROM information_schema.columns WHERE table_name = ANY(:t) ORDER BY 1, 2"),
            {"t": list(TABLES)}).all()
        cons = c.execute(text(
            "SELECT tc.table_name, tc.constraint_type, tc.constraint_name, "
            "string_agg(k.column_name, ',' ORDER BY k.ordinal_position) "
            "FROM information_schema.table_constraints tc "
            "LEFT JOIN information_schema.key_column_usage k ON k.constraint_name = tc.constraint_name "
            "WHERE tc.table_name = ANY(:t) AND tc.constraint_type IN ('PRIMARY KEY', 'CHECK') "
            "AND tc.constraint_name NOT LIKE '%_not_null' "
            "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"), {"t": list(TABLES)}).all()
    return [tuple(r) for r in cols], [tuple(r) for r in cons]


@pytest.fixture
def scratch_dbs():
    from infrastructure.database.connection import get_engine
    from infrastructure.utilities.db_url import engine_connect_args, sqlalchemy_url

    base = get_engine().url

    def engine_for(db, **kw):
        url = sqlalchemy_url(base.set(database=db).render_as_string(hide_password=False))
        return create_engine(url, connect_args=engine_connect_args(url), **kw)

    admin = engine_for("postgres", isolation_level="AUTOCOMMIT")
    names = [f"scratch_1038_{tag}_{uuid.uuid4().hex[:8]}" for tag in ("mig", "orm")]
    with admin.connect() as c:
        for n in names:
            c.execute(text(f'CREATE DATABASE "{n}"'))
    engines = [engine_for(n) for n in names]
    try:
        yield engines
    finally:
        for e in engines:
            e.dispose()
        with admin.connect() as c:
            for n in names:
                c.execute(text(f'DROP DATABASE IF EXISTS "{n}" WITH (FORCE)'))
        admin.dispose()


def test_migration_033_and_models_declare_the_same_tables(scratch_dbs):
    from infrastructure.database.models import Base
    mig, orm = scratch_dbs
    with mig.begin() as c:
        c.exec_driver_sql(MIGRATION.read_text())
    Base.metadata.create_all(orm, tables=[Base.metadata.tables[t] for t in TABLES])

    mig_cols, mig_cons = _shape(mig)
    orm_cols, orm_cons = _shape(orm)
    assert {r[0] for r in mig_cols} == set(TABLES)
    assert mig_cols == orm_cols
    assert mig_cons == orm_cons


def test_migration_033_is_idempotent(scratch_dbs):
    mig, _ = scratch_dbs
    sql = MIGRATION.read_text()
    with mig.begin() as c:
        c.exec_driver_sql(sql)
    with mig.begin() as c:
        c.exec_driver_sql(sql)          # IF NOT EXISTS throughout: a second apply is a no-op
    assert {r[0] for r in _shape(mig)[0]} == set(TABLES)
