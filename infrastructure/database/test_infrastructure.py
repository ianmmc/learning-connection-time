#!/usr/bin/env python3
"""
Test script for database infrastructure.

Tests all key functionality:
1. Database queries
2. Adding bell schedules
3. Data integrity constraints
4. JSON export
5. Relationships and joins

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
    get_district_by_id,
    get_top_districts,
    get_unenriched_districts,
    search_districts,
    get_bell_schedule,
    add_bell_schedule,
    get_state_requirement,
    get_enrichment_summary,
    export_bell_schedules_to_json,
)
from infrastructure.database.models import District, BellSchedule, StateRequirement


def test_basic_queries():
    """Test basic database queries."""
    print("\n" + "="*60)
    print("TEST 1: Basic Database Queries")
    print("="*60)

    with session_scope() as session:
        # Test: Get district by ID
        print("\n1.1 Get district by ID (Los Angeles):")
        la = get_district_by_id(session, "622710")
        if la:
            print(f"  ✓ Found: {la.name}, {la.state}")
            print(f"    Enrollment: {la.enrollment:,}")
            print(f"    Staff: {la.instructional_staff}")
        else:
            print("  ✗ FAILED: District not found")
            return False

        # Test: Get top districts
        print("\n1.2 Get top 5 districts by enrollment:")
        top_5 = get_top_districts(session, limit=5)
        if len(top_5) == 5:
            print("  ✓ Found 5 districts:")
            for d in top_5:
                print(f"    {d.nces_id}: {d.name} - {d.enrollment:,} students")
        else:
            print(f"  ✗ FAILED: Expected 5, got {len(top_5)}")
            return False

        # Test: Search districts
        print("\n1.3 Search for 'Chicago':")
        chicago = search_districts(session, "Chicago")
        if len(chicago) > 0:
            print(f"  ✓ Found {len(chicago)} districts:")
            for d in chicago[:3]:
                print(f"    {d.nces_id}: {d.name}")
        else:
            print("  ✗ FAILED: No results found")
            return False

        # Test: Get unenriched districts
        print("\n1.4 Get unenriched districts (min 50k enrollment):")
        unenriched = get_unenriched_districts(session, min_enrollment=50000, limit=5)
        if len(unenriched) > 0:
            print(f"  ✓ Found {len(unenriched)} unenriched districts:")
            for d in unenriched:
                print(f"    {d.nces_id}: {d.name} - {d.enrollment:,} students")
        else:
            print("  ⚠ No unenriched districts found (may be OK if all large districts enriched)")

    print("\n✓ TEST 1 PASSED")
    return True


def test_state_requirements():
    """Test state requirements queries."""
    print("\n" + "="*60)
    print("TEST 2: State Requirements")
    print("="*60)

    with session_scope() as session:
        # Test: Get state requirement
        print("\n2.1 Get California requirements:")
        ca = get_state_requirement(session, "CA")
        if ca:
            print(f"  ✓ Found: {ca.state_name}")
            print(f"    Elementary: {ca.elementary_minutes} min")
            print(f"    Middle: {ca.middle_minutes} min")
            print(f"    High: {ca.high_minutes} min")
        else:
            print("  ✗ FAILED: State not found")
            return False

        # Test: Get minutes for grade level
        print("\n2.2 Test get_minutes() method:")
        elem_min = ca.get_minutes("elementary")
        print(f"  ✓ Elementary minutes: {elem_min}")

        # Test: Count all states
        print("\n2.3 Count all state requirements:")
        count = session.query(StateRequirement).count()
        print(f"  ✓ Total states: {count}")
        if count < 50:
            print(f"  ⚠ Warning: Expected ~50 states, got {count}")

    print("\n✓ TEST 2 PASSED")
    return True


def test_bell_schedules():
    """Test bell schedule queries."""
    print("\n" + "="*60)
    print("TEST 3: Bell Schedule Queries")
    print("="*60)

    with session_scope() as session:
        # Test: Get existing bell schedule
        print("\n3.1 Get Los Angeles elementary schedule:")
        la_elem = get_bell_schedule(session, "622710", "2024-25", "elementary")
        if la_elem:
            print(f"  ✓ Found: {la_elem.instructional_minutes} minutes")
            print(f"    Method: {la_elem.method}")
            print(f"    Confidence: {la_elem.confidence}")
        else:
            print("  ⚠ No schedule found (may not be in database)")

        # Test: Count bell schedules
        print("\n3.2 Count all bell schedules:")
        count = session.query(BellSchedule).count()
        print(f"  ✓ Total schedules: {count}")

        # Test: Get district with schedules via relationship
        print("\n3.3 Test district-schedule relationship:")
        districts_with_schedules = (
            session.query(District)
            .join(BellSchedule)
            .distinct()
            .limit(5)
            .all()
        )
        print(f"  ✓ Found {len(districts_with_schedules)} districts with schedules:")
        for d in districts_with_schedules:
            schedule_count = len(d.bell_schedules)
            print(f"    {d.name}: {schedule_count} schedules")

    print("\n✓ TEST 3 PASSED")
    return True


def test_add_bell_schedule():
    """Test adding a new bell schedule (and rolling back)."""
    print("\n" + "="*60)
    print("TEST 4: Add Bell Schedule (with rollback)")
    print("="*60)

    with session_scope() as session:
        # Find a district without a schedule
        print("\n4.1 Finding test district...")
        test_district = get_unenriched_districts(session, min_enrollment=10000, limit=1)

        if not test_district:
            print("  ⚠ No unenriched districts available for testing")
            print("  Using Los Angeles for update test instead...")
            test_id = "622710"
            test_grade = "high"  # Try a different grade level
        else:
            test_id = test_district[0].nces_id
            test_grade = "elementary"
            print(f"  ✓ Using district: {test_district[0].name} ({test_id})")

        # Add a test schedule
        print(f"\n4.2 Adding {test_grade} schedule...")
        try:
            add_bell_schedule(
                session,
                district_id=test_id,
                year="2024-25",
                grade_level=test_grade,
                instructional_minutes=360,
                start_time="8:00 AM",
                end_time="3:00 PM",
                lunch_duration=30,
                method="human_provided",
                confidence="high",
                schools_sampled=["Test School"],
                source_urls=["https://example.com/test"],
                notes="Test schedule - will be rolled back"
            )
            print("  ✓ Bell schedule added successfully")

            # Verify it was added
            print("\n4.3 Verifying schedule was added...")
            verify = get_bell_schedule(session, test_id, "2024-25", test_grade)
            if verify and verify.notes == "Test schedule - will be rolled back":
                print(f"  ✓ Verified: {verify.instructional_minutes} minutes")
            else:
                print("  ✗ FAILED: Could not verify schedule")
                return False

        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            return False

        # Rollback the transaction
        print("\n4.4 Rolling back transaction...")
        session.rollback()
        print("  ✓ Transaction rolled back")

    # Verify rollback worked (new session)
    print("\n4.5 Verifying rollback (new session)...")
    with session_scope() as session:
        verify = get_bell_schedule(session, test_id, "2024-25", test_grade)
        if verify and verify.notes == "Test schedule - will be rolled back":
            print("  ✗ FAILED: Schedule still exists after rollback")
            return False
        else:
            print("  ✓ Rollback successful - test schedule removed")

    print("\n✓ TEST 4 PASSED")
    return True


def test_data_integrity():
    """Test data integrity constraints."""
    print("\n" + "="*60)
    print("TEST 5: Data Integrity Constraints")
    print("="*60)

    with session_scope() as session:
        # Test: Invalid district ID should fail
        print("\n5.1 Test foreign key constraint (invalid district):")
        try:
            add_bell_schedule(
                session,
                district_id="9999999",  # Invalid ID
                year="2024-25",
                grade_level="elementary",
                instructional_minutes=360,
                method="human_provided",
                confidence="high"
            )
            print("  ✗ FAILED: Should have raised error for invalid district")
            session.rollback()
            return False
        except ValueError as e:
            print(f"  ✓ Correctly rejected: {e}")
            session.rollback()

        # Test: Check constraint (invalid minutes)
        print("\n5.2 Test check constraint (minutes out of range):")
        from infrastructure.database.models import BellSchedule
        from sqlalchemy.exc import IntegrityError

        try:
            # Try to create schedule with invalid minutes (>600)
            bad_schedule = BellSchedule(
                district_id="622710",
                year="2024-25",
                grade_level="elementary",
                instructional_minutes=700,  # Invalid - exceeds 600
                method="human_provided",
                confidence="high"
            )
            session.add(bad_schedule)
            session.flush()
            print("  ✗ FAILED: Should have raised constraint error")
            session.rollback()
            return False
        except IntegrityError as e:
            print(f"  ✓ Correctly rejected invalid minutes")
            session.rollback()

        # Test: Unique constraint (duplicate schedule)
        print("\n5.3 Test unique constraint (duplicate schedule):")
        try:
            # Get an existing schedule
            existing = session.query(BellSchedule).first()
            if existing:
                # Try to add duplicate
                duplicate = BellSchedule(
                    district_id=existing.district_id,
                    year=existing.year,
                    grade_level=existing.grade_level,
                    instructional_minutes=360,
                    method="human_provided",
                    confidence="high"
                )
                session.add(duplicate)
                session.flush()
                print("  ✗ FAILED: Should have raised unique constraint error")
                session.rollback()
                return False
            else:
                print("  ⚠ No existing schedules to test duplicate")
        except IntegrityError as e:
            print(f"  ✓ Correctly rejected duplicate")
            session.rollback()

    print("\n✓ TEST 5 PASSED")
    return True


def test_enrichment_summary():
    """Test enrichment summary and reporting."""
    print("\n" + "="*60)
    print("TEST 6: Enrichment Summary")
    print("="*60)

    with session_scope() as session:
        print("\n6.1 Get enrichment summary:")
        summary = get_enrichment_summary(session)

        print(f"  Total districts: {summary['total_districts']:,}")
        print(f"  Enriched districts: {summary['enriched_districts']}")
        print(f"  Enrichment rate: {summary['enrichment_rate']:.2%}")
        print(f"  Schedule records: {summary['schedule_records']}")
        print(f"  States represented: {summary['states_represented']}")
        print(f"  Methods: {summary['by_method']}")

        # Validate summary
        if summary['total_districts'] > 10000:
            print("\n  ✓ District count looks reasonable")
        else:
            print(f"\n  ⚠ Warning: Low district count ({summary['total_districts']})")

        if summary['enriched_districts'] > 0:
            print("  ✓ Has enriched districts")
        else:
            print("  ⚠ Warning: No enriched districts")

    print("\n✓ TEST 6 PASSED")
    return True


def test_json_export():
    """Test JSON export functionality."""
    print("\n" + "="*60)
    print("TEST 7: JSON Export")
    print("="*60)

    with session_scope() as session:
        print("\n7.1 Export to JSON format:")
        json_str = export_bell_schedules_to_json(session, year="2024-25")

        # Validate JSON
        import json
        try:
            data = json.loads(json_str)
            print(f"  ✓ Valid JSON generated")
            print(f"  Districts in export: {len(data)}")

            # Check structure
            if len(data) > 0:
                first_district = list(data.values())[0]
                required_fields = ['district_id', 'district_name', 'state', 'year']
                has_all = all(field in first_district for field in required_fields)
                if has_all:
                    print(f"  ✓ Export structure valid")
                else:
                    print(f"  ✗ FAILED: Missing required fields")
                    return False

            # Check file size
            size = len(json_str)
            print(f"  Export size: {size:,} characters")

        except json.JSONDecodeError as e:
            print(f"  ✗ FAILED: Invalid JSON - {e}")
            return False

    print("\n✓ TEST 7 PASSED")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("DATABASE INFRASTRUCTURE TEST SUITE")
    print("="*60)

    tests = [
        ("Basic Queries", test_basic_queries),
        ("State Requirements", test_state_requirements),
        ("Bell Schedules", test_bell_schedules),
        ("Add Bell Schedule", test_add_bell_schedule),
        ("Data Integrity", test_data_integrity),
        ("Enrichment Summary", test_enrichment_summary),
        ("JSON Export", test_json_export),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ TEST FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{name:.<40} {status}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
