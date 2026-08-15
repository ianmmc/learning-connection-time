"""#716 — re-aggregate a frozen Stage-7 extraction receipt through the CURRENT deterministic
consensus. ZERO model spend: the voters' (and judge's) verbatim facts are already in the receipt's
per-call records; only the deterministic half (aggregate.consensus_school_facts + band modes)
re-runs. This is the recovery path for consensus-boundary defects — a normalizer/clustering fix
lands, and every district whose stored receipt carries the defect's signature can be recovered
without re-buying the council (the anchor case: Washoe 3200480 run 7696, where ambiguous 12-hour
afternoon ends minted 67 false disagreements; re-aggregation recovers ~64 of them for $0).

Append-only, matching persist_run's own contract ("a re-run is a new extraction row, history
preserved"): the original extraction row + receipt stay untouched; the re-aggregation persists a
NEW extraction row (cost_usd=0 — the paid spend belongs to the ORIGINAL row, and the REQ-051
governor sums extraction.cost_usd, so carrying the cost again would double-charge the district) +
its school_fact rows + a new frozen receipt that names its source.

CLI-first per the ramp-up model:
    python3 -m infrastructure.acquisition.process_governance.reaggregate <receipt_path> [--dry-run]
"""
from __future__ import annotations

import json
from pathlib import Path

from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common.timeutil import fs_stamp
from infrastructure.acquisition.stage8_aggregate import aggregate as AGG
from infrastructure.acquisition.process_governance import stage7_run as S7R

CREATED_BY = "auto:reaggregate-716"


def _rebuild_rep(rep: dict) -> dict:
    """Re-run the deterministic consensus over one rep's stored per-call facts. The call records
    ride along verbatim (they are the audit trail: who said what, and what the original run cost)
    — only accepted/unresolved are recomputed."""
    voters = {c["model"]: (c.get("facts") or []) for c in rep.get("calls", [])
              if c.get("role") == "voter"}
    judges = {c["model"]: (c.get("facts") or []) for c in rep.get("calls", [])
              if c.get("role") == "judge" and c.get("facts")}
    accepted, unresolved = AGG.consensus_school_facts(voters, judges or None)
    for f in accepted:
        f["rec_key"], f["source_file"] = rep.get("rec_key"), rep.get("file")
    for u in unresolved:
        u["rec_key"], u["source_file"] = rep.get("rec_key"), rep.get("file")
    return {**rep, "judged": bool(judges), "accepted": accepted, "unresolved": unresolved}


def reaggregate_receipt(receipt_path: str, *, dry_run: bool = False) -> dict:
    """Replay `receipt_path` (an extraction_<hash>_<did>_<ts>.json central receipt) through the
    current consensus. Returns {district_id, was: {accepted, unresolved}, now: {...}, persisted}."""
    src = Path(receipt_path)
    doc = json.loads(src.read_text())
    hh, old = doc.get("handoff_hash"), doc["district"]
    did = old["district_id"]

    reps = [_rebuild_rep(r) for r in old.get("reps", [])]
    accepted = [f for r in reps for f in r["accepted"]]
    unresolved = [u for r in reps for u in r["unresolved"]]
    pd = {**old, "reps": reps, "accepted": accepted, "unresolved": unresolved,
          "n_judged": sum(1 for r in reps if r["judged"]),
          "bands": AGG.district_bands_from_facts(accepted),
          # cost_usd MUST be 0 on the new extraction row (REQ-051 double-count); the true spend
          # stays on the original row + in the carried call records. Token counts likewise.
          "telemetry": {"calls": 0, "judge_calls": 0, "errors": 0, "prompt_tokens": 0,
                        "completion_tokens": 0, "cost_usd": 0.0},
          "reaggregated_from": src.name}

    out = {"district_id": did, "handoff_hash": hh,
           "was": {"accepted": len(old.get("accepted") or []),
                   "unresolved": len(old.get("unresolved") or [])},
           "now": {"accepted": len(accepted), "unresolved": len(unresolved)},
           "persisted": False}
    if dry_run:
        return out

    d = paths.ACQUISITION / "extractions"
    d.mkdir(parents=True, exist_ok=True)
    new_path = d / f"extraction_{hh or 'nohash'}_{did}_{fs_stamp()}.json"
    paths.atomic_write_json(new_path, {"handoff_hash": hh, "district": pd})
    summary = S7R.persist_run({"handoff_hash": hh, "districts": {did: pd}},
                              created_by=CREATED_BY, receipt_path=str(new_path))
    out.update({"persisted": True, "receipt": str(new_path),
                "extraction_id": summary["districts"][0]["extraction_id"]})
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="#716: re-aggregate a frozen extraction receipt (zero model spend)")
    ap.add_argument("receipt", help="path to an extraction_<hash>_<did>_<ts>.json central receipt")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = reaggregate_receipt(a.receipt, dry_run=a.dry_run)
    tag = " (DRY RUN — nothing persisted)" if a.dry_run else ""
    print(f"{out['district_id']} @ {out['handoff_hash']}: "
          f"{out['was']['accepted']} accepted / {out['was']['unresolved']} unresolved  ->  "
          f"{out['now']['accepted']} accepted / {out['now']['unresolved']} unresolved{tag}")
    if out.get("persisted"):
        print(f"persisted extraction_id={out['extraction_id']} (cost_usd=0, append-only)\n"
              f"receipt: {out['receipt']}")


if __name__ == "__main__":
    main()
