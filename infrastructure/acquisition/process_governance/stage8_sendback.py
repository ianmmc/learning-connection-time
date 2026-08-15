"""gate@8 SEND-BACK routing — the 8->1 / 8->6 back-edges (#689, epic #92).

Four docstrings and the console itself promised these edges ("'sent_back' … → an 8->1/8->6
back-edge"); no code composed either. Clicking **Send back** wrote the precious approval row, the
state_event, the calibration verdict and blocked the Stage-9 write — all correct — and then **routed
nothing**. The district's `furthest_stage` stayed 8, no queue received it, and the reason (which IS
the routing instruction) waited for a human to remember it and act by hand in another stage's UI.
Broward `1200180` is the live pin: sent back 2026-07-29, re-composed by hand days later.

This is the APP layer (may import across stages), and it composes with the SAME machinery the other
back-edges use — never a parallel path:

  * **8->1 (rediscover)** — "go find better/newer evidence" (Broward's case: a thin sample, find the
    fresh Opening & Closing Schools PDF). Builds ONE targeted DRAFT Stage-1 follow-up batch for this
    district through `Q1.build_followup_batch`, shaped by the same #162 untried-schools / #499
    unfilled-slot inputs the 7->2 composer uses, with the send-back reason riding as the note.
  * **8->6 (redispatch)** — "the evidence is there; the wrong reps were sent". Seeds a new gate@6
    DRAFT dispatch with this district via the existing draft store. Cheaper: no new discovery.

Three properties, all from the issue:

  1. **Choice, not automation.** Nothing fires on send-back. The human picks the route (or neither) —
     consistent with the ramp-up posture; the win is that the console EXECUTES the choice instead of
     making the operator translate their own reason into another stage's UI.
  2. **The linkage is recorded.** Each routing appends a `send_back_routed` state_event carrying the
     approval_id and the artifact it produced, so "what did approval 1568 produce?" has an answer.
  3. **"Sent back and never re-routed" is queryable** (`unrouted_send_backs`) — the silent-parked
     state becomes a list instead of a silence. Same shape as #682's `incorporation_blocked`: an
     unowned state is a defect, and the fix is to give it a record.

Never auto-flows: like the 5->1 zero-yield escalation, a send-back batch is individually gate@1'd.
CLI-first per the ramp-up model; the console endpoints wrap the same functions.
"""
from __future__ import annotations

import json

from sqlalchemy import text

from infrastructure.acquisition.common import batch_types as BT
from infrastructure.acquisition.common import budget as BUD
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import discovered_domain as DDOM
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common.timeutil import utcnow
from infrastructure.acquisition.process_governance import stage6_draft_store as DSTORE6
from infrastructure.acquisition.process_governance import stage7_execute as EX7
from infrastructure.acquisition.process_governance.stage7_execute import (
    _attempted_schools,
    _district_target_bands,
    _unfilled_slots_now,
)
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue import queue_batch as Q1
from infrastructure.acquisition.stage8_aggregate import approval as APV8
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA8

ROUTE_REDISCOVER = "8->1"    # a Stage-1 follow-up batch — go find better/newer evidence
ROUTE_REDISPATCH = "8->6"    # a gate@6 draft — the evidence exists, the reps chosen were wrong
ROUTES = (ROUTE_REDISCOVER, ROUTE_REDISPATCH)

ROUTED_CHECKPOINT = "send_back_routed"


def _target_bands(session, district_id: str, ca: dict) -> list:
    """The bands an 8->1 re-targets: every band in the pool that is not REQ-149 SATISFIED.

    The signal is REQ-149's per-band `satisfied` flag on the live closing argument — the SAME
    coverage/plurality test the 7->2 compose gate suppresses spend on (#771). The earlier draft keyed
    on `negative_space.unsatisfied_bands`, a cruder zero-facts-only signal: one thin fact removed a
    band from it, so a genuinely thin band was silently EXCLUDED from the re-target whenever a
    zero-fact sibling eclipsed it — precisely the band a thin-sample send-back is about. Under the
    REQ-149 rule zero-fact and thin-but-unsatisfied bands are both targets, and only a confidently
    resolved band is spared re-discovery.

    If EVERYTHING is satisfied (odd for a send-back, but the human explicitly asked), fall back to the
    whole pool — the Broward thin-evidence read: re-target the district rather than refuse.

    The pool: `real` (the bands ≥1 real school actually serves) by MEMBERSHIP, never truthiness
    (#757) — `real_bands_for_district` can legitimately return an EMPTY set for a present district
    (zero-school rosters, a crosswalk-degenerate record), and that is an authoritative "no real
    bands", not an invitation to fall back to phantom claimed bands. Same membership idiom as the
    sibling compose gate (`did not in real_bands or b in real_bands[did]`)."""
    claimed, real, _ = _district_target_bands(session, [district_id])
    if district_id in real:
        pool = list(real[district_id])
    else:
        pool = list(claimed.get(district_id) or [])
    satisfied = {b for b, ob in (ca.get("bands") or {}).items()
                 if ((ob or {}).get("satisfied") or {}).get("satisfied")}
    targets = [b for b in pool if b not in satisfied]
    return targets or pool


def _record_routing(session, district_id, *, route, approval_id, artifact, actor, reason,
                    name="", state=None) -> None:
    """The linkage (#689 acceptance 2): given approval_id N, the DB answers "what did this send-back
    produce?". Append-only state_event at stage 8 — no schema change, and the precious
    `stage8_approval` row is never mutated (favor append over mutate on precious state)."""
    session.execute(DS.INSERT_STATE_EVENT, {
        "district_id": district_id, "name": name, "state": state,
        "stage": 8, "stage_name": "aggregate", "checkpoint": ROUTED_CHECKPOINT,
        "event_type": ROUTED_CHECKPOINT, "outcome": route, "topology": None,
        "batch_id": artifact if route == ROUTE_REDISCOVER else None,
        "fingerprints_json": json.dumps({"approval_id": approval_id, "route": route,
                                         "artifact": artifact}),
        "actor": actor,
        "note": f"{route} → {artifact}" + (f" (send-back reason: {reason})" if reason else ""),
        "created_at": utcnow()})


def routing_for(session, district_id: str, approval_id) -> dict | None:
    """What THIS send-back produced, or None. Keyed on approval_id, not district: an earlier
    send-back's routing must never make a NEW one look already-handled."""
    for row in session.execute(text(
            "SELECT outcome, note, fingerprints_json, created_at FROM state_event "
            "WHERE district_id=:d AND checkpoint=:c ORDER BY event_id DESC"),
            {"d": district_id, "c": ROUTED_CHECKPOINT}).mappings().all():
        fp = json.loads(row["fingerprints_json"] or "{}")
        if approval_id is None or fp.get("approval_id") == approval_id:
            return {"route": row["outcome"], "artifact": fp.get("artifact"),
                    "note": row["note"], "created_at": row["created_at"]}
    return None


def route_send_back(district_id: str, *, route: str, actor: str = "ian", year: str = "2024_25",
                    dry_run: bool = False, session=None) -> dict:
    """Execute the human's chosen back-edge for a SENT-BACK district. Returns
    {ok, route, artifact, targets, skipped, ...}; `ok=False` + `reason` on a refusal.

    `session` = the inject-or-own idiom (an injected test session does DB work only, so receipts and
    the registry never escape a rollback) — matching the 5->1 composer."""
    if route not in ROUTES:
        return {"ok": False, "reason": f"route must be one of {ROUTES} (got {route!r})"}

    def _work(s) -> dict:
        if not dry_run:
            # #754: the already-routed check below is a read-then-act; two concurrent routes for the
            # same send-back (two tabs, a double-POST) could both read `prior=None` and mint two
            # artifacts, with routing_for's newest-first read silently masking the first. state_event
            # is append-only by design (no unique key to lean on), so serialize the check+compose in
            # a per-district transaction-scoped advisory lock: the second route waits, then reads the
            # first's committed record and refuses honestly. Dry-run skips the lock (read-only).
            s.execute(text("SELECT pg_advisory_xact_lock(hashtext('sendback:' || CAST(:d AS text)))"),
                      {"d": district_id})
        latest = APV8.latest_decision(s, district_id)
        if not latest:
            return {"ok": False, "reason": f"{district_id} has no gate@8 decision to route"}
        if latest["disposition"] != "sent_back":
            return {"ok": False, "reason": (f"{district_id}'s latest gate@8 decision is "
                                            f"'{latest['disposition']}', not 'sent_back' — only a "
                                            "send-back has a back-edge to route")}
        approval_id = latest["approval_id"]
        prior = routing_for(s, district_id, approval_id)
        if prior:
            # #761: refuse UNIFORMLY — a dry-run of an already-routed send-back used to fall through
            # and return a fake fresh preview (a batch id that a real call would then refuse to
            # mint), with nothing in the payload saying the routing already happened.
            return {"ok": False, "reason": (f"this send-back (approval {approval_id}) was already "
                                            f"routed {prior['route']} → {prior['artifact']} — act on "
                                            "that artifact rather than composing a second one"),
                    "already_routed": prior}
        meta = s.execute(text("SELECT name, state FROM district WHERE district_id = :d"),
                         {"d": district_id}).mappings().first() or {}
        common = {"ok": True, "route": route, "district_id": district_id,
                  "approval_id": approval_id, "reason_given": latest.get("reason"),
                  "name": meta.get("name", ""), "state": meta.get("state")}

        if route == ROUTE_REDISPATCH:
            # 8->6: no new discovery — seed a gate@6 draft with this district and let the human pick
            # different representations there (the cheap route, mirroring 7->6).
            if dry_run:
                return {**common, "dry_run": True, "artifact": None,
                        "plan": "a NEW gate@6 draft dispatch seeded with this district"}
            draft_id = DSTORE6.create_draft(s, actor=actor)
            DSTORE6.add_district(s, draft_id, district_id,
                                 meta={"name": meta.get("name", ""), "state": meta.get("state")})
            _record_routing(s, district_id, route=route, approval_id=approval_id,
                            artifact=draft_id, actor=actor, reason=latest.get("reason"),
                            name=meta.get("name", ""), state=meta.get("state"))
            return {**common, "artifact": draft_id}

        # 8->1: one targeted DRAFT follow-up batch for this district, gate@1-reviewable.
        ca = CA8.load_closing_argument(s, district_id, record_drift_event=False)
        bands = _target_bands(s, district_id, ca)
        if not bands:
            return {"ok": False, "reason": (f"{district_id} has no target band to re-discover (no "
                                            "real/claimed bands on record) — an 8->1 would compose "
                                            "an empty batch")}
        targets = {district_id: bands}
        attempted = _attempted_schools(s, [district_id])
        unfilled = _unfilled_slots_now(s, [district_id])
        slot_targets = {did: {b: m[b] for b in bands if b in m} for did, m in unfilled.items()}
        slot_targets = {did: m for did, m in slot_targets.items() if m}
        # #769: the #159 hold, SURFACED not enforced — the ordinary compose path defers a district's
        # new work while a fresh, un-executed 7->6 (an already-captured alternate rep, free to try)
        # is pending. An 8->1 is the human's explicit choice, so it must not be blocked by a
        # heuristic — but the human deserves to see the free option before spending on discovery.
        held = bool(EX7._defer_76_districts(s, [district_id], BUD.load_budget().max_request_rounds))
        # #752: the scope is a DIAGNOSIS, not a default — the same rule the 7->1 and 5->1 composers
        # follow (#719/#726). scope="domain" hardcoded here reproduced the exact dead end #646 exists
        # to close, one edge over: a domain-less district's 8->1 hit the #229 refusal and the
        # back-edge was a permanent dead end for precisely the class geo exists for.
        dd = DDOM.all_confirmed(s)
        domain, _src = Q1.usable_scoping_domains(year, [district_id], dd).get(district_id, ("", ""))
        scope = "domain" if domain else "geo"
        new_bid = f"batch_{BSTORE.next_batch_number(s):05d}"
        doc, skipped = Q1.build_followup_batch(
            year, new_bid, targets, attempted_by_did=attempted, preferred_by_did=slot_targets,
            scope=scope, discovered_domains=dd)
        if not doc["districts"]:
            return {"ok": False, "reason": (f"{district_id} is not composable into a follow-up batch: "
                                            + "; ".join(x.get("reason", "") for x in skipped)),
                    "skipped": skipped}
        # #764: the batch declares WHO composed it and why. followup_rounds counts every approved
        # follow-up batch toward the shared escalation ladder regardless of composer — deliberate
        # (spend is spend; the ladder is the spend-conservative bound) — so the audit trail must let
        # a human see, when a ladder reads exhausted, that one of its rounds was an 8->1 remediation.
        doc["composed_by"] = (f"8->1 send-back routing (approval {approval_id})"
                              + (f": {latest.get('reason')}" if latest.get("reason") else ""))
        if dry_run:
            return {**common, "dry_run": True, "artifact": new_bid, "targets": bands, "scope": scope,
                    "open_76": held, "skipped": skipped,
                    "n_schools": len(doc["districts"][0].get("schools") or [])}
        BSTORE.create_batch(s, doc, batch_type=BT.FOLLOW_UP, actor=actor,
                            redo_attempted=BT.default_redo_attempted(BT.FOLLOW_UP))
        _record_routing(s, district_id, route=route, approval_id=approval_id, artifact=new_bid,
                        actor=actor, reason=latest.get("reason"),
                        name=meta.get("name", ""), state=meta.get("state"))
        return {**common, "artifact": new_bid, "targets": bands, "scope": scope, "open_76": held,
                "skipped": skipped,
                "_registry": {"district_id": district_id, "name": meta.get("name", ""),
                              "state": meta.get("state"), "batch_id": new_bid}}

    if session is not None:
        out = _work(session)
        out.pop("_registry", None)
        return out

    gdb.init_precious_schema()
    with gdb.session_scope() as s:
        out = _work(s)
    reg = out.pop("_registry", None)
    if reg and not out.get("dry_run"):
        # #765: the ONE shared post-commit receipt+registry refresh (batch_store) — this block used
        # to be the third hand-copy beside the 5->1 and 7->1 composers'.
        BSTORE.finalize_composed_batches([reg["batch_id"]], [reg])
    return out


def unrouted_send_backs(session) -> list:
    """#689 acceptance 3 — the districts whose CURRENT gate@8 state is 'sent back' and which have no
    routing on record. Before this, a forgotten send-back was indistinguishable from a handled one:
    both were simply a row nobody was looking at.

    Latest decision per district (DISTINCT ON), filtered to `sent_back`, minus the ones whose own
    approval_id appears in a `send_back_routed` event."""
    rows = [dict(m) for m in session.execute(text(
        "SELECT DISTINCT ON (district_id) district_id, approval_id, disposition, reason, actor, "
        "created_at FROM stage8_approval ORDER BY district_id, approval_id DESC")).mappings().all()
        if m["disposition"] == "sent_back"]
    if not rows:
        return []
    routed = set()
    for m in session.execute(text(
            "SELECT fingerprints_json FROM state_event WHERE checkpoint = :c"),
            {"c": ROUTED_CHECKPOINT}).mappings().all():
        try:
            routed.add(json.loads(m["fingerprints_json"] or "{}").get("approval_id"))
        except (TypeError, ValueError):
            continue
    return [r for r in rows if r["approval_id"] not in routed]


def main():
    import argparse
    ap = argparse.ArgumentParser(description="gate@8 send-back routing — the 8->1/8->6 back-edges (#689)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("route", help="route one sent-back district")
    r.add_argument("district_id")
    r.add_argument("--route", choices=list(ROUTES), default=ROUTE_REDISCOVER)
    r.add_argument("--actor", default="cli")
    r.add_argument("--year", default="2024_25")
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("unrouted", help="list sent-back districts with no routing on record")
    a = ap.parse_args()

    if a.cmd == "unrouted":
        gdb.init_precious_schema()
        with gdb.session_scope() as s:
            rows = unrouted_send_backs(s)
        if not rows:
            print("No unrouted send-backs.")
            return
        print(f"{len(rows)} sent back with nothing composed:")
        for x in rows:
            print(f"  {x['district_id']} (approval {x['approval_id']}, {x['created_at']}) "
                  f"— {x['reason']}")
        return

    out = route_send_back(a.district_id, route=a.route, actor=a.actor, year=a.year,
                          dry_run=a.dry_run)
    if not out["ok"]:
        print(f"Refused: {out['reason']}")
        return
    tag = " (DRY RUN — nothing persisted)" if out.get("dry_run") else ""
    print(f"{out['route']} → {out.get('artifact') or out.get('plan')}{tag}")
    if out.get("targets"):
        print(f"  target bands: {', '.join(out['targets'])}")
    for sk in out.get("skipped", []):
        print(f"  skipped: {sk.get('district_id')} ({sk.get('reason')})")


if __name__ == "__main__":
    main()
