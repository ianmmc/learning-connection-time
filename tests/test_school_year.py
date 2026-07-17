"""The school_year constants module (issue #24/#72) — the single source of year + plausibility
truth. Window semantics per Ian's 2026-07-01 decision: 3 consecutive school years (span <= 2),
COVID exclusion first, SPED 2017-18 baseline exempt."""
import pytest

from infrastructure.database import school_year as SY


class TestContentSchoolYear:
    """The deterministic URL/filename year read feeding the Stage-5 `content_school_year` signal
    (#107/#241, STAGE5_FILTER_DESIGN §3a obs. 6). Never infers from today's date (REQ-054)."""

    def test_four_digit_full_pair(self):
        assert SY.content_school_year("https://x.org/Bell-Schedule-2018-2019.pdf") == "2018-19"

    def test_four_digit_short_pair(self):
        assert SY.content_school_year("https://x.org/files/bell-2025-26.pdf") == "2025-26"

    def test_slash_separator_is_a_school_year(self):
        assert SY.content_school_year("https://x.org/schedule-2024/25") == "2024-25"

    def test_url_decode_first(self):
        # obs. 6: %20 is an encoded space, not a stray "20" — decode BEFORE matching so "25-26"
        # is read for the right reason (and it generalizes).
        assert SY.content_school_year("https://x.org/Bell%20Schedule%2025-26") == "2025-26"

    def test_consecutive_pair_required_rejects_plan_span(self):
        assert SY.content_school_year("https://x.org/strategic-plan-2020-2023.pdf") is None

    def test_bare_upload_path_year_is_not_a_vintage(self):
        # a CMS upload path dates the upload, not the schedule — and it carries no consecutive pair
        assert SY.content_school_year("https://x.org/wp-content/uploads/2021/05/handbook.pdf") is None

    def test_guards_guids_and_asset_ids(self):
        assert SY.content_school_year("https://x.org/live_feed_image/17728374") is None
        assert SY.content_school_year("https://x.org/uploaded_file/5125") is None

    def test_a_date_is_not_a_school_year(self):
        # 4-20-21-Minutes.pdf is April 20 2021 — the "20-21" tail must not read as a school year
        assert SY.content_school_year("https://x.org/minutes/4-20-21-Minutes.pdf") is None

    def test_word_month_date_is_not_a_school_year(self):
        # a month-name + DD-YY date (board-meeting-March-20-21.pdf) must not read as school year 2020-21
        assert SY.content_school_year("https://x.org/board-meeting-March-20-21.pdf") is None
        assert SY.content_school_year("https://x.org/agenda/may-20-21.htm") is None

    def test_labelled_range_or_index_is_not_a_school_year(self):
        # grade ranges / page / section / version numbers are 2-digit pairs but not school years
        assert SY.content_school_year("https://x.org/grades-06-07-bell-times.pdf") is None
        assert SY.content_school_year("https://x.org/handbook/page-12-13.pdf") is None
        assert SY.content_school_year("https://x.org/docs/handbook-v12-13.pdf") is None
        assert SY.content_school_year("https://x.org/maps/bldg-22-23-annex.pdf") is None

    def test_two_digit_guard_does_not_over_reject_a_real_year(self):
        # the month/label guard must fire only on a WHOLE bounded token — 'mar' inside 'marshall' must not
        # block a genuine SY-25-26, and an 'SY'/'Bell Schedule' cue keeps a bare pair valid
        assert SY.content_school_year("https://marshallschools.org/marshall-25-26-calendar.pdf") == "2025-26"
        assert SY.content_school_year("https://x.org/SY25-26-bell.pdf") == "2025-26"

    def test_century_rollover_short_pair(self):
        # a turn-of-century 2-digit pair reads as the in-range century, not 2099
        assert SY.content_school_year("http://x.org/newsletters/bell-99-00.pdf") == "1999-00"

    def test_source_precedence_primary_url_wins_over_final_url_noise(self):
        # the FIRST source with a year wins — a CDN/CMS upload-date path in final_url must NOT override a
        # real older year in the primary url (else it silently clears #241's validity floor)
        assert SY.content_school_year("https://x.org/timetracker-2012-13.pdf",
                                      "https://x.org/system/files/2025-26/handler.pdf") == "2012-13"
        # ... but final_url is still a fallback when the primary url carries no year
        assert SY.content_school_year("https://x.org/document/view",
                                      "https://x.org/files/Handbook-2024-2025.pdf") == "2024-25"

    def test_sees_old_years_the_241_floor_needs(self):
        # UNLIKE the bell-year floor, the content read must SEE pre-2017-18 years so #241 can flag them
        assert SY.content_school_year("https://x.org/bell-2001-2002.pdf") == "2001-02"

    def test_brashear_month_word_dates_are_read(self):
        # #531: a month-word + year date (the newsletter/board-minutes shape obs.6 named as a pair-matcher
        # blind spot) maps to the school year CONTAINING that month (July-1 rollover, current_school_year's rule)
        assert SY.content_school_year("http://brashear.k12.mo.us/newsletters/September01.htm") == "2001-02"
        assert SY.content_school_year("http://brashear.k12.mo.us/newsletters/December98.htm") == "1998-99"
        assert SY.content_school_year("http://brashear.k12.mo.us/newsletters/April00.htm") == "1999-00"  # Apr → prev SY
        assert SY.content_school_year("http://x.org/newsletters/October%2004.htm") == "2004-05"  # decoded space
        assert SY.content_school_year("http://x.org/board/January-2024-minutes.pdf") == "2023-24"  # Jan → prev SY

    def test_month_word_guard_does_not_over_read(self):
        # a FULL calendar date (month-DD-YY) is not a month-year → still None (a third -NN is guarded out);
        # and a month substring inside a word ('mar' in marshall, 'may' in mayfield) must not trip
        assert SY.content_school_year("https://x.org/board-meeting-March-20-21.pdf") is None
        assert SY.content_school_year("https://marshallschools.org/marshall-25-26.pdf") == "2025-26"
        assert SY.content_school_year("https://x.org/mayfield-elementary-2024-25.pdf") == "2024-25"

    def test_multiple_years_returns_most_recent(self):
        # conservative for both consumers: prefer-recent ranks on it; #241 only flags a doc stale when
        # even its NEWEST referenced year is pre-floor
        assert SY.content_school_year("https://x.org/archive-2015-16-and-2019-20.pdf") == "2019-20"

    def test_covid_year_is_still_reported(self):
        # the signal is "what year is this doc", not "is it acceptable" — COVID handling is downstream
        assert SY.content_school_year("https://x.org/bell-2021-22.pdf") == "2021-22"

    def test_scans_multiple_sources(self):
        assert SY.content_school_year("https://x.org/page", "", "Handbook-2023-2024.pdf") == "2023-24"

    def test_no_year_and_empty_inputs(self):
        assert SY.content_school_year("https://x.org/schedules/bell.html") is None
        assert SY.content_school_year("", None) is None
        assert SY.content_school_year() is None


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

    def test_current_bell_schedule_blends_with_the_live_nces_primary_year(self):
        # REQ-026/REQ-136: pins the PR #491 rollover arithmetic as a durable regression guard, tied to
        # the LIVE constants rather than a one-off manual check — the coupling recurs every rollover.
        assert SY.within_blend_window([SY.CURRENT_SCHOOL_YEAR, SY.NCES_PRIMARY_YEAR])

    def test_a_stale_nces_primary_year_would_have_failed_the_window(self):
        # the exact failure the 2026-07-14 NCES_PRIMARY_YEAR bump (2023-24 -> 2024-25) fixed: a
        # 2026-27 bell schedule against the THEN-current 2023-24 vintage is span 3, out of window.
        assert not SY.within_blend_window(["2026-27", "2023-24"])


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


class TestCurrentSchoolYearDerivation:
    def test_july_first_rolls_over(self):
        from datetime import date
        assert SY.current_school_year(date(2026, 6, 30)) == "2025-26"
        assert SY.current_school_year(date(2026, 7, 1)) == "2026-27"

    def test_spring_belongs_to_prior_start_year(self):
        from datetime import date
        assert SY.current_school_year(date(2027, 1, 15)) == "2026-27"
        assert SY.current_school_year(date(2026, 12, 31)) == "2026-27"

    def test_module_constant_matches_derivation(self):
        assert SY.CURRENT_SCHOOL_YEAR == SY.current_school_year()

    def test_acceptable_bell_years_floor_at_first_post_covid_year(self):
        assert SY.ACCEPTABLE_BELL_YEARS[-1] == "2023-24"
        assert SY.ACCEPTABLE_BELL_YEARS[0] == SY.CURRENT_SCHOOL_YEAR

    def test_current_school_year_constant_is_derived_not_a_literal(self):
        """REQ-136 regression guard. test_module_constant_matches_derivation above only proves
        CURRENT_SCHOOL_YEAR equals current_school_year() TODAY, in this process — a hand-bumped
        literal (the pre-2026-07 bug class) would pass that check right up until the next July 1 in
        PRODUCTION, not in CI. This inspects the module SOURCE and fails immediately if the constant
        is ever rebound to a string literal instead of a call expression."""
        import ast
        import inspect

        from infrastructure.utilities import school_year as _real_module   # not the database/ shim —
        # the shim re-exports via `from ... import (...)`, which carries no Assign node to inspect
        tree = ast.parse(inspect.getsource(_real_module))
        assign = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "CURRENT_SCHOOL_YEAR" for t in node.targets))
        assert isinstance(assign.value, ast.Call), (
            "CURRENT_SCHOOL_YEAR must be assigned from a call to current_school_year() — found a "
            f"{type(assign.value).__name__} instead (a hardcoded literal would silently go stale "
            "at the next July-1 rollover, exactly the bug this module exists to prevent)")
        assert getattr(assign.value.func, "id", None) == "current_school_year"


class TestConstants:
    def test_current_year_is_well_formed_and_post_covid(self):
        assert SY.is_acceptable_data_year(SY.CURRENT_SCHOOL_YEAR)
        assert SY.CURRENT_SCHOOL_YEAR in SY.ACCEPTABLE_BELL_YEARS

    def test_acceptable_bell_years_newest_first_and_post_covid(self):
        starts = [SY.start_year(y) for y in SY.ACCEPTABLE_BELL_YEARS]
        assert starts == sorted(starts, reverse=True)
        assert all(SY.is_acceptable_data_year(y) for y in SY.ACCEPTABLE_BELL_YEARS)
