#!/usr/bin/env python3
"""Stage-5 drift detector (REQ-097, #75) — alert when newly-labeled data degrades the LIVE config
enough to warrant a retune. ADVISORY ONLY: surfaces "retune recommended" in the governance console
and never auto-retunes (the CP ramp-up posture).

The series is the fingerprinted SCORECARD directory (harness.py output), not the tuning-ledger
episodes: episodes record deltas + provenance but not levels/counts, while each scorecard carries
the absolute tier metrics WITH their binomial counts (tp/fp/fn) — exactly what a Bernoulli CUSUM
and a Wilson interval need. The ledger remains the decision log; the scorecards are the monitor's
time series (both are REQ-095 outputs of the same measured-pass discipline).

The config-induced vs. new-district distinction (REQ-097 criterion 3) is STRUCTURAL: the series is
segmented by config fingerprint, and the CUSUM runs only within the LATEST segment — a config
change starts a fresh segment (its own before→after delta is the tuning move's expected effect,
already recorded as a ledger episode), while movement across scorecards of the SAME config can only
come from new labels/data (the world shifted → the drift this detector exists to catch; the
2026-06-30 V1 incident — 85%→69% tier-A precision from 12→59 districts at fixed config — was
caught by hand exactly this way).

Two streams, two-gate each (CUSUM trip AND Wilson lower bound breach). The Wilson gate stops a
LONE noisy small-n scorecard from alerting in isolation; it does not — and should not — stop
accumulated cross-scorecard CUSUM evidence from concluding via a final small-n point that
corroborates the trend (that accumulation IS the CUSUM's job; #543-#547 review nuance):
  - floored recall (harness.FLOOR_TIER, the #208 policy floor) vs RECALL_FLOOR
  - tier-A precision vs a per-segment reference = the segment's FIRST scorecard (the level the
    config was adopted at) minus PRECISION_MARGIN — there is no policy precision floor, so the
    adoption-time level is the defensible p0. JURISDICTION NOTE (#543-#547 review): this baseline
    is deliberately self-referential, so drift catches POST-ADOPTION degradation only — a config
    that ships already-regressed is the #212 group-aware non-inferiority PROMOTION GATE's job to
    stop at adoption time (promotion_gate.py, the ledger's gate-verdict attachment), not this
    monitor's. The verdict carries `historical_best` (the best tier-A precision any scorecard in
    the whole series ever reached, cross-config) as an informational reference so a human reading
    the badge can see an adoption-level gap the CUSUM structurally cannot alert on.
"""
import argparse
import json
import math
from pathlib import Path

from statsmodels.stats.proportion import proportion_confint  # noqa: E402  (already a package dependency — promotion_gate.py)

from infrastructure.acquisition.common import paths  # noqa: E402
from infrastructure.acquisition.stage5_filter import harness  # noqa: E402

CUSUM_H = 4.0                 # log-likelihood alert threshold (small-series regime; ~e^4 evidence ratio)
RECALL_P1_DELTA = 0.03        # H1 for the recall stream = floor − this (the degraded state tested for)
PRECISION_MARGIN = 0.05       # precision p0 = segment-adoption level − this
_EPS = 1e-6


def scorecard_dir() -> Path:
    return paths.STAGE5_DIR / "scorecards"


def load_series(directory=None) -> list:
    """Scorecard summaries sorted by generated_at — one point per scorecard."""
    d = Path(directory or scorecard_dir())
    pts = []
    for p in sorted(d.glob("scorecard_*.json")):
        try:
            card = json.loads(p.read_text())
            pts.append(_point(card))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue   # a malformed/legacy scorecard is skipped, never fatal to the monitor
    pts.sort(key=lambda x: x["at"] or "")
    return pts


def _point(card: dict) -> dict:
    t = card["tier_vs_target"]["thresholds"]
    a, fl = t["A"], t[harness.FLOOR_TIER]
    return {"at": card.get("generated_at"), "config": card["fingerprints"]["config"],
            "precision": a["precision"], "prec_k": a["tp"], "prec_n": a["tp"] + a["fp"],
            "recall": fl["recall"], "rec_k": fl["tp"], "rec_n": fl["tp"] + fl["fn"]}


def wilson_lower(k: int, n: int):
    """Lower bound of the 95% Wilson score interval — the small-n gate (REQ-097 criterion 2).
    Precondition 0 <= k <= n; k is clamped defensively (the #543-#547 review found the raw formula
    raised a math-domain error on k>n). Delegates to statsmodels' proportion_confint
    (method='wilson', alpha=0.05 ↔ z=1.96) — already a direct dependency used in this same package
    (promotion_gate.py) — instead of a hand-maintained transcription of the formula."""
    if not n:
        return None
    k = min(max(int(k), 0), int(n))
    lo, _ = proportion_confint(k, n, alpha=0.05, method="wilson")
    return float(lo)


def _llr(k: int, n: int, p0: float, p1: float) -> float:
    """Bernoulli log-likelihood ratio of the degraded state (p1) vs the reference (p0)."""
    return k * math.log(p1 / p0) + (n - k) * math.log((1 - p1) / (1 - p0))


def _stream(points: list, k_key: str, n_key: str, p0: float, p1: float) -> dict:
    """One-sided CUSUM (accumulating evidence of sitting BELOW p0) + the Wilson two-gate on the
    latest point. p1 < p0 strictly (clamped)."""
    p0 = min(max(p0, 0.05), 1 - _EPS)
    p1 = min(max(p1, 0.05 - _EPS), p0 - _EPS)
    s = 0.0
    for pt in points:
        s = max(0.0, s + _llr(pt[k_key], pt[n_key], p0, p1))
    last = points[-1]
    wl = wilson_lower(last[k_key], last[n_key])   # gates a LONE noisy point, not accumulated evidence
    tripped, breach = s > CUSUM_H, (wl is not None and wl < p0)
    return {"cusum": round(s, 3), "tripped": tripped, "p0": round(p0, 4),
            "latest": round(last[k_key] / last[n_key], 4) if last[n_key] else None,
            "wilson_lower": round(wl, 4) if wl is not None else None, "breach": breach,
            "alert": tripped and breach}


# The inert per-stream verdict for a segment with no measurable points (e.g. a fresh config whose
# only scorecard has zero tier-A predictions — harness sets precision=None there, a documented
# shape that crashed the unguarded first build; #543-#547 review). Never alerts, never crashes.
_INERT_STREAM = {"cusum": 0.0, "tripped": False, "p0": None, "latest": None,
                 "wilson_lower": None, "breach": False, "alert": False,
                 "note": "no measurable points in this segment"}


def detect(directory=None) -> dict:
    """The REQ-097 verdict over the LATEST config segment. Pure read; never mutates anything."""
    series = load_series(directory)
    if not series:
        return {"retune_recommended": False, "n_points": 0, "config": None,
                "note": "no scorecards yet — nothing to monitor"}
    live = series[-1]["config"]
    seg = [pt for pt in series if pt["config"] == live]   # oldest first (series already sorted)
    rec_pts = [pt for pt in seg if pt["rec_n"]]
    recall = (_stream(rec_pts, "rec_k", "rec_n", p0=harness.RECALL_FLOOR,
                      p1=harness.RECALL_FLOOR - RECALL_P1_DELTA)
              if rec_pts else dict(_INERT_STREAM))
    prec_pts = [pt for pt in seg if pt["prec_n"] and pt["precision"] is not None]
    if prec_pts:
        prec_base = prec_pts[0]["precision"]
        precision = _stream(prec_pts, "prec_k", "prec_n", p0=prec_base - PRECISION_MARGIN,
                            p1=prec_base - 2 * PRECISION_MARGIN)
        precision["baseline"] = round(prec_base, 4)
    else:
        precision = dict(_INERT_STREAM)
    # Informational, cross-config: the best tier-A precision ANY scorecard ever reached. The CUSUM's
    # self-referential baseline structurally cannot alert on a config ADOPTED below history (that is
    # the #212 promotion gate's jurisdiction — see the module docstring); this field lets the human
    # reading the verdict see that gap anyway.
    hist = [pt["precision"] for pt in series if pt.get("precision") is not None]
    precision["historical_best"] = round(max(hist), 4) if hist else None
    return {"retune_recommended": recall["alert"] or precision["alert"],
            "config": live, "n_points": len(seg),
            "recall": {**recall, "floor_tier": harness.FLOOR_TIER},
            "precision": precision,
            "posture": "advisory — never auto-retunes (REQ-097 / CP ramp-up)"}


def main():
    ap = argparse.ArgumentParser(description="Stage-5 drift detector (REQ-097) — advisory verdict")
    ap.add_argument("--dir", default=None, help="scorecard directory (default: the live one)")
    a = ap.parse_args()
    print(json.dumps(detect(a.dir), indent=2))


if __name__ == "__main__":
    main()
