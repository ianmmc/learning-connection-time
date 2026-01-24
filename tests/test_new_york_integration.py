"""
Integration Tests for New York State Education Department (NYSED) Data.

These tests validate the New York state data integration against actual NYSED files.
Inherits from SEAIntegrationTestBase to leverage common patterns.

IMPORTANT: These tests require actual NYSED data files in:
  data/raw/state/new-york/

NYC is divided into 32 geographic districts (1-32) + District 75 (citywide SPED).
District 75 is 98.7% Students with Disabilities and provides crucial SPED ratio data.

Run with: pytest tests/test_new_york_integration.py -v
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
    SEARegressionPreventionTests,
    calculate_lct,
)


# =============================================================================
# NEW YORK-SPECIFIC CONFIGURATION
# =============================================================================

NYSED_DATA_DIR = Path("data/raw/state/new-york")
NYSED_FILES_PRESENT = NYSED_DATA_DIR.exists() and any(NYSED_DATA_DIR.glob("*.xlsx"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not NYSED_FILES_PRESENT,
        reason="NYSED data files not present in data/raw/state/new-york/"
    ),
]


class NewYorkSEAConfig(SEAIntegrationTestBase):
    """New York-specific SEA configuration."""

    STATE_CODE = "NY"
    STATE_NAME = "New York"
    SEA_NAME = "NYSED"
    DATA_YEAR = "2023-24"

    # New York uses 360 minutes default
    DEFAULT_INSTRUCTIONAL_MINUTES = 360

    # NCES LEAID -> NYSED State District ID (12-digit format)
    CROSSWALK = {
        "3600077": "310200010000",  # NYC Geog Dist #2 - Manhattan
        "3600135": "307500010000",  # NYC Special Schools - District 75
        "3605850": "050100010000",  # Buffalo City SD (approximate - needs verification)
        "3631920": "660100010000",  # Yonkers City SD (approximate - needs verification)
        "3624750": "261600010000",  # Rochester City SD (approximate - needs verification)
        "3600103": "353100010000",  # NYC Geog Dist #31 - Staten Island
        "3600087": "321000010000",  # NYC Geog Dist #10 - Bronx
        "3600098": "342400010000",  # NYC Geog Dist #24 - Queens
        "3600151": "332000010000",  # NYC Geog Dist #20 - Brooklyn
        "3600123": "342700010000",  # NYC Geog Dist #27 - Queens
    }

    # Expected values from NYSED 2023-24 data files
    EXPECTED_DISTRICTS = {
        "NYC_DISTRICT_2": {
            "state_district_id": "310200010000",
            "nces_leaid": "3600077",
            "enrollment": 56783,  # From enrollment file (PreK-12 Total, 'All Students')
            "total_teachers": 4272.08,
            "expected_lct_teachers_only": 27.1,  # (360 * 4272.08) / 56783 = 27.09
            "instructional_minutes": 360,
        },
        "NYC_DISTRICT_75": {
            "state_district_id": "307500010000",
            "nces_leaid": "3600135",
            "enrollment": 27212,  # From enrollment file (PreK-12 Total, 'All Students')
            "total_teachers": 5073.63,
            "para_professional_staff": 8290.00,
            "teaching_assistants": 7525.00,
            "expected_lct_teachers_only": 67.1,  # (360 * 5073.63) / 27212 = 67.12
            "expected_lct_instructional": 277.1,  # Including paras and TAs: (360 * 20888.63) / 27212
            "instructional_minutes": 360,
            "sped_percentage": 98.7,  # 26,868 / 27,212
            # Flag: SPED-intensive district with ratios outside normal ranges
            "sped_intensive": True,
            "skip_ratio_validation": True,  # 4.8:1 ratio is valid for self-contained SPED
            "skip_lct_range_validation": True,  # 74.9 min LCT expected for SPED
        },
        "BUFFALO": {
            "state_district_id": "050100010000",  # TODO: Needs verification against NYSED data
            "nces_leaid": "3605850",
            "enrollment": None,  # NCES: 29866, awaiting crosswalk verification
            "total_teachers": None,  # Awaiting crosswalk verification
            "expected_lct_teachers_only": None,
            "instructional_minutes": 360,
        },
        "YONKERS": {
            "state_district_id": "660100010000",  # TODO: Needs verification against NYSED data
            "nces_leaid": "3631920",
            "enrollment": None,  # NCES: 24339, awaiting crosswalk verification
            "total_teachers": None,  # Awaiting crosswalk verification
            "expected_lct_teachers_only": None,
            "instructional_minutes": 360,
        },
        "ROCHESTER": {
            "state_district_id": "261600010000",  # TODO: Needs verification against NYSED data
            "nces_leaid": "3624750",
            "enrollment": None,  # NCES: 22164, awaiting crosswalk verification
            "total_teachers": None,  # Awaiting crosswalk verification
            "expected_lct_teachers_only": None,
            "instructional_minutes": 360,
        },
    }

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to NYSED data files."""
        return {
            "enrollment": NYSED_DATA_DIR / "ny_enrollment_district_2023_24.xlsx",
            "enrollment_sped": NYSED_DATA_DIR / "ny_enrollment_sped_2023_24.xlsx",
            "staff": NYSED_DATA_DIR / "ny_staffing_2023_24.xlsx",
        }

    def load_staff_data(self) -> pd.DataFrame:
        """
        Load NYSED staffing data from Personnel Master File.

        Returns DataFrame with columns:
        - STATE_DISTRICT_ID (int)
        - DISTRICT_NAME
        - STAFF_IND_DESC (e.g., 'Classroom Teacher')
        - FTE
        - K-12_ENROLL
        - DISTRICT_RATIO
        """
        files = self.get_data_files()
        staff_df = pd.read_excel(
            files["staff"],
            sheet_name="STAFF_RATIOS"
        )
        return staff_df

    def load_enrollment_data(self) -> pd.DataFrame:
        """
        Load NYSED enrollment data.

        Returns DataFrame with columns:
        - State District Identifier (int)
        - District Name
        - Subgroup Name (e.g., 'All Students')
        - PreK-12 Total
        - Grade-level columns
        """
        files = self.get_data_files()
        enroll_df = pd.read_excel(
            files["enrollment"],
            sheet_name="public-district-2023-24"
        )
        return enroll_df

    def load_sped_enrollment_data(self) -> pd.DataFrame:
        """
        Load NYSED SPED-disaggregated enrollment data.

        Returns DataFrame with columns:
        - State District Identifier (int)
        - District Name
        - Subgroup Name ('General Education Students', 'Students with Disabilities')
        - PreK-12 Total
        - Grade-level columns
        """
        files = self.get_data_files()
        sped_df = pd.read_excel(
            files["enrollment_sped"],
            sheet_name="public-district-2023-24"
        )
        return sped_df

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get teacher count for New York district by STATE_DISTRICT_ID.

        Args:
            df: DataFrame from load_staff_data() with STATE_DISTRICT_ID, STAFF_IND_DESC, and FTE columns
            state_id: NY state district ID (12-digit string, e.g., "310200010000")

        Returns:
            Teacher FTE count for 'Classroom Teacher' position, or None if not found
        """
        # STATE_DISTRICT_ID is int in data, state_id is string - convert for comparison
        state_id_int = int(state_id)

        # Filter to the specific district and 'Classroom Teacher' position
        teachers = df[
            (df["STATE_DISTRICT_ID"] == state_id_int) &
            (df["STAFF_IND_DESC"] == "Classroom Teacher")
        ]
        if len(teachers) == 0:
            return None
        return float(teachers.iloc[0]["FTE"])

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get enrollment for New York district by State District Identifier.

        Args:
            df: DataFrame from load_enrollment_data() with State District Identifier,
                Subgroup Name, and PreK-12 Total columns
            state_id: NY state district ID (12-digit string, e.g., "310200010000")

        Returns:
            Enrollment count for 'All Students', or None if not found
        """
        # State District Identifier is int in data, state_id is string
        state_id_int = int(state_id)

        # Filter to 'All Students' subgroup for the district
        enrollment = df[
            (df["State District Identifier"] == state_id_int) &
            (df["Subgroup Name"] == "All Students")
        ]
        if len(enrollment) == 0:
            return None
        return float(enrollment.iloc[0]["PreK-12 Total"])


# =============================================================================
# NEW YORK-SPECIFIC TESTS (MIXIN)
# =============================================================================

class NewYorkSpecificValidations:
    """New York-specific validation tests (mixin - not run standalone)."""

    def test_nyc_district_count(self):
        """Verify NYC has 32 geographic districts + District 75."""
        enroll = self.load_enrollment_data()

        # Get NYC districts
        nyc_geog = enroll[
            enroll['District Name'].str.contains('NYC GEOG DIST', case=False, na=False)
        ]

        unique_nyc_geog = nyc_geog['District Name'].unique()
        assert len(unique_nyc_geog) == 32, f"Expected 32 NYC geographic districts, found {len(unique_nyc_geog)}"

        # Verify District 75 exists
        d75 = enroll[enroll['State District Identifier'] == 307500010000]
        assert len(d75) > 0, "District 75 (NYC Special Schools) not found"

    def test_district_75_is_sped_focused(self):
        """Verify District 75 is predominantly Students with Disabilities."""
        sped = self.load_sped_enrollment_data()

        d75 = sped[sped['State District Identifier'] == 307500010000]
        assert len(d75) > 0, "District 75 not found in SPED enrollment file"

        # Get SPED and GenEd counts
        total_enrollment = 0
        sped_enrollment = 0

        for _, row in d75.iterrows():
            enrollment = int(row['PreK-12 Total'])
            total_enrollment += enrollment

            if row['Subgroup Name'] == 'Students with Disabilities':
                sped_enrollment = enrollment

        sped_percentage = (sped_enrollment / total_enrollment) * 100

        # District 75 should be >95% SPED
        assert sped_percentage > 95.0, f"District 75 should be >95% SPED, found {sped_percentage:.1f}%"

    def test_district_75_has_intensive_staffing(self):
        """Verify District 75 has much lower student-teacher ratio than regular districts."""
        staff = self.load_staff_data()

        # District 75 teachers
        d75_teachers = staff[
            (staff['STATE_DISTRICT_ID'] == 307500010000) &
            (staff['STAFF_IND_DESC'] == 'Classroom Teacher')
        ]
        assert len(d75_teachers) > 0, "District 75 teacher data not found"

        d75_ratio = d75_teachers['DISTRICT_RATIO'].iloc[0]

        # Regular NYC district (District 2)
        d2_teachers = staff[
            (staff['STATE_DISTRICT_ID'] == 310200010000) &
            (staff['STAFF_IND_DESC'] == 'Classroom Teacher')
        ]
        assert len(d2_teachers) > 0, "NYC District 2 teacher data not found"

        d2_ratio = d2_teachers['DISTRICT_RATIO'].iloc[0]

        # District 75 ratio should be significantly lower (more intensive)
        assert d75_ratio < d2_ratio / 2, \
            f"District 75 ratio ({d75_ratio:.1f}) should be less than half of regular district ({d2_ratio:.1f})"

    def test_district_75_has_massive_para_support(self):
        """Verify District 75 has extensive para-professional support."""
        staff = self.load_staff_data()

        # Get District 75 staffing
        d75 = staff[staff['STATE_DISTRICT_ID'] == 307500010000]

        teachers = d75[d75['STAFF_IND_DESC'] == 'Classroom Teacher']['FTE'].iloc[0]
        paras = d75[d75['STAFF_IND_DESC'] == 'Para-Professional Staff']['FTE'].iloc[0]
        tas = d75[d75['STAFF_IND_DESC'] == 'Teaching Assistants/Aides']['FTE'].iloc[0]

        # Combined para support should exceed classroom teachers
        combined_support = paras + tas
        assert combined_support > teachers, \
            f"District 75 para support ({combined_support:.0f}) should exceed teachers ({teachers:.0f})"

    def test_state_id_format(self):
        """Verify NY state IDs follow expected 12-digit format."""
        enroll = self.load_enrollment_data()

        # Sample some state IDs
        sample_ids = enroll['State District Identifier'].head(20).tolist()

        for state_id in sample_ids:
            # Should be 11-12 digits
            id_str = str(state_id)
            assert len(id_str) >= 11 and len(id_str) <= 12, \
                f"State ID {state_id} doesn't match expected format"

    def test_sped_data_completeness(self):
        """Verify SPED enrollment file has data for all districts."""
        enroll = self.load_enrollment_data()
        sped = self.load_sped_enrollment_data()

        # Get unique districts from each file
        enroll_districts = set(enroll['State District Identifier'].unique())
        sped_districts = set(sped['State District Identifier'].unique())

        # SPED file should have same or similar number of districts
        coverage = len(sped_districts) / len(enroll_districts)
        assert coverage > 0.95, \
            f"SPED file should cover >95% of districts, found {coverage*100:.1f}%"


# =============================================================================
# MAIN TEST CLASS
# =============================================================================

class TestNewYorkIntegration(
    NewYorkSEAConfig,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEARegressionPreventionTests,
    NewYorkSpecificValidations,
):
    """
    Comprehensive integration tests for New York State (NYSED) data.

    Combines:
    - Standard SEA integration tests (from mixins)
    - NY-specific validations (NYC structure, District 75, SPED data)

    Total: ~77 tests (71 from mixins + 6 NY-specific)
    """
    pass
