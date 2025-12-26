#!/usr/bin/env python3
"""
Example workflow demonstrating the new database-driven enrichment process.

This shows how to:
1. Query unenriched districts
2. Add bell schedules to the database
3. Export results to JSON

Author: Claude (AI Assistant)
Date: December 25, 2025
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.database.connection import session_scope
from infrastructure.database.queries import (
    get_unenriched_districts,
    add_bell_schedule,
    get_enrichment_summary,
    print_enrichment_report,
)


def main():
    """Demonstrate the enrichment workflow."""

    print("\n" + "="*60)
    print("DATABASE-DRIVEN ENRICHMENT WORKFLOW EXAMPLE")
    print("="*60)

    with session_scope() as session:
        # Step 1: Find unenriched districts
        print("\n📋 STEP 1: Find Unenriched Districts")
        print("-" * 60)

        print("\nQuerying database for unenriched districts with 50k+ enrollment...")
        unenriched = get_unenriched_districts(session, min_enrollment=50000, limit=10)

        print(f"\nFound {len(unenriched)} unenriched districts:")
        for i, district in enumerate(unenriched, 1):
            print(f"{i:2}. {district.nces_id} | {district.name:45} | {district.state} | {district.enrollment:>7,} students")

        # Step 2: Example of adding a bell schedule
        print("\n\n📝 STEP 2: Add Bell Schedule (Example)")
        print("-" * 60)

        if unenriched:
            example_district = unenriched[0]
            print(f"\nExample: Adding elementary schedule for {example_district.name}")
            print(f"District ID: {example_district.nces_id}")
            print(f"State: {example_district.state}")
            print(f"Enrollment: {example_district.enrollment:,}")

            print("\nCode to add schedule:")
            print("""
add_bell_schedule(
    session,
    district_id="{district_id}",
    year="2024-25",
    grade_level="elementary",
    instructional_minutes=360,
    start_time="8:00 AM",
    end_time="3:00 PM",
    lunch_duration=30,
    passing_periods=15,
    method="human_provided",
    confidence="high",
    schools_sampled=["Example Elementary School"],
    source_urls=["https://example.com/bell-schedule.pdf"],
    notes="Example schedule - collected from district website"
)
session.commit()
""".format(district_id=example_district.nces_id))

            print("\n⚠️  Not actually adding schedule (this is a demonstration)")

        # Step 3: Show current enrichment status
        print("\n\n📊 STEP 3: Current Enrichment Status")
        print("-" * 60)

        summary = get_enrichment_summary(session)
        print(f"\nTotal districts: {summary['total_districts']:,}")
        print(f"Enriched districts: {summary['enriched_districts']}")
        print(f"Enrichment rate: {summary['enrichment_rate']:.2%}")
        print(f"Schedule records: {summary['schedule_records']}")
        print(f"States represented: {summary['states_represented']}")

        print("\n\nCollection methods breakdown:")
        for method, count in sorted(summary['by_method'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {method:25} {count:>4} schedules")

        # Step 4: Show how to export
        print("\n\n💾 STEP 4: Export to JSON")
        print("-" * 60)

        print("\nTo export current database to JSON format:")
        print("  python infrastructure/database/export_json.py")
        print("\nTo export with reference CSV:")
        print("  python infrastructure/database/export_json.py --include-reference-csv")
        print("\nTo export individual files:")
        print("  python infrastructure/database/export_json.py --individual-files")

    # Step 5: Query examples
    print("\n\n🔍 STEP 5: Useful Query Examples")
    print("-" * 60)

    print("""
# Get a specific district
from infrastructure.database.queries import get_district_by_id
with session_scope() as session:
    district = get_district_by_id(session, "622710")  # Los Angeles
    print(f"{district.name}: {district.enrollment:,} students")

# Get top 10 districts by enrollment
from infrastructure.database.queries import get_top_districts
with session_scope() as session:
    top_10 = get_top_districts(session, limit=10)
    for d in top_10:
        print(f"{d.name}: {d.enrollment:,}")

# Search for districts by name
from infrastructure.database.queries import search_districts
with session_scope() as session:
    results = search_districts(session, "Chicago")
    for d in results:
        print(f"{d.nces_id}: {d.name}")

# Get all bell schedules for a district
from infrastructure.database.queries import get_bell_schedule
with session_scope() as session:
    schedules = get_bell_schedule(session, "622710")  # All grade levels
    for s in schedules:
        print(f"{s.grade_level}: {s.instructional_minutes} min")

# Get specific grade level
with session_scope() as session:
    elem = get_bell_schedule(session, "622710", grade_level="elementary")
    if elem:
        print(f"Elementary: {elem.instructional_minutes} min")

# Get state requirement
from infrastructure.database.queries import get_state_requirement
with session_scope() as session:
    ca = get_state_requirement(session, "CA")
    print(f"CA Elementary: {ca.elementary_minutes} min")
""")

    print("\n\n✅ WORKFLOW DEMONSTRATION COMPLETE")
    print("="*60)
    print("\nFor full documentation, see:")
    print("  docs/DATABASE_SETUP.md")
    print("\n")


if __name__ == "__main__":
    main()
