#!/usr/bin/env python3
"""Stage 5 review app — local FastAPI server (single-user, localhost only).

Serves the 3-column review UI, the SQLite-backed record/label API, and the captured local
files (text/image/pdf) for inspection. NO AI anywhere — this is the human-labeling harness
around the deterministic signals computed by build_signals.py.

Run:  uvicorn server:app --reload --port 8005   (from this directory)
  or  python3 server.py
"""
import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[3]            # .../learning-connection-time
DB_PATH = PROJECT_ROOT / "data/acquisition/stage5_review/review.db"
RAW_DIR = PROJECT_ROOT / "data/raw/lea-website-captures"

app = FastAPI(title="Stage 5 Review")


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@app.get("/api/tree")
def tree():
    """Districts -> records for the left column. Records carry tier + label status only
    (NOT the category hypothesis — that stays hidden until the record is labeled)."""
    con = db()
    out = []
    for d in con.execute("SELECT * FROM district ORDER BY name"):
        recs = []
        q = """SELECT r.rec_key, r.url, r.hash, r.kind, r.tier, r.sort_score, r.duplicate_of,
                      l.status, l.primary_label
               FROM record r LEFT JOIN label l ON l.rec_key=r.rec_key
               WHERE r.district_id=? ORDER BY r.tier, r.sort_score DESC"""
        for r in con.execute(q, (d["district_id"],)):
            recs.append(dict(r))
        out.append({"district_id": d["district_id"], "name": d["name"], "state": d["state"],
                    "batch_id": d["batch_id"], "topology_hypothesis": d["topology_hypothesis"],
                    "records": recs})
    con.close()
    return out


@app.get("/api/record/{rec_key}")
def record(rec_key: str):
    con = db()
    r = con.execute("SELECT * FROM record WHERE rec_key=?", (rec_key,)).fetchone()
    if not r:
        con.close()
        raise HTTPException(404, "no such record")
    reps = [dict(x) for x in con.execute(
        "SELECT source, filename, file_kind, n_chars, n_times, usable FROM representation WHERE rec_key=?",
        (rec_key,))]
    label = dict(con.execute("SELECT * FROM label WHERE rec_key=?", (rec_key,)).fetchone() or {})
    con.close()
    signals = json.loads(r["signals_json"])
    # category_hypothesis is returned but the FRONTEND keeps it hidden until labeled, to avoid
    # anchoring the human's judgment (methodological choice — see the design note).
    return {
        "rec_key": rec_key, "url": r["url"], "hash": r["hash"], "kind": r["kind"],
        "final_url": r["final_url"], "district_dir": r["district_dir"], "tier": r["tier"],
        "category_hypothesis": r["category_hypothesis"], "duplicate_of": r["duplicate_of"],
        "content_hash": r["content_hash"], "signals": signals, "representations": reps,
        "label": label,
    }


@app.post("/api/label/{rec_key}")
async def save_label(rec_key: str, payload: dict):
    con = db()
    if not con.execute("SELECT 1 FROM record WHERE rec_key=?", (rec_key,)).fetchone():
        con.close()
        raise HTTPException(404, "no such record")
    from datetime import datetime, timezone
    con.execute(
        """INSERT INTO label (rec_key, primary_label, flags_json, note, status, updated_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(rec_key) DO UPDATE SET
             primary_label=excluded.primary_label, flags_json=excluded.flags_json,
             note=excluded.note, status=excluded.status, updated_at=excluded.updated_at""",
        (rec_key, payload.get("primary_label"), json.dumps(payload.get("flags", [])),
         payload.get("note", ""), payload.get("status", "labeled"),
         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    con.commit()
    con.close()
    return {"ok": True}


@app.get("/api/progress")
def progress():
    con = db()
    total = con.execute("SELECT COUNT(*) FROM record").fetchone()[0]
    done = con.execute("SELECT COUNT(*) FROM label WHERE status!='unlabeled'").fetchone()[0]
    con.close()
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
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found at {DB_PATH} — run build_signals.py first.")
    uvicorn.run(app, host="127.0.0.1", port=8005)
