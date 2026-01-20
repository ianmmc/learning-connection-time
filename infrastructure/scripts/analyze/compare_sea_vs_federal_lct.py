#!/usr/bin/env python3
"""
Compare LCT calculations using State (SEA) vs Federal (NCES) data sources.

This script generates a state-level aggregate comparison showing how LCT differs
when calculated from state-reported data versus federal NCES CCD data.

**Comparison Scopes:**
- teachers_only: K-12 teachers only
- teachers_gened: GenEd teachers / GenEd enrollment
- all: All staff

**Output:**
State aggregate table with columns:
- state: Two-letter state code
- scope: LCT scope name
- districts_compared: Number of districts with both sources
- federal_mean: Mean LCT using NCES data
- sea_mean: Mean LCT using SEA data
- diff_mean: sea_mean - federal_mean
- pct_diff: (diff_mean / federal_mean) * 100

Usage:
    python compare_sea_vs_federal_lct.py [--year 2023-24]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from sqlalchemy import text

# Default instructional minutes
DEFAULT_MINUTES = 360

# SEA states with data
SEA_STATES = {
    'CA': {'year': '2024-25', 'staff_table': 'ca_staff_data', 'enroll_table': 'ca_enrollment_data'},
    'FL': {'year': '2024-25', 'staff_table': 'fl_staff_data', 'enroll_table': 'fl_enrollment_data'},
    'IL': {'year': '2023-24', 'staff_table': 'il_staff_data', 'enroll_table': 'il_enrollment_data'},
    'MA': {'year': '2025-26', 'staff_table': 'ma_staff_data', 'enroll_table': 'ma_enrollment_data'},
    'MI': {'year': '2023-24', 'staff_table': 'mi_staff_data', 'enroll_table': 'mi_enrollment_data'},
    'NY': {'year': '2023-24', 'staff_table': 'ny_staff_data', 'enroll_table': 'ny_enrollment_data'},
    'PA': {'year': '2024-25', 'staff_table': 'pa_staff_data', 'enroll_table': 'pa_enrollment_data'},
    'TX': {'year': '2024-25', 'staff_table': 'tx_staff_data', 'enroll_table': 'tx_enrollment_data'},
    'VA': {'year': '2025-26', 'staff_table': 'va_staff_data', 'enroll_table': 'va_enrollment_data'},
}


def calculate_lct(minutes: float, staff: float, enrollment: float) -> float:
    """Calculate LCT = (minutes * staff) / enrollment"""
    if staff is None or enrollment is None:
        return None
    if enrollment <= 0 or staff <= 0:
        return None
    return (minutes * staff) / enrollment


def get_federal_data(session, state: str, nces_year: str) -> pd.DataFrame:
    """Get NCES federal data for a state."""
    query = text("""
        SELECT
            sc.district_id,
            sc.teachers_total,
            eg.enrollment_k12,
            eg.enrollment_prek + eg.enrollment_kindergarten +
                eg.enrollment_grade_1 + eg.enrollment_grade_2 + eg.enrollment_grade_3 +
                eg.enrollment_grade_4 + eg.enrollment_grade_5 as enrollment_k5
        FROM staff_counts sc
        JOIN enrollment_by_grade eg ON sc.district_id = eg.district_id
        JOIN districts d ON sc.district_id = d.nces_id
        WHERE d.state = :state
          AND sc.source_year = :year
          AND eg.source_year = :year
    """)

    result = session.execute(query, {"state": state, "year": nces_year})
    rows = []
    for row in result:
        rows.append({
            'district_id': row[0],
            'teachers': row[1],
            'enrollment_k12': row[2],
            'enrollment_k5': row[3],
        })

    return pd.DataFrame(rows)


def get_sea_data(session, state: str, config: dict) -> pd.DataFrame:
    """Get SEA state data for a state."""
    # State-specific queries (simplified - just get teachers and enrollment)
    if state == 'CA':
        staff_query = "SELECT nces_id, teachers_fte FROM ca_staff_data"
        enroll_query = "SELECT nces_id, total_k12 FROM ca_enrollment_data"
    elif state == 'FL':
        staff_query = "SELECT nces_id, classroom_teachers FROM fl_staff_data"
        enroll_query = "SELECT nces_id, total_enrollment FROM fl_enrollment_data"
    elif state == 'IL':
        staff_query = "SELECT nces_id, total_teacher_fte FROM il_staff_data"
        enroll_query = "SELECT nces_id, total_enrollment FROM il_enrollment_data"
    elif state == 'MA':
        staff_query = "SELECT nces_id, teachers_fte FROM ma_staff_data"
        enroll_query = "SELECT nces_id, total_enrollment FROM ma_enrollment_data"
    elif state == 'MI':
        staff_query = "SELECT nces_id, total_teacher_fte FROM mi_staff_data"
        enroll_query = "SELECT nces_id, total_k12 FROM mi_enrollment_data"
    elif state == 'NY':
        staff_query = "SELECT nces_id, SUM(fte) FROM ny_staff_data WHERE staff_category = 'Classroom Teacher' GROUP BY nces_id"
        enroll_query = "SELECT nces_id, SUM(enrollment_prek12) FROM ny_enrollment_data GROUP BY nces_id"
    elif state == 'PA':
        staff_query = "SELECT nces_id, classroom_teachers_fte FROM pa_staff_data"
        enroll_query = "SELECT nces_id, total_k12 FROM pa_enrollment_data"
    elif state == 'TX':
        staff_query = "SELECT nces_id, teachers_total_fte FROM tx_staff_data"
        enroll_query = "SELECT nces_id, total_enrollment FROM tx_enrollment_data"
    elif state == 'VA':
        staff_query = "SELECT nces_id, teachers_fte FROM va_staff_data"
        enroll_query = "SELECT nces_id, total_enrollment FROM va_enrollment_data"
    else:
        return pd.DataFrame()

    # Get staff
    staff_result = session.execute(text(staff_query))
    staff_data = {row[0]: row[1] for row in staff_result}

    # Get enrollment
    enroll_result = session.execute(text(enroll_query))
    enroll_data = {row[0]: row[1] for row in enroll_result}

    # Merge
    rows = []
    for nces_id in set(staff_data.keys()) & set(enroll_data.keys()):
        rows.append({
            'district_id': nces_id,
            'teachers': staff_data[nces_id],
            'enrollment_k12': enroll_data[nces_id],
        })

    return pd.DataFrame(rows)


def compare_sources(federal_df: pd.DataFrame, sea_df: pd.DataFrame, state: str) -> Dict:
    """Compare LCT from federal vs SEA sources for a state."""
    # Check if we have data
    if len(federal_df) == 0 or len(sea_df) == 0:
        return None

    # Merge on district_id
    merged = federal_df.merge(sea_df, on='district_id', suffixes=('_fed', '_sea'))

    if len(merged) == 0:
        return None

    # Calculate LCT for teachers_only and all scopes
    results = {}

    for scope in ['teachers_only', 'all']:
        # For this comparison, teachers_only = teachers, all = teachers (we don't have full staff breakdown in SEA)
        merged[f'lct_fed_{scope}'] = merged.apply(
            lambda row: calculate_lct(DEFAULT_MINUTES, row['teachers_fed'], row['enrollment_k12_fed']),
            axis=1
        )
        merged[f'lct_sea_{scope}'] = merged.apply(
            lambda row: calculate_lct(DEFAULT_MINUTES, row['teachers_sea'], row['enrollment_k12_sea']),
            axis=1
        )

    # Filter valid calculations only
    valid = merged[(merged['lct_fed_teachers_only'].notna()) & (merged['lct_sea_teachers_only'].notna())]

    if len(valid) == 0:
        return None

    # Aggregate statistics
    comparison = {
        'state': state,
        'districts_compared': len(valid),
        'teachers_only_fed_mean': valid['lct_fed_teachers_only'].mean(),
        'teachers_only_sea_mean': valid['lct_sea_teachers_only'].mean(),
        'all_fed_mean': valid['lct_fed_all'].mean(),
        'all_sea_mean': valid['lct_sea_all'].mean(),
    }

    # Calculate differences
    comparison['teachers_only_diff'] = comparison['teachers_only_sea_mean'] - comparison['teachers_only_fed_mean']
    comparison['teachers_only_pct_diff'] = (comparison['teachers_only_diff'] / comparison['teachers_only_fed_mean']) * 100
    comparison['all_diff'] = comparison['all_sea_mean'] - comparison['all_fed_mean']
    comparison['all_pct_diff'] = (comparison['all_diff'] / comparison['all_fed_mean']) * 100

    return comparison


def main():
    parser = argparse.ArgumentParser(description="Compare SEA vs Federal LCT calculations")
    parser.add_argument("--year", default="2023-24", help="NCES baseline year")
    args = parser.parse_args()

    print("=" * 70)
    print("SEA vs FEDERAL LCT COMPARISON")
    print("=" * 70)
    print(f"NCES Year: {args.year}")
    print(f"Scopes: teachers_only, all")
    print()

    results = []

    with session_scope() as session:
        for state, config in SEA_STATES.items():
            print(f"Processing {state}...")

            # Get federal data
            federal_df = get_federal_data(session, state, args.year)
            print(f"  Federal: {len(federal_df)} districts")

            # Get SEA data
            sea_df = get_sea_data(session, state, config)
            print(f"  SEA: {len(sea_df)} districts")

            # Compare
            comparison = compare_sources(federal_df, sea_df, state)
            if comparison:
                results.append(comparison)
                print(f"  Compared: {comparison['districts_compared']} districts")
            else:
                print(f"  No overlapping data")

    # Create comparison dataframe
    if not results:
        print("\nNo comparison data available.")
        return

    comparison_df = pd.DataFrame(results)

    # Save to CSV
    output_dir = project_root / "data" / "enriched" / "lct-calculations"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_file = output_dir / f"lct_sea_vs_federal_comparison_{args.year.replace('-', '_')}_{timestamp}.csv"

    comparison_df.to_csv(output_file, index=False, float_format='%.2f')

    print()
    print("=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(comparison_df[['state', 'districts_compared', 'teachers_only_fed_mean', 'teachers_only_sea_mean', 'teachers_only_diff', 'teachers_only_pct_diff']].to_string(index=False))
    print()
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()
