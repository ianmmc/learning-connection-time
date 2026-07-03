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
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import prompts as P6
from infrastructure.acquisition.stage6_handoff import requests as R6
from infrastructure.acquisition.stage7_extract import content as CONTENT
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


def _acc_telemetry(tel: dict, res) -> None:
    tel["calls"] += 1
    tel["prompt_tokens"] += res.prompt_tokens
    tel["completion_tokens"] += res.completion_tokens
    tel["cost_usd"] += (res.cost_usd or 0.0)
    if not res.ok:
        tel["errors"] += 1


def _call(model: str, prompt_id: str, kind: str, content) -> "OR.CallResult":
    return OR.call(R6.build_request({"model": model, "prompt_id": prompt_id, "kind": kind}, content))


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
    below — can be fed directly without a file)."""
    plan = R6.plan_requests(doc)
    councils = doc.get("councils") or {}
    ddirs = district_dirs({p["district_id"] for p in plan})
    _require_key()

    tel = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0,
           "errors": 0, "judge_calls": 0}
    districts: dict = {}

    for (did, rec_key, file, kind, cid), g in _group_reps(plan).items():
        content = resolve_content(ddirs[did], rec_key, file, kind)
        cfg = councils.get(cid) or {}
        model_rows = {}
        for model in g["voters"]:
            res = _call(model, g["prompt_ids"][model], kind, content)
            _acc_telemetry(tel, res)
            model_rows[model] = PARSE.parse_schedules(res.content) if res.ok else []

        accepted, unresolved = AGG.consensus_school_facts(model_rows)
        judged = False
        if use_judge and unresolved and cfg.get("judge"):
            jmodel = cfg["judge"]
            jres = _call(jmodel, P6.select_prompt_id(cfg, jmodel), kind, content)
            _acc_telemetry(tel, jres)
            tel["judge_calls"] += 1
            judge_rows = {jmodel: PARSE.parse_schedules(jres.content) if jres.ok else []}
            accepted, unresolved = AGG.consensus_school_facts(model_rows, judge_rows)
            judged = True

        pd = districts.setdefault(did, {"district_id": did, "name": _district_name(doc, did),
                                        "accepted": [], "unresolved": [], "n_reps": 0, "n_judged": 0})
        pd["accepted"].extend(accepted)
        pd["unresolved"].extend(unresolved)
        pd["n_reps"] += 1
        pd["n_judged"] += 1 if judged else 0

    for pd in districts.values():
        pd["bands"] = AGG.district_bands_from_facts(pd["accepted"])
    return {"districts": districts, "telemetry": tel}


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
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Stage 7 run (slice 1 plumbing / slice 2 council)")
    ap.add_argument("handoff", help="path to a frozen handoff_<hash>_<ts>.json")
    ap.add_argument("--mode", choices=["plumbing", "council", "image"], default="council")
    ap.add_argument("--limit", type=int, default=1, help="plumbing mode: number of voter calls")
    ap.add_argument("--no-judge", action="store_true", help="skip judge escalation")
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
