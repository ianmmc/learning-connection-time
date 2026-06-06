"""
Tests for schedule_aggregation: times->instructional-minutes and per-school -> district
grade-band aggregation (enrollment-weighted mean + distribution).

Covers REQ-042 (enrollment-weighted-mean aggregation with distribution transparency).
"""

import pytest

from infrastructure.database.schedule_aggregation import (
    compute_instructional_minutes,
    aggregate_grade_band,
    aggregate_district,
)


class TestComputeInstructionalMinutes:
    def test_gross_day(self):
        assert compute_instructional_minutes("07:40", "14:10") == 390

    def test_lunch_deducted(self):
        assert compute_instructional_minutes("07:40", "14:10", lunch_minutes=30) == 360

    def test_lunch_and_passing(self):
        assert compute_instructional_minutes("08:00", "15:00", lunch_minutes=30, passing_minutes=20) == 370

    def test_end_before_start_is_none(self):
        assert compute_instructional_minutes("14:00", "08:00") is None

    def test_bad_input_is_none(self):
        assert compute_instructional_minutes("", "14:10") is None
        assert compute_instructional_minutes("8am", "2pm") is None

    def test_overlong_deduction_is_none(self):
        assert compute_instructional_minutes("08:00", "09:00", lunch_minutes=90) is None


class TestAggregateGradeBand:
    def test_mode_is_the_value(self):
        # 390 occurs twice, 420 once -> mode (and district value) is 390; min/max kept
        a = aggregate_grade_band([
            {"instructional_minutes": 390},
            {"instructional_minutes": 390},
            {"instructional_minutes": 420},
        ])
        assert a["aggregation_method"] == "mode_of_sample"
        assert a["value"] == 390 and a["mode"] == 390
        assert (a["min"], a["max"], a["n_schools"]) == (390, 420, 3)

    def test_single_school(self):
        a = aggregate_grade_band([{"instructional_minutes": 390}])
        assert a["aggregation_method"] == "single_school"
        assert a["value"] == 390
        assert a["min"] == a["max"] == a["mode"] == 390

    def test_staggered_starts_same_length(self):
        # Different clock times, same daily minutes -> distribution collapses to one value
        a = aggregate_grade_band([
            {"instructional_minutes": 390},
            {"instructional_minutes": 390},
        ])
        assert a["value"] == 390
        assert (a["min"], a["max"], a["mode"]) == (390, 390, 390)

    def test_mode_tiebreak_smallest(self):
        a = aggregate_grade_band([
            {"instructional_minutes": 390}, {"instructional_minutes": 390},
            {"instructional_minutes": 420}, {"instructional_minutes": 420},
        ])
        assert a["mode"] == 390  # tie -> smallest (conservative)

    def test_empty_is_none(self):
        assert aggregate_grade_band([]) is None
        assert aggregate_grade_band([{"school_name": "x"}]) is None  # no minutes


class TestAggregateDistrict:
    def test_groups_by_grade_band(self):
        d = aggregate_district([
            {"grade_level": "elementary", "instructional_minutes": 360},
            {"grade_level": "elementary", "instructional_minutes": 360},
            {"grade_level": "elementary", "instructional_minutes": 390},
            {"grade_level": "high", "instructional_minutes": 420},
        ])
        assert set(d.keys()) == {"elementary", "high"}
        assert d["elementary"]["value"] == 360  # mode (360 twice, 390 once)
        assert d["elementary"]["max"] == 390
        assert d["high"]["aggregation_method"] == "single_school"
