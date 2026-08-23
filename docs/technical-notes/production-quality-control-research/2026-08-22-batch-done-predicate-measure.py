#!/usr/bin/env python3
"""#671 — batch-scoped stage done-ness: what the corrected predicate withdraws, and what it can't add.

READ-ONLY. Rerunnable. Imports the LIVE production predicate (`DS.completed_by_batch`) rather than
re-spelling it — #879's rule, learned when a measurement script's hand-rolled `endswith` counted
North Little Rock's `nlrsd.org` as on-domain for Little Rock's `lrsd.org` and published a wrong
corpus figure. The ONE rule this script does spell locally is the PRE-FIX predicate, which no longer
exists in production: it is the historical baseline being measured against, not a live rule, and
`_prefix_dispatch_only` is named to say so.

The defect (#671). Stages 2/3/4 scoped a redo batch's done-ness to "this batch DISPATCHED it AND the
disk artifact exists". Dispatch is stamped for the WHOLE todo list up front, before any work, so
from t=0 of a redo run every district holding a prior run's artifact satisfied both conjuncts and
rendered `done` — with the PRIOR run's metrics — until its own work finished. The fix asks instead
for a stage OUTCOME (`stage IS NOT NULL`) landing AFTER that dispatch.

  C1  the safety invariant: the corrected set is never a SUPERSET of the pre-fix set, over every
      batch x stage in the corpus. The fix can only withdraw a false `done`, never assert a new one.
  C2  the population the fix withdraws, per batch/stage, with the age of the false `done`.
  C3  the #670 boundary: does a `failed` event count as finishing? Two candidate definitions, and
      the records the choice moves. (Shipped: it does NOT — a batch that errored did not finish.)
  C4  watchdog: districts dispatched with no outcome since. C2's population should drain as these
      are re-run; a NEW entry here is a run that died without writing a failure event.

Usage:  python3 docs/technical-notes/production-quality-control-research/2026-08-22-batch-done-predicate-measure.py
"""
from __future__ import annotations

import datetime as _dt

from sqlalchemy import text

from infrastructure.acquisition.common import batch_types as BT
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.process_governance.server import _batch_from_db

STAGES = ("discover", "capture", "process")
NOTHING = "NOTHING MEASURED"


def _prefix_dispatch_only(batch_id: str, stage_name: str, ids: list) -> set:
    """The PRE-FIX rule, reconstructed. Not a production predicate — the baseline under measurement.

    Verbatim from `district_status.dispatched_by_batch` as it stood at d059471, before #671."""
    with gdb.session_scope() as con:
        return {r[0] for r in con.execute(
            text("SELECT DISTINCT district_id FROM state_event WHERE stage_name = :nm "
                 "AND event_type = 'dispatched' AND batch_id = :b AND district_id = ANY(:ids)"),
            {"nm": stage_name, "b": batch_id, "ids": ids or [""]})}


def _outcome_counts_failed(batch_id: str, stage_name: str, ids: list) -> set:
    """Candidate definition A: ANY non-dispatch event finishes the district, `failed` included.

    Rejected. A batch that errored did not finish the district, and treating `failed` as terminal
    preserves #670's precedence bug (a late timeout leaves a populated captures.json, which then
    outranks the failure event). Kept here so C3 can show exactly which records the choice moves."""
    with gdb.session_scope() as con:
        return {r[0] for r in con.execute(
            text("""WITH disp AS (
                      SELECT district_id, MAX(event_id) AS dispatch_id FROM state_event
                       WHERE stage_name = :nm AND event_type = 'dispatched'
                         AND batch_id = :b AND district_id = ANY(:ids)
                       GROUP BY district_id)
                    SELECT disp.district_id FROM disp
                     WHERE EXISTS (SELECT 1 FROM state_event e
                                    WHERE e.district_id = disp.district_id AND e.stage_name = :nm
                                      AND e.event_type <> 'dispatched'
                                      AND e.event_id > disp.dispatch_id)"""),
            {"nm": stage_name, "b": batch_id, "ids": ids or [""]})}


def _age_days(stamp, now: _dt.datetime) -> str:
    """`state_event.created_at` is a VARCHAR of ISO-8601-with-Z, not a timestamp — parse, don't
    assume. The first draft of this script treated it as a datetime and silently printed an empty
    age column for every row, which is the "measurement that cannot fail" shape in miniature."""
    if not stamp:
        return "?"
    try:
        d0 = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return "?"
    if d0.tzinfo is None:
        d0 = d0.replace(tzinfo=_dt.timezone.utc)
    return f"{(now - d0).days}d"


def _redo_batches() -> list:
    with gdb.session_scope() as con:
        bids = [r[0] for r in con.execute(text("SELECT batch_id FROM batch ORDER BY batch_id"))]
    out = []
    for bid in bids:
        b = _batch_from_db(bid)
        if b and b.get("districts") and BT.redoes_attempted(b):
            out.append(b)
    return out


def _dispatch_detail(did: str, stage_name: str, batch_id: str) -> tuple:
    """(when this batch dispatched it, when its displayed outcome was actually stamped)."""
    with gdb.session_scope() as con:
        disp = con.execute(text(
            "SELECT MAX(created_at) FROM state_event WHERE district_id=:d AND stage_name=:nm "
            "AND event_type='dispatched' AND batch_id=:b"),
            {"d": did, "nm": stage_name, "b": batch_id}).scalar()
        prior = con.execute(text(
            "SELECT event_type, created_at FROM state_event WHERE district_id=:d AND stage_name=:nm "
            "AND stage IS NOT NULL ORDER BY event_id DESC LIMIT 1"),
            {"d": did, "nm": stage_name}).mappings().first()
    return disp, (prior["event_type"] if prior else None), (prior["created_at"] if prior else None)


def main() -> None:
    batches = _redo_batches()
    print(f"# 2026-08-22 · #671 batch-done predicate · {len(batches)} redo batches in the corpus\n")
    if not batches:
        print(f"C1..C4: {NOTHING} — no redo batch in the corpus; the predicate is unexercised.")
        return

    # ---------------------------------------------------------------- C1 the safety invariant
    print("## C1 — the corrected set is never a superset of the pre-fix set")
    pairs = violations = 0
    for b in batches:
        ids = [d["district_id"] for d in b["districts"]]
        for st in STAGES:
            before = _prefix_dispatch_only(b["batch_id"], st, ids)
            after = DS.completed_by_batch(b["batch_id"], st, ids)
            pairs += 1
            if after - before:
                violations += 1
                print(f"  VIOLATION {b['batch_id']} {st}: newly-done {sorted(after - before)}")
    if not pairs:
        print(f"  {NOTHING} — no batch/stage pair examined.")
    elif violations:
        print(f"  FAIL — {violations}/{pairs} pairs assert a `done` the pre-fix rule did not.")
    else:
        print(f"  HOLDS — {pairs} batch/stage pairs, 0 newly-asserted `done`. The change is")
        print("  strictly withdrawing: it cannot invent completion, only retract it.\n")

    # ---------------------------------------------------------------- C2 what it withdraws
    print("## C2 — false `done` withdrawn (dispatched by this batch, no outcome since)")
    now, rows = _dt.datetime.now(_dt.timezone.utc), []
    for b in batches:
        ids = [d["district_id"] for d in b["districts"]]
        names = {d["district_id"]: d.get("name", "") for d in b["districts"]}
        for st in STAGES:
            for did in sorted(_prefix_dispatch_only(b["batch_id"], st, ids)
                              - DS.completed_by_batch(b["batch_id"], st, ids)):
                disp, ptype, pat = _dispatch_detail(did, st, b["batch_id"])
                age = _age_days(disp, now)
                rows.append((b["batch_id"], st, did, names.get(did, "")[:22], str(disp)[:19],
                             f"{ptype or '-'} @ {str(pat)[:19]}", age))
    if not rows:
        print(f"  {NOTHING} — no district in the corpus is dispatched-without-outcome.")
        print("  (Expected once C2's population has been re-run; a green zero here is only")
        print("   meaningful alongside C1 having examined a non-zero number of pairs.)\n")
    else:
        print(f"  {len(rows)} district/stage rows read `done` off work that never happened:\n")
        print(f"  {'batch':<13}{'stage':<9}{'district':<9}{'name':<24}"
              f"{'dispatched':<21}{'displayed outcome':<42}stale")
        for r in rows:
            print(f"  {r[0]:<13}{r[1]:<9}{r[2]:<9}{r[3]:<24}{r[4]:<21}{r[5]:<42}{r[6]}")
        by_stage: dict = {}
        for r in rows:
            by_stage[r[1]] = by_stage.get(r[1], 0) + 1
        print(f"\n  by stage: {by_stage}\n")

    # ---------------------------------------------------------------- C3 the #670 boundary
    print("## C3 — does a `failed` event count as finishing? (shipped answer: no)")
    moved = []
    for b in batches:
        ids = [d["district_id"] for d in b["districts"]]
        for st in STAGES:
            a = _outcome_counts_failed(b["batch_id"], st, ids)
            shipped = DS.completed_by_batch(b["batch_id"], st, ids)
            assert not (shipped - a), f"shipped superset of A at {b['batch_id']}/{st}"
            for did in sorted(a - shipped):
                moved.append((b["batch_id"], st, did))
    if not moved:
        print(f"  {NOTHING} — no district's done-ness turns on the choice; the two definitions")
        print("  agree everywhere in the corpus today. The shipped one is still the principled")
        print("  one (a batch that errored did not finish), but this corpus cannot show it.\n")
    else:
        print(f"  {len(moved)} record(s) read `done` under A and NOT under the shipped rule —")
        print("  each one a district whose batch errored on it. These are #670's shape:\n")
        for bid, st, did in moved:
            print(f"    {bid}  {st:<9}{did}")
        print()

    # ---------------------------------------------------------------- C4 watchdog
    print("## C4 — watchdog: dispatches with no outcome since (should drain as C2 is re-run)")
    with gdb.session_scope() as con:
        tot = con.execute(text("""
            WITH disp AS (
              SELECT district_id, stage_name, batch_id, MAX(event_id) AS d FROM state_event
               WHERE event_type='dispatched' AND stage_name = ANY(:st) AND batch_id IS NOT NULL
               GROUP BY 1,2,3)
            SELECT COUNT(*) FROM disp
             WHERE NOT EXISTS (SELECT 1 FROM state_event e
                                WHERE e.district_id=disp.district_id
                                  AND e.stage_name=disp.stage_name
                                  AND e.stage IS NOT NULL AND e.event_id > disp.d)"""),
            {"st": list(STAGES)}).scalar()
    print(f"  {tot} dispatch(es) awaiting an outcome."
          + ("  (matches C2 — nothing has been re-run yet)" if tot == len(rows) else ""))


if __name__ == "__main__":
    main()
