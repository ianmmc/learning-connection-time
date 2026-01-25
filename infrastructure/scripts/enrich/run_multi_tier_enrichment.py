#!/usr/bin/env python3
"""
Multi-Tier Bell Schedule Enrichment - Master Orchestrator
Runs the enrichment workflow: Tiers 1-3 (automated) → Claude Review → Manual Review

Tier Escalation Flow:
    Tier 1 (Firecrawl/Playwright) → Tier 2 (HTML Extraction) → Tier 3 (PDF/OCR)
    → Claude Review (interactive) → Manual Review

Usage:
    # Default: staged processing (each tier completes before next)
    python run_multi_tier_enrichment.py

    # Process only a specific tier (1-3 automated)
    python run_multi_tier_enrichment.py --tier 1
    python run_multi_tier_enrichment.py --tier 3

    # Process specific districts
    python run_multi_tier_enrichment.py --districts 0622710 3623370 3003290

    # Prepare Claude Review batch (outputs districts for interactive processing)
    python run_multi_tier_enrichment.py --claude-review

    # Legacy continuous mode (discouraged)
    python run_multi_tier_enrichment.py --continuous

    # Dry run (no changes)
    python run_multi_tier_enrichment.py --dry-run
"""

import argparse
import logging
import subprocess
import sys
from typing import List, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from infrastructure.database.connection import session_scope
from infrastructure.database.enrichment_queue_manager import EnrichmentQueueManager
from infrastructure.database.verification import (
    generate_handoff_report,
    check_audit_integrity,
)
from infrastructure.database.models import District

# Configure logging - minimal for console, detailed for file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('multi_tier_enrichment.log'),
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
            'tier_1': {'processed': 0, 'succeeded': 0, 'escalated': 0, 'blocked': 0},
            'tier_2': {'processed': 0, 'succeeded': 0, 'escalated': 0, 'blocked': 0},
            'tier_3': {'processed': 0, 'succeeded': 0, 'escalated': 0, 'blocked': 0},
            'claude_review': {'processed': 0, 'succeeded': 0, 'manual_review': 0}
        }

    # =========================================================================
    # Output Helpers
    # =========================================================================

    def _print_transition(
        self,
        district_id: str,
        district_name: str,
        from_tier: int,
        to_state: str,
        detail: str = None
    ):
        """Print a district state transition in real-time."""
        detail_str = f" ({detail})" if detail else ""
        # Truncate long district names
        name = district_name[:40] + "..." if len(district_name) > 40 else district_name
        print(f"  [{district_id}] {name}: Tier {from_tier} -> {to_state}{detail_str}")
        sys.stdout.flush()  # Ensure immediate output

    def _print_tier_summary(self, tier, results: dict):
        """Print summary after completing a tier."""
        parts = []
        if results.get('succeeded', 0) > 0:
            parts.append(f"{results['succeeded']} succeeded")
        if results.get('escalated', 0) > 0:
            parts.append(f"{results['escalated']} escalated")
        if results.get('blocked', 0) > 0:
            parts.append(f"{results['blocked']} blocked")
        if results.get('manual_review', 0) > 0:
            parts.append(f"{results['manual_review']} manual_review")

        summary = ", ".join(parts) if parts else "0 processed"
        tier_name = f"Tier {tier}" if isinstance(tier, int) else tier
        print(f"\n{tier_name} complete: {summary}")

    # =========================================================================
    # Staged Processing (New Default)
    # =========================================================================

    def run_staged(
        self,
        district_ids: Optional[List[str]] = None,
        tier_filter: Optional[int] = None,
        run_tests_on_complete: bool = True
    ) -> bool:
        """
        Run staged processing - complete each tier before advancing to the next.

        This is the new default mode. Each tier processes ALL pending districts
        before any district advances to the next tier.

        Args:
            district_ids: Optional list of specific districts to process
            tier_filter: If specified, only process this tier
            run_tests_on_complete: Run test suite when queue clears

        Returns:
            True if completed successfully, False if halted
        """
        print("=" * 60)
        print("MULTI-TIER ENRICHMENT - STAGED MODE")
        print("=" * 60)
        if self.dry_run:
            print("DRY RUN MODE - No changes will be made")
        if tier_filter:
            print(f"Processing only Tier {tier_filter}")
        print()

        with session_scope() as session:
            queue_manager = EnrichmentQueueManager(session, self.max_cost_dollars)

            # Add districts to queue if specified
            if district_ids:
                print(f"Adding {len(district_ids)} districts to queue...")
                added = queue_manager.add_districts(district_ids)
                print(f"Added {added} new districts to queue\n")

            # Determine which tiers to process (only 1-3 are automated)
            tiers_to_process = [tier_filter] if tier_filter else [1, 2, 3]

            # Process each automated tier to completion
            for tier in tiers_to_process:
                pending = queue_manager.get_pending_count_for_tier(tier)
                if pending == 0:
                    print(f"Tier {tier}: No districts pending, skipping")
                    continue

                print(f"\n{'='*60}")
                print(f"TIER {tier} PROCESSING ({pending} districts)")
                print(f"{'='*60}\n")

                results = self._process_tier_to_completion(
                    queue_manager, session, tier
                )

                self._accumulate_stats(f'tier_{tier}', results)
                self._print_tier_summary(tier, results)

            # Check for districts needing Claude Review
            claude_review_pending = queue_manager.get_pending_count_for_tier(4)
            if claude_review_pending > 0:
                print(f"\n{'='*60}")
                print(f"CLAUDE REVIEW QUEUE ({claude_review_pending} districts)")
                print(f"{'='*60}")
                print(f"\nTo process these districts interactively:")
                print(f"  python run_multi_tier_enrichment.py --claude-review")
                print(f"\nOr run the tier_4_processor.py directly for batch preparation.")

            # Final summary
            self._print_final_summary(queue_manager)

            # Run verification
            self._run_verification(session)

            # Run tests if queue is complete
            if queue_manager.is_queue_complete() and run_tests_on_complete:
                print("\n" + "=" * 60)
                print("RUNNING TEST SUITE")
                print("=" * 60)
                tests_passed = self._run_tests()
                if not tests_passed:
                    print("\nTESTS FAILED - Halting for user review")
                    return False

            return True

    def _process_tier_to_completion(
        self,
        queue_manager: EnrichmentQueueManager,
        session,
        tier: int
    ) -> dict:
        """
        Process ALL districts at a tier before returning.

        Uses the existing batch methods which already print per-district output.

        Args:
            queue_manager: Queue manager instance
            session: Database session
            tier: Tier number (1-5)

        Returns:
            Results dict with succeeded, escalated, blocked, manual_review counts
        """
        total_results = {
            'processed': 0,
            'succeeded': 0,
            'escalated': 0,
            'blocked': 0,
            'failed': 0,
            'manual_review': 0
        }

        if self.dry_run:
            pending = queue_manager.get_pending_count_for_tier(tier)
            print(f"  DRY RUN: Would process {pending} districts at Tier {tier}")
            return total_results

        # Process in batches until no more pending at this tier
        # Only tiers 1-3 are automated; tier 4 (Claude Review) is interactive
        while queue_manager.get_pending_count_for_tier(tier) > 0:
            if tier == 1:
                batch_result = queue_manager.process_tier_1_batch(
                    batch_size=10, dry_run=False
                )
            elif tier == 2:
                batch_result = queue_manager.process_tier_2_batch(
                    batch_size=10, dry_run=False
                )
            elif tier == 3:
                batch_result = queue_manager.process_tier_3_batch(
                    batch_size=10, dry_run=False
                )
            else:
                # Tiers 4+ are not automated
                break

            # Accumulate results
            for key in total_results:
                if key in batch_result:
                    total_results[key] += batch_result[key]

            # If no districts were processed, break to avoid infinite loop
            if batch_result.get('processed', 0) == 0:
                break

        return total_results

    def _process_claude_review_item(
        self,
        queue_manager: EnrichmentQueueManager,
        queue_item,
        district_name: str
    ) -> dict:
        """Process a single district through Claude Review (interactive)."""
        from infrastructure.scripts.enrich.tier_4_processor import Tier4Processor

        processor = Tier4Processor(queue_manager.session)

        try:
            result = processor.process_district(
                district_id=queue_item.district_id,
                previous_results={
                    'tier_1': queue_item.tier_1_result,
                    'tier_2': queue_item.tier_2_result,
                    'tier_3': queue_item.tier_3_result,
                }
            )

            if result.get('success') and result.get('schedule_extracted'):
                if queue_manager.record_tier_success(
                    queue_item.district_id, tier=4, result=result
                ):
                    self._print_transition(
                        queue_item.district_id,
                        district_name,
                        "Claude Review",
                        "SUCCESS",
                        f"{len(result.get('schedules_extracted', []))} schedule(s)"
                    )
                    return {'type': 'succeeded'}

            # Escalate to Manual Review (no more automated tiers)
            queue_manager.record_manual_review(
                queue_item.district_id,
                result=result,
                reason=result.get('error', 'no_schedule_extracted')
            )
            self._print_transition(
                queue_item.district_id,
                district_name,
                "Claude Review",
                "MANUAL_REVIEW",
                result.get('error', 'no schedule')
            )
            return {'type': 'manual_review'}

        except Exception as e:
            logger.error(f"Claude Review error for {queue_item.district_id}: {e}")
            queue_manager.record_manual_review(
                queue_item.district_id,
                result={'error': str(e)},
                reason=f'exception: {str(e)}'
            )
            self._print_transition(
                queue_item.district_id,
                district_name,
                "Claude Review",
                "MANUAL_REVIEW",
                f"error: {str(e)[:30]}"
            )
            return {'type': 'manual_review'}

    # =========================================================================
    # Legacy Continuous Mode
    # =========================================================================

    def run_continuous(
        self,
        district_ids: Optional[List[str]] = None,
        tier1_batch_size: int = 50,
        tier2_batch_size: int = 50,
        tier3_batch_size: int = 20,
        run_tests_on_complete: bool = True
    ) -> bool:
        """
        Run enrichment continuously until all items reach terminal state.
        (Legacy mode - consider using run_staged instead)

        Loops through all tiers, advancing items until:
        - All items are 'completed' or 'manual_review'
        - A processing error halts execution
        """
        print("=" * 60)
        print("MULTI-TIER ENRICHMENT - CONTINUOUS MODE (Legacy)")
        print("=" * 60)
        if self.dry_run:
            print("DRY RUN MODE - No changes will be made")
        print()

        with session_scope() as session:
            queue_manager = EnrichmentQueueManager(session, self.max_cost_dollars)

            # Add districts to queue if specified
            if district_ids:
                print(f"Adding {len(district_ids)} districts to queue...")
                added = queue_manager.add_districts(district_ids)
                print(f"Added {added} new districts to queue")
                print()

            # Main processing loop
            iteration = 0
            max_iterations = 100  # Safety limit

            while iteration < max_iterations:
                iteration += 1

                # Check if queue is complete
                if queue_manager.is_queue_complete():
                    print("\n" + "=" * 60)
                    print("QUEUE COMPLETE - All items reached terminal state")
                    print("=" * 60)
                    break

                # Print current status
                summary = queue_manager.get_queue_summary()
                print(f"\n--- Iteration {iteration} ---")
                print(f"Pending: {summary['pending']} | Completed: {summary['completed']} | Manual Review: {summary.get('manual_review', 0)}")

                # Process each tier in sequence
                made_progress = False

                # Tier 1
                depth = queue_manager.get_queue_depth(1)
                if depth > 0:
                    print(f"\nTier 1: {depth} districts pending")
                    result = queue_manager.process_tier_1_batch(
                        batch_size=tier1_batch_size,
                        dry_run=self.dry_run
                    )
                    self._accumulate_stats('tier_1', result)
                    if result.get('processed', 0) > 0:
                        made_progress = True

                # Tier 2
                depth = queue_manager.get_queue_depth(2)
                if depth > 0:
                    print(f"\nTier 2: {depth} districts pending")
                    result = queue_manager.process_tier_2_batch(
                        batch_size=tier2_batch_size,
                        dry_run=self.dry_run
                    )
                    self._accumulate_stats('tier_2', result)
                    if result.get('processed', 0) > 0:
                        made_progress = True

                # Tier 3
                depth = queue_manager.get_queue_depth(3)
                if depth > 0:
                    print(f"\nTier 3: {depth} districts pending")
                    result = queue_manager.process_tier_3_batch(
                        batch_size=tier3_batch_size,
                        dry_run=self.dry_run
                    )
                    self._accumulate_stats('tier_3', result)
                    if result.get('processed', 0) > 0:
                        made_progress = True

                # Claude Review - Interactive (not automated in continuous mode)
                claude_review_depth = queue_manager.get_queue_depth(4)
                if claude_review_depth > 0:
                    print(f"\nClaude Review: {claude_review_depth} districts pending")
                    print("  (Run --claude-review for interactive processing)")

                # Check for stalled queue
                if not made_progress and not queue_manager.is_queue_complete():
                    print("\nWARNING: No progress made this iteration")
                    break

            # Final summary
            self._print_final_summary(queue_manager)

            # Run verification
            self._run_verification(session)

            # Run tests if queue is complete
            if queue_manager.is_queue_complete() and run_tests_on_complete:
                print("\n" + "=" * 60)
                print("RUNNING TEST SUITE")
                print("=" * 60)
                tests_passed = self._run_tests()
                if not tests_passed:
                    print("\nTESTS FAILED - Halting for user review")
                    return False

            return queue_manager.is_queue_complete()

    def _process_claude_review_batch(
        self,
        queue_manager: EnrichmentQueueManager,
        batch_size: int
    ) -> dict:
        """Process Claude Review batch (interactive processing)."""
        if self.dry_run:
            print("  DRY RUN: Would process via Claude Review")
            return {'processed': 0, 'dry_run': True}

        from infrastructure.scripts.enrich.tier_4_processor import Tier4Processor

        districts = queue_manager.get_districts_for_processing(tier=4, batch_size=batch_size)
        if not districts:
            return {'processed': 0, 'succeeded': 0, 'manual_review': 0}

        processor = Tier4Processor(queue_manager.session)
        succeeded = 0
        manual_review = 0

        for queue_item in districts:
            try:
                result = processor.process_district(
                    district_id=queue_item.district_id,
                    previous_results={
                        'tier_1': queue_item.tier_1_result,
                        'tier_2': queue_item.tier_2_result,
                        'tier_3': queue_item.tier_3_result,
                    }
                )

                if result.get('success') and result.get('schedule_extracted'):
                    if queue_manager.record_tier_success(
                        queue_item.district_id, tier=4, result=result
                    ):
                        succeeded += 1
                        print(f"  {queue_item.district_id}: Claude Review -> SUCCESS")
                    else:
                        queue_manager.record_manual_review(
                            queue_item.district_id,
                            result={'error': 'commit_failed', **result},
                            reason='database_commit_failed'
                        )
                        manual_review += 1
                        print(f"  {queue_item.district_id}: Claude Review -> MANUAL_REVIEW (commit failed)")
                else:
                    queue_manager.record_manual_review(
                        queue_item.district_id,
                        result=result,
                        reason=result.get('error', 'no_schedule_extracted')
                    )
                    manual_review += 1
                    print(f"  {queue_item.district_id}: Claude Review -> MANUAL_REVIEW")

            except Exception as e:
                logger.error(f"Claude Review error for {queue_item.district_id}: {e}")
                queue_manager.record_manual_review(
                    queue_item.district_id,
                    result={'error': str(e)},
                    reason=f'exception: {str(e)}'
                )
                manual_review += 1
                print(f"  {queue_item.district_id}: Claude Review -> MANUAL_REVIEW (error)")

        print(f"Claude Review complete: {succeeded} succeeded, {manual_review} to manual review")
        return {'processed': len(districts), 'succeeded': succeeded, 'manual_review': manual_review}

    # =========================================================================
    # Shared Helpers
    # =========================================================================

    def _accumulate_stats(self, tier_key: str, result: dict):
        """Accumulate stats from a tier run"""
        if not result:
            return
        for key in ['processed', 'succeeded', 'escalated', 'blocked', 'manual_review']:
            if key in result:
                self.stats[tier_key][key] = self.stats[tier_key].get(key, 0) + result[key]

    def _print_final_summary(self, queue_manager: EnrichmentQueueManager):
        """Print final processing summary"""
        print("\n" + "=" * 60)
        print("FINAL SUMMARY")
        print("=" * 60)

        summary = queue_manager.get_queue_summary()
        print(f"\nQueue State:")
        print(f"  Total:         {summary['total']}")
        print(f"  Completed:     {summary['completed']}")
        print(f"  Manual Review: {summary.get('manual_review', 0)}")
        print(f"  Pending:       {summary['pending']}")

        print(f"\nTier Statistics:")
        for tier in range(1, 4):
            stats = self.stats.get(f'tier_{tier}', {})
            if stats.get('processed', 0) > 0:
                print(f"  Tier {tier}: processed={stats.get('processed', 0)}, "
                      f"succeeded={stats.get('succeeded', 0)}, "
                      f"escalated={stats.get('escalated', 0)}"
                      f"{', blocked=' + str(stats['blocked']) if stats.get('blocked') else ''}")

        # Claude Review stats
        claude_stats = self.stats.get('claude_review', {})
        if claude_stats.get('processed', 0) > 0:
            print(f"  Claude Review: processed={claude_stats.get('processed', 0)}, "
                  f"succeeded={claude_stats.get('succeeded', 0)}, "
                  f"manual_review={claude_stats.get('manual_review', 0)}")

    def _run_verification(self, session):
        """Run post-enrichment verification"""
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)

        try:
            report = generate_handoff_report(session)
            print(f"Enriched districts: {report['enriched_districts']}")
            print(f"States with data: {report['states_with_enrichment']}")

            integrity = check_audit_integrity(session)
            print(f"Audit integrity: {integrity['integrity_status']}")

        except Exception as e:
            print(f"Verification error: {e}")

    def _run_tests(self) -> bool:
        """Run the test suite after queue completion."""
        try:
            result = subprocess.run(
                ['python3', '-m', 'pytest', 'tests/', '-v', '--tb=short'],
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parents[3]
            )

            print(result.stdout)
            if result.returncode != 0:
                print("\nTest failures detected:")
                print(result.stderr)
                return False

            print("\nAll tests passed!")
            return True

        except Exception as e:
            print(f"Error running tests: {e}")
            return False


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Multi-Tier Bell Schedule Enrichment Orchestrator"
    )

    parser.add_argument(
        '--tier',
        type=int,
        choices=[1, 2, 3],
        help='Process only this automated tier (1-3)'
    )

    parser.add_argument(
        '--claude-review',
        action='store_true',
        help='Prepare batch for Claude Review (interactive processing)'
    )

    parser.add_argument(
        '--continuous',
        action='store_true',
        help='Legacy continuous mode (discouraged - use staged mode instead)'
    )

    parser.add_argument(
        '--districts',
        nargs='+',
        help='Specific district NCES IDs to process'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate without making changes'
    )

    parser.add_argument(
        '--skip-tests',
        action='store_true',
        help='Skip running tests after queue completion'
    )

    # Legacy batch size args (for --continuous mode)
    parser.add_argument('--tier1-batch-size', type=int, default=50)
    parser.add_argument('--tier2-batch-size', type=int, default=50)
    parser.add_argument('--tier3-batch-size', type=int, default=20)

    args = parser.parse_args()

    orchestrator = MultiTierOrchestrator(dry_run=args.dry_run)

    if args.claude_review:
        # Prepare Claude Review batch
        from infrastructure.scripts.enrich.tier_4_processor import Tier4Processor
        with session_scope() as session:
            from infrastructure.database.models import EnrichmentQueue
            processor = Tier4Processor(session)

            # Get districts pending Claude Review
            districts = session.query(EnrichmentQueue).filter_by(
                current_tier=4, status='pending'
            ).limit(20).all()

            if not districts:
                print("No districts pending Claude Review")
                sys.exit(0)

            batch = processor.prepare_batch_for_claude(districts)
            request_text = processor.format_batch_request(batch)
            print(request_text)

            # Save to file
            with open('claude_review_batch.txt', 'w') as f:
                f.write(request_text)
            print(f"\nBatch saved to: claude_review_batch.txt")
            print("Process these districts interactively, then use record_schedule_from_session()")

        sys.exit(0)

    elif args.continuous:
        # Legacy continuous mode
        success = orchestrator.run_continuous(
            district_ids=args.districts,
            tier1_batch_size=args.tier1_batch_size,
            tier2_batch_size=args.tier2_batch_size,
            tier3_batch_size=args.tier3_batch_size,
            run_tests_on_complete=not args.skip_tests
        )
        sys.exit(0 if success else 1)
    else:
        # Default staged mode
        success = orchestrator.run_staged(
            district_ids=args.districts,
            tier_filter=args.tier,
            run_tests_on_complete=not args.skip_tests
        )
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
