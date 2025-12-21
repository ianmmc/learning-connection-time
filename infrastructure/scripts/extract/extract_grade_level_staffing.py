#!/usr/bin/env python3
"""
Extract grade-level staffing data from NCES CCD Staff file

This script processes the CCD LEA-level staff file (059) which contains
staff counts broken down by role. It extracts instructional staff and
allocates them to grade levels using a hybrid approach (Option C):

- Elementary (K-5): Uses "Elementary Teachers" category directly
- Secondary (6-12): Uses "Secondary Teachers" category
  - Split proportionally between Middle (6-8) and High (9-12) based on enrollment

This requires enrollment data to calculate the proportional split.

OPTIMIZATION: For faster processing, use the slim staff file:
    data/processed/slim/staff_by_level_slim.csv
This reduces file size from 57 MB to 1.1 MB (98% reduction) with no loss of data.

Usage:
    python extract_grade_level_staffing.py <staff_file> <enrollment_file> [--output <output_file>]

Examples:
    # Using slim file (recommended - 98% faster):
    python extract_grade_level_staffing.py \\
        data/processed/slim/staff_by_level_slim.csv \\
        data/processed/normalized/grade_level_enrollment_2324.csv

    # Using raw file (if slim not available):
    python extract_grade_level_staffing.py \\
        data/raw/federal/nces-ccd/2023_24/ccd_lea_059_2324_l_1a_073124.csv \\
        data/processed/normalized/grade_level_enrollment_2324.csv
"""

import argparse
import logging
import sys
from pathlib import Path
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_grade_level_staffing(
    staff_file: Path,
    enrollment_file: Path,
    output_file: Path
):
    """
    Extract and allocate instructional staff by grade level

    Args:
        staff_file: Path to CCD LEA-level staff file (059)
        enrollment_file: Path to grade-level enrollment file (from extract_grade_level_enrollment.py)
        output_file: Path to output CSV file
    """
    logger.info(f"Loading staff data from {staff_file}")

    # Read staff file
    # We're looking for specific staff categories
    target_categories = {
        'Elementary Teachers',
        'Secondary Teachers',
        'Pre-kindergarten Teachers',
        'Kindergarten Teachers',
        'Ungraded Teachers',
        'Teachers'  # Total for validation
    }

    df_staff = pd.read_csv(staff_file, low_memory=False)

    # Filter for target categories and Category Set A (most granular, non-derived)
    mask = (
        (df_staff['STAFF'].isin(target_categories)) &
        (df_staff['TOTAL_INDICATOR'] == 'Category Set A')
    )

    df_staff = df_staff[mask].copy()

    # Convert STAFF_COUNT to numeric
    df_staff['STAFF_COUNT'] = pd.to_numeric(
        df_staff['STAFF_COUNT'],
        errors='coerce'
    ).fillna(0)

    # Pivot to get one row per district with columns for each staff type
    logger.info("Pivoting staff data...")
    df_staff_wide = df_staff.pivot_table(
        index='LEAID',
        columns='STAFF',
        values='STAFF_COUNT',
        aggfunc='sum',
        fill_value=0
    ).reset_index()

    # Rename LEAID to district_id for consistency
    df_staff_wide = df_staff_wide.rename(columns={'LEAID': 'district_id'})

    # Ensure all expected columns exist
    for category in target_categories:
        if category not in df_staff_wide.columns:
            df_staff_wide[category] = 0

    # Load enrollment data for proportional allocation
    logger.info(f"Loading enrollment data from {enrollment_file}")
    df_enrollment = pd.read_csv(enrollment_file)

    # Merge staff and enrollment
    logger.info("Merging staff and enrollment data...")
    df = pd.merge(
        df_staff_wide,
        df_enrollment[['district_id', 'enrollment_elementary', 'enrollment_middle', 'enrollment_high', 'enrollment_total']],
        on='district_id',
        how='left'
    )

    # Fill NaN enrollments with 0
    df['enrollment_elementary'] = df['enrollment_elementary'].fillna(0)
    df['enrollment_middle'] = df['enrollment_middle'].fillna(0)
    df['enrollment_high'] = df['enrollment_high'].fillna(0)
    df['enrollment_total'] = df['enrollment_total'].fillna(0)

    # Calculate secondary enrollment (6-12) for proportional allocation
    df['enrollment_secondary'] = df['enrollment_middle'] + df['enrollment_high']

    # Allocate staff using Hybrid Approach (Option C)
    logger.info("Allocating staff to grade levels...")

    # Elementary: Use Elementary Teachers directly
    # (Pre-K and K teachers are separate categories, not included in Elementary Teachers per NCES)
    df['instructional_staff_elementary'] = df['Elementary Teachers']

    # Secondary: Split between Middle and High based on enrollment proportion
    # Middle staff = Secondary Teachers × (Middle Enrollment / Secondary Enrollment)
    # High staff = Secondary Teachers × (High Enrollment / Secondary Enrollment)

    # Calculate proportions (avoid division by zero)
    df['middle_proportion'] = 0.0
    df['high_proportion'] = 0.0

    mask_secondary = df['enrollment_secondary'] > 0
    df.loc[mask_secondary, 'middle_proportion'] = (
        df.loc[mask_secondary, 'enrollment_middle'] / df.loc[mask_secondary, 'enrollment_secondary']
    )
    df.loc[mask_secondary, 'high_proportion'] = (
        df.loc[mask_secondary, 'enrollment_high'] / df.loc[mask_secondary, 'enrollment_secondary']
    )

    df['instructional_staff_middle'] = (df['Secondary Teachers'] * df['middle_proportion']).round(2)
    df['instructional_staff_high'] = (df['Secondary Teachers'] * df['high_proportion']).round(2)

    # Select output columns
    output_columns = [
        'district_id',
        'instructional_staff_elementary',
        'instructional_staff_middle',
        'instructional_staff_high',
        'Elementary Teachers',  # Keep originals for reference
        'Secondary Teachers',
        'Pre-kindergarten Teachers',
        'Kindergarten Teachers',
        'Ungraded Teachers',
        'Teachers',
        'middle_proportion',
        'high_proportion'
    ]

    df_output = df[output_columns].copy()

    # Rename for clarity
    df_output = df_output.rename(columns={
        'Elementary Teachers': 'teachers_elementary_actual',
        'Secondary Teachers': 'teachers_secondary_actual',
        'Pre-kindergarten Teachers': 'teachers_prek',
        'Kindergarten Teachers': 'teachers_k',
        'Ungraded Teachers': 'teachers_ungraded',
        'Teachers': 'teachers_total'
    })

    # Save to file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_output.to_csv(output_file, index=False)

    # Report statistics
    total_districts = len(df_output)
    districts_with_elem = (df_output['instructional_staff_elementary'] > 0).sum()
    districts_with_middle = (df_output['instructional_staff_middle'] > 0).sum()
    districts_with_high = (df_output['instructional_staff_high'] > 0).sum()

    # Calculate how many districts had secondary staff split
    districts_split = (df_output['teachers_secondary_actual'] > 0).sum()

    logger.info(f"\n{'='*60}")
    logger.info("GRADE-LEVEL STAFFING EXTRACTION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Total districts: {total_districts:,}")
    logger.info(f"\nDistricts with instructional staff:")
    logger.info(f"  Elementary (K-5): {districts_with_elem:,} ({districts_with_elem/total_districts*100:.1f}%)")
    logger.info(f"  Middle (6-8): {districts_with_middle:,} ({districts_with_middle/total_districts*100:.1f}%)")
    logger.info(f"  High (9-12): {districts_with_high:,} ({districts_with_high/total_districts*100:.1f}%)")
    logger.info(f"\nSecondary staff allocation:")
    logger.info(f"  Districts with secondary teachers split: {districts_split:,}")
    logger.info(f"\nTotal instructional staff:")
    logger.info(f"  Elementary: {df_output['instructional_staff_elementary'].sum():,.1f}")
    logger.info(f"  Middle: {df_output['instructional_staff_middle'].sum():,.1f}")
    logger.info(f"  High: {df_output['instructional_staff_high'].sum():,.1f}")
    logger.info(f"  Total reported: {df_output['teachers_total'].sum():,.1f}")
    logger.info(f"\n✓ Output saved to: {output_file}")
    logger.info(f"\nMethodology Note:")
    logger.info(f"  - Elementary staff: Actual 'Elementary Teachers' from NCES")
    logger.info(f"  - Middle/High staff: 'Secondary Teachers' split proportionally")
    logger.info(f"    based on enrollment in grades 6-8 vs 9-12")


def main():
    parser = argparse.ArgumentParser(
        description="Extract grade-level staffing from NCES CCD staff file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'staff_file',
        type=Path,
        help='CCD LEA-level staff file (059)'
    )

    parser.add_argument(
        'enrollment_file',
        type=Path,
        help='Grade-level enrollment file (from extract_grade_level_enrollment.py)'
    )

    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: data/processed/normalized/grade_level_staffing_YEAR.csv)'
    )

    args = parser.parse_args()

    # Validate input files
    if not args.staff_file.exists():
        logger.error(f"Staff file not found: {args.staff_file}")
        return 1

    if not args.enrollment_file.exists():
        logger.error(f"Enrollment file not found: {args.enrollment_file}")
        return 1

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        # Extract year from filename
        filename = args.staff_file.name
        year_match = filename.split('_')[3] if '_' in filename else 'unknown'
        output_file = Path(f"data/processed/normalized/grade_level_staffing_{year_match}.csv")

    # Process the file
    extract_grade_level_staffing(args.staff_file, args.enrollment_file, output_file)

    return 0


if __name__ == '__main__':
    sys.exit(main())
