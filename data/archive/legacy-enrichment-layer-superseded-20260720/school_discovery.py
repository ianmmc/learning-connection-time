"""
School Discovery Utilities

Provides functions for discovering individual school websites within districts.
Based on empirical findings showing 80%+ of districts do NOT publish district-wide
bell schedules - schedules are decentralized at the school level.

Usage:
    from infrastructure.utilities.school_discovery import discover_school_sites

    schools = discover_school_sites('https://district.org', 'WI')
    for school in schools:
        print(f"{school['name']}: {school['url']}")
"""

import requests
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

# State-specific URL patterns
# Based on DISTRICT_WEBSITE_LANDSCAPE_2026.md
STATE_PATTERNS = {
    'FL': ['{school}.{district}.k12.fl.us', '{district}.k12.fl.us/{school}'],
    'WI': ['{school}.{district}.k12.wi.us', '{district}.k12.wi.us/{school}'],
    'OR': ['{school}.{district}.k12.or.us', '{district}.k12.or.us/{school}'],
    'CA': ['{district}.org/{school}', '{school}.{district}.org'],
    'TX': ['{school}.{district}.net', '{district}.net/{school}'],
    'NY': ['{district}.org/schools/{school}', '{school}.{district}.org'],
    'IL': ['{school}.{district}.k12.il.us', '{district}.k12.il.us/{school}'],
    'MI': ['{school}.{district}.k12.mi.us', '{district}.k12.mi.us/{school}'],
    'PA': ['{school}.{district}.org', '{district}.org/{school}'],
    'VA': ['{school}.{district}.org', '{district}.org/{school}'],
    'MA': ['{school}.{district}.org', '{district}.org/{school}'],
}

# Common subdomain prefixes
COMMON_PREFIXES = [
    # Elementary
    'elementary', 'elem', 'es', 'primary',
    # Middle
    'middle', 'ms', 'intermediate', 'junior',
    # High
    'high', 'hs', 'senior',
]

# School abbreviation patterns
ABBREVIATION_PATTERNS = ['lhs', 'wms', 'ees', 'rhs', 'jhs']


def extract_domain(url: str) -> str:
    """Extract domain from URL"""
    parsed = urlparse(url)
    return parsed.netloc or url


def generate_subdomain_tests(district_domain: str, state: Optional[str] = None) -> List[str]:
    """
    Generate test URLs for common subdomain patterns

    Args:
        district_domain: Base district domain (e.g., 'district.org')
        state: Two-letter state code (optional, enables state-specific patterns)

    Returns:
        List of test URLs to check

    Example:
        >>> generate_subdomain_tests('milwaukee.k12.wi.us', 'WI')
        ['https://hs.milwaukee.k12.wi.us', 'https://ms.milwaukee.k12.wi.us', ...]
    """
    test_urls = []

    # State-specific patterns first (if state provided)
    if state and state in STATE_PATTERNS:
        for prefix in COMMON_PREFIXES[:6]:  # Top 6 most common
            test_urls.append(f"https://{prefix}.{district_domain}")

    # Generic subdomain tests
    for prefix in COMMON_PREFIXES:
        test_urls.append(f"https://{prefix}.{district_domain}")

    # School abbreviations
    for abbr in ABBREVIATION_PATTERNS:
        test_urls.append(f"https://{abbr}.{district_domain}")

    # Deduplicate
    return list(set(test_urls))


def test_url_accessibility(url: str, timeout: int = 10) -> Tuple[bool, int]:
    """
    Test if a URL is accessible

    Args:
        url: URL to test
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_accessible, status_code)

    Example:
        >>> accessible, status = test_url_accessibility('https://hs.district.org')
        >>> if accessible:
        ...     print(f"Found school site at {url}")
    """
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        status = response.status_code

        # Consider 200 and redirects (301/302/307) as accessible
        is_accessible = 200 <= status < 400

        # Check if redirected to completely different domain
        if is_accessible:
            original_domain = extract_domain(url)
            final_domain = extract_domain(response.url)

            # If redirected away from district, not a school site
            if not final_domain.startswith(original_domain.split('.')[0]):
                is_accessible = False

        return is_accessible, status

    except requests.RequestException as e:
        logger.debug(f"URL {url} not accessible: {e}")
        return False, 0


def discover_school_sites_via_scraper(
    district_url: str,
    state: Optional[str] = None,
    scraper_url: str = "http://localhost:3000",
    representative_only: bool = True
) -> List[Dict]:
    """
    Discover school sites using the scraper service

    Args:
        district_url: District website URL
        state: Two-letter state code (optional)
        scraper_url: Scraper service URL
        representative_only: Return only representative sample (1 per level)

    Returns:
        List of school site dictionaries with keys: url, name, level, pattern

    Example:
        >>> schools = discover_school_sites_via_scraper('https://district.org', 'WI')
        >>> for school in schools:
        ...     print(f"{school['level']}: {school['url']}")
    """
    try:
        response = requests.post(
            f"{scraper_url}/discover",
            json={
                "districtUrl": district_url,
                "state": state,
                "representativeOnly": representative_only
            },
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                logger.info(f"Discovered {len(data['schools'])} school sites for {district_url}")
                return data['schools']

        logger.warning(f"School discovery failed for {district_url}: {response.status_code}")
        return []

    except requests.RequestException as e:
        logger.error(f"Failed to call scraper service: {e}")
        return []


def discover_school_sites_simple(
    district_domain: str,
    state: Optional[str] = None,
    max_tests: int = 10
) -> List[Dict]:
    """
    Discover school sites using simple HTTP HEAD requests (no JavaScript)

    This is a lightweight alternative to the scraper service.
    Use when scraper service is unavailable or for quick checks.

    Args:
        district_domain: District domain (e.g., 'district.org')
        state: Two-letter state code (optional)
        max_tests: Maximum number of URLs to test

    Returns:
        List of school site dictionaries

    Example:
        >>> schools = discover_school_sites_simple('milwaukee.k12.wi.us', 'WI')
    """
    test_urls = generate_subdomain_tests(district_domain, state)[:max_tests]
    schools = []

    for url in test_urls:
        accessible, status = test_url_accessibility(url)
        if accessible:
            prefix = url.split('//')[1].split('.')[0]

            # Determine level from prefix
            level = None
            if prefix in ['elementary', 'elem', 'es', 'primary']:
                level = 'elementary'
            elif prefix in ['middle', 'ms', 'intermediate', 'junior']:
                level = 'middle'
            elif prefix in ['high', 'hs', 'senior']:
                level = 'high'

            schools.append({
                'url': url,
                'name': f"{prefix} school",
                'level': level,
                'pattern': 'subdomain_test',
                'status_code': status
            })

            logger.info(f"Found accessible school site: {url} (status: {status})")

    return schools


def filter_schools_by_level(schools: List[Dict], level: str) -> List[Dict]:
    """
    Filter schools by grade level

    Args:
        schools: List of school dictionaries
        level: 'elementary', 'middle', or 'high'

    Returns:
        Filtered list of schools
    """
    return [s for s in schools if s.get('level') == level]


def get_representative_sample(schools: List[Dict]) -> List[Dict]:
    """
    Get representative sample of schools (1 per level)

    Args:
        schools: List of school dictionaries

    Returns:
        Representative sample (up to 3 schools, 1 per level)

    Example:
        >>> all_schools = discover_school_sites_simple('district.org')
        >>> sample = get_representative_sample(all_schools)
        >>> len(sample)  # 1-3 schools
        3
    """
    sample = []

    # Get one of each level
    for level in ['elementary', 'middle', 'high']:
        level_schools = filter_schools_by_level(schools, level)
        if level_schools:
            sample.append(level_schools[0])

    # If no levels determined, return up to 3 schools
    if not sample and schools:
        sample = schools[:3]

    return sample


# Convenience function combining strategies
def discover_schools(
    district_url: str,
    state: Optional[str] = None,
    use_scraper: bool = True,
    scraper_url: str = "http://localhost:3000"
) -> List[Dict]:
    """
    Discover school sites using the best available strategy

    This is the main entry point for school discovery.
    Tries scraper service first, falls back to simple HTTP requests.

    Args:
        district_url: District website URL
        state: Two-letter state code (optional)
        use_scraper: Whether to try scraper service first
        scraper_url: Scraper service URL

    Returns:
        List of discovered school sites

    Example:
        >>> schools = discover_schools('https://milwaukee.k12.wi.us', 'WI')
        >>> for school in get_representative_sample(schools):
        ...     print(f"Check {school['url']} for bell schedule")
    """
    schools = []

    # Strategy 1: Use scraper service (if available)
    if use_scraper:
        try:
            schools = discover_school_sites_via_scraper(
                district_url, state, scraper_url, representative_only=False
            )
            if schools:
                logger.info(f"Scraper service found {len(schools)} schools")
                return schools
        except Exception as e:
            logger.warning(f"Scraper service unavailable, falling back to simple discovery: {e}")

    # Strategy 2: Simple HTTP HEAD requests
    district_domain = extract_domain(district_url)
    schools = discover_school_sites_simple(district_domain, state)

    if schools:
        logger.info(f"Simple discovery found {len(schools)} schools")
    else:
        logger.warning(f"No school sites discovered for {district_url}")

    return schools


if __name__ == '__main__':
    # Example usage
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python school_discovery.py <district_url> [state_code]")
        sys.exit(1)

    district_url = sys.argv[1]
    state = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Discovering school sites for: {district_url}")
    schools = discover_schools(district_url, state)

    if schools:
        print(f"\nFound {len(schools)} school sites:")
        for school in get_representative_sample(schools):
            print(f"  [{school.get('level', 'unknown'):12}] {school['url']}")
    else:
        print("No school sites found")
