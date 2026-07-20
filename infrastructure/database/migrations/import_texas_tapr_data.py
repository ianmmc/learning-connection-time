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

All fields are read BY COLUMN NAME (issue #17). The old iloc-positional access was
off by one for nearly every field: e.g. row.iloc[27] was used for BOTH total
enrollment and grade 12 (it is actually the grade-11 count; "All Students Count"
is column 29), iloc[14] labeled PK was the EE (Early Education) count, and every
staff program field (regular/bilingual/gifted/special-ed) was shifted one column
left (iloc[39] labeled Special Ed is the Gifted & Talented count). Column names in
the TAPR export are verbose and year-prefixed ("District 2025 Staff: Teacher Total
Full Time Equiv Count"), so fields are resolved by unique year-agnostic suffix via
find_column(). Files are read with dtype=str so district numbers keep leading
zeros and masking sentinels (-1/-2/-3) reach safe_float/safe_int intact.

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
    safe_float, safe_int, format_state_id,
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

DISTRICT_NO_COL = '6 Digit County District Number'

# Year-agnostic column-name suffixes (headers are prefixed "District <YYYY> ...").
# Verified against the 2024-25 TAPR district CSV headers (issue #17).
STAFF_COLUMNS = {
    'teacher_total': 'Staff: Teacher Total Full Time Equiv Count',
    'teacher_regular': 'Staff: Teacher Regular Program Full Time Equiv Count',
    'teacher_bilingual': 'Staff: Teacher Bilingual Program Full Time Equiv Count',
    'teacher_gifted': 'Staff: Teacher Gifted & Talented Program Full Time Equiv Count',
    'teacher_special_ed': 'Staff: Teacher Special Education Full Time Equiv Count',
}

STUDENT_COLUMNS = {
    'total': 'Student Membership: All Students Count',
    'pk': 'Student Membership: PK Count',
    'k': 'Student Membership: KG Count',
    'g1': 'Student Membership: 01 Count',
    'g2': 'Student Membership: 02 Count',
    'g3': 'Student Membership: 03 Count',
    'g4': 'Student Membership: 04 Count',
    'g5': 'Student Membership: 05 Count',
    'g6': 'Student Membership: 06 Count',
    'g7': 'Student Membership: 07 Count',
    'g8': 'Student Membership: 08 Count',
    'g9': 'Student Membership: 09 Count',
    'g10': 'Student Membership: 10 Count',
    'g11': 'Student Membership: 11 Count',
    'g12': 'Student Membership: 12 Count',
    'sped': 'Student Membership: Special Ed Count',
    'ell': 'Student Membership: EB/EL Count',
    'econ_disadv': 'Student Membership: Econ Disadv Count',
}


def find_column(columns, suffix: str) -> str:
    """Resolve the single column name ending with `suffix`.

    Raises KeyError when the suffix matches zero or multiple columns, so a header
    change fails loudly instead of silently importing the wrong field (the failure
    mode positional iloc access created).
    """
    matches = [c for c in columns if c.endswith(suffix)]
    if len(matches) != 1:
        raise KeyError(
            f"expected exactly one column ending with {suffix!r}, found {matches!r}"
        )
    return matches[0]


def resolve_columns(df: pd.DataFrame, spec: dict) -> dict:
    """Map each field key in `spec` to the actual DataFrame column name."""
    return {key: find_column(df.columns, suffix) for key, suffix in spec.items()}


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

    # Read CSV with verbose column names; dtype=str keeps leading zeros in the
    # district number and delivers masking sentinels intact (issue #17/#22)
    df = pd.read_csv(STAFF_FILE, dtype=str)

    df.columns = [col.strip('"') for col in df.columns]

    logger.info(f"  Loaded {len(df)} district records")
    logger.info(f"  Columns: {len(df.columns)}")

    return df


def load_student_data() -> pd.DataFrame:
    """Load TAPR student data from CSV file."""
    logger.info(f"Loading student data from: {STUDENT_FILE}")

    df = pd.read_csv(STUDENT_FILE, dtype=str)
    df.columns = [col.strip('"') for col in df.columns]

    logger.info(f"  Loaded {len(df)} district records")

    return df


def import_staff_to_database(session, staff_df: pd.DataFrame, crosswalk: dict, dry_run: bool = False):
    """Import staff data to tx_staff_data table."""
    logger.info("Importing staff data to database...")

    stats = {'total': 0, 'matched': 0, 'skipped': 0, 'inserted': 0}

    cols = resolve_columns(staff_df, STAFF_COLUMNS)

    for _, row in staff_df.iterrows():
        stats['total'] += 1

        # format_state_id handles Excel float-casts like '227901.0' that
        # missed the 6-digit crosswalk keys (issue #409); missing/NaN codes
        # skip cleanly. Missing 'District Name' must not KeyError (issue #370).
        try:
            tea_code = format_state_id('TX', row[DISTRICT_NO_COL])
        except (ValueError, TypeError, KeyError):
            stats['skipped'] += 1
            continue
        district_name = row.get('District Name', '')

        # Get NCES ID from crosswalk
        nces_id = crosswalk.get(tea_code)
        if not nces_id:
            if stats['skipped'] < 5:
                logger.warning(f"  No NCES match for TEA {tea_code} ({district_name})")
            stats['skipped'] += 1
            continue

        stats['matched'] += 1

        # Extract key staff fields by column name (issue #17)
        teacher_total = safe_float(row[cols['teacher_total']])
        teacher_special_ed = safe_float(row[cols['teacher_special_ed']])
        teacher_regular = safe_float(row[cols['teacher_regular']])
        teacher_bilingual = safe_float(row[cols['teacher_bilingual']])
        teacher_gifted = safe_float(row[cols['teacher_gifted']])

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

    # No commit here: main() commits once after BOTH imports succeed, so a
    # failed enrollment import can't leave committed staff-only state (issue #410)
    if not dry_run:
        session.flush()

    return stats


def import_enrollment_to_database(session, student_df: pd.DataFrame, crosswalk: dict, dry_run: bool = False):
    """Import enrollment data to tx_enrollment_data table."""
    logger.info("Importing enrollment data to database...")

    stats = {'total': 0, 'matched': 0, 'skipped': 0, 'inserted': 0}

    cols = resolve_columns(student_df, STUDENT_COLUMNS)

    for _, row in student_df.iterrows():
        stats['total'] += 1

        # Same Excel-float normalization as the staff loop (issue #409)
        try:
            tea_code = format_state_id('TX', row[DISTRICT_NO_COL])
        except (ValueError, TypeError, KeyError):
            stats['skipped'] += 1
            continue

        # Get NCES ID from crosswalk
        nces_id = crosswalk.get(tea_code)
        if not nces_id:
            stats['skipped'] += 1
            continue

        stats['matched'] += 1

        # Extract enrollment fields by column name (issue #17 — the old iloc
        # access used column 27 for BOTH total and grade 12, and was off by one
        # for every grade)
        total_enrollment = safe_int(row[cols['total']])

        # By grade
        enrollment_pk = safe_int(row[cols['pk']])
        enrollment_k = safe_int(row[cols['k']])
        enrollment_g1 = safe_int(row[cols['g1']])
        enrollment_g2 = safe_int(row[cols['g2']])
        enrollment_g3 = safe_int(row[cols['g3']])
        enrollment_g4 = safe_int(row[cols['g4']])
        enrollment_g5 = safe_int(row[cols['g5']])
        enrollment_g6 = safe_int(row[cols['g6']])
        enrollment_g7 = safe_int(row[cols['g7']])
        enrollment_g8 = safe_int(row[cols['g8']])
        enrollment_g9 = safe_int(row[cols['g9']])
        enrollment_g10 = safe_int(row[cols['g10']])
        enrollment_g11 = safe_int(row[cols['g11']])
        enrollment_g12 = safe_int(row[cols['g12']])

        # Special populations
        enrollment_sped = safe_int(row[cols['sped']])
        enrollment_ell = safe_int(row[cols['ell']])
        enrollment_econ_disadv = safe_int(row[cols['econ_disadv']])

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
        session.flush()

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
        if not crosswalk:
            # An empty crosswalk means EVERY district silently skips and the
            # run reports success while importing nothing (issue #408)
            raise RuntimeError(
                "tx_district_identifiers is empty — run import_tx_crosswalk.py first"
            )
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

        # Single commit AFTER both imports — per-function commits could leave
        # staff-only state when the enrollment import failed (issue #410)
        if not args.dry_run:
            session.commit()

    logger.info("")
    logger.info("=" * 70)
    if args.dry_run:
        logger.info("DRY RUN COMPLETE - Run without --dry-run to import")
    else:
        logger.info("IMPORT COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
