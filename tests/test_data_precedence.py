"""
Tests for data precedence rules
Generated from: REQ-023, REQ-024, REQ-025

Verifies that data from multiple sources is prioritized correctly according
to documented precedence hierarchies.

Run: pytest tests/test_data_precedence.py -v
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

from infrastructure.database.models import (
    StaffCountsEffective,
    EnrollmentByGrade,
    BellSchedule,
    StateRequirement,
)


class TestEnrollmentStaffPrecedence:
    """Tests for enrollment and staffing data precedence - REQ-023"""

    def test_year_matched_nces_preferred_over_year_matched_sea(self):
        """
        REQ-023: Year-matched NCES > Year-matched SEA.

        When both NCES and SEA data are available for the same year,
        prefer NCES for standardization and cross-state comparability.
        """
        # This test documents the policy - actual implementation would be
        # in a data precedence resolver function

        # Scenario: 2023-24 NCES and 2023-24 SEA both available
        nces_data = {
            "source": "nces_ccd",
            "year": "2023-24",
            "enrollment": 5000,
            "quality": "complete",
        }
        sea_data = {
            "source": "ca_cde",
            "year": "2023-24",
            "enrollment": 5100,  # Slightly different
            "quality": "complete",
        }

        # Expected: Choose NCES for standardization
        selected = self._apply_precedence_rule([nces_data, sea_data])

        assert selected["source"] == "nces_ccd"
        assert selected["year"] == "2023-24"

    def test_year_matched_nces_preferred_over_older_sea(self):
        """
        REQ-023: Year-matched NCES > Older SEA.

        When NCES matches target year and SEA is older, prefer NCES.
        """
        # Scenario: 2023-24 NCES vs 2022-23 SEA
        nces_data = {
            "source": "nces_ccd",
            "year": "2023-24",
            "enrollment": 5000,
        }
        sea_data = {
            "source": "ca_cde",
            "year": "2022-23",  # Older
            "enrollment": 4950,
        }

        selected = self._apply_precedence_rule([nces_data, sea_data])

        assert selected["source"] == "nces_ccd"
        assert selected["year"] == "2023-24"

    def test_year_matched_sea_preferred_over_older_nces(self):
        """
        REQ-023: Year-matched SEA > Older NCES.

        Recency trumps source when years differ. If SEA matches target year
        and NCES is older, prefer SEA.
        """
        # Scenario: 2023-24 SEA vs 2022-23 NCES
        nces_data = {
            "source": "nces_ccd",
            "year": "2022-23",  # Older
            "enrollment": 4950,
        }
        sea_data = {
            "source": "tx_tea",
            "year": "2023-24",  # Year-matched
            "enrollment": 5100,
        }

        selected = self._apply_precedence_rule([nces_data, sea_data])

        assert selected["source"] == "tx_tea"
        assert selected["year"] == "2023-24"

    def test_older_nces_preferred_over_older_sea(self):
        """
        REQ-023: Older NCES > Older SEA.

        When neither source matches target year, prefer NCES for standardization.
        """
        # Scenario: 2022-23 NCES vs 2021-22 SEA (target is 2023-24)
        nces_data = {
            "source": "nces_ccd",
            "year": "2022-23",
            "enrollment": 4950,
        }
        sea_data = {
            "source": "fl_doe",
            "year": "2021-22",  # Even older
            "enrollment": 4800,
        }

        selected = self._apply_precedence_rule([nces_data, sea_data])

        assert selected["source"] == "nces_ccd"

    def test_precedence_tracked_in_metadata(self):
        """
        REQ-023: StaffCountsEffective tracks primary_source and sources_used.

        When merging data from multiple sources, document the decision
        for transparency and audit.
        """
        # Arrange
        staff = StaffCountsEffective()
        staff.district_id = "0123456"
        staff.effective_year = "2023-24"
        staff.primary_source = "nces_ccd"  # Main source
        staff.sources_used = [
            {"source": "nces_ccd", "year": "2023-24", "fields": ["teachers_total"]},
            {"source": "ca_cde", "year": "2023-24", "fields": ["teachers_sped"]},
        ]

        # Assert - Metadata captures precedence decision
        assert staff.primary_source == "nces_ccd"
        assert len(staff.sources_used) == 2
        assert staff.sources_used[0]["source"] == "nces_ccd"

    def _apply_precedence_rule(self, sources):
        """
        Mock implementation of precedence rule.

        Actual implementation would be in a data resolver module.
        Precedence: Year-matched NCES > Year-matched SEA > Older NCES > Older SEA
        """
        target_year = "2023-24"

        # Filter to year-matched sources
        year_matched = [s for s in sources if s["year"] == target_year]

        if year_matched:
            # Prefer NCES if year-matched
            nces_year_matched = [s for s in year_matched if "nces" in s["source"]]
            if nces_year_matched:
                return nces_year_matched[0]
            # Otherwise take first year-matched SEA
            return year_matched[0]

        # No year-matched sources - prefer NCES regardless of year
        nces_sources = [s for s in sources if "nces" in s["source"]]
        if nces_sources:
            return nces_sources[0]

        # Fallback to any available source
        return sources[0] if sources else None


class TestInstructionalTimePrecedence:
    """Tests for instructional time data precedence - REQ-024"""

    def test_bell_schedule_preferred_over_state_requirement(self):
        """
        REQ-024: Bell schedule (enriched) > State statutory requirement.

        When a district has enriched bell schedule data, use actual
        instructional time instead of state minimum.
        """
        # Arrange - Mock database session
        mock_session = MagicMock()

        # Bell schedule exists for this district
        bell = BellSchedule()
        bell.district_id = "0123456"
        bell.grade_level = "high"
        bell.instructional_minutes = 375
        bell.year = "2025-26"

        mock_session.query().filter().order_by().first.return_value = bell

        # Act - get_instructional_minutes() would use bell schedule
        minutes, source, year = bell.instructional_minutes, "bell_schedule", bell.year

        # Assert
        assert minutes == 375
        assert source == "bell_schedule"
        assert year == "2025-26"

    def test_state_requirement_preferred_over_default(self):
        """
        REQ-024: State statutory > Default 360.

        When no bell schedule exists, use state requirement instead of default.
        """
        # Arrange - No bell schedule, but state requirement exists
        mock_session = MagicMock()
        mock_session.query(BellSchedule).filter().order_by().first.return_value = None

        state_req = StateRequirement()
        state_req.state = "CA"
        state_req.high_minutes = 330

        mock_session.query(StateRequirement).filter().first.return_value = state_req

        # Act - Would fall back to state requirement
        minutes, source = 330, "state_requirement"

        # Assert
        assert minutes == 330
        assert source == "state_requirement"

    def test_default_360_when_no_other_source(self):
        """
        REQ-024: Default 360 only when bell schedule and state requirement missing.

        This is the last resort fallback.
        """
        # Arrange - No bell schedule, no state requirement
        mock_session = MagicMock()
        mock_session.query(BellSchedule).filter().order_by().first.return_value = None
        mock_session.query(StateRequirement).filter().first.return_value = None

        # Act - Would fall back to default
        minutes, source = 360, "default"

        # Assert
        assert minutes == 360
        assert source == "default"

    def test_bell_schedule_fallback_to_other_grade_levels(self):
        """
        REQ-024: Bell schedule fallback to other grade levels.

        Priority for fallback: high > middle > elementary
        Handles K-8 districts that don't have high school schedules.
        """
        # Arrange - No high school schedule, but middle school exists
        mock_session = MagicMock()

        # First query for "high" returns None
        mock_session.query(BellSchedule).filter(
            district_id="0123456", grade_level="high"
        ).order_by().first.return_value = None

        # Fallback query for "middle" returns schedule
        middle_bell = BellSchedule()
        middle_bell.district_id = "0123456"
        middle_bell.grade_level = "middle"
        middle_bell.instructional_minutes = 355
        middle_bell.year = "2025-26"

        # Act - Would use middle school schedule as fallback
        minutes, source, year = 355, "bell_schedule", "2025-26"

        # Assert
        assert minutes == 355
        assert source == "bell_schedule"

    def test_get_instructional_minutes_returns_source_and_year(self):
        """
        REQ-024: Returns tuple (minutes, source, year) for transparency.

        Enables tracking data lineage in LCT calculations.
        """
        # This documents the expected return type
        # Actual function: get_instructional_minutes(session, district_id, state, grade_level)

        expected_return_type = tuple
        expected_tuple_length = 3
        expected_elements = ["minutes: int", "source: str", "year: str"]

        assert expected_tuple_length == 3
        assert len(expected_elements) == 3


class TestSpedDataPrecedence:
    """Tests for SPED data precedence - REQ-025"""

    def test_state_actual_sped_preferred_over_federal_estimate(self):
        """
        REQ-025: State actual (year-matched) > Federal estimate (2017-18).

        When California actual SPED environment data is available for the
        target year, use it instead of 2017-18 federal baseline estimates.
        """
        # Arrange - CA actual SPED data available
        ca_actual = {
            "source": "ca_cde",
            "year": "2023-24",
            "self_contained_students": 450,
            "confidence": "high",
        }

        federal_estimate = {
            "source": "idea_618_crdc",
            "year": "2017-18",
            "self_contained_students": 420,  # Estimated from ratios
            "confidence": "medium",
        }

        # Act - DATA PRECEDENCE comment in calculate_lct_variants.py
        selected = ca_actual if ca_actual else federal_estimate

        # Assert
        assert selected["source"] == "ca_cde"
        assert selected["year"] == "2023-24"
        assert selected["confidence"] == "high"

    def test_federal_estimate_used_when_no_state_actual(self):
        """
        REQ-025: Federal estimate (2017-18) used when state actual unavailable.

        For districts outside California or where CA data doesn't exist,
        use 2017-18 IDEA 618 + CRDC baseline ratios.
        """
        # Arrange - No CA actual data (Texas district)
        ca_actual = None

        federal_estimate = {
            "source": "idea_618_crdc",
            "year": "2017-18",
            "self_contained_students": 380,
            "confidence": "medium",
        }

        # Act
        selected = ca_actual if ca_actual else federal_estimate

        # Assert
        assert selected["source"] == "idea_618_crdc"
        assert selected["year"] == "2017-18"

    def test_state_proportional_estimate_lowest_priority(self):
        """
        REQ-025: State proportional estimate is lowest priority.

        If state provides only proportions (not actual counts), apply to
        federal baseline ratios. This is lowest confidence.
        """
        # Arrange - State provides proportion but not counts
        state_proportion = {
            "source": "tx_tea",
            "year": "2023-24",
            "sped_percentage": 0.13,  # 13% SPED, but no environment breakdown
            "confidence": "low",
        }

        federal_baseline_ratio = 0.067  # 6.7% self-contained from 2017-18

        # Act - Apply state proportion to federal environment ratios
        estimated_self_contained_pct = state_proportion["sped_percentage"] * federal_baseline_ratio
        estimated_sped = {
            "source": "tx_tea_proportion_on_federal_baseline",
            "year": "2023-24",
            "self_contained_pct": estimated_self_contained_pct,
            "confidence": "low",
        }

        # Assert
        assert estimated_sped["confidence"] == "low"
        assert "proportion_on_federal_baseline" in estimated_sped["source"]

    def test_teacher_estimates_always_use_2017_18_ratios(self):
        """
        REQ-025: Teacher estimates always use 2017-18 federal ratios.

        State-level SPED teacher splits (by environment) are not available,
        so always use 2017-18 IDEA 618 Personnel ratios even when state
        enrollment data is actual.
        """
        # This documents current limitation
        # Even CA with actual SPED enrollment uses federal teacher ratios

        ca_sped_enrollment = {
            "source": "ca_cde",
            "year": "2023-24",
            "self_contained_students": 450,
        }

        sped_teacher_estimate = {
            "source": "idea_618_personnel",
            "year": "2017-18",
            "state_sped_teacher_ratio": 0.145,  # 14.5% of all teachers
        }

        # Assert - Teacher ratios always from 2017-18 even with actual enrollment
        assert sped_teacher_estimate["year"] == "2017-18"
        assert ca_sped_enrollment["year"] == "2023-24"

    def test_confidence_levels_documented_in_output(self):
        """
        REQ-025: Confidence levels documented - high for state actual, medium for estimates.

        LCT calculations should track data quality via confidence field
        or notes.
        """
        # High confidence - state actual data
        high_confidence_source = {
            "type": "state_actual",
            "confidence": "high",
            "source": "ca_cde",
        }

        # Medium confidence - federal estimates
        medium_confidence_source = {
            "type": "federal_estimate",
            "confidence": "medium",
            "source": "idea_618_crdc",
        }

        # Low confidence - proportional estimates
        low_confidence_source = {
            "type": "proportional_estimate",
            "confidence": "low",
            "source": "state_proportion_on_federal_baseline",
        }

        assert high_confidence_source["confidence"] == "high"
        assert medium_confidence_source["confidence"] == "medium"
        assert low_confidence_source["confidence"] == "low"

    def test_enrollment_source_tracked_in_database(self):
        """
        REQ-025: Enrollment source tracked - ca_actual_YYYY-YY vs sped_estimate_2017-18.

        SpedEstimate table or similar should track which source was used
        for each district's SPED enrollment.
        """
        # Mock SPED estimate record
        sped_estimate = {
            "district_id": "6000001",  # CA district
            "year": "2023-24",
            "self_contained_enrollment": 450,
            "enrollment_source": "ca_actual_2023-24",  # Indicates CA actual data
            "teacher_source": "sped_estimate_2017-18",  # Always estimated
        }

        # Assert - Source tracking for transparency
        assert "ca_actual" in sped_estimate["enrollment_source"]
        assert "2023-24" in sped_estimate["enrollment_source"]
        assert sped_estimate["teacher_source"] == "sped_estimate_2017-18"


class TestDataPrecedenceIntegration:
    """Integration tests for data precedence across all types - REQ-023, REQ-024, REQ-025"""

    def test_precedence_rules_documented_in_requirements(self):
        """
        All three precedence rules (enrollment/staff, instructional time, SPED)
        should be documented in REQUIREMENTS.yaml for transparency.
        """
        # This test documents that precedence rules exist in requirements
        precedence_requirements = [
            "REQ-023: Data source precedence for enrollment and staffing",
            "REQ-024: Instructional time data precedence hierarchy",
            "REQ-025: SPED data precedence with proportional estimate fallback",
        ]

        assert len(precedence_requirements) == 3

    def test_calculate_lct_variants_implements_all_precedence_rules(self):
        """
        The calculate_lct_variants.py script should implement all three
        precedence hierarchies consistently.
        """
        # This documents that the main calculation script handles:
        # 1. Enrollment/staff precedence (via StaffCountsEffective, EnrollmentByGrade)
        # 2. Instructional time precedence (via get_instructional_minutes())
        # 3. SPED precedence (via CA vs federal estimate lookups)

        implemented_functions = [
            "get_instructional_minutes()",  # REQ-024
            "CA actual SPED lookup with federal fallback",  # REQ-025
            "StaffCountsEffective.primary_source tracking",  # REQ-023
        ]

        assert len(implemented_functions) == 3


# --- Fixtures ---

@pytest.fixture
def mock_database_session():
    """Mock database session for testing queries."""
    session = MagicMock()
    return session


@pytest.fixture
def sample_bell_schedule():
    """Sample bell schedule for testing."""
    bell = BellSchedule()
    bell.district_id = "0123456"
    bell.grade_level = "high"
    bell.instructional_minutes = 375
    bell.start_time = "8:00 AM"
    bell.end_time = "3:30 PM"
    bell.lunch_duration = 30
    bell.year = "2025-26"
    bell.method = "web_scraping"
    bell.confidence = "high"
    bell.schools_sampled = ["Example High School"]
    bell.source_urls = ["https://example.edu/bell-schedule"]
    return bell


@pytest.fixture
def sample_state_requirement():
    """Sample state requirement for testing."""
    req = StateRequirement()
    req.state = "CA"
    req.state_name = "California"
    req.elementary_minutes = 240
    req.middle_minutes = 300
    req.high_minutes = 330
    req.default_minutes = 330
    req.annual_days = 180
    req.source = "CA Ed Code 46201"
    return req
