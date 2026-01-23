#!/usr/bin/env python3
"""
Import Swarm Results to Database

Imports bell schedule scraping attempts from the swarm run (Jan 21-22, 2026)
into the enrichment_attempts database table for tracking.

Usage:
    python import_swarm_results.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add database modules to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "database"))

from connection import session_scope
from enrichment_tracking import log_attempt


def map_status_to_db_format(status: str, error_code: str = None) -> tuple[str, str]:
    """
    Map swarm result status to database status format

    Returns:
        Tuple of (status, block_type) for database
    """
    status_lower = status.lower()

    # Map statuses
    if status_lower in ['success', 'successful']:
        return ('success', None)
    elif status_lower == 'blocked':
        return ('blocked', 'cloudflare')  # Default, may need refinement
    elif status_lower in ['timeout', 'timed_out']:
        return ('timeout', None)
    elif status_lower in ['not_found', '404']:
        return ('not_found', None)
    elif status_lower in ['failed', 'failure', 'dns_error', 'network_error']:
        return ('error', None)
    elif status_lower == 'homepage_loaded':
        # Homepage loaded but no bell schedule found
        return ('not_found', None)
    else:
        return ('error', None)


def import_ca_format(file_path: Path) -> List[Dict]:
    """Import CA-style results format"""
    with open(file_path) as f:
        data = json.load(f)

    attempts = []

    # Process all categories
    for category in ['high_enrollment', 'mean_enrollment', 'median_enrollment']:
        districts = data.get('districts_attempted', {}).get(category, [])
        for district in districts:
            status, block_type = map_status_to_db_format(
                district.get('status', 'error'),
                district.get('error')
            )

            # Use first URL tried as primary
            url = district.get('urls_tried', [''])[0] if district.get('urls_tried') else ''

            attempts.append({
                'district_id': district.get('id'),
                'district_name': district.get('name'),
                'url': url,
                'status': status,
                'block_type': block_type,
                'error_message': district.get('error') or district.get('notes'),
                'notes': district.get('notes'),
                'urls_tried': district.get('urls_tried', []),
                'enrollment': district.get('enrollment')
            })

    return attempts


def import_other_format(file_path: Path) -> List[Dict]:
    """Import TX-style results format (with 'details' array)"""
    with open(file_path) as f:
        data = json.load(f)

    attempts = []

    for district in data.get('details', []):
        status_raw = district.get('status', 'error')
        error_code = district.get('error_code')

        # Map blocked status
        if status_raw == 'blocked':
            status = 'blocked'
            block_type = 'cloudflare'  # Default assumption
        else:
            status, block_type = map_status_to_db_format(status_raw, error_code)

        attempts.append({
            'district_id': district.get('district_id'),
            'district_name': district.get('district_name'),
            'url': district.get('url', ''),
            'status': status,
            'block_type': block_type,
            'error_message': district.get('error_code') or district.get('notes'),
            'notes': district.get('notes'),
            'urls_tried': [district.get('url')] if district.get('url') else [],
            'enrollment': district.get('enrollment'),
            'stratum': district.get('stratum')
        })

    return attempts


def import_strata_format(file_path: Path) -> List[Dict]:
    """Import MT-style results format (with 'districts' dict of strata)"""
    with open(file_path) as f:
        data = json.load(f)

    attempts = []

    # Process all strata (minimum, mean, median, high_enrollment, etc.)
    districts_data = data.get('districts', {})
    for stratum, districts_list in districts_data.items():
        for district in districts_list:
            status_raw = district.get('status', 'error')
            error_type = district.get('error_type')

            # Map status
            if status_raw == 'blocked':
                status = 'blocked'
                block_type = 'cloudflare'
            elif status_raw == 'partial':
                # Partial success - homepage loaded but no schedule found
                status = 'not_found'
                block_type = None
            else:
                status, block_type = map_status_to_db_format(status_raw, error_type)

            # Use first URL attempted
            urls_attempted = district.get('urls_attempted', [])
            url = urls_attempted[0] if urls_attempted else ''

            attempts.append({
                'district_id': district.get('id'),
                'district_name': district.get('name'),
                'url': url,
                'status': status,
                'block_type': block_type,
                'error_message': district.get('error_type') or district.get('notes'),
                'notes': district.get('notes'),
                'urls_tried': urls_attempted,
                'enrollment': district.get('enrollment'),
                'stratum': stratum
            })

    return attempts


def import_extraction_format(file_path: Path) -> List[Dict]:
    """Import OH/VT-style results format (with success/failed/blocked arrays)"""
    with open(file_path) as f:
        data = json.load(f)

    attempts = []

    # Process successful extractions (OH uses successful_extractions, VT uses successful_districts)
    for district in data.get('successful_extractions', []) + data.get('successful_districts', []):
        # Get source URLs (VT format)
        source_urls = district.get('source_urls', [])
        url = source_urls[0] if source_urls else district.get('url', '')

        attempts.append({
            'district_id': district.get('district_id'),
            'district_name': district.get('name'),
            'url': url,
            'status': 'success',
            'block_type': None,
            'error_message': None,
            'notes': district.get('notes'),
            'urls_tried': source_urls if source_urls else ([url] if url else []),
            'enrollment': district.get('enrollment'),
            'stratum': district.get('tier')
        })

    # Process failed extractions (OH uses failed_districts, VT uses failed_districts)
    for district in data.get('failed_extractions', []) + data.get('failed_districts', []):
        error_type = district.get('error_type') or district.get('error', 'error')

        # Map status
        if error_type == 'blocked' or 'cloudflare' in str(error_type).lower() or 'blocked' in str(error_type).lower():
            status = 'blocked'
            block_type = 'cloudflare'
        elif 'timeout' in str(error_type).lower():
            status = 'timeout'
            block_type = None
        elif '404' in str(error_type) or 'not_found' in str(error_type).lower():
            status = 'not_found'
            block_type = None
        else:
            status, block_type = map_status_to_db_format('failed', error_type)

        # Get attempted URLs (VT format has 'attempts' array)
        urls_tried = district.get('attempts', [])
        url = urls_tried[0] if urls_tried else (district.get('url_attempted') or district.get('url', ''))

        attempts.append({
            'district_id': district.get('district_id'),
            'district_name': district.get('name'),
            'url': url,
            'status': status,
            'block_type': block_type,
            'error_message': error_type,
            'notes': district.get('notes'),
            'urls_tried': urls_tried if urls_tried else ([url] if url else []),
            'enrollment': district.get('enrollment'),
            'stratum': district.get('tier')
        })

    # Process blocked districts (VT format)
    for district in data.get('blocked_districts', []):
        # Get attempted URLs
        urls_tried = district.get('attempts', [])
        url = urls_tried[0] if urls_tried else (district.get('url_attempted') or district.get('url', ''))

        attempts.append({
            'district_id': district.get('district_id'),
            'district_name': district.get('name'),
            'url': url,
            'status': 'blocked',
            'block_type': 'cloudflare',
            'error_message': district.get('error', 'Security block detected'),
            'notes': district.get('notes'),
            'urls_tried': urls_tried if urls_tried else ([url] if url else []),
            'enrollment': district.get('enrollment'),
            'stratum': district.get('tier')
        })

    return attempts


def import_all_swarm_results():
    """Import all pilot results from swarm run"""

    results_dir = Path(__file__).parent.parent.parent.parent / "data" / "enriched" / "bell-schedules"
    pilot_files = list(results_dir.glob("pilot_*_results.json"))

    print(f"Found {len(pilot_files)} pilot results files")

    all_attempts = []

    for file_path in sorted(pilot_files):
        print(f"\nProcessing {file_path.name}...")

        try:
            # Detect format by checking file structure
            with open(file_path) as f:
                peek = json.load(f)

            if 'pilot_summary' in peek:
                # CA format
                attempts = import_ca_format(file_path)
            elif 'details' in peek:
                # TX format (with details array)
                attempts = import_other_format(file_path)
            elif 'districts' in peek and isinstance(peek['districts'], dict):
                # MT format (with districts dict of strata)
                attempts = import_strata_format(file_path)
            elif any(key in peek for key in ['successful_extractions', 'failed_extractions',
                                                       'successful_districts', 'failed_districts', 'blocked_districts']):
                # OH/VT format (with extraction/district arrays)
                attempts = import_extraction_format(file_path)
            else:
                print(f"  ⚠ Unknown format, skipping")
                continue

            print(f"  Extracted {len(attempts)} district attempts")
            all_attempts.extend(attempts)

        except Exception as e:
            print(f"  ❌ Error processing file: {e}")
            continue

    print(f"\n{'='*60}")
    print(f"Total attempts to import: {len(all_attempts)}")
    print(f"{'='*60}\n")

    # Import to database
    imported_count = 0
    skipped_count = 0
    error_count = 0

    with session_scope() as session:
        for attempt in all_attempts:
            district_id = attempt['district_id']

            if not district_id:
                print(f"  ⚠ Skipping - no district ID")
                skipped_count += 1
                continue

            try:
                # Create scraper response format
                scraper_response = {
                    'success': attempt['status'] == 'success',
                    'blocked': attempt['status'] == 'blocked',
                    'url': attempt['url'],
                    'errorCode': attempt['error_message'] if attempt['status'] != 'success' else None,
                    'error': attempt['error_message'],
                    'statusCode': 404 if attempt['status'] == 'not_found' else None,
                    'timing': 0,  # Not captured in swarm data
                    'swarm_metadata': {
                        'district_name': attempt['district_name'],
                        'enrollment': attempt.get('enrollment'),
                        'stratum': attempt.get('stratum'),
                        'urls_tried': attempt.get('urls_tried', []),
                        'notes': attempt.get('notes'),
                        'source': 'swarm_jan_2026'
                    }
                }

                # Log to database
                log_attempt(
                    session=session,
                    district_id=district_id,
                    url=attempt['url'] or 'unknown',
                    response=scraper_response,
                    enrichment_tier='tier2',  # Automated tier
                    scraper_version='swarm_1.0',
                    notes=f"Imported from swarm run Jan 2026 - {attempt.get('notes', '')}"
                )

                imported_count += 1

                if imported_count % 10 == 0:
                    print(f"  Imported {imported_count} attempts...")

            except Exception as e:
                print(f"  ❌ Error importing {district_id}: {e}")
                error_count += 1
                continue

    print(f"\n{'='*60}")
    print(f"Import Summary:")
    print(f"  ✅ Imported: {imported_count}")
    print(f"  ⚠ Skipped: {skipped_count}")
    print(f"  ❌ Errors: {error_count}")
    print(f"{'='*60}\n")

    return {
        'imported': imported_count,
        'skipped': skipped_count,
        'errors': error_count
    }


if __name__ == '__main__':
    print("=" * 60)
    print("Importing Swarm Results to Enrichment Attempts Database")
    print("=" * 60)
    print()

    try:
        result = import_all_swarm_results()

        if result['imported'] > 0:
            print("\n✅ Import completed successfully!")
            print(f"   {result['imported']} district attempts now tracked in database")
        else:
            print("\n⚠ No attempts were imported")

    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
