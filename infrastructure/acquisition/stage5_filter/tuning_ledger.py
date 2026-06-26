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

# Default recall floor for the Stage 5 operational filter: the human at CP-B is the precision
# backstop, so the constraint we defend automatically is RECALL on targets (tier A).
DEFAULT_RECALL_FLOOR = 0.98

# The metrics we diff between scorecards. Each maps a delta key -> how to pull it from a scorecard.
_METRIC_GETTERS = {
    "tier_A_precision": lambda c: c["tier_vs_target"]["thresholds"]["A"]["precision"],
    "tier_A_recall": lambda c: c["tier_vs_target"]["thresholds"]["A"]["recall"],
    "tier_AB_precision": lambda c: c["tier_vs_target"]["thresholds"]["A+B"]["precision"],
    "category_accuracy": lambda c: c["category_accuracy"]["overall"],
    "topology_agreement": lambda c: c["topology"]["coarse_agreement"],
    "labeled": lambda c: c["counts"]["labeled"],
    "targets": lambda c: c["counts"]["targets"],
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
                  recall_floor=DEFAULT_RECALL_FLOOR):
    """Build one tuning episode from two scorecard dicts (the harness's output shape).

    Records the before/after fingerprints, the metric deltas, the recall-constraint check, and
    the human provenance. `pure_config_move` is True only when label_set AND data fingerprints
    are unchanged — i.e. the delta is attributable to the config alone (a clean A/B). A move
    where labels/data also changed is flagged so no recommender mistakes it for a tuning result.
    """
    fb, fa = before["fingerprints"], after["fingerprints"]
    deltas = {k: _delta(before, after, g) for k, g in _METRIC_GETTERS.items()}
    try:
        after_recall = after["tier_vs_target"]["thresholds"]["A"]["recall"]
    except (KeyError, TypeError):
        after_recall = None
    satisfied = (after_recall is not None and after_recall >= recall_floor)
    return {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "before": {"config": fb["config"], "label_set": fb["label_set"], "data": fb["data"]},
        "after": {"config": fa["config"], "label_set": fa["label_set"], "data": fa["data"]},
        "pure_config_move": (fb["label_set"] == fa["label_set"] and fb["data"] == fa["data"]),
        "deltas": deltas,
        "constraint": {"recall_floor": recall_floor, "after_recall": after_recall,
                       "satisfied": satisfied},
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
                      recall_floor=DEFAULT_RECALL_FLOOR, ledger_path=None):
    """Load two scorecard JSONs, build an episode, append it. The helper a tuning round calls —
    chat-driven now, automated later — so both paths write the identical shape."""
    before = json.loads(Path(before_path).read_text())
    after = json.loads(Path(after_path).read_text())
    episode = build_episode(before, after, knobs_touched=knobs_touched, rationale=rationale,
                            decided_by=decided_by, recall_floor=recall_floor)
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
    r.add_argument("--ledger", default=None)
    s = sub.add_parser("show", help="print the ledger")
    s.add_argument("--ledger", default=None)
    a = ap.parse_args()

    if a.cmd == "record":
        knobs = [k.strip() for k in a.knobs.split(",") if k.strip()]
        ep = record_from_files(a.before, a.after, knobs_touched=knobs, rationale=a.rationale,
                               decided_by=a.by, recall_floor=a.recall_floor, ledger_path=a.ledger)
        ok = "OK" if ep["constraint"]["satisfied"] else "VIOLATES RECALL FLOOR"
        print(f"recorded episode  {ep['before']['config']} -> {ep['after']['config']}  [{ok}]")
        for k, v in ep["deltas"].items():
            print(f"    {k:22} {_fmt_delta(v)}")
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
