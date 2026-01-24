#!/usr/bin/env python3
"""
Tier 2 Processor: Local Extraction (HTML Parsing + Patterns)
Extracts bell schedules from HTML using known patterns and time parsing

Tasks:
    - Parse HTML for time patterns (HH:MM AM/PM)
    - Extract from common table structures
    - Check for embedded calendars/widgets
    - Detect PDF/image schedule links
    - Parse time ranges and calculate total minutes

Cost: $0 (local compute only)

Usage:
    from tier_2_processor import Tier2Processor
    from connection import session_scope

    with session_scope() as session:
        processor = Tier2Processor(session)
        result = processor.process_district('0622710', tier_1_result={...})
"""

import logging
import re
import requests
from typing import Dict, Optional, List, Tuple
from datetime import datetime, time as dt_time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from sqlalchemy.orm import Session

from infrastructure.database.models import District, EnrichmentQueue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Tier2Processor:
    """Tier 2: Local HTML/Pattern Extraction"""

    # Time pattern regex (matches HH:MM AM/PM, H:MM AM/PM)
    TIME_PATTERN = re.compile(
        r'\b(\d{1,2}):(\d{2})\s*([AaPp][Mm])\b'
    )

    # Bell schedule keywords
    SCHEDULE_KEYWORDS = [
        'bell schedule', 'daily schedule', 'school day',
        'start time', 'end time', 'dismissal', 'arrival',
        'first bell', 'last bell', 'instructional time'
    ]

    # Scraper service configuration
    SCRAPER_BASE_URL = "http://localhost:3000"
    SCRAPER_TIMEOUT = 60

    def __init__(self, session: Session, scraper_url: str = None):
        """
        Initialize Tier 2 processor

        Args:
            session: SQLAlchemy database session
            scraper_url: URL of scraper service (default: http://localhost:3000)
        """
        self.session = session
        self.scraper_url = scraper_url or self.SCRAPER_BASE_URL

    # =========================================================================
    # Main Processing
    # =========================================================================

    def process_district(
        self,
        district_id: str,
        tier_1_result: Dict
    ) -> Dict:
        """
        Process a single district through Tier 2

        Args:
            district_id: NCES district ID
            tier_1_result: Results from Tier 1 (discovery)

        Returns:
            Result dictionary with extraction findings
        """
        logger.info(f"Processing district {district_id} at Tier 2")
        start_time = datetime.now()

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

        # Get URLs to try from Tier 1
        urls_to_try = self._get_urls_from_tier_1(tier_1_result)

        if not urls_to_try:
            logger.warning(f"No URLs to extract from Tier 1 results")
            return {
                'success': False,
                'error': 'no_urls_to_extract',
                'district_id': district_id,
                'escalation_needed': True,
                'escalation_reason': 'no_viable_urls_from_tier_1'
            }

        # Try extraction from each URL
        extraction_results = []
        for url in urls_to_try:
            try:
                result = self._extract_from_url(url)
                extraction_results.append(result)

                # If we got a valid schedule, we're done
                if result.get('schedule_found') and result.get('start_time'):
                    logger.info(f"Successfully extracted schedule from {url}")
                    break

            except Exception as e:
                logger.error(f"Extraction failed for {url}: {e}")
                extraction_results.append({
                    'url': url,
                    'success': False,
                    'error': str(e)
                })

        # Compile best result
        best_result = self._select_best_result(extraction_results)

        processing_time = int((datetime.now() - start_time).total_seconds())

        result = {
            'success': best_result.get('schedule_found', False),
            'district_id': district_id,
            'district_name': district.name,
            'extraction_attempts': len(extraction_results),
            'schedule_found': best_result.get('schedule_found', False),
            'start_time': best_result.get('start_time'),
            'end_time': best_result.get('end_time'),
            'total_minutes': best_result.get('total_minutes'),
            'confidence': best_result.get('confidence', 0.0),
            'source_url': best_result.get('url'),
            'extraction_method': best_result.get('method'),
            'pdf_links_found': best_result.get('pdf_links', []),
            'image_links_found': best_result.get('image_links', []),
            'processing_time_seconds': processing_time,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Determine escalation
        result['escalation_needed'] = self._should_escalate(result)
        result['escalation_reason'] = self._get_escalation_reason(result)

        logger.info(f"Tier 2 completed for {district_id}: "
                   f"schedule_found={result['schedule_found']}, "
                   f"confidence={result['confidence']}, "
                   f"escalate={result['escalation_needed']}")

        return result

    # =========================================================================
    # URL Management
    # =========================================================================

    def _get_urls_from_tier_1(self, tier_1_result: Dict) -> List[str]:
        """
        Extract promising URLs from Tier 1 results

        Priority:
            1. URLs that returned schedule content
            2. School-level URLs
            3. District-level URLs
        """
        urls = []

        # Get tested URLs from Tier 1
        urls_attempted = tier_1_result.get('urls_attempted', [])

        # Priority 1: URLs with schedule content
        for url_info in urls_attempted:
            if url_info.get('has_schedule_content') and url_info.get('found'):
                urls.append(url_info['url'])

        # Priority 2: Other found URLs
        for url_info in urls_attempted:
            if url_info.get('found') and url_info['url'] not in urls:
                urls.append(url_info['url'])

        # If no specific URLs, try district homepage
        if not urls:
            district_url = tier_1_result.get('district_url')
            if district_url:
                urls.append(district_url)

        return urls

    # =========================================================================
    # Extraction Methods
    # =========================================================================

    def _extract_from_url(self, url: str) -> Dict:
        """
        Extract bell schedule from a URL

        Tries multiple extraction strategies:
            1. HTML table extraction
            2. Time pattern matching
            3. Structured content parsing
            4. PDF/image link detection
        """
        try:
            # Use scraper service to fetch HTML (avoids 403/CAPTCHA)
            scrape_response = requests.post(
                f"{self.scraper_url}/scrape",
                json={'url': url, 'timeout': self.SCRAPER_TIMEOUT * 1000},
                timeout=self.SCRAPER_TIMEOUT
            )
            scrape_response.raise_for_status()
            scrape_data = scrape_response.json()

            if not scrape_data.get('success'):
                error_msg = scrape_data.get('error', 'Unknown error')
                logger.error(f"Scraper failed for {url}: {error_msg}")
                return {
                    'url': url,
                    'success': False,
                    'error': f'scraper_failed: {error_msg}'
                }

            html_content = scrape_data.get('content', '')
            soup = BeautifulSoup(html_content, 'html.parser')

            # Strategy 1: Try HTML table extraction
            table_result = self._extract_from_tables(soup, url)
            if table_result.get('schedule_found'):
                return table_result

            # Strategy 2: Try time pattern matching
            pattern_result = self._extract_from_patterns(soup, url)
            if pattern_result.get('schedule_found'):
                return pattern_result

            # Strategy 3: Try structured content (lists, divs)
            structured_result = self._extract_from_structured_content(soup, url)
            if structured_result.get('schedule_found'):
                return structured_result

            # Strategy 4: Check for PDF/image links
            pdf_links = self._find_pdf_links(soup, url)
            image_links = self._find_image_links(soup, url)

            return {
                'url': url,
                'schedule_found': False,
                'method': 'no_extraction_successful',
                'pdf_links': pdf_links,
                'image_links': image_links,
                'confidence': 0.0
            }

        except Exception as e:
            logger.error(f"Failed to extract from {url}: {e}")
            return {
                'url': url,
                'success': False,
                'error': str(e)
            }

    def _extract_from_tables(self, soup: BeautifulSoup, url: str) -> Dict:
        """
        Extract schedule from HTML tables

        Looks for tables with time patterns in cells
        """
        tables = soup.find_all('table')

        for table in tables:
            # Check if table contains schedule keywords
            table_text = table.get_text().lower()
            if not any(keyword in table_text for keyword in self.SCHEDULE_KEYWORDS):
                continue

            # Extract times from table cells
            times_found = []
            for cell in table.find_all(['td', 'th']):
                cell_text = cell.get_text()
                matches = self.TIME_PATTERN.findall(cell_text)
                for match in matches:
                    time_obj = self._parse_time(match)
                    if time_obj:
                        times_found.append(time_obj)

            # If we found start and end times
            if len(times_found) >= 2:
                times_sorted = sorted(times_found)
                start_time = times_sorted[0]
                end_time = times_sorted[-1]

                total_minutes = self._calculate_minutes(start_time, end_time)

                return {
                    'url': url,
                    'schedule_found': True,
                    'method': 'html_table',
                    'start_time': start_time.strftime('%I:%M %p'),
                    'end_time': end_time.strftime('%I:%M %p'),
                    'total_minutes': total_minutes,
                    'confidence': 0.8
                }

        return {'schedule_found': False}

    def _extract_from_patterns(self, soup: BeautifulSoup, url: str) -> Dict:
        """
        Extract schedule using time pattern matching

        Finds time patterns in proximity to schedule keywords
        """
        # Get all text content
        text_content = soup.get_text()

        # Check for schedule keywords
        has_keywords = any(
            keyword in text_content.lower()
            for keyword in self.SCHEDULE_KEYWORDS
        )

        if not has_keywords:
            return {'schedule_found': False}

        # Find all time patterns
        matches = self.TIME_PATTERN.findall(text_content)

        if len(matches) < 2:
            return {'schedule_found': False}

        # Parse times
        times_found = []
        for match in matches:
            time_obj = self._parse_time(match)
            if time_obj:
                times_found.append(time_obj)

        if len(times_found) >= 2:
            times_sorted = sorted(times_found)
            start_time = times_sorted[0]
            end_time = times_sorted[-1]

            total_minutes = self._calculate_minutes(start_time, end_time)

            # Sanity check: reasonable school day (180-540 minutes)
            if 180 <= total_minutes <= 540:
                return {
                    'url': url,
                    'schedule_found': True,
                    'method': 'time_pattern',
                    'start_time': start_time.strftime('%I:%M %p'),
                    'end_time': end_time.strftime('%I:%M %p'),
                    'total_minutes': total_minutes,
                    'confidence': 0.6  # Lower confidence for pattern matching
                }

        return {'schedule_found': False}

    def _extract_from_structured_content(
        self,
        soup: BeautifulSoup,
        url: str
    ) -> Dict:
        """
        Extract from structured content (div, ul, dl)

        Looks for schedule-related sections with time patterns
        """
        # Find sections with schedule keywords
        schedule_sections = soup.find_all(
            ['div', 'section', 'article'],
            string=lambda text: text and any(
                keyword in text.lower()
                for keyword in self.SCHEDULE_KEYWORDS
            )
        )

        for section in schedule_sections:
            section_text = section.get_text()
            matches = self.TIME_PATTERN.findall(section_text)

            if len(matches) >= 2:
                times_found = []
                for match in matches:
                    time_obj = self._parse_time(match)
                    if time_obj:
                        times_found.append(time_obj)

                if len(times_found) >= 2:
                    times_sorted = sorted(times_found)
                    start_time = times_sorted[0]
                    end_time = times_sorted[-1]

                    total_minutes = self._calculate_minutes(start_time, end_time)

                    if 180 <= total_minutes <= 540:
                        return {
                            'url': url,
                            'schedule_found': True,
                            'method': 'structured_content',
                            'start_time': start_time.strftime('%I:%M %p'),
                            'end_time': end_time.strftime('%I:%M %p'),
                            'total_minutes': total_minutes,
                            'confidence': 0.7
                        }

        return {'schedule_found': False}

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_time(self, time_match: Tuple[str, str, str]) -> Optional[dt_time]:
        """
        Parse time from regex match

        Args:
            time_match: Tuple of (hour, minute, am/pm)

        Returns:
            datetime.time object or None if invalid
        """
        try:
            hour, minute, meridiem = time_match
            hour = int(hour)
            minute = int(minute)

            # Convert to 24-hour format
            if meridiem.upper() == 'PM' and hour != 12:
                hour += 12
            elif meridiem.upper() == 'AM' and hour == 12:
                hour = 0

            return dt_time(hour, minute)

        except (ValueError, OverflowError):
            return None

    def _calculate_minutes(
        self,
        start_time: dt_time,
        end_time: dt_time
    ) -> int:
        """
        Calculate minutes between start and end times

        Assumes same day (no overnight schedules)
        """
        start_minutes = start_time.hour * 60 + start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute

        # Handle case where end < start (crossing midnight - shouldn't happen for schools)
        if end_minutes < start_minutes:
            end_minutes += 24 * 60

        return end_minutes - start_minutes

    def _find_pdf_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find PDF links in page"""
        pdf_links = []

        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.lower().endswith('.pdf') or 'pdf' in href.lower():
                full_url = urljoin(base_url, href)
                pdf_links.append(full_url)

        return pdf_links

    def _find_image_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find schedule-related images"""
        image_links = []

        for img in soup.find_all('img', src=True):
            src = img['src']
            alt = img.get('alt', '').lower()

            # Check if image might be a schedule
            if any(keyword in alt for keyword in ['schedule', 'bell', 'time']):
                full_url = urljoin(base_url, src)
                image_links.append(full_url)

        return image_links

    # =========================================================================
    # Result Selection
    # =========================================================================

    def _select_best_result(self, results: List[Dict]) -> Dict:
        """
        Select best extraction result from multiple attempts

        Priority:
            1. Highest confidence
            2. Has start/end times
            3. Reasonable total minutes (180-540)
        """
        valid_results = [
            r for r in results
            if r.get('schedule_found') and r.get('start_time')
        ]

        if not valid_results:
            # Return result with most information
            for result in results:
                if result.get('pdf_links') or result.get('image_links'):
                    return result
            return results[0] if results else {}

        # Sort by confidence
        valid_results.sort(key=lambda r: r.get('confidence', 0), reverse=True)
        return valid_results[0]

    # =========================================================================
    # Escalation Logic
    # =========================================================================

    def _should_escalate(self, result: Dict) -> bool:
        """
        Determine if district should escalate to next tier

        Escalate to Tier 3 if:
            - PDF links found → Need PDF extraction
            - Image links found → Need OCR

        Escalate to Tier 4 if:
            - Schedule found but low confidence < 0.7
            - No extraction successful but URLs available
        """
        if result.get('schedule_found') and result.get('confidence', 0) >= 0.7:
            return False

        # Escalate to Tier 3 if PDF/images found
        if result.get('pdf_links_found') or result.get('image_links_found'):
            return True

        # Escalate to Tier 4 if low confidence or no success
        if result.get('schedule_found') and result.get('confidence', 0) < 0.7:
            return True

        # Escalate if no success at all
        return not result.get('schedule_found')

    def _get_escalation_reason(self, result: Dict) -> Optional[str]:
        """Get human-readable escalation reason"""
        if not result.get('escalation_needed'):
            return None

        if result.get('pdf_links_found'):
            return "pdf_links_found_need_pdf_extraction"

        if result.get('image_links_found'):
            return "image_links_found_need_ocr"

        if result.get('schedule_found') and result.get('confidence', 0) < 0.7:
            return "schedule_found_but_low_confidence"

        return "no_schedule_extracted_need_advanced_processing"


def main():
    """Example usage"""
    from infrastructure.database.connection import session_scope

    with session_scope() as session:
        processor = Tier2Processor(session)

        # Example Tier 1 result
        tier_1_result = {
            'district_url': 'https://www.bsd44.org',
            'urls_attempted': [
                {
                    'url': 'https://hs.bsd44.org/information/bell-schedule',
                    'found': True,
                    'has_schedule_content': True
                }
            ]
        }

        test_district_id = '3003290'  # Belgrade Elementary, MT
        result = processor.process_district(test_district_id, tier_1_result)

        import json
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
