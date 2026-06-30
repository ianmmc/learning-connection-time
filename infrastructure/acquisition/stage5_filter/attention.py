"""Stage 5 ATTENTION scoring — "where does my judgment move us forward?" (the district-driven console).

Attention is the INVERSE of automatable-confidence. It is NOT "most likely a target": a clean tier-A page
(headline + a dense time table) has high target-likelihood but LOW attention — it's a swift yes, first to
automate. Attention peaks instead at:
  - explicit follow-up FLAGS (a human already said "decide what to do here"), and
  - PROMISING-BUT-UNRESOLVED records: a strong schedule signal the text didn't pin down (image-only / OCR
    gap, signal-vs-tier disagreement, a schedule buried in a long handbook) — exactly where the human eye
    is decisive AND where we learn to improve the filter.
…and troughs at clean obvious targets and already-resolved records. The score shrinks as the process
learns (the clean-yes zone auto-resolves), so it doubles as the ramp-up dashboard.

Per record we emit a structured {score, reasons[]} — the reasons are the rationale CHIPS the console
shows (and the greppable diagnostic). Rolled up per district so the left pane sorts/groups attention-first.
Config-as-data + harness-measurable: weights/thresholds live in common/config/stage5_attention.json.
"""
from infrastructure.acquisition.common import config_loader

# Highest human-attention first. The DOMINANT reason (first applicable in this order) sets the score;
# all applicable reasons travel in reasons[] for the chips.
REASON_ORDER = ["manual_flag", "image_only", "signal_text_disagree", "buried_long_doc",
                "ambiguous", "clean_target", "low_signal", "resolved"]


def load_config() -> dict:
    """The attention weights + thresholds (provenance-bearing knob). Read once per ingest pass."""
    doc = config_loader.load("stage5_attention")
    return {"weights": doc["weights"], "thresholds": doc.get("thresholds", {})}


def _has_schedule_signal(sig: dict) -> bool:
    """A positive bell-schedule indicator of ANY kind — a positive keyword, a time-proximity pair, or an
    explicit instructional-time declaration. 'The page claims to be about a schedule.'"""
    return bool(sig.get("positive_kw")) or sig.get("proximity_pairs", 0) >= 1 or bool(sig.get("instructional_time"))


def record_reasons(sig: dict, tier: str, label_status: str | None, *, has_flag: bool, thresholds: dict) -> list:
    """All applicable attention reason codes for one record, ordered by REASON_ORDER (dominant first).
    `sig` = record.signals_json; `tier` = record.tier; `label_status` from the label table; `has_flag`
    = an unresolved follow-up flag on this record."""
    resolved = bool(label_status) and label_status != "unlabeled"
    reasons: list = []
    if has_flag:
        reasons.append("manual_flag")           # an active directive outranks everything, even if labeled
    if resolved:
        # a resolved record is done — it contributes no further attention (a flag still shows on top)
        reasons.append("resolved")
        return reasons

    if sig.get("visual_text_gap"):
        reasons.append("image_only")             # strong visual, text below the usable bar (OCR/vision gap)
    if _has_schedule_signal(sig) and tier in ("C", "D") and not sig.get("visual_text_gap"):
        reasons.append("signal_text_disagree")   # the signal says schedule, the deterministic tier doesn't
    if sig.get("is_handbook") and sig.get("harvest_pages"):
        reasons.append("buried_long_doc")        # a schedule likely on a few pages of a long document

    clean = tier == "A" and sig.get("has_table") and sig.get("n_times_in_window", 0) >= thresholds.get("clean_target_win_min", 3)
    if not reasons:
        if clean:
            reasons.append("clean_target")       # the obvious yes — low attention, first to automate
        elif tier in ("A", "B", "C") and _has_schedule_signal(sig):
            reasons.append("ambiguous")          # mixed signals, a genuine judgment call
        else:
            reasons.append("low_signal")         # confident not-a-target / nothing to act on — lowest value
    # de-dup preserving REASON_ORDER
    return sorted(set(reasons), key=REASON_ORDER.index)


def record_attention(sig: dict, tier: str, label_status: str | None, cfg: dict, *, has_flag: bool = False) -> dict:
    """{score, reasons} for one record. score = the weight of the DOMINANT (highest-priority) reason."""
    reasons = record_reasons(sig, tier, label_status, has_flag=has_flag, thresholds=cfg["thresholds"])
    score = max((cfg["weights"].get(r, 0) for r in reasons), default=0)
    return {"score": float(score), "reasons": reasons}


def district_attention(record_attentions: list, cfg: dict, *, has_district_flag: bool = False) -> dict:
    """Roll up a district's records into a single {score, reasons}. The NEEDIEST record sets the base
    (max), with a small capped volume nudge so many needy records outrank one. A district-level
    follow-up flag floors the score at the manual-flag weight (a directive about the district is top).
    reasons = the union of the records' dominant reasons (+ manual_flag if district-flagged), ordered."""
    w, th = cfg["weights"], cfg["thresholds"]
    active = [r for r in record_attentions if r["score"] > 0]          # resolved (0) records don't pull
    base = max((r["score"] for r in active), default=0.0)
    n_extra = max(0, min(len(active) - 1, th.get("district_volume_cap", 10)))
    score = base + n_extra * th.get("district_volume_per_extra", 2)
    dominant = sorted({r["reasons"][0] for r in active if r["reasons"]}, key=REASON_ORDER.index)
    if has_district_flag:
        score = max(score, w.get("manual_flag", 100))
        dominant = sorted(set(dominant) | {"manual_flag"}, key=REASON_ORDER.index)
    if not dominant:
        dominant = ["resolved"]                                       # every record resolved -> district done
    return {"score": float(score), "reasons": dominant}
