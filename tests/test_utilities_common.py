"""infrastructure/utilities/common.py helpers — state normalization, safe math, formatting,
DataFrame validation.

Salvaged 2026-07-14 (epic #481 sweep) from the orphaned infrastructure/quality-assurance/tests/
test_utilities.py, which was NEVER collected (pytest.ini testpaths=tests) and could not import
anyway — its sys.path shim resolved to infrastructure/infrastructure/utilities (crossfam #295).
Imports fixed to the proper package path (REQ-098 editable install). The original file's
TestLCTCalculation class was dropped, not salvaged: it evaluated an inline formula against
hard-coded expectations, validating Python arithmetic rather than any production function
(crossfam #296/#374) — the REAL LCT function is covered by tests/test_lct_calculation.py.
"""
import pandas as pd

from infrastructure.utilities.common import (
    format_number,
    get_state_name,
    safe_divide,
    standardize_state,
    validate_required_columns,
)


class TestStateStandardization:
    def test_standardize_state_full_name(self):
        assert standardize_state('California') == 'CA'
        assert standardize_state('New York') == 'NY'
        assert standardize_state('texas') == 'TX'

    def test_standardize_state_abbreviation(self):
        assert standardize_state('CA') == 'CA'
        assert standardize_state('ca') == 'CA'
        assert standardize_state('NY') == 'NY'

    def test_standardize_state_invalid(self):
        assert standardize_state('Invalid State') is None
        assert standardize_state('XX') is None
        assert standardize_state('') is None
        assert standardize_state(None) is None

    def test_get_state_name(self):
        assert get_state_name('CA') == 'California'
        assert get_state_name('NY') == 'New York'
        assert get_state_name('ca') == 'California'

    def test_get_state_name_invalid(self):
        assert get_state_name('XX') is None
        assert get_state_name('') is None
        assert get_state_name(None) is None


class TestSafeDivide:
    def test_safe_divide_normal(self):
        assert safe_divide(10, 2) == 5.0
        assert safe_divide(100, 4) == 25.0

    def test_safe_divide_by_zero(self):
        assert safe_divide(10, 0) == 0.0
        assert safe_divide(10, 0, default=999) == 999

    def test_safe_divide_with_nan(self):
        assert safe_divide(float('nan'), 2) == 0.0
        assert safe_divide(10, float('nan')) == 0.0
        assert safe_divide(float('nan'), float('nan')) == 0.0

    def test_safe_divide_custom_default(self):
        assert safe_divide(10, 0, default=-1) == -1
        assert safe_divide(float('nan'), 2, default=100) == 100


class TestFormatNumber:
    def test_format_number_integer(self):
        assert format_number(1234567) == '1,234,567'
        assert format_number(1000) == '1,000'
        assert format_number(100) == '100'

    def test_format_number_with_decimals(self):
        assert format_number(1234.567, 2) == '1,234.57'
        assert format_number(1000.1, 1) == '1,000.1'

    def test_format_number_nan(self):
        assert format_number(float('nan')) == 'N/A'


class TestValidateRequiredColumns:
    def test_validate_all_present(self):
        df = pd.DataFrame({'col1': [1, 2], 'col2': [3, 4], 'col3': [5, 6]})
        assert validate_required_columns(df, ['col1', 'col2'], 'test')
        assert validate_required_columns(df, ['col1'], 'test')

    def test_validate_missing_columns(self):
        df = pd.DataFrame({'col1': [1, 2], 'col2': [3, 4]})
        assert not validate_required_columns(df, ['col1', 'col3'], 'test')
        assert not validate_required_columns(df, ['missing'], 'test')

    def test_validate_empty_requirements(self):
        df = pd.DataFrame({'col1': [1, 2]})
        assert validate_required_columns(df, [], 'test')
