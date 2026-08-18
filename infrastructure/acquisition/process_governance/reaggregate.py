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


def _rebuild_rep(rep: dict, ctx: dict = None) -> dict:
    """Re-run the deterministic consensus over one rep's stored per-call facts. The call records
    ride along verbatim (they are the audit trail: who said what, and what the original run cost)
    — only accepted/unresolved are recomputed. `ctx` is the #707 district context (labels +
    roster), sliced per-rep exactly as the production run does."""
    voters = {c["model"]: (c.get("facts") or []) for c in rep.get("calls", [])
              if c.get("role") == "voter"}
    # #742 review: NO facts-filter here — a judge call that ran but returned zero parseable facts
    # (timeout, refusal) still means the rep WAS escalated; filtering it out would flip `judged`
    # to False and make council_lab's replay treat the rep as never-escalated. An empty facts list
    # is harmless to consensus (no rows).
    judges = {c["model"]: (c.get("facts") or []) for c in rep.get("calls", [])
              if c.get("role") == "judge"}
    accepted, unresolved = AGG.consensus_school_facts(
        voters, judges or None,
        context=S7R._rep_consensus_context(ctx, rep.get("rec_key")))
    for f in accepted:
        f["rec_key"], f["source_file"] = rep.get("rec_key"), rep.get("file")
    for u in unresolved:
        u["rec_key"], u["source_file"] = rep.get("rec_key"), rep.get("file")
    # #742: `judged` unions the recompute with the ORIGINAL run's record of escalation; #741: a
    # stale per-rep `error` from the original run (#173/#184 failure path) must not survive a
    # successful recompute — a reader gating trust on rep['error'] would wrongly distrust
    # legitimately-recovered facts.
    rebuilt = {**rep, "judged": bool(judges) or bool(rep.get("judged")),
               "accepted": accepted, "unresolved": unresolved}
    rebuilt.pop("error", None)
    # #709 (REQ-174): derive the council-degraded marker from the stored call records — receipts
    # written before the marker existed (Memphis 3004896917ca, Orange 0e1bf02c3ea6) become
    # honestly distinguishable from barren on replay, zero spend. Same derivation as the live run.
    degraded = S7R.council_degraded(rep.get("calls") or [])
    if degraded:
        rebuilt["council_degraded"] = degraded
    else:
        rebuilt.pop("council_degraded", None)
    # #845 (#822): `degraded_kind` is a PROJECTION of (council_degraded, overflow) and is always
    # recomputed here through the same one fold the live paths use — never inherited from the
    # receipt, where a pre-#822 record has none and a post-#822 one may be stale.
    # `overflow` itself is deliberately NOT re-derived. It is the receipt's own dispatch-time
    # testimony ("at that moment, against that council, we judged it would not fit"), and the
    # replay has no honest way to recompute it: a pre-#822 receipt carries no n_times/n_chars for
    # the rep, and re-judging against a since-retuned registry would overwrite what WAS decided
    # with what would be decided now — the retroactive relabelling REQ-175 P7 exists to forbid.
    # A receipt without the key stays without it (un-assessable, counted as such by the rollup).
    S7R._stamp_degraded_kind(rebuilt)
    return rebuilt


def _labels_for_recs(rec_keys: list) -> dict:
    """{rec_key: primary_label} from the LIVE gov_db label table (the frozen receipt doesn't carry
    the record's human label — the working store does). Deliberately the CURRENT label, not the
    dispatch-time one production saw (#738): a human who re-labels a record is correcting the
    pipeline's input, and the replay should honor the correction — replaying a stale label would
    reproduce the mistake. Best-effort: no DB ⇒ no label context."""
    if not rec_keys:
        return {}
    try:
        from sqlalchemy import text
        from infrastructure.acquisition.common import db as gdb
        with gdb.session_scope() as s:
            return dict(s.execute(
                text("SELECT rec_key, primary_label FROM label WHERE rec_key = ANY(:k)"),
                {"k": list(rec_keys)}).all())
    except Exception as e:  # noqa: BLE001 — advisory context
        print(f"[reaggregate] label lookup failed ({type(e).__name__}: {str(e)[:80]}) — "
              "band-grain resolution disabled", flush=True)
        return {}


def reaggregate_receipt(receipt_path: str, *, dry_run: bool = False) -> dict:
    """Replay `receipt_path` (an extraction_<hash>_<did>_<ts>.json central receipt) through the
    current consensus. Returns {district_id, was: {accepted, unresolved}, now: {...}, persisted}."""
    src = Path(receipt_path)
    doc = json.loads(src.read_text())
    hh, old = doc.get("handoff_hash"), doc["district"]
    did = old["district_id"]

    ctx = S7R.consensus_context_for_district(
        did, _labels_for_recs([r.get("rec_key") for r in old.get("reps", [])]))
    reps = [_rebuild_rep(r, ctx) for r in old.get("reps", [])]
    accepted = [f for r in reps for f in r["accepted"]]
    unresolved = [u for r in reps for u in r["unresolved"]]
    pd = {**old, "reps": reps, "accepted": accepted, "unresolved": unresolved,
          "n_judged": sum(1 for r in reps if r["judged"]),
          "bands": AGG.district_bands_from_facts(accepted),
          # #843: telemetry is DERIVED from the rebuilt reps by the same rollup the live run uses,
          # so degraded_reps / degraded_kinds / overflow_unassessable ride into degraded_json and a
          # replayed degraded receipt cannot read clean at gate@7 (the "clean zero" #822 forbids,
          # and #800's rule that a replay reproduces derived markers). THEN the spend/token fields
          # are zeroed: cost_usd MUST be 0 on the new extraction row (REQ-051 double-count) — the
          # true spend stays on the original row + in the carried call records.
          "telemetry": {**S7R._rollup_tel(reps),
                        "calls": 0, "judge_calls": 0, "errors": 0, "prompt_tokens": 0,
                        "completion_tokens": 0, "cost_usd": 0.0},
          "reaggregated_from": src.name}

    out = {"district_id": did, "handoff_hash": hh,
           "was": {"accepted": len(old.get("accepted") or []),
                   "unresolved": len(old.get("unresolved") or [])},
           "now": {"accepted": len(accepted), "unresolved": len(unresolved)},
           # #843: the degraded rollup this replay WILL persist — visible on a dry run too, so an
           # operator previewing a replay sees that its zeros are (or are not) structural.
           "degraded": {"n": pd["telemetry"]["degraded_reps"],
                        "kinds": pd["telemetry"]["degraded_kinds"],
                        "unassessable": pd["telemetry"]["overflow_unassessable"]},
           "persisted": False}
    if dry_run:
        return out

    # #731 review: the replay must carry the ORIGINAL run's run_kind — persist_run defaults a
    # missing key to 'production', which would leak a benchmark/probe receipt's facts into every
    # `run_kind='production'` filter (the benchmark wall is an invariant, not operator discipline).
    # Source of truth: the original extraction row(s) for this (handoff, district) in gov_db.
    run_kind = _original_run_kind(hh, did)
    d = paths.ACQUISITION / "extractions"
    d.mkdir(parents=True, exist_ok=True)
    new_path = d / f"extraction_{hh or 'nohash'}_{did}_{fs_stamp()}.json"
    paths.atomic_write_json(new_path, {"handoff_hash": hh, "district": pd})
    summary = S7R.persist_run({"handoff_hash": hh, "run_kind": run_kind, "districts": {did: pd}},
                              created_by=CREATED_BY, receipt_path=str(new_path))
    out.update({"persisted": True, "run_kind": run_kind, "receipt": str(new_path),
                "extraction_id": summary["districts"][0]["extraction_id"]})
    # #739 review: production's persist path withdraws open directives the new facts satisfy
    # (#233) — the replay must too, or a recovered band's 7->2 sits pending until a later sweep
    # auto-rejects it via a noisier path. #800: and it must also DETECT — a marker derived on
    # replay (council_degraded, #709/#793) is only honest if it produces the remedy the
    # requirement promises; without this, the zero-spend backfill changed the receipt and nothing
    # downstream. Detect before withdraw (backfill_requests' own order); idempotent by
    # detect_and_persist_requests' two-layer dedup (#234), so replaying a receipt an earlier live
    # run already detected adds nothing. Production-only: probe/benchmark rows never drive the
    # request loop (#148).
    if run_kind == "production":
        from infrastructure.acquisition.common import db as gdb
        with gdb.session_scope() as s:
            out["new_requests"] = S7R.detect_and_persist_requests(s, pd, hh)
            withdrawn = S7R.withdraw_satisfied_requests(s, did)
        out["withdrawn_requests"] = [req_id for req_id, _note in (withdrawn or [])]
    return out


def _original_run_kind(handoff_hash: str, district_id: str) -> str:
    """The run_kind of the original extraction row(s) for this (handoff, district) — the value the
    replay must reproduce (#731). Falls back to 'production' only when no prior row exists (a
    receipt with no gov_db row is already an anomaly; the append-only row still lands reviewable)."""
    try:
        from sqlalchemy import text
        from infrastructure.acquisition.common import db as gdb
        with gdb.session_scope() as s:
            rk = s.execute(text(
                "SELECT run_kind FROM extraction WHERE handoff_hash = :h AND district_id = :d "
                "AND created_by != :rb ORDER BY extraction_id LIMIT 1"),
                {"h": handoff_hash or "", "d": district_id, "rb": CREATED_BY}).scalar()
            return rk or "production"
    except Exception as e:  # noqa: BLE001 — fail toward the reviewable default, loudly
        print(f"[reaggregate] run_kind lookup failed ({type(e).__name__}: {str(e)[:80]}) — "
              "defaulting to 'production'", flush=True)
        return "production"


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
        if "new_requests" in out:
            print(f"requests: {out['new_requests']} newly detected, "
                  f"{len(out.get('withdrawn_requests') or [])} withdrawn")


if __name__ == "__main__":
    main()
