"""G5 (#972 generalization): NCES_PRIMARY_YEAR must be present in every year-keyed LCT table.

CLAUDE.md says the constant is "verified against lct_calculations rows" on each bump — this makes
that sentence executable. It catches both directions: the constant bumped without an ingest, and an
ingest landed without the bump (the newest year in the table outruns the constant).

Needs the live LCT DB (Docker up) — marker `integration`, excluded from the fast gate.
"""

import pytest
from sqlalchemy import text

from infrastructure.utilities.school_year import COVID_EXCLUDED_YEARS, NCES_PRIMARY_YEAR

YEAR_KEYED = [
    ("enrollment_by_grade", "source_year"),
    ("staff_counts_effective", "effective_year"),
    ("sped_estimates", "estimate_year"),
    ("lct_calculations", "enrollment_source_year"),
]


@pytest.mark.integration
@pytest.mark.parametrize("table,column", YEAR_KEYED, ids=[t for t, _ in YEAR_KEYED])
def test_primary_year_is_present_and_is_the_newest(table, column):
    from infrastructure.database.connection import session_scope

    with session_scope() as s:
        years = {y for (y,) in s.execute(text(f"SELECT DISTINCT {column} FROM {table}")) if y}
    assert years, f"NOTHING MEASURED — {table}.{column} has no non-null years"
    assert NCES_PRIMARY_YEAR in years, (
        f"{table}.{column} carries {sorted(years)} but NCES_PRIMARY_YEAR is {NCES_PRIMARY_YEAR} — "
        f"the constant was bumped without an ingest (or the ingest targeted another year)"
    )
    newest = max(y for y in years if y not in COVID_EXCLUDED_YEARS)
    assert newest == NCES_PRIMARY_YEAR, (
        f"{table}.{column} already carries {newest}, newer than NCES_PRIMARY_YEAR={NCES_PRIMARY_YEAR} — "
        f"an ingest landed without the bump (school_year.py)"
    )
