#!/usr/bin/env python3
"""
Apply ST_LEAID migration and populate from NCES data.

Adds st_leaid column to districts table and populates it from raw NCES CCD data.
"""

import sys
from pathlib import Path
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import get_engine, session_scope
from infrastructure.database.models import District
from sqlalchemy import text

def add_st_leaid_column():
    """Add st_leaid column to districts table."""
    print("Adding st_leaid column to districts table...")

    engine = get_engine()
    with engine.connect() as conn:
        # Add column if doesn't exist
        conn.execute(text("ALTER TABLE districts ADD COLUMN IF NOT EXISTS st_leaid VARCHAR(20)"))

        # Add index
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_districts_st_leaid ON districts(st_leaid) WHERE st_leaid IS NOT NULL"))

        # Add comment
        conn.execute(text("COMMENT ON COLUMN districts.st_leaid IS 'State-assigned LEA ID (e.g., CA-6275796 for California CDS codes)'"))

        conn.commit()

    print("✓ Column added successfully")


def populate_st_leaid():
    """Populate st_leaid from raw NCES data."""
    print("\nPopulating st_leaid from NCES data...")

    # Find raw NCES directory file
    nces_dir = project_root / "data" / "raw" / "federal" / "nces-ccd" / "2023_24"
    directory_files = list(nces_dir.glob("ccd_lea_029_*.csv"))

    if not directory_files:
        print("✗ No NCES directory file found")
        return

    directory_file = directory_files[0]
    print(f"  Reading: {directory_file.name}")

    # Read ST_LEAID from directory file
    df = pd.read_csv(directory_file, usecols=['LEAID', 'ST_LEAID'], dtype=str)

    print(f"  Found {len(df)} records")

    # Update database
    engine = get_engine()
    updated_count = 0

    with session_scope() as session:
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

            if updated_count % 1000 == 0 and updated_count > 0:
                print(f"  Updated {updated_count} districts...")
                session.commit()

        session.commit()

    print(f"✓ Updated {updated_count} districts with ST_LEAID")


def verify_california_crosswalk():
    """Verify California CDS crosswalk."""
    print("\nVerifying California CDS crosswalk...")

    with session_scope() as session:
        # Count California districts with ST_LEAID
        ca_count = session.query(District).filter(
            District.state == 'CA',
            District.st_leaid.isnot(None)
        ).count()

        print(f"  California districts with ST_LEAID: {ca_count}")

        # Sample a few
        samples = session.query(District).filter(
            District.state == 'CA',
            District.st_leaid.isnot(None)
        ).limit(5).all()

        print("\n  Sample California districts:")
        for dist in samples:
            cds_code = dist.st_leaid.replace('CA-', '') if dist.st_leaid and dist.st_leaid.startswith('CA-') else dist.st_leaid
            print(f"    {dist.nces_id}: {dist.name[:40]:40s} | CDS: {cds_code}")


def main():
    """Main migration function."""
    print("=" * 70)
    print("Migration 004: Add ST_LEAID to districts table")
    print("=" * 70)

    add_st_leaid_column()
    populate_st_leaid()
    verify_california_crosswalk()

    print("\n" + "=" * 70)
    print("✓ Migration complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
