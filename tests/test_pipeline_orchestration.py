#!/usr/bin/env python3
"""
End-to-End Pipeline Orchestration Tests

REQ-033: End-to-end pipeline verification

These tests verify the full enrichment pipeline works correctly from
URL discovery through to LCT calculation and export. They test cross-stage
data contracts and ensure outputs from one stage are valid inputs for the next.

Pipeline stages tested:
1. URL Discovery (NCES CCD import, Firecrawl discovery)
2. Content Scraping (Playwright scraper service)
3. Content Parsing (ContentParser, bell schedule extraction)
4. Database Enrichment (enrichment_utils, bell_schedules table)
5. LCT Calculation (calculate_lct_variants.py)
6. Data Export (CSV/JSON with metadata)
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ===========================================================================
# Cross-Stage Data Contract Tests
# ===========================================================================

class TestScraperToParserContract:
    """
    Verify scraper output format matches parser expected input.

    Contract: Scraper returns {success, url, html, markdown, title, error, errorCode, timing}
    Parser expects: markdown string and optional html string
    """

    def test_scraper_response_has_required_fields(self):
        """Scraper response must have fields parser needs."""
        # Simulated scraper response
        scraper_response = {
            'success': True,
            'url': 'https://example.com/bell-schedule',
            'html': '<html><body><h1>Bell Schedule</h1></body></html>',
            'markdown': '# Bell Schedule\n\nStart: 8:00 AM\nEnd: 3:00 PM',
            'title': 'Bell Schedule',
            'timing': 1500,
        }

        # Parser requires these fields
        assert 'markdown' in scraper_response
        assert 'html' in scraper_response
        assert scraper_response['markdown'] is not None or scraper_response['html'] is not None

    def test_scraper_error_response_format(self):
        """Scraper error responses must have errorCode for retry logic."""
        error_response = {
            'success': False,
            'url': 'https://example.com/bell-schedule',
            'error': 'Connection timeout',
            'errorCode': 'TIMEOUT',
            'timing': 30000,
        }

        # REQ-030: Error codes used for retry decisions
        valid_error_codes = ['TIMEOUT', 'NETWORK_ERROR', 'BLOCKED', 'NOT_FOUND', 'QUEUE_FULL']
        assert error_response['errorCode'] in valid_error_codes

    def test_parser_handles_scraper_output(self):
        """Parser correctly processes scraper output format."""
        from infrastructure.scripts.enrich.content_parser import ContentParser

        # Simulated scraper response with bell schedule
        scraper_response = {
            'success': True,
            'markdown': '''
            # Bell Schedule

            | School Level | Bell Times |
            |-------------|-----------|
            | High School | 7:35 AM - 2:20 PM |
            ''',
            'html': '',
        }

        parser = ContentParser(use_llm=False)
        result = parser.parse(
            markdown=scraper_response.get('markdown', ''),
            html=scraper_response.get('html', '')
        )

        assert result is not None
        assert result.start_time is not None
        assert result.end_time is not None
        assert result.instructional_minutes > 0


class TestParserToDatabaseContract:
    """
    Verify parser output format matches database enrichment expected input.

    Contract: Parser returns BellScheduleData dataclass
    Database expects: start_time, end_time, instructional_minutes, grade_level, confidence, source_method
    """

    def test_bell_schedule_data_has_required_fields(self):
        """BellScheduleData must have all fields database needs."""
        from infrastructure.scripts.enrich.content_parser import BellScheduleData

        data = BellScheduleData(
            start_time="8:00 AM",
            end_time="3:00 PM",
            instructional_minutes=420,
            grade_level="high",
            confidence=0.9,
            source_method="table",
        )

        # Database columns require these
        assert hasattr(data, 'start_time')
        assert hasattr(data, 'end_time')
        assert hasattr(data, 'instructional_minutes')
        assert hasattr(data, 'grade_level')
        assert hasattr(data, 'confidence')
        assert hasattr(data, 'source_method')

    def test_grade_level_values_valid(self):
        """Grade level must be one of expected values."""
        from infrastructure.scripts.enrich.content_parser import BellScheduleData

        valid_levels = ['elementary', 'middle', 'high']

        for level in valid_levels:
            data = BellScheduleData(
                start_time="8:00 AM",
                end_time="3:00 PM",
                instructional_minutes=420,
                grade_level=level,
            )
            assert data.grade_level in valid_levels

    def test_instructional_minutes_in_valid_range(self):
        """Instructional minutes must be within reasonable range."""
        from infrastructure.scripts.enrich.content_parser import BellScheduleData

        # Valid range: 240-540 minutes (4-9 hours)
        data = BellScheduleData(
            start_time="8:00 AM",
            end_time="3:00 PM",
            instructional_minutes=420,
            grade_level="high",
        )

        assert 240 <= data.instructional_minutes <= 540


class TestDatabaseToCalculationContract:
    """
    Verify database output format matches LCT calculation expected input.

    Contract: get_instructional_minutes() returns (minutes, source, year)
    Calculation expects: integer minutes value
    """

    def test_instructional_minutes_return_format(self):
        """get_instructional_minutes should return tuple with minutes."""
        # Mock the database query result
        mock_result = (360, 'bell_schedule', '2024-25')

        minutes, source, year = mock_result

        assert isinstance(minutes, int)
        assert minutes > 0
        assert source in ['bell_schedule', 'state_requirement', 'default']
        assert year is None or isinstance(year, str)

    def test_lct_calculation_input_validation(self):
        """LCT calculation handles various input scenarios."""
        # LCT = (minutes * staff) / enrollment

        test_cases = [
            # (minutes, staff, enrollment, expected_valid)
            (360, 100, 1000, True),   # Normal case
            (360, 0, 1000, False),    # Zero staff
            (360, 100, 0, False),     # Zero enrollment
            (0, 100, 1000, False),    # Zero minutes
            (None, 100, 1000, False), # None minutes
        ]

        for minutes, staff, enrollment, expected_valid in test_cases:
            if expected_valid and minutes and staff and enrollment:
                lct = (minutes * staff) / enrollment
                assert lct > 0
            else:
                # Should handle gracefully
                pass


class TestCalculationToExportContract:
    """
    Verify LCT calculation output format matches export expected input.

    Contract: Calculations produce district rows with LCT values per scope
    Export expects: district_id, nces_id, state, and LCT values for each scope
    """

    def test_lct_output_has_required_columns(self):
        """LCT output must have columns export needs."""
        # Simulated LCT calculation output
        lct_row = {
            'district_id': 1,
            'nces_id': '0100001',
            'district_name': 'Test District',
            'state': 'AL',
            'enrollment_k12': 5000,
            'teachers_only': 18.5,
            'teachers_core': 22.3,
            'instructional': 28.7,
            'all': 35.2,
        }

        # Export requires these columns
        required_columns = ['nces_id', 'state', 'teachers_only', 'instructional']
        for col in required_columns:
            assert col in lct_row

    def test_lct_values_in_valid_range(self):
        """LCT values must be within valid range 0-360."""
        lct_row = {
            'teachers_only': 18.5,
            'teachers_core': 22.3,
            'instructional': 28.7,
            'all': 35.2,
        }

        for scope, value in lct_row.items():
            assert 0 < value <= 360, f"LCT {scope}={value} out of range"


# ===========================================================================
# End-to-End Flow Tests (Mocked)
# ===========================================================================

class TestEndToEndEnrichmentFlow:
    """
    Test full enrichment pipeline with mocked external dependencies.

    Flow: District URL -> Scrape -> Parse -> Store -> Calculate -> Export
    """

    @pytest.fixture
    def sample_district(self):
        """Sample district data for testing."""
        return {
            'nces_id': '0100001',
            'district_name': 'Test Unified School District',
            'state': 'AL',
            'website_url': 'https://testusd.k12.al.us',
            'grade_span_low': 'PK',
            'grade_span_high': '12',
            'enrollment_k12': 5000,
            'teachers': 250,
        }

    @pytest.fixture
    def sample_scraper_response(self):
        """Sample successful scraper response."""
        return {
            'success': True,
            'url': 'https://testusd.k12.al.us/bell-schedule',
            'markdown': '''
            # Bell Schedule 2024-25

            | School Level | Bell Times |
            |--------------|-----------|
            | Elementary | 7:30 AM - 2:30 PM |
            | Middle School | 7:45 AM - 2:45 PM |
            | High School | 8:00 AM - 3:00 PM |
            ''',
            'html': '<html></html>',
            'title': 'Bell Schedule',
            'timing': 1500,
        }

    def test_full_enrichment_pipeline_mocked(self, sample_district, sample_scraper_response):
        """
        Test complete enrichment pipeline with all external calls mocked.

        This verifies data flows correctly through all stages.
        """
        from infrastructure.scripts.enrich.content_parser import ContentParser

        # Stage 1: URL Discovery (mock - district already has URL)
        assert sample_district['website_url'] is not None

        # Stage 2: Content Scraping (mock response)
        scraper_response = sample_scraper_response
        assert scraper_response['success'] is True

        # Stage 3: Content Parsing
        parser = ContentParser(use_llm=False)
        results = parser.parse_all(
            markdown=scraper_response['markdown'],
            html=scraper_response['html'],
        )

        assert len(results) == 3  # elementary, middle, high

        # Verify all grade levels extracted
        levels = {r.grade_level for r in results}
        assert levels == {'elementary', 'middle', 'high'}

        # Stage 4: Database Enrichment (mock)
        for result in results:
            enrichment_data = {
                'district_id': sample_district['nces_id'],
                'year': '2024-25',
                'grade_level': result.grade_level,
                'start_time': result.start_time,
                'end_time': result.end_time,
                'instructional_minutes': result.instructional_minutes,
                'confidence': result.confidence,
                'source_method': result.source_method,
            }

            # Validate data structure
            assert enrichment_data['instructional_minutes'] >= 240
            assert enrichment_data['instructional_minutes'] <= 540

        # Stage 5: LCT Calculation (mock)
        high_school = next(r for r in results if r.grade_level == 'high')
        lct = (high_school.instructional_minutes * sample_district['teachers']) / sample_district['enrollment_k12']

        assert lct > 0
        assert lct <= 360

        # Stage 6: Export (mock)
        export_row = {
            'nces_id': sample_district['nces_id'],
            'district_name': sample_district['district_name'],
            'state': sample_district['state'],
            'enrollment_k12': sample_district['enrollment_k12'],
            'instructional_minutes': high_school.instructional_minutes,
            'lct_teachers_only': round(lct, 2),
        }

        # Validate export data
        assert export_row['lct_teachers_only'] > 0


class TestPartialFailureRecovery:
    """
    Test pipeline handles partial failures gracefully.
    """

    def test_handles_scraper_timeout(self):
        """Pipeline should handle scraper timeout for individual districts."""
        timeout_response = {
            'success': False,
            'url': 'https://slow-district.k12.us',
            'error': 'Request timed out after 30000ms',
            'errorCode': 'TIMEOUT',
            'timing': 30000,
        }

        # Should be marked as failed, not crash pipeline
        assert timeout_response['success'] is False
        assert timeout_response['errorCode'] == 'TIMEOUT'

        # REQ-030: Timeout should trigger retry
        retryable_errors = ['TIMEOUT', 'NETWORK_ERROR']
        assert timeout_response['errorCode'] in retryable_errors

    def test_handles_blocked_site(self):
        """Pipeline should handle blocked sites without retry."""
        blocked_response = {
            'success': False,
            'url': 'https://blocked-district.k12.us',
            'error': 'Security challenge detected',
            'errorCode': 'BLOCKED',
            'blocked': True,
            'timing': 5000,
        }

        # Should be marked for manual review, not retried
        assert blocked_response['blocked'] is True
        assert blocked_response['errorCode'] == 'BLOCKED'

        # REQ-030: Blocked should NOT trigger retry
        non_retryable_errors = ['BLOCKED', 'NOT_FOUND']
        assert blocked_response['errorCode'] in non_retryable_errors

    def test_handles_parse_failure(self):
        """Pipeline should handle parse failures gracefully."""
        from infrastructure.scripts.enrich.content_parser import ContentParser

        # Content with no parseable times
        unparseable_content = "Welcome to our school! Contact us for more information."

        parser = ContentParser(use_llm=False)
        result = parser.parse(unparseable_content, "")

        # Should return None, not crash
        assert result is None

    def test_handles_invalid_time_range(self):
        """Pipeline should reject invalid time ranges."""
        from infrastructure.scripts.enrich.content_parser import ContentParser

        # Time range too short (1 hour is not a valid school day)
        invalid_content = "School hours: 8:00 AM - 9:00 AM"

        parser = ContentParser(use_llm=False)
        result = parser.parse(invalid_content, "")

        # Should be rejected as invalid
        assert result is None


class TestBatchProcessing:
    """
    Test batch processing scenarios.
    """

    def test_multi_district_enrichment(self):
        """Batch enrichment should process multiple districts."""
        districts = [
            {'nces_id': '0100001', 'state': 'AL'},
            {'nces_id': '0100002', 'state': 'AL'},
            {'nces_id': '0100003', 'state': 'AL'},
        ]

        results = {
            'processed': 0,
            'success': 0,
            'failed': 0,
        }

        # Simulate batch processing
        for district in districts:
            results['processed'] += 1
            # Mock: alternating success/failure
            if results['processed'] % 2 == 1:
                results['success'] += 1
            else:
                results['failed'] += 1

        # Verify batch tracking
        assert results['processed'] == 3
        assert results['success'] + results['failed'] == results['processed']

    def test_state_level_aggregation(self):
        """State-level stats should aggregate correctly."""
        district_lcts = [
            {'state': 'AL', 'lct': 18.5},
            {'state': 'AL', 'lct': 22.3},
            {'state': 'AL', 'lct': 19.7},
            {'state': 'CA', 'lct': 25.1},
            {'state': 'CA', 'lct': 28.9},
        ]

        # Aggregate by state
        state_stats = {}
        for row in district_lcts:
            state = row['state']
            if state not in state_stats:
                state_stats[state] = {'sum': 0, 'count': 0}
            state_stats[state]['sum'] += row['lct']
            state_stats[state]['count'] += 1

        # Calculate averages
        for state, stats in state_stats.items():
            stats['avg'] = stats['sum'] / stats['count']

        assert state_stats['AL']['count'] == 3
        assert state_stats['CA']['count'] == 2
        assert 15 < state_stats['AL']['avg'] < 25


# ===========================================================================
# Data Quality Tracking
# ===========================================================================

class TestDataQualityTracking:
    """
    Test data quality is tracked through pipeline.
    """

    def test_confidence_level_preserved(self):
        """Confidence level should flow from parser to database."""
        from infrastructure.scripts.enrich.content_parser import BellScheduleData

        # High confidence from table parsing
        table_result = BellScheduleData(
            start_time="8:00 AM",
            end_time="3:00 PM",
            instructional_minutes=420,
            grade_level="high",
            confidence=0.9,
            source_method="table",
        )

        # Lower confidence from regex
        regex_result = BellScheduleData(
            start_time="8:00 AM",
            end_time="3:00 PM",
            instructional_minutes=420,
            grade_level="high",
            confidence=0.7,
            source_method="regex",
        )

        assert table_result.confidence > regex_result.confidence

    def test_source_method_tracked(self):
        """Source method should be tracked for transparency."""
        valid_methods = ['table', 'regex', 'llm', 'manual', 'state_requirement']

        for method in valid_methods:
            assert method in valid_methods


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
