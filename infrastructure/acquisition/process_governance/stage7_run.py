"""Stage 7 run — the app-layer glue that executes a frozen handoff's paid council calls (REQ-117).

Mirrors `stage6_dispatch.py`: this is an APP-layer module, so it is the one place allowed to import
across stages — Stage 6's request assembly (`stage6_handoff.requests`/`prompts`) and Stage 8's
consensus (`stage8_aggregate.aggregate`) — plus the Stage-7 client (`stage7_extract`). The stage
packages themselves stay independent (import-linter). It reads the immutable handoff, resolves each
sent rep's content off disk (`RAW_CAPTURES/<district_dir>/captures/<hash>/<file>` — the same
resolver gate@6's `inspect` uses), drives the paid calls, and runs the council.

Slices present:
  - `run_plumbing()` (slice 1): the first N planned VOTER calls, parsed facts + telemetry — a
    single-call proof the whole path works.
  - `run_council()` (slice 2): per rep, both voters → cross-family consensus
    (`aggregate.consensus_school_facts`) → judge-on-disagreement (the council's 3rd-family model
    re-reads the same page) → per-district modal bands (`aggregate.district_bands_from_facts`).
Storage, state events, gate@7, and GT scoring come in later slices.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import prompts as P6
from infrastructure.acquisition.stage6_handoff import requests as R6
from infrastructure.acquisition.stage7_extract import content as CONTENT
from infrastructure.acquisition.stage7_extract import models as M7
from infrastructure.acquisition.stage7_extract import openrouter as OR
from infrastructure.acquisition.stage7_extract import parse as PARSE
from infrastructure.acquisition.stage8_aggregate import aggregate as AGG


def load_handoff(path) -> dict:
    """Read a frozen handoff doc (`data/acquisition/handoffs/handoff_<hash>_<ts>.json`)."""
    return json.loads(Path(path).read_text())


def resolve_content(district_dir: str, rec_key: str, file: str, kind: str = "text"):
    """The rep's on-disk content (RAW_CAPTURES/<district_dir>/captures/<hash>/<file>). `hash` is the
    hex tail of `rec_key` — the same path gate@6's `inspect` serves. Text reps → the file text;
    image reps → a base64 data: URL for the vision council (`.webp`→`.png` normalized)."""
    h = rec_key.split(":", 1)[1]
    fp = paths.RAW_CAPTURES / district_dir / "captures" / h / file
    if CONTENT.is_image_kind(kind):
        return CONTENT.image_data_url(fp)
    return fp.read_text(errors="replace")


def district_dirs(district_ids) -> dict:
    """{district_id: district_dir} from the governance `district` table."""
    with gdb.session_scope() as s:
        rows = s.execute(
            text("SELECT district_id, district_dir FROM district WHERE district_id = ANY(:d)"),
            {"d": list(district_ids)}).all()
    return {r[0]: r[1] for r in rows}


def _require_key():
    if not OR.has_key():
        raise SystemExit("no OPENROUTER_API_KEY (env or config/secrets.local.json) — Stage 7 is paid; "
                         "set a key to run")


# ---------------------------------------------------------------------------
# Slice 1 — single-call plumbing
# ---------------------------------------------------------------------------
def run_plumbing(handoff_path, *, limit: int = 1) -> list[dict]:
    """SLICE 1: execute the first `limit` planned voter calls; return one record per call with the
    parsed schedules + telemetry. No persistence."""
    doc = load_handoff(handoff_path)
    plan = R6.plan_requests(doc)
    ddirs = district_dirs({p["district_id"] for p in plan})
    _require_key()
    out = []
    for planned in plan[:limit]:
        content = resolve_content(ddirs[planned["district_id"]], planned["rec_key"],
                                  planned["file"], planned["kind"])
        res = OR.call(R6.build_request(planned, content))
        facts = PARSE.parse_schedules(res.content)
        out.append({
            "district_id": planned["district_id"], "rec_key": planned["rec_key"],
            "file": planned["file"], "council_id": planned["council_id"], "model": planned["model"],
            "ok": res.ok, "error": res.error, "n_facts": len(facts), "facts": facts,
            "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
            "cost_usd": res.cost_usd, "latency_ms": res.latency_ms,
            "n_chars_in": len(content), "raw": res.content})
    return out


# ---------------------------------------------------------------------------
# Slice 2 — full council (2 voters → consensus → judge on disagreement) per rep
# ---------------------------------------------------------------------------
def _group_reps(plan: list) -> dict:
    """Collapse the flat voter plan into one entry per (district, rec_key, file, kind, council),
    carrying the voter models + their per-model prompt ids (the reps a council votes on together)."""
    groups = {}
    for p in plan:
        k = (p["district_id"], p["rec_key"], p["file"], p["kind"], p["council_id"])
        g = groups.setdefault(k, {"voters": [], "prompt_ids": {}})
        g["voters"].append(p["model"])
        g["prompt_ids"][p["model"]] = p["prompt_id"]
    return groups


def _call(model: str, prompt_id: str, kind: str, content) -> "OR.CallResult":
    return OR.call(R6.build_request({"model": model, "prompt_id": prompt_id, "kind": kind}, content))


def _call_record(model: str, role: str, res, facts: list) -> dict:
    """One model call's audit row for the receipt/gate@7 — telemetry + what it read (no raw content)."""
    return {"model": model, "role": role, "ok": res.ok, "error": res.error, "n_facts": len(facts),
            "facts": facts, "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens, "cost_usd": res.cost_usd,
            "latency_ms": res.latency_ms}


def _rollup_tel(reps: list) -> dict:
    """Sum per-call telemetry across a set of reps (per-district or global)."""
    t = {"calls": 0, "judge_calls": 0, "errors": 0, "prompt_tokens": 0,
         "completion_tokens": 0, "cost_usd": 0.0}
    for rep in reps:
        for c in rep["calls"]:
            t["calls"] += 1
            t["prompt_tokens"] += c["prompt_tokens"]
            t["completion_tokens"] += c["completion_tokens"]
            t["cost_usd"] += (c["cost_usd"] or 0.0)
            if not c["ok"]:
                t["errors"] += 1
            if c["role"] == "judge":
                t["judge_calls"] += 1
    return t


def run_council(handoff_path, *, use_judge: bool = True) -> dict:
    """SLICE 2: run the full council over every sent rep in the handoff.

    Per rep: call both voters, run cross-family per-school consensus
    (`aggregate.consensus_school_facts`); if any (band,school) is unresolved and the council has a
    judge, the judge (3rd family) re-reads the SAME page once and consensus is re-run with its rows.
    Per district: pool the accepted per-school facts across its reps and take the modal band value
    (`aggregate.district_bands_from_facts`). Returns {districts:{...}, telemetry:{...}}. No persist.

    Consensus keys `model_rows` by the full OpenRouter model id, matching the canonical family map
    (`common.model_families`, unified on full ids) that both `aggregate` and `councils` now share —
    so cross-family counting is correct here, not merely coincidental.
    """
    return run_council_doc(load_handoff(handoff_path), use_judge=use_judge)


def run_council_doc(doc: dict, *, use_judge: bool = True) -> dict:
    """`run_council` on an already-loaded handoff doc (so a variant — e.g. the image-routed probe
    below — can be fed directly without a file). Captures per-rep, per-model call detail so the run
    can be persisted (`persist_run`) and written as a gate@7 receipt (`write_receipt`)."""
    plan = R6.plan_requests(doc)
    councils = doc.get("councils") or {}
    ddirs = district_dirs({p["district_id"] for p in plan})
    _require_key()

    districts: dict = {}
    for (did, rec_key, file, kind, cid), g in _group_reps(plan).items():
        content = resolve_content(ddirs[did], rec_key, file, kind)
        cfg = councils.get(cid) or {}
        model_rows, calls = {}, []
        for model in g["voters"]:
            res = _call(model, g["prompt_ids"][model], kind, content)
            facts = PARSE.parse_schedules(res.content) if res.ok else []
            model_rows[model] = facts
            calls.append(_call_record(model, "voter", res, facts))

        accepted, unresolved = AGG.consensus_school_facts(model_rows)
        judged = False
        if use_judge and unresolved and cfg.get("judge"):
            jmodel = cfg["judge"]
            jres = _call(jmodel, P6.select_prompt_id(cfg, jmodel), kind, content)
            jfacts = PARSE.parse_schedules(jres.content) if jres.ok else []
            calls.append(_call_record(jmodel, "judge", jres, jfacts))
            accepted, unresolved = AGG.consensus_school_facts(model_rows, {jmodel: jfacts})
            judged = True

        # Tag each fact with the rep it came from (consensus runs per rep) — provenance for gate@7.
        for f in accepted:
            f["rec_key"], f["source_file"] = rec_key, file
        for u in unresolved:
            u["rec_key"], u["source_file"] = rec_key, file

        pd = districts.setdefault(did, {"district_id": did, "name": _district_name(doc, did),
                                        "reps": [], "accepted": [], "unresolved": [],
                                        "n_reps": 0, "n_judged": 0})
        pd["reps"].append({"rec_key": rec_key, "file": file, "kind": kind, "council_id": cid,
                           "judged": judged, "calls": calls,
                           "accepted": accepted, "unresolved": unresolved})
        pd["accepted"].extend(accepted)
        pd["unresolved"].extend(unresolved)
        pd["n_reps"] += 1
        pd["n_judged"] += 1 if judged else 0

    for pd in districts.values():
        pd["bands"] = AGG.district_bands_from_facts(pd["accepted"])
        pd["telemetry"] = _rollup_tel(pd["reps"])
    all_reps = [rep for pd in districts.values() for rep in pd["reps"]]
    return {"handoff_hash": doc.get("handoff_hash"), "districts": districts,
            "telemetry": _rollup_tel(all_reps)}


def image_handoff_variant(doc: dict, *, image_file: str = "raster_p-1.png",
                          council_id: str = "image") -> dict:
    """DEV/TEST probe (Ian, 2026-07-02): rewrite a text handoff so each record routes its
    in-store rasterized page image (`raster_p-1.png`, produced by Stage 4) to the VISION `image`
    council — a text-vs-vision comparison on the SAME documents. Records whose image isn't on disk
    are dropped. NOT a production dispatch (it bypasses release/routing) — a controlled probe of the
    vision path the user asked to exercise; a real image dispatch comes from routing on
    `visual_text_gap`/`needs_vision`."""
    import copy
    v = copy.deepcopy(doc)
    v.setdefault("councils", {})[council_id] = C6.load_configs()[council_id]
    ddirs = district_dirs({d["district_id"] for d in v["districts"]})
    kept = []
    for d in v["districts"]:
        ddir = ddirs.get(d["district_id"])
        recs = []
        for rec in d["records"]:
            h = rec["rec_key"].split(":", 1)[1]
            fp = (paths.RAW_CAPTURES / ddir / "captures" / h / image_file) if ddir else None
            if fp and fp.exists():
                rec = copy.deepcopy(rec)
                rec["reps"] = [{"file": image_file, "kind": "image", "councils": [council_id],
                                "fidelity_suspect": False, "route_reason": "image-test-override"}]
                recs.append(rec)
        if recs:
            d = copy.deepcopy(d)
            d["records"] = recs
            kept.append(d)
    v["districts"] = kept
    return v


def _district_name(doc: dict, did: str) -> str:
    for d in doc.get("districts", []):
        if d.get("district_id") == did:
            return d.get("name", "")
    return ""


# ---------------------------------------------------------------------------
# Slice 3 — receipt (disk) + governance persistence (DB, never the LCT DB)
# ---------------------------------------------------------------------------
def _fs_ts() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_receipt(results: dict, *, root=None) -> str:
    """Write the full run — per-rep, per-model detail incl. what each model read — as the auditable
    on-disk receipt (the DB holds the queryable per-school facts; disk holds the audit trail,
    governance §1). Returns the path."""
    hh = results.get("handoff_hash") or "nohash"
    d = Path(root) if root else (paths.ACQUISITION / "extractions")
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"extraction_{hh}_{_fs_ts()}.json"
    path.write_text(json.dumps(results, indent=2))
    return str(path)


def persist_run_session(s, results: dict, *, created_by: str = "auto:stage7",
                        receipt_path=None) -> dict:
    """The DB writes for one Stage-7 run on a GIVEN session (no commit — the caller's transaction
    owns it, so this is unit-testable under the rollback fixture). Per district: one `extraction`
    row (telemetry rollup + receipt pointer) + its `school_fact` rows (accepted + unresolved) + a
    `stage=7` `extracted` state_event (furthest_stage -> 7). Returns a summary."""
    hh = results.get("handoff_hash")
    summary = {"handoff_hash": hh, "districts": [], "n_facts": 0}
    for did, pd in results["districts"].items():
        tel = pd.get("telemetry") or {}
        ex = M7.Extraction(
            handoff_hash=hh or "", district_id=did, created_by=created_by,
            n_reps=pd.get("n_reps", 0), n_calls=tel.get("calls", 0),
            n_judge_calls=tel.get("judge_calls", 0), n_errors=tel.get("errors", 0),
            prompt_tokens=tel.get("prompt_tokens", 0),
            completion_tokens=tel.get("completion_tokens", 0), cost_usd=tel.get("cost_usd", 0.0),
            n_accepted=len(pd["accepted"]), n_unresolved=len(pd["unresolved"]),
            receipt_path=receipt_path)
        s.add(ex)
        s.flush()   # assign extraction_id
        for f in pd["accepted"]:
            s.add(M7.SchoolFact(
                extraction_id=ex.extraction_id, district_id=did, band=f["band"],
                school=f["school"], status="accepted", start_time=f["start"], end_time=f["end"],
                gross_minutes=f["gross"], method=f["method"],
                models_json=json.dumps(f.get("models") or []),
                rec_key=f.get("rec_key"), source_file=f.get("source_file")))
        for u in pd["unresolved"]:
            s.add(M7.SchoolFact(
                extraction_id=ex.extraction_id, district_id=did, band=u.get("band", ""),
                school=u.get("school", ""), status="unresolved", gross_minutes=u.get("gross"),
                method=u.get("reason", "disagree"),
                detail_json=json.dumps({k: u[k] for k in ("starts", "ends", "gross") if k in u}),
                rec_key=u.get("rec_key"), source_file=u.get("source_file")))
        s.execute(DS.INSERT_STATE_EVENT, {
            "district_id": did, "name": pd.get("name", ""), "state": None, "stage": 7,
            "stage_name": "extract", "checkpoint": None, "event_type": "extracted",
            "outcome": "extracted", "topology": None, "batch_id": None,
            "fingerprints_json": None, "actor": created_by, "note": hh,
            "created_at": M7.utcnow()})
        summary["districts"].append(
            {"district_id": did, "extraction_id": ex.extraction_id,
             "n_accepted": len(pd["accepted"]), "n_unresolved": len(pd["unresolved"])})
        summary["n_facts"] += len(pd["accepted"]) + len(pd["unresolved"])
    return summary


def persist_run(results: dict, *, created_by: str = "auto:stage7", receipt_path=None) -> dict:
    """Standalone entry: ensure the precious schema (never the LCT DB — benchmark stays walled off,
    Stage 9 is the only LCT promoter), open a session (commit on success), persist. Append-only —
    a re-run is a new extraction row, history preserved. Returns the summary."""
    gdb.init_precious_schema()   # M7 imported at module top → extraction/school_fact register + create
    with gdb.session_scope() as s:
        summary = persist_run_session(s, results, created_by=created_by, receipt_path=receipt_path)
    # Refresh the git-swept state_event backup so the stage=7 events survive a DB loss (best-effort,
    # after the commit — the DB is authoritative; mirrors stage6_dispatch's post-write export).
    try:
        with gdb.session_scope() as s:
            DS.export_status(s)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] district_status.json backup refresh failed after persist "
              f"({type(e).__name__}: {e}); the DB is authoritative — re-export later")
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Stage 7 run (slice 1 plumbing / slice 2 council)")
    ap.add_argument("handoff", help="path to a frozen handoff_<hash>_<ts>.json")
    ap.add_argument("--mode", choices=["plumbing", "council", "image"], default="council")
    ap.add_argument("--limit", type=int, default=1, help="plumbing mode: number of voter calls")
    ap.add_argument("--no-judge", action="store_true", help="skip judge escalation")
    ap.add_argument("--persist", action="store_true",
                    help="council/image: write the receipt + persist facts to the governance DB")
    args = ap.parse_args()

    if args.mode == "plumbing":
        for r in run_plumbing(args.handoff, limit=args.limit):
            print(f"\n=== {r['district_id']} {r['model']} ({r['council_id']}) ok={r['ok']} "
                  f"{r['latency_ms']}ms in={r['prompt_tokens']} out={r['completion_tokens']} "
                  f"cost={r['cost_usd']} ===")
            if r["error"]:
                print("  ERROR:", r["error"])
            for f in r["facts"]:
                print(f"    - {f.get('grade_level','?'):10s} {f.get('start_time','?')}-"
                      f"{f.get('end_time','?')} {f.get('school_name','?')}")
        return

    if args.mode == "image":
        doc = image_handoff_variant(load_handoff(args.handoff))
        out = run_council_doc(doc, use_judge=not args.no_judge)
    else:
        out = run_council(args.handoff, use_judge=not args.no_judge)
    _print_council(out)

    if args.persist:
        rp = write_receipt(out)
        summ = persist_run(out, created_by="ian:batch0-stage7-dev", receipt_path=rp)
        print(f"\nPERSISTED to governance DB (receipt: {rp}):")
        for d in summ["districts"]:
            print(f"  extraction #{d['extraction_id']} {d['district_id']}: "
                  f"{d['n_accepted']} accepted, {d['n_unresolved']} unresolved")


def _print_council(out: dict) -> None:
    tel = out["telemetry"]
    for did, pd in out["districts"].items():
        print(f"\n=== {did} {pd['name']} — {pd['n_reps']} reps, {pd['n_judged']} judged, "
              f"{len(pd['accepted'])} schools accepted, {len(pd['unresolved'])} unresolved ===")
        for band, b in pd["bands"].items():
            print(f"  {band:10s} {b['gross_minutes']:>3} min ({b['start_time']}-{b['end_time']}) "
                  f"n={b['n_schools']} [{b['method']}]")
        for u in pd["unresolved"]:
            print(f"    UNRESOLVED {u.get('band')}/{u.get('school')} {u.get('reason','disagree')}")
    print(f"\nTELEMETRY: {tel['calls']} calls ({tel['judge_calls']} judge), "
          f"{tel['prompt_tokens']}+{tel['completion_tokens']} tok, "
          f"${tel['cost_usd']:.4f}, {tel['errors']} errors")


if __name__ == "__main__":
    main()
