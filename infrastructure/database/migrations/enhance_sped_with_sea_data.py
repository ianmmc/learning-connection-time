#!/usr/bin/env python3
"""
Enhance SPED estimates with actual SEA data where available.

This script implements selective enhancement (Option B) for SPED teacher breakdowns:
- Florida (FL): Use actual classroom_teachers (GenEd) + ese_teachers (SPED)
- Other states: Keep federal estimates (baseline 2017-18)

Updates the sped_estimates table to prefer SEA actual data over federal estimates.

Usage:
    python enhance_sped_with_sea_data.py [--year 2023-24] [--dry-run]

Reference:
    - docs/technical-notes/SEA_TEACHER_CATEGORY_MAPPINGS.md (to be created)
    - Gemini consultation: January 19, 2026 (data architecture context)
"""

import argparse
import sys
from pathlib import Path
from typing import Dict

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from sqlalchemy import text
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def update_fl_sped_estimates(session, year: str, dry_run: bool = False) -> Dict[str, int]:
    """
    Update SPED estimates for Florida districts with actual SEA data.

    Args:
        session: SQLAlchemy session
        year: School year (e.g., "2023-24")
        dry_run: If True, don't commit changes

    Returns:
        Dict with statistics (updated, unchanged, errors)
    """
    stats = {
        'districts_checked': 0,
        'updated_with_actual': 0,
        'no_change_needed': 0,
        'errors': 0,
    }

    logger.info("Updating FL SPED estimates with actual SEA data...")

    # Get FL actual data and current estimates
    query = text("""
        SELECT
            se.id as estimate_id,
            se.district_id,
            se.estimated_sped_teachers,
            se.estimated_gened_teachers,
            se.estimation_method,
            se.confidence,
            fl.classroom_teachers as fl_gened_teachers,
            fl.ese_teachers as fl_sped_teachers,
            se.current_total_teachers,
            fl.classroom_teachers + fl.ese_teachers as fl_total_teachers
        FROM sped_estimates se
        JOIN fl_staff_data fl ON se.district_id = fl.nces_id
        WHERE se.estimate_year = :year
          AND fl.classroom_teachers IS NOT NULL
          AND fl.ese_teachers IS NOT NULL
    """)

    results = session.execute(query, {"year": year})

    for row in results:
        stats['districts_checked'] += 1

        (estimate_id, district_id, est_sped, est_gened, method, confidence,
         fl_gened, fl_sped, est_total, fl_total) = row

        # Only update if FL data is materially different from estimates
        # (allow 5% tolerance for rounding differences)
        gened_diff_pct = abs(fl_gened - est_gened) / est_gened * 100 if est_gened else 100
        sped_diff_pct = abs(fl_sped - est_sped) / est_sped * 100 if est_sped else 100

        if gened_diff_pct > 5 or sped_diff_pct > 5:
            if not dry_run:
                # Update with FL actual data
                update_query = text("""
                    UPDATE sped_estimates
                    SET estimated_gened_teachers = :gened_teachers,
                        estimated_sped_teachers = :sped_teachers,
                        estimation_method = 'fl_sea_actual',
                        confidence = 'high',
                        notes = CONCAT(COALESCE(notes, ''),
                                      '; Updated with FL SEA actual data (', :year, ')',
                                      ' replacing ', :old_method, ' estimate'),
                        updated_at = NOW()
                    WHERE id = :estimate_id
                """)

                session.execute(update_query, {
                    "gened_teachers": float(fl_gened),
                    "sped_teachers": float(fl_sped),
                    "year": year,
                    "old_method": method,
                    "estimate_id": estimate_id
                })

            stats['updated_with_actual'] += 1
            logger.info(
                f"  {district_id}: Updated - GenEd {est_gened:.1f} → {fl_gened:.1f}, "
                f"SPED {est_sped:.1f} → {fl_sped:.1f}"
            )
        else:
            stats['no_change_needed'] += 1

        if stats['districts_checked'] % 20 == 0:
            logger.info(f"  Processed {stats['districts_checked']} districts...")

    if not dry_run:
        session.commit()
        logger.info("Changes committed to database")
    else:
        logger.info("DRY RUN - no changes committed")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Enhance SPED estimates with actual SEA data"
    )
    parser.add_argument(
        "--year",
        default="2023-24",
        help="School year (default: 2023-24)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing"
    )
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("SPED ESTIMATES ENHANCEMENT WITH SEA DATA")
    logger.info("=" * 70)
    logger.info(f"School year: {args.year}")
    logger.info(f"States with SPED breakdowns: FL (classroom + ESE teachers)")
    logger.info("")

    with session_scope() as session:
        stats = update_fl_sped_estimates(
            session,
            year=args.year,
            dry_run=args.dry_run
        )

    logger.info("=" * 70)
    logger.info("ENHANCEMENT SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Districts checked: {stats['districts_checked']:,}")
    logger.info(f"Updated with actual SEA data: {stats['updated_with_actual']:,}")
    logger.info(f"No change needed (within 5% tolerance): {stats['no_change_needed']:,}")
    logger.info(f"Errors: {stats['errors']:,}")
    logger.info("")

    if args.dry_run:
        logger.info("DRY RUN COMPLETE - Run without --dry-run to apply changes")
    else:
        logger.info("ENHANCEMENT COMPLETE")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Run LCT calculations to use enhanced SPED data:")
        logger.info("   python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24")
        logger.info("2. Compare FL SPED scopes (core_sped, teachers_gened) before/after")
        logger.info("3. Document enhancement in methodology")


if __name__ == "__main__":
    main()
