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
from infrastructure.acquisition.stage7_extract import validate as VALID
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
def _group_reps_by_district(plan: list) -> dict:
    """Collapse the flat voter plan to rep-groups (one per district/rec_key/file/kind/council with
    its voters + per-model prompt ids), then bucket BY DISTRICT — so a run can process one district
    fully and persist it before touching the next (durability, §incremental)."""
    groups = {}
    for p in plan:
        k = (p["district_id"], p["rec_key"], p["file"], p["kind"], p["council_id"])
        g = groups.setdefault(k, {"voters": [], "prompt_ids": {}})
        g["voters"].append(p["model"])
        g["prompt_ids"][p["model"]] = p["prompt_id"]
    by_did = {}
    for (did, rec_key, file, kind, cid), g in groups.items():
        by_did.setdefault(did, []).append(
            {"rec_key": rec_key, "file": file, "kind": kind, "council_id": cid,
             "voters": g["voters"], "prompt_ids": g["prompt_ids"]})
    return by_did


def _run_district(did: str, name: str, rep_groups: list, councils: dict, ddir, use_judge: bool) -> dict:
    """Run the full council over ONE district's reps and return its result dict (reps + per-model
    call detail, pooled accepted/unresolved facts, modal bands, telemetry). All the paid calls for a
    district happen here so the caller can persist it as a unit."""
    pd = {"district_id": did, "name": name, "reps": [], "accepted": [], "unresolved": [],
          "n_reps": 0, "n_judged": 0}
    n_total = len(rep_groups)
    for i, rg in enumerate(rep_groups, 1):
        rec_key, file, kind, cid = rg["rec_key"], rg["file"], rg["kind"], rg["council_id"]
        content = resolve_content(ddir, rec_key, file, kind)
        cfg = councils.get(cid) or {}
        model_rows, calls = {}, []
        for model in rg["voters"]:
            res = _call(model, rg["prompt_ids"][model], kind, content)
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

        for f in accepted:      # provenance: the rep each fact came from (consensus runs per rep)
            f["rec_key"], f["source_file"] = rec_key, file
        for u in unresolved:
            u["rec_key"], u["source_file"] = rec_key, file

        pd["reps"].append({"rec_key": rec_key, "file": file, "kind": kind, "council_id": cid,
                           "judged": judged, "calls": calls,
                           "accepted": accepted, "unresolved": unresolved})
        pd["accepted"].extend(accepted)
        pd["unresolved"].extend(unresolved)
        pd["n_reps"] += 1
        pd["n_judged"] += 1 if judged else 0

        # Per-rep progress line (Ian, 2026-07-03): inside a big district (Baldwin = 12 reps) the
        # [done] line can be many silent minutes away — if a run snags, the last [rep] line says
        # exactly where. Pure print; the durability/resume boundary stays the district.
        rep_cost = sum((c["cost_usd"] or 0.0) for c in calls)
        rep_errs = sum(1 for c in calls if not c["ok"])
        rep_trunc = sum(1 for c in calls if c.get("finish_reason") == "length")
        line = (f"  [rep {i}/{n_total}] {did} {file[:28]:28s} ({kind}->{cid}) "
                f"acc={len(accepted)} unres={len(unresolved)}"
                f"{' judged' if judged else ''} err={rep_errs} ${rep_cost:.4f}")
        if rep_trunc:
            line += f"  ⚠ {rep_trunc} TRUNCATED"
        print(line, flush=True)

    pd["bands"] = AGG.district_bands_from_facts(pd["accepted"])
    pd["telemetry"] = _rollup_tel(pd["reps"])
    return pd


def _call(model: str, prompt_id: str, kind: str, content) -> "OR.CallResult":
    return OR.call(R6.build_request({"model": model, "prompt_id": prompt_id, "kind": kind}, content))


def _call_record(model: str, role: str, res, facts: list) -> dict:
    """One model call's audit row for the receipt/gate@7 — telemetry + what it read (no raw content).
    `finish_reason == "length"` marks a TRUNCATED reply (tail schools silently gone — the salvage
    parser keeps only the head), surfaced through the telemetry rollup + progress line."""
    return {"model": model, "role": role, "ok": res.ok, "error": res.error, "n_facts": len(facts),
            "facts": facts, "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens, "cost_usd": res.cost_usd,
            "latency_ms": res.latency_ms, "finish_reason": res.finish_reason,
            "generation_id": res.generation_id}


def _rollup_tel(reps: list) -> dict:
    """Sum per-call telemetry across a set of reps (per-district or global)."""
    t = {"calls": 0, "judge_calls": 0, "errors": 0, "truncated": 0, "prompt_tokens": 0,
         "completion_tokens": 0, "cost_usd": 0.0}
    for rep in reps:
        for c in rep["calls"]:
            t["calls"] += 1
            t["prompt_tokens"] += c["prompt_tokens"]
            t["completion_tokens"] += c["completion_tokens"]
            t["cost_usd"] += (c["cost_usd"] or 0.0)
            if not c["ok"]:
                t["errors"] += 1
            if c.get("finish_reason") == "length":
                t["truncated"] += 1
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
    """Batch (in-memory) run over an already-loaded handoff doc — collect ALL districts, no persist.
    Kept for tests + the image-variant probe. For real runs prefer `run_council_streaming` (persists
    + streams per district so a mid-run failure keeps completed work). Both share `_run_district`."""
    councils = doc.get("councils") or {}
    by_district = _group_reps_by_district(R6.plan_requests(doc))
    ddirs = district_dirs(by_district.keys())
    _require_key()
    districts = {did: _run_district(did, _district_name(doc, did), rg, councils, ddirs.get(did), use_judge)
                 for did, rg in by_district.items()}
    all_reps = [rep for pd in districts.values() for rep in pd["reps"]]
    return {"handoff_hash": doc.get("handoff_hash"), "districts": districts,
            "telemetry": _rollup_tel(all_reps)}


def run_council_streaming(doc: dict, *, use_judge: bool = True, persist: bool = False,
                          gt_data: dict = None, created_by: str = "auto:stage7", resume: bool = True,
                          on_district=None) -> dict:
    """The DURABLE, RESUMABLE run: process ONE district at a time and, if `persist`, commit it
    immediately (its extraction + school_fact rows + state_event + a per-district receipt) before
    the next — so a crash / network drop / OpenRouter outage at district N keeps districts 1..N-1
    and a re-run skips them (`resume` — query `extraction` for this handoff_hash). Streams a
    per-district progress line (+ a mini GT scorecard when `gt_data` is given). Returns the
    THIS-SESSION results (skipped districts are already durable in the DB, not re-collected)."""
    councils = doc.get("councils") or {}
    by_district = _group_reps_by_district(R6.plan_requests(doc))
    ddirs = district_dirs(by_district.keys())
    _require_key()
    hh = doc.get("handoff_hash")

    done = set()
    if persist:
        gdb.init_precious_schema()
        if resume:
            done = _already_extracted(hh)

    results = {"handoff_hash": hh, "districts": {}}
    for did in sorted(by_district):
        if did in done:
            print(f"[skip]  {did} — already extracted for handoff {hh}", flush=True)
            continue
        pd = _run_district(did, _district_name(doc, did), by_district[did], councils,
                           ddirs.get(did), use_judge)
        results["districts"][did] = pd
        if persist:
            rp = write_district_receipt(pd, hh)
            with gdb.session_scope() as s:
                persist_run_session(s, {"handoff_hash": hh, "districts": {did: pd}},
                                    created_by=created_by, receipt_path=rp)
        _print_district_progress(did, pd, gt_data)
        if on_district:
            on_district(did, pd)

    if persist:
        try:   # refresh the git-swept backup ONCE at the end (per-district would re-dump 24×)
            with gdb.session_scope() as s:
                DS.export_status(s)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] district_status.json backup refresh failed ({type(e).__name__}: {e})")

    results["telemetry"] = _rollup_tel(
        [rep for pd in results["districts"].values() for rep in pd["reps"]])
    return results


def _pick_png(capture_dir: Path, *, preferred: str = "raster_p-1.png"):
    """The best in-store PNG for a capture — `raster_p-1.png` (Stage-4's rasterized-PDF-page
    rep) if present, else any other `.png` (e.g. a native image capture's `original.png`).
    Deliberately PNG-only: never `.webp`/`.jpg`/`.jpeg` (Ian, 2026-07-03 — the pipeline doesn't
    produce webp; jpg/jpeg-only captures are excluded from the image pathway, not converted)."""
    pref = capture_dir / preferred
    if pref.exists():
        return pref.name
    pngs = sorted(capture_dir.glob("*.png")) if capture_dir.exists() else []
    return pngs[0].name if pngs else None


def image_handoff_variant(doc: dict, *, council_id: str = "image") -> dict:
    """Rewrite a text handoff so each record routes its best in-store PNG (`_pick_png` — Stage 4's
    rasterized page, or a native PNG capture) to the VISION `image` council — a text-vs-vision
    comparison on the SAME documents. Records with no PNG on disk (jpg/jpeg/webp-only captures)
    are dropped, never converted. NOT a production dispatch (it bypasses release/routing) — a
    controlled probe of the vision path; a real image dispatch comes from routing on
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
            capdir = (paths.RAW_CAPTURES / ddir / "captures" / h) if ddir else None
            png = _pick_png(capdir) if capdir else None
            if png:
                rec = copy.deepcopy(rec)
                rec["reps"] = [{"file": png, "kind": "image", "councils": [council_id],
                                "fidelity_suspect": False, "route_reason": "image-test-override"}]
                recs.append(rec)
        if recs:
            d = copy.deepcopy(d)
            d["records"] = recs
            kept.append(d)
    v["districts"] = kept
    # Distinct handoff_hash (Ian, 2026-07-03): the variant is a materially different package
    # (different reps/council) from the text handoff it was built from — sharing the hash would
    # make run_council_streaming's resume check see the text run's extraction rows and SKIP every
    # district on the image pass, wrongly treating it as already done. Suffixed, not re-derived, so
    # the lineage (which text handoff this probe came from) stays legible in the DB/receipts.
    base_hash = v.get("handoff_hash")
    if base_hash:
        v["handoff_hash"] = f"{base_hash}-{council_id}"
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


def write_district_receipt(pd: dict, handoff_hash: str, *, root=None) -> str:
    """One district's run as an immutable receipt (`extraction_<hash>_<did>_<ts>.json`), written the
    moment the district completes — durable independent of the rest of the batch (the streaming path)."""
    d = Path(root) if root else (paths.ACQUISITION / "extractions")
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"extraction_{handoff_hash or 'nohash'}_{pd['district_id']}_{_fs_ts()}.json"
    path.write_text(json.dumps({"handoff_hash": handoff_hash, "district": pd}, indent=2))
    return str(path)


def _already_extracted(handoff_hash: str) -> set:
    """District ids already persisted for this handoff (the resume skip-set). Schema must exist."""
    with gdb.session_scope() as s:
        return {r[0] for r in s.execute(
            text("SELECT DISTINCT district_id FROM extraction WHERE handoff_hash = :h"),
            {"h": handoff_hash or ""})}


def _print_district_progress(did: str, pd: dict, gt_data: dict = None) -> None:
    tel = pd.get("telemetry") or {}
    bands = pd.get("bands") or {}
    band_str = " ".join(f"{b[0].upper()}={v['gross_minutes']}" for b, v in bands.items()) or "(none)"
    line = (f"[done]  {did} {pd['name'][:22]:22s} reps={pd['n_reps']:2d} "
            f"acc={len(pd['accepted']):2d} unres={len(pd['unresolved']):2d} "
            f"err={tel.get('errors', 0)} ${tel.get('cost_usd', 0):.4f} | {band_str}")
    if tel.get("truncated"):
        line += f"  ⚠ {tel['truncated']} TRUNCATED reply(s) — raise max_tokens / check tail loss"
    if gt_data and did in gt_data:
        card = VALID.score_district(pd, gt_data[did])
        hit = sum(1 for b in card["bands"] if b["status"] == "hit")
        cmp = sum(1 for b in card["bands"] if b["status"] in ("hit", "miss"))
        gap = sum(1 for b in card["bands"] if b["status"] == "gap")
        line += f"  || GT bands {hit}/{cmp} hit, {gap} gap"
    print(line, flush=True)


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
# Slice 4 — GT scoring (batch_00000)
# ---------------------------------------------------------------------------
def default_gt_path():
    """The newest curated `gt_proposals.json` under data/benchmark/gt_curation_*/ (or None)."""
    import glob
    hits = sorted(glob.glob(str(paths.DATA_ROOT / "benchmark" / "gt_curation_*" / "gt_proposals.json")))
    return hits[-1] if hits else None


def _print_scorecard(card_run: dict) -> None:
    marks = {"hit": "HIT ", "miss": "MISS", "gap": "gap ", "extra": "xtra", "neither": "  - "}
    print("\n=== GT SCORECARD (±%d min) ===" % VALID.TOL)
    for c in card_run["cards"]:
        print(f"  {c['district_id']}")
        for b in c["bands"]:
            if b["status"] == "neither":
                continue
            print(f"     {marks[b['status']]}  {b['band']:10s} ours={b['our']} gt={b['gt']}")
        for s in c["schools"]:
            if not s["matched"]:
                continue
            print(f"        {'HIT ' if s['hit'] else 'MISS'}  {s['band'][:4]}/{s['school'][:24]:24s} "
                  f"ours={s['our']} gt={s['gt']}")
    b, s = card_run["bands"], card_run["schools"]
    print(f"\n  BANDS:   {b['hit']}/{b['compared']} hit = {b['pct']}%  "
          f"(+{b['gap']} coverage gaps, {b['extra']} extra bands vs GT)")
    print(f"  SCHOOLS: {s['hit']}/{s['matched']} matched-hit = {s['pct']}%  "
          f"({s['matched']}/{s['total']} of our accepted schools matched a GT school)")


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
    ap.add_argument("--validate", action="store_true",
                    help="council/image: score the run vs the curated GT (gt_proposals.json)")
    ap.add_argument("--gt", default=None, help="path to gt_proposals.json (default: newest gt_curation)")
    ap.add_argument("--no-resume", action="store_true",
                    help="council/image + persist: re-run districts already extracted for this handoff")
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

    doc = load_handoff(args.handoff)
    if args.mode == "image":
        doc = image_handoff_variant(doc)
    gt_data = None
    if args.validate:
        gt_path = args.gt or default_gt_path()
        if not gt_path:
            raise SystemExit("no GT found — pass --gt <gt_proposals.json>")
        gt_data = VALID.load_gt(gt_path)

    # The streaming/resumable path: each district is persisted + printed as it finishes, so a
    # mid-run failure keeps completed districts and a re-run skips them.
    print(f"Running {sum(len(v) for v in _group_reps_by_district(R6.plan_requests(doc)).values())} "
          f"reps across {len(doc.get('districts', []))} districts "
          f"(mode={args.mode}, persist={args.persist}, resume={not args.no_resume})...", flush=True)
    out = run_council_streaming(doc, use_judge=not args.no_judge, persist=args.persist,
                                gt_data=gt_data, created_by="ian:batch0-stage7-dev",
                                resume=not args.no_resume)
    _print_council(out)
    if gt_data:
        _print_scorecard(VALID.score_run(out, gt_data))


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
          f"${tel['cost_usd']:.4f}, {tel['errors']} errors, "
          f"{tel.get('truncated', 0)} truncated")


if __name__ == "__main__":
    main()
