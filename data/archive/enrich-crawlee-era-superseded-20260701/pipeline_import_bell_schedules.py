#!/usr/bin/env python3
"""
pipeline_import_bell_schedules.py - Import enrichment_ready.json to database

PURPOSE:
    Reads enrichment_ready.json and imports validated bell schedule records
    to the database. This script handles all database quirks and constraints.

CONTEXT - ENRICHMENT PIPELINE POSITION:
    This script is Step 4 of 5 in the Phase 8 Enrichment Pipeline:
    1. Ollama extraction (POST /enrich/extract) → extraction_result.json
    2. Claude verification → verified_extraction.json
    3. calculate_minutes.py → enrichment_ready.json
    4. import_bell_schedules.py → database + import_result.json  <-- THIS SCRIPT
    5. verify_enrichment.py → verification_report.json

    This script handles step 4: Database import with validation and quirk handling.

INPUT:
    - File: data/raw/bell_schedule_pdfs/{state}/{district}/enrichment_ready.json
    - Schema: extraction_result with instructional_minutes calculated
    - Source: calculate_minutes.py (step 3)

OUTPUT:
    - File: data/raw/bell_schedule_pdfs/{state}/{district}/import_result.json
    - Schema: {records_created, records_skipped, errors}
    - Consumed by: verify_enrichment.py (step 5)

DATABASE QUIRKS (CRITICAL - READ CAREFULLY):
    1. BellSchedule uses 'year' NOT 'school_year'
    2. JSONB fields (source_urls, schools_sampled) must be set AFTER object creation:
        bs = BellSchedule(district_id=..., ...)  # Create without JSONB
        bs.source_urls = ["url"]                 # Then set JSONB fields
        bs.schools_sampled = ["School"]
        session.add(bs)
    3. Valid methods: 'automated_enrichment', 'human_provided', 'statutory_fallback'
       - Use 'automated_enrichment' for pipeline imports
    4. Valid confidence: 'high', 'medium', 'low'
    5. Valid grade_levels: 'elementary', 'middle', 'high'
    6. instructional_minutes must be between 100 and 600
    7. UniqueConstraint on (district_id, year, grade_level) - duplicates will fail
    8. Always check for existing records before insert

USAGE:
    python infrastructure/scripts/enrich/pipeline_import_bell_schedules.py \\
        --input data/raw/bell_schedule_pdfs/FL/1200390_Pasco_County/enrichment_ready.json

    # Or process by district ID (auto-find directory):
    python infrastructure/scripts/enrich/pipeline_import_bell_schedules.py \\
        --district 1200390

    # Dry run (validate without inserting):
    python infrastructure/scripts/enrich/pipeline_import_bell_schedules.py \\
        --district 1200390 --dry-run

DEPENDENCIES:
    - sqlalchemy
    - infrastructure.database.connection
    - infrastructure.database.models

SEE ALSO:
    - Plan: ~/.claude/plans/crispy-brewing-blanket.md (Phase 8)
    - Related: calculate_minutes.py (step 3), verify_enrichment.py (step 5)
    - Model: infrastructure/database/models.py (BellSchedule class)
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Base directory for bell schedule PDFs
PDF_BASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "bell_schedule_pdfs"

# Valid values for constrained fields
VALID_METHODS = ['automated_enrichment', 'human_provided', 'statutory_fallback']
VALID_CONFIDENCE = ['high', 'medium', 'low']
VALID_GRADE_LEVELS = ['elementary', 'middle', 'high']

# Default year for new imports
DEFAULT_YEAR = '2025-26'


def find_district_dir(district_id: str) -> Optional[Path]:
    """
    Find the district directory by ID prefix.

    Args:
        district_id: NCES district ID

    Returns:
        Path to district directory or None if not found
    """
    for state_dir in PDF_BASE_DIR.iterdir():
        if not state_dir.is_dir():
            continue
        for district_dir in state_dir.iterdir():
            if district_dir.is_dir() and district_dir.name.startswith(district_id):
                return district_dir
    return None


def validate_schedule(schedule: Dict[str, Any], district_id: str) -> Dict[str, Any]:
    """
    Validate and normalize a schedule entry before import.

    Args:
        schedule: Schedule data from enrichment_ready.json
        district_id: NCES district ID

    Returns:
        Dict with validation results:
            - valid: bool
            - normalized: normalized schedule dict (if valid)
            - errors: list of validation errors
    """
    errors = []
    normalized = {}

    # Required fields
    if not schedule.get('instructional_minutes'):
        errors.append("Missing instructional_minutes")
    else:
        minutes = schedule['instructional_minutes']
        if not isinstance(minutes, int):
            try:
                minutes = int(minutes)
            except (ValueError, TypeError):
                errors.append(f"Invalid instructional_minutes: {minutes}")
                minutes = None

        if minutes is not None:
            if not (100 <= minutes <= 600):
                errors.append(f"instructional_minutes ({minutes}) outside valid range (100-600)")
            else:
                normalized['instructional_minutes'] = minutes

    # Grade level
    grade_level = schedule.get('grade_level', '').lower()
    if grade_level not in VALID_GRADE_LEVELS:
        errors.append(f"Invalid grade_level: {grade_level} (must be one of {VALID_GRADE_LEVELS})")
    else:
        normalized['grade_level'] = grade_level

    # Times (optional but recommended)
    normalized['start_time'] = schedule.get('start_time')
    normalized['end_time'] = schedule.get('end_time')

    # Confidence
    confidence = schedule.get('confidence', 'medium').lower()
    if confidence not in VALID_CONFIDENCE:
        confidence = 'medium'
    normalized['confidence'] = confidence

    # Year
    normalized['year'] = schedule.get('year', DEFAULT_YEAR)

    # Source info
    normalized['source_url'] = schedule.get('source_url')
    normalized['school_name'] = schedule.get('school_name')
    normalized['notes'] = schedule.get('notes', '')

    # District ID
    normalized['district_id'] = district_id

    return {
        'valid': len(errors) == 0,
        'normalized': normalized if len(errors) == 0 else None,
        'errors': errors,
    }


def check_existing(session, district_id: str, year: str, grade_level: str) -> bool:
    """
    Check if a bell schedule record already exists.

    Args:
        session: SQLAlchemy session
        district_id: NCES district ID
        year: School year
        grade_level: Grade level

    Returns:
        True if record exists, False otherwise
    """
    from infrastructure.database.models import BellSchedule

    existing = session.query(BellSchedule).filter_by(
        district_id=district_id,
        year=year,
        grade_level=grade_level,
    ).first()

    return existing is not None


def import_schedule(session, schedule: Dict[str, Any], source_file: str) -> Dict[str, Any]:
    """
    Import a single schedule to the database.

    CRITICAL: JSONB fields must be set AFTER object creation.

    Args:
        session: SQLAlchemy session
        schedule: Validated schedule data
        source_file: Source filename for tracking

    Returns:
        Dict with import result
    """
    from infrastructure.database.models import BellSchedule

    district_id = schedule['district_id']
    year = schedule['year']
    grade_level = schedule['grade_level']

    # Check for existing record
    if check_existing(session, district_id, year, grade_level):
        return {
            'status': 'skipped',
            'reason': 'duplicate',
            'message': f"Record already exists for {district_id}/{year}/{grade_level}",
        }

    try:
        # Create BellSchedule object WITHOUT JSONB fields
        bs = BellSchedule(
            district_id=district_id,
            year=year,
            grade_level=grade_level,
            instructional_minutes=schedule['instructional_minutes'],
            start_time=schedule.get('start_time'),
            end_time=schedule.get('end_time'),
            confidence=schedule.get('confidence', 'medium'),
            method='automated_enrichment',
            source_description=f"Phase 8 pipeline import from {source_file}",
            notes=schedule.get('notes', ''),
        )

        # CRITICAL: Set JSONB fields AFTER creation
        source_url = schedule.get('source_url')
        if source_url:
            bs.source_urls = [source_url]

        school_name = schedule.get('school_name')
        if school_name:
            bs.schools_sampled = [school_name]

        session.add(bs)

        return {
            'status': 'created',
            'id': None,  # Will be set after commit
            'grade_level': grade_level,
            'instructional_minutes': schedule['instructional_minutes'],
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
        }


def process_import(
    input_data: Dict[str, Any],
    session,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Process enrichment_ready.json and import schedules to database.

    Args:
        input_data: Data from enrichment_ready.json
        session: SQLAlchemy session
        dry_run: If True, validate but don't commit

    Returns:
        Import result summary
    """
    district_id = input_data.get('district_id')
    if not district_id:
        return {
            'success': False,
            'error': 'Missing district_id in input file',
        }

    results = {
        'district_id': district_id,
        'import_date': datetime.utcnow().isoformat(),
        'dry_run': dry_run,
        'records_processed': 0,
        'records_created': 0,
        'records_skipped': 0,
        'records_with_errors': 0,
        'details': [],
    }

    schedules = input_data.get('schedules', [])

    # Deduplicate by grade level - keep highest confidence record for each
    # The unique constraint is (district_id, year, grade_level)
    confidence_priority = {'high': 0, 'medium': 1, 'low': 2}
    deduped_schedules = {}
    for schedule in schedules:
        grade = schedule.get('grade_level', '').lower()
        if grade not in VALID_GRADE_LEVELS:
            continue  # Will be caught by validation later
        conf = schedule.get('confidence', 'medium')
        conf_rank = confidence_priority.get(conf, 1)

        if grade not in deduped_schedules:
            deduped_schedules[grade] = schedule
        else:
            existing_conf = deduped_schedules[grade].get('confidence', 'medium')
            existing_rank = confidence_priority.get(existing_conf, 1)
            if conf_rank < existing_rank:
                # Higher confidence (lower rank) wins
                logger.info(f"  Dedup: Replacing {grade} ({existing_conf}) with ({conf})")
                deduped_schedules[grade] = schedule

    schedules = list(deduped_schedules.values())
    logger.info(f"  After deduplication: {len(schedules)} schedules for {len(deduped_schedules)} grade levels")

    for schedule in schedules:
        results['records_processed'] += 1

        # Validate
        validation = validate_schedule(schedule, district_id)

        if not validation['valid']:
            results['records_with_errors'] += 1
            results['details'].append({
                'grade_level': schedule.get('grade_level', 'unknown'),
                'status': 'validation_error',
                'errors': validation['errors'],
            })
            continue

        normalized = validation['normalized']

        if dry_run:
            # Check for duplicates even in dry run
            if check_existing(session, district_id, normalized['year'], normalized['grade_level']):
                results['records_skipped'] += 1
                results['details'].append({
                    'grade_level': normalized['grade_level'],
                    'status': 'would_skip',
                    'reason': 'duplicate',
                })
            else:
                results['records_created'] += 1
                results['details'].append({
                    'grade_level': normalized['grade_level'],
                    'status': 'would_create',
                    'instructional_minutes': normalized['instructional_minutes'],
                })
        else:
            # Actually import
            source_file = input_data.get('source_file', 'enrichment_ready.json')
            import_result = import_schedule(session, normalized, source_file)

            if import_result['status'] == 'created':
                results['records_created'] += 1
            elif import_result['status'] == 'skipped':
                results['records_skipped'] += 1
            else:
                results['records_with_errors'] += 1

            results['details'].append({
                'grade_level': normalized['grade_level'],
                **import_result,
            })

    # Commit if not dry run
    if not dry_run and results['records_created'] > 0:
        try:
            session.commit()
            results['committed'] = True
        except Exception as e:
            session.rollback()
            results['committed'] = False
            results['commit_error'] = str(e)
            logger.error(f"Commit failed: {e}")

    results['success'] = results['records_with_errors'] == 0

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Import enrichment_ready.json to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process specific file:
  python pipeline_import_bell_schedules.py --input enrichment_ready.json

  # Process by district ID (auto-find directory):
  python pipeline_import_bell_schedules.py --district 1200390

  # Dry run (validate without inserting):
  python pipeline_import_bell_schedules.py --district 1200390 --dry-run
        """
    )

    parser.add_argument(
        "--input", "-i",
        type=Path,
        help="Input file (enrichment_ready.json)"
    )
    parser.add_argument(
        "--district", "-d",
        help="District ID (auto-find directory and use default filenames)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without inserting to database"
    )

    args = parser.parse_args()

    # Determine input path
    if args.district:
        district_dir = find_district_dir(args.district)
        if not district_dir:
            logger.error(f"District directory not found for {args.district}")
            sys.exit(1)

        input_path = district_dir / "enrichment_ready.json"

        # Fall back to verified_extraction.json if enrichment_ready doesn't exist
        if not input_path.exists():
            fallback = district_dir / "verified_extraction.json"
            if fallback.exists():
                logger.warning(f"enrichment_ready.json not found, using {fallback.name}")
                input_path = fallback
            else:
                logger.error(f"No enrichment file found in {district_dir}")
                sys.exit(1)
    else:
        if not args.input:
            parser.error("Either --district or --input is required")
        input_path = args.input
        district_dir = input_path.parent

    # Read input
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    logger.info(f"Reading: {input_path}")
    with open(input_path) as f:
        input_data = json.load(f)

    # Import
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        logger.info(f"Processing import (dry_run={args.dry_run})")
        results = process_import(input_data, session, args.dry_run)

    # Report summary
    logger.info(f"Processed: {results['records_processed']} schedules")
    logger.info(f"Created: {results['records_created']}")
    logger.info(f"Skipped: {results['records_skipped']}")
    logger.info(f"Errors: {results['records_with_errors']}")

    if results.get('commit_error'):
        logger.error(f"Commit error: {results['commit_error']}")

    # Show details
    for detail in results.get('details', []):
        grade = detail.get('grade_level', 'unknown')
        status = detail.get('status', 'unknown')
        if detail.get('errors'):
            logger.warning(f"  {grade}: {status} - {detail['errors']}")
        elif detail.get('instructional_minutes'):
            logger.info(f"  {grade}: {status} ({detail['instructional_minutes']} min)")
        else:
            logger.info(f"  {grade}: {status}")

    # Save results
    output_path = district_dir / "import_result.json"
    logger.info(f"Writing: {output_path}")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    if results['success']:
        logger.info("Import completed successfully!")
    else:
        logger.warning("Import completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
