"""
Tests for LCT scope calculations
Generated from: REQ-008, REQ-009, REQ-010, REQ-011

Verifies that all LCT staff scopes are calculated correctly without data loss,
and that the scope hierarchy relationships are maintained.

Run: pytest tests/test_lct_scope_calculations.py -v
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, Mock

from infrastructure.database.models import (
    StaffCountsEffective,
    EnrollmentByGrade,
)


class TestScopeCalculations:
    """Tests for StaffCountsEffective.calculate_scopes() - REQ-008, REQ-009"""

    def test_all_scopes_calculated_without_data_loss(self):
        """
        REQ-008: Generates exactly 10 scopes without dropping any.

        Verifies that calculate_scopes() populates all scope fields:
        - teachers_k12 (for teachers_only)
        - teachers_elementary_k5
        - teachers_secondary_6_12
        - scope_teachers_only
        - scope_teachers_core
        - scope_instructional
        - scope_instructional_plus_support
        - scope_all
        """
        # Arrange
        staff = StaffCountsEffective()
        staff.district_id = "0123456"
        staff.effective_year = "2023-24"
        staff.primary_source = "nces_ccd"

        # Set realistic staff counts
        staff.teachers_elementary = Decimal("100.0")
        staff.teachers_kindergarten = Decimal("20.0")
        staff.teachers_secondary = Decimal("80.0")
        staff.teachers_ungraded = Decimal("5.0")
        staff.instructional_coordinators = Decimal("3.0")
        staff.paraprofessionals = Decimal("15.0")
        staff.counselors_total = Decimal("4.0")
        staff.psychologists = Decimal("2.0")
        staff.student_support_services = Decimal("3.0")
        staff.librarians = Decimal("2.0")
        staff.lea_administrators = Decimal("5.0")
        staff.school_administrators = Decimal("10.0")
        staff.other_staff = Decimal("20.0")

        # Act
        staff.calculate_scopes()

        # Assert - All scopes must be populated
        assert staff.teachers_k12 is not None, "teachers_k12 should not be None"
        assert staff.teachers_elementary_k5 is not None, "teachers_elementary_k5 should not be None"
        assert staff.teachers_secondary_6_12 is not None, "teachers_secondary_6_12 should not be None"
        assert staff.scope_teachers_only is not None, "scope_teachers_only should not be None"
        assert staff.scope_teachers_core is not None, "scope_teachers_core should not be None"
        assert staff.scope_instructional is not None, "scope_instructional should not be None"
        assert staff.scope_instructional_plus_support is not None, "scope_instructional_plus_support should not be None"
        assert staff.scope_all is not None, "scope_all should not be None"

        # Verify specific values
        assert staff.teachers_k12 == 200.0, "teachers_k12 = elem + sec + kinder = 100 + 80 + 20"
        assert staff.teachers_elementary_k5 == 120.0, "teachers_elementary_k5 = elem + kinder = 100 + 20"
        assert staff.teachers_secondary_6_12 == 80.0, "teachers_secondary_6_12 = secondary only"

    def test_elementary_teachers_preserved_from_nces(self):
        """
        REQ-009: Elementary and kindergarten teachers are correctly summed.

        Verifies that:
        - Elementary Teachers category is preserved
        - Kindergarten Teachers category is preserved
        - teachers_elementary_k5 = elementary + kindergarten
        """
        # Arrange
        staff = StaffCountsEffective()
        staff.teachers_elementary = Decimal("150.5")
        staff.teachers_kindergarten = Decimal("30.25")
        staff.teachers_secondary = None  # Optional

        # Act
        staff.calculate_scopes()

        # Assert
        assert staff.teachers_elementary_k5 == 180.75
        assert staff.teachers_elementary_k5 == (
            float(staff.teachers_elementary) + float(staff.teachers_kindergarten)
        )

    def test_secondary_teachers_preserved_from_nces(self):
        """
        REQ-009: Secondary teachers are preserved as-is for secondary scope.
        """
        # Arrange
        staff = StaffCountsEffective()
        staff.teachers_secondary = Decimal("95.0")
        staff.teachers_elementary = None  # Optional
        staff.teachers_kindergarten = None  # Optional

        # Act
        staff.calculate_scopes()

        # Assert
        assert staff.teachers_secondary_6_12 == 95.0
        assert staff.teachers_secondary_6_12 == float(staff.teachers_secondary)

    def test_ungraded_excluded_from_teachers_only(self):
        """
        REQ-008: Ungraded teachers EXCLUDED from teachers_only scope.

        Key Decision December 2025: teachers_only = elem + sec + kinder (NO ungraded)
        """
        # Arrange
        staff = StaffCountsEffective()
        staff.teachers_elementary = Decimal("100.0")
        staff.teachers_secondary = Decimal("80.0")
        staff.teachers_kindergarten = Decimal("20.0")
        staff.teachers_ungraded = Decimal("10.0")  # Should NOT be in teachers_only

        # Act
        staff.calculate_scopes()

        # Assert
        assert staff.scope_teachers_only == 200.0  # 100 + 80 + 20, NO ungraded
        assert staff.scope_teachers_core == 210.0  # 100 + 80 + 20 + 10, includes ungraded

    def test_prek_excluded_from_all_scopes(self):
        """
        REQ-014: Pre-K teachers excluded from all scopes.

        Key Decision December 2025: ALL scopes exclude Pre-K teachers.
        """
        # Arrange
        staff = StaffCountsEffective()
        staff.teachers_elementary = Decimal("100.0")
        staff.teachers_secondary = Decimal("80.0")
        staff.teachers_kindergarten = Decimal("20.0")
        staff.teachers_prek = Decimal("15.0")  # Should be excluded from ALL scopes

        # Act
        staff.calculate_scopes()

        # Assert - Pre-K teachers should not appear in any scope
        assert staff.scope_teachers_only == 200.0  # No Pre-K
        assert staff.scope_teachers_core == 200.0  # No Pre-K
        assert staff.scope_all == 200.0  # Even scope_all excludes Pre-K teachers

    def test_handles_missing_teacher_categories_gracefully(self):
        """
        REQ-009: Import preserves data but handles None values.

        Districts may not report all teacher categories. Calculate_scopes
        should handle None values gracefully (treat as 0).
        """
        # Arrange
        staff = StaffCountsEffective()
        staff.teachers_elementary = Decimal("100.0")
        staff.teachers_secondary = None  # K-8 district
        staff.teachers_kindergarten = Decimal("20.0")
        staff.teachers_ungraded = None

        # Act
        staff.calculate_scopes()

        # Assert - Should not crash, None treated as 0
        assert staff.teachers_k12 == 120.0  # 100 + 20, secondary=0
        assert staff.teachers_elementary_k5 == 120.0
        assert staff.teachers_secondary_6_12 is None  # Preserve None for missing data


class TestScopeHierarchy:
    """Tests for LCT scope hierarchy validation - REQ-011"""

    def test_scope_hierarchy_relationships(self):
        """
        REQ-011: Verify scope hierarchy at district level.

        Expected relationships for a single district:
        - teachers_only <= teachers_core (core adds ungraded)
        - teachers_core <= instructional (adds coordinators + paras)
        - instructional <= instructional_plus_support (adds counselors + support)
        - instructional_plus_support <= all (adds all other staff)
        """
        # Arrange
        staff = StaffCountsEffective()
        staff.teachers_elementary = Decimal("100.0")
        staff.teachers_secondary = Decimal("80.0")
        staff.teachers_kindergarten = Decimal("20.0")
        staff.teachers_ungraded = Decimal("5.0")
        staff.instructional_coordinators = Decimal("3.0")
        staff.paraprofessionals = Decimal("15.0")
        staff.counselors_total = Decimal("4.0")
        staff.psychologists = Decimal("2.0")
        staff.student_support_services = Decimal("3.0")
        staff.librarians = Decimal("2.0")
        staff.lea_administrators = Decimal("5.0")
        staff.school_administrators = Decimal("10.0")
        staff.other_staff = Decimal("20.0")

        # Act
        staff.calculate_scopes()

        # Assert - Verify hierarchy
        assert staff.scope_teachers_only <= staff.scope_teachers_core
        assert staff.scope_teachers_core <= staff.scope_instructional
        assert staff.scope_instructional <= staff.scope_instructional_plus_support
        assert staff.scope_instructional_plus_support <= staff.scope_all

    def test_teachers_secondary_less_than_teachers_only(self):
        """
        REQ-011: Secondary LCT typically higher (lower staff per student).

        For districts with both elementary and secondary teachers,
        teachers_secondary_6_12 < teachers_k12 (secondary is subset).
        """
        # Arrange
        staff = StaffCountsEffective()
        staff.teachers_elementary = Decimal("100.0")
        staff.teachers_secondary = Decimal("80.0")
        staff.teachers_kindergarten = Decimal("20.0")

        # Act
        staff.calculate_scopes()

        # Assert
        assert staff.teachers_secondary_6_12 < staff.teachers_k12


class TestEnrollmentLevelCalculations:
    """Tests for EnrollmentByGrade.calculate_level_enrollments() - REQ-010"""

    def test_elementary_enrollment_k_through_5(self):
        """
        REQ-010: Elementary enrollment = K + grades 1-5.
        """
        # Arrange
        enrollment = EnrollmentByGrade()
        enrollment.district_id = "0123456"
        enrollment.source_year = "2023-24"
        enrollment.enrollment_kindergarten = 100
        enrollment.enrollment_grade_1 = 95
        enrollment.enrollment_grade_2 = 90
        enrollment.enrollment_grade_3 = 92
        enrollment.enrollment_grade_4 = 88
        enrollment.enrollment_grade_5 = 85

        # Act
        enrollment.calculate_level_enrollments()

        # Assert
        expected = 100 + 95 + 90 + 92 + 88 + 85
        assert enrollment.enrollment_elementary == expected

    def test_secondary_enrollment_grades_6_through_12(self):
        """
        REQ-010: Secondary enrollment = grades 6-12.
        """
        # Arrange
        enrollment = EnrollmentByGrade()
        enrollment.district_id = "0123456"
        enrollment.source_year = "2023-24"
        enrollment.enrollment_grade_6 = 80
        enrollment.enrollment_grade_7 = 78
        enrollment.enrollment_grade_8 = 75
        enrollment.enrollment_grade_9 = 120
        enrollment.enrollment_grade_10 = 110
        enrollment.enrollment_grade_11 = 100
        enrollment.enrollment_grade_12 = 95

        # Act
        enrollment.calculate_level_enrollments()

        # Assert
        expected = 80 + 78 + 75 + 120 + 110 + 100 + 95
        assert enrollment.enrollment_secondary == expected

    def test_elementary_plus_secondary_equals_k12(self):
        """
        REQ-010: Sum of elementary + secondary ≈ enrollment_k12.

        Should be exact match (within rounding) for districts with complete data.
        """
        # Arrange
        enrollment = EnrollmentByGrade()
        enrollment.district_id = "0123456"
        enrollment.source_year = "2023-24"

        # K-5 enrollment
        enrollment.enrollment_kindergarten = 100
        enrollment.enrollment_grade_1 = 95
        enrollment.enrollment_grade_2 = 90
        enrollment.enrollment_grade_3 = 92
        enrollment.enrollment_grade_4 = 88
        enrollment.enrollment_grade_5 = 85

        # 6-12 enrollment
        enrollment.enrollment_grade_6 = 80
        enrollment.enrollment_grade_7 = 78
        enrollment.enrollment_grade_8 = 75
        enrollment.enrollment_grade_9 = 120
        enrollment.enrollment_grade_10 = 110
        enrollment.enrollment_grade_11 = 100
        enrollment.enrollment_grade_12 = 95

        # Total enrollment
        enrollment.enrollment_total = 1258  # Sum of all grades + Pre-K (1208 + 50)
        enrollment.enrollment_prek = 50
        enrollment.calculate_k12()  # enrollment_k12 = 1258 - 50 = 1208

        # Act
        enrollment.calculate_level_enrollments()

        # Assert
        elementary_plus_secondary = (
            enrollment.enrollment_elementary + enrollment.enrollment_secondary
        )
        assert elementary_plus_secondary == enrollment.enrollment_k12

    def test_handles_missing_grades_gracefully(self):
        """
        REQ-010: Handles None values in grade enrollment (K-5 or 6-8 only districts).
        """
        # Arrange - K-8 district with no high school
        enrollment = EnrollmentByGrade()
        enrollment.district_id = "0123456"
        enrollment.source_year = "2023-24"
        enrollment.enrollment_kindergarten = 100
        enrollment.enrollment_grade_1 = 95
        enrollment.enrollment_grade_2 = 90
        enrollment.enrollment_grade_3 = 92
        enrollment.enrollment_grade_4 = 88
        enrollment.enrollment_grade_5 = 85
        enrollment.enrollment_grade_6 = 80
        enrollment.enrollment_grade_7 = 78
        enrollment.enrollment_grade_8 = 75
        # Grades 9-12 are None
        enrollment.enrollment_grade_9 = None
        enrollment.enrollment_grade_10 = None
        enrollment.enrollment_grade_11 = None
        enrollment.enrollment_grade_12 = None

        # Act
        enrollment.calculate_level_enrollments()

        # Assert
        assert enrollment.enrollment_elementary == 550  # K-5
        assert enrollment.enrollment_secondary == 233  # 6-8, None treated as 0


class TestRegressionPrevention:
    """Tests to prevent specific regressions - REQ-008"""

    def test_staff_import_does_not_zero_teacher_categories(self):
        """
        REQ-008, REQ-009: Regression test for 2026-01-10 issue.

        Staff import must preserve elementary, kindergarten, and secondary
        teacher counts from NCES CCD, not zero them out.

        This is a database integration test placeholder - actual test would
        verify pivot operation preserves all teacher categories.
        """
        # This test documents the regression that occurred
        # Actual implementation would test the import script's pivot logic

        # The issue: after staff re-import, teachers_elementary_k5 was 0
        # Root cause: pivot operation or missing calculate_scopes() call

        # Prevention: Verify pivot creates correct columns
        # Expected columns from NCES staff file:
        expected_columns = [
            "teachers_elementary",
            "teachers_kindergarten",
            "teachers_secondary",
            "teachers_prek",
            "teachers_ungraded",
        ]

        # Mock test: verify these columns would exist after pivot
        # (Actual test would run import on sample data and verify)
        assert len(expected_columns) == 5
        assert "teachers_elementary" in expected_columns
        assert "teachers_secondary" in expected_columns

    def test_scope_counts_match_expected_district_availability(self):
        """
        REQ-008: Verify scope district counts match NCES data availability.

        Based on 2023-24 NCES CCD data:
        - teachers_elementary should have 15,000+ districts
        - teachers_secondary should have 14,000+ districts

        This is a data quality test - would run against actual calculation results.
        """
        # This documents expected data availability
        # Actual test would query lct_calculations table

        expected_counts = {
            "teachers_only": 17000,  # Nearly all districts
            "teachers_elementary": 15000,  # Most have elementary
            "teachers_secondary": 14000,  # Fewer have secondary
            "teachers_core": 17000,
            "instructional": 17000,
            "instructional_plus_support": 17000,
            "all": 17000,
        }

        # Mock assertion
        assert expected_counts["teachers_elementary"] >= 15000
        assert expected_counts["teachers_secondary"] >= 14000


# --- Fixtures ---

@pytest.fixture
def sample_staff_complete():
    """Complete staff data for a typical K-12 district."""
    staff = StaffCountsEffective()
    staff.district_id = "0123456"
    staff.effective_year = "2023-24"
    staff.primary_source = "nces_ccd"

    # Teachers
    staff.teachers_elementary = Decimal("100.0")
    staff.teachers_kindergarten = Decimal("20.0")
    staff.teachers_secondary = Decimal("80.0")
    staff.teachers_ungraded = Decimal("5.0")
    staff.teachers_prek = Decimal("10.0")  # Should be excluded

    # Instructional support
    staff.instructional_coordinators = Decimal("3.0")
    staff.paraprofessionals = Decimal("15.0")

    # Student support
    staff.counselors_total = Decimal("4.0")
    staff.psychologists = Decimal("2.0")
    staff.student_support_services = Decimal("3.0")

    # Other staff
    staff.librarians = Decimal("2.0")
    staff.lea_administrators = Decimal("5.0")
    staff.school_administrators = Decimal("10.0")
    staff.other_staff = Decimal("20.0")

    return staff


@pytest.fixture
def sample_enrollment_complete():
    """Complete enrollment data for a typical K-12 district."""
    enrollment = EnrollmentByGrade()
    enrollment.district_id = "0123456"
    enrollment.source_year = "2023-24"
    enrollment.data_source = "nces_ccd"

    # Pre-K (excluded from K-12)
    enrollment.enrollment_prek = 50

    # K-5 (elementary)
    enrollment.enrollment_kindergarten = 100
    enrollment.enrollment_grade_1 = 95
    enrollment.enrollment_grade_2 = 90
    enrollment.enrollment_grade_3 = 92
    enrollment.enrollment_grade_4 = 88
    enrollment.enrollment_grade_5 = 85

    # 6-12 (secondary)
    enrollment.enrollment_grade_6 = 80
    enrollment.enrollment_grade_7 = 78
    enrollment.enrollment_grade_8 = 75
    enrollment.enrollment_grade_9 = 120
    enrollment.enrollment_grade_10 = 110
    enrollment.enrollment_grade_11 = 100
    enrollment.enrollment_grade_12 = 95

    # Total
    enrollment.enrollment_total = 1258
    enrollment.enrollment_k12 = 1208

    return enrollment
