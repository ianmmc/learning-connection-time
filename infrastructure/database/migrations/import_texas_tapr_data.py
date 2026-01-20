#!/usr/bin/env python3
"""
Import Texas TAPR 2024-25 Data to Database

This script imports TEA TAPR data from CSV files into the database:
1. Staff data (teacher FTE by program, demographics, experience)
2. Enrollment data (by grade, demographics, special populations)

Data sources:
- 2025 District Staff Information.csv (488KB, 1,208 districts)
- 2025 District Student Information.csv (1.0MB, 1,208 districts)
- 2025 District Reference.csv (136KB, 1,208 districts)

Texas District Code Format: 6-digit TEA district number (e.g., "227901" for Houston ISD)
- Crosswalk via tx_district_identifiers table (TEA → NCES)

Uses shared utilities from sea_import_utils.py for common operations.

Usage:
    python import_texas_tapr_data.py [--year 2024-25] [--dry-run]
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
STATE_CODE = 'TX'
DATA_YEAR = '2024-25'

# Data file paths
TX_DATA_DIR = project_root / "data" / "raw" / "state" / "texas" / "2024-25"
STAFF_FILE = TX_DATA_DIR / "2025 District Staff Information.csv"
STUDENT_FILE = TX_DATA_DIR / "2025 District Student Information.csv"
REFERENCE_FILE = TX_DATA_DIR / "2025 District Reference.csv"


def log_stats(stats: dict) -> None:
    """Log import statistics."""
    logger.info(f"  Total records: {stats['total']}")
    logger.info(f"  Matched with NCES: {stats['matched']}")
    logger.info(f"  Skipped (no match): {stats['skipped']}")
    logger.info(f"  Inserted/Updated: {stats['inserted']}")


def load_tx_crosswalk(session) -> dict:
    """Load Texas crosswalk from database.

    Returns:
        Dict mapping TEA District Number (6-digit) -> NCES ID
    """
    result = session.execute(text("""
        SELECT tea_district_no, nces_id
        FROM tx_district_identifiers
    """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_staff_data() -> pd.DataFrame:
    """Load TAPR staff data from CSV file."""
    logger.info(f"Loading staff data from: {STAFF_FILE}")

    # Read CSV with first row as verbose column names
    df = pd.read_csv(STAFF_FILE)

    # Extract TEA district code and district name from first two columns
    df.columns = [col.strip('"') for col in df.columns]

    logger.info(f"  Loaded {len(df)} district records")
    logger.info(f"  Columns: {len(df.columns)}")

    return df


def load_student_data() -> pd.DataFrame:
    """Load TAPR student data from CSV file."""
    logger.info(f"Loading student data from: {STUDENT_FILE}")

    df = pd.read_csv(STUDENT_FILE)
    df.columns = [col.strip('"') for col in df.columns]

    logger.info(f"  Loaded {len(df)} district records")

    return df


def import_staff_to_database(session, staff_df: pd.DataFrame, crosswalk: dict, dry_run: bool = False):
    """Import staff data to tx_staff_data table."""
    logger.info("Importing staff data to database...")

    stats = {'total': 0, 'matched': 0, 'skipped': 0, 'inserted': 0}

    for _, row in staff_df.iterrows():
        stats['total'] += 1

        tea_code = str(row['6 Digit County District Number']).strip()
        district_name = row['District Name']

        # Get NCES ID from crosswalk
        nces_id = crosswalk.get(tea_code)
        if not nces_id:
            if stats['skipped'] < 5:
                logger.warning(f"  No NCES match for TEA {tea_code} ({district_name})")
            stats['skipped'] += 1
            continue

        stats['matched'] += 1

        # Extract key staff fields
        # Use internal column names (second header row)
        teacher_total = safe_float(row.iloc[2])  # DPSTTOFC
        teacher_special_ed = safe_float(row.iloc[39])  # DPSTSPFC
        teacher_regular = safe_float(row.iloc[34])  # DPSTREFC
        teacher_bilingual = safe_float(row.iloc[36])  # DPSTBIFC
        teacher_gifted = safe_float(row.iloc[38])  # DPSTGIFC

        if not dry_run:
            # Check if record exists
            existing = session.execute(text("""
                SELECT nces_id FROM tx_staff_data
                WHERE nces_id = :nces_id AND year = :year
            """), {"nces_id": nces_id, "year": DATA_YEAR}).fetchone()

            if existing:
                # Update existing record
                session.execute(text("""
                    UPDATE tx_staff_data
                    SET teachers_total_fte = :teachers_total,
                        teachers_special_ed_fte = :teachers_sped,
                        teachers_regular_fte = :teachers_regular,
                        teachers_bilingual_fte = :teachers_bilingual,
                        teachers_gifted_fte = :teachers_gifted,
                        data_source = 'tea_tapr',
                        updated_at = NOW()
                    WHERE nces_id = :nces_id AND year = :year
                """), {
                    "nces_id": nces_id,
                    "year": DATA_YEAR,
                    "teachers_total": teacher_total,
                    "teachers_sped": teacher_special_ed,
                    "teachers_regular": teacher_regular,
                    "teachers_bilingual": teacher_bilingual,
                    "teachers_gifted": teacher_gifted
                })
            else:
                # Insert new record
                session.execute(text("""
                    INSERT INTO tx_staff_data (
                        nces_id, tea_district_no, year,
                        teachers_total_fte,
                        teachers_special_ed_fte,
                        teachers_regular_fte,
                        teachers_bilingual_fte,
                        teachers_gifted_fte,
                        data_source
                    ) VALUES (
                        :nces_id, :tea_code, :year,
                        :teachers_total, :teachers_sped, :teachers_regular,
                        :teachers_bilingual, :teachers_gifted,
                        'tea_tapr'
                    )
                """), {
                    "nces_id": nces_id,
                    "tea_code": tea_code,
                    "year": DATA_YEAR,
                    "teachers_total": teacher_total,
                    "teachers_sped": teacher_special_ed,
                    "teachers_regular": teacher_regular,
                    "teachers_bilingual": teacher_bilingual,
                    "teachers_gifted": teacher_gifted
                })

            stats['inserted'] += 1

        if stats['matched'] % 100 == 0:
            logger.info(f"  Processed {stats['matched']} districts...")

    if not dry_run:
        session.commit()

    return stats


def import_enrollment_to_database(session, student_df: pd.DataFrame, crosswalk: dict, dry_run: bool = False):
    """Import enrollment data to tx_enrollment_data table."""
    logger.info("Importing enrollment data to database...")

    stats = {'total': 0, 'matched': 0, 'skipped': 0, 'inserted': 0}

    for _, row in student_df.iterrows():
        stats['total'] += 1

        tea_code = str(row['6 Digit County District Number']).strip()

        # Get NCES ID from crosswalk
        nces_id = crosswalk.get(tea_code)
        if not nces_id:
            stats['skipped'] += 1
            continue

        stats['matched'] += 1

        # Extract enrollment fields
        # Total enrollment
        total_enrollment = safe_int(row.iloc[27])  # DPETALLC

        # By grade
        enrollment_pk = safe_int(row.iloc[14])  # DPETGPKC
        enrollment_k = safe_int(row.iloc[15])  # DPETGKNC
        enrollment_g1 = safe_int(row.iloc[16])  # DPETG01C
        enrollment_g2 = safe_int(row.iloc[17])  # DPETG02C
        enrollment_g3 = safe_int(row.iloc[18])  # DPETG03C
        enrollment_g4 = safe_int(row.iloc[19])  # DPETG04C
        enrollment_g5 = safe_int(row.iloc[20])  # DPETG05C
        enrollment_g6 = safe_int(row.iloc[21])  # DPETG06C
        enrollment_g7 = safe_int(row.iloc[22])  # DPETG07C
        enrollment_g8 = safe_int(row.iloc[23])  # DPETG08C
        enrollment_g9 = safe_int(row.iloc[24])  # DPETG09C
        enrollment_g10 = safe_int(row.iloc[25])  # DPETG10C
        enrollment_g11 = safe_int(row.iloc[26])  # DPETG11C
        enrollment_g12 = safe_int(row.iloc[27])  # DPETG12C

        # Special populations
        enrollment_sped = safe_int(row.iloc[28])  # DPETSPEC
        enrollment_ell = safe_int(row.iloc[31])  # DPETLEPC
        enrollment_econ_disadv = safe_int(row.iloc[32])  # DPETECOC

        if not dry_run:
            # Check if record exists
            existing = session.execute(text("""
                SELECT nces_id FROM tx_enrollment_data
                WHERE nces_id = :nces_id AND year = :year
            """), {"nces_id": nces_id, "year": DATA_YEAR}).fetchone()

            if existing:
                # Update
                session.execute(text("""
                    UPDATE tx_enrollment_data
                    SET total_enrollment = :total,
                        enrollment_pk = :pk, enrollment_k = :k,
                        enrollment_g1 = :g1, enrollment_g2 = :g2,
                        enrollment_g3 = :g3, enrollment_g4 = :g4,
                        enrollment_g5 = :g5, enrollment_g6 = :g6,
                        enrollment_g7 = :g7, enrollment_g8 = :g8,
                        enrollment_g9 = :g9, enrollment_g10 = :g10,
                        enrollment_g11 = :g11, enrollment_g12 = :g12,
                        enrollment_sped = :sped,
                        enrollment_ell = :ell,
                        enrollment_econ_disadvantaged = :econ,
                        data_source = 'tea_tapr',
                        updated_at = NOW()
                    WHERE nces_id = :nces_id AND year = :year
                """), {
                    "nces_id": nces_id, "year": DATA_YEAR,
                    "total": total_enrollment,
                    "pk": enrollment_pk, "k": enrollment_k,
                    "g1": enrollment_g1, "g2": enrollment_g2, "g3": enrollment_g3,
                    "g4": enrollment_g4, "g5": enrollment_g5, "g6": enrollment_g6,
                    "g7": enrollment_g7, "g8": enrollment_g8, "g9": enrollment_g9,
                    "g10": enrollment_g10, "g11": enrollment_g11, "g12": enrollment_g12,
                    "sped": enrollment_sped, "ell": enrollment_ell, "econ": enrollment_econ_disadv
                })
            else:
                # Insert
                session.execute(text("""
                    INSERT INTO tx_enrollment_data (
                        nces_id, tea_district_no, year,
                        total_enrollment,
                        enrollment_pk, enrollment_k,
                        enrollment_g1, enrollment_g2, enrollment_g3,
                        enrollment_g4, enrollment_g5, enrollment_g6,
                        enrollment_g7, enrollment_g8, enrollment_g9,
                        enrollment_g10, enrollment_g11, enrollment_g12,
                        enrollment_sped, enrollment_ell, enrollment_econ_disadvantaged,
                        data_source
                    ) VALUES (
                        :nces_id, :tea_code, :year,
                        :total,
                        :pk, :k, :g1, :g2, :g3, :g4, :g5, :g6,
                        :g7, :g8, :g9, :g10, :g11, :g12,
                        :sped, :ell, :econ,
                        'tea_tapr'
                    )
                """), {
                    "nces_id": nces_id, "tea_code": tea_code, "year": DATA_YEAR,
                    "total": total_enrollment,
                    "pk": enrollment_pk, "k": enrollment_k,
                    "g1": enrollment_g1, "g2": enrollment_g2, "g3": enrollment_g3,
                    "g4": enrollment_g4, "g5": enrollment_g5, "g6": enrollment_g6,
                    "g7": enrollment_g7, "g8": enrollment_g8, "g9": enrollment_g9,
                    "g10": enrollment_g10, "g11": enrollment_g11, "g12": enrollment_g12,
                    "sped": enrollment_sped, "ell": enrollment_ell, "econ": enrollment_econ_disadv
                })

            stats['inserted'] += 1

        if stats['matched'] % 100 == 0:
            logger.info(f"  Processed {stats['matched']} districts...")

    if not dry_run:
        session.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Import Texas TAPR 2024-25 data")
    parser.add_argument("--year", default="2024-25", help="School year (default: 2024-25)")
    parser.add_argument("--dry-run", action="store_true", help="Preview import without committing")
    args = parser.parse_args()

    global DATA_YEAR
    DATA_YEAR = args.year

    logger.info("=" * 70)
    logger.info("TEXAS TAPR DATA IMPORT")
    logger.info("=" * 70)
    logger.info(f"Year: {DATA_YEAR}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("")

    # Load data files
    staff_df = load_staff_data()
    student_df = load_student_data()

    with session_scope() as session:
        # Load crosswalk
        logger.info("Loading TX crosswalk from database...")
        crosswalk = load_tx_crosswalk(session)
        logger.info(f"  Loaded {len(crosswalk)} TEA → NCES mappings")
        logger.info("")

        # Import staff data
        staff_stats = import_staff_to_database(session, staff_df, crosswalk, args.dry_run)
        logger.info("")
        logger.info("Staff Import Summary:")
        log_stats(staff_stats)
        logger.info("")

        # Import enrollment data
        enroll_stats = import_enrollment_to_database(session, student_df, crosswalk, args.dry_run)
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
