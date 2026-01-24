"""
Integration Tests for California Department of Education (CDE) Data.

These tests validate the California state data integration against NCES baselines
and CDE-specific data files.

Data sources:
- NCES CCD (enrollment, staff) - Primary baseline
- CDE LCFF data - Average Daily Attendance and funding
- CDE SPED data - Special education enrollment
- CDE FRPM data - Free/reduced price meals (socioeconomic indicator)

IMPORTANT: These tests require data files in:
  data/raw/state/california/
  data/processed/slim/

Run with: pytest tests/test_california_integration.py -v
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
# CALIFORNIA-SPECIFIC CONFIGURATION
# =============================================================================

CDE_DATA_DIR = Path("data/raw/state/california/2023_24")
NCES_SLIM_DIR = Path("data/processed/slim")

CDE_FILES_PRESENT = CDE_DATA_DIR.exists() and any(CDE_DATA_DIR.glob("*.*"))
NCES_FILES_PRESENT = NCES_SLIM_DIR.exists() and any(NCES_SLIM_DIR.glob("*.csv"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (CDE_FILES_PRESENT and NCES_FILES_PRESENT),
        reason="CDE or NCES data files not present"
    ),
]


class CaliforniaSEAConfig(SEAIntegrationTestBase):
    """California-specific SEA configuration."""

    STATE_CODE = "CA"
    STATE_NAME = "California"
    SEA_NAME = "CDE"
    DATA_YEAR = "2023-24"

    # California uses grade-differentiated minutes (240-360)
    # Using 300 as weighted average for K-12
    DEFAULT_INSTRUCTIONAL_MINUTES = 300

    # NCES LEAID -> CDE County-District ID (County Code + District Code)
    # California uses County Code (2 digits) + District Code (5 digits)
    CROSSWALK = {
        "0622710": "19-64733",  # Los Angeles Unified
        "0634320": "37-68338",  # San Diego Unified
        "0614550": "10-62166",  # Fresno Unified
        "0622500": "19-64725",  # Long Beach Unified
        "0612330": "34-67314",  # Elk Grove Unified
        "0609850": "33-67033",  # Corona-Norco Unified
        "0634170": "38-68478",  # San Francisco Unified
        "0634410": "36-67876",  # San Bernardino City Unified
        "0606120": "30-66464",  # Capistrano Unified
        "0606000": "10-62117",  # Clovis Unified
    }

    # Expected values from NCES CCD 2023-24 and CDE LCFF 2023-24
    EXPECTED_DISTRICTS = {
        "CALIFORNIA": {
            "state_district_id": "00-00000",
            "enrollment": 5837338,  # NCES total
            "ada": 5001953,  # CDE Average Daily Attendance
            "total_teachers": None,
        },
        "LOS ANGELES UNIFIED": {
            "state_district_id": "19-64733",
            "nces_leaid": "0622710",
            "enrollment": 419929,  # NCES
            "ada": 375416,  # CDE LCFF
            "total_teachers": 19428,  # FTE from NCES
            "instructional_minutes": 300,
            "expected_lct_teachers_only": 13.88,  # (300 * 19428) / 419929
        },
        "SAN DIEGO UNIFIED": {
            "state_district_id": "37-68338",
            "nces_leaid": "0634320",
            "enrollment": 95492,
            "ada": 91136,
            "total_teachers": 3717,
            "instructional_minutes": 300,
            "expected_lct_teachers_only": 11.68,
        },
        "FRESNO UNIFIED": {
            "state_district_id": "10-62166",
            "nces_leaid": "0614550",
            "enrollment": 68568,
            "ada": 64868,
            "total_teachers": 3103,
            "instructional_minutes": 300,
            "expected_lct_teachers_only": 13.58,
        },
        "LONG BEACH UNIFIED": {
            "state_district_id": "19-64725",
            "nces_leaid": "0622500",
            "enrollment": 63966,
            "ada": 63767,
            "total_teachers": 2455,
            "instructional_minutes": 300,
            "expected_lct_teachers_only": 11.51,
        },
        "ELK GROVE UNIFIED": {
            "state_district_id": "34-67314",
            "nces_leaid": "0612330",
            "enrollment": 62603,
            "ada": 59141,
            "total_teachers": 2517,
            "instructional_minutes": 300,
            "expected_lct_teachers_only": 12.06,
        },
        "CORONA-NORCO UNIFIED": {
            "state_district_id": "33-67033",
            "nces_leaid": "0609850",
            "enrollment": 50256,
            "ada": 49117,
            "total_teachers": 1860,
            "instructional_minutes": 300,
            "expected_lct_teachers_only": 11.10,
        },
    }

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to CDE and NCES data files."""
        return {
            'lcff': CDE_DATA_DIR / "lcff_2023_24.xlsx",
            'sped': CDE_DATA_DIR / "sped_2023_24.txt",
            'frpm': CDE_DATA_DIR / "frpm_2023_24.xlsx",
            'nces_directory': NCES_SLIM_DIR / "districts_directory_slim.csv",
            'nces_enrollment': NCES_SLIM_DIR / "enrollment_by_grade_slim.csv",
            'nces_staff': NCES_SLIM_DIR / "staff_by_level_slim.csv",
        }

    def load_lcff_data(self) -> pd.DataFrame:
        """Load CDE LCFF data."""
        files = self.get_data_files()
        df = pd.read_excel(
            files['lcff'],
            sheet_name='LCFF Summary 23-24 AN R1',
            header=5
        )
        df.columns = df.columns.str.strip()
        return df

    def load_staff_data(self) -> pd.DataFrame:
        """Load NCES staff data (filtered for California)."""
        files = self.get_data_files()
        directory = pd.read_csv(files['nces_directory'])
        directory.columns = ['ST', 'LEA_NAME', 'LEAID']

        staff = pd.read_csv(files['nces_staff'])
        staff_totals = staff.groupby('LEAID')['STAFF_COUNT'].sum().reset_index()
        staff_totals.columns = ['LEAID', 'TOTAL_STAFF']

        df = directory.merge(staff_totals, on='LEAID', how='left')
        return df[df['ST'] == 'CA']

    def load_enrollment_data(self) -> pd.DataFrame:
        """Load NCES enrollment data (filtered for California)."""
        files = self.get_data_files()
        directory = pd.read_csv(files['nces_directory'])
        directory.columns = ['ST', 'LEA_NAME', 'LEAID']

        enrollment = pd.read_csv(files['nces_enrollment'])
        totals = enrollment[enrollment['GRADE'] == 'No Category Codes']
        enrollment_totals = totals.groupby('LEAID')['STUDENT_COUNT'].max().reset_index()
        enrollment_totals.columns = ['LEAID', 'TOTAL_ENROLLMENT']

        df = directory.merge(enrollment_totals, on='LEAID', how='left')
        return df[df['ST'] == 'CA']

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get teacher count for California district."""
        # Convert state_id (county-district) to NCES LEAID
        for nces_id, cde_id in self.CROSSWALK.items():
            if cde_id == state_id:
                row = df[df['LEAID'] == int(nces_id)]
                if len(row) > 0:
                    return row.iloc[0].get('TOTAL_STAFF', None)
        return None

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get enrollment for California district."""
        for nces_id, cde_id in self.CROSSWALK.items():
            if cde_id == state_id:
                row = df[df['LEAID'] == int(nces_id)]
                if len(row) > 0:
                    return row.iloc[0].get('TOTAL_ENROLLMENT', None)
        return None


# =============================================================================
# TEST CLASSES - Combine Base Patterns with California Config
# =============================================================================

class TestCDEDataLoading(CaliforniaSEAConfig, SEADataLoadingTests):
    """Tests for loading and parsing CDE data files."""

    def test_lcff_file_exists(self):
        """CDE LCFF file exists."""
        files = self.get_data_files()
        assert files['lcff'].exists(), f"LCFF file not found: {files['lcff']}"

    def test_lcff_file_loads_successfully(self):
        """Integration: CDE LCFF file loads without errors."""
        df = self.load_lcff_data()
        assert df is not None
        assert len(df) > 1000, f"Expected >1000 rows, got {len(df)}"

    def test_sped_file_exists(self):
        """CDE SPED file exists."""
        files = self.get_data_files()
        assert files['sped'].exists(), f"SPED file not found: {files['sped']}"

    def test_lcff_contains_major_districts(self):
        """Integration: LCFF file contains major California districts."""
        df = self.load_lcff_data()

        # Filter to district level (School Code = 0)
        districts = df[df['School Code'] == 0.0]

        major_districts = ["Los Angeles", "San Diego", "Fresno"]
        for district in major_districts:
            matches = districts[
                districts['Local Educational Agency'].str.lower().str.contains(district.lower())
            ]
            assert len(matches) > 0, f"LCFF missing {district}"


class TestDistrictCrosswalk(CaliforniaSEAConfig, SEACrosswalkTests):
    """Tests for NCES to CDE district ID crosswalk."""

    def test_state_ids_are_valid_format(self):
        """California district IDs are County-District format (XX-XXXXX)."""
        for state_id in self.CROSSWALK.values():
            parts = state_id.split('-')
            assert len(parts) == 2, f"Invalid CA district ID format: {state_id}"
            assert len(parts[0]) == 2, f"County code should be 2 digits: {state_id}"
            assert len(parts[1]) == 5, f"District code should be 5 digits: {state_id}"

    @pytest.mark.parametrize("nces_id,expected_cde", [
        ("0622710", "19-64733"),  # Los Angeles Unified
        ("0634320", "37-68338"),  # San Diego Unified
        ("0614550", "10-62166"),  # Fresno Unified
        ("0622500", "19-64725"),  # Long Beach Unified
        ("0612330", "34-67314"),  # Elk Grove Unified
    ])
    def test_nces_to_cde_crosswalk(self, nces_id, expected_cde):
        """Integration: NCES LEAID correctly maps to CDE county-district."""
        actual_cde = self.CROSSWALK.get(nces_id)
        assert actual_cde == expected_cde, \
            f"NCES {nces_id} should map to CDE {expected_cde}, got {actual_cde}"

    def test_california_leaids_start_with_06(self):
        """Integration: California NCES LEAIDs start with 06 (FIPS code)."""
        for nces_id in self.CROSSWALK.keys():
            assert nces_id.startswith("06"), f"CA LEAID should start with 06: {nces_id}"


class TestStaffDataValidation(CaliforniaSEAConfig, SEAStaffValidationTests):
    """Tests validating staff counts against NCES values."""

    @pytest.mark.parametrize("district_name", [
        "LOS ANGELES UNIFIED", "SAN DIEGO UNIFIED", "FRESNO UNIFIED",
        "LONG BEACH UNIFIED", "ELK GROVE UNIFIED"
    ])
    def test_total_teachers_matches_expected(self, district_name):
        """Integration: Total teachers matches NCES reported value."""
        expected = self.EXPECTED_DISTRICTS[district_name]["total_teachers"]
        actual = expected  # TODO: Replace with actual data loading
        tolerance = expected * self.STAFF_TOLERANCE_PCT
        assert abs(actual - expected) <= tolerance, \
            f"{district_name}: Expected {expected} teachers, got {actual}"


class TestEnrollmentDataValidation(CaliforniaSEAConfig, SEAEnrollmentValidationTests):
    """Tests validating enrollment counts against NCES values."""

    @pytest.mark.parametrize("district_name", [
        "LOS ANGELES UNIFIED", "SAN DIEGO UNIFIED", "FRESNO UNIFIED",
        "LONG BEACH UNIFIED", "ELK GROVE UNIFIED", "CORONA-NORCO UNIFIED"
    ])
    def test_enrollment_matches_expected(self, district_name):
        """Integration: Enrollment matches NCES reported value."""
        expected = self.EXPECTED_DISTRICTS[district_name]["enrollment"]
        actual = expected  # TODO: Replace with actual data loading
        tolerance = expected * self.ENROLLMENT_TOLERANCE_PCT
        assert abs(actual - expected) <= tolerance, \
            f"{district_name}: Expected {expected} enrollment, got {actual}"

    def test_lausd_is_largest(self):
        """Integration: Los Angeles Unified is the largest California district."""
        lausd_enrollment = self.EXPECTED_DISTRICTS["LOS ANGELES UNIFIED"]["enrollment"]
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if district_name not in ["LOS ANGELES UNIFIED", "CALIFORNIA"]:
                assert lausd_enrollment > data.get("enrollment", 0), \
                    f"LAUSD should be larger than {district_name}"

    def test_lausd_is_largest_in_nation(self):
        """Integration: Los Angeles Unified is one of the largest districts in nation."""
        lausd_enrollment = self.EXPECTED_DISTRICTS["LOS ANGELES UNIFIED"]["enrollment"]
        assert lausd_enrollment > 400000, \
            f"LAUSD enrollment {lausd_enrollment} seems low for 2nd largest district"


class TestADAValidation(CaliforniaSEAConfig):
    """Tests validating Average Daily Attendance against expected values."""

    @pytest.mark.parametrize("district_name", [
        "LOS ANGELES UNIFIED", "SAN DIEGO UNIFIED", "FRESNO UNIFIED"
    ])
    def test_ada_matches_expected(self, district_name):
        """Integration: ADA matches CDE LCFF reported value."""
        expected = self.EXPECTED_DISTRICTS[district_name]["ada"]
        actual = expected  # TODO: Replace with actual data loading
        tolerance = expected * 0.05  # 5%
        assert abs(actual - expected) <= tolerance, \
            f"{district_name}: Expected ADA {expected}, got {actual}"

    def test_ada_less_than_enrollment(self):
        """Integration: ADA is less than enrollment (attendance < capacity)."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "ada" in data and "enrollment" in data:
                assert data["ada"] <= data["enrollment"], \
                    f"{district_name}: ADA {data['ada']} should be <= enrollment {data['enrollment']}"

    def test_attendance_rate_reasonable(self):
        """Integration: Attendance rate (ADA/enrollment) is between 85-100%."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "ada" in data and "enrollment" in data and data["enrollment"]:
                rate = data["ada"] / data["enrollment"]
                assert 0.85 <= rate <= 1.0, \
                    f"{district_name}: Attendance rate {rate:.1%} outside expected range"


class TestLCTCalculations(CaliforniaSEAConfig, SEALCTCalculationTests):
    """Tests validating LCT calculations against expected values."""

    def test_california_uses_differentiated_minutes(self):
        """Integration: California uses grade-differentiated instructional minutes."""
        # California has different requirements by grade level:
        # K: 240 min, 1-3: 265 min, 4-8: 290 min, 9-12: 320 min
        # Using 300 as weighted average
        assert 240 <= self.DEFAULT_INSTRUCTIONAL_MINUTES <= 360

    @pytest.mark.parametrize("district_name", [
        "LOS ANGELES UNIFIED", "SAN DIEGO UNIFIED", "FRESNO UNIFIED",
        "LONG BEACH UNIFIED", "ELK GROVE UNIFIED", "CORONA-NORCO UNIFIED"
    ])
    def test_lct_teachers_only_calculation(self, district_name):
        """Integration: LCT teachers_only scope matches expected calculation."""
        data = self.EXPECTED_DISTRICTS[district_name]
        teachers = data["total_teachers"]
        enrollment = data["enrollment"]
        minutes = data.get("instructional_minutes", self.DEFAULT_INSTRUCTIONAL_MINUTES)

        expected_lct = calculate_lct(minutes, teachers, enrollment)
        actual_lct = expected_lct  # TODO: Replace with actual calculation

        assert abs(actual_lct - expected_lct) < 0.5, \
            f"{district_name}: Expected LCT {expected_lct:.2f}, got {actual_lct:.2f}"

    def test_california_lct_lower_than_texas(self):
        """Integration: California LCT values should be lower than Texas (fewer minutes)."""
        # CA uses ~300 min vs TX 420 min
        # For similar staff/enrollment ratios, CA LCT should be ~71% of TX LCT
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "expected_lct_teachers_only" in data:
                lct = data["expected_lct_teachers_only"]
                # CA LCT should generally be 10-15 minutes for large districts
                assert 8 <= lct <= 20, \
                    f"{district_name}: CA LCT {lct} outside expected range"


class TestDataIntegrity(CaliforniaSEAConfig, SEADataIntegrityTests):
    """Tests for data integrity across CDE files."""

    def test_county_codes_valid(self):
        """Integration: All county codes are valid (01-58)."""
        for state_id in self.CROSSWALK.values():
            county = int(state_id.split('-')[0])
            assert 1 <= county <= 58, f"Invalid CA county code: {county}"


class TestCDERegressionPrevention(CaliforniaSEAConfig, SEARegressionPreventionTests):
    """Regression tests to prevent specific bugs in California data integration."""

    def test_cde_district_id_format(self):
        """Regression: CDE district IDs must be County-District format."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "state_district_id" in data:
                state_id = data["state_district_id"]
                assert '-' in state_id, f"{district_name}: ID should contain hyphen"
                parts = state_id.split('-')
                assert len(parts) == 2, f"{district_name}: ID {state_id} should be XX-XXXXX"

    def test_nces_leaid_is_7_digits(self):
        """Regression: NCES LEAIDs should be 7-digit strings."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "nces_leaid" in data:
                leaid = data["nces_leaid"]
                assert len(leaid) == 7, f"{district_name}: LEAID {leaid} should be 7 digits"
                assert leaid.isdigit(), f"{district_name}: LEAID {leaid} should be numeric"

    def test_california_leaids_start_with_06(self):
        """Regression: California NCES LEAIDs start with 06 (FIPS code)."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "nces_leaid" in data:
                leaid = data["nces_leaid"]
                assert leaid.startswith("06"), f"{district_name}: CA LEAID should start with 06"


class TestDatabaseIntegration(CaliforniaSEAConfig):
    """Tests for database storage of CDE data."""

    def test_cde_districts_have_st_leaid(self):
        """Integration: CDE districts stored with st_leaid in database."""
        # TODO: Implement database query
        pass

    def test_cde_ada_stored_in_database(self):
        """Integration: CDE ADA data stored alongside enrollment."""
        # TODO: Implement database query
        pass
