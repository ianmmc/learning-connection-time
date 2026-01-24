#!/usr/bin/env python3
"""
Data Migration Script: Import all core data into PostgreSQL database.

Imports (in order, with dependencies):
1. State requirements from YAML config
2. Districts from NCES CCD CSV
3. ST_LEAID population from raw NCES CCD (depends on districts)
4. State crosswalk table (depends on st_leaid)
5. Bell schedules from enriched JSON files (optional)

The st_leaid and crosswalk steps are critical for SEA state data imports.
Without them, state-specific imports will fail to match districts.

Usage:
    python import_all_data.py [--dry-run] [--skip-districts] [--skip-schedules] [--skip-crosswalk]

Author: Claude (AI Assistant)
Date: December 25, 2025
Updated: January 24, 2026 - Added st_leaid and crosswalk steps
"""

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.database.connection import get_engine, session_scope, get_table_counts
from infrastructure.database.models import (
    District,
    StateRequirement,
    BellSchedule,
    DataLineage,
)
from sqlalchemy import text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / "logs" / "migration.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

# File paths
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
MIGRATIONS_DIR = Path(__file__).parent
STATE_REQUIREMENTS_FILE = CONFIG_DIR / "state-requirements.yaml"
DISTRICTS_FILE = DATA_DIR / "processed" / "normalized" / "districts_2023_24_nces.csv"
BELL_SCHEDULES_FILE = DATA_DIR / "enriched" / "bell-schedules" / "bell_schedules_manual_collection_2024_25.json"

# Raw NCES CCD file for ST_LEAID population
NCES_RAW_DIR = DATA_DIR / "raw" / "federal" / "nces-ccd" / "2023_24"
CROSSWALK_MIGRATION_FILE = MIGRATIONS_DIR / "007_add_state_crosswalk.sql"


def ensure_log_directory():
    """Ensure logs directory exists."""
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)


def import_state_requirements(session, dry_run: bool = False) -> int:
    """
    Import state requirements from YAML config.

    Args:
        session: SQLAlchemy session
        dry_run: If True, don't commit changes

    Returns:
        Number of records imported
    """
    logger.info(f"Importing state requirements from {STATE_REQUIREMENTS_FILE}")

    if not STATE_REQUIREMENTS_FILE.exists():
        logger.error(f"State requirements file not found: {STATE_REQUIREMENTS_FILE}")
        return 0

    with open(STATE_REQUIREMENTS_FILE, "r") as f:
        data = yaml.safe_load(f)

    states = data.get("states", {})
    count = 0

    for state_key, state_data in states.items():
        state_code = state_data.get("code", state_key[:2].upper())

        # Create state name from key
        state_name = state_key.replace("_", " ").title()

        requirement = StateRequirement(
            state=state_code,
            state_name=state_name,
            elementary_minutes=state_data.get("elementary"),
            middle_minutes=state_data.get("middle_school"),
            high_minutes=state_data.get("high_school"),
            notes=state_data.get("notes"),
            source=state_data.get("source_url"),
        )

        if not dry_run:
            # Use merge to handle existing records
            session.merge(requirement)

            # Log lineage
            DataLineage.log(
                session,
                entity_type="state_requirement",
                entity_id=state_code,
                operation="import",
                source_file=str(STATE_REQUIREMENTS_FILE),
                created_by="migration",
            )

        count += 1
        logger.debug(f"Imported state requirement: {state_code}")

    if not dry_run:
        session.flush()

    logger.info(f"Imported {count} state requirements")
    return count


def import_districts(session, dry_run: bool = False) -> int:
    """
    Import districts from NCES CCD CSV.

    Args:
        session: SQLAlchemy session
        dry_run: If True, don't commit changes

    Returns:
        Number of records imported
    """
    logger.info(f"Importing districts from {DISTRICTS_FILE}")

    if not DISTRICTS_FILE.exists():
        logger.error(f"Districts file not found: {DISTRICTS_FILE}")
        return 0

    count = 0
    batch_size = 1000

    with open(DISTRICTS_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        batch = []
        for row in reader:
            # Parse numeric values, handling empty strings
            enrollment = None
            if row.get("enrollment") and row["enrollment"] not in ("", "nan", "None"):
                try:
                    enrollment = int(float(row["enrollment"]))
                except (ValueError, TypeError):
                    pass

            instructional_staff = None
            if row.get("instructional_staff") and row["instructional_staff"] not in ("", "nan", "None"):
                try:
                    instructional_staff = float(row["instructional_staff"])
                except (ValueError, TypeError):
                    pass

            district = District(
                nces_id=str(row["district_id"]).strip(),
                name=row["district_name"].strip(),
                state=row["state"].strip(),
                enrollment=enrollment,
                instructional_staff=instructional_staff,
                year=row.get("year", "2023-24"),
                data_source=row.get("data_source", "nces_ccd"),
            )

            batch.append(district)
            count += 1

            # Batch insert for performance
            if len(batch) >= batch_size:
                if not dry_run:
                    for d in batch:
                        session.merge(d)
                    session.flush()
                    logger.info(f"Imported {count} districts...")
                batch = []

        # Final batch
        if batch and not dry_run:
            for d in batch:
                session.merge(d)
            session.flush()

    # Log lineage for the import operation
    if not dry_run:
        DataLineage.log(
            session,
            entity_type="district",
            entity_id="*",
            operation="bulk_import",
            source_file=str(DISTRICTS_FILE),
            details={"count": count},
            created_by="migration",
        )

    logger.info(f"Imported {count} districts")
    return count


def populate_st_leaid(session, dry_run: bool = False) -> int:
    """
    Populate st_leaid column from raw NCES CCD directory file.

    The ST_LEAID field contains state-assigned LEA IDs (e.g., 'CA-6275796')
    which are needed for the crosswalk table and SEA imports.

    Args:
        session: SQLAlchemy session
        dry_run: If True, don't commit changes

    Returns:
        Number of districts updated
    """
    logger.info("Populating st_leaid from raw NCES CCD data...")

    # Find the raw NCES directory file
    directory_files = list(NCES_RAW_DIR.glob("ccd_lea_029_*.csv"))

    if not directory_files:
        logger.error(f"No NCES directory file found in {NCES_RAW_DIR}")
        return 0

    directory_file = directory_files[0]
    logger.info(f"  Reading: {directory_file.name}")

    # Read ST_LEAID from directory file
    df = pd.read_csv(directory_file, usecols=['LEAID', 'ST_LEAID'], dtype=str)
    logger.info(f"  Found {len(df)} records in NCES file")

    if dry_run:
        logger.info("  DRY RUN - would update st_leaid for districts")
        return len(df)

    # Update database
    updated_count = 0

    for _, row in df.iterrows():
        leaid = row['LEAID']
        st_leaid = row['ST_LEAID'] if pd.notna(row['ST_LEAID']) else None

        if st_leaid:
            # Try both with and without leading zeros
            district = session.query(District).filter(District.nces_id == leaid).first()
            if not district and leaid.startswith('0'):
                # Try without leading zero
                leaid_no_zero = leaid.lstrip('0')
                district = session.query(District).filter(District.nces_id == leaid_no_zero).first()

            if district:
                district.st_leaid = st_leaid
                updated_count += 1

        if updated_count % 5000 == 0 and updated_count > 0:
            logger.info(f"  Updated {updated_count} districts...")
            session.flush()

    session.flush()
    logger.info(f"Populated st_leaid for {updated_count} districts")
    return updated_count


def build_crosswalk(session, dry_run: bool = False) -> int:
    """
    Build the state_district_crosswalk table from st_leaid.

    Creates the crosswalk table (if needed) and populates it by parsing
    the ST_LEAID format ({STATE}-{STATE_ID}).

    Args:
        session: SQLAlchemy session
        dry_run: If True, don't commit changes

    Returns:
        Number of crosswalk entries created
    """
    logger.info("Building state district crosswalk table...")

    if not CROSSWALK_MIGRATION_FILE.exists():
        logger.error(f"Crosswalk migration file not found: {CROSSWALK_MIGRATION_FILE}")
        return 0

    if dry_run:
        logger.info("  DRY RUN - would create crosswalk table and populate")
        return 0

    # Read and execute the migration SQL
    with open(CROSSWALK_MIGRATION_FILE, 'r') as f:
        migration_sql = f.read()

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()

    # Count entries created
    result = session.execute(text("SELECT COUNT(*) FROM state_district_crosswalk"))
    count = result.scalar()

    logger.info(f"Built crosswalk table with {count} entries")

    # Log state distribution
    result = session.execute(text("""
        SELECT state, COUNT(*) as count
        FROM state_district_crosswalk
        GROUP BY state
        ORDER BY count DESC
        LIMIT 5
    """))
    rows = result.fetchall()
    logger.info("  Top 5 states by crosswalk entries:")
    for row in rows:
        logger.info(f"    {row[0]}: {row[1]} districts")

    return count


def import_bell_schedules(session, dry_run: bool = False) -> int:
    """
    Import bell schedules from consolidated JSON file.

    Args:
        session: SQLAlchemy session
        dry_run: If True, don't commit changes

    Returns:
        Number of records imported
    """
    logger.info(f"Importing bell schedules from {BELL_SCHEDULES_FILE}")

    if not BELL_SCHEDULES_FILE.exists():
        logger.error(f"Bell schedules file not found: {BELL_SCHEDULES_FILE}")
        return 0

    with open(BELL_SCHEDULES_FILE, "r") as f:
        data = json.load(f)

    # Get set of valid district IDs from database
    valid_district_ids = set(
        row[0] for row in session.query(District.nces_id).all()
    )
    logger.info(f"Found {len(valid_district_ids)} valid districts in database")

    count = 0
    skipped = 0
    grade_levels = ["elementary", "middle", "high"]

    for district_id, district_data in data.items():
        # Normalize district ID (strip leading zeros to match CSV format)
        normalized_id = district_id.lstrip("0") or district_id

        # Check if district exists in database
        if normalized_id not in valid_district_ids:
            # Try original ID as fallback
            if district_id not in valid_district_ids:
                logger.warning(f"District {district_id} not found in database, skipping")
                skipped += 1
                continue
            else:
                normalized_id = district_id

        year = district_data.get("year", "2024-25")

        for grade_level in grade_levels:
            if grade_level not in district_data:
                continue

            schedule_data = district_data[grade_level]

            # Skip if no data for this grade level
            if schedule_data is None:
                continue

            # Skip if no instructional minutes
            instructional_minutes = schedule_data.get("instructional_minutes")
            if not instructional_minutes:
                continue

            # Normalize method value to database-accepted values
            # Maps web scraping methods to 'automated_enrichment'
            raw_method = schedule_data.get("method", "human_provided")
            method_mapping = {
                "web_scrape_tier1": "automated_enrichment",
                "web_scrape_tier2": "automated_enrichment",
                "web_scraping": "automated_enrichment",
                "automated": "automated_enrichment",
            }
            normalized_method = method_mapping.get(raw_method, raw_method)

            # Create bell schedule record
            schedule = BellSchedule(
                district_id=normalized_id,
                year=year,
                grade_level=grade_level,
                instructional_minutes=instructional_minutes,
                start_time=schedule_data.get("start_time"),
                end_time=schedule_data.get("end_time"),
                lunch_duration=schedule_data.get("lunch_duration"),
                passing_periods=schedule_data.get("passing_periods"),
                recess_duration=schedule_data.get("recess_duration"),
                schools_sampled=schedule_data.get("schools_sampled", []),
                source_urls=schedule_data.get("source_urls", []),
                confidence=schedule_data.get("confidence", "high"),
                method=normalized_method,
                source_description=schedule_data.get("source"),
                notes=schedule_data.get("notes"),
                raw_import=schedule_data,  # Preserve original data
            )

            if not dry_run:
                session.merge(schedule)

                # Log lineage
                DataLineage.log(
                    session,
                    entity_type="bell_schedule",
                    entity_id=f"{normalized_id}/{year}/{grade_level}",
                    operation="import",
                    source_file=str(BELL_SCHEDULES_FILE),
                    details={"instructional_minutes": instructional_minutes},
                    created_by="migration",
                )

            count += 1
            logger.debug(f"Imported bell schedule: {district_id}/{grade_level}")

    if not dry_run:
        session.flush()

    logger.info(f"Imported {count} bell schedule records ({skipped} districts skipped - not in database)")
    return count


def verify_data(session) -> dict:
    """
    Verify imported data counts.

    Args:
        session: SQLAlchemy session

    Returns:
        Dictionary with counts and validation status
    """
    from sqlalchemy import func

    results = {
        "districts": session.query(func.count(District.nces_id)).scalar(),
        "state_requirements": session.query(func.count(StateRequirement.state)).scalar(),
        "bell_schedules": session.query(func.count(BellSchedule.id)).scalar(),
        "lineage_records": session.query(func.count(DataLineage.id)).scalar(),
    }

    # Count districts with st_leaid
    results["districts_with_st_leaid"] = session.query(
        func.count(District.nces_id)
    ).filter(District.st_leaid.isnot(None)).scalar()

    # Count crosswalk entries
    try:
        result = session.execute(text("SELECT COUNT(*) FROM state_district_crosswalk"))
        results["crosswalk_entries"] = result.scalar()
    except Exception:
        results["crosswalk_entries"] = 0

    # Count unique districts with bell schedules
    results["districts_with_schedules"] = session.query(
        func.count(func.distinct(BellSchedule.district_id))
    ).scalar()

    # Validate expected counts
    results["valid"] = (
        results["districts"] >= 17000  # Expected ~17,842 in normalized CSV
        and results["state_requirements"] >= 50  # Expected 50 states
        and results["crosswalk_entries"] >= 17000  # Crosswalk should match districts
    )

    return results


def main():
    """Main migration entry point."""
    parser = argparse.ArgumentParser(description="Import data into PostgreSQL database")
    parser.add_argument("--dry-run", action="store_true", help="Preview without committing")
    parser.add_argument("--skip-districts", action="store_true", help="Skip district import")
    parser.add_argument("--skip-crosswalk", action="store_true", help="Skip st_leaid and crosswalk steps")
    parser.add_argument("--skip-schedules", action="store_true", help="Skip bell schedule import")
    parser.add_argument("--skip-states", action="store_true", help="Skip state requirements import")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    ensure_log_directory()

    logger.info("=" * 60)
    logger.info("Starting data migration to PostgreSQL")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    start_time = datetime.now()

    try:
        # Test connection
        engine = get_engine()
        logger.info("Database connection established")

        with session_scope() as session:
            # 1. Import state requirements (no dependencies)
            if not args.skip_states:
                import_state_requirements(session, dry_run=args.dry_run)

            # 2. Import districts
            if not args.skip_districts:
                import_districts(session, dry_run=args.dry_run)

            if args.dry_run:
                logger.info("DRY RUN - Rolling back all changes")
                session.rollback()
            else:
                # Commit is handled by session_scope context manager
                pass

        # 3. Populate st_leaid (depends on districts, uses raw NCES file)
        # 4. Build crosswalk (depends on st_leaid)
        # These run outside the main session to ensure districts are committed first
        if not args.skip_crosswalk and not args.skip_districts and not args.dry_run:
            with session_scope() as session:
                populate_st_leaid(session, dry_run=args.dry_run)

            # Build crosswalk (runs its own SQL transaction)
            with session_scope() as session:
                build_crosswalk(session, dry_run=args.dry_run)

        # 5. Import bell schedules (optional, depends on districts)
        if not args.skip_schedules and not args.dry_run:
            with session_scope() as session:
                import_bell_schedules(session, dry_run=args.dry_run)

        # Verify results (new session for accurate counts)
        if not args.dry_run:
            with session_scope() as session:
                results = verify_data(session)
                logger.info("=" * 60)
                logger.info("Migration Complete - Verification Results:")
                logger.info(f"  Districts: {results['districts']:,}")
                logger.info(f"  Districts with st_leaid: {results['districts_with_st_leaid']:,}")
                logger.info(f"  Crosswalk entries: {results['crosswalk_entries']:,}")
                logger.info(f"  State requirements: {results['state_requirements']}")
                logger.info(f"  Bell schedules: {results['bell_schedules']}")
                logger.info(f"  Districts with schedules: {results['districts_with_schedules']}")
                logger.info(f"  Lineage records: {results['lineage_records']}")
                logger.info(f"  Validation: {'PASSED' if results['valid'] else 'FAILED'}")
                logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)

    elapsed = datetime.now() - start_time
    logger.info(f"Migration completed in {elapsed.total_seconds():.2f} seconds")


if __name__ == "__main__":
    main()
