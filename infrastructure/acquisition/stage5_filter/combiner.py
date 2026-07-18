#!/usr/bin/env python3
"""Stage 5 V2 COMBINER — reduce detector votes to a routing decision (REQ-113).

Takes the votes emitted by `detectors.run_all(sig)` and reduces them to the decision Stage 6 consumes:
`send` / `suppress` / `review`, plus a derived tier letter (A/B/C/D) kept for human legibility and
back-compat with the existing release tier-gate + attention model, and a weak category hypothesis.

Deliberately a TRANSPARENT rule (not a learned model) — the research's "start with a transparent weighted
vote; only graduate to a Snorkel LabelModel once per-detector diagnostics show heterogeneous accuracy at
medium label density" (STAGE5_TUNING_NOTES Part C). PURE: votes in, decision out.

Decision policy (recall-biased — the expensive error is dropping a real schedule before the human sees it):
  - a STRONG-STRUCTURAL target (footer hours / heading hours / explicit minutes — an intentional hours block
    or declaration) → SEND (tier A): trustworthy even amid negatives (a feed page with a real footer schedule
    IS a target)
  - a schedule TABLE (lf_time_table) → SEND (tier A) UNLESS undermined by a feed/calendar negative, in which
    case it → REVIEW (tier B): a lone times-table on a feed/calendar page is probably that widget's own
    events/scores/agenda table, not the student day (#528 — measured 14 tier-A false-sends, 0 real targets)
  - a TIME-PROXIMITY target (prose pair) with NO feed/calendar undermining → SEND (tier A)
  - a time-proximity/weak target UNDERMINED by a feed/calendar negative OR a nonstandard-day soft negative
    (#60) → REVIEW (tier B): the incidental-times case (a news post's times tripped the pair, or the pair is
    a weather/delay day's times) — don't auto-send, don't auto-drop; a human decides at gate@5
  - only a WEAK target → REVIEW (tier B)
  - a SUPPRESS/hard-negative with NO target → SUPPRESS (tier D): a confident drop
  - anything else (some evidence, nothing conclusive) → REVIEW (tier C)
`send`/`review`/`suppress` map onto the already-built 5/6 tier-gate: A auto-sends, B/C hold for a label, D rejects.
"""
HARD_NEGATIVE = {"lf_no_times", "lf_news_feed", "lf_calendar_widget", "lf_board", "lf_sports", "lf_transport"}
# Targets grounded in a real hours STRUCTURE (an intentional block/table/declaration) — trustworthy even on a
# feed page. vs. lf_prose_pair, whose evidence is just two nearby times, which a news post can incidentally trip.
# STRONG_STRUCTURAL = an INTENTIONAL hours block/declaration (footer/heading hours block, explicit minutes) —
# it beats feed/calendar noise UNCONDITIONALLY. TABLE_TARGET (`lf_time_table`) is structural but weaker: a
# bare times-TABLE can be a feed's or a calendar widget's OWN events/scores/agenda table, so it auto-sends
# only when NOT undermined by a feed/calendar negative (#528, measured: a lone table undermined by
# news_feed/calendar with no hours block = 14 tier-A false-sends demoted, 0 real targets — a real schedule
# delivered in a feed carries an hours heading, which lands in STRONG_STRUCTURAL and still sends).
STRONG_STRUCTURAL = {"lf_footer_hours", "lf_heading_hours", "lf_explicit_minutes"}
TABLE_TARGET = {"lf_time_table"}
# The full structural set — DERIVED so a new structural detector added to one set can't silently miss the
# other (it's used only to keep a real hours structure OUT of the incidental/prose-pair bucket).
STRUCTURAL_TARGET = STRONG_STRUCTURAL | TABLE_TARGET
# Negatives that specifically UNDERMINE incidental-time evidence — the times an lf_prose_pair/lf_weak_times
# saw are probably NOT the regular student day. Two flavors, ONE mechanism (the next such detector joins a
# set here instead of growing a new one-off boolean — #199 review):
#   hard: the times are the page's own post/event times (a feed or calendar widget)
#   soft (#60): a real bell-shape but the WRONG schedule (weather / remote / delay / early-dismissal) —
#     don't auto-send the pair, route to review so a human confirms the standard day. Structural targets
#     (footer block / schedule table / explicit minutes) still auto-send: the structure IS the standard
#     day even amid delay language, and structure beats noise (the combiner's core rule).
UNDERMINE_TIMES = {"lf_news_feed", "lf_calendar_widget"}
UNDERMINE_TIMES_SOFT = {"lf_nonstandard_day"}


def _by(votes, polarity, strength=None):
    return [v for v in votes if v["polarity"] == polarity and (strength is None or v["strength"] == strength)]


def combine(votes: list) -> dict:
    """votes: list of vote-dicts from detectors.run_all(). Returns
    {decision, tier, sort_score, category, reasons[], fired[]}."""
    strong_t = _by(votes, "target", "strong")
    weak_t = _by(votes, "target", "weak")
    strong_structural = [v for v in strong_t if v["name"] in STRONG_STRUCTURAL]
    table = [v for v in strong_t if v["name"] in TABLE_TARGET]
    incidental = [v for v in strong_t if v["name"] not in STRUCTURAL_TARGET]
    suppress = [v for v in votes if v["polarity"] == "suppress"]
    hard_neg = [v for v in votes if v["polarity"] == "negative" and v["strength"] == "strong"
                and v["name"] in HARD_NEGATIVE]
    soft_neg = [v for v in votes if v["polarity"] == "negative" and v["strength"] == "soft"]
    # ONE hard-undermine test, reused: a firing feed/calendar negative, OR a STRONG wrong-day negative
    # (#537 follow-on: the non-regular-day term titles the schedule / sits at the times — the DASD
    # "Early Dismissal Bell Schedule" table shape, where the table's times ARE the irregular day's).
    # `undermined` (hard OR a soft #60 wrong-day mention) demotes an incidental/weak pair; a TABLE is
    # undermined by the HARD test only — a real schedule TABLE still survives a soft wrong-day MENTION
    # (structure beats a bare mention, #60/#528), but not a positional wrong-day claim. Keeping these as
    # ONE expression stops the variants from silently desyncing.
    wrong_day_strong = [v for v in votes if v["polarity"] == "negative" and v["strength"] == "strong"
                        and v["name"] in UNDERMINE_TIMES_SOFT]
    hard_undermined = any(v["name"] in UNDERMINE_TIMES for v in hard_neg) or bool(wrong_day_strong)
    undermined = hard_undermined or any(v["name"] in UNDERMINE_TIMES_SOFT for v in soft_neg)

    tconf = max((v["confidence"] for v in strong_t), default=0.0)
    nconf = max((v["confidence"] for v in hard_neg + suppress), default=0.0)

    if strong_structural:                              # an intentional hours block/declaration beats feed/calendar/wrong-day noise
        decision, tier, winner = "send", "A", max(strong_structural, key=lambda v: v["confidence"])
    elif table:                                        # a schedule table sends UNLESS a feed/calendar owns it (#528) -> review
        decision, tier = ("review", "B") if hard_undermined else ("send", "A")
        winner = max(table, key=lambda v: v["confidence"])
    elif incidental and not undermined:                # a clean prose start/end pair, standard day
        decision, tier, winner = "send", "A", max(incidental, key=lambda v: v["confidence"])
    elif (incidental or weak_t) and undermined:        # incidental times undermined (feed/calendar/wrong-day) -> human decides
        decision, tier, winner = "review", "B", max(incidental + weak_t, key=lambda v: v["confidence"])
    elif weak_t:
        decision, tier, winner = "review", "B", max(weak_t, key=lambda v: v["confidence"])
    elif suppress:
        decision, tier, winner = "suppress", "D", max(suppress, key=lambda v: v["confidence"])
    elif hard_neg:
        decision, tier, winner = "suppress", "D", max(hard_neg, key=lambda v: v["confidence"])
    elif soft_neg or wrong_day_strong:                 # wrong-day-only evidence is review, never suppress
        decision, tier, winner = "review", "C", max(soft_neg + wrong_day_strong, key=lambda v: v["confidence"])
    else:
        decision, tier, winner = "suppress", "D", None

    # a transparent, legible sort score: target confidence up, negatives down (intra-tier ordering only).
    # wrong_day_strong counts with the soft term (it is a wrong-DAY claim, not a wrong-CONTENT one).
    sort_score = round(10 * tconf - 6 * nconf - 3 * sum(v["confidence"] for v in soft_neg + wrong_day_strong), 3)
    # category_hypothesis = the winning TARGET shape (v2.1); a non-target winner predicts the primary
    # 'target_absent' (the specific confounder is a facet, scored per-detector, not the primary guess).
    # NB: a record demoted to REVIEW on an undermined target (a feed-owned table, or an undermined prose
    # pair) keeps that target SHAPE as its hypothesis — deliberately: the shape is the human's hint at
    # gate@5 ("looks like a bell table — is it the school's or the feed's own?"), and the feed/calendar
    # confounder already travels in reasons[]. The decision (review), not the category, gates dispatch.
    category = winner["category"] if (winner and winner["polarity"] == "target") else "target_absent"
    reasons = [v["reason"] for v in sorted(votes, key=lambda v: -v["confidence"])]
    return {"decision": decision, "tier": tier, "sort_score": sort_score, "category": category,
            "reasons": reasons, "fired": [v["name"] for v in votes]}


def score_record(sig: dict, params=None) -> dict:
    """Convenience: run the detectors on `sig` and combine — returns the combine() dict PLUS the raw votes
    (stored into signals_json so the harness can compute per-detector diagnostics + the UI can pre-fill facets)."""
    from infrastructure.acquisition.stage5_filter import detectors as D
    votes = D.run_all(sig, params)
    out = combine(votes)
    out["votes"] = votes
    return out
