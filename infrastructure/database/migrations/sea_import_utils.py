#!/usr/bin/env python3
"""
Shared Utilities for State Education Agency (SEA) Data Imports

Consolidates common patterns discovered during FL, NY, IL integrations:
- Safe value conversion (handling suppressed data: '*', '-', '')
- Crosswalk loading and lookup
- State ID format conversion
- Common import workflow helpers

Usage:
    from sea_import_utils import (
        safe_float, safe_int, safe_pct,
        load_state_crosswalk, get_nces_id,
        format_state_id, SEA_ID_FORMATS
    )

Lessons Learned (January 2026):
- SQLAlchemy JSONB: Use CAST(:param AS jsonb), not :param::jsonb
- Suppressed values: State data uses '*', '-', '', NaN for suppressed data
- State ID formats: Each state has unique format, use format_state_id()
- Mixin naming: Don't prefix with 'Test' or pytest collects them
"""

import pandas as pd
from typing import Optional, Dict, Any, Callable
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# SAFE VALUE CONVERSION
# =============================================================================

SUPPRESSED_VALUES = ('*', '-', '', 'N/A', 'n/a', 'NA', 'null', 'NULL', None)


def safe_float(val, suppressed_values: tuple = SUPPRESSED_VALUES) -> Optional[float]:
    """
    Convert value to float, returning None for suppressed/invalid values.

    State education data commonly uses special characters for suppressed data
    due to privacy rules (small cell sizes) or missing data.

    Args:
        val: Value to convert (can be str, int, float, None)
        suppressed_values: Tuple of values to treat as suppressed

    Returns:
        Float value or None if suppressed/invalid

    Examples:
        >>> safe_float(42.5)
        42.5
        >>> safe_float('*')
        None
        >>> safe_float('-')
        None
        >>> safe_float('')
        None
    """
    if pd.isna(val):
        return None
    if isinstance(val, str) and val.strip() in suppressed_values:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val, suppressed_values: tuple = SUPPRESSED_VALUES) -> Optional[int]:
    """
    Convert value to int, returning None for suppressed/invalid values.

    Args:
        val: Value to convert
        suppressed_values: Tuple of values to treat as suppressed

    Returns:
        Integer value or None if suppressed/invalid

    Examples:
        >>> safe_int(42)
        42
        >>> safe_int(42.7)
        42
        >>> safe_int('*')
        None
    """
    f = safe_float(val, suppressed_values)
    return int(f) if f is not None else None


def safe_pct(val, as_decimal: bool = False) -> Optional[float]:
    """
    Convert percentage value, optionally to decimal.

    Args:
        val: Percentage value (expected 0-100 range)
        as_decimal: If True, divide by 100 to get 0.0-1.0 range

    Returns:
        Float percentage or None if invalid

    Examples:
        >>> safe_pct(75.5)
        75.5
        >>> safe_pct(75.5, as_decimal=True)
        0.755
    """
    f = safe_float(val)
    if f is None:
        return None
    return f / 100.0 if as_decimal else f


# =============================================================================
# CROSSWALK UTILITIES
# =============================================================================

def load_state_crosswalk(session, state: str) -> Dict[str, str]:
    """
    Load crosswalk mapping state_district_id -> nces_id for a state.

    Uses the master state_district_crosswalk table populated from NCES CCD.

    Args:
        session: SQLAlchemy session
        state: Two-letter state code (e.g., 'FL', 'NY', 'IL')

    Returns:
        Dict mapping state district ID to NCES LEAID

    Example:
        >>> crosswalk = load_state_crosswalk(session, 'FL')
        >>> crosswalk['13']  # Miami-Dade
        '1200390'
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = :state
          AND id_system = 'st_leaid'
    """), {"state": state})
    return {row[0]: row[1] for row in result.fetchall()}


def get_nces_id(session, state: str, state_district_id: str) -> Optional[str]:
    """
    Look up NCES LEAID for a single state district ID.

    For bulk lookups, use load_state_crosswalk() instead.

    Args:
        session: SQLAlchemy session
        state: Two-letter state code
        state_district_id: State's district identifier

    Returns:
        NCES LEAID (7-digit string) or None if not found
    """
    result = session.execute(text("""
        SELECT nces_id
        FROM state_district_crosswalk
        WHERE state = :state
          AND state_district_id = :state_id
          AND id_system = 'st_leaid'
    """), {"state": state, "state_id": state_district_id})
    row = result.fetchone()
    return row[0] if row else None


def get_district_name(session, nces_id: str) -> Optional[str]:
    """
    Look up district name from NCES ID.

    Args:
        session: SQLAlchemy session
        nces_id: NCES LEAID

    Returns:
        District name or None if not found
    """
    result = session.execute(text("""
        SELECT name FROM districts WHERE nces_id = :nces_id
    """), {"nces_id": nces_id})
    row = result.fetchone()
    return row[0] if row else None


# =============================================================================
# STATE ID FORMAT CONVERSION
# =============================================================================

# State ID format converters
# Each state uses a different format for district identifiers

SEA_ID_FORMATS: Dict[str, Dict[str, Any]] = {
    'FL': {
        'name': 'FLDOE District Number',
        'format': '2-digit county code (01-67)',
        'example': '13 (Miami-Dade)',
        'converter': lambda x: str(int(x)).zfill(2),
    },
    'NY': {
        'name': 'NYSED BEDS Code',
        'format': '12-digit (RRCCDDDDTTTT)',
        'example': '310200010000 (NYC District 2)',
        'converter': lambda x: str(int(x)).strip(),
    },
    'IL': {
        'name': 'ISBE RCDTS Code',
        'format': '15-digit → RR-CCC-DDDD-TT',
        'example': '150162990250000 → 15-016-2990-25 (Chicago)',
        'converter': lambda rcdts: f'{str(rcdts)[0:2]}-{str(rcdts)[2:5]}-{str(rcdts)[5:9]}-{str(rcdts)[9:11]}',
    },
    'TX': {
        'name': 'TEA District Number',
        'format': '6-digit',
        'example': '101912 (Houston ISD)',
        'converter': lambda x: str(x).strip(),
    },
    'CA': {
        'name': 'CDE County-District Code',
        'format': 'CC-DDDDD (county-district)',
        'example': '19-64733 (Los Angeles Unified)',
        'converter': lambda x: str(x).strip(),
    },
    'MI': {
        'name': 'MDE District Code',
        'format': '5-digit',
        'example': '82015 (Detroit)',
        'converter': lambda x: str(int(x)).strip(),
    },
    'PA': {
        'name': 'PDE AUN',
        'format': '9-digit Administrative Unit Number',
        'example': '126515001 (Philadelphia)',
        'converter': lambda x: str(int(x)).strip(),
    },
    'MA': {
        'name': 'DESE District Code',
        'format': '4-digit zero-padded',
        'example': '0035 (Boston)',
        'converter': lambda x: str(int(x)).zfill(8)[:4],
    },
    'VA': {
        'name': 'VDOE Division Number',
        'format': '3-digit zero-padded',
        'example': '029 (Fairfax County)',
        'converter': lambda x: str(int(x)).zfill(3),
    },
}


def format_state_id(state: str, raw_id) -> str:
    """
    Format a state district ID according to state conventions.

    Uses the SEA_ID_FORMATS registry to apply state-specific formatting.

    Args:
        state: Two-letter state code
        raw_id: Raw district ID from state data file

    Returns:
        Formatted state district ID matching crosswalk format

    Examples:
        >>> format_state_id('FL', 13)
        '13'
        >>> format_state_id('IL', '150162990250000')
        '15-016-2990-25'
    """
    if state in SEA_ID_FORMATS:
        converter = SEA_ID_FORMATS[state]['converter']
        return converter(raw_id)
    # Default: strip whitespace and convert to string
    return str(raw_id).strip()


def get_state_id_info(state: str) -> Dict[str, str]:
    """
    Get information about a state's district ID format.

    Args:
        state: Two-letter state code

    Returns:
        Dict with 'name', 'format', 'example' keys
    """
    if state in SEA_ID_FORMATS:
        info = SEA_ID_FORMATS[state]
        return {
            'name': info['name'],
            'format': info['format'],
            'example': info['example'],
        }
    return {
        'name': f'{state} District ID',
        'format': 'Unknown',
        'example': 'N/A',
    }


# =============================================================================
# IMPORT WORKFLOW HELPERS
# =============================================================================

def check_crosswalk_coverage(session, state: str, state_ids: list) -> Dict[str, Any]:
    """
    Check what percentage of state district IDs have NCES matches.

    Useful for diagnosing import issues.

    Args:
        session: SQLAlchemy session
        state: Two-letter state code
        state_ids: List of state district IDs from source file

    Returns:
        Dict with 'total', 'matched', 'unmatched', 'coverage_pct', 'unmatched_ids'
    """
    crosswalk = load_state_crosswalk(session, state)

    matched = []
    unmatched = []

    for sid in state_ids:
        formatted = format_state_id(state, sid)
        if formatted in crosswalk:
            matched.append(formatted)
        else:
            unmatched.append(formatted)

    total = len(state_ids)
    return {
        'total': total,
        'matched': len(matched),
        'unmatched': len(unmatched),
        'coverage_pct': (len(matched) / total * 100) if total > 0 else 0,
        'unmatched_ids': unmatched[:20],  # First 20 for debugging
    }


def log_import_summary(
    state: str,
    identifiers: int,
    staff: int,
    enrollment: int,
    skipped: int = 0
) -> None:
    """
    Log a standardized import summary.

    Args:
        state: Two-letter state code
        identifiers: Number of district identifiers imported
        staff: Number of staff records imported
        enrollment: Number of enrollment records imported
        skipped: Number of records skipped (no NCES match)
    """
    logger.info("=" * 60)
    logger.info(f"{state} Import Summary:")
    logger.info(f"  District identifiers: {identifiers}")
    logger.info(f"  Staff records: {staff}")
    logger.info(f"  Enrollment records: {enrollment}")
    if skipped > 0:
        logger.info(f"  Skipped (no NCES match): {skipped}")
    logger.info("=" * 60)


# =============================================================================
# JSONB HELPER (SQLAlchemy workaround)
# =============================================================================

def jsonb_insert_sql(base_sql: str) -> str:
    """
    Transform SQL to use CAST() for JSONB instead of :: syntax.

    SQLAlchemy's parameter binding doesn't handle ::jsonb well.
    This is a reminder/documentation of the pattern.

    WRONG: VALUES (:data::jsonb)
    RIGHT: VALUES (CAST(:data AS jsonb))

    Args:
        base_sql: SQL string (for documentation)

    Returns:
        Same SQL (this is primarily documentation)
    """
    # This function exists primarily as documentation
    # The actual fix is in how you write the SQL
    return base_sql


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_enrollment_staff_ratio(
    enrollment: Optional[int],
    teachers: Optional[float],
    min_ratio: float = 5.0,
    max_ratio: float = 100.0
) -> bool:
    """
    Check if student-teacher ratio is reasonable.

    Args:
        enrollment: Student enrollment count
        teachers: Teacher FTE count
        min_ratio: Minimum reasonable ratio (default 5:1)
        max_ratio: Maximum reasonable ratio (default 100:1)

    Returns:
        True if ratio is within reasonable bounds
    """
    if enrollment is None or teachers is None:
        return False
    if enrollment <= 0 or teachers <= 0:
        return False

    ratio = enrollment / teachers
    return min_ratio <= ratio <= max_ratio


def is_sped_intensive(
    enrollment: Optional[int],
    teachers: Optional[float],
    threshold: float = 10.0
) -> bool:
    """
    Check if district appears to be SPED-intensive.

    Districts with very low student-teacher ratios (< 10:1) may be
    special education focused and need different validation rules.

    Args:
        enrollment: Student enrollment count
        teachers: Teacher FTE count
        threshold: Ratio threshold below which district is flagged

    Returns:
        True if district appears SPED-intensive
    """
    if enrollment is None or teachers is None:
        return False
    if enrollment <= 0 or teachers <= 0:
        return False

    ratio = enrollment / teachers
    return ratio < threshold


# =============================================================================
# COVID YEAR VALIDATION
# =============================================================================

COVID_EXCLUDED_YEARS = {'2019-20', '2020-21', '2021-22', '2022-23'}
VALID_DATA_YEARS = {'2018-19', '2023-24', '2024-25', '2025-26'}


def is_covid_year(year: str) -> bool:
    """
    Check if a school year falls in the COVID-excluded period.

    COVID years (2019-20 through 2022-23) should not be used for
    bell schedule or instructional time data due to abnormal operations.

    Args:
        year: School year in 'YYYY-YY' format

    Returns:
        True if year is in COVID-excluded period
    """
    return year in COVID_EXCLUDED_YEARS


def validate_data_year(year: str) -> bool:
    """
    Validate that a data year is acceptable for use.

    Args:
        year: School year in 'YYYY-YY' format

    Returns:
        True if year is valid (not COVID-era)
    """
    return not is_covid_year(year)
