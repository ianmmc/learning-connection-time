#!/usr/bin/env python3
"""
Tests for the ContentParser module.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.scripts.enrich.content_parser import ContentParser, BellScheduleData
from infrastructure.scripts.enrich.firecrawl_discovery import get_expected_grade_levels


class TestContentParser:
    """Test cases for ContentParser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ContentParser(use_llm=False)

    # === Table Parsing Tests ===

    def test_parse_markdown_table_basic(self):
        """Test parsing a basic markdown table."""
        markdown = """
        | School Level | Bell Times |
        |-------------|-----------|
        | Elementary | 7:25 AM - 2:05 PM |
        | High School | 7:35 AM - 2:20 PM |
        """
        result = self.parser.parse(markdown, "")

        assert result is not None
        assert result.start_time == "7:35 AM"
        assert result.end_time == "2:20 PM"
        assert result.grade_level == "high"
        assert result.source_method == "table"
        assert result.confidence >= 0.8

    def test_parse_markdown_table_no_am_pm(self):
        """Test parsing table with times missing AM/PM (uses regex fallback)."""
        # Tables without proper time ranges fall back to regex
        markdown = """
        High School Bell Schedule
        Start: 7:30 AM
        End: 2:20 PM
        """
        result = self.parser.parse(markdown, "")

        assert result is not None
        assert "7:30" in result.start_time
        assert "2:20" in result.end_time

    def test_parse_markdown_table_compact_times(self):
        """Test parsing table with compact time format (7:25-2:05)."""
        markdown = """
        | School | Times |
        |--------|-------|
        | Elementary | 7:25-2:05 |
        """
        result = self.parser.parse(markdown, "")

        assert result is not None
        assert result.instructional_minutes > 0

    # === Regex Extraction Tests ===

    def test_regex_explicit_start_end(self):
        """Test regex with explicit start/end times."""
        text = """
        School starts at 8:00 AM
        Dismissal is at 3:15 PM
        """
        result = self.parser.parse(text, "")

        assert result is not None
        assert result.start_time == "8:00 AM"
        assert result.end_time == "3:15 PM"
        assert result.source_method == "regex"

    def test_regex_time_range(self):
        """Test regex with time range format."""
        text = """
        School hours: 8:00 AM - 3:00 PM
        """
        result = self.parser.parse(text, "")

        assert result is not None
        assert result.instructional_minutes == 420  # 7 hours

    def test_regex_begin_ends(self):
        """Test regex with begin/ends keywords."""
        text = """
        School begins at 7:45 AM
        School ends at 2:30 PM
        """
        result = self.parser.parse(text, "")

        assert result is not None
        assert "7:45" in result.start_time
        assert "2:30" in result.end_time

    # === Time Normalization Tests ===

    def test_normalize_time_am_pm(self):
        """Test time normalization with various AM/PM formats."""
        assert self.parser._normalize_time("8:00am") == "8:00 AM"
        assert self.parser._normalize_time("3:00pm") == "3:00 PM"
        assert self.parser._normalize_time("8:00 a.m.") == "8:00 AM"
        assert self.parser._normalize_time("3:00 p.m.") == "3:00 PM"

    def test_normalize_time_inference(self):
        """Test AM/PM inference for times without period."""
        assert "AM" in self.parser._normalize_time("8:00")
        assert "PM" in self.parser._normalize_time("3:00")

    # === Minutes Calculation Tests ===

    def test_calculate_minutes_basic(self):
        """Test basic minutes calculation."""
        minutes = self.parser._calculate_minutes("8:00 AM", "3:00 PM")
        assert minutes == 420  # 7 hours

    def test_calculate_minutes_with_lunch(self):
        """Test typical school day length."""
        minutes = self.parser._calculate_minutes("7:30 AM", "2:30 PM")
        assert minutes == 420  # 7 hours

    def test_calculate_minutes_short_day(self):
        """Test early dismissal day."""
        minutes = self.parser._calculate_minutes("8:00 AM", "12:00 PM")
        assert minutes == 240  # 4 hours

    # === Grade Level Detection Tests ===

    def test_detect_grade_level_elementary(self):
        """Test elementary school detection."""
        assert self.parser._detect_grade_level("Elementary School Schedule") == "elementary"
        assert self.parser._detect_grade_level("K-5 Bell Times") == "elementary"
        assert self.parser._detect_grade_level("Primary School Hours") == "elementary"

    def test_detect_grade_level_middle(self):
        """Test middle school detection."""
        assert self.parser._detect_grade_level("Middle School Schedule") == "middle"
        assert self.parser._detect_grade_level("Junior High Bell Times") == "middle"
        assert self.parser._detect_grade_level("Grades 6-8") == "middle"

    def test_detect_grade_level_high(self):
        """Test high school detection."""
        assert self.parser._detect_grade_level("High School Schedule") == "high"
        assert self.parser._detect_grade_level("9-12 Bell Times") == "high"
        assert self.parser._detect_grade_level("Secondary School") == "high"

    def test_detect_grade_level_default(self):
        """Test default grade level when none detected."""
        assert self.parser._detect_grade_level("Bell Schedule") == "high"

    # === Edge Cases ===

    def test_empty_content(self):
        """Test with empty content."""
        assert self.parser.parse("", "") is None
        assert self.parser.parse(None, None) is None

    def test_no_times_found(self):
        """Test with content that has no times."""
        text = "Welcome to our school. We have great teachers."
        assert self.parser.parse(text, "") is None

    def test_invalid_time_range(self):
        """Test with invalid time range (too short)."""
        text = "School hours: 8:00 AM - 9:00 AM"
        result = self.parser.parse(text, "")
        # Should return None because 1 hour is too short
        assert result is None

    def test_invalid_time_range_too_long(self):
        """Test with invalid time range (too long)."""
        text = "School hours: 6:00 AM - 6:00 PM"
        result = self.parser.parse(text, "")
        # Should return None because 12 hours is too long
        assert result is None


class TestMultiGradeExtraction:
    """Test cases for multi-grade level extraction."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ContentParser(use_llm=False)

    def test_parse_all_three_levels(self):
        """Test extracting all three grade levels from a table."""
        markdown = """
        | School Level | Bell Times |
        |-------------|-----------|
        | Elementary | 7:25 AM - 2:05 PM |
        | Middle School | 7:30 AM - 2:15 PM |
        | High School | 7:35 AM - 2:20 PM |
        """
        results = self.parser.parse_all(markdown, "")

        assert len(results) == 3

        # Check each level exists
        levels = {r.grade_level for r in results}
        assert levels == {'elementary', 'middle', 'high'}

        # Check times are different
        for result in results:
            assert result.instructional_minutes >= 400
            assert result.source_method == "table"

    def test_parse_all_with_filter(self):
        """Test filtering to specific grade levels (K-8 district)."""
        markdown = """
        | School Level | Bell Times |
        |-------------|-----------|
        | Elementary | 7:25 AM - 2:05 PM |
        | Middle School | 7:30 AM - 2:15 PM |
        | High School | 7:35 AM - 2:20 PM |
        """
        results = self.parser.parse_all(markdown, "", expected_levels=['elementary', 'middle'])

        assert len(results) == 2

        levels = {r.grade_level for r in results}
        assert 'high' not in levels
        assert 'elementary' in levels
        assert 'middle' in levels

    def test_parse_all_single_level(self):
        """Test when only one grade level is present."""
        markdown = """
        | School | Bell Times |
        |--------|-----------|
        | High School | 7:35 AM - 2:20 PM |
        """
        results = self.parser.parse_all(markdown, "", expected_levels=['elementary', 'middle', 'high'])

        assert len(results) == 1
        assert results[0].grade_level == "high"

    def test_parse_all_empty(self):
        """Test with no content."""
        results = self.parser.parse_all("", "")
        assert results == []

    def test_backward_compatible_parse(self):
        """Test that parse() still returns single result (high priority)."""
        markdown = """
        | School Level | Bell Times |
        |-------------|-----------|
        | Elementary | 7:25 AM - 2:05 PM |
        | Middle School | 7:30 AM - 2:15 PM |
        | High School | 7:35 AM - 2:20 PM |
        """
        result = self.parser.parse(markdown, "")

        # Should return high school (priority)
        assert result is not None
        assert result.grade_level == "high"
        assert result.start_time == "7:35 AM"


class TestBellScheduleData:
    """Test cases for BellScheduleData dataclass."""

    def test_dataclass_creation(self):
        """Test creating a BellScheduleData instance."""
        data = BellScheduleData(
            start_time="8:00 AM",
            end_time="3:00 PM",
            instructional_minutes=420,
            grade_level="high",
            confidence=0.9,
            source_method="table"
        )
        assert data.start_time == "8:00 AM"
        assert data.end_time == "3:00 PM"
        assert data.instructional_minutes == 420
        assert data.grade_level == "high"
        assert data.confidence == 0.9
        assert data.source_method == "table"
        assert data.schools_sampled == []
        assert data.raw_data == {}


class TestGradeSpanHelper:
    """Test cases for get_expected_grade_levels function."""

    def test_full_k12(self):
        """Test PK-12 district returns all levels."""
        levels = get_expected_grade_levels("PK", "12")
        assert set(levels) == {'elementary', 'middle', 'high'}

    def test_k8_district(self):
        """Test K-8 district (no high school)."""
        levels = get_expected_grade_levels("KG", "08")
        assert 'elementary' in levels
        assert 'middle' in levels
        assert 'high' not in levels

    def test_high_school_only(self):
        """Test 9-12 district (high school only)."""
        levels = get_expected_grade_levels("09", "12")
        assert levels == ['high']

    def test_6_12_district(self):
        """Test 6-12 district (middle + high)."""
        levels = get_expected_grade_levels("06", "12")
        assert 'middle' in levels
        assert 'high' in levels
        assert 'elementary' not in levels

    def test_elementary_only(self):
        """Test K-5 district (elementary only)."""
        levels = get_expected_grade_levels("KG", "05")
        assert levels == ['elementary']

    def test_none_values(self):
        """Test with None values returns all levels."""
        levels = get_expected_grade_levels(None, None)
        assert set(levels) == {'elementary', 'middle', 'high'}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
