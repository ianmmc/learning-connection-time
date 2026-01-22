#!/usr/bin/env python3
"""
Import Illinois Data to Database

This script imports ISBE data from the Report Card Excel file into the database:
1. District identifiers (crosswalk) - uses state_district_crosswalk table
2. Staff data (Total Teacher FTE, support staff)
3. Enrollment data (total and SPED-disaggregated)

The ISBE Report Card file contains all data in a single "General" sheet.

Uses shared utilities from sea_import_utils.py for common operations.

RCDTS Format: 15-digit code
  - Positions 1-2: Region code
  - Positions 3-5: County code
  - Positions 6-9: District number
  - Positions 10-11: Type code
  - Positions 12-15: School code (0000 for district level)

Example: Chicago = 150162990250000 -> 15-016-2990-25 (in crosswalk format)

Usage:
    python import_illinois_data.py
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
STATE_CODE = 'IL'

# Data file paths
IL_DATA_DIR = project_root / "data" / "raw" / "state" / "illinois"
REPORT_CARD_FILE = IL_DATA_DIR / "il_report_card_2023_24.xlsx"


def rcdts_to_state_id(rcdts):
    """Convert 15-digit RCDTS to crosswalk format (RR-CCC-DDDD-TT).

    Args:
        rcdts: 15-digit RCDTS code (e.g., 150162990250000)

    Returns:
        Formatted state ID (e.g., 15-016-2990-25)
    """
    s = str(rcdts)
    return f'{s[0:2]}-{s[2:5]}-{s[5:9]}-{s[9:11]}'


def load_il_crosswalk(session) -> dict:
    """Load Illinois crosswalk from database.

    Returns:
        Dict mapping ISBE state district ID -> NCES ID
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = 'IL'
          AND id_system = 'st_leaid'
    """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_report_card_data():
    """Load ISBE Report Card data from Excel file."""
    logger.info(f"Loading Report Card data from: {REPORT_CARD_FILE}")

    if not REPORT_CARD_FILE.exists():
        logger.error(f"Report Card file not found: {REPORT_CARD_FILE}")
        return None

    try:
        df = pd.read_excel(
            REPORT_CARD_FILE,
            sheet_name="General"
        )
        # Filter to district-level records only
        districts = df[df["Type"] == "District"].copy()
        logger.info(f"Loaded {len(districts)} district records from Report Card file")
        return districts
    except Exception as e:
        logger.error(f"Failed to load Report Card file: {e}")
        return None


def create_il_tables():
    """Create Illinois-specific tables if they don't exist."""
    logger.info("Creating Illinois-specific tables...")

    with session_scope() as session:
        # Create IL district identifiers table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS il_district_identifiers (
                nces_id VARCHAR(10) PRIMARY KEY REFERENCES districts(nces_id),
                isbe_rcdts VARCHAR(20) UNIQUE NOT NULL,
                district_name_isbe VARCHAR(255),
                source_year VARCHAR(10),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create IL staff data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS il_staff_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                total_teacher_fte NUMERIC(10, 2),
                counselor_fte NUMERIC(10, 2),
                nurse_fte NUMERIC(10, 2),
                psychologist_fte NUMERIC(10, 2),
                social_worker_fte NUMERIC(10, 2),
                ptr_elementary NUMERIC(5, 2),
                ptr_high_school NUMERIC(5, 2),
                teacher_retention_rate NUMERIC(5, 2),
                teacher_avg_salary NUMERIC(10, 2),
                data_source VARCHAR(50) DEFAULT 'isbe_report_card',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        # Create IL enrollment data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS il_enrollment_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                total_enrollment INTEGER,
                pct_white NUMERIC(5, 2),
                pct_black NUMERIC(5, 2),
                pct_hispanic NUMERIC(5, 2),
                pct_asian NUMERIC(5, 2),
                pct_low_income NUMERIC(5, 2),
                pct_iep NUMERIC(5, 2),
                pct_el NUMERIC(5, 2),
                students_with_disabilities INTEGER,
                iep_students INTEGER,
                data_source VARCHAR(50) DEFAULT 'isbe_report_card',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        session.commit()
        logger.info("✅ Tables created/verified")


# Note: safe_float and safe_int are now imported from sea_import_utils


def import_district_identifiers(df):
    """Import Illinois district identifiers from Report Card data."""
    if df is None:
        logger.warning("No data to import")
        return 0

    logger.info("Importing Illinois district identifiers...")

    with session_scope() as session:
        # Load crosswalk from database
        il_crosswalk = load_il_crosswalk(session)
        logger.info(f"Loaded {len(il_crosswalk)} Illinois districts from crosswalk table")

        count = 0
        for _, row in df.iterrows():
            try:
                # Convert RCDTS to state ID format
                rcdts = str(row['RCDTS'])
                state_id = rcdts_to_state_id(rcdts)

                # Look up NCES ID
                nces_id = il_crosswalk.get(state_id)
                if not nces_id:
                    continue

                district_name = str(row.get('District', '')).strip()

                # Insert into il_district_identifiers
                session.execute(text("""
                    INSERT INTO il_district_identifiers
                    (nces_id, isbe_rcdts, district_name_isbe, source_year)
                    VALUES (:nces_id, :rcdts, :name, '2023-24')
                    ON CONFLICT (nces_id) DO UPDATE SET
                        isbe_rcdts = EXCLUDED.isbe_rcdts,
                        district_name_isbe = EXCLUDED.district_name_isbe,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "rcdts": rcdts,
                    "name": district_name
                })
                count += 1

            except Exception as e:
                logger.debug(f"Failed to import {rcdts}: {e}")

        session.commit()
        logger.info(f"✅ Imported {count} district identifiers")
        return count


def import_staff_data(df):
    """Import staff data into database."""
    if df is None:
        logger.warning("No data to import")
        return 0

    logger.info("Importing Illinois staff data...")

    # Load crosswalk once for efficiency
    with session_scope() as session:
        il_crosswalk = load_il_crosswalk(session)

    count = 0
    skipped = 0
    for _, row in df.iterrows():
        try:
            # Convert RCDTS to state ID format
            rcdts = str(row['RCDTS'])
            state_id = rcdts_to_state_id(rcdts)

            # Look up NCES ID from crosswalk
            nces_id = il_crosswalk.get(state_id)
            if not nces_id:
                skipped += 1
                continue

            # Extract staff data
            total_teacher_fte = safe_float(row.get('Total Teacher FTE'))
            counselor_fte = safe_float(row.get('School Counselor FTE'))
            nurse_fte = safe_float(row.get('School Nurse FTE'))
            psychologist_fte = safe_float(row.get('School Psychologist FTE'))
            social_worker_fte = safe_float(row.get('School Social Worker FTE'))
            ptr_elementary = safe_float(row.get('Pupil Teacher Ratio - Elementary'))
            ptr_high_school = safe_float(row.get('Pupil Teacher Ratio - High School'))
            teacher_retention = safe_float(row.get('Teacher Retention Rate'))
            teacher_salary = safe_float(row.get('Teacher Avg Salary'))

            # Skip if no teacher FTE
            if total_teacher_fte is None or total_teacher_fte == 0:
                continue

            # Use individual transaction for each row
            with session_scope() as session:
                session.execute(text("""
                    INSERT INTO il_staff_data
                    (nces_id, year, total_teacher_fte, counselor_fte, nurse_fte,
                     psychologist_fte, social_worker_fte, ptr_elementary,
                     ptr_high_school, teacher_retention_rate, teacher_avg_salary)
                    VALUES (:nces_id, '2023-24', :teacher_fte, :counselor, :nurse,
                            :psychologist, :social_worker, :ptr_elem,
                            :ptr_hs, :retention, :salary)
                    ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                        total_teacher_fte = EXCLUDED.total_teacher_fte,
                        counselor_fte = EXCLUDED.counselor_fte,
                        nurse_fte = EXCLUDED.nurse_fte,
                        psychologist_fte = EXCLUDED.psychologist_fte,
                        social_worker_fte = EXCLUDED.social_worker_fte,
                        ptr_elementary = EXCLUDED.ptr_elementary,
                        ptr_high_school = EXCLUDED.ptr_high_school,
                        teacher_retention_rate = EXCLUDED.teacher_retention_rate,
                        teacher_avg_salary = EXCLUDED.teacher_avg_salary,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "teacher_fte": total_teacher_fte,
                    "counselor": counselor_fte,
                    "nurse": nurse_fte,
                    "psychologist": psychologist_fte,
                    "social_worker": social_worker_fte,
                    "ptr_elem": ptr_elementary,
                    "ptr_hs": ptr_high_school,
                    "retention": teacher_retention,
                    "salary": teacher_salary
                })
                session.commit()
                count += 1

        except Exception as e:
            logger.debug(f"Skipping row: {str(e)[:100]}")
            continue

    logger.info(f"✅ Imported {count} staff records ({skipped} skipped - no NCES match)")
    return count


def import_enrollment_data(df):
    """Import enrollment data into database."""
    if df is None:
        logger.warning("No data to import")
        return 0

    logger.info("Importing Illinois enrollment data...")

    # Load crosswalk once for efficiency
    with session_scope() as session:
        il_crosswalk = load_il_crosswalk(session)

    count = 0
    skipped = 0
    for _, row in df.iterrows():
        try:
            # Convert RCDTS to state ID format
            rcdts = str(row['RCDTS'])
            state_id = rcdts_to_state_id(rcdts)

            # Look up NCES ID from crosswalk
            nces_id = il_crosswalk.get(state_id)
            if not nces_id:
                skipped += 1
                continue

            # Extract enrollment data
            total_enrollment = safe_int(row.get('# Student Enrollment'))
            pct_white = safe_float(row.get('% Student Enrollment - White'))
            pct_black = safe_float(row.get('% Student Enrollment - Black or African American'))
            pct_hispanic = safe_float(row.get('% Student Enrollment - Hispanic or Latino'))
            pct_asian = safe_float(row.get('% Student Enrollment - Asian'))
            pct_low_income = safe_float(row.get('% Student Enrollment - Low Income'))
            pct_iep = safe_float(row.get('% Student Enrollment - IEP'))
            pct_el = safe_float(row.get('% Student Enrollment - EL'))
            students_with_disabilities = safe_int(row.get('# Student Enrollment - Children with Disabilities'))
            iep_students = safe_int(row.get('# Student Enrollment - IEP'))

            # Skip if no enrollment
            if total_enrollment is None or total_enrollment == 0:
                continue

            # Use individual transaction for each row
            with session_scope() as session:
                session.execute(text("""
                    INSERT INTO il_enrollment_data
                    (nces_id, year, total_enrollment, pct_white, pct_black,
                     pct_hispanic, pct_asian, pct_low_income, pct_iep, pct_el,
                     students_with_disabilities, iep_students)
                    VALUES (:nces_id, '2023-24', :enrollment, :white, :black,
                            :hispanic, :asian, :low_income, :iep, :el,
                            :swd, :iep_students)
                    ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                        total_enrollment = EXCLUDED.total_enrollment,
                        pct_white = EXCLUDED.pct_white,
                        pct_black = EXCLUDED.pct_black,
                        pct_hispanic = EXCLUDED.pct_hispanic,
                        pct_asian = EXCLUDED.pct_asian,
                        pct_low_income = EXCLUDED.pct_low_income,
                        pct_iep = EXCLUDED.pct_iep,
                        pct_el = EXCLUDED.pct_el,
                        students_with_disabilities = EXCLUDED.students_with_disabilities,
                        iep_students = EXCLUDED.iep_students,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "enrollment": total_enrollment,
                    "white": pct_white,
                    "black": pct_black,
                    "hispanic": pct_hispanic,
                    "asian": pct_asian,
                    "low_income": pct_low_income,
                    "iep": pct_iep,
                    "el": pct_el,
                    "swd": students_with_disabilities,
                    "iep_students": iep_students
                })
                session.commit()
                count += 1

        except Exception as e:
            logger.debug(f"Skipping row: {str(e)[:100]}")
            continue

    logger.info(f"✅ Imported {count} enrollment records ({skipped} skipped - no NCES match)")
    return count


def main():
    """Main import process."""
    logger.info("=" * 80)
    logger.info("STARTING ILLINOIS DATA IMPORT")
    logger.info("=" * 80)

    # Create tables
    create_il_tables()

    # Load data
    df = load_report_card_data()

    # Import data
    id_count = import_district_identifiers(df)
    staff_count = import_staff_data(df)
    enroll_count = import_enrollment_data(df)

    logger.info("=" * 80)
    logger.info("IMPORT COMPLETE")
    logger.info(f"  District identifiers: {id_count}")
    logger.info(f"  Staff records: {staff_count}")
    logger.info(f"  Enrollment records: {enroll_count}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
