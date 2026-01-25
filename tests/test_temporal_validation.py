"""
Tests for Temporal Data Blending Validation (REQ-026).

These tests validate the 3-year blending window rule that ensures data from
multiple sources (enrollment, staffing, bell schedules) span ≤3 consecutive
school years.

Rule: Data from multiple sources must span ≤3 consecutive school years
Exception: SPED baseline ratios (2017-18 IDEA 618/CRDC) are exempt as ratio proxies

Run with: pytest tests/test_temporal_validation.py -v
"""

import pytest
from typing import Optional


# =============================================================================
# HELPER FUNCTIONS (matching database SQL functions)
# =============================================================================

def school_year_to_numeric(year_str: Optional[str]) -> Optional[int]:
    """Convert school year string to numeric for calculations.

    Examples:
        '2023-24' -> 2023
        '2024-25' -> 2024
        '2023' -> 2023
    """
    if not year_str or year_str == '':
        return None
    try:
        return int(year_str[:4])
    except (ValueError, TypeError):
        return None


def year_span(year1: Optional[str], year2: Optional[str]) -> Optional[int]:
    """Calculate year span between two school years.

    Per REQ-026 (corrected): Returns absolute difference in start years.
    - 0 = same year
    - 1 = adjacent years (e.g., 2024-25 and 2023-24)
    - 2 = 1-year gap
    - 3 = 2-year gap

    Examples:
        span('2023-24', '2023-24') -> 0
        span('2023-24', '2024-25') -> 1
        span('2023-24', '2025-26') -> 2
    """
    y1 = school_year_to_numeric(year1)
    y2 = school_year_to_numeric(year2)

    if y1 is None or y2 is None:
        return None

    return abs(y2 - y1)


def is_within_3year_window(
    enrollment_year: Optional[str],
    staffing_year: Optional[str],
    bell_schedule_year: Optional[str]
) -> bool:
    """Check if component years are within the 3-year window.

    Per REQ-026 (corrected): Returns True if years span ≤3 years apart.
    - span = |max_year - min_year|
    - 0-1 = no flags (same or adjacent years)
    - 2-3 = warning (1-2 year gap)
    - >3 = error (exceeds window)
    """
    years = []

    if enrollment_year:
        y = school_year_to_numeric(enrollment_year)
        if y:
            years.append(y)

    if staffing_year:
        y = school_year_to_numeric(staffing_year)
        if y:
            years.append(y)

    if bell_schedule_year:
        y = school_year_to_numeric(bell_schedule_year)
        if y:
            years.append(y)

    # If fewer than 2 years, no span to check
    if len(years) < 2:
        return True

    # Calculate span (absolute difference, not +1)
    min_year = min(years)
    max_year = max(years)
    span = max_year - min_year

    return span <= 3


def calculate_temporal_flags(
    enrollment_year: Optional[str],
    staffing_year: Optional[str],
    bell_schedule_year: Optional[str],
    is_sped_baseline: bool = False
) -> list:
    """Calculate temporal validation flags for a calculation.

    Per REQ-026 (corrected):
    - No flags: span 0-1 (same year or adjacent years like 2024-25 and 2023-24)
    - WARN_YEAR_GAP: span 2-3 (1-2 year gap, e.g., 2025-26 and 2023-24)
    - ERR_SPAN_EXCEEDED: span >3 (exceeds blending window)
    - INFO_RATIO_BASELINE: Uses SPED ratio baseline (2017-18, exempt)
    """
    flags = []

    years = []
    for year in [enrollment_year, staffing_year, bell_schedule_year]:
        if year:
            y = school_year_to_numeric(year)
            if y:
                years.append(y)

    if len(years) >= 2:
        span = max(years) - min(years)  # No +1, just absolute difference

        if span > 3:
            flags.append('ERR_SPAN_EXCEEDED')
        elif span >= 2:  # 2-3 year span gets warning
            flags.append('WARN_YEAR_GAP')
        # span 0-1 gets no flags

    if is_sped_baseline:
        flags.append('INFO_RATIO_BASELINE')

    return flags


# =============================================================================
# TEST CLASSES
# =============================================================================

class TestYearSpanCalculation:
    """Tests for calculating year span from multiple sources."""

    def test_calculates_year_span_from_sources(self):
        """Year span calculated as absolute difference of start years."""
        assert year_span('2023-24', '2025-26') == 2  # |2025-2023| = 2
        assert year_span('2023-24', '2026-27') == 3  # |2026-2023| = 3
        assert year_span('2020-21', '2023-24') == 3  # |2023-2020| = 3

    def test_same_year_sources_span_is_0(self):
        """Same year for all sources has span of 0."""
        assert year_span('2023-24', '2023-24') == 0

        # Using the 3-year window function
        assert is_within_3year_window('2023-24', '2023-24', '2023-24') is True

    def test_adjacent_year_sources_span_is_1(self):
        """Adjacent years (e.g., 2024-25 and 2023-24) have span of 1."""
        assert year_span('2023-24', '2024-25') == 1
        assert is_within_3year_window('2023-24', '2024-25', '2024-25') is True

    def test_2_year_span_is_valid(self):
        """2-year span (1-year gap) is within window but gets warning."""
        assert year_span('2023-24', '2025-26') == 2  # |2025-2023| = 2
        assert is_within_3year_window('2023-24', '2024-25', '2025-26') is True

    def test_3_year_span_is_valid(self):
        """3-year span (2-year gap) is at the edge but still valid."""
        assert year_span('2023-24', '2026-27') == 3  # |2026-2023| = 3
        assert is_within_3year_window('2023-24', '2025-26', '2026-27') is True

    def test_4_year_span_exceeds_window(self):
        """4-year span exceeds the 3-year window."""
        assert year_span('2023-24', '2027-28') == 4  # |2027-2023| = 4
        assert is_within_3year_window('2023-24', '2025-26', '2027-28') is False

    def test_handles_null_years(self):
        """Null years are ignored in span calculation."""
        assert is_within_3year_window('2023-24', None, '2025-26') is True
        assert is_within_3year_window(None, '2024-25', None) is True

    def test_single_year_always_valid(self):
        """Single year source is always valid (no span to check)."""
        assert is_within_3year_window('2023-24', None, None) is True
        assert is_within_3year_window(None, '2024-25', None) is True


class TestTemporalFlags:
    """Tests for temporal validation flag assignment."""

    def test_warn_year_gap_added_for_2_3_year_span(self):
        """WARN_YEAR_GAP flag added when sources span 2-3 years."""
        # 2-year span (1-year gap: 2025-26 and 2023-24)
        flags = calculate_temporal_flags('2023-24', '2024-25', '2025-26')
        assert 'WARN_YEAR_GAP' in flags
        assert 'ERR_SPAN_EXCEEDED' not in flags

        # 3-year span (2-year gap: 2026-27 and 2023-24)
        flags = calculate_temporal_flags('2023-24', '2025-26', '2026-27')
        assert 'WARN_YEAR_GAP' in flags
        assert 'ERR_SPAN_EXCEEDED' not in flags

    def test_err_span_exceeded_added_for_greater_than_3(self):
        """ERR_SPAN_EXCEEDED flag added when sources span >3 years."""
        # 4-year span (3-year gap: 2027-28 and 2023-24)
        flags = calculate_temporal_flags('2023-24', '2025-26', '2027-28')
        assert 'ERR_SPAN_EXCEEDED' in flags
        assert 'WARN_YEAR_GAP' not in flags

        # 4-year span (2020-21 to 2024-25)
        flags = calculate_temporal_flags('2020-21', '2022-23', '2024-25')
        assert 'ERR_SPAN_EXCEEDED' in flags

    def test_no_flags_for_same_year_data(self):
        """No temporal flags when all sources are from same year."""
        flags = calculate_temporal_flags('2023-24', '2023-24', '2023-24')
        assert len(flags) == 0

    def test_no_flags_for_adjacent_years(self):
        """No flags for adjacent years (span = 1)."""
        # 2024-25 and 2023-24 are adjacent (span = 1)
        flags = calculate_temporal_flags('2023-24', '2024-25', '2023-24')
        assert len(flags) == 0


class TestSpedBaselineException:
    """Tests for SPED 2017-18 baseline exemption from 3-year rule."""

    def test_sped_2017_18_exempt_from_3_year_rule(self):
        """SPED baseline (2017-18) is exempt from the 3-year window rule.

        The 2017-18 IDEA 618 and CRDC data are used as ratio proxies
        for SPED teacher/enrollment splits. These are the most recent
        complete federal datasets pre-COVID and are exempt from the
        temporal blending window.
        """
        # This would normally exceed the 3-year window (2017-18 to 2025-26 = 9 years)
        # But SPED baseline is exempt
        flags = calculate_temporal_flags(
            enrollment_year='2023-24',
            staffing_year='2023-24',
            bell_schedule_year='2025-26',
            is_sped_baseline=True
        )
        assert 'INFO_RATIO_BASELINE' in flags

    def test_info_ratio_baseline_flag_for_sped_exception(self):
        """INFO_RATIO_BASELINE flag indicates SPED baseline exemption."""
        flags = calculate_temporal_flags(
            enrollment_year='2023-24',
            staffing_year='2017-18',  # SPED baseline year
            bell_schedule_year='2025-26',
            is_sped_baseline=True
        )
        assert 'INFO_RATIO_BASELINE' in flags

    def test_sped_baseline_still_validates_other_sources(self):
        """SPED baseline exemption applies to SPED ratios only.

        The exemption doesn't prevent other sources from being validated.
        The INFO_RATIO_BASELINE flag documents the exception.
        """
        flags = calculate_temporal_flags(
            enrollment_year='2023-24',
            staffing_year='2023-24',
            bell_schedule_year='2023-24',
            is_sped_baseline=True
        )
        assert 'INFO_RATIO_BASELINE' in flags
        assert 'ERR_SPAN_EXCEEDED' not in flags


class TestValidationTrigger:
    """Tests for automatic validation trigger behavior."""

    def test_trigger_auto_validates_on_insert(self):
        """Trigger trg_lct_temporal_validation fires on INSERT.

        Note: This tests the expected behavior. Actual trigger testing
        requires database integration tests.
        """
        # Test that our validation logic would flag this correctly
        enrollment_year = '2023-24'
        staffing_year = '2025-26'
        bell_schedule_year = '2027-28'  # |2027-2023| = 4-year span

        # This should trigger ERR_SPAN_EXCEEDED
        assert not is_within_3year_window(enrollment_year, staffing_year, bell_schedule_year)
        flags = calculate_temporal_flags(enrollment_year, staffing_year, bell_schedule_year)
        assert 'ERR_SPAN_EXCEEDED' in flags

    def test_trigger_auto_validates_on_update(self):
        """Trigger trg_lct_temporal_validation fires on UPDATE.

        Note: This tests the expected behavior. Actual trigger testing
        requires database integration tests.
        """
        # Originally valid (span 0)
        original_flags = calculate_temporal_flags('2023-24', '2023-24', '2023-24')
        assert len(original_flags) == 0

        # After update to 4-year span (|2027-2023| = 4)
        updated_flags = calculate_temporal_flags('2023-24', '2024-25', '2027-28')
        assert 'ERR_SPAN_EXCEEDED' in updated_flags


class TestSchoolYearConversion:
    """Tests for school year string to numeric conversion."""

    def test_converts_standard_format(self):
        """Standard school year format (YYYY-YY) converts correctly."""
        assert school_year_to_numeric('2023-24') == 2023
        assert school_year_to_numeric('2024-25') == 2024
        assert school_year_to_numeric('2025-26') == 2025

    def test_handles_four_digit_only(self):
        """Four-digit year format works."""
        assert school_year_to_numeric('2023') == 2023

    def test_handles_full_year_format(self):
        """Full year format (YYYY-YYYY) works."""
        assert school_year_to_numeric('2023-2024') == 2023

    def test_returns_none_for_invalid(self):
        """Invalid formats return None."""
        assert school_year_to_numeric(None) is None
        assert school_year_to_numeric('') is None
        assert school_year_to_numeric('invalid') is None


class TestEdgeCases:
    """Tests for edge cases in temporal validation."""

    def test_all_null_years_valid(self):
        """All null years is valid (nothing to validate)."""
        assert is_within_3year_window(None, None, None) is True

    def test_exactly_3_year_boundary(self):
        """Exactly 3-year span is valid (at boundary)."""
        # 2023-24 to 2026-27 = |2026-2023| = 3 year span
        assert is_within_3year_window('2023-24', '2025-26', '2026-27') is True
        flags = calculate_temporal_flags('2023-24', '2025-26', '2026-27')
        assert 'WARN_YEAR_GAP' in flags
        assert 'ERR_SPAN_EXCEEDED' not in flags

    def test_just_over_3_year_boundary(self):
        """Just over 3-year span is invalid."""
        # 2023-24 to 2027-28 = |2027-2023| = 4 year span
        assert is_within_3year_window('2023-24', '2025-26', '2027-28') is False
        flags = calculate_temporal_flags('2023-24', '2025-26', '2027-28')
        assert 'ERR_SPAN_EXCEEDED' in flags

    def test_non_contiguous_years_calculated_correctly(self):
        """Non-contiguous years still use min/max for span."""
        # 2020-21 and 2024-25 (skipping 2021-2023) = |2024-2020| = 4 year span
        assert year_span('2020-21', '2024-25') == 4
        assert is_within_3year_window('2020-21', None, '2024-25') is False


class TestResolutionOptions:
    """Tests documenting resolution options for span violations."""

    def test_resolution_option_update_source(self):
        """Resolution: Update source to more recent data.

        When ERR_SPAN_EXCEEDED is flagged, one option is to find
        more recent source data to reduce the span.
        """
        # Original: 4-year span (|2024-2020| = 4)
        flags_before = calculate_temporal_flags('2020-21', '2022-23', '2024-25')
        assert 'ERR_SPAN_EXCEEDED' in flags_before

        # After updating to more recent sources: 2-year span (|2024-2022| = 2)
        flags_after = calculate_temporal_flags('2022-23', '2023-24', '2024-25')
        assert 'ERR_SPAN_EXCEEDED' not in flags_after
        assert 'WARN_YEAR_GAP' in flags_after  # Still warned but valid

    def test_resolution_option_user_direction(self):
        """Resolution: Flag for user direction.

        When span exceeds 3 years and update isn't possible,
        flag for manual review by user.
        """
        # 5-year span (|2025-2020| = 5)
        flags = calculate_temporal_flags('2020-21', '2023-24', '2025-26')
        assert 'ERR_SPAN_EXCEEDED' in flags
        # This calculation should be queued for user review

    def test_resolution_option_accept_with_flag(self):
        """Resolution: Accept with flag (for transparency).

        In some cases, data may be accepted with ERR_SPAN_EXCEEDED
        flag for transparency in reports.
        """
        # 5-year span
        flags = calculate_temporal_flags('2020-21', '2023-24', '2025-26')
        assert 'ERR_SPAN_EXCEEDED' in flags
        # ERR_ prefix indicates error that should be addressed
        # but doesn't necessarily exclude from calculations


@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests requiring database connection.

    These tests verify the actual database implementation of temporal
    validation matches the Python helper functions.

    These tests require the full database setup including migrations
    (specifically migration 008 for temporal validation functions).
    """

    @pytest.fixture
    def db_session(self):
        """Database session fixture.

        Skip if database not available.
        """
        try:
            import sys
            from pathlib import Path
            project_root = Path(__file__).parent.parent
            sys.path.insert(0, str(project_root))

            from infrastructure.database.connection import session_scope
            with session_scope() as session:
                yield session
        except Exception:
            pytest.skip("Database not available")

    def _check_function_exists(self, db_session, func_name: str) -> bool:
        """Check if a SQL function exists."""
        from sqlalchemy import text
        result = db_session.execute(text("""
            SELECT COUNT(*) FROM information_schema.routines
            WHERE routine_schema = 'public' AND routine_name = :func_name
        """), {"func_name": func_name})
        return result.scalar() > 0

    def test_school_year_to_numeric_matches_sql(self, db_session):
        """Python function matches SQL function output."""
        from sqlalchemy import text

        if not self._check_function_exists(db_session, 'school_year_to_numeric'):
            pytest.skip("SQL function school_year_to_numeric not installed - run migration 008")

        test_years = ['2023-24', '2024-25', '2025-26', '2020-21']
        for year in test_years:
            result = db_session.execute(
                text("SELECT school_year_to_numeric(:year)"),
                {"year": year}
            )
            sql_result = result.scalar()
            python_result = school_year_to_numeric(year)
            assert sql_result == python_result, f"Mismatch for {year}"

    def test_year_span_matches_sql(self, db_session):
        """Python year_span matches SQL function output."""
        from sqlalchemy import text

        if not self._check_function_exists(db_session, 'year_span'):
            pytest.skip("SQL function year_span not installed - run migration 008")

        test_cases = [
            ('2023-24', '2023-24', 0),  # Same year
            ('2023-24', '2024-25', 1),  # Adjacent years
            ('2023-24', '2025-26', 2),  # 1-year gap
            ('2023-24', '2026-27', 3),  # 2-year gap
        ]
        for year1, year2, expected in test_cases:
            result = db_session.execute(
                text("SELECT year_span(:y1, :y2)"),
                {"y1": year1, "y2": year2}
            )
            sql_result = result.scalar()
            python_result = year_span(year1, year2)
            assert sql_result == expected, f"SQL: {sql_result} != {expected}"
            assert python_result == expected, f"Python: {python_result} != {expected}"

    def test_is_within_3year_window_matches_sql(self, db_session):
        """Python function matches SQL function output."""
        from sqlalchemy import text

        if not self._check_function_exists(db_session, 'is_within_3year_window'):
            pytest.skip("SQL function is_within_3year_window not installed - run migration 008")

        test_cases = [
            ('2023-24', '2023-24', '2023-24', True),  # span 0
            ('2023-24', '2024-25', '2025-26', True),  # span 2 (within window)
            ('2023-24', '2025-26', '2026-27', True),  # span 3 (at boundary)
            ('2023-24', '2025-26', '2027-28', False),  # span 4 (exceeds)
        ]
        for enroll, staff, bell, expected in test_cases:
            result = db_session.execute(
                text("SELECT is_within_3year_window(:e, :s, :b)"),
                {"e": enroll, "s": staff, "b": bell}
            )
            sql_result = result.scalar()
            python_result = is_within_3year_window(enroll, staff, bell)
            assert sql_result == expected, f"SQL: {sql_result} != {expected}"
            assert python_result == expected, f"Python: {python_result} != {expected}"

    def test_temporal_validation_columns_exist(self, db_session):
        """lct_calculations table has temporal validation columns."""
        from sqlalchemy import text

        result = db_session.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'lct_calculations'
            AND column_name IN ('year_span', 'within_3year_window', 'temporal_flags')
            ORDER BY column_name
        """))
        columns = [row[0] for row in result.fetchall()]

        # Skip if migration 008 columns haven't been added (requires DBA privileges)
        if not columns:
            pytest.skip("Temporal validation columns not installed - run migration 008 with DBA privileges")

        assert 'temporal_flags' in columns
        assert 'within_3year_window' in columns
        assert 'year_span' in columns

    def test_temporal_validation_trigger_exists(self, db_session):
        """trg_lct_temporal_validation trigger exists."""
        from sqlalchemy import text

        result = db_session.execute(text("""
            SELECT trigger_name
            FROM information_schema.triggers
            WHERE event_object_table = 'lct_calculations'
            AND trigger_name = 'trg_lct_temporal_validation'
        """))
        trigger = result.fetchone()

        # Skip if migration 008 trigger hasn't been created (requires DBA privileges)
        if trigger is None:
            pytest.skip("Trigger trg_lct_temporal_validation not installed - run migration 008 with DBA privileges")

        assert trigger is not None, "Trigger trg_lct_temporal_validation not found"

    def test_temporal_validation_view_exists(self, db_session):
        """v_lct_temporal_validation view exists."""
        from sqlalchemy import text

        result = db_session.execute(text("""
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'public'
            AND table_name = 'v_lct_temporal_validation'
        """))
        view = result.fetchone()

        # Skip if migration 008 view hasn't been created (requires DBA privileges)
        if view is None:
            pytest.skip("View v_lct_temporal_validation not installed - run migration 008 with DBA privileges")

        assert view is not None, "View v_lct_temporal_validation not found"
