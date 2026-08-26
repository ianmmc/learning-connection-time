#!/usr/bin/env python3
"""#670 — the failed-latest veto: what it withdraws on the live corpus, and the invariant it keeps.

READ-ONLY. Rerunnable. Imports the LIVE `status_for_batch` (stages 3 and 4) rather than re-spelling
it (#879's rule). The ONE rule spelled locally is the PRE-FIX disk rule — the historical baseline
being measured against, named `_prefix_disk_done` to say so.

The defect (#670). A late capture timeout kills the Node subprocess AFTER it has written a populated
captures.json (Orange County FL `1201440`, 119 ok=true records + a TimeoutExpired event). The
console's `captured` set was pure disk existence for ordinary batches, so artifact-existence
outranked the gov_db failure event and the district rendered a clean, unretriable `done`. The fix is
a VETO on every batch type: a district whose LATEST stage event is `failed` is subtracted from the
disk-done set — gov_db outranks the artifact (epic #723). Stage 4 carried the same latent twin
(its comment claimed process failures "leave NO processed.json"), fixed in the same change, both
sets (own done-ness + the upstream capture gate).

  C1  blast radius: every district whose LATEST capture/process event is `failed` while the disk
      artifact exists — exactly the rows the veto withdraws from `done` — with the age of the
      failed event. This is the number the fix's PR body must quote.
  C2  the safety invariant, replayed through the LIVE status_for_batch over every batch: no
      district that renders `done` has a failed-latest event; and the veto is strictly-withdrawing
      against the pre-fix disk rule (it never asserts a `done` disk did not).
  C3  the no-events population: districts done-on-disk with NO stage event at all (the corpus the
      veto deliberately leaves untouched — the #885 re-pay trap this fix refuses). MEASURED 0 on
      2026-08-24: every disk-done district HAS a completion event (119/119) — the historical gap
      was the batch_id STAMP on those events, never their absence — so the no-events guard is
      belt-and-braces, and the operative protection is latest-event-wins (an old failure followed
      by a successful outcome never vetoes).

Explicit `NOTHING MEASURED` verdicts: an empty sweep is a wrong-path signal, not a green zero.

Usage:  python3 docs/technical-notes/production-quality-control-research/2026-08-24-failed-latest-veto-measure.py
"""
from __future__ import annotations

import datetime as _dt

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.process_governance.server import _batch_from_db
from infrastructure.acquisition.stage3_capture import capture_stage3 as C3
from infrastructure.acquisition.stage3_capture import headless as H3
from infrastructure.acquisition.stage4_process import headless as H4

NOTHING = "NOTHING MEASURED"
ARTIFACT = {"capture": "captures.json", "process": "processed.json"}


def _dirs_by_id() -> dict:
    return {d["district_id"]: d["dir"] for d in C3.find_districts(paths.RAW_CAPTURES)}


def _latest_events(stage_name: str) -> dict:
    """district_id -> (event_type, note, created_at) for the LATEST event of stage_name — the same
    DISTINCT ON shape the live veto uses (district-keyed; no batch_id filter, per the one-home rule)."""
    with gdb.session_scope() as con:
        return {r["district_id"]: (r["event_type"], r["note"] or "", r["created_at"])
                for r in con.execute(text(
                    """SELECT DISTINCT ON (district_id) district_id, event_type, note, created_at
                       FROM state_event WHERE stage_name = :nm
                       ORDER BY district_id, event_id DESC"""), {"nm": stage_name}).mappings()}


def _prefix_disk_done(stage_name: str, dirs: dict) -> set:
    """The PRE-FIX rule for an ordinary batch, reconstructed: artifact existence IS done.
    Not a production predicate — the baseline under measurement."""
    return {did for did, ddir in dirs.items() if (ddir / ARTIFACT[stage_name]).exists()}


def _age_days(created_at: str) -> str:
    try:
        at = _dt.datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        return f"{(_dt.datetime.now(_dt.timezone.utc) - at).days}d"
    except (ValueError, TypeError):
        return "?"


def _all_batches() -> list:
    with gdb.session_scope() as s:
        ids = [r[0] for r in s.execute(text("SELECT batch_id FROM batch ORDER BY batch_id"))]
    return [_batch_from_db(b) for b in ids]


def main() -> None:
    dirs = _dirs_by_id()
    if not dirs:
        print(f"C1: {NOTHING} — no district dirs under {paths.RAW_CAPTURES} (wrong root?)")
        return

    # ---- C1: the withdrawn population -------------------------------------------------------
    print("== C1: failed-latest + artifact-on-disk (what the veto withdraws from `done`) ==")
    c1_total = 0
    for stage in ("capture", "process"):
        latest = _latest_events(stage)
        rows = [(did, note, at) for did, (et, note, at) in latest.items()
                if et == "failed" and did in dirs and (dirs[did] / ARTIFACT[stage]).exists()]
        c1_total += len(rows)
        print(f"  {stage}: {len(rows)} district(s)")
        for did, note, at in sorted(rows):
            # #926: the PRODUCTION predicate, not a copy — H3.is_timeout_note is the one home
            # (REQ-182) and knows both note generations (TimeoutExpired pre-#924, CaptureTimeout
            # since). The hand-rolled startswith() this replaced would have silently classified
            # every post-#924 timeout as `failed` while the console said `timed_out` (#879).
            kind = "timed_out" if H3.is_timeout_note(note) else "failed"
            print(f"    {did}  [{kind}, {_age_days(at)} old]  {note[:90]}")
    if c1_total == 0:
        print(f"  (population currently empty — fine AFTER remediation; on first run this would be "
              f"{NOTHING}-suspicious, cross-check C3 is nonzero)")

    # ---- C2: the invariant, through the LIVE status ------------------------------------------
    print("\n== C2: live replay over every batch — no `done` district has a failed-latest event ==")
    batches = _all_batches()
    if not batches:
        print(f"  {NOTHING} — no batches in gov_db (is Docker up / the canonical DB connected?)")
        return
    latest_by_stage = {s: _latest_events(s) for s in ("capture", "process")}
    disk_done = {s: _prefix_disk_done(s, dirs) for s in ("capture", "process")}
    violations, withdrawn, asserted, scanned = [], 0, 0, 0
    for batch, H, stage in [(b, H, s) for b in batches
                            for H, s in ((H3, "capture"), (H4, "process"))]:
        out = H.status_for_batch(batch)
        for d in out["districts"]:
            scanned += 1
            did, st = d["district_id"], d["status"]
            failed_latest = latest_by_stage[stage].get(did, (None,))[0] == "failed"
            if st == "done" and failed_latest:
                violations.append((batch["batch_id"], stage, did))
            # strictly-withdrawing vs the pre-fix disk rule (ordinary-batch baseline):
            if st == "done" and did not in disk_done[stage]:
                asserted += 1          # a done disk did NOT assert — must stay 0
            if did in disk_done[stage] and st in ("failed", "timed_out"):
                withdrawn += 1
    if scanned == 0:
        print(f"  {NOTHING} — batches exist but contributed no district rows")
        return
    print(f"  scanned {scanned} district×batch×stage rows across {len(batches)} batches")
    print(f"  violations (done despite failed-latest): {len(violations)}"
          + (f"  {violations}" if violations else "  — INVARIANT HOLDS"))
    print(f"  withdrawn vs disk rule (done -> failed/timed_out): {withdrawn}")
    print(f"  asserted vs disk rule (done that disk did not have): {asserted}"
          + ("  — STRICTLY-WITHDRAWING HOLDS" if asserted == 0 else "  — VIOLATION"))

    # ---- C3: the untouched historical corpus -------------------------------------------------
    print("\n== C3: done-on-disk with NO stage event at all (deliberately untouched — no re-pay) ==")
    for stage in ("capture", "process"):
        latest = _latest_events(stage)
        n = sum(1 for did in disk_done[stage] if did not in latest)
        print(f"  {stage}: {n} district(s) keep `done` purely from disk (their completions predate "
              f"the event log)")


if __name__ == "__main__":
    main()
