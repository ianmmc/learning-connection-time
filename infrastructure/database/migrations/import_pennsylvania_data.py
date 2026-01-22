#!/usr/bin/env python3
"""
Import Pennsylvania Data to Database

This script imports PDE data from Excel files into the database:
1. District identifiers (crosswalk) - uses state_district_crosswalk table
2. Staff data (classroom teachers, professional personnel)
3. Enrollment data (total K-12 enrollment by grade)

Data sources:
- pa_staffing_2024_25.xlsx (LEA_FT+PT sheet)
- pa_enrollment_2024_25.xlsx (LEA sheet)

Uses shared utilities from sea_import_utils.py for common operations.

Pennsylvania District Code Format: AUN (Administrative Unit Number) - 9-digit

Usage:
    python import_pennsylvania_data.py
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
STATE_CODE = 'PA'

# Data file paths
PA_DATA_DIR = project_root / "data" / "raw" / "state" / "pennsylvania"
STAFFING_FILE = PA_DATA_DIR / "pa_staffing_2024_25.xlsx"
ENROLLMENT_FILE = PA_DATA_DIR / "pa_enrollment_2024_25.xlsx"


def load_pa_crosswalk(session) -> dict:
    """Load Pennsylvania crosswalk from database.

    Returns:
        Dict mapping PDE AUN -> NCES ID
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = 'PA'
          AND id_system = 'st_leaid'
    """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_staffing_data():
    """Load PDE staffing data from Excel file."""
    logger.info(f"Loading staffing data from: {STAFFING_FILE}")

    if not STAFFING_FILE.exists():
        logger.error(f"Staffing file not found: {STAFFING_FILE}")
        return None

    try:
        df = pd.read_excel(
            STAFFING_FILE,
            sheet_name="LEA_FT+PT",
            skiprows=4  # Skip header rows
        )
        logger.info(f"Loaded {len(df)} district records from staffing file")
        return df
    except Exception as e:
        logger.error(f"Failed to load staffing file: {e}")
        return None


def load_enrollment_data():
    """Load PDE enrollment data from Excel file."""
    logger.info(f"Loading enrollment data from: {ENROLLMENT_FILE}")

    if not ENROLLMENT_FILE.exists():
        logger.error(f"Enrollment file not found: {ENROLLMENT_FILE}")
        return None

    try:
        df = pd.read_excel(
            ENROLLMENT_FILE,
            sheet_name="LEA",
            header=4  # Row 4 is the header
        )
        logger.info(f"Loaded {len(df)} district records from enrollment file")
        return df
    except Exception as e:
        logger.error(f"Failed to load enrollment file: {e}")
        return None


def create_pa_tables():
    """Create Pennsylvania-specific tables if they don't exist."""
    logger.info("Creating Pennsylvania-specific tables...")

    with session_scope() as session:
        # Create PA district identifiers table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS pa_district_identifiers (
                nces_id VARCHAR(10) PRIMARY KEY REFERENCES districts(nces_id),
                pde_aun VARCHAR(10) UNIQUE NOT NULL,
                district_name_pde VARCHAR(255),
                lea_type VARCHAR(10),
                county VARCHAR(50),
                source_year VARCHAR(10),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create PA staff data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS pa_staff_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                classroom_teachers_fte NUMERIC(10, 2),
                professional_personnel_fte NUMERIC(10, 2),
                administrators_fte NUMERIC(10, 2),
                coordinate_services_fte NUMERIC(10, 2),
                other_professional_fte NUMERIC(10, 2),
                data_source VARCHAR(50) DEFAULT 'pde_professional_staff',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        # Create PA enrollment data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS pa_enrollment_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                total_k12 NUMERIC(10, 2),
                prekf_enrollment NUMERIC(10, 2),
                k5f_enrollment NUMERIC(10, 2),
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
                data_source VARCHAR(50) DEFAULT 'pde_enrollment',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        session.commit()
        logger.info("Pennsylvania-specific tables created successfully")


def import_district_identifiers(session, crosswalk, staffing_df, enrollment_df):
    """Import district identifiers to pa_district_identifiers table."""
    logger.info("Importing district identifiers...")

    imported = 0
    skipped = 0

    # Use enrollment file for primary district info
    for _, row in enrollment_df.iterrows():
        aun = str(safe_int(row.get('AUN')))

        if aun not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[aun]
        district_name = row.get('LEA Name', '').strip()
        lea_type = row.get('LEA Type', '').strip()
        county = row.get('County', '').strip()

        try:
            session.execute(text("""
                INSERT INTO pa_district_identifiers
                (nces_id, pde_aun, district_name_pde, lea_type, county, source_year)
                VALUES (:nces_id, :aun, :name, :type, :county, :year)
                ON CONFLICT (nces_id) DO UPDATE SET
                    district_name_pde = EXCLUDED.district_name_pde,
                    lea_type = EXCLUDED.lea_type,
                    county = EXCLUDED.county,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "aun": aun,
                "name": district_name,
                "type": lea_type,
                "county": county,
                "year": "2024-25"
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import identifier for AUN {aun}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} district identifiers, skipped {skipped}")
    return imported, skipped


def import_staff_data(session, crosswalk, staffing_df):
    """Import staff data to pa_staff_data table."""
    logger.info("Importing staff data...")

    imported = 0
    skipped = 0

    for _, row in staffing_df.iterrows():
        aun = str(safe_int(row.get('AUN')))

        if aun not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[aun]

        try:
            session.execute(text("""
                INSERT INTO pa_staff_data
                (nces_id, year, classroom_teachers_fte, professional_personnel_fte,
                 administrators_fte, coordinate_services_fte, other_professional_fte)
                VALUES (:nces_id, :year, :ct, :pp, :ad, :co, :ot)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    classroom_teachers_fte = EXCLUDED.classroom_teachers_fte,
                    professional_personnel_fte = EXCLUDED.professional_personnel_fte,
                    administrators_fte = EXCLUDED.administrators_fte,
                    coordinate_services_fte = EXCLUDED.coordinate_services_fte,
                    other_professional_fte = EXCLUDED.other_professional_fte,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": "2024-25",
                "ct": safe_float(row.get('CT')),    # Classroom Teachers
                "pp": safe_float(row.get('PP')),    # Professional Personnel
                "ad": safe_float(row.get('Ad')),    # Administrators
                "co": safe_float(row.get('Co')),    # Coordinate Services
                "ot": safe_float(row.get('Ot'))     # Other
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import staff data for AUN {aun}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} staff records, skipped {skipped}")
    return imported, skipped


def import_enrollment_data(session, crosswalk, enrollment_df):
    """Import enrollment data to pa_enrollment_data table."""
    logger.info("Importing enrollment data...")

    imported = 0
    skipped = 0

    for _, row in enrollment_df.iterrows():
        aun = str(safe_int(row.get('AUN')))

        if aun not in crosswalk:
            skipped += 1
            continue

        nces_id = crosswalk[aun]

        try:
            # Column names are numbers (1.0, 2.0, etc.)
            session.execute(text("""
                INSERT INTO pa_enrollment_data
                (nces_id, year, total_k12, prekf_enrollment, k5f_enrollment,
                 g1_enrollment, g2_enrollment, g3_enrollment, g4_enrollment,
                 g5_enrollment, g6_enrollment, g7_enrollment, g8_enrollment,
                 g9_enrollment, g10_enrollment, g11_enrollment, g12_enrollment)
                VALUES (:nces_id, :year, :total, :prekf, :k5f, :g1, :g2, :g3, :g4,
                        :g5, :g6, :g7, :g8, :g9, :g10, :g11, :g12)
                ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                    total_k12 = EXCLUDED.total_k12,
                    prekf_enrollment = EXCLUDED.prekf_enrollment,
                    k5f_enrollment = EXCLUDED.k5f_enrollment,
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
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "year": "2024-25",
                "total": safe_float(row.get('Total')),
                "prekf": safe_float(row.get('PKF')),
                "k5f": safe_float(row.get('K5F')),
                "g1": safe_float(row.get(1.0)),    # Grades are numeric columns
                "g2": safe_float(row.get(2.0)),
                "g3": safe_float(row.get(3.0)),
                "g4": safe_float(row.get(4.0)),
                "g5": safe_float(row.get(5.0)),
                "g6": safe_float(row.get(6.0)),
                "g7": safe_float(row.get(7.0)),
                "g8": safe_float(row.get(8.0)),
                "g9": safe_float(row.get(9.0)),
                "g10": safe_float(row.get(10.0)),
                "g11": safe_float(row.get(11.0)),
                "g12": safe_float(row.get(12.0))
            })
            imported += 1
        except Exception as e:
            logger.error(f"Failed to import enrollment data for AUN {aun}: {e}")
            skipped += 1

    session.commit()
    logger.info(f"Imported {imported} enrollment records, skipped {skipped}")
    return imported, skipped


def main():
    """Main import function."""
    logger.info("=" * 60)
    logger.info("Starting Pennsylvania Data Import")
    logger.info("=" * 60)

    # Create tables
    create_pa_tables()

    # Load data files
    staffing_df = load_staffing_data()
    enrollment_df = load_enrollment_data()

    if staffing_df is None or enrollment_df is None:
        logger.error("Failed to load one or more data files. Aborting.")
        return

    # Load crosswalk
    with session_scope() as session:
        crosswalk = load_pa_crosswalk(session)
        logger.info(f"Loaded {len(crosswalk)} entries from crosswalk table")

        # Import data
        id_imported, id_skipped = import_district_identifiers(session, crosswalk, staffing_df, enrollment_df)
        staff_imported, staff_skipped = import_staff_data(session, crosswalk, staffing_df)
        enroll_imported, enroll_skipped = import_enrollment_data(session, crosswalk, enrollment_df)

    # Summary
    logger.info("=" * 60)
    logger.info("Pennsylvania Data Import Complete")
    logger.info("=" * 60)
    logger.info(f"District Identifiers: {id_imported} imported, {id_skipped} skipped")
    logger.info(f"Staff Data: {staff_imported} imported, {staff_skipped} skipped")
    logger.info(f"Enrollment Data: {enroll_imported} imported, {enroll_skipped} skipped")


if __name__ == "__main__":
    main()
