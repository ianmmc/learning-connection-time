"""
Integration Tests for Pennsylvania Department of Education (PDE) Data.

These tests validate the Pennsylvania state data integration against actual PDE files.
Inherits from SEAIntegrationTestBase to leverage common patterns.

IMPORTANT: These tests require actual PDE data files in:
  data/raw/state/pennsylvania/

Pennsylvania has 779 school districts serving ~1.6M students. Philadelphia City SD
is the largest district with ~120K students.

Run with: pytest tests/test_pennsylvania_integration.py -v
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
# PENNSYLVANIA-SPECIFIC CONFIGURATION
# =============================================================================

PDE_DATA_DIR = Path("data/raw/state/pennsylvania")
PDE_FILES_PRESENT = PDE_DATA_DIR.exists() and any(PDE_DATA_DIR.glob("*.xlsx"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not PDE_FILES_PRESENT,
        reason="PDE data files not present in data/raw/state/pennsylvania/"
    ),
]


class PennsylvaniaSEAConfig(SEAIntegrationTestBase):
    """Pennsylvania-specific SEA configuration."""

    STATE_CODE = "PA"
    STATE_NAME = "Pennsylvania"
    SEA_NAME = "PDE"
    DATA_YEAR = "2024-25"

    # Pennsylvania uses 300 minutes default (5 hours)
    DEFAULT_INSTRUCTIONAL_MINUTES = 300

    # NCES LEAID -> Pennsylvania AUN (Administrative Unit Number)
    CROSSWALK = {
        "4218990": "126515001",  # Philadelphia City SD
        "4200119": "115220002",  # Commonwealth Charter Academy CS
        "4219170": "102027451",  # Pittsburgh SD
        "4205310": "122092102",  # Central Bucks SD
        "4202280": "121390302",  # Allentown City SD
    }

    # Expected values from PDE 2024-25 data files
    EXPECTED_DISTRICTS = {
        "PHILADELPHIA": {
            "state_district_id": "126515001",
            "nces_leaid": "4218990",
            "enrollment": 120148,
            "total_teachers": 8504,
            "expected_lct_teachers_only": 21.2,
            "instructional_minutes": 300,
            # Philadelphia City SD
        },
        "COMMONWEALTH_CHARTER": {
            "state_district_id": "115220002",
            "nces_leaid": "4200119",
            "enrollment": 29327,
            "total_teachers": 1807,
            "expected_lct_teachers_only": 18.5,
            "instructional_minutes": 300,
            # Commonwealth Charter Academy CS
        },
        "PITTSBURGH": {
            "state_district_id": "102027451",
            "nces_leaid": "4219170",
            "enrollment": 19581,
            "total_teachers": 1650,
            "expected_lct_teachers_only": 25.3,
            "instructional_minutes": 300,
            # Pittsburgh SD
        },
        "CENTRAL_BUCKS": {
            "state_district_id": "122092102",
            "nces_leaid": "4205310",
            "enrollment": 16941,
            "total_teachers": 1251,
            "expected_lct_teachers_only": 22.2,
            "instructional_minutes": 300,
            # Central Bucks SD
        },
        "ALLENTOWN": {
            "state_district_id": "121390302",
            "nces_leaid": "4202280",
            "enrollment": 16770,
            "total_teachers": 1012,
            "expected_lct_teachers_only": 18.1,
            "instructional_minutes": 300,
            # Allentown City SD
        },
    }

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to PDE data files."""
        return {
            "staffing": PDE_DATA_DIR / "pa_staffing_2024_25.xlsx",
            "enrollment": PDE_DATA_DIR / "pa_enrollment_2024_25.xlsx",
        }

    def load_staff_data(self) -> pd.DataFrame:
        """
        Load PDE staffing data.

        Returns DataFrame with columns:
        - AUN (Administrative Unit Number)
        - LEA NAME (district name)
        - CT (Classroom Teachers - FTE count)
        - PP (Total Professional Personnel)
        """
        files = self.get_data_files()
        df = pd.read_excel(files["staffing"], sheet_name="LEA_FT+PT", skiprows=4)
        return df

    def load_enrollment_data(self) -> pd.DataFrame:
        """
        Load PDE enrollment data.

        Returns DataFrame with columns:
        - AUN (Administrative Unit Number)
        - LEA Name (district name)
        - Total (total K-12 enrollment)
        - Grade-level columns (PKF, K5F, 1.0-12.0)
        """
        files = self.get_data_files()
        df = pd.read_excel(files["enrollment"], sheet_name="LEA", header=4)
        return df

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get teacher count for Pennsylvania district by AUN.

        Args:
            df: DataFrame from load_staff_data() with AUN and CT (Classroom Teachers) columns
            state_id: Pennsylvania AUN (9-digit string, e.g., "126515001")

        Returns:
            Classroom Teacher FTE count, or None if district not found
        """
        # AUN may be int or string, normalize for comparison
        state_id_int = int(state_id)
        district = df[df["AUN"] == state_id_int]
        if len(district) == 0:
            return None
        return float(district.iloc[0]["CT"])

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get enrollment for Pennsylvania district by AUN.

        Args:
            df: DataFrame from load_enrollment_data() with AUN and Total columns
            state_id: Pennsylvania AUN (9-digit string, e.g., "126515001")

        Returns:
            Enrollment count, or None if district not found
        """
        # AUN may be int or string, normalize for comparison
        state_id_int = int(state_id)
        district = df[df["AUN"] == state_id_int]
        if len(district) == 0:
            return None
        return float(district.iloc[0]["Total"])


# =============================================================================
# PENNSYLVANIA-SPECIFIC TESTS (MIXIN)
# =============================================================================

class PennsylvaniaSpecificValidations:
    """Pennsylvania-specific validation tests (mixin - not run standalone)."""

    def test_philadelphia_is_largest(self):
        """Verify Philadelphia City SD is the largest district."""
        enroll = self.load_enrollment_data()

        # Sort by enrollment
        enroll_sorted = enroll.sort_values("Total", ascending=False)
        largest = enroll_sorted.iloc[0]

        assert "Philadelphia" in largest["LEA Name"], \
            f"Expected Philadelphia to be largest, found {largest['LEA Name']}"

    def test_philadelphia_enrollment_exceeds_100k(self):
        """Verify Philadelphia has >100K students."""
        enroll = self.load_enrollment_data()

        philly = enroll[enroll["LEA Name"].str.contains("Philadelphia City", case=False, na=False)]
        assert len(philly) > 0, "Philadelphia not found"

        philly_enrollment = philly.iloc[0]["Total"]
        assert philly_enrollment > 100000, \
            f"Philadelphia enrollment {philly_enrollment:,} should exceed 100K"

    def test_aun_format(self):
        """Verify AUN codes follow expected 9-digit format."""
        enroll = self.load_enrollment_data()

        # Sample some AUN codes
        sample_auns = enroll["AUN"].head(20).tolist()

        for aun in sample_auns:
            # AUN should be numeric
            aun_str = str(aun)
            # Can be 9 digits or less (some have leading zeros removed)
            assert len(aun_str) <= 9, \
                f"AUN {aun} should be ≤9 digits, got {len(aun_str)}"
            assert aun_str.isdigit(), \
                f"AUN {aun} should be all digits"

    def test_district_count_reasonable(self):
        """Verify district count is reasonable (700-800)."""
        enroll = self.load_enrollment_data()

        district_count = len(enroll)
        # Pennsylvania has ~779 districts
        assert 700 <= district_count <= 850, \
            f"District count {district_count} should be between 700-850"

    def test_total_enrollment_reasonable(self):
        """Verify total state enrollment is reasonable (~1.5-1.8M)."""
        enroll = self.load_enrollment_data()

        total_enrollment = enroll["Total"].sum()
        # Pennsylvania has ~1.6M students
        assert 1_500_000 <= total_enrollment <= 1_800_000, \
            f"Total enrollment {total_enrollment:,} should be ~1.5-1.8M"

    def test_classroom_teachers_vs_all_personnel(self):
        """Verify classroom teachers (CT) are subset of professional personnel (PP)."""
        staff = self.load_staff_data()

        # Sample some districts
        sample = staff.head(20)

        for _, row in sample.iterrows():
            ct = row.get('CT', 0)
            pp = row.get('PP', 0)
            if ct > 0 and pp > 0:
                assert ct <= pp, \
                    f"Classroom teachers ({ct}) should be ≤ total personnel ({pp}) for {row['LEA NAME']}"


# =============================================================================
# MAIN TEST CLASS
# =============================================================================

class TestPennsylvaniaIntegration(
    PennsylvaniaSEAConfig,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEADataQualityTests,
    SEARegressionPreventionTests,
    PennsylvaniaSpecificValidations,
):
    """
    Comprehensive integration tests for Pennsylvania State (PDE) data.

    Combines:
    - Standard SEA integration tests (from mixins)
    - PA-specific validations (Philadelphia, AUN format, state totals)

    Total: ~30+ tests (including data quality tests)
    """
    pass
