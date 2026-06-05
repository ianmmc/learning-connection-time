#!/usr/bin/env python3
"""
pipeline_verify_enrichment.py - Verify database import matches source data

PURPOSE:
    Verifies that bell schedule records in the database match the data from
    enrichment_ready.json. This is the final quality check in the pipeline.

CONTEXT - ENRICHMENT PIPELINE POSITION:
    This script is Step 5 of 5 in the Phase 8 Enrichment Pipeline:
    1. Ollama extraction (POST /enrich/extract) → extraction_result.json
    2. Claude verification → verified_extraction.json
    3. calculate_minutes.py → enrichment_ready.json
    4. import_bell_schedules.py → database + import_result.json
    5. verify_enrichment.py → verification_report.json  <-- THIS SCRIPT

    This script handles step 5: Post-import verification to ensure data integrity.

INPUT:
    - File: data/raw/bell_schedule_pdfs/{state}/{district}/enrichment_ready.json
    - File: data/raw/bell_schedule_pdfs/{state}/{district}/import_result.json
    - Database: bell_schedules table

OUTPUT:
    - File: data/raw/bell_schedule_pdfs/{state}/{district}/verification_report.json
    - Schema: {verified, mismatches, missing, extra}

VERIFICATION CHECKS:
    1. All schedules in enrichment_ready.json exist in database
    2. instructional_minutes matches exactly
    3. start_time/end_time match
    4. source_urls populated correctly
    5. No orphaned records (in DB but not in source)

USAGE:
    python infrastructure/scripts/enrich/pipeline_verify_enrichment.py \\
        --district 1200390

    # Verbose output with all record details:
    python infrastructure/scripts/enrich/pipeline_verify_enrichment.py \\
        --district 1200390 --verbose

DEPENDENCIES:
    - sqlalchemy
    - infrastructure.database.connection
    - infrastructure.database.models

SEE ALSO:
    - Plan: ~/.claude/plans/crispy-brewing-blanket.md (Phase 8)
    - Related: import_bell_schedules.py (step 4)
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


def get_db_records(session, district_id: str) -> Dict[str, Any]:
    """
    Get all bell schedule records for a district from the database.

    Args:
        session: SQLAlchemy session
        district_id: NCES district ID

    Returns:
        Dict mapping (year, grade_level) to record data
    """
    from infrastructure.database.models import BellSchedule

    records = session.query(BellSchedule).filter_by(district_id=district_id).all()

    result = {}
    for record in records:
        key = (record.year, record.grade_level)
        result[key] = {
            'id': record.id,
            'district_id': record.district_id,
            'year': record.year,
            'grade_level': record.grade_level,
            'instructional_minutes': record.instructional_minutes,
            'start_time': record.start_time,
            'end_time': record.end_time,
            'confidence': record.confidence,
            'method': record.method,
            'source_urls': record.source_urls or [],
            'schools_sampled': record.schools_sampled or [],
            'created_at': record.created_at.isoformat() if record.created_at else None,
        }

    return result


def verify_record(expected: Dict[str, Any], actual: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify a single record matches expected values.

    Args:
        expected: Expected data from enrichment_ready.json
        actual: Actual data from database

    Returns:
        Verification result with any mismatches
    """
    mismatches = []

    # Check instructional_minutes (must match exactly)
    expected_mins = expected.get('instructional_minutes')
    actual_mins = actual.get('instructional_minutes')
    if expected_mins != actual_mins:
        mismatches.append({
            'field': 'instructional_minutes',
            'expected': expected_mins,
            'actual': actual_mins,
        })

    # Check start_time (optional but should match if present)
    expected_start = expected.get('start_time')
    actual_start = actual.get('start_time')
    if expected_start and actual_start and expected_start != actual_start:
        mismatches.append({
            'field': 'start_time',
            'expected': expected_start,
            'actual': actual_start,
        })

    # Check end_time (optional but should match if present)
    expected_end = expected.get('end_time')
    actual_end = actual.get('end_time')
    if expected_end and actual_end and expected_end != actual_end:
        mismatches.append({
            'field': 'end_time',
            'expected': expected_end,
            'actual': actual_end,
        })

    # Check source_urls (should contain expected URL)
    expected_url = expected.get('source_url')
    actual_urls = actual.get('source_urls', [])
    if expected_url and expected_url not in actual_urls:
        mismatches.append({
            'field': 'source_urls',
            'expected': expected_url,
            'actual': actual_urls,
        })

    return {
        'verified': len(mismatches) == 0,
        'mismatches': mismatches,
        'db_id': actual.get('id'),
    }


def verify_enrichment(
    enrichment_data: Dict[str, Any],
    db_records: Dict[tuple, Dict[str, Any]],
    import_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Verify enrichment data against database records.

    Args:
        enrichment_data: Data from enrichment_ready.json
        db_records: Records from database
        import_result: Optional import_result.json data

    Returns:
        Verification report
    """
    district_id = enrichment_data.get('district_id')
    year = enrichment_data.get('schedules', [{}])[0].get('year', '2025-26')

    report = {
        'district_id': district_id,
        'verification_date': datetime.utcnow().isoformat(),
        'overall_verified': True,
        'total_expected': 0,
        'total_verified': 0,
        'total_mismatched': 0,
        'total_missing': 0,
        'total_extra': 0,
        'verified_records': [],
        'mismatched_records': [],
        'missing_records': [],
        'extra_records': [],
    }

    # Track which DB records we've seen
    seen_keys = set()

    for schedule in enrichment_data.get('schedules', []):
        report['total_expected'] += 1

        grade_level = schedule.get('grade_level')
        schedule_year = schedule.get('year', year)
        key = (schedule_year, grade_level)

        if key not in db_records:
            report['total_missing'] += 1
            report['missing_records'].append({
                'grade_level': grade_level,
                'year': schedule_year,
                'expected_minutes': schedule.get('instructional_minutes'),
            })
            report['overall_verified'] = False
            continue

        seen_keys.add(key)
        db_record = db_records[key]

        verification = verify_record(schedule, db_record)

        if verification['verified']:
            report['total_verified'] += 1
            report['verified_records'].append({
                'grade_level': grade_level,
                'year': schedule_year,
                'instructional_minutes': schedule.get('instructional_minutes'),
                'db_id': verification['db_id'],
            })
        else:
            report['total_mismatched'] += 1
            report['mismatched_records'].append({
                'grade_level': grade_level,
                'year': schedule_year,
                'mismatches': verification['mismatches'],
                'db_id': verification['db_id'],
            })
            report['overall_verified'] = False

    # Check for extra records in DB not in source
    for key, db_record in db_records.items():
        if key not in seen_keys:
            report['total_extra'] += 1
            report['extra_records'].append({
                'grade_level': key[1],
                'year': key[0],
                'instructional_minutes': db_record.get('instructional_minutes'),
                'db_id': db_record.get('id'),
                'note': 'Record exists in database but not in enrichment source',
            })
            # Extra records don't necessarily fail verification
            # as they might be from previous imports

    # Add import result cross-reference if available
    if import_result:
        report['import_result_summary'] = {
            'records_created': import_result.get('records_created', 0),
            'records_skipped': import_result.get('records_skipped', 0),
            'records_with_errors': import_result.get('records_with_errors', 0),
        }

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Verify database import matches enrichment source data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify by district ID:
  python pipeline_verify_enrichment.py --district 1200390

  # Verbose output:
  python pipeline_verify_enrichment.py --district 1200390 --verbose
        """
    )

    parser.add_argument(
        "--district", "-d",
        required=True,
        help="District ID to verify"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed record information"
    )

    args = parser.parse_args()

    # Find district directory
    district_dir = find_district_dir(args.district)
    if not district_dir:
        logger.error(f"District directory not found for {args.district}")
        sys.exit(1)

    # Read enrichment_ready.json (or fallback)
    enrichment_path = district_dir / "enrichment_ready.json"
    if not enrichment_path.exists():
        enrichment_path = district_dir / "verified_extraction.json"
    if not enrichment_path.exists():
        enrichment_path = district_dir / "extraction_result.json"

    if not enrichment_path.exists():
        logger.error(f"No enrichment file found in {district_dir}")
        sys.exit(1)

    logger.info(f"Reading: {enrichment_path}")
    with open(enrichment_path) as f:
        enrichment_data = json.load(f)

    # Read import_result.json if exists
    import_result = None
    import_path = district_dir / "import_result.json"
    if import_path.exists():
        with open(import_path) as f:
            import_result = json.load(f)

    # Get database records
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        logger.info(f"Querying database for district {args.district}")
        db_records = get_db_records(session, args.district)

    logger.info(f"Found {len(db_records)} records in database")

    # Run verification
    report = verify_enrichment(enrichment_data, db_records, import_result)

    # Output results
    if report['overall_verified']:
        logger.info("VERIFICATION PASSED")
    else:
        logger.warning("VERIFICATION FAILED")

    logger.info(f"Expected: {report['total_expected']} records")
    logger.info(f"Verified: {report['total_verified']} records")
    logger.info(f"Mismatched: {report['total_mismatched']} records")
    logger.info(f"Missing: {report['total_missing']} records")
    logger.info(f"Extra (in DB only): {report['total_extra']} records")

    if args.verbose:
        if report['verified_records']:
            logger.info("\nVerified records:")
            for rec in report['verified_records']:
                logger.info(f"  {rec['grade_level']}: {rec['instructional_minutes']} min (DB ID: {rec['db_id']})")

        if report['mismatched_records']:
            logger.warning("\nMismatched records:")
            for rec in report['mismatched_records']:
                logger.warning(f"  {rec['grade_level']}:")
                for mismatch in rec['mismatches']:
                    logger.warning(f"    {mismatch['field']}: expected {mismatch['expected']}, got {mismatch['actual']}")

        if report['missing_records']:
            logger.warning("\nMissing records (not in DB):")
            for rec in report['missing_records']:
                logger.warning(f"  {rec['grade_level']}: expected {rec['expected_minutes']} min")

        if report['extra_records']:
            logger.info("\nExtra records (in DB, not in source):")
            for rec in report['extra_records']:
                logger.info(f"  {rec['grade_level']}: {rec['instructional_minutes']} min (DB ID: {rec['db_id']})")

    # Save report
    output_path = district_dir / "verification_report.json"
    logger.info(f"Writing: {output_path}")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    if report['overall_verified']:
        logger.info("Verification completed successfully!")
    else:
        logger.warning("Verification completed with issues - review verification_report.json")
        sys.exit(1)


if __name__ == "__main__":
    main()
