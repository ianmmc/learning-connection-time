"""
Tests for utility functions

Run with: pytest test_utilities.py
"""

import pytest
import pandas as pd
from pathlib import Path
import sys

# Add utilities to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "infrastructure" / "utilities"))
from common import (
    standardize_state,
    get_state_name,
    safe_divide,
    format_number,
    validate_required_columns
)


class TestStateStandardization:
    """Tests for state name/abbreviation functions"""
    
    def test_standardize_state_full_name(self):
        """Test standardization of full state names"""
        assert standardize_state('California') == 'CA'
        assert standardize_state('New York') == 'NY'
        assert standardize_state('texas') == 'TX'
    
    def test_standardize_state_abbreviation(self):
        """Test that abbreviations pass through correctly"""
        assert standardize_state('CA') == 'CA'
        assert standardize_state('ca') == 'CA'
        assert standardize_state('NY') == 'NY'
    
    def test_standardize_state_invalid(self):
        """Test handling of invalid inputs"""
        assert standardize_state('Invalid State') is None
        assert standardize_state('XX') is None
        assert standardize_state('') is None
        assert standardize_state(None) is None
    
    def test_get_state_name(self):
        """Test retrieving full state names"""
        assert get_state_name('CA') == 'California'
        assert get_state_name('NY') == 'New York'
        assert get_state_name('ca') == 'California'  # Should handle lowercase
    
    def test_get_state_name_invalid(self):
        """Test handling of invalid abbreviations"""
        assert get_state_name('XX') is None
        assert get_state_name('') is None
        assert get_state_name(None) is None


class TestSafeDivide:
    """Tests for safe division function"""
    
    def test_safe_divide_normal(self):
        """Test normal division"""
        assert safe_divide(10, 2) == 5.0
        assert safe_divide(100, 4) == 25.0
    
    def test_safe_divide_by_zero(self):
        """Test division by zero returns default"""
        assert safe_divide(10, 0) == 0.0
        assert safe_divide(10, 0, default=999) == 999
    
    def test_safe_divide_with_nan(self):
        """Test handling of NaN values"""
        assert safe_divide(float('nan'), 2) == 0.0
        assert safe_divide(10, float('nan')) == 0.0
        assert safe_divide(float('nan'), float('nan')) == 0.0
    
    def test_safe_divide_custom_default(self):
        """Test custom default values"""
        assert safe_divide(10, 0, default=-1) == -1
        assert safe_divide(float('nan'), 2, default=100) == 100


class TestFormatNumber:
    """Tests for number formatting"""
    
    def test_format_number_integer(self):
        """Test formatting integers"""
        assert format_number(1234567) == '1,234,567'
        assert format_number(1000) == '1,000'
        assert format_number(100) == '100'
    
    def test_format_number_with_decimals(self):
        """Test formatting with decimal places"""
        assert format_number(1234.567, 2) == '1,234.57'
        assert format_number(1000.1, 1) == '1,000.1'
    
    def test_format_number_nan(self):
        """Test handling of NaN"""
        assert format_number(float('nan')) == 'N/A'


class TestValidateRequiredColumns:
    """Tests for DataFrame column validation"""
    
    def test_validate_all_present(self):
        """Test when all required columns are present"""
        df = pd.DataFrame({
            'col1': [1, 2],
            'col2': [3, 4],
            'col3': [5, 6]
        })
        
        assert validate_required_columns(df, ['col1', 'col2'], 'test')
        assert validate_required_columns(df, ['col1'], 'test')
    
    def test_validate_missing_columns(self):
        """Test when required columns are missing"""
        df = pd.DataFrame({
            'col1': [1, 2],
            'col2': [3, 4]
        })
        
        assert not validate_required_columns(df, ['col1', 'col3'], 'test')
        assert not validate_required_columns(df, ['missing'], 'test')
    
    def test_validate_empty_requirements(self):
        """Test with empty requirements list"""
        df = pd.DataFrame({'col1': [1, 2]})
        assert validate_required_columns(df, [], 'test')


class TestLCTCalculation:
    """Tests for LCT calculation logic"""
    
    def test_basic_lct_calculation(self):
        """Test basic LCT formula"""
        # Example: 5000 students, 250 teachers, 360 min/day
        # LCT = (360 * 250) / 5000 = 18 minutes
        
        enrollment = 5000
        staff = 250
        minutes = 360
        
        lct = (minutes * staff) / enrollment
        assert lct == 18.0
    
    def test_lct_with_different_times(self):
        """Test LCT with different daily instructional times"""
        # Texas: 420 minutes
        # Same students and teachers
        enrollment = 5000
        staff = 250
        minutes = 420
        
        lct = (minutes * staff) / enrollment
        assert lct == 21.0
    
    def test_lct_edge_cases(self):
        """Test edge cases for LCT calculation"""
        # Very small district
        lct_small = (360 * 10) / 200
        assert lct_small == 18.0
        
        # Very large district  
        lct_large = (360 * 1000) / 50000
        assert lct_large == 7.2


# Integration test example
class TestDataIntegration:
    """Integration tests for data processing"""
    
    def test_normalize_sample_data(self):
        """Test normalization of sample data"""
        # Create sample data
        data = {
            'LEAID': ['0100001', '0100002'],
            'LEA_NAME': ['District 1', 'District 2'],
            'STATE': ['AL', 'AL'],
            'MEMBER': [5000, 8000],
            'TEACHERS': [250, 400]
        }
        df = pd.DataFrame(data)
        
        # Test that we can process it
        assert len(df) == 2
        assert 'LEAID' in df.columns
        assert 'MEMBER' in df.columns


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, '-v'])
