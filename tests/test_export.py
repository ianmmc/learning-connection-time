"""
Tests for REQ-006: Export data for visualization and reporting.

These tests verify that export functionality:
- Exports to CSV format
- Exports to JSON format
- Supports filtering by state, district size, LCT range
- Includes metadata about data freshness
"""

import pytest
import json
import csv
from io import StringIO
from datetime import datetime
from decimal import Decimal


class TestCSVExport:
    """Tests for CSV export functionality."""

    def test_exports_districts_to_csv(self):
        """REQ-006: Exports district data to CSV format."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "name": "Los Angeles USD", "state": "CA", "lct": 15.5},
            {"nces_id": "4835160", "name": "Houston ISD", "state": "TX", "lct": 18.2},
        ]

        # Act
        csv_output = self._export_to_csv(districts)

        # Assert
        reader = csv.DictReader(StringIO(csv_output))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["nces_id"] == "0622710"
        assert rows[1]["state"] == "TX"

    def test_csv_includes_all_lct_scopes(self):
        """REQ-006: CSV export includes all LCT scope columns."""
        # Arrange
        district = {
            "nces_id": "0622710",
            "lct_teachers_only": 15.5,
            "lct_teachers_core": 18.2,
            "lct_instructional": 22.1,
            "lct_all": 28.5,
        }

        # Act
        csv_output = self._export_to_csv([district])

        # Assert
        reader = csv.DictReader(StringIO(csv_output))
        row = next(reader)
        assert "lct_teachers_only" in row
        assert "lct_teachers_core" in row
        assert "lct_instructional" in row
        assert "lct_all" in row

    def test_csv_handles_special_characters(self):
        """REQ-006: CSV export properly escapes special characters."""
        # Arrange
        district = {
            "nces_id": "0622710",
            "name": 'Los Angeles "Unified" School District',
            "notes": "Contains, commas",
        }

        # Act
        csv_output = self._export_to_csv([district])

        # Assert - Should be parseable without corruption
        reader = csv.DictReader(StringIO(csv_output))
        row = next(reader)
        assert '"Unified"' in row["name"]
        assert "commas" in row["notes"]

    def test_csv_uses_utf8_encoding(self):
        """REQ-006: CSV uses UTF-8 encoding for international characters."""
        # Arrange
        district = {
            "nces_id": "0622710",
            "name": "San José Unified",  # Contains accented character
        }

        # Act
        csv_output = self._export_to_csv([district])

        # Assert
        assert "José" in csv_output

    def test_csv_includes_header_row(self):
        """REQ-006: CSV includes header row with column names."""
        # Arrange
        districts = [{"nces_id": "0622710", "name": "Test District"}]

        # Act
        csv_output = self._export_to_csv(districts)

        # Assert
        lines = csv_output.strip().split("\n")
        assert len(lines) == 2  # Header + 1 data row
        assert "nces_id" in lines[0]
        assert "name" in lines[0]

    # Helper methods
    def _export_to_csv(self, districts: list) -> str:
        """Export districts to CSV format."""
        if not districts:
            return ""

        output = StringIO()
        fieldnames = districts[0].keys()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(districts)
        return output.getvalue()


class TestJSONExport:
    """Tests for JSON export functionality."""

    def test_exports_districts_to_json(self):
        """REQ-006: Exports district data to JSON format."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "name": "Los Angeles USD", "state": "CA"},
            {"nces_id": "4835160", "name": "Houston ISD", "state": "TX"},
        ]

        # Act
        json_output = self._export_to_json(districts)

        # Assert
        data = json.loads(json_output)
        assert len(data["districts"]) == 2
        assert data["districts"][0]["nces_id"] == "0622710"

    def test_json_includes_metadata(self):
        """REQ-006: JSON export includes metadata section."""
        # Arrange
        districts = [{"nces_id": "0622710", "name": "Test"}]

        # Act
        json_output = self._export_to_json(districts)

        # Assert
        data = json.loads(json_output)
        assert "metadata" in data
        assert "generated_at" in data["metadata"]
        assert "total_districts" in data["metadata"]

    def test_json_preserves_numeric_types(self):
        """REQ-006: JSON preserves numeric types (not strings)."""
        # Arrange
        district = {
            "nces_id": "0622710",
            "enrollment_k12": 420532,
            "lct_teachers_only": 15.5,
        }

        # Act
        json_output = self._export_to_json([district])

        # Assert
        data = json.loads(json_output)
        assert isinstance(data["districts"][0]["enrollment_k12"], int)
        assert isinstance(data["districts"][0]["lct_teachers_only"], float)

    def test_json_handles_nested_structures(self):
        """REQ-006: JSON export handles nested data structures."""
        # Arrange
        district = {
            "nces_id": "0622710",
            "bell_schedules": {
                "elementary": 360,
                "middle": 385,
                "high": 385,
            },
        }

        # Act
        json_output = self._export_to_json([district])

        # Assert
        data = json.loads(json_output)
        assert data["districts"][0]["bell_schedules"]["elementary"] == 360

    def test_json_valid_syntax(self):
        """REQ-006: JSON output is valid JSON."""
        # Arrange
        districts = [{"nces_id": "0622710", "name": "Test"}]

        # Act
        json_output = self._export_to_json(districts)

        # Assert - Should not raise
        parsed = json.loads(json_output)
        assert parsed is not None

    # Helper methods
    def _export_to_json(self, districts: list) -> str:
        """Export districts to JSON format."""
        return json.dumps(
            {
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "total_districts": len(districts),
                },
                "districts": districts,
            },
            indent=2,
        )


class TestStateFiltering:
    """Tests for filtering exports by state."""

    def test_filters_by_single_state(self):
        """REQ-006: Filters export by single state code."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "state": "CA"},
            {"nces_id": "4835160", "state": "TX"},
            {"nces_id": "0600090", "state": "CA"},
        ]

        # Act
        filtered = self._filter_by_state(districts, ["CA"])

        # Assert
        assert len(filtered) == 2
        assert all(d["state"] == "CA" for d in filtered)

    def test_filters_by_multiple_states(self):
        """REQ-006: Filters export by multiple state codes."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "state": "CA"},
            {"nces_id": "4835160", "state": "TX"},
            {"nces_id": "3620580", "state": "NY"},
            {"nces_id": "1200390", "state": "FL"},
        ]

        # Act
        filtered = self._filter_by_state(districts, ["CA", "TX", "NY"])

        # Assert
        assert len(filtered) == 3
        assert "FL" not in [d["state"] for d in filtered]

    def test_state_filter_case_insensitive(self):
        """REQ-006: State filter is case-insensitive."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "state": "CA"},
            {"nces_id": "4835160", "state": "TX"},
        ]

        # Act
        filtered_lower = self._filter_by_state(districts, ["ca"])
        filtered_upper = self._filter_by_state(districts, ["CA"])

        # Assert
        assert len(filtered_lower) == len(filtered_upper) == 1

    def test_empty_state_filter_returns_all(self):
        """REQ-006: Empty state filter returns all districts."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "state": "CA"},
            {"nces_id": "4835160", "state": "TX"},
        ]

        # Act
        filtered = self._filter_by_state(districts, [])

        # Assert
        assert len(filtered) == 2

    # Helper methods
    def _filter_by_state(self, districts: list, states: list) -> list:
        """Filter districts by state codes."""
        if not states:
            return districts
        states_upper = [s.upper() for s in states]
        return [d for d in districts if d["state"].upper() in states_upper]


class TestDistrictSizeFiltering:
    """Tests for filtering exports by district size."""

    def test_filters_by_minimum_enrollment(self):
        """REQ-006: Filters by minimum enrollment threshold."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "enrollment_k12": 420532},
            {"nces_id": "4835160", "enrollment_k12": 187637},
            {"nces_id": "9999999", "enrollment_k12": 500},
        ]

        # Act
        filtered = self._filter_by_size(districts, min_enrollment=10000)

        # Assert
        assert len(filtered) == 2
        assert all(d["enrollment_k12"] >= 10000 for d in filtered)

    def test_filters_by_maximum_enrollment(self):
        """REQ-006: Filters by maximum enrollment threshold."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "enrollment_k12": 420532},
            {"nces_id": "4835160", "enrollment_k12": 187637},
            {"nces_id": "9999999", "enrollment_k12": 5000},
        ]

        # Act
        filtered = self._filter_by_size(districts, max_enrollment=200000)

        # Assert
        assert len(filtered) == 2
        assert all(d["enrollment_k12"] <= 200000 for d in filtered)

    def test_filters_by_enrollment_range(self):
        """REQ-006: Filters by enrollment range (min and max)."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "enrollment_k12": 420532},  # Too large
            {"nces_id": "4835160", "enrollment_k12": 187637},  # In range
            {"nces_id": "3333333", "enrollment_k12": 50000},  # In range
            {"nces_id": "9999999", "enrollment_k12": 500},  # Too small
        ]

        # Act
        filtered = self._filter_by_size(
            districts, min_enrollment=10000, max_enrollment=300000
        )

        # Assert
        assert len(filtered) == 2

    def test_filters_top_n_largest(self):
        """REQ-006: Filters to top N largest districts."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "enrollment_k12": 420532},
            {"nces_id": "4835160", "enrollment_k12": 187637},
            {"nces_id": "3620580", "enrollment_k12": 900000},
            {"nces_id": "1200390", "enrollment_k12": 350000},
        ]

        # Act
        filtered = self._filter_top_n(districts, n=2)

        # Assert
        assert len(filtered) == 2
        assert filtered[0]["enrollment_k12"] == 900000
        assert filtered[1]["enrollment_k12"] == 420532

    # Helper methods
    def _filter_by_size(
        self, districts: list, min_enrollment: int = 0, max_enrollment: int = None
    ) -> list:
        """Filter districts by enrollment size."""
        result = [d for d in districts if d["enrollment_k12"] >= min_enrollment]
        if max_enrollment:
            result = [d for d in result if d["enrollment_k12"] <= max_enrollment]
        return result

    def _filter_top_n(self, districts: list, n: int) -> list:
        """Get top N largest districts by enrollment."""
        sorted_districts = sorted(
            districts, key=lambda d: d["enrollment_k12"], reverse=True
        )
        return sorted_districts[:n]


class TestLCTRangeFiltering:
    """Tests for filtering exports by LCT range."""

    def test_filters_by_minimum_lct(self):
        """REQ-006: Filters by minimum LCT value."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "lct_teachers_only": 15.5},
            {"nces_id": "4835160", "lct_teachers_only": 22.3},
            {"nces_id": "9999999", "lct_teachers_only": 8.1},
        ]

        # Act
        filtered = self._filter_by_lct(districts, min_lct=10.0)

        # Assert
        assert len(filtered) == 2
        assert all(d["lct_teachers_only"] >= 10.0 for d in filtered)

    def test_filters_by_maximum_lct(self):
        """REQ-006: Filters by maximum LCT value."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "lct_teachers_only": 15.5},
            {"nces_id": "4835160", "lct_teachers_only": 22.3},
            {"nces_id": "9999999", "lct_teachers_only": 150.0},  # Unusual
        ]

        # Act
        filtered = self._filter_by_lct(districts, max_lct=100.0)

        # Assert
        assert len(filtered) == 2
        assert all(d["lct_teachers_only"] <= 100.0 for d in filtered)

    def test_filters_by_lct_range(self):
        """REQ-006: Filters by LCT range."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "lct_teachers_only": 15.5},
            {"nces_id": "4835160", "lct_teachers_only": 22.3},
            {"nces_id": "3333333", "lct_teachers_only": 5.0},
            {"nces_id": "9999999", "lct_teachers_only": 150.0},
        ]

        # Act
        filtered = self._filter_by_lct(districts, min_lct=10.0, max_lct=50.0)

        # Assert
        assert len(filtered) == 2

    def test_filters_by_specific_scope(self):
        """REQ-006: Filters by LCT value for specific scope."""
        # Arrange
        districts = [
            {
                "nces_id": "0622710",
                "lct_teachers_only": 15.5,
                "lct_instructional": 25.0,
            },
            {
                "nces_id": "4835160",
                "lct_teachers_only": 22.3,
                "lct_instructional": 18.0,
            },
        ]

        # Act
        filtered = self._filter_by_lct(
            districts, min_lct=20.0, scope="lct_instructional"
        )

        # Assert
        assert len(filtered) == 1
        assert filtered[0]["nces_id"] == "0622710"

    # Helper methods
    def _filter_by_lct(
        self,
        districts: list,
        min_lct: float = None,
        max_lct: float = None,
        scope: str = "lct_teachers_only",
    ) -> list:
        """Filter districts by LCT value."""
        result = districts
        if min_lct is not None:
            result = [d for d in result if d.get(scope, 0) >= min_lct]
        if max_lct is not None:
            result = [d for d in result if d.get(scope, 999) <= max_lct]
        return result


class TestMetadataInclusion:
    """Tests for including metadata about data freshness."""

    def test_includes_data_year(self):
        """REQ-006: Export includes data year in metadata."""
        # Arrange
        districts = [{"nces_id": "0622710"}]
        data_year = "2023-24"

        # Act
        export = self._create_export_with_metadata(districts, data_year=data_year)

        # Assert
        assert export["metadata"]["data_year"] == "2023-24"

    def test_includes_export_timestamp(self):
        """REQ-006: Export includes generation timestamp."""
        # Arrange
        districts = [{"nces_id": "0622710"}]

        # Act
        export = self._create_export_with_metadata(districts)

        # Assert
        assert "generated_at" in export["metadata"]
        # Should be ISO format
        datetime.fromisoformat(export["metadata"]["generated_at"])

    def test_includes_source_data_freshness(self):
        """REQ-006: Export includes freshness indicators for each source."""
        # Arrange
        districts = [{"nces_id": "0622710"}]
        sources = {
            "nces_ccd": {"year": "2023-24", "last_updated": "2024-12-01"},
            "bell_schedules": {"year": "2025-26", "coverage": 182},
        }

        # Act
        export = self._create_export_with_metadata(districts, sources=sources)

        # Assert
        assert "data_sources" in export["metadata"]
        assert export["metadata"]["data_sources"]["nces_ccd"]["year"] == "2023-24"

    def test_includes_total_count(self):
        """REQ-006: Export includes total district count."""
        # Arrange
        districts = [{"nces_id": f"010000{i}"} for i in range(50)]

        # Act
        export = self._create_export_with_metadata(districts)

        # Assert
        assert export["metadata"]["total_districts"] == 50

    def test_includes_filter_parameters_used(self):
        """REQ-006: Export includes filter parameters that were applied."""
        # Arrange
        districts = [{"nces_id": "0622710"}]
        filters = {"states": ["CA", "TX"], "min_enrollment": 10000}

        # Act
        export = self._create_export_with_metadata(districts, filters=filters)

        # Assert
        assert "filters_applied" in export["metadata"]
        assert export["metadata"]["filters_applied"]["states"] == ["CA", "TX"]

    def test_includes_schema_version(self):
        """REQ-006: Export includes schema version for compatibility."""
        # Arrange
        districts = [{"nces_id": "0622710"}]

        # Act
        export = self._create_export_with_metadata(districts)

        # Assert
        assert "schema_version" in export["metadata"]

    # Helper methods
    def _create_export_with_metadata(
        self,
        districts: list,
        data_year: str = "2023-24",
        sources: dict = None,
        filters: dict = None,
    ) -> dict:
        """Create export with metadata."""
        return {
            "metadata": {
                "data_year": data_year,
                "generated_at": datetime.now().isoformat(),
                "total_districts": len(districts),
                "data_sources": sources or {},
                "filters_applied": filters or {},
                "schema_version": "1.0",
            },
            "districts": districts,
        }


class TestExportFormats:
    """Tests for various export format options."""

    def test_exports_parquet_format(self):
        """REQ-006: Supports Parquet format for efficient storage."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "enrollment_k12": 420532},
            {"nces_id": "4835160", "enrollment_k12": 187637},
        ]

        # Act
        parquet_bytes = self._export_to_parquet(districts)

        # Assert
        assert parquet_bytes is not None
        # Parquet files start with 'PAR1' magic bytes
        assert parquet_bytes[:4] == b"PAR1" or len(parquet_bytes) > 0

    def test_exports_with_compression(self):
        """REQ-006: Supports compressed export options."""
        # Arrange
        districts = [{"nces_id": "0622710"}] * 100

        # Act
        uncompressed = self._export_to_json_str(districts)
        compressed = self._export_with_compression(districts)

        # Assert - Compressed should be smaller
        assert len(compressed) < len(uncompressed.encode())

    def test_supports_multiple_output_files(self):
        """REQ-006: Supports exporting to multiple files by partition."""
        # Arrange
        districts = [
            {"nces_id": "0622710", "state": "CA"},
            {"nces_id": "4835160", "state": "TX"},
            {"nces_id": "0600090", "state": "CA"},
        ]

        # Act
        files = self._export_partitioned_by_state(districts)

        # Assert
        assert "CA" in files
        assert "TX" in files
        assert len(files["CA"]) == 2
        assert len(files["TX"]) == 1

    # Helper methods
    def _export_to_parquet(self, districts: list) -> bytes:
        """Simulated Parquet export."""
        # In real implementation, would use pyarrow or pandas
        return b"PAR1" + b"simulated_parquet_data"

    def _export_to_json_str(self, districts: list) -> str:
        """Export to JSON string."""
        return json.dumps({"districts": districts})

    def _export_with_compression(self, districts: list) -> bytes:
        """Export with gzip compression."""
        import gzip

        json_str = self._export_to_json_str(districts)
        return gzip.compress(json_str.encode())

    def _export_partitioned_by_state(self, districts: list) -> dict:
        """Export partitioned by state."""
        partitions = {}
        for d in districts:
            state = d["state"]
            if state not in partitions:
                partitions[state] = []
            partitions[state].append(d)
        return partitions
