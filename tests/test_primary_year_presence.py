"""G5 (#972 generalization): NCES_PRIMARY_YEAR must be present in every year-keyed LCT table.

CLAUDE.md says the constant is "verified against lct_calculations rows" on each bump — this makes
that sentence executable. It catches both directions: the constant bumped without an ingest, and an
ingest landed without the bump (the newest year in the table outruns the constant).

The verdict is ONE pure function, `check_primary_year_presence`, so the fast gate can prove it is red
for a bumped constant without a DB (#981: plan property P5 had no test). The live-DB sweep below
feeds it the real distinct years — marker `integration`, excluded from the fast gate.
"""

import pytest

from infrastructure.utilities.school_year import COVID_EXCLUDED_YEARS, NCES_PRIMARY_YEAR

YEAR_KEYED = [
    ("enrollment_by_grade", "source_year"),
    ("staff_counts_effective", "effective_year"),
    ("sped_estimates", "estimate_year"),
    ("lct_calculations", "enrollment_source_year"),
]


def check_primary_year_presence(table: str, column: str, years: set[str], primary: str = NCES_PRIMARY_YEAR) -> None:
    """Raise AssertionError unless `primary` is present in `years` AND is the newest non-COVID one."""
    assert years, f"NOTHING MEASURED — {table}.{column} has no non-null years"
    assert primary in years, (
        f"{table}.{column} carries {sorted(years)} but NCES_PRIMARY_YEAR is {primary} — "
        f"the constant was bumped without an ingest (or the ingest targeted another year)"
    )
    newest = max(y for y in years if y not in COVID_EXCLUDED_YEARS)
    assert newest == primary, (
        f"{table}.{column} already carries {newest}, newer than NCES_PRIMARY_YEAR={primary} — "
        f"an ingest landed without the bump (school_year.py)"
    )


class TestTheVerdictCanFail:
    """P5: the check must go red in both directions, and green only on the healthy shape."""

    def test_healthy(self):
        check_primary_year_presence("t", "c", {"2023-24", "2024-25"}, primary="2024-25")

    def test_bumped_without_an_ingest(self):
        with pytest.raises(AssertionError, match="bumped without an ingest"):
            check_primary_year_presence("t", "c", {"2023-24", "2024-25"}, primary="2025-26")

    def test_ingest_landed_without_the_bump(self):
        with pytest.raises(AssertionError, match="without the bump"):
            check_primary_year_presence("t", "c", {"2023-24", "2024-25", "2025-26"}, primary="2024-25")

    def test_covid_years_never_count_as_newest(self):
        check_primary_year_presence("t", "c", {"2018-19", "2021-22"}, primary="2018-19")

    def test_empty_is_nothing_measured(self):
        with pytest.raises(AssertionError, match="NOTHING MEASURED"):
            check_primary_year_presence("t", "c", set())


@pytest.mark.integration
@pytest.mark.parametrize("table,column", YEAR_KEYED, ids=[t for t, _ in YEAR_KEYED])
def test_primary_year_is_present_and_is_the_newest(table, column):
    from infrastructure.database.connection import session_scope
    from infrastructure.database.queries import distinct_years

    with session_scope() as s:
        years = set(distinct_years(s, table, column))
    check_primary_year_presence(table, column, years)
