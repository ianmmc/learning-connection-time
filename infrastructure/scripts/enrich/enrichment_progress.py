#!/usr/bin/env python3
"""
Enrichment Progress Tracker

Provides real-time visibility into the bell schedule enrichment campaign.
Tracks progress by state, generates reports, and identifies next districts to enrich.

Usage:
    # Show overall progress
    python enrichment_progress.py

    # Show progress for specific state
    python enrichment_progress.py --state WY

    # Show next N districts to enrich
    python enrichment_progress.py --next 10

    # Export progress report
    python enrichment_progress.py --export progress_report.txt

    # Campaign dashboard
    python enrichment_progress.py --campaign
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

# Add utilities to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "utilities"))


class EnrichmentProgressTracker:
    """Track and report on enrichment campaign progress"""

    def __init__(self, enrichment_ref_path: Path):
        """
        Initialize progress tracker

        Args:
            enrichment_ref_path: Path to enrichment reference CSV
        """
        self.enrichment_ref_path = enrichment_ref_path
        self.ref_df = pd.read_csv(enrichment_ref_path)

        # Paths
        self.bell_schedules_dir = Path("data/enriched/bell-schedules")
        self.manual_followup_path = self.bell_schedules_dir / "manual_followup_needed.json"

        # Load manual follow-up list
        self.load_manual_followup()

        # State population order (for campaign)
        self.state_order = [
            'WY', 'VT', 'DC', 'AK', 'ND', 'SD', 'DE', 'RI', 'MT', 'ME',
            'NH', 'HI', 'WV', 'ID', 'NE', 'NM', 'KS', 'MS', 'AR', 'NV',
            'IA', 'UT', 'CT', 'OK', 'OR', 'KY', 'LA', 'SC', 'AL', 'CO',
            'MN', 'WI', 'MD', 'MO', 'TN', 'IN', 'MA', 'AZ', 'WA', 'VA',
            'NJ', 'NC', 'GA', 'MI', 'OH', 'IL', 'PA', 'NY', 'FL', 'TX', 'CA'
        ]

    def load_manual_followup(self):
        """Load manual follow-up list"""
        if self.manual_followup_path.exists():
            with open(self.manual_followup_path, 'r') as f:
                self.manual_followup = json.load(f)
        else:
            self.manual_followup = {"districts": [], "last_updated": None}

    def get_overall_stats(self) -> Dict:
        """Get overall enrichment statistics"""
        total = len(self.ref_df)
        enriched = self.ref_df['enriched'].sum()
        pending = total - enriched

        return {
            "total_districts": total,
            "enriched": enriched,
            "pending": pending,
            "enrichment_rate": enriched / total * 100,
            "manual_followup": len(self.manual_followup['districts'])
        }

    def get_state_stats(self, state: Optional[str] = None) -> pd.DataFrame:
        """
        Get enrichment statistics by state

        Args:
            state: Optional state filter

        Returns:
            DataFrame with state statistics
        """
        if state:
            df = self.ref_df[self.ref_df['state'] == state.upper()]
        else:
            df = self.ref_df

        # Group by state
        state_stats = df.groupby('state').agg({
            'district_id': 'count',
            'enriched': 'sum',
            'enrollment_total': 'sum'
        }).rename(columns={
            'district_id': 'total_districts',
            'enriched': 'enriched_count',
            'enrollment_total': 'total_enrollment'
        })

        state_stats['pending'] = state_stats['total_districts'] - state_stats['enriched_count']
        state_stats['enrichment_rate'] = (
            state_stats['enriched_count'] / state_stats['total_districts'] * 100
        )

        # Sort by state order for campaign
        state_stats['priority'] = state_stats.index.map(
            lambda x: self.state_order.index(x) if x in self.state_order else 999
        )
        state_stats = state_stats.sort_values('priority')
        state_stats = state_stats.drop(columns=['priority'])

        return state_stats

    def get_next_districts(
        self,
        n: int = 10,
        state: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get next N districts to enrich

        Args:
            n: Number of districts to return
            state: Optional state filter

        Returns:
            DataFrame of next districts
        """
        pending = self.ref_df[~self.ref_df['enriched']]

        if state:
            pending = pending[pending['state'] == state.upper()]

        # Sort by enrollment (largest first)
        pending = pending.sort_values('enrollment_total', ascending=False)

        return pending.head(n)[[
            'district_id', 'district_name', 'state',
            'enrollment_total', 'enrollment_elementary',
            'enrollment_middle', 'enrollment_high'
        ]]

    def get_campaign_progress(self, target_per_state: int = 3) -> pd.DataFrame:
        """
        Get campaign progress (N districts per state)

        Args:
            target_per_state: Target enrichments per state

        Returns:
            DataFrame with campaign progress
        """
        state_stats = self.get_state_stats()

        state_stats['target'] = target_per_state
        state_stats['needed'] = target_per_state - state_stats['enriched_count']
        state_stats['needed'] = state_stats['needed'].clip(lower=0)
        state_stats['campaign_complete'] = state_stats['enriched_count'] >= target_per_state

        return state_stats[[
            'total_districts', 'enriched_count', 'target',
            'needed', 'campaign_complete', 'total_enrollment'
        ]]

    def print_overall_progress(self):
        """Print overall progress summary"""
        stats = self.get_overall_stats()

        print("=" * 60)
        print("ENRICHMENT CAMPAIGN PROGRESS")
        print("=" * 60)
        print(f"Total districts: {stats['total_districts']:,}")
        print(f"Enriched: {stats['enriched']:,} ({stats['enrichment_rate']:.1f}%)")
        print(f"Pending: {stats['pending']:,}")
        print(f"Manual follow-up: {stats['manual_followup']}")
        print("=" * 60)

    def print_state_progress(self, state: Optional[str] = None, limit: int = 10):
        """Print state-by-state progress"""
        state_stats = self.get_state_stats(state)

        if state:
            print(f"\n{state.upper()} ENRICHMENT STATUS")
            print("=" * 60)
        else:
            print("\nSTATE-BY-STATE PROGRESS (Top {})".format(limit))
            print("=" * 60)
            print(f"{'State':<6} {'Total':<7} {'Enriched':<9} {'Pending':<8} {'Rate':<6}")
            print("-" * 60)

        for idx, (state_code, row) in enumerate(state_stats.iterrows()):
            if not state and idx >= limit:
                break

            if state:
                print(f"Total districts: {row['total_districts']}")
                print(f"Enriched: {row['enriched_count']}")
                print(f"Pending: {row['pending']}")
                print(f"Rate: {row['enrichment_rate']:.1f}%")
                print(f"Total enrollment: {row['total_enrollment']:,.0f}")
            else:
                print(
                    f"{state_code:<6} "
                    f"{row['total_districts']:<7} "
                    f"{row['enriched_count']:<9} "
                    f"{row['pending']:<8} "
                    f"{row['enrichment_rate']:>5.1f}%"
                )

        print("=" * 60)

    def print_next_districts(self, n: int = 10, state: Optional[str] = None):
        """Print next N districts to enrich"""
        next_districts = self.get_next_districts(n, state)

        if state:
            print(f"\nNEXT {n} DISTRICTS TO ENRICH IN {state.upper()}")
        else:
            print(f"\nNEXT {n} DISTRICTS TO ENRICH (BY ENROLLMENT)")

        print("=" * 60)

        for idx, row in next_districts.iterrows():
            print(f"\n{row['district_name']} ({row['state']})")
            print(f"  ID: {row['district_id']}")
            print(f"  Total enrollment: {row['enrollment_total']:,.0f}")
            print(f"  Elementary: {row['enrollment_elementary']:,.0f}")
            print(f"  Middle: {row['enrollment_middle']:,.0f}")
            print(f"  High: {row['enrollment_high']:,.0f}")

        print("=" * 60)

    def print_campaign_dashboard(self, target_per_state: int = 3):
        """Print campaign-style dashboard"""
        campaign = self.get_campaign_progress(target_per_state)

        print("\nCAMPAIGN DASHBOARD")
        print(f"Target: {target_per_state} districts per state")
        print("=" * 60)

        # Summary
        total_states = len(campaign)
        complete_states = campaign['campaign_complete'].sum()
        total_target = total_states * target_per_state
        total_enriched = campaign['enriched_count'].sum()

        print(f"\nCampaign Summary:")
        print(f"  States: {complete_states}/{total_states} complete")
        print(f"  Districts: {total_enriched}/{total_target} enriched")
        print(f"  Overall rate: {total_enriched/total_target*100:.1f}%")

        # Show incomplete states
        incomplete = campaign[~campaign['campaign_complete']]

        if not incomplete.empty:
            print(f"\nStates needing enrichment ({len(incomplete)}):")
            print(f"{'State':<6} {'Enriched':<9} {'Target':<7} {'Needed':<7}")
            print("-" * 60)

            for state, row in incomplete.head(20).iterrows():
                print(
                    f"{state:<6} "
                    f"{row['enriched_count']:<9} "
                    f"{row['target']:<7} "
                    f"{row['needed']:<7}"
                )

            if len(incomplete) > 20:
                print(f"... and {len(incomplete) - 20} more states")

        print("=" * 60)

    def export_report(self, output_path: Path):
        """Export detailed progress report"""
        with open(output_path, 'w') as f:
            # Header
            f.write("=" * 60 + "\n")
            f.write("ENRICHMENT CAMPAIGN PROGRESS REPORT\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")

            # Overall stats
            stats = self.get_overall_stats()
            f.write("OVERALL STATISTICS\n")
            f.write("-" * 60 + "\n")
            f.write(f"Total districts: {stats['total_districts']:,}\n")
            f.write(f"Enriched: {stats['enriched']:,} ({stats['enrichment_rate']:.1f}%)\n")
            f.write(f"Pending: {stats['pending']:,}\n")
            f.write(f"Manual follow-up: {stats['manual_followup']}\n\n")

            # State-by-state
            f.write("STATE-BY-STATE PROGRESS\n")
            f.write("-" * 60 + "\n")
            f.write(f"{'State':<6} {'Total':<7} {'Enriched':<9} {'Pending':<8} {'Rate':<6}\n")
            f.write("-" * 60 + "\n")

            state_stats = self.get_state_stats()
            for state, row in state_stats.iterrows():
                f.write(
                    f"{state:<6} "
                    f"{row['total_districts']:<7} "
                    f"{row['enriched_count']:<9} "
                    f"{row['pending']:<8} "
                    f"{row['enrichment_rate']:>5.1f}%\n"
                )

            f.write("\n")

            # Campaign progress
            f.write("CAMPAIGN PROGRESS (3 per state)\n")
            f.write("-" * 60 + "\n")
            campaign = self.get_campaign_progress(target_per_state=3)

            complete = campaign[campaign['campaign_complete']]
            incomplete = campaign[~campaign['campaign_complete']]

            f.write(f"Complete: {len(complete)}/{len(campaign)} states\n\n")

            if not incomplete.empty:
                f.write("States needing enrichment:\n")
                for state, row in incomplete.iterrows():
                    f.write(
                        f"  {state}: {row['enriched_count']}/{row['target']} "
                        f"(need {row['needed']} more)\n"
                    )

        print(f"✓ Exported progress report to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Track enrichment campaign progress",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--state',
        help="Show progress for specific state"
    )
    parser.add_argument(
        '--next',
        type=int,
        metavar='N',
        help="Show next N districts to enrich"
    )
    parser.add_argument(
        '--campaign',
        action='store_true',
        help="Show campaign dashboard (N per state)"
    )
    parser.add_argument(
        '--target-per-state',
        type=int,
        default=3,
        help="Target districts per state for campaign (default: 3)"
    )
    parser.add_argument(
        '--export',
        type=Path,
        metavar='FILE',
        help="Export progress report to file"
    )

    args = parser.parse_args()

    # Initialize tracker
    enrichment_ref_path = Path('data/processed/normalized/enrichment_reference.csv')

    if not enrichment_ref_path.exists():
        print(f"Error: Enrichment reference file not found: {enrichment_ref_path}")
        return 1

    tracker = EnrichmentProgressTracker(enrichment_ref_path)

    # Execute based on arguments
    if args.export:
        tracker.export_report(args.export)
    elif args.campaign:
        tracker.print_campaign_dashboard(args.target_per_state)
    elif args.next:
        tracker.print_next_districts(args.next, args.state)
    elif args.state:
        tracker.print_overall_progress()
        tracker.print_state_progress(args.state)
    else:
        # Default: overall + top states
        tracker.print_overall_progress()
        tracker.print_state_progress(limit=15)

    return 0


if __name__ == "__main__":
    sys.exit(main())
