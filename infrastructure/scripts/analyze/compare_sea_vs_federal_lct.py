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
    python compare_sea_vs_federal_lct.py [--year 2024-25]

`--year` selects the FEDERAL (NCES CCD) vintage only. Each state's SEA data is always read at the vintage
declared in `SEA_STATES` (sea_import_utils.py), so a state whose SEA vintage differs from `--year` is a
cross-vintage pair: the output carries `sea_year`, `federal_year` and `vintage_aligned` per state and the
console flags every mismatch. A `--year` with no federal rows at all exits non-zero (DataGuardError).
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

from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR  # noqa: E402 — after the shim (#987)
from infrastructure.database.connection import session_scope
from sqlalchemy import text

# Default instructional minutes
DEFAULT_MINUTES = 360

# SEA states with data: the per-state vintage registry has ONE home (#990).
from infrastructure.database.migrations.sea_import_utils import SEA_STATES  # noqa: E402
from infrastructure.database.queries import distinct_years  # noqa: E402
from infrastructure.utilities.data_guards import require_nonempty_selection  # noqa: E402


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
          AND d.is_shared_service_entity = FALSE
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
    # Every query filters on the state's configured vintage — unfiltered
    # queries mixed all stored school years against year-filtered federal
    # data, making the comparison meaningless (issue #298). All *_staff_data /
    # *_enrollment_data tables carry a `year` column (verified 2026-07-20).
    yr = config['year']
    # Staff and enrollment can be different vintages (MA: enrollment is published a year ahead of staffing).
    enroll_yr = config.get('enroll_year', yr)
    if state == 'CA':
        staff_query = "SELECT nces_id, teachers_fte FROM ca_staff_data WHERE year = :year"
        enroll_query = "SELECT nces_id, total_k12 FROM ca_enrollment_data WHERE year = :year"
    elif state == 'FL':
        staff_query = "SELECT nces_id, classroom_teachers FROM fl_staff_data WHERE year = :year"
        enroll_query = "SELECT nces_id, total_enrollment FROM fl_enrollment_data WHERE year = :year"
    elif state == 'IL':
        staff_query = "SELECT nces_id, total_teacher_fte FROM il_staff_data WHERE year = :year"
        enroll_query = "SELECT nces_id, total_enrollment FROM il_enrollment_data WHERE year = :year"
    elif state == 'MA':
        staff_query = "SELECT nces_id, teachers_fte FROM ma_staff_data WHERE year = :year"
        enroll_query = "SELECT nces_id, total_enrollment FROM ma_enrollment_data WHERE year = :year"
    elif state == 'MI':
        staff_query = "SELECT nces_id, total_teacher_fte FROM mi_staff_data WHERE year = :year"
        enroll_query = "SELECT nces_id, total_k12 FROM mi_enrollment_data WHERE year = :year"
    elif state == 'NY':
        staff_query = "SELECT nces_id, SUM(fte) FROM ny_staff_data WHERE staff_category = 'Classroom Teacher' AND year = :year GROUP BY nces_id"
        enroll_query = "SELECT nces_id, SUM(enrollment_prek12) FROM ny_enrollment_data WHERE year = :year GROUP BY nces_id"
    elif state == 'PA':
        staff_query = "SELECT nces_id, classroom_teachers_fte FROM pa_staff_data WHERE year = :year"
        enroll_query = "SELECT nces_id, total_k12 FROM pa_enrollment_data WHERE year = :year"
    elif state == 'TX':
        staff_query = "SELECT nces_id, teachers_total_fte FROM tx_staff_data WHERE year = :year"
        enroll_query = "SELECT nces_id, total_enrollment FROM tx_enrollment_data WHERE year = :year"
    elif state == 'VA':
        staff_query = "SELECT nces_id, teachers_fte FROM va_staff_data WHERE year = :year"
        enroll_query = "SELECT nces_id, total_enrollment FROM va_enrollment_data WHERE year = :year"
    else:
        return pd.DataFrame()

    # Get staff
    staff_result = session.execute(text(staff_query), {"year": yr})
    staff_data = {row[0]: row[1] for row in staff_result}

    # Get enrollment
    enroll_result = session.execute(text(enroll_query), {"year": enroll_yr})
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

    # Only teachers_only is honestly computable — SEA tables carry no full
    # staff breakdown, and the old 'all_*' columns silently duplicated the
    # teacher numbers under a misleading name (issue #379)
    for scope in ['teachers_only']:
        merged[f'lct_fed_{scope}'] = merged.apply(
            lambda row: calculate_lct(DEFAULT_MINUTES, row['teachers_fed'], row['enrollment_k12_fed']),
            axis=1
        )
        merged[f'lct_sea_{scope}'] = merged.apply(
            lambda row: calculate_lct(DEFAULT_MINUTES, row['teachers_sea'], row['enrollment_k12_sea']),
            axis=1
        )

    # Filter valid calculations only — same validity band as the production
    # pipeline (0 < LCT <= 360). Without it, intermediate units / cyber
    # entities with tiny enrollments but real staff (implied LCT in the
    # hundreds-to-thousands) dominated the unweighted state means and made
    # PA/NY look absurd (issue #595 guardrail; Rule-6 CTC exclusion is also
    # applied in get_federal_data's WHERE clause).
    valid = merged[
        (merged['lct_fed_teachers_only'].notna()) & (merged['lct_sea_teachers_only'].notna())
        & (merged['lct_fed_teachers_only'] > 0) & (merged['lct_fed_teachers_only'] <= 360)
        & (merged['lct_sea_teachers_only'] > 0) & (merged['lct_sea_teachers_only'] <= 360)
    ]
    dropped = len(merged) - len(valid)
    if dropped:
        print(f"  Excluded {dropped} district(s) outside the 0-360 validity band")

    if len(valid) == 0:
        return None

    # Aggregate statistics
    comparison = {
        'state': state,
        'districts_compared': len(valid),
        'teachers_only_fed_mean': valid['lct_fed_teachers_only'].mean(),
        'teachers_only_sea_mean': valid['lct_sea_teachers_only'].mean(),
    }

    # Calculate differences (zero/NaN-safe denominator — issue #378)
    fed_mean = comparison['teachers_only_fed_mean']
    comparison['teachers_only_diff'] = comparison['teachers_only_sea_mean'] - fed_mean
    comparison['teachers_only_pct_diff'] = (
        (comparison['teachers_only_diff'] / fed_mean) * 100 if fed_mean else None
    )

    return comparison


def compare_all(session, federal_year: str) -> List[Dict]:
    """Compare every SEA state against the federal data of `federal_year`.

    Each result carries the SEA and federal vintages and whether they match (#992): `--year` moves only the
    federal side, so a mismatched pair is flagged rather than presented as a single-year comparison. An
    empty federal selection across ALL states is a wrong `--year`, not an empty workload, and raises."""
    results = []
    federal_rows = 0
    for state, config in SEA_STATES.items():
        print(f"Processing {state}...")

        federal_df = get_federal_data(session, state, federal_year)
        federal_rows += len(federal_df)
        print(f"  Federal: {len(federal_df)} districts")

        sea_df = get_sea_data(session, state, config)
        print(f"  SEA: {len(sea_df)} districts")

        comparison = compare_sources(federal_df, sea_df, state)
        if comparison:
            # Both SEA vintages must match the federal one (#1012): MA reads 2024-25 staff against 2025-26
            # enrollment, a mixed pair the staff year alone reported as aligned.
            enroll_year = config.get('enroll_year', config['year'])
            comparison['sea_year'] = config['year']
            comparison['sea_enroll_year'] = enroll_year
            comparison['federal_year'] = federal_year
            comparison['vintage_aligned'] = config['year'] == federal_year == enroll_year
            results.append(comparison)
            print(f"  Compared: {comparison['districts_compared']} districts")
            if not comparison['vintage_aligned']:
                sea_label = config['year'] if enroll_year == config['year'] else \
                    f"{config['year']} (enrollment {enroll_year})"
                print(f"  WARNING: cross-vintage pair - SEA {sea_label} vs federal {federal_year}")
        else:
            print("  No overlapping data")

    if federal_rows == 0:
        # Only the empty case pays for the extra query.
        require_nonempty_selection(
            [], what=f"federal staff/enrollment rows for --year {federal_year}",
            available=lambda: distinct_years(session, "staff_counts", "source_year"))
    return results


def main():
    parser = argparse.ArgumentParser(description="Compare SEA vs Federal LCT calculations")
    parser.add_argument("--year", default=NCES_PRIMARY_YEAR, help=f"NCES baseline year (default: NCES_PRIMARY_YEAR = {NCES_PRIMARY_YEAR})")
    args = parser.parse_args()

    print("=" * 70)
    print("SEA vs FEDERAL LCT COMPARISON")
    print("=" * 70)
    print(f"NCES Year: {args.year}")
    print(f"Scopes: teachers_only, all")
    print()

    with session_scope() as session:
        results = compare_all(session, args.year)

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
    if not comparison_df['vintage_aligned'].all():
        print("NOTE: rows with vintage_aligned=False compare SEA data against a different federal vintage.")
    print(comparison_df[['state', 'sea_year', 'federal_year', 'vintage_aligned', 'districts_compared', 'teachers_only_fed_mean', 'teachers_only_sea_mean', 'teachers_only_diff', 'teachers_only_pct_diff']].to_string(index=False))
    print()
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()
