#!/usr/bin/env python3
"""
Import Texas Education Agency (TEA) District Identifiers Crosswalk

This script imports TEA district metadata into tx_district_identifiers table.
Uses state_district_crosswalk table as source of truth for NCES ↔ TEA mapping.

Data Source:
- state_district_crosswalk table (populated from NCES CCD ST_LEAID field)
- Optional: CSV file for additional TEA-specific metadata

Usage:
    python import_tx_crosswalk.py
"""

import sys
import os
from pathlib import Path
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import District
from sqlalchemy import text
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_nces_id_from_crosswalk(session, state: str, state_district_id: str) -> str:
    """Look up NCES ID from state district ID using crosswalk table.

    Args:
        session: Database session
        state: Two-letter state code (e.g., 'TX')
        state_district_id: State's district ID (e.g., '101912' for Houston ISD)

    Returns:
        NCES LEAID or None if not found
    """
    result = session.execute(text("""
        SELECT nces_id
        FROM state_district_crosswalk
        WHERE state = :state
          AND state_district_id = :state_id
          AND id_system = 'st_leaid'
    """), {"state": state, "state_id": state_district_id})
    row = result.fetchone()
    return row[0] if row else None


def load_texas_crosswalk(session) -> dict:
    """Load Texas crosswalk from database.

    Returns:
        Dict mapping TEA district number -> NCES ID
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = 'TX'
          AND id_system = 'st_leaid'
    """))
    return {row[0]: row[1] for row in result.fetchall()}


def load_crosswalk_data():
    """Load TEA ↔ NCES crosswalk CSV file."""
    crosswalk_file = project_root / 'data/raw/state/texas/district_identifiers/texas_nces_tea_crosswalk_2018_19.csv'

    if not crosswalk_file.exists():
        logger.error(f"Crosswalk file not found: {crosswalk_file}")
        return None

    logger.info(f"Loading crosswalk data from: {crosswalk_file}")
    df = pd.read_csv(crosswalk_file)

    logger.info(f"Loaded {len(df)} Texas districts from crosswalk file")
    logger.info(f"Columns: {list(df.columns)}")

    return df


def import_crosswalk(df):
    """Import TEA district identifiers and update st_leaid in districts table.

    Uses state_district_crosswalk table as source of truth for NCES ↔ TEA mappings.
    Validates CSV data against crosswalk and logs any discrepancies.
    """
    with session_scope() as session:
        imported_count = 0
        updated_count = 0
        skipped_count = 0
        mismatch_count = 0

        # Load crosswalk from database (source of truth)
        db_crosswalk = load_texas_crosswalk(session)
        logger.info(f"Loaded {len(db_crosswalk)} Texas mappings from crosswalk table")

        for idx, row in df.iterrows():
            tea_district_no = str(row['TEA_DISTRICT_NO']).zfill(6)  # Ensure 6 digits
            csv_nces_leaid = str(row['NCES_LEAID'])
            st_leaid = row['ST_LEAID']
            district_name = row['DISTRICT_NAME']
            lea_type_text = row['LEA_TYPE_TEXT']
            charter_text = row['CHARTER_LEA_TEXT']

            # Extract state district ID from ST_LEAID (format: "TX-XXXXXX")
            state_district_id = st_leaid.replace('TX-', '') if st_leaid.startswith('TX-') else tea_district_no

            # Use crosswalk table as source of truth for NCES ID
            db_nces_id = db_crosswalk.get(state_district_id)

            if db_nces_id and db_nces_id != csv_nces_leaid:
                logger.warning(
                    f"NCES ID mismatch for {district_name}: "
                    f"CSV={csv_nces_leaid}, crosswalk={db_nces_id} - using crosswalk"
                )
                mismatch_count += 1
                nces_leaid = db_nces_id
            elif db_nces_id:
                nces_leaid = db_nces_id
            else:
                # Not in crosswalk, use CSV value but warn
                logger.debug(f"District {state_district_id} not in crosswalk, using CSV NCES ID")
                nces_leaid = csv_nces_leaid

            # Determine if charter
            is_charter = 'charter' in charter_text.lower()

            # Determine charter type
            charter_type = None
            if is_charter:
                if 'Independent' in charter_text:
                    charter_type = 'Independent Charter'
                elif 'Campus' in charter_text or 'campus program' in charter_text.lower():
                    charter_type = 'Campus Program Charter'
                else:
                    charter_type = charter_text

            # Check if district exists in districts table
            district = session.query(District).filter_by(nces_id=nces_leaid).first()

            if not district:
                logger.warning(f"District {nces_leaid} ({district_name}) not found in districts table - skipping")
                skipped_count += 1
                continue

            # Update st_leaid in districts table
            district.st_leaid = st_leaid
            updated_count += 1

            # Insert into tx_district_identifiers
            insert_sql = text("""
                INSERT INTO tx_district_identifiers (
                    nces_id,
                    tea_district_no,
                    st_leaid,
                    tea_district_type_text,
                    is_charter,
                    charter_type,
                    data_source,
                    source_year
                ) VALUES (
                    :nces_id,
                    :tea_district_no,
                    :st_leaid,
                    :tea_district_type_text,
                    :is_charter,
                    :charter_type,
                    :data_source,
                    :source_year
                )
                ON CONFLICT (nces_id) DO UPDATE SET
                    tea_district_no = EXCLUDED.tea_district_no,
                    st_leaid = EXCLUDED.st_leaid,
                    tea_district_type_text = EXCLUDED.tea_district_type_text,
                    is_charter = EXCLUDED.is_charter,
                    charter_type = EXCLUDED.charter_type,
                    updated_at = CURRENT_TIMESTAMP
            """)

            session.execute(insert_sql, {
                'nces_id': nces_leaid,
                'tea_district_no': tea_district_no,
                'st_leaid': st_leaid,
                'tea_district_type_text': lea_type_text,
                'is_charter': is_charter,
                'charter_type': charter_type,
                'data_source': 'nces_ccd',
                'source_year': '2018-19'
            })

            imported_count += 1

            if (idx + 1) % 100 == 0:
                logger.info(f"Processed {idx + 1}/{len(df)} districts...")

        session.commit()

        logger.info(f"\n✅ Import complete!")
        logger.info(f"   - Imported to tx_district_identifiers: {imported_count}")
        logger.info(f"   - Updated st_leaid in districts: {updated_count}")
        logger.info(f"   - Skipped (not in districts table): {skipped_count}")
        if mismatch_count > 0:
            logger.warning(f"   - NCES ID mismatches (used crosswalk): {mismatch_count}")

        return imported_count, updated_count, skipped_count


def verify_import():
    """Verify the import by checking counts and sample data."""
    with session_scope() as session:
        # Count total Texas districts in tx_district_identifiers
        result = session.execute(text("""
            SELECT COUNT(*) FROM tx_district_identifiers
        """))
        tx_count = result.scalar()

        # Count Texas districts with st_leaid in districts table
        result = session.execute(text("""
            SELECT COUNT(*)
            FROM districts
            WHERE state = 'TX' AND st_leaid IS NOT NULL
        """))
        districts_count = result.scalar()

        # Sample data
        result = session.execute(text("""
            SELECT
                d.nces_id,
                d.name,
                d.st_leaid,
                tx.tea_district_no,
                tx.is_charter
            FROM districts d
            JOIN tx_district_identifiers tx ON d.nces_id = tx.nces_id
            WHERE d.state = 'TX'
            LIMIT 5
        """))
        samples = result.fetchall()

        logger.info(f"\n📊 Verification:")
        logger.info(f"   - TX districts in tx_district_identifiers: {tx_count}")
        logger.info(f"   - TX districts with st_leaid in districts: {districts_count}")
        logger.info(f"\n   Sample data:")
        for sample in samples:
            logger.info(f"     {sample[0]} | {sample[1][:30]:30s} | {sample[2]} | TEA#{sample[3]} | Charter: {sample[4]}")


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("Texas District Identifiers Crosswalk Import")
    logger.info("=" * 70)

    # Load crosswalk data
    df = load_crosswalk_data()
    if df is None:
        logger.error("❌ Failed to load crosswalk data")
        sys.exit(1)

    # Import data
    try:
        imported, updated, skipped = import_crosswalk(df)

        # Verify import
        verify_import()

        logger.info("\n✅ Texas crosswalk import complete!")
        logger.info("\nNext steps:")
        logger.info("   1. Import NCES CCD enrollment/staffing data for Texas")
        logger.info("   2. Validate data against TEA enrollment summary")
        logger.info("   3. Run integration validation report")

        sys.exit(0)

    except Exception as e:
        logger.error(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
