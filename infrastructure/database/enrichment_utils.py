#!/usr/bin/env python3
"""
Enrichment Utilities
Utility functions for managing enrichment data integration

Primary function:
- copy_enrichment_to_bell_schedules: Copies completed enrichment results to bell_schedules table
  so they can be used by LCT calculations
"""

import json
import logging
from datetime import datetime
from typing import Tuple, Optional, Dict, List
from sqlalchemy.orm import Session

from infrastructure.database.models import EnrichmentQueue, BellSchedule
from infrastructure.database.school_year import CURRENT_SCHOOL_YEAR
from infrastructure.database.verification import validate_schedule_plausibility

logger = logging.getLogger(__name__)


def resolve_grade_level(schedule_type: str, schools_sampled: List[Dict] = None) -> Tuple[str, bool]:
    """
    Resolve schedule_type from enrichment data to a valid grade_level, saying so
    when it had to guess (issue #68 — 'all'/'district_average' used to map to
    'high' silently).

    Args:
        schedule_type: Schedule type from enrichment (e.g., 'all', 'high_school', 'district_average')
        schools_sampled: Optional list of schools with level information

    Returns:
        (grade_level, was_defaulted): grade_level is 'elementary', 'middle', or 'high';
        was_defaulted is True when nothing in the input indicated a level and 'high'
        was used as the fallback — callers should record that caveat.
    """
    schedule_lower = schedule_type.lower()

    # Direct mappings
    if 'high' in schedule_lower or 'hs' in schedule_lower or 'secondary' in schedule_lower:
        return 'high', False
    elif 'middle' in schedule_lower or 'ms' in schedule_lower or 'intermediate' in schedule_lower:
        return 'middle', False
    elif 'elementary' in schedule_lower or 'elem' in schedule_lower or 'primary' in schedule_lower:
        return 'elementary', False

    # Check schools_sampled for clues
    if schools_sampled:
        for school in schools_sampled:
            if isinstance(school, dict):
                level = school.get('level', '').lower()
                if 'high' in level or 'hs' in level or 'secondary' in level:
                    return 'high', False
                elif 'middle' in level or 'ms' in level or 'intermediate' in level:
                    return 'middle', False
                elif 'elem' in level or 'primary' in level:
                    return 'elementary', False

    # No signal — default to high (most common in secondary/unified districts),
    # but tell the caller it is a guess.
    logger.warning(
        "schedule_type %r has no grade-level signal; defaulting grade_level to 'high'",
        schedule_type,
    )
    return 'high', True


def map_schedule_type_to_grade_level(schedule_type: str, schools_sampled: List[Dict] = None) -> str:
    """Backward-compatible wrapper around resolve_grade_level() (drops the flag)."""
    grade_level, _ = resolve_grade_level(schedule_type, schools_sampled)
    return grade_level


def map_confidence_to_category(confidence: float) -> str:
    """
    Map numeric confidence (0.0-1.0) to categorical confidence for bell_schedules table

    Args:
        confidence: Numeric confidence score from enrichment

    Returns:
        Valid confidence category: 'high', 'medium', or 'low'
    """
    if confidence >= 0.8:
        return 'high'
    elif confidence >= 0.5:
        return 'medium'
    else:
        return 'low'


def copy_enrichment_to_bell_schedules(
    session: Session,
    district_id: str,
    force: bool = False,
    commit: bool = True
) -> Tuple[bool, str]:
    """
    Copy completed enrichment results to bell_schedules table

    This function bridges the gap between the enrichment_queue (where enrichment results
    are stored) and the bell_schedules table (which LCT calculations use).

    Args:
        session: SQLAlchemy session
        district_id: NCES district ID
        force: If True, update existing records even if they exist
        commit: If True (default), commit the write; pass False when the CALLER
            owns the transaction (issue #68 — the unconditional commit here broke
            caller transactionality). With commit=False the write is flushed only.

    Returns:
        Tuple of (success: bool, message: str)
    """
    # Get enrichment record
    enrichment = session.query(EnrichmentQueue).filter_by(district_id=district_id).first()

    if not enrichment:
        return False, "District not found in enrichment queue"

    if enrichment.status != 'completed':
        return False, f"Enrichment not completed (status: {enrichment.status})"

    # Get the tier result data
    tier_result = None
    tier = enrichment.current_tier

    if tier == 1 and enrichment.tier_1_result:
        tier_result = enrichment.tier_1_result
    elif tier == 2 and enrichment.tier_2_result:
        tier_result = enrichment.tier_2_result
    elif tier == 3 and enrichment.tier_3_result:
        tier_result = enrichment.tier_3_result
    elif tier == 4 and enrichment.tier_4_result:
        tier_result = enrichment.tier_4_result
    elif tier == 5 and enrichment.tier_5_result:
        tier_result = enrichment.tier_5_result

    if not tier_result or not isinstance(tier_result, dict):
        return False, f"No tier result data at tier {tier}"

    # Extract instructional minutes
    total_minutes = tier_result.get('total_minutes') or tier_result.get('instructional_minutes')
    if not total_minutes:
        return False, "No instructional minutes data in tier result"

    # Extract schedule data. Absent times stay None (issue #68 — the old
    # 'Unknown' placeholder could never pass time-format validation, so
    # minutes-only enrichments were permanently uncopyable).
    start_time = tier_result.get('start_time') or None
    end_time = tier_result.get('end_time') or None
    source_url = tier_result.get('source_url') or None
    year = tier_result.get('year', CURRENT_SCHOOL_YEAR)
    schedule_type = tier_result.get('schedule_type', 'high')
    schools_sampled = tier_result.get('schools_sampled', [])
    extraction_method = tier_result.get('extraction_method', f'tier_{tier}')
    confidence = tier_result.get('confidence', 0.8)
    notes = tier_result.get('notes', '')

    # Map to valid bell_schedules values
    grade_level, grade_defaulted = resolve_grade_level(schedule_type, schools_sampled)
    if grade_defaulted:
        notes = (
            f"grade_level defaulted to 'high' (schedule_type={schedule_type!r} "
            f"had no grade-level signal). {notes}"
        )
    method = 'automated_enrichment'  # All enriched data uses this method
    confidence_str = map_confidence_to_category(confidence)

    # Ensure source_url is a list
    if source_url is None:
        source_urls = []
    else:
        source_urls = [source_url] if isinstance(source_url, str) else source_url

    # REQ-038: Validate schedule plausibility before database insertion
    validation_result = validate_schedule_plausibility({
        'start_time': start_time,
        'end_time': end_time,
        'grade_level': grade_level,
        'instructional_minutes': total_minutes
    })

    if not validation_result['valid']:
        return False, f"Schedule validation failed: {'; '.join(validation_result['errors'])}"

    # Log warnings but don't block
    if validation_result['warnings']:
        notes = f"WARNINGS: {'; '.join(validation_result['warnings'])}. {notes}"

    # Check if already exists
    existing = session.query(BellSchedule).filter_by(
        district_id=district_id,
        year=year,
        grade_level=grade_level
    ).first()

    if existing and not force:
        return False, f"Bell schedule already exists for {district_id} {year} {grade_level} (use force=True to update)"

    if existing:
        # Update existing
        existing.start_time = start_time
        existing.end_time = end_time
        existing.instructional_minutes = total_minutes
        existing.source_urls = source_urls
        existing.source_description = f"Tier {tier}: {extraction_method}"
        existing.method = method
        existing.confidence = confidence_str
        existing.schools_sampled = schools_sampled if schools_sampled else []
        existing.notes = f"Updated from enrichment tier {tier}. {notes}".strip()
        action = "Updated"
    else:
        # Create new
        new_schedule = BellSchedule(
            district_id=district_id,
            year=year,
            grade_level=grade_level,
            start_time=start_time,
            end_time=end_time,
            instructional_minutes=total_minutes,
            source_urls=source_urls,
            source_description=f"Tier {tier}: {extraction_method}",
            method=method,
            confidence=confidence_str,
            schools_sampled=schools_sampled if schools_sampled else [],
            notes=f"Imported from enrichment tier {tier}. {notes}".strip()
        )
        session.add(new_schedule)
        action = "Created"

    if commit:
        session.commit()
    else:
        session.flush()
    return True, f"{action} bell schedule: {total_minutes} min, {grade_level}, {confidence_str} confidence"


def copy_all_completed_enrichments(
    session: Session,
    force: bool = False,
    verbose: bool = True,
    commit_each: bool = True
) -> Dict[str, any]:
    """
    Copy all completed enrichment results to bell_schedules table

    Args:
        session: SQLAlchemy session
        force: If True, update existing records
        verbose: If True, print progress
        commit_each: If True (default), commit after each district so one bad
            district cannot lose the batch; pass False to let the caller own
            the transaction (issue #68)

    Returns:
        Summary dictionary with counts
    """
    # Get all completed enrichments
    completed = session.query(EnrichmentQueue).filter_by(status='completed').all()

    results = {
        'total': len(completed),
        'success': 0,
        'skipped': 0,
        'failed': 0,
        'errors': []
    }

    for enrichment in completed:
        success, message = copy_enrichment_to_bell_schedules(
            session,
            enrichment.district_id,
            force=force,
            commit=commit_each
        )

        if success:
            results['success'] += 1
            if verbose:
                print(f"✓ {enrichment.district_id}: {message}")
        elif "already exists" in message and not force:
            results['skipped'] += 1
            if verbose:
                print(f"⊘ {enrichment.district_id}: {message}")
        else:
            results['failed'] += 1
            results['errors'].append({
                'district_id': enrichment.district_id,
                'error': message
            })
            if verbose:
                print(f"✗ {enrichment.district_id}: {message}")

    return results


if __name__ == '__main__':
    """
    CLI usage:

    # Copy specific district
    python infrastructure/database/enrichment_utils.py --district 3000655

    # Copy all completed enrichments
    python infrastructure/database/enrichment_utils.py --all

    # Force update existing records
    python infrastructure/database/enrichment_utils.py --all --force
    """
    import argparse
    from infrastructure.database.connection import session_scope

    parser = argparse.ArgumentParser(description="Copy enrichment results to bell_schedules table")
    parser.add_argument('--district', help='Specific district NCES ID')
    parser.add_argument('--all', action='store_true', help='Copy all completed enrichments')
    parser.add_argument('--force', action='store_true', help='Force update existing records')
    parser.add_argument('--quiet', action='store_true', help='Suppress output')

    args = parser.parse_args()

    with session_scope() as session:
        if args.district:
            success, message = copy_enrichment_to_bell_schedules(
                session,
                args.district,
                force=args.force
            )
            if not args.quiet:
                print(message)
        elif args.all:
            results = copy_all_completed_enrichments(
                session,
                force=args.force,
                verbose=not args.quiet
            )
            if not args.quiet:
                print("\n" + "=" * 80)
                print("SUMMARY")
                print("=" * 80)
                print(f"Total: {results['total']}")
                print(f"Success: {results['success']}")
                print(f"Skipped: {results['skipped']}")
                print(f"Failed: {results['failed']}")
                if results['errors']:
                    print("\nErrors:")
                    for error in results['errors']:
                        print(f"  {error['district_id']}: {error['error']}")
        else:
            parser.print_help()
