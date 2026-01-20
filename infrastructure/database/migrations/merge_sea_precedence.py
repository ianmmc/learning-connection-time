#!/usr/bin/env python3
"""
Merge SEA (State Education Agency) data into staff_counts_effective with precedence.

This script implements the data precedence layer that prefers State over Federal sources:
- Precedence: SEA data > NCES CCD data (when available and within 3-year window)
- REQ-026: Enforces 3-year temporal blending window
- REQ-027: Uses master crosswalk table for NCES↔SEA mappings

**Precedence Rules:**
1. If SEA staff data exists for a district:
   - AND year span ≤ 3 years → Use SEA data (update primary_source)
   - AND year span > 3 years → Skip (ERR_SPAN_EXCEEDED, keep NCES)
2. Otherwise → Use NCES baseline (already in staff_counts_effective)

**Temporal Validation (REQ-026):**
- Same year (0 span): No flags
- 2-3 year span: WARN_YEAR_GAP flag
- >3 year span: ERR_SPAN_EXCEEDED flag, data rejected

**States with SEA Data (January 2026):**
- CA: 2024-25 (997 districts, 2-year span = WARN_YEAR_GAP)
- FL: 2024-25 (76 districts, 2-year span = WARN_YEAR_GAP)
- IL: 2023-24 (864 districts, perfect match with NCES)
- MA: 2025-26 (396 districts, 3-year span = WARN_YEAR_GAP)
- MI: 2023-24 (836 districts, perfect match with NCES)
- NY: 2023-24 (9298 staff records, perfect match with NCES)
- PA: 2024-25 (777 districts, 2-year span = WARN_YEAR_GAP)
- TX: 2024-25 (1,190 districts, 2-year span = WARN_YEAR_GAP)
- VA: 2025-26 (131 districts, 3-year span = WARN_YEAR_GAP)

Usage:
    python merge_sea_precedence.py [--year 2023-24] [--dry-run]

Reference:
    - docs/SEA_INTEGRATION_GUIDE.md
    - REQUIREMENTS.yaml (REQ-026, REQ-027)
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import StaffCountsEffective
from sqlalchemy import text
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# SEA State Configurations
SEA_STATES = {
    'CA': {'year': '2024-25', 'table': 'ca_staff_data'},
    'FL': {'year': '2024-25', 'table': 'fl_staff_data'},
    'IL': {'year': '2023-24', 'table': 'il_staff_data'},
    'MA': {'year': '2025-26', 'table': 'ma_staff_data'},
    'MI': {'year': '2023-24', 'table': 'mi_staff_data'},
    'NY': {'year': '2023-24', 'table': 'ny_staff_data'},
    'PA': {'year': '2024-25', 'table': 'pa_staff_data'},
    'TX': {'year': '2024-25', 'table': 'tx_staff_data'},
    'VA': {'year': '2025-26', 'table': 'va_staff_data'},
}


def calculate_year_span(year1: str, year2: str) -> int:
    """
    Calculate year span between two school years.

    Args:
        year1: School year in format "YYYY-YY"
        year2: School year in format "YYYY-YY"

    Returns:
        Absolute difference in start years (0 = same year, 1 = adjacent years)

    Examples:
        >>> calculate_year_span("2023-24", "2023-24")
        0
        >>> calculate_year_span("2023-24", "2024-25")
        1
        >>> calculate_year_span("2023-24", "2025-26")
        2
        >>> calculate_year_span("2023-24", "2026-27")
        3
    """
    # Extract starting year from each
    start1 = int(year1.split('-')[0])
    start2 = int(year2.split('-')[0])

    # Return absolute difference (0 = same, 1 = adjacent, 2+ = gap)
    return abs(start1 - start2)


def get_temporal_flags(year_span: int) -> List[str]:
    """
    Get temporal validation flags based on year span.

    Per REQ-026 (corrected):
    - 0-1 years: No flags (same year or adjacent years like 2024-25 and 2023-24)
    - 2-3 years: WARN_YEAR_GAP (1-2 year gap, e.g., 2025-26 and 2023-24)
    - >3 years: ERR_SPAN_EXCEEDED (exceeds blending window)

    Args:
        year_span: Absolute difference in start years (0 = same, 1 = adjacent)

    Returns:
        List of flag strings
    """
    flags = []

    if year_span >= 2 and year_span <= 3:
        flags.append('WARN_YEAR_GAP')
    elif year_span > 3:
        flags.append('ERR_SPAN_EXCEEDED')

    return flags


def load_sea_staff_data(session, state: str, sea_table: str) -> Dict[str, Dict]:
    """
    Load SEA staff data for a state.

    Args:
        session: SQLAlchemy session
        state: Two-letter state code
        sea_table: Name of SEA staff table

    Returns:
        Dict mapping NCES ID to staff data
    """
    logger.info(f"Loading {state} SEA staff data from {sea_table}...")

    # Each state has different column names, but all have nces_id and teachers_fte
    # We'll query the specific columns we need based on state

    state_queries = {
        'CA': """
            SELECT nces_id, teachers_fte, year
            FROM ca_staff_data
        """,
        'FL': """
            SELECT nces_id, classroom_teachers as teachers_fte, year
            FROM fl_staff_data
        """,
        'IL': """
            SELECT nces_id, total_teacher_fte as teachers_fte, year
            FROM il_staff_data
        """,
        'MA': """
            SELECT nces_id, teachers_fte, year
            FROM ma_staff_data
        """,
        'MI': """
            SELECT nces_id, total_teacher_fte as teachers_fte, year
            FROM mi_staff_data
        """,
        'NY': """
            SELECT nces_id, fte as teachers_fte, year
            FROM ny_staff_data
            WHERE staff_category = 'Classroom Teacher'
        """,
        'PA': """
            SELECT nces_id, classroom_teachers_fte as teachers_fte, year
            FROM pa_staff_data
        """,
        'TX': """
            SELECT nces_id, teachers_total_fte as teachers_fte, year
            FROM tx_staff_data
        """,
        'VA': """
            SELECT nces_id, teachers_fte, year
            FROM va_staff_data
        """,
    }

    query = state_queries.get(state)
    if not query:
        logger.warning(f"No query defined for state {state}")
        return {}

    try:
        result = session.execute(text(query))
        sea_data = {}

        for row in result:
            nces_id = row[0]
            teachers_fte = float(row[1]) if row[1] is not None else None
            year = row[2]

            sea_data[nces_id] = {
                'teachers_fte': teachers_fte,
                'year': year,
            }

        logger.info(f"  Loaded {len(sea_data)} districts from {state} SEA data")
        return sea_data

    except Exception as e:
        logger.error(f"Failed to load {state} SEA data: {e}")
        return {}


def merge_sea_into_effective(
    session,
    nces_year: str,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Merge SEA data into staff_counts_effective with precedence.

    Args:
        session: SQLAlchemy session
        nces_year: NCES baseline year (e.g., "2023-24")
        dry_run: If True, don't commit changes

    Returns:
        Dict with statistics (updated, skipped, etc.)
    """
    stats = {
        'total_checked': 0,
        'sea_updated': 0,
        'year_span_warnings': 0,
        'year_span_errors': 0,
        'no_sea_data': 0,
    }

    logger.info(f"Merging SEA data into staff_counts_effective for {nces_year}...")
    logger.info(f"Dry run: {dry_run}")

    # Process each state with SEA data
    for state_code, state_config in SEA_STATES.items():
        logger.info("=" * 70)
        logger.info(f"Processing {state_code} ({state_config['year']})...")

        # Load SEA data for this state
        sea_data = load_sea_staff_data(session, state_code, state_config['table'])

        if not sea_data:
            logger.warning(f"No SEA data loaded for {state_code}, skipping...")
            continue

        # Get all effective records for this state using raw SQL
        query = text("""
            SELECT staff_counts_effective.*
            FROM staff_counts_effective
            JOIN districts ON staff_counts_effective.district_id = districts.nces_id
            WHERE districts.state = :state_code
              AND staff_counts_effective.effective_year = :nces_year
        """)

        result = session.execute(query, {"state_code": state_code, "nces_year": nces_year})
        district_ids = [row[0] for row in result]  # Get district_id column

        # Now fetch the ORM objects
        effective_records = session.query(StaffCountsEffective).filter(
            StaffCountsEffective.district_id.in_(district_ids)
        ).all() if district_ids else []

        logger.info(f"  Found {len(effective_records)} {state_code} districts in staff_counts_effective")

        # Process each district
        for effective in effective_records:
            stats['total_checked'] += 1

            # Check if SEA data exists for this district
            if effective.district_id not in sea_data:
                stats['no_sea_data'] += 1
                continue

            sea_record = sea_data[effective.district_id]
            sea_year = sea_record['year']

            # Calculate year span
            year_span = calculate_year_span(nces_year, sea_year)

            # Check 3-year window (REQ-026)
            if year_span > 3:
                logger.warning(
                    f"  {effective.district_id}: Year span {year_span} exceeds 3-year window "
                    f"(NCES {nces_year}, SEA {sea_year}), skipping"
                )
                stats['year_span_errors'] += 1
                continue

            # Get temporal flags
            temporal_flags = get_temporal_flags(year_span)

            if 'WARN_YEAR_GAP' in temporal_flags:
                stats['year_span_warnings'] += 1

            # Update effective record with SEA data
            if not dry_run:
                # Update teachers_total from SEA (this is the main staff field we have)
                if sea_record['teachers_fte'] is not None:
                    effective.teachers_total = sea_record['teachers_fte']
                    # Also update teachers_k12 (calculated field)
                    effective.teachers_k12 = sea_record['teachers_fte']

                # Update metadata
                effective.primary_source = f"{state_code.lower()}_sea"
                effective.sources_used = [
                    {"source": "nces_ccd", "year": nces_year},
                    {"source": f"{state_code.lower()}_sea", "year": sea_year}
                ]
                effective.resolution_notes = f"SEA data merged from {state_code} ({sea_year}), year_span={year_span}, flags={temporal_flags}"

                # Recalculate scopes with updated staff counts
                effective.calculate_scopes()

            stats['sea_updated'] += 1

            if stats['sea_updated'] % 100 == 0:
                logger.info(f"  Processed {stats['sea_updated']} districts...")

    if not dry_run:
        session.commit()
        logger.info("Changes committed to database")
    else:
        logger.info("DRY RUN - no changes committed")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Merge SEA data into staff_counts_effective with precedence"
    )
    parser.add_argument(
        "--year",
        default="2023-24",
        help="NCES baseline year (default: 2023-24)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing"
    )
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("SEA PRECEDENCE MERGE")
    logger.info("=" * 70)
    logger.info(f"NCES baseline year: {args.year}")
    logger.info(f"States with SEA data: {', '.join(SEA_STATES.keys())}")
    logger.info("")

    with session_scope() as session:
        stats = merge_sea_into_effective(
            session,
            nces_year=args.year,
            dry_run=args.dry_run
        )

    logger.info("=" * 70)
    logger.info("MERGE SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total districts checked: {stats['total_checked']:,}")
    logger.info(f"Updated with SEA data: {stats['sea_updated']:,}")
    logger.info(f"Year span warnings (2-3 years): {stats['year_span_warnings']:,}")
    logger.info(f"Year span errors (>3 years): {stats['year_span_errors']:,}")
    logger.info(f"No SEA data available: {stats['no_sea_data']:,}")
    logger.info("")

    if args.dry_run:
        logger.info("DRY RUN COMPLETE - Run without --dry-run to apply changes")
    else:
        logger.info("MERGE COMPLETE")


if __name__ == "__main__":
    main()
