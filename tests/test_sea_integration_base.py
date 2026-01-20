"""
Base class for State Education Agency (SEA) integration tests.

This module provides abstract base classes and common test patterns for
validating state-specific education data against NCES baselines.

All state-specific integration tests should inherit from SEAIntegrationTestBase
and provide state-specific expected values and data paths.

Test Categories:
    1. Data Loading - SEA files exist and load correctly
    2. District Crosswalk - State IDs map to NCES LEAIDs
    3. Staff Validation - Teacher counts within tolerance of expected
    4. Enrollment Validation - Student counts within tolerance of expected
    5. LCT Calculations - Learning Connection Time calculations are accurate
    6. Data Integrity - Cross-file consistency checks
    7. Data Quality - Suppressed value handling, SPED district flagging
    8. Regression Prevention - Guard against known failure modes
"""

import pytest
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd


class SEAIntegrationTestBase(ABC):
    """
    Abstract base class for SEA integration tests.

    Subclasses must implement:
        - STATE_CODE: Two-letter state code (e.g., 'FL', 'TX', 'CA')
        - STATE_NAME: Full state name
        - SEA_NAME: State Education Agency name (e.g., 'FLDOE', 'TEA', 'CDE')
        - EXPECTED_DISTRICTS: Dict of expected values for key districts
        - CROSSWALK: Dict mapping NCES LEAID to state district ID
        - get_data_files(): Returns dict of data file paths
    """

    # Must be set by subclasses
    STATE_CODE: str = None
    STATE_NAME: str = None
    SEA_NAME: str = None
    DATA_YEAR: str = None

    # Expected values - must be populated by subclasses
    EXPECTED_DISTRICTS: Dict[str, Dict[str, Any]] = {}
    CROSSWALK: Dict[str, str] = {}  # NCES LEAID -> State ID

    # Tolerances for validation
    ENROLLMENT_TOLERANCE_PCT: float = 0.05  # 5%
    STAFF_TOLERANCE_PCT: float = 0.05  # 5%
    LCT_TOLERANCE_PCT: float = 0.02  # 2%

    # State default instructional minutes (override in subclass if different)
    DEFAULT_INSTRUCTIONAL_MINUTES: int = 360

    # Optional: Expected columns in loaded data (override in subclass for validation)
    # If set, test_staff_data_loads_successfully will verify these columns exist
    EXPECTED_STAFF_COLUMNS: List[str] = None
    # If set, test_enrollment_data_loads_successfully will verify these columns exist
    EXPECTED_ENROLLMENT_COLUMNS: List[str] = None

    @abstractmethod
    def get_data_files(self) -> Dict[str, Path]:
        """
        Return paths to SEA data files.

        Returns:
            Dict with keys like 'staff', 'enrollment', 'calendar'
            and Path values to the actual files.
        """
        pass

    @abstractmethod
    def load_staff_data(self) -> pd.DataFrame:
        """Load and return staff data from SEA files."""
        pass

    @abstractmethod
    def load_enrollment_data(self) -> pd.DataFrame:
        """Load and return enrollment data from SEA files."""
        pass

    def get_district_expected(self, district_name: str) -> Dict[str, Any]:
        """Get expected values for a named district."""
        return self.EXPECTED_DISTRICTS.get(district_name, {})

    def get_nces_leaid(self, district_name: str) -> Optional[str]:
        """Get NCES LEAID for a named district."""
        expected = self.get_district_expected(district_name)
        return expected.get('nces_leaid')

    def get_state_district_id(self, district_name: str) -> Optional[str]:
        """Get state district ID for a named district."""
        expected = self.get_district_expected(district_name)
        return expected.get('state_district_id')


class SEADataLoadingTests:
    """Mixin class for data loading tests."""

    def test_data_directory_exists(self):
        """SEA data directory exists."""
        files = self.get_data_files()
        assert len(files) > 0, f"No data files configured for {self.SEA_NAME}"

    def test_staff_file_exists(self):
        """Staff data file exists."""
        files = self.get_data_files()
        if 'staff' in files:
            assert files['staff'].exists(), f"Staff file not found: {files['staff']}"

    def test_enrollment_file_exists(self):
        """Enrollment data file exists."""
        files = self.get_data_files()
        if 'enrollment' in files:
            assert files['enrollment'].exists(), f"Enrollment file not found: {files['enrollment']}"

    def test_staff_data_loads_successfully(self):
        """Staff data loads without errors and has valid structure.

        Tests the actual contract: can we get staff data from load_staff_data()?
        This validates the data loading mechanism regardless of file organization
        (separate files, combined files, different key names, etc.).
        """
        try:
            df = self.load_staff_data()
        except NotImplementedError:
            pytest.skip("load_staff_data() not implemented for this state")
        except FileNotFoundError as e:
            pytest.fail(f"Staff data file not found: {e}")

        assert df is not None, "load_staff_data() returned None"
        assert len(df) > 0, "Staff data is empty"

        # Optional: verify expected columns if defined by subclass
        expected_cols = getattr(self, 'EXPECTED_STAFF_COLUMNS', None)
        if expected_cols:
            for col in expected_cols:
                assert col in df.columns, \
                    f"Missing expected staff column: {col}. Available: {list(df.columns)}"

    def test_enrollment_data_loads_successfully(self):
        """Enrollment data loads without errors and has valid structure.

        Tests the actual contract: can we get enrollment data from load_enrollment_data()?
        This validates the data loading mechanism regardless of file organization
        (separate files, combined files, different key names, etc.).
        """
        try:
            df = self.load_enrollment_data()
        except NotImplementedError:
            pytest.skip("load_enrollment_data() not implemented for this state")
        except FileNotFoundError as e:
            pytest.fail(f"Enrollment data file not found: {e}")

        assert df is not None, "load_enrollment_data() returned None"
        assert len(df) > 0, "Enrollment data is empty"

        # Optional: verify expected columns if defined by subclass
        expected_cols = getattr(self, 'EXPECTED_ENROLLMENT_COLUMNS', None)
        if expected_cols:
            for col in expected_cols:
                assert col in df.columns, \
                    f"Missing expected enrollment column: {col}. Available: {list(df.columns)}"


class SEACrosswalkTests:
    """Mixin class for district crosswalk tests."""

    def test_crosswalk_has_entries(self):
        """Crosswalk contains at least one mapping."""
        assert len(self.CROSSWALK) > 0, "Crosswalk is empty"

    def test_nces_leaids_are_valid_format(self):
        """NCES LEAIDs are 7-digit strings."""
        for nces_id in self.CROSSWALK.keys():
            assert len(str(nces_id)) == 7, f"Invalid NCES LEAID format: {nces_id}"

    def test_state_ids_are_valid_format(self):
        """State district IDs match expected format for state."""
        # Override in subclass for state-specific format validation
        pass

    def test_all_expected_districts_have_crosswalk(self):
        """All expected districts have crosswalk entries."""
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            if 'nces_leaid' in expected:
                nces_id = expected['nces_leaid']
                assert nces_id in self.CROSSWALK, \
                    f"Missing crosswalk for {district_name} (NCES: {nces_id})"


class SEAStaffValidationTests:
    """Mixin class for staff data validation tests."""

    def test_total_teachers_matches_expected(self):
        """Total teachers match expected values within tolerance.

        Validates that teacher counts from load_staff_data() match expected values.
        Requires subclass to implement _get_district_teachers() to extract
        teacher counts from the state-specific data format.
        """
        # Check if any expected districts have teacher counts to validate
        has_teacher_expectations = any(
            'total_teachers' in exp for exp in self.EXPECTED_DISTRICTS.values()
        )
        if not has_teacher_expectations:
            pytest.skip("No expected teacher counts defined")

        # Try to load staff data
        try:
            df = self.load_staff_data()
        except NotImplementedError:
            pytest.skip("load_staff_data() not implemented for this state")
        except FileNotFoundError as e:
            pytest.fail(f"Staff data file not found: {e}")

        if df is None or len(df) == 0:
            pytest.skip("Staff data is empty")

        validated_count = 0
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            if 'total_teachers' not in expected:
                continue

            expected_val = expected['total_teachers']
            # Skip districts with None or missing expected values
            if expected_val is None:
                continue

            state_id = expected.get('state_district_id')
            if state_id is None:
                continue

            # Subclasses should implement district filtering
            actual = self._get_district_teachers(df, state_id)
            if actual is None:
                continue

            tolerance = expected_val * self.STAFF_TOLERANCE_PCT

            assert abs(actual - expected_val) <= tolerance, \
                f"{district_name}: Teachers {actual} differs from expected {expected_val} by more than {self.STAFF_TOLERANCE_PCT*100}%"
            validated_count += 1

        if validated_count == 0:
            pytest.skip("_get_district_teachers() not implemented or returned None for all districts")

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Override in subclass to get teacher count for district.

        Args:
            df: DataFrame from load_staff_data()
            state_id: State-specific district identifier

        Returns:
            Teacher count as float, or None if district not found
        """
        return None


class SEAEnrollmentValidationTests:
    """Mixin class for enrollment validation tests."""

    def test_enrollment_matches_expected(self):
        """Enrollment matches expected values within tolerance.

        Validates that enrollment counts from load_enrollment_data() match expected values.
        Requires subclass to implement _get_district_enrollment() to extract
        enrollment counts from the state-specific data format.
        """
        # Check if any expected districts have enrollment to validate
        has_enrollment_expectations = any(
            'enrollment' in exp for exp in self.EXPECTED_DISTRICTS.values()
        )
        if not has_enrollment_expectations:
            pytest.skip("No expected enrollment counts defined")

        # Try to load enrollment data
        try:
            df = self.load_enrollment_data()
        except NotImplementedError:
            pytest.skip("load_enrollment_data() not implemented for this state")
        except FileNotFoundError as e:
            pytest.fail(f"Enrollment data file not found: {e}")

        if df is None or len(df) == 0:
            pytest.skip("Enrollment data is empty")

        validated_count = 0
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            if 'enrollment' not in expected:
                continue

            expected_val = expected['enrollment']
            # Skip districts with None or missing expected values
            if expected_val is None:
                continue

            state_id = expected.get('state_district_id')
            if state_id is None:
                continue

            actual = self._get_district_enrollment(df, state_id)
            if actual is None:
                continue

            tolerance = expected_val * self.ENROLLMENT_TOLERANCE_PCT

            assert abs(actual - expected_val) <= tolerance, \
                f"{district_name}: Enrollment {actual} differs from expected {expected_val} by more than {self.ENROLLMENT_TOLERANCE_PCT*100}%"
            validated_count += 1

        if validated_count == 0:
            pytest.skip("_get_district_enrollment() not implemented or returned None for all districts")

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Override in subclass to get enrollment for district.

        Args:
            df: DataFrame from load_enrollment_data()
            state_id: State-specific district identifier

        Returns:
            Enrollment count as float, or None if district not found
        """
        return None


class SEALCTCalculationTests:
    """Mixin class for LCT calculation tests."""

    def test_lct_formula_correct(self):
        """LCT calculation follows formula: (minutes * staff) / enrollment."""
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            if not all(k in expected for k in ['enrollment', 'total_teachers', 'expected_lct_teachers_only']):
                continue

            minutes = expected.get('instructional_minutes', self.DEFAULT_INSTRUCTIONAL_MINUTES)
            teachers = expected['total_teachers']
            enrollment = expected['enrollment']
            expected_lct = expected['expected_lct_teachers_only']

            # Skip if any value is None
            if teachers is None or enrollment is None or expected_lct is None:
                continue

            calculated_lct = (minutes * teachers) / enrollment
            tolerance = expected_lct * self.LCT_TOLERANCE_PCT

            assert abs(calculated_lct - expected_lct) <= tolerance, \
                f"{district_name}: Calculated LCT {calculated_lct:.2f} differs from expected {expected_lct:.2f}"

    def test_lct_values_in_valid_range(self):
        """LCT values are within reasonable range (1-60 minutes)."""
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            # Skip SPED-intensive districts with expected high LCT
            if expected.get('skip_lct_range_validation'):
                continue

            for lct_key in ['expected_lct_teachers_only', 'expected_lct_instructional']:
                if lct_key not in expected:
                    continue

                lct_value = expected[lct_key]
                # Skip if value is None
                if lct_value is None:
                    continue

                assert 1 <= lct_value <= 60, \
                    f"{district_name}: LCT {lct_value} outside valid range (1-60)"


class SEADataIntegrityTests:
    """Mixin class for data integrity tests."""

    def test_no_duplicate_districts_in_expected(self):
        """No duplicate district entries in expected values."""
        district_ids = [
            exp.get('state_district_id')
            for exp in self.EXPECTED_DISTRICTS.values()
            if exp.get('state_district_id')
        ]
        assert len(district_ids) == len(set(district_ids)), "Duplicate district IDs in expected values"

    def test_staff_enrollment_ratio_reasonable(self):
        """Staff to enrollment ratio is reasonable (1:5 to 1:100)."""
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            # Skip SPED-intensive districts with expected intensive staffing
            if expected.get('skip_ratio_validation'):
                continue

            if 'total_teachers' not in expected or 'enrollment' not in expected:
                continue

            teachers = expected['total_teachers']
            enrollment = expected['enrollment']

            # Skip if either value is None or zero
            if teachers is None or teachers == 0:
                continue
            if enrollment is None or enrollment == 0:
                continue

            ratio = enrollment / teachers
            assert 5 <= ratio <= 100, \
                f"{district_name}: Student-teacher ratio {ratio:.1f}:1 outside valid range (5-100)"


class SEADataQualityTests:
    """Mixin class for data quality validation tests."""

    def test_suppressed_values_handled(self):
        """Verify suppressed values ('*', '-', '') don't cause errors."""
        files = self.get_data_files()
        # Check that load functions don't crash on suppressed data
        try:
            if 'staff' in files and files['staff'].exists():
                staff_df = self.load_staff_data()
                assert len(staff_df) >= 0  # Just verify it loads
            if 'enrollment' in files and files['enrollment'].exists():
                enroll_df = self.load_enrollment_data()
                assert len(enroll_df) >= 0  # Just verify it loads
        except Exception as e:
            pytest.fail(f"Loading failed on suppressed values: {e}")

    def test_state_id_format_documented(self):
        """State ID format is documented in expected districts."""
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            if 'state_district_id' in expected:
                state_id = expected['state_district_id']
                # State ID should be a non-empty string
                assert state_id and len(str(state_id)) > 0, \
                    f"{district_name}: state_district_id should be non-empty"

    def test_sped_intensive_districts_flagged(self):
        """SPED-intensive districts have appropriate skip flags."""
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            teachers = expected.get('total_teachers')
            enrollment = expected.get('enrollment')

            # If ratio data is available and ratio < 10:1, should have flags
            if teachers and enrollment and teachers > 0:
                ratio = enrollment / teachers
                if ratio < 10:
                    has_skip_flags = (
                        expected.get('skip_ratio_validation') or
                        expected.get('skip_lct_range_validation') or
                        expected.get('sped_intensive')
                    )
                    assert has_skip_flags, \
                        f"{district_name} has low ratio ({ratio:.1f}:1) but no SPED flags"


class SEARegressionPreventionTests:
    """Mixin class for regression prevention tests."""

    def test_district_ids_correct_type(self):
        """District IDs are correct types (prevent type coercion bugs)."""
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            if 'state_district_id' in expected:
                state_id = expected['state_district_id']
                # State IDs should be strings
                assert isinstance(state_id, str), \
                    f"{district_name}: state_district_id should be string, got {type(state_id)}"

            if 'nces_leaid' in expected:
                nces_id = expected['nces_leaid']
                assert isinstance(nces_id, str), \
                    f"{district_name}: nces_leaid should be string, got {type(nces_id)}"

    def test_enrollment_not_zero(self):
        """Enrollment values are not zero for expected districts."""
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            if 'enrollment' not in expected:
                continue
            # Skip districts with None enrollment (awaiting verification)
            if expected['enrollment'] is None:
                continue
            assert expected['enrollment'] > 0, \
                f"{district_name}: Enrollment should not be zero"

    def test_teachers_not_zero(self):
        """Teacher counts are not zero for expected districts."""
        for district_name, expected in self.EXPECTED_DISTRICTS.items():
            if 'total_teachers' not in expected:
                continue
            # Skip state totals where teachers may be None
            if expected['total_teachers'] is None:
                continue
            assert expected['total_teachers'] > 0, \
                f"{district_name}: Teachers should not be zero"


# Helper functions for subclasses

def calculate_lct(minutes: float, staff: float, enrollment: float) -> float:
    """Calculate Learning Connection Time."""
    if enrollment == 0:
        return 0.0
    return (minutes * staff) / enrollment


def within_tolerance(actual: float, expected: float, tolerance_pct: float) -> bool:
    """Check if actual value is within tolerance of expected."""
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / expected <= tolerance_pct


def format_state_district_id(state: str, raw_id: str) -> str:
    """Format state district ID based on state conventions."""
    state_formats = {
        'FL': lambda x: str(x).zfill(2),  # 2-digit
        'TX': lambda x: f"TX-{str(x).zfill(6)}",  # TX-XXXXXX
        'CA': lambda x: str(x),  # County-District format handled separately
    }
    formatter = state_formats.get(state, lambda x: str(x))
    return formatter(raw_id)
