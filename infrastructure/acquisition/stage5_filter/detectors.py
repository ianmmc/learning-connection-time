#!/usr/bin/env python3
"""Stage 5 V2 DETECTORS — independent labeling functions over the signal vector (REQ-113).

Each detector is a pure function `(sig, params) -> Vote|None` that answers ONE narrow question about a
record and votes toward a routing polarity, or returns None (abstain). This replaces the V1 `tier_and_category`
if/elif cascade whose sequential structure hid *which branch* drifted at scale (85%→69% tier-A precision,
tier-D leaking 10 targets — see STAGE5_FILTER_DESIGN §2). Detectors are independently testable, independently
tunable, and each maps 1:1 onto a human labeling facet (REQ-114) and a harness diagnostic (REQ-113 §5).

NO AI, NO DB — pure dict-in / Vote-out. The combiner (`combiner.py`) reduces the votes to a send/suppress/
review decision. Weak-supervision framing (Snorkel labeling functions): see
docs/technical-notes/filtering-research/ + STAGE5_TUNING_NOTES Part C.
"""
from collections import namedtuple

# A detector's vote. polarity: 'target' (evidence FOR) | 'negative' (evidence AGAINST) | 'suppress'
# (a confident drop). strength: 'strong' | 'weak' | 'soft'. reason: a short human string for the UI/audit.
Vote = namedtuple("Vote", ["name", "polarity", "strength", "confidence", "reason", "category"])

# Thresholds live next to the logic (the DEFAULT_TIER_PARAMS precedent) until the frontier settles them;
# promotable to config-as-data. Keyword lists ARE already config-as-data (build_signals loads them).
DEFAULT_DETECTOR_PARAMS = {
    "table_min_times": 4,     # DENSE in-window times in a table rep (with a positive kw) -> a schedule table
    "table_min_periods": 2,   # OR real period-row structure (Period 1/2/…) — the higher-precision path
    "neg_dom_min": 2,         # a negative class this dominant (and > positives, no proximity pair) -> negative
    "wrong_day_dominance_min": 4,  # >= this many wrong-day schedule TITLES overrides the S3 regular-day
                                   # guard (a variant-dominated page — DASD/MUSD shape). Measured
                                   # 2026-07-18: at 4, +3 facet coverage for 0 extra real-target fires.
}


# ----------------------------- target detectors (evidence FOR a bell schedule) -----------------------------
def lf_explicit_minutes(sig, p):
    """An explicit 'NNN minutes of instruction/day' declaration — the strongest, rarest target (the
    'golden nugget' path; see memory two-paths-to-instructional-minutes)."""
    if sig.get("instructional_time") and not _all_after5(sig):
        return Vote("lf_explicit_minutes", "target", "strong", 0.95,
                    "explicit instructional-minutes declaration", "explicit_instructional_time")
    return None


def lf_time_table(sig, p):
    """A real SCHEDULE table (camelot/pdfplumber Markdown). Precision comes from requiring schedule
    STRUCTURE — period rows (Period 1/2/…), OR dense in-window times WITH a positive keyword — not merely
    a table with ≥2 times (measured: the loose rule fired at 55% accuracy; this lifts canonical tier-A
    precision 0.65→0.78 with zero targets dropped — REQ-113 §5, the diagnostics naming the fix)."""
    density, periods = sig.get("table_time_density", 0), sig.get("table_period_rows", 0)
    if periods >= p["table_min_periods"] or (density >= p["table_min_times"] and sig.get("positive_kw")):
        return Vote("lf_time_table", "target", "strong", 0.85,
                    f"schedule table ({density} times / {periods} period rows)", "school_bell_table")
    return None


def lf_prose_pair(sig, p):
    """A start/end proximity pair in-window + a positive keyword, no negative dominance — the V1 tier-A core."""
    if sig.get("proximity_pairs", 0) >= 1 and (sig.get("positive_kw") or sig.get("period_hits", 0) >= 2) \
            and not _neg_dominant(sig, p) and not _all_after5(sig):
        cat = "school_bell_table" if sig.get("period_hits", 0) >= 2 else "school_start_end_prose"
        return Vote("lf_prose_pair", "target", "strong", 0.8,
                    "in-window start/end pair + positive keyword", cat)
    return None


def lf_footer_hours(sig, p):
    """School hours in the FOOTER/HEADER as an intentional 'Hours: 8:24-3:30' block (REQ-113 §2a-1 — the
    de-chrome false-negative fix). A distinct information SHAPE (list, not table/prose). Down-graded to a
    soft *negative* when the block reads as OFFICE hours (the research's #1 confusable).

    The two segments are evaluated INDEPENDENTLY (#61): the old code OR-ed the two `office` flags into one
    verdict, so an office-hours FOOTER downgraded a genuine school-hours HEADER (and vice versa) to the
    office negative — losing the real target. Now a genuine (non-office) hours block in EITHER segment is a
    target; only when EVERY hit segment reads as office (and no positive keyword rescues it) is it the
    office-hours confusable."""
    fh, hh = sig.get("footer_hours") or {}, sig.get("header_hours") or {}
    segs = [s for s in (fh, hh) if s.get("hit")]
    if not segs:
        return None
    school_seg = any(not s.get("office") for s in segs)   # a genuine, non-office block in either segment
    if school_seg or sig.get("positive_kw"):
        return Vote("lf_footer_hours", "target", "strong", 0.75,
                    "school-hours block in the footer/header", "school_start_end_list")
    return Vote("lf_office_hours", "negative", "soft", 0.5,
                "footer/header hours read as office/staff hours", "other_schedule")


def lf_heading_hours(sig, p):
    """A time-range sitting right under an hours-intent HEADING (heading-proximity). Non-office headings
    are a target; office/staff headings are the confusable negative."""
    if sig.get("heading_hours_hits", 0) < 1:
        return None
    labels = sig.get("heading_hours_labels") or []
    if any("office" in l for l in labels):
        return Vote("lf_office_hours", "negative", "soft", 0.5,
                    f"time under an office-hours heading ({', '.join(labels)})", "other_schedule")
    return Vote("lf_heading_hours", "target", "strong", 0.7,
                f"time under a school-hours heading ({', '.join(labels) or 'hours'})", "school_start_end_list")


def lf_weak_times(sig, p):
    """Weak target evidence: an in-window proximity pair but weak/absent keywords -> the REVIEW middle
    (REQ-113 §2a-2 — was tier-B noise; the proximity-pair requirement is what removed the 13 FPs)."""
    if sig.get("proximity_pairs", 0) >= 1 and not _neg_dominant(sig, p) and not _all_after5(sig):
        return Vote("lf_weak_times", "target", "weak", 0.4,
                    "in-window time pair, weak keyword support", "target_other_shape")
    return None


# ----------------------------- negative detectors (evidence AGAINST / suppress) -----------------------------
def lf_no_times(sig, p):
    """The corrected SUPPRESS floor (REQ-113 §2a-3): NO in-window times anywhere (incl. footer/table) and
    no explicit-minutes -> a confident drop. Was `n_times==0`; all-out-of-window is equally droppable."""
    any_iw = (sig.get("n_times_in_window", 0) or (sig.get("footer_hours") or {}).get("times", 0)
              or (sig.get("header_hours") or {}).get("times", 0) or sig.get("table_time_density", 0))
    if not any_iw and not sig.get("instructional_time") and not sig.get("harvest_pages"):
        return Vote("lf_no_times", "suppress", "strong", 0.9, "no in-window times anywhere", "none")
    return None


def lf_news_feed(sig, p):
    """A CMS news/social feed (URL pattern or an embed to a social/feed host): incidental post times trip
    the time signals. The #1 tier-A pollutant — a DOWN-WEIGHT (not a hard reject: some feed pages also carry
    real hub hours), so it only suppresses when NO target detector fires (the combiner enforces that)."""
    if sig.get("url_feed_pattern") or "social" in (sig.get("embed_hosts") or []):
        return Vote("lf_news_feed", "negative", "strong", 0.7, "news/social feed page", "embedded_feed")
    return None


def lf_calendar_widget(sig, p):
    """An embedded calendar (a calendar-host iframe, or calendar-keyword dominance with no proximity pair)."""
    if "calendar" in (sig.get("embed_hosts") or []):
        return Vote("lf_calendar_widget", "negative", "strong", 0.7, "embedded calendar widget", "academic_calendar")
    nb = {k: len(v) for k, v in (sig.get("negative_kw") or {}).items()}
    if nb.get("calendar", 0) >= 2 and sig.get("proximity_pairs", 0) == 0:
        return Vote("lf_calendar_widget", "negative", "weak", 0.5, "calendar-dominant, no start/end pair", "academic_calendar")
    return None


def lf_nonstandard_day(sig, p):
    """A genuine schedule that is NOT the regular school day (the #537 "Non-Regular-Day Schedule" facet:
    early dismissal / late start / remote / summer / event times). Two strengths (#537 follow-on):
    STRONG when the term is POSITIONAL — titling a schedule ("Early Dismissal Bell Schedule", the DASD
    shape) or adjacent to the in-window times themselves — because then the times ARE the irregular
    day's; SOFT on a bare anywhere-in-text mention (a regular-day page merely mentioning delay policy —
    37% of real targets do, so a mention alone must never demote structure). GUARD (measured, rule S3):
    a page that also declares its REGULAR day ("Regular Schedule" / "Daily Schedule") is a regular-day
    page listing its variants beside the regular rows — positional evidence downgrades to a mention.
    SOFT is the FLOOR either way: guarded-positional and the legacy anywhere-mention both land there,
    which is why the S3 guard reads only in the strong/soft split — there is no weaker level for it to
    act on below soft (PR #538 review; if a future change strengthens the anywhere branch, the guard
    must be re-threaded through it too)."""
    positional = sig.get("nonstandard_near_times") or sig.get("nonstandard_heading")
    # Dominance override (PR #538 review, measured): the guard is an any-match boolean, so one stray
    # "regular hours" phrase would otherwise mute a page carrying MANY variant-schedule titles — a page
    # that variant-dominated is a non-regular-day page regardless. Free at the measured threshold
    # (+3 facet coverage, 0 extra real-target fires).
    variant_dominated = (sig.get("nonstandard_heading") or 0) >= p["wrong_day_dominance_min"]
    if positional and (not sig.get("regular_day_language") or variant_dominated):
        return Vote("lf_nonstandard_day", "negative", "strong", 0.7,
                    "non-regular-day schedule named at/near the times", "other_schedule")
    if positional:
        return Vote("lf_nonstandard_day", "negative", "soft", 0.45,
                    "non-regular-day terms near times, but the page declares its regular day", "other_schedule")
    if sig.get("nonstandard_day"):
        return Vote("lf_nonstandard_day", "negative", "soft", 0.45, "non-standard-day (weather/remote) schedule", "other_schedule")
    return None


def _neg_class(cls, cat):
    def lf(sig, p):
        nb = {k: len(v) for k, v in (sig.get("negative_kw") or {}).items()}
        if nb.get(cls, 0) >= p["neg_dom_min"] and nb[cls] >= max(nb.values()) \
                and nb[cls] > len(sig.get("positive_kw") or []) and sig.get("proximity_pairs", 0) == 0:
            return Vote(f"lf_{cls}", "negative", "strong", 0.65, f"{cls}-dominant negative keywords", cat)
        return None
    return lf


lf_board = _neg_class("board", "board_schedule")
lf_sports = _neg_class("sports", "sports_schedule")
lf_transport = _neg_class("transport", "transportation_schedule")


# ----------------------------- helpers -----------------------------
def _all_after5(sig):
    return sig.get("n_times", 0) > 0 and sig.get("times_after_5pm", 0) == sig.get("n_times", 0)


def _neg_dominant(sig, p):
    nb = {k: len(v) for k, v in (sig.get("negative_kw") or {}).items()}
    tot = sum(nb.values())
    return tot >= p["neg_dom_min"] and tot > len(sig.get("positive_kw") or []) and sig.get("n_times_in_window", 0) <= 1


# The registry — order is documentation only; the combiner treats votes as an unordered set.
DETECTORS = [
    lf_explicit_minutes, lf_time_table, lf_prose_pair, lf_footer_hours, lf_heading_hours, lf_weak_times,
    lf_no_times, lf_news_feed, lf_calendar_widget, lf_nonstandard_day, lf_board, lf_sports, lf_transport,
]


# ----------------------------- relevance-density event weights (#521) -----------------------------
# The console's relevance-density curve places POSITIONAL signal events on a document's character axis and
# signs each by the SAME polarity/confidence the detectors above vote with — ONE source of truth, so the
# heat-strip can never contradict the score (the console guardrail). Each event mirrors the confidence of
# the detector its signal most directly drives (named in the comment); the frontend fetches this map via
# /api/detector-weights and holds ZERO hardcoded weights (the anti-"second-weight-set" discipline #521
# insists on). `test_stage5_detectors` pins each detector-anchored event to that detector's LIVE Vote
# confidence, so this map cannot silently drift from the votes above. `+1` = toward a schedule, `-1` = away.
EVENT_WEIGHTS = {
    # positive — evidence FOR a bell schedule, placed at the offset it fires
    "instructional":  (+1, 0.95),   # lf_explicit_minutes — an explicit instructional-minutes phrase
    "table_times":    (+1, 0.85),   # lf_time_table       — a schedule-table time row
    "proximity_pair": (+1, 0.80),   # lf_prose_pair       — an in-window start/end pair (strongest single signal)
    "in_window_time": (+1, 0.40),   # lf_weak_times       — a lone in-window time (supporting)
    "positive_kw":    (+1, 0.20),   # (no 1:1 detector — a positive keyword; supporting, DIALED BACK from the
                                    #  0.40 weak-tier: measured on Huntington ISD's 130-pg handbook, 0.40 let
                                    #  scattered keyword clusters (dress-code, policy prose) out-rank the real
                                    #  schedule; 0.20 keeps the times/pairs schedule region #1 and drops the
                                    #  keyword-only noise peaks. The one free-to-tune event, so tune it HERE.)
    # negative — confounder context, placed at the offset it fires
    "board":          (-1, 0.65),   # lf_board
    "sports":         (-1, 0.65),   # lf_sports
    "transport":      (-1, 0.65),   # lf_transport
    "office_hours":   (-1, 0.50),   # lf_office_hours     — "office/staff hours" language
    "calendar":       (-1, 0.50),   # lf_calendar_widget  — calendar-keyword context (weak variant)
    "wrong_day":      (-1, 0.70),   # lf_nonstandard_day  — a non-regular-day term (STRONG positional
                                    #  variant's confidence; #537 follow-on — without this event the
                                    #  heat-strip couldn't show the evidence that demoted the record)
}

# Which detector's live Vote confidence each event MUST match (the no-drift contract; positive_kw has no
# 1:1 detector, so it is excluded and free to tune). Used by the test, not at runtime.
EVENT_CONFIDENCE_SOURCE = {
    "instructional": "lf_explicit_minutes", "table_times": "lf_time_table", "proximity_pair": "lf_prose_pair",
    "in_window_time": "lf_weak_times", "board": "lf_board", "sports": "lf_sports", "transport": "lf_transport",
    "office_hours": "lf_office_hours", "calendar": "lf_calendar_widget", "wrong_day": "lf_nonstandard_day",
}


def run_all(sig, params=None):
    """Run every detector; return the list of non-abstain Votes (as dicts, JSON-ready for signals_json)."""
    p = params or DEFAULT_DETECTOR_PARAMS
    votes = []
    for lf in DETECTORS:
        v = lf(sig, p)
        if v is not None:
            votes.append(v._asdict())
    return votes
