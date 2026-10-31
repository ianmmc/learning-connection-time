"""#599: migration 023's staff_counts_effective backfill joins staff_counts on (district_id, source_year), but the
real unique key is (district_id, source_year, DATA_SOURCE). With two data_source values for one district-year that
UPDATE ... FROM picks one source row nondeterministically - a silently wrong backfilled value. Migration 023 is
applied + ledgered (checksummed), so its SQL cannot be edited; the hazard is guarded at the PRECONDITION instead:

* DB-free (fast gate): `staff_counts` has exactly ONE writer and ONE data_source literal, and the effective-table
  copy path scopes by data_source. A second source landing fails here, naming the migration it would break.
* Live DB (integration): no (district_id, source_year) group carries more than one data_source.

Measured live 2026-10-31: one data_source ('nces_ccd', 35,596 rows), 0 multi-source groups."""
import ast
from pathlib import Path

import pytest
from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
IMPORTER = REPO / "infrastructure/database/migrations/import_staff_and_enrollment.py"

WHY = ("A second staff_counts data_source breaks migration 023's backfill JOIN, which keys on "
       "(district_id, source_year) without data_source (#599). Scope any re-backfill by data_source "
       "(sc.data_source = ...) and the effective-table copy path, then update this pin.")


def _scanned():
    for p in sorted((REPO / "infrastructure").rglob("*.py")):
        if "__pycache__" not in p.parts:
            yield p, ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def test_staff_counts_has_one_writer_and_no_raw_insert():
    writers, raw = set(), set()
    for p, tree in _scanned():
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "StaffCounts":
                writers.add(str(p.relative_to(REPO)))
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and "insert into staff_counts " in n.value.lower().replace("\n", " ") + " "):
                raw.add(str(p.relative_to(REPO)))
    assert writers == {"infrastructure/database/migrations/import_staff_and_enrollment.py"}, WHY
    assert not raw, f"raw INSERT INTO staff_counts in {sorted(raw)}. {WHY}"


def test_the_only_data_source_literal_stamped_is_nces_ccd():
    tree = ast.parse(IMPORTER.read_text(encoding="utf-8"))
    stamped = {
        n.value.value for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
        and any(isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "data_source"
                for t in n.targets)
    }
    assert stamped == {"nces_ccd"}, WHY


def test_effective_copy_path_scopes_by_data_source():
    tree = ast.parse(IMPORTER.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "populate_effective_staff_counts")
    assert "StaffCounts.data_source" in ast.unparse(fn), WHY


@pytest.mark.integration
def test_live_staff_counts_has_no_multi_source_district_year():
    from infrastructure.database.connection import get_engine
    try:
        eng = get_engine()
        conn = eng.connect()
    except Exception as e:
        pytest.skip(f"LCT Postgres unavailable: {type(e).__name__}")
    with conn:
        n = conn.execute(text(
            "SELECT count(*) FROM (SELECT district_id, source_year FROM staff_counts "
            "GROUP BY 1, 2 HAVING count(DISTINCT data_source) > 1) t")).scalar()
    assert n == 0, f"{n} (district_id, source_year) groups carry more than one data_source. {WHY}"
