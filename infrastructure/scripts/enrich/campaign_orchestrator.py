#!/usr/bin/env python3
"""
Bell Schedule Enrichment Campaign Orchestrator

Size-stratified campaign driver for scaling bell schedule enrichment
from 192 to 400+ districts while improving statistical representativeness.

Strategy:
- Prioritize medium (1K-50K) and small (<1K) districts
- Avoid large districts (already at 54.8% coverage)
- Use school discovery for 5-10x success improvement
- Maintain geographic spread across all 50 multi-district states

Usage:
    # Dry run for 3 pilot states
    python campaign_orchestrator.py --states MI,PA,CA --dry-run

    # Execute pilot campaign
    python campaign_orchestrator.py --states MI,PA,CA

    # Full campaign (all 50 multi-district states)
    python campaign_orchestrator.py --full

    # Status check
    python campaign_orchestrator.py --status

Examples:
    # Test with 3 pilot states (expect ~12 new enrichments)
    python campaign_orchestrator.py --states MI,PA,CA --dry-run
    python campaign_orchestrator.py --states MI,PA,CA

    # Process 12 states in one session (~50 new enrichments)
    python campaign_orchestrator.py --states AL,AK,AZ,AR,CO,CT,DE,FL,GA,ID,IN,IA
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "database"))

from infrastructure.database.connection import session_scope
from infrastructure.database.queries import (
    get_target_districts,
    get_campaign_targets_by_state,
    get_size_distribution_summary,
    get_enrichment_summary,
    add_district_bell_schedules,
)
from infrastructure.database.models import District

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Single-district states at 100% coverage - cannot add more
SINGLE_DISTRICT_STATES = {'HI', 'PR'}

# Large states that get additional small district targets
LARGE_STATES = ['CA', 'TX', 'NY', 'FL', 'IL']


class CampaignOrchestrator:
    """
    Orchestrates size-stratified bell schedule enrichment campaigns.

    Coordinates the enrichment process across states, prioritizing
    medium and small districts to improve representativeness.
    """

    def __init__(
        self,
        tier: int = 2,
        year: str = "2024-25",
        medium_per_state: int = 4,
        small_per_large_state: int = 2,
    ):
        """
        Initialize the campaign orchestrator.

        Args:
            tier: Quality tier (1=detailed, 2=automated)
            year: School year for bell schedules
            medium_per_state: Target medium districts per state (default 4)
            small_per_large_state: Target small districts per large state (default 2)
        """
        self.tier = tier
        self.year = year
        self.medium_per_state = medium_per_state
        self.small_per_large_state = small_per_large_state

        # Statistics tracking
        self.stats = {
            'attempted': 0,
            'enriched': 0,
            'failed': 0,
            'skipped': 0,
            'by_state': {},
            'by_size': {'medium': 0, 'small': 0},
        }

    def get_all_states(self, session) -> List[str]:
        """Get all state codes from database."""
        results = session.query(District.state).distinct().order_by(District.state).all()
        return [r[0] for r in results]

    def run_campaign(
        self,
        session,
        states: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> Dict:
        """
        Run the enrichment campaign.

        Args:
            session: Database session
            states: Optional list of states to process (default: all)
            dry_run: If True, only show what would be done

        Returns:
            Statistics dict with results
        """
        # Import fetcher here to avoid circular imports and ensure scraper is checked lazily
        from fetch_bell_schedules import BellScheduleFetcher, check_scraper_health

        if not dry_run:
            if not check_scraper_health():
                logger.error("Scraper service not available")
                logger.info("Start the scraper: cd scraper && npm run dev")
                raise RuntimeError("Scraper service must be running for campaign")

        # Determine which states to process
        if states:
            target_states = [s.upper() for s in states if s.upper() not in SINGLE_DISTRICT_STATES]
        else:
            all_states = self.get_all_states(session)
            target_states = [s for s in all_states if s not in SINGLE_DISTRICT_STATES]

        logger.info(f"Campaign targeting {len(target_states)} states")
        logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")

        # Initialize fetcher
        fetcher = BellScheduleFetcher(tier=self.tier, year=self.year)

        # Phase 1: Medium districts (1K-50K), target per state
        logger.info(f"\n{'='*60}")
        logger.info("PHASE 1: Medium Districts (1K-50K enrollment)")
        logger.info(f"{'='*60}")

        for state in target_states:
            self._process_state(
                session=session,
                fetcher=fetcher,
                state=state,
                size_range=(1000, 50000),
                target_count=self.medium_per_state,
                size_category='medium',
                dry_run=dry_run,
            )

        # Phase 2: Small districts (500-1K) in large states
        logger.info(f"\n{'='*60}")
        logger.info("PHASE 2: Small Districts (500-1K enrollment) in Large States")
        logger.info(f"{'='*60}")

        for state in LARGE_STATES:
            if state in target_states or states is None:
                self._process_state(
                    session=session,
                    fetcher=fetcher,
                    state=state,
                    size_range=(500, 1000),
                    target_count=self.small_per_large_state,
                    size_category='small',
                    dry_run=dry_run,
                )

        # Summary
        self._print_summary()

        return self.stats

    def _process_state(
        self,
        session,
        fetcher,
        state: str,
        size_range: tuple,
        target_count: int,
        size_category: str,
        dry_run: bool,
    ):
        """Process districts for a single state."""
        logger.info(f"\n[{state}] Getting {target_count} {size_category} districts...")

        # Get target districts
        districts = get_target_districts(
            session=session,
            state=state,
            size_range=size_range,
            limit=target_count,
            exclude_large=True,
            year=self.year,
        )

        if not districts:
            logger.info(f"[{state}] No unenriched {size_category} districts found")
            return

        logger.info(f"[{state}] Found {len(districts)} candidate districts")

        if state not in self.stats['by_state']:
            self.stats['by_state'][state] = {'attempted': 0, 'enriched': 0}

        for district in districts:
            self.stats['attempted'] += 1
            self.stats['by_state'][state]['attempted'] += 1

            if dry_run:
                logger.info(
                    f"  [DRY RUN] Would attempt: {district.name} "
                    f"({district.enrollment:,} students)"
                )
                continue

            # Attempt enrichment
            try:
                result = fetcher.fetch_district_bell_schedules(
                    district_id=district.nces_id,
                    district_name=district.name,
                    state=district.state,
                    enrollment=district.enrollment,
                )

                if result and result.get('enriched'):
                    # Save to database
                    schedules = {
                        'elementary': result.get('elementary'),
                        'middle': result.get('middle'),
                        'high': result.get('high'),
                    }

                    add_district_bell_schedules(
                        session=session,
                        district_id=district.nces_id,
                        year=self.year,
                        schedules=schedules,
                        method=result.get('data_quality_tier', 'campaign_automated'),
                        created_by='campaign_orchestrator',
                    )
                    session.commit()

                    self.stats['enriched'] += 1
                    self.stats['by_state'][state]['enriched'] += 1
                    self.stats['by_size'][size_category] += 1

                    logger.info(
                        f"  ✓ Enriched: {district.name} "
                        f"({result.get('data_quality_tier', 'unknown')})"
                    )
                else:
                    self.stats['failed'] += 1
                    logger.info(f"  ✗ Failed: {district.name} (flagged for manual follow-up)")

            except Exception as e:
                self.stats['failed'] += 1
                logger.error(f"  ✗ Error processing {district.name}: {e}")

    def _print_summary(self):
        """Print campaign summary statistics."""
        logger.info(f"\n{'='*60}")
        logger.info("CAMPAIGN SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total attempted:  {self.stats['attempted']}")
        logger.info(f"Total enriched:   {self.stats['enriched']}")
        logger.info(f"Total failed:     {self.stats['failed']}")
        logger.info(f"Success rate:     {100*self.stats['enriched']/max(1,self.stats['attempted']):.1f}%")
        logger.info(f"\nBy Size Category:")
        logger.info(f"  Medium (1K-50K): {self.stats['by_size']['medium']}")
        logger.info(f"  Small (<1K):     {self.stats['by_size']['small']}")
        logger.info(f"\nBy State:")
        for state, data in sorted(self.stats['by_state'].items()):
            if data['attempted'] > 0:
                logger.info(f"  {state}: {data['enriched']}/{data['attempted']} enriched")
        logger.info(f"{'='*60}")


def print_status(session):
    """Print current enrichment status and campaign progress."""
    # Overall summary
    summary = get_enrichment_summary(session)

    print("=" * 60)
    print("BELL SCHEDULE ENRICHMENT STATUS")
    print("=" * 60)
    print(f"Total districts:     {summary['total_districts']:,}")
    print(f"Enriched districts:  {summary['enriched_districts']:,}")
    print(f"Coverage rate:       {summary['enrichment_rate']:.2f}%")
    print()

    # Size distribution
    print("SIZE DISTRIBUTION:")
    size_dist = get_size_distribution_summary(session)
    for category, data in size_dist.items():
        print(f"  {category}:")
        print(f"    Total:    {data['total']:,}")
        print(f"    Enriched: {data['enriched']:,}")
        print(f"    Coverage: {data['coverage_pct']:.1f}%")
    print()

    # Campaign targets remaining
    print("CAMPAIGN TARGETS (unenriched medium districts by state):")
    targets = get_campaign_targets_by_state(session, (1000, 50000), districts_per_state=4)
    states_with_targets = sum(1 for d in targets.values() if d)
    total_targets = sum(len(d) for d in targets.values())
    print(f"  States with targets: {states_with_targets}")
    print(f"  Total target districts: {total_targets}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Bell Schedule Enrichment Campaign Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--states',
        type=str,
        help='Comma-separated list of state codes (e.g., MI,PA,CA)'
    )

    parser.add_argument(
        '--full',
        action='store_true',
        help='Run full campaign across all 50 multi-district states'
    )

    parser.add_argument(
        '--status',
        action='store_true',
        help='Show current enrichment status and campaign progress'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually processing'
    )

    parser.add_argument(
        '--tier',
        type=int,
        choices=[1, 2],
        default=2,
        help='Quality tier (1=detailed, 2=automated, default: 2)'
    )

    parser.add_argument(
        '--year',
        type=str,
        default='2024-25',
        help='School year (default: 2024-25)'
    )

    parser.add_argument(
        '--medium-per-state',
        type=int,
        default=4,
        help='Target medium districts per state (default: 4)'
    )

    parser.add_argument(
        '--small-per-large-state',
        type=int,
        default=2,
        help='Target small districts per large state (default: 2)'
    )

    args = parser.parse_args()

    with session_scope() as session:
        if args.status:
            print_status(session)
            return

        # Parse states if provided
        states = None
        if args.states:
            states = [s.strip().upper() for s in args.states.split(',')]
        elif not args.full:
            parser.error("Must specify --states or --full")

        # Initialize orchestrator
        orchestrator = CampaignOrchestrator(
            tier=args.tier,
            year=args.year,
            medium_per_state=args.medium_per_state,
            small_per_large_state=args.small_per_large_state,
        )

        # Run campaign
        stats = orchestrator.run_campaign(
            session=session,
            states=states,
            dry_run=args.dry_run,
        )

        if not args.dry_run:
            logger.info("\n✓ Campaign complete!")
            logger.info(f"Enriched {stats['enriched']} new districts")


if __name__ == '__main__':
    main()
