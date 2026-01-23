#!/usr/bin/env python3
"""
Enrichment Queue Manager
Orchestrates multi-tier bell schedule enrichment with batched API processing

Architecture:
    Tier 1: Local Discovery (Playwright) - Find district/school sites
    Tier 2: Local Extraction (Patterns) - Parse HTML for schedules
    Tier 3: Local PDF/OCR - Extract from documents
    Tier 4: Claude Desktop (Batched) - Complex extraction via user's Claude subscription
    Tier 5: Gemini MCP (Batched) - Web search fallback

Usage:
    from enrichment_queue_manager import EnrichmentQueueManager
    from connection import session_scope

    with session_scope() as session:
        qm = EnrichmentQueueManager(session)

        # Add districts to queue
        added = qm.add_districts(['0622710', '3623370'])

        # Process tiers
        qm.process_tier_1_batch(batch_size=50)
        qm.process_tier_2_batch(batch_size=50)
        qm.process_tier_3_batch(batch_size=20)

        # Prepare batches for Claude Desktop
        tier_4_batches = qm.prepare_tier_4_batches()
        # Present batches to Claude for processing

        # Get status
        status = qm.get_status()
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path
import json

from sqlalchemy.orm import Session
from sqlalchemy import text, func

from infrastructure.database.models import (
    District, EnrichmentQueue, EnrichmentBatch,
    BellSchedule, EnrichmentAttempt
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EnrichmentQueueManager:
    """Manages multi-tier bell schedule enrichment queue"""

    def __init__(self, session: Session, max_cost_dollars: float = None):
        """
        Initialize queue manager

        Args:
            session: SQLAlchemy database session
            max_cost_dollars: Optional budget limit for API costs
        """
        self.session = session
        self.max_cost_dollars = max_cost_dollars
        self.current_cost_dollars = self._get_current_cost()

    def _get_current_cost(self) -> float:
        """Get current total API cost from batches"""
        result = self.session.query(
            func.sum(EnrichmentBatch.api_cost_cents)
        ).filter(
            EnrichmentBatch.status == 'completed'
        ).scalar()

        return (result or 0) / 100.0

    def _check_budget(self, estimated_cost_cents: int) -> bool:
        """Check if operation is within budget"""
        if self.max_cost_dollars is None:
            return True

        estimated_dollars = estimated_cost_cents / 100.0
        return (self.current_cost_dollars + estimated_dollars) <= self.max_cost_dollars

    # =========================================================================
    # Queue Management
    # =========================================================================

    def add_districts(self, district_ids: List[str]) -> int:
        """
        Add districts to enrichment queue at Tier 1

        Args:
            district_ids: List of NCES district IDs

        Returns:
            Number of districts added (excludes duplicates)
        """
        # Use database function for atomic insert
        result = self.session.execute(
            text("SELECT queue_districts_for_enrichment(:ids)"),
            {"ids": district_ids}
        )
        added_count = result.scalar()
        self.session.commit()

        logger.info(f"Added {added_count} districts to queue (attempted {len(district_ids)})")
        return added_count

    def get_status(self) -> Dict:
        """
        Get comprehensive queue status

        Returns:
            Dictionary with status metrics
        """
        # Use database function for dashboard metrics
        dashboard_result = self.session.execute(
            text("SELECT * FROM get_queue_dashboard()")
        ).fetchall()

        # Convert to dictionary
        dashboard = {row[0]: row[1] for row in dashboard_result}

        # Get tier-specific metrics
        tier_status = self.session.execute(text("""
            SELECT
                current_tier,
                status,
                COUNT(*) as count
            FROM enrichment_queue
            GROUP BY current_tier, status
            ORDER BY current_tier, status
        """)).fetchall()

        # Organize by tier
        tiers = {}
        for tier, status, count in tier_status:
            tier_key = f"tier_{tier}"
            if tier_key not in tiers:
                tiers[tier_key] = {}
            tiers[tier_key][status] = count

        return {
            'summary': dashboard,
            'by_tier': tiers,
            'current_cost': self.current_cost_dollars,
            'budget_limit': self.max_cost_dollars,
            'timestamp': datetime.utcnow().isoformat()
        }

    def get_queue_depth(self, tier: int) -> int:
        """Get number of districts pending at specific tier"""
        count = self.session.query(EnrichmentQueue).filter(
            EnrichmentQueue.current_tier == tier,
            EnrichmentQueue.status == 'pending'
        ).count()
        return count

    def get_districts_for_processing(
        self,
        tier: int,
        batch_size: int,
        filters: Dict = None
    ) -> List[EnrichmentQueue]:
        """
        Get districts ready for processing at specific tier

        Args:
            tier: Tier number (1-5)
            batch_size: Maximum number to retrieve
            filters: Optional additional filters (cms_detected, content_type, etc.)

        Returns:
            List of EnrichmentQueue objects
        """
        query = self.session.query(EnrichmentQueue).filter(
            EnrichmentQueue.current_tier == tier,
            EnrichmentQueue.status == 'pending'
        )

        # Apply optional filters
        if filters:
            if 'cms_detected' in filters:
                query = query.filter(EnrichmentQueue.cms_detected == filters['cms_detected'])
            if 'content_type' in filters:
                query = query.filter(EnrichmentQueue.content_type == filters['content_type'])
            if 'batch_type' in filters:
                query = query.filter(EnrichmentQueue.batch_type == filters['batch_type'])

        # Order by district size (larger first) for prioritization
        query = query.join(District).order_by(District.enrollment.desc())

        return query.limit(batch_size).all()

    # =========================================================================
    # Tier Processing (Tiers 1-3: Local)
    # =========================================================================

    def process_tier_1_batch(
        self,
        batch_size: int = 50,
        workers: int = 10,
        dry_run: bool = False
    ) -> Dict:
        """
        Process Tier 1: Local Discovery (Playwright)

        Tasks:
            - Fetch district homepage
            - Discover individual school subsites
            - Test common URL patterns for bell schedules
            - Identify CMS platform

        Args:
            batch_size: Number of districts to process
            workers: Number of parallel workers
            dry_run: If True, log actions but don't execute

        Returns:
            Processing results summary
        """
        logger.info(f"Processing Tier 1 batch (size={batch_size}, workers={workers}, dry_run={dry_run})")

        # Get pending districts
        districts = self.get_districts_for_processing(tier=1, batch_size=batch_size)

        if not districts:
            logger.info("No districts pending at Tier 1")
            return {'processed': 0, 'successful': 0, 'escalated': 0}

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(districts)} districts")
            return {'processed': len(districts), 'dry_run': True}

        # Import tier processor
        from infrastructure.scripts.enrich.tier_1_processor import Tier1Processor

        # Initialize processor
        processor = Tier1Processor(self.session)

        # Process each district
        successful = 0
        escalated = 0
        failed = 0

        for queue_item in districts:
            try:
                # Process district
                result = processor.process_district(queue_item.district_id)

                if result.get('success'):
                    # Check if bell schedule found
                    if result.get('bell_schedule_found'):
                        # Success! Complete enrichment
                        self.record_tier_success(
                            queue_item.district_id,
                            tier=1,
                            result=result,
                            processing_time_seconds=result.get('processing_time_seconds')
                        )
                        successful += 1
                    else:
                        # No schedule found - escalate to Tier 2
                        self.record_tier_escalation(
                            queue_item.district_id,
                            current_tier=1,
                            result=result,
                            escalation_reason=result.get('escalation_reason', 'no_schedule_found'),
                            cms_detected=result.get('cms_detected'),
                            content_type=result.get('content_type')
                        )
                        escalated += 1
                else:
                    # Failed - escalate anyway
                    self.record_tier_escalation(
                        queue_item.district_id,
                        current_tier=1,
                        result=result,
                        escalation_reason=result.get('error', 'processing_failed')
                    )
                    failed += 1

                logger.info(f"Processed {queue_item.district_id}: "
                           f"success={result.get('success')}, "
                           f"schedule_found={result.get('bell_schedule_found')}")

            except Exception as e:
                logger.error(f"Error processing {queue_item.district_id}: {e}")
                failed += 1

        logger.info(f"Tier 1 batch complete: {successful} successful, "
                   f"{escalated} escalated, {failed} failed")

        return {
            'processed': len(districts),
            'successful': successful,
            'escalated': escalated,
            'failed': failed
        }

    def process_tier_2_batch(
        self,
        batch_size: int = 50,
        workers: int = 10,
        dry_run: bool = False
    ) -> Dict:
        """
        Process Tier 2: Local Extraction (HTML parsing)

        Tasks:
            - Parse HTML for time patterns (HH:MM AM/PM)
            - Extract from common table structures
            - Check for embedded calendars/widgets
            - Detect PDF/image schedule links

        Args:
            batch_size: Number of districts to process
            workers: Number of parallel workers
            dry_run: If True, log actions but don't execute

        Returns:
            Processing results summary
        """
        logger.info(f"Processing Tier 2 batch (size={batch_size}, workers={workers}, dry_run={dry_run})")

        districts = self.get_districts_for_processing(tier=2, batch_size=batch_size)

        if not districts:
            logger.info("No districts pending at Tier 2")
            return {'processed': 0, 'successful': 0, 'escalated': 0}

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(districts)} districts")
            return {'processed': len(districts), 'dry_run': True}

        # Implement actual Tier 2 processing
        from infrastructure.scripts.enrich.tier_2_processor import Tier2Processor
        processor = Tier2Processor(self.session)

        successful = 0
        escalated = 0
        failed = 0

        for queue_item in districts:
            try:
                # Process district with Tier 1 results
                tier_1_result = queue_item.tier_1_result or {}
                result = processor.process_district(
                    district_id=queue_item.district_id,
                    tier_1_result=tier_1_result
                )

                if result.get('success'):
                    if result.get('schedule_extracted'):
                        # Success! Found and extracted schedule
                        self.record_tier_success(
                            district_id=queue_item.district_id,
                            tier=2,
                            result=result,
                            processing_time_seconds=result.get('processing_time_seconds')
                        )
                        successful += 1
                    else:
                        # HTML parsed but no schedule extracted - escalate to Tier 3
                        self.record_tier_escalation(
                            queue_item.district_id,
                            current_tier=2,
                            result=result,
                            escalation_reason=result.get('escalation_reason', 'no_schedule_extracted'),
                            cms_detected=result.get('cms_detected'),
                            content_type=result.get('content_type')
                        )
                        escalated += 1
                else:
                    # Failed - escalate to Tier 3
                    self.record_tier_escalation(
                        queue_item.district_id,
                        current_tier=2,
                        result=result,
                        escalation_reason=result.get('error', 'processing_failed')
                    )
                    failed += 1

                logger.info(f"Processed {queue_item.district_id}: "
                           f"success={result.get('success')}, "
                           f"extracted={result.get('schedule_extracted')}")

            except Exception as e:
                logger.error(f"Error processing {queue_item.district_id}: {e}")
                failed += 1

        logger.info(f"Tier 2 batch complete: {successful} successful, "
                   f"{escalated} escalated, {failed} failed")

        return {
            'processed': len(districts),
            'successful': successful,
            'escalated': escalated,
            'failed': failed
        }

    def process_tier_3_batch(
        self,
        batch_size: int = 20,
        workers: int = 5,
        dry_run: bool = False
    ) -> Dict:
        """
        Process Tier 3: Local PDF/OCR Extraction

        Tasks:
            - Download PDF documents
            - Extract text with pdftotext
            - OCR if text extraction fails (tesseract)
            - Parse for time patterns
            - Handle Google Drive PDFs

        Args:
            batch_size: Number of districts to process
            workers: Number of parallel workers
            dry_run: If True, log actions but don't execute

        Returns:
            Processing results summary
        """
        logger.info(f"Processing Tier 3 batch (size={batch_size}, workers={workers}, dry_run={dry_run})")

        districts = self.get_districts_for_processing(tier=3, batch_size=batch_size)

        if not districts:
            logger.info("No districts pending at Tier 3")
            return {'processed': 0, 'successful': 0, 'escalated': 0}

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(districts)} districts")
            return {'processed': len(districts), 'dry_run': True}

        # Implement actual Tier 3 processing
        from infrastructure.scripts.enrich.tier_3_processor import Tier3Processor
        processor = Tier3Processor(self.session)

        successful = 0
        escalated = 0
        failed = 0

        for queue_item in districts:
            try:
                # Process district with Tier 2 results
                tier_2_result = queue_item.tier_2_result or {}
                result = processor.process_district(
                    district_id=queue_item.district_id,
                    tier_2_result=tier_2_result
                )

                if result.get('success'):
                    if result.get('schedule_found'):
                        # Success! Extracted schedule from PDF/OCR
                        self.record_tier_success(
                            district_id=queue_item.district_id,
                            tier=3,
                            result=result,
                            processing_time_seconds=result.get('processing_time_seconds')
                        )
                        successful += 1
                    else:
                        # PDF processed but no schedule extracted - escalate to Tier 4
                        self.record_tier_escalation(
                            queue_item.district_id,
                            current_tier=3,
                            result=result,
                            escalation_reason=result.get('escalation_reason', 'no_schedule_extracted'),
                            cms_detected=result.get('cms_detected'),
                            content_type=result.get('content_type')
                        )
                        escalated += 1
                else:
                    # Failed - escalate to Tier 4
                    self.record_tier_escalation(
                        queue_item.district_id,
                        current_tier=3,
                        result=result,
                        escalation_reason=result.get('error', 'processing_failed')
                    )
                    failed += 1

                logger.info(f"Processed {queue_item.district_id}: "
                           f"success={result.get('success')}, "
                           f"extracted={result.get('schedule_extracted')}")

            except Exception as e:
                logger.error(f"Error processing {queue_item.district_id}: {e}")
                failed += 1

        logger.info(f"Tier 3 batch complete: {successful} successful, "
                   f"{escalated} escalated, {failed} failed")

        return {
            'processed': len(districts),
            'successful': successful,
            'escalated': escalated,
            'failed': failed
        }

    # =========================================================================
    # Tier 4 & 5: Batched API Processing
    # =========================================================================

    def prepare_tier_4_batches(self, batch_size: int = 15) -> List[Dict]:
        """
        Prepare batches for Tier 4: Claude Desktop Processing

        Groups districts by:
            1. CMS platform (Finalsite, SchoolBlocks, etc.)
            2. Content type (PDF tables, JS-heavy HTML, etc.)
            3. District size

        Args:
            batch_size: Districts per batch (10-20 recommended)

        Returns:
            List of batch specifications ready for Claude processing
        """
        logger.info(f"Preparing Tier 4 batches (size={batch_size})")

        # Get all districts ready for Tier 4
        districts = self.get_districts_for_processing(tier=4, batch_size=1000)

        if not districts:
            logger.info("No districts ready for Tier 4 batching")
            return []

        # Group by batch characteristics
        batches = self._compose_claude_batches(districts, batch_size)

        logger.info(f"Prepared {len(batches)} Tier 4 batches covering {len(districts)} districts")
        return batches

    def prepare_tier_5_batches(self, batch_size: int = 15) -> List[Dict]:
        """
        Prepare batches for Tier 5: Gemini MCP Web Search

        Groups districts by:
            1. State (geographic context)
            2. District size
            3. Previous failure patterns

        Args:
            batch_size: Districts per batch (10-20 recommended)

        Returns:
            List of batch specifications ready for Gemini processing
        """
        logger.info(f"Preparing Tier 5 batches (size={batch_size})")

        # Get all districts ready for Tier 5
        districts = self.get_districts_for_processing(tier=5, batch_size=1000)

        if not districts:
            logger.info("No districts ready for Tier 5 batching")
            return []

        # Group by state and characteristics
        batches = self._compose_gemini_batches(districts, batch_size)

        logger.info(f"Prepared {len(batches)} Tier 5 batches covering {len(districts)} districts")
        return batches

    def _compose_claude_batches(
        self,
        districts: List[EnrichmentQueue],
        batch_size: int
    ) -> List[Dict]:
        """
        Compose Claude Desktop batches with intelligent grouping

        Strategy: Group similar processing tasks for context sharing
        """
        # Group by primary characteristic: CMS platform or content type
        groups = {}

        for district in districts:
            # Determine grouping key
            if district.cms_detected:
                group_key = f"cms_{district.cms_detected}"
            elif district.content_type:
                group_key = f"content_{district.content_type}"
            else:
                group_key = "mixed"

            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(district)

        # Create batches
        batches = []
        batch_id = 1

        for group_key, group_districts in groups.items():
            # Split large groups into batches
            for i in range(0, len(group_districts), batch_size):
                batch_districts = group_districts[i:i + batch_size]

                # Get District objects for full context
                district_objs = self.session.query(District).filter(
                    District.nces_id.in_([d.district_id for d in batch_districts])
                ).all()

                # Build batch specification
                batch = {
                    'batch_id': batch_id,
                    'batch_type': group_key,
                    'tier': 4,
                    'district_count': len(batch_districts),
                    'districts': [
                        {
                            'nces_id': d.nces_id,
                            'name': d.name,
                            'state': d.state,
                            'enrollment': d.enrollment,
                            'url': getattr(d, 'website_url', None),
                            'cms_detected': eq.cms_detected,
                            'content_type': eq.content_type,
                            'escalation_reason': eq.escalation_reason,
                            'tier_1_result': eq.tier_1_result,
                            'tier_2_result': eq.tier_2_result,
                            'tier_3_result': eq.tier_3_result
                        }
                        for d in district_objs
                        for eq in batch_districts
                        if d.nces_id == eq.district_id
                    ],
                    'shared_context': self._get_shared_context_claude(group_key)
                }

                batches.append(batch)
                batch_id += 1

        return batches

    def _compose_gemini_batches(
        self,
        districts: List[EnrichmentQueue],
        batch_size: int
    ) -> List[Dict]:
        """
        Compose Gemini MCP batches with state-based grouping

        Strategy: Group by state for geographic context
        """
        # Group by state
        by_state = {}
        for district in districts:
            # Get District object for state
            dist_obj = self.session.query(District).filter_by(
                nces_id=district.district_id
            ).first()

            if not dist_obj:
                continue

            state = dist_obj.state
            if state not in by_state:
                by_state[state] = []
            by_state[state].append((district, dist_obj))

        # Create batches
        batches = []
        batch_id = 1

        for state, state_districts in by_state.items():
            # Split into batches
            for i in range(0, len(state_districts), batch_size):
                batch_pairs = state_districts[i:i + batch_size]

                batch = {
                    'batch_id': batch_id,
                    'batch_type': f"state_{state}",
                    'tier': 5,
                    'district_count': len(batch_pairs),
                    'districts': [
                        {
                            'nces_id': d.nces_id,
                            'name': d.name,
                            'state': d.state,
                            'enrollment': d.enrollment,
                            'district_url': getattr(d, 'website_url', None),
                            'tier_1_attempted_urls': eq.tier_1_result.get('urls_attempted', []) if eq.tier_1_result else [],
                            'schools': eq.tier_1_result.get('schools_found', []) if eq.tier_1_result else []
                        }
                        for eq, d in batch_pairs
                    ],
                    'search_instructions': (
                        "For each district/school, search for bell schedules using terms: "
                        "'bell schedule', 'daily schedule', 'school hours', 'start time', 'dismissal time'. "
                        "Return the URL and extracted schedule data."
                    )
                }

                batches.append(batch)
                batch_id += 1

        return batches

    def _get_shared_context_claude(self, group_key: str) -> str:
        """Generate shared context for Claude batch based on group type"""
        contexts = {
            'cms_finalsite': (
                "These sites use Finalsite CMS. Common patterns: heavy JavaScript rendering, "
                "schedules often in /about-us or /information sections, calendar widgets common."
            ),
            'cms_schoolblocks': (
                "These sites use SchoolBlocks CMS. Look for /pages/index.jsp URLs, "
                "schedules often embedded in page content, may use iframes."
            ),
            'content_pdf': (
                "These districts have PDFs with table-based bell schedule layouts. "
                "Focus on extracting structured table data, watch for multi-page schedules."
            ),
            'content_heavy_js': (
                "These sites have heavy JavaScript rendering. Schedule data may be "
                "dynamically loaded. Check for JSON endpoints or embedded data."
            ),
            'mixed': (
                "Mixed content types. Use best judgment on extraction approach per district."
            )
        }
        return contexts.get(group_key, contexts['mixed'])

    # =========================================================================
    # Result Recording
    # =========================================================================

    def record_tier_success(
        self,
        district_id: str,
        tier: int,
        result: Dict,
        processing_time_seconds: int = None
    ) -> bool:
        """
        Record successful completion at a tier

        Args:
            district_id: NCES district ID
            tier: Tier number that succeeded
            result: Tier result data (JSONB)
            processing_time_seconds: Optional processing time

        Returns:
            True if recorded successfully
        """
        try:
            self.session.execute(
                text("""
                    SELECT complete_enrichment(
                        :district_id, :tier, :result, :success, :time
                    )
                """),
                {
                    'district_id': district_id,
                    'tier': tier,
                    'result': json.dumps(result),
                    'success': True,
                    'time': processing_time_seconds
                }
            )
            self.session.commit()
            logger.info(f"Recorded success for {district_id} at tier {tier}")
            return True
        except Exception as e:
            logger.error(f"Failed to record success for {district_id}: {e}")
            self.session.rollback()
            return False

    def record_tier_escalation(
        self,
        district_id: str,
        current_tier: int,
        result: Dict,
        escalation_reason: str,
        batch_type: str = None,
        cms_detected: str = None,
        content_type: str = None
    ) -> bool:
        """
        Record escalation to next tier

        Args:
            district_id: NCES district ID
            current_tier: Tier that failed (will escalate to current_tier + 1)
            result: Tier result data (JSONB)
            escalation_reason: Why escalation is needed
            batch_type: Optional batch classification
            cms_detected: Optional CMS platform
            content_type: Optional content type

        Returns:
            True if recorded successfully
        """
        try:
            self.session.execute(
                text("""
                    SELECT escalate_to_next_tier(
                        :district_id, :tier, :result, :reason,
                        :batch_type, :cms, :content
                    )
                """),
                {
                    'district_id': district_id,
                    'tier': current_tier,
                    'result': json.dumps(result),
                    'reason': escalation_reason,
                    'batch_type': batch_type,
                    'cms': cms_detected,
                    'content': content_type
                }
            )
            self.session.commit()
            logger.info(f"Escalated {district_id} from tier {current_tier} to {current_tier + 1}: {escalation_reason}")
            return True
        except Exception as e:
            logger.error(f"Failed to record escalation for {district_id}: {e}")
            self.session.rollback()
            return False


def main():
    """Example usage"""
    from connection import session_scope

    with session_scope() as session:
        qm = EnrichmentQueueManager(session, max_cost_dollars=10.00)

        # Get status
        status = qm.get_status()
        print(json.dumps(status, indent=2))

        # Example: Add districts
        # added = qm.add_districts(['0622710', '3623370'])
        # print(f"Added {added} districts")

        # Example: Process Tier 1
        # result = qm.process_tier_1_batch(batch_size=10, dry_run=True)
        # print(f"Tier 1 result: {result}")


if __name__ == '__main__':
    main()
