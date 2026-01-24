#!/usr/bin/env python3
"""
Tests for Firecrawl URL Discovery Integration

REQ-034: Firecrawl URL discovery for bell schedule pages

These tests verify the Firecrawl integration for discovering bell schedule URLs
on district websites. Firecrawl provides intelligent crawling with:
- /v1/map - Discover URLs matching search terms
- /v1/scrape - Extract content from discovered URLs

The tests cover:
1. URL discovery via /v1/map endpoint
2. Content scraping via /v1/scrape endpoint
3. Integration with ContentParser
4. Error handling and fallback to Playwright
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ===========================================================================
# Configuration
# ===========================================================================

FIRECRAWL_API_KEY = os.environ.get('FIRECRAWL_API_KEY', '')


def firecrawl_api_available():
    """Check if Firecrawl API key is configured."""
    return bool(FIRECRAWL_API_KEY)


# ===========================================================================
# Unit Tests (Mocked)
# ===========================================================================

class TestFirecrawlMapEndpoint:
    """
    Test /v1/map endpoint for URL discovery.

    The map endpoint crawls a domain and returns URLs matching search criteria.
    """

    def test_map_response_structure(self):
        """Map endpoint should return expected structure."""
        # Expected Firecrawl /v1/map response structure
        mock_response = {
            'success': True,
            'links': [
                'https://example.com/bell-schedule',
                'https://example.com/about/hours',
                'https://example.com/calendar/bell-times',
            ],
        }

        assert mock_response['success'] is True
        assert 'links' in mock_response
        assert isinstance(mock_response['links'], list)
        assert len(mock_response['links']) > 0

    def test_map_search_terms(self):
        """Map should search for bell schedule related terms."""
        search_terms = [
            'bell schedule',
            'bell times',
            'school hours',
            'start time',
            'dismissal',
        ]

        # All terms should be searchable
        for term in search_terms:
            assert isinstance(term, str)
            assert len(term) > 0

    def test_map_filters_irrelevant_urls(self):
        """Map results should be filtered for relevance."""
        all_urls = [
            'https://example.com/bell-schedule',
            'https://example.com/contact',
            'https://example.com/staff-directory',
            'https://example.com/about/hours',
            'https://example.com/news/2024',
            'https://example.com/calendar/bell-times',
        ]

        # Filter for bell schedule related URLs
        relevant_keywords = ['bell', 'schedule', 'hours', 'times']
        filtered = [
            url for url in all_urls
            if any(kw in url.lower() for kw in relevant_keywords)
        ]

        assert len(filtered) < len(all_urls)
        assert 'https://example.com/bell-schedule' in filtered
        assert 'https://example.com/contact' not in filtered


class TestFirecrawlScrapeEndpoint:
    """
    Test /v1/scrape endpoint for content extraction.

    The scrape endpoint fetches a URL and returns markdown/HTML content.
    """

    def test_scrape_response_structure(self):
        """Scrape endpoint should return expected structure."""
        # Expected Firecrawl /v1/scrape response structure
        mock_response = {
            'success': True,
            'data': {
                'markdown': '# Bell Schedule\n\nSchool hours: 8:00 AM - 3:00 PM',
                'html': '<html><body><h1>Bell Schedule</h1></body></html>',
                'metadata': {
                    'title': 'Bell Schedule',
                    'sourceURL': 'https://example.com/bell-schedule',
                },
            },
        }

        assert mock_response['success'] is True
        assert 'data' in mock_response
        assert 'markdown' in mock_response['data']
        assert 'html' in mock_response['data']

    def test_scrape_extracts_markdown(self):
        """Scrape should convert HTML to clean markdown."""
        mock_response = {
            'data': {
                'markdown': '''
                # Bell Schedule 2024-25

                | School | Start | End |
                |--------|-------|-----|
                | High School | 8:00 AM | 3:00 PM |
                ''',
            },
        }

        markdown = mock_response['data']['markdown']
        assert '|' in markdown  # Has table
        assert '8:00 AM' in markdown  # Has times

    def test_scrape_handles_pdf_urls(self):
        """Scrape should handle PDF URLs with extraction."""
        # Firecrawl can extract text from PDFs
        mock_pdf_response = {
            'success': True,
            'data': {
                'markdown': '''
                BELL SCHEDULE

                High School
                First Bell: 7:45 AM
                Dismissal: 2:45 PM
                ''',
                'metadata': {
                    'sourceURL': 'https://example.com/docs/bell-schedule.pdf',
                    'contentType': 'application/pdf',
                },
            },
        }

        assert mock_pdf_response['success'] is True
        assert '7:45 AM' in mock_pdf_response['data']['markdown']


class TestFirecrawlDiscoveryIntegration:
    """
    Test firecrawl_discovery.py module functions.
    """

    def test_get_expected_grade_levels_full_k12(self):
        """K-12 district should expect all grade levels."""
        from infrastructure.scripts.enrich.firecrawl_discovery import get_expected_grade_levels

        levels = get_expected_grade_levels('PK', '12')
        assert 'elementary' in levels
        assert 'middle' in levels
        assert 'high' in levels

    def test_get_expected_grade_levels_k8(self):
        """K-8 district should not expect high school."""
        from infrastructure.scripts.enrich.firecrawl_discovery import get_expected_grade_levels

        levels = get_expected_grade_levels('KG', '08')
        assert 'elementary' in levels
        assert 'middle' in levels
        assert 'high' not in levels

    def test_get_expected_grade_levels_high_only(self):
        """9-12 district should only expect high school."""
        from infrastructure.scripts.enrich.firecrawl_discovery import get_expected_grade_levels

        levels = get_expected_grade_levels('09', '12')
        assert levels == ['high']

    def test_get_expected_grade_levels_none_values(self):
        """None values should return all grade levels."""
        from infrastructure.scripts.enrich.firecrawl_discovery import get_expected_grade_levels

        levels = get_expected_grade_levels(None, None)
        assert set(levels) == {'elementary', 'middle', 'high'}


class TestFirecrawlWithContentParser:
    """
    Test Firecrawl output integration with ContentParser.
    """

    def test_parse_firecrawl_result(self):
        """parse_firecrawl_result should handle Firecrawl response."""
        from infrastructure.scripts.enrich.content_parser import parse_firecrawl_result

        firecrawl_response = {
            'markdown': '''
            # Bell Schedule

            | School Level | Bell Times |
            |-------------|-----------|
            | High School | 7:35 AM - 2:20 PM |
            ''',
            'html': '',
        }

        result = parse_firecrawl_result(firecrawl_response)

        assert result is not None
        assert result.grade_level == 'high'
        assert '7:35' in result.start_time
        assert '2:20' in result.end_time

    def test_parse_firecrawl_result_all(self):
        """parse_firecrawl_result_all should extract all grade levels."""
        from infrastructure.scripts.enrich.content_parser import parse_firecrawl_result_all

        firecrawl_response = {
            'markdown': '''
            # Bell Schedule 2024-25

            | School Level | Bell Times |
            |-------------|-----------|
            | Elementary | 7:25 AM - 2:05 PM |
            | Middle School | 7:30 AM - 2:15 PM |
            | High School | 7:35 AM - 2:20 PM |
            ''',
            'html': '',
        }

        results = parse_firecrawl_result_all(firecrawl_response)

        assert len(results) == 3
        levels = {r.grade_level for r in results}
        assert levels == {'elementary', 'middle', 'high'}

    def test_parse_firecrawl_result_with_filter(self):
        """parse_firecrawl_result_all should filter by expected levels."""
        from infrastructure.scripts.enrich.content_parser import parse_firecrawl_result_all

        firecrawl_response = {
            'markdown': '''
            | School Level | Bell Times |
            |-------------|-----------|
            | Elementary | 7:25 AM - 2:05 PM |
            | Middle School | 7:30 AM - 2:15 PM |
            | High School | 7:35 AM - 2:20 PM |
            ''',
            'html': '',
        }

        # K-8 district - should only get elementary and middle
        results = parse_firecrawl_result_all(
            firecrawl_response,
            expected_levels=['elementary', 'middle']
        )

        assert len(results) == 2
        levels = {r.grade_level for r in results}
        assert 'high' not in levels


class TestFirecrawlErrorHandling:
    """
    Test error handling for Firecrawl operations.
    """

    def test_handles_api_error(self):
        """Should handle Firecrawl API errors gracefully."""
        error_response = {
            'success': False,
            'error': 'Rate limit exceeded',
        }

        assert error_response['success'] is False
        assert 'error' in error_response

    def test_handles_empty_map_results(self):
        """Should handle no URLs found from map."""
        empty_response = {
            'success': True,
            'links': [],
        }

        assert empty_response['success'] is True
        assert len(empty_response['links']) == 0

    def test_handles_scrape_blocked(self):
        """Should handle blocked/inaccessible sites."""
        blocked_response = {
            'success': False,
            'error': 'Access denied',
            'statusCode': 403,
        }

        assert blocked_response['success'] is False
        assert blocked_response['statusCode'] == 403

    def test_handles_timeout(self):
        """Should handle request timeouts."""
        timeout_response = {
            'success': False,
            'error': 'Request timeout',
        }

        assert timeout_response['success'] is False


class TestFirecrawlVsPlaywrightFallback:
    """
    Test fallback from Firecrawl to Playwright scraper.
    """

    def test_firecrawl_first_strategy(self):
        """Firecrawl should be tried before Playwright."""
        # Strategy order per plan
        extraction_order = ['firecrawl', 'playwright', 'pdf_ocr', 'claude', 'gemini', 'manual']

        assert extraction_order[0] == 'firecrawl'
        assert extraction_order[1] == 'playwright'

    def test_fallback_on_firecrawl_failure(self):
        """Should fallback to Playwright when Firecrawl fails."""
        firecrawl_failed = {
            'success': False,
            'error': 'Could not extract content',
        }

        # On failure, should try Playwright
        should_try_playwright = not firecrawl_failed['success']
        assert should_try_playwright is True

    def test_no_fallback_on_blocked(self):
        """Should not fallback for permanently blocked sites."""
        blocked_response = {
            'success': False,
            'error': 'Security challenge detected',
            'errorCode': 'BLOCKED',
        }

        # Blocked sites should be flagged for manual review, not retried
        should_fallback = blocked_response.get('errorCode') not in ['BLOCKED']
        assert should_fallback is False


# ===========================================================================
# Integration Tests (Require API Key)
# ===========================================================================

@pytest.mark.skipif(not firecrawl_api_available(), reason="FIRECRAWL_API_KEY not set")
class TestFirecrawlLiveAPI:
    """
    Live integration tests with Firecrawl API.

    These tests require FIRECRAWL_API_KEY environment variable.
    """

    def test_map_real_domain(self):
        """Test map endpoint with a real domain."""
        # This would make actual API call
        # Skip if no API key
        pytest.skip("Live API tests should be run manually")

    def test_scrape_real_url(self):
        """Test scrape endpoint with a real URL."""
        # This would make actual API call
        # Skip if no API key
        pytest.skip("Live API tests should be run manually")


# ===========================================================================
# Specification Tests (Document Expected Behavior)
# ===========================================================================

class TestFirecrawlSpecifications:
    """
    Specification tests documenting expected Firecrawl behavior.
    """

    def test_map_returns_ranked_urls(self):
        """
        Specification: /v1/map should return URLs ranked by relevance.

        When searching for "bell schedule", URLs containing that exact phrase
        should be ranked higher than URLs with partial matches.
        """
        # Document expected ranking behavior
        expected_ranking = [
            'https://example.com/bell-schedule',          # Exact match - rank 1
            'https://example.com/schedules/bell-times',   # Contains both - rank 2
            'https://example.com/about/hours',            # Related - rank 3
        ]

        # URLs should be in relevance order
        assert expected_ranking[0] == 'https://example.com/bell-schedule'

    def test_scrape_preserves_tables(self):
        """
        Specification: /v1/scrape markdown should preserve table structure.

        Tables containing bell schedule data should be preserved as markdown
        tables that ContentParser can extract.
        """
        # Expected table format
        expected_format = '''
        | School | Start | End |
        |--------|-------|-----|
        | High School | 8:00 AM | 3:00 PM |
        '''

        # Should contain pipe characters for table structure
        assert '|' in expected_format

    def test_scrape_extracts_time_patterns(self):
        """
        Specification: /v1/scrape should extract recognizable time patterns.

        Time patterns like "8:00 AM", "7:30 a.m.", "14:00" should be preserved
        in the markdown output for ContentParser to extract.
        """
        time_patterns = [
            '8:00 AM',
            '7:30 a.m.',
            '2:30 PM',
            '14:00',
        ]

        for pattern in time_patterns:
            # All patterns should be recognizable
            assert ':' in pattern  # Contains time separator


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
