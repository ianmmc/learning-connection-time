"""#662 — reclassify the historical benchmark-harness extractions out of the production pool.

**The original sin this corrects.** `batch_00000`'s 27 curated-GT districts were extracted by running
the council over INJECTED `gt://` representations (`capture.source='benchmark_gt'`). That is the
benchmark harness — work that structurally terminates at gate@7 and was never release data. It was
nonetheless written with `extraction.run_kind='production'`, because `run_kind` (#148) did not exist
when those runs happened and the column's `DEFAULT 'production'` swept them in.

Every downstream layer reads `run_kind='production'` as "this counts": the gate@8 review queue, the
closing-argument fact pool, and (via `IS_BENCHMARK_PROVENANCE_SQL`) the Stage-9 write wall. So the
mislabel is why an honestly re-run district still could not incorporate — the district's OLD injected
facts stayed in the pool forever (`extraction` and `school_fact` are precious and append-only, so a
re-run ADDS clean facts but can never remove the injected ones) and won the merge on earliest-run.
Full diagnosis: findings report §10.20, issue #662.

**Why a mutation is the right shape here, and why it is safe.** Measured against the live governance
DB before this was written (2026-07-26):

  * **0** extractions are MIXED. `f33790e63820` is mixed at HANDOFF level (9 districts, 3 of them
    holding `gt://` reps) but every individual extraction is cleanly all-injected or all-discovered.
    So extraction grain is surgical: this drops exactly the harness runs and no genuine work. (This
    retires the "must exclude the mixed handoff" caveat carried in §10.8 and in #662's option (c) —
    it was stated at the wrong grain.)
  * **30** extractions across exactly **27** districts, all of them `batch_type='benchmark'` members,
    none outside.
  * **0** of the 27 carry a `stage8_approval`, and **0** have any Stage-9 event. The mutation
    invalidates no frozen human judgment and no production write.

`run_kind='benchmark'` is a THIRD value beside `production` and `probe`, not a reuse of `probe`
(Ian, 2026-07-26): `probe` (#148) means a council-VARIANT measurement, and conflating the two would
make the console's run-kind filter lie about what it is showing.

**Auditability (commandment #1).** Nothing here is silent. Before any write the script emits a
per-district receipt naming every affected `extraction_id`, its handoff, its prior `run_kind`, and its
fact counts — so the change is reconstructible and reversible from disk alone. It refuses to touch a
district whose extractions are not unanimously injected, rather than guessing.

Idempotent: a re-run finds nothing (the rows are no longer `production`) and is a clean no-op.
Fail-loud: the post-write verification re-reads the DB and raises if the count moved (Rule #6).

Usage:
    python3 -m infrastructure.acquisition.maintenance.reclassify_benchmark_extractions --dry-run
    python3 -m infrastructure.acquisition.maintenance.reclassify_benchmark_extractions --apply
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import receipts as RCPT

RUN_KIND_BENCHMARK = "benchmark"
RECEIPT_BASENAME = "reclassify_benchmark_extractions"

# Every production extraction holding at least one fact whose representation was benchmark-injected,
# with the split that proves it is not mixed. Deliberately NOT keyed on batch membership: the whole
# point of epic #617 is that the district's batch history is not what decides how work is handled.
_CANDIDATES_SQL = text(f"""
SELECT e.extraction_id, e.district_id, e.handoff_hash, e.run_kind, e.created_at,
       count(*) FILTER (WHERE c.source = :src)                  AS n_injected,
       count(*) FILTER (WHERE c.source IS DISTINCT FROM :src)   AS n_other
  FROM extraction e
  JOIN school_fact f ON f.extraction_id = e.extraction_id
  JOIN record r      ON r.rec_key = f.rec_key
  JOIN capture c     ON c.district_id = r.district_id AND c.hash = r.hash
 WHERE e.run_kind = 'production'
 GROUP BY e.extraction_id, e.district_id, e.handoff_hash, e.run_kind, e.created_at
HAVING count(*) FILTER (WHERE c.source = :src) > 0
 ORDER BY e.district_id, e.extraction_id""")


def find_candidates(session) -> list[dict]:
    """The extractions this script would reclassify, each with its injected/other fact split."""
    return [dict(r._mapping) for r in session.execute(
        _CANDIDATES_SQL, {"src": BM.BENCHMARK_CAPTURE_SOURCE}).all()]


def split_mixed(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """(clean, mixed). A MIXED extraction produced both injected and discovered facts, so
    reclassifying it wholesale would drop genuine production work along with the harness run.

    None exist today. If one ever does, this script REFUSES it rather than guessing — the same
    refuse-don't-coerce posture as gate@6's freeze guard (REQ-169): the unit available here
    (`extraction.run_kind`) is coarser than the trigger (a per-fact representation), and a guard whose
    unit is coarser than its trigger must not decide on the operator's behalf."""
    clean = [c for c in candidates if not c["n_other"]]
    mixed = [c for c in candidates if c["n_other"]]
    return clean, mixed


def _district_names(session, district_ids) -> dict:
    if not district_ids:
        return {}
    return {r[0]: r[1] for r in session.execute(
        text("SELECT district_id, name FROM district WHERE district_id = ANY(:d)"),
        {"d": list(district_ids)})}


def _write_receipts(session, clean: list[dict]) -> list[str]:
    """One receipt per district, written BEFORE the update — the restore point. Each names the exact
    rows and their prior value, so the change is reversible from disk with no DB history needed."""
    by_district: dict[str, list[dict]] = {}
    for c in clean:
        by_district.setdefault(c["district_id"], []).append(c)
    names = _district_names(session, by_district)
    written = []
    for did, rows in sorted(by_district.items()):
        payload = {
            "action": "reclassify_benchmark_extractions",
            "issue": "#662",
            "district_id": did,
            "from_run_kind": "production",
            "to_run_kind": RUN_KIND_BENCHMARK,
            "reason": ("every fact in these extractions came from a benchmark-injected representation "
                       f"(capture.source='{BM.BENCHMARK_CAPTURE_SOURCE}'); the runs were the GT harness, "
                       "not release work, and predate run_kind (#148)"),
            "extractions": [
                {"extraction_id": r["extraction_id"], "handoff_hash": r["handoff_hash"],
                 "prior_run_kind": r["run_kind"], "created_at": r["created_at"],
                 "n_injected_facts": r["n_injected"], "n_other_facts": r["n_other"]}
                for r in sorted(rows, key=lambda x: x["extraction_id"])],
        }
        written.append(str(RCPT.write_receipt(did, names.get(did, did), RECEIPT_BASENAME, payload)))
    return written


def reclassify(session, *, apply: bool = False) -> dict:
    """Find, receipt, and (with `apply`) reclassify. Returns a summary dict either way."""
    candidates = find_candidates(session)
    clean, mixed = split_mixed(candidates)
    summary = {"n_candidates": len(candidates), "n_clean": len(clean), "n_mixed": len(mixed),
               "districts": sorted({c["district_id"] for c in clean}),
               "extraction_ids": sorted(c["extraction_id"] for c in clean),
               "mixed": mixed, "applied": False, "receipts": []}
    if mixed:
        raise ValueError(
            f"REFUSING: {len(mixed)} extraction(s) produced BOTH injected and discovered facts, so "
            f"reclassifying them would drop genuine production work: "
            f"{[(m['extraction_id'], m['district_id'], m['n_injected'], m['n_other']) for m in mixed]}. "
            f"These need a per-fact decision (band_exclusion at gate@8), not a run_kind sweep.")
    if not clean or not apply:
        return summary          # idempotent when there is nothing left; a DRY RUN writes NOTHING
    # The restore point, written INSIDE the apply path and BEFORE the UPDATE. Deliberately not on the
    # dry-run path: receipts are datetime-stamped, so a dry run that wrote them would leave a fresh
    # set on every rehearsal (27 districts x N runs) and the operator could no longer tell the
    # manifest of a real change from the litter of the rehearsals.
    summary["receipts"] = _write_receipts(session, clean)
    session.execute(text("UPDATE extraction SET run_kind = :rk WHERE extraction_id = ANY(:ids)"),
                    {"rk": RUN_KIND_BENCHMARK, "ids": summary["extraction_ids"]})
    session.flush()
    # Rule #6: verify in the DB, never trust the write. Both directions — the rows moved, and nothing
    # else did.
    still = session.execute(
        text("SELECT count(*) FROM extraction WHERE extraction_id = ANY(:ids) AND run_kind='production'"),
        {"ids": summary["extraction_ids"]}).scalar()
    if still:
        raise RuntimeError(f"reclassify FAILED verification: {still} row(s) still run_kind='production'")
    moved = session.execute(
        text("SELECT count(*) FROM extraction WHERE extraction_id = ANY(:ids) AND run_kind = :rk"),
        {"ids": summary["extraction_ids"], "rk": RUN_KIND_BENCHMARK}).scalar()
    if moved != len(summary["extraction_ids"]):
        raise RuntimeError(f"reclassify FAILED verification: expected {len(summary['extraction_ids'])} "
                           f"rows at run_kind='{RUN_KIND_BENCHMARK}', found {moved}")
    summary["applied"] = True
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="report only — writes nothing at all")
    g.add_argument("--apply", action="store_true", help="write receipts, then reclassify")
    args = ap.parse_args()

    gdb.init_precious_schema()
    with gdb.session_scope() as s:
        summary = reclassify(s, apply=args.apply)
        if not summary["n_clean"]:
            print("[reclassify] nothing to do — no production extraction holds injected-rep facts.")
            return
        print(f"[reclassify] {summary['n_clean']} extraction(s) across "
              f"{len(summary['districts'])} district(s)")
        for did in summary["districts"]:
            eids = [c for c in find_candidates(s) if c["district_id"] == did] if not args.apply else []
            print(f"  {did}" + (f"  extractions={[c['extraction_id'] for c in eids]}" if eids else ""))
        print(f"[reclassify] receipts written: {len(summary['receipts'])}"
              if summary["applied"] else
              f"[reclassify] would write {len(summary['districts'])} receipt(s) on --apply")
        if summary["applied"]:
            print(f"[reclassify] APPLIED — run_kind='{RUN_KIND_BENCHMARK}' verified in the DB.")
        else:
            print("[reclassify] DRY RUN — no rows changed. Re-run with --apply.")
        print(json.dumps({k: summary[k] for k in ("n_clean", "districts", "extraction_ids", "applied")},
                         indent=2))


if __name__ == "__main__":
    main()
