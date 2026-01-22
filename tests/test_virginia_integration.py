"""
Integration Tests for Virginia Department of Education (VDOE) Data.

These tests validate the Virginia state data integration against actual VDOE files.
Inherits from SEAIntegrationTestBase to leverage common patterns.

IMPORTANT: These tests require actual VDOE data files in:
  data/raw/state/virginia/

Virginia has 131 school divisions serving ~1.2M students. Fairfax County
is the largest division with ~177K students (2nd largest in the nation!).

Run with: pytest tests/test_virginia_integration.py -v
"""

import pytest
from pathlib import Path
from typing import Dict, Optional, Any
import pandas as pd

from test_sea_integration_base import (
    SEAIntegrationTestBase,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEADataQualityTests,
    SEARegressionPreventionTests,
    calculate_lct,
)


# =============================================================================
# VIRGINIA-SPECIFIC CONFIGURATION
# =============================================================================

VDOE_DATA_DIR = Path("data/raw/state/virginia")
VDOE_FILES_PRESENT = VDOE_DATA_DIR.exists() and any(VDOE_DATA_DIR.glob("*.csv"))

pytestmark = pytest.mark.skipif(
    not VDOE_FILES_PRESENT,
    reason="VDOE data files not present in data/raw/state/virginia/"
)


class VirginiaSEAConfig(SEAIntegrationTestBase):
    """Virginia-specific SEA configuration."""

    STATE_CODE = "VA"
    STATE_NAME = "Virginia"
    SEA_NAME = "VDOE"
    DATA_YEAR = "2025-26"

    # Virginia uses 300 minutes default (5 hours)
    DEFAULT_INSTRUCTIONAL_MINUTES = 300

    # NCES LEAID -> Virginia Division Number (3-digit zero-padded)
    CROSSWALK = {
        "5101260": "029",  # Fairfax County
        "5103130": "075",  # Prince William County
        "5102250": "053",  # Loudoun County
        "5103840": "128",  # Virginia Beach City
        "5100840": "021",  # Chesterfield County
    }

    # Expected values from VDOE 2025-26 data files
    EXPECTED_DISTRICTS = {
        "FAIRFAX": {
            "state_district_id": "029",
            "nces_leaid": "5101260",
            "enrollment": 177249,
            "total_teachers": 13412.38,
            "expected_lct_teachers_only": 22.7,
            "instructional_minutes": 300,
            # Fairfax County
        },
        "PRINCE_WILLIAM": {
            "state_district_id": "075",
            "nces_leaid": "5103130",
            "enrollment": 89662,
            "total_teachers": 8908.34,
            "expected_lct_teachers_only": 29.8,
            "instructional_minutes": 300,
            # Prince William County
        },
        "LOUDOUN": {
            "state_district_id": "053",
            "nces_leaid": "5102250",
            "enrollment": 80410,
            "total_teachers": 6920.09,
            "expected_lct_teachers_only": 25.8,
            "instructional_minutes": 300,
            # Loudoun County
        },
        "VIRGINIA_BEACH": {
            "state_district_id": "128",
            "nces_leaid": "5103840",
            "enrollment": 63969,
            "total_teachers": 4492.13,
            "expected_lct_teachers_only": 21.1,
            "instructional_minutes": 300,
            # Virginia Beach City
        },
        "CHESTERFIELD": {
            "state_district_id": "021",
            "nces_leaid": "5100840",
            "enrollment": 63955,
            "total_teachers": 4786.25,
            "expected_lct_teachers_only": 22.5,
            "instructional_minutes": 300,
            # Chesterfield County
        },
    }

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to VDOE data files."""
        return {
            "enrollment": VDOE_DATA_DIR / "fall_membership_statistics.csv",
            "staffing": VDOE_DATA_DIR / "staffing_and_vacancy_report_statistics.csv",
            "special_ed": VDOE_DATA_DIR / "dec_1_statistics (Special Education Enrollment).csv",
        }

    def load_staff_data(self) -> pd.DataFrame:
        """
        Load VDOE staffing data.

        Returns DataFrame with columns:
        - Division Number (3-digit, may not be zero-padded in file)
        - Division Name
        - Position Type (Administration, Teachers, etc.)
        - Number of Positions by FTE

        Note: Data is in "long" format with one row per division per position type.
        """
        files = self.get_data_files()
        df = pd.read_csv(files["staffing"])
        return df

    def load_enrollment_data(self) -> pd.DataFrame:
        """
        Load VDOE enrollment data.

        Returns DataFrame with columns:
        - Division Number (integer, not zero-padded)
        - Division Name
        - Total Count (enrollment with commas, needs cleaning)
        """
        files = self.get_data_files()
        df = pd.read_csv(files["enrollment"])
        return df

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get teacher count for Virginia division by Division Number.

        Args:
            df: DataFrame from load_staff_data() in long format with Division Number,
                Position Type, and Number of Positions by FTE columns
            state_id: Virginia Division Number (3-digit zero-padded, e.g., "029")

        Returns:
            Teacher FTE count, or None if not found

        Note: Virginia staff data is in long format (one row per position type).
              We filter for Position Type == 'Teachers' to get teacher count.
        """
        # Convert state_id to int for comparison with Division Number (which is int in CSV)
        div_num_int = int(state_id)

        # Filter for Teachers position type for this division
        teachers = df[
            (df["Division Number"] == div_num_int) &
            (df["Position Type"] == "Teachers")
        ]
        if len(teachers) == 0:
            return None

        # Clean FTE value (may have commas)
        fte_raw = teachers.iloc[0]["Number of Positions by FTE"]
        fte_clean = str(fte_raw).replace(",", "").strip()
        return float(fte_clean)

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get enrollment for Virginia division by Division Number.

        Args:
            df: DataFrame from load_enrollment_data() with Division Number and Total Count columns
            state_id: Virginia Division Number (3-digit zero-padded, e.g., "029")

        Returns:
            Enrollment count, or None if not found

        Note: Total Count values have commas and need cleaning before conversion.
        """
        # Convert state_id to int for comparison with Division Number (which is int in CSV)
        div_num_int = int(state_id)

        division = df[df["Division Number"] == div_num_int]
        if len(division) == 0:
            return None

        # Clean enrollment value (has commas and possibly spaces)
        enroll_raw = division.iloc[0]["Total Count"]
        enroll_clean = str(enroll_raw).replace(",", "").strip()
        return float(enroll_clean)


# =============================================================================
# VIRGINIA-SPECIFIC TESTS (MIXIN)
# =============================================================================

class VirginiaSpecificValidations:
    """Virginia-specific validation tests (mixin - not run standalone)."""

    def test_fairfax_is_largest(self):
        """Verify Fairfax County is the largest division."""
        enroll = self.load_enrollment_data()

        # Clean Total Count column
        enroll['Total Count Clean'] = enroll['Total Count'].astype(str).str.replace(',', '').str.strip().astype(float)

        # Sort by enrollment
        enroll_sorted = enroll.sort_values("Total Count Clean", ascending=False)
        largest = enroll_sorted.iloc[0]

        assert "Fairfax" in largest["Division Name"], \
            f"Expected Fairfax to be largest, found {largest['Division Name']}"

    def test_fairfax_enrollment_exceeds_150k(self):
        """Verify Fairfax has >150K students."""
        enroll = self.load_enrollment_data()

        # Clean Total Count
        enroll['Total Count Clean'] = enroll['Total Count'].astype(str).str.replace(',', '').str.strip().astype(float)

        fairfax = enroll[enroll["Division Name"].str.contains("Fairfax", case=False, na=False)]
        assert len(fairfax) > 0, "Fairfax not found"

        fairfax_enrollment = fairfax.iloc[0]["Total Count Clean"]
        assert fairfax_enrollment > 150000, \
            f"Fairfax enrollment {fairfax_enrollment:,} should exceed 150K"

    def test_division_number_format(self):
        """Verify Division Numbers are integers (not zero-padded in data file)."""
        enroll = self.load_enrollment_data()

        # Sample some division numbers
        sample_divs = enroll["Division Number"].head(20).tolist()

        for div in sample_divs:
            # Division Number should be an integer
            assert isinstance(div, (int, float)), \
                f"Division Number {div} should be numeric, got {type(div)}"

    def test_division_count_reasonable(self):
        """Verify division count is reasonable (130-135)."""
        enroll = self.load_enrollment_data()

        division_count = len(enroll)
        # Virginia has 131 divisions
        assert 130 <= division_count <= 135, \
            f"Division count {division_count} should be between 130-135"

    def test_total_enrollment_reasonable(self):
        """Verify total state enrollment is reasonable (~1.1-1.3M)."""
        enroll = self.load_enrollment_data()

        # Clean Total Count
        enroll['Total Count Clean'] = enroll['Total Count'].astype(str).str.replace(',', '').str.strip().astype(float)

        total_enrollment = enroll["Total Count Clean"].sum()
        # Virginia has ~1.2M students
        assert 1_100_000 <= total_enrollment <= 1_300_000, \
            f"Total enrollment {total_enrollment:,} should be ~1.1-1.3M"

    def test_staffing_long_format(self):
        """Verify staffing data is in long format with position types."""
        staff = self.load_staff_data()

        position_types = staff["Position Type"].unique()

        # Should have at least these position types
        assert "Teachers" in position_types, \
            "Staffing data should include 'Teachers' position type"
        assert len(position_types) >= 3, \
            f"Staffing data should have multiple position types, found {len(position_types)}"

    def test_special_ed_data_available(self):
        """Verify special education data is available."""
        files = self.get_data_files()
        assert files["special_ed"].exists(), "Special ed file should exist"

        sped = pd.read_csv(files["special_ed"])
        assert len(sped) > 0, "Special ed data should not be empty"

        # Check Fairfax has SPED data
        fairfax = sped[sped["Division Name"].str.contains("Fairfax", case=False, na=False)]
        assert len(fairfax) > 0, "Fairfax should have SPED data"


# =============================================================================
# MAIN TEST CLASS
# =============================================================================

class TestVirginiaIntegration(
    VirginiaSEAConfig,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEADataQualityTests,
    SEARegressionPreventionTests,
    VirginiaSpecificValidations,
):
    """
    Comprehensive integration tests for Virginia State (VDOE) data.

    Combines:
    - Standard SEA integration tests (from mixins)
    - VA-specific validations (Fairfax, Division Number format, state totals)

    Total: ~30+ tests (including data quality tests)
    """
    pass
