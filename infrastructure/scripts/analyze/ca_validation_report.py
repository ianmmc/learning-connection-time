#!/usr/bin/env python3
"""
California Phase 2 Validation Report

Compares California actual state data with national baseline estimates:
1. SPED self-contained proportions (actual vs state baseline)
2. SPED enrollment totals (actual vs estimates)
3. FRPM poverty rates (district-specific vs aggregated)
4. LCFF funding equity analysis

Generates comprehensive validation report showing improvements from state-specific data.
"""

import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import (
    District,
    CASpedDistrictEnvironments,
    DistrictSocioeconomic,
    CALCFFFunding,
    SpedStateBaseline,
    SpedLeaBaseline,
    SpedEstimate
)


def generate_sped_comparison():
    """Compare CA actual SPED data with baseline estimates."""
    print("=" * 80)
    print("SPED Self-Contained Proportion Comparison")
    print("=" * 80)

    with session_scope() as session:
        # Get California state baseline
        ca_baseline = session.query(SpedStateBaseline).filter(
            SpedStateBaseline.state == 'CA'
        ).first()

        if ca_baseline:
            print(f"\nState Baseline (2017-18 IDEA 618 + CRDC):")
            print(f"  Self-contained proportion: {ca_baseline.ratio_self_contained_proportion:.2%}")
        else:
            print("\nWARNING: No California state baseline found")
            ca_baseline_prop = 0.067  # National average fallback

        # Get CA districts with actual SPED data
        ca_districts = session.query(
            District,
            CASpedDistrictEnvironments,
            SpedEstimate
        ).join(
            CASpedDistrictEnvironments,
            District.nces_id == CASpedDistrictEnvironments.nces_id
        ).outerjoin(
            SpedEstimate,
            District.nces_id == SpedEstimate.district_id
        ).filter(
            District.state == 'CA',
            CASpedDistrictEnvironments.year == '2023-24'
        ).all()

        print(f"\nDistricts with actual SPED data: {len(ca_districts)}")

        if len(ca_districts) == 0:
            print("ERROR: No California districts with SPED data found")
            return

        # Calculate statistics
        actual_props = []
        baseline_props = []
        differences = []

        for district, actual_sped, estimate in ca_districts:
            if actual_sped.self_contained_proportion is not None:
                actual_props.append(actual_sped.self_contained_proportion)

                # Use state baseline (all CA districts use same baseline for now)
                if ca_baseline:
                    baseline_prop = ca_baseline.ratio_self_contained_proportion
                else:
                    baseline_prop = 0.067  # National average

                baseline_props.append(baseline_prop)
                differences.append(actual_sped.self_contained_proportion - baseline_prop)

        if len(actual_props) == 0:
            print("ERROR: No valid self-contained proportions found")
            return

        # Report statistics
        print(f"\nSelf-Contained Proportion Statistics:")
        print(f"  Actual (CA 2023-24):")
        print(f"    Mean: {sum(actual_props) / len(actual_props):.2%}")
        print(f"    Median: {sorted(actual_props)[len(actual_props)//2]:.2%}")
        print(f"    Min: {min(actual_props):.2%}")
        print(f"    Max: {max(actual_props):.2%}")

        print(f"\n  Baseline Estimates:")
        print(f"    Mean: {sum(baseline_props) / len(baseline_props):.2%}")

        print(f"\n  Differences (Actual - Baseline):")
        print(f"    Mean absolute difference: {sum(abs(d) for d in differences) / len(differences):.2%}")
        print(f"    Districts with >5% difference: {sum(1 for d in differences if abs(d) > 0.05)}")
        print(f"    % of districts with >5% difference: {sum(1 for d in differences if abs(d) > 0.05) / len(differences):.1%}")

        # Show top/bottom differences
        sorted_data = sorted(zip(differences, ca_districts), key=lambda x: x[0])

        baseline_val = ca_baseline.ratio_self_contained_proportion if ca_baseline else 0.067

        print(f"\nTop 5 districts with HIGHER self-contained than baseline:")
        shown = 0
        for diff, (dist, actual, est) in sorted_data[-5:]:
            if actual.self_contained_proportion is not None:
                print(f"  {dist.name[:50]:50s}")
                print(f"    Actual: {actual.self_contained_proportion:.2%} | Baseline: {baseline_val:.2%} | Diff: +{diff:.2%}")
                shown += 1
                if shown >= 5:
                    break

        print(f"\nTop 5 districts with LOWER self-contained than baseline:")
        shown = 0
        for diff, (dist, actual, est) in sorted_data[:10]:  # Check up to 10 to find 5 valid
            if actual.self_contained_proportion is not None:
                print(f"  {dist.name[:50]:50s}")
                print(f"    Actual: {actual.self_contained_proportion:.2%} | Baseline: {baseline_val:.2%} | Diff: {diff:.2%}")
                shown += 1
                if shown >= 5:
                    break


def generate_frpm_summary():
    """Summarize CA FRPM poverty data."""
    print("\n" + "=" * 80)
    print("FRPM Poverty Indicator Summary")
    print("=" * 80)

    with session_scope() as session:
        ca_frpm = session.query(DistrictSocioeconomic).filter(
            DistrictSocioeconomic.state == 'CA',
            DistrictSocioeconomic.year == '2023-24',
            DistrictSocioeconomic.poverty_indicator_type == 'FRPM'
        ).all()

        print(f"\nDistricts with FRPM data: {len(ca_frpm)}")

        if len(ca_frpm) == 0:
            print("ERROR: No FRPM data found")
            return

        # Calculate statistics
        poverty_rates = [d.poverty_percent for d in ca_frpm if d.poverty_percent is not None]

        print(f"\nFRPM Percentage Statistics:")
        print(f"  Mean: {sum(poverty_rates) / len(poverty_rates):.1%}")
        print(f"  Median: {sorted(poverty_rates)[len(poverty_rates)//2]:.1%}")
        print(f"  Min: {min(poverty_rates):.1%}")
        print(f"  Max: {max(poverty_rates):.1%}")

        # Quartiles
        sorted_rates = sorted(poverty_rates)
        q1 = sorted_rates[len(sorted_rates)//4]
        q3 = sorted_rates[(3*len(sorted_rates))//4]

        print(f"\nQuartiles:")
        print(f"  Q1 (25th percentile): {q1:.1%}")
        print(f"  Q3 (75th percentile): {q3:.1%}")
        print(f"  Interquartile range: {q3 - q1:.1%}")

        # Distribution
        print(f"\nDistribution:")
        print(f"  Districts with <25% FRPM: {sum(1 for r in poverty_rates if r < 0.25)}")
        print(f"  Districts with 25-50% FRPM: {sum(1 for r in poverty_rates if 0.25 <= r < 0.50)}")
        print(f"  Districts with 50-75% FRPM: {sum(1 for r in poverty_rates if 0.50 <= r < 0.75)}")
        print(f"  Districts with 75%+ FRPM: {sum(1 for r in poverty_rates if r >= 0.75)}")


def generate_lcff_summary():
    """Summarize CA LCFF funding data."""
    print("\n" + "=" * 80)
    print("LCFF Funding Summary")
    print("=" * 80)

    with session_scope() as session:
        ca_lcff = session.query(CALCFFFunding).filter(
            CALCFFFunding.year == '2023-24'
        ).all()

        print(f"\nDistricts with LCFF data: {len(ca_lcff)}")

        if len(ca_lcff) == 0:
            print("ERROR: No LCFF data found")
            return

        # Calculate statistics
        total_funding = [d.total_lcff for d in ca_lcff if d.total_lcff is not None]
        base_grants = [d.base_grant for d in ca_lcff if d.base_grant is not None]
        supp_grants = [d.supplemental_grant for d in ca_lcff if d.supplemental_grant is not None]
        conc_grants = [d.concentration_grant for d in ca_lcff if d.concentration_grant is not None]

        print(f"\nTotal LCFF Funding:")
        print(f"  Statewide total: ${sum(total_funding):,.0f}")
        print(f"  Mean per district: ${sum(total_funding) / len(total_funding):,.0f}")
        print(f"  Median per district: ${sorted(total_funding)[len(total_funding)//2]:,.0f}")

        print(f"\nFunding Components:")
        print(f"  Total Base Grants: ${sum(base_grants):,.0f} ({sum(base_grants)/sum(total_funding):.1%} of total)")
        print(f"  Total Supplemental: ${sum(supp_grants):,.0f} ({sum(supp_grants)/sum(total_funding):.1%} of total)")
        print(f"  Total Concentration: ${sum(conc_grants):,.0f} ({sum(conc_grants)/sum(total_funding):.1%} of total)")

        # Equity grants (supplemental + concentration)
        equity_grants = []
        for d in ca_lcff:
            supp = d.supplemental_grant or 0
            conc = d.concentration_grant or 0
            if d.total_lcff and d.total_lcff > 0:
                equity_grants.append((supp + conc) / d.total_lcff)

        print(f"\nEquity Funding (Supplemental + Concentration as % of total):")
        print(f"  Mean: {sum(equity_grants) / len(equity_grants):.1%}")
        print(f"  Median: {sorted(equity_grants)[len(equity_grants)//2]:.1%}")
        print(f"  Min: {min(equity_grants):.1%}")
        print(f"  Max: {max(equity_grants):.1%}")


def generate_data_coverage_summary():
    """Summary of data coverage across all CA districts."""
    print("\n" + "=" * 80)
    print("California Data Coverage Summary")
    print("=" * 80)

    with session_scope() as session:
        # Total CA districts
        total_districts = session.query(District).filter(
            District.state == 'CA',
            District.year == '2023-24'
        ).count()

        # Districts with each data type
        sped_count = session.query(CASpedDistrictEnvironments).filter(
            CASpedDistrictEnvironments.year == '2023-24'
        ).count()

        frpm_count = session.query(DistrictSocioeconomic).filter(
            DistrictSocioeconomic.state == 'CA',
            DistrictSocioeconomic.year == '2023-24'
        ).count()

        lcff_count = session.query(CALCFFFunding).filter(
            CALCFFFunding.year == '2023-24'
        ).count()

        print(f"\nTotal CA districts in database: {total_districts}")
        print(f"\nData Coverage:")
        print(f"  SPED (actual environments): {sped_count} ({sped_count/total_districts:.1%})")
        print(f"  FRPM (poverty indicator): {frpm_count} ({frpm_count/total_districts:.1%})")
        print(f"  LCFF (funding): {lcff_count} ({lcff_count/total_districts:.1%})")

        # Districts with all three
        complete_districts = session.query(District).join(
            CASpedDistrictEnvironments
        ).join(
            DistrictSocioeconomic
        ).join(
            CALCFFFunding
        ).filter(
            District.state == 'CA',
            District.year == '2023-24',
            CASpedDistrictEnvironments.year == '2023-24',
            DistrictSocioeconomic.year == '2023-24',
            CALCFFFunding.year == '2023-24'
        ).count()

        print(f"\nDistricts with complete data (all 3 sources): {complete_districts} ({complete_districts/total_districts:.1%})")


def main():
    """Generate complete validation report."""
    print("=" * 80)
    print("CALIFORNIA PHASE 2 VALIDATION REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    generate_data_coverage_summary()
    generate_sped_comparison()
    generate_frpm_summary()
    generate_lcff_summary()

    print("\n" + "=" * 80)
    print("REPORT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
