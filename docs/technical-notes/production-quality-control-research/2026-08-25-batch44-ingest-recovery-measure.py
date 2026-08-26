#!/usr/bin/env python3
"""Verify the batch_00044 Stage-5 ingest recovery (issue #921).

WHY THIS EXISTS
    batch_00044 reached `resolved == total` at Stage 4 without its Stage-5 ingest ever firing.
    Because `_ingest_stage5_if_complete` is only reachable from the tail of a Stage-4 run, and
    `stage4.js:78` withdraws the Run control at exactly that state, the batch was unrecoverable
    from the console (#921). Recovery was a FULL `build_signals --assert-floor` re-ingest
    (Ian, 2026-08-25) rather than a bespoke `ingest_batch` call, so that one scoring vintage
    holds across the corpus instead of per-district vintages coexisting.

WHAT IT CHECKS  (read-only; imports the LIVE production functions, never a re-implementation)
    C1  Coverage — every URL in each district's processed.json has a `record` row.
        Before recovery: ADAIR 13 missing, HUNTINGTON 12 missing, 0 extra (measured 2026-08-25).
        After a successful re-ingest: 0 missing for all 8.
    C2  Direction — no `record` URL absent from processed.json. Was 0 before; must stay 0.
        A non-zero here means the ingest invented rows, which is a DIFFERENT and worse failure
        than the one we were fixing.
    C3  The Stage-5 release receipt from the `release.generate` tail of the ingest.
        CORRECTED 2026-08-25: an earlier version of this script looked for a fixed `filtered.json`
        and reported it MISSING for all 8 districts. That was a BAD CHECK, not a finding —
        REQ-164 retired the fixed filename in favour of a datetime-stamped receipt written by the
        shared `common/receipts.py::write_receipt` (`release.py:567`), and nothing reads
        filtered.json as pipeline input anyway (Stage 6 reads the release projection from gov_db).
        The check now globs the receipt the production writer actually emits, and scores its
        freshness against the ingest, so "the release tail ran" is genuinely testable.
    C4  The `stage=5` progression marker, scored for CONSISTENCY rather than a fixed number
        (corrected 2026-08-26 — see the inline note). Two legitimate states: 0 events (the
        CLI/recovery path, which bypasses `_ingest_stage5_if_complete`'s bookkeeping — the only
        writer — so the gap is #921's scope, not a failure) or one per district (the console path,
        where the Stage-4 tail wrote it). A count strictly between the two is a PARTIAL marker
        write, which neither path produces and nothing else here would catch.

VERDICT DISCIPLINE
    An empty sweep prints NOTHING MEASURED, never a green zero: if the batch cannot be loaded, or
    a district is not Stage-2-complete on disk, or processed.json is missing, that district is
    reported as UNMEASURED and the run cannot pass.

USAGE
    python3 docs/technical-notes/production-quality-control-research/\
        2026-08-25-batch44-ingest-recovery-measure.py [batch_id]      # default: batch_00044
"""
import json
import sys

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage4_process.headless import (
    RAW_DIR,
    load_batch_any,
    stage2_complete,
    status_for_batch,
)

BATCH = sys.argv[1] if len(sys.argv) > 1 else "batch_00044"

# Measured 2026-08-25, BEFORE the recovery re-ingest — the baseline this run is scored against.
PRE = {"2905790": 13, "4824000": 12}


def main() -> int:
    try:
        batch = load_batch_any(BATCH)
    except Exception as e:
        print(f"NOTHING MEASURED — could not load {BATCH}: {type(e).__name__}: {e}")
        return 2

    ids = [d["district_id"] for d in batch["districts"]]
    if not ids:
        print(f"NOTHING MEASURED — {BATCH} has zero districts")
        return 2

    rollup = status_for_batch(batch)["rollup"]
    print(f"{BATCH}: {len(ids)} districts")
    print(f"  Stage-4 rollup: resolved {rollup['resolved']}/{rollup['total']} "
          f"· todo {rollup['todo']} · failed {rollup['failed']} "
          f"· awaiting_capture {rollup['awaiting_capture']}")
    print()

    ondisk = {d["district_id"]: d for d in stage2_complete(RAW_DIR)}

    unmeasured, failures = [], []
    rows = []
    with gdb.session_scope() as s:
        for did in sorted(ids):
            dk = ondisk.get(did)
            if dk is None:
                unmeasured.append((did, "not Stage-2-complete on disk"))
                continue
            pj = dk["dir"] / "processed.json"
            if not pj.exists():
                unmeasured.append((did, "processed.json missing"))
                continue
            try:
                proc = json.loads(pj.read_text())
            except Exception as e:
                unmeasured.append((did, f"processed.json unreadable: {e}"))
                continue

            purls = {p.get("url") for p in proc if isinstance(p, dict) and p.get("url")}
            rurls = {r[0] for r in s.execute(
                text("SELECT url FROM record WHERE district_id = :d"), {"d": did})}

            missing = len(purls - rurls)      # C1
            extra = len(rurls - purls)        # C2
            # C3 — the REQ-164 stamped receipt the release tail actually writes. Newest wins;
            # its mtime must be at or after the newest processed.json this ingest consumed.
            rcpts = sorted(dk["dir"].glob("stage5_filter.*.json"),
                           key=lambda p: p.stat().st_mtime)
            rcpt = rcpts[-1] if rcpts else None
            fresh = bool(rcpt and rcpt.stat().st_mtime >= pj.stat().st_mtime)

            if missing or extra or not fresh:
                failures.append(did)
            rows.append((did, len(purls), len(rurls), missing, extra,
                         rcpt.name if rcpt else None, fresh))

    hdr = (f"{'district':<10}{'processed':>10}{'record':>8}{'missing':>9}{'extra':>7}"
           f"  stage5_filter receipt")
    print(hdr)
    print("-" * len(hdr))
    for did, np_, nr, missing, extra, rcpt_name, fresh in rows:
        note = f"   (was {PRE[did]} missing)" if did in PRE else ""
        flag = "" if not (missing or extra or not fresh) else "  <<< FAIL"
        if rcpt_name is None:
            rc = "NO RECEIPT"
        else:
            rc = f"{rcpt_name.split('.')[1]}{'' if fresh else ' STALE'}"
        print(f"{did:<10}{np_:>10}{nr:>8}{missing:>9}{extra:>7}  {rc}{note}{flag}")
    print()

    # C4 — the stage=5 progression marker. CORRECTED 2026-08-26 (found by running this against
    # batch_00058): the first version hard-coded "0 is expected", because it was written for the
    # batch_00044 RECOVERY, where a CLI re-ingest bypasses `_ingest_stage5_if_complete`'s
    # bookkeeping — the only writer of this event. Run against a healthy console-driven batch it
    # called the correct answer (one event per district) "unexpected — investigate". A measurement
    # whose expectation is hard-coded to one of its two legitimate paths reports false alarms on
    # the other.
    #
    # There are exactly two consistent states, and the script cannot know which path ran, so it
    # scores CONSISTENCY rather than a fixed number:
    #   n == 0            -> the CLI/recovery path; the marker gap is #921's remaining scope
    #   n == n_districts  -> the console path (Stage-4 tail); the seam wrote its marker, healthy
    # Anything strictly between is the real anomaly — a PARTIAL marker write, which neither path
    # produces and which no other check here would catch.
    with gdb.session_scope() as s:
        n_evt = s.execute(text(
            "SELECT COUNT(DISTINCT district_id) FROM state_event "
            "WHERE batch_id = :b AND stage = 5"), {"b": BATCH}).scalar()
    if n_evt == 0:
        c4 = "recovery/CLI path — the marker gap is #921's remaining scope, not a failure"
    elif n_evt == len(ids):
        c4 = f"console path — the Stage-4→5 seam wrote its marker for all {len(ids)}, healthy"
    else:
        c4 = (f"*** PARTIAL MARKER WRITE — {n_evt} of {len(ids)} districts. Neither path produces "
              f"this; investigate the Stage-4→5 seam ***")
        failures.append("C4-partial-marker")
    print(f"C4  districts with a stage=5 event under {BATCH}: {n_evt}/{len(ids)} — {c4}")
    print()

    for did, why in unmeasured:
        print(f"UNMEASURED  {did}: {why}")

    if unmeasured:
        print(f"\nVERDICT: NOTHING MEASURED for {len(unmeasured)} of {len(ids)} districts — cannot pass")
        return 2
    if failures:
        print(f"\nVERDICT: FAIL — {len(failures)} district(s) still short: {', '.join(failures)}")
        return 1
    tail = ("The stage=5 marker gap remains open as #921."
            if n_evt == 0 else "Stage-4→5 seam marker present — the #921 gap does not apply here.")
    print(f"\nVERDICT: PASS — all {len(rows)} districts fully ingested "
          f"(0 missing, 0 extra). {tail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
