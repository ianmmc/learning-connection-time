#!/usr/bin/env python3
"""
Import Florida Data to Database

This script imports FLDOE data from Excel files into the database:
1. District identifiers (crosswalk) - uses state_district_crosswalk table
2. Staff data
3. Enrollment data

Uses shared utilities from sea_import_utils.py for common operations.

Usage:
    python import_florida_data.py
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
    format_state_id, log_import_summary,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Data file paths
FLORIDA_DATA_DIR = project_root / "data" / "raw" / "state" / "florida"
STAFF_FILE = FLORIDA_DATA_DIR / "ARInstructionalDistStaff2425.xlsx"
ENROLLMENT_FILE = FLORIDA_DATA_DIR / "2425MembInFLPublicSchools.xlsx"

# State configuration
STATE_CODE = 'FL'


def load_florida_crosswalk(session, county_districts_only: bool = True) -> dict:
    """Load Florida crosswalk from database.

    Args:
        session: Database session
        county_districts_only: If True, only return 2-digit county district codes (01-67).
                              If False, include charter districts (e.g., 53D).

    Returns:
        Dict mapping FLDOE district code -> NCES ID
    """
    if county_districts_only:
        # Only return 2-digit numeric county district codes
        result = session.execute(text("""
            SELECT state_district_id, nces_id
            FROM state_district_crosswalk
            WHERE state = 'FL'
              AND id_system = 'st_leaid'
              AND LENGTH(state_district_id) = 2
              AND state_district_id ~ '^[0-9]+$'
        """))
    else:
        result = session.execute(text("""
            SELECT state_district_id, nces_id
            FROM state_district_crosswalk
            WHERE state = 'FL'
              AND id_system = 'st_leaid'
        """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_staff_data():
    """Load staff data from Excel file."""
    logger.info(f"Loading staff data from: {STAFF_FILE}")

    if not STAFF_FILE.exists():
        logger.error(f"Staff file not found: {STAFF_FILE}")
        return None

    try:
        df = pd.read_excel(
            STAFF_FILE,
            sheet_name="Instr_Staff_by_Assignment",
            header=2
        )
        logger.info(f"Loaded {len(df)} rows from staff file")
        return df
    except Exception as e:
        logger.error(f"Failed to load staff file: {e}")
        return None


def load_enrollment_data():
    """Load enrollment data from Excel file."""
    logger.info(f"Loading enrollment data from: {ENROLLMENT_FILE}")

    if not ENROLLMENT_FILE.exists():
        logger.error(f"Enrollment file not found: {ENROLLMENT_FILE}")
        return None

    try:
        df = pd.read_excel(
            ENROLLMENT_FILE,
            sheet_name="District",
            header=2
        )
        logger.info(f"Loaded {len(df)} rows from enrollment file")
        return df
    except Exception as e:
        logger.error(f"Failed to load enrollment file: {e}")
        return None


def import_district_identifiers():
    """Import Florida district identifiers from crosswalk table.

    Uses state_district_crosswalk as source of truth for NCES ↔ FLDOE mapping.
    """
    logger.info("Importing Florida district identifiers from crosswalk table...")

    with session_scope() as session:
        # Load crosswalk from database
        florida_crosswalk = load_florida_crosswalk(session)
        logger.info(f"Loaded {len(florida_crosswalk)} Florida districts from crosswalk table")

        count = 0
        for fldoe_no, nces_id in florida_crosswalk.items():
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

                # Insert into fl_district_identifiers
                session.execute(text("""
                    INSERT INTO fl_district_identifiers
                    (nces_id, fldoe_district_no, district_name_fldoe, source_year)
                    VALUES (:nces_id, :fldoe_no, :name, '2024-25')
                    ON CONFLICT (nces_id) DO UPDATE SET
                        fldoe_district_no = EXCLUDED.fldoe_district_no,
                        district_name_fldoe = EXCLUDED.district_name_fldoe,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "fldoe_no": fldoe_no,
                    "name": district_name
                })
                count += 1

            except Exception as e:
                logger.error(f"Failed to import {fldoe_no}: {e}")

        session.commit()
        logger.info(f"✅ Imported {count} district identifiers")
        return count


def import_staff_data(df):
    """Import staff data into database.

    Uses state_district_crosswalk table for NCES ID lookups.
    """
    if df is None:
        logger.warning("No staff data to import")
        return 0

    logger.info("Importing Florida staff data...")

    # Load crosswalk once for efficiency
    with session_scope() as session:
        florida_crosswalk = load_florida_crosswalk(session)

    count = 0
    for _, row in df.iterrows():
        try:
            # Extract district code from 'Dist #'
            district_code = str(int(row.get('Dist #', 0))).strip().zfill(2)

            # Look up NCES ID from crosswalk
            nces_id = florida_crosswalk.get(district_code)
            if not nces_id:
                continue

            # Extract staff counts using safe conversion
            total_staff = safe_float(row.get('Total Instructional Staff')) or 0
            total_teachers = safe_float(row.get('Total Teachers')) or 0
            ese_teachers = safe_float(row.get('Exceptional Education Teachers')) or 0

            # Use individual transaction for each row
            with session_scope() as session:
                session.execute(text("""
                    INSERT INTO fl_staff_data
                    (nces_id, year, total_instructional_staff, classroom_teachers, ese_teachers)
                    VALUES (:nces_id, '2024-25', :total, :teachers, :ese)
                    ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                        total_instructional_staff = EXCLUDED.total_instructional_staff,
                        classroom_teachers = EXCLUDED.classroom_teachers,
                        ese_teachers = EXCLUDED.ese_teachers,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "total": total_staff,
                    "teachers": total_teachers,
                    "ese": ese_teachers
                })
                session.commit()
                count += 1

        except Exception as e:
            logger.debug(f"Skipping district {district_code}: {str(e)[:100]}")
            continue

    logger.info(f"✅ Imported {count} staff records")
    return count


def import_enrollment_data(df):
    """Import enrollment data into database.

    Uses state_district_crosswalk table for NCES ID lookups.
    """
    if df is None:
        logger.warning("No enrollment data to import")
        return 0

    logger.info("Importing Florida enrollment data...")

    # Load crosswalk once for efficiency
    with session_scope() as session:
        florida_crosswalk = load_florida_crosswalk(session)

    count = 0
    for idx, row in df.iterrows():
        district_code = "unknown"
        try:
            # Extract district code from 'District #'
            district_code = str(int(row.get('District #', 0))).strip().zfill(2)

            # Look up NCES ID from crosswalk
            nces_id = florida_crosswalk.get(district_code)
            if not nces_id:
                continue

            # Extract enrollment using safe conversion
            total_enrollment = safe_int(row.get('Total Enrollment')) or 0

            # Use individual transaction for each row
            with session_scope() as session:
                session.execute(text("""
                    INSERT INTO fl_enrollment_data
                    (nces_id, year, total_enrollment)
                    VALUES (:nces_id, '2024-25', :enrollment)
                    ON CONFLICT (nces_id, year, data_source) DO UPDATE SET
                        total_enrollment = EXCLUDED.total_enrollment,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "enrollment": total_enrollment
                })
                session.commit()
                count += 1

        except Exception as e:
            logger.debug(f"Skipping district {district_code} (row {idx}): {str(e)[:100]}")
            continue

    logger.info(f"✅ Imported {count} enrollment records")
    return count


def main():
    """Main import process."""
    logger.info("=" * 60)
    logger.info("Florida Data Import")
    logger.info("=" * 60)

    # Import district identifiers first
    id_count = import_district_identifiers()

    # Load data files
    staff_df = load_staff_data()
    enrollment_df = load_enrollment_data()

    # Import data
    staff_count = import_staff_data(staff_df)
    enrollment_count = import_enrollment_data(enrollment_df)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Import Summary:")
    logger.info(f"  District identifiers: {id_count}")
    logger.info(f"  Staff records: {staff_count}")
    logger.info(f"  Enrollment records: {enrollment_count}")
    logger.info("=" * 60)

    if id_count > 0:
        logger.info("\n✅ Import complete! Next step:")
        logger.info("   Run integration tests: pytest tests/test_florida_integration.py -v")
    else:
        logger.warning("\n⚠️  Import completed with warnings. Review logs above.")


if __name__ == "__main__":
    main()
