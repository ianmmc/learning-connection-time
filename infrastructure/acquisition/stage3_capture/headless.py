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

from infrastructure.acquisition.common import batch_guard as BG
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage3_capture import capture_stage3 as C3

RAW_DIR = paths.RAW_CAPTURES
CAPTURE_MJS = paths.REPO_ROOT / "infrastructure" / "scraper" / "capture_discovery.mjs"
CAPTURE_DEADLINE_S = 600   # the Node-owns-shutdown budget passed to the capture: once it passes, Node
                           # stops pulling new pages, records the rest `not_attempted`, and writes a
                           # PARTIAL captures.json (captured_partial) instead of being killed with its
                           # work orphaned. A large district (LAS CRUCES, 128 candidates) captures what
                           # fits and cleanly reports the remainder, retriable later.
DRAIN_BUFFER_S = 240       # headroom for in-flight pages to finish + the manifest write after the
                           # deadline (each page is bounded by the per-op timeouts: goto 15 (#225,
                           # GOTO_WAIT in capture_discovery.mjs) / fetch 20 / screenshot+pdf 45 each).
                           # The Python subprocess timeout is the BACKSTOP —
                           # it only fires if Node itself hangs; then reconstruct-from-disk recovers it.
CAPTURE_TIMEOUT_S = CAPTURE_DEADLINE_S + DRAIN_BUFFER_S   # subprocess backstop (> Node's own deadline)
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


def candidate_count(ddir: Path) -> int:
    """Number of capture-plan URLs in a district's candidates.json (0 if empty/absent/unreadable).
    Zero == Stage 2 found no links (district_outcome `manual_flag_all`) == nothing for Playwright to
    capture. The authoritative pre-capture signal: a no-link district is terminal at Stage 2 and is
    never dispatched (we know it has no links before sending it into the process)."""
    cf = ddir / "candidates.json"
    try:
        return len(json.loads(cf.read_text()).get("candidates", []))
    except (json.JSONDecodeError, OSError, AttributeError, TypeError):
        return 0


def _capture_one(district: dict, *, _run=subprocess.run) -> None:
    """Run the Node Playwright capture for ONE district dir (a fresh subprocess). Raises on a non-zero
    exit or a missing captures.json, so run_batch records the district `failed` rather than silently
    advancing it."""
    cmd = ["node", str(CAPTURE_MJS), "district", str(RAW_DIR), district["dir"].name,
           str(CONCURRENCY), str(CAPTURE_DEADLINE_S)]   # Node owns its deadline; the subprocess timeout is a backstop
    proc = _run(cmd, capture_output=True, text=True, timeout=CAPTURE_TIMEOUT_S, cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(f"node capture exit {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}")
    if not (district["dir"] / "captures.json").exists():
        raise RuntimeError("node capture finished but wrote no captures.json")


# ----------------------------------------------------------------- status / observability (reads the DB)
def status_for_batch(batch: dict) -> dict:
    """Read-only Stage-3 observability for a batch, FROM THE DB cross-stage cache (the working store the
    Stage-3 finish hook keeps fresh). Per district, one of four states:
      - `awaiting_discovery` — no discovery yet (no candidates.json on disk)
      - `manual_flag_all`    — discovered but ZERO links (terminal at Stage 2; never captured) — the
                               SAME label Stage 2 uses, sourced from the candidate count, NOT a Stage-3
                               artifact (so it's correct even for the empty-capture districts the old
                               pre-skip runs left behind)
      - `todo`               — has links, not captured yet
      - `done`               — captured; outcome + counts (ok/failed/emergent) + the err breakdown
    Batch-level: a rollup + the CMS/host distribution (governance §11f). SELF-HEALING like Stage 2: a
    captured district whose rows aren't in the cache yet (pre-hook / DB-down run) is ingested on view."""
    ids = [d["district_id"] for d in batch["districts"]]
    ondisk = {d["district_id"]: d for d in C3.find_districts(RAW_DIR)}   # id -> {dir, name, ...}
    cand_n = {did: candidate_count(dk["dir"]) for did, dk in ondisk.items()}
    captured_on_disk = {did for did, dk in ondisk.items() if (dk["dir"] / "captures.json").exists()}
    # `done` = discovered, HAD links, and captured. (No-link districts never capture -> manual_flag_all.)
    done_ids = [d["district_id"] for d in batch["districts"]
                if d["district_id"] in captured_on_disk and cand_n.get(d["district_id"], 0) > 0]

    # Capture FAILURES (timeout / Node crash) leave NO captures.json and write a `failed` capture event
    # with no stage number -- so without this they read as `todo`, indistinguishable from "not attempted"
    # (the Brookwood bug: the failure showed only in the run log). Surface the latest capture event per
    # district; if it's `failed` and there's no captures.json, the district is `failed`, not `todo`.
    failed_caps: dict = {}
    with gdb.session_scope() as con:
        CI.ensure_cache_schema(con)
        for r in con.execute(text(
                """SELECT DISTINCT ON (district_id) district_id, event_type, note
                   FROM state_event WHERE stage_name = 'capture' AND district_id = ANY(:ids)
                   ORDER BY district_id, event_id DESC"""), {"ids": ids or [""]}).mappings():
            if r["event_type"] == "failed":
                failed_caps[r["district_id"]] = r["note"]
        cached_ids = {r[0] for r in con.execute(text(
            "SELECT DISTINCT district_id FROM capture WHERE district_id = ANY(:ids)"),
            {"ids": done_ids or [""]})}
    for did in done_ids:                     # self-heal: ingest captures the cache is missing
        if did not in cached_ids:
            CI.cache_capture(ondisk[did]["dir"], did)

    rows_by_did: dict = {}
    with gdb.session_scope() as con:
        for r in con.execute(text(
                """SELECT district_id, ok, source, err, final_host, fingerprint_json
                   FROM capture WHERE district_id = ANY(:ids)"""), {"ids": done_ids or [""]}).mappings():
            rows_by_did.setdefault(r["district_id"], []).append(dict(r))

    districts, hosts, cmss = [], Counter(), Counter()
    for d in batch["districts"]:
        did = d["district_id"]
        row = {"district_id": did, "name": d["name"], "state": d.get("state", ""),
               "domain": d.get("domain", ""), "outcome": None, "n_captures": 0, "n_ok": 0,
               "n_failed": 0, "n_emergent": 0, "errs": {}}
        if did not in ondisk:
            districts.append({**row, "status": "awaiting_discovery"})
            continue
        if cand_n.get(did, 0) == 0:          # discovered, no links -> terminal manual_flag_all
            districts.append({**row, "status": "manual_flag_all", "outcome": "manual_flag_all"})
            continue
        if did not in captured_on_disk:
            if did in failed_caps:           # capture errored/timed out -> failed (retriable), not todo
                note = failed_caps[did] or ""
                st = "timed_out" if note.startswith("TimeoutExpired") else "failed"
                districts.append({**row, "status": st, "outcome": st, "error": note[:300]})
            else:
                districts.append({**row, "status": "todo"})
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
        outcome = ("captured_all" if n_failed == 0 else
                   "capture_failed_all" if n_ok == 0 else "captured_partial")
        districts.append({**row, "status": "done", "outcome": outcome, "n_captures": len(caps),
                          "n_ok": n_ok, "n_failed": n_failed,
                          "n_emergent": sum(1 for c in caps if c["source"] == "emergent"),
                          "errs": dict(errs)})

    return {"districts": districts, "rollup": _rollup(districts),
            "hosts": hosts.most_common(), "cms": cmss.most_common()}


# District-level capture failures (retriable, NOT resolved): a generic error or a timeout. Both count
# as `failed` in the rollup; the per-district status distinguishes `timed_out` for the UI.
FAILED_STATUSES = ("failed", "timed_out")


def _rollup(districts: list) -> dict:
    done = [d for d in districts if d["status"] == "done"]
    flagged = sum(1 for d in districts if d["status"] == "manual_flag_all")
    total = len(districts)
    return {
        "total": total,
        "done": len(done),
        "manual_flag_all": flagged,
        "todo": sum(1 for d in districts if d["status"] == "todo"),
        # district-level capture failures (timeout / crash) — retriable; NOT counted as resolved
        "failed": sum(1 for d in districts if d["status"] in FAILED_STATUSES),
        "awaiting_discovery": sum(1 for d in districts if d["status"] == "awaiting_discovery"),
        # resolved = captured OR terminally flagged; the batch's Stage-3 is complete when resolved==total
        "resolved": len(done) + flagged,
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
    with gdb.session_scope() as _con:      # #168: never run a stage on a terminal abandoned batch
        BG.assert_runnable(_con, batch_id)

    def emit(kind, **payload):
        if on_event:
            on_event(kind, {"batch_id": batch_id, **payload})

    # Per-district saves defer the district_status.json regeneration (export=False; issue #49) — one
    # explicit DS.export() at run end (in a finally, so a crash still exports the committed events).
    try:
        districts = find_batch_districts(batch)
        registry = DS.load()
        todo, skipped = C3.reconcile(districts, registry,
                                     redo=batch.get("batch_type") == "follow-up")
        DS.save(registry, export=False)
        # Drop no-link districts (Stage 2 manual_flag_all -> empty candidates.json) BEFORE dispatch: they
        # have nothing for Playwright, are terminal at Stage 2, and get no Stage-3 artifact/event (they
        # surface as `manual_flag_all` in status, sourced from the discovery state). Cheap pre-capture skip
        # that matters at continuous-running scale.
        n_cands = {d["district_id"]: candidate_count(d["dir"]) for d in todo}   # one read per district (#454)
        no_link = [d for d in todo if n_cands[d["district_id"]] == 0]
        todo = [d for d in todo if n_cands[d["district_id"]] > 0]
        for d in no_link:
            emit("skipped_no_links", district_id=d["district_id"], name=d["name"])
        emit("reconciled", todo=[d["district_id"] for d in todo],
             skipped=[d["district_id"] for d in skipped], no_links=[d["district_id"] for d in no_link])
        if not todo:
            return {"batch_id": batch_id, "todo": 0, "skipped": len(skipped),
                    "no_links": len(no_link), "results": []}

        registry = DS.load()
        for d in todo:
            DS.record_stage(registry, d["district_id"], d["name"], d["state"], stage_name="capture",
                            event_type="dispatched", actor=actor, batch_id=batch_id)
            emit("dispatched", district_id=d["district_id"], name=d["name"])
        DS.save(registry, export=False)

        results = []
        for d in todo:
            did = d["district_id"]
            try:
                _capture_one(d, _run=_run)
                registry = DS.load()
                outcome = C3.finish_district(d, registry)   # reads captures.json + upserts the DB cache
                DS.save(registry, export=False)
                results.append({"district_id": did, "name": d["name"], "outcome": outcome})
                emit("completed", district_id=did, name=d["name"], outcome=outcome)
            except SystemExit:
                raise   # CONTROL FAILURE -- never swallow
            except Exception as e:
                registry = DS.load()
                DS.record_stage(registry, did, d["name"], d["state"], stage_name="capture",
                                event_type="failed", actor=actor, batch_id=batch_id,
                                notes=f"{type(e).__name__}: {str(e)[:200]}")
                DS.save(registry, export=False)
                results.append({"district_id": did, "name": d["name"], "outcome": "error",
                                "error": f"{type(e).__name__}: {str(e)[:200]}"})
                emit("failed", district_id=did, name=d["name"], error=str(e)[:200])
        return {"batch_id": batch_id, "todo": len(todo), "skipped": len(skipped),
                "no_links": len(no_link), "results": results}
    finally:
        DS.export()   # one full district_status.json regeneration per run (issue #49)


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
