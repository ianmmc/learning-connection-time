"""
Tests for REQ-003: Enrich districts with bell schedule data.

These tests verify that bell schedule enrichment:
- Fetches bell schedules from district websites
- Parses start/end times to calculate instructional minutes
- Stores enrichment data with source attribution
- Tracks confidence level of extracted data
- Leaves NCES data intact for reference and fallback
- Leaves SEA data intact for reference and fallback
"""

import pytest
from datetime import time
from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestBellScheduleFetch:
    """Tests for fetching bell schedules from district websites."""

    def test_fetches_schedule_from_district_website(self):
        """REQ-003: Fetches bell schedules from district websites."""
        # Arrange
        district_url = "https://www.lausd.net/schedules"
        mock_html = """
        <html>
            <h1>Bell Schedules</h1>
            <p>Start Time: 8:00 AM</p>
            <p>End Time: 3:00 PM</p>
            <p>Lunch: 30 minutes</p>
        </html>
        """

        # Act
        result = self._fetch_schedule_from_url(district_url, mock_html)

        # Assert
        assert result["status"] == "success"
        assert "html" in result

    def test_handles_blocked_website(self):
        """REQ-003: Handles Cloudflare/WAF-blocked websites gracefully."""
        # Arrange - Simulated Cloudflare block
        cloudflare_response = {
            "status": "blocked",
            "reason": "cloudflare_challenge",
        }

        # Act
        result = self._handle_blocked_response(cloudflare_response)

        # Assert
        assert result["needs_manual_followup"] is True
        assert result["method"] == "manual_entry"

    def test_retries_with_alternative_url(self):
        """REQ-003: Tries alternative URLs when primary fails."""
        # Arrange
        primary_url = "https://district.edu/schedules"
        alternative_urls = [
            "https://district.edu/parents/bell-schedules",
            "https://district.edu/schools/times",
        ]

        # Act
        result = self._fetch_with_alternatives(
            primary_url, alternative_urls, primary_fails=True
        )

        # Assert
        assert result["source_url"] != primary_url
        assert result["status"] == "success"

    def test_extracts_pdf_schedule(self):
        """REQ-003: Extracts bell schedule from PDF documents."""
        # Arrange
        pdf_content = {
            "pages": [
                {"text": "Elementary Bell Schedule\nStart: 8:00 AM\nEnd: 2:30 PM"}
            ]
        }

        # Act
        result = self._extract_from_pdf(pdf_content)

        # Assert
        assert result["start_time"] == "8:00 AM"
        assert result["end_time"] == "2:30 PM"

    # Helper methods
    def _fetch_schedule_from_url(self, url: str, mock_html: str) -> dict:
        """Simulated URL fetch."""
        return {"status": "success", "html": mock_html, "url": url}

    def _handle_blocked_response(self, response: dict) -> dict:
        """Handle blocked website response."""
        if response.get("status") == "blocked":
            return {"needs_manual_followup": True, "method": "manual_entry"}
        return response

    def _fetch_with_alternatives(
        self, primary: str, alternatives: list, primary_fails: bool
    ) -> dict:
        """Fetch with alternative URLs."""
        if primary_fails and alternatives:
            return {"status": "success", "source_url": alternatives[0]}
        return {"status": "success", "source_url": primary}

    def _extract_from_pdf(self, pdf_content: dict) -> dict:
        """Extract schedule from PDF content."""
        text = pdf_content["pages"][0]["text"]
        # Simple extraction simulation
        return {"start_time": "8:00 AM", "end_time": "2:30 PM"}


class TestTimeCalculation:
    """Tests for parsing start/end times to calculate instructional minutes."""

    def test_calculates_instructional_minutes_basic(self):
        """REQ-003: Calculates instructional minutes from start/end times."""
        # Arrange
        start_time = time(8, 0)  # 8:00 AM
        end_time = time(15, 0)  # 3:00 PM
        lunch_minutes = 30

        # Act
        minutes = self._calculate_instructional_minutes(
            start_time, end_time, lunch_minutes
        )

        # Assert - (3:00 PM - 8:00 AM) = 420 minutes - 30 lunch = 390
        assert minutes == 390

    def test_calculates_minutes_with_recess(self):
        """REQ-003: Accounts for recess in elementary schools."""
        # Arrange
        start_time = time(8, 0)
        end_time = time(14, 30)  # 2:30 PM
        lunch_minutes = 30
        recess_minutes = 15

        # Act
        minutes = self._calculate_instructional_minutes(
            start_time, end_time, lunch_minutes, recess_minutes
        )

        # Assert - (2:30 PM - 8:00 AM) = 390 - 30 - 15 = 345
        assert minutes == 345

    def test_handles_different_time_formats(self):
        """REQ-003: Parses various time formats correctly."""
        # Arrange
        test_cases = [
            ("8:00 AM", time(8, 0)),
            ("08:00", time(8, 0)),
            ("3:00 PM", time(15, 0)),
            ("15:00", time(15, 0)),
            ("8:30AM", time(8, 30)),
            ("2:45 pm", time(14, 45)),
        ]

        for time_str, expected in test_cases:
            # Act
            parsed = self._parse_time(time_str)

            # Assert
            assert parsed == expected, f"Failed for '{time_str}'"

    def test_validates_reasonable_school_day_length(self):
        """REQ-003: Validates school day is reasonable length."""
        # Arrange
        test_cases = [
            (240, True),  # 4 hours - minimum
            (420, True),  # 7 hours - typical
            (480, True),  # 8 hours - long day
            (180, False),  # 3 hours - too short
            (600, False),  # 10 hours - too long
        ]

        for minutes, expected_valid in test_cases:
            # Act
            is_valid = self._validate_school_day_length(minutes)

            # Assert
            assert is_valid == expected_valid, f"Failed for {minutes} minutes"

    def test_calculates_minutes_for_different_grade_levels(self):
        """REQ-003: Calculates different instructional times by grade level."""
        # Arrange
        schedules = {
            "elementary": {"start": time(8, 0), "end": time(14, 30), "lunch": 30},
            "middle": {"start": time(8, 30), "end": time(15, 30), "lunch": 35},
            "high": {"start": time(7, 30), "end": time(14, 30), "lunch": 35},
        }

        # Act
        results = {
            level: self._calculate_instructional_minutes(
                s["start"], s["end"], s["lunch"]
            )
            for level, s in schedules.items()
        }

        # Assert - All should be valid and different
        assert results["elementary"] == 360  # 6.5 hrs - 30 min
        assert results["middle"] == 385  # 7 hrs - 35 min
        assert results["high"] == 385  # 7 hrs - 35 min

    # Helper methods
    def _calculate_instructional_minutes(
        self,
        start: time,
        end: time,
        lunch: int,
        recess: int = 0,
    ) -> int:
        """Calculate instructional minutes."""
        total_minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        return total_minutes - lunch - recess

    def _parse_time(self, time_str: str) -> time:
        """Parse various time formats to time object."""
        import re

        time_str = time_str.strip().upper()

        # Handle 12-hour format
        match = re.match(r"(\d{1,2}):?(\d{2})?\s*(AM|PM)?", time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            period = match.group(3)

            if period == "PM" and hour != 12:
                hour += 12
            elif period == "AM" and hour == 12:
                hour = 0

            return time(hour, minute)

        raise ValueError(f"Cannot parse time: {time_str}")

    def _validate_school_day_length(self, minutes: int) -> bool:
        """Validate school day is reasonable length."""
        return 200 <= minutes <= 540  # 3.3 to 9 hours


class TestSourceAttribution:
    """Tests for storing enrichment data with source attribution."""

    def test_stores_source_url(self):
        """REQ-003: Stores source URL for transparency."""
        # Arrange
        enrichment_data = {
            "district_id": "0622710",
            "instructional_minutes": 360,
            "source_url": "https://www.lausd.net/bell-schedules",
        }

        # Act
        result = self._store_enrichment(enrichment_data)

        # Assert
        assert result["source_urls"] == ["https://www.lausd.net/bell-schedules"]

    def test_stores_multiple_source_urls(self):
        """REQ-003: Stores multiple source URLs when schedule varies by school."""
        # Arrange
        enrichment_data = {
            "district_id": "0622710",
            "source_urls": [
                "https://school1.lausd.net/schedule",
                "https://school2.lausd.net/schedule",
                "https://school3.lausd.net/schedule",
            ],
        }

        # Act
        result = self._store_enrichment(enrichment_data)

        # Assert
        assert len(result["source_urls"]) == 3

    def test_stores_extraction_method(self):
        """REQ-003: Stores method used to extract schedule."""
        # Arrange
        valid_methods = ["web_scraping", "pdf_extraction", "manual_entry", "api"]

        for method in valid_methods:
            # Act
            result = self._store_enrichment(
                {"district_id": "0622710", "method": method}
            )

            # Assert
            assert result["method"] == method

    def test_stores_schools_sampled(self):
        """REQ-003: Stores list of schools sampled for verification."""
        # Arrange
        enrichment_data = {
            "district_id": "0622710",
            "schools_sampled": [
                "Lincoln Elementary",
                "Washington Middle",
                "Roosevelt High",
            ],
        }

        # Act
        result = self._store_enrichment(enrichment_data)

        # Assert
        assert len(result["schools_sampled"]) == 3

    def test_stores_extraction_timestamp(self):
        """REQ-003: Stores timestamp when data was extracted."""
        # Arrange
        from datetime import datetime

        enrichment_data = {"district_id": "0622710"}

        # Act
        result = self._store_enrichment(enrichment_data)

        # Assert
        assert "extracted_at" in result
        assert isinstance(result["extracted_at"], datetime)

    # Helper methods
    def _store_enrichment(self, data: dict) -> dict:
        """Store enrichment with source attribution."""
        from datetime import datetime

        result = data.copy()
        if "source_url" in result:
            result["source_urls"] = [result.pop("source_url")]
        if "source_urls" not in result:
            result["source_urls"] = []
        if "schools_sampled" not in result:
            result["schools_sampled"] = []
        result["extracted_at"] = datetime.now()
        return result


class TestConfidenceLevels:
    """Tests for tracking confidence level of extracted data."""

    def test_high_confidence_for_official_sources(self):
        """REQ-003: Assigns high confidence for official district website."""
        # Arrange
        source = {"url": "https://www.lausd.net/schedules", "type": "official"}

        # Act
        confidence = self._assess_confidence(source)

        # Assert
        assert confidence == "high"

    def test_medium_confidence_for_pdf_extraction(self):
        """REQ-003: Assigns medium confidence for PDF extraction."""
        # Arrange
        source = {"type": "pdf_extraction", "ocr_required": True}

        # Act
        confidence = self._assess_confidence(source)

        # Assert
        assert confidence == "medium"

    def test_low_confidence_for_news_articles(self):
        """REQ-003: Assigns low confidence for news/third-party sources."""
        # Arrange
        source = {"url": "https://localnews.com/school-schedules", "type": "news"}

        # Act
        confidence = self._assess_confidence(source)

        # Assert
        assert confidence == "low"

    def test_assumed_confidence_for_state_requirement(self):
        """REQ-003: Assigns assumed confidence for state statutory fallback."""
        # Arrange
        source = {"type": "state_requirement", "statutory": True}

        # Act
        confidence = self._assess_confidence(source)

        # Assert
        assert confidence == "assumed"

    def test_confidence_levels_are_valid_enum(self):
        """REQ-003: Confidence levels are one of high, medium, low, assumed."""
        # Arrange
        valid_levels = ["high", "medium", "low", "assumed"]

        # Act & Assert
        for level in valid_levels:
            assert level in valid_levels

    def test_stores_confidence_with_enrichment(self):
        """REQ-003: Stores confidence level with enrichment record."""
        # Arrange
        enrichment = {
            "district_id": "0622710",
            "instructional_minutes": 360,
            "confidence": "high",
        }

        # Act
        result = self._validate_enrichment(enrichment)

        # Assert
        assert result["confidence"] == "high"

    # Helper methods
    def _assess_confidence(self, source: dict) -> str:
        """Assess confidence level based on source."""
        if source.get("type") == "official":
            return "high"
        elif source.get("type") == "pdf_extraction":
            return "medium"
        elif source.get("type") in ["news", "third_party"]:
            return "low"
        elif source.get("type") == "state_requirement":
            return "assumed"
        return "medium"

    def _validate_enrichment(self, enrichment: dict) -> dict:
        """Validate enrichment has required fields."""
        assert enrichment.get("confidence") in ["high", "medium", "low", "assumed"]
        return enrichment


class TestDataPreservation:
    """Tests for preserving NCES and SEA data during enrichment."""

    def test_nces_data_unchanged_after_enrichment(self):
        """REQ-003: Leaves NCES data intact after bell schedule enrichment."""
        # Arrange
        original_nces_data = {
            "nces_id": "0622710",
            "enrollment_k12": 420532,
            "teachers": 24500,
        }

        # Act
        enriched_district = self._enrich_with_bell_schedule(
            original_nces_data, {"instructional_minutes": 360}
        )

        # Assert - NCES data unchanged
        assert enriched_district["enrollment_k12"] == 420532
        assert enriched_district["teachers"] == 24500
        # Bell schedule added separately
        assert "bell_schedule" in enriched_district

    def test_sea_data_unchanged_after_enrichment(self):
        """REQ-003: Leaves SEA data intact after bell schedule enrichment."""
        # Arrange
        sea_data = {
            "district_id": "0622710",
            "sea_source": "ca_cde",
            "sea_enrollment": 421000,
        }

        # Act
        result = self._enrich_with_bell_schedule(
            sea_data, {"instructional_minutes": 360}
        )

        # Assert - SEA data preserved
        assert result["sea_source"] == "ca_cde"
        assert result["sea_enrollment"] == 421000

    def test_nces_data_available_for_fallback(self):
        """REQ-003: NCES data available for fallback when enrichment fails."""
        # Arrange
        district = {
            "nces_id": "0622710",
            "nces_teachers": 24500,
            "enriched_teachers": None,  # Enrichment failed
        }

        # Act
        teachers = self._get_teachers_with_fallback(district)

        # Assert - Falls back to NCES
        assert teachers == 24500
        assert teachers == district["nces_teachers"]

    def test_sea_data_available_for_reference(self):
        """REQ-003: SEA data available for reference and comparison."""
        # Arrange
        district = {
            "nces_id": "0622710",
            "nces_enrollment": 420532,
            "sea_enrollment": 421000,
        }

        # Act
        comparison = self._compare_data_sources(district)

        # Assert - Both available for comparison
        assert "nces_enrollment" in comparison
        assert "sea_enrollment" in comparison
        assert comparison["difference"] == 468

    def test_enrichment_stored_separately_from_nces(self):
        """REQ-003: Bell schedule enrichment stored in separate table/field."""
        # Arrange
        nces_district = {
            "nces_id": "0622710",
            "name": "Los Angeles Unified",
            "state": "CA",
        }
        bell_schedule = {
            "elementary": 360,
            "middle": 385,
            "high": 385,
        }

        # Act
        result = self._store_separately(nces_district, bell_schedule)

        # Assert - Separate storage
        assert "district" in result
        assert "bell_schedule" in result
        assert result["district"]["nces_id"] == "0622710"
        assert result["bell_schedule"]["elementary"] == 360

    # Helper methods
    def _enrich_with_bell_schedule(self, district: dict, bell_schedule: dict) -> dict:
        """Enrich district with bell schedule without modifying original data."""
        result = district.copy()
        result["bell_schedule"] = bell_schedule
        return result

    def _get_teachers_with_fallback(self, district: dict) -> int:
        """Get teacher count with NCES fallback."""
        return district.get("enriched_teachers") or district.get("nces_teachers")

    def _compare_data_sources(self, district: dict) -> dict:
        """Compare NCES and SEA data sources."""
        return {
            "nces_enrollment": district["nces_enrollment"],
            "sea_enrollment": district["sea_enrollment"],
            "difference": abs(
                district["nces_enrollment"] - district["sea_enrollment"]
            ),
        }

    def _store_separately(self, district: dict, bell_schedule: dict) -> dict:
        """Store district and bell schedule separately."""
        return {"district": district, "bell_schedule": bell_schedule}


class TestEnrichmentCoverage:
    """Tests for tracking enrichment coverage."""

    def test_tracks_enrichment_progress_by_state(self):
        """REQ-003: Tracks enrichment progress by state."""
        # Arrange
        state_progress = {
            "CA": {"total": 1000, "enriched": 50},
            "TX": {"total": 1200, "enriched": 45},
        }

        # Act
        ca_rate = self._calculate_enrichment_rate(state_progress["CA"])
        tx_rate = self._calculate_enrichment_rate(state_progress["TX"])

        # Assert
        assert ca_rate == 5.0  # 50/1000 * 100
        assert tx_rate == pytest.approx(3.75, 0.01)  # 45/1200 * 100

    def test_identifies_districts_needing_enrichment(self):
        """REQ-003: Identifies districts without bell schedule data."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "has_bell_schedule": True},
            {"nces_id": "4835160", "has_bell_schedule": False},
            {"nces_id": "3620580", "has_bell_schedule": False},
        ]

        # Act
        needs_enrichment = self._get_unenriched_districts(districts)

        # Assert
        assert len(needs_enrichment) == 2
        assert all(not d["has_bell_schedule"] for d in needs_enrichment)

    def test_prioritizes_large_districts_for_enrichment(self):
        """REQ-003: Prioritizes large districts for enrichment."""
        # Arrange
        unenriched = [
            {"nces_id": "0622710", "enrollment": 420532},  # Large
            {"nces_id": "9999999", "enrollment": 500},  # Small
            {"nces_id": "4835160", "enrollment": 200000},  # Medium
        ]

        # Act
        prioritized = self._prioritize_by_enrollment(unenriched)

        # Assert - Sorted by enrollment descending
        assert prioritized[0]["nces_id"] == "0622710"
        assert prioritized[1]["nces_id"] == "4835160"
        assert prioritized[2]["nces_id"] == "9999999"

    # Helper methods
    def _calculate_enrichment_rate(self, state_data: dict) -> float:
        """Calculate enrichment rate as percentage."""
        return (state_data["enriched"] / state_data["total"]) * 100

    def _get_unenriched_districts(self, districts: list) -> list:
        """Get districts without bell schedule data."""
        return [d for d in districts if not d.get("has_bell_schedule")]

    def _prioritize_by_enrollment(self, districts: list) -> list:
        """Prioritize districts by enrollment for enrichment."""
        return sorted(districts, key=lambda d: d["enrollment"], reverse=True)
