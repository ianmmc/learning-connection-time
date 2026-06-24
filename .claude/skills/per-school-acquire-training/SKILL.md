---
name: per-school-acquire-training
description: Discovery+capture TRAINING loop (steps 1-5 of the acquisition pipeline, NO extraction). Run a seeded stratified batch of untouched NCES districts through wave discovery + tiered capture, sort captures by Haiku-determined topology, for human verification of discovery/capture/classifier quality. Use to build a labeled scorecard before extraction.
---

# /per-school-acquire-training — Discovery + Capture Training Loop

> **OBSOLETE (2026-06-23).** Superseded entirely: queue-building is Stage 1's `queue_batch.py` (built and CP-A-validated); discovery is `.claude/skills/stage2-discover/` (built 2026-06-23, reads Stage 1's `batch_NNNNN.json` directly). This skill's discovery step has the same flaw as `per-school-acquire`'s — it never consumed Stage 1's batch output. Kept for reference only — do not run as-is.
>
> **2026-06-22: step 1 below is stale.** `training_batch.py` has been archived (superseded by Stage 1's real implementation, `infrastructure/acquisition/stage1_queue/queue_batch.py` — see `docs/ACQUISITION_PIPELINE.md` Stage 1). Per CLAUDE.md, this whole skill is premature/reference-only and not the active runbook; it hasn't been updated to call the new script. Use `queue_batch.py <N>` directly for now (writes `data/acquisition/queue/batch_<NN>.json`, a different schema than the `batch.json` this skill describes) until this skill is revised.

Runs **only steps 1–5** of `per-school-acquire` (wave discovery → capture; **no extraction, no council, no scoring**). Purpose: isolate and *measure* the upstream gates — **did the waves find a page, did capture render it legibly, did Haiku classify topology correctly** — on genuinely cold NCES districts (no prior manual data). Cheap: Claude WebSearch (subscription) + OpenRouter search + local Playwright only. **No per-token extraction cost.**

**Freeze the config across a run of batches** (waves = Claude→OpenRouter, Perplexity off, tiered capture) so batches are comparable; the version is recorded in each `batch.json`.

## Steps

1. **Pick the batch.** `python3 infrastructure/acquisition/discovery/training_batch.py <N>` — seeded (seed = batch number, reproducible), stratified by size (~2 large / 6 mid / 4 small per 12), excludes every touched district. Writes `data/acquisition/training_batches/batch_<NN>/batch.json`.

2. **Roster + queries.** For each district in `batch.json`, build per-school queries (reuse `per_school_run.py` logic / `school_sampling.roster`). Cap schools per band (default 12).

3. **Wave 1 — Claude WebSearch + topology (AGENT'S JOB).** Spawn one Haiku subagent per district: WebSearch each school's query scoped by `allowed_domains`=district domain; collect URLs; **also classify topology STRICTLY from search results** (`hub` / `per_school` / `none`) — do NOT read pages. Write `claude_urls.json` = `{"topology": "...", "<school>": [urls...]}`.

4. **Wave 2 — OpenRouter residual.** OpenRouter `gpt-4o-mini-search` only on schools Wave 1 left empty. Merge → dedup across schools.

5. **Capture (tiered, local Playwright)** the deduped distinct pages: text-layer → screenshot+OCR fallback.

6. **Sort output by Haiku topology + emit decision log.** Write captures to:
   `data/acquisition/training_batches/batch_<NN>/<topology>/<district_id>_<name>/` where `<topology>` ∈ `hub` / `per_school` / `none`. Copy the human-viewable capture artifacts (PDF/PNG/txt) there. **Per district write `result.json`**: which **wave** satisfied each school (claude / openrouter / manual-flag), Haiku's **topology** call, per-page **source tier** (text-layer / screenshot-ocr / pdf), and capture ok/empty. This is the learning signal — verify the *files* AND the *decisions*.

7. **Hand off for verification.** Tell the user the batch is ready. They sort each district into:
   - `good/` — capture legible AND topology correct
   - `wrong-topology/` — usable page but Haiku misclassified hub↔per_school
   - `unusable/` — junk / empty / illegible capture
   - `deferred/` — real but hard (Parent Handbook, accordion/expanding page, image-layout)

8. **Score the batch (after user sorts).** Compute + append to a running scorecard (`training_batches/SCORECARD.md`): wave hit-rate (% districts with ≥1 captured page), **Haiku topology accuracy** (user label vs its call, from `result.json` + the user's good/wrong-topology split), capture-tier mix, and the good/unusable/deferred breakdown. Note the frozen config version. Then pick the next batch.

## Notes
- **No extraction** — this loop stops before any council/model extraction; that keeps the signal clean (upstream gates only) and the cost near-zero.
- `none`-topology and manual-flag districts are themselves data (discovery misses) — keep them, don't silently drop.
- Same agent-in-the-loop constraint as `per-school-acquire`: Wave 1 needs the agent (Haiku WebSearch subagent).
- Batches are reproducible by seed; if the discovery/capture config changes, start a new frozen run (earlier batches aren't comparable).
