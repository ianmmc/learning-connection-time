# Project Terminology Guide

**Last Updated:** 2026-06-25

The canonical vocabulary for the Learning Connection Time (LCT) project — the file an auditor or new
developer should read first. It standardizes the terms used across `docs/ACQUISITION_PIPELINE.md`,
the design notes, the database, and the data artifacts.

> **Two eras live side by side.** The database and older docs contain records/terms from the original
> **enrichment-campaign** era (state-by-state manual + Crawlee/Ollama collection, retired); the active
> work is the stage-based **acquisition pipeline** (`infrastructure/acquisition/`). Current vocabulary
> comes first; the legacy terms are preserved (clearly marked **LEGACY**) at the end so old records and
> docs remain readable. The retired Crawlee+Ollama code was archived 2026-06-25 to
> `data/archive/crawlee-ollama-era-superseded-20260625/`.

---

## 1 · The metric

### Learning Connection Time (LCT)
`LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment` — minutes of
teacher-time per student per day. Computed over nested staffing scopes
(`teachers_only ⊂ teachers_core ⊂ instructional ⊂ instructional_plus_support ⊂ all`); **`instructional`
is the recommended primary scope**.

### Daily Instructional Minutes — Gross vs. Net
- **Gross (bell-to-bell) — the CURRENT target:** `end − start`, **no deductions**. What we extract and
  store today; the ground truth is also gross. Overstates true instructional time by ~30–60 min/day
  (lunch + passing + recess), inconsistently across districts, so it is always labeled
  **`gross_bell_to_bell`** (`minutes_basis` field).
- **Net (deferred):** gross − lunch − passing − recess. More accurate, much harder to extract; **not
  attempted yet**. We never apply *assumed* deductions (a guessed 30-min lunch) — assumed precision is
  fake precision.

### The INVARIANT (extraction)
**Extractors read TIMES; deterministic Python computes MINUTES and the MODE.** Models return only
per-school facts `{start_time, end_time, grade_level, school_name}`; code does `gross = end − start` and
the per-band exact mode. A model is **never** asked to compute minutes or pick a "typical" schedule.

---

## 2 · Data status & quality

### Enriched
A district/school for which we hold an **actual** bell-to-bell schedule (from an authoritative district
or school source), **not** a statutory minimum. The goal of the pipeline. *(Counts toward progress.)*

### Statutory fallback
A state's **minimum** instructional-time requirement, used as a default when no actual schedule is
found. Stored with `method = statutory_fallback`; **NOT enriched**, does not count as collected data.
The thing the pipeline exists to replace with real data.

### Confidence levels
`High` (specific times from an official source) · `Medium` (school-sampled / reasonably representative)
· `Low` (single school standing in for a diverse district) · `Assumed` (statutory only, no real schedule).

---

## 3 · The acquisition pipeline — structure

### Stage / the 9 stages
The pipeline is built and walked **stage by stage** with human checkpoints. Canonical doc:
`docs/ACQUISITION_PIPELINE.md`. Stages: **1 Queue · 2 Discover · 3 Capture · 4 Local processing ·
5 Local filtering · 6 Dispatch · 7 Council extraction · 8 Aggregate · 9 Write**.

### Checkpoints (CP-A / CP-B / CP-C) — human-in-the-loop
Deliberate high-supervision gates: **CP-A (Queue)** — are the right schools/bands targeted? · **CP-B
(Input)** — is the captured input legible and relevant (the critical gate, before any paid call)? ·
**CP-C (Output→Write)** — are the per-school times correct + honestly labeled before the DB write?

### Batch / `batch_NNNNN.json`
One run's worth of targeting, produced by Stage 1 (`data/acquisition/queue/`). Carries the selected
districts + per-band school lists + the NCES denominator. `batch_00001` is the live working batch.

### District-status registry / `district_status.json`
The cross-stage progress ledger (`data/acquisition/status/`): each district's `furthest_stage` and
outcome. `already_attempted()` excludes a district from re-queue once it has reached **Stage 3
(Capture)+** — searched/queued-only districts stay eligible.

---

## 4 · Stage-specific vocabulary

### Stage 1 — Queue (NCES targeting)
- **LEA** — Local Education Agency (a school district), NCES's unit. **`ccd_lea` / `ccd_sch`** — NCES
  Common Core of Data LEA-level and school-level files (`ccd_lea_029` / `ccd_sch_029_2425`).
- **Band** — grade tier: **elementary / middle / high**. **`LEVEL`** — NCES's per-school category
  (`Elementary`/`Middle`/`High`/`Secondary`/`Other`/…); **LEVEL-primary classification** trusts a clean
  LEVEL over grade-range overlap. **`bands_for()` / `recursive_band_groups()`** — band-assignment from
  grade spans when LEVEL is ambiguous.
- **Claimed bands** — the bands an LEA's overall grade span covers. **Grade-span integrity (Rule 7)** —
  exclude+flag a district whose claimed band has **zero** covering schools at the school level.
- **CTC / shared-service entity** — career-technical / service agencies, excluded from sampling
  (`is_shared_service_entity`).
- **Cross-band overlap minimization** — a K-8/K-12 school can satisfy multiple bands; bands are sampled
  **most-constrained-first** so one school isn't drawn into several bands unnecessarily.
- **Cap** — ≤ **12 schools per band** (seeded random sample over the cap; full census below it).
- **NCES denominator / `nces_school_counts`** — per district, `{total, by_level}`: the count of schools
  meeting our eligibility (**open · regular · non-virtual · non-preschool**, the shared `_eligible()`
  predicate), grouped by **raw `ccd_sch` LEVEL**. The **topology denominator** — our-criteria count,
  *not* `ccd_lea`'s self-reported figure; captured at Stage 1 with `nces_year` for provenance.

### Stage 2 — Discover (recall)
- **Discovery = a recall problem** — find *a* schedule page; capture verifies it. Run in cost-ascending
  **waves** with stop-when-found (not a council): **Wave 1** Claude WebSearch (Haiku subagent) → **Wave 2**
  OpenRouter `gpt-4o-mini-search` → flag for manual.
- **`gate()`** — deterministic filter rejecting off-domain / news / aggregator URLs. **Residual** — a
  school still unsatisfied after gating; only residuals go to Wave 2.
- **`discovery.json`** — per-district discovery output (the `schools[]` roster + raw per-school URLs).
- **`candidates.json`** — the Stage 2 **D_FLATTEN** output: the deduped, capture-ready URL list, each
  candidate carrying its **`schools[]`** (the URL→school map) and `tools[]` (which wave found it).

### Stage 3 — Capture (tiered, local Playwright)
- **Capture** — render/fetch each candidate, writing per-URL artifacts to
  `data/raw/lea-website-captures/<district>/captures/<md5(url)>/` (`page.txt` innerText, `page.png`
  screenshot, `page.pdf` Chromium print). **`captures.json`** records each. **Drive Tier 1/2** —
  Google Drive/Docs export handling (Tier 1 unauthenticated; Tier 2 OAuth, deferred). **Modal dismissal**
  — hide cookie/consent overlays before capture.
- **Emergent candidate** — a schedule-keyword link found *in* a rendered page (one hop, no recursion) →
  a new candidate Discovery never surfaced. **Emergent record** — a captured URL that was **never a
  planned candidate** (`is_emergent`), i.e. discovered during capture.
- **Fingerprint** — per-record raw hosting/CMS signals (`final_host`, `server`, `resource_hosts[]`,
  `meta_generator`, `js_dependent`, **`cms_hint`**). **`CMS_HOSTS`** — the curated set of *school-district
  CMS vendors* (SharpSchool, Apptegy, Educational Networks, …); a `cms_hint` is a host-suffix match
  against it. Additions are **human-in-the-loop, school-vendor-only** (never a general host/CDN).
- **DOM segmentation / de-chrome (PLANNED)** — segment a page's `<header>`/`<footer>`/`<nav>` vs `main`
  at render time into separate representations (`page.main/header/footer/nav.txt`), so CMS **chrome**
  (a footer "Building Hours", a school-switcher nav) can't pollute signals. **Landmark** — the
  semantic/ARIA selectors used to identify chrome.

### Stage 4 — Local processing
- **Representation** — one extracted view of a captured artifact: a text file from a tool, an image, a
  rasterized PDF page. A record has many; they can disagree. **Usable text** — passes a weak length +
  printable-char bar (≥120 chars) — "is this recognizable text," *not* "is this a schedule" (that's
  Stage 5). **Tool roster** — `pdftotext -layout`, `pdfplumber` (lines), `camelot` (stream/hybrid),
  `tesseract`; the rule is **run every kept tool on every applicable input, keep everything**.
- **Raster** — `raster_p-N.png`, a PDF page rendered to image for OCR/inspection. **`processed.json`** —
  per-record list of representations (each with `usable`, `n_chars`, `n_times`, a `text_file` reference).

### Stage 5 — Local filtering / CP-B review
- **Signal** — a deterministic, no-AI measurement over a representation's text (`n_times`,
  `n_times_in_window`, `proximity_pairs`, `positive_kw`, `negative_kw`, `instructional_time`,
  `roster_school_names_hit`, `visual_text_gap`, per-page time counts, …). The script's raw material.
- **Tier (A–D)** — the script's confident, sortable likelihood: **A** strong target candidate · **B**
  plausible · **C** unlikely/negative-leaning · **D** drop-candidate (no times/unusable).
- **Category hypothesis** vs **label** — the *hypothesis* is the script's weak guess at the primary
  label (noisy, hidden in the UI until the human labels, to avoid anchoring); the **label** is the
  human's ground-truth judgment. (Full label taxonomy lives in `STAGE5_FILTER_DESIGN_2026-06.md`:
  target-shape labels, non-target-reason labels incl. `community_calendar`/`embedded_feed`, and flags
  incl. `duplicate`, `buried_in_long_doc`, `building_hours_visible`, `target_image_only`.)
- **Topology** — a district's schedule *shape*, kept as two separate values: **`guessed_topology`**
  (from signals — noisy) and **`labeled_topology`** (from human labels + NCES — **the truth**). Values:
  **`single_school`** (NCES says 1 school) · **`per_school`** · **`district_hub`** (one page covers all)
  · **`mixed`** · **`incomplete_coverage`** (one bell schedule but NCES says >1 school) · **`none_found`**
  · **`unknown`**.
- **Near-duplicate clustering** — group a district's content-similar records so the reviewer labels the
  **cluster representative** once; labels cascade to members. **Split** — a durable human override
  pulling a member out of its cluster (survives re-ingest). **Duplicate / `content_hash`** — exact
  byte-identical dedup (a subset of clustering).
- **Building hours (red herring)** — a footer's *building/office* open hours mimic a student start/end
  pair but are **not** the student day; flagged `building_hours_visible`.

### Stages 6–9 — Dispatch, Council, Aggregate, Write
- **Council** (extraction = correctness) vs **waves** (discovery = recall). A small, **cross-family**
  set of non-reasoning models reads the *same* captured input. Candidate set: Gemini 2.5 Flash, Mistral
  Large 2512, DeepSeek V3.2, Mistral Small 24B, Gemini Flash-Lite, Qwen3-235B.
- **Consensus** — agreement on the per-school **`(start, end)` pair, cross-family, within ±15 min**.
  Same-family agreement is **not** consensus (shared blind spots → false consensus).
- **Mode** — the deterministic per-band exact modal `(start,end)` chosen from the council's per-school
  facts. **Per-school extract→aggregate** — extract per file (never concat-and-truncate), then aggregate.
- **Reader-routing** (outcome-based, route the reader to the input): **Tier 1** plain text → **Tier 2**
  `page.pdf()` + `pdftotext -layout` (multi-column) → **Tier 2.5** OCR a clean image → **Tier 3** vision
  (Gemini Flash / Mistral Large read JS/image/scan pages text paths miss). Trigger = "did the cheap
  reader recover usable content," not file format.

---

## 5 · The learning loop & configuration

### Config-as-data / tunables / knobs
The pipeline's adjustable inputs — `CMS_HOSTS`, keyword lists, the Stage-4 tool roster, the de-chrome
landmark list, search-query templates, council composition — externalized from code into versioned JSON
under `infrastructure/acquisition/common/config/` (read by both Python and Node). Each entry carries
**per-entry provenance** (`added`, `rationale`, `evidence`, `approved_by`, `loop_tier`) so a tunable
*is* its own decision log.

### Loop tiers (cost of re-measuring a change)
- **Tier 0 — Re-derive** (free, offline, same evidence): pure functions over stored artifacts — Stage 5
  signals/keywords/tiers (re-ingest), `cms_hint` (recompute), Stage 4 roster (re-process).
- **Tier 1 — Backfill** (one re-visit, no API/$): needs render-time data we didn't persist — de-chrome
  landmarks (`backfill-segments`); drops to Tier 0 downstream after.
- **Tier 2 — Re-acquire** (metered, stochastic): changes what we fetch — search queries, search APIs,
  council config.
- **Tier 3 — Re-sample** (changes the cohort): Stage 1 queue criteria — re-running yields *different*
  districts, so you validate the *principle*, not a before/after on a fixed set.
- **Design heuristic:** engineer knobs *down* the tiers (capture raw facts early so classification is a
  cheap re-derive).

### Measurement harness / scorecard
The **scorecard** is the *result* of running a **config state** over the data and comparing programmatic
outputs to the human labels — metrics at representation / url / district granularity (tier
precision-recall, category accuracy, topology agreement). A score is only meaningful as the tuple
**(config × label-set × data snapshot) → metrics**, so each scorecard **stamps all three input
fingerprints** (config version, label-set hash, ingest snapshot) to be reproducible/auditable. Run
**on-demand + at batch completion** (or after *n* updates — itself a knob), never per-label-write.

### Provenance / lineage
The end-to-end chain that lets us **explain why** a district shows real daily instructional time rather
than statutory fallback: page → extraction → signals → config version → human labels. Provenance-rich
config, fingerprinted scorecards, and preserved labels are its building blocks (the project's
transparency principle, defensible to an auditor).

### `DATA_ROOT` / paths module
A single settings indirection (`infrastructure/acquisition/common/paths.py`) defining every runtime
location, so generated state stays in a consolidated, **relocatable** `data/` root (one knob to move it
to an external drive) while *code* stays clean. Config lives near code; **runtime state stays in
`data/`**.

### CP-B tuning mode / proposals view
A planned CP-B mode where the agent **proposes** evidence-backed config changes from the DB (e.g.
"promote this CMS to `CMS_HOSTS` — 51 records, currently `null`"), each declaring its **loop tier** and,
where Tier 0/1, a before/after against the labels. **Human disposes**; the agent never auto-applies.
Guardrail: every knob has a stated *principle* for a valid change; Tier-2/3 changes need cross-batch
confirmation.

---

## 6 · Data-collection modes (who/how)

- **Automated** — collected by the pipeline (search-led discovery + tiered capture + cheap-cloud council
  extraction). The default path.
- **Human-provided** — schedules a human collected and placed in `data/raw/manual_import_files/`
  (e.g. where a WAF/Cloudflare block stopped automation). Still counts as **enriched** (it's real data).
- **Manual intervention** — automation attempted, then hit a block needing human help; tracked, retried
  deliberately (never silently). **Security blocks** (Cloudflare/WAF/CAPTCHA) get the **ONE-attempt
  rule** — flagged for manual, never bypassed.

---

## 7 · LEGACY vocabulary (for reading old records & docs)

These describe the retired enrichment-campaign / Crawlee+Ollama era. Kept so historical DB records and
archived docs remain interpretable — **not** current practice.

- **Enrichment campaign / "Option A"** — the old state-by-state sequencing (ascending enrollment, attempt
  ranks 1–9, stop at 3 successes/state). Superseded by the batch/stage pipeline.
- **Legacy `method` field values** (on older `bell_schedules` rows): `web_scraping`, `pdf_extraction`,
  `district_policy`, `school_sample`, `school_specific_schedules`, `district_standardized_schedule`,
  `school_hours_with_estimation`, `manual_data_collection`, `human_provided`, `state_statutory` /
  `fallback_statutory`.
- **Collection file** — `bell_schedules_manual_collection_2024_25.json` (a legacy bulk export).
- **"Scraped the data"** — historically meant the Crawlee+Ollama scraper; today means the pipeline's
  Stage 3 Playwright capture. Prefer "captured" for the current pipeline.
- **Crawlee mapper / Ollama ranking-triage / the `:8000` API / `:3000` scraper** — the retired stack,
  archived to `data/archive/crawlee-ollama-era-superseded-20260625/`.

---

## 8 · When unclear — disambiguating questions

1. **Which era?** Stage/`batch_*`/`candidates.json`/`labeled_topology` → current pipeline; `method`
   field / `manual_import_files` / "Option A" → legacy.
2. **Enriched or not?** Actual schedule (gross bell-to-bell) → enriched; `statutory_fallback` → not.
3. **Discovery or extraction?** Finding the page (recall, **waves**) vs reading the times (correctness,
   **council**).
4. **Guess or truth?** `guessed_topology` / `category_hypothesis` are the *script's* noisy guesses;
   `labeled_topology` / the **label** are the *human's* ground truth.
5. **Whose data / what quality?** Be explicit about WHO collected it (automated vs human-provided) and
   WHAT it represents (actual schedule vs statutory).
