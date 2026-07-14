#!/usr/bin/env python3
"""Tuning-episode ledger (REQ-095) — a durable, append-only record of every config tuning round.

An EPISODE is a transition between two harness scorecards (before -> after): it captures the
fingerprints of each (config / label_set / data), the metric DELTAS, whether the recall
constraint held, the knobs touched, and the human RATIONALE. It is the durable training history
the future tuning recommender reads, and doubles as a human-readable decision log (transparency).

Built BEFORE the grid search and drift detector so both write episodes here from day one — a
chat-driven tuning round today and an automated tuner later emit the *same* shape.

Lives under DATA_ROOT (history/output), NOT under CONFIG_DIR (runtime input): the ledger must
never be loadable as a knob. One JSON object per line (JSONL), append-only, version-controlled
like labels.json.

Reuses the harness fingerprint scheme; does NOT recompute scorecard metrics — it reads them.

Usage:
    python3 tuning_ledger.py record <before.json> <after.json> \
        --knobs stage5_neg_board,stage5_neg_sports \
        --rationale "retune board negs after de-chrome" --by chat
    python3 tuning_ledger.py show          # print the ledger
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.acquisition.common import paths  # noqa: E402
from infrastructure.acquisition.stage5_filter import harness  # noqa: E402  (canonical RECALL_FLOOR/FLOOR_TIER, #208)

# The defended recall floor is the SINGLE SOURCE OF TRUTH in harness (#208) — it defends A+B recall
# (reaches-review: no target silently dropped to tier D), NOT tier-A recall (the auto-send bucket, ~0.89
# by design). Previously the ledger hard-coded 0.98 on tier-A recall while frontier used 0.97 — inconsistent
# AND non-binding (tier-A recall can't reach 0.98). Re-exported for back-compat.
DEFAULT_RECALL_FLOOR = harness.RECALL_FLOOR

# The metrics we diff between scorecards. Each maps a delta key -> how to pull it from a scorecard.
_METRIC_GETTERS = {
    "tier_A_precision": lambda c: c["tier_vs_target"]["thresholds"]["A"]["precision"],
    "tier_A_recall": lambda c: c["tier_vs_target"]["thresholds"]["A"]["recall"],
    "tier_AB_precision": lambda c: c["tier_vs_target"]["thresholds"]["A+B"]["precision"],
    "tier_AB_recall": lambda c: c["tier_vs_target"]["thresholds"]["A+B"]["recall"],   # the floored metric (#208)
    "category_accuracy": lambda c: c["category_accuracy"]["overall"],
    "topology_agreement": lambda c: c["topology"]["coarse_agreement"],
    "labeled": lambda c: c["counts"]["labeled"],
    "targets": lambda c: c["counts"]["targets"],
    # #214: the exploration-cohort Rejection-Quality/TNR on the pruned tail — the honest recall signal the
    # approved-set precision/recall deltas above are structurally blind to. A tuning move that lifts tier_A
    # precision while this FALLS is the illusion of improvement (FINDINGS §0), now visible in the episode.
    "reject_cohort_quality": lambda c: c["exploration_cohort"]["rejection_quality"],
    # #91: the extract-outcome calibration — P(any_accepted) over dispatched-and-extracted reps, the
    # PAID-outcome headline. An episode now shows whether a scoring change moved paid-outcome
    # calibration, not just label agreement. None on legacy scorecards that predate the section.
    "extract_outcome_calibration": lambda c: c["extract_outcome"]["any_accepted_rate"],
}


def _delta(before, after, getter):
    """after - before when both are numbers; None if either is missing/non-numeric."""
    try:
        b, a = getter(before), getter(after)
    except (KeyError, TypeError):
        return None
    if isinstance(b, (int, float)) and isinstance(a, (int, float)):
        return a - b
    return None


# ----------------------------- pure core (testable, no I/O) -----------------------------
def build_episode(before, after, *, knobs_touched, rationale, decided_by,
                  recall_floor=DEFAULT_RECALL_FLOOR, promotion_gate=None):
    """Build one tuning episode from two scorecard dicts (the harness's output shape).

    Records the before/after fingerprints, the metric deltas, the recall-constraint check, and
    the human provenance. `pure_config_move` is True only when label_set AND data fingerprints
    are unchanged — i.e. the delta is attributable to the config alone (a clean A/B). A move
    where labels/data also changed is flagged so no recommender mistakes it for a tuning result.

    `promotion_gate` (optional) is a `promotion_gate.verdict_summary(...)` dict (#212): the
    group-aware non-inferiority verdict recorded ALONGSIDE the scorecard deltas, so a promotion
    episode carries the district-clustered, cluster-honest evidence (the bootstrap lower bound vs
    Δ, the LOGO guard, ICC/DEFF), not just the approved-set metric movements the deltas capture.
    The `constraint.recall_floor` above is the labeled-set floor (#208); the gate is the group-aware
    upgrade for when promotion is even semi-automated. None until a gate was actually run for the move.
    """
    fb, fa = before["fingerprints"], after["fingerprints"]
    deltas = {k: _delta(before, after, g) for k, g in _METRIC_GETTERS.items()}
    # The floor defends A+B recall (harness.FLOOR_TIER) — reaches-review, not the tier-A auto-send bucket (#208).
    after_recall = harness.floor_recall(after)
    satisfied = (after_recall is not None and after_recall >= recall_floor)
    # #214: the illusion-of-improvement guard — flag when the exploration-cohort reject-quality FELL across
    # the move (the honest recall signal on the pruned tail dropping while approved-set metrics may have
    # risen). ADVISORY only: the hard gate is the live quota's demote-hook (#211); here it makes the episode
    # self-incriminating so a reviewer sees a tail regression that the approved-set deltas would hide. None
    # when either scorecard predates the section (legacy) — a missing signal is not a pass.
    rq_delta = deltas.get("reject_cohort_quality")
    reject_quality_regressed = rq_delta is not None and rq_delta < 0
    return {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "before": {"config": fb["config"], "label_set": fb["label_set"], "data": fb["data"]},
        "after": {"config": fa["config"], "label_set": fa["label_set"], "data": fa["data"]},
        "pure_config_move": (fb["label_set"] == fa["label_set"] and fb["data"] == fa["data"]),
        "deltas": deltas,
        "constraint": {"recall_floor": recall_floor, "floor_tier": harness.FLOOR_TIER,
                       "after_recall": after_recall, "satisfied": satisfied,
                       "reject_cohort_quality_delta": rq_delta,
                       "reject_quality_regressed": reject_quality_regressed},
        "promotion_gate": promotion_gate,
        "knobs_touched": list(knobs_touched),
        "rationale": rationale,
        "decided_by": decided_by,
    }


# ----------------------------- I/O shell -----------------------------
def append_episode(episode, ledger_path=None):
    """Append one episode as a single JSONL line. Append-only — never rewrites prior episodes."""
    path = Path(ledger_path or default_ledger_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(episode) + "\n")
    return path


def read_episodes(ledger_path=None):
    """Read all episodes (oldest first). Empty list if the ledger doesn't exist yet."""
    path = Path(ledger_path or default_ledger_path())
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def record_from_files(before_path, after_path, *, knobs_touched, rationale, decided_by,
                      recall_floor=DEFAULT_RECALL_FLOOR, ledger_path=None, gate_verdict_path=None):
    """Load two scorecard JSONs, build an episode, append it. The helper a tuning round calls —
    chat-driven now, automated later — so both paths write the identical shape. `gate_verdict_path`
    (optional) is a saved `promotion_gate.verdict_summary` JSON — attach it when the move went through
    the #212 non-inferiority gate."""
    before = json.loads(Path(before_path).read_text())
    after = json.loads(Path(after_path).read_text())
    gate = json.loads(Path(gate_verdict_path).read_text()) if gate_verdict_path else None
    episode = build_episode(before, after, knobs_touched=knobs_touched, rationale=rationale,
                            decided_by=decided_by, recall_floor=recall_floor, promotion_gate=gate)
    append_episode(episode, ledger_path)
    return episode


def default_ledger_path():
    return paths.STAGE5_DIR / "tuning_ledger" / "episodes.jsonl"


# ----------------------------- CLI -----------------------------
def _fmt_delta(x):
    if x is None:
        return "  —  "
    return f"{x:+.4f}" if isinstance(x, float) else f"{x:+d}"


def main():
    ap = argparse.ArgumentParser(description="Tuning-episode ledger (REQ-095)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="record an episode from two scorecard files")
    r.add_argument("before")
    r.add_argument("after")
    r.add_argument("--knobs", default="", help="comma-separated knob names touched")
    r.add_argument("--rationale", required=True)
    r.add_argument("--by", default="chat", help="decided_by")
    r.add_argument("--recall-floor", type=float, default=DEFAULT_RECALL_FLOOR)
    r.add_argument("--gate-verdict", default=None,
                   help="path to a saved promotion_gate.verdict_summary JSON (#212) to attach")
    r.add_argument("--ledger", default=None)
    s = sub.add_parser("show", help="print the ledger")
    s.add_argument("--ledger", default=None)
    a = ap.parse_args()

    if a.cmd == "record":
        knobs = [k.strip() for k in a.knobs.split(",") if k.strip()]
        ep = record_from_files(a.before, a.after, knobs_touched=knobs, rationale=a.rationale,
                               decided_by=a.by, recall_floor=a.recall_floor, ledger_path=a.ledger,
                               gate_verdict_path=a.gate_verdict)
        ok = "OK" if ep["constraint"]["satisfied"] else "VIOLATES RECALL FLOOR"
        print(f"recorded episode  {ep['before']['config']} -> {ep['after']['config']}  [{ok}]")
        for k, v in ep["deltas"].items():
            print(f"    {k:22} {_fmt_delta(v)}")
        if ep["promotion_gate"]:
            g = ep["promotion_gate"]
            print(f"    promotion gate (#212): {'PROMOTE' if g['promote'] else 'HOLD'} "
                  f"Δ={g['margin']} NI-lower={g['ni_lower_bound']} DEFF={g['deff']}")
    elif a.cmd == "show":
        eps = read_episodes(a.ledger)
        if not eps:
            print("(empty ledger)")
            return
        for ep in eps:
            flag = "" if ep["pure_config_move"] else "  ⚠ labels/data also changed"
            ok = "ok" if ep["constraint"]["satisfied"] else "RECALL VIOLATION"
            print(f"{ep['recorded_at']}  {ep['before']['config']}->{ep['after']['config']}  "
                  f"[{ok}] {','.join(ep['knobs_touched']) or '(no knobs noted)'}{flag}")
            print(f"    {ep['rationale']}  — {ep['decided_by']}")


if __name__ == "__main__":
    main()
