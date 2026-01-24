#!/usr/bin/env python3
"""
Content Parser for Bell Schedule Extraction

Hybrid extraction approach:
1. Parse markdown tables (for clean tabular data)
2. Try regex patterns (for text-based content)
3. Escalate to LLM if regex fails (Claude first, Gemini fallback)

This module bridges Firecrawl markdown output to structured bell schedule data.
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class BellScheduleData:
    """Structured bell schedule data extracted from content."""
    start_time: str
    end_time: str
    instructional_minutes: int
    grade_level: str = "high"  # 'elementary', 'middle', 'high'
    confidence: float = 0.0  # 0.0-1.0
    source_method: str = ""  # 'table', 'regex', 'llm'
    schools_sampled: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)


class ContentParser:
    """
    Hybrid content parser for bell schedule extraction.

    Usage:
        parser = ContentParser()
        result = parser.parse(markdown, html)
        if result:
            print(f"Start: {result.start_time}, End: {result.end_time}")
    """

    # Time patterns
    TIME_PATTERN = r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.)?)'

    # Patterns indicating start time
    START_PATTERNS = [
        r'(?:start|begin|arrival|first\s+bell|morning\s+bell)[:\s]+' + TIME_PATTERN,
        r'(?:school\s+(?:starts|begins))[:\s]+(?:at\s+)?' + TIME_PATTERN,
        r'(?:1st\s+period|first\s+period|period\s+1)[:\s]+' + TIME_PATTERN,
    ]

    # Patterns indicating end time
    END_PATTERNS = [
        r'(?:end|dismissal|release|final\s+bell|afternoon\s+bell)[:\s]+(?:is\s+)?(?:at\s+)?' + TIME_PATTERN,
        r'(?:school\s+(?:ends|dismisses))[:\s]+(?:at\s+)?' + TIME_PATTERN,
        r'(?:last\s+period|period\s+[678])[:\s]+\d{1,2}:\d{2}[^-]*[-–—]\s*' + TIME_PATTERN,
    ]

    # Time range pattern (e.g., "8:00 AM - 3:00 PM")
    TIME_RANGE_PATTERN = r'(\d{1,2}:\d{2}\s*(?:AM|am|a\.m\.)?)\s*[-–—to]+\s*(\d{1,2}:\d{2}\s*(?:PM|pm|p\.m\.)?)'

    # Grade level indicators
    ELEMENTARY_PATTERNS = [r'elementary', r'primary', r'k-?5', r'k-?6', r'grades?\s*k']
    MIDDLE_PATTERNS = [r'middle', r'junior\s*high', r'6-?8', r'7-?8', r'grades?\s*6']
    HIGH_PATTERNS = [r'high\s*school', r'secondary', r'9-?12', r'10-?12', r'grades?\s*9']

    def __init__(self, use_llm: bool = True):
        """
        Initialize the content parser.

        Args:
            use_llm: Whether to use LLM extraction as fallback
        """
        self.use_llm = use_llm

    def parse(self, markdown: str, html: str = "") -> Optional[BellScheduleData]:
        """
        Parse content to extract bell schedule data (single result, backward compatible).

        Args:
            markdown: Markdown content from Firecrawl
            html: Raw HTML content (fallback)

        Returns:
            BellScheduleData if extraction successful, None otherwise (prioritizes high school)
        """
        results = self.parse_all(markdown, html)
        if not results:
            return None

        # Prioritize high > middle > elementary for backward compatibility
        for level in ['high', 'middle', 'elementary']:
            for result in results:
                if result.grade_level == level:
                    return result

        return results[0] if results else None

    def parse_all(self, markdown: str, html: str = "", expected_levels: List[str] = None) -> List[BellScheduleData]:
        """
        Parse content to extract ALL bell schedule data for each grade level.

        Args:
            markdown: Markdown content from Firecrawl
            html: Raw HTML content (fallback)
            expected_levels: List of grade levels to extract (e.g., ['elementary', 'middle', 'high'])
                           If None, extracts all found levels

        Returns:
            List of BellScheduleData, one per grade level found
        """
        text = markdown if markdown else html
        if not text:
            return []

        results = []

        # Step 1: Try markdown table parsing (can return multiple levels)
        table_results = self._parse_markdown_tables_all(markdown)
        if table_results:
            for result in table_results:
                result.source_method = 'table'
                result.confidence = 0.9
            results.extend(table_results)

        # Step 2: Try regex patterns for any levels not yet found
        found_levels = {r.grade_level for r in results}
        missing_levels = (set(expected_levels) if expected_levels else {'elementary', 'middle', 'high'}) - found_levels

        if missing_levels:
            regex_result = self._regex_extraction(text)
            if regex_result and regex_result.grade_level in missing_levels:
                regex_result.source_method = 'regex'
                regex_result.confidence = 0.7
                results.append(regex_result)

        # Step 3: Try LLM extraction for remaining levels (if enabled)
        if self.use_llm:
            found_levels = {r.grade_level for r in results}
            missing_levels = (set(expected_levels) if expected_levels else set()) - found_levels

            for level in missing_levels:
                llm_result = self._llm_extraction(text, target_level=level)
                if llm_result:
                    llm_result.source_method = 'llm'
                    results.append(llm_result)

        # Filter to expected levels if specified
        if expected_levels:
            results = [r for r in results if r.grade_level in expected_levels]

        return results

    def _parse_markdown_tables(self, markdown: str) -> Optional[BellScheduleData]:
        """
        Parse markdown tables to extract bell schedule data (single result).

        Handles formats like:
        | School | Bell Times |
        |--------|-----------|
        | Elementary | 7:25-2:05 |
        | High School | 7:30-2:20 |
        """
        results = self._parse_markdown_tables_all(markdown)
        if not results:
            return None

        # Prioritize high > middle > elementary
        for level in ['high', 'middle', 'elementary']:
            for result in results:
                if result.grade_level == level:
                    return result

        return results[0] if results else None

    def _parse_markdown_tables_all(self, markdown: str) -> List[BellScheduleData]:
        """
        Parse markdown tables to extract ALL bell schedule data for each grade level.

        Returns:
            List of BellScheduleData, one per grade level found
        """
        if not markdown:
            return []

        # Find ALL markdown tables (rows with |)
        all_tables = []
        current_table = []
        in_table = False

        for line in markdown.split('\n'):
            line_stripped = line.strip()
            if '|' in line_stripped:
                in_table = True
                current_table.append(line_stripped)
            elif in_table:
                if current_table:
                    all_tables.append(current_table)
                current_table = []
                in_table = False

        # Don't forget last table
        if current_table:
            all_tables.append(current_table)

        # Extract time ranges from all tables
        times_by_level = {'elementary': [], 'middle': [], 'high': []}

        for table_lines in all_tables:
            if len(table_lines) < 3:  # Need header, separator, and at least one data row
                continue

            for line in table_lines[2:]:  # Skip header and separator
                cells = [c.strip() for c in line.split('|') if c.strip()]

                # Look for time patterns in each cell
                for cell in cells:
                    # Try time range pattern (e.g., "7:25-2:05" or "7:25 AM - 2:05 PM")
                    match = re.search(self.TIME_RANGE_PATTERN, cell, re.IGNORECASE)
                    if match:
                        start, end = match.groups()

                        # Determine grade level from the row
                        row_text = line.lower()
                        level = self._detect_grade_level(row_text)

                        times_by_level[level].append({
                            'start': self._normalize_time(start),
                            'end': self._normalize_time(end),
                            'raw': cell
                        })

        # Build results for each grade level with data
        results = []
        for level in ['elementary', 'middle', 'high']:
            if times_by_level[level]:
                times = times_by_level[level]
                # Use the first valid time found for this level
                start = times[0]['start']
                end = times[0]['end']
                minutes = self._calculate_minutes(start, end)

                if minutes and 240 <= minutes <= 540:  # 4-9 hours reasonable
                    results.append(BellScheduleData(
                        start_time=start,
                        end_time=end,
                        instructional_minutes=minutes,
                        grade_level=level,
                        schools_sampled=[t['raw'] for t in times[:5]],
                        raw_data={'times_by_level': {level: times_by_level[level]}}
                    ))

        return results

    def _regex_extraction(self, text: str) -> Optional[BellScheduleData]:
        """
        Extract bell schedule times using regex patterns.

        This is the existing approach from fetch_bell_schedules.py.
        """
        start_time = None
        end_time = None

        # Try start patterns
        for pattern in self.START_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start_time = self._normalize_time(match.group(1).strip())
                break

        # Try end patterns
        for pattern in self.END_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                end_time = self._normalize_time(match.group(1).strip())
                break

        # Try time range pattern if we're missing one
        if not start_time or not end_time:
            match = re.search(self.TIME_RANGE_PATTERN, text, re.IGNORECASE)
            if match:
                if not start_time:
                    start_time = self._normalize_time(match.group(1))
                if not end_time:
                    end_time = self._normalize_time(match.group(2))

        # Validate we have both times
        if not start_time or not end_time:
            return None

        # Calculate minutes
        minutes = self._calculate_minutes(start_time, end_time)
        if not minutes or minutes < 240 or minutes > 540:  # 4-9 hours
            return None

        # Detect grade level from context
        grade_level = self._detect_grade_level(text)

        return BellScheduleData(
            start_time=start_time,
            end_time=end_time,
            instructional_minutes=minutes,
            grade_level=grade_level,
        )

    def _llm_extraction(self, text: str, target_level: str = None) -> Optional[BellScheduleData]:
        """
        Use LLM to extract bell schedule times.

        Tries Claude first (via API), then Gemini (via MCP).

        Args:
            text: Content to parse
            target_level: Optional specific grade level to extract ('elementary', 'middle', 'high')

        Returns:
            BellScheduleData or None
        """
        # TODO: Implement LLM extraction
        # For now, return None to indicate this step is not yet implemented
        return None

    def _normalize_time(self, time_str: str) -> str:
        """
        Normalize a time string to consistent format.

        Examples:
            "8:00" -> "8:00 AM"
            "8:00am" -> "8:00 AM"
            "3:00 p.m." -> "3:00 PM"
        """
        time_str = time_str.strip()

        # Remove periods from am/pm
        time_str = re.sub(r'a\.m\.', 'AM', time_str, flags=re.IGNORECASE)
        time_str = re.sub(r'p\.m\.', 'PM', time_str, flags=re.IGNORECASE)
        time_str = re.sub(r'am', 'AM', time_str, flags=re.IGNORECASE)
        time_str = re.sub(r'pm', 'PM', time_str, flags=re.IGNORECASE)

        # Add space before AM/PM if missing
        time_str = re.sub(r'(\d)(AM|PM)', r'\1 \2', time_str)

        # Add AM/PM if missing (assume AM for times 6-11, PM for 12-5)
        if 'AM' not in time_str and 'PM' not in time_str:
            match = re.match(r'(\d{1,2}):(\d{2})', time_str)
            if match:
                hour = int(match.group(1))
                if 6 <= hour <= 11:
                    time_str += ' AM'
                elif hour == 12 or 1 <= hour <= 5:
                    time_str += ' PM'

        return time_str

    def _calculate_minutes(self, start: str, end: str) -> Optional[int]:
        """
        Calculate instructional minutes between start and end times.

        Args:
            start: Start time string (e.g., "8:00 AM")
            end: End time string (e.g., "3:00 PM")

        Returns:
            Number of minutes, or None if calculation fails
        """
        try:
            # Parse times
            start_parsed = self._parse_time(start)
            end_parsed = self._parse_time(end)

            if not start_parsed or not end_parsed:
                return None

            # Calculate difference in minutes
            start_minutes = start_parsed[0] * 60 + start_parsed[1]
            end_minutes = end_parsed[0] * 60 + end_parsed[1]

            diff = end_minutes - start_minutes

            # Handle edge case where end is before start (shouldn't happen)
            if diff < 0:
                diff += 24 * 60

            return diff

        except Exception:
            return None

    def _parse_time(self, time_str: str) -> Optional[tuple]:
        """
        Parse a time string to (hour, minute) tuple in 24-hour format.

        Returns:
            (hour, minute) tuple or None if parsing fails
        """
        time_str = time_str.strip().upper()

        match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)?', time_str)
        if not match:
            return None

        hour = int(match.group(1))
        minute = int(match.group(2))
        period = match.group(3)

        # Convert to 24-hour format
        if period == 'PM' and hour != 12:
            hour += 12
        elif period == 'AM' and hour == 12:
            hour = 0

        return (hour, minute)

    def _detect_grade_level(self, text: str) -> str:
        """
        Detect grade level from text context.

        Returns:
            'elementary', 'middle', or 'high'
        """
        text_lower = text.lower()

        for pattern in self.ELEMENTARY_PATTERNS:
            if re.search(pattern, text_lower):
                return 'elementary'

        for pattern in self.MIDDLE_PATTERNS:
            if re.search(pattern, text_lower):
                return 'middle'

        for pattern in self.HIGH_PATTERNS:
            if re.search(pattern, text_lower):
                return 'high'

        # Default to high school if no grade level detected
        return 'high'


def parse_firecrawl_result(firecrawl_data: Dict) -> Optional[BellScheduleData]:
    """
    Parse a Firecrawl scrape result to extract bell schedule data (single result).

    Args:
        firecrawl_data: Response from Firecrawl /v1/scrape endpoint

    Returns:
        BellScheduleData if extraction successful, None otherwise (prioritizes high school)
    """
    markdown = firecrawl_data.get('markdown', '')
    html = firecrawl_data.get('html', '')

    parser = ContentParser()
    return parser.parse(markdown, html)


def parse_firecrawl_result_all(
    firecrawl_data: Dict,
    expected_levels: List[str] = None
) -> List[BellScheduleData]:
    """
    Parse a Firecrawl scrape result to extract ALL bell schedule data.

    Args:
        firecrawl_data: Response from Firecrawl /v1/scrape endpoint
        expected_levels: List of grade levels to extract (e.g., ['elementary', 'middle', 'high'])
                        If None, extracts all found levels

    Returns:
        List of BellScheduleData, one per grade level found
    """
    markdown = firecrawl_data.get('markdown', '')
    html = firecrawl_data.get('html', '')

    parser = ContentParser()
    return parser.parse_all(markdown, html, expected_levels)


# For testing
if __name__ == "__main__":
    # Test with sample data containing all three levels
    sample_markdown = """
    # Bell Schedules

    | School Level | Bell Times |
    |-------------|-----------|
    | Elementary | 7:25 AM - 2:05 PM |
    | Middle School | 7:30 AM - 2:15 PM |
    | High School | 7:35 AM - 2:20 PM |
    """

    parser = ContentParser()

    print("=== Single Result (backward compatible) ===")
    result = parser.parse(sample_markdown, "")
    if result:
        print(f"  {result.grade_level}: {result.start_time} - {result.end_time} ({result.instructional_minutes} min)")
    else:
        print("  No bell schedule found")

    print("\n=== All Results (multi-level) ===")
    results = parser.parse_all(sample_markdown, "")
    if results:
        for result in results:
            print(f"  {result.grade_level}: {result.start_time} - {result.end_time} ({result.instructional_minutes} min)")
    else:
        print("  No bell schedules found")

    print("\n=== Filtered Results (K-8 district) ===")
    results = parser.parse_all(sample_markdown, "", expected_levels=['elementary', 'middle'])
    if results:
        for result in results:
            print(f"  {result.grade_level}: {result.start_time} - {result.end_time} ({result.instructional_minutes} min)")
    else:
        print("  No bell schedules found")
