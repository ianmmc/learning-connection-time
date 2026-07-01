#!/usr/bin/env python3
"""Stage 5 V2 COMBINER — reduce detector votes to a routing decision (REQ-113).

Takes the votes emitted by `detectors.run_all(sig)` and reduces them to the decision Stage 6 consumes:
`send` / `suppress` / `review`, plus a derived tier letter (A/B/C/D) kept for human legibility and
back-compat with the existing release tier-gate + attention model, and a weak category hypothesis.

Deliberately a TRANSPARENT rule (not a learned model) — the research's "start with a transparent weighted
vote; only graduate to a Snorkel LabelModel once per-detector diagnostics show heterogeneous accuracy at
medium label density" (STAGE5_TUNING_NOTES Part C). PURE: votes in, decision out.

Decision policy (recall-biased — the expensive error is dropping a real schedule before the human sees it):
  - a STRUCTURAL target (footer hours / schedule table / explicit minutes / heading hours) → SEND (tier A):
    these are real hours blocks, trustworthy even amid negatives (a feed page with a real footer schedule IS a target)
  - a TIME-PROXIMITY target (prose pair) with NO feed/calendar undermining → SEND (tier A)
  - a time-proximity/weak target UNDERMINED by a feed/calendar negative → REVIEW (tier B): the incidental-times
    case (a news post's times tripped the pair) — don't auto-send, don't auto-drop; a human decides at gate@5
  - only a WEAK target → REVIEW (tier B)
  - a SUPPRESS/hard-negative with NO target → SUPPRESS (tier D): a confident drop
  - anything else (some evidence, nothing conclusive) → REVIEW (tier C)
`send`/`review`/`suppress` map onto the already-built 5/6 tier-gate: A auto-sends, B/C hold for a label, D rejects.
"""
HARD_NEGATIVE = {"lf_no_times", "lf_news_feed", "lf_calendar_widget", "lf_board", "lf_sports", "lf_transport"}
# Targets grounded in a real hours STRUCTURE (an intentional block/table/declaration) — trustworthy even on a
# feed page. vs. lf_prose_pair, whose evidence is just two nearby times, which a news post can incidentally trip.
STRUCTURAL_TARGET = {"lf_footer_hours", "lf_heading_hours", "lf_time_table", "lf_explicit_minutes"}
# Negatives that specifically UNDERMINE incidental-time evidence (the times are the feed's own post/event times).
UNDERMINE_TIMES = {"lf_news_feed", "lf_calendar_widget"}


def _by(votes, polarity, strength=None):
    return [v for v in votes if v["polarity"] == polarity and (strength is None or v["strength"] == strength)]


def combine(votes: list) -> dict:
    """votes: list of vote-dicts from detectors.run_all(). Returns
    {decision, tier, sort_score, category, reasons[], fired[]}."""
    strong_t = _by(votes, "target", "strong")
    weak_t = _by(votes, "target", "weak")
    structural = [v for v in strong_t if v["name"] in STRUCTURAL_TARGET]
    incidental = [v for v in strong_t if v["name"] not in STRUCTURAL_TARGET]
    suppress = [v for v in votes if v["polarity"] == "suppress"]
    hard_neg = [v for v in votes if v["polarity"] == "negative" and v["strength"] == "strong"
                and v["name"] in HARD_NEGATIVE]
    soft_neg = [v for v in votes if v["polarity"] == "negative" and v["strength"] == "soft"]
    undermines = any(v["name"] in UNDERMINE_TIMES for v in hard_neg)

    tconf = max((v["confidence"] for v in strong_t), default=0.0)
    nconf = max((v["confidence"] for v in hard_neg + suppress), default=0.0)

    if structural:                                     # a real hours structure beats feed/negative noise
        decision, tier, winner = "send", "A", max(structural, key=lambda v: v["confidence"])
    elif incidental and not undermines:                # a prose start/end pair, no feed undermining it
        decision, tier, winner = "send", "A", max(incidental, key=lambda v: v["confidence"])
    elif (incidental or weak_t) and undermines:        # incidental times on a feed/calendar page -> human decides
        decision, tier, winner = "review", "B", max(incidental + weak_t, key=lambda v: v["confidence"])
    elif weak_t:
        decision, tier, winner = "review", "B", max(weak_t, key=lambda v: v["confidence"])
    elif suppress:
        decision, tier, winner = "suppress", "D", max(suppress, key=lambda v: v["confidence"])
    elif hard_neg:
        decision, tier, winner = "suppress", "D", max(hard_neg, key=lambda v: v["confidence"])
    elif soft_neg:
        decision, tier, winner = "review", "C", max(soft_neg, key=lambda v: v["confidence"])
    else:
        decision, tier, winner = "suppress", "D", None

    # a transparent, legible sort score: target confidence up, negatives down (intra-tier ordering only).
    sort_score = round(10 * tconf - 6 * nconf - 3 * sum(v["confidence"] for v in soft_neg), 3)
    category = winner["category"] if winner else "none"
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
