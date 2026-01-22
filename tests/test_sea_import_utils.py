"""
Tests for SEA Import Utilities.

Tests the shared utility functions used across FL, NY, IL integrations.
"""

import pytest
import pandas as pd
import numpy as np
from infrastructure.database.migrations.sea_import_utils import (
    safe_float, safe_int, safe_pct,
    format_state_id, get_state_id_info, SEA_ID_FORMATS,
    validate_enrollment_staff_ratio, is_sped_intensive,
    is_covid_year, validate_data_year,
    COVID_EXCLUDED_YEARS, VALID_DATA_YEARS,
    SUPPRESSED_VALUES,
)


# =============================================================================
# SAFE VALUE CONVERSION TESTS
# =============================================================================

class TestSafeFloat:
    """Tests for safe_float() function."""

    def test_numeric_values(self):
        """Normal numeric values convert correctly."""
        assert safe_float(42) == 42.0
        assert safe_float(42.5) == 42.5
        assert safe_float("42.5") == 42.5
        assert safe_float(0) == 0.0

    def test_suppressed_values_return_none(self):
        """Suppressed values return None."""
        for val in SUPPRESSED_VALUES:
            if val is not None:  # None tested separately
                assert safe_float(val) is None, f"Expected None for '{val}'"

    def test_none_returns_none(self):
        """None returns None."""
        assert safe_float(None) is None

    def test_nan_returns_none(self):
        """NaN returns None."""
        assert safe_float(np.nan) is None
        assert safe_float(float('nan')) is None

    def test_pandas_na_returns_none(self):
        """Pandas NA/NaT returns None."""
        assert safe_float(pd.NA) is None
        assert safe_float(pd.NaT) is None

    def test_whitespace_suppressed_values(self):
        """Values with whitespace still detected."""
        assert safe_float(" * ") is None
        assert safe_float("  -  ") is None
        assert safe_float("   ") is None

    def test_invalid_strings_return_none(self):
        """Non-numeric strings return None."""
        assert safe_float("abc") is None
        assert safe_float("not a number") is None

    def test_negative_values(self):
        """Negative values convert correctly."""
        assert safe_float(-42.5) == -42.5
        assert safe_float("-42.5") == -42.5


class TestSafeInt:
    """Tests for safe_int() function."""

    def test_integer_values(self):
        """Integer values convert correctly."""
        assert safe_int(42) == 42
        assert safe_int("42") == 42

    def test_float_values_truncate(self):
        """Float values truncate to integer."""
        assert safe_int(42.7) == 42
        assert safe_int(42.1) == 42
        assert safe_int("42.9") == 42

    def test_suppressed_values_return_none(self):
        """Suppressed values return None."""
        assert safe_int("*") is None
        assert safe_int("-") is None
        assert safe_int("") is None

    def test_none_and_nan_return_none(self):
        """None and NaN return None."""
        assert safe_int(None) is None
        assert safe_int(np.nan) is None


class TestSafePct:
    """Tests for safe_pct() function."""

    def test_percentage_values(self):
        """Percentage values convert correctly."""
        assert safe_pct(75.5) == 75.5
        assert safe_pct("75.5") == 75.5

    def test_decimal_conversion(self):
        """as_decimal=True divides by 100."""
        assert safe_pct(75.5, as_decimal=True) == 0.755
        assert safe_pct(100, as_decimal=True) == 1.0
        assert safe_pct(0, as_decimal=True) == 0.0

    def test_suppressed_values(self):
        """Suppressed values return None."""
        assert safe_pct("*") is None
        assert safe_pct("*", as_decimal=True) is None


# =============================================================================
# STATE ID FORMAT TESTS
# =============================================================================

class TestFormatStateId:
    """Tests for format_state_id() and SEA_ID_FORMATS."""

    def test_florida_format(self):
        """Florida 2-digit county codes."""
        assert format_state_id('FL', 13) == '13'
        assert format_state_id('FL', '13') == '13'
        assert format_state_id('FL', 1) == '01'  # Zero-padded

    def test_illinois_rcdts_format(self):
        """Illinois RCDTS 15-digit to formatted."""
        # Chicago: 150162990250000 -> 15-016-2990-25
        assert format_state_id('IL', '150162990250000') == '15-016-2990-25'

    def test_new_york_beds_format(self):
        """New York BEDS codes."""
        assert format_state_id('NY', 310200010000) == '310200010000'
        assert format_state_id('NY', '310200010000') == '310200010000'

    def test_texas_format(self):
        """Texas district numbers."""
        assert format_state_id('TX', '101912') == '101912'
        assert format_state_id('TX', 101912) == '101912'

    def test_california_format(self):
        """California county-district codes."""
        assert format_state_id('CA', '19-64733') == '19-64733'

    def test_unknown_state_uses_default(self):
        """Unknown states use default string conversion."""
        assert format_state_id('XX', '12345') == '12345'
        assert format_state_id('ZZ', 12345) == '12345'

    def test_sea_id_formats_has_required_keys(self):
        """SEA_ID_FORMATS entries have required keys."""
        for state, info in SEA_ID_FORMATS.items():
            assert 'name' in info, f"{state} missing 'name'"
            assert 'format' in info, f"{state} missing 'format'"
            assert 'example' in info, f"{state} missing 'example'"
            assert 'converter' in info, f"{state} missing 'converter'"
            assert callable(info['converter']), f"{state} converter not callable"


class TestGetStateIdInfo:
    """Tests for get_state_id_info() function."""

    def test_known_states_return_info(self):
        """Known states return full info."""
        for state in ['FL', 'NY', 'IL', 'TX', 'CA']:
            info = get_state_id_info(state)
            assert 'name' in info
            assert 'format' in info
            assert 'example' in info
            assert info['format'] != 'Unknown'

    def test_unknown_states_return_defaults(self):
        """Unknown states return default info."""
        info = get_state_id_info('XX')
        assert info['format'] == 'Unknown'
        assert info['example'] == 'N/A'


# =============================================================================
# VALIDATION HELPER TESTS
# =============================================================================

class TestValidateEnrollmentStaffRatio:
    """Tests for validate_enrollment_staff_ratio() function."""

    def test_valid_ratios(self):
        """Valid ratios return True."""
        assert validate_enrollment_staff_ratio(1000, 50) is True  # 20:1
        assert validate_enrollment_staff_ratio(500, 25) is True   # 20:1
        assert validate_enrollment_staff_ratio(2000, 40) is True  # 50:1

    def test_ratio_too_low(self):
        """Ratios below minimum return False."""
        assert validate_enrollment_staff_ratio(50, 20) is False  # 2.5:1

    def test_ratio_too_high(self):
        """Ratios above maximum return False."""
        assert validate_enrollment_staff_ratio(5000, 10) is False  # 500:1

    def test_none_values(self):
        """None values return False."""
        assert validate_enrollment_staff_ratio(None, 50) is False
        assert validate_enrollment_staff_ratio(1000, None) is False
        assert validate_enrollment_staff_ratio(None, None) is False

    def test_zero_values(self):
        """Zero values return False."""
        assert validate_enrollment_staff_ratio(0, 50) is False
        assert validate_enrollment_staff_ratio(1000, 0) is False

    def test_custom_thresholds(self):
        """Custom min/max ratios work."""
        # 4:1 ratio with min=3, max=5
        assert validate_enrollment_staff_ratio(400, 100, min_ratio=3, max_ratio=5) is True
        # 4:1 ratio with min=5 should fail
        assert validate_enrollment_staff_ratio(400, 100, min_ratio=5, max_ratio=10) is False


class TestIsSpedIntensive:
    """Tests for is_sped_intensive() function."""

    def test_normal_districts(self):
        """Normal districts (>10:1 ratio) return False."""
        assert is_sped_intensive(2000, 100) is False  # 20:1
        assert is_sped_intensive(1500, 100) is False  # 15:1
        assert is_sped_intensive(1000, 100) is False  # 10:1 (at threshold)

    def test_sped_intensive_districts(self):
        """SPED-intensive districts (<10:1 ratio) return True."""
        assert is_sped_intensive(800, 100) is True   # 8:1
        assert is_sped_intensive(500, 100) is True   # 5:1
        assert is_sped_intensive(300, 100) is True   # 3:1

    def test_none_and_zero_values(self):
        """None and zero values return False."""
        assert is_sped_intensive(None, 100) is False
        assert is_sped_intensive(1000, None) is False
        assert is_sped_intensive(0, 100) is False
        assert is_sped_intensive(1000, 0) is False

    def test_custom_threshold(self):
        """Custom threshold works."""
        # 8:1 ratio
        assert is_sped_intensive(800, 100, threshold=10) is True  # Below 10
        assert is_sped_intensive(800, 100, threshold=5) is False  # Above 5


# =============================================================================
# COVID YEAR VALIDATION TESTS
# =============================================================================

class TestCovidYearValidation:
    """Tests for COVID year validation functions."""

    def test_covid_years_detected(self):
        """COVID years are correctly identified."""
        for year in COVID_EXCLUDED_YEARS:
            assert is_covid_year(year) is True, f"Expected {year} to be COVID year"

    def test_valid_years_not_covid(self):
        """Valid years are not flagged as COVID."""
        for year in ['2018-19', '2023-24', '2024-25', '2025-26']:
            assert is_covid_year(year) is False, f"Expected {year} to NOT be COVID year"

    def test_validate_data_year(self):
        """validate_data_year returns True for non-COVID years."""
        assert validate_data_year('2023-24') is True
        assert validate_data_year('2024-25') is True
        assert validate_data_year('2018-19') is True

    def test_validate_data_year_rejects_covid(self):
        """validate_data_year returns False for COVID years."""
        for year in COVID_EXCLUDED_YEARS:
            assert validate_data_year(year) is False


# =============================================================================
# SUPPRESSED VALUES CONSTANT TESTS
# =============================================================================

class TestSuppressedValues:
    """Tests for SUPPRESSED_VALUES constant."""

    def test_common_suppressed_values_included(self):
        """Common suppressed values are in the tuple."""
        assert '*' in SUPPRESSED_VALUES
        assert '-' in SUPPRESSED_VALUES
        assert '' in SUPPRESSED_VALUES
        assert 'N/A' in SUPPRESSED_VALUES
        assert None in SUPPRESSED_VALUES

    def test_suppressed_values_is_tuple(self):
        """SUPPRESSED_VALUES is a tuple (immutable)."""
        assert isinstance(SUPPRESSED_VALUES, tuple)
