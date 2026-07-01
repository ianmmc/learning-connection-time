#!/usr/bin/env python3
"""Stage 5 review app — local FastAPI server (single-user, localhost only).

Serves the 3-column review UI, the SQLite-backed record/label API, and the captured local
files (text/image/pdf) for inspection. NO AI anywhere — this is the human-labeling harness
around the deterministic signals computed by build_signals.py.

Run:  uvicorn server:app --reload --port 8005   (from this directory)
  or  python3 server.py
"""
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

HERE = Path(__file__).resolve().parent
from infrastructure.acquisition.stage5_filter import build_signals as BS    # noqa: E402  (export_labels lives here, shared with ingest)
from infrastructure.acquisition.stage5_filter import release as REL         # noqa: E402  (filtered.json projection — REQ-094)
from infrastructure.acquisition.common import db as gdb                     # noqa: E402  (isolated governance Postgres — REQ-103)
from infrastructure.acquisition.common import district_status as DS         # noqa: E402  (state_event log — gate@1 audit events)
from infrastructure.acquisition.common import school_sampling as SS         # noqa: E402  (add-school candidate lookup)
from infrastructure.acquisition.stage1_queue import queue_batch as Q1       # noqa: E402  (build/persist a batch — REQ-102)
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE   # noqa: E402  (the batch working store)
from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict, BatchSchool  # noqa: E402
from infrastructure.acquisition.stage2_discover import headless as H2       # noqa: E402  (Stage 2 headless runner — REQ-104)
from infrastructure.acquisition.stage3_capture import headless as H3       # noqa: E402  (Stage 3 capture runner + DB-cache status)
from infrastructure.acquisition.stage4_process import headless as H4       # noqa: E402  (Stage 4 process runner + DB-cache status)
from infrastructure.acquisition.process_governance import stage6_dispatch as H6  # noqa: E402  (Stage 6 routing/release bridge — REQ-101)
from infrastructure.acquisition.stage6_handoff import handoff as HND6       # noqa: E402  (immutable handoff filename helper)
from infrastructure.acquisition.common import paths                         # noqa: E402  (RAW_CAPTURES — rep inspect)
from infrastructure.acquisition.stage6_handoff import councils as C6        # noqa: E402  (council registry — gate@6 override options)
from infrastructure.acquisition.stage6_handoff.models import Handoff        # noqa: E402  (precious handoff index row)


def _refresh_filtered(con, district_id: str) -> None:
    """Event-driven: a label/split change updates this district's filtered.json projection (REQ-094).
    Best-effort — the precious label/split is already committed + JSON-backed, and filtered.json is a
    regenerable projection that also refreshes on the next ingest, so a hiccup here must never fail
    the write."""
    try:
        REL.generate(con, district_id=district_id)
    except Exception as e:
        print(f"[warn] filtered.json refresh for {district_id} failed ({type(e).__name__}: {e}); "
              f"it will regenerate on the next ingest")

# Runtime-state locations come from the single source of truth (paths.py, via build_signals).
# The DB is now the isolated governance Postgres (gdb.session_scope), not a SQLite file.
LABELS_JSON = BS.LABELS_JSON
CLUSTER_SPLITS_JSON = BS.CLUSTER_SPLITS_JSON
RAW_DIR = BS.RAW_DIR

app = FastAPI(title="Stage 5 Review")


@app.get("/api/tree")
def tree():
    """Districts -> records for the left column. Records carry tier + label status +
    cluster grouping (NOT the category hypothesis — that stays hidden until labeled)."""
    out = []
    with gdb.session_scope() as con:
        districts = con.execute(text("SELECT * FROM district ORDER BY name")).mappings().all()
        q = text("""SELECT r.rec_key, r.url, r.hash, r.kind, r.tier, r.sort_score, r.duplicate_of,
                      r.cluster_id, r.is_cluster_rep, r.cluster_size, r.is_emergent,
                      l.status, l.primary_label
               FROM record r LEFT JOIN label l ON l.rec_key=r.rec_key
               WHERE r.district_id=:did ORDER BY r.tier, r.sort_score DESC""")
        for d in districts:
            recs = [dict(r) for r in con.execute(q, {"did": d["district_id"]}).mappings()]
            t = con.execute(text("SELECT nces_by_level_json FROM district_target WHERE district_id=:did"),
                            {"did": d["district_id"]}).mappings().first()
            out.append({"district_id": d["district_id"], "name": d["name"], "state": d["state"],
                        "batch_id": d["batch_id"], "guessed_topology": d["guessed_topology"],
                        "labeled_topology": d["labeled_topology"], "nces_school_count": d["nces_school_count"],
                        "nces_by_level": json.loads(t["nces_by_level_json"]) if t else None,
                        "records": recs})
    return out


@app.get("/api/record/{rec_key}")
def record(rec_key: str):
    with gdb.session_scope() as con:
        r = con.execute(text("SELECT * FROM record WHERE rec_key=:rk"), {"rk": rec_key}).mappings().first()
        if not r:
            raise HTTPException(404, "no such record")
        reps = [dict(x) for x in con.execute(text(
            "SELECT source, filename, file_kind, n_chars, n_times, usable FROM representation WHERE rec_key=:rk"),
            {"rk": rec_key}).mappings()]
        lab_row = con.execute(text("SELECT * FROM label WHERE rec_key=:rk"), {"rk": rec_key}).mappings().first()
        label = dict(lab_row) if lab_row else {}
        # cluster members (siblings) so the panel can show the cascade + per-member split control
        members = []
        if r["cluster_id"]:
            for m in con.execute(text(
                    """SELECT r.rec_key, r.url, r.is_cluster_rep, l.status FROM record r
                       LEFT JOIN label l ON l.rec_key=r.rec_key
                       WHERE r.cluster_id=:cid ORDER BY r.is_cluster_rep DESC, r.tier, r.sort_score DESC"""),
                    {"cid": r["cluster_id"]}).mappings():
                members.append(dict(m))
        signals = json.loads(r["signals_json"])
        # category_hypothesis is returned but the FRONTEND keeps it hidden until labeled, to avoid
        # anchoring the human's judgment (methodological choice — see the design note).
        return {
            "rec_key": rec_key, "url": r["url"], "hash": r["hash"], "kind": r["kind"],
            "final_url": r["final_url"], "district_dir": r["district_dir"], "tier": r["tier"],
            "category_hypothesis": r["category_hypothesis"], "duplicate_of": r["duplicate_of"],
            "content_hash": r["content_hash"], "signals": signals, "representations": reps,
            "label": label, "cluster_id": r["cluster_id"], "is_cluster_rep": r["is_cluster_rep"],
            "cluster_size": r["cluster_size"], "cluster_members": members,
            "intended_schools": json.loads(r["intended_schools_json"] or "[]"),
            "candidate_tools": json.loads(r["candidate_tools_json"] or "[]"),
            "is_emergent": r["is_emergent"],
        }


UPSERT_LABEL = text(
    """INSERT INTO label (rec_key, primary_label, flags_json, note, status, updated_at)
       VALUES (:rec_key, :primary_label, :flags_json, :note, :status, :updated_at)
       ON CONFLICT (rec_key) DO UPDATE SET
         primary_label=excluded.primary_label, flags_json=excluded.flags_json,
         note=excluded.note, status=excluded.status, updated_at=excluded.updated_at""")


@app.post("/api/label/{rec_key}")
async def save_label(rec_key: str, payload: dict):
    with gdb.session_scope() as con:
        rec = con.execute(text("SELECT district_id, cluster_id, is_cluster_rep FROM record WHERE rec_key=:rk"),
                          {"rk": rec_key}).mappings().first()
        if not rec:
            raise HTTPException(404, "no such record")
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        vals = {"primary_label": payload.get("primary_label"),
                "flags_json": json.dumps(payload.get("flags", [])), "note": payload.get("note", ""),
                "status": payload.get("status", "labeled"), "updated_at": ts}
        con.execute(UPSERT_LABEL, {"rec_key": rec_key, **vals})
        # Cluster cascade: labeling the REPRESENTATIVE applies the same label to its (unsplit)
        # members, so a near-dup cluster is labeled once. Split members already have cluster_id
        # cleared, so they're naturally excluded.
        cascaded = 0
        if rec["cluster_id"] and rec["is_cluster_rep"]:
            for (m,) in con.execute(text("SELECT rec_key FROM record WHERE cluster_id=:cid AND rec_key!=:rk"),
                                    {"cid": rec["cluster_id"], "rk": rec_key}).fetchall():
                con.execute(UPSERT_LABEL, {"rec_key": m, **vals})
                cascaded += 1
        BS.recompute_labeled_topology(con, rec["district_id"])
        BS.recompute_attention(con, rec["district_id"])   # label/split changed canonical/resolved state -> refresh attention
        con.commit()   # persist before exporting, so the JSON backup only reflects committed state
        # Export-on-save: the precious label is backed up to the tracked JSON before we return,
        # so it survives DB loss with zero action from the user (no reliance on remembering).
        BS.export_labels(con, LABELS_JSON)
        _refresh_filtered(con, rec["district_id"])   # label event -> refresh filtered.json
    return {"ok": True, "cascaded": cascaded}


@app.post("/api/split/{rec_key}")
async def split_record(rec_key: str):
    """Pull one record OUT of its auto-cluster (it turned out to be genuinely unique). Cheap,
    DB-only: detach the record, re-fix the remaining cluster (new rep / collapse to singleton),
    and record a DURABLE split so re-ingest keeps it out. NOT a re-cluster (no re-shingling)."""
    with gdb.session_scope() as con:
        rec = con.execute(text("SELECT district_id, cluster_id FROM record WHERE rec_key=:rk"),
                          {"rk": rec_key}).mappings().first()
        if not rec:
            raise HTTPException(404, "no such record")
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Precious, durable override first (survives re-ingest + DB wipe via the JSON backup).
        con.execute(text("INSERT INTO cluster_split (rec_key, created_at) VALUES (:rk,:ts) "
                         "ON CONFLICT (rec_key) DO NOTHING"), {"rk": rec_key, "ts": ts})
        cid = rec["cluster_id"]
        if cid:
            con.execute(text("UPDATE record SET cluster_id=NULL, is_cluster_rep=1, cluster_size=1 WHERE rec_key=:rk"),
                        {"rk": rec_key})
            rest = [row[0] for row in con.execute(text(
                "SELECT rec_key FROM record WHERE cluster_id=:cid ORDER BY tier, sort_score DESC"),
                {"cid": cid}).fetchall()]
            if len(rest) <= 1:   # cluster collapses — remaining record (if any) becomes a singleton
                for rk in rest:
                    con.execute(text("UPDATE record SET cluster_id=NULL, is_cluster_rep=1, cluster_size=1 WHERE rec_key=:rk"),
                                {"rk": rk})
            else:                # promote a new representative; refresh sizes
                for i, rk in enumerate(rest):
                    con.execute(text("UPDATE record SET is_cluster_rep=:rep, cluster_size=:sz WHERE rec_key=:rk"),
                                {"rep": 1 if i == 0 else 0, "sz": len(rest), "rk": rk})
        BS.recompute_labeled_topology(con, rec["district_id"])
        BS.recompute_attention(con, rec["district_id"])   # label/split changed canonical/resolved state -> refresh attention
        con.commit()   # persist before exporting, so the JSON backup only reflects committed state
        BS.export_splits(con, CLUSTER_SPLITS_JSON)
        _refresh_filtered(con, rec["district_id"])   # split changes the canonical set -> refresh filtered.json
    return {"ok": True}


@app.get("/api/progress")
def progress():
    with gdb.session_scope() as con:
        total = con.execute(text("SELECT COUNT(*) FROM record")).scalar()
        done = con.execute(text("SELECT COUNT(*) FROM label WHERE status!='unlabeled'")).scalar()
    return {"total": total, "labeled": done}


# ---------------------------------------------------------------- Stage 5 faceted console (the rework)
# District-driven, attention-first left pane. Group by DISTRICT facets; filter by RECORD facets (the
# district stays visible) + a hide-resolved district toggle; sort by district fields (incl. continuous)
# asc/desc. Server-side on the stored attention/facet columns so it scales to ~5M reps. The batch is
# gone here — "first_seen_at" (the first gate@5 event) replaces it; the district is the canonical unit.
_GROUP_COLS = {"none": None, "pipeline_state": "d.pipeline_state", "state": "d.state",
               "topology": "COALESCE(d.labeled_topology, d.guessed_topology)"}
# "recent" = the latest activity of ANY kind: stage progression OR a label edit (the completion log is
# coarse, so label.updated_at carries the per-URL judgments the user wants reflected). GREATEST ignores NULLs.
_RECENT = "GREATEST(ev.last_event, lbl.last_label)"
_SORT_COLS = {"attention": "d.attention_score", "name": "d.name", "enrollment": "dt.enrollment_k12",
              "schools": "d.nces_school_count", "recent": _RECENT, "first_seen": "ev.first_seen"}


@app.get("/api/stage5/districts")
def stage5_districts(
    group_by: str = "none", sort: str = "attention", dir: str = "desc",
    label: str | None = None,                          # 'labeled' | 'unlabeled' record filter
    tier: list[str] = Query(default=[]),               # record tier filter (repeatable)
    reason: list[str] = Query(default=[]),             # attention-reason record filter (repeatable)
    hide_resolved: bool = False,                       # district toggle: drop pipeline_state='complete'
    limit: int = 500, offset: int = 0,
):
    """The faceted district list + each district's (filtered) records. Sort/filter/paginate run in SQL
    on the stored attention/facet columns; grouping is applied over the returned page."""
    gcol = _GROUP_COLS.get(group_by, None)
    scol = _SORT_COLS.get(sort, "d.attention_score")
    order = "ASC" if dir == "asc" else "DESC"
    nulls = "NULLS LAST" if order == "DESC" else "NULLS FIRST"
    where, params = ["1=1"], {"lim": limit, "off": offset}
    if hide_resolved:
        where.append("(d.pipeline_state IS DISTINCT FROM 'complete')")
    with gdb.session_scope() as con:
        # 1) districts: stored columns + first/last event from the log, filtered + sorted + paginated.
        drows = con.execute(text(f"""
            SELECT d.district_id, d.name, d.state, d.attention_score, d.attention_reasons_json,
                   d.pipeline_state, d.n_unlabeled, d.n_flagged, d.n_records,
                   d.guessed_topology, d.labeled_topology, d.nces_school_count,
                   dt.enrollment_k12, ev.first_seen, {_RECENT} AS last_event
            FROM district d
            LEFT JOIN district_target dt ON dt.district_id = d.district_id
            LEFT JOIN (SELECT district_id, MIN(created_at) FILTER (WHERE stage=5) AS first_seen,
                              MAX(created_at) AS last_event FROM state_event GROUP BY district_id) ev
                   ON ev.district_id = d.district_id
            LEFT JOIN (SELECT r.district_id, MAX(l.updated_at) AS last_label FROM record r
                              JOIN label l ON l.rec_key=r.rec_key WHERE l.status!='unlabeled'
                              GROUP BY r.district_id) lbl ON lbl.district_id = d.district_id
            WHERE {' AND '.join(where)}
            ORDER BY {scol} {order} {nulls}, d.name ASC
            LIMIT :lim OFFSET :off"""), params).mappings().all()
        dids = [r["district_id"] for r in drows]

        # 2) records for the returned page, filtered by the record facets (district stays visible even
        #    if all its records are filtered out — the user's rule: filter URLs, not districts).
        rwhere, rparams = ["r.district_id = ANY(:ids)"], {"ids": dids or [""]}
        if label == "labeled":
            rwhere.append("l.status IS NOT NULL AND l.status != 'unlabeled'")
        elif label == "unlabeled":
            rwhere.append("(l.status IS NULL OR l.status = 'unlabeled')")
        if tier:
            rwhere.append("r.tier = ANY(:tiers)"); rparams["tiers"] = tier
        if reason:   # the DOMINANT reason (reasons[0]) is element 0 of the JSON array text
            rwhere.append("(r.attention_reasons_json::jsonb ->> 0) = ANY(:reasons)"); rparams["reasons"] = reason
        recs_by_did: dict = {}
        for r in con.execute(text(f"""
            SELECT r.rec_key, r.district_id, r.url, r.tier, r.attention_score, r.attention_reasons_json,
                   r.is_cluster_rep, r.cluster_id, r.cluster_size, r.is_emergent,
                   COALESCE(l.status,'unlabeled') AS label_status, l.primary_label
            FROM record r LEFT JOIN label l ON l.rec_key=r.rec_key
            WHERE {' AND '.join(rwhere)}
            ORDER BY r.attention_score DESC NULLS LAST, r.tier"""), rparams).mappings():
            recs_by_did.setdefault(r["district_id"], []).append({
                **{k: r[k] for k in ("rec_key", "url", "tier", "attention_score", "is_cluster_rep",
                                     "cluster_id", "cluster_size", "is_emergent", "label_status", "primary_label")},
                "attention_reasons": json.loads(r["attention_reasons_json"]) if r["attention_reasons_json"] else []})

        total = con.execute(text(f"SELECT COUNT(*) FROM district d WHERE {' AND '.join(where)}")).scalar()

    # 3) assemble districts, then group over the page (order preserved from the SQL sort).
    districts = []
    for r in drows:
        districts.append({
            "district_id": r["district_id"], "name": r["name"], "state": r["state"],
            "attention_score": r["attention_score"] or 0,
            "attention_reasons": json.loads(r["attention_reasons_json"]) if r["attention_reasons_json"] else [],
            "pipeline_state": r["pipeline_state"], "n_unlabeled": r["n_unlabeled"] or 0,
            "n_flagged": r["n_flagged"] or 0, "n_records": r["n_records"] or 0,
            "guessed_topology": r["guessed_topology"], "labeled_topology": r["labeled_topology"],
            "nces_school_count": r["nces_school_count"], "enrollment_k12": r["enrollment_k12"],
            "first_seen_at": r["first_seen"], "last_event_at": r["last_event"],
            "records": recs_by_did.get(r["district_id"], [])})

    def group_key(d):
        if group_by == "state":          return d["state"] or "—"
        if group_by == "pipeline_state": return d["pipeline_state"] or "untouched"
        if group_by == "topology":       return d["labeled_topology"] or d["guessed_topology"] or "unknown"
        return "all"
    groups: list = []
    seen: dict = {}
    for d in districts:
        k = group_key(d)
        if k not in seen:
            seen[k] = {"key": k, "n_districts": 0, "n_attention": 0, "districts": []}
            groups.append(seen[k])
        g = seen[k]
        g["districts"].append(d)
        g["n_districts"] += 1
        g["n_attention"] += 1 if (d["attention_score"] or 0) > 0 else 0
    return {"group_by": group_by, "sort": {"field": sort, "dir": order.lower()},
            "total_districts": total, "shown": len(districts), "groups": groups}


@app.get("/api/stage5/facets")
def stage5_facets():
    """The available group/filter options + their district/record counts — feeds the mini-dashboards
    and the filter menu so the UI never hardcodes the vocabulary."""
    with gdb.session_scope() as con:
        def counts(sql):
            return [{"value": r[0], "count": r[1]} for r in con.execute(text(sql)) if r[0] is not None]
        return {
            "group_by": list(_GROUP_COLS.keys()),
            "sort": list(_SORT_COLS.keys()),
            "pipeline_state": counts("SELECT pipeline_state, COUNT(*) FROM district GROUP BY pipeline_state ORDER BY 2 DESC"),
            "state": counts("SELECT state, COUNT(*) FROM district GROUP BY state ORDER BY 1"),
            "topology": counts("SELECT COALESCE(labeled_topology,guessed_topology), COUNT(*) FROM district GROUP BY 1 ORDER BY 2 DESC"),
            "tier": counts("SELECT tier, COUNT(*) FROM record GROUP BY tier ORDER BY 1"),
            "reason": counts("SELECT attention_reasons_json::jsonb->>0, COUNT(*) FROM record GROUP BY 1 ORDER BY 2 DESC"),
        }


# ---- follow-up flags (the top attention tier — a directive on a district or a record) ----
def _backup_followups(con) -> int:
    """Back the precious follow-up flags to a tracked JSON (the labels.json pattern), so a human
    directive survives a DB wipe. Atomic write."""
    rows = con.execute(text("SELECT scope, target_id, district_id, directive, actor, created_at, resolved_at "
                            "FROM followup_flag ORDER BY id")).mappings().all()
    data = [dict(r) for r in rows]
    out = BS.LABELS_JSON.parent / "followup_flags.json"
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(out)
    return len(data)


@app.get("/api/followup")
def followup_list(district_id: str | None = None, include_resolved: bool = False):
    where = ["1=1"]
    params: dict = {}
    if district_id:
        where.append("district_id=:did"); params["did"] = district_id
    if not include_resolved:
        where.append("resolved_at IS NULL")
    with gdb.session_scope() as con:
        rows = con.execute(text(f"SELECT id, scope, target_id, district_id, directive, actor, created_at, "
                                f"resolved_at FROM followup_flag WHERE {' AND '.join(where)} ORDER BY id DESC"),
                           params).mappings().all()
    return [dict(r) for r in rows]


@app.post("/api/followup")
async def followup_create(payload: dict):
    """Flag a district or a record for follow-up with a directive (the top attention tier). Records a
    gate@5 state_event and refreshes the affected district's attention."""
    scope = payload.get("scope")
    target_id = payload.get("target_id")
    if scope not in ("district", "record") or not target_id:
        raise HTTPException(400, "scope must be 'district'|'record' and target_id is required")
    actor = payload.get("actor", "ian")
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with gdb.session_scope() as con:
        did = target_id if scope == "district" else con.execute(
            text("SELECT district_id FROM record WHERE rec_key=:rk"), {"rk": target_id}).scalar()
        if not did:
            raise HTTPException(404, f"no such {scope} {target_id}")
        con.execute(text("""INSERT INTO followup_flag (scope, target_id, district_id, directive, actor, created_at)
                            VALUES (:s,:t,:d,:dir,:a,:ts)"""),
                    {"s": scope, "t": target_id, "d": did, "dir": payload.get("directive", ""), "a": actor, "ts": ts})
        BS.recompute_attention(con, did)
        con.commit()
        _backup_followups(con)
    # No state_event: the governance log is completion-only (§11c). The flag IS its own audit row
    # (followup_flag, timestamped) and feeds the "recent change" sort alongside label.updated_at.
    return {"ok": True, "district_id": did}


@app.post("/api/followup/{flag_id}/resolve")
async def followup_resolve(flag_id: int, payload: dict):
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with gdb.session_scope() as con:
        did = con.execute(text("SELECT district_id FROM followup_flag WHERE id=:i"), {"i": flag_id}).scalar()
        if not did:
            raise HTTPException(404, f"no such flag {flag_id}")
        con.execute(text("UPDATE followup_flag SET resolved_at=:ts WHERE id=:i"), {"ts": ts, "i": flag_id})
        BS.recompute_attention(con, did)
        con.commit()
        _backup_followups(con)
    return {"ok": True, "district_id": did}


# ---- saved views (named left-pane presets; persistent UI convenience) ----
@app.get("/api/views")
def views_list(actor: str = "ian"):
    with gdb.session_scope() as con:
        rows = con.execute(text("SELECT id, name, config_json, created_at FROM saved_view "
                                "WHERE actor=:a ORDER BY name"), {"a": actor}).mappings().all()
    return [{"id": r["id"], "name": r["name"], "config": json.loads(r["config_json"] or "{}"),
             "created_at": r["created_at"]} for r in rows]


@app.post("/api/views")
async def views_save(payload: dict):
    """Create or overwrite (by name+actor) a named left-pane preset."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    actor = payload.get("actor", "ian")
    cfg = json.dumps(payload.get("config", {}))
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with gdb.session_scope() as con:
        existing = con.execute(text("SELECT id FROM saved_view WHERE actor=:a AND name=:n"),
                               {"a": actor, "n": name}).scalar()
        if existing:
            con.execute(text("UPDATE saved_view SET config_json=:c WHERE id=:i"), {"c": cfg, "i": existing})
            vid = existing
        else:
            vid = con.execute(text("INSERT INTO saved_view (actor, name, config_json, created_at) "
                                   "VALUES (:a,:n,:c,:ts) RETURNING id"),
                              {"a": actor, "n": name, "c": cfg, "ts": ts}).scalar()
    return {"ok": True, "id": vid}


@app.delete("/api/views/{view_id}")
async def views_delete(view_id: int):
    with gdb.session_scope() as con:
        con.execute(text("DELETE FROM saved_view WHERE id=:i"), {"i": view_id})
    return {"ok": True}


@app.get("/files/{district_dir}/{rec_hash}/{filename}")
def serve_file(district_dir: str, rec_hash: str, filename: str):
    """Serve a captured file for inspection. Path-restricted to within a record's capture dir."""
    base = (RAW_DIR / district_dir / "captures" / rec_hash).resolve()
    target = (base / filename).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(target)


# ---------------------------------------------------------------- gate@1 (Stage 1 Queue) console — REQ-102
# The governance DB is the working store for a batch; batch_NNNNN.json is the receipt regenerated from
# the rows. Edits are SOFT (included flags / row inserts) so the full proposed batch stays auditable.
# Batch-level lifecycle (draft -> approved) lives on the `batch` row; per-district gate@1 events are the
# auditable timeline.

@app.on_event("startup")
def _ensure_batch_tables():
    """Create the PRECIOUS batch tables if absent (idempotent). Best-effort so the app still boots when
    Docker is down — DB calls then fail with the same clear error the Stage-5 path already gives."""
    try:
        gdb.init_precious_schema()
    except Exception as e:
        print(f"[warn] could not init batch schema at startup ({type(e).__name__}: {e}); "
              f"start Docker (lct_postgres) — queue endpoints will error until then")


def _record_gate1(district_rows, *, event_type: str, actor: str, note: str = "") -> None:
    """Record a per-district gate@1 event (approved/edited/reopened) — the auditable timeline that
    complements the batch-row lifecycle. `district_rows`: iterable of (district_id, name, state).
    A pure checkpoint event (no `stage`), so it never moves furthest_stage."""
    registry = DS.load()
    for did, name, state in district_rows:
        DS.record_stage(registry, did, name, state, stage_name="queue",
                        checkpoint="gate@1", event_type=event_type, actor=actor, notes=note)
    DS.save(registry)


@app.get("/api/queue")
def queue_list():
    with gdb.session_scope() as con:
        return BSTORE.list_batches(con)


@app.post("/api/queue/create")
async def queue_create(payload: dict):
    """Stratified auto-draw a new batch (synchronous — build_batch reads the full NCES corpus + DB, so
    this blocks ~10-20s; the UI shows a progress affordance). Writes the working store + receipt +
    stage=1 'queued' events, then returns the review payload."""
    year = payload.get("nces_year", "2024_25")
    n = int(payload.get("n", 12))
    batch_type = payload.get("batch_type", "first-run")
    actor = payload.get("actor", "ian")
    with gdb.session_scope() as con:
        batch_id = f"batch_{BSTORE.next_batch_number(con):05d}"
    registry = DS.load()
    batch_doc, _gap, _n_elig = Q1.build_batch(year, n, batch_id, registry)
    Q1.persist_batch(batch_doc, registry, batch_type=batch_type, actor=actor)
    with gdb.session_scope() as con:
        return BSTORE.to_view(con, batch_id)


@app.get("/api/queue/{batch_id}")
def queue_get(batch_id: str):
    with gdb.session_scope() as con:
        try:
            return BSTORE.to_view(con, batch_id)
        except KeyError:
            raise HTTPException(404, f"no such batch {batch_id}")


@app.post("/api/queue/{batch_id}/edit")
async def queue_edit(batch_id: str, payload: dict):
    """gate@1 soft edit: reject_district | reject_school | add_school. Mutates the working store,
    regenerates the receipt, and records a per-district gate@1 'edited' audit event."""
    op = payload.get("op")
    actor = payload.get("actor", "ian")
    did = payload.get("district_id")
    try:
        with gdb.session_scope() as con:
            if op == "reject_district":
                BSTORE.reject_district(con, batch_id, did)
                note = f"reject district {did}"
            elif op == "reject_school":
                sid = payload["school_id"]
                BSTORE.reject_school(con, batch_id, did, sid)
                note = f"reject school {sid} ({did})"
            elif op == "restore_district":
                BSTORE.restore_district(con, batch_id, did)
                note = f"restore district {did}"
            elif op == "restore_school":
                sid = payload["school_id"]
                BSTORE.restore_school(con, batch_id, did, sid)
                note = f"restore school {sid} ({did})"
            elif op == "add_school":
                BSTORE.add_school(con, batch_id, did, payload["school"], payload["bands"])
                note = f"add school {payload['school']['school_id']} -> {payload['bands']} ({did})"
            else:
                raise HTTPException(400, f"unknown edit op {op!r}")
            drow = con.get(BatchDistrict, (batch_id, did))
            dname, dstate = (drow.name, drow.state) if drow else (did, "")
            BSTORE.write_receipt(con, batch_id)
    except BSTORE.BatchLocked as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    _record_gate1([(did, dname, dstate)], event_type="edited", actor=actor, note=note)
    with gdb.session_scope() as con:
        return BSTORE.to_view(con, batch_id)


@app.post("/api/queue/{batch_id}/approve")
async def queue_approve(batch_id: str, payload: dict):
    """gate@1 approval — the batch-level transition + a gate@1 'approved' event per included district."""
    actor = payload.get("actor", "ian")
    try:
        with gdb.session_scope() as con:
            BSTORE.approve_batch(con, batch_id, actor)
            included = [(d.district_id, d.name, d.state) for d in con.scalars(
                select(BatchDistrict).where(BatchDistrict.batch_id == batch_id,
                                            BatchDistrict.included.is_(True)))]
    except BSTORE.BatchLocked as e:
        raise HTTPException(409, str(e))
    except KeyError:
        raise HTTPException(404, f"no such batch {batch_id}")
    _record_gate1(included, event_type="approved", actor=actor, note=f"gate@1 approved {batch_id}")
    with gdb.session_scope() as con:
        return BSTORE.to_view(con, batch_id)


@app.post("/api/queue/{batch_id}/reopen")
async def queue_reopen(batch_id: str, payload: dict):
    actor = payload.get("actor", "ian")
    with gdb.session_scope() as con:
        try:
            BSTORE.reopen_batch(con, batch_id, actor)
        except KeyError:
            raise HTTPException(404, f"no such batch {batch_id}")
        view = BSTORE.to_view(con, batch_id)
    _record_gate1([(d["district_id"], d["name"], d["state"]) for d in view["districts"] if d["included"]],
                  event_type="reopened", actor=actor, note=f"gate@1 reopened {batch_id}")
    return view


@app.get("/api/queue/{batch_id}/district/{district_id}/candidates")
def queue_candidates(batch_id: str, district_id: str):
    """The district's remaining eligible NCES schools (per band) not already selected — the pick-list
    for 'add school'. Reads the full NCES index for the batch's year (heavy; a rare action)."""
    with gdb.session_scope() as con:
        b = con.get(Batch, batch_id)
        if b is None:
            raise HTTPException(404, f"no such batch {batch_id}")
        year = b.nces_year
        selected = {s.school_id for s in con.scalars(select(BatchSchool).where(
            BatchSchool.batch_id == batch_id, BatchSchool.district_id == district_id,
            BatchSchool.included.is_(True)))}
    idx = SS.school_index(year).get(district_id, {})   # {band: [school dicts]}
    out = {b: avail for b, cands in idx.items()
           if (avail := [c for c in cands if c["school_id"] not in selected])}
    return {"batch_id": batch_id, "district_id": district_id, "candidates_by_band": out}


# ---------------------------------------------------------------- Stage 2 (Discover) console — REQ-104
# Stage 2 is UNGATED, so the console surfaces it as STATUS/observability + an orchestration trigger
# (headless `claude -p` Wave 1, subscription-billed). The run is a background job; its status is the
# state_event log + the on-disk discovery.json (the filesystem is authoritative), projected here.
# In-process job board (single-user localhost): batch_id -> live run state. Ephemeral by design —
# the DURABLE record is the state_event log + discovery.json; this is just the live progress feed.
_DISCOVER_JOBS: dict = {}


def _job_view(batch_id: str) -> dict | None:
    j = _DISCOVER_JOBS.get(batch_id)
    if not j:
        return None
    return {"state": j["state"], "started_at": j["started_at"], "finished_at": j.get("finished_at"),
            "actor": j["actor"], "events": j["events"][-50:], "summary": j.get("summary"),
            "error": j.get("error")}


@app.get("/api/discover/{batch_id}")
def discover_status(batch_id: str):
    """Read-only Stage 2 status for a batch: lifecycle (must be gate@1-approved to run) + per-district
    discovery outcome read straight from disk + the live job feed (if a run is in flight)."""
    try:
        batch = H2.load_batch_any(batch_id)
    except SystemExit as e:
        raise HTTPException(404, str(e))
    with gdb.session_scope() as con:
        try:
            batch_status = BSTORE.to_view(con, batch_id)["status"]
        except KeyError:
            batch_status = None
    districts = H2.status_for_batch(batch)
    return {"batch_id": batch_id, "batch_status": batch_status, "districts": districts,
            "rollup": H2.rollup(districts), "job": _job_view(batch_id)}


@app.post("/api/discover/{batch_id}/run")
async def discover_run(batch_id: str, payload: dict):
    """Trigger headless Stage 2 discovery for an approved batch as a BACKGROUND job (12 × `claude -p`
    WebSearch agents at cap-2 concurrency can't block a request). Guards: batch must be gate@1-approved,
    and no run already in flight. Live progress streams into _DISCOVER_JOBS; durable truth is the
    state_event log + discovery.json that run_batch writes."""
    actor = payload.get("actor", "ian")
    with gdb.session_scope() as con:
        try:
            view = BSTORE.to_view(con, batch_id)
        except KeyError:
            raise HTTPException(404, f"no such batch {batch_id}")
    if view["status"] != "approved":
        raise HTTPException(409, f"batch {batch_id} is '{view['status']}' — gate@1 approval is required "
                                 f"before discovery")
    existing = _DISCOVER_JOBS.get(batch_id)
    if existing and existing["state"] == "running":
        raise HTTPException(409, f"discovery already running for {batch_id}")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {"state": "running", "started_at": now, "actor": actor, "events": [],
           "summary": None, "error": None, "finished_at": None}
    _DISCOVER_JOBS[batch_id] = job

    def _on_event(kind, p):
        job["events"].append({"kind": kind, **p})

    def _work():
        try:
            job["summary"] = H2.run_batch(batch_id, actor=actor, on_event=_on_event)
            job["state"] = "done"
        except SystemExit as e:   # reconcile CONTROL FAILURE / billing-auth halt — surface, don't hide
            job["state"], job["error"] = "halted", f"CONTROL FAILURE: {e}"
        except Exception as e:
            job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
        finally:
            job["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    import threading
    threading.Thread(target=_work, name=f"discover-{batch_id}", daemon=True).start()
    return {"started": True, "batch_id": batch_id}


# ---------------------------------------------------------------- Stage 3 (Capture) console — REQ-110
# Stage 3 is UNGATED -> status/observability (a health/emergent readout read FROM THE DB cross-stage
# cache, the working store the Stage-3 finish hook keeps fresh) + an orchestration trigger (per-district
# Node Playwright capture, a background job). Durable truth = captures.json on disk + the state_event log.
_CAPTURE_JOBS: dict = {}


def _capture_job_view(batch_id: str) -> dict | None:
    j = _CAPTURE_JOBS.get(batch_id)
    if not j:
        return None
    return {"state": j["state"], "started_at": j["started_at"], "finished_at": j.get("finished_at"),
            "actor": j["actor"], "events": j["events"][-50:], "summary": j.get("summary"),
            "error": j.get("error")}


def _batch_from_db(batch_id: str) -> dict | None:
    """Resolve the batch's INCLUDED districts straight from the governance DB working store (not the
    on-disk receipt) — the DB is the source of truth for the batch (§7a-A / §11h). Shared by every
    ungated stage view (capture, process). None if no such batch."""
    with gdb.session_scope() as con:
        try:
            view = BSTORE.to_view(con, batch_id)
        except KeyError:
            return None
    districts = [d for d in view["districts"] if d.get("included", True)]
    return {"batch_id": batch_id, "batch_status": view["status"], "districts": districts}


@app.get("/api/capture/{batch_id}")
def capture_status(batch_id: str):
    """Read-only Stage 3 status for a batch: per-district capture outcome + the CMS/host distribution,
    read from the DB cross-stage cache, plus the live job feed (if a run is in flight)."""
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    st = H3.status_for_batch(batch)
    return {"batch_id": batch_id, "batch_status": batch["batch_status"], **st,
            "job": _capture_job_view(batch_id)}


@app.post("/api/capture/{batch_id}/run")
async def capture_run(batch_id: str, payload: dict):
    """Trigger Stage 3 capture for a discovered batch as a BACKGROUND job (per-district Node Playwright
    subprocesses can't block a request). Guard: no run already in flight. Live progress streams into
    _CAPTURE_JOBS; durable truth is captures.json + the state_event log + the DB cache that run_batch
    writes."""
    actor = payload.get("actor", "ian")
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    existing = _CAPTURE_JOBS.get(batch_id)
    if existing and existing["state"] == "running":
        raise HTTPException(409, f"capture already running for {batch_id}")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {"state": "running", "started_at": now, "actor": actor, "events": [],
           "summary": None, "error": None, "finished_at": None}
    _CAPTURE_JOBS[batch_id] = job

    def _on_event(kind, p):
        job["events"].append({"kind": kind, **p})

    def _work():
        try:
            job["summary"] = H3.run_batch(batch, actor=actor, on_event=_on_event)
            job["state"] = "done"
        except SystemExit as e:   # reconcile CONTROL FAILURE — surface, don't hide
            job["state"], job["error"] = "halted", f"CONTROL FAILURE: {e}"
        except Exception as e:
            job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
        finally:
            job["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    import threading
    threading.Thread(target=_work, name=f"capture-{batch_id}", daemon=True).start()
    return {"started": True, "batch_id": batch_id}


# ---------------------------------------------------------------- Stage 4 (Process) console — REQ-111
# Stage 4 is UNGATED -> status/observability (a processing-health + tool-effectiveness readout read FROM
# THE DB cross-stage cache, the working store the Stage-4 finish hook keeps fresh) + an orchestration
# trigger (the local harvesters, run IN-PROCESS as a background job). Unlike Stage 2/3 the work is plain
# Python, not a subprocess. Durable truth = processed.json on disk + the state_event log.
_PROCESS_JOBS: dict = {}


def _process_job_view(batch_id: str) -> dict | None:
    j = _PROCESS_JOBS.get(batch_id)
    if not j:
        return None
    return {"state": j["state"], "started_at": j["started_at"], "finished_at": j.get("finished_at"),
            "actor": j["actor"], "events": j["events"][-50:], "summary": j.get("summary"),
            "error": j.get("error")}


@app.get("/api/process/{batch_id}")
def process_status(batch_id: str):
    """Read-only Stage 4 status for a batch: per-district process outcome + usable-doc counts + the
    usable-representations-by-tool distribution, read from the DB cross-stage cache, plus the live job
    feed (if a run is in flight)."""
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    st = H4.status_for_batch(batch)
    return {"batch_id": batch_id, "batch_status": batch["batch_status"], **st,
            "job": _process_job_view(batch_id)}


@app.post("/api/process/{batch_id}/run")
async def process_run(batch_id: str, payload: dict):
    """Trigger Stage 4 processing for a captured batch as a BACKGROUND job (the per-district local
    harvesters run sequentially and can't block a request). Guard: no run already in flight. Live
    progress streams into _PROCESS_JOBS; durable truth is processed.json + the state_event log + the DB
    cache that run_batch writes."""
    actor = payload.get("actor", "ian")
    batch = _batch_from_db(batch_id)
    if batch is None:
        raise HTTPException(404, f"no such batch {batch_id}")
    existing = _PROCESS_JOBS.get(batch_id)
    if existing and existing["state"] == "running":
        raise HTTPException(409, f"processing already running for {batch_id}")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {"state": "running", "started_at": now, "actor": actor, "events": [],
           "summary": None, "error": None, "finished_at": None}
    _PROCESS_JOBS[batch_id] = job

    def _on_event(kind, p):
        job["events"].append({"kind": kind, **p})

    def _work():
        try:
            summary = H4.run_batch(batch, actor=actor, on_event=_on_event)
            job["summary"] = summary
            job["state"] = "done"
            # Stage 4 -> Stage 5 handoff: when THIS run actually processed districts (todo>0), check
            # whether the batch is now fully resolved and, if so, incrementally ingest just this batch
            # into the Stage 5 signal tables (+ regenerate filtered.json). Precomputing here means
            # switching to the Stage 5 view is instant — no full-corpus rebuild, no perceived lag.
            if summary.get("todo"):
                _ingest_stage5_if_complete(batch, _on_event)
        except SystemExit as e:   # reconcile / file-existence CONTROL FAILURE — surface, don't hide
            job["state"], job["error"] = "halted", f"CONTROL FAILURE: {e}"
        except Exception as e:
            job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
        finally:
            job["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    import threading
    threading.Thread(target=_work, name=f"process-{batch_id}", daemon=True).start()
    return {"started": True, "batch_id": batch_id}


def _ingest_stage5_if_complete(batch: dict, on_event) -> None:
    """The Stage-4 -> Stage-5 handoff. If every district in `batch` is now resolved (processed or
    terminally no-link), run the INCREMENTAL Stage-5 ingest for just this batch (BS.ingest_batch —
    leaves prior batches untouched) and record a Stage-5 progression event per ingested district
    (furthest_stage -> 5), so the batch is durably "done through Stage 4 / in Stage 5". Best-effort:
    Stage 4's processed.json is already the durable record, so an ingest hiccup is surfaced as an
    event (and re-runnable via build_signals) but never fails the successful Stage-4 job."""
    rollup = H4.status_for_batch(batch)["rollup"]
    if rollup["resolved"] < rollup["total"]:
        return   # not fully processed yet (failures awaiting retry) — defer the ingest to a later run
    try:
        ids = [d["district_id"] for d in batch["districts"]]
        summary = BS.ingest_batch(ids)
        registry = DS.load()
        for did in summary["districts"]:
            d = next((x for x in batch["districts"] if x["district_id"] == did), {})
            DS.record_stage(registry, did, d.get("name", ""), d.get("state", ""), stage=5,
                            stage_name="filter", outcome="ingested", actor="auto:stage5",
                            batch_id=batch["batch_id"])
        DS.save(registry)
        on_event("stage5_ingested", {"batch_id": batch["batch_id"], "n_districts": summary["n_districts"],
                                     "n_records": summary["n_records"], "n_send": summary["n_send"]})
    except Exception as e:
        on_event("stage5_ingest_failed", {"batch_id": batch["batch_id"], "error": str(e)[:200]})
        print(f"[warn] Stage 5 ingest for {batch['batch_id']} failed ({type(e).__name__}: {e}); "
              f"re-run `python3 -m infrastructure.acquisition.stage5_filter.build_signals` manually")


# ----------------------------- Stage 6 — Dispatch routing/release (gate@6, REQ-101) -----------------------------
# Build a handoff package from the Stage-5 release decision, review routed councils + estimated cost,
# then APPROVE & FREEZE (gate@6) — writes the immutable handoff_<hash>.json + records the dispatch.
# Stops at the seam: NO paid Stage-7 calls here.
_TARGET_IN = "','".join(sorted(BS.TARGET_LABELS))


@app.get("/api/handoff/candidates")
def handoff_candidates():
    """Stage-5 districts available to dispatch, each with `n_send` (canonical records `release.decide`
    will SEND — labeled targets + unlabeled tier-A), `n_verified` (the human-labeled-target subset of
    n_send — what a `verified_only` dispatch sends), and `n_hold` (unlabeled tier-B/C awaiting a gate@5
    label). Matches the tier-gated release rule, so the badge reflects what dispatch actually sends, not
    the whole recall-biased funnel. Reuses release.CANONICAL_RECORD_WHERE. Preview stays authoritative
    for the exact representation count + cost."""
    with gdb.session_scope() as con:
        rows = con.execute(text(
            f"""SELECT d.district_id, d.name, d.state, d.labeled_topology,
                       COALESCE(t.n_send, 0) AS n_send, COALESCE(t.n_verified, 0) AS n_verified,
                       COALESCE(t.n_hold, 0) AS n_hold
                FROM district d
                LEFT JOIN (
                    SELECT r.district_id,
                      COUNT(*) FILTER (WHERE l.primary_label IN ('{_TARGET_IN}')
                                          OR (l.primary_label IS NULL AND r.tier = 'A')) AS n_send,
                      COUNT(*) FILTER (WHERE l.primary_label IN ('{_TARGET_IN}')) AS n_verified,
                      COUNT(*) FILTER (WHERE l.primary_label IS NULL AND r.tier IN ('B', 'C')) AS n_hold
                    FROM record r LEFT JOIN label l ON l.rec_key = r.rec_key
                    WHERE {REL.CANONICAL_RECORD_WHERE}
                    GROUP BY r.district_id
                ) t ON t.district_id = d.district_id
                ORDER BY n_send DESC, n_hold DESC, d.district_id""")).mappings().all()
        return [dict(r) for r in rows]


@app.post("/api/handoff/preview")
async def handoff_preview(payload: dict):
    """Build the in-memory handoff package for the selected districts (routed + priced) — no persist.
    `overrides` = gate@6 per-rep council overrides ({"<rec_key>::<file>": council_id})."""
    ids = payload.get("district_ids") or []
    overrides = payload.get("overrides") or {}
    verified_only = bool(payload.get("verified_only"))
    with gdb.session_scope() as con:
        return H6.build_handoff_package(con, ids, overrides=overrides, verified_only=verified_only)


@app.post("/api/handoff/dispatch")
async def handoff_dispatch(payload: dict):
    """gate@6 approve: freeze the immutable handoff + record the dispatch (the index row + per-district
    `dispatched` state_events). Stops at the seam — no paid OpenRouter calls (that's Stage 7)."""
    ids = payload.get("district_ids") or []
    actor = payload.get("actor", "ian")
    overrides = payload.get("overrides") or {}
    verified_only = bool(payload.get("verified_only"))
    if not ids:
        raise HTTPException(400, "no districts selected")
    try:
        with gdb.session_scope() as con:
            doc, path = H6.dispatch_handoff(con, ids, created_by=actor, overrides=overrides,
                                            verified_only=verified_only)
    except FileExistsError:
        raise HTTPException(409, "an identical handoff was just dispatched (same content within the "
                                 "same second) — the prior one stands; retry in a moment if intended")
    cost = doc.get("cost") or {}
    return {"handoff_id": HND6.handoff_filename(doc)[:-5], "handoff_hash": doc["handoff_hash"],
            "verified_only": bool(doc.get("verified_only")),
            "n_districts": len(doc.get("districts", [])), "n_reps": cost.get("n_reps", 0),
            "total_usd": cost.get("total_usd", 0.0), "provenance": cost.get("provenance", "unknown"),
            "path": str(path)}


@app.get("/api/handoffs")
def handoff_list():
    """The dispatched handoffs index (newest first)."""
    with gdb.session_scope() as con:
        rows = con.execute(text(
            "SELECT handoff_id, created_at, created_by, status, n_districts, n_reps, total_usd, "
            "cost_provenance FROM handoff ORDER BY created_at DESC")).mappings().all()
        return [dict(r) for r in rows]


@app.get("/api/handoff/councils")
def handoff_councils():
    """The council registry (id / name / input_kinds) for the gate@6 per-rep override dropdown."""
    return [{"id": cid, "name": c.get("name", cid), "input_kinds": c.get("input_kinds", [])}
            for cid, c in C6.load_configs().items()]


@app.get("/api/handoff/inspect")
def handoff_inspect(district_id: str, rec_key: str, file: str):
    """Serve one representation's file (text / image / pdf) for gate@6 inspection. Resolves
    RAW_CAPTURES/<district_dir>/captures/<hash>/<file>; path-safe (basename-only file + hex hash)."""
    if not file or "/" in file or "\\" in file or ".." in file:
        raise HTTPException(400, "bad file")
    if ":" not in rec_key or not re.fullmatch(r"[0-9a-fA-F]+", rec_key.split(":", 1)[1]):
        raise HTTPException(400, "bad rec_key")
    h = rec_key.split(":", 1)[1]
    with gdb.session_scope() as con:
        ddir = con.execute(text("SELECT district_dir FROM district WHERE district_id = :d"),
                           {"d": district_id}).scalar()
    if not ddir:
        raise HTTPException(404, "no such district")
    fp = paths.RAW_CAPTURES / ddir / "captures" / h / file
    if not fp.exists():
        raise HTTPException(404, f"file not found: {file}")
    return FileResponse(fp)


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


if __name__ == "__main__":
    import uvicorn
    # The governance Postgres must be reachable AND ingested (run build_signals.py). Fail fast with
    # a clear hint rather than 500ing on the first request.
    try:
        with gdb.session_scope() as con:
            con.execute(text("SELECT 1 FROM record LIMIT 1"))
    except Exception as e:
        raise SystemExit(f"governance DB not reachable/ingested ({type(e).__name__}: {e}) — "
                         f"start Docker (lct_postgres) and run build_signals.py first.")
    uvicorn.run(app, host="127.0.0.1", port=8005)
