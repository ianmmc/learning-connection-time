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

import argparse
import re
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
from infrastructure.utilities.data_guards import DataGuardError, require_labels_seen
from infrastructure.utilities.school_year import COVID_EXCLUDED_YEARS
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

# Vintage of the NYSED workbooks on disk (sheet "public-district-<year>"). This is the SOURCE's year,
# not the project's current primary year — a SEA file is what it is. Override with --year when a
# newer workbook is dropped in; the three workbook paths, the sheet name, the staffing sheet's own
# REPORT_SCHOOL_YEAR check and every stored row follow it (#978).
SOURCE_YEAR = "2023-24"

NY_DATA_DIR = project_root / "data" / "raw" / "state" / "new-york"
_YEAR_RE = re.compile(r"^(20\d\d)-(\d\d)$")


def validate_source_year(year: str) -> str:
    """A NYSED vintage must be a well-formed, non-COVID school year (#978: 'garbage' and '2021-22'
    were accepted and stamped onto every row)."""
    m = _YEAR_RE.match(year or "")
    if not m or int(m.group(2)) != (int(m.group(1)) + 1) % 100:
        raise DataGuardError(f"import_new_york_data: --year {year!r} is not a school year (YYYY-YY)")
    if year in COVID_EXCLUDED_YEARS:
        raise DataGuardError(f"import_new_york_data: {year} is a COVID-excluded year (REQ-007)")
    return year


def workbook_paths(year: str) -> tuple[Path, Path, Path]:
    """(staff, enrollment, sped enrollment) workbook paths for a vintage — derived, never fixed, so
    --year can never pair one vintage's files with another's label."""
    tag = year.replace("-", "_")
    return (NY_DATA_DIR / f"ny_staffing_{tag}.xlsx",
            NY_DATA_DIR / f"ny_enrollment_district_{tag}.xlsx",
            NY_DATA_DIR / f"ny_enrollment_sped_{tag}.xlsx")


STAFF_FILE, ENROLLMENT_FILE, SPED_ENROLLMENT_FILE = workbook_paths(SOURCE_YEAR)


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
        raise DataGuardError(f"NYSED staff workbook for {SOURCE_YEAR} not found: {STAFF_FILE}")

    df = pd.read_excel(STAFF_FILE, sheet_name="STAFF_RATIOS")
    # The staffing sheet is year-less by name but carries its own REPORT_SCHOOL_YEAR column: the file's
    # vintage must be the one we stamp (#978), never 2023-24 rows labelled with whatever --year said.
    require_labels_seen(["REPORT_SCHOOL_YEAR"], df.columns, label="NYSED STAFF_RATIOS columns")
    file_years = sorted(str(y) for y in df["REPORT_SCHOOL_YEAR"].dropna().unique())
    if file_years != [SOURCE_YEAR]:
        raise DataGuardError(
            f"NYSED staff workbook {STAFF_FILE.name} reports school year(s) {file_years}, "
            f"not the vintage being imported ({SOURCE_YEAR})"
        )
    logger.info(f"Loaded {len(df)} rows from staff file")
    return df


def load_enrollment_data():
    """Load enrollment data from NYSED file."""
    logger.info(f"Loading enrollment data from: {ENROLLMENT_FILE}")

    df = read_district_sheet(ENROLLMENT_FILE, label="NYSED enrollment workbook")
    logger.info(f"Loaded {len(df)} rows from enrollment file")
    return df


def read_district_sheet(path: Path, *, label: str) -> pd.DataFrame:
    """Read the `public-district-<SOURCE_YEAR>` sheet. A missing workbook or sheet is a wrong-vintage
    run and FAILS (#978): the old `except Exception: return None` turned 'Worksheet not found' into
    'Enrollment records: 0' and exit 0."""
    if not path.exists():
        raise DataGuardError(f"{label} for {SOURCE_YEAR} not found: {path}")
    sheet = f"public-district-{SOURCE_YEAR}"
    sheets = pd.ExcelFile(path).sheet_names
    if sheet not in sheets:
        raise DataGuardError(f"{label} {path.name} has no sheet {sheet!r}; sheets: {sheets}")
    return pd.read_excel(path, sheet_name=sheet)


def load_sped_enrollment_data():
    """Load SPED-disaggregated enrollment data from NYSED file."""
    logger.info(f"Loading SPED enrollment data from: {SPED_ENROLLMENT_FILE}")

    df = read_district_sheet(SPED_ENROLLMENT_FILE, label="NYSED SPED enrollment workbook")
    logger.info(f"Loaded {len(df)} rows from SPED enrollment file")
    return df


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
                    VALUES (:nces_id, :nysed_id, :name, :source_year)
                    ON CONFLICT (nces_id) DO UPDATE SET
                        nysed_district_id = EXCLUDED.nysed_district_id,
                        district_name_nysed = EXCLUDED.district_name_nysed,
                        source_year = EXCLUDED.source_year,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "source_year": SOURCE_YEAR,
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
            # 12-digit zero-padded BEDS code — str(raw_id) dropped leading
            # zeros and silently missed crosswalk rows (issue #286)
            state_district_id = format_state_id('NY', raw_id)

            # Look up NCES ID from crosswalk
            nces_id = ny_crosswalk.get(state_district_id)
            if not nces_id:
                skipped += 1
                continue

            # Extract staff data using safe conversion. Suppressed/masked values
            # stay None and are stored as NULL — never coerced to 0 (issue #22)
            staff_category = str(row.get('STAFF_IND_DESC', '')).strip()
            fte = safe_float(row.get('FTE'))
            enrollment = safe_int(row.get('K-12_ENROLL'))
            ratio = safe_float(row.get('DISTRICT_RATIO'))

            # Skip if FTE missing/suppressed or zero
            if not fte:
                continue

            # Use individual transaction for each row
            with session_scope() as session:
                session.execute(text("""
                    INSERT INTO ny_staff_data
                    (nces_id, year, staff_category, fte, enrollment_k12, district_ratio)
                    VALUES (:nces_id, :source_year, :category, :fte, :enroll, :ratio)
                    ON CONFLICT (nces_id, year, staff_category, data_source) DO UPDATE SET
                        fte = EXCLUDED.fte,
                        enrollment_k12 = EXCLUDED.enrollment_k12,
                        district_ratio = EXCLUDED.district_ratio,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "nces_id": nces_id,
                    "source_year": SOURCE_YEAR,
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

                # Extract enrollment data using safe conversion; suppressed -> NULL,
                # not 0 (issue #22)
                subgroup = str(row.get('Subgroup Name', '')).strip()
                enrollment = safe_int(row.get('PreK-12 Total'))

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
                        VALUES (:nces_id, :source_year, :subgroup, :enrollment, CAST(:grades_json AS jsonb))
                        ON CONFLICT (nces_id, year, subgroup, data_source) DO UPDATE SET
                            enrollment_prek12 = EXCLUDED.enrollment_prek12,
                            enrollment_by_grade = EXCLUDED.enrollment_by_grade,
                            updated_at = CURRENT_TIMESTAMP
                    """), {
                        "nces_id": nces_id,
                    "source_year": SOURCE_YEAR,
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
                # Suppressed -> NULL, not 0 (issue #22)
                enrollment = safe_int(row.get('PreK-12 Total'))

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
                        VALUES (:nces_id, :source_year, :subgroup, :enrollment, CAST(:grades_json AS jsonb))
                        ON CONFLICT (nces_id, year, subgroup, data_source) DO UPDATE SET
                            enrollment_prek12 = EXCLUDED.enrollment_prek12,
                            enrollment_by_grade = EXCLUDED.enrollment_by_grade,
                            updated_at = CURRENT_TIMESTAMP
                    """), {
                        "nces_id": nces_id,
                    "source_year": SOURCE_YEAR,
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
    global SOURCE_YEAR, STAFF_FILE, ENROLLMENT_FILE, SPED_ENROLLMENT_FILE
    parser = argparse.ArgumentParser(description="Import NYSED staff + enrollment workbooks")
    parser.add_argument("--year", default=SOURCE_YEAR,
                        help=f"Vintage of the NYSED workbooks (default: {SOURCE_YEAR}; selects the three "
                             f"ny_*_<year>.xlsx workbooks and the sheet, and stamps every row)")
    SOURCE_YEAR = validate_source_year(parser.parse_args().year)
    STAFF_FILE, ENROLLMENT_FILE, SPED_ENROLLMENT_FILE = workbook_paths(SOURCE_YEAR)
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
