#!/usr/bin/env python3
"""
Reset database script for Learning Connection Time project.

This script performs a controlled database reset that:
1. Creates a timestamped backup (pg_dump)
2. Truncates all records (preserves schema)
3. Verifies the empty state

Usage:
    python infrastructure/scripts/reset_database.py [--no-backup] [--force]

Options:
    --no-backup    Skip backup creation (use with caution)
    --force        Skip confirmation prompt
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from infrastructure.database.connection import get_engine, session_scope, get_database_url


# Tables in order of truncation (respects foreign key dependencies)
# Tables with FK dependencies should be listed BEFORE tables they depend on
TRUNCATION_ORDER = [
    # Layer 3: Computed/derived tables
    "lct_calculations",
    "data_lineage",
    "calculation_runs",

    # Layer 2: Enrichment system
    "bell_schedules",
    "enrichment_attempts",
    "enrichment_queue",
    "enrichment_batches",

    # Layer 2: SPED estimates (depends on districts)
    "sped_estimates",

    # Layer 2: Staff and enrollment (depends on districts)
    "staff_counts_effective",
    "staff_counts",
    "enrollment_by_grade",

    # Layer 2: California-specific
    "ca_sped_district_environments",

    # Layer 2: Socioeconomic and funding
    "district_socioeconomic",
    "district_funding",
    "ca_lcff_funding",

    # Layer 2: SPED baseline (LEA-level)
    "sped_lea_baseline",

    # Layer 1.5: Crosswalk (FK ON DELETE CASCADE from districts — truncating districts wipes it
    # regardless; listing it EXPLICITLY so it is counted, reported, and verified rather than
    # silently cascaded (issue #16). Rebuild phase 2 re-imports it and verifies the count.
    "state_district_crosswalk",

    # Layer 1: Core tables (truncated last)
    "districts",
    "state_requirements",

    # Layer 0: Reference tables
    "data_source_registry",
    "sped_state_baseline",
]


def get_existing_tables(engine) -> set:
    """Get set of tables that actually exist in the database."""
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        return {row[0] for row in result}


def create_backup(backup_dir: Path) -> str:
    """
    Create a timestamped pg_dump backup.

    Args:
        backup_dir: Directory to store backup

    Returns:
        Path to backup file
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"backup_pre_reset_{timestamp}.sql"

    # Pass the FULL connection URL to pg_dump so host/port/user/password reach
    # it — the old bare-dbname invocation only worked against a default local
    # socket and silently ignored ?sslmode= query params (issues #305/#306).
    # pg_dump accepts a libpq URI; strip any SQLAlchemy "+driver" suffix first.
    db_url = re.sub(r'^postgresql\+[^:]+', 'postgresql', get_database_url())

    print(f"Creating backup to {backup_file}...")

    try:
        result = subprocess.run(
            ["pg_dump", "-d", db_url, "-f", str(backup_file)],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"  Backup created successfully ({backup_file.stat().st_size / 1024:.1f} KB)")
        return str(backup_file)
    except subprocess.CalledProcessError as e:
        print(f"  Error creating backup: {e.stderr}")
        raise
    except FileNotFoundError:
        print("  Error: pg_dump not found. Is PostgreSQL installed?")
        raise


def get_all_table_counts(engine, existing_tables: set = None) -> dict:
    """Get row counts for all tables in truncation order."""
    if existing_tables is None:
        existing_tables = get_existing_tables(engine)

    counts = {}
    with engine.connect() as conn:
        for table in TRUNCATION_ORDER:
            if table not in existing_tables:
                continue  # Skip tables that don't exist
            try:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                counts[table] = result.scalar()
            except Exception as e:
                counts[table] = f"ERROR: {e}"
    return counts


def truncate_all_tables(engine, existing_tables: set = None, verbose: bool = True) -> dict:
    """
    Truncate all tables using CASCADE.

    Args:
        engine: SQLAlchemy engine
        existing_tables: Set of tables that exist (for filtering)
        verbose: Print progress

    Returns:
        Dictionary of table: status
    """
    if existing_tables is None:
        existing_tables = get_existing_tables(engine)

    results = {}

    with engine.connect() as conn:
        # Use a single transaction for atomicity. No per-table swallow: after
        # any error Postgres aborts the whole transaction, so continuing the
        # loop just piles up "current transaction is aborted" errors while the
        # results dict claims earlier tables were truncated — they were rolled
        # back (issue #426). Fail loud and atomic instead.
        trans = conn.begin()

        try:
            for table in TRUNCATION_ORDER:
                if table not in existing_tables:
                    continue  # Skip tables that don't exist
                conn.execute(text(f"TRUNCATE {table} CASCADE"))
                results[table] = "truncated"
                if verbose:
                    print(f"  ✓ {table}")

            trans.commit()

        except Exception as e:
            trans.rollback()
            if verbose:
                print(f"  ✗ truncation failed, rolled back: {str(e).splitlines()[0]}")
            raise

    return results


def verify_empty_state(engine, existing_tables: set = None) -> bool:
    """
    Verify all tables are empty.

    Returns:
        True if all tables have 0 rows
    """
    if existing_tables is None:
        existing_tables = get_existing_tables(engine)

    counts = get_all_table_counts(engine, existing_tables)
    all_empty = True

    print("\nVerification:")
    for table, count in counts.items():
        if isinstance(count, int) and count == 0:
            print(f"  ✓ {table}: 0 rows")
        elif isinstance(count, int):
            print(f"  ✗ {table}: {count} rows (should be 0)")
            all_empty = False
        else:
            print(f"  ? {table}: {count}")
            all_empty = False

    return all_empty


def main():
    parser = argparse.ArgumentParser(
        description="Reset the Learning Connection Time database"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup creation (use with caution)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=project_root / "data" / "backups",
        help="Directory for backup files"
    )

    args = parser.parse_args()

    # Show current state
    print("=" * 60)
    print("DATABASE RESET SCRIPT")
    print("=" * 60)

    engine = get_engine()

    # Get tables that actually exist
    existing_tables = get_existing_tables(engine)
    print(f"\nFound {len(existing_tables)} tables in database")

    print("\nCurrent database state:")
    current_counts = get_all_table_counts(engine, existing_tables)
    total_rows = 0
    for table, count in current_counts.items():
        if isinstance(count, int):
            total_rows += count
            if count > 0:
                print(f"  {table}: {count:,} rows")
        else:
            print(f"  {table}: {count}")

    print(f"\nTotal rows to delete: {total_rows:,}")

    if total_rows == 0:
        print("\nDatabase is already empty. Nothing to do.")
        return 0

    # Confirmation
    if not args.force:
        print("\n" + "=" * 60)
        print("WARNING: This will DELETE ALL DATA in the database!")
        print("=" * 60)
        response = input("\nType 'yes' to confirm: ")
        if response.lower() != "yes":
            print("Aborted.")
            return 1

    # Backup
    backup_file = None
    if not args.no_backup:
        print("\n--- Creating backup ---")
        try:
            backup_file = create_backup(args.backup_dir)
        except Exception as e:
            print(f"Backup failed: {e}")
            print("Use --no-backup to proceed without backup (not recommended)")
            return 1
    else:
        print("\n--- Skipping backup (--no-backup specified) ---")

    # Truncate
    print("\n--- Truncating tables ---")
    try:
        results = truncate_all_tables(engine, existing_tables)
    except Exception as e:
        print(f"\nTruncation failed: {e}")
        if backup_file:
            print(f"Restore from backup: psql learning_connection_time < {backup_file}")
        return 1

    # Verify
    print("\n--- Verifying empty state ---")
    if verify_empty_state(engine, existing_tables):
        print("\n" + "=" * 60)
        print("DATABASE RESET COMPLETE")
        print("=" * 60)
        if backup_file:
            print(f"\nBackup saved to: {backup_file}")
        print("\nThe database schema is intact. Tables are empty.")
        print("Run rebuild_database.py to repopulate from raw sources.")
        return 0
    else:
        print("\nVerification FAILED - some tables not empty")
        return 1


if __name__ == "__main__":
    sys.exit(main())
