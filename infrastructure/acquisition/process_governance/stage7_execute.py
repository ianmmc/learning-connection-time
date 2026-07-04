"""Stage 7 request-more-evidence EXECUTION (REQ-118) — turn APPROVED gate@7 directives into real
back-edge work. This is the APP layer, so it is allowed to import across stages (the stage7 model +
the Stage-1 batch builder + the Stage-6 dispatch bridge); the stage packages stay independent.

Two mechanisms, matching the two shapes of an approved `ExtractionRequest` (STAGE7 §3F, governance
§11d):

  * NEW capture/discovery (7->2 rediscover, 7->3 recapture, 7->1 add-schools) → `compose_followup_batch`
    collects the approved directives into ONE targeted Stage-1 **follow-up batch** (batch_type=
    'follow-up'), a DRAFT reviewable at gate@1. Nothing runs straight to discovery — governance §11d:
    anything needing new capture/discovery returns to Stage 1, stays human-reviewable, and only then
    walks 2→3→4→5→6→7 normally. Collected into one batch honoring the 12-district cap (spillover → the
    next compose).

  * EXISTING representations (7->6 alternate-rep re-dispatch) → `execute_alternate_dispatch` (Slice 4)
    builds a NEW immutable Stage-6 dispatch from the named alternate reps and re-enters Stage 7 via the
    normal extract path — no new capture, so it bypasses Stage 1 (the one legitimate back-edge that does).

Guards: the REQ-051 budget governor's `max_request_rounds` is the per-district×band DEPTH guard, so the
cyclic loop provably terminates; the paid 7->6 re-extraction is budget-gated before any OpenRouter call.
An 'executed' directive is never re-fired (idempotency), and its `executed_ref` records the batch_id /
handoff_hash it produced (lineage).
"""
from __future__ import annotations

import json

from sqlalchemy import text

from pathlib import Path

from infrastructure.acquisition.common import budget as BUD
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.process_governance import stage6_dispatch as H6
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue import queue_batch as Q1
from infrastructure.acquisition.stage5_filter import release as REL
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import cost as COST6
from infrastructure.acquisition.stage6_handoff import handoff as HND
from infrastructure.acquisition.stage6_handoff import package as PKG6
from infrastructure.acquisition.stage7_extract import content as CONTENT
from infrastructure.acquisition.stage7_extract import models as M7
from infrastructure.acquisition.stage7_extract import requests as RQ

# The routes that need NEW capture/discovery and therefore route through a Stage-1 follow-up batch.
# 7->6 (existing reps) is the direct-dispatch path (execute_alternate_dispatch), NOT a batch route.
# Imported from the detector's canonical constants (issue #147) — never re-spell route strings.
NEWWORK_ROUTES = (RQ.ROUTE_REDISCOVER, RQ.ROUTE_RECAPTURE, RQ.ROUTE_ADD_SCHOOLS)


# ---------------------------------------------------------------------------
# Pure planner (no DB/network) — the collect / depth-guard / cap / band-expand logic
# ---------------------------------------------------------------------------
def plan_followup(requests: list, *, claimed_bands: dict, executed_rounds: dict = None,
                  cap: int = 12, max_rounds: int = None) -> dict:
    """Decide the follow-up batch from approved NEW-work request dicts — PURE (unit-testable, the real
    logic). Steps: filter to NEW-work routes → apply the per-district×band DEPTH guard → group by
    district in first-seen order (upstream attention sort preserved) → apply the 12-district cap
    (overflow spills, its requests left un-swept) → per kept district, the union of target bands (an
    explicit `band` from 7->2; a band-less 7->3/7->1 expands to the district's claimed bands).

    requests:        [{request_id, district_id, route, band}]  (band may be None)
    claimed_bands:   {district_id: [band, ...]}                 (for band-less expansion)
    executed_rounds: {(district_id, band): n_already_executed}  (depth guard; band key may be None)
    Returns {targets: {did: [band,...]}, swept_ids: [...], spilled: [{district_id, reason}],
             blocked: [{request_id, district_id, band, reason}]}."""
    executed_rounds = executed_rounds or {}
    blocked, eligible = [], []
    for r in requests:
        if r["route"] not in NEWWORK_ROUTES:
            continue
        did, band = r["district_id"], r.get("band")
        used = executed_rounds.get((did, band), 0)
        if max_rounds is not None and used >= max_rounds:
            blocked.append({"request_id": r["request_id"], "district_id": did, "band": band,
                            "reason": f"depth guard: {used} round(s) already executed (max {max_rounds})"})
            continue
        eligible.append(r)

    by_district: dict = {}
    for r in eligible:                       # first-seen order preserves the upstream attention sort
        by_district.setdefault(r["district_id"], []).append(r)

    ordered = list(by_district)
    kept, overflow = ordered[:cap], ordered[cap:]
    spilled = [{"district_id": d, "reason": f"{cap}-district follow-up cap reached; spills to the next batch"}
               for d in overflow]

    targets, swept_ids = {}, []
    for did in kept:
        bands: list = []
        for r in by_district[did]:
            if r.get("band"):
                if r["band"] not in bands:
                    bands.append(r["band"])
            else:
                for b in claimed_bands.get(did, []):
                    if b not in bands:
                        bands.append(b)
            swept_ids.append(r["request_id"])
        targets[did] = bands
    return {"targets": targets, "swept_ids": swept_ids, "spilled": spilled, "blocked": blocked}


# ---------------------------------------------------------------------------
# DB glue — read approved directives, plan, build + persist a DRAFT follow-up batch, flip requests
# ---------------------------------------------------------------------------
def _approved_newwork(session, handoff_hash: str = None) -> list:
    q = ("SELECT request_id, district_id, route, band FROM extraction_request "
         "WHERE status = 'approved' AND route = ANY(:routes)")
    params = {"routes": list(NEWWORK_ROUTES)}
    if handoff_hash:
        q += " AND handoff_hash = :h"
        params["h"] = handoff_hash
    q += " ORDER BY request_id"
    return [dict(m) for m in session.execute(text(q), params).mappings()]


def _claimed_bands(session, district_ids: list) -> dict:
    if not district_ids:
        return {}
    rows = session.execute(text(
        "SELECT district_id, lea_claimed_bands_json FROM district_target WHERE district_id = ANY(:d)"),
        {"d": list(district_ids)})
    out = {}
    for did, cb in rows:
        try:
            out[did] = json.loads(cb) if cb else []
        except (TypeError, json.JSONDecodeError):
            out[did] = cb if isinstance(cb, list) else []
    return out


def _executed_rounds(session, district_ids: list) -> dict:
    """{(district_id, band): count} of already-EXECUTED directives — the depth-guard history,
    scoped to the districts under consideration (issue #148: never a full-table aggregate)."""
    if not district_ids:
        return {}
    rows = session.execute(text(
        "SELECT district_id, band, COUNT(*) FROM extraction_request "
        "WHERE status = 'executed' AND district_id = ANY(:d) GROUP BY district_id, band"),
        {"d": list(district_ids)})
    return {(r[0], r[1]): r[2] for r in rows}


def _benchmark_district_ids(session, district_ids: list) -> set:
    """The subset of `district_ids` belonging to any batch_type='benchmark' batch (batch_00000 —
    permanently WALLED OFF from Stage-9 writes and funnel/enrichment stats, CLAUDE.md). Request
    execution must never rebadge these into a follow-up batch (issue #134)."""
    if not district_ids:
        return set()
    rows = session.execute(text(
        "SELECT DISTINCT bd.district_id FROM batch_district bd "
        "JOIN batch b ON b.batch_id = bd.batch_id "
        "WHERE b.batch_type = 'benchmark' AND bd.district_id = ANY(:d)"),
        {"d": list(district_ids)})
    return {r[0] for r in rows}


def _gather(session, handoff_hash: str) -> tuple:
    """Read the detector inputs on `session`: the approved NEW-work rows (benchmark districts
    EXCLUDED — the wall, #134), per-district claimed bands (band-less expansion), the executed-round
    history (depth guard), and the next free batch id.

    Returns (rows, claimed, exec_rounds, batch_id, benchmark_excluded)."""
    rows = _approved_newwork(session, handoff_hash)
    if not rows:
        return rows, {}, {}, None, []
    dids = sorted({r["district_id"] for r in rows})
    bm = _benchmark_district_ids(session, dids)
    benchmark_excluded = [{"district_id": r["district_id"], "request_id": r["request_id"],
                           "reason": "benchmark district (batch_00000) — walled off from execution"}
                          for r in rows if r["district_id"] in bm]
    rows = [r for r in rows if r["district_id"] not in bm]
    if not rows:
        return rows, {}, {}, None, benchmark_excluded
    dids = sorted({r["district_id"] for r in rows})
    claimed = _claimed_bands(session, dids)
    exec_rounds = _executed_rounds(session, dids)
    batch_id = f"batch_{BSTORE.next_batch_number(session):05d}"
    return rows, claimed, exec_rounds, batch_id, benchmark_excluded


def _flip(session, swept_ids: list, executed_ref: str) -> None:
    """Flip the swept directives to 'executed' with `executed_ref` (the follow-up batch_id, or the
    7->6 dispatch's handoff_hash) as their lineage, guarded on status='approved' so a partial retry
    never double-flips (idempotency). The ONE home for this statement (issue #147)."""
    session.execute(text(
        "UPDATE extraction_request SET status = 'executed', executed_ref = :b, executed_at = :t "
        "WHERE request_id = ANY(:ids) AND status = 'approved'"),
        {"b": executed_ref, "t": M7.utcnow(), "ids": list(swept_ids)})


def compose_followup_batch(*, year: str = "2024_25", actor: str = "ian", handoff_hash: str = None,
                           cap: int = 12, session=None) -> dict:
    """Sweep APPROVED 7->2/7->3/7->1 directives into ONE targeted, DRAFT Stage-1 follow-up batch
    (reviewable at gate@1), flipping the swept directives to 'executed' with the batch_id as their
    `executed_ref`. Benchmark (batch_00000) districts are EXCLUDED — the wall (#134). Scope to one
    run with `handoff_hash`, else all approved NEW-work directives.

    ATOMICITY (#139): the batch rows + the directive flip commit in ONE transaction (batch_store on
    the same session), so a crash can never leave a batch persisted with its directives still
    'approved' (the duplicate-batch hazard). Only directives whose district actually made it into the
    batch are flipped — a district build_followup_batch skips stays 'approved' and re-sweepable
    (#136). The regenerable receipt file + the registry updates happen AFTER commit (file-last, like
    dispatch_handoff), best-effort. `session` = the inject-or-own idiom: an injected (test) session
    does the DB work only — no receipt/registry side effects escape a rollback.
    Returns {batch_id, n_requests, n_districts, targets, spilled, blocked, skipped, benchmark_excluded}."""
    b = BUD.load_budget()

    def _work(s) -> dict:
        rows, claimed, exec_rounds, batch_id, bm_excluded = _gather(s, handoff_hash)
        if not rows:
            return {**_empty_result(), "benchmark_excluded": bm_excluded}

        plan = plan_followup(rows, claimed_bands=claimed, executed_rounds=exec_rounds,
                             cap=cap, max_rounds=b.max_request_rounds)
        if not plan["targets"]:
            return {**_empty_result(), "spilled": plan["spilled"], "blocked": plan["blocked"],
                    "benchmark_excluded": bm_excluded}

        batch_doc, skipped = Q1.build_followup_batch(year, batch_id, plan["targets"])
        if not batch_doc["districts"]:            # every target district was un-buildable (no coverage)
            return {**_empty_result(), "spilled": plan["spilled"], "blocked": plan["blocked"],
                    "skipped": skipped, "benchmark_excluded": bm_excluded}

        # Rows + flip on ONE session (atomic, #139). Flip ONLY the directives whose district made it
        # into the batch (#136) — a skipped district's directive stays 'approved', re-sweepable.
        BSTORE.create_batch(s, batch_doc, batch_type="follow-up", actor=actor)
        built = {d["district_id"] for d in batch_doc["districts"]}
        did_by_id = {r["request_id"]: r["district_id"] for r in rows}
        flip_ids = [i for i in plan["swept_ids"] if did_by_id[i] in built]
        _flip(s, flip_ids, batch_id)
        return {"batch_id": batch_id, "n_requests": len(flip_ids),
                "n_districts": len(batch_doc["districts"]), "targets": plan["targets"],
                "spilled": plan["spilled"], "blocked": plan["blocked"], "skipped": skipped,
                "benchmark_excluded": bm_excluded,
                "_batch_districts": [{"district_id": d["district_id"], "name": d.get("name", ""),
                                      "state": d.get("state", "")} for d in batch_doc["districts"]]}

    if session is not None:
        out = _work(session)                      # DB-only; a rolling-back test session leaks nothing
        out.pop("_batch_districts", None)
        return out

    gdb.init_precious_schema()                    # ensure executed_ref/executed_at columns exist
    with gdb.session_scope() as s:
        out = _work(s)
    batch_districts = out.pop("_batch_districts", None)
    if out["batch_id"] and batch_districts:
        # Post-commit, best-effort (file-last, like dispatch_handoff): the receipt is regenerable
        # FROM the committed rows; the registry backup is regenerable from the DB.
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
            print(f"[warn] follow-up receipt/registry refresh failed ({type(e).__name__}: {e}); "
                  f"the DB is authoritative — regenerate later")
    return out


def _empty_result() -> dict:
    return {"batch_id": None, "n_requests": 0, "n_districts": 0, "targets": {},
            "spilled": [], "blocked": [], "skipped": [], "benchmark_excluded": []}


# ===========================================================================
# 7->6 — DIRECT alternate-representation re-dispatch (existing reps; bypasses Stage 1)
# ===========================================================================
def pick_alternate(alternate_reps: list) -> dict | None:
    """Choose which already-captured alternate rep to re-dispatch — prefer an IMAGE rep (the common
    text→vision escalation the detector flags), else the first TEXT alternate. None if none is
    dispatchable. Defensive kind filter (#140): a binary rep (kind 'pdf'/'bin') must never be chosen —
    it would route to the text council and be read as raw bytes (paid mojibake)."""
    if not alternate_reps:
        return None
    imgs = [a for a in alternate_reps if CONTENT.is_image_kind(a.get("kind"))]
    if imgs:
        return imgs[0]
    texts = [a for a in alternate_reps if a.get("kind") == "text"]
    return texts[0] if texts else None


def build_alternate_input(meta: dict, rec: dict, alt: dict, *, council_id: str = None) -> tuple:
    """Synthesize the ONE-record dispatch input (+ council override) that re-dispatches the NAMED
    alternate rep instead of the release winner — the 7->6 bridge. `overrides` picks the council
    ({rec_key::file: council_id}); an image alt with no explicit council defaults to the 'image'
    council (the text→vision escalation). Returns (districts_input, overrides) for assemble_package.
    Size fields are joined from the record's representation rows (cost inputs; the flat bootstrap model
    ignores them, but the measured model will not)."""
    reps_by_file = {r.get("filename"): r for r in (rec.get("reps") or [])}
    rr = reps_by_file.get(alt["file"], {})
    send_entry = {"file": alt["file"], "kind": alt.get("kind"),
                  "n_chars": rr.get("n_chars"), "n_times": rr.get("n_times"),
                  "n_schools": len(rec.get("intended_schools") or []) or None}
    record = {"rec_key": rec["rec_key"], "url": rec.get("url"), "decision": "send",
              "reason": "7->6 alternate-rep re-dispatch (REQ-118)",
              "signals": rec.get("signals") or {}, "send": [send_entry]}
    cid = council_id or ("image" if CONTENT.is_image_kind(alt.get("kind")) else None)
    overrides = {f"{rec['rec_key']}::{alt['file']}": cid} if cid else {}
    return [(meta, [record])], overrides


def _load_request(session, request_id: int) -> dict | None:
    row = session.execute(text(
        "SELECT request_id, district_id, route, band, target, params_json, status "
        "FROM extraction_request WHERE request_id = :id"), {"id": request_id}).mappings().first()
    return dict(row) if row else None


def _executed_count(session, district_id: str, band) -> int:
    return session.execute(text(
        "SELECT COUNT(*) FROM extraction_request WHERE status = 'executed' "
        "AND district_id = :d AND band IS NOT DISTINCT FROM :b"),
        {"d": district_id, "b": band}).scalar() or 0


def execute_alternate_dispatch(request_id: int, *, actor: str = "ian", council_id: str = None,
                               root=None, session=None) -> dict:
    """Fire an APPROVED 7->6 directive: build a NEW immutable Stage-6 dispatch of the named alternate
    rep (no new capture — it bypasses Stage 1), so it re-enters Stage 7 via the normal extract path.
    The prior dispatch is untouched (history preserved). Depth-guarded by the REQ-051 governor's
    max_request_rounds (per district×band) so the loop terminates; the PAID re-extraction is separately
    budget-gated when the new handoff is run (run_council_streaming, REQ-051). Flips the directive to
    'executed' with the new handoff_hash as its `executed_ref`. `session` follows the inject-or-own
    idiom. Returns {ok, handoff_hash?, path?, reason?}."""
    def _run(s) -> dict:
        req = _load_request(s, request_id)
        if not req:
            return {"ok": False, "reason": f"no such request {request_id}"}
        if req["route"] != RQ.ROUTE_ALT_REP:
            return {"ok": False, "reason": f"request {request_id} is {req['route']}, not a 7->6 re-dispatch"}
        if req["status"] != "approved":
            return {"ok": False, "reason": f"request {request_id} is {req['status']}, not approved"}
        if _benchmark_district_ids(s, [req["district_id"]]):
            # The wall (#134): benchmark (batch_00000) districts never execute — measurement only.
            return {"ok": False, "reason": f"district {req['district_id']} is a benchmark district "
                                           f"(batch_00000) — walled off from request execution"}

        b = BUD.load_budget()
        used = _executed_count(s, req["district_id"], req["band"])
        if b.max_request_rounds is not None and used >= b.max_request_rounds:
            return {"ok": False, "blocked": True,
                    "reason": f"depth guard: {used} round(s) already executed for "
                              f"{req['district_id']}/{req['band']} (max {b.max_request_rounds})"}

        did, rec_key = req["district_id"], req["target"]
        meta = REL.load_district(s, did)
        if not meta:
            return {"ok": False, "reason": f"district {did} not in the release store"}
        rec = next((r for r in REL.load_district_records(s, did) if r["rec_key"] == rec_key), None)
        if not rec:
            return {"ok": False, "reason": f"record {rec_key} not found for {did}"}
        params = json.loads(req["params_json"] or "{}")
        alt = pick_alternate(params.get("alternate_reps") or [])
        if not alt:
            return {"ok": False, "reason": f"request {request_id} names no dispatchable alternate rep "
                                           f"(text/image) to re-dispatch"}

        councils = C6.load_configs()
        cost_model = COST6.load_cost_model()
        districts_input, overrides = build_alternate_input(meta, rec, alt, council_id=council_id)
        package = PKG6.assemble_package(districts_input, councils, cost_model, overrides)
        if not package["cost"]["n_reps"]:
            return {"ok": False, "reason": "the alternate rep produced an empty dispatch package"}
        package["verified_only"] = False
        fps = {did: REL.district_fingerprints(s, did)}
        doc = HND.freeze(package, councils, fps, created_by=actor)
        path = (Path(root) if root else HND.DEFAULT_ROOT) / HND.handoff_filename(doc)
        # Commit-order (#143, mirrors dispatch_handoff): every DB statement FIRST (index row +
        # state_events + the directive flip), the immutable file LAST — a DB failure rolls back
        # cleanly with no orphaned file, and a file failure rolls the DB back with it. The
        # district_status backup refresh is NOT here — it's best-effort and must never share this
        # transaction (see below).
        H6.record_dispatch(s, doc, path, actor=actor, metas={did: meta})
        _flip(s, [request_id], doc["handoff_hash"])
        HND.write(doc, root=root)
        return {"ok": True, "handoff_hash": doc["handoff_hash"], "path": str(path),
                "alt_file": alt["file"], "council": overrides or "auto-routed"}

    if session is not None:
        return _run(session)      # injected: DB-only; no receipt/registry side effects escape a rollback
    gdb.init_precious_schema()
    with gdb.session_scope() as s:
        out = _run(s)
    if out.get("ok"):
        # Best-effort backup refresh AFTER the dispatch commits, on a SEPARATE session (the altitude
        # lesson, #143/#139): export_status reads the `current_state` view, so ANY failure there
        # (e.g. a fresh DB without the view) would poison the load-bearing transaction and roll back
        # the committed dispatch. Post-commit + separate session makes that impossible.
        try:
            with gdb.session_scope() as s2:
                DS.export_status(s2)
        except Exception as e:  # noqa: BLE001 — the DB is authoritative; the backup regenerates
            print(f"[warn] district_status.json refresh failed after 7->6 dispatch "
                  f"({type(e).__name__}: {e}); the DB is authoritative — regenerate later")
    return out


# ---------------------------------------------------------------------------
# CLI — CLI-first per the ramp-up model; the console buttons wrap the same functions
# ---------------------------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Stage 7 request-more-evidence execution (REQ-118)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compose-followup", help="sweep approved 7->2/7->3/7->1 into a draft follow-up batch")
    c.add_argument("--handoff", help="scope to one handoff_hash (else all approved NEW-work)")
    c.add_argument("--year", default="2024_25")
    c.add_argument("--actor", default="cli")
    c.add_argument("--cap", type=int, default=12)
    e = sub.add_parser("execute", help="fire an approved 7->6 alternate-rep re-dispatch")
    e.add_argument("request_id", type=int)
    e.add_argument("--council", help="council id override (default: image council for an image alt)")
    e.add_argument("--actor", default="cli")
    a = ap.parse_args()

    if a.cmd == "compose-followup":
        out = compose_followup_batch(year=a.year, actor=a.actor, handoff_hash=a.handoff, cap=a.cap)
        if not out["batch_id"]:
            print("No approved NEW-work directives to compose.")
        else:
            print(f"Draft follow-up {out['batch_id']}: {out['n_districts']} district(s), "
                  f"{out['n_requests']} directive(s) executed. Review at gate@1.")
        for sp in out.get("spilled", []):
            print(f"  spilled: {sp['district_id']} ({sp['reason']})")
        for bl in out.get("blocked", []):
            print(f"  blocked (depth guard): req {bl['request_id']} {bl['district_id']}/{bl['band']}")
        for sk in out.get("skipped", []):
            print(f"  skipped: {sk['district_id']} ({sk['reason']})")
        for bm in out.get("benchmark_excluded", []):
            print(f"  benchmark-excluded: req {bm['request_id']} {bm['district_id']} ({bm['reason']})")
    elif a.cmd == "execute":
        out = execute_alternate_dispatch(a.request_id, actor=a.actor, council_id=a.council)
        if out["ok"]:
            print(f"Re-dispatched {out['alt_file']} → new handoff {out['handoff_hash']}. "
                  f"Run Stage 7 on it to extract (budget-gated).")
        else:
            print(f"Refused: {out['reason']}")


if __name__ == "__main__":
    main()
