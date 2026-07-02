"""Issue #11 regression: the temporal trigger must fire on rows written THROUGH THE ORM.

The original defect was invisible to raw-SQL tests: migration 008's trigger read
*_source_year columns that LCTCalculation didn't even map, so the production write path
(calculate_lct_variants → ORM) could never populate them and every row passed validation.
This test inserts via the ORM — exactly the production path — and asserts the trigger
computed span/window/flags (v2 semantics: 3 consecutive school years, span <= 2)."""
import pytest
from sqlalchemy import text

from infrastructure.database.connection import get_engine, get_session_factory
from infrastructure.database.models import LCTCalculation

pytestmark = pytest.mark.integration

TEST_DISTRICT = None  # resolved from the DB at runtime


@pytest.fixture
def session_or_skip():
    try:
        eng = get_engine()
        eng.connect().close()
    except Exception as e:
        pytest.skip(f"LCT Postgres unavailable: {type(e).__name__}")
    trg = get_engine().connect().execute(text(
        "SELECT 1 FROM pg_trigger WHERE tgname='trg_lct_temporal_validation'")).fetchone()
    if not trg:
        pytest.skip("temporal trigger not installed (migration 008/018)")
    s = get_session_factory()()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _any_district(session):
    row = session.execute(text("SELECT nces_id FROM districts LIMIT 1")).fetchone()
    if not row:
        pytest.skip("no districts loaded")
    return row[0]


def _mk(session, did, **years):
    # staff_scope must satisfy the live chk_staff_scope allowlist (a migration-era CHECK the
    # model doesn't declare — issue #21 drift); the session is rolled back, nothing persists.
    return LCTCalculation(
        district_id=did, year="2025-26", grade_level=None, staff_scope="teachers_only",
        run_id="zz-test", instructional_minutes=360, instructional_minutes_source="bell_schedule",
        enrollment=1000, instructional_staff=50.0, lct_value=18.0, data_tier=1, **years)


class TestTriggerFiresViaORM:
    def test_coherent_three_year_blend_flagged_warn(self, session_or_skip):
        s = session_or_skip
        calc = _mk(s, _any_district(s),
                   enrollment_source_year="2023-24",
                   staff_source_year="2024-25",
                   bell_schedule_source_year="2025-26")
        s.add(calc)
        s.flush()
        s.refresh(calc)
        assert calc.year_span == 2
        assert calc.within_3year_window is True
        assert "WARN_YEAR_GAP" in (calc.temporal_flags or [])

    def test_four_year_span_errors(self, session_or_skip):
        s = session_or_skip
        calc = _mk(s, _any_district(s),
                   enrollment_source_year="2023-24",
                   staff_source_year="2023-24",
                   bell_schedule_source_year="2026-27")
        s.add(calc)
        s.flush()
        s.refresh(calc)
        assert calc.year_span == 3
        assert calc.within_3year_window is False
        assert "ERR_SPAN_EXCEEDED" in (calc.temporal_flags or [])

    def test_covid_source_year_errors_outright(self, session_or_skip):
        s = session_or_skip
        calc = _mk(s, _any_district(s),
                   enrollment_source_year="2023-24",
                   staff_source_year="2023-24",
                   bell_schedule_source_year="2022-23")
        s.add(calc)
        s.flush()
        s.refresh(calc)
        assert calc.within_3year_window is False
        assert "ERR_COVID_YEAR" in (calc.temporal_flags or [])

    def test_statutory_rows_pass_clean(self, session_or_skip):
        s = session_or_skip
        calc = _mk(s, _any_district(s),
                   enrollment_source_year="2023-24",
                   staff_source_year="2023-24",
                   bell_schedule_source_year=None)   # statutory minutes carry no year
        s.add(calc)
        s.flush()
        s.refresh(calc)
        assert calc.year_span == 0
        assert calc.within_3year_window is True
