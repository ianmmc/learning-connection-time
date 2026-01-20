#!/usr/bin/env python3
"""
Import Massachusetts Data to Database

This script imports DESE data from files into the database:
1. District identifiers (crosswalk) - uses state_district_crosswalk table
2. Staff data (teacher FTE)
3. Enrollment data (total K-12 enrollment)
4. Special education data (SWD counts from enrollment file)

Data sources:
- MA 2024-25 teacherdata.xlsx (DESE Profiles export)
- ma_enrollment_all_years.csv (E2C Hub Socrata export, multi-year)

Massachusetts District Code Format: 4-digit zero-padded (e.g., "0035" for Boston)
- In data files: 8-digit integer with trailing zeros (e.g., 350000 or 00350000)
- In crosswalk: 4-digit string (e.g., "0035")

Uses shared utilities from sea_import_utils.py for common operations.

Usage:
    python import_massachusetts_data.py
"""

import sys
from pathlib import Path

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
STATE_CODE = 'MA'
DATA_YEAR = '2025-26'  # Primary data year (updated to 2025-26)

# Data file paths
MA_DATA_DIR = project_root / "data" / "raw" / "state" / "massachusetts"
TEACHER_FILE = MA_DATA_DIR / "MA 2024-25 teacherdata.xlsx"
ENROLLMENT_FILE = MA_DATA_DIR / "Enrollment__Grade,_Race_Ethnicity,_Gender,_and_Selected_Populations_20260119.xlsx"


def format_ma_district_code(dist_code) -> str:
    """Convert 8-digit integer code to 4-digit zero-padded crosswalk format.

    Massachusetts uses two formats:
    - 8-digit in data files: 350000 or 00350000 (Boston)
    - 4-digit in crosswalk: "0035" (Boston)

    Conversion: Take first 4 digits after stripping trailing zeros up to 4 chars.
    Actually: Remove trailing 0000 and zero-pad to 4 digits.

    Examples:
        350000 -> "0035"
        00350000 -> "0035"
        10000 -> "0001"  (hypothetical)
    """
    # Convert to string, zero-pad to 8 digits
    code_str = str(int(dist_code)).zfill(8)
    # Remove trailing 0000 and take first 4 chars
    # But actually the format is DDDD0000, so we take first 4 digits of 8-digit padded
    return code_str[:4]


def load_ma_crosswalk(session) -> dict:
    """Load Massachusetts crosswalk from database.

    Returns:
        Dict mapping DESE District Code (4-digit zero-padded) -> NCES ID
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = 'MA'
          AND id_system = 'st_leaid'
    """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_teacher_data():
    """Load DESE teacher data from Excel file."""
    logger.info(f"Loading teacher data from: {TEACHER_FILE}")

    if not TEACHER_FILE.exists():
        logger.error(f"Teacher file not found: {TEACHER_FILE}")
        return None

    try:
        # Read Excel, skip first row (which has the title row)
        df = pd.read_excel(TEACHER_FILE, header=1)

        # Rename columns to standardized names
        df.columns = [
            'district_name', 'district_code', 'teachers_fte',
            'pct_licensed', 'student_teacher_ratio', 'pct_experienced',
            'pct_no_waiver', 'pct_in_field'
        ]

        # Filter out state totals and non-district rows
        df = df[df['district_code'].notna()]
        df = df[df['district_code'] != 'District Code']  # Header row repeated

        logger.info(f"Loaded {len(df)} district records from teacher file")
        return df
    except Exception as e:
        logger.error(f"Failed to load teacher file: {e}")
        return None


def load_enrollment_data():
    """Load DESE enrollment data from Excel file (Socrata export 2025-26)."""
    logger.info(f"Loading enrollment data from: {ENROLLMENT_FILE}")

    if not ENROLLMENT_FILE.exists():
        logger.error(f"Enrollment file not found: {ENROLLMENT_FILE}")
        return None

    try:
        df = pd.read_excel(ENROLLMENT_FILE)

        # Filter to most recent year (2026 = 2025-26 school year) and district-level only
        df = df[(df['SY'] == 2026) & (df['ORG_TYPE'] == 'District')]

        # Filter out state totals
        df = df[df['DIST_CODE'] != 0]

        logger.info(f"Loaded {len(df)} district records from enrollment file (SY 2026 = 2025-26)")
        return df
    except Exception as e:
        logger.error(f"Failed to load enrollment file: {e}")
        return None


def create_ma_tables():
    """Create Massachusetts-specific tables if they don't exist."""
    logger.info("Creating Massachusetts-specific tables...")

    with session_scope() as session:
        # Create MA district identifiers table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS ma_district_identifiers (
                nces_id VARCHAR(10) PRIMARY KEY REFERENCES districts(nces_id),
                dese_district_code VARCHAR(10) UNIQUE NOT NULL,
                district_name_dese VARCHAR(255),
                source_year VARCHAR(10),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create MA staff data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS ma_staff_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                teachers_fte NUMERIC(10, 2),
                pct_licensed NUMERIC(5, 2),
                student_teacher_ratio NUMERIC(5, 2),
                pct_experienced NUMERIC(5, 2),
                data_source VARCHAR(50) DEFAULT 'dese_profiles',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        # Create MA enrollment data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS ma_enrollment_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                total_enrollment INTEGER,
                pk_enrollment INTEGER,
                k_enrollment INTEGER,
                sped_count INTEGER,
                sped_pct NUMERIC(5, 3),
                el_count INTEGER,
                el_pct NUMERIC(5, 3),
                low_income_count INTEGER,
                low_income_pct NUMERIC(5, 3),
                data_source VARCHAR(50) DEFAULT 'dese_e2c_hub',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        session.commit()
        logger.info("Massachusetts-specific tables created successfully")


def import_district_identifiers(session, crosswalk, teacher_df, enrollment_df):
    """Import district identifiers to ma_district_identifiers table."""
    logger.info("Importing district identifiers...")

    imported = 0
    skipped = 0

    # Use teacher data for names (more complete district names)
    for _, row in teacher_df.iterrows():
        try:
            dist_code_4 = format_ma_district_code(row['district_code'])
        except (ValueError, TypeError):
            skipped += 1
            continue

        if dist_code_4 not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[dist_code_4]
        district_name = str(row.get('district_name', '')).strip()

        try:
            session.execute(text("""
                INSERT INTO ma_district_identifiers
                (nces_id, dese_district_code, district_name_dese, source_year)
                VALUES (:nces_id, :dist_code, :name, :year)
                ON CONFLICT (nces_id) DO UPDATE SET
                    district_name_dese = EXCLUDED.district_name_dese,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "dist_code": dist_code_4,
                "name": district_name,
                "year": DATA_YEAR
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import identifier for District {dist_code_4}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} district identifiers, skipped {skipped}")
    return imported, skipped


def import_staff_data(session, crosswalk, teacher_df):
    """Import staff data to ma_staff_data table."""
    logger.info("Importing staff data...")

    imported = 0
    skipped = 0

    for _, row in teacher_df.iterrows():
        try:
            dist_code_4 = format_ma_district_code(row['district_code'])
        except (ValueError, TypeError):
            skipped += 1
            continue

        if dist_code_4 not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[dist_code_4]

        # Parse student/teacher ratio (format: "11.3 to 1")
        ratio_raw = row.get('student_teacher_ratio', '')
        ratio_val = None
        if isinstance(ratio_raw, str) and 'to' in ratio_raw:
            try:
                ratio_val = float(ratio_raw.split('to')[0].strip())
            except ValueError:
                pass
        elif isinstance(ratio_raw, (int, float)):
            ratio_val = float(ratio_raw)

        try:
            session.execute(text("""
                INSERT INTO ma_staff_data
                (nces_id, year, teachers_fte, pct_licensed, student_teacher_ratio, pct_experienced)
                VALUES (:nces_id, :year, :teachers, :pct_lic, :ratio, :pct_exp)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    teachers_fte = EXCLUDED.teachers_fte,
                    pct_licensed = EXCLUDED.pct_licensed,
                    student_teacher_ratio = EXCLUDED.student_teacher_ratio,
                    pct_experienced = EXCLUDED.pct_experienced,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": DATA_YEAR,
                "teachers": safe_float(row.get('teachers_fte')),
                "pct_lic": safe_float(row.get('pct_licensed')),
                "ratio": ratio_val,
                "pct_exp": safe_float(row.get('pct_experienced'))
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import staff data for District {dist_code_4}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} staff records, skipped {skipped}")
    return imported, skipped


def import_enrollment_data(session, crosswalk, enrollment_df):
    """Import enrollment data to ma_enrollment_data table."""
    logger.info("Importing enrollment data...")

    imported = 0
    skipped = 0

    for _, row in enrollment_df.iterrows():
        try:
            dist_code_4 = format_ma_district_code(row['DIST_CODE'])
        except (ValueError, TypeError):
            skipped += 1
            continue

        if dist_code_4 not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[dist_code_4]

        try:
            session.execute(text("""
                INSERT INTO ma_enrollment_data
                (nces_id, year, total_enrollment, pk_enrollment, k_enrollment,
                 sped_count, sped_pct, el_count, el_pct, low_income_count, low_income_pct)
                VALUES (:nces_id, :year, :total, :pk, :k, :sped, :sped_pct, :el, :el_pct, :li, :li_pct)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    total_enrollment = EXCLUDED.total_enrollment,
                    pk_enrollment = EXCLUDED.pk_enrollment,
                    k_enrollment = EXCLUDED.k_enrollment,
                    sped_count = EXCLUDED.sped_count,
                    sped_pct = EXCLUDED.sped_pct,
                    el_count = EXCLUDED.el_count,
                    el_pct = EXCLUDED.el_pct,
                    low_income_count = EXCLUDED.low_income_count,
                    low_income_pct = EXCLUDED.low_income_pct,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": DATA_YEAR,
                "total": safe_int(row.get('TOTAL_CNT')),
                "pk": safe_int(row.get('PK_CNT')),
                "k": safe_int(row.get('K_CNT')),
                "sped": safe_int(row.get('SWD_CNT')),
                "sped_pct": safe_float(row.get('SWD_PCT')),
                "el": safe_int(row.get('EL_CNT')),
                "el_pct": safe_float(row.get('EL_PCT')),
                "li": safe_int(row.get('LI_CNT')),
                "li_pct": safe_float(row.get('LI_PCT'))
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import enrollment data for District {dist_code_4}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} enrollment records, skipped {skipped}")
    return imported, skipped


def main():
    """Main import function."""
    logger.info("=" * 60)
    logger.info("Starting Massachusetts Data Import")
    logger.info("=" * 60)

    # Create tables
    create_ma_tables()

    # Load data files
    teacher_df = load_teacher_data()
    enrollment_df = load_enrollment_data()

    if teacher_df is None:
        logger.error("Failed to load teacher data file. Aborting.")
        return

    if enrollment_df is None:
        logger.error("Failed to load enrollment data file. Aborting.")
        return

    # Load crosswalk
    with session_scope() as session:
        crosswalk = load_ma_crosswalk(session)
        logger.info(f"Loaded {len(crosswalk)} entries from crosswalk table")

        if len(crosswalk) == 0:
            logger.error("No MA entries in crosswalk table. "
                        "Ensure state_district_crosswalk is populated.")
            return

        # Import data
        id_imported, id_skipped = import_district_identifiers(
            session, crosswalk, teacher_df, enrollment_df
        )
        staff_imported, staff_skipped = import_staff_data(
            session, crosswalk, teacher_df
        )
        enroll_imported, enroll_skipped = import_enrollment_data(
            session, crosswalk, enrollment_df
        )

    # Summary
    logger.info("=" * 60)
    logger.info("Massachusetts Data Import Complete")
    logger.info("=" * 60)
    logger.info(f"District Identifiers: {id_imported} imported, {id_skipped} skipped")
    logger.info(f"Staff Data: {staff_imported} imported, {staff_skipped} skipped")
    logger.info(f"Enrollment Data: {enroll_imported} imported, {enroll_skipped} skipped")


if __name__ == "__main__":
    main()
