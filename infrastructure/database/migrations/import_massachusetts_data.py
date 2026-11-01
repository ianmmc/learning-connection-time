#!/usr/bin/env python3
"""
Import Massachusetts Data to Database

This script imports DESE data from files into the database:
1. District identifiers (crosswalk) - uses state_district_crosswalk table
2. Staff data (teacher FTE)
3. Enrollment data (total K-12 enrollment)
4. Special education data (SWD counts from enrollment file)

Data sources:
- MA <year>/teacherdata.xlsx (DESE Profiles export; current vintage 2025-26)
- E2C Hub enrollment export (DESE Socrata export, filtered to one SY)

Massachusetts District Code Format: 4-digit zero-padded (e.g., "0035" for Boston)
- In data files: 8-digit integer with trailing zeros (e.g., 350000 or 00350000)
- In crosswalk: 4-digit string (e.g., "0035")

Uses shared utilities from sea_import_utils.py for common operations.

Usage:
    python import_massachusetts_data.py
"""

import argparse
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
from infrastructure.utilities.data_guards import (
    DataGuardError, require_nonempty_selection, require_year_carried,
)
from infrastructure.database.models import DataLineage
from infrastructure.database.queries import distinct_years
from infrastructure.utilities.school_year import is_covid_year, start_year
from infrastructure.database.migrations.sea_import_utils import (
    safe_float, safe_int,
    load_state_crosswalk, get_district_name,
    log_import_summary, ma_district_code,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# State configuration
STATE_CODE = 'MA'
# Label data with its ACTUAL year (issue #23): the DESE teacher-FTE file carries its vintage in its
# title row ("2025-26 Teacher Data - All Teachers"); the E2C Hub enrollment export is filtered to
# SY 2026 (= 2025-26). The old single DATA_YEAR = '2025-26' mislabeled 2024-25 teacher FTE as 2025-26
# (relabelled 2026-11-01 via --relabel-staff, #984). Both are SOURCE vintages (the files on disk),
# overridable with --teacher-year / --enrollment-year when newer DESE exports are dropped in — the
# same shape as the TX/CA/NY imports' --year.
TEACHER_DATA_YEAR = '2025-26'
ENROLLMENT_DATA_YEAR = '2025-26'

# Data file paths
MA_DATA_DIR = project_root / "data" / "raw" / "state" / "massachusetts"
ENROLLMENT_FILE = MA_DATA_DIR / "Enrollment__Grade,_Race_Ethnicity,_Gender,_and_Selected_Populations_20260119.xlsx"


def teacher_file_for(year: str) -> Path:
    """The DESE teacher file of one vintage: the per-year folder layout the raw inventory uses
    (`<year>/teacherdata.xlsx`, MANIFEST.md), else the legacy flat name `MA <year> teacherdata.xlsx`."""
    layout = MA_DATA_DIR / year / "teacherdata.xlsx"
    return layout if layout.exists() else MA_DATA_DIR / f"MA {year} teacherdata.xlsx"


def format_ma_district_code(dist_code) -> str:
    """Convert a DESE code to the 4-digit zero-padded crosswalk format.

    Massachusetts uses two shapes (issue #23):
    - 8-digit org code in data files: DDDD0000, e.g. 350000 or 00350000 (Boston)
    - 4-digit district code in the crosswalk: "0035" (Boston)

    Delegates to the shared converter, which handles both shapes — the old
    str(int(x)).zfill(8)[:4] returned '0000' for a 4-digit input like '0035'.

    Examples:
        350000 -> "0035"
        '00350000' -> "0035"
        '0035' -> "0035"
    """
    return ma_district_code(dist_code)


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
    """Load DESE teacher data from Excel file. Resolves the path from TEACHER_DATA_YEAR itself every call
    (no cached module-level path to drift out of sync — #1015 review) and cross-checks the file's own
    title row against the vintage being stamped, the same guard import_new_york_data.py applies to
    REPORT_SCHOOL_YEAR (#978): a file whose title says a different year must never be silently stamped
    under TEACHER_DATA_YEAR."""
    teacher_file = teacher_file_for(TEACHER_DATA_YEAR)
    logger.info(f"Loading teacher data from: {teacher_file}")

    if not teacher_file.exists():
        logger.error(f"Teacher file not found: {teacher_file}")
        return None

    try:
        # Row 0 is the title row ("<year> Teacher Data - All Teachers") — the file's own vintage stamp.
        title = str(pd.read_excel(teacher_file, header=None, nrows=1).iat[0, 0])
        if TEACHER_DATA_YEAR not in title:
            raise DataGuardError(
                f"{teacher_file.name} title row {title!r} does not name {TEACHER_DATA_YEAR} "
                f"(the vintage being imported) — refusing to stamp a mismatched file (#23, #978)"
            )

        df = pd.read_excel(teacher_file, header=1)

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
    except DataGuardError:
        raise
    except Exception as e:
        logger.error(f"Failed to load teacher file: {e}")
        return None


def dese_sy_for(school_year: str) -> int:
    """DESE's E2C Hub stamps a school year by its END calendar year: '2025-26' → SY 2026."""
    start = int(school_year[:4])
    return start + 1


def load_enrollment_data():
    """Load DESE enrollment data from the E2C Hub export, filtered to ENROLLMENT_DATA_YEAR's rows."""
    logger.info(f"Loading enrollment data from: {ENROLLMENT_FILE}")

    if not ENROLLMENT_FILE.exists():
        logger.error(f"Enrollment file not found: {ENROLLMENT_FILE}")
        return None

    try:
        df = pd.read_excel(ENROLLMENT_FILE)
    except Exception as e:
        logger.error(f"Failed to load enrollment file: {e}")
        return None

    # The SY filter is DERIVED from the vintage being stamped (#977): the old hard-coded `SY == 2026`
    # meant --enrollment-year only relabelled 2025-26 rows as whatever year was given.
    sy = dese_sy_for(ENROLLMENT_DATA_YEAR)
    available = sorted(int(v) for v in df['SY'].dropna().unique())
    df = df[(df['SY'] == sy) & (df['ORG_TYPE'] == 'District')]

    # Filter out state totals
    df = df[df['DIST_CODE'] != 0]

    # G4: an export that does not carry the requested vintage is a wrong-year run, never 0 rows imported
    require_nonempty_selection(df, what=f"DESE enrollment district rows for SY {sy} ({ENROLLMENT_DATA_YEAR})",
                               available=available)
    logger.info(f"Loaded {len(df)} district records from enrollment file (SY {sy} = {ENROLLMENT_DATA_YEAR})")
    return df


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


def import_district_identifiers(session, crosswalk, teacher_df):
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
                    source_year = EXCLUDED.source_year,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "nces_id": nces_id,
                "dist_code": dist_code_4,
                "name": district_name,
                "year": TEACHER_DATA_YEAR  # names come from the teacher file of that vintage
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
                "year": TEACHER_DATA_YEAR,
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


def relabel_staff_year(session, from_year: str, to_year: str) -> int:
    """A LOGGED relabel of the ma_staff_data AND ma_district_identifiers rows stamped `from_year` to
    `to_year` (#23 / #984). The rows loaded 2026-01-24 as '2025-26' hold the 2024-25 DESE export (386/388
    equal NCES 2024-25), and that file is no longer on disk to re-import under its true year. Both tables
    are stamped from the SAME teacher-file load (import_district_identifiers / import_staff_data), so a
    relabel of one without the other would leave them disagreeing about this import event's vintage.
    Refuses when `to_year` rows already exist in EITHER table — a relabel never merges two vintages — and
    fails loud when `from_year` carries nothing in ma_staff_data."""
    require_year_carried(from_year, lambda: distinct_years(session, "ma_staff_data"), what="ma_staff_data")
    moved = 0
    for table in ("ma_staff_data", "ma_district_identifiers"):
        to_existing = sorted(distinct_years(session, table, "source_year" if table.endswith("identifiers") else "year"))
        if to_year in to_existing:
            raise DataGuardError(f"{table} already carries rows for {to_year}; "
                                 f"refusing to relabel {from_year} onto an existing vintage")
    for table, col in (("ma_staff_data", "year"), ("ma_district_identifiers", "source_year")):
        n = session.execute(
            text(f"UPDATE {table} SET {col} = :to_year, updated_at = CURRENT_TIMESTAMP WHERE {col} = :from_year"),
            {"to_year": to_year, "from_year": from_year}).rowcount
        moved += n
        logger.info(f"  {table}.{col}: {n} rows {from_year} -> {to_year}")
    DataLineage.log(
        session, entity_type="ma_staff_data", entity_id=to_year, operation="relabel",
        source_file="import_massachusetts_data.py",
        details={"from_year": from_year, "to_year": to_year, "rows": moved,
                 "why": "rows loaded as 2025-26 hold the 2024-25 DESE teacher export (#23, #984)"},
        created_by="import_massachusetts_data --relabel-staff",
    )
    session.commit()
    logger.info(f"Relabelled {moved} rows {from_year} -> {to_year} (logged in data_lineage)")
    return moved


def require_staff_rows_written(session, year: str, imported: int, skipped: int) -> None:
    """A relabel that commits, followed by a teacher import that silently writes 0 rows (e.g. a header
    change in the new file), would leave ma_staff_data with NO rows for `year` at all (#1015 review) —
    fail loud rather than exit 0 reporting '0 imported, 0 skipped'."""
    if imported == 0:
        raise DataGuardError(
            f"import_staff_data wrote 0 rows for {year} ({skipped} skipped); "
            f"ma_staff_data now carries: {distinct_years(session, 'ma_staff_data')}"
        )


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
                "year": ENROLLMENT_DATA_YEAR,
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
    global TEACHER_DATA_YEAR, ENROLLMENT_DATA_YEAR
    parser = argparse.ArgumentParser(description="Import DESE teacher FTE + E2C Hub enrollment exports")
    parser.add_argument("--teacher-year", default=TEACHER_DATA_YEAR,
                        help=f"Vintage of the DESE teacher file (default: {TEACHER_DATA_YEAR}; selects 'MA <year> teacherdata.xlsx' and stamps the rows)")
    parser.add_argument("--enrollment-year", default=ENROLLMENT_DATA_YEAR,
                        help=f"Vintage the E2C Hub enrollment export is filtered to (default: {ENROLLMENT_DATA_YEAR}; stamps the rows)")
    parser.add_argument("--skip-enrollment", action="store_true",
                        help="Import the teacher file only (the E2C Hub enrollment export is a separate drop)")
    parser.add_argument("--relabel-staff", nargs=2, metavar=("FROM", "TO"), default=None,
                        help="Before importing, relabel ma_staff_data rows stamped FROM as TO, logged in "
                             "data_lineage (the #23 mislabel: --relabel-staff 2025-26 2024-25). Refuses if "
                             "TO rows exist; both years are validated (parseable, non-COVID).")
    args = parser.parse_args()
    TEACHER_DATA_YEAR, ENROLLMENT_DATA_YEAR = args.teacher_year, args.enrollment_year
    relabel = tuple(args.relabel_staff) if args.relabel_staff else None
    if relabel:
        for y in relabel:
            try:
                start_year(y)
            except ValueError:
                parser.error(f"--relabel-staff: {y!r} is not a parseable school year (expect 'YYYY-YY')")
            if is_covid_year(y):
                parser.error(f"--relabel-staff: {y!r} is a COVID-excluded year (Rule #2) — refusing to relabel to/from it")

    logger.info("=" * 60)
    logger.info("Starting Massachusetts Data Import")
    logger.info("=" * 60)

    # Create tables
    create_ma_tables()

    # Load data files
    teacher_df = load_teacher_data()
    enrollment_df = None if args.skip_enrollment else load_enrollment_data()

    # Aborts exit NON-zero (#977): a missing file for the requested vintage used to log 'Aborting.' and
    # return 0, indistinguishable from a clean import to rebuild_database / a shell caller.
    if teacher_df is None:
        logger.error("Failed to load teacher data file. Aborting.")
        sys.exit(1)

    if enrollment_df is None and not args.skip_enrollment:
        logger.error("Failed to load enrollment data file. Aborting.")
        sys.exit(1)

    # Load crosswalk
    with session_scope() as session:
        crosswalk = load_ma_crosswalk(session)
        logger.info(f"Loaded {len(crosswalk)} entries from crosswalk table")

        if len(crosswalk) == 0:
            logger.error("No MA entries in crosswalk table. "
                        "Ensure state_district_crosswalk is populated.")
            sys.exit(1)

        if relabel:
            relabel_staff_year(session, *relabel)

        # Import data
        id_imported, id_skipped = import_district_identifiers(
            session, crosswalk, teacher_df
        )
        staff_imported, staff_skipped = import_staff_data(
            session, crosswalk, teacher_df
        )
        require_staff_rows_written(session, TEACHER_DATA_YEAR, staff_imported, staff_skipped)
        enroll_imported, enroll_skipped = (0, 0) if args.skip_enrollment else import_enrollment_data(
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
