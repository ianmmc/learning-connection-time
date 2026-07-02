#!/usr/bin/env python3
"""Measurement harness (REQ-090) — score the current config + deterministic signals against the
human labels, emitting a reproducible SCORECARD.

A score is only meaningful as the tuple (config x label-set x data) -> metrics, so every scorecard
stamps three fingerprints (config version, label-set hash, data/ingest snapshot) and is therefore
re-derivable/auditable. Read-only over the governance Postgres signal tables (common/db.py). Run ON
DEMAND or at batch completion — never per-label-write.

v1 scores the CURRENTLY-INGESTED state (the config that produced the live signal tables). To compare
config A vs B: re-ingest under B (cheap, Tier-0) and re-run the harness — the two scorecards are
comparable via their stamped fingerprints. (In-memory candidate-config scoring without re-ingest is
a later enhancement.)

Usage:  python3 harness.py [--db <path>] [--no-write]   (prints a summary; writes a scorecard JSON)
"""
import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import build_signals as BS   # noqa: E402  (TARGET_LABELS + the path constants)
from infrastructure.acquisition.common import paths                  # noqa: E402
from infrastructure.acquisition.common import db as gdb              # noqa: E402  (governance Postgres — REQ-103)

TARGET = BS.TARGET_LABELS

# Coarse hub/per-school axis so the (different-vocabulary) guessed and labeled topologies can be
# compared at all. Values outside {hub, per_school} don't make a hub-vs-per-school claim.
GUESS_COARSE = {"hub": "hub", "per_school": "per_school", "unknown": "unknown"}
LABEL_COARSE = {"district_hub": "hub", "mixed": "hub", "per_school": "per_school",
                "incomplete_coverage": "per_school", "single_school": "single",
                "none_found": "none", "unknown": "unknown"}


# ----------------------------- pure metric functions (testable) -----------------------------
def tier_target_metrics(rows):
    """rows: iterable of (tier, is_target: bool) over LABELED records. Returns per-tier target
    counts + precision/recall/F1 treating tier in {A} and {A,B} as the positive prediction."""
    per_tier = defaultdict(lambda: {"target": 0, "nontarget": 0})
    rows = list(rows)
    for tier, is_target in rows:
        per_tier[tier]["target" if is_target else "nontarget"] += 1
    thresholds = {}
    for name, positive in (("A", {"A"}), ("A+B", {"A", "B"})):
        tp = sum(1 for t, g in rows if t in positive and g)
        fp = sum(1 for t, g in rows if t in positive and not g)
        fn = sum(1 for t, g in rows if t not in positive and g)
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else None
        thresholds[name] = {"tp": tp, "fp": fp, "fn": fn,
                            "precision": _r(prec), "recall": _r(rec), "f1": _r(f1)}
    return {"per_tier": {k: dict(v) for k, v in sorted(per_tier.items())}, "thresholds": thresholds}


def category_accuracy(rows):
    """rows: iterable of (category_hypothesis, primary_label) over LABELED records. Fraction where
    the script's category guess equals the human label, plus a per-true-label breakdown."""
    rows = list(rows)
    n = len(rows)
    correct = sum(1 for guess, label in rows if guess == label)
    per_label = defaultdict(lambda: {"n": 0, "correct": 0})
    for guess, label in rows:
        per_label[label]["n"] += 1
        if guess == label:
            per_label[label]["correct"] += 1
    return {"overall": _r(correct / n if n else None), "n": n, "correct": correct,
            "per_label": {k: dict(v) for k, v in sorted(per_label.items())}}


def topology_report(rows):
    """rows: iterable of (district_name, guessed_topology, labeled_topology). Reports the raw pairs
    and coarse hub-vs-per-school agreement over districts where the LABELED topology makes such a
    claim (so single_school/none_found/unknown don't pollute the rate)."""
    pairs = {name: [g, l] for name, g, l in rows}
    coarse_den = coarse_agree = 0
    for _, g, l in rows:
        lc = LABEL_COARSE.get(l, "unknown")
        if lc in ("hub", "per_school"):
            coarse_den += 1
            if GUESS_COARSE.get(g, "unknown") == lc:
                coarse_agree += 1
    return {"coarse_agreement": _r(coarse_agree / coarse_den if coarse_den else None),
            "coarse_agree": coarse_agree, "coarse_den": coarse_den, "pairs": pairs}


def _r(x, p=4):
    return round(x, p) if isinstance(x, float) else x


# ----------------------------- V2: per-detector diagnostics (REQ-113, Snorkel LFAnalysis) -----------------------------
# Static polarity per labeling function (the direction it votes) — accuracy is scored against it.
DETECTOR_POLARITY = {
    "lf_explicit_minutes": "target", "lf_time_table": "target", "lf_prose_pair": "target",
    "lf_footer_hours": "target", "lf_heading_hours": "target", "lf_weak_times": "target",
    "lf_no_times": "negative", "lf_news_feed": "negative", "lf_calendar_widget": "negative",
    "lf_nonstandard_day": "negative", "lf_office_hours": "negative",
    "lf_board": "negative", "lf_sports": "negative", "lf_transport": "negative",
}


def detector_diagnostics(rows):
    """rows: iterable of (fired: list[str], is_target: bool) over LABELED records. Per labeling function,
    Snorkel-style diagnostics: COVERAGE (fraction of records it fires on), ACCURACY (when it fires, was its
    polarity right — a target LF wants a target, a negative LF wants a non-target), and the raw split. Plus
    per-record OVERLAP (≥2 LFs fired) and CONFLICT (a target LF and a negative LF both fired). This turns
    'adjust the weights' into a data-grounded conversation and names the next detector to fix."""
    rows = list(rows)
    n = len(rows)
    per = defaultdict(lambda: {"fires": 0, "on_target": 0, "on_nontarget": 0})
    overlap = conflict = 0
    for fired, is_target in rows:
        if len(fired) >= 2:
            overlap += 1
        pols = {DETECTOR_POLARITY.get(nm) for nm in fired}
        if "target" in pols and "negative" in pols:
            conflict += 1
        for name in fired:
            per[name]["fires"] += 1
            per[name]["on_target" if is_target else "on_nontarget"] += 1
    out = {}
    for name, d in sorted(per.items()):
        pol = DETECTOR_POLARITY.get(name, "?")
        correct = d["on_target"] if pol == "target" else d["on_nontarget"]
        out[name] = {"polarity": pol, "coverage": _r(d["fires"] / n if n else None), "fires": d["fires"],
                     "accuracy": _r(correct / d["fires"] if d["fires"] else None),
                     "on_target": d["on_target"], "on_nontarget": d["on_nontarget"]}
    return {"n": n, "overlap": overlap, "conflict": conflict, "per_detector": out}


# ----------------------------- DB reading + fingerprints -----------------------------
def _labeled_records(con):
    return con.execute(text(
        """SELECT r.tier, r.category_hypothesis, l.primary_label, r.signals_json
           FROM record r JOIN label l ON l.rec_key = r.rec_key
           WHERE l.status != 'unlabeled' AND l.primary_label IS NOT NULL""")).fetchall()


def score(con):
    recs = _labeled_records(con)
    tier_rows = [(t, lab in TARGET) for t, _cat, lab, _sj in recs]
    cat_rows = [(cat, lab) for _t, cat, lab, _sj in recs]
    # V2 (REQ-113): per-detector diagnostics from the fired votes stored in signals_json.
    det_rows = [([v["name"] for v in (json.loads(sj or "{}").get("detectors") or [])], lab in TARGET)
                for _t, _cat, lab, sj in recs]
    topo_rows = con.execute(text(
        "SELECT name, guessed_topology, labeled_topology FROM district ORDER BY name")).fetchall()
    n_rec = con.execute(text("SELECT COUNT(*) FROM record")).scalar()
    n_dist = con.execute(text("SELECT COUNT(*) FROM district")).scalar()
    return {
        "counts": {"records": n_rec, "labeled": len(recs), "districts": n_dist,
                   "targets": sum(1 for _t, g in tier_rows if g)},
        "tier_vs_target": tier_target_metrics(tier_rows),
        "category_accuracy": category_accuracy(cat_rows),
        "detectors": detector_diagnostics(det_rows),
        "topology": topology_report(topo_rows),
    }


def _h(s):
    return hashlib.md5(s.encode("utf-8", "replace")).hexdigest()[:12]


def fingerprints(con):
    cfg = "".join(sorted(f.read_text() for f in paths.CONFIG_DIR.glob("*.json"))) \
        if paths.CONFIG_DIR.exists() else ""
    labels = con.execute(text(
        """SELECT rec_key, primary_label, status, facets_json FROM label
           WHERE status != 'unlabeled' ORDER BY rec_key""")).fetchall()
    data = con.execute(text("SELECT rec_key, tier, category_hypothesis FROM record ORDER BY rec_key")).fetchall()
    topo = con.execute(text(
        "SELECT district_id, guessed_topology, labeled_topology, nces_school_count FROM district ORDER BY district_id")).fetchall()
    return {
        "config": _h(cfg),
        "label_set": _h("|".join("·".join(map(str, r)) for r in labels)),
        "data": _h("|".join("·".join(map(str, r)) for r in data + topo)),
    }


def build_scorecard():
    with gdb.session_scope() as con:
        return {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fingerprints": fingerprints(con),
            **score(con),
        }


def write_scorecard(card, out_dir=None):
    out_dir = Path(out_dir or paths.SCORECARDS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = card["fingerprints"]
    out = out_dir / f"scorecard_{card['generated_at'].replace(':', '').replace('-', '')}_{fp['config']}.json"
    out.write_text(json.dumps(card, indent=2))
    return out


def print_summary(card):
    c, t = card["counts"], card["tier_vs_target"]
    print(f"SCORECARD {card['generated_at']}  fingerprints: "
          f"config={card['fingerprints']['config']} labels={card['fingerprints']['label_set']} data={card['fingerprints']['data']}")
    print(f"  records={c['records']} labeled={c['labeled']} targets={c['targets']} districts={c['districts']}")
    print("  tier vs target (label in TARGET set):")
    for tier, v in t["per_tier"].items():
        print(f"    tier {tier}: {v['target']} target / {v['nontarget']} non-target")
    for name, m in t["thresholds"].items():
        print(f"    predict-target = tier {name:3}: precision={m['precision']} recall={m['recall']} f1={m['f1']}")
    ca = card["category_accuracy"]
    print(f"  category-guess accuracy: {ca['overall']} ({ca['correct']}/{ca['n']})")
    det = card.get("detectors")
    if det:
        print(f"  detector diagnostics (n={det['n']}, overlap={det['overlap']}, conflict={det['conflict']}):")
        for name, d in det["per_detector"].items():
            print(f"    {name:22} {d['polarity']:8} cov={d['coverage']} acc={d['accuracy']} "
                  f"(fires {d['fires']}: {d['on_target']} target / {d['on_nontarget']} non-target)")
    tp = card["topology"]
    print(f"  topology coarse hub/per-school agreement: {tp['coarse_agreement']} ({tp['coarse_agree']}/{tp['coarse_den']})")
    diverge = {k: v for k, v in tp["pairs"].items() if GUESS_COARSE.get(v[0], "?") != LABEL_COARSE.get(v[1], "?")}
    if diverge:
        print(f"    guessed != labeled (the learning signal): " +
              ", ".join(f"{k}[{v[0]}→{v[1]}]" for k, v in diverge.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    card = build_scorecard()
    print_summary(card)
    if not a.no_write:
        print("wrote", write_scorecard(card))


if __name__ == "__main__":
    main()
