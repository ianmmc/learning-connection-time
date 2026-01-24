"""
Integration Tests for Michigan Department of Education (MDE) Data.

These tests validate the Michigan state data integration against actual MDE files.
Inherits from SEAIntegrationTestBase to leverage common patterns.

IMPORTANT: These tests require actual MDE data files in:
  data/raw/state/michigan/

Michigan has 880 school districts serving ~1.4M students. Detroit Public Schools
is the largest district with ~48K students.

Run with: pytest tests/test_michigan_integration.py -v
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
# MICHIGAN-SPECIFIC CONFIGURATION
# =============================================================================

MDE_DATA_DIR = Path("data/raw/state/michigan")
MDE_FILES_PRESENT = MDE_DATA_DIR.exists() and any(MDE_DATA_DIR.glob("*.xlsx"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not MDE_FILES_PRESENT,
        reason="MDE data files not present in data/raw/state/michigan/"
    ),
]


class MichiganSEAConfig(SEAIntegrationTestBase):
    """Michigan-specific SEA configuration."""

    STATE_CODE = "MI"
    STATE_NAME = "Michigan"
    SEA_NAME = "MDE"
    DATA_YEAR = "2023-24"

    # Michigan uses 300 minutes default (5 hours)
    DEFAULT_INSTRUCTIONAL_MINUTES = 300

    # NCES LEAID -> Michigan District Code (5-digit)
    CROSSWALK = {
        "2601103": "82015",  # Detroit Public Schools Community District
        "2634470": "50210",  # Utica Community Schools
        "2611600": "82030",  # Dearborn City School District
        "2602820": "81010",  # Ann Arbor Public Schools
        "2628560": "82100",  # Plymouth-Canton Community Schools
    }

    # Expected values from MDE 2023-24 data files
    EXPECTED_DISTRICTS = {
        "DETROIT": {
            "state_district_id": "82015",
            "nces_leaid": "2601103",
            "enrollment": 47581,
            "total_teachers": 2429.56,
            "expected_lct_teachers_only": 15.3,
            "instructional_minutes": 300,
            # Detroit Public Schools Community District
        },
        "UTICA": {
            "state_district_id": "50210",
            "nces_leaid": "2634470",
            "enrollment": 25303,
            "total_teachers": 1148.25,
            "expected_lct_teachers_only": 13.6,
            "instructional_minutes": 300,
            # Utica Community Schools
        },
        "DEARBORN": {
            "state_district_id": "82030",
            "nces_leaid": "2611600",
            "enrollment": 19524,
            "total_teachers": 1134.18,
            "expected_lct_teachers_only": 17.4,
            "instructional_minutes": 300,
            # Dearborn City School District
        },
        "ANN_ARBOR": {
            "state_district_id": "81010",
            "nces_leaid": "2602820",
            "enrollment": 16918,
            "total_teachers": 1048.53,
            "expected_lct_teachers_only": 18.6,
            "instructional_minutes": 300,
            # Ann Arbor Public Schools
        },
        "PLYMOUTH_CANTON": {
            "state_district_id": "82100",
            "nces_leaid": "2628560",
            "enrollment": 16051,
            "total_teachers": 800.97,
            "expected_lct_teachers_only": 15.0,
            "instructional_minutes": 300,
            # Plymouth-Canton Community Schools
        },
    }

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to MDE data files."""
        return {
            "staffing": MDE_DATA_DIR / "mi_staffing_2023_24.xlsx",
            "enrollment": MDE_DATA_DIR / "Spring_2024_Headcount.xlsx",
            "special_ed": MDE_DATA_DIR / "mi_special_ed_2023_24.xlsx",
        }

    def load_staff_data(self) -> pd.DataFrame:
        """
        Load MDE staffing data.

        Returns DataFrame with columns:
        - DCODE (district code)
        - DNAME (district name)
        - TEACHER (total teacher FTE)
        - SE_INSTR (special education instructional staff)
        """
        files = self.get_data_files()
        df = pd.read_excel(files["staffing"], sheet_name="District", skiprows=4)
        return df

    def load_enrollment_data(self) -> pd.DataFrame:
        """
        Load MDE enrollment data.

        Returns DataFrame with columns:
        - District Code (5-digit)
        - District Name
        - tot_all (total K-12 enrollment)
        - k_totl, g1_totl, ... g12_totl (grade-level enrollment)
        """
        files = self.get_data_files()
        df = pd.read_excel(
            files["enrollment"],
            sheet_name="Fall Dist K-12 Total Data",
            skiprows=4
        )
        return df

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get teacher count for Michigan district by DCODE.

        Args:
            df: DataFrame from load_staff_data() with DCODE and TEACHER columns
            state_id: Michigan district code (5-digit string, e.g., "82015")

        Returns:
            Teacher FTE count, or None if district not found
        """
        # DCODE may be int or string, normalize to string for comparison
        df_copy = df.copy()
        df_copy["DCODE_str"] = df_copy["DCODE"].astype(str).str.zfill(5)
        district = df_copy[df_copy["DCODE_str"] == str(state_id).zfill(5)]
        if len(district) == 0:
            return None
        return float(district.iloc[0]["TEACHER"])

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get enrollment for Michigan district by District Code.

        Args:
            df: DataFrame from load_enrollment_data() with District Code and tot_all columns
            state_id: Michigan district code (5-digit string, e.g., "82015")

        Returns:
            Enrollment count, or None if district not found
        """
        # District Code may be int or string, normalize to string for comparison
        df_copy = df.copy()
        df_copy["DC_str"] = df_copy["District Code"].astype(str).str.zfill(5)
        district = df_copy[df_copy["DC_str"] == str(state_id).zfill(5)]
        if len(district) == 0:
            return None
        return float(district.iloc[0]["tot_all"])


# =============================================================================
# MICHIGAN-SPECIFIC TESTS (MIXIN)
# =============================================================================

class MichiganSpecificValidations:
    """Michigan-specific validation tests (mixin - not run standalone)."""

    def test_detroit_is_largest(self):
        """Verify Detroit Public Schools is the largest district."""
        enroll = self.load_enrollment_data()

        # Sort by enrollment
        enroll_sorted = enroll.sort_values("tot_all", ascending=False)
        largest = enroll_sorted.iloc[0]

        assert "Detroit" in largest["District Name"], \
            f"Expected Detroit to be largest, found {largest['District Name']}"

    def test_detroit_enrollment_exceeds_45k(self):
        """Verify Detroit has >45K students."""
        enroll = self.load_enrollment_data()

        detroit = enroll[enroll["District Name"].str.contains("Detroit", case=False, na=False)]
        assert len(detroit) > 0, "Detroit not found"

        detroit_enrollment = detroit.iloc[0]["tot_all"]
        assert detroit_enrollment > 45000, \
            f"Detroit enrollment {detroit_enrollment:,} should exceed 45K"

    def test_district_code_format(self):
        """Verify district codes follow expected 5-digit format."""
        enroll = self.load_enrollment_data()

        # Sample some district codes
        sample_codes = enroll["District Code"].head(20).tolist()

        for code in sample_codes:
            # District code should be 5 digits
            code_str = str(code)
            assert len(code_str) == 5, \
                f"District code {code} should be 5 digits, got {len(code_str)}"
            assert code_str.isdigit(), \
                f"District code {code} should be all digits"

    def test_district_count_reasonable(self):
        """Verify district count is reasonable (800-900)."""
        enroll = self.load_enrollment_data()

        district_count = len(enroll)
        # Michigan has ~880 districts
        assert 800 <= district_count <= 900, \
            f"District count {district_count} should be between 800-900"

    def test_total_enrollment_reasonable(self):
        """Verify total state enrollment is reasonable (~1.3-1.5M)."""
        enroll = self.load_enrollment_data()

        total_enrollment = enroll["tot_all"].sum()
        # Michigan has ~1.4M students
        assert 1_300_000 <= total_enrollment <= 1_500_000, \
            f"Total enrollment {total_enrollment:,} should be ~1.3-1.5M"

    def test_special_ed_data_available(self):
        """Verify special education data is available."""
        files = self.get_data_files()
        assert files["special_ed"].exists(), "Special ed file should exist"

        sped = pd.read_excel(files["special_ed"], sheet_name="Fall 2023 Data", skiprows=4)
        assert len(sped) > 0, "Special ed data should not be empty"

        # Check Detroit has SPED data
        detroit = sped[sped["DNAME"].str.contains("Detroit", case=False, na=False)]
        assert len(detroit) > 0, "Detroit should have SPED data"


# =============================================================================
# MAIN TEST CLASS
# =============================================================================

class TestMichiganIntegration(
    MichiganSEAConfig,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEADataQualityTests,
    SEARegressionPreventionTests,
    MichiganSpecificValidations,
):
    """
    Comprehensive integration tests for Michigan State (MDE) data.

    Combines:
    - Standard SEA integration tests (from mixins)
    - MI-specific validations (Detroit, district codes, state totals)

    Total: ~30+ tests (including data quality tests)
    """
    pass
