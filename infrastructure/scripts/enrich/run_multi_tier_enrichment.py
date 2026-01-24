#!/usr/bin/env python3
"""
Multi-Tier Bell Schedule Enrichment - Master Orchestrator
Runs the complete 5-tier enrichment workflow

Tier Escalation Flow:
    Tier 1 (Local Discovery) → Tier 2 (HTML Extraction) → Tier 3 (PDF/OCR)
    → Tier 4 (Claude Desktop) → Tier 5 (Gemini MCP) → Manual Review

Usage:
    # Process all pending districts
    python run_multi_tier_enrichment.py

    # Process specific districts
    python run_multi_tier_enrichment.py --districts 0622710 3623370 3003290

    # Run specific tiers only
    python run_multi_tier_enrichment.py --tiers 1 2 3

    # Dry run (no changes)
    python run_multi_tier_enrichment.py --dry-run

    # Set batch sizes
    python run_multi_tier_enrichment.py --tier1-batch-size 50 --tier4-batch-size 15
"""

import argparse
import logging
import sys
import time
from typing import List, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from infrastructure.database.connection import session_scope
from infrastructure.database.enrichment_queue_manager import EnrichmentQueueManager
from infrastructure.database.batch_composer import BatchComposer
from infrastructure.database.verification import (
    generate_handoff_report,
    check_audit_integrity,
    detect_count_discrepancy
)
from infrastructure.scripts.enrich.tier_1_processor import Tier1Processor
from infrastructure.scripts.enrich.tier_2_processor import Tier2Processor
from infrastructure.scripts.enrich.tier_3_processor import Tier3Processor
from infrastructure.scripts.enrich.tier_4_processor import Tier4Processor
from infrastructure.scripts.enrich.tier_5_processor import Tier5Processor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('multi_tier_enrichment.log')
    ]
)
logger = logging.getLogger(__name__)


class MultiTierOrchestrator:
    """Orchestrates the complete multi-tier enrichment workflow"""

    def __init__(
        self,
        max_cost_dollars: float = None,
        dry_run: bool = False
    ):
        """
        Initialize orchestrator

        Args:
            max_cost_dollars: Optional budget limit
            dry_run: If True, simulate without making changes
        """
        self.max_cost_dollars = max_cost_dollars
        self.dry_run = dry_run
        self.stats = {
            'tier_1': {'processed': 0, 'successful': 0, 'escalated': 0},
            'tier_2': {'processed': 0, 'successful': 0, 'escalated': 0},
            'tier_3': {'processed': 0, 'successful': 0, 'escalated': 0},
            'tier_4': {'processed': 0, 'successful': 0, 'escalated': 0},
            'tier_5': {'processed': 0, 'successful': 0, 'manual_review': 0}
        }

    def run(
        self,
        district_ids: Optional[List[str]] = None,
        tiers_to_run: List[int] = None,
        tier1_batch_size: int = 50,
        tier2_batch_size: int = 50,
        tier3_batch_size: int = 20,
        tier4_batch_size: int = 15,
        tier5_batch_size: int = 15
    ):
        """
        Run multi-tier enrichment workflow

        Args:
            district_ids: Optional list of specific districts to process
            tiers_to_run: Optional list of tiers to run (default: all)
            tier1_batch_size: Batch size for Tier 1
            tier2_batch_size: Batch size for Tier 2
            tier3_batch_size: Batch size for Tier 3
            tier4_batch_size: Batch size for Tier 4
            tier5_batch_size: Batch size for Tier 5
        """
        logger.info("=" * 80)
        logger.info("MULTI-TIER BELL SCHEDULE ENRICHMENT")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info(f"Max cost: ${self.max_cost_dollars}" if self.max_cost_dollars else "Max cost: Unlimited")
        logger.info("=" * 80)

        if tiers_to_run is None:
            tiers_to_run = [1, 2, 3, 4, 5]

        with session_scope() as session:
            queue_manager = EnrichmentQueueManager(session, self.max_cost_dollars)

            # Add districts to queue if specified
            if district_ids:
                logger.info(f"Adding {len(district_ids)} districts to queue...")
                added = queue_manager.add_districts(district_ids)
                logger.info(f"Added {added} districts to queue")

            # Print initial status
            status = queue_manager.get_status()
            logger.info(f"\nInitial queue status:")
            logger.info(f"  Total districts: {status['summary'].get('total_districts', 0)}")
            logger.info(f"  Pending: {status['summary'].get('pending', 0)}")
            logger.info(f"  Processing: {status['summary'].get('processing', 0)}")
            logger.info(f"  Completed: {status['summary'].get('completed', 0)}")
            logger.info("")

            # Process tiers
            if 1 in tiers_to_run:
                self._process_tier_1(queue_manager, tier1_batch_size)

            if 2 in tiers_to_run:
                self._process_tier_2(queue_manager, tier2_batch_size)

            if 3 in tiers_to_run:
                self._process_tier_3(queue_manager, tier3_batch_size)

            if 4 in tiers_to_run:
                self._process_tier_4(queue_manager, tier4_batch_size)

            if 5 in tiers_to_run:
                self._process_tier_5(queue_manager, tier5_batch_size)

            # Print final status
            self._print_summary(queue_manager)

    def _process_tier_1(self, queue_manager: EnrichmentQueueManager, batch_size: int):
        """Process Tier 1: Local Discovery"""
        logger.info("\n" + "=" * 80)
        logger.info("TIER 1: LOCAL DISCOVERY (Playwright)")
        logger.info("=" * 80)

        depth = queue_manager.get_queue_depth(1)
        if depth == 0:
            logger.info("No districts pending at Tier 1")
            return

        logger.info(f"Processing {depth} districts...")

        result = queue_manager.process_tier_1_batch(
            batch_size=batch_size,
            dry_run=self.dry_run
        )

        self.stats['tier_1'] = result
        logger.info(f"Tier 1 complete: {result}")

    def _process_tier_2(self, queue_manager: EnrichmentQueueManager, batch_size: int):
        """Process Tier 2: HTML Extraction"""
        logger.info("\n" + "=" * 80)
        logger.info("TIER 2: LOCAL EXTRACTION (HTML Parsing)")
        logger.info("=" * 80)

        depth = queue_manager.get_queue_depth(2)
        if depth == 0:
            logger.info("No districts pending at Tier 2")
            return

        logger.info(f"Processing {depth} districts...")

        result = queue_manager.process_tier_2_batch(
            batch_size=batch_size,
            dry_run=self.dry_run
        )

        self.stats['tier_2'] = result
        logger.info(f"Tier 2 complete: {result}")

    def _process_tier_3(self, queue_manager: EnrichmentQueueManager, batch_size: int):
        """Process Tier 3: PDF/OCR"""
        logger.info("\n" + "=" * 80)
        logger.info("TIER 3: LOCAL PDF/OCR EXTRACTION")
        logger.info("=" * 80)

        depth = queue_manager.get_queue_depth(3)
        if depth == 0:
            logger.info("No districts pending at Tier 3")
            return

        logger.info(f"Processing {depth} districts...")

        result = queue_manager.process_tier_3_batch(
            batch_size=batch_size,
            dry_run=self.dry_run
        )

        self.stats['tier_3'] = result
        logger.info(f"Tier 3 complete: {result}")

    def _process_tier_4(self, queue_manager: EnrichmentQueueManager, batch_size: int):
        """Process Tier 4: Claude Desktop"""
        logger.info("\n" + "=" * 80)
        logger.info("TIER 4: CLAUDE DESKTOP PROCESSING (Batched)")
        logger.info("=" * 80)

        depth = queue_manager.get_queue_depth(4)
        if depth == 0:
            logger.info("No districts pending at Tier 4")
            return

        logger.info(f"Preparing batches for {depth} districts...")

        # Prepare batches
        batches = queue_manager.prepare_tier_4_batches(batch_size=batch_size)

        if not batches:
            logger.info("No batches ready for Tier 4")
            return

        logger.info(f"Created {len(batches)} batches")

        if self.dry_run:
            logger.info("DRY RUN: Would present batches to Claude for processing")
            self.stats['tier_4'] = {
                'batches_prepared': len(batches),
                'districts': sum(b['district_count'] for b in batches)
            }
        else:
            logger.warning("\n" + "!" * 80)
            logger.warning("TIER 4 REQUIRES MANUAL CLAUDE INTERACTION")
            logger.warning("Batches have been prepared and logged to files.")
            logger.warning("Present these batches to Claude in conversation for processing.")
            logger.warning("!" * 80)

            # Save batches to files
            for i, batch in enumerate(batches, 1):
                from infrastructure.scripts.enrich.tier_4_processor import Tier4Processor
                with session_scope() as session:
                    processor = Tier4Processor(session)
                    request_text = processor.format_batch_request(batch)

                    filename = f"tier_4_batch_{batch['batch_id']:03d}.txt"
                    with open(filename, 'w') as f:
                        f.write(request_text)

                    logger.info(f"Batch {i}/{len(batches)} saved to: {filename}")

    def _process_tier_5(self, queue_manager: EnrichmentQueueManager, batch_size: int):
        """Process Tier 5: Gemini MCP"""
        logger.info("\n" + "=" * 80)
        logger.info("TIER 5: GEMINI MCP WEB SEARCH (Batched)")
        logger.info("=" * 80)

        depth = queue_manager.get_queue_depth(5)
        if depth == 0:
            logger.info("No districts pending at Tier 5")
            return

        logger.info(f"Preparing batches for {depth} districts...")

        # Prepare batches
        batches = queue_manager.prepare_tier_5_batches(batch_size=batch_size)

        if not batches:
            logger.info("No batches ready for Tier 5")
            return

        logger.info(f"Created {len(batches)} batches")

        if self.dry_run:
            logger.info("DRY RUN: Would process batches via Gemini MCP")
            self.stats['tier_5'] = {
                'batches_prepared': len(batches),
                'districts': sum(b['district_count'] for b in batches)
            }
        else:
            logger.warning("\n" + "!" * 80)
            logger.warning("TIER 5: GEMINI MCP NOT YET IMPLEMENTED")
            logger.warning("Batches have been prepared. Integration pending.")
            logger.warning("!" * 80)

    def _print_summary(self, queue_manager: EnrichmentQueueManager):
        """Print final summary"""
        logger.info("\n" + "=" * 80)
        logger.info("ENRICHMENT SUMMARY")
        logger.info("=" * 80)

        # Get final status
        status = queue_manager.get_status()

        logger.info("\nQueue Status:")
        logger.info(f"  Total districts: {status['summary'].get('total_districts', 0)}")
        logger.info(f"  Completed: {status['summary'].get('completed', 0)}")
        logger.info(f"  Processing: {status['summary'].get('processing', 0)}")
        logger.info(f"  Pending: {status['summary'].get('pending', 0)}")
        logger.info(f"  Manual review: {status['summary'].get('manual_review', 0)}")

        logger.info("\nTier Performance:")
        for tier in range(1, 6):
            stats = self.stats.get(f'tier_{tier}', {})
            if stats:
                logger.info(f"  Tier {tier}: {stats}")

        logger.info("\nEstimated Cost:")
        logger.info(f"  Current: ${status.get('current_cost', 0):.2f}")
        logger.info(f"  Budget: ${status.get('budget_limit') or 'Unlimited'}")

        # Run verification checks (REQ-035, REQ-036, REQ-037)
        self._run_verification(queue_manager.session)

        logger.info("\n" + "=" * 80)
        logger.info("ENRICHMENT COMPLETE")
        logger.info("=" * 80)

    def _run_verification(self, session):
        """
        Run post-enrichment verification checks (REQ-035, REQ-036, REQ-037).

        This safeguard was added after 'The Case of the Missing Bell Schedules'
        investigation (Jan 24, 2026) to prevent AI hallucination of enrichment counts.
        """
        logger.info("\n" + "=" * 80)
        logger.info("VERIFICATION CHECKS (Post-Enrichment)")
        logger.info("=" * 80)

        try:
            # Generate verified report from database
            report = generate_handoff_report(session)

            logger.info(f"\nVerified Database State:")
            logger.info(f"  Enriched districts: {report['enriched_districts']}")
            logger.info(f"  States with data: {report['states_with_enrichment']}")
            logger.info(f"  Database snapshot: {report['verified_at']}")

            # Check audit trail integrity
            integrity = check_audit_integrity(session)

            logger.info(f"\nAudit Trail Integrity: {integrity['integrity_status'].upper()}")
            logger.info(f"  Completeness: {integrity['completeness_percent']:.1f}%")

            if integrity['violations']:
                logger.warning("  Violations detected:")
                for v in integrity['violations']:
                    logger.warning(f"    - {v['type']}: {v['message']}")

            # Log date distribution for verification
            if report.get('date_distribution'):
                logger.info(f"\nRecords by date:")
                for date, count in sorted(report['date_distribution'].items())[-5:]:
                    logger.info(f"    {date}: {count} records")

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            logger.warning("Proceeding without verification - CHECK DATABASE MANUALLY")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Multi-Tier Bell Schedule Enrichment Orchestrator"
    )

    parser.add_argument(
        '--districts',
        nargs='+',
        help='Specific district NCES IDs to process'
    )

    parser.add_argument(
        '--tiers',
        type=int,
        nargs='+',
        choices=[1, 2, 3, 4, 5],
        help='Specific tiers to run (default: all)'
    )

    parser.add_argument(
        '--tier1-batch-size',
        type=int,
        default=50,
        help='Batch size for Tier 1 (default: 50)'
    )

    parser.add_argument(
        '--tier2-batch-size',
        type=int,
        default=50,
        help='Batch size for Tier 2 (default: 50)'
    )

    parser.add_argument(
        '--tier3-batch-size',
        type=int,
        default=20,
        help='Batch size for Tier 3 (default: 20)'
    )

    parser.add_argument(
        '--tier4-batch-size',
        type=int,
        default=15,
        help='Batch size for Tier 4 (default: 15)'
    )

    parser.add_argument(
        '--tier5-batch-size',
        type=int,
        default=15,
        help='Batch size for Tier 5 (default: 15)'
    )

    parser.add_argument(
        '--max-cost',
        type=float,
        help='Maximum cost in dollars for API tiers'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate without making changes'
    )

    args = parser.parse_args()

    # Create orchestrator
    orchestrator = MultiTierOrchestrator(
        max_cost_dollars=args.max_cost,
        dry_run=args.dry_run
    )

    # Run workflow
    orchestrator.run(
        district_ids=args.districts,
        tiers_to_run=args.tiers,
        tier1_batch_size=args.tier1_batch_size,
        tier2_batch_size=args.tier2_batch_size,
        tier3_batch_size=args.tier3_batch_size,
        tier4_batch_size=args.tier4_batch_size,
        tier5_batch_size=args.tier5_batch_size
    )


if __name__ == '__main__':
    main()
