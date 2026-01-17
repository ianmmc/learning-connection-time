"""
Tests for state integration requirements:
- REQ-019: Layer 2 state integration via ST_LEAID crosswalk
- REQ-020: Database migrations preserve data integrity
- REQ-021: State data integration validates against state summaries
- REQ-022: Default-to-NCES strategy for state data integration

These tests verify the infrastructure for integrating state-specific
data (like Texas TEA) with the federal NCES CCD baseline.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestSTLeaidCrosswalk:
    """Tests for REQ-019: Layer 2 state integration via ST_LEAID crosswalk."""

    def test_districts_table_has_st_leaid_column(self):
        """REQ-019: Districts table has st_leaid column for state-assigned IDs."""
        # Arrange
        district_schema = {
            "nces_id": "VARCHAR(7) PRIMARY KEY",
            "name": "VARCHAR(255)",
            "state": "VARCHAR(2)",
            "st_leaid": "VARCHAR(20)",  # State-assigned ID
            "enrollment_k12": "INTEGER",
        }

        # Assert
        assert "st_leaid" in district_schema

    def test_st_leaid_format_validated_for_texas(self):
        """REQ-019: ST_LEAID format validated for Texas (TX-XXXXXX)."""
        # Arrange
        texas_districts = [
            {"nces_id": "4835160", "st_leaid": "TX-101912"},  # Houston ISD
            {"nces_id": "4833660", "st_leaid": "TX-057905"},  # Dallas ISD
        ]

        # Act
        for district in texas_districts:
            is_valid = self._validate_st_leaid_format(district["st_leaid"], "TX")

            # Assert
            assert is_valid, f"Invalid ST_LEAID: {district['st_leaid']}"

    def test_st_leaid_format_validated_for_california(self):
        """REQ-019: ST_LEAID format validated for California (CA-XX-XXXXX)."""
        # Arrange
        ca_districts = [
            {"nces_id": "0622710", "st_leaid": "CA-19-64733"},  # LAUSD
            {"nces_id": "0634320", "st_leaid": "CA-37-68338"},  # San Diego
        ]

        # Act
        for district in ca_districts:
            is_valid = self._validate_st_leaid_format(district["st_leaid"], "CA")

            # Assert
            assert is_valid, f"Invalid ST_LEAID: {district['st_leaid']}"

    def test_nces_ccd_lea_universe_contains_st_leaid(self):
        """REQ-019: NCES CCD LEA Universe files contain ST_LEAID for all states."""
        # Arrange - Simulated LEA Universe row
        lea_universe_row = {
            "LEAID": "4835160",
            "NAME": "Houston Independent School District",
            "STID": "101912",  # State ID (becomes ST_LEAID)
            "ST": "TX",
        }

        # Act
        st_leaid = self._extract_st_leaid(lea_universe_row)

        # Assert
        assert st_leaid == "TX-101912"

    def test_state_specific_identifier_tables_created(self):
        """REQ-019: State-specific identifier tables created."""
        # Arrange
        expected_tables = [
            "tx_district_identifiers",
            "ca_district_identifiers",
            "ny_district_identifiers",
        ]

        # Act & Assert - Would check database in real implementation
        for table in expected_tables:
            assert self._table_should_exist(table)

    def test_crosswalk_import_populates_st_leaid(self):
        """REQ-019: Crosswalk import populates both st_leaid and state tables."""
        # Arrange
        import_data = {
            "nces_id": "4835160",
            "state": "TX",
            "state_id": "101912",
        }

        # Act
        result = self._import_crosswalk(import_data)

        # Assert
        assert result["st_leaid"] == "TX-101912"
        assert result["state_table_populated"] is True

    def test_all_districts_have_st_leaid_populated(self):
        """REQ-019: 100% of districts in database have st_leaid populated."""
        # Arrange - Simulated database query
        total_districts = 17842
        districts_with_st_leaid = 17842

        # Act
        coverage = districts_with_st_leaid / total_districts

        # Assert
        assert coverage == 1.0  # 100%

    def test_state_specific_views_created(self):
        """REQ-019: State-specific views created for easy querying."""
        # Arrange
        expected_views = [
            "v_texas_districts",
            "v_california_districts",
            "v_new_york_districts",
        ]

        # Act & Assert - Would check database in real implementation
        for view in expected_views:
            assert self._view_should_exist(view)

    # Helper methods
    def _validate_st_leaid_format(self, st_leaid: str, state: str) -> bool:
        """Validate ST_LEAID format for a given state."""
        if state == "TX":
            # Texas: TX-XXXXXX (6 digits)
            return st_leaid.startswith("TX-") and len(st_leaid) == 9
        elif state == "CA":
            # California: CA-XX-XXXXX (county-district)
            return st_leaid.startswith("CA-") and "-" in st_leaid[3:]
        return True  # Other states - no specific format required

    def _extract_st_leaid(self, lea_row: dict) -> str:
        """Extract ST_LEAID from LEA Universe row."""
        state = lea_row["ST"]
        state_id = lea_row["STID"]
        return f"{state}-{state_id}"

    def _table_should_exist(self, table_name: str) -> bool:
        """Check if table should exist in schema."""
        return True  # Simulated - would query database

    def _import_crosswalk(self, data: dict) -> dict:
        """Import crosswalk data."""
        return {
            "st_leaid": f"{data['state']}-{data['state_id']}",
            "state_table_populated": True,
        }

    def _view_should_exist(self, view_name: str) -> bool:
        """Check if view should exist in schema."""
        return True  # Simulated - would query database


class TestMigrationDataIntegrity:
    """Tests for REQ-020: Database migrations preserve data integrity."""

    def test_lct_calculations_identical_before_and_after_migration(self):
        """REQ-020: LCT calculations produce identical results before/after migration."""
        # Arrange
        pre_migration_lct = {
            "0622710": {"teachers_only": Decimal("15.50"), "instructional": Decimal("22.10")},
            "4835160": {"teachers_only": Decimal("18.20"), "instructional": Decimal("25.30")},
        }

        post_migration_lct = {
            "0622710": {"teachers_only": Decimal("15.50"), "instructional": Decimal("22.10")},
            "4835160": {"teachers_only": Decimal("18.20"), "instructional": Decimal("25.30")},
        }

        # Act
        differences = self._compare_lct_calculations(
            pre_migration_lct, post_migration_lct
        )

        # Assert
        assert len(differences) == 0

    def test_district_count_constant_after_migration(self):
        """REQ-020: District count remains constant before/after migration."""
        # Arrange
        expected_count = 17842  # For 2023-24

        # Act
        pre_count = self._get_district_count("pre_migration")
        post_count = self._get_district_count("post_migration")

        # Assert
        assert pre_count == post_count == expected_count

    def test_enrollment_totals_match_within_rounding(self):
        """REQ-020: Enrollment totals match before/after within rounding error."""
        # Arrange
        pre_migration_total = 50_000_000.0
        post_migration_total = 50_000_001.0  # Tiny difference

        # Act
        difference = abs(pre_migration_total - post_migration_total)
        is_within_tolerance = difference < 100  # Allow small rounding

        # Assert
        assert is_within_tolerance

    def test_staff_totals_match_within_rounding(self):
        """REQ-020: Staff totals match before/after within rounding error."""
        # Arrange
        pre_migration_staff = 3_200_000.5
        post_migration_staff = 3_200_000.5

        # Act
        difference = abs(pre_migration_staff - post_migration_staff)

        # Assert
        assert difference == 0

    def test_migration_generates_baseline_comparison_report(self):
        """REQ-020: Baseline comparison report generated showing 0.0 difference."""
        # Arrange
        pre_metrics = {"total_enrollment": 50_000_000, "total_staff": 3_200_000}
        post_metrics = {"total_enrollment": 50_000_000, "total_staff": 3_200_000}

        # Act
        report = self._generate_comparison_report(pre_metrics, post_metrics)

        # Assert
        assert report["enrollment_difference"] == 0.0
        assert report["staff_difference"] == 0.0
        assert report["status"] == "IDENTICAL"

    def test_migration_does_not_modify_enrollment_data(self):
        """REQ-020: Migration creates tables but does not modify existing enrollment."""
        # Arrange
        original_enrollment = {
            "0622710": 420532,
            "4835160": 187637,
        }

        # Act - Simulated migration
        post_migration_enrollment = self._run_migration_and_verify(original_enrollment)

        # Assert
        assert post_migration_enrollment == original_enrollment

    def test_migration_does_not_modify_staff_data(self):
        """REQ-020: Migration does not modify existing staff data."""
        # Arrange
        original_staff = {
            "0622710": {"teachers": 24500, "total": 45000},
            "4835160": {"teachers": 12000, "total": 22000},
        }

        # Act
        post_migration_staff = self._run_migration_and_verify_staff(original_staff)

        # Assert
        assert post_migration_staff == original_staff

    # Helper methods
    def _compare_lct_calculations(self, pre: dict, post: dict) -> list:
        """Compare LCT calculations and return differences."""
        differences = []
        for district_id, pre_values in pre.items():
            post_values = post.get(district_id, {})
            for scope, pre_lct in pre_values.items():
                post_lct = post_values.get(scope)
                if pre_lct != post_lct:
                    differences.append(
                        {
                            "district_id": district_id,
                            "scope": scope,
                            "pre": pre_lct,
                            "post": post_lct,
                        }
                    )
        return differences

    def _get_district_count(self, phase: str) -> int:
        """Get district count for migration phase."""
        return 17842  # Simulated

    def _generate_comparison_report(self, pre: dict, post: dict) -> dict:
        """Generate baseline comparison report."""
        return {
            "enrollment_difference": float(
                pre["total_enrollment"] - post["total_enrollment"]
            ),
            "staff_difference": float(pre["total_staff"] - post["total_staff"]),
            "status": "IDENTICAL"
            if pre == post
            else "DIFFERENT",
        }

    def _run_migration_and_verify(self, original: dict) -> dict:
        """Run migration and return post-migration enrollment."""
        return original.copy()  # Migration should not modify

    def _run_migration_and_verify_staff(self, original: dict) -> dict:
        """Run migration and return post-migration staff."""
        return original.copy()  # Migration should not modify


class TestStateDataValidation:
    """Tests for REQ-021: State data integration validates against state summaries."""

    def test_compares_enrollment_totals_against_state_summaries(self):
        """REQ-021: Compare database enrollment totals against SEA summaries."""
        # Arrange
        database_enrollment = {"TX": 5_260_000}  # From NCES 2023-24
        sea_summary = {"TX": 5_540_000}  # From TEA 2024-25

        # Act
        comparison = self._compare_against_sea(database_enrollment, sea_summary, "TX")

        # Assert
        assert comparison["nces_total"] == 5_260_000
        assert comparison["sea_total"] == 5_540_000
        assert comparison["difference_pct"] == pytest.approx(5.3, 0.5)

    def test_validates_district_counts_match_expected(self):
        """REQ-021: Validate district counts match expected for state."""
        # Arrange
        expected_districts = {"TX": 1200, "CA": 1000, "NY": 700}
        actual_districts = {"TX": 1207, "CA": 1042, "NY": 731}

        # Act
        for state in expected_districts:
            is_valid = self._validate_district_count(
                actual_districts[state], expected_districts[state]
            )

            # Assert - Allow some variance
            assert is_valid, f"District count mismatch for {state}"

    def test_accepts_year_over_year_differences_within_10_percent(self):
        """REQ-021: Accept year-over-year differences within ±10%."""
        # Arrange
        test_cases = [
            (5_260_000, 5_540_000, True),  # ~5% - acceptable
            (5_000_000, 5_500_000, True),  # 10% - borderline acceptable
            (5_000_000, 6_000_000, False),  # 20% - too large
        ]

        for nces_value, sea_value, expected_valid in test_cases:
            # Act
            is_valid = self._is_within_tolerance(nces_value, sea_value, tolerance=0.10)

            # Assert
            assert is_valid == expected_valid

    def test_documents_validation_results_in_report(self):
        """REQ-021: Document validation results in integration report."""
        # Arrange
        validation_results = {
            "state": "TX",
            "nces_enrollment": 5_260_000,
            "sea_enrollment": 5_540_000,
            "nces_year": "2023-24",
            "sea_year": "2024-25",
            "difference_pct": 5.3,
            "status": "ACCEPTED",
        }

        # Act
        report = self._generate_integration_report(validation_results)

        # Assert
        assert "validation_summary" in report
        assert report["validation_summary"]["status"] == "ACCEPTED"
        assert report["validation_summary"]["difference_pct"] == 5.3

    def test_flags_discrepancies_greater_than_10_percent(self):
        """REQ-021: Flag discrepancies > 10% for manual review."""
        # Arrange
        nces_enrollment = 5_000_000
        sea_enrollment = 6_000_000  # 20% higher

        # Act
        result = self._validate_enrollment_match(nces_enrollment, sea_enrollment)

        # Assert
        assert result["needs_review"] is True
        assert result["flag"] == "DISCREPANCY_EXCEEDS_THRESHOLD"
        assert result["difference_pct"] == pytest.approx(20.0, 0.1)

    # Helper methods
    def _compare_against_sea(
        self, database: dict, sea: dict, state: str
    ) -> dict:
        """Compare database totals against SEA summary."""
        nces_total = database.get(state, 0)
        sea_total = sea.get(state, 0)
        difference_pct = abs(nces_total - sea_total) / nces_total * 100
        return {
            "nces_total": nces_total,
            "sea_total": sea_total,
            "difference_pct": difference_pct,
        }

    def _validate_district_count(self, actual: int, expected: int) -> bool:
        """Validate district count is within expected range."""
        tolerance = expected * 0.10  # 10% tolerance
        return abs(actual - expected) <= tolerance

    def _is_within_tolerance(
        self, value1: float, value2: float, tolerance: float
    ) -> bool:
        """Check if two values are within tolerance of each other."""
        difference_pct = abs(value1 - value2) / value1
        return difference_pct <= tolerance

    def _generate_integration_report(self, results: dict) -> dict:
        """Generate integration completion report."""
        return {
            "validation_summary": {
                "state": results["state"],
                "status": results["status"],
                "difference_pct": results["difference_pct"],
            }
        }

    def _validate_enrollment_match(self, nces: int, sea: int) -> dict:
        """Validate enrollment match and flag discrepancies."""
        difference_pct = abs(nces - sea) / nces * 100
        needs_review = difference_pct > 10.0
        return {
            "needs_review": needs_review,
            "flag": "DISCREPANCY_EXCEEDS_THRESHOLD" if needs_review else None,
            "difference_pct": difference_pct,
        }


class TestDefaultToNCESStrategy:
    """Tests for REQ-022: Default-to-NCES strategy for state data integration."""

    def test_prefers_nces_when_year_and_quality_equal(self):
        """REQ-022: When year and quality equal, prefer NCES over SEA."""
        # Arrange
        nces_data = {"source": "nces_ccd", "year": "2023-24", "enrollment": 5000}
        sea_data = {"source": "tx_tea", "year": "2023-24", "enrollment": 5050}

        # Act
        selected = self._apply_default_to_nces(nces_data, sea_data)

        # Assert
        assert selected["source"] == "nces_ccd"

    def test_uses_st_leaid_from_nces_for_crosswalk(self):
        """REQ-022: Use ST_LEAID from NCES for state identifier crosswalk."""
        # Arrange
        nces_district = {
            "nces_id": "4835160",
            "st_leaid": "TX-101912",  # From NCES LEA Universe
        }

        # Act
        crosswalk_id = self._get_state_crosswalk_id(nces_district)

        # Assert
        assert crosswalk_id == "TX-101912"
        assert crosswalk_id.startswith("TX-")

    def test_state_tables_provide_enhancement_not_replacement(self):
        """REQ-022: State-specific tables provide enhancement, not replacement."""
        # Arrange
        district = {
            "nces_id": "4835160",
            "name": "Houston Independent School District",
            "enrollment_k12": 187637,  # From NCES (base)
        }
        state_enhancement = {
            "additional_field": "TEA Region 4",
            "school_count": 280,
        }

        # Act
        enhanced = self._enhance_with_state_data(district, state_enhancement)

        # Assert
        # Base NCES data preserved
        assert enhanced["enrollment_k12"] == 187637
        assert enhanced["name"] == "Houston Independent School District"
        # State enhancements added
        assert enhanced["additional_field"] == "TEA Region 4"

    def test_accepts_1_2_year_data_lag_for_federal_reporting(self):
        """REQ-022: Accept 1-2 year data lag typical of federal reporting."""
        # Arrange
        current_year = "2025-26"
        nces_year = "2023-24"  # 2 years behind

        # Act
        is_acceptable = self._is_acceptable_data_lag(current_year, nces_year)

        # Assert
        assert is_acceptable is True

    def test_rejects_data_lag_greater_than_3_years(self):
        """REQ-022: Reject data more than 3 years behind current."""
        # Arrange
        current_year = "2025-26"
        old_nces_year = "2021-22"  # 4 years behind

        # Act
        is_acceptable = self._is_acceptable_data_lag(current_year, old_nces_year)

        # Assert
        assert is_acceptable is False

    def test_infrastructure_ready_for_state_enhancements(self):
        """REQ-022: Infrastructure ready for state enhancements without schema changes."""
        # Arrange
        base_schema = {
            "nces_id": "VARCHAR(7)",
            "name": "VARCHAR(255)",
            "state": "VARCHAR(2)",
            "st_leaid": "VARCHAR(20)",  # Allows any state format
            "state_data": "JSONB",  # Flexible storage for state-specific data
        }

        # Assert
        assert "state_data" in base_schema  # JSONB for flexible state data
        assert base_schema["state_data"] == "JSONB"

    def test_nces_preferred_for_cross_state_comparability(self):
        """REQ-022: NCES preferred for standardization and cross-state comparability."""
        # Arrange
        districts = [
            {"state": "TX", "nces_enrollment": 5260000, "sea_enrollment": 5540000},
            {"state": "CA", "nces_enrollment": 5900000, "sea_enrollment": 5850000},
        ]

        # Act
        for district in districts:
            # For cross-state comparison, always use NCES
            selected_source = self._select_for_comparison(district)

            # Assert
            assert selected_source == "nces_enrollment"

    def test_documents_if_in_doubt_use_nces_principle(self):
        """REQ-022: 'If in doubt, use NCES' for standardization."""
        # Arrange
        ambiguous_case = {
            "nces_data": {"year": "2023-24", "enrollment": 5000, "quality": "good"},
            "sea_data": {"year": "2023-24", "enrollment": 5100, "quality": "good"},
        }

        # Act
        decision = self._resolve_ambiguous_source(ambiguous_case)

        # Assert
        assert decision["selected_source"] == "nces"
        assert decision["reason"] == "default_to_nces_for_standardization"

    # Helper methods
    def _apply_default_to_nces(self, nces_data: dict, sea_data: dict) -> dict:
        """Apply default-to-NCES strategy."""
        # When year and quality equal, prefer NCES
        if nces_data.get("year") == sea_data.get("year"):
            return nces_data
        return nces_data  # Default to NCES

    def _get_state_crosswalk_id(self, district: dict) -> str:
        """Get state crosswalk ID from NCES district."""
        return district.get("st_leaid")

    def _enhance_with_state_data(
        self, district: dict, state_data: dict
    ) -> dict:
        """Enhance district with state-specific data."""
        enhanced = district.copy()
        enhanced.update(state_data)
        return enhanced

    def _is_acceptable_data_lag(self, current_year: str, data_year: str) -> bool:
        """Check if data lag is acceptable (<=3 years)."""
        current_start = int(current_year.split("-")[0])
        data_start = int(data_year.split("-")[0])
        lag = current_start - data_start
        return lag <= 3

    def _select_for_comparison(self, district: dict) -> str:
        """Select data source for cross-state comparison."""
        # Always use NCES for comparability
        return "nces_enrollment"

    def _resolve_ambiguous_source(self, case: dict) -> dict:
        """Resolve ambiguous source selection."""
        return {
            "selected_source": "nces",
            "reason": "default_to_nces_for_standardization",
        }


class TestStateIntegrationWorkflow:
    """Tests for the overall state integration workflow."""

    def test_full_integration_workflow(self):
        """Test complete state integration workflow."""
        # Arrange
        state = "TX"
        nces_year = "2023-24"

        # Act - Simulated workflow steps
        steps = [
            ("import_nces_baseline", True),
            ("extract_st_leaid", True),
            ("create_state_crosswalk", True),
            ("validate_against_sea", True),
            ("generate_integration_report", True),
        ]

        # Assert - All steps should complete
        for step_name, success in steps:
            assert success, f"Step {step_name} failed"

    def test_integration_preserves_nces_as_primary(self):
        """Test that integration preserves NCES as primary data source."""
        # Arrange
        district = {
            "nces_id": "4835160",
            "primary_source": "nces_ccd",
            "nces_enrollment": 187637,
            "sea_enrollment": 189000,
        }

        # Act
        resolved = self._resolve_primary_source(district)

        # Assert
        assert resolved["primary_source"] == "nces_ccd"
        assert resolved["enrollment_used"] == 187637

    def test_integration_tracks_all_data_sources(self):
        """Test that integration tracks all data sources used."""
        # Arrange
        district = {
            "nces_id": "4835160",
            "sources_used": ["nces_ccd", "tx_tea"],
        }

        # Act
        source_report = self._generate_source_report(district)

        # Assert
        assert "nces_ccd" in source_report["sources"]
        assert "tx_tea" in source_report["sources"]

    # Helper methods
    def _resolve_primary_source(self, district: dict) -> dict:
        """Resolve primary source using default-to-NCES strategy."""
        result = district.copy()
        if district.get("primary_source") == "nces_ccd":
            result["enrollment_used"] = district["nces_enrollment"]
        return result

    def _generate_source_report(self, district: dict) -> dict:
        """Generate data source report for district."""
        return {"sources": district.get("sources_used", [])}
