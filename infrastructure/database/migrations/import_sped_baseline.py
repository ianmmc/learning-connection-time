#!/usr/bin/env python3
"""
Import SPED baseline data from 2017-18 federal sources.

This script imports:
1. IDEA 618 Personnel (state-level SPED teachers)
2. IDEA 618 Child Count (state-level SPED students ages 6-21)
3. CRDC Enrollment (LEA-level SPED students)
4. CCD Enrollment (LEA-level total enrollment)

And calculates:
- Ratio 4a: State SPED Teachers / State SPED Students
- Ratio 4b: LEA SPED Students / LEA Total Students

Usage:
    python import_sped_baseline.py [--sample N]
"""

import argparse
import csv
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import SpedStateBaseline, SpedLeaBaseline, DataLineage

# File paths
DATA_DIR = project_root / "data" / "raw" / "federal"
IDEA_PERSONNEL_FILE = DATA_DIR / "idea-618" / "2017_18" / "bpersonnel2017-18.csv"
IDEA_CHILD_COUNT_FILE = DATA_DIR / "idea-618" / "2017_18" / "bchildcountandedenvironments2017-18.csv"
CRDC_ENROLLMENT_FILE = DATA_DIR / "crdc" / "2017_18" / "Enrollment.csv"
CCD_ENROLLMENT_FILE = DATA_DIR / "nces-ccd" / "2017_18" / "ccd_lea_052_1718_l_1a_083118.csv"

# State name to abbreviation mapping
STATE_ABBR = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA',
    'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'District of Columbia': 'DC',
    'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL',
    'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA',
    'Maine': 'ME', 'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
    'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV',
    'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
    'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK', 'Oregon': 'OR',
    'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
    'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA',
    'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY',
    'American Samoa': 'AS', 'Guam': 'GU', 'Northern Marianas': 'MP', 'Puerto Rico': 'PR',
    'Virgin Islands': 'VI',
    # Skip BIE - not a valid 2-letter state code
    # 'Bureau of Indian Education': 'BIE'
}


def safe_float(value: str) -> float | None:
    """Convert string to float, handling dashes and empty values."""
    if not value or value.strip() in ['-', '', 'N/A', 'na', 'NA']:
        return None
    try:
        return float(value.strip().replace(',', ''))
    except (ValueError, AttributeError):
        return None


def safe_int(value: str) -> int | None:
    """Convert string to int, handling dashes and empty values."""
    f = safe_float(value)
    return int(f) if f is not None else None


def import_idea_personnel(session) -> dict:
    """
    Import IDEA 618 Personnel data (state-level SPED teachers and paraprofessionals).

    Returns dict mapping state to SpedStateBaseline record.
    """
    print("\n=== Importing IDEA 618 Personnel (State SPED Teachers + Paras) ===")

    state_data = {}

    # Personnel types we care about (Ages 6-21 only)
    TEACHER_TYPE = 'Special Education Teachers for Ages 6-21'
    PARA_TYPE = 'Special Education Paraprofessionals for Ages 6-21'

    with open(IDEA_PERSONNEL_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)

        # Skip header rows (first 4 rows are metadata)
        for _ in range(4):
            next(reader)

        # Get column headers
        headers = next(reader)

        for row in reader:
            if len(row) < 6:
                continue

            year = row[0].strip()
            state_name = row[1].strip()
            personnel_type = row[2].strip()

            # Only process 2017 data (SY 2017-18)
            if year != '2017':
                continue

            state_abbr = STATE_ABBR.get(state_name)
            if not state_abbr:
                if state_name not in ['Bureau of Indian Education', 'Federated States of Micronesia',
                                       'Republic of Palau', 'Republic of the Marshall Islands',
                                       'US, Outlying Areas, and Freely Associated States']:
                    print(f"  Warning: Unknown state '{state_name}'")
                continue

            if state_abbr not in state_data:
                state_data[state_abbr] = SpedStateBaseline(
                    state=state_abbr,
                    source_year="2017-18",
                    personnel_source_file=str(IDEA_PERSONNEL_FILE.name)
                )

            # Parse values
            qualified = safe_float(row[3])
            not_qualified = safe_float(row[4])
            total = safe_float(row[5])

            # Process teachers (Ages 6-21)
            if personnel_type == TEACHER_TYPE:
                state_data[state_abbr].sped_teachers_certified = qualified
                state_data[state_abbr].sped_teachers_not_certified = not_qualified
                state_data[state_abbr].sped_teachers_total = total

            # Process paraprofessionals (Ages 6-21)
            elif personnel_type == PARA_TYPE:
                state_data[state_abbr].sped_paras_qualified = qualified
                state_data[state_abbr].sped_paras_not_qualified = not_qualified
                state_data[state_abbr].sped_paras_total = total

    # Calculate instructional totals (teachers + paras)
    for state_abbr, record in state_data.items():
        teachers = float(record.sped_teachers_total) if record.sped_teachers_total else 0
        paras = float(record.sped_paras_total) if record.sped_paras_total else 0
        if teachers > 0 or paras > 0:
            record.sped_instructional_total = teachers + paras

    teachers_count = sum(1 for s in state_data.values() if s.sped_teachers_total)
    paras_count = sum(1 for s in state_data.values() if s.sped_paras_total)
    print(f"  Loaded SPED teacher data for {teachers_count} states")
    print(f"  Loaded SPED paraprofessional data for {paras_count} states")
    return state_data


def import_idea_child_count(session, state_data: dict) -> dict:
    """
    Import IDEA 618 Child Count data (state-level SPED students).

    Sums Ages 6-21 across all educational environments for each state.
    Also categorizes students by educational environment:
    - Self-contained: Separate Class, Separate School, <40% in regular class
    - Mainstreamed: 80%+ in regular class, 40-79% in regular class
    """
    print("\n=== Importing IDEA 618 Child Count (State SPED Students) ===")

    # Educational environment categorization (Ages 6-21)
    SELF_CONTAINED_ENVIRONMENTS = {
        'Separate Class',
        'Separate School',
        'Inside regular class less than 40% of the day',
    }
    MAINSTREAMED_ENVIRONMENTS = {
        'Inside regular class 80% or more of the day',
        'Inside regular class 40% through 79% of the day',
    }
    # Excluded from both (not district-managed or other):
    # - Residential Facility
    # - Correctional Facilities
    # - Home, Homebound/Hospital
    # - Parentally Placed in Private Schools

    # Track totals by state
    state_totals = {}  # state -> {'ages_3_5': sum, 'ages_6_21': sum, 'self_contained': sum, 'mainstreamed': sum}

    with open(IDEA_CHILD_COUNT_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)

        # Skip header rows (first 4 rows are metadata)
        for _ in range(4):
            next(reader)

        # Get column headers
        headers = next(reader)

        # Find column indices
        idx_ages_3_5 = headers.index('Age 3 to 5') if 'Age 3 to 5' in headers else 18
        idx_ages_6_21 = headers.index('Ages 6-21') if 'Ages 6-21' in headers else 38

        for row in reader:
            if len(row) < max(idx_ages_3_5, idx_ages_6_21) + 1:
                continue

            year = row[0].strip()
            state_name = row[1].strip()
            environment = row[2].strip()
            disability = row[3].strip()

            # Only process 2017 data
            if year != '2017':
                continue

            # Only process "All Disabilities" rows (to get total across disabilities)
            if disability != 'All Disabilities':
                continue

            state_abbr = STATE_ABBR.get(state_name)
            if not state_abbr:
                continue

            ages_3_5 = safe_int(row[idx_ages_3_5])
            ages_6_21 = safe_int(row[idx_ages_6_21])

            if state_abbr not in state_totals:
                state_totals[state_abbr] = {
                    'ages_3_5': 0,
                    'ages_6_21': 0,
                    'self_contained': 0,
                    'mainstreamed': 0
                }

            if ages_3_5:
                state_totals[state_abbr]['ages_3_5'] += ages_3_5
            if ages_6_21:
                state_totals[state_abbr]['ages_6_21'] += ages_6_21

                # Categorize by educational environment (Ages 6-21 only)
                if environment in SELF_CONTAINED_ENVIRONMENTS:
                    state_totals[state_abbr]['self_contained'] += ages_6_21
                elif environment in MAINSTREAMED_ENVIRONMENTS:
                    state_totals[state_abbr]['mainstreamed'] += ages_6_21

    # Merge into state_data
    for state_abbr, totals in state_totals.items():
        if state_abbr not in state_data:
            state_data[state_abbr] = SpedStateBaseline(
                state=state_abbr,
                source_year="2017-18"
            )

        state_data[state_abbr].sped_students_ages_3_5 = totals['ages_3_5'] or None
        state_data[state_abbr].sped_students_ages_6_21 = totals['ages_6_21'] or None
        state_data[state_abbr].sped_students_total = (totals['ages_3_5'] or 0) + (totals['ages_6_21'] or 0) or None
        state_data[state_abbr].sped_students_self_contained = totals['self_contained'] or None
        state_data[state_abbr].sped_students_mainstreamed = totals['mainstreamed'] or None
        state_data[state_abbr].child_count_source_file = str(IDEA_CHILD_COUNT_FILE.name)

        # Calculate ratios (teachers and instructional per self-contained student)
        state_data[state_abbr].calculate_ratios()

    # Print summary
    total_self_contained = sum(t['self_contained'] for t in state_totals.values())
    total_all = sum(t['ages_6_21'] for t in state_totals.values())
    pct_self_contained = (total_self_contained / total_all * 100) if total_all > 0 else 0

    print(f"  Loaded SPED student data for {len(state_totals)} states")
    print(f"  Total Ages 6-21: {total_all:,}")
    print(f"  Self-contained: {total_self_contained:,} ({pct_self_contained:.1f}%)")

    return state_data


def import_crdc_enrollment(session, sample_limit: int = None) -> dict:
    """
    Import CRDC 2017-18 Enrollment data (LEA-level SPED students).

    Returns dict mapping LEA ID to SpedLeaBaseline record.
    """
    print("\n=== Importing CRDC Enrollment (LEA SPED Students) ===")

    lea_data = {}
    row_count = 0

    with open(CRDC_ENROLLMENT_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row in reader:
            lea_id = row.get('LEAID', '').strip()
            if not lea_id or len(lea_id) != 7:
                continue

            state = row.get('LEA_STATE', '').strip()
            lea_name = row.get('LEA_NAME', '').strip()

            # SPED enrollment (IDEA students)
            sped_m = safe_int(row.get('SCH_ENR_IDEA_M', ''))
            sped_f = safe_int(row.get('SCH_ENR_IDEA_F', ''))

            # Total enrollment
            tot_m = safe_int(row.get('TOT_ENR_M', ''))
            tot_f = safe_int(row.get('TOT_ENR_F', ''))

            # Aggregate by LEA (CRDC is school-level, we need LEA totals)
            if lea_id not in lea_data:
                lea_data[lea_id] = SpedLeaBaseline(
                    lea_id=lea_id,
                    lea_name=lea_name,
                    state=state,
                    source_year="2017-18",
                    crdc_sped_enrollment_m=0,
                    crdc_sped_enrollment_f=0,
                    crdc_sped_enrollment_total=0,
                    crdc_total_enrollment_m=0,
                    crdc_total_enrollment_f=0,
                    crdc_total_enrollment=0,
                    crdc_source_file=str(CRDC_ENROLLMENT_FILE.name)
                )

            # Sum across schools
            if sped_m:
                lea_data[lea_id].crdc_sped_enrollment_m += sped_m
            if sped_f:
                lea_data[lea_id].crdc_sped_enrollment_f += sped_f
            if tot_m:
                lea_data[lea_id].crdc_total_enrollment_m += tot_m
            if tot_f:
                lea_data[lea_id].crdc_total_enrollment_f += tot_f

            row_count += 1

            if sample_limit and len(lea_data) >= sample_limit:
                break

    # Calculate totals
    for lea in lea_data.values():
        lea.crdc_sped_enrollment_total = (lea.crdc_sped_enrollment_m or 0) + (lea.crdc_sped_enrollment_f or 0)
        lea.crdc_total_enrollment = (lea.crdc_total_enrollment_m or 0) + (lea.crdc_total_enrollment_f or 0)

        # Set to None if zero
        if lea.crdc_sped_enrollment_total == 0:
            lea.crdc_sped_enrollment_total = None
        if lea.crdc_total_enrollment == 0:
            lea.crdc_total_enrollment = None

    print(f"  Loaded CRDC data for {len(lea_data)} LEAs from {row_count:,} school records")
    return lea_data


def import_ccd_enrollment(session, lea_data: dict, sample_limit: int = None) -> dict:
    """
    Import CCD 2017-18 LEA Membership data (LEA-level total enrollment).

    Updates existing lea_data with CCD total enrollment.
    """
    print("\n=== Importing CCD Enrollment (LEA Total Enrollment) ===")

    matched = 0
    new_leas = 0

    with open(CCD_ENROLLMENT_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Only process total rows
            total_indicator = row.get('TOTAL_INDICATOR', '')
            if 'Derived - Education Unit Total' not in total_indicator:
                continue

            lea_id = row.get('LEAID', '').strip()
            if not lea_id or len(lea_id) != 7:
                continue

            enrollment = safe_int(row.get('STUDENT_COUNT', ''))
            state = row.get('ST', '').strip()
            lea_name = row.get('LEA_NAME', '').strip()

            if lea_id in lea_data:
                lea_data[lea_id].ccd_total_enrollment = enrollment
                lea_data[lea_id].ccd_source_file = str(CCD_ENROLLMENT_FILE.name)
                lea_data[lea_id].calculate_ratio()
                matched += 1
            else:
                # Create new entry for LEAs not in CRDC
                lea_data[lea_id] = SpedLeaBaseline(
                    lea_id=lea_id,
                    lea_name=lea_name,
                    state=state,
                    source_year="2017-18",
                    ccd_total_enrollment=enrollment,
                    ccd_source_file=str(CCD_ENROLLMENT_FILE.name)
                )
                new_leas += 1

            if sample_limit and (matched + new_leas) >= sample_limit:
                break

    print(f"  Matched {matched:,} LEAs with CRDC data")
    print(f"  Added {new_leas:,} new LEAs from CCD only")
    return lea_data


def save_to_database(session, state_data: dict, lea_data: dict):
    """Save all data to database."""
    print("\n=== Saving to Database ===")

    # Save state data
    for state_abbr, record in state_data.items():
        session.merge(record)
    print(f"  Saved {len(state_data)} state baseline records")

    # Save LEA data
    for lea_id, record in lea_data.items():
        session.merge(record)
    print(f"  Saved {len(lea_data):,} LEA baseline records")

    # Log lineage
    DataLineage.log(
        session,
        entity_type="sped_state_baseline",
        entity_id="all",
        operation="import",
        source_file="import_sped_baseline.py",
        details={
            "states_imported": len(state_data),
            "sources": ["IDEA 618 Personnel 2017-18", "IDEA 618 Child Count 2017-18"]
        },
        created_by="import_sped_baseline"
    )

    DataLineage.log(
        session,
        entity_type="sped_lea_baseline",
        entity_id="all",
        operation="import",
        source_file="import_sped_baseline.py",
        details={
            "leas_imported": len(lea_data),
            "sources": ["CRDC 2017-18 Enrollment", "CCD 2017-18 LEA Membership"]
        },
        created_by="import_sped_baseline"
    )

    session.commit()
    print("  Committed to database")


def print_summary(state_data: dict, lea_data: dict):
    """Print summary statistics."""
    print("\n=== Summary ===")

    # State-level stats
    states_with_teachers = sum(1 for s in state_data.values() if s.sped_teachers_total)
    states_with_students = sum(1 for s in state_data.values() if s.sped_students_ages_6_21)
    states_with_ratio = sum(1 for s in state_data.values() if s.ratio_sped_teachers_per_student)

    print(f"\nState-Level (Ratio 4a: SPED Teachers / SPED Students):")
    print(f"  States with teacher data: {states_with_teachers}")
    print(f"  States with student data: {states_with_students}")
    print(f"  States with calculated ratio: {states_with_ratio}")

    # Sample ratios
    print("\n  Sample state ratios (teachers per student):")
    for state_abbr in ['CA', 'TX', 'NY', 'FL', 'IL']:
        if state_abbr in state_data:
            s = state_data[state_abbr]
            if s.ratio_sped_teachers_per_student:
                print(f"    {state_abbr}: {float(s.ratio_sped_teachers_per_student):.4f} ({int(s.sped_teachers_total or 0):,} teachers / {s.sped_students_ages_6_21:,} students)")

    # LEA-level stats
    leas_with_sped = sum(1 for l in lea_data.values() if l.crdc_sped_enrollment_total)
    leas_with_total = sum(1 for l in lea_data.values() if l.ccd_total_enrollment)
    leas_with_ratio = sum(1 for l in lea_data.values() if l.ratio_sped_proportion)

    print(f"\nLEA-Level (Ratio 4b: SPED Students / Total Students):")
    print(f"  LEAs with SPED enrollment: {leas_with_sped:,}")
    print(f"  LEAs with total enrollment: {leas_with_total:,}")
    print(f"  LEAs with calculated ratio: {leas_with_ratio:,}")

    # SPED proportion distribution
    if leas_with_ratio > 0:
        proportions = [float(l.ratio_sped_proportion) for l in lea_data.values() if l.ratio_sped_proportion]
        avg_proportion = sum(proportions) / len(proportions)
        min_proportion = min(proportions)
        max_proportion = max(proportions)

        print(f"\n  SPED proportion statistics:")
        print(f"    Average: {avg_proportion:.2%}")
        print(f"    Min: {min_proportion:.2%}")
        print(f"    Max: {max_proportion:.2%}")


def main():
    parser = argparse.ArgumentParser(description="Import SPED baseline data from 2017-18 sources")
    parser.add_argument("--sample", type=int, help="Limit LEA records for testing")
    args = parser.parse_args()

    print("=" * 60)
    print("SPED Baseline Data Import (2017-18)")
    print("=" * 60)

    # Check files exist
    required_files = [IDEA_PERSONNEL_FILE, IDEA_CHILD_COUNT_FILE, CRDC_ENROLLMENT_FILE, CCD_ENROLLMENT_FILE]
    for f in required_files:
        if not f.exists():
            print(f"ERROR: Required file not found: {f}")
            sys.exit(1)

    print("\nData files found:")
    for f in required_files:
        print(f"  {f.name}")

    with session_scope() as session:
        # Import state-level data
        state_data = import_idea_personnel(session)
        state_data = import_idea_child_count(session, state_data)

        # Import LEA-level data
        lea_data = import_crdc_enrollment(session, sample_limit=args.sample)
        lea_data = import_ccd_enrollment(session, lea_data, sample_limit=args.sample)

        # Save to database
        save_to_database(session, state_data, lea_data)

        # Print summary
        print_summary(state_data, lea_data)

    print("\n" + "=" * 60)
    print("Import complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
