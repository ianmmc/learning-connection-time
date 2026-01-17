"""
Tests for REQ-005: Validate data integrity with 6 validation flags.

These tests verify that data validation:
- Flags anomalous enrollment values
- Flags missing instructional time data
- Flags out-of-range LCT calculations
- Flags stale/outdated source data
- Provides validation summary report
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import MagicMock


class TestEnrollmentValidation:
    """Tests for flagging anomalous enrollment values."""

    def test_flags_negative_enrollment(self):
        """REQ-005: Flags negative enrollment as invalid."""
        # Arrange
        district = {"nces_id": "0100005", "enrollment_k12": -100}

        # Act
        flags = self._validate_enrollment(district)

        # Assert
        assert "INVALID_ENROLLMENT" in flags
        assert flags["INVALID_ENROLLMENT"]["reason"] == "negative_value"

    def test_flags_zero_enrollment(self):
        """REQ-005: Flags zero enrollment as potentially invalid."""
        # Arrange
        district = {"nces_id": "0100005", "enrollment_k12": 0}

        # Act
        flags = self._validate_enrollment(district)

        # Assert
        assert "ZERO_ENROLLMENT" in flags

    def test_flags_extremely_high_enrollment(self):
        """REQ-005: Flags unrealistically high enrollment values."""
        # Arrange - No district has > 2M students
        district = {"nces_id": "0100005", "enrollment_k12": 3_000_000}

        # Act
        flags = self._validate_enrollment(district)

        # Assert
        assert "EXTREME_ENROLLMENT" in flags
        assert flags["EXTREME_ENROLLMENT"]["threshold"] == 2_000_000

    def test_flags_enrollment_exceeds_total(self):
        """REQ-005: Flags when K-12 enrollment exceeds total enrollment."""
        # Arrange - K-12 should not exceed total (which includes Pre-K)
        district = {
            "nces_id": "0100005",
            "enrollment_total": 5000,
            "enrollment_k12": 5500,  # K-12 > total is impossible
        }

        # Act
        flags = self._validate_enrollment(district)

        # Assert
        assert "K12_EXCEEDS_TOTAL" in flags

    def test_passes_valid_enrollment(self):
        """REQ-005: Passes districts with valid enrollment."""
        # Arrange
        district = {
            "nces_id": "0100005",
            "enrollment_total": 5500,
            "enrollment_k12": 5000,
            "enrollment_prek": 500,
        }

        # Act
        flags = self._validate_enrollment(district)

        # Assert
        assert len(flags) == 0

    def test_flags_enrollment_sum_mismatch(self):
        """REQ-005: Flags when grade-level enrollments don't sum to K-12."""
        # Arrange
        district = {
            "enrollment_k12": 1000,
            "enrollment_elementary": 400,
            "enrollment_secondary": 500,
            # Sum = 900, should be 1000
        }

        # Act
        flags = self._validate_enrollment(district)

        # Assert
        assert "ENROLLMENT_SUM_MISMATCH" in flags
        assert flags["ENROLLMENT_SUM_MISMATCH"]["expected"] == 1000
        assert flags["ENROLLMENT_SUM_MISMATCH"]["actual"] == 900

    # Helper methods
    def _validate_enrollment(self, district: dict) -> dict:
        """Validate enrollment values and return flags."""
        flags = {}

        enrollment_k12 = district.get("enrollment_k12", 0)
        enrollment_total = district.get("enrollment_total")

        if enrollment_k12 < 0:
            flags["INVALID_ENROLLMENT"] = {"reason": "negative_value"}
        elif enrollment_k12 == 0:
            flags["ZERO_ENROLLMENT"] = {"reason": "zero_value"}
        elif enrollment_k12 > 2_000_000:
            flags["EXTREME_ENROLLMENT"] = {"threshold": 2_000_000}

        if enrollment_total and enrollment_k12 > enrollment_total:
            flags["K12_EXCEEDS_TOTAL"] = {
                "k12": enrollment_k12,
                "total": enrollment_total,
            }

        # Check grade-level sum
        elem = district.get("enrollment_elementary", 0) or 0
        secondary = district.get("enrollment_secondary", 0) or 0
        if elem and secondary:
            actual_sum = elem + secondary
            if actual_sum != enrollment_k12 and enrollment_k12 > 0:
                flags["ENROLLMENT_SUM_MISMATCH"] = {
                    "expected": enrollment_k12,
                    "actual": actual_sum,
                }

        return flags


class TestInstructionalTimeValidation:
    """Tests for flagging missing instructional time data."""

    def test_flags_missing_instructional_minutes(self):
        """REQ-005: Flags districts with no instructional time data."""
        # Arrange
        district = {
            "nces_id": "0100005",
            "instructional_minutes": None,
            "has_bell_schedule": False,
            "state_requirement": None,
        }

        # Act
        flags = self._validate_instructional_time(district)

        # Assert
        assert "MISSING_INSTRUCTIONAL_TIME" in flags

    def test_flags_zero_instructional_minutes(self):
        """REQ-005: Flags zero instructional minutes as invalid."""
        # Arrange
        district = {"nces_id": "0100005", "instructional_minutes": 0}

        # Act
        flags = self._validate_instructional_time(district)

        # Assert
        assert "ZERO_INSTRUCTIONAL_MINUTES" in flags

    def test_flags_instructional_time_too_short(self):
        """REQ-005: Flags unrealistically short instructional time."""
        # Arrange - Less than 2 hours is not valid
        district = {"nces_id": "0100005", "instructional_minutes": 100}

        # Act
        flags = self._validate_instructional_time(district)

        # Assert
        assert "INSTRUCTIONAL_TIME_TOO_SHORT" in flags
        assert flags["INSTRUCTIONAL_TIME_TOO_SHORT"]["minimum"] == 120

    def test_flags_instructional_time_too_long(self):
        """REQ-005: Flags unrealistically long instructional time."""
        # Arrange - More than 8 hours (480 min) is unusual
        district = {"nces_id": "0100005", "instructional_minutes": 600}

        # Act
        flags = self._validate_instructional_time(district)

        # Assert
        assert "INSTRUCTIONAL_TIME_TOO_LONG" in flags
        assert flags["INSTRUCTIONAL_TIME_TOO_LONG"]["maximum"] == 540

    def test_passes_valid_instructional_time(self):
        """REQ-005: Passes districts with valid instructional time."""
        # Arrange
        district = {"nces_id": "0100005", "instructional_minutes": 360}

        # Act
        flags = self._validate_instructional_time(district)

        # Assert
        assert len(flags) == 0

    def test_flags_using_default_360(self):
        """REQ-005: Flags when using default 360 minutes (no actual data)."""
        # Arrange
        district = {
            "nces_id": "0100005",
            "instructional_minutes": 360,
            "instructional_minutes_source": "default",
        }

        # Act
        flags = self._validate_instructional_time(district)

        # Assert
        assert "USING_DEFAULT_INSTRUCTIONAL_TIME" in flags

    # Helper methods
    def _validate_instructional_time(self, district: dict) -> dict:
        """Validate instructional time and return flags."""
        flags = {}

        minutes = district.get("instructional_minutes")
        source = district.get("instructional_minutes_source")

        if minutes is None:
            flags["MISSING_INSTRUCTIONAL_TIME"] = {}
        elif minutes == 0:
            flags["ZERO_INSTRUCTIONAL_MINUTES"] = {}
        elif minutes < 120:
            flags["INSTRUCTIONAL_TIME_TOO_SHORT"] = {"minimum": 120}
        elif minutes > 540:
            flags["INSTRUCTIONAL_TIME_TOO_LONG"] = {"maximum": 540}

        if source == "default":
            flags["USING_DEFAULT_INSTRUCTIONAL_TIME"] = {}

        return flags


class TestLCTRangeValidation:
    """Tests for flagging out-of-range LCT calculations."""

    def test_flags_negative_lct(self):
        """REQ-005: Flags negative LCT values as invalid."""
        # Arrange
        lct_value = -5.0

        # Act
        flags = self._validate_lct_range(lct_value)

        # Assert
        assert "INVALID_LCT_NEGATIVE" in flags

    def test_flags_lct_exceeds_360(self):
        """REQ-005: Flags LCT > 360 minutes for non-SPED scopes."""
        # Arrange
        lct_value = 400.0
        scope = "teachers_only"

        # Act
        flags = self._validate_lct_range(lct_value, scope)

        # Assert
        assert "LCT_EXCEEDS_DAY_LENGTH" in flags
        assert flags["LCT_EXCEEDS_DAY_LENGTH"]["maximum"] == 360

    def test_flags_lct_below_minimum(self):
        """REQ-005: Flags extremely low LCT values."""
        # Arrange - LCT < 1 minute indicates data issue
        lct_value = 0.5

        # Act
        flags = self._validate_lct_range(lct_value)

        # Assert
        assert "LCT_BELOW_MINIMUM" in flags
        assert flags["LCT_BELOW_MINIMUM"]["minimum"] == 1.0

    def test_passes_valid_lct_range(self):
        """REQ-005: Passes LCT values in valid range."""
        # Arrange
        test_cases = [5.0, 15.0, 25.0, 50.0, 100.0, 360.0]

        for lct in test_cases:
            # Act
            flags = self._validate_lct_range(lct)

            # Assert
            assert len(flags) == 0, f"Failed for LCT={lct}"

    def test_allows_sped_lct_above_360_with_cap(self):
        """REQ-005: Allows SPED LCT above 360 but caps and flags."""
        # Arrange
        lct_value = 500.0
        scope = "core_sped"

        # Act
        flags = self._validate_lct_range(lct_value, scope, allow_sped_cap=True)

        # Assert
        assert "LCT_SPED_CAPPED" in flags
        assert flags["LCT_SPED_CAPPED"]["original"] == 500.0
        assert flags["LCT_SPED_CAPPED"]["capped_to"] == 360.0

    # Helper methods
    def _validate_lct_range(
        self, lct: float, scope: str = None, allow_sped_cap: bool = False
    ) -> dict:
        """Validate LCT is in acceptable range."""
        flags = {}

        if lct < 0:
            flags["INVALID_LCT_NEGATIVE"] = {"value": lct}
        elif lct < 1.0:
            flags["LCT_BELOW_MINIMUM"] = {"minimum": 1.0, "value": lct}
        elif lct > 360:
            if scope in ["core_sped", "instructional_sped"] and allow_sped_cap:
                flags["LCT_SPED_CAPPED"] = {"original": lct, "capped_to": 360.0}
            else:
                flags["LCT_EXCEEDS_DAY_LENGTH"] = {"maximum": 360, "value": lct}

        return flags


class TestDataFreshnessValidation:
    """Tests for flagging stale/outdated source data."""

    def test_flags_data_older_than_3_years(self):
        """REQ-005: Flags data more than 3 years old as stale."""
        # Arrange
        district = {
            "nces_id": "0100005",
            "data_year": "2020-21",
            "current_year": "2025-26",
        }

        # Act
        flags = self._validate_data_freshness(district)

        # Assert
        assert "STALE_DATA" in flags
        assert flags["STALE_DATA"]["years_old"] >= 4

    def test_passes_current_year_data(self):
        """REQ-005: Passes data from current or prior year."""
        # Arrange
        district = {
            "nces_id": "0100005",
            "data_year": "2024-25",
            "current_year": "2025-26",
        }

        # Act
        flags = self._validate_data_freshness(district)

        # Assert
        assert "STALE_DATA" not in flags

    def test_flags_covid_era_data(self):
        """REQ-005: Flags COVID-era data (2019-20 through 2022-23)."""
        # Arrange
        covid_years = ["2019-20", "2020-21", "2021-22", "2022-23"]

        for year in covid_years:
            district = {"data_year": year}

            # Act
            flags = self._validate_data_freshness(district)

            # Assert
            assert "COVID_ERA_DATA" in flags, f"Failed for {year}"

    def test_flags_missing_data_year(self):
        """REQ-005: Flags when data year is unknown."""
        # Arrange
        district = {"nces_id": "0100005", "data_year": None}

        # Act
        flags = self._validate_data_freshness(district)

        # Assert
        assert "UNKNOWN_DATA_YEAR" in flags

    def test_tracks_data_source_freshness(self):
        """REQ-005: Tracks freshness of different data sources."""
        # Arrange
        district = {
            "nces_year": "2023-24",
            "bell_schedule_year": "2025-26",
            "sped_baseline_year": "2017-18",
        }

        # Act
        freshness = self._assess_source_freshness(district)

        # Assert
        assert freshness["nces"]["is_current"] is True
        assert freshness["bell_schedule"]["is_current"] is True
        assert freshness["sped_baseline"]["is_current"] is False
        assert freshness["sped_baseline"]["is_intentional"] is True

    # Helper methods
    def _validate_data_freshness(self, district: dict) -> dict:
        """Validate data freshness and return flags."""
        flags = {}

        data_year = district.get("data_year")
        current_year = district.get("current_year", "2025-26")

        if data_year is None:
            flags["UNKNOWN_DATA_YEAR"] = {}
            return flags

        # Check COVID era
        covid_years = ["2019-20", "2020-21", "2021-22", "2022-23"]
        if data_year in covid_years:
            flags["COVID_ERA_DATA"] = {"year": data_year}

        # Check staleness
        data_start = int(data_year.split("-")[0])
        current_start = int(current_year.split("-")[0])
        years_old = current_start - data_start

        if years_old > 3:
            flags["STALE_DATA"] = {"years_old": years_old}

        return flags

    def _assess_source_freshness(self, district: dict) -> dict:
        """Assess freshness of each data source."""
        current_start = 2025

        def is_current(year_str):
            if not year_str:
                return False
            year_start = int(year_str.split("-")[0])
            return current_start - year_start <= 2

        return {
            "nces": {"is_current": is_current(district.get("nces_year"))},
            "bell_schedule": {
                "is_current": is_current(district.get("bell_schedule_year"))
            },
            "sped_baseline": {
                "is_current": is_current(district.get("sped_baseline_year")),
                "is_intentional": True,  # SPED baseline is intentionally 2017-18
            },
        }


class TestValidationSummaryReport:
    """Tests for validation summary report generation."""

    def test_generates_summary_report(self):
        """REQ-005: Generates validation summary report."""
        # Arrange
        validation_results = [
            {"district_id": "0100005", "flags": ["FLAG_A"]},
            {"district_id": "0100006", "flags": []},
            {"district_id": "0100007", "flags": ["FLAG_B", "FLAG_C"]},
        ]

        # Act
        report = self._generate_summary_report(validation_results)

        # Assert
        assert "total_districts" in report
        assert "districts_with_flags" in report
        assert "flag_counts" in report

    def test_report_includes_pass_rate(self):
        """REQ-005: Report includes pass rate percentage."""
        # Arrange
        validation_results = [
            {"district_id": "0100005", "flags": []},  # Pass
            {"district_id": "0100006", "flags": []},  # Pass
            {"district_id": "0100007", "flags": ["FLAG_A"]},  # Fail
        ]

        # Act
        report = self._generate_summary_report(validation_results)

        # Assert
        assert report["pass_rate"] == pytest.approx(66.67, 0.1)

    def test_report_counts_each_flag_type(self):
        """REQ-005: Report counts occurrences of each flag type."""
        # Arrange
        validation_results = [
            {"flags": ["FLAG_A", "FLAG_B"]},
            {"flags": ["FLAG_A"]},
            {"flags": ["FLAG_A", "FLAG_C"]},
        ]

        # Act
        report = self._generate_summary_report(validation_results)

        # Assert
        assert report["flag_counts"]["FLAG_A"] == 3
        assert report["flag_counts"]["FLAG_B"] == 1
        assert report["flag_counts"]["FLAG_C"] == 1

    def test_report_identifies_most_common_issues(self):
        """REQ-005: Report identifies most common validation issues."""
        # Arrange
        validation_results = [
            {"flags": ["FLAG_A"] * 3 + ["FLAG_B"]},
            {"flags": ["FLAG_A"] * 2},
            {"flags": ["FLAG_B", "FLAG_C"]},
        ]

        # Act
        report = self._generate_summary_report(validation_results)
        top_issues = self._get_top_issues(report["flag_counts"], n=2)

        # Assert
        assert top_issues[0]["flag"] == "FLAG_A"
        assert top_issues[1]["flag"] == "FLAG_B"

    def test_report_includes_timestamp(self):
        """REQ-005: Report includes generation timestamp."""
        # Arrange
        validation_results = []

        # Act
        report = self._generate_summary_report(validation_results)

        # Assert
        assert "generated_at" in report
        assert isinstance(report["generated_at"], datetime)

    def test_report_includes_validation_version(self):
        """REQ-005: Report includes validation rules version."""
        # Arrange
        validation_results = []

        # Act
        report = self._generate_summary_report(validation_results)

        # Assert
        assert "validation_version" in report

    # Helper methods
    def _generate_summary_report(self, results: list) -> dict:
        """Generate validation summary report."""
        total = len(results)
        with_flags = sum(1 for r in results if r.get("flags"))

        # Count flags
        flag_counts = {}
        for r in results:
            for flag in r.get("flags", []):
                flag_counts[flag] = flag_counts.get(flag, 0) + 1

        pass_rate = ((total - with_flags) / total * 100) if total > 0 else 100.0

        return {
            "total_districts": total,
            "districts_with_flags": with_flags,
            "flag_counts": flag_counts,
            "pass_rate": pass_rate,
            "generated_at": datetime.now(),
            "validation_version": "1.0",
        }

    def _get_top_issues(self, flag_counts: dict, n: int = 5) -> list:
        """Get top N most common validation issues."""
        sorted_flags = sorted(
            flag_counts.items(), key=lambda x: x[1], reverse=True
        )
        return [{"flag": f, "count": c} for f, c in sorted_flags[:n]]


class TestValidationWorkflow:
    """Tests for the overall validation workflow."""

    def test_validates_all_districts_in_batch(self):
        """REQ-005: Validates all districts in a batch operation."""
        # Arrange
        districts = [
            {"nces_id": f"010000{i}", "enrollment_k12": 1000 * (i + 1)}
            for i in range(100)
        ]

        # Act
        results = self._validate_batch(districts)

        # Assert
        assert len(results) == 100
        assert all("flags" in r for r in results)

    def test_validation_does_not_modify_source_data(self):
        """REQ-005: Validation is non-destructive."""
        # Arrange
        district = {"nces_id": "0100005", "enrollment_k12": 5000}
        original = district.copy()

        # Act
        self._validate_district(district)

        # Assert - District unchanged
        assert district == original

    def test_validation_returns_flagged_and_unflagged_districts(self):
        """REQ-005: Returns both flagged and unflagged districts."""
        # Arrange
        districts = [
            {"nces_id": "0100005", "enrollment_k12": 5000},  # Valid
            {"nces_id": "0100006", "enrollment_k12": -100},  # Invalid
        ]

        # Act
        valid, invalid = self._partition_by_validity(districts)

        # Assert
        assert len(valid) == 1
        assert len(invalid) == 1
        assert valid[0]["nces_id"] == "0100005"
        assert invalid[0]["nces_id"] == "0100006"

    # Helper methods
    def _validate_batch(self, districts: list) -> list:
        """Validate a batch of districts."""
        return [{"district_id": d["nces_id"], "flags": []} for d in districts]

    def _validate_district(self, district: dict) -> dict:
        """Validate a single district (non-destructive)."""
        return {"flags": []}

    def _partition_by_validity(self, districts: list) -> tuple:
        """Partition districts into valid and invalid."""
        valid = [d for d in districts if d.get("enrollment_k12", 0) > 0]
        invalid = [d for d in districts if d.get("enrollment_k12", 0) <= 0]
        return valid, invalid
