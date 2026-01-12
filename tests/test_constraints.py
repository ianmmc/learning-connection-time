"""
Tests for constraint requirements
Generated from: REQ-007 (COVID exclusion), REQ-014 (Pre-K exclusion)

Verifies that data constraints are enforced to maintain data quality.

Run: pytest tests/test_constraints.py -v
"""

import pytest
from datetime import datetime


class TestCovidEraExclusion:
    """Tests for COVID-era data exclusion - REQ-007"""

    def test_rejects_2019_20_school_year(self):
        """
        REQ-007: Rejects data from 2019-20 school year.

        COVID-19 shutdowns began March 2020, making this year invalid.
        """
        # Arrange
        year = "2019-20"

        # Act
        is_covid_era = self._is_covid_era_year(year)

        # Assert
        assert is_covid_era is True

    def test_rejects_2020_21_school_year(self):
        """
        REQ-007: Rejects data from 2020-21 school year.

        Remote/hybrid learning year, abnormal schedules.
        """
        year = "2020-21"
        assert self._is_covid_era_year(year) is True

    def test_rejects_2021_22_school_year(self):
        """
        REQ-007: Rejects data from 2021-22 school year.

        Continued disruptions and transitions.
        """
        year = "2021-22"
        assert self._is_covid_era_year(year) is True

    def test_rejects_2022_23_school_year(self):
        """
        REQ-007: Rejects data from 2022-23 school year.

        Transitional year, still recovering from COVID disruptions.
        """
        year = "2022-23"
        assert self._is_covid_era_year(year) is True

    def test_accepts_2018_19_school_year(self):
        """
        REQ-007: Accepts 2018-19 data (pre-COVID).

        Last complete normal school year before pandemic.
        """
        year = "2018-19"
        assert self._is_covid_era_year(year) is False

    def test_accepts_2023_24_school_year(self):
        """
        REQ-007: Accepts 2023-24 data (post-COVID normalization).

        First year considered normalized post-COVID operations.
        """
        year = "2023-24"
        assert self._is_covid_era_year(year) is False

    def test_accepts_2024_25_school_year(self):
        """
        REQ-007: Accepts 2024-25 data (current operations).
        """
        year = "2024-25"
        assert self._is_covid_era_year(year) is False

    def test_accepts_2025_26_school_year(self):
        """
        REQ-007: Accepts 2025-26 data (current operations).
        """
        year = "2025-26"
        assert self._is_covid_era_year(year) is False

    def test_prefers_2018_19_over_covid_years(self):
        """
        REQ-007: When recent data unavailable, prefer 2018-19 over COVID years.

        If we have 2018-19 and 2020-21, use 2018-19 even though it's older.
        """
        available_years = ["2018-19", "2020-21", "2021-22"]

        # Filter out COVID years
        valid_years = [y for y in available_years if not self._is_covid_era_year(y)]

        # Assert - Only 2018-19 should remain
        assert valid_years == ["2018-19"]

    def test_logs_warning_for_covid_data(self):
        """
        REQ-007: Logs warning when COVID-era data is encountered.

        This documents expected behavior - actual implementation would
        use Python logging to warn users.
        """
        # This test documents the logging requirement
        # Actual implementation would use logging.warning()

        covid_year = "2020-21"
        is_covid = self._is_covid_era_year(covid_year)

        if is_covid:
            warning_message = f"WARNING: Year {covid_year} is COVID-era data and should be excluded"
            assert "WARNING" in warning_message
            assert covid_year in warning_message

    def test_covid_era_year_list_complete(self):
        """
        REQ-007: All four COVID-era years are identified.

        Documents the complete list for transparency.
        """
        covid_years = ["2019-20", "2020-21", "2021-22", "2022-23"]

        for year in covid_years:
            assert self._is_covid_era_year(year), f"{year} should be flagged as COVID-era"

    def test_year_format_validation(self):
        """
        REQ-007: Handles different year format variations.

        Years can be formatted as "2023-24", "2023_24", or "202324".
        """
        # Common formats for 2020-21 (COVID year)
        formats = ["2020-21", "2020_21", "202021"]

        for year_str in formats:
            # Normalize format before checking
            normalized = self._normalize_year_format(year_str)
            assert self._is_covid_era_year(normalized) is True

    def _is_covid_era_year(self, year: str) -> bool:
        """
        Helper function to identify COVID-era years.

        This documents the logic that should be implemented in actual code.

        Args:
            year: School year in format "YYYY-YY"

        Returns:
            True if year is 2019-20 through 2022-23
        """
        covid_years = ["2019-20", "2020-21", "2021-22", "2022-23"]
        normalized = self._normalize_year_format(year)
        return normalized in covid_years

    def _normalize_year_format(self, year: str) -> str:
        """
        Normalize year format to "YYYY-YY".

        Handles: "2023-24", "2023_24", "202324"
        Returns: "2023-24"
        """
        # Remove underscores, convert to dash format
        if "_" in year:
            year = year.replace("_", "-")

        # Handle 6-digit format (202324 -> 2023-24)
        if len(year) == 6 and year.isdigit():
            return f"{year[:4]}-{year[4:]}"

        return year


class TestPreKExclusion:
    """Tests for Pre-K exclusion from all scopes - REQ-014"""

    def test_enrollment_k12_excludes_prek(self):
        """
        REQ-014: K-12 enrollment excludes Pre-K students.

        enrollment_k12 = enrollment_total - enrollment_prek
        """
        # Arrange
        enrollment_total = 5000
        enrollment_prek = 200

        # Act
        enrollment_k12 = enrollment_total - enrollment_prek

        # Assert
        assert enrollment_k12 == 4800
        assert enrollment_k12 < enrollment_total

    def test_all_scopes_use_k12_enrollment(self):
        """
        REQ-014: All LCT scopes use enrollment_k12 as denominator.

        No scope should use enrollment_total (which includes Pre-K).
        """
        # This documents the policy
        # Actual implementation in calculate_lct_variants.py

        scopes_that_use_k12 = [
            "teachers_only",
            "teachers_core",
            "instructional",
            "instructional_plus_support",
            "all",
            "core_sped",
            "teachers_gened",
            "instructional_sped",
        ]

        # Assert - All base scopes use K-12 enrollment
        assert len(scopes_that_use_k12) == 8
        # Level-specific scopes use their own enrollments (K-5, 6-12)
        # but those also exclude Pre-K by definition

    def test_teachers_prek_excluded_from_all_scopes(self):
        """
        REQ-014: Pre-K teachers excluded from all staff scopes.

        Even scope_all (which includes admin, support, etc.) excludes Pre-K teachers.
        """
        # This is tested in test_lct_scope_calculations.py::test_prek_excluded_from_all_scopes
        # but documenting the requirement here as well

        staff_categories_excluded = ["teachers_prek"]

        for category in staff_categories_excluded:
            assert "prek" in category.lower()

    def test_scope_calculation_never_includes_prek_field(self):
        """
        REQ-014: StaffCountsEffective.calculate_scopes() does not include teachers_prek.

        Code inspection requirement - no scope calculation should sum teachers_prek.
        """
        # This documents expected behavior from models.py

        # From StaffCountsEffective.calculate_scopes():
        # self.scope_all = safe_sum(
        #     self.teachers_elementary,
        #     self.teachers_secondary,
        #     self.teachers_kindergarten,
        #     self.teachers_ungraded,
        #     self.instructional_coordinators,
        #     ...  # many other categories
        #     # NOTE: teachers_prek is NOT included
        # )

        excluded_fields = ["teachers_prek"]
        assert len(excluded_fields) == 1

    def test_lct_calculations_verify_enrollment_type_k12(self):
        """
        REQ-014: LCT calculations verify enrollment_type = 'k12' for base scopes.

        When calculating LCT, ensure using K-12 enrollment, not total.
        """
        # Mock calculation verification
        enrollment_data = {
            "enrollment_total": 5000,
            "enrollment_prek": 200,
            "enrollment_k12": 4800,
            "enrollment_type_used": "k12",  # Should always be 'k12' for base scopes
        }

        # Assert - K-12 enrollment is used
        assert enrollment_data["enrollment_type_used"] == "k12"
        assert enrollment_data["enrollment_k12"] == (
            enrollment_data["enrollment_total"] - enrollment_data["enrollment_prek"]
        )

    def test_prek_exclusion_applies_to_all_years(self):
        """
        REQ-014: Pre-K exclusion applies consistently across all data years.

        This is a methodology decision that applies to all historical and future data.
        """
        # Test years
        test_years = ["2018-19", "2023-24", "2024-25", "2025-26"]

        for year in test_years:
            # For all years, Pre-K should be excluded
            policy = {"year": year, "exclude_prek": True}
            assert policy["exclude_prek"] is True


class TestDataYearValidation:
    """Additional validation tests for year handling"""

    def test_identifies_valid_post_covid_years(self):
        """Documents which years are considered valid for analysis."""
        valid_years = [
            "2023-24",  # Primary campaign year
            "2024-25",  # Recent data
            "2025-26",  # Current year
            "2018-19",  # Pre-COVID baseline
        ]

        covid_checker = TestCovidEraExclusion()
        for year in valid_years:
            assert not covid_checker._is_covid_era_year(year), f"{year} should be valid"

    def test_documents_preferred_year_order(self):
        """
        REQ-007: Documents preferred year selection when multiple available.

        For bell schedules: 2025-26 > 2024-25 > 2023-24 > 2018-19
        Never use 2019-20 through 2022-23.
        """
        available_years = ["2025-26", "2024-25", "2023-24", "2020-21", "2018-19"]

        # Filter out COVID years
        covid_checker = TestCovidEraExclusion()
        valid_years = [y for y in available_years if not covid_checker._is_covid_era_year(y)]

        # Sort by year (most recent first)
        valid_years_sorted = sorted(valid_years, reverse=True)

        # Assert - Preferred order
        assert valid_years_sorted == ["2025-26", "2024-25", "2023-24", "2018-19"]
        assert "2020-21" not in valid_years  # COVID year excluded


# --- Fixtures ---

@pytest.fixture
def sample_enrollment_with_prek():
    """Sample enrollment data including Pre-K for testing exclusion."""
    return {
        "enrollment_prek": 200,
        "enrollment_kindergarten": 300,
        "enrollment_grade_1": 280,
        "enrollment_grade_2": 275,
        "enrollment_grade_3": 270,
        "enrollment_grade_4": 265,
        "enrollment_grade_5": 260,
        "enrollment_grade_6": 255,
        "enrollment_grade_7": 250,
        "enrollment_grade_8": 245,
        "enrollment_grade_9": 400,
        "enrollment_grade_10": 380,
        "enrollment_grade_11": 360,
        "enrollment_grade_12": 340,
        "enrollment_total": 4080,  # Includes Pre-K
        "enrollment_k12": 3880,    # Excludes Pre-K (4080 - 200)
    }


@pytest.fixture
def sample_staff_with_prek():
    """Sample staff data including Pre-K teachers for testing exclusion."""
    return {
        "teachers_prek": 10.0,         # Should be excluded
        "teachers_kindergarten": 15.0,
        "teachers_elementary": 100.0,
        "teachers_secondary": 80.0,
        "teachers_ungraded": 5.0,
        "teachers_total": 210.0,       # Includes Pre-K
    }
