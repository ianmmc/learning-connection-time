#!/usr/bin/env python3
"""
Enrichment Verification CLI

Run this script to verify enrichment claims against database reality.
Added after 'The Case of the Missing Bell Schedules' investigation (Jan 24, 2026).

Usage:
    # Full verification report
    python verify_enrichment.py

    # Quick count check
    python verify_enrichment.py --quick

    # Check specific date range
    python verify_enrichment.py --date-range 2025-12-25 2025-12-27

    # Validate a handoff document claim
    python verify_enrichment.py --validate-claim 192

    # JSON output for CI/CD
    python verify_enrichment.py --json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from infrastructure.database.connection import session_scope
from infrastructure.database.verification import (
    generate_handoff_report,
    check_audit_integrity,
    detect_count_discrepancy,
    validate_date_range,
    find_lineage_gaps
)
from infrastructure.database.queries import get_enrichment_summary


def main():
    parser = argparse.ArgumentParser(
        description='Verify enrichment claims against database'
    )
    parser.add_argument(
        '--quick', action='store_true',
        help='Quick count check only'
    )
    parser.add_argument(
        '--date-range', nargs=2, metavar=('START', 'END'),
        help='Check records in date range (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--validate-claim', type=int, metavar='COUNT',
        help='Validate a specific enrichment count claim'
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Output as JSON'
    )
    parser.add_argument(
        '--year', default='2024-25',
        help='School year to verify (default: 2024-25)'
    )

    args = parser.parse_args()

    with session_scope() as session:
        if args.quick:
            run_quick_check(session, args)
        elif args.date_range:
            run_date_range_check(session, args)
        elif args.validate_claim:
            run_claim_validation(session, args)
        else:
            run_full_verification(session, args)


def run_quick_check(session, args):
    """Quick count verification"""
    summary = get_enrichment_summary(session, args.year)

    if args.json:
        print(json.dumps({
            'year': args.year,
            'enriched_districts': summary['enriched_districts'],
            'schedule_records': summary['schedule_records'],
            'states': summary['states_represented'],
            'verified_at': datetime.utcnow().isoformat()
        }, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print("QUICK ENRICHMENT VERIFICATION")
        print(f"{'=' * 60}")
        print(f"\nYear: {args.year}")
        print(f"Enriched districts: {summary['enriched_districts']}")
        print(f"Bell schedule records: {summary['schedule_records']}")
        print(f"States represented: {summary['states_represented']}")
        print(f"\nVerified at: {datetime.utcnow().isoformat()}")
        print(f"{'=' * 60}\n")


def run_date_range_check(session, args):
    """Check records in date range"""
    start = datetime.strptime(args.date_range[0], '%Y-%m-%d')
    end = datetime.strptime(args.date_range[1], '%Y-%m-%d')

    result = validate_date_range(session, start, end)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print(f"DATE RANGE CHECK: {args.date_range[0]} to {args.date_range[1]}")
        print(f"{'=' * 60}")

        print("\nDaily record counts:")
        for date, count in sorted(result['daily_counts'].items()):
            status = "OK" if count > 0 else "GAP!"
            print(f"  {date}: {count:4d} records  [{status}]")

        if result['gap_dates']:
            print(f"\nWARNING: {len(result['gap_dates'])} dates with zero records!")
            print("Gap dates:", ', '.join(result['gap_dates']))

        print(f"\n{'=' * 60}\n")


def run_claim_validation(session, args):
    """Validate a specific count claim"""
    summary = get_enrichment_summary(session, args.year)
    actual = summary['enriched_districts']
    claimed = args.validate_claim

    result = detect_count_discrepancy(claimed, actual)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print("CLAIM VALIDATION")
        print(f"{'=' * 60}")
        print(f"\nClaimed count: {claimed}")
        print(f"Actual count:  {actual}")
        print(f"Difference:    {claimed - actual} ({result['discrepancy_percent']:.1f}%)")
        print(f"\nSeverity: {result['severity'].upper()}")
        print(f"Status: {'VALID' if not result['has_discrepancy'] else 'INVALID'}")

        if result['has_discrepancy']:
            print(f"\nWARNING: {result['message']}")

        print(f"\n{'=' * 60}\n")

        # Exit with error code if invalid
        if result.get('alert'):
            sys.exit(1)


def run_full_verification(session, args):
    """Full verification report"""
    report = generate_handoff_report(session)
    integrity = check_audit_integrity(session)
    gaps = find_lineage_gaps(session)

    if args.json:
        output = {
            'report': report,
            'integrity': integrity,
            'lineage_gaps': len(gaps),
            'verified_at': datetime.utcnow().isoformat()
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(f"\n{'=' * 60}")
        print("FULL ENRICHMENT VERIFICATION REPORT")
        print(f"{'=' * 60}")

        print(f"\nDatabase Snapshot: {report['verified_at']}")
        print(f"\nEnrichment Status:")
        print(f"  Enriched districts: {report['enriched_districts']}")
        print(f"  States with data: {report['states_with_enrichment']}")

        print(f"\nRecords by date (last 7):")
        for date, count in sorted(report['date_distribution'].items())[-7:]:
            print(f"  {date}: {count:4d} records")

        print(f"\nAudit Trail Integrity:")
        print(f"  Status: {integrity['integrity_status'].upper()}")
        print(f"  Completeness: {integrity['completeness_percent']:.1f}%")

        if integrity['violations']:
            print(f"\n  Violations:")
            for v in integrity['violations']:
                print(f"    - {v['type']}: {v['message']}")

        if gaps:
            print(f"\n  Lineage gaps: {len(gaps)} bell_schedules without audit trail")

        print(f"\n{'=' * 60}")
        print("VERIFICATION COMPLETE")
        print(f"{'=' * 60}\n")

        # Exit with error if violations
        if integrity['violations']:
            sys.exit(1)


if __name__ == '__main__':
    main()
