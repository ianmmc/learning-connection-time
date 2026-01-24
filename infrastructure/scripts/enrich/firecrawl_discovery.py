"""
Firecrawl integration for intelligent bell schedule discovery.

Uses Firecrawl's map endpoint to discover actual bell schedule pages
instead of guessing predictable URL patterns.

Features:
- URL discovery via /v1/map with smart search terms
- Content scraping via /v1/scrape
- Result caching to avoid duplicate requests
- School-level discovery for decentralized schedules
- Integration with ContentParser for structured extraction
"""

import hashlib
import json
import logging
import os
import re
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Configuration
FIRECRAWL_URL = os.getenv("FIRECRAWL_URL", "http://localhost:3002")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")  # Optional for self-hosted

# Cache configuration
CACHE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "cache" / "firecrawl"
CACHE_TTL_HOURS = 24  # How long to cache results


class FirecrawlCache:
    """Simple file-based cache for Firecrawl results."""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, url: str, operation: str) -> str:
        """Generate cache key from URL and operation."""
        key_data = f"{operation}:{url}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _get_cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, url: str, operation: str) -> Optional[Dict]:
        """Get cached result if valid."""
        key = self._get_cache_key(url, operation)
        path = self._get_cache_path(key)

        if not path.exists():
            return None

        try:
            with open(path, 'r') as f:
                data = json.load(f)

            # Check TTL
            cached_at = datetime.fromisoformat(data.get('cached_at', '2000-01-01'))
            if datetime.now() - cached_at > timedelta(hours=CACHE_TTL_HOURS):
                path.unlink()  # Delete expired cache
                return None

            return data.get('result')

        except Exception as e:
            logger.debug(f"Cache read error: {e}")
            return None

    def set(self, url: str, operation: str, result: Dict):
        """Cache a result."""
        key = self._get_cache_key(url, operation)
        path = self._get_cache_path(key)

        try:
            with open(path, 'w') as f:
                json.dump({
                    'url': url,
                    'operation': operation,
                    'cached_at': datetime.now().isoformat(),
                    'result': result
                }, f)
        except Exception as e:
            logger.debug(f"Cache write error: {e}")


class FirecrawlDiscovery:
    """
    Discover bell schedule pages using Firecrawl's map endpoint.

    Supports:
    - District-level discovery (main district site)
    - School-level discovery (individual school sites)
    - Result caching to avoid redundant requests
    """

    def __init__(self, base_url: str = None, api_key: str = None, use_cache: bool = True):
        self.base_url = base_url or FIRECRAWL_URL
        self.api_key = api_key or FIRECRAWL_API_KEY
        self.use_cache = use_cache
        self.cache = FirecrawlCache() if use_cache else None
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"
        self.session.headers["Content-Type"] = "application/json"

    def is_available(self) -> bool:
        """Check if Firecrawl service is available."""
        try:
            response = self.session.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200 and "Firecrawl" in response.text
        except Exception as e:
            logger.debug(f"Firecrawl not available: {e}")
            return False

    def discover_bell_schedule_urls(
        self,
        district_url: str,
        search_terms: List[str] = None
    ) -> List[str]:
        """
        Discover bell schedule URLs for a school district website.

        Args:
            district_url: Base URL of the school district website
            search_terms: Optional list of search terms (default: bell-related terms)

        Returns:
            List of URLs likely to contain bell schedule information
        """
        if not search_terms:
            search_terms = ["bell schedule", "bell times", "school hours", "start end times"]

        all_urls = set()

        for term in search_terms:
            try:
                urls = self._map_with_search(district_url, term)
                all_urls.update(urls)
            except Exception as e:
                logger.warning(f"Firecrawl map failed for '{term}': {e}")

        # Filter and rank URLs
        ranked = self._rank_urls(list(all_urls))

        return ranked[:20]  # Return top 20 most likely URLs

    def _map_with_search(self, url: str, search: str) -> List[str]:
        """Use Firecrawl map endpoint with search parameter."""
        try:
            response = self.session.post(
                f"{self.base_url}/v1/map",
                json={"url": url, "search": search},
                timeout=60
            )

            if response.status_code != 200:
                logger.warning(f"Firecrawl map returned {response.status_code}")
                return []

            data = response.json()
            if not data.get("success"):
                logger.warning(f"Firecrawl map unsuccessful: {data}")
                return []

            return data.get("links", [])

        except requests.exceptions.Timeout:
            logger.warning(f"Firecrawl map timeout for {url}")
            return []
        except Exception as e:
            logger.error(f"Firecrawl map error: {e}")
            return []

    def _rank_urls(self, urls: List[str]) -> List[str]:
        """Rank URLs by likelihood of containing bell schedule info."""

        # Keywords that strongly indicate bell schedules
        strong_keywords = [
            "bell_time", "bell-time", "belltime",
            "bell_schedule", "bell-schedule", "bellschedule",
            "school_hours", "school-hours", "schoolhours",
        ]

        # Keywords that moderately indicate bell schedules
        moderate_keywords = [
            "bell", "schedule", "hours", "times",
            "start", "end", "calendar",
        ]

        # Keywords that might be false positives
        negative_keywords = [
            "salary", "pay", "job", "career", "employment",
            "lunch_schedule", "bus_schedule", "sports",
            "event", "meeting", "board",
        ]

        def score_url(url: str) -> int:
            url_lower = url.lower()
            path = urlparse(url).path.lower()

            score = 0

            # Strong keywords in path
            for kw in strong_keywords:
                if kw in path:
                    score += 100

            # Moderate keywords in path
            for kw in moderate_keywords:
                if kw in path:
                    score += 10

            # Negative keywords reduce score
            for kw in negative_keywords:
                if kw in path:
                    score -= 50

            # Prefer shorter paths (more likely to be main pages)
            path_depth = len([p for p in path.split("/") if p])
            score -= path_depth * 2

            return score

        # Sort by score descending
        scored = [(url, score_url(url)) for url in urls]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [url for url, score in scored if score > 0]

    def discover_school_sites(self, district_url: str) -> List[str]:
        """
        Discover individual school websites from a district site.

        Used for school-level discovery when district-level fails.
        Many districts (80%+) have schedules at school level, not district level.

        Args:
            district_url: Base URL of the school district

        Returns:
            List of school website URLs
        """
        # Check cache first
        if self.cache:
            cached = self.cache.get(district_url, "schools")
            if cached:
                logger.debug(f"Using cached school discovery for {district_url}")
                return cached

        search_terms = [
            "schools",
            "school list",
            "our schools",
            "elementary middle high",
        ]

        all_urls = set()

        for term in search_terms:
            try:
                urls = self._map_with_search(district_url, term)
                all_urls.update(urls)
            except Exception as e:
                logger.warning(f"School discovery failed for '{term}': {e}")

        # Filter for school sites
        school_patterns = [
            r'/schools?/',
            r'es\.', r'ms\.', r'hs\.',  # elementary/middle/high school subdomains
            r'elementary', r'middle', r'high',
            r'-es', r'-ms', r'-hs',
        ]

        filtered = []
        for url in all_urls:
            url_lower = url.lower()
            for pattern in school_patterns:
                if re.search(pattern, url_lower):
                    filtered.append(url)
                    break

        # Cache results
        if self.cache and filtered:
            self.cache.set(district_url, "schools", filtered[:50])

        return filtered[:50]  # Return up to 50 school sites

    def scrape_url(self, url: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Scrape a single URL using Firecrawl.

        Args:
            url: URL to scrape
            use_cache: Whether to use/store cached results

        Returns:
            Dict with 'markdown', 'html', and 'metadata' keys, or None on failure
        """
        # Check cache first
        if use_cache and self.cache:
            cached = self.cache.get(url, "scrape")
            if cached:
                logger.debug(f"Using cached scrape for {url}")
                return cached

        try:
            response = self.session.post(
                f"{self.base_url}/v1/scrape",
                json={
                    "url": url,
                    "formats": ["markdown", "html"]
                },
                timeout=60
            )

            if response.status_code != 200:
                logger.warning(f"Firecrawl scrape returned {response.status_code}")
                return None

            data = response.json()
            if not data.get("success"):
                return None

            doc = data.get("data", {})
            result = {
                "markdown": doc.get("markdown", ""),
                "html": doc.get("html", ""),
                "metadata": doc.get("metadata", {}),
                "url": url
            }

            # Cache successful results
            if use_cache and self.cache:
                self.cache.set(url, "scrape", result)

            return result

        except Exception as e:
            logger.error(f"Firecrawl scrape error for {url}: {e}")
            return None


def discover_and_scrape_bell_schedules(
    district_url: str,
    max_urls: int = 5,
    try_school_level: bool = True
) -> List[Dict]:
    """
    Convenience function to discover and scrape bell schedule pages.

    Args:
        district_url: Base URL of the school district
        max_urls: Maximum number of URLs to scrape
        try_school_level: If district-level fails, try school-level discovery

    Returns:
        List of scraped page data with content
    """
    discovery = FirecrawlDiscovery()

    if not discovery.is_available():
        logger.warning("Firecrawl not available, skipping discovery")
        return []

    # First try district-level discovery
    urls = discovery.discover_bell_schedule_urls(district_url)
    logger.info(f"Discovered {len(urls)} potential bell schedule URLs at district level")

    results = []
    for url in urls[:max_urls]:
        logger.debug(f"Scraping: {url}")
        data = discovery.scrape_url(url)
        if data:
            results.append(data)

    # If no results and school-level enabled, try school sites
    if not results and try_school_level:
        logger.info("No district-level results, trying school-level discovery")
        school_sites = discovery.discover_school_sites(district_url)
        logger.info(f"Found {len(school_sites)} school sites")

        for school_url in school_sites[:10]:  # Try up to 10 schools
            school_urls = discovery.discover_bell_schedule_urls(school_url)
            for url in school_urls[:2]:  # 2 URLs per school
                data = discovery.scrape_url(url)
                if data:
                    results.append(data)
                    if len(results) >= max_urls:
                        break
            if len(results) >= max_urls:
                break

    return results


def get_expected_grade_levels(gslo: str, gshi: str) -> List[str]:
    """
    Determine expected grade levels based on NCES grade span codes.

    Args:
        gslo: Grade span low (PK, KG, 01-12)
        gshi: Grade span high (PK, KG, 01-12)

    Returns:
        List of grade levels: subset of ['elementary', 'middle', 'high']
    """
    if not gslo or not gshi:
        return ['elementary', 'middle', 'high']  # Default to all

    # Convert to numeric
    def to_num(grade):
        if grade in ('PK', 'pk'):
            return -1
        if grade in ('KG', 'kg'):
            return 0
        try:
            return int(grade)
        except:
            return 0

    low = to_num(gslo)
    high = to_num(gshi)

    levels = []

    # Elementary: serves any of PK-5
    if low <= 5 and high >= 0:
        levels.append('elementary')

    # Middle: serves any of 6-8
    if low <= 8 and high >= 6:
        levels.append('middle')

    # High: serves any of 9-12
    if high >= 9:
        levels.append('high')

    return levels if levels else ['high']  # Default to high if nothing detected


def extract_bell_schedule(
    district_url: str,
    max_urls: int = 5
) -> Optional[Tuple[Dict, str]]:
    """
    End-to-end bell schedule extraction using Firecrawl and ContentParser (single result).

    Args:
        district_url: Base URL of the school district
        max_urls: Maximum number of URLs to try

    Returns:
        Tuple of (BellScheduleData dict, source_url) or None if not found
    """
    results = extract_bell_schedules_all(district_url, max_urls)
    if not results:
        return None

    # Prioritize high > middle > elementary
    for level in ['high', 'middle', 'elementary']:
        for schedule_data, source_url in results:
            if schedule_data.get('grade_level') == level:
                return (schedule_data, source_url)

    return results[0] if results else None


def extract_bell_schedules_all(
    district_url: str,
    max_urls: int = 5,
    expected_levels: List[str] = None
) -> List[Tuple[Dict, str]]:
    """
    End-to-end bell schedule extraction for ALL grade levels.

    Args:
        district_url: Base URL of the school district
        max_urls: Maximum number of URLs to try
        expected_levels: List of grade levels to extract (e.g., ['elementary', 'middle', 'high'])

    Returns:
        List of (BellScheduleData dict, source_url) tuples, one per grade level found
    """
    from .content_parser import ContentParser

    discovery = FirecrawlDiscovery()
    parser = ContentParser(use_llm=False)  # LLM fallback disabled for now

    if not discovery.is_available():
        logger.warning("Firecrawl not available")
        return []

    # Discover and scrape
    results = discover_and_scrape_bell_schedules(district_url, max_urls)

    # Collect all schedules from all pages
    all_schedules = []
    found_levels = set()

    for result in results:
        schedules = parser.parse_all(
            result.get('markdown', ''),
            result.get('html', ''),
            expected_levels=expected_levels
        )

        for schedule in schedules:
            if schedule.grade_level not in found_levels:
                found_levels.add(schedule.grade_level)
                all_schedules.append((
                    {
                        'start_time': schedule.start_time,
                        'end_time': schedule.end_time,
                        'instructional_minutes': schedule.instructional_minutes,
                        'grade_level': schedule.grade_level,
                        'confidence': schedule.confidence,
                        'source_method': f"firecrawl_{schedule.source_method}",
                        'schools_sampled': schedule.schools_sampled,
                    },
                    result['url']
                ))

        # Stop if we have all expected levels
        if expected_levels and found_levels >= set(expected_levels):
            break

    return all_schedules


def save_firecrawl_result_to_database(
    session,
    district_id: str,
    schedule_data: Dict,
    source_url: str,
    tier: int = 1
) -> Tuple[bool, str]:
    """
    Save single Firecrawl extraction result to the enrichment queue and bell_schedules table.

    Args:
        session: SQLAlchemy database session
        district_id: NCES district ID
        schedule_data: Dict from extract_bell_schedule (start_time, end_time, etc.)
        source_url: URL where the schedule was found
        tier: Which tier to record this as (default 1 for Firecrawl)

    Returns:
        Tuple of (success: bool, message: str)
    """
    # Wrap single schedule in list and call multi-save
    results = save_firecrawl_results_to_database(
        session, district_id, [(schedule_data, source_url)], tier
    )
    return results


def save_firecrawl_results_to_database(
    session,
    district_id: str,
    schedule_results: List[Tuple[Dict, str]],
    tier: int = 1
) -> Tuple[bool, str]:
    """
    Save multiple Firecrawl extraction results (all grade levels) to the database.

    This function:
    1. Creates/updates an EnrichmentQueue record with combined Firecrawl results
    2. Marks it as completed
    3. Directly inserts into bell_schedules table for each grade level

    Args:
        session: SQLAlchemy database session
        district_id: NCES district ID
        schedule_results: List of (schedule_data dict, source_url) tuples
        tier: Which tier to record this as (default 1 for Firecrawl)

    Returns:
        Tuple of (success: bool, message: str)
    """
    from sqlalchemy import text
    from infrastructure.database.models import EnrichmentQueue

    if not schedule_results:
        return False, "No schedules to save"

    # Verify district exists using raw SQL (avoids ORM schema mismatch issues)
    result = session.execute(
        text("SELECT nces_id FROM districts WHERE nces_id = :id"),
        {"id": district_id}
    )
    if not result.fetchone():
        return False, f"District {district_id} not found in database"

    # Build combined tier result with all grade levels
    tier_result = {
        'schedules': [],
        'year': '2025-26',
        'extraction_method': 'firecrawl',
    }

    saved_levels = []

    for schedule_data, source_url in schedule_results:
        grade_level = schedule_data.get('grade_level', 'high')

        tier_result['schedules'].append({
            'start_time': schedule_data.get('start_time'),
            'end_time': schedule_data.get('end_time'),
            'instructional_minutes': schedule_data.get('instructional_minutes'),
            'schedule_type': grade_level,
            'confidence': schedule_data.get('confidence', 0.8),
            'source_url': source_url,
            'extraction_method': schedule_data.get('source_method', 'firecrawl'),
            'schools_sampled': schedule_data.get('schools_sampled', []),
        })

        # Insert directly into bell_schedules table
        try:
            # Check if record exists
            existing = session.execute(
                text("""
                    SELECT id FROM bell_schedules
                    WHERE district_id = :district_id AND year = '2025-26' AND grade_level = :grade_level
                """),
                {"district_id": district_id, "grade_level": grade_level}
            ).fetchone()

            if existing:
                # Update existing
                session.execute(
                    text("""
                        UPDATE bell_schedules SET
                            start_time = :start_time,
                            end_time = :end_time,
                            instructional_minutes = :instructional_minutes,
                            source_urls = :source_urls,
                            confidence = :confidence,
                            method = 'automated_enrichment',
                            updated_at = NOW()
                        WHERE id = :id
                    """),
                    {
                        "id": existing[0],
                        "start_time": schedule_data.get('start_time'),
                        "end_time": schedule_data.get('end_time'),
                        "instructional_minutes": schedule_data.get('instructional_minutes'),
                        "source_urls": f'["{source_url}"]',
                        "confidence": 'high' if schedule_data.get('confidence', 0.8) >= 0.8 else 'medium',
                    }
                )
            else:
                # Insert new
                session.execute(
                    text("""
                        INSERT INTO bell_schedules
                        (district_id, year, grade_level, start_time, end_time, instructional_minutes,
                         source_urls, confidence, method)
                        VALUES (:district_id, '2025-26', :grade_level, :start_time, :end_time,
                                :instructional_minutes, :source_urls, :confidence, 'automated_enrichment')
                    """),
                    {
                        "district_id": district_id,
                        "grade_level": grade_level,
                        "start_time": schedule_data.get('start_time'),
                        "end_time": schedule_data.get('end_time'),
                        "instructional_minutes": schedule_data.get('instructional_minutes'),
                        "source_urls": f'["{source_url}"]',
                        "confidence": 'high' if schedule_data.get('confidence', 0.8) >= 0.8 else 'medium',
                    }
                )

            saved_levels.append(grade_level)

        except Exception as e:
            logger.error(f"Error saving {grade_level} schedule for {district_id}: {e}")

    # Update enrichment queue
    enrichment = session.query(EnrichmentQueue).filter_by(district_id=district_id).first()

    if not enrichment:
        enrichment = EnrichmentQueue(
            district_id=district_id,
            current_tier=tier,
            status='completed'
        )
        session.add(enrichment)
    else:
        enrichment.current_tier = tier
        enrichment.status = 'completed'

    # Set the tier result
    if tier == 1:
        enrichment.tier_1_result = tier_result
    elif tier == 2:
        enrichment.tier_2_result = tier_result
    elif tier == 3:
        enrichment.tier_3_result = tier_result
    elif tier == 4:
        enrichment.tier_4_result = tier_result
    elif tier == 5:
        enrichment.tier_5_result = tier_result

    session.commit()

    if saved_levels:
        return True, f"Saved {len(saved_levels)} grade levels: {', '.join(saved_levels)}"
    else:
        return False, "No schedules saved successfully"


def enrich_district_with_firecrawl(
    session,
    district_id: str,
    max_urls: int = 5,
    extract_all_levels: bool = True
) -> Tuple[bool, str]:
    """
    Complete Firecrawl enrichment workflow for a single district.

    This is the main entry point for Firecrawl-based enrichment:
    1. Gets district URL and grade span from database
    2. Determines which grade levels to extract based on GSLO/GSHI
    3. Uses Firecrawl to discover and extract bell schedules for each level
    4. Saves results to enrichment_queue and bell_schedules tables

    Args:
        session: SQLAlchemy database session
        district_id: NCES district ID
        max_urls: Maximum URLs to try
        extract_all_levels: If True, extract all grade levels; if False, just high school

    Returns:
        Tuple of (success: bool, message: str)
    """
    from sqlalchemy import text

    # Get district with grade span using raw SQL (avoids ORM schema mismatch issues)
    result = session.execute(
        text("""
            SELECT nces_id, name, website_url, grade_span_low, grade_span_high
            FROM districts WHERE nces_id = :id
        """),
        {"id": district_id}
    )
    row = result.fetchone()

    if not row:
        return False, f"District {district_id} not found"

    district_name = row[1]
    website_url = row[2]
    gslo = row[3]
    gshi = row[4]

    if not website_url:
        return False, f"District {district_id} has no website URL"

    # Determine expected grade levels from grade span
    if extract_all_levels:
        expected_levels = get_expected_grade_levels(gslo, gshi)
        logger.info(f"District {district_id} ({district_name}): expecting levels {expected_levels} (span: {gslo}-{gshi})")
    else:
        expected_levels = None  # Will prioritize high school

    # Extract bell schedules for all expected levels
    if extract_all_levels and expected_levels:
        extraction_results = extract_bell_schedules_all(website_url, max_urls, expected_levels)

        if not extraction_results:
            return False, f"No bell schedules found for {district_name}"

        # Save all results
        return save_firecrawl_results_to_database(
            session, district_id, extraction_results
        )
    else:
        # Backward compatible single extraction
        extraction_result = extract_bell_schedule(website_url, max_urls)

        if not extraction_result:
            return False, f"No bell schedule found for {district_name}"

        schedule_data, source_url = extraction_result
        return save_firecrawl_result_to_database(
            session, district_id, schedule_data, source_url
        )


# Test if running directly
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with a sample district
    discovery = FirecrawlDiscovery()

    if discovery.is_available():
        print("Firecrawl is available!")

        # Test discovery
        urls = discovery.discover_bell_schedule_urls("https://www.leeschools.net")
        print(f"\nDiscovered {len(urls)} URLs:")
        for url in urls[:10]:
            print(f"  - {url}")

        # Test scrape
        if urls:
            print(f"\nScraping first URL: {urls[0]}")
            data = discovery.scrape_url(urls[0])
            if data:
                print(f"  Markdown length: {len(data['markdown'])} chars")
                print(f"  HTML length: {len(data['html'])} chars")
    else:
        print("Firecrawl is not available")
        print("Start it with: cd ~/Development/firecrawl-main/apps/api && pnpm run server:production")
