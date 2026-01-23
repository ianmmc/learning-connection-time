#!/usr/bin/env python3
"""
Tier 5 Processor: Gemini MCP Web Search (Batched)
Final fallback using Gemini's web search to find missing bell schedules

This tier uses Gemini MCP for comprehensive web search when all local and
Claude Desktop methods have been exhausted. Gemini can navigate websites,
search across multiple sources, and extract data from discovered pages.

**Cost**: Variable (MCP provider dependent)

Workflow:
    1. Queue manager prepares batch (10-20 districts, grouped by state)
    2. Send batch to Gemini MCP via WebSearch tool
    3. Gemini searches for bell schedules using multiple strategies
    4. Parse and validate Gemini's results
    5. Record to database or mark for manual review

Usage:
    from tier_5_processor import Tier5Processor
    from connection import session_scope

    with session_scope() as session:
        processor = Tier5Processor(session)
        result = processor.process_batch(districts)
"""

import logging
import json
from typing import Dict, List, Optional
from datetime import datetime
import re

from sqlalchemy.orm import Session

from infrastructure.database.models import District, EnrichmentQueue, EnrichmentBatch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Tier5Processor:
    """Tier 5: Gemini MCP Web Search (Batched)"""

    # Time validation pattern
    TIME_PATTERN = re.compile(
        r'\b(\d{1,2}):(\d{2})\s*([AaPp][Mm])\b'
    )

    def __init__(self, session: Session):
        """
        Initialize Tier 5 processor

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    # =========================================================================
    # Batch Processing
    # =========================================================================

    def process_batch(
        self,
        districts: List[EnrichmentQueue],
        batch_id: int = None
    ) -> Dict:
        """
        Process batch of districts through Gemini MCP

        Args:
            districts: List of EnrichmentQueue objects at Tier 5
            batch_id: Optional batch ID

        Returns:
            Processing summary
        """
        logger.info(f"Processing Tier 5 batch: {len(districts)} districts")
        start_time = datetime.now()

        if batch_id is None:
            # Generate batch ID
            from sqlalchemy import func
            max_id = self.session.query(
                func.max(EnrichmentBatch.id)
            ).scalar() or 0
            batch_id = max_id + 1

        # Build search queries
        search_queries = self._build_search_queries(districts)

        # Execute searches via Gemini MCP
        search_results = self._execute_gemini_searches(search_queries)

        # Parse and validate results
        validated_results = self._validate_results(search_results, districts)

        # Record results
        summary = self._record_results(batch_id, validated_results, districts)

        processing_time = int((datetime.now() - start_time).total_seconds())

        # Record batch metadata
        batch = EnrichmentBatch(
            id=batch_id,
            batch_type='tier_5_gemini',
            tier=5,
            district_count=len(districts),
            success_count=summary['successes'],
            failure_count=summary['manual_review'],
            status='completed',
            processing_time_seconds=processing_time,
            submitted_at=start_time,
            completed_at=datetime.now()
        )

        self.session.add(batch)
        self.session.commit()

        logger.info(f"Tier 5 batch {batch_id} complete: {summary}")
        return summary

    # =========================================================================
    # Search Query Building
    # =========================================================================

    def _build_search_queries(
        self,
        districts: List[EnrichmentQueue]
    ) -> List[Dict]:
        """
        Build search queries for Gemini

        Args:
            districts: List of EnrichmentQueue objects

        Returns:
            List of search query specifications
        """
        queries = []

        # Get District objects
        district_ids = [d.district_id for d in districts]
        district_objs = {
            d.nces_id: d
            for d in self.session.query(District).filter(
                District.nces_id.in_(district_ids)
            ).all()
        }

        for queue_item in districts:
            dist_obj = district_objs.get(queue_item.district_id)
            if not dist_obj:
                continue

            # Build comprehensive search query
            query = {
                'nces_id': dist_obj.nces_id,
                'district_name': dist_obj.name,
                'state': dist_obj.state,
                'search_terms': self._generate_search_terms(dist_obj, queue_item),
                'context': self._build_search_context(queue_item)
            }

            queries.append(query)

        return queries

    def _generate_search_terms(
        self,
        district: District,
        queue_item: EnrichmentQueue
    ) -> List[str]:
        """
        Generate search terms for a district

        Tries multiple variations to maximize discovery chances
        """
        terms = []

        # Primary term: District name + "bell schedule"
        terms.append(f'"{district.name}" bell schedule {district.state}')

        # Alternative terms
        terms.append(f'"{district.name}" daily schedule {district.state}')
        terms.append(f'"{district.name}" school hours {district.state}')
        terms.append(f'"{district.name}" start time end time {district.state}')
        terms.append(f'"{district.name}" dismissal time {district.state}')

        # If we know schools, search those too
        if queue_item.tier_1_result:
            schools = queue_item.tier_1_result.get('schools_found', [])
            for school in schools[:2]:  # Limit to 2 schools
                school_name = school.get('name', '')
                if school_name:
                    terms.append(f'"{school_name}" bell schedule {district.state}')

        return terms

    def _build_search_context(self, queue_item: EnrichmentQueue) -> str:
        """
        Build search context from previous tier attempts

        This helps Gemini understand what we've already tried
        """
        context_parts = []

        # CMS info
        if queue_item.cms_detected:
            context_parts.append(f"District website uses {queue_item.cms_detected} CMS.")

        # Previous attempts
        if queue_item.tier_1_result:
            urls_attempted = queue_item.tier_1_result.get('urls_attempted', [])
            if urls_attempted:
                context_parts.append(f"Already checked {len(urls_attempted)} URLs without success.")

        # Escalation reason
        if queue_item.escalation_reason:
            context_parts.append(f"Previous failure reason: {queue_item.escalation_reason}")

        return " ".join(context_parts) if context_parts else "No previous context available."

    # =========================================================================
    # Gemini MCP Execution
    # =========================================================================

    def _execute_gemini_searches(
        self,
        search_queries: List[Dict]
    ) -> List[Dict]:
        """
        Execute searches via Gemini MCP

        NOTE: This is a placeholder. Actual implementation would use
        the Gemini MCP tool (mcp__gemini__gemini-chat or similar).

        For now, this returns a structure indicating the searches
        that need to be executed.
        """
        logger.info(f"Would execute {len(search_queries)} Gemini searches")

        # TODO: Implement actual Gemini MCP calls
        # For now, return empty results to indicate not implemented
        results = []

        for query in search_queries:
            results.append({
                'nces_id': query['nces_id'],
                'search_executed': False,
                'implementation_needed': True,
                'search_terms': query['search_terms'],
                'context': query['context']
            })

        logger.warning("Gemini MCP integration not yet implemented")
        return results

    def _call_gemini_mcp(self, query: Dict) -> Dict:
        """
        Call Gemini MCP for a single district

        This would use the mcp__gemini__gemini-chat tool to:
        1. Search for bell schedules
        2. Navigate discovered pages
        3. Extract schedule data
        4. Return structured results
        """
        # TODO: Implement actual MCP call
        # Example structure:
        #
        # from mcp_tools import gemini_chat
        #
        # prompt = f"""
        # Search for the bell schedule for {query['district_name']} in {query['state']}.
        #
        # Try these search terms:
        # {chr(10).join(f"- {term}" for term in query['search_terms'])}
        #
        # Context: {query['context']}
        #
        # Return:
        # - Start time (e.g., "8:00 AM")
        # - End time (e.g., "3:00 PM")
        # - Source URL
        # - Confidence (0.0-1.0)
        # """
        #
        # response = gemini_chat(prompt)
        # return self._parse_gemini_response(response, query)

        pass

    # =========================================================================
    # Result Validation
    # =========================================================================

    def _validate_results(
        self,
        search_results: List[Dict],
        districts: List[EnrichmentQueue]
    ) -> List[Dict]:
        """
        Validate results from Gemini searches

        Checks:
            - Times are in valid format
            - Total minutes is reasonable (180-540)
            - Source URL is provided
            - Confidence is within bounds
        """
        validated = []

        for result in search_results:
            nces_id = result.get('nces_id')

            # If search not executed (implementation pending)
            if result.get('implementation_needed'):
                validated.append({
                    'nces_id': nces_id,
                    'success': False,
                    'validation_error': 'gemini_mcp_not_implemented',
                    'needs_manual_review': True
                })
                continue

            # Validate times
            start_time = result.get('start_time')
            end_time = result.get('end_time')

            if not start_time or not end_time:
                validated.append({
                    'nces_id': nces_id,
                    'success': False,
                    'validation_error': 'missing_times',
                    'needs_manual_review': True
                })
                continue

            # Validate time format
            if not self.TIME_PATTERN.match(start_time) or not self.TIME_PATTERN.match(end_time):
                validated.append({
                    'nces_id': nces_id,
                    'success': False,
                    'validation_error': 'invalid_time_format',
                    'needs_manual_review': True,
                    'raw_times': {'start': start_time, 'end': end_time}
                })
                continue

            # Validate total minutes
            total_minutes = result.get('total_minutes', 0)
            if not (180 <= total_minutes <= 540):
                validated.append({
                    'nces_id': nces_id,
                    'success': False,
                    'validation_error': 'unreasonable_total_minutes',
                    'needs_manual_review': True,
                    'total_minutes': total_minutes
                })
                continue

            # Validate source URL
            if not result.get('source_url'):
                logger.warning(f"No source URL for {nces_id}")

            # Validate confidence
            confidence = result.get('confidence', 0.0)
            if not (0.0 <= confidence <= 1.0):
                confidence = 0.5  # Default to medium confidence

            # If all validations pass
            validated.append({
                'nces_id': nces_id,
                'success': True,
                'start_time': start_time,
                'end_time': end_time,
                'total_minutes': total_minutes,
                'source_url': result.get('source_url'),
                'confidence': confidence,
                'notes': result.get('notes', 'Extracted via Gemini MCP'),
                'needs_manual_review': confidence < 0.6  # Low confidence still needs review
            })

        return validated

    # =========================================================================
    # Result Recording
    # =========================================================================

    def _record_results(
        self,
        batch_id: int,
        validated_results: List[Dict],
        districts: List[EnrichmentQueue]
    ) -> Dict:
        """
        Record results to database

        Args:
            batch_id: Batch ID
            validated_results: Validated results
            districts: Original queue items

        Returns:
            Summary statistics
        """
        successes = 0
        manual_review = 0

        for result in validated_results:
            nces_id = result.get('nces_id')

            if result.get('success') and not result.get('needs_manual_review'):
                # Success - complete enrichment
                self._record_success(nces_id, result)
                successes += 1
            else:
                # Failed or needs review - mark for manual review
                self._mark_manual_review(nces_id, result)
                manual_review += 1

        return {
            'batch_id': batch_id,
            'districts_processed': len(validated_results),
            'successes': successes,
            'manual_review': manual_review,
            'success_rate': successes / len(validated_results) if validated_results else 0
        }

    def _record_success(self, nces_id: str, result: Dict):
        """Record successful extraction"""
        from sqlalchemy import text

        self.session.execute(
            text("""
                SELECT complete_enrichment(
                    :district_id, :tier, :result::jsonb, :success, :time
                )
            """),
            {
                'district_id': nces_id,
                'tier': 5,
                'result': json.dumps(result),
                'success': True,
                'time': None
            }
        )
        self.session.commit()

    def _mark_manual_review(self, nces_id: str, result: Dict):
        """Mark district for manual review"""
        queue_item = self.session.query(EnrichmentQueue).filter_by(
            district_id=nces_id,
            current_tier=5
        ).first()

        if queue_item:
            queue_item.status = 'manual_review'
            queue_item.tier_5_result = result
            queue_item.completed_at = datetime.utcnow()
            queue_item.final_success = False

        self.session.commit()


def main():
    """Example usage"""
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        processor = Tier5Processor(session)

        # Get districts at Tier 5
        districts = session.query(EnrichmentQueue).filter_by(
            current_tier=5, status='pending'
        ).limit(10).all()

        if districts:
            # Build search queries
            queries = processor._build_search_queries(districts)

            print(f"Generated {len(queries)} search queries:")
            print(json.dumps(queries[0], indent=2))

            # Process batch (will show placeholder message)
            result = processor.process_batch(districts)
            print(f"\nBatch processing result: {result}")

        else:
            print("No districts at Tier 5")


if __name__ == '__main__':
    main()
