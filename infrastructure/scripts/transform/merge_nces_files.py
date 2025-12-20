#!/usr/bin/env python3
"""
Merge NCES CCD files (Directory, Membership, Staff) into a single normalized file.

This script combines the three core NCES CCD files for a given year:
- LEA Directory: Basic district information
- LEA Membership: Student enrollment counts
- LEA Staff: Teacher and staff counts

Output is a single CSV with one row per district containing all needed data for LCT calculation.
"""

import pandas as pd
import argparse
import logging
from pathlib import Path
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def merge_nces_ccd_files(directory_file, membership_file, staff_file, output_file, year):
    """
    Merge NCES CCD files into normalized format.

    Args:
        directory_file: Path to LEA directory file
        membership_file: Path to LEA membership file
        staff_file: Path to LEA staff file
        output_file: Path for output file
        year: School year (e.g., "2023-24")
    """
    logger.info(f"Merging NCES CCD files for {year}")

    # Read directory file
    logger.info(f"Reading directory: {directory_file}")
    directory = pd.read_csv(directory_file)
    logger.info(f"  Loaded {len(directory):,} districts")

    # Read membership file and get total enrollment
    logger.info(f"Reading membership: {membership_file}")
    membership = pd.read_csv(membership_file)
    logger.info(f"  Loaded {len(membership):,} membership records")

    # Filter for total enrollment (Education Unit Total)
    total_enrollment = membership[
        membership['TOTAL_INDICATOR'] == 'Education Unit Total'
    ][['LEAID', 'STUDENT_COUNT']].copy()
    total_enrollment.columns = ['LEAID', 'enrollment']
    logger.info(f"  Found {len(total_enrollment):,} districts with enrollment data")

    # Read staff file and get total teachers
    logger.info(f"Reading staff: {staff_file}")
    staff = pd.read_csv(staff_file)
    logger.info(f"  Loaded {len(staff):,} staff records")

    # Filter for teachers (Derived - Major Staffing Category)
    teachers = staff[
        (staff['STAFF'] == 'Teachers') &
        (staff['TOTAL_INDICATOR'] == 'Derived - Major Staffing Category')
    ][['LEAID', 'STAFF_COUNT']].copy()
    teachers.columns = ['LEAID', 'instructional_staff']
    logger.info(f"  Found {len(teachers):,} districts with teacher data")

    # Select needed columns from directory
    district_info = directory[['LEAID', 'LEA_NAME', 'ST']].copy()
    district_info.columns = ['district_id', 'district_name', 'state']

    # Merge all together
    logger.info("Merging datasets...")
    result = district_info.merge(total_enrollment, left_on='district_id', right_on='LEAID', how='left')
    result = result.merge(teachers, left_on='district_id', right_on='LEAID', how='left')

    # Drop extra LEAID columns from merges
    result = result.drop(columns=['LEAID_x', 'LEAID_y'], errors='ignore')

    # Add metadata
    result['year'] = year
    result['data_source'] = 'nces_ccd'

    # Reorder columns
    result = result[['district_id', 'district_name', 'state', 'enrollment', 'instructional_staff', 'year', 'data_source']]

    # Filter out districts with no enrollment or staff data
    before_filter = len(result)
    result = result[result['enrollment'].notna() & result['instructional_staff'].notna()]
    logger.info(f"  Filtered {before_filter - len(result):,} districts with missing data")

    # Save
    output_file.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_file, index=False)
    logger.info(f"✓ Saved {len(result):,} districts to {output_file}")

    # Show summary
    logger.info("\nSummary Statistics:")
    logger.info(f"  Total Districts: {len(result):,}")
    logger.info(f"  Total Enrollment: {result['enrollment'].sum():,.0f}")
    logger.info(f"  Total Teachers: {result['instructional_staff'].sum():,.1f}")
    logger.info(f"  States: {result['state'].nunique()}")
    logger.info(f"  Avg District Size: {result['enrollment'].mean():,.0f} students")
    logger.info(f"  Avg Teachers/District: {result['instructional_staff'].mean():,.1f}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Merge NCES CCD files into normalized format"
    )

    parser.add_argument(
        'directory_file',
        type=Path,
        help='LEA Directory file (e.g., ccd_lea_029_*.csv)'
    )

    parser.add_argument(
        'membership_file',
        type=Path,
        help='LEA Membership file (e.g., ccd_lea_052_*.csv)'
    )

    parser.add_argument(
        'staff_file',
        type=Path,
        help='LEA Staff file (e.g., ccd_lea_059_*.csv)'
    )

    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: data/processed/normalized/districts_YEAR_nces.csv)'
    )

    parser.add_argument(
        '--year',
        required=True,
        help='School year (e.g., "2023-24")'
    )

    args = parser.parse_args()

    # Validate input files exist
    for file in [args.directory_file, args.membership_file, args.staff_file]:
        if not file.exists():
            logger.error(f"File not found: {file}")
            sys.exit(1)

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        year_str = args.year.replace('-', '_')
        output_file = Path(f"data/processed/normalized/districts_{year_str}_nces.csv")

    # Merge files
    result = merge_nces_ccd_files(
        args.directory_file,
        args.membership_file,
        args.staff_file,
        output_file,
        args.year
    )

    return 0


if __name__ == '__main__':
    sys.exit(main())
