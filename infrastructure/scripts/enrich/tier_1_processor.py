#!/usr/bin/env python3
"""
Tier 1 Processor: Firecrawl Discovery + Playwright Fallback
Discovers bell schedule pages using Firecrawl's intelligent map endpoint

Tasks:
    - Use Firecrawl /v1/map to discover actual bell schedule URLs
    - Fall back to Playwright scraper if Firecrawl unavailable
    - Extract bell schedules using ContentParser
    - Identify CMS platform and security blocks

Cost: $0 (local compute only - self-hosted Firecrawl)

Usage:
    from tier_1_processor import Tier1Processor
    from connection import session_scope

    with session_scope() as session:
        processor = Tier1Processor(session)
        result = processor.process_district('0622710')  # LA Unified
"""

import logging
import requests
import time
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from urllib.parse import urljoin, urlparse

from sqlalchemy.orm import Session

from infrastructure.database.models import District, EnrichmentQueue
from infrastructure.scripts.enrich.firecrawl_discovery import (
    FirecrawlDiscovery,
    extract_bell_schedules_all,
    get_expected_grade_levels,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Scraper service configuration
SCRAPER_BASE_URL = "http://localhost:3000"
SCRAPER_TIMEOUT = 120  # seconds


class Tier1Processor:
    """Tier 1: Firecrawl Discovery with Playwright fallback"""

    def __init__(self, session: Session, scraper_url: str = SCRAPER_BASE_URL):
        """
        Initialize Tier 1 processor

        Args:
            session: SQLAlchemy database session
            scraper_url: URL of scraper service (default: http://localhost:3000)
        """
        self.session = session
        self.scraper_url = scraper_url

        # Initialize Firecrawl discovery
        self.firecrawl = FirecrawlDiscovery()
        self.firecrawl_available = self.firecrawl.is_available()
        if self.firecrawl_available:
            logger.info("Firecrawl service is available - using intelligent discovery")
        else:
            logger.warning("Firecrawl not available - falling back to pattern matching")

        self._check_scraper_health()

    def _check_scraper_health(self):
        """Check if scraper service is healthy"""
        try:
            response = requests.get(f"{self.scraper_url}/health", timeout=5)
            response.raise_for_status()
            logger.info("Scraper service is healthy")
        except Exception as e:
            logger.warning(f"Scraper service may not be available: {e}")

    # =========================================================================
    # Firecrawl-Based Discovery
    # =========================================================================

    def _process_with_firecrawl(
        self,
        district_id: str,
        district_name: str,
        district_url: str,
        expected_levels: List[str],
        start_time: float
    ) -> Dict:
        """
        Process district using Firecrawl's intelligent map discovery.

        Args:
            district_id: NCES district ID
            district_name: District name
            district_url: District website URL
            expected_levels: Expected grade levels (elementary, middle, high)
            start_time: Processing start time

        Returns:
            Result dictionary with discovery findings
        """
        logger.info(f"Using Firecrawl discovery for {district_name}")

        try:
            # Step 1: Discover bell schedule URLs using Firecrawl map
            discovered_urls = self.firecrawl.discover_bell_schedule_urls(district_url)
            logger.info(f"Firecrawl discovered {len(discovered_urls)} potential URLs")

            if not discovered_urls:
                # Try school-level discovery
                logger.info("No district-level URLs, trying school-level discovery")
                school_sites = self.firecrawl.discover_school_sites(district_url)
                logger.info(f"Found {len(school_sites)} school sites")

                for school_url in school_sites[:5]:
                    school_urls = self.firecrawl.discover_bell_schedule_urls(school_url)
                    discovered_urls.extend(school_urls[:3])

            # Step 2: Extract bell schedules from discovered URLs
            schedules_extracted = []
            urls_with_content = []

            if discovered_urls:
                schedules = extract_bell_schedules_all(
                    district_url,
                    max_urls=min(10, len(discovered_urls)),
                    expected_levels=expected_levels
                )

                for schedule_data, source_url in schedules:
                    schedules_extracted.append({
                        'grade_level': schedule_data.get('grade_level'),
                        'start_time': schedule_data.get('start_time'),
                        'end_time': schedule_data.get('end_time'),
                        'instructional_minutes': schedule_data.get('instructional_minutes'),
                        'confidence': schedule_data.get('confidence', 0.8),
                        'source_url': source_url,
                        'method': schedule_data.get('source_method', 'firecrawl')
                    })
                    urls_with_content.append({
                        'url': source_url,
                        'found': True,
                        'has_schedule_content': True,
                        'level': 'district'
                    })

            processing_time = int(time.time() - start_time)

            result = {
                'success': True,
                'district_id': district_id,
                'district_name': district_name,
                'district_url': district_url,
                'discovery_method': 'firecrawl_map',
                'urls_discovered': len(discovered_urls),
                'urls_attempted': urls_with_content + [
                    {'url': u, 'found': False, 'has_schedule_content': False}
                    for u in discovered_urls[:10] if u not in [x['url'] for x in urls_with_content]
                ],
                'bell_schedule_found': len(schedules_extracted) > 0,
                'schedules_extracted': schedules_extracted,
                'schools_found': [],
                'school_count': 0,
                'cms_detected': None,
                'content_type': 'html',
                'security_blocked': False,
                'security_details': {'blocked': False},
                'processing_time_seconds': processing_time,
                'timestamp': datetime.utcnow().isoformat()
            }

            # Determine escalation
            if schedules_extracted:
                result['escalation_needed'] = False
                result['escalation_reason'] = None
            else:
                result['escalation_needed'] = True
                result['escalation_reason'] = 'firecrawl_no_schedules_extracted'

            logger.info(f"Firecrawl completed for {district_id}: "
                       f"urls_discovered={len(discovered_urls)}, "
                       f"schedules_extracted={len(schedules_extracted)}")

            return result

        except Exception as e:
            logger.error(f"Firecrawl processing failed for {district_id}: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'firecrawl_error: {str(e)}',
                'district_id': district_id,
                'discovery_method': 'firecrawl_failed',
                'escalation_needed': True,
                'escalation_reason': 'firecrawl_error'
            }

    # =========================================================================
    # Main Processing
    # =========================================================================

    def process_district(self, district_id: str) -> Dict:
        """
        Process a single district through Tier 1

        Args:
            district_id: NCES district ID

        Returns:
            Result dictionary with discovery findings
        """
        logger.info(f"Processing district {district_id} at Tier 1")
        start_time = time.time()

        # Get district from database
        district = self.session.query(District).filter_by(
            nces_id=district_id
        ).first()

        if not district:
            logger.error(f"District {district_id} not found in database")
            return {
                'success': False,
                'error': 'district_not_found',
                'district_id': district_id
            }

        # Check if district has website URL, search if missing
        district_url = getattr(district, 'website_url', None)
        if not district_url:
            logger.info(f"District {district_id} has no website URL, searching...")
            district_url = self._search_for_district_url(district.name, district.state)
            if district_url:
                # Save the discovered URL to the database
                district.website_url = district_url
                self.session.commit()
                logger.info(f"Found and saved URL for {district.name}: {district_url}")
            else:
                logger.warning(f"Could not find website URL for {district.name}")
                return {
                    'success': False,
                    'error': 'no_website_url_found',
                    'district_id': district_id,
                    'district_name': district.name,
                    'escalation_needed': True,
                    'escalation_reason': 'no_website_url'
                }

        try:
            # Get expected grade levels from district
            gslo = getattr(district, 'grade_span_low', None)
            gshi = getattr(district, 'grade_span_high', None)
            expected_levels = get_expected_grade_levels(gslo, gshi)

            # Try Firecrawl-based discovery first
            if self.firecrawl_available:
                result = self._process_with_firecrawl(
                    district_id, district.name, district_url, expected_levels, start_time
                )
                if result.get('bell_schedule_found') and result.get('schedules_extracted'):
                    return result
                logger.info(f"Firecrawl discovery didn't find schedules, trying fallback")

            # Fallback to scraper-based discovery
            discovery_result = self._discover_schools(district_url, district.state)

            # Test common bell schedule URLs (fallback)
            schedule_urls = self._test_common_schedule_urls(
                district_url,
                discovery_result.get('schools', [])
            )

            # Detect CMS platform
            cms_detected = self._detect_cms(district_url, discovery_result)

            # Check for security blocks
            security_status = self._check_security_blocks(discovery_result)

            # Compile results
            processing_time = int(time.time() - start_time)

            result = {
                'success': True,
                'district_id': district_id,
                'district_name': district.name,
                'district_url': district_url,
                'discovery_method': 'fallback_pattern_matching',
                'schools_found': discovery_result.get('schools', []),
                'school_count': len(discovery_result.get('schools', [])),
                'urls_attempted': schedule_urls,
                'bell_schedule_found': any(
                    url.get('found') and url.get('has_schedule_content')
                    for url in schedule_urls
                ),
                'schedules_extracted': [],
                'cms_detected': cms_detected,
                'content_type': self._determine_content_type(discovery_result, schedule_urls),
                'security_blocked': security_status.get('blocked', False),
                'security_details': security_status,
                'processing_time_seconds': processing_time,
                'timestamp': datetime.utcnow().isoformat()
            }

            # Determine escalation
            result['escalation_needed'] = self._should_escalate(result)
            result['escalation_reason'] = self._get_escalation_reason(result)

            logger.info(f"Tier 1 completed for {district_id}: "
                       f"schools={result['school_count']}, "
                       f"schedule_found={result['bell_schedule_found']}, "
                       f"escalate={result['escalation_needed']}")

            return result

        except Exception as e:
            logger.error(f"Tier 1 processing failed for {district_id}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'district_id': district_id,
                'processing_time_seconds': int(time.time() - start_time)
            }

    # =========================================================================
    # Discovery Methods
    # =========================================================================

    def _search_for_district_url(self, district_name: str, state: str) -> Optional[str]:
        """
        Search for district website URL using web search when not in database.

        Args:
            district_name: Name of the school district
            state: Two-letter state code

        Returns:
            District website URL if found, None otherwise
        """
        import subprocess
        import json as json_module

        # Build search query
        query = f"{district_name} {state} school district official website"
        logger.info(f"Searching for district URL: {query}")

        try:
            # Use curl to call Claude's WebSearch-like functionality
            # In practice, this would be called by Claude during interactive processing
            # For automated runs, we'll use a simple heuristic approach

            # Try common URL patterns first
            name_slug = district_name.lower()
            # Remove common suffixes
            for suffix in [' school district', ' schools', ' unified', ' independent', ' public', ' city', ' county']:
                name_slug = name_slug.replace(suffix, '')
            name_slug = name_slug.strip().replace(' ', '')

            # Common URL patterns to try
            patterns = [
                f"https://www.{name_slug}.k12.{state.lower()}.us",
                f"https://{name_slug}.k12.{state.lower()}.us",
                f"https://www.{name_slug}schools.org",
                f"https://www.{name_slug}isd.org",
                f"https://www.{name_slug}usd.org",
            ]

            for url in patterns:
                try:
                    response = requests.head(url, timeout=5, allow_redirects=True)
                    if response.status_code == 200:
                        logger.info(f"Found district URL via pattern: {url}")
                        return response.url  # Return final URL after redirects
                except Exception:
                    continue

            # If patterns don't work, log that manual search is needed
            logger.warning(f"Could not find URL for {district_name}, {state} - needs WebSearch")
            return None

        except Exception as e:
            logger.error(f"URL search failed for {district_name}: {e}")
            return None

    def _discover_schools(self, district_url: str, state: str) -> Dict:
        """
        Discover school subsites using scraper service

        Args:
            district_url: District homepage URL
            state: Two-letter state code

        Returns:
            Discovery result from scraper
        """
        try:
            payload = {
                'districtUrl': district_url,
                'state': state,
                'representativeOnly': True
            }

            response = requests.post(
                f"{self.scraper_url}/discover",
                json=payload,
                timeout=SCRAPER_TIMEOUT
            )

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            logger.error(f"School discovery timed out for {district_url}")
            return {'success': False, 'error': 'timeout', 'schools': []}

        except Exception as e:
            logger.error(f"School discovery failed for {district_url}: {e}")
            return {'success': False, 'error': str(e), 'schools': []}

    def _test_common_schedule_urls(
        self,
        district_url: str,
        schools: List[Dict]
    ) -> List[Dict]:
        """
        Test common bell schedule URL patterns

        Common patterns:
            - /bell-schedule
            - /daily-schedule
            - /information/bell-schedule
            - /about-us/bell-schedule
            - /parents/bell-schedule
            - /academics/bell-schedule
        """
        patterns = [
            '/bell-schedule',
            '/daily-schedule',
            '/information/bell-schedule',
            '/about-us/bell-schedule',
            '/parents/bell-schedule',
            '/academics/bell-schedule',
            '/student-life/bell-schedule',
            '/schedules/bell-schedule'
        ]

        urls_tested = []

        # Test at district level
        for pattern in patterns:
            url = urljoin(district_url, pattern)
            result = self._test_url(url)
            urls_tested.append({
                'url': url,
                'level': 'district',
                'found': result.get('found', False),
                'status_code': result.get('status_code'),
                'has_schedule_content': result.get('has_schedule_content', False)
            })

        # Test at school level (first 3 schools only to avoid overload)
        for school in schools[:3]:
            school_url = school.get('url')
            if not school_url:
                continue

            for pattern in patterns[:3]:  # Fewer patterns for schools
                url = urljoin(school_url, pattern)
                result = self._test_url(url)
                urls_tested.append({
                    'url': url,
                    'level': 'school',
                    'school_name': school.get('name'),
                    'found': result.get('found', False),
                    'status_code': result.get('status_code'),
                    'has_schedule_content': result.get('has_schedule_content', False)
                })

        return urls_tested

    def _test_url(self, url: str) -> Dict:
        """
        Test if URL exists and contains schedule content

        Args:
            url: URL to test

        Returns:
            Result with found status and content hints
        """
        try:
            # Simple HEAD request first
            response = requests.head(url, timeout=10, allow_redirects=True)

            if response.status_code == 200:
                # If HEAD succeeded, try GET to check content
                get_response = requests.get(url, timeout=15)
                content_lower = get_response.text.lower()

                # Check for schedule-related content
                has_schedule_content = any(
                    term in content_lower
                    for term in ['bell', 'schedule', 'start time', 'end time', 'dismissal']
                )

                return {
                    'found': True,
                    'status_code': 200,
                    'has_schedule_content': has_schedule_content
                }

            return {
                'found': False,
                'status_code': response.status_code
            }

        except Exception as e:
            logger.debug(f"URL test failed for {url}: {e}")
            return {
                'found': False,
                'error': str(e)
            }

    # =========================================================================
    # Detection Methods
    # =========================================================================

    def _detect_cms(self, district_url: str, discovery_result: Dict) -> Optional[str]:
        """
        Detect CMS platform from URL patterns and page content

        Common CMS platforms:
            - Finalsite: finalsite.com, /fs/ in path
            - SchoolBlocks: /pages/index.jsp
            - Blackboard: blackboard.com, /bbcswebdav/
            - Edlio: edlio.com
            - Apptegy: apptegy.com
            - WordPress: /wp-content/
        """
        try:
            response = requests.get(district_url, timeout=15)
            content_lower = response.text.lower()
            url_lower = response.url.lower()

            # Check URL patterns
            if 'finalsite.com' in url_lower or '/fs/' in url_lower:
                return 'finalsite'
            if 'schoolblocks' in url_lower or '/pages/index.jsp' in url_lower:
                return 'schoolblocks'
            if 'blackboard.com' in url_lower or '/bbcswebdav/' in url_lower:
                return 'blackboard'
            if 'edlio.com' in url_lower:
                return 'edlio'
            if 'apptegy.com' in url_lower or 'thrillshare.com' in url_lower:
                return 'apptegy'

            # Check content patterns
            if 'wp-content' in content_lower or 'wordpress' in content_lower:
                return 'wordpress'
            if 'powered by finalsite' in content_lower:
                return 'finalsite'
            if 'schoolblocks' in content_lower:
                return 'schoolblocks'

            # Check schools for CMS hints
            for school in discovery_result.get('schools', [])[:5]:
                school_url = school.get('url', '')
                if 'finalsite' in school_url:
                    return 'finalsite'
                if 'schoolblocks' in school_url:
                    return 'schoolblocks'

            return None

        except Exception as e:
            logger.debug(f"CMS detection failed for {district_url}: {e}")
            return None

    def _determine_content_type(
        self,
        discovery_result: Dict,
        schedule_urls: List[Dict]
    ) -> str:
        """
        Determine content type for downstream processing

        Types:
            - heavy_js: JavaScript-heavy rendering
            - html: Standard HTML content
            - pdf: PDF documents
            - image: Image-based schedules
            - mixed: Multiple types
        """
        # Check if any schedule URLs found
        found_urls = [u for u in schedule_urls if u.get('found')]

        if not found_urls:
            # Check discovery method for JS hints
            method = discovery_result.get('method', '')
            if 'playwright' in method.lower() or 'browser' in method.lower():
                return 'heavy_js'
            return 'html'

        # Check content types of found URLs
        content_types = set()

        for url_info in found_urls[:3]:  # Check first 3
            url = url_info.get('url')
            try:
                response = requests.head(url, timeout=10, allow_redirects=True)
                content_type = response.headers.get('Content-Type', '').lower()

                if 'pdf' in content_type:
                    content_types.add('pdf')
                elif 'image' in content_type:
                    content_types.add('image')
                elif 'html' in content_type:
                    content_types.add('html')

            except Exception:
                pass

        if not content_types:
            return 'html'
        elif len(content_types) > 1:
            return 'mixed'
        else:
            return content_types.pop()

    def _check_security_blocks(self, discovery_result: Dict) -> Dict:
        """
        Check if district website has security blocks

        Security types:
            - cloudflare: Cloudflare protection
            - waf: Web Application Firewall
            - captcha: CAPTCHA challenge
            - rate_limit: Rate limiting
        """
        error = discovery_result.get('error', '')
        response_text = discovery_result.get('response', '')

        blocked = False
        block_type = None

        # Check error messages
        if any(term in error.lower() for term in ['cloudflare', 'cf-ray']):
            blocked = True
            block_type = 'cloudflare'
        elif 'captcha' in error.lower():
            blocked = True
            block_type = 'captcha'
        elif 'waf' in error.lower() or 'firewall' in error.lower():
            blocked = True
            block_type = 'waf'
        elif 'rate limit' in error.lower() or '429' in error:
            blocked = True
            block_type = 'rate_limit'

        # Check response content
        if response_text:
            response_lower = response_text.lower()
            if 'cloudflare' in response_lower and 'checking' in response_lower:
                blocked = True
                block_type = 'cloudflare'

        return {
            'blocked': blocked,
            'block_type': block_type,
            'details': error if blocked else None
        }

    # =========================================================================
    # Escalation Logic
    # =========================================================================

    def _should_escalate(self, result: Dict) -> bool:
        """
        Determine if district should escalate to next tier

        Escalate if:
            - Bell schedule page found but no data extracted → Tier 2
            - Homepage accessible but no schedule found → Tier 2
            - Security blocked → Manual review (no escalation)
        """
        if not result.get('success'):
            return False

        # Don't escalate if security blocked
        if result.get('security_blocked'):
            return False

        # Escalate if no bell schedule found (move to Tier 2 for extraction attempts)
        return True

    def _get_escalation_reason(self, result: Dict) -> Optional[str]:
        """Get human-readable escalation reason"""
        if not result.get('escalation_needed'):
            return None

        if result.get('bell_schedule_found'):
            return "bell_schedule_page_found_but_no_data_extracted"

        if result.get('schools_found'):
            return "schools_found_but_no_bell_schedule_urls"

        return "no_bell_schedule_found_needs_extraction"


def main():
    """Example usage"""
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        processor = Tier1Processor(session)

        # Test on a district
        test_district_id = '3003290'  # Belgrade Elementary, MT
        result = processor.process_district(test_district_id)

        import json
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
