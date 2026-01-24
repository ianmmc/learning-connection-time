"""
Integration Tests for Illinois State Board of Education (ISBE) Data.

These tests validate the Illinois state data integration against actual ISBE files.
Inherits from SEAIntegrationTestBase to leverage common patterns.

IMPORTANT: These tests require actual ISBE data files in:
  data/raw/state/illinois/

Chicago Public Schools District 299 is the third-largest school district in the US
with ~322K students and unique characteristics:
- 76% low-income students
- 22% students with disabilities
- 15.6% IEP students
- 17.6:1 elementary PTR, 18.9:1 high school PTR

Run with: pytest tests/test_illinois_integration.py -v
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
# ILLINOIS-SPECIFIC CONFIGURATION
# =============================================================================

ISBE_DATA_DIR = Path("data/raw/state/illinois")
ISBE_FILES_PRESENT = ISBE_DATA_DIR.exists() and any(ISBE_DATA_DIR.glob("*.xlsx"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not ISBE_FILES_PRESENT,
        reason="ISBE data files not present in data/raw/state/illinois/"
    ),
]


class IllinoisSEAConfig(SEAIntegrationTestBase):
    """Illinois-specific SEA configuration."""

    STATE_CODE = "IL"
    STATE_NAME = "Illinois"
    SEA_NAME = "ISBE"
    DATA_YEAR = "2023-24"

    # Illinois uses 300 minutes default (5 hours)
    DEFAULT_INSTRUCTIONAL_MINUTES = 300

    # NCES LEAID -> ISBE RCDTS (formatted as RR-CCC-DDDD-TT)
    CROSSWALK = {
        "1709930": "15-016-2990-25",  # Chicago Public Schools Dist 299
        "1713710": "31-045-0460-22",  # SD U-46 (Elgin)
        "1734510": "04-101-2050-25",  # Rockford SD 205
        "1741690": "19-022-2040-26",  # Indian Prairie CUSD 204
        "1731740": "56-099-2020-22",  # Plainfield SD 202
        "1708550": "31-045-3000-26",  # CUSD 300
        "1730270": "24-047-3080-26",  # CUSD 308
        "1727710": "19-022-2030-26",  # Naperville CUSD 203
    }

    # Expected values from ISBE 2023-24 data files
    EXPECTED_DISTRICTS = {
        "CHICAGO": {
            "state_district_id": "15-016-2990-25",
            "nces_leaid": "1709930",
            "enrollment": 321668,  # From ISBE Report Card
            "total_teachers": 23604.3,
            "expected_lct_teachers_only": 22.0,  # (300 * 23604.3) / 321668 = 22.0
            "instructional_minutes": 300,
            # Additional CPS-specific data
            "students_with_disabilities": 70727,
            "iep_students": 50096,
            "pct_low_income": 76.0,
            "ptr_elementary": 17.6,
            "ptr_high_school": 18.9,
        },
        "ELGIN_U46": {
            "state_district_id": "31-045-0460-22",
            "nces_leaid": "1713710",
            "enrollment": 33948,  # From ISBE
            "total_teachers": None,  # To be verified
            "expected_lct_teachers_only": None,
            "instructional_minutes": 300,
        },
        "ROCKFORD": {
            "state_district_id": "04-101-2050-25",
            "nces_leaid": "1734510",
            "enrollment": 27268,  # From ISBE
            "total_teachers": None,  # To be verified
            "expected_lct_teachers_only": None,
            "instructional_minutes": 300,
        },
        "INDIAN_PRAIRIE": {
            "state_district_id": "19-022-2040-26",
            "nces_leaid": "1741690",
            "enrollment": 25781,  # From ISBE
            "total_teachers": None,  # To be verified
            "expected_lct_teachers_only": None,
            "instructional_minutes": 300,
        },
        "PLAINFIELD": {
            "state_district_id": "56-099-2020-22",
            "nces_leaid": "1731740",
            "enrollment": 24554,  # From ISBE
            "total_teachers": None,  # To be verified
            "expected_lct_teachers_only": None,
            "instructional_minutes": 300,
        },
    }

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to ISBE data files."""
        return {
            "report_card": ISBE_DATA_DIR / "il_report_card_2023_24.xlsx",
        }

    def load_staff_data(self) -> pd.DataFrame:
        """
        Load ISBE staffing data from Report Card file.

        Returns DataFrame with columns:
        - RCDTS (state district ID)
        - District
        - Total Teacher FTE
        - School Counselor FTE
        - School Nurse FTE
        - School Psychologist FTE
        - School Social Worker FTE
        """
        files = self.get_data_files()
        df = pd.read_excel(files["report_card"], sheet_name="General")
        # Filter to district-level records only
        districts = df[df["Type"] == "District"].copy()
        return districts

    def load_enrollment_data(self) -> pd.DataFrame:
        """
        Load ISBE enrollment data from Report Card file.

        Returns DataFrame with columns:
        - RCDTS (state district ID)
        - District
        - # Student Enrollment
        - % Student Enrollment - Children with Disabilities
        - # Student Enrollment - IEP
        """
        files = self.get_data_files()
        df = pd.read_excel(files["report_card"], sheet_name="General")
        # Filter to district-level records only
        districts = df[df["Type"] == "District"].copy()
        return districts

    def _normalize_rcdts(self, rcdts: str) -> str:
        """Convert RCDTS from dashed format to 15-digit format.

        Illinois uses two RCDTS formats:
        - Dashed format: RR-CCC-DDDD-TT (e.g., "15-016-2990-25")
        - 15-digit format: RRCCCDDDDTT0000 (e.g., "150162990250000")

        The data files use 15-digit format, but crosswalk uses dashed format
        for human readability.

        Args:
            rcdts: RCDTS in either format

        Returns:
            RCDTS in 15-digit format
        """
        # Remove dashes if present
        normalized = rcdts.replace("-", "")
        # Pad to 15 digits with trailing zeros
        return normalized.ljust(15, "0")

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get teacher count for Illinois district by RCDTS.

        Args:
            df: DataFrame from load_staff_data() with RCDTS and Total Teacher FTE columns
            state_id: Illinois RCDTS format (dashed or 15-digit)

        Returns:
            Teacher FTE count, or None if district not found
        """
        # Normalize to 15-digit format for matching
        normalized_id = self._normalize_rcdts(state_id)
        district = df[df["RCDTS"].astype(str) == normalized_id]
        if len(district) == 0:
            return None
        return float(district.iloc[0]["Total Teacher FTE"])

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get enrollment for Illinois district by RCDTS.

        Args:
            df: DataFrame from load_enrollment_data() with RCDTS and # Student Enrollment columns
            state_id: Illinois RCDTS format (dashed or 15-digit)

        Returns:
            Enrollment count, or None if district not found
        """
        # Normalize to 15-digit format for matching
        normalized_id = self._normalize_rcdts(state_id)
        district = df[df["RCDTS"].astype(str) == normalized_id]
        if len(district) == 0:
            return None
        return float(district.iloc[0]["# Student Enrollment"])


# =============================================================================
# ILLINOIS-SPECIFIC TESTS (MIXIN)
# =============================================================================

class IllinoisSpecificValidations:
    """Illinois-specific validation tests (mixin - not run standalone)."""

    def test_chicago_is_largest(self):
        """Verify Chicago Public Schools is the largest district."""
        enroll = self.load_enrollment_data()

        # Sort by enrollment
        enroll_sorted = enroll.sort_values("# Student Enrollment", ascending=False)
        largest = enroll_sorted.iloc[0]

        assert "Chicago" in largest["District"], \
            f"Expected Chicago to be largest, found {largest['District']}"

    def test_chicago_enrollment_exceeds_300k(self):
        """Verify Chicago has >300K students (third-largest in US)."""
        enroll = self.load_enrollment_data()

        chicago = enroll[enroll["District"].str.contains("Chicago Public", case=False, na=False)]
        assert len(chicago) > 0, "Chicago not found"

        chicago_enrollment = chicago.iloc[0]["# Student Enrollment"]
        assert chicago_enrollment > 300000, \
            f"Chicago enrollment {chicago_enrollment:,} should exceed 300K"

    def test_chicago_has_high_sped_population(self):
        """Verify Chicago has significant SPED population (>15% IEP)."""
        enroll = self.load_enrollment_data()

        chicago = enroll[enroll["District"].str.contains("Chicago Public", case=False, na=False)]
        assert len(chicago) > 0, "Chicago not found"

        pct_iep_raw = chicago.iloc[0]["% Student Enrollment - IEP"]
        # Handle string values (ISBE sometimes uses '*' or '-' for suppressed data)
        try:
            pct_iep = float(pct_iep_raw)
        except (ValueError, TypeError):
            pytest.skip(f"IEP percentage not available: {pct_iep_raw}")

        # Chicago has ~15.6% IEP students
        assert pct_iep > 10.0, \
            f"Chicago IEP percentage {pct_iep}% should exceed 10%"

    def test_chicago_has_high_low_income(self):
        """Verify Chicago has high low-income population (>70%)."""
        enroll = self.load_enrollment_data()

        chicago = enroll[enroll["District"].str.contains("Chicago Public", case=False, na=False)]
        assert len(chicago) > 0, "Chicago not found"

        pct_low_income_raw = chicago.iloc[0]["% Student Enrollment - Low Income"]
        # Handle string values
        try:
            pct_low_income = float(pct_low_income_raw)
        except (ValueError, TypeError):
            pytest.skip(f"Low income percentage not available: {pct_low_income_raw}")

        # Chicago has ~76% low-income students
        assert pct_low_income > 70.0, \
            f"Chicago low-income percentage {pct_low_income}% should exceed 70%"

    def test_rcdts_format(self):
        """Verify RCDTS codes follow expected 15-digit format."""
        enroll = self.load_enrollment_data()

        # Sample some RCDTS codes
        sample_rcdts = enroll["RCDTS"].head(20).tolist()

        for rcdts in sample_rcdts:
            # RCDTS should be 15 digits
            rcdts_str = str(rcdts)
            assert len(rcdts_str) == 15, \
                f"RCDTS {rcdts} should be 15 digits, got {len(rcdts_str)}"
            assert rcdts_str.isdigit(), \
                f"RCDTS {rcdts} should be all digits"

    def test_district_count_reasonable(self):
        """Verify district count is reasonable (800-1000)."""
        enroll = self.load_enrollment_data()

        district_count = len(enroll)
        # Illinois has ~866 districts
        assert 800 <= district_count <= 1000, \
            f"District count {district_count} should be between 800-1000"

    def test_total_enrollment_reasonable(self):
        """Verify total state enrollment is reasonable (~1.8-2M)."""
        enroll = self.load_enrollment_data()

        total_enrollment = enroll["# Student Enrollment"].sum()
        # Illinois has ~1.85M students
        assert 1_700_000 <= total_enrollment <= 2_100_000, \
            f"Total enrollment {total_enrollment:,} should be ~1.8-2M"


# =============================================================================
# MAIN TEST CLASS
# =============================================================================

class TestIllinoisIntegration(
    IllinoisSEAConfig,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEADataQualityTests,
    SEARegressionPreventionTests,
    IllinoisSpecificValidations,
):
    """
    Comprehensive integration tests for Illinois State (ISBE) data.

    Combines:
    - Standard SEA integration tests (from mixins)
    - IL-specific validations (Chicago, RCDTS format, state totals)

    Total: ~27+ tests (including data quality tests)
    """
    pass
