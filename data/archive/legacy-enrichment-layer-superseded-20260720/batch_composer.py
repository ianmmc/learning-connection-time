#!/usr/bin/env python3
"""
Batch Composer
Intelligent batch composition for API-efficient enrichment processing

Composes batches by grouping similar districts to maximize context sharing and
minimize token usage across Claude Desktop and Gemini MCP processing.

Usage:
    from batch_composer import BatchComposer
    from connection import session_scope

    with session_scope() as session:
        composer = BatchComposer(session)

        # Compose Claude batches
        claude_batches = composer.compose_claude_batches(districts, batch_size=15)

        # Compose Gemini batches
        gemini_batches = composer.compose_gemini_batches(districts, batch_size=15)
"""

import logging
from typing import List, Dict, Tuple
from collections import defaultdict
import statistics

from sqlalchemy.orm import Session

from infrastructure.database.models import District, EnrichmentQueue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BatchComposer:
    """Intelligent batch composition for API efficiency"""

    def __init__(self, session: Session):
        """
        Initialize batch composer

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    # =========================================================================
    # Claude Desktop Batch Composition (Tier 4)
    # =========================================================================

    def compose_claude_batches(
        self,
        districts: List[EnrichmentQueue],
        batch_size: int = 15,
        strategy: str = 'auto'
    ) -> List[Dict]:
        """
        Compose batches for Claude Desktop processing

        Grouping strategies:
            1. CMS Platform: Group same CMS (Finalsite, SchoolBlocks, etc.)
            2. Content Type: Group similar content (PDF tables, JS-heavy, etc.)
            3. District Size: Group similar enrollment ranges
            4. Mixed: Balance across characteristics

        Args:
            districts: List of EnrichmentQueue objects at Tier 4
            batch_size: Districts per batch (10-20 recommended)
            strategy: 'auto', 'cms', 'content', 'size', or 'mixed'

        Returns:
            List of batch specifications
        """
        logger.info(f"Composing Claude batches: {len(districts)} districts, "
                   f"size={batch_size}, strategy={strategy}")

        if not districts:
            return []

        # Determine strategy
        if strategy == 'auto':
            strategy = self._determine_claude_strategy(districts)
            logger.info(f"Auto-selected strategy: {strategy}")

        # Apply strategy
        if strategy == 'cms':
            groups = self._group_by_cms(districts)
        elif strategy == 'content':
            groups = self._group_by_content_type(districts)
        elif strategy == 'size':
            groups = self._group_by_size(districts)
        else:  # mixed
            groups = self._group_mixed(districts)

        # Create batches from groups
        batches = self._create_batches_from_groups(
            groups, batch_size, tier=4, batch_type='claude'
        )

        logger.info(f"Created {len(batches)} Claude batches from {len(groups)} groups")
        return batches

    def _determine_claude_strategy(self, districts: List[EnrichmentQueue]) -> str:
        """
        Automatically determine best batching strategy

        Logic:
            - If >50% have same CMS → Use 'cms'
            - Else if >50% have same content_type → Use 'content'
            - Else → Use 'mixed'
        """
        # Count CMS platforms
        cms_counts = defaultdict(int)
        content_counts = defaultdict(int)

        for d in districts:
            if d.cms_detected:
                cms_counts[d.cms_detected] += 1
            if d.content_type:
                content_counts[d.content_type] += 1

        total = len(districts)

        # Check CMS concentration
        if cms_counts:
            max_cms_count = max(cms_counts.values())
            if max_cms_count / total > 0.5:
                return 'cms'

        # Check content type concentration
        if content_counts:
            max_content_count = max(content_counts.values())
            if max_content_count / total > 0.5:
                return 'content'

        # Default to mixed
        return 'mixed'

    def _group_by_cms(self, districts: List[EnrichmentQueue]) -> Dict[str, List]:
        """Group districts by CMS platform"""
        groups = defaultdict(list)

        for district in districts:
            cms = district.cms_detected or 'unknown'
            groups[f"cms_{cms}"].append(district)

        return dict(groups)

    def _group_by_content_type(self, districts: List[EnrichmentQueue]) -> Dict[str, List]:
        """Group districts by content type"""
        groups = defaultdict(list)

        for district in districts:
            content = district.content_type or 'mixed'
            groups[f"content_{content}"].append(district)

        return dict(groups)

    def _group_by_size(self, districts: List[EnrichmentQueue]) -> Dict[str, List]:
        """
        Group districts by enrollment size

        Size categories:
            - small: <2000 students
            - medium: 2000-10000 students
            - large: 10000-50000 students
            - xlarge: >50000 students
        """
        groups = defaultdict(list)

        # Get District objects for enrollment
        district_ids = [d.district_id for d in districts]
        district_objs = {
            d.nces_id: d
            for d in self.session.query(District).filter(
                District.nces_id.in_(district_ids)
            ).all()
        }

        for queue_item in districts:
            dist_obj = district_objs.get(queue_item.district_id)
            if not dist_obj or dist_obj.enrollment is None:
                size = 'unknown'
            elif dist_obj.enrollment < 2000:
                size = 'small'
            elif dist_obj.enrollment < 10000:
                size = 'medium'
            elif dist_obj.enrollment < 50000:
                size = 'large'
            else:
                size = 'xlarge'

            groups[f"size_{size}"].append(queue_item)

        return dict(groups)

    def _group_mixed(self, districts: List[EnrichmentQueue]) -> Dict[str, List]:
        """
        Mixed grouping strategy - balance multiple characteristics

        Creates composite keys like: "finalsite_pdf_medium"
        """
        groups = defaultdict(list)

        # Get District objects for size
        district_ids = [d.district_id for d in districts]
        district_objs = {
            d.nces_id: d
            for d in self.session.query(District).filter(
                District.nces_id.in_(district_ids)
            ).all()
        }

        for queue_item in districts:
            # Build composite key
            cms = (queue_item.cms_detected or 'unknown')[:10]  # Truncate
            content = (queue_item.content_type or 'mixed')[:10]

            # Get size
            dist_obj = district_objs.get(queue_item.district_id)
            if not dist_obj or dist_obj.enrollment is None:
                size = 'unk'
            elif dist_obj.enrollment < 5000:
                size = 'sm'
            elif dist_obj.enrollment < 25000:
                size = 'md'
            else:
                size = 'lg'

            key = f"{cms}_{content}_{size}"
            groups[key].append(queue_item)

        return dict(groups)

    # =========================================================================
    # Gemini MCP Batch Composition (Tier 5)
    # =========================================================================

    def compose_gemini_batches(
        self,
        districts: List[EnrichmentQueue],
        batch_size: int = 15,
        strategy: str = 'state'
    ) -> List[Dict]:
        """
        Compose batches for Gemini MCP web search

        Grouping strategies:
            1. State: Group by state for geographic context (default)
            2. Failure Pattern: Group by similar Tier 4 failure reasons
            3. Size: Group by enrollment size

        Args:
            districts: List of EnrichmentQueue objects at Tier 5
            batch_size: Districts per batch (10-20 recommended)
            strategy: 'state', 'failure', or 'size'

        Returns:
            List of batch specifications
        """
        logger.info(f"Composing Gemini batches: {len(districts)} districts, "
                   f"size={batch_size}, strategy={strategy}")

        if not districts:
            return []

        # Apply strategy
        if strategy == 'state':
            groups = self._group_by_state(districts)
        elif strategy == 'failure':
            groups = self._group_by_failure_pattern(districts)
        elif strategy == 'size':
            groups = self._group_by_size(districts)
        else:
            logger.warning(f"Unknown strategy '{strategy}', using 'state'")
            groups = self._group_by_state(districts)

        # Create batches from groups
        batches = self._create_batches_from_groups(
            groups, batch_size, tier=5, batch_type='gemini'
        )

        logger.info(f"Created {len(batches)} Gemini batches from {len(groups)} groups")
        return batches

    def _group_by_state(self, districts: List[EnrichmentQueue]) -> Dict[str, List]:
        """Group districts by state"""
        groups = defaultdict(list)

        # Get District objects for state
        district_ids = [d.district_id for d in districts]
        district_objs = {
            d.nces_id: d
            for d in self.session.query(District).filter(
                District.nces_id.in_(district_ids)
            ).all()
        }

        for queue_item in districts:
            dist_obj = district_objs.get(queue_item.district_id)
            state = dist_obj.state if dist_obj else 'unknown'
            groups[f"state_{state}"].append(queue_item)

        return dict(groups)

    def _group_by_failure_pattern(self, districts: List[EnrichmentQueue]) -> Dict[str, List]:
        """Group by common Tier 4 failure reasons"""
        groups = defaultdict(list)

        for district in districts:
            # Check Tier 4 result for failure reason
            tier_4_result = district.tier_4_result or {}
            failure_reason = tier_4_result.get('failure_reason', 'unknown')

            # Normalize failure reasons
            if 'confidence' in failure_reason.lower():
                pattern = 'low_confidence'
            elif 'timeout' in failure_reason.lower():
                pattern = 'timeout'
            elif 'not_found' in failure_reason.lower() or 'missing' in failure_reason.lower():
                pattern = 'not_found'
            else:
                pattern = 'other'

            groups[f"failure_{pattern}"].append(district)

        return dict(groups)

    # =========================================================================
    # Batch Creation
    # =========================================================================

    def _create_batches_from_groups(
        self,
        groups: Dict[str, List[EnrichmentQueue]],
        batch_size: int,
        tier: int,
        batch_type: str
    ) -> List[Dict]:
        """
        Create batches from grouped districts

        Args:
            groups: Dictionary of group_key -> districts
            batch_size: Maximum districts per batch
            tier: Tier number (4 or 5)
            batch_type: 'claude' or 'gemini'

        Returns:
            List of batch specifications
        """
        batches = []
        batch_id = 1

        for group_key, group_districts in groups.items():
            # Sort by enrollment (descending) for prioritization
            district_ids = [d.district_id for d in group_districts]
            district_objs = {
                d.nces_id: d
                for d in self.session.query(District).filter(
                    District.nces_id.in_(district_ids)
                ).all()
            }

            # Sort queue items by enrollment
            sorted_districts = sorted(
                group_districts,
                key=lambda d: district_objs.get(d.district_id).enrollment
                if district_objs.get(d.district_id) and district_objs.get(d.district_id).enrollment
                else 0,
                reverse=True
            )

            # Split into batches
            for i in range(0, len(sorted_districts), batch_size):
                batch_districts = sorted_districts[i:i + batch_size]

                # Build batch specification
                batch = {
                    'batch_id': batch_id,
                    'group_key': group_key,
                    'batch_type': batch_type,
                    'tier': tier,
                    'district_count': len(batch_districts),
                    'districts': self._build_district_context(
                        batch_districts, district_objs, tier
                    ),
                    'shared_context': self._get_shared_context(
                        group_key, batch_type, tier
                    ),
                    'grouping_strategy': group_key
                }

                batches.append(batch)
                batch_id += 1

        return batches

    def _build_district_context(
        self,
        queue_items: List[EnrichmentQueue],
        district_objs: Dict[str, District],
        tier: int
    ) -> List[Dict]:
        """Build district context for batch"""
        contexts = []

        for queue_item in queue_items:
            dist_obj = district_objs.get(queue_item.district_id)

            if not dist_obj:
                logger.warning(f"District {queue_item.district_id} not found")
                continue

            context = {
                'nces_id': dist_obj.nces_id,
                'name': dist_obj.name,
                'state': dist_obj.state,
                'enrollment': dist_obj.enrollment,
                'cms_detected': queue_item.cms_detected,
                'content_type': queue_item.content_type,
                'escalation_reason': queue_item.escalation_reason
            }

            # Add tier-specific context
            if tier == 4:
                # Claude needs all previous tier results
                context.update({
                    'tier_1_result': queue_item.tier_1_result,
                    'tier_2_result': queue_item.tier_2_result,
                    'tier_3_result': queue_item.tier_3_result
                })
            elif tier == 5:
                # Gemini needs school discovery results
                tier_1 = queue_item.tier_1_result or {}
                context.update({
                    'district_url': dist_obj.website_url if hasattr(dist_obj, 'website_url') else None,
                    'schools': tier_1.get('schools_found', []),
                    'attempted_urls': tier_1.get('urls_attempted', [])
                })

            contexts.append(context)

        return contexts

    def _get_shared_context(
        self,
        group_key: str,
        batch_type: str,
        tier: int
    ) -> str:
        """Generate shared context description for batch"""

        if batch_type == 'claude':
            return self._get_claude_context(group_key)
        elif batch_type == 'gemini':
            return self._get_gemini_context(group_key)
        else:
            return "Mixed content batch - use best judgment per district."

    def _get_claude_context(self, group_key: str) -> str:
        """Generate Claude-specific context"""
        contexts = {
            'cms_finalsite': (
                "Finalsite CMS sites - Heavy JavaScript rendering. "
                "Schedules typically in /about-us or /information sections. "
                "Calendar widgets common. Check for dynamic content loading."
            ),
            'cms_schoolblocks': (
                "SchoolBlocks CMS sites - Look for /pages/index.jsp URLs. "
                "Schedules often embedded in page content. May use iframes. "
                "Check for tabbed navigation."
            ),
            'cms_blackboard': (
                "Blackboard CMS sites - Enterprise portal structure. "
                "Schedules may be behind navigation menus. "
                "Check for /departments and /schools sections."
            ),
            'content_pdf': (
                "PDF-based bell schedules with table layouts. "
                "Extract structured table data. Watch for multi-page schedules. "
                "Common patterns: time blocks, period labels, grade-level sections."
            ),
            'content_heavy_js': (
                "JavaScript-heavy sites with dynamic rendering. "
                "Schedule data may be dynamically loaded. "
                "Check for JSON endpoints, AJAX calls, or embedded data attributes."
            ),
            'content_html': (
                "HTML table-based schedules. "
                "Parse DOM structure for time patterns. "
                "Common: tr/td tables, div-based layouts, dl/dt/dd lists."
            )
        }

        # Handle composite keys
        for key_pattern, context in contexts.items():
            if key_pattern in group_key:
                return context

        return "Mixed content - apply appropriate extraction strategy per district."

    def _get_gemini_context(self, group_key: str) -> str:
        """Generate Gemini-specific search context"""
        if 'state_' in group_key:
            state = group_key.split('_')[1]
            return (
                f"Search for bell schedules in {state} school districts. "
                f"Common state education board websites may have consolidated data. "
                f"Try district websites and individual school sites. "
                f"Search terms: 'bell schedule', 'daily schedule', 'school hours', "
                f"'start time', 'dismissal time'."
            )
        elif 'failure_not_found' in group_key:
            return (
                "These districts had no schedule data found in Tier 1-4. "
                "Try broader web search including state education databases, "
                "local news articles, and community resources."
            )
        elif 'failure_low_confidence' in group_key:
            return (
                "These districts had low-confidence extractions. "
                "Search for alternative schedule sources. "
                "Verify with multiple sources if possible."
            )
        else:
            return (
                "Web search for missing bell schedule data. "
                "Try district sites, school sites, state databases, and public documents."
            )

    # =========================================================================
    # Batch Statistics
    # =========================================================================

    def analyze_batch_composition(self, batches: List[Dict]) -> Dict:
        """
        Analyze batch composition for optimization insights

        Returns statistics about batch characteristics
        """
        stats = {
            'total_batches': len(batches),
            'total_districts': sum(b['district_count'] for b in batches),
            'batch_sizes': [b['district_count'] for b in batches],
            'groups': defaultdict(int)
        }

        # Batch size statistics
        if stats['batch_sizes']:
            stats['batch_size_stats'] = {
                'min': min(stats['batch_sizes']),
                'max': max(stats['batch_sizes']),
                'mean': statistics.mean(stats['batch_sizes']),
                'median': statistics.median(stats['batch_sizes'])
            }

        # Group distribution
        for batch in batches:
            stats['groups'][batch['group_key']] += batch['district_count']

        return stats


def main():
    """Example usage"""
    from connection import session_scope

    with session_scope() as session:
        composer = BatchComposer(session)

        # Get some districts at Tier 4
        from models import EnrichmentQueue
        districts = session.query(EnrichmentQueue).filter_by(
            current_tier=4, status='pending'
        ).limit(50).all()

        if districts:
            # Compose batches
            batches = composer.compose_claude_batches(districts, batch_size=15)

            # Analyze composition
            stats = composer.analyze_batch_composition(batches)

            print(f"Created {len(batches)} batches:")
            print(f"  Total districts: {stats['total_districts']}")
            print(f"  Batch sizes: {stats['batch_size_stats']}")
            print(f"  Groups: {dict(stats['groups'])}")
        else:
            print("No districts at Tier 4")


if __name__ == '__main__':
    main()
