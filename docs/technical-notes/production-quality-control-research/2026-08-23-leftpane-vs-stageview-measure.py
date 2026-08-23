#!/usr/bin/env python3
"""#888 — the left-pane progress badge vs the stage view's own rollup: do they agree?

READ-ONLY. Rerunnable. Imports the LIVE functions on both sides (`BSTORE._batch_progress` and each
stage's `status_for_batch`) rather than re-spelling either — #879's rule.

The defect. Two predicates answer "has this batch finished stage N", and the console renders both:

  * LEFT PANE   stage{2,3,4}.js:~51 -> /api/queue -> stage1_queue/batch_store.py::_batch_progress
                One grouped SQL query over state_event, `WHERE batch_id IS NOT NULL AND stage IS NOT
                NULL`. Done = max stage reached among events STAMPED WITH THIS batch_id.
  * STAGE VIEW  stage{2,3,4}.js:~93 -> <stage>/headless.py::status_for_batch(...)["rollup"]
                The on-disk artifact, AND — only when `BT.redoes_attempted(batch)` — intersected
                with DS.completed_by_batch (the #671/#885 dispatch-window rule, which keys on event
                ORDER precisely because the batch_id stamp is unreliable).

Most historical completion events carry no batch_id, so the left pane under-reports: a complete
batch renders NOT STARTED. stage4.js:~127 then OVERWRITES the left-pane chip with the header's
value on click, and the list is re-fetched on every view-show — hence the flip, and the recurrence
on every toggle.

  C1  the disagreement table — the defect itself.
  C2  batch_id stamping coverage on stage-outcome events — the root cause of C1's direction.
  C3  sizing: how many disagreements close if `_batch_progress` keys on `completed_by_batch`
      instead of the stamp, and WHICH stay open and why.
  C4  the performance constraint, measured — why the left pane must keep ONE grouped query.
  C5  the one-home fitness guard's blind spot: the rule that exists to prevent this drift does not
      match the spelling that caused it. Flips to a pass when the fix widens the pattern.

Usage:  python3 docs/technical-notes/production-quality-control-research/2026-08-23-leftpane-vs-stageview-measure.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.process_governance.server import _batch_from_db
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage2_discover import headless as H2
from infrastructure.acquisition.stage3_capture import headless as H3
from infrastructure.acquisition.stage4_process import headless as H4

NOTHING = "NOTHING MEASURED"

# (label, the _batch_progress key, the stage_name for completed_by_batch, the rollup getter)
STAGES = [
    ("stage2", "discovered", "discover", lambda b: H2.rollup(H2.status_for_batch(b))),
    ("stage3", "captured", "capture", lambda b: H3.status_for_batch(b)["rollup"]),
    ("stage4", "processed", "process", lambda b: H4.status_for_batch(b)["rollup"]),
]


def _approved_batches() -> list:
    """Approved batches only — that is what both surfaces badge (`status === "approved"` gates the
    progress badge in stage{2,3,4}.js; a draft/abandoned batch shows a lifecycle badge instead).
    batch_00000 (benchmark, 27 districts) IS included and currently AGREES; it is walled off from
    Stage-9 writes and funnel stats, not from the console's progress badge."""
    with gdb.session_scope() as s:
        ids = [b["batch_id"] for b in BSTORE.list_batches(s) if b["status"] == "approved"]
    out = []
    for bid in ids:
        b = _batch_from_db(bid)
        if b and b.get("districts"):
            out.append(b)
    return out


def main() -> None:
    batches = _approved_batches()
    print(f"# 2026-08-23 · #888 left pane vs stage view · {len(batches)} approved batches\n")
    if not batches:
        print(f"C1..C5: {NOTHING} — no approved batch with districts; nothing is badged.")
        return

    with gdb.session_scope() as s:
        prog = BSTORE._batch_progress(s)
    if not prog:
        print(f"C1: {NOTHING} — _batch_progress returned {{}} (its best-effort degrade). The left "
              "pane would render no badge at all, so there is nothing to compare. Investigate "
              "rather than reading this as agreement.")
        return

    # ------------------------------------------------------------------ C1 the disagreement
    print("## C1 — left-pane badge vs the stage view's own rollup")
    rows, per_stage = [], {}
    for b in batches:
        p = prog.get(b["batch_id"]) or {}
        for label, key, _nm, fn in STAGES:
            try:
                r = fn(b)
            except Exception as e:                      # a stage that cannot render is not agreement
                print(f"  ERROR {b['batch_id']} {label}: {type(e).__name__}: {e}")
                continue
            left, right = p.get(key, 0), r.get("done", 0)
            if left != right:
                rows.append((b["batch_id"], label, left, right))
                per_stage[label] = per_stage.get(label, 0) + 1
    if not rows:
        print(f"  {NOTHING} — every approved batch agrees on every stage. If this follows a fix, "
              "confirm C3's residual list is also empty; if it follows nothing, suspect the sweep.")
    else:
        print(f"  {len(rows)} disagreeing batch/stage pairs  {per_stage}\n")
        print(f"  {'batch':<14}{'stage':<9}{'left pane':<12}{'stage view':<12}direction")
        for bid, label, left, right in rows:
            print(f"  {bid:<14}{label:<9}{left:<12}{right:<12}"
                  f"{'UNDER-reports' if left < right else 'OVER-reports'}")
        under = sum(1 for r in rows if r[2] < r[3])
        print(f"\n  {under} under-report (a complete batch renders NOT STARTED), "
              f"{len(rows) - under} over-report.")

    # ------------------------------------------------------------------ C2 the root cause
    print("\n## C2 — batch_id coverage on stage-OUTCOME events (why the left pane under-reports)")
    with gdb.session_scope() as s:
        for r in s.execute(text("""
                SELECT stage_name, COUNT(*) n, COUNT(batch_id) nb
                  FROM state_event
                 WHERE stage_name IN ('discover','capture','process') AND stage IS NOT NULL
                 GROUP BY 1 ORDER BY 1""")):
            pct = (100.0 * r[2] / r[1]) if r[1] else 0.0
            print(f"  {r[0]:9s} outcomes={r[1]:4d}  carry batch_id={r[2]:4d}  ({pct:.1f}%)")
    print("  _batch_progress counts ONLY the stamped ones, so the unstamped majority reads as")
    print("  no-progress. Its docstring calls that 'honest, and those batches are long done' —")
    print("  which is exactly when the badge is the operator's only completeness signal.")

    # ------------------------------------------------------------------ C3 sizing the fix
    print("\n## C3 — would keying on completed_by_batch instead of the stamp close them?")
    closed, still = [], []
    for b in batches:
        p = prog.get(b["batch_id"]) or {}
        ids = [d["district_id"] for d in b["districts"]]
        for label, key, nm, fn in STAGES:
            try:
                right = fn(b).get("done", 0)
            except Exception:
                continue
            if p.get(key, 0) == right:
                continue
            cbb = len(DS.completed_by_batch(b["batch_id"], nm, ids))
            (closed if cbb == right else still).append((b["batch_id"], label, cbb, right))
    tot = len(closed) + len(still)
    if not tot:
        print(f"  {NOTHING} — no disagreements to size (see C1).")
    else:
        print(f"  closes {len(closed)} of {tot};  {len(still)} remain:\n")
        for bid, label, cbb, right in still:
            print(f"    {bid:<14}{label:<9}completed_by_batch={cbb:<4}stage view={right}")
        print("\n  The residue is NOT stamping — it is the two things the pure-SQL query cannot")
        print("  see: no-link districts (Stage 3 reports `manual_flag_all`, not `done`) and the")
        print("  DISK conjunct that status_for_batch intersects. Both belong to #622's inversion,")
        print("  not to a second copy of the disk check in the left pane.")

    # ------------------------------------------------------------------ C4 the perf constraint
    print("\n## C4 — why the left pane must stay ONE grouped query")
    with gdb.session_scope() as s:
        t = time.perf_counter()
        BSTORE._batch_progress(s)
        grouped = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    for b in batches:
        ids = [d["district_id"] for d in b["districts"]]
        for _label, _key, nm, _fn in STAGES:
            DS.completed_by_batch(b["batch_id"], nm, ids)
    per_batch = (time.perf_counter() - t) * 1000
    n_calls = len(batches) * len(STAGES)
    print(f"  current _batch_progress, ONE grouped query : {grouped:7.1f} ms")
    print(f"  naive per-batch completed_by_batch ({n_calls:3d} calls): {per_batch:7.0f} ms"
          f"   ({per_batch / max(grouped, 0.001):.0f}x)")
    print(f"  per call: {per_batch / max(n_calls, 1):.1f} ms — higher than the 1.5-2.0ms a single")
    print("  call measures in a tight loop (#886), because each call opens its OWN session and")
    print("  each batch/stage is a fresh parameter set. Quote THIS number, not that one: the")
    print("  relevant unit is the whole left-pane render, not one warm repeated query.")

    # ------------------------------------------------------------------ C5 the blind guard
    print("\n## C5 — does the one-home fitness guard catch this drift?")
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
    try:
        from test_one_home_fitness import RULES            # noqa: E402
    except Exception as e:
        print(f"  {NOTHING} — could not import the fitness RULES ({type(e).__name__}: {e}). "
              "That is a broken check, not a pass.")
        return
    rule = next((r for r in RULES if r["rule"] == "batch-scoped stage done-ness"), None)
    if rule is None:
        print(f"  {NOTHING} — no 'batch-scoped stage done-ness' rule found; it may have been "
              "renamed. Do not read this as a pass.")
        return
    bp = Path("infrastructure/acquisition/stage1_queue/batch_store.py")
    hit = bool(rule["forbid"].search(bp.read_text()))
    print(f"  rule home   : {Path(rule['home']).name}")
    print(f"  forbid regex: {rule['forbid'].pattern}")
    print(f"  matches {bp.name}? {hit}")
    if hit:
        print("  PASS — the guard now sees _batch_progress's spelling.")
    else:
        print("  BLIND — the pattern requires a BOUND PARAMETER (`batch_id = :`), and")
        print("  _batch_progress spells it `batch_id IS NOT NULL`. The guard that exists to stop")
        print("  exactly this drift never looked at the query that caused it. Widening this")
        print("  pattern is part of the fix, or the next copy drifts past it too.")


if __name__ == "__main__":
    main()
