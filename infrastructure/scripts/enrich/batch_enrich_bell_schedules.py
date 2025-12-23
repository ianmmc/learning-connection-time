#!/usr/bin/env python3
"""
Batch Bell Schedule Enrichment Script

Efficiently enriches multiple districts with bell schedule data in a single session.
Includes checkpoint/resume capability, progress tracking, and auto-updates to the
enrichment reference file.

Usage:
    # Enrich next 10 districts in Wyoming
    python batch_enrich_bell_schedules.py --state WY --batch-size 10

    # Resume previous batch
    python batch_enrich_bell_schedules.py --resume

    # Campaign mode: 3 districts per state
    python batch_enrich_bell_schedules.py --campaign --districts-per-state 3

    # Specific district list
    python batch_enrich_bell_schedules.py --districts 5605302,5601470,5604510

Features:
    - Checkpoint/resume capability (saves after each district)
    - Auto-updates enrichment reference file
    - Progress reporting
    - Follows ONE-attempt protocol for blocked districts
    - Uses lightweight enrichment reference file (90% token savings)
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd

# Add utilities to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "utilities"))
from common import standardize_state

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BatchEnricher:
    """Batch enrichment manager with checkpoint/resume"""

    def __init__(
        self,
        enrichment_ref_path: Path,
        batch_size: int = 10,
        tier: int = 2,
        year: str = "2023-24"
    ):
        """
        Initialize batch enricher

        Args:
            enrichment_ref_path: Path to enrichment reference CSV
            batch_size: Number of districts to process per batch
            tier: Bell schedule quality tier (1=detailed, 2=automated, 3=statutory)
            year: School year
        """
        self.enrichment_ref_path = enrichment_ref_path
        self.batch_size = batch_size
        self.tier = tier
        self.year = year

        # Load enrichment reference (lightweight!)
        self.ref_df = pd.read_csv(enrichment_ref_path)
        logger.info(f"Loaded enrichment reference: {len(self.ref_df)} districts")

        # Paths
        self.bell_schedules_dir = Path("data/enriched/bell-schedules")
        self.bell_schedules_dir.mkdir(parents=True, exist_ok=True)

        self.checkpoint_path = self.bell_schedules_dir / "batch_checkpoint.json"
        self.manual_followup_path = self.bell_schedules_dir / "manual_followup_needed.json"

        # Stats
        self.stats = {
            "attempted": 0,
            "enriched": 0,
            "failed": 0,
            "manual_followup": 0,
            "start_time": datetime.now().isoformat()
        }

        # Load manual follow-up list
        self.load_manual_followup()

    def load_manual_followup(self):
        """Load manual follow-up list"""
        if self.manual_followup_path.exists():
            with open(self.manual_followup_path, 'r') as f:
                self.manual_followup = json.load(f)
        else:
            self.manual_followup = {"districts": [], "last_updated": None}

    def save_manual_followup(self):
        """Save manual follow-up list"""
        self.manual_followup['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.manual_followup_path, 'w') as f:
            json.dump(self.manual_followup, f, indent=2)

    def add_to_manual_followup(
        self,
        district_row: pd.Series,
        reason: str,
        methods_tried: List[str],
        notes: str = ""
    ):
        """Add district to manual follow-up list"""
        entry = {
            "district_id": str(district_row['district_id']),
            "district_name": district_row['district_name'],
            "state": district_row['state'],
            "enrollment": int(district_row['enrollment_total']),
            "reason": reason,
            "attempts": [{
                "date": datetime.now().strftime("%Y-%m-%d"),
                "methods_tried": methods_tried,
                "notes": notes
            }],
            "suggested_action": "Manual contact or alternative access method",
            "priority": "medium",
            "added_date": datetime.now().strftime("%Y-%m-%d")
        }

        # Check if already exists
        existing_ids = [d['district_id'] for d in self.manual_followup['districts']]
        if entry['district_id'] not in existing_ids:
            self.manual_followup['districts'].append(entry)
            self.save_manual_followup()
            logger.info(f"  Added to manual follow-up: {district_row['district_name']}")

    def get_next_batch(
        self,
        state: Optional[str] = None,
        district_ids: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get next batch of unenriched districts

        Args:
            state: Filter by state code
            district_ids: Specific district IDs to process

        Returns:
            DataFrame of districts to enrich
        """
        if district_ids:
            # Process specific districts
            batch = self.ref_df[
                self.ref_df['district_id'].astype(str).isin(district_ids)
            ]
        else:
            # Get unenriched districts
            pending = self.ref_df[~self.ref_df['enriched']]

            if state:
                pending = pending[pending['state'] == state.upper()]

            # Sort by enrollment (largest first)
            pending = pending.sort_values('enrollment_total', ascending=False)

            batch = pending.head(self.batch_size)

        return batch

    def save_checkpoint(self, current_index: int, batch_info: Dict):
        """Save checkpoint for resume capability"""
        checkpoint = {
            "timestamp": datetime.now().isoformat(),
            "current_index": current_index,
            "batch_info": batch_info,
            "stats": self.stats
        }

        with open(self.checkpoint_path, 'w') as f:
            json.dump(checkpoint, f, indent=2)

    def load_checkpoint(self) -> Optional[Dict]:
        """Load checkpoint if exists"""
        if self.checkpoint_path.exists():
            with open(self.checkpoint_path, 'r') as f:
                return json.load(f)
        return None

    def clear_checkpoint(self):
        """Clear checkpoint file"""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

    def update_enrichment_reference(self, district_id: str, enriched: bool = True):
        """Update enrichment reference file"""
        self.ref_df.loc[
            self.ref_df['district_id'].astype(str) == str(district_id),
            'enriched'
        ] = enriched

        # Save to disk
        self.ref_df.to_csv(self.enrichment_ref_path, index=False)

    def enrich_district(self, district_row: pd.Series) -> Tuple[bool, str]:
        """
        Enrich a single district

        This is a PLACEHOLDER that returns instructions for manual enrichment.
        In a real implementation, this would call web search, download, and OCR tools.

        For now, this shows the structure and returns success=False to demonstrate
        the checkpoint/tracking system.

        Args:
            district_row: Row from enrichment reference DataFrame

        Returns:
            Tuple of (success, message)
        """
        district_id = str(district_row['district_id'])
        district_name = district_row['district_name']
        state = district_row['state']

        logger.info(f"\n{'='*60}")
        logger.info(f"Enriching: {district_name} ({state})")
        logger.info(f"District ID: {district_id}")
        logger.info(f"Enrollment: {district_row['enrollment_total']:.0f} total")
        logger.info(f"  Elementary: {district_row['enrollment_elementary']:.0f}")
        logger.info(f"  Middle: {district_row['enrollment_middle']:.0f}")
        logger.info(f"  High: {district_row['enrollment_high']:.0f}")
        logger.info(f"{'='*60}")

        # PLACEHOLDER: In real implementation, this would:
        # 1. WebSearch for bell schedules
        # 2. Evaluate results for security blocks (ONE attempt rule)
        # 3. Download documents (curl to /tmp/)
        # 4. Process locally (tesseract/pdftotext/pup)
        # 5. Extract times and calculate minutes
        # 6. Save enrichment JSON
        # 7. Return (True, "Enriched successfully")

        # For now, return placeholder response
        logger.info("PLACEHOLDER: Manual enrichment required")
        logger.info("  Follow these steps:")
        logger.info(f"  1. WebSearch('{district_name} {state} bell schedule {self.year}')")
        logger.info("  2. Check for security blocks (Cloudflare/WAF/404s)")
        logger.info("  3. If blocked → Add to manual follow-up")
        logger.info("  4. If accessible → Download with curl")
        logger.info("  5. Process locally (tesseract for images, pdftotext for PDFs)")
        logger.info("  6. Save JSON to data/enriched/bell-schedules/{district_id}_{year}.json")

        # Return False to show this needs manual work
        # (Change to True when actual enrichment logic is implemented)
        return False, "Manual enrichment required (placeholder)"

    def enrich_batch(
        self,
        state: Optional[str] = None,
        district_ids: Optional[List[str]] = None,
        resume: bool = False
    ) -> Dict:
        """
        Enrich a batch of districts with checkpoint/resume

        Args:
            state: Filter by state
            district_ids: Specific districts to process
            resume: Resume from checkpoint

        Returns:
            Statistics dictionary
        """
        # Handle resume
        start_index = 0
        if resume:
            checkpoint = self.load_checkpoint()
            if checkpoint:
                logger.info(f"Resuming from checkpoint: {checkpoint['timestamp']}")
                start_index = checkpoint['current_index'] + 1
                self.stats = checkpoint['stats']

        # Get batch
        batch = self.get_next_batch(state, district_ids)

        if batch.empty:
            logger.warning("No districts to enrich")
            return self.stats

        logger.info(f"\n{'='*60}")
        logger.info(f"BATCH ENRICHMENT")
        logger.info(f"{'='*60}")
        logger.info(f"Districts in batch: {len(batch)}")
        logger.info(f"Starting from index: {start_index}")
        if state:
            logger.info(f"State filter: {state}")
        logger.info(f"Tier: {self.tier}")
        logger.info(f"Year: {self.year}")
        logger.info(f"{'='*60}\n")

        # Process each district
        for idx, (_, district) in enumerate(batch.iterrows()):
            if idx < start_index:
                continue

            district_id = str(district['district_id'])

            try:
                self.stats['attempted'] += 1

                # Enrich district
                success, message = self.enrich_district(district)

                if success:
                    # Update tracking
                    self.update_enrichment_reference(district_id, enriched=True)
                    self.stats['enriched'] += 1
                    logger.info(f"✓ Enriched: {district['district_name']}")
                else:
                    # Failed - this is normal for placeholder
                    self.stats['failed'] += 1
                    logger.warning(f"✗ Failed: {message}")

                # Save checkpoint after each district
                batch_info = {
                    "state": state,
                    "batch_size": len(batch),
                    "district_ids": batch['district_id'].astype(str).tolist()
                }
                self.save_checkpoint(idx, batch_info)

            except Exception as e:
                logger.error(f"Error enriching {district['district_name']}: {e}")
                self.stats['failed'] += 1
                continue

        # Clear checkpoint when batch complete
        self.clear_checkpoint()

        # Calculate summary stats
        self.stats['end_time'] = datetime.now().isoformat()
        self.stats['duration_seconds'] = (
            datetime.fromisoformat(self.stats['end_time']) -
            datetime.fromisoformat(self.stats['start_time'])
        ).total_seconds()

        return self.stats

    def campaign_mode(self, districts_per_state: int = 3, states: Optional[List[str]] = None):
        """
        Campaign mode: Enrich N districts per state in population order

        Args:
            districts_per_state: Target enrichments per state
            states: Optional list of states to process (default: all in population order)
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"CAMPAIGN MODE")
        logger.info(f"{'='*60}")
        logger.info(f"Target: {districts_per_state} districts per state")
        logger.info(f"{'='*60}\n")

        # State population order (from enrichment campaign plan)
        state_order = [
            'WY', 'VT', 'DC', 'AK', 'ND', 'SD', 'DE', 'RI', 'MT', 'ME',
            'NH', 'HI', 'WV', 'ID', 'NE', 'NM', 'KS', 'MS', 'AR', 'NV',
            'IA', 'UT', 'CT', 'OK', 'OR', 'KY', 'LA', 'SC', 'AL', 'CO',
            'MN', 'WI', 'MD', 'MO', 'TN', 'IN', 'MA', 'AZ', 'WA', 'VA',
            'NJ', 'NC', 'GA', 'MI', 'OH', 'IL', 'PA', 'NY', 'FL', 'TX', 'CA'
        ]

        if states:
            # Use provided state list
            state_order = [s.upper() for s in states]

        total_campaign_stats = {
            "states_processed": 0,
            "total_enriched": 0,
            "total_failed": 0,
            "total_manual_followup": 0
        }

        for state in state_order:
            # Check how many already enriched
            state_df = self.ref_df[self.ref_df['state'] == state]
            already_enriched = state_df['enriched'].sum()

            if already_enriched >= districts_per_state:
                logger.info(f"✓ {state}: Already has {already_enriched}/{districts_per_state} enriched, skipping")
                continue

            # Calculate how many needed
            needed = districts_per_state - already_enriched

            logger.info(f"\n{'='*60}")
            logger.info(f"STATE: {state}")
            logger.info(f"Already enriched: {already_enriched}/{districts_per_state}")
            logger.info(f"Need to enrich: {needed}")
            logger.info(f"{'='*60}\n")

            # Enrich batch for this state
            self.batch_size = needed
            stats = self.enrich_batch(state=state)

            total_campaign_stats['states_processed'] += 1
            total_campaign_stats['total_enriched'] += stats['enriched']
            total_campaign_stats['total_failed'] += stats['failed']

            logger.info(f"\n{state} complete: {stats['enriched']} enriched, {stats['failed']} failed\n")

        logger.info(f"\n{'='*60}")
        logger.info(f"CAMPAIGN COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"States processed: {total_campaign_stats['states_processed']}")
        logger.info(f"Total enriched: {total_campaign_stats['total_enriched']}")
        logger.info(f"Total failed: {total_campaign_stats['total_failed']}")
        logger.info(f"{'='*60}\n")

        return total_campaign_stats

    def print_summary(self):
        """Print summary statistics"""
        logger.info(f"\n{'='*60}")
        logger.info(f"BATCH ENRICHMENT SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Attempted: {self.stats['attempted']}")
        logger.info(f"Enriched: {self.stats['enriched']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Manual follow-up: {len(self.manual_followup['districts'])}")

        if 'duration_seconds' in self.stats:
            logger.info(f"Duration: {self.stats['duration_seconds']:.1f} seconds")
            if self.stats['enriched'] > 0:
                avg_time = self.stats['duration_seconds'] / self.stats['enriched']
                logger.info(f"Avg time per district: {avg_time:.1f} seconds")

        logger.info(f"{'='*60}\n")

        # Show current enrichment status
        total = len(self.ref_df)
        enriched = self.ref_df['enriched'].sum()
        pending = total - enriched

        logger.info(f"Overall enrichment status:")
        logger.info(f"  Total districts: {total}")
        logger.info(f"  Enriched: {enriched} ({enriched/total*100:.1f}%)")
        logger.info(f"  Pending: {pending} ({pending/total*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description="Batch enrich districts with bell schedules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Enrich next 10 districts in Wyoming
    python batch_enrich_bell_schedules.py --state WY --batch-size 10

    # Resume previous batch
    python batch_enrich_bell_schedules.py --resume

    # Campaign mode: 3 districts per state
    python batch_enrich_bell_schedules.py --campaign --districts-per-state 3

    # Specific districts
    python batch_enrich_bell_schedules.py --districts 5605302,5601470,5604510
        """
    )

    parser.add_argument(
        '--state',
        help="Filter by state code (e.g., WY, CA, TX)"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help="Number of districts to process (default: 10)"
    )
    parser.add_argument(
        '--districts',
        help="Comma-separated list of specific district IDs to process"
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help="Resume from last checkpoint"
    )
    parser.add_argument(
        '--campaign',
        action='store_true',
        help="Campaign mode: process states in population order"
    )
    parser.add_argument(
        '--districts-per-state',
        type=int,
        default=3,
        help="Districts per state in campaign mode (default: 3)"
    )
    parser.add_argument(
        '--tier',
        type=int,
        choices=[1, 2, 3],
        default=2,
        help="Quality tier: 1=detailed, 2=automated, 3=statutory (default: 2)"
    )
    parser.add_argument(
        '--year',
        default="2023-24",
        help="School year (default: 2023-24)"
    )

    args = parser.parse_args()

    # Initialize batch enricher
    enrichment_ref_path = Path('data/processed/normalized/enrichment_reference.csv')

    if not enrichment_ref_path.exists():
        logger.error(f"Enrichment reference file not found: {enrichment_ref_path}")
        logger.error("Run the pipeline or create it first")
        return 1

    enricher = BatchEnricher(
        enrichment_ref_path=enrichment_ref_path,
        batch_size=args.batch_size,
        tier=args.tier,
        year=args.year
    )

    # Execute based on mode
    if args.campaign:
        # Campaign mode
        enricher.campaign_mode(districts_per_state=args.districts_per_state)
    else:
        # Batch mode
        district_ids = None
        if args.districts:
            district_ids = args.districts.split(',')

        enricher.enrich_batch(
            state=args.state,
            district_ids=district_ids,
            resume=args.resume
        )

    # Print summary
    enricher.print_summary()

    return 0


if __name__ == "__main__":
    sys.exit(main())
