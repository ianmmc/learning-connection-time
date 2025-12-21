#!/usr/bin/env python3
"""
Normalize district data to a common schema

This script takes raw district data from various sources and normalizes it to
a standardized schema for consistent processing.

Usage:
    python normalize_districts.py <input_file> --source <nces|state> [--output <output_file>]
    
Example:
    python normalize_districts.py data/raw/federal/nces-ccd/2023-24/districts.csv --source nces
    python normalize_districts.py data/raw/state/california/districts.csv --source state --state CA
"""

import argparse
import logging
from pathlib import Path
import pandas as pd
import sys
from typing import Optional

# Add utilities to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "utilities"))
from common import (
    standardize_state,
    validate_required_columns,
    create_data_lineage_file,
    setup_logging
)

logger = logging.getLogger(__name__)


# Standard schema for normalized district data
NORMALIZED_SCHEMA = {
    'district_id': str,          # Unique district identifier
    'district_name': str,        # District name
    'state': str,                # Two-letter state code
    'enrollment': float,         # Total student enrollment
    'instructional_staff': float,  # Number of instructional staff
    'total_staff': float,        # Total staff count (optional)
    'schools': float,            # Number of schools (optional)
    'year': str,                 # School year
    'data_source': str,          # Source of data (nces, state, etc.)
}


def normalize_nces_ccd(df: pd.DataFrame, year: str) -> pd.DataFrame:
    """
    Normalize NCES Common Core of Data to standard schema
    
    Args:
        df: Raw NCES CCD data
        year: School year
    
    Returns:
        Normalized DataFrame
    """
    logger.info("Normalizing NCES CCD data...")

    # NCES CCD column mappings (adjust based on actual NCES columns)
    # Support both uppercase (real NCES) and lowercase (sample data)
    column_map = {
        'LEAID': 'district_id',
        'leaid': 'district_id',
        'LEA_NAME': 'district_name',
        'lea_name': 'district_name',
        'ST': 'state',                   # Two-letter state code in directory file
        'STATE': 'state',
        'state': 'state',
        'MEMBER': 'enrollment',          # Total membership
        'total_students': 'enrollment',  # Sample data format
        'TEACHERS': 'instructional_staff',  # FTE teachers
        'total_teachers': 'instructional_staff',  # Sample data format
        'TOTAL_STAFF': 'total_staff',
        'SCH_COUNT': 'schools',
        'OPERATIONAL_SCHOOLS': 'schools',  # In directory file
    }

    # Rename columns
    normalized = df.rename(columns=column_map)
    
    # Select and order columns
    available_cols = [col for col in NORMALIZED_SCHEMA.keys() if col in normalized.columns]
    normalized = normalized[available_cols].copy()
    
    # Add metadata
    normalized['year'] = year
    normalized['data_source'] = 'nces_ccd'
    
    # Standardize state codes
    if 'state' in normalized.columns:
        normalized['state'] = normalized['state'].apply(standardize_state)
    
    # Ensure numeric columns are numeric
    numeric_cols = ['enrollment', 'instructional_staff', 'total_staff', 'schools']
    for col in numeric_cols:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors='coerce')
    
    logger.info(f"  Normalized {len(normalized):,} districts")
    
    return normalized


def normalize_state_data(df: pd.DataFrame, state: str, year: str) -> pd.DataFrame:
    """
    Normalize state-specific data to standard schema
    
    Args:
        df: Raw state data
        state: State abbreviation
        year: School year
    
    Returns:
        Normalized DataFrame
    """
    logger.info(f"Normalizing {state} state data...")
    
    # State-specific mappings would go here
    # This is a template - actual mappings depend on state data format
    
    # Example for California (adjust based on actual format)
    if state == 'CA':
        column_map = {
            'CDSCode': 'district_id',
            'District': 'district_name',
            'Enrollment': 'enrollment',
            'Teachers': 'instructional_staff',
        }
    else:
        # Generic mapping attempt
        column_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'id' in col_lower or 'code' in col_lower:
                column_map[col] = 'district_id'
            elif 'name' in col_lower or 'district' in col_lower:
                column_map[col] = 'district_name'
            elif 'enroll' in col_lower or 'student' in col_lower:
                column_map[col] = 'enrollment'
            elif 'teacher' in col_lower or 'staff' in col_lower:
                column_map[col] = 'instructional_staff'
    
    normalized = df.rename(columns=column_map)
    
    # Select available columns
    available_cols = [col for col in NORMALIZED_SCHEMA.keys() if col in normalized.columns]
    normalized = normalized[available_cols].copy()
    
    # Add metadata
    normalized['state'] = state
    normalized['year'] = year
    normalized['data_source'] = f'state_{state.lower()}'
    
    # Ensure numeric columns are numeric
    numeric_cols = ['enrollment', 'instructional_staff', 'total_staff', 'schools']
    for col in numeric_cols:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors='coerce')
    
    logger.info(f"  Normalized {len(normalized):,} districts")
    
    return normalized


def merge_grade_level_data(
    df: pd.DataFrame,
    enrollment_file: Optional[Path] = None,
    staffing_file: Optional[Path] = None
) -> pd.DataFrame:
    """
    Merge grade-level enrollment and staffing data into normalized districts

    Args:
        df: Normalized district DataFrame
        enrollment_file: Path to grade-level enrollment file (optional)
        staffing_file: Path to grade-level staffing file (optional)

    Returns:
        DataFrame with grade-level columns added
    """
    result = df.copy()

    # Merge enrollment data if provided
    if enrollment_file and enrollment_file.exists():
        logger.info(f"Merging grade-level enrollment from {enrollment_file}")
        df_enrollment = pd.read_csv(enrollment_file)

        result = pd.merge(
            result,
            df_enrollment,
            on='district_id',
            how='left'
        )

        logger.info(f"  Added {len(df_enrollment.columns)} enrollment columns")

    # Merge staffing data if provided
    if staffing_file and staffing_file.exists():
        logger.info(f"Merging grade-level staffing from {staffing_file}")
        df_staffing = pd.read_csv(staffing_file)

        result = pd.merge(
            result,
            df_staffing,
            on='district_id',
            how='left'
        )

        logger.info(f"  Added {len(df_staffing.columns)} staffing columns")

    return result


def validate_normalized_data(df: pd.DataFrame) -> bool:
    """
    Validate normalized data meets quality requirements

    Args:
        df: Normalized DataFrame

    Returns:
        True if validation passes
    """
    logger.info("Validating normalized data...")

    # Check required columns
    required = ['district_id', 'district_name', 'state', 'year', 'data_source']
    if not validate_required_columns(df, required, "Normalized data"):
        return False

    # Check for null values in key columns
    for col in ['district_id', 'state']:
        null_count = df[col].isna().sum()
        if null_count > 0:
            logger.warning(f"  {null_count:,} null values in {col}")

    # Check data types
    if 'enrollment' in df.columns:
        if df['enrollment'].dtype not in ['float64', 'int64']:
            logger.error("enrollment column is not numeric")
            return False

    if 'instructional_staff' in df.columns:
        if df['instructional_staff'].dtype not in ['float64', 'int64']:
            logger.error("instructional_staff column is not numeric")
            return False
    
    # Check for reasonable values
    if 'enrollment' in df.columns:
        negative = (df['enrollment'] < 0).sum()
        if negative > 0:
            logger.warning(f"  {negative:,} districts with negative enrollment")
    
    if 'instructional_staff' in df.columns:
        negative = (df['instructional_staff'] < 0).sum()
        if negative > 0:
            logger.warning(f"  {negative:,} districts with negative staff counts")
    
    logger.info("✓ Validation passed")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Normalize district data to standard schema",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "input_file",
        type=Path,
        help="Raw district data file"
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=['nces', 'state'],
        help="Data source type"
    )
    parser.add_argument(
        "--state",
        help="State abbreviation (required for state data)"
    )
    parser.add_argument(
        "--year",
        required=True,
        help="School year (e.g., 2023-24)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (default: data/processed/normalized/)"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate without saving"
    )
    parser.add_argument(
        "--enrollment-file",
        type=Path,
        help="Grade-level enrollment file (from extract_grade_level_enrollment.py)"
    )
    parser.add_argument(
        "--staffing-file",
        type=Path,
        help="Grade-level staffing file (from extract_grade_level_staffing.py)"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging()

    # Validate arguments
    if args.source == 'state' and not args.state:
        logger.error("--state required for state data")
        return 1

    # Load input data
    if not args.input_file.exists():
        logger.error(f"Input file not found: {args.input_file}")
        return 1

    logger.info(f"Loading {args.input_file}")
    try:
        df = pd.read_csv(args.input_file, low_memory=False)
        logger.info(f"  Loaded {len(df):,} rows")
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return 1

    # Normalize based on source
    if args.source == 'nces':
        normalized = normalize_nces_ccd(df, args.year)
    elif args.source == 'state':
        normalized = normalize_state_data(df, args.state, args.year)
    else:
        logger.error(f"Unknown source: {args.source}")
        return 1

    # Merge grade-level data if provided
    if args.enrollment_file or args.staffing_file:
        normalized = merge_grade_level_data(
            normalized,
            enrollment_file=args.enrollment_file,
            staffing_file=args.staffing_file
        )

        # Add computed total enrollment and staff if not present
        if 'enrollment_total' in normalized.columns and 'enrollment' not in normalized.columns:
            normalized['enrollment'] = normalized['enrollment_total']
            logger.info("Added total enrollment column from grade-level sum")

        if 'instructional_staff' not in normalized.columns:
            # Calculate total instructional staff from grade-level data
            if all(col in normalized.columns for col in ['instructional_staff_elementary', 'instructional_staff_middle', 'instructional_staff_high']):
                normalized['instructional_staff'] = (
                    normalized['instructional_staff_elementary'].fillna(0) +
                    normalized['instructional_staff_middle'].fillna(0) +
                    normalized['instructional_staff_high'].fillna(0)
                )
                logger.info("Added total instructional_staff column from grade-level sum")
            elif 'teachers_total' in normalized.columns:
                normalized['instructional_staff'] = normalized['teachers_total']
                logger.info("Added total instructional_staff column from teachers_total")

    # Validate
    if not validate_normalized_data(normalized):
        logger.error("Validation failed")
        return 1
    
    if args.validate_only:
        logger.info("Validation complete (no output saved)")
        return 0
    
    # Determine output path
    if args.output:
        output_file = args.output
    else:
        # Default to normalized directory
        script_dir = Path(__file__).parent
        output_dir = script_dir.parent.parent.parent / "data" / "processed" / "normalized"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        source_suffix = args.state.lower() if args.source == 'state' else 'nces'
        output_file = output_dir / f"districts_{args.year.replace('-', '_')}_{source_suffix}.csv"
    
    # Save
    output_file.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_file, index=False)
    logger.info(f"✓ Saved to: {output_file}")
    
    # Create lineage file
    processing_steps = [
        f"Loaded from {args.input_file}",
        f"Normalized {args.source} data format",
        "Standardized column names and data types",
        "Validated data quality"
    ]
    
    create_data_lineage_file(
        output_file,
        [args.input_file],
        processing_steps,
        {
            'source_type': args.source,
            'year': args.year,
            'rows': len(normalized)
        }
    )
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("NORMALIZATION SUMMARY")
    logger.info("="*60)
    logger.info(f"Source: {args.source}")
    logger.info(f"Input rows: {len(df):,}")
    logger.info(f"Output rows: {len(normalized):,}")
    logger.info(f"Columns: {len(normalized.columns)}")
    
    if 'state' in normalized.columns:
        state_counts = normalized['state'].value_counts()
        logger.info(f"\nDistricts by state:")
        for state, count in state_counts.head(10).items():
            logger.info(f"  {state}: {count:,}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
