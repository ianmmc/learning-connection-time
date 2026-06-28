"""Stage 3 (Capture) batch runner -- the console's orchestration + observability entry.

Stage 3 is UNGATED: the console surfaces it as STATUS/observability (a health / emergent readout) plus a
run trigger. This mirrors the Stage 2 headless runner exactly -- Python orchestrates (reconcile
filesystem-authoritative, SEQUENTIAL per-district so there is one registry writer, events for the job
feed), and a SUBPROCESS does the risky/external work. Here that subprocess is the Node Playwright capture
(`capture_discovery.mjs district <ROOT> <district_dir>`), one fresh process per district -- batch-scoped,
so a run never re-captures the rest of RAW_DIR.

After each district's captures.json lands, `capture_stage3.finish_district` records the state_event AND
projects the capture receipts into the live DB cache (common/cache_ingest) -- which is what the console
reads. The DB is the working store; captures.json on disk is the regenerable, authoritative source.

Driven by `run_batch()` (the console's POST /api/capture/{batch_id}/run trigger) or as a CLI:
  python3 -m infrastructure.acquisition.stage3_capture.headless run <batch_id|path>
"""
import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage3_capture import capture_stage3 as C3

RAW_DIR = paths.RAW_CAPTURES
CAPTURE_MJS = paths.REPO_ROOT / "infrastructure" / "scraper" / "capture_discovery.mjs"
CAPTURE_TIMEOUT_S = 1800   # per-district Node capture budget (a large district's pages + emergent hops)
CONCURRENCY = 5            # within-district page concurrency passed to the Node script


def load_batch_any(batch_ref: str) -> dict:
    """Accept either a batch receipt path or a bare batch_id (resolved under paths.QUEUE_DIR)."""
    p = Path(batch_ref)
    if not p.exists():
        p = paths.QUEUE_DIR / (batch_ref if batch_ref.endswith(".json") else f"{batch_ref}.json")
    if not p.exists():
        raise SystemExit(f"batch not found: {batch_ref} (looked at {p})")
    return json.loads(p.read_text())


def find_batch_districts(batch: dict) -> list:
    """The batch's districts that are READY for capture -- i.e. on disk with discovery.json +
    candidates.json (C3.find_districts builds the dir + header fields from disk). Districts still
    awaiting Stage 2 naturally drop out here (and show as `awaiting_discovery` in status)."""
    ids = {d["district_id"] for d in batch["districts"]}
    return [d for d in C3.find_districts(RAW_DIR) if d["district_id"] in ids]


def _capture_one(district: dict, *, _run=subprocess.run) -> None:
    """Run the Node Playwright capture for ONE district dir (a fresh subprocess). Raises on a non-zero
    exit or a missing captures.json, so run_batch records the district `failed` rather than silently
    advancing it."""
    cmd = ["node", str(CAPTURE_MJS), "district", str(RAW_DIR), district["dir"].name, str(CONCURRENCY)]
    proc = _run(cmd, capture_output=True, text=True, timeout=CAPTURE_TIMEOUT_S, cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(f"node capture exit {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}")
    if not (district["dir"] / "captures.json").exists():
        raise RuntimeError("node capture finished but wrote no captures.json")


# ----------------------------------------------------------------- status / observability (reads the DB)
def status_for_batch(batch: dict) -> dict:
    """Read-only Stage-3 observability for a batch, FROM THE DB cross-stage cache (the working store the
    Stage-3 finish hook keeps fresh). Per district: lifecycle status (awaiting_discovery / todo / done),
    capture outcome + counts (ok / failed / emergent), and the failure-reason breakdown. Batch-level:
    a rollup + the CMS/host distribution (governance §11f). Disk is consulted ONLY to tell
    awaiting_discovery (no candidates.json) from todo (candidates.json, no captures.json) from done."""
    ondisk = {d["district_id"]: d for d in C3.find_districts(RAW_DIR)}   # id -> {dir, name, ...}
    ids = [d["district_id"] for d in batch["districts"]]
    rows_by_did: dict = {}
    with gdb.session_scope() as con:
        CI.ensure_cache_schema(con)
        for r in con.execute(text(
                """SELECT district_id, ok, source, err, final_host, fingerprint_json
                   FROM capture WHERE district_id = ANY(:ids)"""), {"ids": ids}).mappings():
            rows_by_did.setdefault(r["district_id"], []).append(dict(r))

    districts, hosts, cmss = [], Counter(), Counter()
    for d in batch["districts"]:
        did = d["district_id"]
        row = {"district_id": did, "name": d["name"], "state": d.get("state", ""),
               "domain": d.get("domain", "")}
        disk = ondisk.get(did)
        captured = bool(disk) and (disk["dir"] / "captures.json").exists()
        if not disk:
            row.update(status="awaiting_discovery", outcome=None, n_captures=0, n_ok=0,
                       n_failed=0, n_emergent=0, errs={}, cached=True)
            districts.append(row)
            continue
        if not captured:
            row.update(status="todo", outcome=None, n_captures=0, n_ok=0, n_failed=0,
                       n_emergent=0, errs={}, cached=True)
            districts.append(row)
            continue
        caps = rows_by_did.get(did, [])
        n_ok = sum(1 for c in caps if c["ok"])
        n_failed = sum(1 for c in caps if not c["ok"])
        errs = Counter(c["err"] or "unknown" for c in caps if not c["ok"])
        for c in caps:
            if c["ok"] and c["final_host"]:
                hosts[c["final_host"]] += 1
                try:
                    hint = (json.loads(c["fingerprint_json"]) or {}).get("cms_hint")
                except (json.JSONDecodeError, TypeError):
                    hint = None
                if hint:
                    cmss[hint] += 1
        outcome = (None if not caps else
                   "captured_all" if n_failed == 0 else
                   "capture_failed_all" if n_ok == 0 else "captured_partial")
        row.update(status="done", outcome=outcome, n_captures=len(caps), n_ok=n_ok,
                   n_failed=n_failed, n_emergent=sum(1 for c in caps if c["source"] == "emergent"),
                   errs=dict(errs), cached=bool(caps))   # captured-but-uncached -> cached=False (DB stale)
        districts.append(row)

    return {"districts": districts, "rollup": _rollup(districts),
            "hosts": hosts.most_common(), "cms": cmss.most_common()}


def _rollup(districts: list) -> dict:
    done = [d for d in districts if d["status"] == "done"]
    return {
        "total": len(districts),
        "done": len(done),
        "todo": sum(1 for d in districts if d["status"] == "todo"),
        "awaiting_discovery": sum(1 for d in districts if d["status"] == "awaiting_discovery"),
        "captured_all": sum(1 for d in done if d["outcome"] == "captured_all"),
        "captured_partial": sum(1 for d in done if d["outcome"] == "captured_partial"),
        "capture_failed_all": sum(1 for d in done if d["outcome"] == "capture_failed_all"),
        "n_captures": sum(d["n_captures"] for d in done),
        "n_failed": sum(d["n_failed"] for d in done),
        "n_emergent": sum(d["n_emergent"] for d in done),
    }


# ----------------------------------------------------------------------------------- the batch run
def run_batch(batch: dict, *, actor: str = "auto:stage3", on_event=None, _run=subprocess.run) -> dict:
    """Deterministic Stage 3 (Capture) for a batch: reconcile (filesystem is truth; a
    registry-ahead-of-disk CONTROL FAILURE raises SystemExit and halts), then per todo district run the
    Node capture subprocess -> capture_stage3.finish_district (state_event + DB cache upsert).
    SEQUENTIAL (one registry writer, no race). `on_event(kind, payload)` feeds the console job board.
    `_run` is injectable for tests (no live Node subprocess).

    `batch` is the resolved working-store dict ({batch_id, districts:[{district_id,name,state,...}]}) —
    the caller passes it from the DB (the console) or the receipt (the CLI), so the runner never reaches
    for the on-disk receipt itself."""
    batch_id = batch["batch_id"]

    def emit(kind, **payload):
        if on_event:
            on_event(kind, {"batch_id": batch_id, **payload})

    districts = find_batch_districts(batch)
    registry = DS.load()
    todo, skipped = C3.reconcile(districts, registry)
    DS.save(registry)
    emit("reconciled", todo=[d["district_id"] for d in todo],
         skipped=[d["district_id"] for d in skipped])
    if not todo:
        return {"batch_id": batch_id, "todo": 0, "skipped": len(skipped), "results": []}

    registry = DS.load()
    for d in todo:
        DS.record_stage(registry, d["district_id"], d["name"], d["state"], stage_name="capture",
                        event_type="dispatched", actor=actor, batch_id=batch_id)
        emit("dispatched", district_id=d["district_id"], name=d["name"])
    DS.save(registry)

    results = []
    for d in todo:
        did = d["district_id"]
        try:
            _capture_one(d, _run=_run)
            registry = DS.load()
            outcome = C3.finish_district(d, registry)   # reads captures.json + upserts the DB cache
            DS.save(registry)
            results.append({"district_id": did, "name": d["name"], "outcome": outcome})
            emit("completed", district_id=did, name=d["name"], outcome=outcome)
        except SystemExit:
            raise   # CONTROL FAILURE -- never swallow
        except Exception as e:
            registry = DS.load()
            DS.record_stage(registry, did, d["name"], d["state"], stage_name="capture",
                            event_type="failed", actor=actor, batch_id=batch_id,
                            notes=f"{type(e).__name__}: {str(e)[:200]}")
            DS.save(registry)
            results.append({"district_id": did, "name": d["name"], "outcome": "error",
                            "error": f"{type(e).__name__}: {str(e)[:200]}"})
            emit("failed", district_id=did, name=d["name"], error=str(e)[:200])
    return {"batch_id": batch_id, "todo": len(todo), "skipped": len(skipped), "results": results}


def main():
    ap = argparse.ArgumentParser(description="Stage 3 (Capture) batch runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="capture an approved+discovered batch (per-district Node subprocess)")
    p.add_argument("batch", help="batch_id or path to batch_NNNNN.json receipt")
    p.add_argument("--actor", default="ian")
    a = ap.parse_args()
    if a.cmd == "run":
        batch = load_batch_any(a.batch)   # CLI loads the receipt; the console passes a DB-resolved dict
        summary = run_batch(batch, actor=a.actor,
                            on_event=lambda k, p: print(f"[{k}] " + json.dumps(p)))
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
