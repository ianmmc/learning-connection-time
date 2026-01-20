#!/usr/bin/env python3
"""
Import California Staff Ratios 2024-25 Data to Database

This script imports CDE staff ratio data from tab-delimited files into the database:
1. Staff data (teacher FTE, admin FTE, pupil services FTE)
2. Enrollment data (total enrollment by district)

Data source:
- strat2425.txt (3.1MB, ~30,209 records including district/school/state levels)
- Filter to district-level totals: Aggregate Level='D', Charter='ALL', DASS='ALL', Grade Span='ALL'
- Results in ~1,016 district records

California District Code Format: 7-digit CDS code (County-District: CCCDDDD)
- Example: "0110017" = Alameda County (01) + Alameda COE (10017)
- Crosswalk via ST_LEAID field in NCES CCD: "CA-CCCDDDD"

Uses shared utilities from sea_import_utils.py for common operations.

Usage:
    python import_california_staff_data.py [--year 2024-25] [--dry-run]
"""

import sys
from pathlib import Path
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from sqlalchemy import text
import pandas as pd
import logging

# Import shared SEA utilities
from infrastructure.database.migrations.sea_import_utils import (
    safe_float, safe_int,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# State configuration
STATE_CODE = 'CA'
DATA_YEAR = '2024-25'

# Data file paths
CA_DATA_DIR = project_root / "data" / "raw" / "state" / "california" / "2024_25"
STAFF_RATIO_FILE = CA_DATA_DIR / "strat2425.txt"
ENROLLMENT_FILE = CA_DATA_DIR / "cdenroll2425.txt"


def log_stats(stats: dict) -> None:
    """Log import statistics."""
    logger.info(f"  Total records: {stats['total']}")
    logger.info(f"  Matched with NCES: {stats['matched']}")
    logger.info(f"  Skipped (no match): {stats['skipped']}")
    logger.info(f"  Inserted/Updated: {stats['inserted']}")


def load_ca_crosswalk(session) -> dict:
    """Load California crosswalk from database.

    Returns:
        Dict mapping CDS Code (7-digit) -> NCES ID
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = 'CA'
          AND id_system = 'st_leaid'
    """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_staff_ratio_data() -> pd.DataFrame:
    """Load CDE staff ratio data from tab-delimited file.

    Filters to district-level totals only:
    - Aggregate Level = 'D'
    - Charter School = 'ALL'
    - DASS = 'ALL'
    - School Grade Span = 'ALL'
    """
    logger.info(f"Loading staff ratio data from: {STAFF_RATIO_FILE}")

    # Read tab-delimited file (use latin1 encoding for CDE files)
    df = pd.read_csv(STAFF_RATIO_FILE, sep='\t', dtype=str, encoding='latin1')

    logger.info(f"  Total records: {len(df):,}")

    # Filter to district totals
    district_df = df[
        (df['Aggregate Level'] == 'D') &
        (df['Charter School'] == 'ALL') &
        (df['DASS'] == 'ALL') &
        (df['School Grade Span'] == 'ALL')
    ].copy()

    logger.info(f"  District-level records: {len(district_df):,}")

    # Build CDS code from County Code + District Code
    district_df['cds_code'] = (
        district_df['County Code'].str.zfill(2) +
        district_df['District Code'].str.zfill(5)
    )

    return district_df


def import_staff_to_database(session, staff_df: pd.DataFrame, crosswalk: dict, dry_run: bool = False):
    """Import staff data to ca_staff_data table."""
    logger.info("Importing staff data to database...")

    stats = {'total': 0, 'matched': 0, 'skipped': 0, 'inserted': 0}

    for _, row in staff_df.iterrows():
        stats['total'] += 1

        cds_code = row['cds_code']
        district_name = row['District Name']

        # Get NCES ID from crosswalk
        nces_id = crosswalk.get(cds_code)
        if not nces_id:
            if stats['skipped'] < 5:
                logger.warning(f"  No NCES match for CDS {cds_code} ({district_name})")
            stats['skipped'] += 1
            continue

        stats['matched'] += 1

        # Extract staff fields
        total_enrollment = safe_int(row['TOTAL_ENR_N'])
        teachers_fte = safe_float(row['TCH_FTE_N'])
        admin_fte = safe_float(row['ADM_FTE_N'])
        pupil_services_fte = safe_float(row['PSV_FTE_N'])
        other_staff_fte = safe_float(row['OTH_FTE_N'])

        # Calculate K-12 enrollment (exclude PK if needed)
        # For now, use TOTAL_ENR_N as is since it's district-level

        if not dry_run:
            # Check if record exists
            existing = session.execute(text("""
                SELECT nces_id FROM ca_staff_data
                WHERE nces_id = :nces_id AND year = :year
            """), {"nces_id": nces_id, "year": DATA_YEAR}).fetchone()

            if existing:
                # Update existing record
                session.execute(text("""
                    UPDATE ca_staff_data
                    SET teachers_fte = :teachers_fte,
                        admin_fte = :admin_fte,
                        pupil_services_fte = :pupil_services_fte,
                        other_staff_fte = :other_staff_fte,
                        data_source = 'cde_staff_ratios',
                        updated_at = NOW()
                    WHERE nces_id = :nces_id AND year = :year
                """), {
                    "nces_id": nces_id,
                    "year": DATA_YEAR,
                    "teachers_fte": teachers_fte,
                    "admin_fte": admin_fte,
                    "pupil_services_fte": pupil_services_fte,
                    "other_staff_fte": other_staff_fte
                })
            else:
                # Insert new record
                session.execute(text("""
                    INSERT INTO ca_staff_data (
                        nces_id, cds_code, year,
                        teachers_fte,
                        admin_fte,
                        pupil_services_fte,
                        other_staff_fte,
                        data_source
                    ) VALUES (
                        :nces_id, :cds_code, :year,
                        :teachers_fte, :admin_fte, :pupil_services_fte, :other_staff_fte,
                        'cde_staff_ratios'
                    )
                """), {
                    "nces_id": nces_id,
                    "cds_code": cds_code,
                    "year": DATA_YEAR,
                    "teachers_fte": teachers_fte,
                    "admin_fte": admin_fte,
                    "pupil_services_fte": pupil_services_fte,
                    "other_staff_fte": other_staff_fte
                })

            stats['inserted'] += 1

        if stats['matched'] % 100 == 0:
            logger.info(f"  Processed {stats['matched']} districts...")

    if not dry_run:
        session.commit()

    return stats


def import_enrollment_to_database(session, staff_df: pd.DataFrame, crosswalk: dict, dry_run: bool = False):
    """Import enrollment data to ca_enrollment_data table.

    Note: Using enrollment from staff ratio file. Could also load from cdenroll2425.txt
    if more detailed grade-level breakdowns are needed.
    """
    logger.info("Importing enrollment data to database...")

    stats = {'total': 0, 'matched': 0, 'skipped': 0, 'inserted': 0}

    for _, row in staff_df.iterrows():
        stats['total'] += 1

        cds_code = row['cds_code']

        # Get NCES ID from crosswalk
        nces_id = crosswalk.get(cds_code)
        if not nces_id:
            stats['skipped'] += 1
            continue

        stats['matched'] += 1

        # Extract enrollment
        total_enrollment = safe_int(row['TOTAL_ENR_N'])

        if not dry_run:
            # Check if record exists
            existing = session.execute(text("""
                SELECT nces_id FROM ca_enrollment_data
                WHERE nces_id = :nces_id AND year = :year
            """), {"nces_id": nces_id, "year": DATA_YEAR}).fetchone()

            if existing:
                # Update
                session.execute(text("""
                    UPDATE ca_enrollment_data
                    SET total_k12 = :total_k12,
                        data_source = 'cde_staff_ratios',
                        updated_at = NOW()
                    WHERE nces_id = :nces_id AND year = :year
                """), {
                    "nces_id": nces_id,
                    "year": DATA_YEAR,
                    "total_k12": total_enrollment
                })
            else:
                # Insert
                session.execute(text("""
                    INSERT INTO ca_enrollment_data (
                        nces_id, cds_code, year,
                        total_k12,
                        data_source
                    ) VALUES (
                        :nces_id, :cds_code, :year,
                        :total_k12,
                        'cde_staff_ratios'
                    )
                """), {
                    "nces_id": nces_id,
                    "cds_code": cds_code,
                    "year": DATA_YEAR,
                    "total_k12": total_enrollment
                })

            stats['inserted'] += 1

        if stats['matched'] % 100 == 0:
            logger.info(f"  Processed {stats['matched']} districts...")

    if not dry_run:
        session.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Import California staff ratio data 2024-25")
    parser.add_argument("--year", default="2024-25", help="School year (default: 2024-25)")
    parser.add_argument("--dry-run", action="store_true", help="Preview import without committing")
    args = parser.parse_args()

    global DATA_YEAR
    DATA_YEAR = args.year

    logger.info("=" * 70)
    logger.info("CALIFORNIA STAFF RATIO DATA IMPORT")
    logger.info("=" * 70)
    logger.info(f"Year: {DATA_YEAR}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("")

    # Load data files
    staff_df = load_staff_ratio_data()

    with session_scope() as session:
        # Load crosswalk
        logger.info("Loading CA crosswalk from database...")
        crosswalk = load_ca_crosswalk(session)
        logger.info(f"  Loaded {len(crosswalk)} CDS → NCES mappings")
        logger.info("")

        # Import staff data
        staff_stats = import_staff_to_database(session, staff_df, crosswalk, args.dry_run)
        logger.info("")
        logger.info("Staff Import Summary:")
        log_stats(staff_stats)
        logger.info("")

        # Import enrollment data
        enroll_stats = import_enrollment_to_database(session, staff_df, crosswalk, args.dry_run)
        logger.info("")
        logger.info("Enrollment Import Summary:")
        log_stats(enroll_stats)

    logger.info("")
    logger.info("=" * 70)
    if args.dry_run:
        logger.info("DRY RUN COMPLETE - Run without --dry-run to import")
    else:
        logger.info("IMPORT COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
