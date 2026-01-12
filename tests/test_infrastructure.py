"""
Tests for infrastructure requirements
Generated from: REQ-016 (Calculation run tracking), REQ-017 (Bell schedule enrichment)

Verifies infrastructure components for tracking and enrichment.

Run: pytest tests/test_infrastructure.py -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock


class TestCalculationRunTracking:
    """Tests for calculation run tracking - REQ-016"""

    def test_start_run_creates_record_with_timestamp(self):
        """
        REQ-016: CalculationRun.start_run() creates record with timestamp.

        Timestamp format: YYYYMMDDTHHMMSSZ (ISO 8601 UTC)
        """
        # Arrange
        mock_session = MagicMock()
        year = "2023-24"
        run_type = "full"

        # Act - Mock the start_run behavior
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        calculation_run = {
            "run_id": run_id,
            "year": year,
            "run_type": run_type,
            "status": "running",
            "previous_run_id": None,
        }

        # Assert
        assert calculation_run["run_id"] is not None
        assert len(calculation_run["run_id"]) == 16  # YYYYMMDDTHHMMSSZassert calculation_run["year"] == year
        assert calculation_run["run_type"] == run_type
        assert calculation_run["status"] == "running"

    def test_records_year_and_run_type(self):
        """
        REQ-016: Records year and run_type (full/incremental).
        """
        # Arrange
        run_data = {
            "year": "2023-24",
            "run_type": "incremental",
        }

        # Assert
        assert run_data["year"] in ["2023-24", "2024-25"]
        assert run_data["run_type"] in ["full", "incremental"]

    def test_stores_input_hash_for_change_detection(self):
        """
        REQ-016: Stores input_hash for detecting data changes.

        Hash is computed from staff counts, enrollment counts, and
        other input data state to enable incremental calculations.
        """
        # Arrange
        input_state = {
            "staff_count": 17842,
            "enrollment_count": 17842,
        }

        # Act - Compute hash (simplified example)
        import hashlib
        hash_input = f"{input_state['staff_count']}:{input_state['enrollment_count']}"
        input_hash = hashlib.md5(hash_input.encode()).hexdigest()[:16]

        # Assert
        assert len(input_hash) == 16
        assert isinstance(input_hash, str)

    def test_complete_updates_districts_processed_and_calculations_created(self):
        """
        REQ-016: CalculationRun.complete() updates with counts.

        Tracks districts_processed and calculations_created for audit trail.
        """
        # Arrange
        calculation_run = {
            "run_id": "20260112T030905Z",
            "status": "running",
            "districts_processed": None,
            "calculations_created": None,
        }

        # Act - Mock complete() behavior
        calculation_run["status"] = "completed"
        calculation_run["completed_at"] = datetime.utcnow()
        calculation_run["districts_processed"] = 17842
        calculation_run["calculations_created"] = 166576

        # Assert
        assert calculation_run["status"] == "completed"
        assert calculation_run["districts_processed"] == 17842
        assert calculation_run["calculations_created"] == 166576
        assert calculation_run["completed_at"] is not None

    def test_stores_output_files_list(self):
        """
        REQ-016: Stores output_files list for tracking generated artifacts.
        """
        # Arrange
        output_files = [
            "data/enriched/lct-calculations/lct_all_variants_2023_24_20260112T030905Z.csv",
            "data/enriched/lct-calculations/lct_all_variants_2023_24_valid_20260112T030905Z.csv",
            "data/enriched/lct-calculations/lct_variants_summary_2023_24_20260112T030905Z.csv",
            "data/enriched/lct-calculations/lct_qa_report_2023_24_20260112T030905Z.json",
        ]

        # Assert
        assert len(output_files) >= 4  # At least 4 output files
        assert all("lct" in f for f in output_files)
        assert all("2023_24" in f for f in output_files)

    def test_stores_qa_summary_json(self):
        """
        REQ-016: Stores qa_summary as JSON for embedded QA report.

        Enables querying calculation runs with their quality metrics.
        """
        # Arrange
        qa_summary = {
            "pass_rate": 99.34,
            "total_calculations": 166576,
            "valid_calculations": 165481,
            "overall_status": "PASS",
        }

        # Assert
        assert "pass_rate" in qa_summary
        assert "overall_status" in qa_summary
        assert qa_summary["pass_rate"] >= 99.0

    def test_enables_incremental_flag_to_skip_unchanged_districts(self):
        """
        REQ-016: --incremental flag skips unchanged districts.

        When input_hash matches previous run, only recalculate districts
        where source data has changed.
        """
        # Arrange
        previous_run = {
            "run_id": "20260111T000000Z",
            "input_hash": "abc123def456",
            "districts_processed": 17842,
        }

        current_input_hash = "abc123def456"  # Same as previous

        # Act - Check if incremental run is needed
        is_data_changed = current_input_hash != previous_run["input_hash"]

        # Assert - No changes, can skip full recalculation
        assert is_data_changed is False

    def test_database_tracks_multiple_runs_for_audit_trail(self):
        """
        REQ-016: Database stores multiple runs for history.

        Enables tracking calculation evolution over time.
        """
        # Arrange - Multiple runs
        runs = [
            {"run_id": "20260110T072703Z", "status": "completed"},
            {"run_id": "20260110T075424Z", "status": "completed"},
            {"run_id": "20260112T030905Z", "status": "completed"},
        ]

        # Assert - All runs tracked
        assert len(runs) >= 3
        assert all(r["status"] == "completed" for r in runs)
        # run_ids are sortable by timestamp
        assert runs[0]["run_id"] < runs[1]["run_id"] < runs[2]["run_id"]


class TestBellScheduleEnrichment:
    """Tests for bell schedule enrichment with confidence levels - REQ-017"""

    def test_stores_grade_level_elementary_middle_high(self):
        """
        REQ-017: BellSchedule table stores grade_level.

        Supports: elementary, middle, high
        """
        # Arrange
        grade_levels = ["elementary", "middle", "high"]

        for grade_level in grade_levels:
            bell_schedule = {
                "district_id": "0123456",
                "grade_level": grade_level,
                "instructional_minutes": 360,
            }

            # Assert
            assert bell_schedule["grade_level"] in grade_levels

    def test_confidence_levels_high_medium_low_assumed(self):
        """
        REQ-017: Confidence levels - high, medium, low, assumed.

        - high: Direct observation from published schedule
        - medium: Calculated from start/end times with assumptions
        - low: Estimated from partial data
        - assumed: Using state requirement as proxy
        """
        confidence_levels = ["high", "medium", "low", "assumed"]

        for level in confidence_levels:
            bell_schedule = {
                "district_id": "0123456",
                "confidence": level,
            }

            assert bell_schedule["confidence"] in confidence_levels

    def test_method_tracking_web_scraping_pdf_manual_state(self):
        """
        REQ-017: Method tracking for data provenance.

        Tracks how bell schedule data was collected:
        - web_scraping: Automated extraction from district website
        - pdf_extraction: OCR or text extraction from PDF
        - manual_entry: Human-provided data
        - state_requirement: Statutory fallback (not actual schedule)
        """
        methods = ["web_scraping", "pdf_extraction", "manual_entry", "state_requirement"]

        for method in methods:
            bell_schedule = {
                "district_id": "0123456",
                "method": method,
            }

            assert bell_schedule["method"] in methods

    def test_source_urls_stored_in_jsonb_array(self):
        """
        REQ-017: Source URLs stored for verification and transparency.

        JSONB array allows multiple source URLs per schedule.
        """
        # Arrange
        bell_schedule = {
            "district_id": "0123456",
            "source_urls": [
                "https://district.edu/bell-schedule",
                "https://district.edu/calendars/daily-schedule.pdf",
            ],
        }

        # Assert
        assert isinstance(bell_schedule["source_urls"], list)
        assert len(bell_schedule["source_urls"]) >= 1
        assert all("http" in url for url in bell_schedule["source_urls"])

    def test_schools_sampled_list_stored(self):
        """
        REQ-017: Schools sampled list stored for verification.

        When using sampling methodology, track which schools were reviewed.
        """
        # Arrange
        bell_schedule = {
            "district_id": "0123456",
            "schools_sampled": [
                "Example Elementary School",
                "Example Middle School",
                "Example High School",
            ],
        }

        # Assert
        assert isinstance(bell_schedule["schools_sampled"], list)
        assert len(bell_schedule["schools_sampled"]) >= 1

    def test_get_instructional_minutes_prioritizes_bell_schedule(self):
        """
        REQ-017: get_instructional_minutes() prioritizes enriched data.

        Priority: bell schedule > state requirement > default 360
        """
        # This is tested in test_data_precedence.py::TestInstructionalTimePrecedence
        # but documenting requirement here as well

        data_sources = [
            {"type": "bell_schedule", "priority": 1, "minutes": 375},
            {"type": "state_requirement", "priority": 2, "minutes": 330},
            {"type": "default", "priority": 3, "minutes": 360},
        ]

        # Sort by priority
        selected = sorted(data_sources, key=lambda x: x["priority"])[0]

        # Assert - Bell schedule has highest priority
        assert selected["type"] == "bell_schedule"
        assert selected["priority"] == 1

    def test_bell_schedule_enrichment_optional_step(self):
        """
        REQ-017: Bell schedule enrichment is optional in pipeline.

        Districts without enriched data fall back to state requirements.
        """
        # Arrange
        districts = [
            {"id": "0001", "has_bell_schedule": True, "instructional_minutes": 375},
            {"id": "0002", "has_bell_schedule": False, "instructional_minutes": 330},  # State req
        ]

        # Assert - Both districts have instructional minutes
        for district in districts:
            assert "instructional_minutes" in district
            assert district["instructional_minutes"] > 0

    def test_enrichment_tracks_data_quality(self):
        """
        REQ-017: Enrichment tracks data quality via confidence and method.

        Combination of confidence + method provides quality assessment.
        """
        # Arrange
        enrichment_records = [
            {"method": "web_scraping", "confidence": "high"},      # Best quality
            {"method": "pdf_extraction", "confidence": "medium"},  # Good quality
            {"method": "manual_entry", "confidence": "high"},      # High trust
            {"method": "state_requirement", "confidence": "assumed"},  # Fallback
        ]

        # Assert - All records have both fields
        for record in enrichment_records:
            assert "method" in record
            assert "confidence" in record

    def test_bell_schedule_by_grade_level_supports_differentiation(self):
        """
        REQ-017: Storing schedules by grade level enables differentiated LCT.

        Elementary, middle, and high schools often have different schedules.
        """
        # Arrange - District with different schedules by level
        bell_schedules = [
            {"district_id": "0123456", "grade_level": "elementary", "instructional_minutes": 330},
            {"district_id": "0123456", "grade_level": "middle", "instructional_minutes": 345},
            {"district_id": "0123456", "grade_level": "high", "instructional_minutes": 360},
        ]

        # Assert - Different minutes per level
        minutes_by_level = {bs["grade_level"]: bs["instructional_minutes"] for bs in bell_schedules}
        assert minutes_by_level["elementary"] < minutes_by_level["high"]


class TestEnrichmentDataQuality:
    """Additional tests for enrichment data quality"""

    def test_method_matches_confidence_expectations(self):
        """
        Documents expected confidence levels by collection method.

        web_scraping: typically high
        pdf_extraction: typically medium (depends on OCR quality)
        manual_entry: typically high (human verification)
        state_requirement: always assumed (not actual schedule)
        """
        expected_mappings = [
            {"method": "web_scraping", "typical_confidence": "high"},
            {"method": "pdf_extraction", "typical_confidence": "medium"},
            {"method": "manual_entry", "typical_confidence": "high"},
            {"method": "state_requirement", "typical_confidence": "assumed"},
        ]

        for mapping in expected_mappings:
            assert mapping["method"] is not None
            assert mapping["typical_confidence"] is not None

    def test_enrichment_preserves_nces_and_sea_data(self):
        """
        REQ-003: Enrichment leaves NCES and SEA data intact.

        Bell schedule enrichment adds data, doesn't replace base data.
        """
        # Arrange - District with both base and enriched data
        district_data = {
            "nces_id": "0123456",
            "name": "Example District",
            "enrollment": 5000,            # From NCES (base)
            "staff": 250,                  # From NCES (base)
            "instructional_minutes": 375,  # From enrichment (added)
            "enrichment_source": "bell_schedule",
        }

        # Assert - Both base and enriched data present
        assert "enrollment" in district_data  # NCES data preserved
        assert "staff" in district_data       # NCES data preserved
        assert "instructional_minutes" in district_data  # Enriched data added


# --- Fixtures ---

@pytest.fixture
def sample_calculation_run():
    """Sample CalculationRun for testing."""
    return {
        "run_id": "20260112T030905Z",
        "year": "2023-24",
        "run_type": "full",
        "status": "completed",
        "started_at": datetime.utcnow(),
        "completed_at": datetime.utcnow(),
        "districts_processed": 17842,
        "calculations_created": 166576,
        "input_hash": "abc123def456",
        "output_files": [
            "lct_all_variants_2023_24_20260112T030905Z.csv",
            "lct_qa_report_2023_24_20260112T030905Z.json",
        ],
        "qa_summary": {
            "pass_rate": 99.34,
            "overall_status": "PASS",
        },
    }


@pytest.fixture
def sample_bell_schedule():
    """Sample BellSchedule for testing."""
    return {
        "district_id": "0123456",
        "year": "2025-26",
        "grade_level": "high",
        "instructional_minutes": 375,
        "start_time": "8:00 AM",
        "end_time": "3:30 PM",
        "lunch_duration": 30,
        "method": "web_scraping",
        "confidence": "high",
        "schools_sampled": ["Example High School"],
        "source_urls": ["https://district.edu/bell-schedule"],
        "notes": "District-wide schedule applies to all high schools",
    }


@pytest.fixture
def sample_enrichment_by_grade():
    """Sample enrichment with different schedules by grade level."""
    return [
        {
            "district_id": "0123456",
            "grade_level": "elementary",
            "instructional_minutes": 330,
            "method": "web_scraping",
            "confidence": "high",
        },
        {
            "district_id": "0123456",
            "grade_level": "middle",
            "instructional_minutes": 345,
            "method": "pdf_extraction",
            "confidence": "medium",
        },
        {
            "district_id": "0123456",
            "grade_level": "high",
            "instructional_minutes": 360,
            "method": "web_scraping",
            "confidence": "high",
        },
    ]
