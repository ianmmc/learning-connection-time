#!/usr/bin/env python3
"""
Import Virginia Data to Database

This script imports VDOE data from CSV files into the database:
1. District identifiers (crosswalk) - uses state_district_crosswalk table
2. Staff data (teacher FTE by position type)
3. Enrollment data (total K-12 enrollment)
4. Special education data (SPED enrollment counts)

Data sources:
- fall_membership_statistics.csv (2025-26)
- staffing_and_vacancy_report_statistics.csv (2025-26, long format)
- dec_1_statistics (Special Education Enrollment).csv (2024-25)

Uses shared utilities from sea_import_utils.py for common operations.

Virginia District Code Format: Division Number (3-digit zero-padded, e.g., "029" for Fairfax)

Usage:
    python import_virginia_data.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from sqlalchemy import text
import pandas as pd
import json
import logging

# Import shared SEA utilities
from infrastructure.database.migrations.sea_import_utils import (
    safe_float, safe_int,
    load_state_crosswalk, get_district_name,
    log_import_summary,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# State configuration
STATE_CODE = 'VA'

# Data file paths
VA_DATA_DIR = project_root / "data" / "raw" / "state" / "virginia"
ENROLLMENT_FILE = VA_DATA_DIR / "fall_membership_statistics.csv"
STAFFING_FILE = VA_DATA_DIR / "staffing_and_vacancy_report_statistics.csv"
SPECIAL_ED_FILE = VA_DATA_DIR / "dec_1_statistics (Special Education Enrollment).csv"


def load_va_crosswalk(session) -> dict:
    """Load Virginia crosswalk from database.

    Returns:
        Dict mapping VDOE Division Number (zero-padded) -> NCES ID
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = 'VA'
          AND id_system = 'st_leaid'
    """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_enrollment_data():
    """Load VDOE enrollment data from CSV file."""
    logger.info(f"Loading enrollment data from: {ENROLLMENT_FILE}")

    if not ENROLLMENT_FILE.exists():
        logger.error(f"Enrollment file not found: {ENROLLMENT_FILE}")
        return None

    try:
        df = pd.read_csv(ENROLLMENT_FILE)
        logger.info(f"Loaded {len(df)} division records from enrollment file")
        return df
    except Exception as e:
        logger.error(f"Failed to load enrollment file: {e}")
        return None


def load_staffing_data():
    """Load VDOE staffing data from CSV file (long format)."""
    logger.info(f"Loading staffing data from: {STAFFING_FILE}")

    if not STAFFING_FILE.exists():
        logger.error(f"Staffing file not found: {STAFFING_FILE}")
        return None

    try:
        df = pd.read_csv(STAFFING_FILE)
        logger.info(f"Loaded {len(df)} position records from staffing file")

        # Pivot to wide format: one row per division, columns for each position type
        df_wide = df.pivot_table(
            index=['Division Number', 'Division Name'],
            columns='Position Type',
            values='Number of Positions by FTE',
            aggfunc='first'
        ).reset_index()

        logger.info(f"Pivoted to {len(df_wide)} division records")
        return df_wide
    except Exception as e:
        logger.error(f"Failed to load/pivot staffing file: {e}")
        return None


def load_special_ed_data():
    """Load VDOE special education data from CSV file."""
    logger.info(f"Loading special ed data from: {SPECIAL_ED_FILE}")

    if not SPECIAL_ED_FILE.exists():
        logger.error(f"Special ed file not found: {SPECIAL_ED_FILE}")
        return None

    try:
        df = pd.read_csv(SPECIAL_ED_FILE)
        logger.info(f"Loaded {len(df)} division records from special ed file")
        return df
    except Exception as e:
        logger.error(f"Failed to load special ed file: {e}")
        return None


def create_va_tables():
    """Create Virginia-specific tables if they don't exist."""
    logger.info("Creating Virginia-specific tables...")

    with session_scope() as session:
        # Create VA district identifiers table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS va_district_identifiers (
                nces_id VARCHAR(10) PRIMARY KEY REFERENCES districts(nces_id),
                vdoe_division_number VARCHAR(10) UNIQUE NOT NULL,
                division_name_vdoe VARCHAR(255),
                source_year VARCHAR(10),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create VA staff data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS va_staff_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                teachers_fte NUMERIC(10, 2),
                administration_fte NUMERIC(10, 2),
                aides_paraprofessionals_fte NUMERIC(10, 2),
                non_instructional_fte NUMERIC(10, 2),
                data_source VARCHAR(50) DEFAULT 'vdoe_staffing',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        # Create VA enrollment data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS va_enrollment_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                total_enrollment NUMERIC(10, 2),
                full_time_count NUMERIC(10, 2),
                part_time_count NUMERIC(10, 2),
                data_source VARCHAR(50) DEFAULT 'vdoe_fall_membership',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        # Create VA special education data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS va_special_ed_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                sped_enrollment INTEGER,
                data_source VARCHAR(50) DEFAULT 'vdoe_special_ed',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        session.commit()
        logger.info("Virginia-specific tables created successfully")


def format_division_number(div_num):
    """Format Division Number to 3-digit zero-padded format for crosswalk."""
    return str(int(div_num)).zfill(3)


def import_district_identifiers(session, crosswalk, enrollment_df):
    """Import district identifiers to va_district_identifiers table."""
    logger.info("Importing district identifiers...")

    imported = 0
    skipped = 0

    for _, row in enrollment_df.iterrows():
        div_num = format_division_number(row.get('Division Number'))

        if div_num not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[div_num]
        division_name = row.get('Division Name', '').strip()

        try:
            session.execute(text("""
                INSERT INTO va_district_identifiers
                (nces_id, vdoe_division_number, division_name_vdoe, source_year)
                VALUES (:nces_id, :div_num, :name, :year)
                ON CONFLICT (nces_id) DO UPDATE SET
                    division_name_vdoe = EXCLUDED.division_name_vdoe,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "div_num": div_num,
                "name": division_name,
                "year": "2025-26"
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import identifier for Division {div_num}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} district identifiers, skipped {skipped}")
    return imported, skipped


def import_staff_data(session, crosswalk, staffing_df):
    """Import staff data to va_staff_data table."""
    logger.info("Importing staff data...")

    imported = 0
    skipped = 0

    for _, row in staffing_df.iterrows():
        div_num = format_division_number(row.get('Division Number'))

        if div_num not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[div_num]

        # Clean FTE values (remove commas, handle spaces)
        def clean_fte(val):
            if pd.isna(val):
                return None
            return safe_float(str(val).replace(',', '').strip())

        try:
            session.execute(text("""
                INSERT INTO va_staff_data
                (nces_id, year, teachers_fte, administration_fte,
                 aides_paraprofessionals_fte, non_instructional_fte)
                VALUES (:nces_id, :year, :teachers, :admin, :aides, :non_instr)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    teachers_fte = EXCLUDED.teachers_fte,
                    administration_fte = EXCLUDED.administration_fte,
                    aides_paraprofessionals_fte = EXCLUDED.aides_paraprofessionals_fte,
                    non_instructional_fte = EXCLUDED.non_instructional_fte,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": "2025-26",
                "teachers": clean_fte(row.get('Teachers')),
                "admin": clean_fte(row.get('Administration')),
                "aides": clean_fte(row.get('Aides and Paraprofessionals')),
                "non_instr": clean_fte(row.get('Non-Instructional Personnel'))
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import staff data for Division {div_num}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} staff records, skipped {skipped}")
    return imported, skipped


def import_enrollment_data(session, crosswalk, enrollment_df):
    """Import enrollment data to va_enrollment_data table."""
    logger.info("Importing enrollment data...")

    imported = 0
    skipped = 0

    for _, row in enrollment_df.iterrows():
        div_num = format_division_number(row.get('Division Number'))

        if div_num not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[div_num]

        # Clean enrollment values (remove commas, handle spaces)
        def clean_count(val):
            if pd.isna(val):
                return None
            return safe_float(str(val).replace(',', '').strip())

        try:
            session.execute(text("""
                INSERT INTO va_enrollment_data
                (nces_id, year, total_enrollment, full_time_count, part_time_count)
                VALUES (:nces_id, :year, :total, :ft, :pt)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    total_enrollment = EXCLUDED.total_enrollment,
                    full_time_count = EXCLUDED.full_time_count,
                    part_time_count = EXCLUDED.part_time_count,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": "2025-26",
                "total": clean_count(row.get('Total Count')),
                "ft": clean_count(row.get('FT Count')),
                "pt": clean_count(row.get('PT Count'))
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import enrollment data for Division {div_num}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} enrollment records, skipped {skipped}")
    return imported, skipped


def import_special_ed_data(session, crosswalk, sped_df):
    """Import special education data to va_special_ed_data table."""
    logger.info("Importing special education data...")

    imported = 0
    skipped = 0

    for _, row in sped_df.iterrows():
        div_num = format_division_number(row.get('Division Number'))

        if div_num not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[div_num]

        # Clean SPED count
        def clean_count(val):
            if pd.isna(val):
                return None
            return safe_int(str(val).replace(',', '').strip())

        try:
            session.execute(text("""
                INSERT INTO va_special_ed_data
                (nces_id, year, sped_enrollment)
                VALUES (:nces_id, :year, :sped_count)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    sped_enrollment = EXCLUDED.sped_enrollment,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": "2024-25",  # SPED data is from 2024-25
                "sped_count": clean_count(row.get('Total Count'))
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import SPED data for Division {div_num}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} special ed records, skipped {skipped}")
    return imported, skipped


def main():
    """Main import function."""
    logger.info("=" * 60)
    logger.info("Starting Virginia Data Import")
    logger.info("=" * 60)

    # Create tables
    create_va_tables()

    # Load data files
    enrollment_df = load_enrollment_data()
    staffing_df = load_staffing_data()
    sped_df = load_special_ed_data()

    if enrollment_df is None or staffing_df is None or sped_df is None:
        logger.error("Failed to load one or more data files. Aborting.")
        return

    # Load crosswalk
    with session_scope() as session:
        crosswalk = load_va_crosswalk(session)
        logger.info(f"Loaded {len(crosswalk)} entries from crosswalk table")

        # Import data
        id_imported, id_skipped = import_district_identifiers(session, crosswalk, enrollment_df)
        staff_imported, staff_skipped = import_staff_data(session, crosswalk, staffing_df)
        enroll_imported, enroll_skipped = import_enrollment_data(session, crosswalk, enrollment_df)
        sped_imported, sped_skipped = import_special_ed_data(session, crosswalk, sped_df)

    # Summary
    logger.info("=" * 60)
    logger.info("Virginia Data Import Complete")
    logger.info("=" * 60)
    logger.info(f"District Identifiers: {id_imported} imported, {id_skipped} skipped")
    logger.info(f"Staff Data: {staff_imported} imported, {staff_skipped} skipped")
    logger.info(f"Enrollment Data: {enroll_imported} imported, {enroll_skipped} skipped")
    logger.info(f"Special Ed Data: {sped_imported} imported, {sped_skipped} skipped")


if __name__ == "__main__":
    main()
