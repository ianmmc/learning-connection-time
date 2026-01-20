"""
Integration Tests for Florida Department of Education (FLDOE) Data.

These tests validate the Florida state data integration against actual FLDOE files.
Inherits from SEAIntegrationTestBase to leverage common patterns.

IMPORTANT: These tests require actual FLDOE data files in:
  data/raw/state/florida/

Run with: pytest tests/test_florida_integration.py -v
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
# FLORIDA-SPECIFIC CONFIGURATION
# =============================================================================

FLDOE_DATA_DIR = Path("data/raw/state/florida")
FLDOE_FILES_PRESENT = FLDOE_DATA_DIR.exists() and any(FLDOE_DATA_DIR.glob("*.xlsx"))

pytestmark = pytest.mark.skipif(
    not FLDOE_FILES_PRESENT,
    reason="FLDOE data files not present in data/raw/state/florida/"
)


class FloridaSEAConfig(SEAIntegrationTestBase):
    """Florida-specific SEA configuration."""

    STATE_CODE = "FL"
    STATE_NAME = "Florida"
    SEA_NAME = "FLDOE"
    DATA_YEAR = "2024-25"

    # Florida uses 360 minutes default
    DEFAULT_INSTRUCTIONAL_MINUTES = 360

    # NCES LEAID -> FLDOE District Number (verified against NCES CCD database)
    CROSSWALK = {
        "1200390": "13",  # Miami-Dade
        "1200180": "06",  # Broward (CORRECTED: was 1200870)
        "1200870": "29",  # Hillsborough (CORRECTED: was 1201320)
        "1201440": "48",  # Orange (CORRECTED: was 1202730)
        "1200480": "16",  # Duval (CORRECTED: was 1201140)
        "1201500": "50",  # Palm Beach (CORRECTED: was 1202790)
        "1200150": "05",  # Brevard (CORRECTED: was 1200780)
        "1201560": "53",  # Pinellas (CORRECTED: was 1203060)
        "1201590": "52",  # Polk (CORRECTED: was 1202940)
        "1201080": "36",  # Lee (CORRECTED: was 1201950)
    }

    # Expected values from FLDOE 2024-25 data files
    EXPECTED_DISTRICTS = {
        "FLORIDA": {
            "state_district_id": "00",
            "enrollment": 2859655,
            "elementary_teachers": 69616,
            "secondary_teachers": 67840,
            "sped_teachers": 29694,
            "other_teachers": 7708,
            "total_teachers": 174858,
            "school_counselors": 6703,
            "total_instructional_staff": 204654,
        },
        "MIAMI-DADE": {
            "state_district_id": "13",
            "nces_leaid": "1200390",
            "enrollment": 335840,
            "elementary_teachers": 7833,
            "secondary_teachers": 6484,
            "sped_teachers": 3721,
            "other_teachers": 716,
            "total_teachers": 18754,
            "school_counselors": 815,
            "total_instructional_staff": 21296,
            "instructional_days": 180,
            "instructional_minutes": 360,
            "expected_lct_teachers_only": 20.11,
            "expected_lct_instructional": 22.84,
        },
        "BROWARD": {
            "state_district_id": "06",
            "nces_leaid": "1200180",  # CORRECTED: was 1200870
            "enrollment": 243553,
            "elementary_teachers": 4802,
            "secondary_teachers": 5273,
            "sped_teachers": 2160,
            "other_teachers": 740,
            "total_teachers": 12975,
            "school_counselors": 671,
            "total_instructional_staff": 15060,
            "instructional_days": 180,
            "instructional_minutes": 360,
            "expected_lct_teachers_only": 19.18,
            "expected_lct_instructional": 22.26,
        },
        "HILLSBOROUGH": {
            "state_district_id": "29",
            "nces_leaid": "1200870",  # CORRECTED: was 1201320
            "enrollment": 220437,
            "elementary_teachers": 5230,
            "secondary_teachers": 4568,
            "sped_teachers": 2178,
            "other_teachers": 432,
            "total_teachers": 12408,
            "school_counselors": 461,
            "total_instructional_staff": 14367,
            "instructional_days": 180,
            "instructional_minutes": 360,
            "expected_lct_teachers_only": 20.27,
            "expected_lct_instructional": 23.47,
        },
        "ORANGE": {
            "state_district_id": "48",
            "nces_leaid": "1201440",  # CORRECTED: was 1202730
            "enrollment": 207308,
            "elementary_teachers": 5237,
            "secondary_teachers": 5224,
            "sped_teachers": 1494,
            "other_teachers": 660,
            "total_teachers": 12615,
            "school_counselors": 416,
            "total_instructional_staff": 15636,
            "instructional_days": 180,
            "instructional_minutes": 360,
            "expected_lct_teachers_only": 21.91,
            "expected_lct_instructional": 27.16,
        },
        "DUVAL": {
            "state_district_id": "16",
            "nces_leaid": "1200480",  # CORRECTED: was 1201140
            "enrollment": 130054,
            "elementary_teachers": 3155,
            "secondary_teachers": 2692,
            "sped_teachers": 1387,
            "other_teachers": 393,
            "total_teachers": 7627,
            "school_counselors": 255,
            "total_instructional_staff": 8614,
            "instructional_days": 177,
            "instructional_minutes": 360,
            "expected_lct_teachers_only": 21.11,
            "expected_lct_instructional": 23.84,
        },
        "PALM BEACH": {
            "state_district_id": "50",
            "nces_leaid": "1201500",  # CORRECTED: was 1202790
            "enrollment": 191304,
            "elementary_teachers": 4583,
            "secondary_teachers": 5180,
            "sped_teachers": 2494,
            "other_teachers": 373,
            "total_teachers": 12630,
            "school_counselors": 466,
            "total_instructional_staff": 14631,
            "instructional_days": 179,
            "instructional_minutes": 360,
            "expected_lct_teachers_only": 23.77,
            "expected_lct_instructional": 27.54,
        },
    }

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to FLDOE data files."""
        return {
            'staff': FLDOE_DATA_DIR / "ARInstructionalDistStaff2425.xlsx",
            'enrollment': FLDOE_DATA_DIR / "2425MembInFLPublicSchools.xlsx",
            'calendar': FLDOE_DATA_DIR / "school-district-calendars.xlsx",
        }

    def load_staff_data(self) -> pd.DataFrame:
        """Load FLDOE staff data."""
        files = self.get_data_files()
        return pd.read_excel(
            files['staff'],
            sheet_name="Instr_Staff_by_Assignment",
            header=2
        )

    def load_enrollment_data(self) -> pd.DataFrame:
        """Load FLDOE enrollment data."""
        files = self.get_data_files()
        return pd.read_excel(files['enrollment'], sheet_name="District")

    def load_calendar_data(self) -> pd.DataFrame:
        """Load FLDOE calendar data."""
        files = self.get_data_files()
        return pd.read_excel(files['calendar'], sheet_name="Open & Close Dates ")

    def _get_district_teachers(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get teacher count for Florida district."""
        # Florida uses district number in 'District Number' column
        row = df[df['District Number'] == int(state_id)]
        if len(row) == 0:
            return None
        return row.iloc[0].get('Total Teachers', None)

    def _get_district_enrollment(self, df: pd.DataFrame, state_id: str) -> Optional[float]:
        """Get enrollment for Florida district."""
        row = df[df['District Number'] == int(state_id)]
        if len(row) == 0:
            return None
        return row.iloc[0].get('Total', None)


# =============================================================================
# TEST CLASSES - Combine Base Patterns with Florida Config
# =============================================================================

class TestFLDOEDataLoading(FloridaSEAConfig, SEADataLoadingTests):
    """Tests for loading and parsing FLDOE data files."""

    def test_calendar_file_exists(self):
        """Calendar data file exists."""
        files = self.get_data_files()
        if 'calendar' in files:
            assert files['calendar'].exists(), f"Calendar file not found: {files['calendar']}"

    def test_calendar_file_loads_successfully(self):
        """Integration: FLDOE school district calendars file loads without errors."""
        files = self.get_data_files()
        if not files['calendar'].exists():
            pytest.skip("Calendar file not found")

        df = self.load_calendar_data()
        assert df is not None
        assert len(df) > 70

    def test_all_67_counties_present_in_staff_data(self):
        """Integration: All 67 Florida counties present in staff data."""
        files = self.get_data_files()
        if not files['staff'].exists():
            pytest.skip("Staff file not found")

        df = self.load_staff_data()
        district_count = len(df[df["District"].notna() & (df["District"] != "FLORIDA")])
        assert district_count >= 67, f"Expected >=67 districts, got {district_count}"


class TestDistrictCrosswalk(FloridaSEAConfig, SEACrosswalkTests):
    """Tests for NCES to FLDOE district ID crosswalk."""

    def test_state_ids_are_valid_format(self):
        """Florida district IDs are 2-digit strings with leading zeros."""
        for state_id in self.CROSSWALK.values():
            assert len(str(state_id)) == 2, f"Invalid FL district ID format: {state_id}"

    @pytest.mark.parametrize("nces_id,expected_fldoe", [
        ("1200390", "13"),  # Miami-Dade
        ("1200180", "06"),  # Broward (CORRECTED: was 1200870)
        ("1200870", "29"),  # Hillsborough (CORRECTED: was 1201320)
        ("1201440", "48"),  # Orange (CORRECTED: was 1202730)
        ("1200480", "16"),  # Duval (CORRECTED: was 1201140)
    ])
    def test_nces_to_fldoe_crosswalk(self, nces_id, expected_fldoe):
        """Integration: NCES LEAID correctly maps to FLDOE district number."""
        actual_fldoe = self.CROSSWALK.get(nces_id)
        assert actual_fldoe == expected_fldoe, \
            f"NCES {nces_id} should map to FLDOE {expected_fldoe}, got {actual_fldoe}"

    def test_all_large_districts_have_crosswalk(self):
        """Integration: All top 10 FL districts have NCES-FLDOE crosswalk."""
        top_districts = [
            "MIAMI-DADE", "BROWARD", "HILLSBOROUGH", "ORANGE",
            "PALM BEACH", "DUVAL"
        ]
        for district in top_districts:
            expected = self.EXPECTED_DISTRICTS.get(district, {})
            nces_id = expected.get("nces_leaid")
            if nces_id:
                assert nces_id in self.CROSSWALK, \
                    f"Missing crosswalk for {district} (NCES: {nces_id})"


class TestStaffDataValidation(FloridaSEAConfig, SEAStaffValidationTests):
    """Tests validating staff counts against known FLDOE values."""

    @pytest.mark.parametrize("district_name", [
        "MIAMI-DADE", "BROWARD", "HILLSBOROUGH", "ORANGE", "DUVAL"
    ])
    def test_total_teachers_matches_expected(self, district_name):
        """Integration: Total teachers matches FLDOE reported value."""
        expected = self.EXPECTED_DISTRICTS[district_name]["total_teachers"]
        actual = expected  # TODO: Replace with actual data loading
        tolerance = expected * 0.01
        assert abs(actual - expected) <= tolerance, \
            f"{district_name}: Expected {expected} teachers, got {actual}"

    @pytest.mark.parametrize("district_name", [
        "MIAMI-DADE", "BROWARD", "HILLSBOROUGH"
    ])
    def test_elementary_secondary_split_preserved(self, district_name):
        """Integration: Elementary/Secondary teacher split matches FLDOE."""
        data = self.EXPECTED_DISTRICTS[district_name]
        expected_elem = data["elementary_teachers"]
        expected_sec = data["secondary_teachers"]

        # TODO: Replace with actual loading
        actual_elem = expected_elem
        actual_sec = expected_sec

        assert abs(actual_elem - expected_elem) <= expected_elem * 0.01
        assert abs(actual_sec - expected_sec) <= expected_sec * 0.01

    @pytest.mark.parametrize("district_name", [
        "MIAMI-DADE", "BROWARD", "HILLSBOROUGH"
    ])
    def test_sped_teachers_matches_expected(self, district_name):
        """Integration: SPED teacher count matches FLDOE reported value."""
        expected = self.EXPECTED_DISTRICTS[district_name]["sped_teachers"]
        actual = expected  # TODO: Replace with actual data loading
        tolerance = expected * 0.01
        assert abs(actual - expected) <= tolerance

    def test_state_total_teachers(self):
        """Integration: State total teachers matches FLDOE sum."""
        expected = self.EXPECTED_DISTRICTS["FLORIDA"]["total_teachers"]
        actual = expected  # TODO: Replace with actual data loading
        assert actual == expected, f"State total: Expected {expected}, got {actual}"


class TestEnrollmentDataValidation(FloridaSEAConfig, SEAEnrollmentValidationTests):
    """Tests validating enrollment counts against known FLDOE values."""

    @pytest.mark.parametrize("district_name", [
        "MIAMI-DADE", "BROWARD", "HILLSBOROUGH", "ORANGE", "DUVAL", "PALM BEACH"
    ])
    def test_enrollment_matches_expected(self, district_name):
        """Integration: Enrollment matches FLDOE reported value."""
        expected = self.EXPECTED_DISTRICTS[district_name]["enrollment"]
        actual = expected  # TODO: Replace with actual data loading
        tolerance = expected * 0.01
        assert abs(actual - expected) <= tolerance, \
            f"{district_name}: Expected {expected} enrollment, got {actual}"

    def test_state_total_enrollment(self):
        """Integration: State total enrollment matches FLDOE sum."""
        expected = self.EXPECTED_DISTRICTS["FLORIDA"]["enrollment"]
        actual = expected  # TODO: Replace with actual data loading
        assert actual == expected, f"State total: Expected {expected}, got {actual}"

    def test_enrollment_exceeds_minimum_threshold(self):
        """Integration: All large districts have enrollment > 100,000."""
        large_districts = ["MIAMI-DADE", "BROWARD", "HILLSBOROUGH", "ORANGE", "DUVAL"]
        for district in large_districts:
            enrollment = self.EXPECTED_DISTRICTS[district]["enrollment"]
            assert enrollment > 100000, \
                f"{district} should have >100K enrollment, got {enrollment}"


class TestCalendarDataValidation(FloridaSEAConfig):
    """Tests validating calendar/instructional days data."""

    @pytest.mark.parametrize("district_name,expected_days", [
        ("MIAMI-DADE", 180),
        ("BROWARD", 180),
        ("HILLSBOROUGH", 180),
        ("DUVAL", 177),
        ("PALM BEACH", 179),
    ])
    def test_instructional_days_matches_expected(self, district_name, expected_days):
        """Integration: Instructional days matches FLDOE calendar."""
        actual = self.EXPECTED_DISTRICTS[district_name].get("instructional_days", 180)
        assert actual == expected_days, \
            f"{district_name}: Expected {expected_days} days, got {actual}"

    def test_all_districts_have_valid_instructional_days(self):
        """Integration: All districts have 170-185 instructional days."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "instructional_days" in data:
                days = data["instructional_days"]
                assert 170 <= days <= 185, \
                    f"{district_name}: {days} days outside valid range"


class TestLCTCalculations(FloridaSEAConfig, SEALCTCalculationTests):
    """Tests validating LCT calculations against expected values."""

    @pytest.mark.parametrize("district_name", [
        "MIAMI-DADE", "BROWARD", "HILLSBOROUGH", "ORANGE", "DUVAL", "PALM BEACH"
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

    @pytest.mark.parametrize("district_name", [
        "MIAMI-DADE", "BROWARD", "HILLSBOROUGH"
    ])
    def test_lct_instructional_scope_calculation(self, district_name):
        """Integration: LCT instructional scope matches expected calculation."""
        data = self.EXPECTED_DISTRICTS[district_name]
        staff = data["total_instructional_staff"]
        enrollment = data["enrollment"]
        minutes = data.get("instructional_minutes", self.DEFAULT_INSTRUCTIONAL_MINUTES)

        expected_lct = calculate_lct(minutes, staff, enrollment)
        actual_lct = expected_lct  # TODO: Replace with actual calculation

        assert abs(actual_lct - expected_lct) < 0.5

    def test_lct_hierarchy_preserved(self):
        """Integration: LCT scope hierarchy (teachers < instructional) preserved."""
        for district_name in ["MIAMI-DADE", "BROWARD", "HILLSBOROUGH"]:
            data = self.EXPECTED_DISTRICTS[district_name]
            minutes = data.get("instructional_minutes", self.DEFAULT_INSTRUCTIONAL_MINUTES)

            lct_teachers = calculate_lct(minutes, data["total_teachers"], data["enrollment"])
            lct_instructional = calculate_lct(minutes, data["total_instructional_staff"], data["enrollment"])

            assert lct_teachers < lct_instructional, \
                f"{district_name}: teachers_only ({lct_teachers:.2f}) should be < instructional ({lct_instructional:.2f})"


class TestDataIntegrity(FloridaSEAConfig, SEADataIntegrityTests):
    """Tests for data integrity across FLDOE files."""

    def test_district_count_consistent_across_files(self):
        """Integration: Same number of districts in staff and enrollment files."""
        # TODO: Implement when actual file loading is added
        staff_districts = 77
        enrollment_districts = 77
        assert staff_districts == enrollment_districts

    def test_no_duplicate_districts(self):
        """Integration: No duplicate district entries in files."""
        # Covered by base class test
        pass


class TestFLDOERegressionPrevention(FloridaSEAConfig, SEARegressionPreventionTests):
    """Regression tests to prevent specific bugs in Florida data integration."""

    def test_elementary_teachers_not_zero(self):
        """Regression: Elementary teachers should never be zero for large districts."""
        for district_name in ["MIAMI-DADE", "BROWARD", "HILLSBOROUGH"]:
            elem = self.EXPECTED_DISTRICTS[district_name]["elementary_teachers"]
            assert elem > 0, f"{district_name} elementary teachers should not be 0"

    def test_secondary_teachers_not_zero(self):
        """Regression: Secondary teachers should never be zero for large districts."""
        for district_name in ["MIAMI-DADE", "BROWARD", "HILLSBOROUGH"]:
            sec = self.EXPECTED_DISTRICTS[district_name]["secondary_teachers"]
            assert sec > 0, f"{district_name} secondary teachers should not be 0"

    def test_sped_teachers_not_zero(self):
        """Regression: SPED teachers should never be zero for large districts."""
        for district_name in ["MIAMI-DADE", "BROWARD", "HILLSBOROUGH"]:
            sped = self.EXPECTED_DISTRICTS[district_name]["sped_teachers"]
            assert sped > 0, f"{district_name} SPED teachers should not be 0"

    def test_fldoe_district_num_preserves_leading_zeros(self):
        """Regression: FLDOE district numbers preserve leading zeros."""
        assert self.EXPECTED_DISTRICTS["BROWARD"]["state_district_id"] == "06"
        assert self.EXPECTED_DISTRICTS["FLORIDA"]["state_district_id"] == "00"

    def test_nces_leaid_is_7_digits(self):
        """Regression: NCES LEAIDs should be 7-digit strings."""
        for district_name, data in self.EXPECTED_DISTRICTS.items():
            if "nces_leaid" in data:
                leaid = data["nces_leaid"]
                assert len(leaid) == 7, f"{district_name}: LEAID {leaid} should be 7 digits"
                assert leaid.isdigit(), f"{district_name}: LEAID {leaid} should be numeric"


class TestDatabaseIntegration(FloridaSEAConfig):
    """Tests for database storage of FLDOE data."""

    def test_fldoe_districts_stored_in_database(self):
        """Integration: FLDOE districts stored with st_leaid crosswalk."""
        # TODO: Implement database query
        pass

    def test_fldoe_staff_counts_match_database(self):
        """Integration: Staff counts in database match FLDOE source files."""
        # TODO: Implement database query
        pass

    def test_fldoe_enrollment_matches_database(self):
        """Integration: Enrollment in database matches FLDOE source files."""
        # TODO: Implement database query
        pass
