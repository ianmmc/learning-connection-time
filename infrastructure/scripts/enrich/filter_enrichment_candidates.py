#!/usr/bin/env python3
"""
Smart District Filtering for Enrichment

Pre-filters enrichment candidates based on likelihood of success.
Avoids wasted attempts on districts unlikely to have accessible bell schedules.

Filtering Criteria:
    - District size (larger districts more likely to have public schedules)
    - Multiple grade levels (need elem+middle OR middle+high)
    - Not already in manual follow-up
    - State data availability patterns

Usage:
    # Filter enrichment candidates (update enrichment reference)
    python filter_enrichment_candidates.py

    # Preview filtering without updating
    python filter_enrichment_candidates.py --dry-run

    # Custom minimum enrollment
    python filter_enrichment_candidates.py --min-enrollment 500

    # Show filtering statistics
    python filter_enrichment_candidates.py --stats
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict
import pandas as pd

# Add utilities to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "utilities"))


class EnrichmentCandidateFilter:
    """Filter enrichment candidates for optimal success rate"""

    def __init__(
        self,
        enrichment_ref_path: Path,
        min_enrollment: int = 1000,
        require_multiple_levels: bool = True
    ):
        """
        Initialize candidate filter

        Args:
            enrichment_ref_path: Path to enrichment reference CSV
            min_enrollment: Minimum total enrollment
            require_multiple_levels: Require multiple grade levels
        """
        self.enrichment_ref_path = enrichment_ref_path
        self.min_enrollment = min_enrollment
        self.require_multiple_levels = require_multiple_levels

        # Load enrichment reference
        self.ref_df = pd.read_csv(enrichment_ref_path)

        # Load manual follow-up list
        self.manual_followup_path = Path("data/enriched/bell-schedules/manual_followup_needed.json")
        self.load_manual_followup()

        # State difficulty ratings (based on experience)
        # Higher score = easier to find bell schedules
        self.state_accessibility = {
            'CA': 5,  # Excellent data availability
            'TX': 5,  # Excellent data availability
            'FL': 4,  # Good data availability
            'NY': 4,  # Good data availability
            'IL': 3,  # Moderate
            'PA': 3,  # Moderate
            # Most states default to 3 (moderate)
        }

    def load_manual_followup(self):
        """Load manual follow-up list"""
        if self.manual_followup_path.exists():
            with open(self.manual_followup_path, 'r') as f:
                data = json.load(f)
                self.manual_followup_ids = [
                    d['district_id'] for d in data.get('districts', [])
                ]
        else:
            self.manual_followup_ids = []

    def filter_by_size(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter by minimum enrollment"""
        return df[df['enrollment_total'] >= self.min_enrollment]

    def filter_by_grade_levels(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter to districts with multiple grade levels

        Rationale: Districts serving only one level (e.g., only elementary)
        may not have distinct bell schedules or may be single-school districts
        without comprehensive online presence.
        """
        if not self.require_multiple_levels:
            return df

        # Require at least 2 of the 3 levels to have enrollment
        has_elem = df['enrollment_elementary'] > 0
        has_middle = df['enrollment_middle'] > 0
        has_high = df['enrollment_high'] > 0

        # Count how many levels have enrollment
        level_count = has_elem.astype(int) + has_middle.astype(int) + has_high.astype(int)

        return df[level_count >= 2]

    def filter_manual_followup(self, df: pd.DataFrame) -> pd.DataFrame:
        """Exclude districts already in manual follow-up"""
        return df[~df['district_id'].astype(str).isin(self.manual_followup_ids)]

    def add_priority_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add priority score for enrichment candidates

        Scoring factors:
        - Enrollment size (larger = higher priority for impact)
        - State accessibility (easier states = higher priority)
        - Already enriched (lower priority if state has many enriched)
        """
        df = df.copy()

        # Enrollment score (normalized 0-10)
        max_enrollment = df['enrollment_total'].max()
        df['enrollment_score'] = (df['enrollment_total'] / max_enrollment) * 10

        # State accessibility score
        df['state_score'] = df['state'].map(
            lambda s: self.state_accessibility.get(s, 3)
        )

        # Calculate state enrichment rate
        state_enrichment_rate = df.groupby('state')['enriched'].transform('mean')
        # Lower rate = higher priority for that state
        df['state_coverage_score'] = (1 - state_enrichment_rate) * 5

        # Combined priority score
        df['priority_score'] = (
            df['enrollment_score'] * 0.5 +  # 50% weight on size
            df['state_score'] * 0.3 +        # 30% weight on accessibility
            df['state_coverage_score'] * 0.2 # 20% weight on state coverage
        )

        return df

    def apply_filters(self, df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Apply all filters to enrichment candidates

        Args:
            df: Optional DataFrame to filter (default: use enrichment reference)

        Returns:
            Filtered DataFrame
        """
        if df is None:
            df = self.ref_df.copy()

        # Only filter unenriched districts
        df = df[~df['enriched']]

        print("Applying filters...")
        print(f"  Starting with: {len(df)} unenriched districts")

        # Apply filters
        df = self.filter_by_size(df)
        print(f"  After size filter (>={self.min_enrollment}): {len(df)} districts")

        df = self.filter_by_grade_levels(df)
        print(f"  After grade level filter: {len(df)} districts")

        df = self.filter_manual_followup(df)
        print(f"  After excluding manual follow-up: {len(df)} districts")

        # Add priority scoring
        df = self.add_priority_score(df)

        # Sort by priority score
        df = df.sort_values('priority_score', ascending=False)

        return df

    def get_top_candidates(
        self,
        n: int = 100,
        state: str = None
    ) -> pd.DataFrame:
        """
        Get top N enrichment candidates

        Args:
            n: Number of candidates to return
            state: Optional state filter

        Returns:
            DataFrame of top candidates
        """
        candidates = self.apply_filters()

        if state:
            candidates = candidates[candidates['state'] == state.upper()]

        return candidates.head(n)[[
            'district_id', 'district_name', 'state',
            'enrollment_total', 'enrollment_elementary',
            'enrollment_middle', 'enrollment_high',
            'priority_score'
        ]]

    def update_enrichment_reference(
        self,
        mark_filtered: bool = True,
        dry_run: bool = False
    ):
        """
        Update enrichment reference with filtering results

        Args:
            mark_filtered: Add 'priority' field to enrichment reference
            dry_run: Preview without saving
        """
        candidates = self.apply_filters(self.ref_df)

        if mark_filtered:
            # Reset priority to 0
            self.ref_df['priority'] = 0

            # Set priority based on filtering
            # Priority > 0 = good candidate
            # Priority 0 = filtered out
            candidate_ids = candidates['district_id'].astype(str).tolist()
            self.ref_df.loc[
                self.ref_df['district_id'].astype(str).isin(candidate_ids),
                'priority'
            ] = 1

            # Add priority scores to top candidates
            for idx, row in candidates.iterrows():
                self.ref_df.loc[
                    self.ref_df['district_id'] == row['district_id'],
                    'priority'
                ] = int(row['priority_score'])

        if not dry_run:
            self.ref_df.to_csv(self.enrichment_ref_path, index=False)
            print(f"\n✓ Updated enrichment reference file")

    def print_filter_stats(self):
        """Print filtering statistics"""
        # Original counts
        total = len(self.ref_df)
        unenriched = (~self.ref_df['enriched']).sum()

        # After filtering
        candidates = self.apply_filters()

        print("\n" + "=" * 60)
        print("FILTERING STATISTICS")
        print("=" * 60)
        print(f"Total districts: {total:,}")
        print(f"Already enriched: {total - unenriched:,}")
        print(f"Unenriched: {unenriched:,}")
        print(f"\nAfter filtering:")
        print(f"  Good candidates: {len(candidates):,}")
        print(f"  Filtered out: {unenriched - len(candidates):,}")
        print(f"  Success rate improvement: {len(candidates)/unenriched*100:.1f}% of attempts")
        print("=" * 60)

        # Show top states
        print("\nTop 10 states by candidate count:")
        state_counts = candidates['state'].value_counts().head(10)
        for state, count in state_counts.items():
            print(f"  {state}: {count} candidates")

        print("\n" + "=" * 60)

    def export_candidate_list(
        self,
        output_path: Path,
        n: int = 500,
        state: str = None
    ):
        """
        Export top candidates to CSV

        Args:
            output_path: Output file path
            n: Number of candidates to export
            state: Optional state filter
        """
        candidates = self.get_top_candidates(n, state)
        candidates.to_csv(output_path, index=False)
        print(f"✓ Exported {len(candidates)} candidates to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Filter enrichment candidates for optimal success",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--min-enrollment',
        type=int,
        default=1000,
        help="Minimum district enrollment (default: 1000)"
    )
    parser.add_argument(
        '--allow-single-level',
        action='store_true',
        help="Allow districts with only one grade level"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Preview filtering without updating files"
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help="Show filtering statistics"
    )
    parser.add_argument(
        '--export',
        type=Path,
        metavar='FILE',
        help="Export top candidates to CSV"
    )
    parser.add_argument(
        '--top-n',
        type=int,
        default=500,
        help="Number of candidates to export (default: 500)"
    )
    parser.add_argument(
        '--state',
        help="Filter by state for export"
    )

    args = parser.parse_args()

    # Initialize filter
    enrichment_ref_path = Path('data/processed/normalized/enrichment_reference.csv')

    if not enrichment_ref_path.exists():
        print(f"Error: Enrichment reference file not found: {enrichment_ref_path}")
        return 1

    filter_tool = EnrichmentCandidateFilter(
        enrichment_ref_path=enrichment_ref_path,
        min_enrollment=args.min_enrollment,
        require_multiple_levels=not args.allow_single_level
    )

    # Execute based on arguments
    if args.stats:
        filter_tool.print_filter_stats()
    elif args.export:
        filter_tool.export_candidate_list(
            output_path=args.export,
            n=args.top_n,
            state=args.state
        )
    else:
        # Default: update enrichment reference
        filter_tool.update_enrichment_reference(
            mark_filtered=True,
            dry_run=args.dry_run
        )

        if not args.dry_run:
            # Show stats after updating
            filter_tool.print_filter_stats()

    return 0


if __name__ == "__main__":
    sys.exit(main())
