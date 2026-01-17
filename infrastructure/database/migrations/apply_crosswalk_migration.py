#!/usr/bin/env python3
"""
Apply State Crosswalk Migration (007)

This script applies migration 007 which creates:
1. state_district_crosswalk table (master crosswalk)
2. Populates from ST_LEAID field in districts table
3. Helper functions for crosswalk lookups

Usage:
    python apply_crosswalk_migration.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import get_engine, session_scope
from sqlalchemy import text
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def apply_migration():
    """Apply migration 007: State District Crosswalk."""
    migration_file = Path(__file__).parent / '007_add_state_crosswalk.sql'

    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False

    logger.info(f"Reading migration file: {migration_file}")
    with open(migration_file, 'r') as f:
        migration_sql = f.read()

    engine = get_engine()

    try:
        logger.info("Applying migration 007: State District Crosswalk...")

        with engine.connect() as conn:
            # Execute migration
            conn.execute(text(migration_sql))
            conn.commit()

        logger.info("Migration applied successfully!")

        # Verify table was created and populated
        with session_scope() as session:
            # Check table exists
            result = session.execute(text("""
                SELECT COUNT(*) FROM state_district_crosswalk
            """))
            count = result.scalar()
            logger.info(f"Crosswalk table created with {count} entries")

            # Check state distribution
            result = session.execute(text("""
                SELECT state, COUNT(*) as count
                FROM state_district_crosswalk
                GROUP BY state
                ORDER BY count DESC
                LIMIT 10
            """))
            rows = result.fetchall()
            logger.info("Top 10 states by crosswalk entries:")
            for row in rows:
                logger.info(f"  {row[0]}: {row[1]} districts")

            # Verify Florida crosswalk matches our known mappings
            result = session.execute(text("""
                SELECT nces_id, state_district_id
                FROM state_district_crosswalk
                WHERE state = 'FL'
                ORDER BY state_district_id
                LIMIT 15
            """))
            rows = result.fetchall()
            logger.info("\nFlorida crosswalk (sample):")
            for row in rows:
                logger.info(f"  NCES {row[0]} -> FLDOE {row[1]}")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_crosswalk():
    """Verify crosswalk matches known Florida mappings."""
    logger.info("\nVerifying Florida crosswalk against known values...")

    # Known correct mappings from our Florida integration
    known_mappings = {
        "1200390": "13",   # Miami-Dade
        "1200180": "06",   # Broward
        "1200870": "29",   # Hillsborough
        "1201440": "48",   # Orange
        "1201500": "50",   # Palm Beach
        "1200480": "16",   # Duval
        "1201590": "53",   # Polk
        "1201080": "36",   # Lee
        "1201560": "52",   # Pinellas
        "1201530": "51",   # Pasco
        "1200150": "05",   # Brevard
    }

    with session_scope() as session:
        all_match = True
        for nces_id, expected_fldoe in known_mappings.items():
            result = session.execute(text("""
                SELECT state_district_id
                FROM state_district_crosswalk
                WHERE nces_id = :nces_id AND id_system = 'st_leaid'
            """), {"nces_id": nces_id})
            row = result.fetchone()

            if row is None:
                logger.error(f"  NCES {nces_id}: NOT FOUND in crosswalk")
                all_match = False
            elif row[0] != expected_fldoe:
                logger.error(f"  NCES {nces_id}: Expected {expected_fldoe}, got {row[0]}")
                all_match = False
            else:
                logger.info(f"  NCES {nces_id} -> FLDOE {row[0]}")

        if all_match:
            logger.info("All Florida mappings verified correctly!")
        else:
            logger.warning("Some Florida mappings did not match!")

        return all_match


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("State District Crosswalk Migration (007)")
    logger.info("=" * 60)

    success = apply_migration()

    if success:
        verify_success = verify_crosswalk()

        logger.info("\n" + "=" * 60)
        logger.info("Migration Summary:")
        logger.info(f"  Table created: {'Yes' if success else 'No'}")
        logger.info(f"  Florida verified: {'Yes' if verify_success else 'No'}")
        logger.info("=" * 60)

        if verify_success:
            logger.info("\nNext steps:")
            logger.info("  1. Update import scripts to use crosswalk table")
            logger.info("  2. Add year tracking to lct_calculations")
            logger.info("  3. Implement 3-year span validation")
            sys.exit(0)
        else:
            logger.warning("\nCrosswalk created but verification failed. Review logs.")
            sys.exit(1)
    else:
        logger.error("\nMigration failed. Please review errors above.")
        sys.exit(1)
