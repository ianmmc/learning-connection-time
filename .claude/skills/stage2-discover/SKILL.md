---
name: stage2-discover
description: SUPERSEDED (2026-07-06) — Stage 2 now runs as a deterministic headless SERP cascade (python3 -m infrastructure.acquisition.stage2_discover.headless run <batch_id>), no subagents. Do NOT follow this skill's procedure; see the header note. Kept for the 2026-06-23 design history only.
---

# /stage2-discover — Stage 2 (Discover)

> **SUPERSEDED (2026-07-06, kept for history — same pattern as the per-school-acquire headers).**
> This skill describes the retired agent-in-the-loop architecture: Haiku WebSearch subagents as
> Wave 1 and the OpenRouter AI-search as Wave 2. The live Stage 2 (REQ-104, decided 2026-06-28) is a
> **deterministic SERP cascade** — Wave 1 = Bright Data SERP → Serper failover, Wave 2 = Claude
> WebSearch (`claude -p`) on the residual — run headlessly, no subagents:
> `python3 -m infrastructure.acquisition.stage2_discover.headless run <batch_id>` (or the console's
> Stage-2 trigger / the follow-up auto-flow, #157). No `OPENROUTER_API_KEY` is involved anywhere in
> Stage 2 anymore (the retired providers + `_openrouter_key` were removed, #87); Wave 2 needs only the
> `claude` CLI. Also superseded below: the "never redo" rule — a **follow-up batch** now redoes
> discovery deliberately, with union-merged manifests (#174). Authority:
> `STAGE2_DISCOVER_DESIGN.md`.

Written explicitly so the procedure survives across sessions without relying on conversational nuance (the full design was negotiated in detail on 2026-06-23 — see `docs/ACQUISITION_PIPELINE.md` Stage 2 and `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE2_DISCOVER_DESIGN.md` §6 for the decision trail; this skill is the executable form of that design, not a paraphrase of it).

**Supersedes** `.claude/skills/per-school-acquire/` and `per-school-acquire-training/` — both obsolete, see their headers.

**Why a skill, not a script:** Wave 1 (Claude WebSearch) can only run from inside the agent — it spawns a Haiku WebSearch subagent, which `discover_stage2.py` cannot do on its own. Every other step (reconciliation, gating, Wave 2, flatten, write, registry) is pure deterministic script, invoked via `infrastructure/acquisition/stage2_discover/discover_stage2.py`.

## Non-negotiable invariants (re-state these to yourself before running; do not silently relax any of them)

1. **Never recompute band membership from NCES CSV.** Per-school targeting data comes ONLY from the Stage 1 batch's `schools_by_band` — re-deriving it would discard every Stage 1 CP-A fix.
2. **The filesystem is authoritative, not the registry.** A district's `discovery.json` existing in `data/raw/lea-website-captures/<id>_<slug>/` IS "done." The registry is a cache of that fact.
3. **If `reconcile` reports a control failure (registry says Stage 2+ done, disk doesn't have the file), STOP THE ENTIRE RUN immediately.** Do not proceed to any other district in the batch. Report the exact error and wait for explicit instruction.
4. **Subagents never write to `data/raw/`.** They return findings as a result message only; this script does the one atomic write per district.
5. **Subagents return ONE strict, machine-parseable JSON block — never prose for you to hand-transcribe.** You copy that JSON out of the subagent's result verbatim; you do not retype, summarize, or "clean up" its contents.
6. **Wave 2 (OpenRouter) is a script call, never a subagent, and only runs when a residual exists.** If Wave 1 + gating already satisfied every school in a district, skip Wave 2 entirely — `discover_stage2.py finish` already does this check; you don't need to decide it yourself.
7. **A redo is a deliberate, explicitly-requested action only.** Never re-run discovery for a district whose `discovery.json` already exists unless the user has explicitly asked for that specific district to be redone. The reconciliation step is what normally prevents this from ever coming up.
8. **One registry write per district, only from this orchestration (never from a subagent).** `discover_stage2.py finish` does this for you — don't call `district_status` functions yourself outside this script.

## Inputs

- A Stage 1 batch file: `data/acquisition/queue/batch_NNNNN.json` (must already be CP-A-approved by the user — confirm this if it isn't obvious from context).
- Concurrency: **hard cap of 2 concurrent subagents.** Do not raise this on your own judgment — we'll revise this skill explicitly when it's time to raise it. Watch for API rate-limit signals (429s, degraded/empty WebSearch results) even at 2, and drop to running subagents one at a time if you see them.
- **`OPENROUTER_API_KEY` (needed only if a district has a residual).** `discover.py::_openrouter_key()` falls back to reading it directly from `config/secrets.local.json` if it isn't already in the environment — no manual export needed, and this works even across separate tool-call invocations where shell state doesn't persist. If it's genuinely missing from `secrets.local.json` too, Wave 2 fails per-school (caught, logged, treated as zero URLs found) rather than crashing — but that silently degrades every residual school to `manual_flag` for the wrong reason, so if you see every Wave-2-invoked school come back empty, check this first.

## Procedure

### Step 0 — Reconcile (always run first, before dispatching anything)

```
python3 infrastructure/acquisition/stage2_discover/discover_stage2.py reconcile data/acquisition/queue/batch_NNNNN.json
```

- If this exits with `CONTROL FAILURE`: **stop.** Do not run `roster` or dispatch any subagent for this batch. Report the error verbatim to the user.
- Otherwise it prints two lists: `skip` (already done, filesystem-confirmed — do nothing further for these) and `todo` (districts that need Wave 1). Only `todo` districts proceed to Step 1.

### Step 1 — Wave 1: one Haiku subagent per district

For each `todo` district, **up to 2 at a time** (use the Agent tool with `run_in_background: true`, refilling the in-flight pool as subagents complete — never more than 2 running at once, never more than one district per subagent):

1. Get that district's roster and domain:
   ```
   python3 infrastructure/acquisition/stage2_discover/discover_stage2.py roster data/acquisition/queue/batch_NNNNN.json <district_id>
   ```
2. Spawn a subagent (model: haiku) with **exactly** this brief — fill in the bracketed parts from the roster output, and do not add extra instructions beyond what's below:

   > First, call your ToolSearch tool with query "select:WebSearch" to load the WebSearch tool — it is deferred and not callable until you do this. Then use ONLY WebSearch for the searches below; do not read, fetch, or write any files, and do not use any other tool.
   >
   > You will search the web for bell-schedule pages for schools in one school district.
   >
   > District: `<name>` (`<district_id>`), domain: `<domain or "none">`.
   >
   > For each row below, call WebSearch with the `query` parameter set to **exactly** the quoted text after "SEARCH FOR:" — nothing added, nothing removed. **Do not include the school_id, any NCES number, or any other identifier in the WebSearch query itself** — the school_id is given only so you can label your results correctly in the JSON you return; a search containing it would return NCES/SEA database pages, not the district's own site. If a domain is given, set `allowed_domains` to `["<domain>"]` for every search; if no domain is given, search unscoped. Do not guess URLs — only report URLs that WebSearch actually returned.
   >
   > Schools (school_id is a label for your output only, never part of the search):
   > - school_id `<school_id>` — SEARCH FOR: `"<query>"`
   > - school_id `<school_id>` — SEARCH FOR: `"<query>"`
   > ... (one row per roster entry)
   >
   > When you have run a search for every school, respond with **ONLY** this JSON, in a single fenced code block, and nothing else (no other prose before or after it):
   > ```json
   > {"district_id": "<district_id>", "domain": "<domain or empty string>",
   >  "schools": [{"school_id": "<id>", "urls": ["<url>", "..."]}, ...]}
   > ```
   > Include EVERY school listed above, even if its `urls` list is empty (a school with no results found must still appear with `"urls": []`, not be omitted).

3. When the subagent returns, extract its JSON block verbatim and write it to `data/acquisition/_scratch/wave1/<district_id>.json` (create the directory if needed). This is scratch working state, not the audit trail — it gets superseded by `discovery.json` once `finish` runs.

### Step 2 — Finish: deterministic gate → conditional Wave 2 → flatten → write → registry

For each district whose Wave-1 scratch file is ready:

```
python3 infrastructure/acquisition/stage2_discover/discover_stage2.py finish data/acquisition/queue/batch_NNNNN.json <district_id> data/acquisition/_scratch/wave1/<district_id>.json
```

This single command does everything else: validates the subagent's district_id/domain echo (fails loud on mismatch — if this happens, do not retry blindly, investigate why the subagent's result doesn't match what it was given), gates Wave 1's URLs, checks for a residual, runs Wave 2 only if one exists, flattens/dedups, writes `discovery.json` + `candidates.json` to `data/raw/lea-website-captures/<id>_<slug>/`, and writes the registry outcome. It prints the final outcome (`found_all` / `found_partial` / `manual_flag_all`).

Once `finish` succeeds for a district, you may delete its scratch file (`data/acquisition/_scratch/wave1/<district_id>.json`) — the durable record now lives in `discovery.json`.

### Step 3 — Report

Summarize for the user: how many districts reached each outcome, which specific schools (if any) ended up `manual_flag` (for visibility — these need eventual human follow-up, tracked via the registry per REQ-072, not a separate file), how many Wave-2 calls were actually made vs. skipped, and any anomalies encountered.

### Stopping point

This skill ends once Step 3's report is delivered. There is currently nothing to chain into — Stage 3 (Capture) doesn't exist yet. Once it does, per the design in `ACQUISITION_PIPELINE.md`, the deterministic chain (gate → Wave 2 → flatten → write → registry) will be able to invoke Stage 3 directly, since capture has no agent-judgment step either — but that wiring is not part of this skill until Stage 3 is built.

## Notes

- **The concurrency cap (2) is fixed — do not raise it on your own judgment.** If you hit rate-limit errors or visibly degraded WebSearch results even at 2, drop to running subagents one at a time; don't push through. Raising the cap is a deliberate edit to this skill, made when we decide it's time, not a per-run decision.
- **A school with `outcome: "manual_flag"` is not an error** — it means neither Claude WebSearch nor OpenRouter found anything for it. That's an expected, recorded outcome, not a bug to chase.
- **Never invent or guess a URL.** If a subagent's result looks suspicious (e.g., URLs unrelated to the school/domain it was given), don't silently accept it — flag it to the user rather than passing it through to `finish`.
- **WebSearch is a deferred tool for subagents, exactly as it is for the main agent — it does NOT appear in a subagent's tool list until it calls `ToolSearch(select:WebSearch)` first.** Confirmed by direct test (2026-06-23): a subagent given the Wave-1 brief without this instruction reported having no WebSearch tool at all (one variant claimed only WebFetch, another claimed neither). This is why the prompt template above opens with the ToolSearch step — do not remove it as "unnecessary," it is the fix for a real failure, not a defensive guess.
