#!/usr/bin/env python3
"""
Extract grade-level enrollment data from NCES CCD Membership file

This script processes the CCD LEA-level membership file (052) which contains
student counts broken down by grade, race/ethnicity, and sex. It aggregates
these to produce district-level enrollment counts by grade level:
- Elementary (K-5)
- Middle (6-8)
- High (9-12)

OPTIMIZATION: For faster processing, use the slim enrollment file:
    data/processed/slim/enrollment_by_grade_slim.csv
This reduces file size from 618 MB to 81 MB (87% reduction) with no loss of data.

Usage:
    python extract_grade_level_enrollment.py <membership_file> [--output <output_file>]

Examples:
    # Using slim file (recommended - 87% faster):
    python extract_grade_level_enrollment.py data/processed/slim/enrollment_by_grade_slim.csv

    # Using raw file (if slim not available):
    python extract_grade_level_enrollment.py data/raw/federal/nces-ccd/2023_24/ccd_lea_052_2324_l_1a_073124.csv
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


# Grade mappings
GRADE_MAPPING = {
    'Kindergarten': 0,
    'Grade 1': 1,
    'Grade 2': 2,
    'Grade 3': 3,
    'Grade 4': 4,
    'Grade 5': 5,
    'Grade 6': 6,
    'Grade 7': 7,
    'Grade 8': 8,
    'Grade 9': 9,
    'Grade 10': 10,
    'Grade 11': 11,
    'Grade 12': 12,
}

# Grade level groupings
ELEMENTARY_GRADES = [0, 1, 2, 3, 4, 5]  # K-5
MIDDLE_GRADES = [6, 7, 8]  # 6-8
HIGH_GRADES = [9, 10, 11, 12]  # 9-12


def extract_grade_level_enrollment(membership_file: Path, output_file: Path):
    """
    Extract and aggregate enrollment by grade level from CCD membership file

    Args:
        membership_file: Path to CCD LEA-level membership file (052)
        output_file: Path to output CSV file
    """
    logger.info(f"Loading membership data from {membership_file}")

    # Read the membership file
    # This file is very large, so we'll use chunking
    chunks = []
    chunksize = 100000

    for chunk in pd.read_csv(membership_file, chunksize=chunksize, low_memory=False):
        # Filter for records we care about
        # We want records where TOTAL_INDICATOR is "Category Set A" (by grade/race/sex)
        # and where GRADE is one of our target grades
        mask = (
            (chunk['TOTAL_INDICATOR'] == 'Category Set A - By Race/Ethnicity; Sex; Grade') &
            (chunk['GRADE'].isin(GRADE_MAPPING.keys()))
        )

        filtered = chunk[mask].copy()

        if len(filtered) > 0:
            # Convert STUDENT_COUNT to numeric, treating missing/suppressed as 0
            filtered['STUDENT_COUNT'] = pd.to_numeric(
                filtered['STUDENT_COUNT'],
                errors='coerce'
            ).fillna(0)

            # Map grades to numeric values
            filtered['grade_num'] = filtered['GRADE'].map(GRADE_MAPPING)

            # Group by district and grade
            district_grade = filtered.groupby(
                ['LEAID', 'grade_num'],
                as_index=False
            )['STUDENT_COUNT'].sum()

            chunks.append(district_grade)

        logger.info(f"  Processed {len(chunks) * chunksize:,} rows...")

    if not chunks:
        logger.error("No valid enrollment data found")
        return

    # Combine all chunks
    logger.info("Combining data chunks...")
    df = pd.concat(chunks, ignore_index=True)

    # Aggregate by district and grade (in case there were duplicates across chunks)
    logger.info("Aggregating by district and grade...")
    df = df.groupby(['LEAID', 'grade_num'], as_index=False)['STUDENT_COUNT'].sum()

    # Pivot to wide format with one column per grade
    logger.info("Pivoting to wide format...")
    df_wide = df.pivot(index='LEAID', columns='grade_num', values='STUDENT_COUNT').fillna(0)

    # Ensure all grade columns exist (even if 0)
    for grade in range(0, 13):
        if grade not in df_wide.columns:
            df_wide[grade] = 0

    # Calculate grade level totals
    logger.info("Calculating grade level totals...")
    df_wide['enrollment_elementary'] = df_wide[ELEMENTARY_GRADES].sum(axis=1)
    df_wide['enrollment_middle'] = df_wide[MIDDLE_GRADES].sum(axis=1)
    df_wide['enrollment_high'] = df_wide[HIGH_GRADES].sum(axis=1)
    df_wide['enrollment_total'] = df_wide['enrollment_elementary'] + df_wide['enrollment_middle'] + df_wide['enrollment_high']

    # Reset index to make LEAID a column
    df_wide = df_wide.reset_index()

    # Rename LEAID to district_id for consistency
    df_wide = df_wide.rename(columns={'LEAID': 'district_id'})

    # Keep only the summary columns and district_id
    output_columns = [
        'district_id',
        'enrollment_elementary',
        'enrollment_middle',
        'enrollment_high',
        'enrollment_total'
    ]

    # Also keep individual grades for reference
    for grade in range(0, 13):
        col_name = f'enrollment_grade_{grade}' if grade > 0 else 'enrollment_grade_k'
        df_wide[col_name] = df_wide[grade]
        output_columns.append(col_name)

    df_output = df_wide[output_columns]

    # Save to file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_output.to_csv(output_file, index=False)

    # Report statistics
    total_districts = len(df_output)
    districts_with_elem = (df_output['enrollment_elementary'] > 0).sum()
    districts_with_middle = (df_output['enrollment_middle'] > 0).sum()
    districts_with_high = (df_output['enrollment_high'] > 0).sum()

    logger.info(f"\n{'='*60}")
    logger.info("GRADE-LEVEL ENROLLMENT EXTRACTION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Total districts: {total_districts:,}")
    logger.info(f"Districts with elementary students (K-5): {districts_with_elem:,} ({districts_with_elem/total_districts*100:.1f}%)")
    logger.info(f"Districts with middle school students (6-8): {districts_with_middle:,} ({districts_with_middle/total_districts*100:.1f}%)")
    logger.info(f"Districts with high school students (9-12): {districts_with_high:,} ({districts_with_high/total_districts*100:.1f}%)")
    logger.info(f"\nTotal enrollment:")
    logger.info(f"  Elementary: {df_output['enrollment_elementary'].sum():,.0f}")
    logger.info(f"  Middle: {df_output['enrollment_middle'].sum():,.0f}")
    logger.info(f"  High: {df_output['enrollment_high'].sum():,.0f}")
    logger.info(f"  Total: {df_output['enrollment_total'].sum():,.0f}")
    logger.info(f"\n✓ Output saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract grade-level enrollment from NCES CCD membership file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'membership_file',
        type=Path,
        help='CCD LEA-level membership file (052)'
    )

    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: data/processed/normalized/grade_level_enrollment_YEAR.csv)'
    )

    args = parser.parse_args()

    # Validate input file
    if not args.membership_file.exists():
        logger.error(f"Input file not found: {args.membership_file}")
        return 1

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        # Extract year from filename (e.g., "2324" from ccd_lea_052_2324_l_1a_073124.csv)
        filename = args.membership_file.name
        year_match = filename.split('_')[3] if '_' in filename else 'unknown'
        output_file = Path(f"data/processed/normalized/grade_level_enrollment_{year_match}.csv")

    # Process the file
    extract_grade_level_enrollment(args.membership_file, output_file)

    return 0


if __name__ == '__main__':
    sys.exit(main())
