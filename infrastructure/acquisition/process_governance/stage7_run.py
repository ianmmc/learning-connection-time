"""Stage 7 run — the app-layer glue that executes a frozen handoff's paid council calls (REQ-117).

Mirrors `stage6_dispatch.py`: this is an APP-layer module, so it is the one place allowed to import
across stages — Stage 6's request assembly (`stage6_handoff.requests`/`prompts`) and Stage 8's
consensus (`stage8_aggregate.aggregate`) — plus the Stage-7 client (`stage7_extract`). The stage
packages themselves stay independent (import-linter). It reads the immutable handoff, resolves each
sent rep's content off disk (`RAW_CAPTURES/<district_dir>/captures/<hash>/<file>` — the same
resolver gate@6's `inspect` uses), drives the paid calls, and runs the council.

Entry points:
  - `run_plumbing()` (diagnostics): the first N planned VOTER calls, parsed facts + telemetry — a
    single-call proof the whole path works.
  - `run_council_streaming()` (THE production run): per rep, both voters → cross-family consensus
    (`aggregate.consensus_school_facts`) → judge-on-disagreement (the council's 3rd-family model
    re-reads the same page) → per-district modal bands (`aggregate.district_bands_from_facts`) —
    durable/resumable per-district persistence, REQ-051 budget-governed, image-council vision-checked.
    (The old unguarded batch entry points run_council/run_council_doc were deleted, issue #146 —
    they had no callers and bypassed the budget governor.)
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import budget as BUD
from infrastructure.acquisition.common import config_loader as CFG
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import model_families as MF
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common import receipts as RCPT
from infrastructure.acquisition.common import school_sampling as SS
from infrastructure.acquisition.common import timeutil as TU
from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.stage6_handoff import cost as COST6
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import prompts as P6
from infrastructure.acquisition.stage6_handoff import requests as R6
from infrastructure.acquisition.stage7_extract import content as CONTENT
from infrastructure.acquisition.stage7_extract import models as M7
from infrastructure.acquisition.stage7_extract import openrouter as OR
from infrastructure.acquisition.stage7_extract import parse as PARSE
from infrastructure.acquisition.stage7_extract import requests as RQ
from infrastructure.acquisition.stage7_extract import validate as VALID
from infrastructure.acquisition.stage8_aggregate import aggregate as AGG
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA8

# The exceptions that must propagate through BOTH isolation boundaries (per-rep in `_run_district`,
# per-district in `run_council_streaming`) and HALT the whole run rather than degrade to a skip (#189).
# Only BillingAuthError needs listing: SystemExit/KeyboardInterrupt are BaseException subclasses that a
# bare `except Exception` never catches anyway, so they already propagate unaided. One canonical tuple
# so a third halting type added later lands in a single place, not two divergent inline lists.
HALTING_EXCEPTIONS = (OR.BillingAuthError,)


def load_handoff(path) -> dict:
    """Read a frozen handoff doc (`data/acquisition/handoffs/handoff_<hash>_<ts>.json`)."""
    return json.loads(Path(path).read_text())


def resolve_content(district_dir: str, rec_key: str, file: str, kind: str = "text"):
    """The rep's on-disk content (RAW_CAPTURES/<district_dir>/captures/<hash>/<file>). `hash` is the
    hex tail of `rec_key` — the same path gate@6's `inspect` serves. Text reps → the file text;
    image reps → a base64 data: URL for the vision council (`.webp`→`.png` normalized).

    A `harvest_slice.txt` rep is a DERIVED artifact that was relocated OUT of the capture dir (the #58
    relocation), so joining the capture dir ourselves fails for every relocated slice. Resolve it
    through `build_signals.resolve_harvest_slice` (new-location-first, legacy fallback) — the same
    resolver gate@6's `inspect` uses — so the extraction read agrees with what the console serves."""
    h = rec_key.split(":", 1)[1]
    if file == BS.HARVEST_SLICE_FILE and not CONTENT.is_image_kind(kind):
        district_id = rec_key.split(":", 1)[0]
        slice_fp = BS.resolve_harvest_slice(district_id, district_dir, rec_key)
        if slice_fp is not None:
            return slice_fp.read_text(errors="replace")
        # neither location exists — fall through so the legacy path raises the same clear error
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
        res = OR.call(R6.build_request(planned, content),      # #180: size like the production path
                      max_tokens=OR.size_max_tokens(_content_n_times(planned["kind"], content)))
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


# ---------------------------------------------------------------------------
# #120 — the extraction-time mode-stability early-exit (district-grain, decision A: Ian 2026-07-15).
# The params are config-as-data (stage7_mode_stability.json — methodology, changed by PR); `enabled`
# is the one operational field the Settings toggle may flip (the kill-switch).
# ---------------------------------------------------------------------------
def load_mode_stability() -> dict:
    """The #120 knob's params. A missing/corrupt knob degrades to DISABLED — the full census is the
    always-safe posture; never guess parameters."""
    try:
        return dict(CFG.load("stage7_mode_stability")["params"])
    except Exception:  # noqa: BLE001 — degrade to the pre-#120 behavior, never crash a paid run
        return {"enabled": False}


def _bands_mode_stable(accepted: list, bands, p: dict) -> bool:
    """True when EVERY band in `bands` has a stable running mode over the accepted facts so far
    (arrival order — the order paid calls actually produced them). Empty/None `bands` is never
    stable: unknown targets must not vacuously exit after the first rep."""
    if not bands:
        return False
    for band in bands:
        vals = [f["gross"] for f in accepted if f.get("band") == band and f.get("gross") is not None]
        if not AGG.mode_stable(vals, window=p.get("window", 5), min_n=p.get("min_n", 3),
                               min_share=p.get("min_share", 0.6)):
            return False
    return True


def _early_exit_enabled(doc: dict, run_kind: str, gt_data, ms_params: dict) -> bool:
    """Is the #120 mode-stability early-exit live for THIS RUN? Every disabler here is a property of
    the run, read off the frozen handoff — a MEASUREMENT run wants the full census, because the
    shortcut would measure the shortcut (REQ-151).

    Three kinds of measurement, at one altitude: a probe (#148 — a council variant), a GT-scored run,
    and, since #619, a BENCHMARK dispatch (#618 — the Stages-6/7 A/B harness). The third replaced a
    per-district `batch_type='benchmark'` MEMBERSHIP check that could see none of them and answered
    permanently for a district instead; it is also the only form that can see a Council Lab A/B
    composed entirely of production reps, which carries no rep-level signal at all.

    RUN-WIDE only — this is arm 1. A handoff is stamped with ONE dispatch_type, so it cannot see the
    mixed case: a genuine production dispatch that pulled in a few `gt://` curated PDFs (the real
    `f33790e63820`, 3 reps across 3 of its 9 districts). Arm 2 is per-district and lives in
    `_drop_benchmark_provenance_districts`, applied to the targets this gate lets through (#653)."""
    return bool(ms_params.get("enabled")) and run_kind == "production" and gt_data is None \
        and not BM.is_benchmark_dispatch(doc)


def _drop_benchmark_provenance_districts(targets: dict, by_district: dict) -> dict:
    """ARM 2 of the early-exit disabler (#653): drop any district whose reps IN THIS RUN carry
    benchmark provenance, so it pays the full census REQ-151 asks of a measurement run.

    `_early_exit_enabled` reads the run's stamped `dispatch_type`, which is handoff-wide and so is
    blind to a production dispatch holding a few injected reps — precisely the case `common/benchmark`
    needed two arms for. Asked per district over the reps this run will actually send, which is the
    grain the shortcut is decided at.

    Degrades CONSERVATIVELY, unlike `_early_exit_targets`: a lookup failure here drops every district
    (full census, more paid calls) rather than leaving the shortcut on. The two degradations disagree
    on purpose — an absent target means "we don't know what to fill", an unknown provenance means
    "we might be measuring the shortcut", and only the second is a correctness risk."""
    if not targets:
        return targets
    keys_by_did = {did: [r["rec_key"] for r in by_district.get(did, []) if r.get("rec_key")]
                   for did in targets}
    all_keys = sorted({k for ks in keys_by_did.values() for k in ks})
    if not all_keys:
        return targets
    try:
        with gdb.session_scope() as s:
            flagged = BM.benchmark_provenance_rec_keys(s, all_keys)
    except Exception as e:  # noqa: BLE001 — unknown provenance ⇒ no shortcut (the safe direction)
        print(f"[mode-stability] provenance lookup failed ({type(e).__name__}: {str(e)[:80]}) — "
              f"early-exit disabled this run", flush=True)
        return {}
    if not flagged:
        return targets
    out = {did: bands for did, bands in targets.items()
           if not any(k in flagged for k in keys_by_did[did])}
    for did in sorted(set(targets) - set(out)):
        print(f"[mode-stability] {did} — benchmark-provenance rep(s) in this run; full census "
              f"(REQ-151, #653)", flush=True)
    return out


def _early_exit_targets(district_ids) -> dict:
    """{district_id: fillable target bands (claimed ∩ real)} for the #120 early-exit. A district is
    ABSENT (→ no early exit, the full census) when its district_target row is missing — unknown is
    never assumed satisfied. Failure degrades to {} — disabling the exit, never blocking the run.

    #619 REMOVED a district-membership benchmark exemption from here, and the removal INVERTS this
    function's answer for the 27 batch_00000 districts. Its intent — REQ-151's "a measurement run
    wants the full census, the shortcut would measure the shortcut" — is a property of THE RUN, so it
    now lives with the run-level disablers at the call site (`run_kind == production`, `gt_data is
    None`, and #618's `dispatch_type != benchmark`), where the frozen handoff can actually answer it.
    District membership was a third belt firing on runs that measure nothing, and — membership being
    permanent — it would have made all 27 re-run districts pay a full-census extraction on every
    future production run, forever (#620 makes those runs real).

    #621 is still the standing lesson for whatever keys here next: the removed exemption keyed on the
    `batch_00000` id LITERAL while every other benchmark guard keyed on `batch_type`, so a SECOND
    benchmark batch would silently have lost the exemption it was there to provide."""
    out: dict = {}
    ids = list(district_ids)
    if not ids:
        return out
    try:
        with gdb.session_scope() as s:
            rows = s.execute(
                text("SELECT district_id, lea_claimed_bands_json, schools_by_band_json, "
                     "nces_by_level_json FROM district_target WHERE district_id = ANY(:d)"),
                {"d": ids}).all()
            for did, cj, sj, lj in rows:
                claimed = json.loads(cj) if cj else []
                sbb = json.loads(sj) if sj else {}
                by_level = json.loads(lj) if lj else {}
                real = SS.real_bands_for_district(by_level, sbb,
                                                  band_rosters=SS.band_rosters_for_district(did))
                fillable = {b for b in claimed if b in real}
                if fillable:
                    out[did] = fillable
    except Exception as e:  # noqa: BLE001 — advisory: no targets ⇒ no early exit, the run proceeds
        print(f"[mode-stability] target lookup failed ({type(e).__name__}: {str(e)[:80]}) — "
              f"early-exit disabled this run", flush=True)
        return {}
    return out


def consensus_context_for_district(did: str, labels_by_rec: dict) -> dict:
    """#707: the deterministic per-district context that can RESOLVE a degenerate school name at
    the consensus boundary — {labels_by_rec: {rec_key: human label}, roster_by_band: {band:
    [school names]}} (the Stage-1 slot spine, live from ccd_sch; None-safe when the CCD files
    aren't on disk). Shared MECHANISM between the production run and the #716 re-aggregation
    replay (same slicing, same resolution rules). The LABEL INPUT deliberately differs (#738):
    production reads the handoff doc's label (current at dispatch time); the replay reads the
    LIVE label table — the working store — so a human's label correction corrects the replay,
    which is the point of replaying. A replay can therefore legitimately partition
    accepted/unresolved differently than the original run when the label has since changed."""
    roster_by_band, roster_recs = {}, {}
    try:
        br = SS.band_rosters_for_district(did)
        if br:
            roster_by_band = {b: list(m.get("schools") or []) for b, m in br.items()
                              if isinstance(m, dict) and not b.startswith("_")}
            # #693/#721: the slot spine WITH ids — the roster-anchored identity resolver's input
            # (resolve_school_identity). Same source, richer grain; names-only roster_by_band
            # stays for #707's N=1 resolution.
            roster_recs = {b: [{"name": sr.get("name"), "school_id": sr.get("school_id")}
                               for sr in (m.get("slot_recs") or [])]
                           for b, m in br.items()
                           if isinstance(m, dict) and not b.startswith("_")}
    except Exception as e:  # noqa: BLE001 — advisory context: no roster ⇒ no N=1 resolution
        print(f"[consensus-context] roster lookup failed for {did} "
              f"({type(e).__name__}: {str(e)[:80]}) — N=1/identity resolution disabled", flush=True)
    return {"labels_by_rec": labels_by_rec or {}, "roster_by_band": roster_by_band,
            "roster_recs": roster_recs}


def _rep_consensus_context(ctx: dict, rec_key: str) -> dict:
    """The per-rep slice consensus_school_facts takes: band_grain iff THIS record's human label is
    district_hub_by_band (band referents are that label's expected grain, #707)."""
    if not ctx:
        return None
    return {"band_grain": (ctx.get("labels_by_rec") or {}).get(rec_key) == "district_hub_by_band",
            "roster_by_band": ctx.get("roster_by_band") or {},
            "roster_recs": ctx.get("roster_recs") or {}}


def _run_district(did: str, name: str, rep_groups: list, councils: dict, ddir, use_judge: bool,
                  early_exit_bands=None, ms_params: dict = None, ctx: dict = None) -> dict:
    """Run the full council over ONE district's reps and return its result dict (reps + per-model
    call detail, pooled accepted/unresolved facts, modal bands, telemetry). All the paid calls for a
    district happen here so the caller can persist it as a unit."""
    pd = {"district_id": did, "name": name, "reps": [], "accepted": [], "unresolved": [],
          "n_reps": 0, "n_judged": 0}
    n_total = len(rep_groups)
    for i, rg in enumerate(rep_groups, 1):
        # Per-rep isolation (#173): a rep that can't be READ (unreadable/relocated file) or whose
        # processing throws must not kill the district — record it as a failed rep and move on, so the
        # district's OTHER reps still extract (the Marshall harvest_slice case: one bad rep of many).
        # `calls` is seeded BEFORE the try so any voter calls that already SUCCEEDED (and were billed)
        # before a later step raised are preserved in the failure record, not discarded (#184). The
        # rep-group unpack is INSIDE the try so a malformed rep-group is isolated here at the rep level,
        # not left to escape and strand the whole district (#185). BillingAuthError still propagates.
        calls: list = []
        try:
            rec_key, file, kind, cid = rg["rec_key"], rg["file"], rg["kind"], rg["council_id"]
            content = resolve_content(ddir, rec_key, file, kind)
            cfg = councils.get(cid) or {}
            model_rows = {}
            for model in rg["voters"]:
                res = _call(model, rg["prompt_ids"][model], kind, content)
                facts = PARSE.parse_schedules(res.content) if res.ok else []
                model_rows[model] = facts
                calls.append(_call_record(model, "voter", res, facts))

            rep_ctx = _rep_consensus_context(ctx, rec_key)   # #707: label + roster resolution
            accepted, unresolved = AGG.consensus_school_facts(model_rows, context=rep_ctx)
            judged = False
            if use_judge and unresolved and cfg.get("judge"):
                jmodel = cfg["judge"]
                jres = _call(jmodel, P6.select_prompt_id(cfg, jmodel), kind, content)
                jfacts = PARSE.parse_schedules(jres.content) if jres.ok else []
                calls.append(_call_record(jmodel, "judge", jres, jfacts))
                accepted, unresolved = AGG.consensus_school_facts(model_rows, {jmodel: jfacts},
                                                                  context=rep_ctx)
                judged = True
        except HALTING_EXCEPTIONS:
            raise                       # halt — every later paid call fails identically (#173/#189)
        except Exception as e:          # noqa: BLE001 — a bad rep must not lose the whole district
            pd["reps"].append({"rec_key": rg.get("rec_key"), "file": rg.get("file"),
                               "kind": rg.get("kind"), "council_id": rg.get("council_id"),
                               "judged": False, "calls": calls, "accepted": [], "unresolved": [],
                               "error": f"{type(e).__name__}: {e}"})
            pd["n_reps"] += 1
            print(f"  [rep {i}/{n_total}] {did} {str(rg.get('file', ''))[:28]:28s} "
                  f"({rg.get('kind')}->{rg.get('council_id')})  "
                  f"⚠ SKIPPED — {type(e).__name__}: {str(e)[:80]}", flush=True)
            continue

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

        # #120 mode-stability early-exit (district-grain): once EVERY fillable target band's running
        # mode is stable, the remaining reps are pure spend — stop, and record them as SKIPPED
        # receipts (a separate list, never in `reps`: a skipped rep must not read as barren to the
        # request loop, and it stays dispatchable via 7->6 if a human distrusts the value at gate@8).
        if (i < n_total and ms_params and ms_params.get("enabled")
                and _bands_mode_stable(pd["accepted"], early_exit_bands, ms_params)):
            skipped = [{"rec_key": rg2.get("rec_key"), "file": rg2.get("file"),
                        "kind": rg2.get("kind"), "council_id": rg2.get("council_id"),
                        "reason": "mode_stable"} for rg2 in rep_groups[i:]]
            pd["skipped_reps"] = skipped
            pd["early_exit"] = {"reason": "mode_stable", "after_rep": i,
                                "n_reps_skipped": len(skipped),
                                "stable_bands": sorted(early_exit_bands),
                                "params": {k: ms_params.get(k) for k in ("window", "min_n", "min_share")}}
            print(f"  [rep {i}/{n_total}] {did} — mode stable on "
                  f"{'/'.join(sorted(early_exit_bands))}; skipping {len(skipped)} remaining rep(s) "
                  f"(#120)", flush=True)
            break

    # Post-loop aggregation is guarded too (#183): a bug in band-modeling must not discard the reps
    # that already ran and were billed. On failure, keep the reps + telemetry (so the district still
    # persists and its spend is recorded) and mark the district errored with empty bands.
    try:
        pd["bands"] = AGG.district_bands_from_facts(pd["accepted"])
    except Exception as e:  # noqa: BLE001 — an aggregation bug must not lose already-billed reps (#183)
        pd["bands"], pd["error"] = {}, f"district_bands: {type(e).__name__}: {e}"
        print(f"  [district {did}] ⚠ band aggregation failed — {type(e).__name__}: {str(e)[:80]} "
              f"(reps preserved)", flush=True)
    pd["telemetry"] = _rollup_tel(pd["reps"])
    return pd


def _content_n_times(kind: str, content) -> "int | None":
    """The clock-time count of a TEXT rep's resolved content — the SAME signal Stage 5 stores as
    `representation.n_times` (`build_signals.time_positions`), recomputed here from exactly what we're
    about to send, so #180 sizing needs no handoff plumbing (n_times isn't carried through freeze).
    Image reps (content is a data/URL) can't be counted → None → the 16k floor + the #169 retry."""
    return len(BS.time_positions(content)) if kind == "text" and isinstance(content, str) else None


def _call(model: str, prompt_id: str, kind: str, content) -> "OR.CallResult":
    body = R6.build_request({"model": model, "prompt_id": prompt_id, "kind": kind}, content)
    # #180: pre-size max_tokens from the roster (via the rep's time count) so a big table is sized
    # right on the FIRST call — no truncate-then-retry double prompt-charge. Retry stays the backstop.
    return OR.call(body, max_tokens=OR.size_max_tokens(_content_n_times(kind, content)))


def _call_record(model: str, role: str, res, facts: list) -> dict:
    """One model call's audit row for the receipt/gate@7 — telemetry + what it read (no raw content).
    `finish_reason == "length"` marks a TRUNCATED reply (tail schools silently gone — the salvage
    parser keeps only the head), surfaced through the telemetry rollup + progress line."""
    return {"model": model, "role": role, "ok": res.ok, "error": res.error, "n_facts": len(facts),
            "facts": facts, "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens, "cost_usd": res.cost_usd,
            "latency_ms": res.latency_ms, "finish_reason": res.finish_reason,
            "generation_id": res.generation_id, "truncation_retried": res.truncation_retried}


def _rollup_tel(reps: list) -> dict:
    """Sum per-call telemetry across a set of reps (per-district or global)."""
    t = {"calls": 0, "judge_calls": 0, "errors": 0, "rep_errors": 0, "truncated": 0,
         "truncation_retries": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
    for rep in reps:
        if rep.get("error"):        # a rep that couldn't be read/processed at all (#173) — no calls
            t["errors"] += 1
            t["rep_errors"] += 1
        for c in rep["calls"]:
            if c.get("truncation_retried"):
                t["truncation_retries"] += 1
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


def _check_image_councils(doc: dict) -> None:
    """Refuse a frozen handoff whose image-kind reps route to a council with a non-vision-capable
    member (#138 / #82 recurrence guard). The `councils.validate()` vision guard runs only at
    config-LOAD — a frozen handoff EMBEDS its configs, so a pre-swap doc still carries the dead
    text-only image judge and would 404 every judge call while paying for the voters. Scoped to the
    image hazard only (text councils validate at freeze time; test fixtures with synthetic text
    models stay valid). Raises ValueError naming the blind model(s) — re-freeze under current configs."""
    councils = doc.get("councils") or {}
    blind = {}
    for d in doc.get("districts", []):
        for rec in d.get("records", []):
            for rep in rec.get("reps", []):
                if not CONTENT.is_image_kind(rep.get("kind")):
                    continue
                for cid in rep.get("councils", []):
                    cfg = councils.get(cid) or {}
                    for m in list(cfg.get("voters") or []) + [cfg.get("judge")]:
                        if m and not MF.is_vision_capable(m):
                            blind.setdefault(cid, set()).add(m)
    if blind:
        detail = "; ".join(f"council '{cid}': {sorted(ms)}" for cid, ms in sorted(blind.items()))
        raise ValueError(
            f"frozen handoff routes image reps to non-vision-capable model(s) — {detail}. "
            f"Every call would 404 ('No endpoints found that support image input', #82). "
            f"Re-freeze the dispatch under the current council configs instead of re-running this doc.")


def run_council_streaming(doc: dict, *, use_judge: bool = True, persist: bool = False,
                          gt_data: dict = None, created_by: str = "auto:stage7", resume: bool = True,
                          on_district=None) -> dict:
    """The DURABLE, RESUMABLE run: process ONE district at a time and, if `persist`, commit it
    immediately (its extraction + school_fact rows + state_event + a per-district receipt) before
    the next — so a crash / network drop / OpenRouter outage at district N keeps districts 1..N-1
    and a re-run skips them (`resume` — query `extraction` for this handoff_hash). Streams a
    per-district progress line (+ a mini GT scorecard when `gt_data` is given). Returns the
    THIS-SESSION results (skipped districts are already durable in the DB, not re-collected)."""
    _check_image_councils(doc)      # #82-recurrence guard: fail BEFORE any paid call or key check
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

    # REQ-051 budget governor: seed from DURABLE recorded spend (so a resumed run continues under the
    # SAME ceiling) when persisting; else count only this session. A null cap disables its dimension.
    # #147: the three REQ-051 ceilings share ONE spend definition. This-run per-district spend seeds
    # both the per-district ceiling AND the run ceiling (run total = sum of the per-district dict —
    # never a separate query that could define "spend" differently).
    this_run = _spend_by_district(handoff_hash=hh) if persist else None
    gov = BUD.BudgetGovernor(BUD.load_budget(),
                             run_spent=sum(this_run.values()) if this_run else 0.0,
                             district_spent=this_run,
                             district_total_spent=(_spend_by_district(district_ids=by_district.keys())
                                                   if persist else None))
    try:
        cost_model = COST6.load_cost_model()
    except Exception:  # noqa: BLE001 — estimate is advisory (see _estimate_district_cost)
        cost_model = None

    run_kind = doc.get("run_kind") or "production"    # #148: probes (image_handoff_variant) stamp this
    # #662: a run against a BENCHMARK dispatch (#618) is never production, whatever #148's own axis
    # says. Without this, persist_run_session (below) writes run_kind='production' for every benchmark
    # harness run — which is exactly the mislabel #662's migration existed to correct retroactively.
    # Stamping it correctly HERE means a second benchmark batch/dispatch (#618/2c made this possible;
    # #620/mobility-property-2 is the point of building it) never needs that migration re-run. `probe`
    # takes precedence when both are true — #148's axis answers a narrower, more specific question
    # (which council variant) than #618's (production vs. benchmark harness), and #148 predates #618.
    if run_kind == "production" and BM.is_benchmark_dispatch(doc):
        run_kind = BM.RUN_KIND_BENCHMARK
    ms_params = load_mode_stability()
    ms_targets = (_drop_benchmark_provenance_districts(
                      _early_exit_targets(by_district.keys()), by_district)
                  if _early_exit_enabled(doc, run_kind, gt_data, ms_params) else {})
    results = {"handoff_hash": hh, "run_kind": run_kind, "districts": {}}
    for did in sorted(by_district):
        if did in done:
            print(f"[skip]  {did} — already extracted for handoff {hh}", flush=True)
            continue
        est = _estimate_district_cost(by_district[did], councils, cost_model)
        if gov.run_would_exceed(est):
            print(f"[budget] run cap ${gov.budget.per_run_usd:.2f} reached "
                  f"(spent ${gov.run_spent:.4f}, est +${est:.4f}) — HALTING before {did}", flush=True)
            break
        if gov.district_would_exceed(did, est):
            print(f"[budget] district {did} per-run cap ${gov.budget.per_district_usd:.2f} would be "
                  f"exceeded (spent ${gov.district_spent.get(did, 0.0):.4f}, est +${est:.4f}) — SKIPPING",
                  flush=True)
            continue
        if gov.district_total_would_exceed(did, est):
            print(f"[budget] district {did} TOTAL acquisition cap ${gov.budget.per_district_total_usd:.2f} "
                  f"would be exceeded (cumulative ${gov.district_total_spent.get(did, 0.0):.4f}, "
                  f"est +${est:.4f}) — SKIPPING", flush=True)
            continue
        # Per-district isolation (#173): the per-rep guard in _run_district already recovers a bad
        # rep, so this is the batch-level backstop — any OTHER unexpected failure computing a district
        # (a malformed rep group, an aggregation bug) is recorded and the batch moves on, rather than
        # aborting every remaining district (the original #122 symptom: 1 bad rep stranded 16→18).
        # BillingAuthError / SystemExit / KeyboardInterrupt still halt — they're not per-district.
        try:
            labels_by_rec = {r.get("rec_key"): r.get("label")
                             for d in (doc.get("districts") or []) if d.get("district_id") == did
                             for r in (d.get("records") or [])}
            pd = _run_district(did, _district_name(doc, did), by_district[did], councils,
                               ddirs.get(did), use_judge,
                               early_exit_bands=ms_targets.get(did), ms_params=ms_params,
                               ctx=consensus_context_for_district(did, labels_by_rec))
        except HALTING_EXCEPTIONS:
            raise                       # halt — never degrade a billing/auth failure to a skip (#189)
        except Exception as e:  # noqa: BLE001
            print(f"[fail]  {did} — {type(e).__name__}: {str(e)[:120]} — SKIPPING (batch continues)",
                  flush=True)
            results.setdefault("failed", []).append(
                {"district_id": did, "error": f"{type(e).__name__}: {e}"})
            continue
        pd["state"] = _district_state(doc, did)   # onto pd BEFORE receipt/persist (#165)
        gov.record(did, (pd.get("telemetry") or {}).get("cost_usd", 0.0))
        results["districts"][did] = pd
        if persist:
            rp = write_district_receipt(pd, hh)
            with gdb.session_scope() as s:
                persist_run_session(s, {"handoff_hash": hh, "run_kind": run_kind,
                                        "districts": {did: pd}},
                                    created_by=created_by, receipt_path=rp)
                # Request-more-evidence, same txn — PRODUCTION only (#148 review): the console's
                # pending counts + detail cards are district-scoped across all handoffs, so a probe's
                # directives would surface as reviewable production work (and an approved one could be
                # swept into a paid follow-up). A probe is a measurement, never a remedy driver.
                if run_kind == "production":
                    # ONE closing-argument load serves both calls (#703 review): detect + withdraw
                    # both need the district's slot view, same txn — share the cache dict.
                    ca_cache: dict = {}
                    detect_and_persist_requests(s, pd, hh, ca_cache=ca_cache)
                    # #233, same txn: this round's facts may have satisfied EARLIER rounds' still-open
                    # directives — retire them so the gate@7 queue reflects the cumulative truth.
                    withdraw_satisfied_requests(s, did, ca_cache=ca_cache)
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
    # #148: mark this as a PROBE so its extraction rows carry run_kind='probe' and stay out of the
    # gate@7 console — a first-class flag, independent of the hash suffix (which now serves only
    # resume-isolation + lineage). Any council_id, not just 'image', is a probe.
    v["run_kind"] = "probe"
    return v


def _district_name(doc: dict, did: str) -> str:
    for d in doc.get("districts", []):
        if d.get("district_id") == did:
            return d.get("name", "")
    return ""


def _district_state(doc: dict, did: str) -> str | None:
    """The district's US state from the frozen handoff entry — carried onto pd so the persist
    path's state_event doesn't write state NULL (#165: the old NULL nulled the current_state
    header for every extracted district)."""
    for d in doc.get("districts", []):
        if d.get("district_id") == did:
            return d.get("state") or None
    return None


# ---------------------------------------------------------------------------
# Slice 3 — receipt (disk) + governance persistence (DB, never the LCT DB)
# ---------------------------------------------------------------------------
def _fs_ts() -> str:
    return TU.fs_stamp()


def write_receipt(results: dict, *, root=None) -> str:
    """Write the full run — per-rep, per-model detail incl. what each model read — as the auditable
    on-disk receipt (the DB holds the queryable per-school facts; disk holds the audit trail,
    governance §1). Returns the path."""
    hh = results.get("handoff_hash") or "nohash"
    d = Path(root) if root else (paths.ACQUISITION / "extractions")
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"extraction_{hh}_{_fs_ts()}.json"
    paths.atomic_write_json(path, results)   # crash-safe (was a bare write_text — the one non-atomic receipt)
    return str(path)


def write_district_receipt(pd: dict, handoff_hash: str, *, root=None) -> str:
    """One district's run as an immutable receipt (`extraction_<hash>_<did>_<ts>.json`), written the
    moment the district completes — durable independent of the rest of the batch (the streaming path).
    ALSO drops a per-district capture-dir audit receipt (REQ-164) pointing at this authoritative file."""
    d = Path(root) if root else (paths.ACQUISITION / "extractions")
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"extraction_{handoff_hash or 'nohash'}_{pd['district_id']}_{_fs_ts()}.json"
    paths.atomic_write_json(path, {"handoff_hash": handoff_hash, "district": pd})   # crash-safe (was write_text)
    _stage7_capture_receipt(pd, handoff_hash, path)
    return str(path)


def _stage7_capture_receipt(pd: dict, handoff_hash: str, central_path: Path) -> None:
    """Faithful per-district Stage-7 receipt into the capture dir (REQ-164), carrying the district's
    extraction detail + a pointer to the authoritative central file (acquisition/extractions/) and the
    gov DB (extraction/school_fact). Best-effort — those two ARE authoritative, so a disk hiccup is
    logged, never a failed extraction (the receipt is regenerable)."""
    try:
        RCPT.write_receipt(pd["district_id"], "", "stage7_extract", {
            "stage": 7, "stage_name": "extract", "district_id": pd["district_id"],
            "handoff_hash": handoff_hash,
            "authoritative": f"gov_db:extraction/school_fact + acquisition/extractions/{central_path.name}",
            "central_receipt": central_path.name, "district": pd})
    except Exception as e:  # noqa: BLE001 — the receipt is regenerable; never fail an extraction
        print(f"[warn] Stage 7 capture-dir receipt failed for {pd.get('district_id')} "
              f"({type(e).__name__}: {e}); regenerable from gov_db + the central receipt")


def _already_extracted(handoff_hash: str) -> set:
    """District ids already persisted for this handoff (the resume skip-set). Schema must exist."""
    with gdb.session_scope() as s:
        return {r[0] for r in s.execute(
            text("SELECT DISTINCT district_id FROM extraction WHERE handoff_hash = :h"),
            {"h": handoff_hash or ""})}


def _spend_by_district(*, handoff_hash: str = None, district_ids=None) -> dict:
    """{district_id: SUM(extraction.cost_usd)} — the ONE spend-seed query behind all three REQ-051
    governor ceilings (#147), so "spend" is defined once and can't drift between them.
      • `handoff_hash` — THIS run's per-district durable spend (the resume seed; the run total is its
        SUM, never a separate query). Kept consistent with `_already_extracted`'s scope.
      • `district_ids` — CUMULATIVE per-district spend across ALL handoffs (the per-district TOTAL
        acquisition ceiling — bounds a hard district's runaway spend over every follow-up round).
    Exactly one scope; `district_ids` wins if both are given. Empty `district_ids` → {} (no query)."""
    if district_ids is not None:
        ids = list(district_ids)
        if not ids:
            return {}
        where, params = "district_id = ANY(:d)", {"d": ids}
    else:
        where, params = "handoff_hash = :h", {"h": handoff_hash or ""}
    with gdb.session_scope() as s:
        rows = s.execute(text("SELECT district_id, COALESCE(SUM(cost_usd), 0.0) FROM extraction "
                              f"WHERE {where} GROUP BY district_id"), params)
        return {r[0]: float(r[1] or 0.0) for r in rows}


def _estimate_district_cost(rep_groups: list, councils: dict, cost_model) -> float:
    """Best-effort pre-run cost estimate for one district (the per-rep council estimate summed) — the
    number the governor checks BEFORE a paid district so a per-district/run cap can pre-empt rather
    than only halt after a breach. Best-effort: any estimator gap ⇒ 0.0 (the actuals-recorded run-cap
    halt is the hard guarantee), so a missing/broken cost model never blocks a legitimate run."""
    if not cost_model:
        return 0.0
    total = 0.0
    for rg in rep_groups:
        cfg = councils.get(rg["council_id"]) or {}
        try:
            total += COST6.estimate_council_cost({"n_chars": 0, "n_schools": 1}, cfg, cost_model)
        except Exception:  # noqa: BLE001 — estimate is advisory; never let it abort the run
            return 0.0
    return total


def _print_district_progress(did: str, pd: dict, gt_data: dict = None) -> None:
    tel = pd.get("telemetry") or {}
    bands = pd.get("bands") or {}
    band_str = " ".join(f"{b[0].upper()}={v['gross_minutes']}" for b, v in bands.items()) or "(none)"
    line = (f"[done]  {did} {pd['name'][:22]:22s} reps={pd['n_reps']:2d} "
            f"acc={len(pd['accepted']):2d} unres={len(pd['unresolved']):2d} "
            f"err={tel.get('errors', 0)} ${tel.get('cost_usd', 0):.4f} | {band_str}")
    if tel.get("truncation_retries"):
        line += f"  ↻ {tel['truncation_retries']} retried@{OR.MAX_TOKENS_CEILING//1000}k"
    if tel.get("truncated"):
        line += (f"  ⚠ {tel['truncated']} STILL TRUNCATED at the "
                 f"{OR.MAX_TOKENS_CEILING//1000}k ceiling — roster exceeds the model window; check tail loss")
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
    run_kind = results.get("run_kind") or "production"   # #148: probe vs production, console discriminator
    summary = {"handoff_hash": hh, "districts": [], "n_facts": 0}
    for did, pd in results["districts"].items():
        tel = pd.get("telemetry") or {}
        ex = M7.Extraction(
            handoff_hash=hh or "", district_id=did, created_by=created_by, run_kind=run_kind,
            n_reps=pd.get("n_reps", 0),
            n_reps_skipped=len(pd.get("skipped_reps") or []),   # #120: the early-exit receipt count
            n_calls=tel.get("calls", 0),
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
                evidence_json=json.dumps(f["evidence"]) if f.get("evidence") else None,
                school_year=f.get("school_year"), applies_to=f.get("applies_to"),   # v3 readings (#254)
                campus_names_json=(json.dumps(f["campus_names"])
                                   if f.get("campus_names") else None),      # v4 reading (#499)
                identity_json=(json.dumps(f["identity"])
                               if f.get("identity") else None),              # v5 marking (#693/#721)
                rec_key=f.get("rec_key"), source_file=f.get("source_file")))
        for u in pd["unresolved"]:
            s.add(M7.SchoolFact(
                extraction_id=ex.extraction_id, district_id=did, band=u.get("band", ""),
                school=u.get("school", ""), status="unresolved", gross_minutes=u.get("gross"),
                method=u.get("reason", "disagree"),
                detail_json=json.dumps({k: u[k] for k in ("starts", "ends", "gross") if k in u}),
                identity_json=(json.dumps(u["identity"])
                               if u.get("identity") else None),              # v5 marking (#693/#721)
                rec_key=u.get("rec_key"), source_file=u.get("source_file")))
        s.execute(DS.INSERT_STATE_EVENT, {
            "district_id": did, "name": pd.get("name", ""), "state": pd.get("state"), "stage": 7,
            "stage_name": "extract", "checkpoint": None, "event_type": "extracted",
            "outcome": "extracted", "topology": None, "batch_id": None,
            "fingerprints_json": None, "actor": created_by, "note": hh,
            "created_at": M7.utcnow()})
        summary["districts"].append(
            {"district_id": did, "extraction_id": ex.extraction_id,
             "n_accepted": len(pd["accepted"]), "n_unresolved": len(pd["unresolved"])})
        summary["n_facts"] += len(pd["accepted"]) + len(pd["unresolved"])
    # Flush the SchoolFact adds before returning (PR #240 review, HIGH): the session factory runs
    # autoflush=False, so without this the caller's same-transaction raw-SQL reads — detect's
    # covered-bands check and #233's withdraw pass, which exist precisely to react to THIS round's
    # facts — silently cannot see them. (The tests masked this: gov_session defaults autoflush=True.)
    s.flush()
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
# The request-more-evidence loop: detect (pure) + persist (app-layer DB inputs)
# ---------------------------------------------------------------------------
def covered_bands_for_district(session, district_id: str) -> set:
    """Bands with a cumulative accepted fact across ALL production runs — the ONE per-district
    'covered' predicate (REQ-122 semantics; probes are measurements, never coverage). Shared by
    _district_request_inputs (detect) and withdraw_satisfied_requests (#233) so the two can never
    disagree within a transaction; stage7_execute._covered_bands_now is the BATCHED twin of this
    query (different shape, same predicate — keep aligned)."""
    return {b for (b,) in session.execute(
        text("SELECT DISTINCT f.band FROM school_fact f "
             "JOIN extraction e ON e.extraction_id = f.extraction_id "
             "WHERE f.district_id = :d AND f.status = 'accepted' AND f.band IS NOT NULL "
             "AND e.run_kind = 'production'"), {"d": district_id}).all()}


def _slot_gaps_for_district(session, district_id: str, sbb: dict, ca_cache: dict = None):
    """#694: the detector's slot-grain view — the live gate@8 closing argument (the SAME projection
    Stage 8 and the compose gate read; slot state has ONE home, slot_spine via closing_argument)
    compressed by the pure `RQ.slot_gap_summary`, with the Stage-1 pool (`schools_by_band_json`,
    extracted by the ONE shared `SS.stage1_pool_ids` — the same spelling gate@8's outside-pool
    count uses) marking which unfilled slots follow-up chases vs the bounded #696 mode-check class.

    `ca_cache` ({district_id: closing_argument}) is the stage7_execute `_load_ca_cached` pattern:
    detect + withdraw run back-to-back per district in one transaction (#703 review), so the caller
    shares one dict to pay for the ~9-query + CCD-roster assembly ONCE, not twice.

    Best-effort (the `_satisfied_bands_now` posture): any failure — CCD roster unavailable, no
    projection — returns None and the detector falls back to the covered-band boolean; degradation
    costs precision, never correctness. The failure is PRINTED (#703 review): a genuine bug in this
    path would otherwise be indistinguishable from the benign no-roster case and silently disable
    slot-grain detection for the district with no trace in the run log."""
    try:
        if ca_cache is not None and district_id in ca_cache:
            ca = ca_cache[district_id]
        else:
            ca = CA8.load_closing_argument(session, district_id, record_drift_event=False)
            if ca_cache is not None:
                ca_cache[district_id] = ca
        return RQ.slot_gap_summary(ca, pool_by_band=SS.stage1_pool_ids(sbb))
    except Exception as e:  # noqa: BLE001 — best-effort; the covered-band hard gate remains
        print(f"  [requests] {district_id}: slot view unavailable ({type(e).__name__}: "
              f"{str(e)[:80]}) — detection falls back to the covered-band boolean", flush=True)
        return None


def _district_request_inputs(session, result: dict, ca_cache: dict = None):
    """The DB-derived inputs the pure detector (`requests.detect_requests`) needs for one district:
    claimed bands + the band's schools (`district_target`), the alternate reps per sent record
    (`representation`, the usable reps of a rec_key other than the one we sent — drives 7→6 vs 7→3),
    the district-wide covered bands (`school_fact` across all extractions — so a partial result
    can't fabricate band gaps), the real (fillable) bands (#175/#176), and the #694 slot-gap
    summary (None when unavailable).
    Returns (claimed, band_schools, alts, covered, real_bands, slot_gaps) — a 6-tuple."""
    did = result["district_id"]
    # ALL files sent per rec_key (#145): Stage 6 may dispatch several reps of one record, and a rep we
    # already sent (and that just failed) must never be offered back as its own 7->6 "alternate".
    sent: dict = {}
    for rep in result.get("reps", []):
        sent.setdefault(rep["rec_key"], set()).add(rep["file"])
    # #231: that invariant must hold across ROUNDS, not just within this dispatch — the record's own
    # request lineage IS its dispatch history (every barren round persisted a request naming what it
    # sent; emission itself proves the send, so status doesn't matter). Union those files in too.
    # Without this, round 2's detect re-offers round 1's failed rep and the bounded retry budget
    # circles known-barren reps instead of reaching the untried ones (live #122: Union Hill #3624
    # re-asked for round-1's tesseract_raster.txt, Brownsville #3622 for page.txt).
    for tgt, pj in session.execute(
            text("SELECT target, params_json FROM extraction_request "
                 "WHERE district_id = :d AND route IN (:r6, :r3)"),
            {"d": did, "r6": RQ.ROUTE_ALT_REP, "r3": RQ.ROUTE_RECAPTURE}).all():
        p = json.loads(pj or "{}")
        hist = p.get("sent_files") or ([p["sent_file"]] if p.get("sent_file") else [])
        if hist:
            sent.setdefault(tgt, set()).update(hist)
    row = session.execute(text("SELECT lea_claimed_bands_json, schools_by_band_json, nces_by_level_json "
                               "FROM district_target WHERE district_id = :d"), {"d": did}).fetchone()
    claimed = json.loads(row[0]) if row and row[0] else []
    sbb = json.loads(row[1]) if row and row[1] else {}
    band_schools = {b: [x["name"] for x in (sbb.get(b, {}) or {}).get("schools", [])] for b in RQ.BANDS}
    # real_bands (#175/#176): the bands SERVED by ≥1 real NCES school — derived by the ONE shared
    # helper (it owns the sbb traversal too, so the detector's gate and the compose gate in
    # stage7_execute can never diverge on the definition). Fillability, incl. Stage 1's gap-fill.
    # #498 (PR #500 review round): the LIVE roster rides along so the carve-out-blind aggregate
    # signal can't keep the spend gate chasing a phantom band (56-district corpus class).
    by_level = json.loads(row[2]) if row and row[2] else {}
    real_bands = SS.real_bands_for_district(by_level, sbb,
                                            band_rosters=SS.band_rosters_for_district(did))
    alts = {}
    for rec_key, sent_files in sent.items():
        # Dispatchable kinds only (#140): binaries (pdf/bin) and chrome segments are usable=1 in the
        # Stage-4 sense ("produced"), but a 7->6 alternate must be something a council can READ —
        # a pdf alternate would route to the text council and be read as raw bytes (paid mojibake).
        # n_times drives the yield-aware ranking (#155): a fuller text extraction beats a raster image.
        for fn, kind, nt in session.execute(
                text("SELECT filename, file_kind, n_times FROM representation WHERE rec_key = :k "
                     "AND usable = 1 AND file_kind IN ('text', 'image') "
                     "AND source NOT LIKE 'segment:%'"),
                {"k": rec_key}).all():
            if fn not in sent_files:
                alts.setdefault(rec_key, []).append({"file": fn, "kind": kind, "n_times": nt})
    # District-WIDE band coverage across ALL extractions (this run's facts are already flushed on
    # this session by persist_run_session, so they're visible too). Without this, a PARTIAL result
    # (a 1-record 7->6 re-dispatch) fabricates a gap for every claimed band the single record
    # doesn't cover — the live Las Cruces #285-287/#289-291 spurious 7->2s.
    # `band IS NOT NULL` keeps the covered set band-only — aligned with the batched twin
    # `stage7_execute._covered_bands_now` (the compose gate) so the two never disagree on membership.
    # run_kind='production' only, matching the twin: a probe's accepted fact must not mask a real gap.
    covered = covered_bands_for_district(session, did)
    # #694: this run's facts are already flushed on this session (persist_run_session), so the
    # closing argument the summary reads includes them — the slot view is never behind `covered`.
    slot_gaps = _slot_gaps_for_district(session, did, sbb, ca_cache=ca_cache)
    return claimed, band_schools, alts, covered, real_bands, slot_gaps


def detect_and_persist_requests(session, result: dict, handoff_hash: str,
                                ca_cache: dict = None) -> int:
    """Detect the request-more-evidence directives for one district's result and persist the NEW ones.
    Dedup is two-layered (#234): (a) same handoff, ANY status — a re-detect/backfill is idempotent and
    never resurrects a directive a human already actioned this round; (b) ANY handoff, OPEN status
    (pending/approved) — a still-open ask is the same logical ask, so a fresh round triggered by
    actioning a SIBLING request must not duplicate it. An executed/rejected/withdrawn prior round does
    NOT block re-emission: a new round's identical gap is a genuinely new ask (the depth guard, not
    dedup, bounds how many rounds may fire). Returns the count newly persisted."""
    claimed, band_schools, alts, covered, real_bands, slot_gaps = \
        _district_request_inputs(session, result, ca_cache=ca_cache)
    explain: dict = {}
    reqs = RQ.detect_requests(result, claimed_bands=claimed, alternates_by_rec=alts,
                              band_schools=band_schools, covered_bands=covered, real_bands=real_bands,
                              slot_gaps=slot_gaps, explain=explain)
    # Detect-time suppression is NON-emission (nothing persists; re-detection re-emits if coverage
    # regresses) — log it so a barren rep with no request next to it is explicable from the run log.
    if explain.get("suppressed_barren_reps") or explain.get("phantom_bands"):
        did = result.get("district_id")
        bits = []
        if explain.get("suppressed_barren_reps"):
            bits.append(f"{explain['suppressed_barren_reps']} barren-rep remedy(ies) suppressed — "
                        f"no fillable band gap remains")
        if explain.get("phantom_bands"):
            bits.append(f"phantom claimed band(s) {explain['phantom_bands']} — no school serves "
                        f"those grades, no 7->2 emitted")
        print(f"  [requests] {did}: " + "; ".join(bits), flush=True)
    n = 0
    if reqs:
        # Serialize concurrent detects for this district (PR #240 review): the check-then-insert
        # below has no DB unique constraint behind it, so two overlapping writers (live streaming +
        # a backfill sweep, or two autoflow threads) could both pass the SELECT before either
        # INSERTs. The xact-scoped advisory lock releases at commit, and READ COMMITTED means the
        # second writer's SELECT then sees the first's committed rows.
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext('extreq:' || :d))"),
                        {"d": result.get("district_id", "")})
    for r in reqs:
        exists = session.execute(
            text("SELECT 1 FROM extraction_request WHERE district_id = :d AND target = :t "
                 "AND altitude = :a AND route = :r AND band IS NOT DISTINCT FROM :b "
                 f"AND (handoff_hash = :h OR status IN {RQ.OPEN_STATUSES_SQL})"),
            {"d": r["district_id"], "h": handoff_hash, "t": r["target"], "a": r["altitude"],
             "r": r["route"], "b": r["band"]}
        ).first()
        if exists:
            continue
        session.add(M7.ExtractionRequest(
            district_id=r["district_id"], handoff_hash=handoff_hash, altitude=r["altitude"],
            route=r["route"], target=r["target"], band=r["band"],
            params_json=json.dumps(r["params"]), reason=r["reason"]))
        n += 1
    return n


def withdraw_satisfied_requests(session, district_id: str, ca_cache: dict = None) -> list:
    """#233: retire OPEN directives whose premise the CUMULATIVE state has satisfied — requests must
    not only grow per round (observed live: Redbank 5->6, Aspen 3->5, Union Hill 4->7 pending), each
    stale one adding to the human's gate@7 load. The premise-check is deterministic code against the
    cumulative production truth (merge_fact_runs semantics, REQ-122), never an LLM judgment:
      - a BAND-scoped directive (7->2/7->1 with band) is withdrawn once that band is DONE — #694:
        the ONE shared `RQ.band_done` predicate (satisfied / no open unfilled slots at slot grain
        when the slot view is available, the covered-band boolean otherwise). Emission and
        withdrawal MUST share this predicate: a directive detect emits for a covered-but-
        unsatisfied band that a weaker withdraw predicate then retires would churn
        (emit → withdraw → re-emit) every round;
      - a RECORD/DISTRICT-scoped directive (band NULL: 7->6/7->3 retries) is withdrawn only when NO
        fillable band remains un-done — the conservative mirror of detect-time's no-fillable-gap
        suppression (a record retry might fill ANY remaining gap, so it stays while one exists).
    Withdrawal is reversible by construction: 'withdrawn' is not an OPEN status, so if the gap ever
    re-opens a fresh re-detection re-emits (#234's dedup only blocks on pending/approved); a human
    Reopen re-runs this check server-side. The request row itself is the durable audit — machine
    actor, timestamp, and the satisfied premise in the note (same pattern as compose's
    _reject_suppressed). Returns [(request_id, note), ...] ACTUALLY withdrawn (rowcount-checked: a
    concurrent review/execute that wins the row must not fabricate an audit entry).

    Band-NULL semantics mirror detect_requests EXACTLY (PR #240 review): fillable = claimed ∩ real,
    and 'no gap left' is VACUOUSLY true when nothing is fillable (an all-phantom district — detect
    has permanently suppressed it, so a record retry can never fill anything). The one asymmetry: a
    MISSING district_target row means the target data is unknown, and unknown is never satisfied."""
    open_rows = session.execute(text(
        f"SELECT request_id, band FROM extraction_request "
        f"WHERE district_id = :d AND status IN {RQ.OPEN_STATUSES_SQL}"), {"d": district_id}).all()
    if not open_rows:
        return []                     # nothing open — skip the coverage/target queries entirely
    covered = covered_bands_for_district(session, district_id)
    row = session.execute(text("SELECT lea_claimed_bands_json, schools_by_band_json, nces_by_level_json "
                               "FROM district_target WHERE district_id = :d"), {"d": district_id}).fetchone()
    if row is None:
        fillable, no_gap_left, slot_gaps = [], False, None  # target data UNKNOWN — never satisfied
    else:
        claimed = json.loads(row[0]) if row[0] else []
        sbb = json.loads(row[1]) if row[1] else {}
        by_level = json.loads(row[2]) if row[2] else {}
        real_bands = SS.real_bands_for_district(by_level, sbb,
                                                band_rosters=SS.band_rosters_for_district(district_id))
        fillable = [b for b in claimed if b in real_bands]
        # #694: the SAME slot-grain done predicate detect uses (RQ.band_done over the same summary)
        # — see the docstring's churn rationale. Vacuously True when nothing fillable.
        slot_gaps = _slot_gaps_for_district(session, district_id, sbb, ca_cache=ca_cache)
        no_gap_left = all(RQ.band_done(b, covered, slot_gaps) for b in fillable)
    withdrawn, now = [], M7.utcnow()
    for req_id, band in open_rows:
        if band is not None and RQ.band_done(band, covered, slot_gaps):
            g = (slot_gaps or {}).get(band)
            note = (f"auto-withdrawn: band '{band}' is done at slot grain — satisfied (REQ-149) or "
                    f"no open unfilled slots (#233/#694)") if g is not None else \
                   f"auto-withdrawn: band '{band}' now has a cumulative accepted fact (#233)"
        elif band is None and no_gap_left:
            note = (f"auto-withdrawn: every fillable band ({', '.join(fillable)}) now covered — "
                    f"no fillable gap remains (#233)") if fillable else \
                ("auto-withdrawn: no fillable band exists (every claimed band is phantom) — "
                 "nothing a record retry could fill (#233)")
        else:
            continue
        res = session.execute(text(
            f"UPDATE extraction_request SET status = 'withdrawn', reviewed_by = 'auto:premise-satisfied', "
            f"reviewed_at = :t, review_note = :n "
            f"WHERE request_id = :id AND status IN {RQ.OPEN_STATUSES_SQL}"),
            {"t": now, "n": note, "id": req_id})
        if res.rowcount == 1:
            withdrawn.append((req_id, note))
    if withdrawn:
        print(f"  [requests] {district_id}: auto-withdrew {len(withdrawn)} satisfied directive(s) "
              f"(#233)", flush=True)
    return withdrawn


def backfill_requests(handoff_hash: str, *, root=None) -> int:
    """Detect + persist requests for every persisted district of a handoff, from its receipts on disk
    — no re-extraction, no paid calls. Idempotent. Returns the count newly persisted."""
    gdb.init_precious_schema()
    d = Path(root) if root else (paths.ACQUISITION / "extractions")
    total = 0
    with gdb.session_scope() as s:
        dids = set()
        ca_cache: dict = {}   # one closing-argument load per district across detect + withdraw (#703)
        for f in sorted(d.glob(f"extraction_{handoff_hash}_*.json")):
            doc = json.loads(f.read_text())
            pd = doc.get("district")
            if pd:
                total += detect_and_persist_requests(s, pd, handoff_hash, ca_cache=ca_cache)
                dids.add(pd.get("district_id"))
        # #233 must hold on THIS entry point too (PR #240 review): a backfill sweep that persists
        # new requests but never retires satisfied ones would re-accumulate the stale gate@7 load.
        for did in sorted(x for x in dids if x):
            withdraw_satisfied_requests(s, did, ca_cache=ca_cache)
    return total


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
    # #188: a district-level failure isolates + continues the batch (#173) — surface it in the CLI
    # summary too, so a redirected-to-log run doesn't read as clean when N districts were skipped.
    failed = out.get("failed") or []
    if failed:
        print(f"\n⚠ {len(failed)} districts FAILED (skipped, batch continued): "
              f"{', '.join(f['district_id'] for f in failed)}")
        for f in failed:
            print(f"    {f['district_id']}: {f['error']}")
    print(f"\nTELEMETRY: {tel['calls']} calls ({tel['judge_calls']} judge), "
          f"{tel['prompt_tokens']}+{tel['completion_tokens']} tok, "
          f"${tel['cost_usd']:.4f}, {tel['errors']} errors, "
          f"{tel.get('truncated', 0)} truncated")


if __name__ == "__main__":
    main()
