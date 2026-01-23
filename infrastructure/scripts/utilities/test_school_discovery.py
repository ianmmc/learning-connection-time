#!/usr/bin/env python3
"""
Test School-Level Discovery on Candidates

Tests the scraper service's /discover endpoint on school-level discovery
candidates identified from the swarm run.
"""

import json
import sys
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Add database modules to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "database"))

from connection import session_scope
from enrichment_tracking import log_attempt

SCRAPER_URL = "http://localhost:3000/discover"

# Test candidates (diverse size range)
TEST_CANDIDATES = [
    {
        'nces_id': '633600',
        'name': 'Roseville City Elementary',
        'state': 'CA',
        'url': 'https://www.rcsdk8.org',
        'enrollment': 12004,
        'size_category': 'large',
        'notes': 'Schools listing page loaded but no bell schedule data found'
    },
    {
        'nces_id': '601488',
        'name': 'Palisades Charter High District',
        'state': 'CA',
        'url': 'https://www.palihigh.org/',
        'enrollment': 2991,
        'size_category': 'medium',
        'notes': 'Homepage loaded but bell schedule pages returned 404'
    },
    {
        'nces_id': '3003290',
        'name': 'Belgrade Elem',
        'state': 'MT',
        'url': 'https://www.bsd44.org',
        'enrollment': 2303,
        'size_category': 'small',
        'notes': 'Website accessible but bell schedule page not found'
    },
    {
        'nces_id': '3910023',
        'name': 'Van Wert City',
        'state': 'OH',
        'url': 'https://www.vanwertschools.org',  # Assuming URL based on district name
        'enrollment': 2038,
        'size_category': 'small',
        'notes': 'Website found but no bell schedule on accessible pages'
    },
    {
        'nces_id': '3000655',
        'name': 'East Helena K-12',
        'state': 'MT',
        'url': 'https://www.ehps.k12.mt.us',
        'enrollment': 1915,
        'size_category': 'small',
        'notes': 'Website accessible but bell schedule information not found in HTML'
    },
]


def test_discovery(district: Dict) -> Dict:
    """Test school-level discovery for a district"""
    print(f"\n{'='*70}")
    print(f"Testing: {district['name']} ({district['state']})")
    print(f"NCES ID: {district['nces_id']}")
    print(f"URL: {district['url']}")
    print(f"Enrollment: {district['enrollment']:,} ({district['size_category']})")
    print(f"Previous result: {district['notes']}")
    print(f"{'='*70}\n")

    try:
        # Call discovery endpoint
        payload = {
            'districtUrl': district['url'],
            'state': district['state'],
            'representativeOnly': True  # Just get one representative school
        }

        print(f"Calling discovery endpoint...")
        response = requests.post(SCRAPER_URL, json=payload, timeout=120)

        if response.status_code != 200:
            print(f"❌ Discovery failed with status {response.status_code}")
            result = {
                'success': False,
                'error': f"HTTP {response.status_code}",
                'response': response.text
            }
        else:
            result = response.json()
            print(f"✅ Discovery completed")

            # Print summary
            if result.get('success'):
                schools_found = len(result.get('schools', []))
                print(f"   Schools discovered: {schools_found}")

                if result.get('representative'):
                    rep = result['representative']
                    print(f"\n   Representative school:")
                    print(f"     - Name: {rep.get('name', 'Unknown')}")
                    print(f"     - URL: {rep.get('url', 'Unknown')}")
                    print(f"     - Pattern: {rep.get('pattern', 'Unknown')}")

                    if rep.get('bellSchedule'):
                        print(f"     - ✅ Bell schedule found!")
                    else:
                        print(f"     - ⚠️  No bell schedule on school site")
            else:
                print(f"   Error: {result.get('error', 'Unknown error')}")

        return result

    except requests.exceptions.Timeout:
        print(f"❌ Discovery timeout (120s)")
        return {
            'success': False,
            'error': 'timeout',
            'timeout': True
        }
    except Exception as e:
        print(f"❌ Discovery error: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def log_result(district: Dict, result: Dict):
    """Log discovery result to database"""
    try:
        with session_scope() as session:
            # Convert discovery result to scraper response format
            scraper_response = {
                'success': result.get('success', False),
                'blocked': result.get('blocked', False),
                'url': district['url'],
                'errorCode': result.get('error') if not result.get('success') else None,
                'error': result.get('error'),
                'timing': 0,  # Not tracked
                'discovery_metadata': {
                    'schools_found': len(result.get('schools', [])),
                    'representative': result.get('representative'),
                    'method': 'school_level_discovery',
                    'test_date': datetime.utcnow().isoformat(),
                    'source': 'school_discovery_test'
                }
            }

            log_attempt(
                session=session,
                district_id=district['nces_id'],
                url=district['url'],
                response=scraper_response,
                enrichment_tier='tier2',
                scraper_version='discovery_1.0',
                notes=f"School-level discovery test - {result.get('error', 'tested')}"
            )

            print(f"   Logged to database")

    except Exception as e:
        print(f"   ⚠️  Failed to log to database: {e}")


def main():
    """Main test runner"""
    print("="*70)
    print("School-Level Discovery Test")
    print("="*70)
    print(f"Testing {len(TEST_CANDIDATES)} candidates from swarm run")
    print(f"Scraper endpoint: {SCRAPER_URL}")
    print()

    results = []

    for district in TEST_CANDIDATES:
        result = test_discovery(district)
        results.append({
            'district': district,
            'result': result
        })

        # Log to database
        log_result(district, result)

        # Brief pause between requests
        import time
        time.sleep(2)

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}\n")

    success_count = sum(1 for r in results if r['result'].get('success'))
    schools_found_count = sum(1 for r in results if r['result'].get('success') and len(r['result'].get('schools', [])) > 0)
    bell_schedule_count = sum(1 for r in results if r['result'].get('representative', {}).get('bellSchedule'))

    print(f"Districts tested: {len(results)}")
    print(f"Discovery successful: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")
    print(f"Schools found: {schools_found_count}/{len(results)} ({schools_found_count/len(results)*100:.1f}%)")
    print(f"Bell schedules found: {bell_schedule_count}/{len(results)} ({bell_schedule_count/len(results)*100:.1f}%)")

    print(f"\n{'='*70}\n")

    # Save detailed results
    output_file = Path(__file__).parent.parent.parent.parent / "data" / "enriched" / "bell-schedules" / f"school_discovery_test_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.utcnow().isoformat(),
            'test_type': 'school_level_discovery',
            'summary': {
                'tested': len(results),
                'successful': success_count,
                'schools_found': schools_found_count,
                'bell_schedules_found': bell_schedule_count
            },
            'results': results
        }, f, indent=2)

    print(f"Detailed results saved to: {output_file}")


if __name__ == '__main__':
    main()
