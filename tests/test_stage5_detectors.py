"""Stage 5 V2 detectors + combiner (REQ-113) — the labeling-function decomposition.

Pure signal-dict in / decision out. These lock the three measured V1 fixes (de-chrome footer recovery,
proximity requirement, suppress floor) and the structural-vs-incidental target distinction that keeps
feed pages from auto-sending while still sending a feed page that carries a real hours block.
"""
from infrastructure.acquisition.stage5_filter import combiner as C
from infrastructure.acquisition.stage5_filter import detectors as D


def sig(**kw):
    base = dict(n_times=0, n_times_in_window=0, times_after_5pm=0, proximity_pairs=0,
                positive_kw=[], negative_kw={"board": [], "sports": [], "calendar": [], "transport": []},
                neg_total=0, instructional_time=False, has_table=False, period_hits=0,
                table_time_density=0, table_period_rows=0, roster_school_names_hit=0,
                footer_hours={"hit": False, "times": 0, "office": False},
                header_hours={"hit": False, "times": 0, "office": False},
                heading_hours_hits=0, heading_hours_labels=[], nonstandard_day=False,
                harvest_pages=[], url_feed_pattern=False, embed_hosts=[])
    base.update(kw)
    return base


def decide(**kw):
    return C.score_record(sig(**kw))


# ---- the three measured V1 fixes ----
def test_footer_hours_target_is_no_longer_suppressed():
    # Dickinson/Henning: real school hours ONLY in the footer -> was tier D (de-chrome zeroed it).
    r = decide(footer_hours={"hit": True, "times": 2, "office": False}, positive_kw=["bell schedule"])
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_footer_hours" in r["fired"]


def test_office_hours_footer_is_a_negative_not_a_target():
    r = decide(footer_hours={"hit": True, "times": 2, "office": True})
    assert r["decision"] != "send"
    assert "lf_office_hours" in r["fired"] and "lf_footer_hours" not in r["fired"]


def test_weak_times_need_a_proximity_pair_to_leave_suppress():
    # two in-window times but NO proximity pair (V1 tier-B FP source) -> not a weak-target, gets suppressed.
    assert D.lf_weak_times(sig(n_times_in_window=2, proximity_pairs=0), D.DEFAULT_DETECTOR_PARAMS) is None
    assert D.lf_weak_times(sig(n_times_in_window=2, proximity_pairs=1), D.DEFAULT_DETECTOR_PARAMS) is not None


def test_suppress_floor_is_no_in_window_times_not_no_times():
    # times exist but ALL out of window -> still a confident suppress (the corrected floor).
    r = decide(n_times=3, n_times_in_window=0, times_after_5pm=3)
    assert r["decision"] == "suppress" and r["tier"] == "D"
    assert "lf_no_times" in r["fired"]


# ---- the structural vs incidental target distinction (feed pages) ----
def test_news_feed_demotes_incidental_time_target_to_review():
    r = decide(n_times=11, n_times_in_window=8, proximity_pairs=5, positive_kw=["dismissal"], url_feed_pattern=True)
    assert r["decision"] == "review" and r["tier"] == "B"      # not auto-sent to the paid council
    assert "lf_news_feed" in r["fired"] and "lf_prose_pair" in r["fired"]


def test_feed_page_with_a_real_footer_block_still_sends():
    # a structural hours block survives the feed undermining — the nuance that keeps recall.
    r = decide(proximity_pairs=5, url_feed_pattern=True, positive_kw=["school hours"],
               footer_hours={"hit": True, "times": 2, "office": False})
    assert r["decision"] == "send" and r["tier"] == "A"


# ---- the core targets still send ----
def test_schedule_table_sends():
    r = decide(proximity_pairs=4, positive_kw=["bell schedule"], table_time_density=10,
               table_period_rows=6, has_table=True, period_hits=6)
    assert r["decision"] == "send" and r["category"] == "school_bell_schedule"


def test_explicit_minutes_is_a_strong_target():
    r = decide(instructional_time=True)
    assert r["decision"] == "send" and r["category"] == "explicit_instructional_time"


def test_plain_prose_pair_without_feed_sends():
    r = decide(n_times_in_window=4, proximity_pairs=2, positive_kw=["start time", "dismissal"])
    assert r["decision"] == "send" and r["tier"] == "A"


# ---- combiner bookkeeping ----
def test_votes_and_fired_are_persisted_for_the_harness_and_ui():
    r = decide(footer_hours={"hit": True, "times": 2, "office": False}, positive_kw=["bell schedule"])
    assert isinstance(r["votes"], list) and r["votes"], "votes must be stored for signals_json"
    assert set(r["fired"]) == {v["name"] for v in r["votes"]}
    assert all({"name", "polarity", "strength", "confidence", "reason", "category"} <= set(v) for v in r["votes"])


def test_calendar_dominant_no_pair_suppresses():
    r = decide(n_times=3, n_times_in_window=0,
               negative_kw={"board": [], "sports": [], "calendar": ["school calendar", "holiday"], "transport": []},
               neg_total=2)
    assert r["decision"] == "suppress"
