#!/usr/bin/env python3
"""Frontier / grid search over the Stage 5 V2 detector params (REQ-096) — ADVISORY, not auto-applied.

Re-scores the LABELED records under candidate DETECTOR/COMBINER params and reports the
precision/recall frontier subject to a hard RECALL FLOOR, ranked by precision (= Stage 7 cost
saved). The human (and Claude, in chat) inspects the frontier and the per-record movements;
nothing is written to config automatically. A chosen move is recorded to the tuning ledger (REQ-095).

Issue #56: this tool used to grid-search the V1 `tier_and_category` cascade, which REQ-113 deleted
in favor of the labeling-function DETECTORS + COMBINER (`detectors.py` + `combiner.py`). The knob
surface is now `detectors.DEFAULT_DETECTOR_PARAMS` (table_min_times / table_min_periods /
neg_dom_min — the thresholds every detector reads); the re-score path is the LIVE one:
`combiner.score_record(sig, params)` -> a derived tier letter, scored with the same harness metrics.

Why this needs no re-ingest: the review DB already stores each record's full signal vector
(`signals_json`) and the human `primary_label`. So we load those once and re-run the PARAMETERIZED
detectors+combiner over the stored signals — instant, deterministic, exact. Metrics reuse the
harness (`tier_target_metrics`); scoring reuses the real combiner. Nothing reimplemented.

Overfitting guard (research-confirmed): LeaveOneGroupOut **by district** — records within a district
are correlated (same CMS chrome/templates), so plain k-fold would leak. At small n the CV estimate is
high-variance; it is REPORTED alongside the in-sample number, never a gate (CV detects overfit, it
does not prevent it). See docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE5_FILTER_DESIGN_2026-06.md.

Usage:
    python3 frontier.py            # grid over the detector-threshold knobs (canonical A+B floor, #208)
    python3 frontier.py --cv       # + LOGO-by-district on the best feasible
"""
import argparse
import itertools
import json

from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import build_signals as BS  # noqa: E402  (TARGET_LABELS)
from infrastructure.acquisition.stage5_filter import combiner as COMB  # noqa: E402    (the LIVE V2 scorer)
from infrastructure.acquisition.stage5_filter import detectors as DET  # noqa: E402    (DEFAULT_DETECTOR_PARAMS — the knob surface)
from infrastructure.acquisition.stage5_filter import harness  # noqa: E402             (tier_target_metrics — the metric of record)
from infrastructure.acquisition.common import db as gdb  # noqa: E402  (governance Postgres — REQ-103)

TARGET = BS.TARGET_LABELS

# The default grid: the full V2 detector-threshold knob surface (detectors.DEFAULT_DETECTOR_PARAMS).
# Small, enumerable, exact — each knob one step tighter/looser around the shipped default.
DEFAULT_GRID = {
    "table_min_times": [3, 4, 5],     # lf_time_table: dense in-window table times (with a positive kw)
    "table_min_periods": [1, 2, 3],   # lf_time_table: period-row structure floor
    "neg_dom_min": [2, 3, 4],         # lf_board/sports/transport + _neg_dominant: negative-class dominance
}


# ----------------------------- load (no re-ingest) -----------------------------
def load_labeled(con):
    """[(district_id, rec_key, signals_dict, primary_label), ...] over LABELED, non-duplicate,
    canonical (cluster-rep or singleton) records — the same population the harness scores."""
    rows = con.execute(text(
        """SELECT r.district_id, r.rec_key, r.signals_json, l.primary_label
           FROM record r JOIN label l ON l.rec_key = r.rec_key
           WHERE l.status != 'unlabeled' AND l.primary_label IS NOT NULL
             AND r.duplicate_of IS NULL
             AND (r.is_cluster_rep = 1 OR r.cluster_id IS NULL)""")).fetchall()
    return [(d, rk, json.loads(sj), lab) for d, rk, sj, lab in rows]


# ----------------------------- re-score + evaluate -----------------------------
def _retier(records, params):
    """[(district, rec_key, tier, is_target), ...] under candidate detector params — the LIVE V2
    scoring path (detectors.run_all -> combiner.combine), tier = the derived letter."""
    out = []
    for dist, rk, sig, lab in records:
        tier = COMB.score_record(sig, params)["tier"]
        out.append((dist, rk, tier, lab in TARGET))
    return out


def evaluate(records, params):
    """Harness tier-vs-target metrics for one candidate params over all records."""
    retiered = _retier(records, params)
    return harness.tier_target_metrics([(t, g) for _d, _rk, t, g in retiered])


def _moves(records, baseline, params):
    """Records whose tier changes from baseline -> params (the 'why' surfaced for the human)."""
    base = {rk: t for _d, rk, t, _g in _retier(records, baseline)}
    out = []
    for dist, rk, t, g in _retier(records, params):
        if base[rk] != t:
            out.append({"rec_key": rk, "district": dist, "from": base[rk], "to": t, "is_target": g})
    return sorted(out, key=lambda m: (m["from"], m["to"], m["rec_key"]))


def grid_search(records, grid=None, recall_floor=None, positive_tier="A", floor_tier=None, baseline=None):
    """Enumerate the grid, score each config, keep those FEASIBLE (their `floor_tier` recall >= floor),
    rank by `positive_tier` PRECISION desc. The floor tier and the ranking tier are DELIBERATELY different
    (#208): the floor defends A+B recall (reaches-review — don't drop a target to tier D), while we optimize
    tier-A PRECISION (the auto-send bucket). Both default to the canonical harness.FLOOR_TIER/RECALL_FLOOR.
    Returns [{params, metrics, feasible, recall (floor_tier), precision (positive_tier), moves}, ...]."""
    recall_floor = harness.RECALL_FLOOR if recall_floor is None else recall_floor
    floor_tier = harness.FLOOR_TIER if floor_tier is None else floor_tier
    valid = ("A", "A+B")   # the only thresholds tier_target_metrics builds — fail clean, not KeyError
    if positive_tier not in valid or floor_tier not in valid:
        raise ValueError(f"positive_tier/floor_tier must be one of {valid} "
                         f"(got positive_tier={positive_tier!r}, floor_tier={floor_tier!r})")
    grid = grid or DEFAULT_GRID
    baseline = baseline or DET.DEFAULT_DETECTOR_PARAMS
    keys = list(grid)
    results = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = {**baseline, **dict(zip(keys, combo))}
        m = evaluate(records, params)
        rec = m["thresholds"][floor_tier]["recall"]            # the FLOORED recall (A+B, reaches-review)
        prec = m["thresholds"][positive_tier]["precision"]     # the RANKED precision (A, auto-send)
        feasible = rec is not None and rec >= recall_floor
        results.append({"params": {k: params[k] for k in keys}, "metrics": m,
                        "feasible": feasible, "recall": rec, "precision": prec,
                        "moves": _moves(records, baseline, params)})
    # feasible first, then precision desc (None precision sinks to the bottom)
    results.sort(key=lambda r: (r["feasible"], r["precision"] if r["precision"] is not None else -1),
                 reverse=True)
    return [r for r in results if r["feasible"]] or results


# ----------------------------- LOGO-by-district guard -----------------------------
def logo_cv(records, params, positive_tier="A"):
    """LeaveOneGroupOut by district: for each district, score the HELD-OUT district under `params`
    (thresholds aren't fit per-fold here — they're global — so this measures how the global config
    generalizes across districts). Reports mean/std of held-out precision/recall. High std => the
    config leans on particular districts."""
    retiered = _retier(records, params)
    by_dist = {}
    for dist, rk, tier, g in retiered:
        by_dist.setdefault(dist, []).append((tier, g))
    districts = sorted(by_dist)

    def _pr(rows):
        tp = sum(1 for t, g in rows if t == positive_tier and g)
        fp = sum(1 for t, g in rows if t == positive_tier and not g)
        fn = sum(1 for t, g in rows if t != positive_tier and g)
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        return prec, rec

    precs, recs = [], []
    for held in districts:
        prec, rec = _pr(by_dist[held])           # metrics ON the held-out district
        if prec is not None:
            precs.append(prec)
        if rec is not None:
            recs.append(rec)

    def _mean(xs):
        return sum(xs) / len(xs) if xs else None

    def _std(xs):
        if len(xs) < 2:
            return 0.0
        m = _mean(xs)
        return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5

    return {"n_folds": len(districts),
            "precision_mean": _mean(precs), "precision_std": _std(precs),
            "recall_mean": _mean(recs), "recall_std": _std(recs),
            "per_district": {d: dict(zip(("precision", "recall"), _pr(by_dist[d]))) for d in districts}}


# ----------------------------- CLI -----------------------------
def _fmt(x):
    return f"{x:.4f}" if isinstance(x, float) else ("  —  " if x is None else str(x))


def main():
    ap = argparse.ArgumentParser(description="Stage 5 frontier / grid search over the V2 detector params (REQ-096, advisory)")
    ap.add_argument("--recall-floor", type=float, default=harness.RECALL_FLOOR)   # canonical (#208)
    ap.add_argument("--tier", default="A", choices=["A", "A+B"], help="positive tier to RANK precision on")
    ap.add_argument("--floor-tier", default=harness.FLOOR_TIER, choices=["A", "A+B"],
                    help="tier whose recall the floor defends (default A+B)")
    ap.add_argument("--cv", action="store_true", help="also run LOGO-by-district on the top config")
    a = ap.parse_args()

    with gdb.session_scope() as con:
        records = load_labeled(con)
    base_m = evaluate(records, DET.DEFAULT_DETECTOR_PARAMS)["thresholds"][a.tier]
    print(f"loaded {len(records)} labeled records "
          f"({sum(1 for *_ , lab in records if lab in TARGET)} targets)")
    print(f"baseline tier-{a.tier}: precision={_fmt(base_m['precision'])} recall={_fmt(base_m['recall'])} "
          f"(tp={base_m['tp']} fp={base_m['fp']} fn={base_m['fn']})")
    print(f"\nfrontier (floor: tier-{a.floor_tier} recall >= {a.recall_floor}; ranked by tier-{a.tier} precision):")
    res = grid_search(records, recall_floor=a.recall_floor, positive_tier=a.tier, floor_tier=a.floor_tier)
    for r in res[:10]:
        flag = "" if r["feasible"] else "  (INFEASIBLE — best available)"
        mv = "; ".join(f"{m['rec_key']} {m['from']}->{m['to']}{'*' if m['is_target'] else ''}"
                       for m in r["moves"]) or "no moves vs baseline"
        print(f"  {r['params']}  precision={_fmt(r['precision'])} recall={_fmt(r['recall'])}{flag}")
        print(f"      moves: {mv}")
    if a.cv and res:
        cv = logo_cv(records, {**DET.DEFAULT_DETECTOR_PARAMS, **res[0]["params"]}, positive_tier=a.tier)
        print(f"\nLOGO-by-district on top config ({cv['n_folds']} folds): "
              f"precision {_fmt(cv['precision_mean'])}±{_fmt(cv['precision_std'])}  "
              f"recall {_fmt(cv['recall_mean'])}±{_fmt(cv['recall_std'])}")
        print("  (high std => config leans on particular districts; at small n treat as directional)")


if __name__ == "__main__":
    main()
