#!/usr/bin/env python3
"""
Apply Temporal Validation Migration (008)

This script applies migration 008 which adds:
1. School year utility functions
2. Year span tracking columns
3. 3-year window validation
4. Temporal data quality flags
5. Automatic validation trigger

Usage:
    python apply_temporal_validation.py
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
    """Apply migration 008: Temporal Validation."""
    migration_file = Path(__file__).parent / '008_add_temporal_validation.sql'

    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False

    logger.info(f"Reading migration file: {migration_file}")
    with open(migration_file, 'r') as f:
        migration_sql = f.read()

    engine = get_engine()

    try:
        logger.info("Applying migration 008: Temporal Validation...")

        with engine.connect() as conn:
            # Execute migration
            conn.execute(text(migration_sql))
            conn.commit()

        logger.info("Migration applied successfully!")

        # Verify functions were created
        with session_scope() as session:
            # Test school_year_to_numeric function
            result = session.execute(text("""
                SELECT school_year_to_numeric('2023-24')
            """))
            year_num = result.scalar()
            logger.info(f"Function test: school_year_to_numeric('2023-24') = {year_num}")

            # Test year_span function
            result = session.execute(text("""
                SELECT year_span('2023-24', '2025-26')
            """))
            span = result.scalar()
            logger.info(f"Function test: year_span('2023-24', '2025-26') = {span}")

            # Test is_within_3year_window function
            result = session.execute(text("""
                SELECT is_within_3year_window('2023-24', '2024-25', '2025-26')
            """))
            within_window = result.scalar()
            logger.info(f"Function test: is_within_3year_window('2023-24', '2024-25', '2025-26') = {within_window}")

            # Check if columns were added
            result = session.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'lct_calculations'
                AND column_name IN ('year_span', 'within_3year_window', 'temporal_flags')
                ORDER BY column_name
            """))
            columns = [row[0] for row in result]
            logger.info(f"New columns added: {', '.join(columns)}")

            # Check for validation trigger
            result = session.execute(text("""
                SELECT trigger_name
                FROM information_schema.triggers
                WHERE event_object_table = 'lct_calculations'
                AND trigger_name = 'trg_lct_temporal_validation'
            """))
            trigger = result.fetchone()
            if trigger:
                logger.info(f"Trigger created: {trigger[0]}")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_validation():
    """Test the temporal validation with sample data."""
    logger.info("\nTesting temporal validation...")

    with session_scope() as session:
        # Test cases
        test_cases = [
            ("Same year", "2023-24", "2023-24", "2023-24", True, 1),
            ("2-year span", "2023-24", "2024-25", "2024-25", True, 2),
            ("3-year span (valid)", "2023-24", "2024-25", "2025-26", True, 3),
            ("4-year span (invalid)", "2023-24", "2024-25", "2026-27", False, 4),
        ]

        all_passed = True
        for name, enroll_yr, staff_yr, bell_yr, expected_valid, expected_span in test_cases:
            result = session.execute(text("""
                SELECT
                    is_within_3year_window(:e, :s, :b) AS valid,
                    year_span(:e, :b) AS span
            """), {"e": enroll_yr, "s": staff_yr, "b": bell_yr})
            row = result.fetchone()
            actual_valid = row[0]
            actual_span = row[1]

            status = "✅" if actual_valid == expected_valid else "❌"
            logger.info(f"  {status} {name}: valid={actual_valid} (expected {expected_valid}), span={actual_span}")

            if actual_valid != expected_valid:
                all_passed = False

        return all_passed


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Temporal Validation Migration (008)")
    logger.info("=" * 60)

    success = apply_migration()

    if success:
        test_success = test_validation()

        logger.info("\n" + "=" * 60)
        logger.info("Migration Summary:")
        logger.info(f"  Schema updated: {'Yes' if success else 'No'}")
        logger.info(f"  Validation tests: {'Passed' if test_success else 'Failed'}")
        logger.info("=" * 60)

        if test_success:
            logger.info("\n✅ Temporal validation ready!")
            logger.info("\n3-Year Blending Window Rule:")
            logger.info("  - Data from multiple sources must span ≤3 consecutive school years")
            logger.info("  - Example: 2023-24 + 2024-25 + 2025-26 = VALID (span = 3)")
            logger.info("  - Example: 2023-24 + 2026-27 = INVALID (span = 4)")
            logger.info("\nException: SPED baseline ratios (2017-18) are exempt")
            sys.exit(0)
        else:
            logger.warning("\n⚠️  Some validation tests failed. Review logs.")
            sys.exit(1)
    else:
        logger.error("\n❌ Migration failed. Please review errors above.")
        sys.exit(1)
