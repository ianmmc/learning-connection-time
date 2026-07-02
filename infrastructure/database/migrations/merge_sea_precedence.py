#!/usr/bin/env python3
"""
Merge SEA (State Education Agency) data into staff_counts_effective with precedence.

**Precedence (REQ-023, decided 2026-07-01):**
    year-matched NCES > year-matched SEA > older NCES > older SEA

SEA NEVER unconditionally overwrites NCES. For a given field, SEA applies only when:
- NCES lacks a value for the field, OR
- the SEA year is STRICTLY newer than the NCES year,
and always subject to:
- the SEA year is not COVID-excluded (2019-20..2022-23; issue #14 / school_year module), and
- the blend window: start-year span <= MAX_BLEND_SPAN (2, i.e. 3 consecutive school
  years — REQ-026 as corrected; the old code allowed span <= 3), and
- the SEA value is not suppressed (None values are never merged — issue #22).

The pure decision lives in decide_precedence(); the loop only applies it.

**Coherence design choice (issue #14):**
SEA staff tables supply ONLY a district-total teacher FTE (no per-level split), so this
merge updates ONLY `teachers_total`. It does NOT touch `teachers_k12`, the per-level
teacher fields, or any `scope_*` field, and it does NOT call calculate_scopes() —
none of that computation's inputs changed, and the old code's pattern (set
teachers_k12 = SEA total, then let calculate_scopes() silently recompute it from the
NCES per-level fields) left rows claiming an SEA primary_source while every scope was
NCES-derived. Provenance is instead recorded FIELD-LEVEL: `primary_source` keeps its
NCES baseline value (the per-level fields and scopes that drive LCT remain NCES), and
`sources_used` lists which fields each source supplied. This keeps every row
internally consistent (teachers_k12 always matches its per-level inputs) and its
provenance honest.

**Temporal flags:**
- span 0-1: no flags
- span == 2: WARN_YEAR_GAP (edge of the blend window)
- span > 2: ERR_SPAN_EXCEEDED, data rejected

Usage:
    python merge_sea_precedence.py [--year 2023-24] [--dry-run]

Reference:
    - docs/SEA_INTEGRATION_GUIDE.md
    - docs/REQUIREMENTS.yaml (REQ-023, REQ-026, REQ-027)
    - infrastructure/database/school_year.py (single source of truth for years)
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
from infrastructure.database.school_year import (
    MAX_BLEND_SPAN, is_covid_year, start_year, year_span,
)
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
    'MA': {'year': '2024-25', 'table': 'ma_staff_data'},  # teacher file is 2024-25 (issue #23)
    'MI': {'year': '2023-24', 'table': 'mi_staff_data'},
    'NY': {'year': '2023-24', 'table': 'ny_staff_data'},
    'PA': {'year': '2024-25', 'table': 'pa_staff_data'},
    'TX': {'year': '2024-25', 'table': 'tx_staff_data'},
    'VA': {'year': '2025-26', 'table': 'va_staff_data'},
}


def get_temporal_flags(span: int) -> List[str]:
    """
    Get temporal validation flags based on year span (REQ-026, corrected window):
    - 0-1: no flags (same year or adjacent years)
    - == MAX_BLEND_SPAN (2): WARN_YEAR_GAP (edge of the 3-consecutive-year window)
    - > MAX_BLEND_SPAN: ERR_SPAN_EXCEEDED (rejected)
    """
    flags = []
    if span == MAX_BLEND_SPAN:
        flags.append('WARN_YEAR_GAP')
    elif span > MAX_BLEND_SPAN:
        flags.append('ERR_SPAN_EXCEEDED')
    return flags


def decide_precedence(
    nces_year: str,
    sea_year: str,
    nces_value: Optional[float],
    sea_value: Optional[float],
) -> Tuple[str, str]:
    """
    Pure REQ-023 precedence decision for one field of one district.

        year-matched NCES > year-matched SEA > older NCES > older SEA

    Returns (decision, reason) where decision is:
    - 'sea':  apply the SEA value (NCES lacks the field, or SEA is strictly newer
              within the blend window)
    - 'nces': keep the NCES value (NCES is year-matched or newer and has a value)
    - 'skip': SEA data inadmissible (suppressed, COVID year, malformed year, or
              outside the blend window) — NCES baseline stays untouched
    """
    if sea_value is None:
        return 'skip', 'SEA value suppressed/missing'
    try:
        nces_start = start_year(nces_year)
        sea_start = start_year(sea_year)
    except ValueError:
        return 'skip', f'malformed school year (nces={nces_year!r}, sea={sea_year!r})'
    if is_covid_year(sea_year):
        return 'skip', f'SEA year {sea_year} is COVID-excluded'
    span = abs(nces_start - sea_start)
    if span > MAX_BLEND_SPAN:
        return 'skip', f'span {span} exceeds blend window (max {MAX_BLEND_SPAN})'
    if nces_value is not None and nces_start >= sea_start:
        return 'nces', 'year-matched-or-newer NCES wins (REQ-023)'
    if nces_value is None:
        return 'sea', 'NCES lacks value; SEA supplements within blend window'
    return 'sea', 'SEA strictly newer than NCES within blend window'


def apply_sea_supplement(
    effective: StaffCountsEffective,
    state_code: str,
    nces_year: str,
    sea_year: str,
    sea_teachers_fte: float,
    reason: str,
) -> None:
    """
    Apply an admissible SEA teachers_total to an effective row, keeping the row
    internally coherent (see module docstring):

    - ONLY teachers_total changes. Per-level teacher fields, teachers_k12, and all
      scope_* fields remain NCES-derived; calculate_scopes() is deliberately NOT
      called because none of its inputs changed.
    - primary_source keeps its NCES baseline value; the SEA contribution is recorded
      field-level in sources_used and resolution_notes.
    """
    span = year_span(nces_year, sea_year)
    flags = get_temporal_flags(span)

    effective.teachers_total = sea_teachers_fte
    effective.sources_used = [
        {
            "source": "nces_ccd",
            "year": nces_year,
            "fields": [
                "per-level teacher fields", "teachers_k12", "all scope_* fields",
            ],
        },
        {
            "source": f"{state_code.lower()}_sea",
            "year": sea_year,
            "fields": ["teachers_total"],
        },
    ]
    effective.resolution_notes = (
        f"teachers_total from {state_code} SEA ({sea_year}): {reason}; "
        f"year_span={span}, flags={flags}; per-level fields, teachers_k12 and "
        f"scopes remain NCES ({nces_year})"
    )


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
        'nces_kept': 0,
        'sea_rejected': 0,
        'year_span_warnings': 0,
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

        # Now fetch the ORM objects (year-scoped to match the raw-SQL prefilter above —
        # staff_counts_effective is multi-year since migration 017)
        effective_records = session.query(StaffCountsEffective).filter(
            StaffCountsEffective.district_id.in_(district_ids),
            StaffCountsEffective.effective_year == nces_year,
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
            sea_fte = sea_record['teachers_fte']

            nces_total = (
                float(effective.teachers_total)
                if effective.teachers_total is not None else None
            )

            # REQ-023 precedence: year-matched NCES > year-matched SEA >
            # older NCES > older SEA (COVID/suppressed/out-of-window SEA rejected)
            decision, reason = decide_precedence(nces_year, sea_year, nces_total, sea_fte)

            if decision == 'skip':
                logger.warning(
                    f"  {effective.district_id}: SEA data rejected — {reason} "
                    f"(NCES {nces_year}, SEA {sea_year})"
                )
                stats['sea_rejected'] += 1
                continue

            if decision == 'nces':
                stats['nces_kept'] += 1
                continue

            # decision == 'sea'
            if 'WARN_YEAR_GAP' in get_temporal_flags(year_span(nces_year, sea_year)):
                stats['year_span_warnings'] += 1

            if not dry_run:
                apply_sea_supplement(
                    effective, state_code, nces_year, sea_year, sea_fte, reason
                )

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
    logger.info(f"NCES kept (year-matched or newer): {stats['nces_kept']:,}")
    logger.info(f"SEA rejected (suppressed/COVID/out-of-window): {stats['sea_rejected']:,}")
    logger.info(f"Year span warnings (span == {MAX_BLEND_SPAN}): {stats['year_span_warnings']:,}")
    logger.info(f"No SEA data available: {stats['no_sea_data']:,}")
    logger.info("")

    if args.dry_run:
        logger.info("DRY RUN COMPLETE - Run without --dry-run to apply changes")
    else:
        logger.info("MERGE COMPLETE")


if __name__ == "__main__":
    main()
