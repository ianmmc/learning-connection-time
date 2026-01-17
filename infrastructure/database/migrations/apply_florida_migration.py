#!/usr/bin/env python3
"""
Apply Florida Integration Migration (006)

This script applies migration 006 which adds:
1. fl_district_identifiers table for FLDOE crosswalk
2. fl_staff_data table for FLDOE staff counts
3. fl_enrollment_data table for FLDOE enrollment
4. v_florida_districts view for consolidated queries

Usage:
    python apply_florida_migration.py
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
    """Apply migration 006: Florida Integration."""
    migration_file = Path(__file__).parent / '006_add_florida_integration.sql'

    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False

    logger.info(f"Reading migration file: {migration_file}")
    with open(migration_file, 'r') as f:
        migration_sql = f.read()

    engine = get_engine()

    try:
        logger.info("Applying migration 006: Florida Integration...")

        with engine.connect() as conn:
            # Execute migration
            conn.execute(text(migration_sql))
            conn.commit()

        logger.info("✅ Migration 006 applied successfully!")

        # Verify tables were created
        with session_scope() as session:
            result = session.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('fl_district_identifiers', 'fl_staff_data', 'fl_enrollment_data')
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]

            logger.info(f"Created tables: {', '.join(tables)}")

            # Check if view was created
            result = session.execute(text("""
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'public'
                AND table_name = 'v_florida_districts'
            """))
            if result.fetchone():
                logger.info("✅ Created v_florida_districts view")

        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Florida Integration Migration (006)")
    logger.info("=" * 60)

    success = apply_migration()

    if success:
        logger.info("\n✅ Migration complete! Next steps:")
        logger.info("   1. Import FLDOE district identifiers crosswalk")
        logger.info("   2. Import FLDOE staff data from Excel files")
        logger.info("   3. Import FLDOE enrollment data from Excel files")
        logger.info("   4. Run integration tests to validate")
        sys.exit(0)
    else:
        logger.error("\n❌ Migration failed. Please review errors above.")
        sys.exit(1)
