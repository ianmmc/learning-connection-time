"""
Learning Connection Time (LCT) Calculator

This module provides functions and classes for calculating LCT,
the metric that reframes student-teacher ratios into tangible
minutes of potential individual attention per student per day.
"""

from typing import Union, Dict
import pandas as pd


def calculate_lct(
    enrollment: Union[int, float],
    instructional_staff: Union[int, float],
    daily_minutes: Union[int, float]
) -> float:
    """
    Calculate Learning Connection Time (basic formula)
    
    LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
    
    Args:
        enrollment: Total student count (must be > 0)
        instructional_staff: Full-time equivalent (FTE) instructional staff
        daily_minutes: Statutory daily instructional minutes
        
    Returns:
        LCT in minutes per student per day (rounded to 2 decimal places)
        
    Raises:
        ValueError: If enrollment is zero or negative
        ValueError: If instructional_staff is negative
        ValueError: If daily_minutes is not in reasonable range (180-480)
        
    Example:
        >>> calculate_lct(enrollment=5000, instructional_staff=250, daily_minutes=360)
        18.0
        
        This means students receive 18 minutes of potential individual
        teacher attention per day.
    """
    # Validation
    if enrollment <= 0:
        raise ValueError(f"Enrollment must be positive, got {enrollment}")
    
    if instructional_staff < 0:
        raise ValueError(f"Instructional staff cannot be negative, got {instructional_staff}")
    
    if not (180 <= daily_minutes <= 480):
        raise ValueError(
            f"Daily minutes should be between 180 and 480, got {daily_minutes}. "
            "Check if this is a reasonable instructional time value."
        )
    
    # Calculate
    total_instructional_minutes = daily_minutes * instructional_staff
    lct = total_instructional_minutes / enrollment
    
    return round(lct, 2)


def calculate_weighted_daily_minutes(
    grade_enrollments: Dict[str, int],
    grade_minutes: Dict[str, int]
) -> float:
    """
    Calculate weighted average daily instructional minutes for districts
    with multiple grade levels and different requirements.
    
    Args:
        grade_enrollments: Dict mapping grade span to student count
            Example: {"K-8": 6000, "9-12": 2500}
        grade_minutes: Dict mapping grade span to daily minutes
            Example: {"K-8": 200, "9-12": 360}
            
    Returns:
        Weighted average daily minutes
        
    Example:
        >>> enrollments = {"K-8": 6000, "9-12": 2500}
        >>> minutes = {"K-8": 200, "9-12": 360}
        >>> calculate_weighted_daily_minutes(enrollments, minutes)
        247.06
    """
    total_enrollment = sum(grade_enrollments.values())
    
    if total_enrollment == 0:
        raise ValueError("Total enrollment cannot be zero")
    
    weighted_sum = sum(
        grade_enrollments.get(grade, 0) * grade_minutes.get(grade, 0)
        for grade in grade_enrollments.keys()
    )
    
    return round(weighted_sum / total_enrollment, 2)


class LCTCalculator:
    """
    Object-oriented interface for LCT calculations with configuration
    and batch processing capabilities.
    """
    
    def __init__(self, state_requirements: Dict[str, Dict] = None):
        """
        Initialize calculator with optional state requirements configuration
        
        Args:
            state_requirements: Dict mapping state codes to requirements
        """
        self.state_requirements = state_requirements or {}
        
    def calculate_district_lct(
        self,
        district_data: Dict[str, Union[int, float, str]]
    ) -> Dict[str, Union[float, str]]:
        """
        Calculate LCT for a single district
        
        Args:
            district_data: Dict containing:
                - 'enrollment': int
                - 'instructional_staff': float
                - 'daily_minutes': int (or calculated from state/grades)
                - 'state': str (optional, for state-based minute lookup)
                
        Returns:
            Dict with calculated LCT and metadata
        """
        enrollment = district_data['enrollment']
        staff = district_data['instructional_staff']
        
        # Get daily minutes (provided or from state requirements)
        if 'daily_minutes' in district_data:
            daily_minutes = district_data['daily_minutes']
        elif 'state' in district_data and self.state_requirements:
            daily_minutes = self._get_state_minutes(
                district_data['state'],
                district_data.get('grade_enrollments', {})
            )
        else:
            raise ValueError(
                "Must provide either daily_minutes or state code with requirements"
            )
        
        lct = calculate_lct(enrollment, staff, daily_minutes)
        
        return {
            'lct_minutes': lct,
            'lct_hours': round(lct / 60, 2),
            'lct_yearly_hours': round((lct * 180) / 60, 1),  # Assuming 180-day year
            'student_teacher_ratio': round(enrollment / staff, 1) if staff > 0 else None,
            'daily_minutes_used': daily_minutes,
        }
    
    def calculate_batch_lct(self, districts_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate LCT for multiple districts at once
        
        Args:
            districts_df: DataFrame with columns:
                - enrollment
                - instructional_staff
                - daily_minutes (or state for lookup)
                
        Returns:
            DataFrame with original data plus LCT calculations
        """
        results = []
        
        for idx, row in districts_df.iterrows():
            try:
                district_data = row.to_dict()
                lct_result = self.calculate_district_lct(district_data)
                results.append({**row.to_dict(), **lct_result})
            except Exception as e:
                # Log error but continue processing
                print(f"Error processing district at index {idx}: {e}")
                results.append({**row.to_dict(), 'lct_minutes': None, 'error': str(e)})
        
        return pd.DataFrame(results)
    
    def _get_state_minutes(
        self,
        state_code: str,
        grade_enrollments: Dict[str, int] = None
    ) -> int:
        """
        Look up daily minutes requirement for a state
        
        If state has grade-level variations and grade_enrollments provided,
        calculates weighted average. Otherwise returns primary value.
        """
        if state_code not in self.state_requirements:
            # Default to 300 minutes (5 hours) if unknown
            return 300
        
        state_reqs = self.state_requirements[state_code]
        
        # If simple (all grades same), return that value
        if 'all_grades' in state_reqs:
            return state_reqs['all_grades']['minutes_per_day']
        
        # If complex and we have grade data, calculate weighted
        if grade_enrollments and 'requirements' in state_reqs:
            grade_minutes = {
                grade: data['minutes_per_day']
                for grade, data in state_reqs['requirements'].items()
            }
            return int(calculate_weighted_daily_minutes(
                grade_enrollments,
                grade_minutes
            ))
        
        # Fallback: return first requirement found
        if 'requirements' in state_reqs:
            first_req = list(state_reqs['requirements'].values())[0]
            return first_req['minutes_per_day']
        
        return 300  # Ultimate fallback


# Utility functions

def lct_to_ratio(lct_minutes: float, daily_minutes: int = 360) -> float:
    """
    Convert LCT back to traditional student-teacher ratio
    
    Args:
        lct_minutes: LCT value
        daily_minutes: Daily instructional minutes used in calculation
        
    Returns:
        Student-teacher ratio
        
    Example:
        >>> lct_to_ratio(18.0, 360)
        20.0
    """
    return round(daily_minutes / lct_minutes, 1)


def interpret_lct(lct_minutes: float) -> str:
    """
    Provide plain-language interpretation of an LCT value
    
    Args:
        lct_minutes: LCT value in minutes per student per day
        
    Returns:
        Human-readable interpretation string
    """
    hours = lct_minutes / 60
    yearly_hours = (lct_minutes * 180) / 60
    
    return (
        f"Students receive approximately {lct_minutes:.1f} minutes "
        f"({hours:.1f} hours) of potential individual teacher attention per day, "
        f"totaling {yearly_hours:.0f} hours over a 180-day school year."
    )


if __name__ == "__main__":
    # Example usage
    print("=" * 60)
    print("Learning Connection Time Calculator")
    print("=" * 60)
    
    # Example 1: Basic calculation
    print("\nExample 1: Basic Calculation")
    print("-" * 40)
    enrollment = 5000
    staff = 250
    minutes = 360
    
    lct = calculate_lct(enrollment, staff, minutes)
    print(f"District: {enrollment:,} students, {staff} teachers, {minutes} min/day")
    print(f"LCT: {lct} minutes per student per day")
    print(f"Interpretation: {interpret_lct(lct)}")
    
    # Example 2: Using the calculator class
    print("\nExample 2: Using LCTCalculator")
    print("-" * 40)
    
    calculator = LCTCalculator()
    
    district = {
        'name': 'Example USD',
        'enrollment': 8500,
        'instructional_staff': 425,
        'daily_minutes': 300
    }
    
    result = calculator.calculate_district_lct(district)
    print(f"District: {district['name']}")
    print(f"LCT: {result['lct_minutes']} minutes/day ({result['lct_hours']} hours/day)")
    print(f"Yearly: {result['lct_yearly_hours']} hours")
    print(f"Student-Teacher Ratio: {result['student_teacher_ratio']}:1")
