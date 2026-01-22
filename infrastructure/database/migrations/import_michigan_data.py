#!/usr/bin/env python3
"""
Import Michigan Data to Database

This script imports MDE data from multiple Excel files into the database:
1. District identifiers (crosswalk) - uses state_district_crosswalk table
2. Staff data (teacher FTE, special ed instructional staff)
3. Enrollment data (total K-12 enrollment by grade and demographics)
4. Special education data (IEP counts, SPED percentages)

Data sources:
- mi_staffing_2023_24.xlsx (District sheet)
- Spring_2024_Headcount.xlsx (Fall Dist K-12 Total Data sheet)
- mi_special_ed_2023_24.xlsx (Fall 2023 Data sheet)

Uses shared utilities from sea_import_utils.py for common operations.

Michigan District Code Format: 5-digit (e.g., 82015 for Detroit)

Usage:
    python import_michigan_data.py
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
STATE_CODE = 'MI'

# Data file paths
MI_DATA_DIR = project_root / "data" / "raw" / "state" / "michigan"
STAFFING_FILE = MI_DATA_DIR / "mi_staffing_2023_24.xlsx"
ENROLLMENT_FILE = MI_DATA_DIR / "Spring_2024_Headcount.xlsx"
SPECIAL_ED_FILE = MI_DATA_DIR / "mi_special_ed_2023_24.xlsx"


def load_mi_crosswalk(session) -> dict:
    """Load Michigan crosswalk from database.

    Returns:
        Dict mapping MDE state district ID -> NCES ID
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = 'MI'
          AND id_system = 'st_leaid'
    """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_staffing_data():
    """Load MDE staffing data from Excel file."""
    logger.info(f"Loading staffing data from: {STAFFING_FILE}")

    if not STAFFING_FILE.exists():
        logger.error(f"Staffing file not found: {STAFFING_FILE}")
        return None

    try:
        df = pd.read_excel(
            STAFFING_FILE,
            sheet_name="District",
            skiprows=4  # Skip header rows
        )
        logger.info(f"Loaded {len(df)} district records from staffing file")
        return df
    except Exception as e:
        logger.error(f"Failed to load staffing file: {e}")
        return None


def load_enrollment_data():
    """Load MDE enrollment data from Excel file."""
    logger.info(f"Loading enrollment data from: {ENROLLMENT_FILE}")

    if not ENROLLMENT_FILE.exists():
        logger.error(f"Enrollment file not found: {ENROLLMENT_FILE}")
        return None

    try:
        df = pd.read_excel(
            ENROLLMENT_FILE,
            sheet_name="Fall Dist K-12 Total Data",
            skiprows=4  # Skip header rows
        )
        logger.info(f"Loaded {len(df)} district records from enrollment file")
        return df
    except Exception as e:
        logger.error(f"Failed to load enrollment file: {e}")
        return None


def load_special_ed_data():
    """Load MDE special education data from Excel file."""
    logger.info(f"Loading special ed data from: {SPECIAL_ED_FILE}")

    if not SPECIAL_ED_FILE.exists():
        logger.error(f"Special ed file not found: {SPECIAL_ED_FILE}")
        return None

    try:
        df = pd.read_excel(
            SPECIAL_ED_FILE,
            sheet_name="Fall 2023 Data",
            skiprows=4  # Skip header rows
        )
        logger.info(f"Loaded {len(df)} district records from special ed file")
        return df
    except Exception as e:
        logger.error(f"Failed to load special ed file: {e}")
        return None


def create_mi_tables():
    """Create Michigan-specific tables if they don't exist."""
    logger.info("Creating Michigan-specific tables...")

    with session_scope() as session:
        # Create MI district identifiers table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS mi_district_identifiers (
                nces_id VARCHAR(10) PRIMARY KEY REFERENCES districts(nces_id),
                mde_district_code VARCHAR(10) UNIQUE NOT NULL,
                district_name_mde VARCHAR(255),
                source_year VARCHAR(10),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create MI staff data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS mi_staff_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                total_teacher_fte NUMERIC(10, 2),
                sped_instructional_fte NUMERIC(10, 2),
                instructional_aide_fte NUMERIC(10, 2),
                instructional_support_fte NUMERIC(10, 2),
                data_source VARCHAR(50) DEFAULT 'mde_staffing',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        # Create MI enrollment data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS mi_enrollment_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                total_k12 NUMERIC(10, 2),
                k_enrollment NUMERIC(10, 2),
                g1_enrollment NUMERIC(10, 2),
                g2_enrollment NUMERIC(10, 2),
                g3_enrollment NUMERIC(10, 2),
                g4_enrollment NUMERIC(10, 2),
                g5_enrollment NUMERIC(10, 2),
                g6_enrollment NUMERIC(10, 2),
                g7_enrollment NUMERIC(10, 2),
                g8_enrollment NUMERIC(10, 2),
                g9_enrollment NUMERIC(10, 2),
                g10_enrollment NUMERIC(10, 2),
                g11_enrollment NUMERIC(10, 2),
                g12_enrollment NUMERIC(10, 2),
                male_count NUMERIC(10, 2),
                female_count NUMERIC(10, 2),
                data_source VARCHAR(50) DEFAULT 'mde_headcount',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        # Create MI special education data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS mi_special_ed_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                students_with_iep INTEGER,
                sped_percentage NUMERIC(5, 2),
                data_source VARCHAR(50) DEFAULT 'mde_special_ed',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        session.commit()
        logger.info("Michigan-specific tables created successfully")


def import_district_identifiers(session, crosswalk, staffing_df):
    """Import district identifiers to mi_district_identifiers table."""
    logger.info("Importing district identifiers...")

    imported = 0
    skipped = 0

    for _, row in staffing_df.iterrows():
        district_code = str(safe_int(row.get('DCODE')))

        if district_code not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[district_code]
        district_name = row.get('DNAME', '').strip()

        try:
            session.execute(text("""
                INSERT INTO mi_district_identifiers
                (nces_id, mde_district_code, district_name_mde, source_year)
                VALUES (:nces_id, :code, :name, :year)
                ON CONFLICT (nces_id) DO UPDATE SET
                    district_name_mde = EXCLUDED.district_name_mde,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "code": district_code,
                "name": district_name,
                "year": "2023-24"
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import identifier for {district_code}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} district identifiers, skipped {skipped}")
    return imported, skipped


def import_staff_data(session, crosswalk, staffing_df):
    """Import staff data to mi_staff_data table."""
    logger.info("Importing staff data...")

    imported = 0
    skipped = 0

    for _, row in staffing_df.iterrows():
        district_code = str(safe_int(row.get('DCODE')))

        if district_code not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[district_code]

        try:
            session.execute(text("""
                INSERT INTO mi_staff_data
                (nces_id, year, total_teacher_fte, sped_instructional_fte,
                 instructional_aide_fte, instructional_support_fte)
                VALUES (:nces_id, :year, :teachers, :se_instr, :inst_aide, :inst_sup)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    total_teacher_fte = EXCLUDED.total_teacher_fte,
                    sped_instructional_fte = EXCLUDED.sped_instructional_fte,
                    instructional_aide_fte = EXCLUDED.instructional_aide_fte,
                    instructional_support_fte = EXCLUDED.instructional_support_fte,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": "2023-24",
                "teachers": safe_float(row.get('TEACHER')),
                "se_instr": safe_float(row.get('SE_INSTR')),
                "inst_aide": safe_float(row.get('INST_AID')),
                "inst_sup": safe_float(row.get('INST_SUP'))
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import staff data for {district_code}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} staff records, skipped {skipped}")
    return imported, skipped


def import_enrollment_data(session, crosswalk, enrollment_df):
    """Import enrollment data to mi_enrollment_data table."""
    logger.info("Importing enrollment data...")

    imported = 0
    skipped = 0

    for _, row in enrollment_df.iterrows():
        district_code = str(safe_int(row.get('District Code')))

        if district_code not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[district_code]

        try:
            session.execute(text("""
                INSERT INTO mi_enrollment_data
                (nces_id, year, total_k12, k_enrollment, g1_enrollment, g2_enrollment,
                 g3_enrollment, g4_enrollment, g5_enrollment, g6_enrollment,
                 g7_enrollment, g8_enrollment, g9_enrollment, g10_enrollment,
                 g11_enrollment, g12_enrollment, male_count, female_count)
                VALUES (:nces_id, :year, :total, :k, :g1, :g2, :g3, :g4, :g5,
                        :g6, :g7, :g8, :g9, :g10, :g11, :g12, :male, :female)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    total_k12 = EXCLUDED.total_k12,
                    k_enrollment = EXCLUDED.k_enrollment,
                    g1_enrollment = EXCLUDED.g1_enrollment,
                    g2_enrollment = EXCLUDED.g2_enrollment,
                    g3_enrollment = EXCLUDED.g3_enrollment,
                    g4_enrollment = EXCLUDED.g4_enrollment,
                    g5_enrollment = EXCLUDED.g5_enrollment,
                    g6_enrollment = EXCLUDED.g6_enrollment,
                    g7_enrollment = EXCLUDED.g7_enrollment,
                    g8_enrollment = EXCLUDED.g8_enrollment,
                    g9_enrollment = EXCLUDED.g9_enrollment,
                    g10_enrollment = EXCLUDED.g10_enrollment,
                    g11_enrollment = EXCLUDED.g11_enrollment,
                    g12_enrollment = EXCLUDED.g12_enrollment,
                    male_count = EXCLUDED.male_count,
                    female_count = EXCLUDED.female_count,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": "2023-24",
                "total": safe_float(row.get('tot_all')),
                "k": safe_float(row.get('k_totl')),
                "g1": safe_float(row.get('g1_totl')),
                "g2": safe_float(row.get('g2_totl')),
                "g3": safe_float(row.get('g3_totl')),
                "g4": safe_float(row.get('g4_totl')),
                "g5": safe_float(row.get('g5_totl')),
                "g6": safe_float(row.get('g6_totl')),
                "g7": safe_float(row.get('g7_totl')),
                "g8": safe_float(row.get('g8_totl')),
                "g9": safe_float(row.get('g9_totl')),
                "g10": safe_float(row.get('g10_totl')),
                "g11": safe_float(row.get('g11_totl')),
                "g12": safe_float(row.get('g12_totl')),
                "male": safe_float(row.get('tot_male')),
                "female": safe_float(row.get('tot_fem'))
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import enrollment data for {district_code}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} enrollment records, skipped {skipped}")
    return imported, skipped


def import_special_ed_data(session, crosswalk, sped_df):
    """Import special education data to mi_special_ed_data table."""
    logger.info("Importing special education data...")

    imported = 0
    skipped = 0

    for _, row in sped_df.iterrows():
        # SPED file uses DCODE.1 for district code
        district_code = str(safe_int(row.get('DCODE.1')))

        if district_code not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[district_code]

        try:
            session.execute(text("""
                INSERT INTO mi_special_ed_data
                (nces_id, year, students_with_iep, sped_percentage)
                VALUES (:nces_id, :year, :iep_count, :sped_pct)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    students_with_iep = EXCLUDED.students_with_iep,
                    sped_percentage = EXCLUDED.sped_percentage,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": "2023-24",
                "iep_count": safe_int(row.get('StudwI E P')),
                "sped_pct": safe_float(row.get('SpEd%'))
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import SPED data for {district_code}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} special ed records, skipped {skipped}")
    return imported, skipped


def main():
    """Main import function."""
    logger.info("=" * 60)
    logger.info("Starting Michigan Data Import")
    logger.info("=" * 60)

    # Create tables
    create_mi_tables()

    # Load data files
    staffing_df = load_staffing_data()
    enrollment_df = load_enrollment_data()
    sped_df = load_special_ed_data()

    if staffing_df is None or enrollment_df is None or sped_df is None:
        logger.error("Failed to load one or more data files. Aborting.")
        return

    # Load crosswalk
    with session_scope() as session:
        crosswalk = load_mi_crosswalk(session)
        logger.info(f"Loaded {len(crosswalk)} entries from crosswalk table")

        # Import data
        id_imported, id_skipped = import_district_identifiers(session, crosswalk, staffing_df)
        staff_imported, staff_skipped = import_staff_data(session, crosswalk, staffing_df)
        enroll_imported, enroll_skipped = import_enrollment_data(session, crosswalk, enrollment_df)
        sped_imported, sped_skipped = import_special_ed_data(session, crosswalk, sped_df)

    # Summary
    logger.info("=" * 60)
    logger.info("Michigan Data Import Complete")
    logger.info("=" * 60)
    logger.info(f"District Identifiers: {id_imported} imported, {id_skipped} skipped")
    logger.info(f"Staff Data: {staff_imported} imported, {staff_skipped} skipped")
    logger.info(f"Enrollment Data: {enroll_imported} imported, {enroll_skipped} skipped")
    logger.info(f"Special Ed Data: {sped_imported} imported, {sped_skipped} skipped")


if __name__ == "__main__":
    main()
