#!/usr/bin/env python3
"""
Tier 5 Processor: Gemini Chat MCP (mcp__gemini__gemini-chat)
Final fallback using Gemini's synthesized knowledge to find bell schedules

This tier uses the gemini-chat MCP tool for AI-assisted research when all
local discovery and web search methods have been exhausted. Gemini provides
synthesized knowledge about school districts, including:
- District-wide standardized schedules (when they exist)
- Representative sample schedules (when times vary by school)

**Key Design Decision**: Tier 5 always tries to extract usable times.
Even if schedules vary by school, we request representative samples
from named schools. Only mark as manual_review if no times extractable.

**Cost**: $0 (Gemini MCP via local server)

**MCP Tool**: mcp__gemini__gemini-chat
    - Invoked by Claude to chat with Gemini AI
    - Returns synthesized knowledge about school schedules
    - Provides representative samples when district-wide times don't exist

Workflow:
    1. Queue manager prepares batch (5-10 districts)
    2. For each district, build a gemini-chat prompt requesting either
       district-wide schedules OR representative samples
    3. Claude invokes mcp__gemini__gemini-chat for each district
    4. Parse and extract times (even from representative samples)
    5. Record to database with appropriate confidence level

Usage:
    from tier_5_processor import Tier5Processor
    from connection import session_scope

    with session_scope() as session:
        processor = Tier5Processor(session)

        # Get prompts to send to gemini-chat
        prompts = processor.build_gemini_chat_prompts(districts)

        # For each prompt, Claude should invoke:
        # mcp__gemini__gemini-chat(message=prompt, context="educational research")

        # After getting responses, record them:
        processor.record_gemini_responses(districts, responses)
"""

import logging
import json
from typing import Dict, List, Optional
from datetime import datetime
import re

from sqlalchemy.orm import Session

from infrastructure.database.models import District, EnrichmentQueue, EnrichmentBatch
from infrastructure.database.verification import validate_schedule_plausibility

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Tier5Processor:
    """
    Tier 5: Gemini Chat MCP (mcp__gemini__gemini-chat)

    Uses Gemini's synthesized knowledge to extract bell schedules.
    Always attempts to get usable times - either district-wide schedules
    or representative samples from named schools.

    Terminal states:
    - completed: Times extracted (district-wide or representative)
    - manual_review: Gemini couldn't provide usable schedule data
    """

    # Time validation pattern
    TIME_PATTERN = re.compile(
        r'\b(\d{1,2}):(\d{2})\s*([AaPp][Mm])\b'
    )

    # MCP tool name for reference
    MCP_TOOL = "mcp__gemini__gemini-chat"

    def __init__(self, session: Session):
        """
        Initialize Tier 5 processor

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    # =========================================================================
    # Gemini Chat Prompt Building
    # =========================================================================

    def build_gemini_chat_prompts(
        self,
        districts: List[EnrichmentQueue]
    ) -> List[Dict]:
        """
        Build prompts for mcp__gemini__gemini-chat for each district.

        These prompts are designed to be passed to the gemini-chat MCP tool
        by Claude during interactive processing.

        Args:
            districts: List of EnrichmentQueue objects at Tier 5

        Returns:
            List of dicts with 'nces_id', 'district_name', 'prompt', and 'context'
        """
        prompts = []

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

            website_url = getattr(dist_obj, 'website_url', None) or 'Unknown'

            prompt = f"""What are the bell schedule times for {dist_obj.name} in {dist_obj.state}? I need start and end times for the 2024-25 or 2025-26 school year.

District website: {website_url}

If this district has standardized schedules, provide:
1. Elementary school: start time - end time
2. Middle school: start time - end time
3. High school: start time - end time

If schedules vary by individual school, provide REPRESENTATIVE EXAMPLES:
1. One high school (name the school) - start time, end time
2. One middle school (name the school) - start time, end time
3. One elementary school (name the school) - start time, end time

Please provide specific times like "7:30 AM - 2:45 PM" for each level. Representative samples are acceptable."""

            prompts.append({
                'nces_id': dist_obj.nces_id,
                'district_name': dist_obj.name,
                'state': dist_obj.state,
                'website_url': website_url,
                'prompt': prompt,
                'context': 'educational research'
            })

        return prompts

    def format_mcp_invocation(self, prompt_info: Dict) -> str:
        """
        Format the MCP tool invocation for Claude to use.

        Args:
            prompt_info: Dict from build_gemini_chat_prompts

        Returns:
            Formatted string showing how to invoke the MCP tool
        """
        return f"""mcp__gemini__gemini-chat(
    message="{prompt_info['prompt']}",
    context="{prompt_info['context']}"
)"""

    def parse_gemini_response(
        self,
        nces_id: str,
        district_name: str,
        gemini_response: str
    ) -> Dict:
        """
        Parse a gemini-chat response into structured schedule data.

        Always attempts to extract times, even if response says schedules
        vary by school - we want representative samples in that case.

        Args:
            nces_id: NCES district ID
            district_name: District name
            gemini_response: Raw text response from gemini-chat

        Returns:
            Parsed schedule data dict
        """
        response_lower = gemini_response.lower()

        # Check if this is a representative sample (schedules vary by school)
        representative_indicators = [
            "vary by school",
            "varies by school",
            "vary significantly",
            "not standardized",
            "no district-wide",
            "school-specific",
            "representative",
            "example"
        ]
        is_representative_sample = any(
            indicator in response_lower for indicator in representative_indicators
        )

        # Try to extract times from response (district-wide OR representative)
        schedules = []
        levels = ['elementary', 'middle', 'high']

        for level in levels:
            # Look for times near level mentions - expanded patterns
            level_patterns = [
                # Standard patterns
                rf'{level}[^.]*?(\d{{1,2}}:\d{{2}}\s*[AaPp][Mm])[^.]*?(\d{{1,2}}:\d{{2}}\s*[AaPp][Mm])',
                rf'{level}[:\s]+(\d{{1,2}}:\d{{2}}\s*[AaPp][Mm])\s*[-–to]+\s*(\d{{1,2}}:\d{{2}}\s*[AaPp][Mm])',
                # Time range patterns (7:30 AM - 2:30 PM)
                rf'{level}[^.]*?(\d{{1,2}}:\d{{2}}\s*[AaPp][Mm])\s*[-–—]+\s*(\d{{1,2}}:\d{{2}}\s*[AaPp][Mm])',
                # Approximate patterns (approximately 7:30 AM - 2:30 PM)
                rf'{level}[^.]*?approximately\s*(\d{{1,2}}:\d{{2}}\s*[AaPp][Mm])\s*[-–—]+\s*(\d{{1,2}}:\d{{2}}\s*[AaPp][Mm])',
            ]

            for pattern in level_patterns:
                match = re.search(pattern, response_lower, re.IGNORECASE)
                if match:
                    start_time = match.group(1).upper().replace(' ', '')
                    end_time = match.group(2).upper().replace(' ', '')

                    # Calculate minutes
                    minutes = self._calculate_minutes(start_time, end_time)

                    schedules.append({
                        'grade_level': level,
                        'start_time': start_time,
                        'end_time': end_time,
                        'instructional_minutes': minutes
                    })
                    break

        if schedules:
            # Determine confidence based on source type
            confidence = 0.6 if is_representative_sample else 0.7
            notes_suffix = ' (representative sample)' if is_representative_sample else ''

            return {
                'nces_id': nces_id,
                'success': True,
                'schedules': schedules,
                'confidence': confidence,
                'is_representative_sample': is_representative_sample,
                'raw_response': gemini_response,
                'notes_suffix': notes_suffix,
                'needs_manual_review': len(schedules) < 3  # Review if not all levels found
            }
        else:
            # True failure - could not extract any usable times
            return {
                'nces_id': nces_id,
                'success': False,
                'reason': 'Could not parse schedule times from Gemini response',
                'raw_response': gemini_response,
                'needs_manual_review': True
            }

    def _calculate_minutes(self, start_time: str, end_time: str) -> int:
        """Calculate instructional minutes between two times."""
        try:
            from datetime import datetime

            # Normalize format
            start = start_time.replace(' ', '').upper()
            end = end_time.replace(' ', '').upper()

            # Parse times
            start_dt = datetime.strptime(start, '%I:%M%p')
            end_dt = datetime.strptime(end, '%I:%M%p')

            # Calculate difference
            diff = (end_dt - start_dt).seconds // 60

            return diff if diff > 0 else diff + 720  # Handle overnight
        except Exception:
            return 360  # Default to 6 hours

    def record_gemini_responses(
        self,
        districts: List[EnrichmentQueue],
        responses: List[Dict]
    ) -> Dict:
        """
        Record parsed Gemini responses to database.

        Args:
            districts: List of EnrichmentQueue objects
            responses: List of parsed response dicts from parse_gemini_response

        Returns:
            Summary statistics
        """
        successes = 0
        representative_samples = 0
        manual_review = 0

        for response in responses:
            nces_id = response.get('nces_id')

            if response.get('success'):
                self._save_schedules(nces_id, response)
                successes += 1
                if response.get('is_representative_sample'):
                    representative_samples += 1
            else:
                self._mark_manual_review(nces_id, response)
                manual_review += 1

        return {
            'districts_processed': len(responses),
            'successes': successes,
            'representative_samples': representative_samples,
            'manual_review': manual_review
        }

    def _save_schedules(self, nces_id: str, response: Dict):
        """Save extracted schedules to database."""
        from infrastructure.database.models import BellSchedule

        notes_suffix = response.get('notes_suffix', '')
        base_notes = f'Extracted via Tier 5 Gemini Chat MCP{notes_suffix}'

        for schedule in response.get('schedules', []):
            # REQ-038: Validate schedule plausibility before database insertion
            validation = validate_schedule_plausibility(schedule)
            if not validation['valid']:
                logger.warning(
                    f"Skipping invalid schedule for {nces_id}: {validation['errors']}"
                )
                continue

            # Log warnings but don't block
            if validation['warnings']:
                logger.info(f"Schedule warnings for {nces_id}: {validation['warnings']}")

            # Check if exists
            existing = self.session.query(BellSchedule).filter_by(
                district_id=nces_id,
                year='2025-26',
                grade_level=schedule['grade_level']
            ).first()

            if existing:
                existing.start_time = schedule['start_time']
                existing.end_time = schedule['end_time']
                existing.instructional_minutes = schedule['instructional_minutes']
                existing.method = 'automated_enrichment'
                existing.confidence = 'medium'
                existing.notes = base_notes
            else:
                bell = BellSchedule(
                    district_id=nces_id,
                    year='2025-26',
                    grade_level=schedule['grade_level'],
                    start_time=schedule['start_time'],
                    end_time=schedule['end_time'],
                    instructional_minutes=schedule['instructional_minutes'],
                    method='automated_enrichment',
                    confidence='medium',
                    notes=base_notes
                )
                self.session.add(bell)

        # Update queue
        queue_item = self.session.query(EnrichmentQueue).filter_by(
            district_id=nces_id
        ).first()
        if queue_item:
            queue_item.status = 'completed'
            queue_item.current_tier = 5
            queue_item.tier_5_result = response

        self.session.commit()

    def _mark_manual_review(self, nces_id: str, response: Dict):
        """Mark district as needing manual review - Tier 5 couldn't extract data."""
        queue_item = self.session.query(EnrichmentQueue).filter_by(
            district_id=nces_id
        ).first()
        if queue_item:
            queue_item.status = 'manual_review'
            queue_item.current_tier = 5
            queue_item.tier_5_result = response
            queue_item.notes = response.get('reason', 'Tier 5 extraction failed')
        self.session.commit()



def main():
    """
    Example usage - demonstrates Tier 5 Gemini Chat workflow.

    In practice, Claude invokes mcp__gemini__gemini-chat for each prompt.
    """
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        processor = Tier5Processor(session)

        # Get districts at Tier 5
        districts = session.query(EnrichmentQueue).filter_by(
            current_tier=5, status='pending'
        ).limit(5).all()

        if not districts:
            print("No districts at Tier 5")
            return

        # Step 1: Build prompts for gemini-chat
        prompts = processor.build_gemini_chat_prompts(districts)

        print("=" * 80)
        print("TIER 5: GEMINI CHAT MCP PROMPTS")
        print("=" * 80)

        for i, prompt_info in enumerate(prompts, 1):
            print(f"\n## District {i}/{len(prompts)}: {prompt_info['district_name']} ({prompt_info['state']})")
            print(f"NCES ID: {prompt_info['nces_id']}")
            print(f"\n**To invoke:**")
            print(f"  Tool: {processor.MCP_TOOL}")
            print(f"  Message: {prompt_info['prompt'][:100]}...")
            print(f"  Context: {prompt_info['context']}")

        print("\n" + "=" * 80)
        print("After invoking gemini-chat for each district, use:")
        print("  processor.parse_gemini_response(nces_id, name, response)")
        print("  processor.record_gemini_responses(districts, parsed_responses)")
        print("=" * 80)


if __name__ == '__main__':
    main()
