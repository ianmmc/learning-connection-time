"""Stage 4 (Process) batch runner -- the console's orchestration + observability entry.

Stage 4 is UNGATED: the console surfaces it as STATUS/observability (a processing-health + tool-
effectiveness readout) plus a run trigger. This mirrors the Stage 3 headless runner, with ONE structural
difference: Stage 4 does the work IN-PROCESS (pdftotext / pdfplumber / camelot / tesseract -- fast local
subprocess calls inside process_stage4), NOT via a separate long-lived worker process. So there is **no
node-owns-shutdown / per-district SIGKILL budget** to design here -- a district is processed by a Python
function call (`C4.finish_district`); a crash mid-district simply leaves processed.json unwritten, so
reconcile re-runs that district next time (idempotent). The Stage-3 deadline/partial-manifest pattern does
NOT transfer.

After each district's processed.json lands, `process_stage4.finish_district` records the state_event AND
projects the processed-doc rows into the live DB cache (common/cache_ingest) -- which is what the console
reads. The DB is the working store; processed.json on disk is the regenerable, authoritative source.

Driven by `run_batch()` (the console's POST /api/process/{batch_id}/run trigger) or as a CLI:
  python3 -m infrastructure.acquisition.stage4_process.headless run <batch_id|path>
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage4_process import process_stage4 as C4

RAW_DIR = paths.RAW_CAPTURES


def stage2_complete(root: Path) -> list:
    """Every dir under root that is Stage-2-complete -- discovery.json (header fields: name/state/domain)
    AND candidates.json (the capture plan; an empty one means a no-link `manual_flag_all` district). The
    pre-capture universe the Stage-4 status view classifies against -- deliberately a LOCAL scan, not an
    import of the Stage-3 module (the stages stay independent; the import-linter contract enforces it)."""
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        disc_path, cand_path = d / "discovery.json", d / "candidates.json"
        if not (d.is_dir() and disc_path.exists() and cand_path.exists()):
            continue
        disc = json.loads(disc_path.read_text())
        out.append({"district_id": disc["district_id"], "name": disc["name"],
                    "state": disc["state"], "domain": disc.get("domain", ""), "dir": d})
    return out


def load_batch_any(batch_ref: str) -> dict:
    """Accept either a batch receipt path or a bare batch_id (resolved under paths.QUEUE_DIR)."""
    p = Path(batch_ref)
    if not p.exists():
        p = paths.QUEUE_DIR / (batch_ref if batch_ref.endswith(".json") else f"{batch_ref}.json")
    if not p.exists():
        raise SystemExit(f"batch not found: {batch_ref} (looked at {p})")
    return json.loads(p.read_text())


def find_batch_districts(batch: dict) -> list:
    """The batch's districts READY for processing -- on disk with captures.json + discovery.json
    (C4.find_districts requires both). Districts still awaiting capture naturally drop out here (and
    show as `awaiting_capture` in status)."""
    ids = {d["district_id"] for d in batch["districts"]}
    return [d for d in C4.find_districts(RAW_DIR) if d["district_id"] in ids]


def candidate_count(ddir: Path) -> int:
    """Number of capture-plan URLs in a district's candidates.json (0 if empty/absent/unreadable).
    Zero == Stage 2 found no links (district_outcome `manual_flag_all`) == nothing was ever captured ==
    nothing for Stage 4 to process. The authoritative terminal signal: a no-link district never reaches
    Stage 4 and is denominator-excluded (processable = total - no-links)."""
    cf = ddir / "candidates.json"
    try:
        return len(json.loads(cf.read_text()).get("candidates", []))
    except (json.JSONDecodeError, OSError, AttributeError, TypeError):
        return 0


def winning_sources(ddir: Path) -> list:
    """Sources of every USABLE representation in this district's processed.json -- the tool-effectiveness
    signal (which harvesters/OCR are yielding usable text; governance §11f / STAGE4 §4 user story). Read
    off disk: the per-text `source` is NOT in the live processed_doc cache (which carries only n_texts +
    the doc-level usable flag). [] if absent/unreadable."""
    pf = ddir / "processed.json"
    try:
        docs = json.loads(pf.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [t["source"] for doc in docs for t in (doc.get("texts") or []) if t.get("usable")]


# ----------------------------------------------------------------- status / observability (reads the DB)
def status_for_batch(batch: dict) -> dict:
    """Read-only Stage-4 observability for a batch, FROM THE DB cross-stage cache (the working store the
    Stage-4 finish hook keeps fresh). Per district, one of these states:
      - `awaiting_discovery` — no discovery yet (not Stage-2-complete on disk)
      - `manual_flag_all`    — discovered but ZERO links (terminal at Stage 2; never captured/processed)
                               — the SAME label every stage uses, sourced from the candidate count
      - `awaiting_capture`   — has links, captured? no — Stage 3 not done yet (the upstream gate here)
      - `todo`               — captured, not processed yet
      - `failed`             — a process error left no processed.json (retriable; re-run)
      - `done`               — processed; outcome (processed_all/partial/no_usable_text_any) + doc counts
    Batch-level: a rollup + the usable-representations-by-tool distribution. SELF-HEALING like Stage 3: a
    processed district whose rows aren't in the cache yet (pre-hook / DB-down run) is ingested on view."""
    ids = [d["district_id"] for d in batch["districts"]]
    ondisk = {d["district_id"]: d for d in stage2_complete(RAW_DIR)}   # Stage-2-complete: id -> {dir,...}
    cand_n = {did: candidate_count(dk["dir"]) for did, dk in ondisk.items()}
    captured = {did for did, dk in ondisk.items() if (dk["dir"] / "captures.json").exists()}
    processed = {did for did, dk in ondisk.items() if (dk["dir"] / "processed.json").exists()}
    done_ids = [d["district_id"] for d in batch["districts"] if d["district_id"] in processed]

    # Process FAILURES (a tool/IO crash) leave NO processed.json and write a `failed` process event with
    # no stage number — so without this they read as `todo`, indistinguishable from "not attempted".
    # Surface the latest process event per district; if it's `failed` and there's no processed.json, the
    # district is `failed`, not `todo`.
    failed_procs: dict = {}
    with gdb.session_scope() as con:
        CI.ensure_cache_schema(con)
        for r in con.execute(text(
                """SELECT DISTINCT ON (district_id) district_id, event_type, note
                   FROM state_event WHERE stage_name = 'process' AND district_id = ANY(:ids)
                   ORDER BY district_id, event_id DESC"""), {"ids": ids or [""]}).mappings():
            if r["event_type"] == "failed":
                failed_procs[r["district_id"]] = r["note"]
        cached_ids = {r[0] for r in con.execute(text(
            "SELECT DISTINCT district_id FROM processed_doc WHERE district_id = ANY(:ids)"),
            {"ids": done_ids or [""]})}
    for did in done_ids:                     # self-heal: ingest the processed-doc rows the cache is missing
        if did not in cached_ids:
            CI.cache_processed(ondisk[did]["dir"], did)

    rows_by_did: dict = {}
    with gdb.session_scope() as con:
        for r in con.execute(text(
                "SELECT district_id, hash, url, usable FROM processed_doc WHERE district_id = ANY(:ids)"),
                {"ids": done_ids or [""]}).mappings():
            rows_by_did.setdefault(r["district_id"], []).append(dict(r))

    districts, sources = [], Counter()
    for d in batch["districts"]:
        did = d["district_id"]
        row = {"district_id": did, "name": d["name"], "state": d.get("state", ""),
               "domain": d.get("domain", ""), "outcome": None, "n_docs": 0, "n_usable": 0,
               "n_not_usable": 0}
        if did not in ondisk:
            districts.append({**row, "status": "awaiting_discovery"})
            continue
        if cand_n.get(did, 0) == 0:          # discovered, no links -> terminal manual_flag_all
            districts.append({**row, "status": "manual_flag_all", "outcome": "manual_flag_all"})
            continue
        if did not in captured:              # has links but not captured yet -> Stage 3 still owes it
            districts.append({**row, "status": "awaiting_capture"})
            continue
        if did not in processed:
            if did in failed_procs:          # process errored -> failed (retriable), not todo
                districts.append({**row, "status": "failed", "outcome": "failed",
                                  "error": (failed_procs[did] or "")[:300]})
            else:
                districts.append({**row, "status": "todo"})
            continue
        docs = rows_by_did.get(did, [])
        n_usable = sum(1 for c in docs if c["usable"])
        # Same three-way rollup shape as compute_outcome(): zero docs (all captures were ok:false) reads
        # as no_usable_text_any, matching process_stage4.
        outcome = ("no_usable_text_any" if n_usable == 0 else
                   "processed_all" if n_usable == len(docs) else "processed_partial")
        for src in winning_sources(ondisk[did]["dir"]):
            sources[src] += 1
        districts.append({**row, "status": "done", "outcome": outcome, "n_docs": len(docs),
                          "n_usable": n_usable, "n_not_usable": len(docs) - n_usable})

    return {"districts": districts, "rollup": _rollup(districts), "sources": sources.most_common()}


def _rollup(districts: list) -> dict:
    done = [d for d in districts if d["status"] == "done"]
    flagged = sum(1 for d in districts if d["status"] == "manual_flag_all")
    total = len(districts)
    return {
        "total": total,
        "done": len(done),
        "manual_flag_all": flagged,
        "todo": sum(1 for d in districts if d["status"] == "todo"),
        # process failures — retriable; NOT counted as resolved
        "failed": sum(1 for d in districts if d["status"] == "failed"),
        "awaiting_capture": sum(1 for d in districts if d["status"] == "awaiting_capture"),
        "awaiting_discovery": sum(1 for d in districts if d["status"] == "awaiting_discovery"),
        # resolved = processed OR terminally flagged; the batch's Stage-4 is complete when resolved==total
        "resolved": len(done) + flagged,
        "processed_all": sum(1 for d in done if d["outcome"] == "processed_all"),
        "processed_partial": sum(1 for d in done if d["outcome"] == "processed_partial"),
        "no_usable_text_any": sum(1 for d in done if d["outcome"] == "no_usable_text_any"),
        "n_docs": sum(d["n_docs"] for d in done),
        "n_usable": sum(d["n_usable"] for d in done),
        "n_not_usable": sum(d["n_not_usable"] for d in done),
    }


# ----------------------------------------------------------------------------------- the batch run
def run_batch(batch: dict, *, actor: str = "auto:stage4", on_event=None) -> dict:
    """Deterministic Stage 4 (Process) for a batch: reconcile (filesystem is truth; a
    registry-ahead-of-disk CONTROL FAILURE -- or a captures.json file-existence mismatch -- raises
    SystemExit and halts), then per todo district run the local harvesters IN-PROCESS via
    `C4.finish_district` (process records -> write processed.json -> state_event + DB cache upsert).
    SEQUENTIAL (one registry writer, no race). `on_event(kind, payload)` feeds the console job board.

    Unlike Stage 2/3 there is no injectable `_run`: the work is plain in-process Python, so tests drive
    `run_batch` against real (tiny) on-disk captures rather than a fake subprocess.

    `batch` is the resolved working-store dict ({batch_id, districts:[{district_id,name,state,...}]}) —
    the caller passes it from the DB (the console) or the receipt (the CLI)."""
    batch_id = batch["batch_id"]

    def emit(kind, **payload):
        if on_event:
            on_event(kind, {"batch_id": batch_id, **payload})

    districts = find_batch_districts(batch)
    registry = DS.load()
    # Filesystem truth. Registry-ahead-of-disk = CONTROL FAILURE -> SystemExit (unchanged);
    # a captures.json/disk mismatch quarantines JUST that district (#78) -- recorded as a
    # `failed` process event (so status shows it, retriable after investigation) with a
    # distinct `inconsistent` outcome in the results, while the rest of the batch runs.
    todo, skipped, quarantined = C4.reconcile(districts, registry)
    results = []
    for q in quarantined:
        problems = "; ".join(q.get("inconsistency") or [])
        DS.record_stage(registry, q["district_id"], q["name"], q["state"], stage_name="process",
                        event_type="failed", actor=actor, batch_id=batch_id,
                        notes=f"inconsistent: {problems[:200]}")
        results.append({"district_id": q["district_id"], "name": q["name"],
                        "outcome": "inconsistent", "error": problems[:200]})
        emit("failed", district_id=q["district_id"], name=q["name"],
             error=f"inconsistent: {problems[:200]}")
    DS.save(registry)
    emit("reconciled", todo=[d["district_id"] for d in todo],
         skipped=[d["district_id"] for d in skipped],
         quarantined=[d["district_id"] for d in quarantined])
    if not todo:
        return {"batch_id": batch_id, "todo": 0, "skipped": len(skipped), "results": results}

    registry = DS.load()
    for d in todo:
        DS.record_stage(registry, d["district_id"], d["name"], d["state"], stage_name="process",
                        event_type="dispatched", actor=actor, batch_id=batch_id)
        emit("dispatched", district_id=d["district_id"], name=d["name"])
    DS.save(registry)

    for d in todo:
        did = d["district_id"]
        try:
            registry = DS.load()
            outcome = C4.finish_district(d, registry)   # in-process work + processed.json + DB cache
            DS.save(registry)
            results.append({"district_id": did, "name": d["name"], "outcome": outcome})
            emit("completed", district_id=did, name=d["name"], outcome=outcome)
        except SystemExit:
            raise   # CONTROL FAILURE -- never swallow
        except Exception as e:
            registry = DS.load()
            DS.record_stage(registry, did, d["name"], d["state"], stage_name="process",
                            event_type="failed", actor=actor, batch_id=batch_id,
                            notes=f"{type(e).__name__}: {str(e)[:200]}")
            DS.save(registry)
            results.append({"district_id": did, "name": d["name"], "outcome": "error",
                            "error": f"{type(e).__name__}: {str(e)[:200]}"})
            emit("failed", district_id=did, name=d["name"], error=str(e)[:200])
    return {"batch_id": batch_id, "todo": len(todo), "skipped": len(skipped), "results": results}


def main():
    ap = argparse.ArgumentParser(description="Stage 4 (Process) batch runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="process an approved+captured batch (in-process local harvesters)")
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
