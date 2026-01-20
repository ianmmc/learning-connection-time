"""
Integration Tests for Massachusetts Department of Elementary and Secondary Education (DESE) Data.

These tests validate the Massachusetts state data integration against actual DESE files.
Inherits from SEAIntegrationTestBase to leverage common patterns.

IMPORTANT: These tests require actual DESE data files in:
  data/raw/state/massachusetts/

Massachusetts has ~400 school districts serving ~900K students. Boston
is the largest district with ~46K students.

Data sources:
- Enrollment: E2C Hub (Education-to-Career Data Hub)
- Staffing: DESE Profiles (manually exported)

Run with: pytest tests/test_massachusetts_integration.py -v
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
# MASSACHUSETTS-SPECIFIC CONFIGURATION
# =============================================================================

DESE_DATA_DIR = Path("data/raw/state/massachusetts")
DESE_FILES_PRESENT = DESE_DATA_DIR.exists() and (
    (DESE_DATA_DIR / "ma_enrollment_all_years.csv").exists() or
    (DESE_DATA_DIR / "MA 2024-25 teacherdata.xlsx").exists()
)

pytestmark = pytest.mark.skipif(
    not DESE_FILES_PRESENT,
    reason="DESE data files not present in data/raw/state/massachusetts/"
)


class MassachusettsSEAConfig(SEAIntegrationTestBase):
    """Massachusetts-specific SEA configuration."""

    STATE_CODE = "MA"
    STATE_NAME = "Massachusetts"
    SEA_NAME = "DESE"
    DATA_YEAR = "2023-24"

    # Massachusetts uses 360 minutes default (6 hours)
    DEFAULT_INSTRUCTIONAL_MINUTES = 360

    # NCES LEAID -> Massachusetts District Code (4-digit zero-padded)
    CROSSWALK = {
        "2502790": "0035",  # Boston
        "2513230": "0348",  # Worcester
        "2511130": "0281",  # Springfield
        "2507110": "0163",  # Lynn
        "2503090": "0044",  # Brockton
    }

    # Expected values from DESE data files
    # NOTE: Enrollment is 2023-24, Teacher FTE is 2024-25 (1-year offset acceptable for testing)
    EXPECTED_DISTRICTS = {
        "BOSTON": {
            "state_district_id": "0035",
            "nces_leaid": "2502790",
            "enrollment": 45742,  # 2023-24 from E2C Hub
            "total_teachers": 4365.7,  # 2024-25 from DESE Profiles
            "expected_lct_teachers_only": 34.4,  # (360 * 4365.7) / 45742 = 34.4
            "instructional_minutes": 360,
            # Boston Public Schools
        },
        "WORCESTER": {
            "state_district_id": "0348",
            "nces_leaid": "2513230",
            "enrollment": 24350,  # 2023-24
            "total_teachers": 1909.8,  # 2024-25
            "expected_lct_teachers_only": 28.2,  # (360 * 1909.8) / 24350 = 28.25
            "instructional_minutes": 360,
            # Worcester Public Schools
        },
        "SPRINGFIELD": {
            "state_district_id": "0281",
            "nces_leaid": "2511130",
            "enrollment": 23693,  # 2023-24
            "total_teachers": 2074.8,  # 2024-25
            "expected_lct_teachers_only": 31.5,  # (360 * 2074.8) / 23693 = 31.53
            "instructional_minutes": 360,
            # Springfield Public Schools
        },
        "LYNN": {
            "state_district_id": "0163",
            "nces_leaid": "2507110",
            "enrollment": 16022,  # 2023-24
            "total_teachers": 1363.6,  # 2024-25
            "expected_lct_teachers_only": 30.6,  # (360 * 1363.6) / 16022 = 30.65
            "instructional_minutes": 360,
            # Lynn Public Schools
        },
        "BROCKTON": {
            "state_district_id": "0044",
            "nces_leaid": "2503090",
            "enrollment": 14954,  # 2023-24
            "total_teachers": 979.2,  # 2024-25
            "expected_lct_teachers_only": 23.6,  # (360 * 979.2) / 14954 = 23.58
            "instructional_minutes": 360,
            # Brockton Public Schools
        },
    }

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to DESE data files."""
        return {
            "enrollment": DESE_DATA_DIR / "ma_enrollment_all_years.csv",
            "staffing": DESE_DATA_DIR / "MA 2024-25 teacherdata.xlsx",
        }

    def load_staff_data(self) -> pd.DataFrame:
        """
        Load DESE staffing data from manually exported Excel file.

        Returns DataFrame with columns:
        - District Name
        - District Code (8-digit, e.g., "00350000")
        - Total # of Teachers (FTE)
        - % of Teachers Licensed
        - Student / Teacher Ratio
        - etc.

        Note: This is 2024-25 data (one year ahead of enrollment).
        """
        files = self.get_data_files()
        df = pd.read_excel(files["staffing"], header=0)
        # First row contains column names
        df.columns = df.iloc[0]
        df = df[1:].reset_index(drop=True)
        return df

    def load_enrollment_data(self) -> pd.DataFrame:
        """
        Load DESE enrollment data from E2C Hub CSV.

        Returns DataFrame with columns:
        - SY (school year, e.g., "2024" for 2023-24)
        - DIST_CODE (8-digit, e.g., "00350000")
        - DIST_NAME
        - ORG_CODE
        - ORG_NAME
        - ORG_TYPE ("District", "School", "State")
        - TOTAL_CNT (total enrollment)
        - Grade-level counts (PK_CNT, K_CNT, G1_CNT, etc.)
        """
        files = self.get_data_files()
        df = pd.read_csv(files["enrollment"])
        return df

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get teacher count for Massachusetts district by District Code.

        Args:
            df: DataFrame from load_staff_data() with District Code and Total # of Teachers (FTE)
            state_id: MA district code (4-digit zero-padded, e.g., "0035")

        Returns:
            Teacher FTE count, or None if not found
        """
        # Convert 4-digit to 8-digit format (e.g., "0035" -> "00350000")
        state_id_8digit = state_id.zfill(4) + "0000"

        # Find district by code
        district = df[df["District Code"] == state_id_8digit]
        if len(district) == 0:
            return None

        # Get FTE value and clean it (remove commas if present)
        fte_raw = district.iloc[0]["Total # of Teachers (FTE)"]
        fte_clean = str(fte_raw).replace(",", "").strip()
        return float(fte_clean)

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get enrollment for Massachusetts district by District Code.

        Args:
            df: DataFrame from load_enrollment_data() with DIST_CODE and TOTAL_CNT
            state_id: MA district code (4-digit zero-padded, e.g., "0035")

        Returns:
            Enrollment count, or None if not found
        """
        # Convert 4-digit to 8-digit integer (e.g., "0035" -> 350000)
        state_id_int = int(state_id.zfill(4) + "0000")

        # Filter for 2023-24 school year (SY=2024) and District org type
        # Note: DIST_CODE is integer in CSV
        enrollment = df[
            (df["SY"] == 2024) &
            (df["DIST_CODE"] == state_id_int) &
            (df["ORG_TYPE"] == "District")
        ]
        if len(enrollment) == 0:
            return None

        return float(enrollment.iloc[0]["TOTAL_CNT"])


# =============================================================================
# MASSACHUSETTS-SPECIFIC TESTS (MIXIN)
# =============================================================================

class MassachusettsSpecificValidations:
    """Massachusetts-specific validation tests (mixin - not run standalone)."""

    def test_boston_is_largest(self):
        """Verify Boston is the largest district."""
        enroll = self.load_enrollment_data()

        # Filter for 2023-24 districts only
        districts = enroll[(enroll["SY"] == 2024) & (enroll["ORG_TYPE"] == "District")]

        # Sort by enrollment
        districts_sorted = districts.sort_values("TOTAL_CNT", ascending=False)
        largest = districts_sorted.iloc[0]

        assert "Boston" in largest["DIST_NAME"], \
            f"Expected Boston to be largest, found {largest['DIST_NAME']}"

    def test_boston_enrollment_exceeds_40k(self):
        """Verify Boston has >40K students."""
        enroll = self.load_enrollment_data()

        # Note: DIST_CODE is integer in CSV
        boston = enroll[
            (enroll["SY"] == 2024) &
            (enroll["DIST_CODE"] == 350000) &
            (enroll["ORG_TYPE"] == "District")
        ]
        assert len(boston) > 0, "Boston not found"

        boston_enrollment = boston.iloc[0]["TOTAL_CNT"]
        assert boston_enrollment > 40000, \
            f"Boston enrollment {boston_enrollment:,} should exceed 40K"

    def test_district_code_format(self):
        """Verify MA district codes follow expected format (integers)."""
        enroll = self.load_enrollment_data()

        # Sample some district codes from 2023-24
        sample_codes = enroll[
            (enroll["SY"] == 2024) &
            (enroll["ORG_TYPE"] == "District")
        ]["DIST_CODE"].head(20).tolist()

        for code in sample_codes:
            # DIST_CODE is stored as integer in CSV
            # When formatted as 8-digit string, should be valid
            code_str = str(code).zfill(8)
            assert len(code_str) == 8, \
                f"District code {code} formatted should be 8 digits"
            assert isinstance(code, (int, float)), \
                f"District code {code} should be numeric"

    def test_district_count_reasonable(self):
        """Verify district count is reasonable (~400)."""
        enroll = self.load_enrollment_data()

        district_count = len(enroll[
            (enroll["SY"] == 2024) &
            (enroll["ORG_TYPE"] == "District")
        ])

        # Massachusetts has ~400 districts
        assert 390 <= district_count <= 410, \
            f"District count {district_count} should be between 390-410"

    def test_total_enrollment_reasonable(self):
        """Verify total state enrollment is reasonable (~900K)."""
        enroll = self.load_enrollment_data()

        # Get state total for 2023-24
        state_total = enroll[
            (enroll["SY"] == 2024) &
            (enroll["ORG_CODE"] == "00000000") &
            (enroll["ORG_TYPE"] == "State")
        ]

        if len(state_total) > 0:
            total_enrollment = state_total.iloc[0]["TOTAL_CNT"]
            # Massachusetts has ~900K-950K students
            assert 850_000 <= total_enrollment <= 1_000_000, \
                f"Total enrollment {total_enrollment:,} should be ~850K-1M"

    def test_teacher_data_available(self):
        """Verify teacher staffing data is available."""
        staff = self.load_staff_data()
        assert len(staff) > 0, "Staffing data should not be empty"

        # Check Boston has staffing data
        boston = staff[staff["District Code"] == "00350000"]
        assert len(boston) > 0, "Boston should have staffing data"


# =============================================================================
# MAIN TEST CLASS
# =============================================================================

class TestMassachusettsIntegration(
    MassachusettsSEAConfig,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEADataQualityTests,
    SEARegressionPreventionTests,
    MassachusettsSpecificValidations,
):
    """
    Comprehensive integration tests for Massachusetts State (DESE) data.

    Combines:
    - Standard SEA integration tests (from mixins)
    - MA-specific validations (Boston largest, district count, etc.)

    Total: ~35+ tests (including data quality tests)

    Note: Teacher data is 2024-25, enrollment is 2023-24 (1-year offset acceptable).
    """
    pass
