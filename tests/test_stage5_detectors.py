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


# ---- #61: footer/header evaluated INDEPENDENTLY (an office footer must not downgrade a school header) ----
def test_school_header_survives_an_office_footer():
    # office FOOTER + genuine school-hours HEADER: the old OR-merge downgraded this to office negative,
    # losing the real header target. Now the non-office segment wins -> target.
    r = decide(footer_hours={"hit": True, "times": 2, "office": True},
               header_hours={"hit": True, "times": 2, "office": False})
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_footer_hours" in r["fired"] and "lf_office_hours" not in r["fired"]


def test_both_segments_office_is_still_the_office_negative():
    # regression guard: when EVERY hit segment reads office (no positive kw), it stays the office confusable.
    r = decide(footer_hours={"hit": True, "times": 2, "office": True},
               header_hours={"hit": True, "times": 2, "office": True})
    assert r["decision"] != "send"
    assert "lf_office_hours" in r["fired"] and "lf_footer_hours" not in r["fired"]


# ---- #60: a nonstandard-day soft negative undermines an INCIDENTAL pair, not a structural block ----
def test_nonstandard_day_demotes_an_incidental_pair_to_review():
    # a delay/weather page with a prose start/end pair used to auto-send tier-A (only the extraction
    # prompt's 'ignore early-dismissal' backstopped it); now it routes to review.
    r = decide(n_times_in_window=4, proximity_pairs=2, positive_kw=["start time", "dismissal"],
               nonstandard_day=True)
    assert r["decision"] == "review" and r["tier"] == "B"
    assert "lf_nonstandard_day" in r["fired"] and "lf_prose_pair" in r["fired"]


def test_nonstandard_day_does_not_demote_a_structural_block():
    # a real footer hours block on a page that also mentions a delay is STILL the standard day -> send
    # (structure beats wrong-day noise, the combiner's core rule).
    r = decide(footer_hours={"hit": True, "times": 2, "office": False}, positive_kw=["bell schedule"],
               nonstandard_day=True)
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_footer_hours" in r["fired"]


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


# ---- #528: a lone times-TABLE is undermined by a feed/calendar (its own events/agenda table) ----
def test_feed_page_with_only_a_times_table_is_reviewed():
    # measured (14 tier-A false-sends, 0 real targets): a schedule-shaped table on a feed page with no
    # intentional hours block/heading is probably the feed's OWN table -> review, not auto-send.
    r = decide(table_time_density=10, positive_kw=["bell schedule"], url_feed_pattern=True)
    assert r["decision"] == "review" and r["tier"] == "B"
    assert "lf_time_table" in r["fired"] and "lf_news_feed" in r["fired"]


def test_calendar_page_with_only_a_times_table_is_reviewed():
    # the same rule covers the calendar-widget false-sends (#528's 3 calendar cases)
    r = decide(table_time_density=10, positive_kw=["bell schedule"], embed_hosts=["calendar"])
    assert r["decision"] == "review" and r["tier"] == "B"
    assert "lf_time_table" in r["fired"] and "lf_calendar_widget" in r["fired"]


def test_feed_page_with_a_times_table_AND_hours_heading_still_sends():
    # a REAL schedule delivered in a feed carries an hours heading (strong-structural) -> still sends (0 cost)
    r = decide(table_time_density=10, positive_kw=["bell schedule"], url_feed_pattern=True,
               heading_hours_hits=1, heading_hours_labels=["school hours"])
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_heading_hours" in r["fired"] and "lf_time_table" in r["fired"]


def test_clean_times_table_without_a_feed_still_sends():
    # no feed/calendar undermining -> a schedule table auto-sends as before (guard against over-demotion)
    r = decide(table_time_density=10, positive_kw=["bell schedule"])
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_time_table" in r["fired"]


def test_table_plus_prose_pair_plus_feed_is_reviewed():
    # branch precedence: table+feed routes to review via the TABLE branch before the incidental branch —
    # both target signals are feed-undermined, so review is right either way (guards an elif reorder).
    r = decide(table_time_density=10, positive_kw=["bell schedule"], proximity_pairs=5, url_feed_pattern=True)
    assert r["decision"] == "review" and r["tier"] == "B"
    assert {"lf_time_table", "lf_prose_pair", "lf_news_feed"} <= set(r["fired"])


def test_strong_structural_beats_the_table_undermine_branch():
    # a footer hours block (STRONG_STRUCTURAL) sends unconditionally even with a table AND a feed present
    r = decide(table_time_density=10, positive_kw=["bell schedule"], url_feed_pattern=True,
               footer_hours={"hit": True, "times": 2, "office": False})
    assert r["decision"] == "send" and r["tier"] == "A"
    assert {"lf_footer_hours", "lf_time_table", "lf_news_feed"} <= set(r["fired"])


def test_table_with_only_a_soft_nonstandard_day_still_sends():
    # a TABLE is undermined by feed/calendar ONLY, never a soft #60 wrong-day negative (structure beats soft
    # noise) — guards the deliberate hard-vs-soft asymmetry against a future "unify undermined" change.
    r = decide(table_time_density=10, positive_kw=["bell schedule"], nonstandard_day=True)
    assert r["decision"] == "send" and r["tier"] == "A"
    assert {"lf_time_table", "lf_nonstandard_day"} <= set(r["fired"])


def test_demoted_table_keeps_its_bell_table_category_hypothesis():
    # a demoted-to-review table keeps category=school_bell_table (the human's hint at gate@5), consistent
    # with the incidental-undermined branch — the decision (review), not the category, gates dispatch.
    r = decide(table_time_density=10, positive_kw=["bell schedule"], url_feed_pattern=True)
    assert r["decision"] == "review" and r["category"] == "school_bell_table"


# ---- the core targets still send ----
def test_schedule_table_sends():
    r = decide(proximity_pairs=4, positive_kw=["bell schedule"], table_time_density=10,
               table_period_rows=6, has_table=True, period_hits=6)
    assert r["decision"] == "send" and r["category"] == "school_bell_table"


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


# ---- #521 relevance-density event weights: the no-drift SSOT contract ----
def test_event_weights_match_live_detector_confidence():
    """Every detector-anchored relevance-density event (EVENT_WEIGHTS) must carry the LIVE Vote confidence
    of the detector it mirrors — so the console heat-strip/bookmarks can't drift from the score they
    visualise (#521's anti-second-weight-set discipline). `positive_kw` has no 1:1 detector: excluded here,
    free to tune. If a detector's confidence or trigger changes, this test fails until EVENT_WEIGHTS follows."""
    P = D.DEFAULT_DETECTOR_PARAMS
    # event -> (detector fn, a minimal sig that makes exactly that vote fire)
    triggers = {
        "instructional":  (D.lf_explicit_minutes, {"instructional_time": True}),
        "table_times":    (D.lf_time_table,       {"table_period_rows": 2}),
        "proximity_pair": (D.lf_prose_pair,       {"proximity_pairs": 1, "positive_kw": ["school"]}),
        "in_window_time": (D.lf_weak_times,       {"proximity_pairs": 1}),
        "board":          (D.lf_board,            {"negative_kw": {"board": ["a", "b"]}}),
        "sports":         (D.lf_sports,           {"negative_kw": {"sports": ["a", "b"]}}),
        "transport":      (D.lf_transport,        {"negative_kw": {"transport": ["a", "b"]}}),
        "office_hours":   (D.lf_footer_hours,     {"footer_hours": {"hit": True, "office": True}, "positive_kw": []}),
        "calendar":       (D.lf_calendar_widget,  {"negative_kw": {"calendar": ["a", "b"]}}),
        "wrong_day":      (D.lf_nonstandard_day,  {"nonstandard_near_times": 1}),
    }
    assert set(triggers) == set(D.EVENT_CONFIDENCE_SOURCE), "trigger set must cover every anchored event"
    for event, (fn, sig) in triggers.items():
        vote = fn(sig, P)
        assert vote is not None, f"{event}: crafted sig no longer fires {fn.__name__}"
        assert vote.name == D.EVENT_CONFIDENCE_SOURCE[event], \
            f"{event}: fired {vote.name}, expected {D.EVENT_CONFIDENCE_SOURCE[event]}"
        assert D.EVENT_WEIGHTS[event][1] == vote.confidence, \
            f"{event}: EVENT_WEIGHTS weight {D.EVENT_WEIGHTS[event][1]} != live {vote.name} confidence {vote.confidence}"


def test_event_weights_shape_and_polarity_signs():
    """Positive events vote +1 toward a schedule, negatives -1 away; positive_kw is present but unanchored."""
    pos = {"instructional", "table_times", "proximity_pair", "in_window_time", "positive_kw"}
    neg = {"board", "sports", "transport", "office_hours", "calendar", "wrong_day"}
    assert set(D.EVENT_WEIGHTS) == pos | neg
    assert all(D.EVENT_WEIGHTS[e][0] == +1 and D.EVENT_WEIGHTS[e][1] > 0 for e in pos)
    assert all(D.EVENT_WEIGHTS[e][0] == -1 and D.EVENT_WEIGHTS[e][1] > 0 for e in neg)
    assert "positive_kw" not in D.EVENT_CONFIDENCE_SOURCE   # the one intentionally free-to-tune event


# ---- #532: the page-focus (district-homepage) negative ----
def test_homepage_with_roster_breadth_demotes_incidental_times_to_review():
    # the measured shape (sfps.info / millard / coffeecounty): a landing page hitting >=3 roster school
    # names whose incidental times (news teasers) trip table/prose detectors -> review, not auto-send.
    r = decide(url_rootish=True, roster_school_names_hit=3, proximity_pairs=5, n_times_in_window=6,
               positive_kw=["dismissal"], table_time_density=10)
    assert r["decision"] == "review" and r["tier"] == "B"
    assert "lf_district_homepage" in r["fired"]


def test_homepage_with_an_hours_block_still_sends():
    # the recall guard made flesh: lincnet.org / carlosgilbert — a homepage carrying a REAL intentional
    # hours block (strong-structural) is a target; page-focus must not demote it.
    r = decide(url_rootish=True, roster_school_names_hit=4, proximity_pairs=5,
               positive_kw=["school hours"], heading_hours_hits=1, heading_hours_labels=["school hours"])
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_district_homepage" in r["fired"] and "lf_heading_hours" in r["fired"]


def test_school_homepage_with_low_roster_breadth_is_untouched():
    # a single school's homepage (roster hits < 3) with a clean pair still auto-sends — the detector is
    # about MANY-school landing pages, not homepages per se (learningworkscharter / strasburg).
    r = decide(url_rootish=True, roster_school_names_hit=2, proximity_pairs=2, positive_kw=["school hours"])
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_district_homepage" not in r["fired"]


def test_deep_page_with_roster_breadth_is_untouched():
    # a real district hub PAGE (/schedules/ listing every school) hits many roster names by design —
    # the URL shape is the page-focus half; without a rootish URL the detector must abstain.
    r = decide(url_rootish=False, roster_school_names_hit=9, proximity_pairs=4, positive_kw=["bell schedule"])
    assert r["decision"] == "send" and r["tier"] == "A"
    assert "lf_district_homepage" not in r["fired"]
