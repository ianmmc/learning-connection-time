#!/usr/bin/env python3
"""Stage 5 review app — local FastAPI server (single-user, localhost only).

Serves the 3-column review UI, the SQLite-backed record/label API, and the captured local
files (text/image/pdf) for inspection. NO AI anywhere — this is the human-labeling harness
around the deterministic signals computed by build_signals.py.

Run:  uvicorn server:app --reload --port 8005   (from this directory)
  or  python3 server.py
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

HERE = Path(__file__).resolve().parent
from infrastructure.acquisition.stage5_filter import build_signals as BS    # noqa: E402  (export_labels lives here, shared with ingest)
from infrastructure.acquisition.common import db as gdb                     # noqa: E402  (isolated governance Postgres — REQ-103)

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
        con.commit()   # persist before exporting, so the JSON backup only reflects committed state
        # Export-on-save: the precious label is backed up to the tracked JSON before we return,
        # so it survives DB loss with zero action from the user (no reliance on remembering).
        BS.export_labels(con, LABELS_JSON)
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
        con.commit()   # persist before exporting, so the JSON backup only reflects committed state
        BS.export_splits(con, CLUSTER_SPLITS_JSON)
    return {"ok": True}


@app.get("/api/progress")
def progress():
    with gdb.session_scope() as con:
        total = con.execute(text("SELECT COUNT(*) FROM record")).scalar()
        done = con.execute(text("SELECT COUNT(*) FROM label WHERE status!='unlabeled'")).scalar()
    return {"total": total, "labeled": done}


@app.get("/files/{district_dir}/{rec_hash}/{filename}")
def serve_file(district_dir: str, rec_hash: str, filename: str):
    """Serve a captured file for inspection. Path-restricted to within a record's capture dir."""
    base = (RAW_DIR / district_dir / "captures" / rec_hash).resolve()
    target = (base / filename).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(target)


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
