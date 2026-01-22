#!/usr/bin/env python3
"""
Import New York Data to Database

This script imports NYSED data from Excel files into the database:
1. District identifiers (crosswalk) - uses state_district_crosswalk table
2. Staff data (from Personnel Master File)
3. Enrollment data (total and SPED-disaggregated)

Uses shared utilities from sea_import_utils.py for common operations.

Usage:
    python import_new_york_data.py
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
    format_state_id, log_import_summary,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# State configuration
STATE_CODE = 'NY'

# Data file paths
NY_DATA_DIR = project_root / "data" / "raw" / "state" / "new-york"
STAFF_FILE = NY_DATA_DIR / "ny_staffing_2023_24.xlsx"
ENROLLMENT_FILE = NY_DATA_DIR / "ny_enrollment_district_2023_24.xlsx"
SPED_ENROLLMENT_FILE = NY_DATA_DIR / "ny_enrollment_sped_2023_24.xlsx"


def load_ny_crosswalk(session) -> dict:
    """Load New York crosswalk from database.

    Returns:
        Dict mapping NYSED state district ID -> NCES ID
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = 'NY'
          AND id_system = 'st_leaid'
    """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_staff_data():
    """Load staff data from NYSED Personnel Master File."""
    logger.info(f"Loading staff data from: {STAFF_FILE}")

    if not STAFF_FILE.exists():
        logger.error(f"Staff file not found: {STAFF_FILE}")
        return None

    try:
        df = pd.read_excel(
            STAFF_FILE,
            sheet_name="STAFF_RATIOS"
        )
        logger.info(f"Loaded {len(df)} rows from staff file")
        return df
    except Exception as e:
        logger.error(f"Failed to load staff file: {e}")
        return None


def load_enrollment_data():
    """Load enrollment data from NYSED file."""
    logger.info(f"Loading enrollment data from: {ENROLLMENT_FILE}")

    if not ENROLLMENT_FILE.exists():
        logger.error(f"Enrollment file not found: {ENROLLMENT_FILE}")
        return None

    try:
        df = pd.read_excel(
            ENROLLMENT_FILE,
            sheet_name="public-district-2023-24"
        )
        logger.info(f"Loaded {len(df)} rows from enrollment file")
        return df
    except Exception as e:
        logger.error(f"Failed to load enrollment file: {e}")
        return None


def load_sped_enrollment_data():
    """Load SPED-disaggregated enrollment data from NYSED file."""
    logger.info(f"Loading SPED enrollment data from: {SPED_ENROLLMENT_FILE}")

    if not SPED_ENROLLMENT_FILE.exists():
        logger.error(f"SPED enrollment file not found: {SPED_ENROLLMENT_FILE}")
        return None

    try:
        df = pd.read_excel(
            SPED_ENROLLMENT_FILE,
            sheet_name="public-district-2023-24"
        )
        logger.info(f"Loaded {len(df)} rows from SPED enrollment file")
        return df
    except Exception as e:
        logger.error(f"Failed to load SPED enrollment file: {e}")
        return None


def create_ny_tables():
    """Create New York-specific tables if they don't exist."""
    logger.info("Creating New York-specific tables...")

    with session_scope() as session:
        # Create NY district identifiers table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS ny_district_identifiers (
                nces_id VARCHAR(10) PRIMARY KEY REFERENCES districts(nces_id),
                nysed_district_id VARCHAR(20) UNIQUE NOT NULL,
                district_name_nysed VARCHAR(255),
                source_year VARCHAR(10),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create NY staff data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS ny_staff_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                staff_category VARCHAR(100) NOT NULL,
                fte NUMERIC(10, 2),
                enrollment_k12 INTEGER,
                district_ratio NUMERIC(10, 2),
                data_source VARCHAR(50) DEFAULT 'nysed_pmf',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, staff_category, data_source)
            )
        """))

        # Create NY enrollment data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS ny_enrollment_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                subgroup VARCHAR(100) NOT NULL,
                enrollment_prek12 INTEGER,
                enrollment_by_grade JSONB,
                data_source VARCHAR(50) DEFAULT 'nysed_sirs',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, subgroup, data_source)
            )
        """))

        session.commit()
        logger.info("✅ Tables created/verified")


def import_district_identifiers():
    """Import New York district identifiers from crosswalk table."""
    logger.info("Importing New York district identifiers from crosswalk table...")

    with session_scope() as session:
        # Load crosswalk from database
        ny_crosswalk = load_ny_crosswalk(session)
        logger.info(f"Loaded {len(ny_crosswalk)} New York districts from crosswalk table")

        count = 0
        for nysed_id, nces_id in ny_crosswalk.items():
            try:
                # Get district name from districts table
                result = session.execute(text("""
                    SELECT name FROM districts WHERE nces_id = :nces_id
                """), {"nces_id": nces_id})
                row = result.fetchone()

                if not row:
                    logger.debug(f"District {nces_id} not found in districts table")
                    continue

                district_name = row[0]

                # Insert into ny_district_identifiers
                session.execute(text("""
                    INSERT INTO ny_district_identifiers
                    (nces_id, nysed_district_id, district_name_nysed, source_year)
                    VALUES (:nces_id, :nysed_id, :name, '2023-24')
                    ON CONFLICT (nces_id) DO UPDATE SET
                        nysed_district_id = EXCLUDED.nysed_district_id,
                        district_name_nysed = EXCLUDED.district_name_nysed,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "nysed_id": nysed_id,
                    "name": district_name
                })
                count += 1

            except Exception as e:
                logger.error(f"Failed to import {nysed_id}: {e}")

        session.commit()
        logger.info(f"✅ Imported {count} district identifiers")
        return count


def import_staff_data(df):
    """Import staff data into database.

    NYSED Personnel Master File has one row per district per staff category.
    """
    if df is None:
        logger.warning("No staff data to import")
        return 0

    logger.info("Importing New York staff data...")

    # Load crosswalk once for efficiency
    with session_scope() as session:
        ny_crosswalk = load_ny_crosswalk(session)

    count = 0
    skipped = 0
    for _, row in df.iterrows():
        try:
            # Extract state district ID using safe conversion
            raw_id = safe_int(row.get('STATE_DISTRICT_ID'))
            if raw_id is None:
                skipped += 1
                continue
            state_district_id = str(raw_id).strip()

            # Look up NCES ID from crosswalk
            nces_id = ny_crosswalk.get(state_district_id)
            if not nces_id:
                skipped += 1
                continue

            # Extract staff data using safe conversion
            staff_category = str(row.get('STAFF_IND_DESC', '')).strip()
            fte = safe_float(row.get('FTE')) or 0
            enrollment = safe_int(row.get('K-12_ENROLL')) or 0
            ratio = safe_float(row.get('DISTRICT_RATIO')) or 0

            # Skip if no FTE
            if fte == 0:
                continue

            # Use individual transaction for each row
            with session_scope() as session:
                session.execute(text("""
                    INSERT INTO ny_staff_data
                    (nces_id, year, staff_category, fte, enrollment_k12, district_ratio)
                    VALUES (:nces_id, '2023-24', :category, :fte, :enroll, :ratio)
                    ON CONFLICT (nces_id, year, staff_category, data_source) DO UPDATE SET
                        fte = EXCLUDED.fte,
                        enrollment_k12 = EXCLUDED.enrollment_k12,
                        district_ratio = EXCLUDED.district_ratio,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "category": staff_category,
                    "fte": fte,
                    "enroll": enrollment,
                    "ratio": ratio
                })
                session.commit()
                count += 1

        except Exception as e:
            logger.debug(f"Skipping row: {str(e)[:100]}")
            continue

    logger.info(f"✅ Imported {count} staff records ({skipped} skipped - no NCES match)")
    return count


def import_enrollment_data(df, sped_df=None):
    """Import enrollment data into database.

    Args:
        df: Regular enrollment DataFrame (All Students)
        sped_df: SPED-disaggregated enrollment DataFrame (optional)
    """
    if df is None:
        logger.warning("No enrollment data to import")
        return 0

    logger.info("Importing New York enrollment data...")

    # Load crosswalk once for efficiency
    with session_scope() as session:
        ny_crosswalk = load_ny_crosswalk(session)

    count = 0
    skipped = 0

    # Process SPED enrollment if available (more detailed)
    if sped_df is not None:
        logger.info("Processing SPED-disaggregated enrollment data...")
        for _, row in sped_df.iterrows():
            try:
                # Extract state district ID using safe conversion
                raw_id = safe_int(row.get('State District Identifier'))
                if raw_id is None:
                    skipped += 1
                    continue
                state_district_id = str(raw_id).strip()

                # Look up NCES ID
                nces_id = ny_crosswalk.get(state_district_id)
                if not nces_id:
                    skipped += 1
                    continue

                # Extract enrollment data using safe conversion
                subgroup = str(row.get('Subgroup Name', '')).strip()
                enrollment = safe_int(row.get('PreK-12 Total')) or 0

                # Build grade-level JSON
                grade_data = {}
                grade_columns = [
                    'PreK (Half Day)', 'PreK (Full Day)',
                    'Kindergarten (Half Day)', 'Kindergarten (Full Day)',
                    'Grade 1', 'Grade 2', 'Grade 3', 'Grade 4', 'Grade 5', 'Grade 6',
                    'Ungraded (Elementary)',
                    'Grade 7', 'Grade 8',
                    'Grade 9', 'Grade 10', 'Grade 11', 'Grade 12',
                    'Ungraded (Secondary)'
                ]

                for grade_col in grade_columns:
                    if grade_col in row:
                        try:
                            value = int(row[grade_col])
                            if value > 0:
                                grade_data[grade_col] = value
                        except (ValueError, TypeError):
                            continue

                # Use individual transaction
                with session_scope() as session:
                    session.execute(text("""
                        INSERT INTO ny_enrollment_data
                        (nces_id, year, subgroup, enrollment_prek12, enrollment_by_grade)
                        VALUES (:nces_id, '2023-24', :subgroup, :enrollment, CAST(:grades_json AS jsonb))
                        ON CONFLICT (nces_id, year, subgroup, data_source) DO UPDATE SET
                            enrollment_prek12 = EXCLUDED.enrollment_prek12,
                            enrollment_by_grade = EXCLUDED.enrollment_by_grade,
                            updated_at = CURRENT_TIMESTAMP
                    """), {
                        "nces_id": nces_id,
                        "subgroup": subgroup,
                        "enrollment": enrollment,
                        "grades_json": json.dumps(grade_data)
                    })
                    session.commit()
                    count += 1

            except Exception as e:
                logger.error(f"Failed to import enrollment row: {str(e)}")
                continue

    else:
        # Process regular enrollment (All Students only)
        logger.info("Processing regular enrollment data...")
        for _, row in df.iterrows():
            try:
                # Extract state district ID using safe conversion
                raw_id = safe_int(row.get('State District Identifier'))
                if raw_id is None:
                    skipped += 1
                    continue
                state_district_id = str(raw_id).strip()
                nces_id = ny_crosswalk.get(state_district_id)

                if not nces_id:
                    skipped += 1
                    continue

                subgroup = str(row.get('Subgroup Name', 'All Students')).strip()
                enrollment = safe_int(row.get('PreK-12 Total')) or 0

                # Build grade-level JSON (same as above)
                grade_data = {}
                grade_columns = [
                    'PreK (Half Day)', 'PreK (Full Day)',
                    'Kindergarten (Half Day)', 'Kindergarten (Full Day)',
                    'Grade 1', 'Grade 2', 'Grade 3', 'Grade 4', 'Grade 5', 'Grade 6',
                    'Ungraded (Elementary)',
                    'Grade 7', 'Grade 8',
                    'Grade 9', 'Grade 10', 'Grade 11', 'Grade 12',
                    'Ungraded (Secondary)'
                ]

                for grade_col in grade_columns:
                    if grade_col in row:
                        try:
                            value = int(row[grade_col])
                            if value > 0:
                                grade_data[grade_col] = value
                        except (ValueError, TypeError):
                            continue

                with session_scope() as session:
                    session.execute(text("""
                        INSERT INTO ny_enrollment_data
                        (nces_id, year, subgroup, enrollment_prek12, enrollment_by_grade)
                        VALUES (:nces_id, '2023-24', :subgroup, :enrollment, CAST(:grades_json AS jsonb))
                        ON CONFLICT (nces_id, year, subgroup, data_source) DO UPDATE SET
                            enrollment_prek12 = EXCLUDED.enrollment_prek12,
                            enrollment_by_grade = EXCLUDED.enrollment_by_grade,
                            updated_at = CURRENT_TIMESTAMP
                    """), {
                        "nces_id": nces_id,
                        "subgroup": subgroup,
                        "enrollment": enrollment,
                        "grades_json": json.dumps(grade_data)
                    })
                    session.commit()
                    count += 1

            except Exception as e:
                logger.error(f"Failed to import enrollment row: {str(e)}")
                continue

    logger.info(f"✅ Imported {count} enrollment records ({skipped} skipped - no NCES match)")
    return count


def main():
    """Main import process."""
    logger.info("=" * 80)
    logger.info("STARTING NEW YORK DATA IMPORT")
    logger.info("=" * 80)

    # Create tables
    create_ny_tables()

    # Import district identifiers
    import_district_identifiers()

    # Load data files
    staff_df = load_staff_data()
    enroll_df = load_enrollment_data()
    sped_enroll_df = load_sped_enrollment_data()

    # Import data
    staff_count = import_staff_data(staff_df)
    enroll_count = import_enrollment_data(enroll_df, sped_enroll_df)

    logger.info("=" * 80)
    logger.info("IMPORT COMPLETE")
    logger.info(f"  Staff records: {staff_count}")
    logger.info(f"  Enrollment records: {enroll_count}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
