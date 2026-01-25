#!/usr/bin/env python3
"""
Claude Review Processor (formerly Tier 4)

This processor handles interactive bell schedule extraction in Claude Code sessions.
After automated Tiers 1-3 fail, districts escalate here for interactive processing
with full tool access. If Claude Review cannot extract the schedule, districts
move to Manual Review (terminal state).

Pipeline Flow:
    Tier 1 (Firecrawl) → Tier 2 (HTML) → Tier 3 (PDF/OCR) → Claude Review → Manual Review

**Cost**: $0 (included in Claude Max subscription)

**Integration Model**: Interactive with human oversight
    - Script generates batch requests with district context
    - User runs script and presents batch to Claude Code session
    - Claude Code uses WebFetch, Read, Bash, etc. to find schedules
    - Claude Code calls record_schedule_from_session() to persist results
    - Failed districts go to Manual Review

Workflow:
    1. Run: python run_multi_tier_enrichment.py --claude-review
    2. Script outputs batch request for pending Claude Review districts
    3. In Claude Code session, process each district using available tools
    4. Use record_schedule_from_session() to save found data

Usage in Claude Code Session:
    # After finding bell schedule for a district:
    from infrastructure.scripts.enrich.tier_4_processor import Tier4Processor
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        processor = Tier4Processor(session)
        result = processor.record_schedule_from_session(
            district_id='0100005',
            schedules=[
                {'grade_level': 'elementary', 'start_time': '8:00 AM', 'end_time': '2:30 PM'},
                {'grade_level': 'middle', 'start_time': '8:30 AM', 'end_time': '3:30 PM'},
                {'grade_level': 'high', 'start_time': '7:30 AM', 'end_time': '2:30 PM'}
            ],
            source_url='https://district.org/schedules',
            notes='Found on district calendar page'
        )
        print(result)
"""

import logging
import json
from typing import Dict, List, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import func

from infrastructure.database.models import District, EnrichmentQueue, EnrichmentBatch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Tier4Processor:
    """Tier 4: Claude Desktop Processing (Batched)"""

    def __init__(self, session: Session):
        """
        Initialize Tier 4 processor

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    # =========================================================================
    # Batch Preparation
    # =========================================================================

    def prepare_batch_for_claude(
        self,
        districts: List[EnrichmentQueue],
        batch_id: int = None
    ) -> Dict:
        """
        Prepare batch of districts for Claude processing

        Args:
            districts: List of EnrichmentQueue objects at Tier 4
            batch_id: Optional batch ID (will be generated if not provided)

        Returns:
            Batch specification ready for Claude
        """
        if batch_id is None:
            # Generate next batch ID
            max_id = self.session.query(
                func.max(EnrichmentBatch.id)
            ).scalar() or 0
            batch_id = max_id + 1

        # Build district contexts
        district_contexts = []
        district_ids = [d.district_id for d in districts]

        # Get District objects
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

            context = {
                'nces_id': dist_obj.nces_id,
                'name': dist_obj.name,
                'state': dist_obj.state,
                'enrollment': dist_obj.enrollment,
                'website_url': getattr(dist_obj, 'website_url', None),

                # Include all previous tier results
                'tier_1_result': queue_item.tier_1_result,
                'tier_2_result': queue_item.tier_2_result,
                'tier_3_result': queue_item.tier_3_result,

                # Include escalation context
                'cms_detected': queue_item.cms_detected,
                'content_type': queue_item.content_type,
                'escalation_reason': queue_item.escalation_reason,

                # Include attempted URLs
                'attempted_urls': self._get_attempted_urls(queue_item)
            }

            district_contexts.append(context)

        # Create batch specification
        batch = {
            'batch_id': batch_id,
            'tier': 4,
            'batch_type': 'claude_desktop',
            'district_count': len(district_contexts),
            'districts': district_contexts,
            'created_at': datetime.utcnow().isoformat(),
            'instructions': self._get_processing_instructions(districts),
            'expected_output_format': self._get_output_format_spec()
        }

        return batch

    def _get_attempted_urls(self, queue_item: EnrichmentQueue) -> List[str]:
        """Extract all URLs attempted in previous tiers"""
        urls = []

        # From Tier 1
        if queue_item.tier_1_result:
            urls_attempted = queue_item.tier_1_result.get('urls_attempted', [])
            for url_info in urls_attempted:
                if isinstance(url_info, dict):
                    urls.append(url_info.get('url'))
                else:
                    urls.append(url_info)

        # From Tier 2
        if queue_item.tier_2_result:
            source_url = queue_item.tier_2_result.get('source_url')
            if source_url:
                urls.append(source_url)

        # From Tier 3
        if queue_item.tier_3_result:
            source_url = queue_item.tier_3_result.get('source_url')
            if source_url:
                urls.append(source_url)

        return list(set(urls))  # Deduplicate

    def _get_processing_instructions(
        self,
        districts: List[EnrichmentQueue]
    ) -> str:
        """Generate processing instructions for Claude"""
        # Determine common characteristics
        cms_platforms = set(d.cms_detected for d in districts if d.cms_detected)
        content_types = set(d.content_type for d in districts if d.content_type)

        instructions = [
            "Process each district to extract bell schedule information:",
            "",
            "**Goals:**",
            "1. Find start time and end time for the school day",
            "2. Calculate total instructional minutes",
            "3. Identify source URL where schedule was found",
            "4. Assign confidence score (0.0-1.0)",
            "",
            "**Tools Available:**",
            "- Read: Read files and documents",
            "- WebFetch: Fetch web pages",
            "- Bash: Run CLI commands (curl, pdftotext, etc.)",
            "- Grep: Search within content",
            "",
            "**Approach:**",
            "- Use previous tier results as starting points",
            "- Check attempted URLs first",
            "- Try school-level pages if district pages fail",
            "- Look for PDF documents or schedule pages",
            "- Parse HTML tables, lists, or text patterns",
            "",
        ]

        if cms_platforms:
            instructions.append(f"**CMS Platforms in Batch:** {', '.join(cms_platforms)}")
            instructions.append("")

        if content_types:
            instructions.append(f"**Content Types in Batch:** {', '.join(content_types)}")
            instructions.append("")

        instructions.extend([
            "**Expected Output:**",
            "For each district, return:",
            "```json",
            "{",
            '  "nces_id": "...",',
            '  "success": true/false,',
            '  "start_time": "8:00 AM",',
            '  "end_time": "3:00 PM",',
            '  "total_minutes": 420,',
            '  "source_url": "https://...",',
            '  "confidence": 0.9,',
            '  "notes": "Regular schedule, Mon-Fri"',
            "}",
            "```",
            "",
            "**Confidence Scoring:**",
            "- 0.9-1.0: Official schedule page, clear times",
            "- 0.7-0.9: School website, reasonable inference",
            "- 0.5-0.7: Indirect source or partial information",
            "- <0.5: Low confidence, needs verification"
        ])

        return "\n".join(instructions)

    def _get_output_format_spec(self) -> Dict:
        """Get expected output format specification"""
        return {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["nces_id", "success"],
                "properties": {
                    "nces_id": {"type": "string"},
                    "success": {"type": "boolean"},
                    "start_time": {"type": "string", "pattern": r"\d{1,2}:\d{2} [AP]M"},
                    "end_time": {"type": "string", "pattern": r"\d{1,2}:\d{2} [AP]M"},
                    "total_minutes": {"type": "integer", "minimum": 180, "maximum": 540},
                    "source_url": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "notes": {"type": "string"},
                    "failure_reason": {"type": "string"}
                }
            }
        }

    # =========================================================================
    # Batch Formatting
    # =========================================================================

    def format_batch_request(self, batch: Dict) -> str:
        """
        Format batch as human-readable request for Claude

        Args:
            batch: Batch specification from prepare_batch_for_claude

        Returns:
            Formatted text to present to Claude
        """
        instructions = batch.get('instructions') or batch.get('shared_context') or """
Please search each district's website to find bell schedule information.
Extract:
- Start and end times for each grade level (Elementary, Middle, High)
- Total instructional minutes per day
- Source URL where the information was found

If unable to find bell schedule, note the reason.
"""
        lines = [
            "=" * 80,
            f"TIER 4 BATCH PROCESSING REQUEST",
            f"Batch ID: {batch['batch_id']}",
            f"Districts: {batch['district_count']}",
            f"Batch Type: {batch.get('batch_type', 'mixed')}",
            "=" * 80,
            "",
            instructions.strip(),
            "",
            "=" * 80,
            "DISTRICTS TO PROCESS",
            "=" * 80,
            ""
        ]

        for i, district in enumerate(batch['districts'], 1):
            website_url = district.get('website_url') or district.get('url') or 'Unknown'
            lines.extend([
                f"## District {i}/{batch['district_count']}",
                "",
                f"**NCES ID:** {district['nces_id']}",
                f"**Name:** {district['name']}",
                f"**State:** {district['state']}",
                f"**Enrollment:** {district.get('enrollment', 0):,}",
                f"**Website:** {website_url}",
                "",
                f"**Previous Attempts:**",
                f"- CMS: {district.get('cms_detected') or 'Unknown'}",
                f"- Content Type: {district.get('content_type') or 'Unknown'}",
                f"- Escalation Reason: {district.get('escalation_reason', 'Unknown')}",
                "",
            ])

            attempted_urls = district.get('attempted_urls', [])
            if attempted_urls:
                lines.append("**URLs Attempted:**")
                for url in attempted_urls[:5]:  # Limit to 5
                    lines.append(f"- {url}")
                lines.append("")

            # Include relevant tier results (truncated)
            if district.get('tier_3_result'):
                tier_3 = district['tier_3_result']
                if tier_3.get('source_url'):
                    lines.append(f"**Tier 3 Source:** {tier_3['source_url']}")
                if tier_3.get('confidence'):
                    lines.append(f"**Tier 3 Confidence:** {tier_3['confidence']}")
                lines.append("")

            lines.append("-" * 80)
            lines.append("")

        lines.extend([
            "=" * 80,
            "END OF BATCH",
            "=" * 80,
            "",
            "Please process each district and return results in the specified JSON format."
        ])

        return "\n".join(lines)

    # =========================================================================
    # Result Recording
    # =========================================================================

    def record_batch_results(
        self,
        batch_id: int,
        claude_results: List[Dict],
        processing_time_seconds: int = None
    ) -> Dict:
        """
        Record results from Claude processing

        Args:
            batch_id: Batch ID that was processed
            claude_results: List of district results from Claude
            processing_time_seconds: Optional processing time

        Returns:
            Summary of recorded results
        """
        logger.info(f"Recording results for batch {batch_id}: {len(claude_results)} districts")

        success_count = 0
        failure_count = 0

        for result in claude_results:
            nces_id = result.get('nces_id')
            if not nces_id:
                logger.warning(f"Result missing nces_id: {result}")
                continue

            # Get queue item
            queue_item = self.session.query(EnrichmentQueue).filter_by(
                district_id=nces_id,
                current_tier=4
            ).first()

            if not queue_item:
                logger.warning(f"Queue item not found for {nces_id}")
                continue

            # Record result
            if result.get('success') and result.get('confidence', 0) >= 0.7:
                # High confidence success - complete enrichment
                self._record_success(nces_id, result)
                success_count += 1
            elif result.get('success') and result.get('confidence', 0) < 0.7:
                # Low confidence - escalate to Tier 5
                self._record_escalation(nces_id, result)
                failure_count += 1
            else:
                # Failed - escalate to Tier 5
                self._record_escalation(nces_id, result)
                failure_count += 1

        # Record batch metadata
        batch = EnrichmentBatch(
            id=batch_id,
            batch_type='tier_4_claude',
            tier=4,
            district_count=len(claude_results),
            success_count=success_count,
            failure_count=failure_count,
            status='completed',
            processing_time_seconds=processing_time_seconds,
            submitted_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )

        self.session.add(batch)
        self.session.commit()

        summary = {
            'batch_id': batch_id,
            'districts_processed': len(claude_results),
            'successes': success_count,
            'escalations_to_tier_5': failure_count,
            'success_rate': success_count / len(claude_results) if claude_results else 0
        }

        logger.info(f"Batch {batch_id} complete: {summary}")
        return summary

    def _record_success(self, nces_id: str, result: Dict):
        """Record successful extraction"""
        from sqlalchemy import text

        self.session.execute(
            text("""
                SELECT complete_enrichment(
                    :district_id, :tier, :result, :success, :time
                )
            """),
            {
                'district_id': nces_id,
                'tier': 4,
                'result': json.dumps(result),
                'success': True,
                'time': None
            }
        )

    def _record_escalation(self, nces_id: str, result: Dict):
        """Record escalation to Tier 5"""
        from sqlalchemy import text

        escalation_reason = result.get('failure_reason', 'low_confidence_or_failed')

        self.session.execute(
            text("""
                SELECT escalate_to_next_tier(
                    :district_id, :tier, :result, :reason,
                    NULL, NULL, NULL
                )
            """),
            {
                'district_id': nces_id,
                'tier': 4,
                'result': json.dumps(result),
                'reason': escalation_reason
            }
        )

    # =========================================================================
    # Individual District Processing (for automatic mode)
    # =========================================================================

    def process_district(
        self,
        district_id: str,
        previous_results: Dict = None
    ) -> Dict:
        """
        Process a single district through Tier 4.

        This method attempts automated extraction using web fetching and
        enhanced pattern matching. For complex cases, it may escalate to Tier 5.

        Args:
            district_id: NCES district ID
            previous_results: Results from previous tiers

        Returns:
            Result dictionary with success, schedule_extracted, etc.
        """
        import re
        import requests
        from datetime import datetime

        start_time = datetime.utcnow()
        previous_results = previous_results or {}

        # Get district info
        district = self.session.query(District).filter_by(nces_id=district_id).first()
        if not district:
            return {
                'success': False,
                'error': 'district_not_found',
                'schedule_extracted': False
            }

        # Get URLs to try from previous tier results
        urls_to_try = []
        for tier_key in ['tier_1', 'tier_2', 'tier_3']:
            tier_result = previous_results.get(tier_key) or {}
            if isinstance(tier_result, dict):
                urls_to_try.extend(tier_result.get('schedule_urls', []))
                urls_to_try.extend(tier_result.get('urls_attempted', []))

        # Also try district website
        if hasattr(district, 'website_url') and district.website_url:
            urls_to_try.insert(0, district.website_url)

        if not urls_to_try:
            return {
                'success': False,
                'error': 'no_urls_to_try',
                'schedule_extracted': False
            }

        # Try to fetch and extract from each URL
        time_pattern = re.compile(r'(\d{1,2}):(\d{2})\s*([AaPp]\.?[Mm]\.?)')

        for url in urls_to_try[:5]:  # Limit attempts
            try:
                response = requests.get(url, timeout=30, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; LCT-Bot/1.0)'
                })

                if response.status_code == 200:
                    content = response.text

                    # Look for time patterns
                    times = time_pattern.findall(content)

                    if len(times) >= 2:
                        # Found potential schedule times
                        # Try to extract start/end times
                        schedules = []
                        for i in range(0, len(times) - 1, 2):
                            start = f"{times[i][0]}:{times[i][1]} {times[i][2]}"
                            end = f"{times[i+1][0]}:{times[i+1][1]} {times[i+1][2]}"

                            # Calculate minutes
                            try:
                                start_h = int(times[i][0])
                                start_m = int(times[i][1])
                                end_h = int(times[i+1][0])
                                end_m = int(times[i+1][1])

                                if 'p' in times[i][2].lower() and start_h != 12:
                                    start_h += 12
                                if 'p' in times[i+1][2].lower() and end_h != 12:
                                    end_h += 12

                                minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)

                                if 180 <= minutes <= 540:  # Sanity check
                                    schedules.append({
                                        'grade_level': 'elementary',  # Default
                                        'start_time': start,
                                        'end_time': end,
                                        'instructional_minutes': minutes,
                                        'confidence': 0.6,
                                        'source_url': url,
                                        'method': 'tier4_pattern'
                                    })
                            except (ValueError, IndexError):
                                continue

                        if schedules:
                            processing_time = (datetime.utcnow() - start_time).total_seconds()
                            return {
                                'success': True,
                                'schedule_extracted': True,
                                'schedules_extracted': schedules,
                                'source_url': url,
                                'confidence': 0.6,
                                'processing_time_seconds': int(processing_time)
                            }

            except requests.RequestException as e:
                logger.debug(f"Request failed for {url}: {e}")
                continue

        # No schedule found
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        return {
            'success': False,
            'error': 'no_schedule_extracted',
            'schedule_extracted': False,
            'urls_attempted': urls_to_try[:5],
            'processing_time_seconds': int(processing_time)
        }

    # =========================================================================
    # Claude Code Session Integration
    # =========================================================================

    def record_schedule_from_session(
        self,
        district_id: str,
        schedules: List[Dict],
        source_url: str = None,
        notes: str = None
    ) -> Dict:
        """
        Record bell schedule data found during a Claude Code session.

        This method is designed for use when Claude Code is processing Tier 4
        districts interactively. After finding bell schedule information,
        call this method to persist to the database.

        Args:
            district_id: NCES district ID
            schedules: List of schedule dicts, each with:
                - grade_level: 'elementary', 'middle', or 'high'
                - start_time: e.g., '8:00 AM'
                - end_time: e.g., '3:00 PM'
                - instructional_minutes: int (optional, will be calculated)
            source_url: URL where schedule was found
            notes: Optional notes about the extraction

        Returns:
            Dict with success status and details

        Example:
            processor.record_schedule_from_session(
                district_id='0100005',
                schedules=[
                    {'grade_level': 'elementary', 'start_time': '8:00 AM', 'end_time': '2:30 PM'},
                    {'grade_level': 'middle', 'start_time': '8:30 AM', 'end_time': '3:30 PM'},
                    {'grade_level': 'high', 'start_time': '7:30 AM', 'end_time': '2:30 PM'}
                ],
                source_url='https://district.org/schedules',
                notes='Found on district calendar page'
            )
        """
        from infrastructure.database.models import BellSchedule
        from datetime import datetime
        import re

        # Validate district exists
        district = self.session.query(District).filter_by(nces_id=district_id).first()
        if not district:
            return {'success': False, 'error': f'District {district_id} not found'}

        recorded = []
        errors = []

        for schedule in schedules:
            try:
                grade_level = schedule.get('grade_level', 'elementary')
                start_time = schedule.get('start_time')
                end_time = schedule.get('end_time')

                if not start_time or not end_time:
                    errors.append(f"Missing start/end time for {grade_level}")
                    continue

                # Calculate instructional minutes if not provided
                minutes = schedule.get('instructional_minutes')
                if not minutes:
                    minutes = self._calculate_minutes(start_time, end_time)

                # Create bell schedule record
                bell_schedule = BellSchedule(
                    district_id=district_id,
                    grade_level=grade_level,
                    start_time=start_time,
                    end_time=end_time,
                    instructional_minutes=minutes,
                    source_url=source_url,
                    method='tier_4_claude_session',
                    confidence=0.85,
                    notes=notes,
                    school_year='2024-25',
                    created_at=datetime.utcnow()
                )

                self.session.add(bell_schedule)
                recorded.append({
                    'grade_level': grade_level,
                    'start_time': start_time,
                    'end_time': end_time,
                    'minutes': minutes
                })

            except Exception as e:
                errors.append(f"Error recording {schedule}: {e}")

        if recorded:
            # Update enrichment queue status
            queue_item = self.session.query(EnrichmentQueue).filter_by(
                district_id=district_id
            ).first()

            if queue_item:
                queue_item.status = 'completed'
                queue_item.tier_4_result = {
                    'success': True,
                    'schedules': recorded,
                    'source_url': source_url,
                    'method': 'claude_session'
                }
                queue_item.completed_at = datetime.utcnow()

            self.session.commit()

        return {
            'success': len(recorded) > 0,
            'district_id': district_id,
            'district_name': district.name,
            'schedules_recorded': recorded,
            'errors': errors if errors else None
        }

    def _calculate_minutes(self, start_time: str, end_time: str) -> int:
        """Calculate instructional minutes from start/end times"""
        import re

        def parse_time(t: str) -> int:
            """Convert time string to minutes since midnight"""
            match = re.match(r'(\d{1,2}):(\d{2})\s*([AaPp])', t)
            if not match:
                return 0
            hours = int(match.group(1))
            minutes = int(match.group(2))
            is_pm = match.group(3).lower() == 'p'

            if is_pm and hours != 12:
                hours += 12
            elif not is_pm and hours == 12:
                hours = 0

            return hours * 60 + minutes

        start_mins = parse_time(start_time)
        end_mins = parse_time(end_time)

        return end_mins - start_mins


def main():
    """Example usage"""
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        processor = Tier4Processor(session)

        # Get districts at Tier 4
        districts = session.query(EnrichmentQueue).filter_by(
            current_tier=4, status='pending'
        ).limit(10).all()

        if districts:
            # Prepare batch
            batch = processor.prepare_batch_for_claude(districts)

            # Format for presentation
            request_text = processor.format_batch_request(batch)

            print(request_text)

            # Save batch spec to file
            with open('tier_4_batch_request.txt', 'w') as f:
                f.write(request_text)

            print("\nBatch request saved to: tier_4_batch_request.txt")
            print(f"Present this to Claude for processing.")

        else:
            print("No districts at Tier 4")


if __name__ == '__main__':
    main()
