"""Stage 2 (Discover) runner -- deterministic SERP architecture (REQ-104).

DECIDED 2026-06-28 after a five-provider bake-off on a 53-school known-positive set (results in
data/acquisition/diagnostics/):
  - **Wave 1 = Bright Data SERP** (`discover.brightdata_search`) -- real Google, 5,000/mo RECURRING
    free tier, measured 98% recall / 4.5s -- with **Serper failover** (`discover.serper_search`,
    banked credits, 100% recall) ONLY when Bright Data is out of credits / auth-fails. Bright Data and
    Serper hit the SAME Google index, so Serper is an UPTIME backup, not a recall layer.
  - **Wave 2 = Claude WebSearch** on the genuine residual -- a DIFFERENT index, a speculative 'why not
    try' tier for schools Google's `site:` returned nothing for (reuses the `claude -p` helpers below).
Google is the index that matters for long-tail K-12 sites -- own-index providers cratered (Perplexity
43%) and OpenRouter wraps Google at ~$27/1K (retired). The `claude -p` helpers are BOTH Wave-2 and the
diagnostic harness (`scripts/stage2_cli_reliability.py`).

The deterministic tail (gate -> residual -> Wave 2 -> flatten -> write -> registry) is reused from
discover_stage2 verbatim. `run_batch()` processes districts SEQUENTIALLY -- one registry writer, so no
race; the providers are fast enough at batch scale (parallelize at 17k via Bright Data's unlimited
concurrency later). Status = events in the log (governance Section 7a-C) for the console job feed.

Driven by `run_batch()` (the console's POST /api/discover/{batch_id}/run trigger) or as a CLI:
`python3 -m infrastructure.acquisition.stage2_discover.headless run <batch_id|path>`.
"""
import argparse
import json
import subprocess
import traceback
from pathlib import Path

import requests

from sqlalchemy import text

from infrastructure.acquisition.common import batch_guard as BG
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import discover as DISC
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage2_discover import discover_stage2 as D2

CLI_TIMEOUT_S = 420   # diagnostic-only: per-district `claude -p` budget for the cli_reliability harness
# Wave-2 residual budget (the LIVE sequential run). Lower than the diagnostic budget on purpose: Wave 2
# is the speculative "why-not-try" tier on the few schools Google's `site:` missed; a long hang stalls
# the whole sequential batch (the 420s budget caused the visible latency pauses on batch_00002), and the
# tier degrades to manual_flag anyway, so cap it tight. (STAGE2 §7d-1 watch-item.)
WAVE2_TIMEOUT_S = 75

# The strict Wave-1 output contract, enforced by `claude --json-schema`. Mirrors exactly what
# validate_wave1_result() checks: the NCES seed (district_id + domain) must travel back with the
# fruit, and every targeted school appears (empty urls, never omitted).
WAVE1_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["district_id", "domain", "schools"],
    "properties": {
        "district_id": {"type": "string"},
        "domain": {"type": "string"},
        "schools": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["school_id", "urls"],
                "properties": {
                    "school_id": {"type": "string"},
                    "urls": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def build_wave1_prompt(district: dict, roster: list) -> str:
    """The Wave-1 search brief, headless form -- a faithful translation of the proven subagent brief
    in `.claude/skills/stage2-discover/SKILL.md` (the WebSearch-is-deferred ToolSearch step, the
    "never put the school_id in the query" guard, the domain-scoping rule, the no-guessing rule, the
    every-school-must-appear rule). The school_id labels output ONLY; D2.query_for() already built
    each `query` from the school NAME, never its id.

    NOTE (#160): this agent path uses the SINGLE default `query` per school — a widened follow-up's
    differentiated `queries` set is consumed only by the SERP path (D2.run_wave1). If this fallback
    provider is ever used for a widen_queries follow-up, the widened net silently degrades to the
    default query; extend the brief before relying on it there."""
    domain = district.get("domain", "") or ""
    dlabel = domain if domain else "none"
    lines = [
        "First, call your ToolSearch tool with query \"select:WebSearch\" to load the WebSearch tool "
        "-- it is deferred and not callable until you do. Then use ONLY WebSearch for the searches "
        "below; do not read, fetch, or write any files, and do not use any other tool.",
        "",
        "You will search the web for bell-schedule pages for schools in one school district.",
        "",
        f"District: {district['name']} ({district['district_id']}), domain: {dlabel}.",
        "",
        "For each row below, call WebSearch with the `query` parameter set to EXACTLY the quoted text "
        "after \"SEARCH FOR:\" -- nothing added, nothing removed. Do NOT include the school_id, any "
        "NCES number, or any other identifier in the WebSearch query itself -- the school_id is given "
        "only so you can label your results in the JSON you return; a search containing it would "
        "return NCES/SEA database pages, not the district's own site. "
        + (f"Set `allowed_domains` to [\"{domain}\"] for every search. "
           if domain else "No domain is given, so search unscoped. ")
        + "Do not guess URLs -- only report URLs that WebSearch actually returned.",
        "",
        "Schools (school_id is a label for your output only, never part of the search):",
    ]
    for r in roster:
        lines.append(f"- school_id {r['school_id']} -- SEARCH FOR: \"{r['query']}\"")
    lines += [
        "",
        "When you have run a search for every school, return ONLY a JSON object of this shape "
        "(every school listed above must appear, with an empty `urls` array if nothing was found -- "
        "never omit a school):",
        json.dumps({"district_id": district["district_id"], "domain": domain,
                    "schools": [{"school_id": "<id>", "urls": ["<url>"]}]}),
    ]
    return "\n".join(lines)


def _extract_result_payload(envelope: dict) -> dict:
    """Pull the structured Wave-1 dict out of a `claude -p --output-format json` envelope.

    Defensive about where the structured payload lands across CLI versions: prefer an explicit
    structured-output field, else parse the `result` text (tolerating a ```json fence)."""
    if envelope.get("is_error"):
        raise RuntimeError(f"claude CLI reported is_error: {str(envelope.get('result'))[:300]}")
    # CONFIRMED (smoke test 2026-06-27, CLI 2.1.71): `--json-schema` output lands on a dedicated
    # `structured_output` key; `result` is only the agent's prose summary. The other keys + the
    # `result`-string fallback are defensive against version drift.
    for key in ("structured_output", "structured_result", "structuredOutput"):
        if isinstance(envelope.get(key), dict):
            return envelope[key]
    result = envelope.get("result")
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        s = result.strip()
        if s.startswith("```"):
            s = s.split("```", 2)[1]
            if s.startswith("json"):
                s = s[4:]
            s = s.strip().rstrip("`").strip()
        return json.loads(s)
    raise RuntimeError(f"claude CLI envelope had no parseable result (keys: {sorted(envelope)})")


# Haiku intermittently fails to emit valid structured output (`--json-schema`) even on a trivial
# prompt -- observed live (smoke test 2026-06-27): same prompt succeeded one run, returned
# subtype `error_max_structured_output_retries` (exit 1, but WITH a valid JSON error envelope) the
# next. It's flaky, not deterministic, so one bounded re-invocation usually recovers it.
STRUCTURED_RETRY_SUBTYPE = "error_max_structured_output_retries"


def run_claude_cli(prompt: str, *, model: str = "haiku", effort: str = "low",
                   timeout: int = CLI_TIMEOUT_S, retries: int = 1, _run=subprocess.run) -> dict:
    """One headless WebSearch agent (bounded-retried on the flaky structured-output failure). Prompt
    piped on stdin (robust to long rosters). Returns the structured Wave-1 dict. `--strict-mcp-config`
    + `--disable-slash-commands` keep the scripted start lean (no MCP/skill auto-discovery);
    `--allowedTools WebSearch` is REQUIRED in print mode (it can't answer a permission prompt) and is
    the only tool granted. `_run` is injectable for tests (no live subprocess in CI).

    Parses stdout FIRST (the CLI returns exit 1 *with* a JSON error envelope for structured-output
    exhaustion), so a transient flake is told apart from a genuine non-JSON crash."""
    cmd = [
        "claude", "-p",
        "--model", model,
        "--effort", effort,
        "--output-format", "json",
        "--allowedTools", "WebSearch",
        "--json-schema", json.dumps(WAVE1_SCHEMA),
        "--strict-mcp-config",
        "--disable-slash-commands",
    ]
    last = "no attempts ran"
    for _attempt in range(retries + 1):
        proc = _run(cmd, input=prompt, capture_output=True, text=True,
                    timeout=timeout, cwd=str(paths.REPO_ROOT))
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            last = f"exit {proc.returncode}, non-JSON output: {(proc.stderr or proc.stdout)[:300]}"
            continue   # a real crash, not the structured envelope -- retry
        if envelope.get("subtype") == STRUCTURED_RETRY_SUBTYPE:
            last = f"structured-output retries exhausted: {envelope.get('errors')}"
            continue   # flaky -- re-invoke
        if envelope.get("is_error"):
            # a genuine error (not the flaky one) -- don't burn retries on it
            raise RuntimeError(f"claude CLI error [{envelope.get('subtype')}]: "
                               f"{envelope.get('errors') or envelope.get('result')}")
        # A denied WEBSEARCH means the agent couldn't actually search -- it would otherwise return
        # empty `schools` indistinguishable from a genuine "found nothing", silently degrading every
        # school to manual_flag for the wrong reason (the batch_00001 Wave-1 under-reporting failure
        # class). Fail loud on that specifically; other incidental tool denials are harmless.
        denials = envelope.get("permission_denials") or []
        if any("websearch" in json.dumps(x).lower() for x in denials):
            raise RuntimeError(f"claude CLI denied WebSearch (must be allowed in print mode): {denials}")
        return _extract_result_payload(envelope)
    raise RuntimeError(f"claude CLI failed after {retries + 1} attempt(s): {last}")


class ClaudeCLIProvider:
    """Wave-1 provider: headless `claude -p` WebSearch (subscription quota). Sits behind the pluggable
    provider contract -- `search(district, roster) -> wave1_result_dict` -- so a future Bright Data /
    Brave / cheap-OR-web-search provider drops in without touching gating/flatten/dedup (Section 7a)."""

    name = "claude-cli-websearch"

    def __init__(self, model: str = "haiku", effort: str = "low", timeout: int = CLI_TIMEOUT_S,
                 _run=subprocess.run):
        self.model, self.effort, self.timeout, self._run = model, effort, timeout, _run

    def search(self, district: dict, roster: list) -> dict:
        prompt = build_wave1_prompt(district, roster)
        return run_claude_cli(prompt, model=self.model, effort=self.effort,
                              timeout=self.timeout, _run=self._run)


def finish_from_wave1(batch: dict, district: dict, raw: dict, registry: dict) -> str:
    """The deterministic tail for one district -- reuses discover_stage2 verbatim (validate the seed
    echo, merge + gate Wave 1, conditional Wave 2 on the residual, flatten, atomic write, one registry
    record). Buffers the stage event into `registry`; the caller save()s. Returns the district outcome."""
    roster = D2.build_roster(district)
    D2.validate_wave1_result(raw, district)
    roster = D2.merge_wave1(roster, raw, district.get("domain", ""))
    residual = D2.residual_schools(roster)
    if residual:
        # Wave 2 = the DECIDED Claude WebSearch provider (issue #41: run_wave2's retired
        # openrouter_search default is gone -- this path must never silently reach it).
        _wave2_claude(district, residual, district.get("domain", ""))
    return D2.finish_district(district, roster, batch["batch_id"], registry)


def brightdata_then_serper(query: str, domain: str) -> tuple:
    """Wave-1 search WITH AVAILABILITY FAILOVER. Bright Data is primary (recurring-free Google). If it
    fails for ANY infrastructure reason (issue #29) -- billing/auth SystemExit, 429/non-JSON-zone
    TransientProviderError, network timeout/ConnectionError/5xx (requests.RequestException) -- fall
    back to Serper (banked credits) for THIS school. Both hit the SAME Google index, so this is
    redundancy for UPTIME, not a recall layer (a school Google has no page for is missed by both).
    If Serper ALSO billing-fails, that SystemExit propagates and halts the run (both Google providers
    exhausted); a transient Serper failure propagates as a plain exception (per-school degrade).

    Returns (provider, urls) -- only this cascade knows which provider actually served the query,
    and run_wave1 records it as the candidate's provenance (issue #30)."""
    try:
        return ("brightdata", DISC.brightdata_search(query, domain))
    except SystemExit as e:
        print(f"   [w1] Bright Data billing/auth failure -> Serper failover: {str(e)[:80]}")
    except (requests.RequestException, RuntimeError) as e:   # RuntimeError covers TransientProviderError
        print(f"   [w1] Bright Data {type(e).__name__} -> Serper failover: {str(e)[:80]}")
    return ("serper", DISC.serper_search(query, domain))


def _wave2_claude(district: dict, residual: list, domain: str, *, _run=subprocess.run) -> None:
    """Wave-2 on the genuine residual via Claude WebSearch -- a DIFFERENT index than Google, worth a
    shot on the schools where Bright Data/Serper (Google `site:`) found nothing, in case Claude's crawl
    surfaces a page Google missed or deprioritized (Serper here would just re-hit Google's same empty
    result). ONE `claude -p` call over all residual schools (reusing the ClaudeCLIProvider), mapped back
    per school_id and gated normally. A claude failure degrades the residual to zero (-> manual_flag),
    it never halts the run -- this is the speculative 'why not try' tier, not load-bearing."""
    try:
        raw = ClaudeCLIProvider(timeout=WAVE2_TIMEOUT_S, _run=_run).search(district, residual)
    except Exception as e:
        print(f"   [w2-claude] ERR {str(e)[:80]} -- residual stays manual_flag")
        raw = {"schools": []}
    by_id = {s["school_id"]: s.get("urls", []) for s in raw.get("schools", [])}
    for r in residual:
        urls = by_id.get(r["school_id"], [])
        r["wave2_invoked"] = True
        r["wave2_raw_urls"] = urls
        r["wave2_provider"] = "claude_websearch"   # real provenance for flatten() (issue #30)
        r["wave2_gated"] = D2.gate_urls(urls, domain)


def discover_district(batch: dict, district: dict, registry: dict, *,
                      wave1_search=None, wave2_runner=None) -> str:
    """Stage-2 discovery for one district (DECIDED 2026-06-28):
      Wave 1 = Bright Data (Serper failover on API failure)  ->  residual  ->
      Wave 2 = Claude WebSearch (a DIFFERENT index -- Serper would just re-hit Google's same empty
      result, so Serper's role is Wave-1 failover, NOT residual recall).
    Reuses discover_stage2's gate/residual/flatten/write/registry; buffers the stage event into
    `registry` (caller save()s); returns the district outcome. wave1_search / wave2_runner are
    injectable for tests (no live HTTP / no `claude -p`)."""
    wave1_search = wave1_search or brightdata_then_serper
    wave2_runner = wave2_runner or _wave2_claude
    geo = batch.get("discovery_scope") == "geo"   # #164: scope is a BATCH axis (scope-pure)
    domain = "" if geo else district.get("domain", "")
    roster = D2.build_roster(district, geo=geo)
    D2.run_wave1(roster, domain, wave1_search)
    geo_receipt = None
    if geo:
        # #164: tally -> derive -> re-gate. No derivation leaves every school fail-closed
        # (gate_urls' blank-domain refusal) -> the district honestly resolves manual_flag;
        # a derivation re-gates everything scoped AND becomes wave 2's scoping host below.
        derived, geo_receipt = D2.apply_geo_derivation(roster)
        domain = derived or ""
        if derived:
            # #164 review: write the derived host back onto the district dict — write_discovery
            # builds discovery.json/candidates.json's top-level `domain` from district.get("domain")
            # (blank at geo batch-composition time), and Stage 3/4 status views read that field;
            # without this the live manifests showed domain="" beside a correct derived_host.
            district["domain"] = derived
    residual = D2.residual_schools(roster)
    if residual and (not geo or domain):
        # geo without a derived host NEVER runs wave 2 (it would be an unscoped national
        # search — the #227 class); with one, wave 2 runs domain-scoped as normal.
        wave2_runner(district, residual, domain)
    return D2.finish_district(district, roster, batch["batch_id"], registry,
                              merge=batch.get("batch_type") == "follow-up",
                              geo_receipt=geo_receipt)


def load_batch_any(batch_ref: str) -> dict:
    """Accept either a batch receipt path or a bare batch_id (resolved under paths.QUEUE_DIR)."""
    p = Path(batch_ref)
    if not p.exists():
        p = paths.QUEUE_DIR / (batch_ref if batch_ref.endswith(".json") else f"{batch_ref}.json")
    if not p.exists():
        raise SystemExit(f"batch not found: {batch_ref} (looked at {p})")
    return D2.load_batch(p)


def _district_outcome_from_school_outcomes(outcomes: list) -> str:
    """Derive the per-district outcome from the per-school discovery outcomes in the cache
    (`found` / `manual_flag`): all found -> found_all, all flagged -> manual_flag_all, else partial."""
    if not outcomes:
        return "manual_flag_all"
    if all(o == "found" for o in outcomes):
        return "found_all"
    if all(o != "found" for o in outcomes):
        return "manual_flag_all"
    return "found_partial"


def status_for_batch(batch: dict) -> list:
    """Read-only Stage 2 observability for a batch, FROM THE DB cross-stage cache (the working store the
    Stage-2 finish hook keeps fresh — governance §7a-A). Lifecycle from disk (a district is `done` iff
    its discovery.json exists, `todo` otherwise — the filesystem is the authoritative DATA source); the
    metrics (Wave-1/Wave-2 found counts, manual_flag schools, deduped candidate count, outcome) come
    from `discovery_school`/`candidate`. SELF-HEALING: a district discovered BEFORE this cache hook
    existed (e.g. batch_00002/00003) has no rows yet, so its discovery.json is ingested on first view."""
    ids = [d["district_id"] for d in batch["districts"]]
    ddirs = {d["district_id"]: D2.lea_dir(d["district_id"], d["name"]) for d in batch["districts"]}
    done_ids = [did for did in ids if (ddirs[did] / "discovery.json").exists()]

    with gdb.session_scope() as con:
        CI.ensure_cache_schema(con)
        cached = {r[0] for r in con.execute(
            text("SELECT DISTINCT district_id FROM discovery_school WHERE district_id = ANY(:ids)"),
            {"ids": done_ids or [""]})}
    # Lazy self-heal: backfill the cache for any done-on-disk district missing from it (best-effort).
    for did in done_ids:
        if did not in cached:
            CI.cache_discovery(ddirs[did])

    schools_by_did: dict = {}
    cand_count: dict = {}
    with gdb.session_scope() as con:
        for r in con.execute(text(
                "SELECT district_id, school, outcome, wave1_n_kept, wave2_n_kept "
                "FROM discovery_school WHERE district_id = ANY(:ids)"),
                {"ids": done_ids or [""]}).mappings():
            schools_by_did.setdefault(r["district_id"], []).append(dict(r))
        for did, n in con.execute(text(
                "SELECT district_id, COUNT(*) FROM candidate WHERE district_id = ANY(:ids) "
                "GROUP BY district_id"), {"ids": done_ids or [""]}):
            cand_count[did] = n

    out = []
    for d in batch["districts"]:
        did, name = d["district_id"], d["name"]
        row = {"district_id": did, "name": name, "state": d.get("state", ""),
               "domain": d.get("domain", "")}
        if did not in done_ids:
            row.update(status="todo", outcome=None, n_schools=None, wave1_found=0,
                       wave2_found=0, manual_flags=[], n_candidates=None)
            out.append(row)
            continue
        schools = schools_by_did.get(did, [])
        w1 = sum(1 for s in schools if (s["wave1_n_kept"] or 0) > 0)
        w2 = sum(1 for s in schools if (s["wave2_n_kept"] or 0) > 0)
        flags = [s["school"] for s in schools if s["outcome"] == "manual_flag"]
        out.append({**row, "status": "done",
                    "outcome": _district_outcome_from_school_outcomes([s["outcome"] for s in schools]),
                    "n_schools": len(schools), "wave1_found": w1, "wave2_found": w2,
                    "manual_flags": flags, "n_candidates": cand_count.get(did)})
    return out


def rollup(districts: list) -> dict:
    """Batch-level counts for the status header."""
    done = [d for d in districts if d["status"] == "done"]
    return {
        "total": len(districts),
        "done": len(done),
        "todo": sum(1 for d in districts if d["status"] == "todo"),
        "found_all": sum(1 for d in done if d["outcome"] == "found_all"),
        "found_partial": sum(1 for d in done if d["outcome"] == "found_partial"),
        "manual_flag_all": sum(1 for d in done if d["outcome"] == "manual_flag_all"),
        "manual_flag_schools": sum(len(d["manual_flags"]) for d in done),
    }


def run_batch(batch: dict, *, actor: str = "auto:stage2", on_event=None,
              wave1_search=None, wave2_runner=None) -> dict:
    """Deterministic Stage 2 (SERP) for an approved batch: reconcile (filesystem is truth; a
    registry-ahead-of-disk CONTROL FAILURE raises SystemExit and halts), then per todo district run
    Wave 1 = Bright Data with Serper failover -> Wave 2 = Claude WebSearch on the residual -> atomic
    write -> one registry record. SEQUENTIAL (one registry writer, no race; providers are fast enough
    at batch scale). Records a per-district `dispatched` event up front and `completed`/`failed` per
    district. `on_event(kind, payload)` is the progress hook the console job feed consumes.
    `wave1_search`/`wave2_runner` are injectable for tests.

    `batch` is the resolved working-store dict ({batch_id, districts:[...]}) — the caller passes it
    from the DB (the console, via _batch_from_db) or the receipt (the CLI, via load_batch_any), so
    the runner never reaches for the on-disk receipt itself. Same contract as Stage 3/4 (#526)."""
    batch_id = batch["batch_id"]
    with gdb.session_scope() as _con:      # #168: never run a stage on a terminal abandoned batch
        BG.assert_runnable(_con, batch_id)

    def emit(kind, **payload):
        if on_event:
            on_event(kind, {"batch_id": batch_id, **payload})

    # Per-district saves defer the district_status.json regeneration (export=False) — re-exporting the
    # FULL log per district is O(N²) over a run (issue #49). One explicit DS.export() runs at the end
    # (in a finally, so a crash mid-run still leaves the backup current with the committed events).
    try:
        registry = DS.load()
        todo, skipped = D2.reconcile(batch, registry)
        DS.save(registry, export=False)
        emit("reconciled", todo=[d["district_id"] for d in todo],
             skipped=[d["district_id"] for d in skipped])
        if not todo:
            return {"batch_id": batch_id, "todo": 0, "skipped": len(skipped), "results": []}

        # Mark every todo district dispatched (one buffered event each, single flush) so the console's
        # event-log projection shows "in flight" immediately.
        registry = DS.load()
        for d in todo:
            DS.record_stage(registry, d["district_id"], d["name"], d["state"], stage_name="discover",
                            event_type="dispatched", actor=actor, batch_id=batch_id)
            emit("dispatched", district_id=d["district_id"], name=d["name"])
        DS.save(registry, export=False)

        results = []
        for d in todo:
            did = d["district_id"]
            registry = DS.load()
            try:
                outcome = discover_district(batch, d, registry,
                                            wave1_search=wave1_search, wave2_runner=wave2_runner)
                DS.save(registry, export=False)
                results.append({"district_id": did, "name": d["name"], "outcome": outcome})
                emit("completed", district_id=did, name=d["name"], outcome=outcome)
            except SystemExit:
                raise   # CONTROL FAILURE / billing-auth halt -- never swallow
            except Exception as e:
                # Full stack to job stdout (#452) -- the persisted note stays bounded, but a deep
                # failure must leave its location somewhere findable.
                traceback.print_exc()
                registry = DS.load()
                DS.record_stage(registry, did, d["name"], d["state"], stage_name="discover",
                                event_type="failed", actor=actor, batch_id=batch_id,
                                notes=f"{type(e).__name__}: {str(e)[:200]}")
                DS.save(registry, export=False)
                results.append({"district_id": did, "name": d["name"], "outcome": "error",
                                "error": f"{type(e).__name__}: {str(e)[:200]}"})
                emit("failed", district_id=did, name=d["name"], error=str(e)[:200])
        return {"batch_id": batch_id, "todo": len(todo), "skipped": len(skipped), "results": results}
    finally:
        DS.export()   # one full district_status.json regeneration per run (issue #49)


def main():
    ap = argparse.ArgumentParser(description="Stage 2 (Discover) SERP runner -- REQ-104")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="run Bright Data -> Serper discovery for an approved batch")
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
