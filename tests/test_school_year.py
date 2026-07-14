"""The school_year constants module (issue #24/#72) — the single source of year + plausibility
truth. Window semantics per Ian's 2026-07-01 decision: 3 consecutive school years (span <= 2),
COVID exclusion first, SPED 2017-18 baseline exempt."""
import pytest

from infrastructure.database import school_year as SY


class TestStartYearAndSpan:
    def test_start_year(self):
        assert SY.start_year("2025-26") == 2025
        assert SY.start_year("1999-00") == 1999

    def test_start_year_rejects_malformed(self):
        for bad in ("2025", "25-26", "2025-2026", "", None, "2025-27"):
            with pytest.raises(ValueError):
                SY.start_year(bad)

    def test_year_span(self):
        assert SY.year_span("2023-24", "2025-26") == 2
        assert SY.year_span("2025-26", "2023-24") == 2
        assert SY.year_span("2024-25", "2024-25") == 0


class TestCovidRule:
    def test_covid_years_excluded(self):
        for y in ("2019-20", "2020-21", "2021-22", "2022-23"):
            assert SY.is_covid_year(y)
            assert not SY.is_acceptable_data_year(y)

    def test_post_covid_and_pre_covid_fallback_acceptable(self):
        for y in ("2023-24", "2024-25", "2025-26", "2018-19"):
            assert SY.is_acceptable_data_year(y)

    def test_malformed_year_not_acceptable(self):
        assert not SY.is_acceptable_data_year("unknown")
        assert not SY.is_acceptable_data_year(None)


class TestBlendWindow:
    def test_three_consecutive_years_ok(self):
        # Ian's acceptable case: 2023-24 + 2024-25 + 2025-26
        assert SY.within_blend_window(["2023-24", "2024-25", "2025-26"])

    def test_four_year_span_rejected(self):
        # The case the old span<=3 SQL wrongly admitted
        assert not SY.within_blend_window(["2023-24", "2026-27"])

    def test_gap_beyond_window_rejected(self):
        # Ian's unacceptable case (COVID aside, the span alone is 3)
        assert not SY.within_blend_window(["2023-24", "2025-26", "2026-27", "2023-24"])
        assert not SY.within_blend_window(["2023-24", "2026-27", "2025-26"])

    def test_covid_year_fails_the_window_outright(self):
        assert not SY.within_blend_window(["2022-23", "2023-24", "2024-25"])

    def test_sped_baseline_exempt(self):
        # 2017-18 rides along without breaking the window (REQ-026 exemption)
        assert SY.within_blend_window(["2017-18", "2024-25", "2025-26"])

    def test_empty_and_none_years_ok(self):
        assert SY.within_blend_window([])
        assert SY.within_blend_window([None, "2025-26"])


class TestPlausibility:
    def test_req055_band(self):
        assert SY.plausible_gross_minutes(240)
        assert SY.plausible_gross_minutes(510)
        assert SY.plausible_gross_minutes(360.0)
        assert not SY.plausible_gross_minutes(239)
        assert not SY.plausible_gross_minutes(511)
        assert not SY.plausible_gross_minutes(None)
        assert not SY.plausible_gross_minutes("n/a")

    def test_db_check_is_the_outer_bound(self):
        assert SY.DB_CHECK_MINUTES_MIN < SY.GROSS_MINUTES_MIN
        assert SY.DB_CHECK_MINUTES_MAX > SY.GROSS_MINUTES_MAX


class TestConstants:
    def test_current_year_is_well_formed_and_post_covid(self):
        assert SY.is_acceptable_data_year(SY.CURRENT_SCHOOL_YEAR)
        assert SY.CURRENT_SCHOOL_YEAR in SY.ACCEPTABLE_BELL_YEARS

    def test_acceptable_bell_years_newest_first_and_post_covid(self):
        starts = [SY.start_year(y) for y in SY.ACCEPTABLE_BELL_YEARS]
        assert starts == sorted(starts, reverse=True)
        assert all(SY.is_acceptable_data_year(y) for y in SY.ACCEPTABLE_BELL_YEARS)
