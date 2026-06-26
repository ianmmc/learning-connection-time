"""REQ-093 — Stage 5 keyword knobs load from config; the instructional-time regex is MINUTES-ONLY
(hours reverted after the harness proved it net-negative — a vision problem); an instructional-time
hit rescues a record from the n==0 / neg-keyword drop."""
import sys
from pathlib import Path

REVIEW = Path(__file__).resolve().parents[1] / "infrastructure" / "acquisition" / "stage5_filter" / "review_app"
sys.path.insert(0, str(REVIEW))
import build_signals as BS  # noqa: E402


def _sig(**over):
    base = {"n_times": 0, "n_times_in_window": 0, "proximity_pairs": 0, "times_after_5pm": 0,
            "positive_kw": [], "negative_kw": {"board": [], "sports": [], "calendar": [], "transport": []},
            "neg_total": 0, "instructional_time": False, "has_table": False, "period_hits": 0,
            "roster_school_names_hit": 0, "max_text_chars": 500, "pages": []}
    base.update(over)
    return base


def test_keywords_loaded_from_config_including_class_schedule():
    assert "class schedule" in BS.POSITIVE_KW      # REQ-093 addition (ROY)
    assert "bell schedule" in BS.POSITIVE_KW        # baseline
    assert "academic calendar" in BS.NEG_CALENDAR   # baseline negative class


def test_instructional_regex_is_minutes_only_no_hours_false_positives():
    assert BS.INSTRUCTIONAL_RE.search("students receive 450 minutes of instruction")
    assert BS.INSTRUCTIONAL_RE.search("instructional minutes per day")
    # hours reverted (vision problem) -> must NOT match, so no marketing-copy false positives:
    assert not BS.INSTRUCTIONAL_RE.search("our instructional hours are flexible")
    assert not BS.INSTRUCTIONAL_RE.search("147 days x 7.5 hrs/day")
    # board-meeting "minutes" never false-positives (the original anchor):
    assert not BS.INSTRUCTIONAL_RE.search("board meeting minutes approved")


def test_instructional_time_rescues_calendar_record_to_B():
    # instr hit, no clock times, calendar keywords -> rescued to B (not D via n==0, not C via neg_dominant)
    tier, _score, cat = BS.tier_and_category(
        _sig(instructional_time=True, neg_total=2,
             negative_kw={"board": [], "sports": [], "calendar": ["academic calendar", "holiday"], "transport": []}),
        roster_size=2)
    assert tier == "B"
    assert cat == "explicit_instructional_time"


def test_no_times_no_instr_still_drops_to_D():
    tier, _s, _c = BS.tier_and_category(_sig(), roster_size=0)
    assert tier == "D"


def test_strong_target_still_tier_A_not_demoted_by_rescue():
    # a real bell schedule (time pair + positive kw) must remain A even if instr also true
    tier, _s, _c = BS.tier_and_category(
        _sig(n_times=4, n_times_in_window=4, proximity_pairs=2, positive_kw=["bell schedule"],
             instructional_time=True),
        roster_size=2)
    assert tier == "A"
