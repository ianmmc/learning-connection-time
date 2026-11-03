"""The importer's write path against a REAL Session (#1076): what reaches Postgres, not what a
MagicMock was handed. The three findings the fake-session tests could not see (PR #1068 review):

  * membership_flags for a school with no flagged grade is SQL NULL, never the JSON scalar `null`
    (#1069) — so `IS NULL` and jsonb_each_text() behave;
  * one INSERT statement per chunk, not one per run of identical non-NULL key sets (#1074);
  * the DELETE is scoped to the year: another vintage's rows and their lineage survive a replace.

Scratch SCHEMAS on the governance Postgres (the test_migration_033_parity fixture), the migration
applied verbatim plus a minimal `districts` for the #1085 match guard. The live LCT DB is never touched.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from infrastructure.database.migrations import import_ccd_school_staffing as m
from infrastructure.database.models import DataLineage
from tests.test_import_ccd_school_staffing import ELEM, LEA, YEAR, build_year, three_school_floor  # noqa: F401
from tests.test_migration_033_parity import MIGRATION, scratch_schemas  # noqa: F401

pytestmark = [pytest.mark.govdb, pytest.mark.integration]


def _prepare(conn, districts=(LEA,)):
    conn.exec_driver_sql(MIGRATION.read_text())
    conn.exec_driver_sql("CREATE TABLE districts (nces_id VARCHAR(10) PRIMARY KEY)")
    for d in districts:
        conn.exec_driver_sql("INSERT INTO districts VALUES (%s)", (d,))
    DataLineage.__table__.create(conn)
    conn.commit()


def _count_inserts(conn) -> list:
    seen = []

    @event.listens_for(conn, "before_cursor_execute")
    def _(c, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO CCD_SCHOOL_STAFFING"):
            seen.append(statement)
    return seen


def test_membership_flags_is_sql_null_and_a_chunk_is_one_statement(scratch_schemas, tmp_path, monkeypatch):
    _, conn = scratch_schemas("write")
    _prepare(conn)
    rows, details = m.load_year(YEAR, tmp_path, build_year(tmp_path))
    monkeypatch.setattr(m, "INSERT_CHUNK", 2)
    inserts = _count_inserts(conn)
    with Session(bind=conn) as s:
        assert m.write_year(s, YEAR, rows, details) == 3
        s.commit()
    # 3 rows in chunks of 2 → 2 statements. The ORM bulk path would emit 3: ELEM, MID and HIGH each
    # have a different set of None-valued columns (#1074).
    assert len(inserts) == 2
    sql_null, json_null, total = conn.execute(text(
        "SELECT count(*) FILTER (WHERE membership_flags IS NULL), "
        "count(*) FILTER (WHERE membership_flags = 'null'::jsonb), count(*) FROM ccd_school_staffing")).one()
    assert (sql_null, json_null, total) == (2, 0, 3)                                   # #1069
    flagged = conn.execute(text(
        "SELECT ncessch, key, value FROM ccd_school_staffing, jsonb_each_text(membership_flags) ORDER BY 2")).all()
    assert flagged == [(ELEM, "Grade 1", "Manual adjustment"), (ELEM, "Grade 2", "Suppressed")]
    assert conn.execute(text(
        "SELECT count(*) FROM ccd_school_staffing WHERE memb_01 IS NULL AND memb_02 IS NULL AND ncessch = :s"),
        {"s": ELEM}).scalar() == 1                                                     # #1070
    assert conn.execute(text(
        "SELECT count(*) FROM ccd_school_staffing WHERE school_name = 'NaN' OR gslo = 'NaN' OR level = 'NaN'")).scalar() == 0
    lineage = conn.execute(text("SELECT entity_id, details->'district_match' FROM data_lineage")).all()
    assert lineage == [(YEAR, {"file_leas": 1, "districts": 1, "matched": 1})]


def test_a_replace_is_scoped_to_its_year(scratch_schemas, tmp_path):
    _, conn = scratch_schemas("replace")
    _prepare(conn)
    rows, details = m.load_year(YEAR, tmp_path, build_year(tmp_path))
    other = [dict(r, source_year="2023-24") for r in rows]
    with Session(bind=conn) as s:
        m.write_year(s, YEAR, rows, dict(details))
        m.write_year(s, "2023-24", other, dict(details, year="2023-24"))
        m.write_year(s, YEAR, rows[:2], dict(details))                 # the replace
        s.commit()
    per_year = dict(conn.execute(text(
        "SELECT source_year, count(*) FROM ccd_school_staffing GROUP BY 1")).all())
    assert per_year == {YEAR: 2, "2023-24": 3}
    assert conn.execute(text("SELECT count(*) FROM data_lineage")).scalar() == 3


def test_a_file_whose_leaids_match_no_district_is_refused_before_the_delete(scratch_schemas, tmp_path):
    _, conn = scratch_schemas("match")
    _prepare(conn, districts=("0199999",))                   # ours, but none the file carries
    rows, details = m.load_year(YEAR, tmp_path, build_year(tmp_path))
    with Session(bind=conn) as s:
        with pytest.raises(m.DataGuardError, match="only 0 of 1 districts matched"):
            m.write_year(s, YEAR, rows, details)
        s.rollback()
    assert conn.execute(text("SELECT count(*) FROM ccd_school_staffing")).scalar() == 0
