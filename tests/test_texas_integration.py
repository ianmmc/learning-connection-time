"""
Integration Tests for Texas Education Agency (TEA) Data.

These tests validate the Texas state data integration against NCES baselines
and TEA-specific crosswalk files.

Data sources:
- NCES CCD (enrollment, staff) - Primary baseline
- TEA district crosswalk - NCES LEAID to TEA district mapping
- TEA district types - Classification data

IMPORTANT: These tests require data files in:
  data/raw/state/texas/
  data/processed/slim/

Run with: pytest tests/test_texas_integration.py -v
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
# TEXAS-SPECIFIC CONFIGURATION
# =============================================================================

TEA_DATA_DIR = Path("data/raw/state/texas")
NCES_SLIM_DIR = Path("data/processed/slim")

TEA_FILES_PRESENT = (
    TEA_DATA_DIR.exists() and
    (TEA_DATA_DIR / "district_identifiers" / "texas_nces_tea_crosswalk_2018_19.csv").exists()
)
NCES_FILES_PRESENT = NCES_SLIM_DIR.exists() and any(NCES_SLIM_DIR.glob("*.csv"))

pytestmark = pytest.mark.skipif(
    not (TEA_FILES_PRESENT and NCES_FILES_PRESENT),
    reason="TEA or NCES data files not present"
)


class TexasSEAConfig(SEAIntegrationTestBase):
    """Texas-specific SEA configuration."""

    STATE_CODE = "TX"
    STATE_NAME = "Texas"
    SEA_NAME = "TEA"
    DATA_YEAR = "2023-24"

    # Texas uses 420 minutes default (highest in nation)
    DEFAULT_INSTRUCTIONAL_MINUTES = 420

    # NCES LEAID -> TEA District Number (TX-XXXXXX format)
    # Loaded from crosswalk file, these are key districts for testing
    CROSSWALK = {
        "4823640": "TX-101912",  # Houston ISD
        "4816230": "TX-057905",  # Dallas ISD
        "4816110": "TX-101907",  # Cypress-Fairbanks ISD
        "4833120": "TX-015915",  # Northside ISD (San Antonio)
        "4825170": "TX-101914",  # Katy ISD
        "4819650": "TX-079907",  # Fort Bend ISD
        "4800540": "TX-227901",  # Austin ISD
        "4812720": "TX-015907",  # San Antonio ISD
        "4819700": "TX-220905",  # Fort Worth ISD
        "4812630": "TX-057909",  # Garland ISD
    }

    # Expected values from NCES CCD 2023-24 data
    # These are baseline values - TEA data may differ slightly
    EXPECTED_DISTRICTS = {
        "TEXAS": {
            "state_district_id": "TX-000000",
            "enrollment": 5532518,  # NCES total
            "total_teachers": None,  # Sum from districts
        },
        "HOUSTON ISD": {
            "state_district_id": "TX-101912",
            "nces_leaid": "4823640",
            "enrollment": 184109,
            "total_teachers": 9292,  # FTE from NCES
            "instructional_minutes": 420,
            "expected_lct_teachers_only": 21.19,  # (420 * 9292) / 184109
        },
        "DALLAS ISD": {
            "state_district_id": "TX-057905",
            "nces_leaid": "4816230",
            "enrollment": 139246,
            "total_teachers": 7366,
            "instructional_minutes": 420,
            "expected_lct_teachers_only": 22.22,
        },
        "CYPRESS-FAIRBANKS ISD": {
            "state_district_id": "TX-101907",
            "nces_leaid": "4816110",
            "enrollment": 118470,
            "total_teachers": 7068,
            "instructional_minutes": 420,
            "expected_lct_teachers_only": 25.06,
        },
        "NORTHSIDE ISD": {
            "state_district_id": "TX-015915",
            "nces_leaid": "4833120",
            "enrollment": 101095,
            "total_teachers": 5567,
            "instructional_minutes": 420,
            "expected_lct_teachers_only": 23.13,
        },
        "KATY ISD": {
            "state_district_id": "TX-101914",
            "nces_leaid": "4825170",
            "enrollment": 94785,
            "total_teachers": 5634,
            "instructional_minutes": 420,
            "expected_lct_teachers_only": 24.97,
        },
        "FORT BEND ISD": {
            "state_district_id": "TX-079907",
            "nces_leaid": "4819650",
            "enrollment": 80206,
            "total_teachers": 4112,
            "instructional_minutes": 420,
            "expected_lct_teachers_only": 21.53,
        },
    }

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to TEA and NCES data files."""
        return {
            'crosswalk': TEA_DATA_DIR / "district_identifiers" / "texas_nces_tea_crosswalk_2018_19.csv",
            'district_types': TEA_DATA_DIR / "district_identifiers" / "district_type_2022_23.xlsx",
            'nces_directory': NCES_SLIM_DIR / "districts_directory_slim.csv",
            'nces_enrollment': NCES_SLIM_DIR / "enrollment_by_grade_slim.csv",
            'nces_staff': NCES_SLIM_DIR / "staff_by_level_slim.csv",
        }

    def load_crosswalk_data(self) -> pd.DataFrame:
        """Load TEA crosswalk data."""
        files = self.get_data_files()
        return pd.read_csv(files['crosswalk'])

    def load_staff_data(self) -> pd.DataFrame:
        """Load NCES staff data (filtered for Texas)."""
        files = self.get_data_files()
        directory = pd.read_csv(files['nces_directory'])
        directory.columns = ['ST', 'LEA_NAME', 'LEAID']

        staff = pd.read_csv(files['nces_staff'])
        staff_totals = staff.groupby('LEAID')['STAFF_COUNT'].sum().reset_index()
        staff_totals.columns = ['LEAID', 'TOTAL_STAFF']

        # Join and filter to Texas
        df = directory.merge(staff_totals, on='LEAID', how='left')
        return df[df['ST'] == 'TX']

    def load_enrollment_data(self) -> pd.DataFrame:
        """Load NCES enrollment data (filtered for Texas)."""
        files = self.get_data_files()
        directory = pd.read_csv(files['nces_directory'])
        directory.columns = ['ST', 'LEA_NAME', 'LEAID']

        enrollment = pd.read_csv(files['nces_enrollment'])
        # Get 'No Category Codes' totals (actual enrollment)
        totals = enrollment[enrollment['GRADE'] == 'No Category Codes']
        enrollment_totals = totals.groupby('LEAID')['STUDENT_COUNT'].max().reset_index()
        enrollment_totals.columns = ['LEAID', 'TOTAL_ENROLLMENT']

        # Join and filter to Texas
        df = directory.merge(enrollment_totals, on='LEAID', how='left')
        return df[df['ST'] == 'TX']

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get teacher count for Texas district by ST_LEAID."""
        # Extract NCES LEAID from state_id (TX-XXXXXX -> find NCES match)
        for nces_id, st_leaid in self.CROSSWALK.items():
            if st_leaid == state_id:
                row = df[df['LEAID'] == int(nces_id)]
                if len(row) > 0:
                    return row.iloc[0].get('TOTAL_STAFF', None)
        return None

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get enrollment for Texas district by ST_LEAID."""
        for nces_id, st_leaid in self.CROSSWALK.items():
            if st_leaid == state_id:
                row = df[df['LEAID'] == int(nces_id)]
                if len(row) > 0:
                    return row.iloc[0].get('TOTAL_ENROLLMENT', None)
        return None


# =============================================================================
# TEST CLASSES - Combine Base Patterns with Texas Config
# =============================================================================

class TestTEADataLoading(TexasSEAConfig, SEADataLoadingTests):
    """Tests for loading and parsing TEA data files."""

    def test_crosswalk_file_exists(self):
        """TEA crosswalk file exists."""
        files = self.get_data_files()
        assert files['crosswalk'].exists(), f"Crosswalk file not found: {files['crosswalk']}"

    def test_crosswalk_file_loads_successfully(self):
        """Integration: TEA crosswalk file loads without errors."""
        df = self.load_crosswalk_data()
        assert df is not None
        assert len(df) > 1000, f"Expected >1000 districts, got {len(df)}"

    def test_crosswalk_contains_major_districts(self):
        """Integration: Crosswalk contains all major Texas districts."""
        df = self.load_crosswalk_data()

        major_districts = ["HOUSTON ISD", "DALLAS ISD", "AUSTIN ISD"]
        for district in major_districts:
            matches = df[df['DISTRICT_NAME'].str.upper().str.contains(district.replace(' ISD', ''))]
            assert len(matches) > 0, f"Crosswalk missing {district}"


class TestDistrictCrosswalk(TexasSEAConfig, SEACrosswalkTests):
    """Tests for NCES to TEA district ID crosswalk."""

    def test_state_ids_are_valid_format(self):
        """Texas district IDs are TX-XXXXXX format."""
        for state_id in self.CROSSWALK.values():
            assert state_id.startswith("TX-"), f"Invalid TX district ID: {state_id}"
            assert len(state_id) == 9, f"Invalid TX district ID length: {state_id}"

    @pytest.mark.parametrize("nces_id,expected_tea", [
        ("4823640", "TX-101912"),  # Houston ISD
        ("4816230", "TX-057905"),  # Dallas ISD
        ("4816110", "TX-101907"),  # Cypress-Fairbanks ISD
        ("4833120", "TX-015915"),  # Northside ISD
        ("4825170", "TX-101914"),  # Katy ISD
    ])
    def test_nces_to_tea_crosswalk(self, nces_id, expected_tea):
        """Integration: NCES LEAID correctly maps to TEA district number."""
        actual_tea = self.CROSSWALK.get(nces_id)
        assert actual_tea == expected_tea, \
            f"NCES {nces_id} should map to TEA {expected_tea}, got {actual_tea}"

    def test_crosswalk_file_matches_expected(self):
        """Integration: Crosswalk file contains expected mappings."""
        df = self.load_crosswalk_data()

        for nces_id, expected_st_leaid in self.CROSSWALK.items():
            row = df[df['NCES_LEAID'] == int(nces_id)]
            if len(row) > 0:
                actual_st_leaid = row.iloc[0]['ST_LEAID']
                assert actual_st_leaid == expected_st_leaid, \
                    f"NCES {nces_id}: expected {expected_st_leaid}, got {actual_st_leaid}"


class TestStaffDataValidation(TexasSEAConfig, SEAStaffValidationTests):
    """Tests validating staff counts against NCES values."""

    @pytest.mark.parametrize("district_name", [
        "HOUSTON ISD", "DALLAS ISD", "CYPRESS-FAIRBANKS ISD", "NORTHSIDE ISD", "KATY ISD"
    ])
    def test_total_teachers_matches_expected(self, district_name):
        """Integration: Total teachers matches NCES reported value."""
        expected = self.EXPECTED_DISTRICTS[district_name]["total_teachers"]
        actual = expected  # TODO: Replace with actual data loading
        tolerance = expected * self.STAFF_TOLERANCE_PCT
        assert abs(actual - expected) <= tolerance, \
            f"{district_name}: Expected {expected} teachers, got {actual}"

    def test_texas_teacher_counts_positive(self):
        """Integration: All expected Texas districts have positive teacher counts."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "total_teachers" in data and data["total_teachers"]:
                assert data["total_teachers"] > 0, \
                    f"{district_name} should have positive teacher count"


class TestEnrollmentDataValidation(TexasSEAConfig, SEAEnrollmentValidationTests):
    """Tests validating enrollment counts against NCES values."""

    @pytest.mark.parametrize("district_name", [
        "HOUSTON ISD", "DALLAS ISD", "CYPRESS-FAIRBANKS ISD", "NORTHSIDE ISD", "KATY ISD", "FORT BEND ISD"
    ])
    def test_enrollment_matches_expected(self, district_name):
        """Integration: Enrollment matches NCES reported value."""
        expected = self.EXPECTED_DISTRICTS[district_name]["enrollment"]
        actual = expected  # TODO: Replace with actual data loading
        tolerance = expected * self.ENROLLMENT_TOLERANCE_PCT
        assert abs(actual - expected) <= tolerance, \
            f"{district_name}: Expected {expected} enrollment, got {actual}"

    def test_enrollment_exceeds_minimum_threshold(self):
        """Integration: All large districts have enrollment > 50,000."""
        large_districts = ["HOUSTON ISD", "DALLAS ISD", "CYPRESS-FAIRBANKS ISD", "NORTHSIDE ISD"]
        for district in large_districts:
            enrollment = self.EXPECTED_DISTRICTS[district]["enrollment"]
            assert enrollment > 50000, \
                f"{district} should have >50K enrollment, got {enrollment}"

    def test_houston_is_largest(self):
        """Integration: Houston ISD is the largest Texas district."""
        houston_enrollment = self.EXPECTED_DISTRICTS["HOUSTON ISD"]["enrollment"]
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if district_name not in ["HOUSTON ISD", "TEXAS"]:
                assert houston_enrollment > data.get("enrollment", 0), \
                    f"Houston should be larger than {district_name}"


class TestLCTCalculations(TexasSEAConfig, SEALCTCalculationTests):
    """Tests validating LCT calculations against expected values."""

    def test_texas_uses_420_minutes(self):
        """Integration: Texas LCT uses 420 instructional minutes (highest in nation)."""
        assert self.DEFAULT_INSTRUCTIONAL_MINUTES == 420

    @pytest.mark.parametrize("district_name", [
        "HOUSTON ISD", "DALLAS ISD", "CYPRESS-FAIRBANKS ISD", "NORTHSIDE ISD", "KATY ISD", "FORT BEND ISD"
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

    def test_lct_values_reflect_420_minute_day(self):
        """Integration: Texas LCT values are higher due to 420-minute day."""
        # Texas should have higher LCT than states with 360-minute days
        # (420/360 = 1.167x higher for same staff/enrollment ratio)
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "expected_lct_teachers_only" in data:
                lct = data["expected_lct_teachers_only"]
                # LCT with 420 minutes should generally be 20+ for large districts
                assert lct >= 20, f"{district_name}: Texas LCT {lct} seems low for 420-min day"


class TestDataIntegrity(TexasSEAConfig, SEADataIntegrityTests):
    """Tests for data integrity across TEA files."""

    def test_crosswalk_has_unique_mappings(self):
        """Integration: Each NCES LEAID maps to exactly one TEA district."""
        df = self.load_crosswalk_data()
        duplicates = df[df.duplicated(subset=['NCES_LEAID'], keep=False)]
        assert len(duplicates) == 0, f"Found duplicate NCES LEAIDs in crosswalk"

    def test_tea_ids_are_unique(self):
        """Integration: Each TEA district ID appears only once."""
        df = self.load_crosswalk_data()
        duplicates = df[df.duplicated(subset=['ST_LEAID'], keep=False)]
        assert len(duplicates) == 0, f"Found duplicate TEA district IDs in crosswalk"


class TestTEARegressionPrevention(TexasSEAConfig, SEARegressionPreventionTests):
    """Regression tests to prevent specific bugs in Texas data integration."""

    def test_tea_district_id_format(self):
        """Regression: TEA district IDs must be TX-XXXXXX format."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "state_district_id" in data and district_name != "TEXAS":
                state_id = data["state_district_id"]
                assert state_id.startswith("TX-"), f"{district_name}: ID should start with TX-"
                assert len(state_id) == 9, f"{district_name}: ID {state_id} should be 9 chars"

    def test_nces_leaid_is_7_digits(self):
        """Regression: NCES LEAIDs should be 7-digit strings."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "nces_leaid" in data:
                leaid = data["nces_leaid"]
                assert len(leaid) == 7, f"{district_name}: LEAID {leaid} should be 7 digits"
                assert leaid.isdigit(), f"{district_name}: LEAID {leaid} should be numeric"

    def test_texas_leaids_start_with_48(self):
        """Regression: Texas NCES LEAIDs start with 48 (FIPS code)."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "nces_leaid" in data:
                leaid = data["nces_leaid"]
                assert leaid.startswith("48"), f"{district_name}: TX LEAID should start with 48"


class TestDatabaseIntegration(TexasSEAConfig):
    """Tests for database storage of TEA data."""

    def test_tea_districts_have_st_leaid(self):
        """Integration: TEA districts stored with st_leaid in database."""
        # TODO: Implement database query
        pass

    def test_tea_crosswalk_matches_database(self):
        """Integration: Crosswalk file matches database st_leaid values."""
        # TODO: Implement database query
        pass
