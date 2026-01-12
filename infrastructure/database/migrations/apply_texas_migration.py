#!/usr/bin/env python3
"""
Apply Texas Integration Migration (005)

This script applies migration 005 which adds:
1. st_leaid field to districts table (for multi-state use)
2. tx_district_identifiers table for TEA crosswalk
3. tx_sped_district_data table (placeholder for future)
4. v_texas_districts view for consolidated queries

Usage:
    python apply_texas_migration.py
"""

import sys
import os
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
    """Apply migration 005: Texas Integration."""
    migration_file = Path(__file__).parent / '005_add_texas_integration.sql'

    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False

    logger.info(f"Reading migration file: {migration_file}")
    with open(migration_file, 'r') as f:
        migration_sql = f.read()

    engine = get_engine()

    try:
        logger.info("Applying migration 005: Texas Integration...")

        with engine.connect() as conn:
            # Execute migration
            conn.execute(text(migration_sql))
            conn.commit()

        logger.info("✅ Migration 005 applied successfully!")

        # Verify tables were created
        with session_scope() as session:
            result = session.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('tx_district_identifiers', 'tx_sped_district_data')
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]

            logger.info(f"Created tables: {', '.join(tables)}")

            # Check if st_leaid column was added
            result = session.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'districts'
                AND column_name = 'st_leaid'
            """))
            if result.fetchone():
                logger.info("✅ Added st_leaid column to districts table")

            # Check if view was created
            result = session.execute(text("""
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'public'
                AND table_name = 'v_texas_districts'
            """))
            if result.fetchone():
                logger.info("✅ Created v_texas_districts view")

        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Texas Integration Migration (005)")
    logger.info("=" * 60)

    success = apply_migration()

    if success:
        logger.info("\n✅ Migration complete! Next steps:")
        logger.info("   1. Import TEA district identifiers crosswalk")
        logger.info("   2. Update districts table with st_leaid values")
        logger.info("   3. Import NCES CCD data for Texas districts")
        sys.exit(0)
    else:
        logger.error("\n❌ Migration failed. Please review errors above.")
        sys.exit(1)
