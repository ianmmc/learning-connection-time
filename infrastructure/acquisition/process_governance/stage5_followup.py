"""Stage 5 ZERO-YIELD escalation — the 5->1 back-edge (#164 PR 3b, governance §11d).

A district can come through discovery+capture+process and land at gate@5 with NOTHING dispatchable —
zero records worth sending to the paid council, no errors to retry, nothing to triage. The #164
hypothesis for that shape is that the DOMAIN was the bottleneck (a wrong/stale/absent website), so
the escalation is a GEO-scoped rediscovery around the district's geography, not another pass over
the same domain.

This is the APP layer (may import across stages). The composer:

  * PREDICATE (per included district of a ran batch): zero dispatchable Stage-5 records (no record
    whose release decision is `send` — and none `hold` either: a held maybe-target awaiting a human
    label blocks the zero-yield conclusion, spend-conservatively) AND no retryable capture failures
    (`not_attempted*`/`not_recovered*` route to the #116 retry instead) AND no fidelity-flagged
    captures (login_wall/soft_404 route to #518 triage instead).
  * LADDER (position DERIVED from ever-approved follow-up batch history, `batch_store.
    followup_rounds` — never a stored counter): 0 geo rounds -> geo + standard vocabulary;
    1 geo round -> geo + WIDENED vocabulary; >=2 -> ladder exhausted: manual flag, no compose.
  * OUTPUT: ONE geo-scoped DRAFT follow-up batch at gate@1 — the escalation loops are individually
    gate@1'd (agreed design), so this NEVER auto-flows; Ian reviews the draft like any batch.

CLI-first per the ramp-up model; the console endpoint wraps the same function.
"""
from __future__ import annotations

from sqlalchemy import select, text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.process_governance.stage7_execute import _flag_escalation_exhausted
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue import queue_batch as Q1
from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict
from infrastructure.acquisition.stage3_capture.headless import RETRYABLE_ERR_PREFIXES
from infrastructure.acquisition.stage5_filter import release as REL

# capture.fidelity_json holds the #518 flag list (login_wall/soft_404); "flagged" = a non-empty one.
_FIDELITY_FLAGGED_SQL = ("fidelity_json IS NOT NULL AND fidelity_json NOT IN ('', '[]', '{}', 'null')")


def zero_yield_reason(session, district_id: str) -> str | None:
    """None iff the district IS zero-yield (eligible for the 5->1 geo escalation); else the
    human-readable disqualifier. Checked LIVE — never a stored verdict."""
    recs = REL.load_district_records(session, district_id)
    n_dispatchable = sum(1 for r in recs if REL.decide(r)["decision"] in ("send", "hold"))
    if n_dispatchable:
        return (f"{n_dispatchable} dispatchable/held Stage-5 record(s) — not zero-yield "
                "(a hold awaiting a label blocks escalation, spend-conservatively)")
    # #575 review: one query with conditional aggregation instead of 3 sequential round trips —
    # priority order (retry > fidelity > security_block) is preserved in the Python checks below,
    # only the I/O is combined.
    retry_where = " OR ".join(f"err LIKE :p{i}" for i in range(len(RETRYABLE_ERR_PREFIXES)))
    params = {"d": district_id, **{f"p{i}": f"{p}%" for i, p in enumerate(RETRYABLE_ERR_PREFIXES)}}
    n_retry, n_fid, n_sec = session.execute(text(
        f"SELECT COUNT(*) FILTER (WHERE {retry_where}), "
        f"COUNT(*) FILTER (WHERE {_FIDELITY_FLAGGED_SQL}), "
        f"COUNT(*) FILTER (WHERE err LIKE 'security_block%') "
        f"FROM capture WHERE district_id = :d"), params).one()
    if n_retry:
        return f"{n_retry} retryable capture failure(s) — run the #116 capture retry first"
    if n_fid:
        return f"{n_fid} fidelity-flagged capture(s) (login_wall/soft_404) — triage those first (#518)"
    # #578: a security-blocked district must NOT geo-escalate — the domain was fine, the WAF said
    # no (Rule 3: one attempt, respected). Geo rediscovery would re-derive the same blocked hosts
    # and re-pressure them. Manual triage is the only honest next step.
    if n_sec:
        return (f"{n_sec} security-blocked capture(s) (WAF challenge, one-attempt rule) — "
                "manual triage, never automatic re-pressure (#578)")
    return None


def _survey(s, b: Batch) -> tuple[list, list]:
    """(eligible BatchDistrict rows, ineligible [{district_id, name, reason}]) for a ran batch."""
    dists = list(s.scalars(select(BatchDistrict).where(
        BatchDistrict.batch_id == b.batch_id, BatchDistrict.included.is_(True))))
    eligible, ineligible = [], []
    for d in dists:
        reason = zero_yield_reason(s, d.district_id)
        if reason:
            ineligible.append({"district_id": d.district_id, "name": d.name, "reason": reason})
        else:
            eligible.append(d)
    return eligible, ineligible


def compose_zero_yield(batch_id: str, *, actor: str = "ian", session=None, dry_run: bool = False) -> dict:
    """Evaluate the zero-yield predicate over `batch_id`'s included districts and compose the
    eligible ones into ONE geo-scoped DRAFT follow-up batch (gate@1; never auto-flowed), rung-set
    per district by the derived ladder. `session` = the inject-or-own idiom (an injected test
    session does DB work only; receipts/registry never escape a rollback)."""
    def _work(s) -> dict:
        b = s.get(Batch, batch_id)
        if b is None:
            return {"ok": False, "reason": f"no such batch {batch_id}"}
        if b.batch_type == "benchmark":
            return {"ok": False, "reason": f"{batch_id} is a benchmark batch (batch_00000) — "
                                           "walled off from escalation composes"}
        if b.first_approved_at is None:
            return {"ok": False, "reason": f"{batch_id} was never approved — it never ran "
                                           "discovery, so zero-yield is undefined for it"}
        eligible, ineligible = _survey(s, b)
        if not eligible:
            return {"ok": True, "batch_id": None, "n_districts": 0, "ineligible": ineligible,
                    "flagged": [], "skipped": [], "ladder": {}}

        rounds = BSTORE.followup_rounds(s, [d.district_id for d in eligible])
        compose_rows, widen_dids, flagged = [], set(), []
        ladder = {}
        names = {d.district_id: d.name for d in eligible}   # #572: human-readable modal labels
        for d in eligible:
            rr = rounds[d.district_id]
            # #575 review: exhaustion is the ONE shared predicate (BSTORE.geo_ladder_exhausted) —
            # this composer must never disagree with the 7->1 scope-split composer about the same
            # district's ladder position.
            if BSTORE.geo_ladder_exhausted(rr):
                flagged.append({"district_id": d.district_id, "name": d.name,
                                "reason": (f"5->1 ladder exhausted: {rr['geo']} geo follow-up "
                                           "round(s) already approved — manually flagged")})
                ladder[d.district_id] = "manual_flag"
            elif rr["geo"] == 0:
                compose_rows.append(d)
                ladder[d.district_id] = "geo+standard"
            else:
                compose_rows.append(d)
                widen_dids.add(d.district_id)
                ladder[d.district_id] = "geo+widened"
        if flagged and not dry_run:
            _flag_escalation_exhausted(s, [f["district_id"] for f in flagged], rounds)
        if not compose_rows:
            return {"ok": True, "batch_id": None, "n_districts": 0, "ineligible": ineligible,
                    "flagged": flagged, "skipped": [], "ladder": ladder, "names": names}

        pre_targets = {d.district_id: list(d.lea_claimed_bands or []) for d in compose_rows}
        new_bid = f"batch_{BSTORE.next_batch_number(s):05d}"
        doc, skipped = Q1.build_followup_batch(b.nces_year or "2024_25", new_bid, pre_targets,
                                               scope="geo", force_widen_dids=widen_dids)
        if not doc["districts"]:
            return {"ok": True, "batch_id": None, "n_districts": 0, "ineligible": ineligible,
                    "flagged": flagged, "skipped": skipped, "ladder": ladder, "names": names}
        # #575 review: `targets` must reflect who actually SURVIVED build_followup_batch, not the
        # pre-build candidate set — a claimed band with no NCES school-level coverage gets silently
        # dropped into `skipped`, and the gate@1 dry-run preview must never show it as composable.
        survived = {d["district_id"] for d in doc["districts"]}
        targets = {did: bands for did, bands in pre_targets.items() if did in survived}
        if dry_run:
            return {"ok": True, "batch_id": new_bid, "dry_run": True, "scope": "geo",
                    "n_districts": len(doc["districts"]), "ladder": ladder, "names": names,
                    "ineligible": ineligible, "flagged": flagged, "skipped": skipped,
                    "targets": targets}
        BSTORE.create_batch(s, doc, batch_type="follow-up", redo_attempted=True, actor=actor)
        return {"ok": True, "batch_id": new_bid, "scope": "geo",
                "n_districts": len(doc["districts"]), "ladder": ladder, "names": names,
                "ineligible": ineligible, "flagged": flagged, "skipped": skipped,
                "targets": targets,
                "_batch_districts": [{"district_id": d["district_id"], "name": d.get("name", ""),
                                      "state": d.get("state", "")} for d in doc["districts"]]}

    if session is not None:
        out = _work(session)
        out.pop("_batch_districts", None)
        return out

    gdb.init_precious_schema()
    with gdb.session_scope() as s:
        out = _work(s)
    batch_districts = out.pop("_batch_districts", None)
    if out.get("batch_id") and batch_districts and not out.get("dry_run"):
        # Post-commit, best-effort (file-last): receipt + registry regenerable from the DB.
        try:
            with gdb.session_scope() as s:
                BSTORE.write_receipt(s, out["batch_id"])
            registry = DS.load()
            for d in batch_districts:
                DS.record_stage(registry, d["district_id"], d["name"], d["state"],
                                stage=1, stage_name="queue", outcome="queued",
                                batch_id=out["batch_id"])
            DS.save(registry)
        except Exception as e:  # noqa: BLE001 — receipts/registry are regenerable; the DB committed
            print(f"[warn] zero-yield receipt/registry refresh failed ({type(e).__name__}: {e}); "
                  f"the DB is authoritative — regenerate later")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="5->1 zero-yield geo escalation (#164 PR 3b)")
    ap.add_argument("batch_id", help="the ran (ever-approved) batch to evaluate")
    ap.add_argument("--actor", default="cli")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = compose_zero_yield(a.batch_id, actor=a.actor, dry_run=a.dry_run)
    if not out["ok"]:
        print(f"Refused: {out['reason']}")
        return
    if out.get("batch_id"):
        tag = " (DRY RUN — nothing persisted)" if out.get("dry_run") else ""
        print(f"Geo escalation draft {out['batch_id']}: {out['n_districts']} district(s){tag}. "
              f"Review at gate@1 (never auto-flowed).")
        for did, rung in out.get("ladder", {}).items():
            print(f"  {did}: {rung}")
    else:
        print("No zero-yield district composes from this batch.")
    for x in out.get("ineligible", []):
        print(f"  ineligible: {x['district_id']} {x['name']} ({x['reason']})")
    for f in out.get("flagged", []):
        print(f"  flagged: {f['district_id']} {f['name']} ({f['reason']})")
    for sk in out.get("skipped", []):
        print(f"  skipped: {sk['district_id']} ({sk['reason']})")


if __name__ == "__main__":
    main()
