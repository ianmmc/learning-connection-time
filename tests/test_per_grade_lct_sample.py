"""per_grade_lct_sample.py's "legacy" column (2026-07-22 regression).

An earlier version re-derived "legacy" live via get_instructional_minutes(), which has a pre-existing
REQ-024 fallback (high -> middle -> elementary) that picks up ANY measured bell_schedules row —
including one Stage 9 had *just* written for the very district being sampled. So the moment a district
was incorporated, "legacy" silently stopped meaning "what's actually live in lct_calculations right
now" and started meaning "what the old formula computes today, contaminated by today's own write" —
caught reviewing a real district where this made a genuine +3.53 LCT change look like Δ=0.

These tests seed a district with an OBVIOUSLY contaminating bell_schedules/district_grade_minutes
value (480 min) alongside a DIFFERENT, distinguishable stored lct_calculations value (111 min) and
assert `sample()` returns the stored value, never the contaminating one.
"""
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

TEST_DID = "4809902"
TEST_STATE = "ZZ"


def _require_db():
    from infrastructure.database.connection import test_connection
    if not test_connection():
        pytest.skip("LCT production Postgres unavailable")


def _cleanup():
    from infrastructure.database.connection import session_scope as lct_scope
    with lct_scope() as s:
        for tbl in ("bell_schedules", "district_grade_minutes", "lct_calculations",
                    "enrollment_by_grade", "staff_counts_effective"):
            s.execute(text(f"DELETE FROM {tbl} WHERE district_id = :d"), {"d": TEST_DID})
        s.execute(text("DELETE FROM districts WHERE nces_id = :d"), {"d": TEST_DID})
        s.execute(text("DELETE FROM state_requirements WHERE state = :st"), {"st": TEST_STATE})


@pytest.fixture
def env():
    _require_db()
    _cleanup()
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import District, EnrollmentByGrade, StaffCountsEffective, StateRequirement
    with lct_scope() as s:
        s.add(District(nces_id=TEST_DID, name="LCT Sample Test District", state=TEST_STATE, year="2024-25"))
        s.add(StateRequirement(state=TEST_STATE, state_name="Ztest",
                               elementary_minutes=300, middle_minutes=330, high_minutes=350,
                               default_minutes=360))
        s.add(EnrollmentByGrade(district_id=TEST_DID, source_year="2024-25", data_source="nces_ccd",
                                enrollment_secondary=150,
                                enrollment_grade_6=50, enrollment_grade_7=50, enrollment_grade_8=50))
        s.add(StaffCountsEffective(district_id=TEST_DID, effective_year="2024-25",
                                   primary_source="nces_ccd",
                                   teachers_secondary_6_12=10, scope_teachers_only=10))
    try:
        yield TEST_DID
    finally:
        _cleanup()


def _seed_contaminating_bell_and_grade_data(did):
    """Simulates a Stage-9 write that's already landed: a measured 'middle' band at an
    obviously-distinguishable 480 minutes, and matching per-grade rows for 6-8."""
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import BellSchedule, DistrictGradeMinutes
    with lct_scope() as s:
        s.add(BellSchedule(district_id=did, year="2026-27", grade_level="middle",
                           instructional_minutes=480, confidence="high", method="council_extraction",
                           minutes_basis="gross_bell_to_bell"))
        for g in ("06", "07", "08"):
            s.add(DistrictGradeMinutes(district_id=did, grade=g, instructional_minutes=480,
                                       source_band="middle", method="council_extraction",
                                       minutes_basis="gross_bell_to_bell", year="2024-25"))


def _seed_stored_lct_calculation(did, *, minutes, source, lct_value, year="2025-26",
                                 calculated_at=None, staff_source_year=None,
                                 enrollment_source_year=None):
    from infrastructure.database.connection import session_scope as lct_scope
    from infrastructure.database.models import LCTCalculation
    kw = {}
    if calculated_at is not None:
        kw["calculated_at"] = calculated_at
    if staff_source_year is not None:
        kw["staff_source_year"] = staff_source_year
    if enrollment_source_year is not None:
        kw["enrollment_source_year"] = enrollment_source_year
    with lct_scope() as s:
        s.add(LCTCalculation(
            district_id=did, year=year, grade_level=None, staff_scope="teachers_secondary",
            run_id="zz-lct-sample-test", instructional_minutes=minutes,
            instructional_minutes_source=source, enrollment=150, instructional_staff=10.0,
            lct_value=lct_value, data_tier=3, **kw))


class TestLegacyReadsStoredRowNotLiveDerivation:
    def test_legacy_is_the_stored_value_even_with_contaminating_bell_data(self, env):
        from infrastructure.scripts.analyze.per_grade_lct_sample import sample
        _seed_stored_lct_calculation(env, minutes=111, source="state_requirement", lct_value=42.0)
        _seed_contaminating_bell_and_grade_data(env)   # written AFTER the stored calc, like Stage 9 would

        rows = {r["district_id"]: r for r in sample()}
        assert env in rows, "seeded district should appear (it has district_grade_minutes rows)"
        r = rows[env]
        assert r["legacy_sec_min"] == 111          # the STORED value, not the 480 bell row
        assert r["legacy_source"] == "state_requirement"
        assert r["legacy_sec_lct"] == 42.0
        # the per-grade path is independent and DOES see the 480-minute band — proving the two
        # columns now come from genuinely different sources, not the same (bug's) one
        assert r["per_grade_sec_min"] == 480

    def test_never_computed_district_reports_none_not_a_guess(self, env):
        from infrastructure.scripts.analyze.per_grade_lct_sample import sample
        _seed_contaminating_bell_and_grade_data(env)   # incorporated, but NO lct_calculations row ever

        rows = {r["district_id"]: r for r in sample()}
        r = rows[env]
        assert r["legacy_sec_min"] is None
        assert r["legacy_source"] == "never_computed"
        assert r["legacy_sec_lct"] is None
        assert r["per_grade_sec_min"] == 480          # per-grade path still works independently

    def test_most_recent_stored_row_wins_across_calc_years(self, env):
        """A district recomputed for two different years can hold a row per year for the same scope
        (uq_lct_scope_rows only dedups within a single (district, year, staff_scope) among
        grade_level-NULL rows). `sample()` must show the newest YEAR's row, not an arbitrary one."""
        from infrastructure.scripts.analyze.per_grade_lct_sample import sample
        _seed_contaminating_bell_and_grade_data(env)
        _seed_stored_lct_calculation(env, minutes=111, source="state_requirement", lct_value=42.0,
                                     year="2024-25")
        _seed_stored_lct_calculation(env, minutes=222, source="bell_schedule", lct_value=84.0,
                                     year="2025-26")

        rows = {r["district_id"]: r for r in sample()}
        r = rows[env]
        assert r["legacy_sec_min"] == 222 and r["legacy_sec_lct"] == 84.0

    def test_newest_year_wins_even_when_an_older_year_was_recomputed_later(self, env):
        """The ordering fix (PR #610 review): a TARGET_YEAR recompute clears only its own year, so an
        older year can get a LATER calculated_at than the newest year. Ordering by year DESC first (not
        calculated_at alone) must still surface the newest YEAR — else a stale-year backfill silently
        becomes 'legacy'."""
        import datetime as _dt
        from infrastructure.scripts.analyze.per_grade_lct_sample import sample
        _seed_contaminating_bell_and_grade_data(env)
        # newest year, but computed EARLIER in wall-clock time
        _seed_stored_lct_calculation(env, minutes=222, source="bell_schedule", lct_value=84.0,
                                     year="2025-26",
                                     calculated_at=_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc))
        # older year, backfilled LATER — must NOT win despite the later calculated_at
        _seed_stored_lct_calculation(env, minutes=111, source="state_requirement", lct_value=42.0,
                                     year="2024-25",
                                     calculated_at=_dt.datetime(2026, 6, 1, tzinfo=_dt.timezone.utc))

        rows = {r["district_id"]: r for r in sample()}
        r = rows[env]
        assert r["legacy_sec_min"] == 222 and r["legacy_sec_lct"] == 84.0   # newest YEAR, not latest calc

    def test_denominator_refresh_is_flagged(self, env):
        """#3: legacy LCT is baked from the stored row's staff/enrollment vintage; the per-grade side
        uses today's picks. When they differ, the row must carry denom_refreshed so a reviewer doesn't
        mistake a data-vintage shift for the per-grade methodology effect. The env fixture's
        staff/enrollment are seeded at 2024-25; a stored row from 2023-24 is a mismatch."""
        from infrastructure.scripts.analyze.per_grade_lct_sample import sample
        _seed_contaminating_bell_and_grade_data(env)
        _seed_stored_lct_calculation(env, minutes=111, source="state_requirement", lct_value=42.0,
                                     staff_source_year="2023-24", enrollment_source_year="2023-24")

        r = {row["district_id"]: row for row in sample()}[env]
        assert r["denom_refreshed"] is True

    def test_matching_denominator_years_not_flagged(self, env):
        """The flag must NOT fire when the stored row's vintage matches today's picks (2024-25)."""
        from infrastructure.scripts.analyze.per_grade_lct_sample import sample
        _seed_contaminating_bell_and_grade_data(env)
        _seed_stored_lct_calculation(env, minutes=111, source="state_requirement", lct_value=42.0,
                                     staff_source_year="2024-25", enrollment_source_year="2024-25")

        r = {row["district_id"]: row for row in sample()}[env]
        assert r["denom_refreshed"] is False


class TestMainDoesNotCrash:
    def test_main_prints_never_computed_district_without_crashing(self, env, capsys):
        """PR #610 review finding #1: main() did `pg_min - legacy_sec_min` guarding only pg_min, so a
        never-computed district (legacy_sec_min=None, pg_min a real int — the exact 'BEFORE the
        recompute lands' case) raised TypeError and killed the whole report. main() must complete."""
        from infrastructure.scripts.analyze.per_grade_lct_sample import main
        _seed_contaminating_bell_and_grade_data(env)   # incorporated, never computed -> legacy None

        rc = main(argv=[])   # must not raise
        assert rc == 0
        out = capsys.readouterr().out
        assert env in out
        assert "None" in out   # the never-computed legacy prints as None, Δ prints as None
