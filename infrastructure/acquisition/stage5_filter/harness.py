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
from infrastructure.acquisition.stage5_filter import exploration_audit as EA  # noqa: E402  (#214 exploration-cohort TNR)
from infrastructure.acquisition.common import paths                  # noqa: E402
from infrastructure.acquisition.common import db as gdb              # noqa: E402  (governance Postgres — REQ-103)

TARGET = BS.TARGET_LABELS

# ----------------------------- the defended recall floor — SINGLE SOURCE OF TRUTH (#208) -----------------------------
# The Stage-5 filter's guardrail is "no TARGET is silently dropped below human review" — a target must reach
# at least tier B (SEND or REVIEW), never be SUPPRESSED to tier D. So the floor defends **A+B recall**, NOT
# tier-A recall: tier A is the auto-SEND (precision-oriented) bucket, its recall sits ~0.89 BY DESIGN
# (borderline targets route to review), so a tier-A floor at 0.97/0.98 was unmeetable + non-binding — and
# frontier (0.97) and the ledger (0.98) disagreed on the value. One canonical (floor, tier) pair now, imported
# by frontier (feasibility), tuning_ledger (the recorded constraint), and assert_floor below — the
# ENFORCEMENT gate build_signals --assert-floor runs INSIDE the ingest transaction. NOTE (#214): once the exploration quota
# exists, the honest floor is measured against the exploration cohort (Rejection-Quality/TNR), not only the
# approved/labeled set — this constant is the labeled-set floor until then.
RECALL_FLOOR = 0.98
FLOOR_TIER = "A+B"


def floor_recall(scorecard):
    """The recall the floor defends (FLOOR_TIER = A+B, reaches-review) from a harness scorecard; None for
    ANY malformed/legacy shape, never a crash — the ledger loads scorecards from arbitrary on-disk JSON
    (record_from_files), so this must degrade the way the try/except it replaced did."""
    try:
        return scorecard["tier_vs_target"]["thresholds"][FLOOR_TIER].get("recall")
    except (KeyError, TypeError, AttributeError):
        return None


def floor_satisfied(scorecard, floor=None):
    """True iff the scorecard's floor-tier recall meets the floor (>= — exactly AT the floor passes).
    `floor=None` reads RECALL_FLOOR at call time, so a runtime override of the module constant is honored."""
    floor = RECALL_FLOOR if floor is None else floor
    rec = floor_recall(scorecard)
    return rec is not None and rec >= floor


def assert_floor(con, floor=None):
    """The floor ENFORCEMENT gate (#208): score the labeled set on `con` and raise SystemExit if the
    floor-tier recall is below the floor; returns that recall when it passes. Designed to run INSIDE the
    ingest transaction (build_signals --assert-floor): SystemExit skips session_scope's commit and close()
    discards the uncommitted work (Postgres DDL included), so a violating config's tiers NEVER reach the
    working store — the console keeps serving the prior config. SystemExit matches the batch_guard
    hard-stop convention."""
    floor = RECALL_FLOOR if floor is None else floor
    card = {"fingerprints": fingerprints(con), **score(con)}
    rec = floor_recall(card)
    if rec is None or rec < floor:
        raise SystemExit(
            f"RECALL FLOOR VIOLATED: tier-{FLOOR_TIER} recall={rec} < {floor} "
            f"(config={card['fingerprints']['config']} data={card['fingerprints']['data']}). "
            f"Ingest NOT committed — the prior config's tiers remain live. Loosen the config or record "
            f"an explicit tuning-ledger override before re-running.")
    return rec

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
        # `is not None` on purpose (issue #63): a legitimate 0.0 precision/recall is COMPUTABLE
        # (f1 = 0.0), not missing — truthiness would report it as None.
        if prec is not None and rec is not None:
            f1 = 0.0 if (prec + rec) == 0 else 2 * prec * rec / (prec + rec)
        else:
            f1 = None
        thresholds[name] = {"tp": tp, "fp": fp, "fn": fn,
                            "precision": _r(prec), "recall": _r(rec), "f1": _r(f1)}
    return {"per_tier": {k: dict(v) for k, v in sorted(per_tier.items())}, "thresholds": thresholds}


def exploration_cohort(rows, p=EA.DEFAULT_SAMPLE_RATE, seed=EA.DEFAULT_SEED):
    """The #214 measurement-hole fix — Rejection-Quality/TNR on the EXPLORATION COHORT (the pruned tail),
    the signal the approved-set precision/recall metrics are structurally blind to. Under a *deterministic*
    filter, tuning measured only on the approved set can bless a recall collapse as a win (the 'illusion of
    improvement', FINDINGS §0) — the wrongly-rejected docs never enter the measurement. This closes that
    hole: `rows` is an iterable of `(rec_key, tier, is_target)` over LABELED records; we take the reject
    (tier-D) sub-cohort, draw the SAME randomized audit sample the live quota uses (`select_audit_sample`,
    reproducible + growth-stable), and report `rejection_quality` over the drawn rejects' human labels — the
    honest recall signal, with the rule-of-three ceiling when zero misses were seen.

    Pure + config-relative: pass the CURRENT tiers for the live scorecard, or a candidate config's re-tiered
    rows (frontier `_retier`) for a measured-pass — the cohort is always that config's OWN pruned tail, so a
    challenger that suppresses more real targets shows lower reject-quality here even as approved-set
    precision rises. `audited` is the whole labeled reject cohort; `sampled` is the audited∩drawn window the
    quality is computed over (the same random draw the console audit works)."""
    rows = list(rows)
    audited = [(rk, is_t) for rk, tier, is_t in rows if tier == EA.REJECT_TIER]
    drawn = set(EA.select_audit_sample([rk for rk, _ in audited], p=p, seed=seed))
    sampled_labels = [is_t for rk, is_t in audited if rk in drawn]
    q = EA.rejection_quality(sampled_labels)
    return {"cohort_size": len(audited), "sampled_n": len(sampled_labels),
            "seed": seed, "sample_rate": p, **q}


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


# #108: each NEGATIVE detector's Axis-2 confounder facet(s) — the human ground truth for "is the
# confounder this detector claims actually present?". Scored SEPARATELY from tier-target accuracy above:
# a page can be a target AND carry a confounder (Las Cruces — a real district_hub_by_school delivered in
# a news feed), so a negative detector firing on a target is NOT wrong if its confounder facet is checked.
# This measures the detector's CLAIM (did it name the right confounder), which the coarse target-accuracy
# above cannot. The mapping is explicit (NOT the vote `category` field — lf_office_hours and
# lf_nonstandard_day share category 'other_schedule' but map to different facets). See STAGE5 §5/§8.
# `lf_no_times` (also negative-polarity) is DELIBERATELY absent: it is the suppress FLOOR — a claim that
# NO signal is present, not that a specific confounder shape is — so it has no Axis-2 facet to score against.
DETECTOR_FACET = {
    "lf_news_feed": {"news_feed"},
    "lf_calendar_widget": {"academic_calendar", "community_calendar"},
    # CAVEAT (#199 review): `other_schedule` has NO live checkbox in the v2.1 questionnaire (app.js
    # CONFOUNDERS) — its only writer was the one-time v2.0→v2.1 label migration, so this detector's
    # facet-tagged denominator is FROZEN at the migrated rows and cannot accrue from new gate@5 review
    # until a nonstandard-day/other-schedule checkbox is added (tracked: #207).
    "lf_nonstandard_day": {"other_schedule"},
    "lf_office_hours": {"office_building_hours"},
    "lf_board": {"board"},
    "lf_sports": {"sports"},
    "lf_transport": {"transportation"},
}
# Axis-3 (location) + not-a-confounder keys carried in facets_json — excluded from the confounder set.
_NON_CONFOUNDER_FACETS = {"buried_handbook", "needs_vision"}


def parse_facets(facets_json):
    """Parse a label's facets_json into its v2.1 dict, or None when the value does not represent a v2.1
    review (empty, null, unparseable, or a non-dict legacy shape). ONE predicate for both 'which facets'
    and 'was this record facet-reviewed at all' — the #199 review found the two computed independently
    (a string check vs. a dict-shape check), letting a legacy non-dict value count into the facet-tagged
    DENOMINATOR while contributing no facets, silently deflating facet_precision."""
    try:
        d = json.loads(facets_json or "{}")
    except (TypeError, ValueError):
        return None
    return d if isinstance(d, dict) and d else None


def confounder_facets(facets_json):
    """The set of Axis-2 confounder facets checked 'yes' in a label's facets_json (Axis-3 `_`-prefixed
    location keys + buried_handbook/needs_vision excluded). Only the literal 'yes' counts — the questionnaire
    stores a checked box as 'yes' and OMITS unchecked ones, so any other value (e.g. a future explicit 'no')
    must not read as present (#199 review: the old any-truthy check would have)."""
    d = parse_facets(facets_json)
    if d is None:
        return set()
    return {k for k, v in d.items()
            if v == "yes" and not k.startswith("_") and k not in _NON_CONFOUNDER_FACETS}


def facet_detector_diagnostics(rows):
    """rows: iterable of (fired: list[str], confounders: set[str], facet_tagged: bool) over LABELED records
    (#108). For each NEGATIVE detector, FACET-level precision: among its firings on records whose facets
    the human actually tagged (a non-empty v2.1 dict — `parse_facets` is the single tagged/untagged
    predicate), the fraction where its claimed confounder facet (DETECTOR_FACET) is present. This is
    confounder-ID accuracy, orthogonal to whether a target co-occurs. `fires_facet_tagged` is the
    (transparent) denominator — a small one means facets are still accruing (§8), so read the precision as
    provisional (EXCEPT lf_nonstandard_day, whose facet has no live checkbox — see DETECTOR_FACET).
    Records with no facets tagged can't inform it and are excluded, not counted as misses."""
    rows = list(rows)
    out = {}
    for name, want in sorted(DETECTOR_FACET.items()):
        fires = fires_tagged = hits = 0
        for fired, confounders, tagged in rows:
            if name not in fired:
                continue
            fires += 1
            if tagged:
                fires_tagged += 1
                if confounders & want:
                    hits += 1
        out[name] = {"facets": sorted(want), "fires": fires, "fires_facet_tagged": fires_tagged,
                     "hits": hits, "facet_precision": _r(hits / fires_tagged if fires_tagged else None)}
    return {"per_detector": out}


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
        """SELECT r.tier, r.category_hypothesis, l.primary_label, r.signals_json, l.facets_json, r.rec_key
           FROM record r JOIN label l ON l.rec_key = r.rec_key
           WHERE l.status != 'unlabeled' AND l.primary_label IS NOT NULL""")).fetchall()


def _fired(sj):
    return [v["name"] for v in (json.loads(sj or "{}").get("detectors") or [])]


def score(con):
    recs = _labeled_records(con)
    tier_rows = [(t, lab in TARGET) for t, _cat, lab, _sj, _fj, _rk in recs]
    cat_rows = [(cat, lab) for _t, cat, lab, _sj, _fj, _rk in recs]
    # V2 (REQ-113): per-detector diagnostics from the fired votes stored in signals_json.
    det_rows = [(_fired(sj), lab in TARGET) for _t, _cat, lab, sj, _fj, _rk in recs]
    # #108: facet-level per-detector diagnostics — negative detectors vs their Axis-2 confounder facets.
    # tagged uses the SAME parse_facets predicate as confounder_facets (#199 review: an independent raw-string
    # check counted non-dict legacy shapes into the denominator while they could never contribute a hit).
    facet_rows = [(_fired(sj), confounder_facets(fj), parse_facets(fj) is not None)
                  for _t, _cat, _lab, sj, fj, _rk in recs]
    # #214: the exploration-cohort TNR — the honest recall signal on the pruned (tier-D) tail, over the
    # SAME randomized audit draw the live quota uses. Closes the 'illusion of improvement' hole (FINDINGS §0):
    # a measured-pass reads this beside the approved-set metrics, so recall collapse can't hide.
    reject_rows = [(rk, t, lab in TARGET) for t, _cat, lab, _sj, _fj, rk in recs]
    topo_rows = con.execute(text(
        "SELECT name, guessed_topology, labeled_topology FROM district ORDER BY name")).fetchall()
    n_rec = con.execute(text("SELECT COUNT(*) FROM record")).scalar()
    n_dist = con.execute(text("SELECT COUNT(*) FROM district")).scalar()
    return {
        "counts": {"records": n_rec, "labeled": len(recs), "districts": n_dist,
                   "targets": sum(1 for _t, g in tier_rows if g),
                   "facet_tagged": sum(1 for _f, _c, tagged in facet_rows if tagged)},
        "tier_vs_target": tier_target_metrics(tier_rows),
        "category_accuracy": category_accuracy(cat_rows),
        "detectors": detector_diagnostics(det_rows),
        "facet_detectors": facet_detector_diagnostics(facet_rows),
        "topology": topology_report(topo_rows),
        "exploration_cohort": exploration_cohort(reject_rows),
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
    fd = card.get("facet_detectors")
    if fd:
        ft = card["counts"].get("facet_tagged")
        print(f"  facet-level negative-detector precision (#108; {ft} labeled records carry facets):")
        for name, d in fd["per_detector"].items():
            print(f"    {name:22} facet={'/'.join(d['facets']):24} "
                  f"facet_prec={d['facet_precision']} ({d['hits']}/{d['fires_facet_tagged']} facet-tagged firings; {d['fires']} total)")
    ec = card.get("exploration_cohort")
    if ec:
        # #214: the honest recall signal on the pruned tail — read this BESIDE the approved-set metrics
        # above (a rise there with a fall here is the illusion of improvement, not a win).
        rq = ec.get("rejection_quality")
        bound = f", FN-rate<{ec['fnr_upper_bound_95']} @95%" if ec.get("fnr_upper_bound_95") is not None else ""
        print(f"  exploration cohort (tier-{EA.REJECT_TIER} pruned tail): reject-quality/TNR="
              f"{rq if rq is not None else '—'} over {ec['sampled_n']}/{ec['cohort_size']} audited rejects{bound}")
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
