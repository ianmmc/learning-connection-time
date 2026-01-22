#!/usr/bin/env python3
"""
Fetch bell schedules from district and school websites to determine actual instructional time.

This script enriches district data by gathering actual bell schedules rather than
relying solely on state statutory requirements. It uses web search and scraping to
find schedule information, then extracts instructional time data.

Usage:
    python fetch_bell_schedules.py <districts_file> [options]

    Options:
        --output PATH           Output file path (default: auto-generated)
        --tier {1,2,3}         Quality tier (1=detailed, 2=automated, 3=statutory)
        --sample-size N        Number of schools to sample per level (default: 2)
        --year YEAR            School year (e.g., "2023-24")
        --force-refresh        Re-fetch even if data exists
        --dry-run              Show what would be fetched without fetching

Examples:
    # Tier 1: Detailed search for top 25 districts
    python fetch_bell_schedules.py top_25_districts.csv --tier 1 --sample-size 3

    # Tier 2: Automated search for next 75 districts
    python fetch_bell_schedules.py districts_26_100.csv --tier 2

    # Dry run to see what would be searched
    python fetch_bell_schedules.py districts.csv --dry-run
"""

import argparse
import logging
import sys
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import yaml
import json

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Add utilities to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "utilities"))
from common import DataProcessor, safe_divide, format_number, standardize_state

# Scraper service configuration
SCRAPER_URL = os.environ.get('SCRAPER_URL', 'http://localhost:3000')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HTTPErrorTracker:
    """Track HTTP errors and trigger auto-flagging at threshold

    Per ENRICHMENT_SAFEGUARDS.md Rule 1:
    - 4 or more 404 errors = AUTO-FLAG for manual follow-up
    - Multiple 404s indicate hardened cybersecurity, not missing pages
    """

    def __init__(self, threshold: int = 4):
        self.errors_404 = []
        self.threshold = threshold

    def record_404(self, url: str):
        """Record a 404 error"""
        self.errors_404.append(url)

    def should_flag_manual_followup(self) -> bool:
        """Check if we've hit the threshold"""
        return len(self.errors_404) >= self.threshold

    def get_summary(self) -> dict:
        """Get error summary for flagging"""
        return {
            "total_404s": len(self.errors_404),
            "urls_tried": self.errors_404,
            "threshold": self.threshold,
            "flagged": self.should_flag_manual_followup()
        }


def scrape_url(url: str, timeout: int = 30) -> Optional[Dict]:
    """
    Scrape a URL using the scraper service.

    Args:
        url: URL to scrape
        timeout: Timeout in seconds

    Returns:
        Response dict from scraper service, or None if failed
    """
    if not REQUESTS_AVAILABLE:
        logger.error("requests library not available - cannot use scraper service")
        return None

    try:
        response = requests.post(
            f"{SCRAPER_URL}/scrape",
            json={"url": url, "timeout": timeout * 1000},
            timeout=timeout + 10
        )
        return response.json()
    except requests.exceptions.ConnectionError:
        logger.error(f"Cannot connect to scraper service at {SCRAPER_URL}")
        logger.info("Start the scraper: cd scraper && npm run dev")
        return None
    except requests.RequestException as e:
        logger.error(f"Request error: {e}")
        return None


def check_scraper_health() -> bool:
    """Check if the scraper service is running and healthy."""
    if not REQUESTS_AVAILABLE:
        return False

    try:
        response = requests.get(f"{SCRAPER_URL}/health", timeout=5)
        data = response.json()
        return data.get('status') == 'healthy'
    except Exception:
        return False


def extract_bell_schedule_times(html: str, markdown: str) -> Optional[Dict]:
    """
    Extract bell schedule times from HTML/markdown content.

    Looks for common patterns like:
    - "Start Time: 8:00 AM"
    - "School begins at 7:45"
    - "Dismissal: 3:15 PM"
    - Time ranges like "8:00 AM - 3:00 PM"

    Returns:
        Dict with start_time, end_time, instructional_minutes, or None
    """
    # Use markdown for cleaner text extraction
    text = markdown if markdown else html

    # Time patterns
    time_pattern = r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.)?)'

    # Look for start time patterns
    start_patterns = [
        r'(?:start|begin|arrival|first\s+bell|morning\s+bell)[:\s]+' + time_pattern,
        r'(?:school\s+(?:starts|begins))[:\s]+(?:at\s+)?' + time_pattern,
        r'(\d{1,2}:\d{2}\s*(?:AM|am|a\.m\.))',  # Any morning time as fallback
    ]

    # Look for end time patterns
    end_patterns = [
        r'(?:end|dismissal|release|final\s+bell|afternoon\s+bell)[:\s]+' + time_pattern,
        r'(?:school\s+(?:ends|dismisses))[:\s]+(?:at\s+)?' + time_pattern,
        r'(\d{1,2}:\d{2}\s*(?:PM|pm|p\.m\.))',  # Any afternoon time as fallback
    ]

    start_time = None
    end_time = None

    # Find start time
    for pattern in start_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start_time = match.group(1).strip()
            break

    # Find end time
    for pattern in end_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            end_time = match.group(1).strip()
            break

    # Try to find time range (e.g., "8:00 AM - 3:00 PM")
    range_pattern = r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)\s*[-–—to]+\s*(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)'
    range_match = re.search(range_pattern, text, re.IGNORECASE)
    if range_match:
        if not start_time:
            start_time = range_match.group(1).strip()
        if not end_time:
            end_time = range_match.group(2).strip()

    if not start_time or not end_time:
        return None

    # Calculate instructional minutes
    minutes = calculate_instructional_minutes(start_time, end_time)

    return {
        'start_time': start_time,
        'end_time': end_time,
        'instructional_minutes': minutes,
    }


def calculate_instructional_minutes(start: str, end: str) -> Optional[int]:
    """
    Calculate minutes between two times.

    Args:
        start: Start time string (e.g., "8:00 AM")
        end: End time string (e.g., "3:00 PM")

    Returns:
        Number of minutes, or None if parsing fails
    """
    def parse_time(t: str) -> Optional[Tuple[int, int]]:
        # Normalize
        t = t.upper().replace('.', '').replace(' ', '')
        # Extract hours and minutes
        match = re.match(r'(\d{1,2}):(\d{2})(AM|PM)?', t)
        if not match:
            return None
        hours = int(match.group(1))
        minutes = int(match.group(2))
        period = match.group(3)

        # Convert to 24-hour
        if period == 'PM' and hours < 12:
            hours += 12
        elif period == 'AM' and hours == 12:
            hours = 0

        return (hours, minutes)

    start_parsed = parse_time(start)
    end_parsed = parse_time(end)

    if not start_parsed or not end_parsed:
        return None

    start_minutes = start_parsed[0] * 60 + start_parsed[1]
    end_minutes = end_parsed[0] * 60 + end_parsed[1]

    # Handle overnight (shouldn't happen for school schedules but be safe)
    if end_minutes < start_minutes:
        end_minutes += 24 * 60

    total_minutes = end_minutes - start_minutes

    # Subtract typical lunch (30 min) if total seems to include it
    # Most schedules report gross time, we want instructional time
    if total_minutes > 400:  # More than 6.5 hours
        total_minutes -= 30  # Deduct assumed lunch

    return total_minutes if 180 <= total_minutes <= 480 else None  # Sanity check


def flag_for_manual_followup(district_info: dict, error_summary: dict):
    """Add district to manual follow-up list

    Per ENRICHMENT_SAFEGUARDS.md Rule 3:
    Required fields: district_id, district_name, state, enrollment, reason, attempts
    """
    followup_file = Path('data/enriched/bell-schedules/manual_followup_needed.json')

    # Load existing data
    if followup_file.exists():
        with open(followup_file, 'r') as f:
            data = json.load(f)
    else:
        data = {
            "districts_needing_manual_review": [],
            "completed_manual_collections": [],
            "last_updated": None
        }

    # Create entry
    entry = {
        "district_id": district_info['district_id'],
        "district_name": district_info['district_name'],
        "state": district_info['state'],
        "enrollment": district_info.get('enrollment'),
        "reason": f"Automated collection failed - {error_summary.get('total_404s', 0)} 404 errors",
        "attempts": [{
            "date": datetime.now().strftime("%Y-%m-%d"),
            "method": "WebSearch + WebFetch",
            "total_404s": error_summary.get('total_404s', 0),
            "urls_tried": error_summary.get('urls_tried', [])
        }],
        "next_steps": "Manual collection needed",
        "priority": "high",
        "flagged_date": datetime.now().strftime("%Y-%m-%d")
    }

    data['districts_needing_manual_review'].append(entry)
    data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Save
    followup_file.parent.mkdir(parents=True, exist_ok=True)
    with open(followup_file, 'w') as f:
        json.dump(data, f, indent=2)

    logger.warning(f"Flagged {district_info['district_name']} for manual follow-up")


class BellScheduleFetcher(DataProcessor):
    """Fetches and processes bell schedule data from school websites

    IMPORTANT - Security Block Protocol:
    If a district has Cloudflare, WAF, or similar security measures:
    1. Try ONE web search + ONE primary page fetch
    2. If blocked (Cloudflare 1016/1020, 403, multiple 404s, inaccessible content)
    3. Immediately add to manual_followup_needed.json
    4. Move to next district

    DO NOT attempt multiple workarounds - if main site is blocked, school sites will be too.
    Respect district cybersecurity and conserve resources.

    See docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md for full protocol.
    """

    def __init__(self, tier: int = 2, sample_size: int = 2, year: str = "2023-24"):
        """
        Initialize the bell schedule fetcher.

        Args:
            tier: Quality tier (1=detailed, 2=automated, 3=statutory only)
            sample_size: Number of schools to sample per grade level
            year: School year for bell schedules
        """
        super().__init__()
        self.tier = tier
        self.sample_size = sample_size
        self.year = year
        self.cache_dir = Path("data/enriched/bell-schedules")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_district_bell_schedules(
        self,
        district_id: str,
        district_name: str,
        state: str,
        enrollment: int
    ) -> Optional[Dict]:
        """
        Fetch bell schedules for a district.

        Per ENRICHMENT_SAFEGUARDS.md Rule 4:
        Returns None if enrichment fails (triggers manual follow-up)
        Never returns statutory fallback data

        Args:
            district_id: District identifier
            district_name: District name
            state: Two-letter state code
            enrollment: Total student enrollment

        Returns:
            Dictionary with bell schedule data and metadata, or None if failed
        """
        logger.info(f"Fetching bell schedules for {district_name}, {state}")

        result = {
            'district_id': district_id,
            'district_name': district_name,
            'state': state,
            'enrollment': enrollment,
            'year': self.year,
            'fetch_date': datetime.now().isoformat(),
            'tier': self.tier,
            'elementary': {},
            'middle': {},
            'high': {},
            'sources': [],
            'notes': []
        }

        # Check cache first
        cached = self._check_cache(district_id)
        if cached:
            logger.info(f"Using cached data for {district_name}")
            return cached

        # Tier 1: Detailed manual-assisted search
        if self.tier == 1:
            result = self._tier1_detailed_search(result)

        # Tier 2: Automated search with fallback
        elif self.tier == 2:
            result = self._tier2_automated_search(result)

        # Tier 3: Use state statutory requirements only
        else:
            result = self._tier3_statutory_only(result)

        # Cache the result
        self._cache_result(district_id, result)

        return result

    def _tier1_detailed_search(self, result: Dict) -> Optional[Dict]:
        """
        Tier 1: Detailed search with representative school sampling.

        Uses the Crawlee-based scraper service for JavaScript rendering.
        Implements security block detection and 404 tracking.

        Returns None on failure to trigger manual follow-up.
        """
        # Check scraper service health
        if not check_scraper_health():
            logger.error("Scraper service not available")
            logger.info("Start the scraper: cd scraper && docker-compose up -d")
            raise RuntimeError("Scraper service not available at " + SCRAPER_URL)

        error_tracker = HTTPErrorTracker(threshold=4)
        district_name = result['district_name']
        state = result['state']

        # Build search URLs to try
        # Format district name for URL (lowercase, hyphens)
        url_name = district_name.lower().replace(' ', '-').replace("'", "")
        url_name = re.sub(r'[^a-z0-9-]', '', url_name)

        # Common URL patterns for bell schedules
        base_urls = [
            f"https://www.{url_name}.org",
            f"https://www.{url_name}.k12.{state.lower()}.us",
            f"https://{url_name}.org",
        ]

        schedule_paths = [
            "/bell-schedule",
            "/bell-schedules",
            "/schools/bell-schedule",
            "/parents/bell-schedule",
            "/calendar/bell-schedule",
            "/about/bell-schedule",
            "/students/bell-schedule",
        ]

        found_schedules = {'elementary': None, 'middle': None, 'high': None}
        sources = []

        for base_url in base_urls:
            if error_tracker.should_flag_manual_followup():
                break

            for path in schedule_paths:
                if error_tracker.should_flag_manual_followup():
                    break

                url = base_url + path
                logger.debug(f"Trying URL: {url}")

                response = scrape_url(url, timeout=30)

                if response is None:
                    continue

                # Check for security block
                if response.get('blocked'):
                    logger.warning(f"Security block detected for {district_name}")
                    flag_for_manual_followup(
                        {'district_id': result['district_id'],
                         'district_name': district_name,
                         'state': state,
                         'enrollment': result.get('enrollment')},
                        {'total_404s': 0, 'security_blocked': True}
                    )
                    return None

                # Check for 404
                if response.get('errorCode') == 'NOT_FOUND':
                    error_tracker.record_404(url)
                    continue

                # Check for other errors
                if not response.get('success'):
                    continue

                # Try to extract bell schedule times
                html = response.get('html', '')
                markdown = response.get('markdown', '')

                times = extract_bell_schedule_times(html, markdown)

                if times:
                    logger.info(f"Found bell schedule at {url}")
                    sources.append(url)

                    # Determine school level from URL or content
                    level = self._detect_school_level(url, markdown)

                    if level and not found_schedules[level]:
                        found_schedules[level] = {
                            'instructional_minutes': times['instructional_minutes'],
                            'start_time': times['start_time'],
                            'end_time': times['end_time'],
                            'schools_sampled': [url],
                            'source_urls': [url],
                            'confidence': 'high',
                            'method': 'web_scrape_tier1',
                        }

        # Check if we hit 404 threshold
        if error_tracker.should_flag_manual_followup():
            logger.warning(f"Hit 404 threshold for {district_name}")
            flag_for_manual_followup(
                {'district_id': result['district_id'],
                 'district_name': district_name,
                 'state': state,
                 'enrollment': result.get('enrollment')},
                error_tracker.get_summary()
            )
            return None

        # Check if we found any schedules
        if not any(found_schedules.values()):
            logger.warning(f"No bell schedules found for {district_name}")
            flag_for_manual_followup(
                {'district_id': result['district_id'],
                 'district_name': district_name,
                 'state': state,
                 'enrollment': result.get('enrollment')},
                {'total_404s': len(error_tracker.errors_404), 'no_schedules_found': True}
            )
            return None

        # Apply found schedules to result
        for level in ['elementary', 'middle', 'high']:
            if found_schedules[level]:
                result[level] = found_schedules[level]
            else:
                # Use state statutory as fallback for missing levels
                result = self._apply_state_requirements_for_level(result, level)

        result['sources'] = sources
        result['enriched'] = True
        result['data_quality_tier'] = 'tier1_detailed'
        result['notes'].append(f"Tier 1 detailed search completed - found {len(sources)} sources")

        return result

    def _detect_school_level(self, url: str, content: str) -> Optional[str]:
        """Detect school level from URL or content."""
        text = (url + ' ' + content).lower()

        if any(term in text for term in ['elementary', 'primary', 'grade school', 'k-5', 'k-6']):
            return 'elementary'
        elif any(term in text for term in ['middle', 'junior high', 'intermediate', '6-8', '7-8']):
            return 'middle'
        elif any(term in text for term in ['high school', 'senior high', '9-12', '10-12']):
            return 'high'
        return None

    def _apply_state_requirements_for_level(self, result: Dict, level: str) -> Dict:
        """Apply state statutory requirements for a single grade level."""
        state = result['state']
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "state-requirements.yaml"

        minutes = 360  # Default
        source = 'Default assumption'

        if config_path.exists():
            with open(config_path, 'r') as f:
                state_config = yaml.safe_load(f)

            state_key = state.lower()
            state_data = state_config.get('states', {}).get(state_key, {})
            level_key = level if level == 'elementary' else f"{level}_school"
            minutes = state_data.get(level_key, state_data.get('default', 360))
            source = state_data.get('source', 'State statute')

        result[level] = {
            'instructional_minutes': minutes,
            'start_time': None,
            'end_time': None,
            'schools_sampled': [],
            'source_urls': [],
            'confidence': 'statutory_fallback',
            'method': 'state_statutory',
            'source': source,
        }

        return result

    def _tier2_automated_search(self, result: Dict) -> Optional[Dict]:
        """
        Tier 2: Automated search with simpler heuristics.

        Faster than Tier 1 but less thorough. Uses scraper service.
        Returns None on failure to trigger manual follow-up.

        CRITICAL: Per ENRICHMENT_SAFEGUARDS.md Rule 2:
        Must NOT fall back to statutory requirements.
        """
        # Check scraper service health
        if not check_scraper_health():
            logger.error("Scraper service not available")
            logger.info("Start the scraper: cd scraper && docker-compose up -d")
            raise RuntimeError("Scraper service not available at " + SCRAPER_URL)

        error_tracker = HTTPErrorTracker(threshold=4)
        district_name = result['district_name']
        state = result['state']

        # Build fewer URLs than tier 1 for faster processing
        url_name = district_name.lower().replace(' ', '-').replace("'", "")
        url_name = re.sub(r'[^a-z0-9-]', '', url_name)

        # Try just the most common patterns
        urls_to_try = [
            f"https://www.{url_name}.org/bell-schedule",
            f"https://www.{url_name}.k12.{state.lower()}.us/bell-schedule",
            f"https://www.{url_name}.org/schools/bell-schedule",
        ]

        found_schedule = None
        source_url = None

        for url in urls_to_try:
            if error_tracker.should_flag_manual_followup():
                break

            logger.debug(f"Tier 2 trying: {url}")
            response = scrape_url(url, timeout=20)

            if response is None:
                continue

            # Security block - flag immediately
            if response.get('blocked'):
                logger.warning(f"Security block for {district_name}")
                flag_for_manual_followup(
                    {'district_id': result['district_id'],
                     'district_name': district_name,
                     'state': state,
                     'enrollment': result.get('enrollment')},
                    {'security_blocked': True}
                )
                return None

            if response.get('errorCode') == 'NOT_FOUND':
                error_tracker.record_404(url)
                continue

            if not response.get('success'):
                continue

            # Extract times
            times = extract_bell_schedule_times(
                response.get('html', ''),
                response.get('markdown', '')
            )

            if times:
                found_schedule = times
                source_url = url
                logger.info(f"Tier 2 found schedule at {url}")
                break

        # Check 404 threshold
        if error_tracker.should_flag_manual_followup():
            flag_for_manual_followup(
                {'district_id': result['district_id'],
                 'district_name': district_name,
                 'state': state,
                 'enrollment': result.get('enrollment')},
                error_tracker.get_summary()
            )
            return None

        # No schedule found
        if not found_schedule:
            flag_for_manual_followup(
                {'district_id': result['district_id'],
                 'district_name': district_name,
                 'state': state,
                 'enrollment': result.get('enrollment')},
                {'no_schedules_found': True, 'urls_tried': urls_to_try}
            )
            return None

        # Apply found schedule to all levels (tier 2 uses district-wide)
        for level in ['elementary', 'middle', 'high']:
            result[level] = {
                'instructional_minutes': found_schedule['instructional_minutes'],
                'start_time': found_schedule['start_time'],
                'end_time': found_schedule['end_time'],
                'schools_sampled': [source_url],
                'source_urls': [source_url],
                'confidence': 'medium',
                'method': 'web_scrape_tier2',
            }

        result['sources'] = [source_url]
        result['enriched'] = True
        result['data_quality_tier'] = 'tier2_automated'
        result['notes'].append(f"Tier 2 automated search - found schedule at {source_url}")

        return result

    def _tier3_statutory_only(self, result: Dict) -> Dict:
        """
        Tier 3: Use state statutory requirements only.

        No web searching - just apply known state requirements.

        Per ENRICHMENT_SAFEGUARDS.md Rule 2:
        Sets enriched=False and data_quality_tier='statutory_fallback'
        """
        result['notes'].append(
            f"Tier 3: Using state statutory requirements for {result['state']}"
        )

        result = self._apply_state_requirements(result, confidence='statutory')

        # CRITICAL: Mark as NOT enriched (per ENRICHMENT_SAFEGUARDS.md Rule 2)
        result['enriched'] = False
        result['data_quality_tier'] = 'statutory_fallback'

        return result

    def _apply_state_requirements(self, result: Dict, confidence: str = 'low') -> Dict:
        """
        Apply state statutory instructional time requirements.

        Loads from config/state-requirements.yaml
        """
        state = result['state']

        # Load state requirements
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "state-requirements.yaml"

        if config_path.exists():
            with open(config_path, 'r') as f:
                state_config = yaml.safe_load(f)

            state_key = state.lower()
            state_data = state_config.get('states', {}).get(state_key, {})

            # Apply to each level
            for level in ['elementary', 'middle', 'high']:
                level_key = level if level == 'elementary' else f"{level}_school"
                minutes = state_data.get(level_key, state_data.get('default', 360))

                result[level] = {
                    'instructional_minutes': minutes,
                    'start_time': None,
                    'end_time': None,
                    'lunch_duration': None,
                    'passing_periods': None,
                    'schools_sampled': [],
                    'source_urls': [],
                    'confidence': confidence,
                    'method': 'state_statutory',
                    'source': state_data.get('source', 'State statute')
                }

            result['notes'].append(
                f"Applied state statutory requirements for {state}"
            )
        else:
            # Default to 360 minutes if no config
            logger.warning(f"No state requirements config found, using default 360 minutes")
            for level in ['elementary', 'middle', 'high']:
                result[level] = {
                    'instructional_minutes': 360,
                    'confidence': 'assumed',
                    'method': 'default',
                    'source': 'Default assumption'
                }

        return result

    def _check_cache(self, district_id: str) -> Optional[Dict]:
        """Check if we have cached bell schedule data for this district"""
        cache_file = self.cache_dir / f"{district_id}_{self.year}.json"
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                return json.load(f)
        return None

    def _cache_result(self, district_id: str, result: Dict):
        """Cache the bell schedule result"""
        cache_file = self.cache_dir / f"{district_id}_{self.year}.json"
        with open(cache_file, 'w') as f:
            json.dump(result, f, indent=2)
        logger.info(f"Cached result to {cache_file}")

    def process_districts_file(self, input_file: Path, output_file: Path, dry_run: bool = False):
        """
        Process a file of districts and fetch bell schedules for each.

        Args:
            input_file: Path to CSV with district data
            output_file: Path to output CSV with enriched data
            dry_run: If True, only show what would be done
        """
        logger.info(f"Processing districts from {input_file}")

        # Read districts
        df = pd.read_csv(input_file)

        # Validate required columns
        required_cols = ['district_id', 'district_name', 'state', 'enrollment']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        if dry_run:
            logger.info("DRY RUN MODE - showing what would be processed:")
            for _, row in df.iterrows():
                logger.info(
                    f"  Would fetch: {row['district_name']}, {row['state']} "
                    f"(enrollment: {format_number(row['enrollment'])})"
                )
            logger.info(f"Total districts: {len(df)}")
            return

        # Process each district - Per ENRICHMENT_SAFEGUARDS.md Rule 5
        results = []
        stats = {'enriched': 0, 'statutory': 0, 'flagged_for_manual': 0, 'errors': 0}

        for idx, row in df.iterrows():
            try:
                result = self.fetch_district_bell_schedules(
                    district_id=str(row['district_id']),
                    district_name=row['district_name'],
                    state=row['state'],
                    enrollment=row['enrollment']
                )

                # Handle None returns (enrichment failed, flagged for manual follow-up)
                if result is None:
                    logger.info(f"Flagged {row['district_name']} - continuing to next district")
                    stats['flagged_for_manual'] += 1
                    continue

                # Check if actually enriched or just statutory
                if result.get('enriched', True):  # Default True for backward compatibility
                    stats['enriched'] += 1
                elif result.get('data_quality_tier') == 'statutory_fallback':
                    stats['statutory'] += 1
                else:
                    # Unknown status - log warning
                    logger.warning(f"Unclear enrichment status for {row['district_name']}")

                # Flatten result for CSV output
                flat_result = {
                    'district_id': result['district_id'],
                    'district_name': result['district_name'],
                    'state': result['state'],
                    'enrollment': result['enrollment'],
                    'year': result['year'],
                    'tier': result['tier'],
                    'enriched': result.get('enriched', True),
                    'data_quality_tier': result.get('data_quality_tier', 'unknown'),
                    'elementary_minutes': result['elementary'].get('instructional_minutes'),
                    'elementary_confidence': result['elementary'].get('confidence'),
                    'middle_minutes': result['middle'].get('instructional_minutes'),
                    'middle_confidence': result['middle'].get('confidence'),
                    'high_minutes': result['high'].get('instructional_minutes'),
                    'high_confidence': result['high'].get('confidence'),
                    'sources': '; '.join(result.get('sources', [])),
                    'notes': '; '.join(result.get('notes', []))
                }
                results.append(flat_result)

                logger.info(
                    f"Processed {idx + 1}/{len(df)}: {row['district_name']}"
                )

            except NotImplementedError as e:
                logger.error(f"Implementation error for {row['district_name']}: {str(e)}")
                stats['errors'] += 1
                raise  # Re-raise to stop execution
            except Exception as e:
                logger.error(
                    f"Error processing {row['district_name']}: {str(e)}"
                )
                stats['errors'] += 1
                continue

        # Report statistics
        logger.info("\n" + "="*60)
        logger.info("ENRICHMENT STATISTICS")
        logger.info("="*60)
        logger.info(f"Enriched (actual bell schedules): {stats['enriched']}")
        logger.info(f"Statutory fallback: {stats['statutory']}")
        logger.info(f"Flagged for manual follow-up: {stats['flagged_for_manual']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info("="*60)

        # Create output DataFrame
        output_df = pd.DataFrame(results)

        # Save to file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_df.to_csv(output_file, index=False)
        logger.info(f"Saved enriched data to {output_file}")

        # Generate summary
        self._generate_summary(output_df, output_file)

    def _generate_summary(self, df: pd.DataFrame, output_file: Path):
        """Generate summary statistics for the enrichment process"""
        summary_file = output_file.with_suffix('.txt').with_name(
            output_file.stem + '_summary.txt'
        )

        with open(summary_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("BELL SCHEDULE ENRICHMENT SUMMARY\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"Total districts processed: {len(df)}\n")
            f.write(f"Year: {df['year'].iloc[0] if len(df) > 0 else 'N/A'}\n")
            f.write(f"Tier: {df['tier'].iloc[0] if len(df) > 0 else 'N/A'}\n\n")

            f.write("CONFIDENCE LEVELS:\n")
            for level in ['elementary', 'middle', 'high']:
                col = f'{level}_confidence'
                if col in df.columns:
                    counts = df[col].value_counts()
                    f.write(f"\n{level.capitalize()}:\n")
                    for conf, count in counts.items():
                        f.write(f"  {conf}: {count}\n")

            f.write("\nINSTRUCTIONAL MINUTES STATISTICS:\n")
            for level in ['elementary', 'middle', 'high']:
                col = f'{level}_minutes'
                if col in df.columns:
                    f.write(f"\n{level.capitalize()}:\n")
                    f.write(f"  Mean: {df[col].mean():.1f}\n")
                    f.write(f"  Median: {df[col].median():.1f}\n")
                    f.write(f"  Min: {df[col].min():.1f}\n")
                    f.write(f"  Max: {df[col].max():.1f}\n")

            f.write("\n" + "=" * 80 + "\n")

        logger.info(f"Summary saved to {summary_file}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Fetch bell schedules from district/school websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'districts_file',
        type=Path,
        help='CSV file with district data (must have: district_id, district_name, state, enrollment)'
    )

    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: auto-generated in data/enriched/bell-schedules/)'
    )

    parser.add_argument(
        '--tier',
        type=int,
        choices=[1, 2, 3],
        default=2,
        help='Quality tier: 1=detailed, 2=automated, 3=statutory only (default: 2)'
    )

    parser.add_argument(
        '--sample-size',
        type=int,
        default=2,
        help='Number of schools to sample per grade level (default: 2)'
    )

    parser.add_argument(
        '--year',
        type=str,
        default='2023-24',
        help='School year (default: 2023-24)'
    )

    parser.add_argument(
        '--force-refresh',
        action='store_true',
        help='Re-fetch even if cached data exists'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be fetched without actually fetching'
    )

    args = parser.parse_args()

    # Validate input file
    if not args.districts_file.exists():
        logger.error(f"Input file not found: {args.districts_file}")
        sys.exit(1)

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        # Auto-generate output filename
        stem = args.districts_file.stem
        output_file = Path(f"data/enriched/bell-schedules/{stem}_enriched_{args.year.replace('-', '_')}.csv")

    # Initialize fetcher
    fetcher = BellScheduleFetcher(
        tier=args.tier,
        sample_size=args.sample_size,
        year=args.year
    )

    # Process districts
    fetcher.process_districts_file(
        input_file=args.districts_file,
        output_file=output_file,
        dry_run=args.dry_run
    )

    if not args.dry_run:
        logger.info("✓ Bell schedule enrichment complete!")
        logger.info(f"Output: {output_file}")


if __name__ == '__main__':
    main()
