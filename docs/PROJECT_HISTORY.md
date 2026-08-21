# Project History — Key Decisions & Lessons

> **What this is:** A distilled, decision-oriented record of *why the project is the way it is* — the architectural/methodological choices and the hard-won lessons behind them. It replaces ~55 superseded session-handoff, status-snapshot, and test-result files that previously lived in `docs/archive/` and `docs/chat-history/`.
>
> **Why it exists:** The raw files are preserved in git history (they were removed from the working tree in the cleanup following restore-point commit `59603c3`), but git history is rarely grepped in practice. This doc keeps the *signal* — decisions and lessons — discoverable in the working tree while the noise stays in git.
>
> **How to read it:** This is not a chronological narrative. It's an ADR-style ledger. Dates and source files are cited so the originals can be recovered from git if needed. **Per project Rule #6, treat any count/rate below as a historical finding — verify against the live DB or current code before relying on it.**

---

## Part 1 — Key Decisions & Rationale

### Acquisition strategy: cloud AI-extraction → local-first (Crawlee + Ollama)
The project tried, and abandoned, AI-API extraction of bell schedules. Gemini-class extractors showed a **~28–56% error rate and hallucinated plausible-but-fake schedules** that were costly to verify; automated success rates ran ~0.2–0.4%, and the token/maintenance economics did not work at ~17,000-district scale. Human-assisted search alone produced **52% of all successes** — more than every automated method combined. This drove the pivot to a **local-first pipeline (Crawlee mapping + local Ollama LLMs for ranking/triage/extraction)**: no per-token cost, so the binding constraint becomes compute time, not money. *(Source: `BELL_SCHEDULE_COLLECTION_STRATEGY.md`, Jan 2026.)*

### The interim 5-tier system (and why it too was dropped)
Before the current pipeline there was a cost-bounded 5-tier escalation: Tiers 1–3 free/local (Playwright discovery, HTML parsing, pdftotext/tesseract OCR) handling the easy ~51% at $0, Tier 4 interactive Claude (included in subscription, $0), Tier 5 Gemini API (only ever a placeholder). Projected cost ~$8.80/245 districts. This was removed in Jan 2026 in favor of the simpler local-first design — the tiering added complexity without solving the core accuracy problem. *(Source: `MULTI_TIER_SYSTEM_READY.md`, `QUEUE_SYSTEM_IMPLEMENTATION_STATUS.md`.)*

### PostgreSQL as the DB-first source of truth
Chose PostgreSQL (Docker) over SQLite to avoid a later migration, get real constraints/FKs, use JSONB for nested raw-import data, and keep local/prod on the same engine. Motivated heavily by **token efficiency** — querying specific rows beats loading 41K-token JSON files — and by integrity guardrails. LCT outputs are now written to the DB first and exported to CSV/JSON *from* the DB, not the reverse. *(Source: `DATABASE_MIGRATION_NOTES.md`, Dec 2025.)*

### Five staffing-scope LCT variants
A single "instructional staff" field is ambiguous and tells an incomplete story, so LCT is computed over nested scopes: `teachers_only ⊂ teachers_core ⊂ instructional ⊂ instructional_plus_support ⊂ all`, with **`instructional` as the recommended primary metric**. Different scopes give rhetorical flexibility for different audiences ("time with classroom teachers" vs. "all student-facing adults"). NCES CCD (24 staff categories, ~all 18K districts) is the foundational/fallback source; state/CRDC layer on top via precedence. *(Source: `STAFFING_DATA_ENHANCEMENT_PLAN.md`, Dec 2025.)*

### SPED/GenEd segmentation on CRDC 2017-18
NCES CCD has **no** SPED-teacher categories and IDEA 618 personnel data is state-level only — **CRDC is the only federal source with district-level SPED teacher counts.** Segmentation was triggered by observed **LCT inflation** (median ~25 min vs. expected ~18): SPED teachers serve smaller caseloads, so counting them inflates apparent connection time. **2017-18** was chosen as the most recent pre-COVID clean biennial (2020-21/2021-22 COVID-tainted; 2023-24 not yet released). The method computes ratios (`sped_teachers/total_teachers`) and applies them proportionally to current CCD, so the ~5-year gap is acceptable because the *ratios* are stable; validated against IDEA 618 Child Count with a **correlation threshold ≥0.70**. Caveat: CRDC includes Section 504 students, IDEA 618 is IDEA-only — a definitional mismatch to keep in mind. *(Source: `SPED_SEGMENTATION_HANDOFF_*`, Jan 2026. `docs/METHODOLOGY.md` §SPED Segmentation documents the present-state method (consolidated 2026-07-02 from the retired standalone `SPED_SEGMENTATION_IMPLEMENTATION.md`, archived); the "why 0.70 / why 2017-18 / inflation trigger" rationale is here.)*

### Temporal 3-year blending window (REQ-026)
Post-COVID years (2023-24 / 2024-25 / 2025-26) are interchangeable, so data is blended to maximize coverage, with two modes: **BLENDED** (default; most-recent data per table) and **TARGET_YEAR** (enrollment anchored to a year). The original `year_span` formula was **off-by-one** (`|y1-y2|+1`), flagging adjacent years as gaps; corrected to `|y1-y2|` (0–1 = ok, 2–3 = WARN, >3 = ERR), which **cut false-positive warnings ~85% (3,567 → 527)**. Output filenames encode the mode (year present = anchored, absent = blended). *(Source: `CHANGELOG_2026-01-20_temporal_blending.md`.)*

### NCES-first SEA integration via the `ST_LEAID` crosswalk
A key discovery: **NCES CCD LEA Universe files already contain state-assigned LEA IDs (`ST_LEAID`) for all 50 states**, which eliminated the need to build custom per-state crosswalk utilities and cut state onboarding from weeks to ~1–2 days. California established the "Layer 2" precedence pattern (state-actual data overrides federal estimates); Texas proved it generalizes. The `state_district_crosswalk` table is the single source of truth for ID mappings. *(Source: `TEXAS_INTEGRATION_COMPLETE.md`, `CA_PHASE2_IMPLEMENTATION_SUMMARY.md`.)*

### Enrichment campaign sequencing — "Option A"
Process states in **ascending enrollment order** (smallest first, to minimize context-switching), enriching ranks 1–9 and stopping at 3 successes per state. Measured rates: ranks 1–3 ≈ 44% success, expanding to 4–9 ≈ 83%, combined ≈ 90% single-pass state completion. *(Source: `project_status_archive_2026-01-17.md`.)*

### Test the contract, not the file layout
Early SEA tests asserted on specific dict-key names and **6 of 8 states skipped**. Adopted principle: **"when most states fail/skip a test, fix the test, not the states."** Tests were rewritten to call the real loader functions and assert on returned data, with meaningful failure modes (`NotImplementedError`→skip, `FileNotFoundError`→fail, empty→fail). This is *why* the SEA test framework is state-agnostic and scales without modification. *(Source: `test_framework_refactor_2026-01-19.md`.)*

### Local tools first; decision trees over retry loops
Standing operating principle, born from a real stall (see Lessons): prefer local CLI tools (tesseract/pdftotext) over API/Read-tool for document processing (~87% token reduction claimed), and use **bounded decision trees with max-attempt limits instead of retry loops**. The "ONE attempt" rule for security/CDN blocks originates here. *(Source: `session_2024-12-21_operational_documentation.md`.)*

### The human-QC constraint: decouple coverage from verification (2026-06-12/13)
Before the pipeline was redesigned, a strategy/options review (`INSTRUCTIONAL_MINUTES_ACQUISITION_STRATEGY.md`, now archived — distilled here) named the conflict that shapes every gate design since: **all ~20K districts × human-QC every disagreement × <1 hr/week human time cannot all be satisfied at once.** Two independent ~40–55%-accurate extractors disagree on a large share of districts (call it 30–50%) — that's 6,000–10,000 districts into a human-review queue, which at <1 hr/week clears in **4–6 years**. The human is the binding constraint, by 2–3 orders of magnitude, not money (even a premium single-path extraction run fit comfortably under a $1,000 budget ceiling). **Resolution: decouple *coverage* from *human-verification*.** Auto-accept where independent paths agree within tolerance; statutory fallback (labeled, never counted as enriched, REQ-024) covers the uncertain tail so all 20K have *some* value; human time is spent **enrollment-weighted** — the top few hundred districts hold the majority of U.S. students and dominate every published LCT number, so ~500 districts × 2 min ≈ a few months at <1 hr/week is feasible where draining the full queue is not. This reasoning is why the pipeline's human gates (`gate@1/5/6/7/8`) are positioned where they are — at decision points that shrink or route the queue, not at every extraction — and why `filtered.json`/dispatch carry a `hold` state for the unconfident-but-unlabeled middle rather than forcing an immediate human call on everything. The bake-off/build phased program in that same doc is superseded by the entries above (multi-provider bake-off, per-school pipeline) — this constraint-resolution is the one piece of it that wasn't captured elsewhere.

---

### Extraction quality benchmarked — no silver bullet (2026-06)
A provider-agnostic benchmark (`infrastructure/scripts/benchmark/`) compared reading methods — plain text/OCR, **table-aware** (pdfplumber), and **vision** (qwen2.5-VL) — × models, scored on grade-band *modal instructional minutes* (±15 min) vs the DB's `human_provided` ground truth. **All approaches plateau ~35–53%.** Plain text on a 7B model (mistral/qwen2.5) is the best *local* approach (~42%); table-aware and vision did **not** beat it on aggregate (table-aware is more *precise* when it hits; vision fixates on early-release columns). **Claude Haiku (cloud) edged the locals (~53%)** — a modest model lift, not a fix. **Lesson: the dominant limiter is input + ground-truth quality** (corrupt source PDFs, HTML schedules not in parseable tables, transposed tables, single-band GT) — *not* the model or reading method. *Direction set:* format-aware reading + **dual-path consensus with human review of disagreements** + better multi-band ground truth. This answers the "is local extraction good enough?" question that paused the project (no — ~42% local, ~50% even with a capable model) and reframes the work from model-selection to input/GT quality + QC. Full record: `docs/technical-notes/learning-loop-reports/EXTRACTION_BENCHMARK_FINDINGS.md`.

### Multi-provider bake-off + discovery architecture (2026-06-13) — *partly supersedes the entry above*
A second, much wider bake-off (the local models had been deleted; cloud APIs now in play) ran ~20 models on the **full 41** districts via two new multi-model conduits (Perplexity Agent API `pplx:`, OpenRouter `openrouter:` in `extractors.py`; native Gemini direct API; Claude via subagents). It overturned the "modest model lever / ~53% ceiling" framing:
- **A capable cloud model ~doubles the best local.** Full-41 leaders: **Gemini 2.5 Flash 68.9%** (cheapest *and* best), Mistral Large 2512 / Qwen3.7-Max 67.6%, DeepSeek V3.2 66.2%, **Mistral Small 24B 63.5% (~$0.05/1M)**, Opus 62.3%; **Granite 4.1 8B 51.4%** (tiny, self-hostable, beats Sonnet). **Cheap wins; bigger ≠ better** (DeepSeek V4-Pro 45.9%, GPT-5.5 < GPT-5.4).
- **Decision:** default extractor = **Gemini 2.5 Flash**; council partner = a cross-family model (**DeepSeek V3.2 / Mistral**); local/self-host = **Granite 4.1 8B**. No per-modality routing — one cheap model generalizes; route by **confidence** (consensus auto-accept) instead.
- **Lesson — input is the ceiling (quantified).** A district×model crosstab + difficulty analysis showed **20% of districts are solved by zero models**, but on tractable inputs (difficulty > 0.70) the top models re-score to **~95–100%**. Failure-mode analysis: **22 of 23 hard inputs already contained the schedule as text** (it was *not* an OCR problem) — they failed on **granularity/noise** (giant multi-school dumps, single-band GT) or were the *wrong page*. So the path past ~69% is **better inputs**, dominated by **per-school targeting** (small, focused, current, single-schedule artifacts).
- **Discovery validated (search, not crawling).** Blind Crawlee crawling fails (probe: glob-targeting matched zero links; broad crawl missed every schedule). **Domain-scoped search** (Perplexity `search_domain_filter`, OpenRouter `site:`, Claude `allowed_domains`) eliminates the wrong-district problem and reaches school subdomains. **Google grounding dropped** (its tool has only `exclude_domains`, no site-restriction). New bottleneck = **capture fidelity** on JS school-CMS pages → tiered capture (text-layer preferred; screenshot+OCR/vision fallback). **Crawlee re-cast as terrain-mapper/one-hop off-site fetcher**, not schedule-finder. Relevance gate stays a deliberately-cheap `pdftotext` sniff; high-fidelity reading (pdfplumber/vision) is the extraction stage's job.
- Requirements added: **REQ-043…053** (discovery, relevance gate, multi-format capture, net-minutes extraction, grade-band assignment, consensus, fail-loud fallback, provenance, budget governor, sampling, grounded-extraction+provider-abstraction). Full record: `docs/technical-notes/models-and-council-composition/EXTRACTION_AND_DISCOVERY_LEARNINGS_2026-06.md`, `docs/technical-notes/learning-loop-reports/EXTRACTION_BENCHMARK_FINDINGS.md` (Updates 1–3).

### Discovery scaled, per-school pipeline built, council + metric pinned (2026-06-20)
The acquisition design was carried from proof-of-concept to a concrete, partly-validated pipeline. Canonical doc: `docs/ACQUISITION_PIPELINE.md` (now the single source of truth; the old "production-ready" Crawlee+Ollama description was replaced; the strategy/options report that preceded this pipeline is archived, distilled into the entry above).
- **Discovery scaled to the full 41 (honest hit-rate).** Domain-scoped search + tiered capture (text-layer → screenshot+OCR fallback) found an on-domain schedule page for **37/41 = 90%** (71% on a literally schedule-named URL). Per-tool: OpenRouter `gpt-4o-mini-search` 33/41 (best), Claude WebSearch 32/41, Perplexity 31/41 (worst, hub-skewed). **OCR tier essential** — 20 of 152 relevant pages were image-only (eChalk). Tools are complementary (union 37); **OpenRouter/Claude reach school subdomains, Perplexity skews to the district hub.**
- **Discovery = waves, not council.** Discovery is a recall problem (any tool finding the page wins; capture verifies), so it runs cost-ascending waves with stop-when-found: **Claude WebSearch (Haiku subagent, sunk subscription cost) → OpenRouter `gpt-4o-mini-search` → flag for manual. Perplexity dropped** (lowest coverage, hub-skewed). Extraction stays a *council* (correctness). **Wave 1 can only run from inside the agent** (it spawns a WebSearch subagent), so the pipeline is orchestrated by a **skill** (`.claude/skills/per-school-acquire/`) that glues waves and calls `.py` workers — **agent-in-the-loop, not lights-out** (subscription leverage and unattended operation are mutually exclusive).
- **Extraction council pinned (research-backed).** Deep-research synthesis (`docs/technical-notes/models-and-council-composition/LLM_COUNCIL_RESEARCH_2026-06.md`): diversity > count, **consensus only counts cross-family** (two wrong LLMs agree ~60% vs 33% chance; same-family share blind spots → false consensus), 2–4 models is the sweet spot, a **judge that re-reads the page** beats adding voters, cascades cut cost (FrugalGPT/UCCI). Grok 4.3 & Qwen3.7-Max **removed** (reasoning-token cost 4–70× via real OpenRouter logs; not 100% on difficulty>0.70). Two candidate configs to A/B (decision = measured escalation rate): **Path 1** cheap trio (Mistral Small + Gemini Flash-Lite + Qwen3-235B) + DeepSeek judge; **Path 2** accuracy pair (Mistral Large + Gemini Flash) + DeepSeek judge.
- **Per-school targeting built; lift not yet isolated.** NCES `ccd_sch_029_2425` retrieved; grade-span→band classifier + sampling envelope showed **95/±5 is a near-census (96%)** → policy is **census small districts, cap large at ~8–12/band with mode-stability early-exit**. Per-school discovery→dedup→capture→Path-1 council→deterministic modal aggregation wired and unit-tested (`per_school_run.py`, `aggregate.py`, `council_extract.py`). First run (New Haven) proved the **plumbing** but not the lift — its one GT band routed through an **unlabeled multi-school hub**. Reality confirmed: **hub-vs-per-school is a spectrum** (Christina 20/21 hub, Sweetwater 10/15 mixed, New Haven 0/13 per-school). **Models extract per-school rows; code computes the mode** — never let the LLM pick the "typical" schedule (a triage prompt that did this was removed).
- **Metric decision: GROSS bell-to-bell, not net.** Target is **end − start, no deductions, no assumed-net** — the existing GT was already gross, gross needs only two reliably-published numbers (↑accuracy), and assumed deductions add fake precision. Labeled `gross_bell_to_bell`; **net is a deferred enhancement.** Plausibility cap raised 480→510 min (real days run to ~8.5h). Propagated to `ACQUISITION_PIPELINE.md`, `METHODOLOGY.md`, `TERMINOLOGY.md`, skill.
- **Ground truth re-established by hand (in progress).** The old GT is the limiting instrument: too thin (mean ~1.9 bands, many single-band), at least one **stale** (New Haven GT 8:30–14:05 not on the current page), and the wrong *shape* (a district point vs. the per-school distribution we now produce). **Automated triage of the yardstick failed** (regex can't attribute bands — it's the extraction problem itself) → the user hand-curates from source. A clean curation workspace was built (`data/benchmark/gt_curation_<ts>/`: PDF/image only, 753 junk files dropped, 54 districts in `unsorted/`, 10 HTML-only districts self-eliminated) for the user to sort into `hub`/`per_school`/`excluded`; the council then proposes gross start/end per band for human sign-off ("I draft, you verify").

### Stage 1 (Queue) designed, built, and validated against the full NCES corpus (2026-06-22)
The acquisition pipeline's first stage moved from design to working code in one session, walked stage-by-stage with the human (CP-A) reviewing real output at every turn rather than a batch of design docs reviewed cold.
- **Pre-queue exclusion filters, all live/recomputed (never a frozen list):** not-operating (LEA `SY_STATUS_TEXT`), CTC/shared-service (`is_shared_service_entity`), grade-span integrity (Rule 7 — LEA-level claims a band, school-level union shows zero coverage), already-attempted (new `district_status.json` registry, replacing `training_batch.py`'s directory-presence heuristic). Enrollment-quartile stratified sampling (3 districts/quartile, state as a tiebreak, not an independent axis — staff count and school count were considered and dropped as too collinear with enrollment).
- **The CTC exclusion (METHODOLOGY.md Rule 6) had been schema-only and silently a no-op since it was designed** — `is_shared_service_entity` was `False` for every one of 17,842 districts until this session, despite `calculate_lct_variants.py` filtering on it. Backfilled (152 districts via the documented name-pattern method), then **expanded to 600** after Pima County JTED (Joint Technical Education District, AZ) slipped through into a real acquisition batch — "JTED" doesn't spell "technical." Investigating turned up a cluster of similarly-named AZ JTEDs/CTEDs and led to a broader NCES `LEA_TYPE_TEXT` blanket rule, with an explicit, documented trade-off: it also catches some legitimate full-time special-purpose state schools (deaf/blind institutes, fine-arts academies) that aren't really CTCs — accepted for now, not silently absorbed.
- **Band classification rebuilt twice in one day, both times from real CP-A findings, not theory.** First pass: `bands_for()` pure grade-range overlap caused **dilution** (a real `Connersville Middle School` diluted 6-to-1 by 5 unrelated K-6 elementary schools that merely clipped the boundary grade) — fixed with **LEVEL-primary classification** (trust NCES `LEVEL` when it's a clean Elementary/Middle/High, full stop). Second pass: the rescue mechanism for whatever LEVEL leaves unresolved was first scoped to "exactly 2 schools" (fixing Jasper Co. MO/Jefferson-Morgan PA's elementary+secondary splits) — but profiling the **full 17,265-district corpus** against a hand-built reference table of recognized grade-band shapes showed school-count was the wrong dividing line. **Northern Tioga PA's 3 elementaries/2 secondaries, once collapsed to distinct spans, are structurally identical to Jasper Co.'s 2-school case** — it should have gotten the same fix and previously did not. Replaced the count-based tie-break with `recursive_band_groups()`: a single, general, explicit rule (no overlap-counting) — consecutive leading segments with top grade ≤6 collapse into elementary (handles 1-3+ elementary sub-segments); what's left is middle alone, middle+high merged, or middle plus one-or-more high segments (lower/upper-high splits). Validated against real N=1 through N=6 district shapes nationally (Albertville City AL elementary split 3 ways; Aledo ISD TX high split into a 9th-grade campus + main campus) — districts whose spans don't form a clean partition (Breathitt County KY, Chama Valley NM — genuinely overlapping/redundant elementary spans, not just multiple buildings) correctly stay on the original conservative any-overlap fallback.
- **The recurring lesson, twice in the same day:** an automated check (Rule 7's grade-span-gap detector) cannot distinguish a diluted-but-nonzero candidate pool from a healthy one, and cannot catch a false-gap risk it would create itself if applied too strictly — only a human looking at actual school names, twice, found real bugs no rule-checking could have caught from the output shape alone.
- Two implementation bugs caught by stress-testing against real data immediately after writing the code (not found by review): a lone segment spanning the full grade range with nothing following lost its "high" membership (Universal Academy MI); an ambiguous-LEVEL school was wrongly dropped from a band that already had LEVEL-clean coverage instead of joining it as an additional candidate (Aledo's 9th-grade campus). Both fixed same-session.
- Outcome: `infrastructure/acquisition/discovery/queue_batch.py`, `district_status.py`, and `school_sampling.py` (extended) produced a real, validated `batch_00001.json`; REQ-061 through REQ-067 added with 27→31 real (non-stub) tests; `training_batch.py` archived to `data/archive/training_batch_py-superseded-20260622/`. Full record: `docs/ACQUISITION_PIPELINE.md` (Stage 1 section), `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE1_QUEUE_DESIGN.md` §6 (the turn-by-turn decision log), `METHODOLOGY.md` Rules 6–7.
- **`recursive_band_groups()` rewritten a second time, same day: position-based middle/high assignment → per-segment overlap check.** A further CP-A pass over `batch_00001` caught The Bridge Academy (CT) — a single LEVEL=High, 07-12 school — wrongly listed in the **elementary** band, because the first rewrite still assigned middle/high by *position* ("first remaining segment = middle, rest = high"; a lone non-leading segment was unconditionally dropped into elementary too). Tracing the old code by hand surfaced a second real bug of the same shape (Sequoia Union Elementary CA: an 08-08 LEVEL=Middle school pulled into the **high** pool just for coming last after an elem+middle-merged leading segment) and confirmed one case the old rule already handled correctly (Quitman County GA: a PK-08 elementary's middle-coverage does NOT spuriously pull a trailing 09-12 high school into middle — kept as a regression case, not a fix). **Fix:** elementary stays a positional prefix-collapse, but middle/high now check each segment's *own* grade span independently of position. 3 new tests, REQ-066 updated in place; 34 tests passing. Full record: `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE1_QUEUE_DESIGN.md` §6.
- **`district_status.already_attempted()` threshold bug found while trying to re-confirm the fix above in place.** Re-running `queue_batch.py` to regenerate `batch_00001` silently excluded all 12 of its districts — `already_attempted()` fired on *any* registry presence (any stage), even though Stage 1's own design intent (stated in the decision log as "'Through Stage 3' exclusion") was always Stage 3 (Capture)+; none of the 12 had progressed past Stage 1. **Fix:** `ATTEMPTED_THRESHOLD_STAGE = 3` — a district stays eligible for redraw until it's actually been captured, not merely queued or searched. 2 new tests; REQ-062/REQ-067 updated in place; 36 tests passing. Regenerating after both fixes produced a **different** 12 districts, not the same ones — the per-segment fix also changed Rule 7's grade-span-gap exclusion count (985 → 1,439 nationally), shifting the eligible pool itself. The new batch was reviewed in full: every cross-band overlap traced to a genuinely forced case (single-school districts, explicit Jr/Sr- or Elem/Middle-combined school names, one non-clean-partition fallback case structurally identical to Breathitt County, one ambiguous-LEVEL multi-band school) — no Bridge-Academy-style false positive remained. Judged ready to advance to Stage 2.

### Doc/config locations: `REQUIREMENTS.yaml` → `docs/`, `requirements.txt` stays at root (2026-06-23)
The two files sharing the `requirement(s)` stem at the repo root was a real source of confusion, but the blast-radius check inverted the obvious fix: **`requirements.txt` must stay at root** — it's load-bearing in CI (`pip install -r requirements.txt`) and the single strongest pip/buildpack/dependency-scanner convention there is, so moving it breaks things for zero benefit. **`REQUIREMENTS.yaml` moved to `docs/`** (no code opens it by path — only prose mentions, all updated) — cheap, safe, and consistent with the project's ALL-CAPS reference docs already living there. *Guardrail: don't "consolidate" these two; their collision is cosmetic and the root one is non-negotiable.* (Migrated here 2026-06-30 from the retired flow-diagram decision log.)

### Retired Crawlee+Ollama era formally archived (2026-06-25)
The original **local-first Crawlee HTTP-scraper + local-Ollama** stack (the FastAPI app on `:8000`, the Crawlee server on `:3000`, the Ollama ranking/triage services and their `data/config/` prompts) had been *de facto* dead since the project pivoted to the stage-based `infrastructure/acquisition/` pipeline and deleted local Ollama in favor of cheap paid-cloud extraction — but the code still sat in the live tree, with stale docs (incl. `CLAUDE.md`) pointing at it. An orphan audit confirmed **zero live importers** (nothing in `infrastructure/acquisition`, `infrastructure/scripts`, `infrastructure/database`, or `tests/`), and the whole era was moved to `data/archive/crawlee-ollama-era-superseded-20260625/` via reversible `git mv` (history preserved, manifest README). The live **Stage 3 Playwright capture** (`capture_discovery.mjs` / `capture_drive.mjs`) was untouched; the root `docker-compose` lost its dead `scraper` service (`postgres` kept). *Lesson reinforced: an architecture pivot isn't finished until the superseded code is out of the working tree and the docs that point at it are corrected — dead code that still imports cleanly is invisible rot.* Full record: the archive's manifest README + the doc commits.

### Stage 5 made *learnable*: config-as-data + a measurement harness + de-chrome (2026-06-25)
Rather than hand-tune Stage 5's deterministic filters by eye, the project built the machinery to **measure** changes and **act on them as data** — turning "I think this helps" into a number. Three parts, an implementation wave (REQ-087…093): **(1)** a `paths.py`/`DATA_ROOT` indirection so all generated runtime state relocates as one unit (code stays clean); **(2)** a **config-as-data layer** (`infrastructure/acquisition/common/config/`, JSON read by both the Python and Node halves, **per-entry provenance** so each tunable is its own decision log) with `CMS_HOSTS` migrated as the first knob, ending a drift-prone hand-synced dual definition; **(3)** a **measurement harness** that scores a config state against the 150 human labels and emits a **fingerprinted scorecard** (config × label-set × data → metrics), reproducible/auditable. **The loop's value showed on first use:** a plausible Tier-0 keyword/regex fix (instructional *hours*) was measured **net-negative** and reverted — the harness *prevented a bad ship* and redirected the effort, proving the category-accuracy ceiling was a **de-chrome problem, not a keyword one**. Then **de-chrome** (segment a page's header/footer/nav vs. main at render time, tier signals over the de-chromed `main`) was built and, on a live `backfill-segments` run over `batch_00001`, **measured a strong win: category-guess 0.43→0.60, topology agreement 0.6→0.8, with tier A unchanged** — while the harness simultaneously surfaced a precise side-effect (footer-negative stripping floats non-targets C→B, dropping A+B precision) to investigate next. *Lesson: a deterministic pipeline becomes improvable only once a cheap, reproducible measurement closes the loop — and the same measurement that proves a win also catches a plausible-but-wrong change and names the next thing to fix.* The next step is the operational Stage 5 **filter → `filtered.json`** for Stage 6. Full record: `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE5_FILTER_DESIGN.md`, REQ-087…093.

### Pipeline governance: STATE→Postgres event log, a stage-spanning console, headless Stage 2 (2026-06-26)
A design-first session re-architected the **back half** of the acquisition pipeline once the Stage-5 "Checkpoint B" review app outgrew its single-stage scope. The organizing principle is **STATE vs DATA**: the per-stage JSON artifacts (`discovery/candidates/captures/processed/batch`) stay **authoritative on disk** — their role reframed from data-carriers to **auditable receipts** — while cross-stage *state* (pipeline position, checkpoint approvals, the re-discovery loop) migrates into the database. Decisions: **(1)** the review app becomes the **Acquisition Pipeline Governance App** — a stage-selectable console spanning CP-A (queue) / CP-B (release) / CP-C (write) plus tuning + funnel dashboards. **(2)** The DB moves **SQLite → Postgres** (a genuine SQLite steelman was weighed and lost once the app became central), in an **isolated `governance` database** in the existing container — preserving the one decisive SQLite virtue (the drop+rebuild ingest can't reach the production LCT tables) while consolidating onto the project's existing SQLAlchemy/migrations stack and opening the cloud path; it becomes a **cross-stage cache**. **(3)** State is an **event log** (current-state a projection; `actor` carries identity for a multi-user future), keeping the version-controlled JSON-backup pattern for the new precious rows. **(4)** `filtered.json` is a **regenerable export** of the DB release decision (one best representation per qualifying canonical record); Stage 6 emits an **immutable `handoff_<hash>_<timestamp>.json`** that freezes fingerprints so "what we sent the council" is always recoverable. **(5)** Stage 2 discovery goes **headless** via the Claude Code CLI (`claude -p`, subscription-billed — the cost-decisive distinction from the Agent SDK, which bills per-token), retiring the "subagent requires a chat" framing; search providers become a **pluggable layer** (Claude CLI / OpenRouter / future Bright Data / Brave / new models). Tuning foundations were *built* first (REQ-095 ledger, REQ-096 frontier search). *Lesson: the right database/app boundary is a function of scope — SQLite was correct for a throwaway single-stage cache and wrong for a central, precious-state-bearing console; separating durable STATE (DB) from regenerable/portable DATA (on-disk JSON, now receipts) is what makes "scattered" pipeline state navigable.* Full record + build sequence: `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md` (authority); reconciled into `ACQUISITION_PIPELINE.md` (incl. its flow diagram).

### Governance design executed; console/gate model & a documentation architecture pinned (2026-06-27)
The 2026-06-26 governance design was **built**: the isolated `governance` Postgres DB + cross-stage cache (REQ-103), the `state_event` append-log + `current_state` view that replaced the `district_status.json` registry (REQ-099), and the **event-driven `filtered.json` release generator that concludes Stage 5** (REQ-094, carrying alternate representations for gate@6 override). Then a console-design session settled the **human-gate model and the unit of work**: checkpoints became **stage-numbered `gate@1/5/6/7/8`** (replacing CP-A/B/C; stages 2/3/4 + the Stage-9 write ungated; gate@8 = the effective old CP-C), each manual/auto with **confidence-escalation**; the **batch dissolves at Stage 5** (CP-B is the per-URL representation review), reforming as the per-district handoff at Stage 6; **completion grain = district × BAND** (schools are instrumental — Dunseith published band-level minutes and the schools became moot); two batch types (first-run / follow-up, 12-district cap); and the **pipeline is cyclic** (7→6, 7→1, 8→1, 8→6, with new-work directions routed through a reviewable Stage 1). `filtered.json` is **event-driven** (no manual trigger); Stage 6 = routing/release (which representations → which OpenRouter council config). A **documentation architecture** was also pinned: `ACQUISITION_PIPELINE.md` becomes a slim canonical *map*; each stage gets a design note (for the built Stages 1–4 a **code-verified narrative** — the code is ground truth, established with `grimp` + reading the scripts — written to inform the console); content routes by *nature* (methodology→`METHODOLOGY.md`, stage design+evolution→the stage note, one-liner→the map). The pre-June `docs/claude-instructions/` modular briefing + a stale DB data-dictionary were archived (superseded by the root CLAUDE.md + current docs). *Lesson: when documenting an already-built stage, verify the prose against the code — generating Stage 1's narrative, the import graph gave only the code skeleton; the load-bearing edges (which DB tables/columns, which NCES files by year, downstream subprocess/API hosts) were **environmental** and surfaced only by reading the code.* Authorities: `PIPELINE_GOVERNANCE_AND_STATE.md` §11 (gates/console), `STAGE6_DISPATCH_DESIGN.md`, the per-stage `STAGE*_DESIGN_*.md`; granular status in `REQUIREMENTS.yaml` (REQ-094/099/103/108/109).

### Console build started; the batch becomes a first-class DB entity; gate@1 goes in-band (2026-06-27)
The governance console build began with its first stage view, the **gate@1 queue** (REQ-102, backend). Two decisions shaped it, both reached by the user pushing on the design. **(1) The batch is now the working store in the governance DB, not a JSON file** — normalized PRECIOUS tables (`batch`/`batch_district`/`batch_school`), with `batch_NNNNN.json` *regenerated from the rows as the auditable receipt*. This made the §7a-A "receipts" reframe concrete: the district-dir/queue JSON shifted from a data-transmission vehicle to an auditable receipt, the DB is the working store. A `doc_json` blob was explicitly rejected (it would just park the receipt in a column) in favor of normalized rows, so the gate@1 edits are real row ops and the cross-batch queries the user stories need (a district in multiple batches; per-batch yields) fall out. **(2) gate@1 approval is BATCH-level** — the unit that advances is the batch, so approval is a `batch` row transition (`draft → approved`) plus per-district `gate@1` events for the timeline, *not* a property derived from N per-district events. Editing (reject district/school, add school — the APGA stories 29–31) is **soft + audited** (`included` flips / row inserts; a `gate@1 "edited"` event each), locked once approved. The batch logic split into `build_batch()` (pure) + `persist_batch()` (DB write + receipt + events), shared by the CLI and the console (orchestration = functions, §7a-B). **`batch_00002` is the forcing function**: the batch-of-record is created and advanced *only* through the console (hand-run scripts = dev/test), deliberately driving console development stage view by stage view under the ramp-up model. Frontend (the queue view) is next. *Lesson: a terse user question ("does approval happen to the district or the batch?") caught a modeling error before it set the pattern for every later stage view — the unit of a governance action is worth pinning explicitly, not defaulting to whatever the storage layer makes easy.* Authority: `STAGE1_QUEUE_DESIGN.md` §6 + `PIPELINE_GOVERNANCE_AND_STATE.md` §11h; REQ-102 (+ REQ-100/101/104 registered, REQ-044 scoped to Stage 5).

### gate@1 console finished + validated; the forcing function realized (2026-06-28)
The gate@1 **frontend** was built — the first console stage view — on the **MMM Design System** (the firm's own design project on `claude.ai/design`, imported via the **DesignSync** tool: Badge/Select/Card/Button + the shared tokens the Stage-5 app already used). `batch_00002` was then **created → edited (one district rejected) → approved entirely through the console UI**, with the `batch` row, the `state_event` log (11 `gate@1 approved` + 1 `edited`), and the regenerated receipt all consistent — the forcing-function milestone (the batch-of-record is born from a recorded gate@1 action, not a script). Edits were made **reversible** (reject↔restore) so a mis-reject during draft isn't a dead end. *Lesson (server robustness): the first real launch 500'd because the create path read the NCES CSVs and the LCT `.env` via **CWD-relative** paths — fine from the repo root, broken from any other launch dir. `build_signals` had been immune only because it already used the absolute `paths.DATA_ROOT`. Fix: anchor all data/`.env` reads to the repo, never the CWD — a rule every later stage's file reads must follow.* Separately, **CI was repaired** (green Tests + Lint): the resource-dependent test modules (local NCES dataset / Postgres) were marked `integration` and excluded from CI, flake8 was scoped off `data/archive/`, and the Node-20-deprecated actions were bumped — the failures were never the deprecation warning, just a suite that had outgrown a resource-free CI. Authority: `STAGE1_QUEUE_DESIGN.md` §6 (esp. §6e-ui/§6f).

### Stage 2 re-architected to a deterministic SERP cascade; discovery run live through the console (2026-06-28)
Building Stage 2's headless runner exposed that Claude's `claude -p` **`--json-schema` structured-output mode flakes** (`error_max_structured_output_retries`; *more* effort made it worse) — dropping the schema and parsing the free-text response fixed it. That detour prompted a **measured five-provider bake-off** (53-school known-positive set, reports in `data/acquisition/diagnostics/`), whose load-bearing finding is that **the underlying search INDEX predicts recall**: raw-Google providers cluster at the top (Bright Data 98%, Serper 100%, OpenRouter 100% but $27/1K), while own-index Perplexity craters at 43% — *all* its misses returned zero results because its index simply has no entry for small district domains (by extension Exa/Brave/Tavily are out for long-tail K-12). The architecture became **Wave 1 = Bright Data SERP** (real Google, `site:`-scoped, **recurring**-free 5k/mo, picked first so the renewable tier carries the load) + **Serper failover** (banked credits) *only on a Bright Data API failure* — same Google index, so Serper is **uptime backup, not recall** (the user's insight: don't re-query the same index for the same emptiness) — and **Wave 2 = Claude WebSearch** on the genuine residual, a *different* index as a speculative "why-not-try" tier. Stage 2 is now **fully deterministic** (no agent in the Wave-1 loop; the `stage2-discover` SKILL is obsolete; `claude -p` survives only as the Wave-2 tier + a diagnostic harness). The **Stage-2 console view** (second stage view, built on the gate@1 pattern) ran `batch_00002` and `batch_00003` end-to-end: Bright Data Wave-1 found **28/30 schools**, and the 2 residuals that reached the Claude tier recovered **0** (genuine no-page cases — a different index can't conjure a page that doesn't exist), which (with the latency cost) seeded a watch-item on whether the Claude tier earns its place. *Cost reframe: Stage 2 is now cheap **real cash** (~$0.001–0.0015/query, ~$17–21 per 17k pass), not subscription quota.* *Lesson: don't decide a provider on first principles — measure it; the same harness that bench-tested extraction settled discovery, and a "free + fast" option (Perplexity, Claude-as-Wave-1) lost to a paid one on the metric that mattered (recall/index coverage). Also: own-index ≠ Google — index source is the dominant variable, not price or latency.* (Precision of the *found* pages is **not** judged at Stage 2 — that's Stage 5's learning loop over captured content.) Authority: `STAGE2_DISCOVER_DESIGN.md` §7; REQ-104.

### Stage 3 (Capture) console built + hardened over live runs; capture made resilient to partial failure (2026-06-28/29)
The third console stage view (per-district Node-Playwright capture run trigger + an ungated health/emergent readout) was built on the gate@1/Stage-2 pattern and **run live on batch_00002–00005**, then hardened by what those runs surfaced (REQ-110). The arc, in decisions: **(1) The cross-stage DB cache graduated from a drop-each-ingest cache to a LIVE working store** — its schema + per-district UPSERTs moved to `common/cache_ingest.py` (stages are independent siblings, so the ingest can't live in `stage5_filter`), and every stage's `finish` hook now projects its slice in, so the console reads fresh DB rows for an in-flight batch instead of parsing JSON off disk. This was the load-bearing change that made "the DB is the working store, JSON files are receipts" real for the *data* surfaces, not just the batch. **(2) No-link districts skip Playwright** (a Stage-2 `manual_flag_all` has nothing to capture) and surface with that same label — and the UI's honest-counting rule was pinned: no-link districts are reported *separately*, never folded into a "captured" count (the bug was "2/12 captured" when 0 were), with capture/process denominators excluding them so a stage can reach a real "✓ captured · 2 no-links." A shared `static/outcomes.js` made the per-district label + the left-pane progress badge one source of truth across Stage 2/3/4. **(3) The deepest fix — a timeout must preserve work, not orphan it.** Brookwood SD 167 / Fairfield / LAS CRUCES all read as total failures while real captures (LAS CRUCES: 534 files) sat on disk, because Python's subprocess timeout SIGKILLed Node *before* it wrote its end-of-run manifest. Two responses: **node-owns-shutdown** (Node takes a deadline, stops pulling new pages when it passes, records the rest `not_attempted`, and *always* writes a partial `captures.json` → `captured_partial`; Python's timeout became a backstop), and a **reconstruct-from-disk** recovery tool that rebuilt manifests for the already-orphaned districts (and doubled as the interim manual-follow-up path — it folded a hand-downloaded parent handbook PDF, whose pp. 32–33 carry Brookwood's bell schedule, in as a `source:"manual"` record). A probe proved the Brookwood site was *fine* (every page 1–3s) — the double-timeout was transient (likely rate-limiting from a 5-concurrent burst), which is exactly why resilience-to-transient-stalls, not "fix the bad page," was the right frame. *Lessons: (a) an external worker should **own its own shutdown and always write a complete manifest** — a timeout is a partial outcome, never a total loss; the orchestrator's kill is a backstop, not the primary control. (b) **Status must distinguish "failed/timed-out" from "not yet attempted"** — they looked identical (no manifest) until the failure was read from the event log, which is why a real failure (Brookwood) hid in the run log while the table said "queued." (c) Measure before blaming the site.* Authority: `STAGE3_CAPTURE_DESIGN.md` §7; REQ-110.

### Stage 4 (Process) console + the Stage 4→5 incremental handoff; `build_signals` made batch-scoped (2026-06-29)
The fourth console stage view was the simplest — Stage 4 does its work **in-process** (the local harvesters are fast Python subprocess calls), so unlike Stage 2/3 there's no external worker, no `node-owns-shutdown`, no per-district kill budget; a crash just leaves `processed.json` unwritten and reconcile re-runs it. The status view reads the `processed_doc` DB working store (never parses `captures.json` — only an `.exists()` stat), plus a usable-representations-by-tool readout. The substantive decision was the **Stage 4→5 handoff**: the user's instinct was right — *precompute the Stage-5 ingest the moment a batch finishes Stage 4, so opening the Stage-5 view has no lag* — but a **full-corpus** rebuild at batch completion would just *relocate* the lag and make it **grow with the whole on-disk corpus**. So the build was the incremental option (the user chose "B, do it properly"): `build_signals.ingest()` was refactored to share an extracted **`ingest_district()`** unit with a new **`ingest_batch(district_ids)`** — the signal-table DDL split into drop + `CREATE IF NOT EXISTS`, the batch path does a per-district `DELETE`+`INSERT`, resolves dirs in `O(batch)` (`glob("<did>_*")`), and **leaves prior batches and the precious `label`/`cluster_split` rows untouched** (rec_key is stable). The trigger lives in the **orchestration layer** (`process_governance/server._ingest_stage5_if_complete`), *not* in `stage4_process` — a stage importing another stage breaks the import-linter independence contract (the same wall that forced a *local* `stage2_complete` disk-scan instead of importing Stage 3's `find_districts`); it fires only when a run resolves the whole batch (`resolved==total`, `todo>0`), records a per-district `furthest_stage→5` `state_event`, and is best-effort (an ingest hiccup is surfaced but never fails the already-durable Stage-4 job). A dependency-hygiene pass rode along: Stage 4's **system binaries** (poppler/tesseract/ghostscript) are now documented in GETTING_STARTED (pip can't install them; a fresh clone hit a cryptic `FileNotFoundError`), and the unused `img2table` was dropped. *Lesson: "precompute to remove lag" and "full rebuild" are in tension — the cure for perceived lag is **incremental** work whose cost tracks the unit you just finished, not the whole history; the batch-scoped ingest is the first concrete piece of the Stage-5 rework, mirroring the cross-stage cache's earlier drop→UPSERT shift (REQ-110).* Authority: `STAGE4_PROCESS_DESIGN.md` §4a/§4b, `PIPELINE_GOVERNANCE_AND_STATE.md` §12; REQ-111.

### Forward note — bridging back into Stage 5 (→ BUILT as REQ-112, 2026-06-29; see the two entries after this one)
**Read the whole console-evolution arc above (the 2026-06-25 "Stage 5 made learnable" entry through this one) with one frame: the console was BORN as a Stage-5 review tool and grew *upward* to manage Stages 1–4 — and it is now circling back to its origin, which is shaped differently on purpose.** The Stage-5 labeling surface (the 3-column district→record→representation review app + the deterministic signals/tiers/clusters) came *first*; only later did it become the stage-selectable governance console, acquiring batch-shaped views for gate@1 → Stage 2 → Stage 3 → Stage 4. **Stages 1–4 are batch-shaped** — a batch is the unit that's queued, discovered, captured, processed, and each of those views' left pane is a *list of batches*. **Stage 5 is deliberately NOT batch-shaped:** at the Stage 4→5 handoff the **batch dissolves** (governance §6/§11d/§12), the **district** (and below it the record/representation) becomes the driving unit, and gate@5 is a *per-URL representation review*, not a batch approval. The existing Stage-5 review surface **predates the governance re-architecture** — treat it as the console's *origin*, not its current-architecture exemplar, and **do not force the batch-shaped stage-view pattern onto it.** Concrete open work for the rework, none of it done by the handoff (which only makes districts *appear* in Stage 5 instantly): **(1)** a **district-driven attention queue** as the home view (governance §7b) — "what needs my attention" is a query over `state_event` current-state, not a batch list; **(2)** wire the **existing gate@5 review app** into the stage selector (integrate, don't rebuild); **(3)** the **recency gate** (REQ-044, a Stage-5 filter enhancement, *not* REQ-104); **(4)** a **`state_event`-subscription projector** that regenerates exactly the affected districts' `filtered.json` off the log — generalizing today's two inline `release.generate` hooks; the incremental `ingest_batch` (REQ-111) is the first piece of this; **(5)** the **tuning/funnel dashboards** (REQ-095/096) as a distinct surface from per-district review. Two load-bearing facts the next builder will trip on: the Stage-5 review reads the **signal tables** (`record`/`representation`/`district`), which only refresh when `ingest_batch` (batch path) or the full `build_signals` (schema/recovery path) runs — *not* the live `processed_doc` cache; and the discipline carries through unchanged — **council proposes, human verifies** (the GT is hand-curated by eye), the metric is `gross_bell_to_bell` (REQ-055), and `label`/`cluster_split` are precious + JSON-backed. *The shape of each console surface should follow the work's natural unit — batch through Stages 1–4, district/representation at Stage 5 — and the pull to make Stage 5 "look like the other views" is precisely the thing to resist.*

### Stage 5 reworked: district-driven, attention-first console (REQ-112, 2026-06-29)
The Stage-5 view — the console's *origin* (the standalone 3-column review app) — was brought onto the current architecture and made **district-driven, attention-first**, exactly the "different on purpose" shape the forward note above argued for. The conceptual heart is the **ATTENTION model**, and the load-bearing decision was the user's reframe: **attention = "where does my judgment move us forward?" — the INVERSE of automatable-confidence, NOT "most likely a target."** Those diverge precisely at the clean tier-A case (high target-likelihood, *low* attention — a swift yes, first to automate); attention peaks instead at *flagged* + *promising-but-unresolved* records (image-only, signal-vs-tier disagreement, schedule buried in a handbook) where the human eye is decisive and the filter still has something to learn. It's a `{score, reasons[]}` per record (the reasons are the UI's rationale chips), rolled up per district, **config-as-data** (`stage5_attention.json`) and deliberately **frontier-compatible** so the REQ-096 tuning machinery can later *fit* the weights to labels (the ML on-ramp). A property worth stating: **the score shrinks as the process learns** (the clean-yes zone auto-resolves), so it doubles as the ramp-up dashboard. The build: `stage5_filter/attention.py` + `recompute_attention()` (at ingest + every label/split save), stored on `record`/`district`; a **server-side faceted console** (`/api/stage5/districts` — group by district facets, filter by record facets with the district staying visible, sort incl. continuous, asc/desc — built for ~5M-rep scale), follow-up flags (precious, the top attention tier), DB-backed saved views; the left pane reworked (collapsible mini-dashboard groups, attention chips, re-fetch-on-show, deep-linkable views); the center/right labeling panes unchanged. Plumbing finished: the SQLite vestige retired, the signal tables a never-dropped live working store on the incremental path. Decisions that shaped it: **batch dissolves → "first_seen_at" (first gate@5 event) replaces it**; **no per-label `state_event`** (the log is completion-only, §11c — "recent change" reads `label.updated_at`); **NCES locale descoped** (not in our CCD files — needs an EDGE geographic file). *Lessons: (a) the right attention metric is INVERTED from the obvious one — rank by "needs me," not by "looks like a target," and the two are most different exactly where it matters (the clean wins you don't need to babysit). (b) **Self-verify visuals.** Pass-1 of the UI shipped unfinished and was hedged as "v1 to iterate"; the user (graciously) called it. The fix isn't an apology — it's rendering the page with Playwright (`playwright screenshot --wait-for-selector …`) and looking before handing back. Don't ship visuals blind.* Authority: `STAGE5_FILTER_DESIGN.md` §A–D, `PIPELINE_GOVERNANCE_AND_STATE.md` §12c; REQ-112.

### Forward note — into Stage 6 (routing) & Stage 7 (the council); read before you build the handoff (2026-06-29)
**Where you are:** Stages 1–5 are built and console-driven; the next frontier is **Stage 6 = routing/release** (decide which package of representations goes to which OpenRouter council config — `gate@6` — then emit the **immutable `handoff_<hash>_<timestamp>.json`** that freezes content+config at dispatch) feeding **Stage 7 = the paid extraction council.** Design authority: **`STAGE6_DISPATCH_DESIGN.md`** (design started); the gate model is governance §11.

**Invariants you must not break** (they're hard-won — CLAUDE.md restates them): **extractors read TIMES only** (`{start_time,end_time,grade_level,school_name}`); **deterministic Python computes `gross = end − start` + the per-band mode** (REQ-054) — never ask a model to compute minutes or pick a "typical" schedule. Metric = **GROSS bell-to-bell**, plausibility 240–510 min (REQ-055). **Council consensus = the per-school (start,end) pair, CROSS-FAMILY, ±15 min — same-family agreement is NOT consensus** (REQ-056: two same-family models share blind spots → false consensus).

**Your input is `filtered.json`** (per district, REQ-094): canonical records with a `decision`+`reason`, **one best representation each + the alternate target-flagged reps** (so `gate@6` can swap the rep), carrying tier/topology/`emergent`/`intended_schools`/`cost_estimate` + `(config,labels,data)` fingerprints. The handoff **freezes** this at dispatch — required by the Stage-7 "council can request more evidence" loop and the cyclic back-edges (**7→6** re-extract via a different config, **7→1** re-discover, **8→1** band-gap fill, **8→6** add an existing-rep URL; new capture routes through Stage 1, only re-routing EXISTING reps bypasses it).

**THE NEW LEVER you didn't have when Stage 6 was first sketched — the attention reasons are a ROUTING SIGNAL.** REQ-112 tags every record with *why* it needs attention, and those map straight to routing: **`image_only`/`visual_text_gap` → the text path missed it → route to a VISION council member** (Gemini Flash / Mistral Large read images — proven Tier-3); **`buried_long_doc` → send the `harvest_pages` slice, not the whole handbook**; **`signal_text_disagree` → the genuinely hard cases that most need the cross-family council**; `clean_target` → a cheap single pass likely suffices. Use the per-record attention reasons to drive both *representation selection* and *which council members to spend on*. (filtered.json already encodes the best-rep choice via `visual_text_gap`/`target_image_only`; the attention reasons make the routing rationale explicit and greppable.)

**Open decisions to resolve by MEASUREMENT, not first principles** (the project's recurring lesson): **(1) the exact council composition** — candidate set is 6 non-reasoning models (Gemini 2.5 Flash, Mistral Large 2512, DeepSeek V3.2, Mistral Small 24B, Gemini 2.5 Flash-Lite, Qwen3-235B; Grok 4.3 & Qwen3.7-Max removed for 4–70× reasoning-token cost). Path-1 cheap-trio vs Path-2 accuracy-pair vs Path-1-minus-Mistral, **decided by the measured escalation rate** (the GT is hand-verified, 940/943 — use it). **(2) the council-config GRAIN** — per-district vs per-representation (governance §11d open; STAGE6's agenda). **(3)** signals→routing/assignment + cost estimation.

**Cost is the whole reason the upstream pipeline exists.** Stage 7 (paid OpenRouter, ~$0.05–0.30/1M) is **the** expensive stage; Stage 2 recall is cheap cash, Stage 4 processing + Stage 5 filtering are free local compute whose *job* is to cut what the council never needs to read. So: the **budget governor (REQ-051)** + `gate@6` cost-gating auto-advance, `filtered.json` carries `cost_estimate`, and aggressive Stage-2 recall + a recall-biased Stage-5 filter are the levers that make Stage 7 affordable. Don't let full-auto run up unbounded spend.

**Two standing items the user wants kept alive:** the **ML on-ramp** (frontier-optimize the attention/tier weights → a simple supervised classifier in sklearn once labels are plentiful → heavier ML only if those plateau; revisit when many batches past 800 records) and the **"District Investigator"** holistic-journey view (the data model — `district_id` + the event log — already supports it). And the unchanging discipline: **council proposes, the human verifies**; precious tables are JSON-backed; measure config changes with the harness.

### Stage 6 (Handoff / routing) built to the Stage 6→7 seam; gate@6 live (REQ-101, merged PR #2, 2026-06-30)
*(Naming note, 2026-06-30: Stage 6 was **renamed "Handoff" → "Dispatch"** shortly after this entry — clearer for explaining the stage to people; the code identifiers — `stage6_handoff/`, the `handoff` table, `handoff_<hash>_<ts>.json`, `/api/handoff` — deliberately keep "handoff". This log preserves the original name.)*
Stage 6 was built slice-by-slice into a pure `stage6_handoff/` package (`common`-only imports, independent of the other stages) + an app-layer bridge in `process_governance/`: it reads the Stage-5 release decision **from the DB** (`record`/`representation`/`label` + `release.decide`; `filtered.json` is the auditable *receipt*, never the transport), **routes each representation** to a council, **prices** it, **freezes** an immutable `handoff_<hash>_<ts>.json`, records the dispatch, and **assembles the OpenRouter requests** — **stopping before the paid call** (Stage 7). The `gate@6` console (`static/stage6.js` + `/api/handoff/*`) is preview-routed/priced-package → **Approve & freeze**. ~63 tests + a live end-to-end dispatch; a high-effort `/code-review` surfaced **10 findings, all fixed** before merge. Decisions that were "open by measurement" are now pinned by build:
- **Council template = 2 cross-family voters → a 3rd-family judge** on disagreement (the "cheap-trio vs accuracy-pair" question collapsed — pair+judge *is* the cascade, and the research says judge > extra voter). Enforced as a **hard validation rule** in `councils.validate()` (+ a prompt-resolution check). **Composition** (which models) is deliberately *deferred to the council lab*, not guessed.
- **Routing grain = per-representation**, **data-driven off each council's `input_kinds`** (a new content-typed council plugs in by config, not code) + the **capture-fidelity gate** (a low-fidelity / `visual_text_gap` rep routes to the vision council and is flagged `fidelity_suspect` — never auto-accepted on 2-voter agreement; the New Haven false-consensus lesson).
- **The immutable handoff's identity hash is price-independent** (over what we *sent* — reps + routing + configs + fingerprints — not the dollar figures), so a reprice/retune can't rewrite a past dispatch. The index row + the `dispatched` state_event are recorded **atomically on one session** (`current_state` is a view), with the file written **last** so a DB failure rolls back cleanly.

*Two reframes worth carrying forward.* **(1) Stage 6 is two layers, not one:** a **runtime dispatch path** (per handoff: route → price → freeze → dispatch) that *consumes*, and a recurring **council lab** (`cost_benchmark` + a measured cost model + a ledger) that *produces* — the same shape as the Stage-5 tuning loop. The cost-model `provenance` field is the contract between them, so the runtime path is indifferent to bootstrap-vs-measured. **(2) The cost estimate decomposes by owner + volatility:** **token consumption** (ours, measured by the lab on our reps) × **per-token price** (OpenRouter's — *fetched live from `/api/v1/models` and cached, never hardcoded*) + an **escalation rate** (accuracy, later). So the expensive lab re-runs only when content/models change; a reprice just refreshes a free cache. *Lesson: the thing that first looks like a one-off calibration (a cost estimator) is usually standing infrastructure — design it as a producer/consumer pair with a versioned, provenance-stamped artifact between, and separate what you measure from what the provider sets.* (A companion guardrail surfaced when scoping accuracy: the hand-verified `gt_curation` GT has **zero district overlap** with the current pipeline and predates the clean Stage-1..5 reps, so cost work needs no GT but *composition/accuracy* must first **align the prior GT into the pipeline** — a future large `batch_00000` — rather than score against a parallel island.) *Post-merge refinements (2026-06-30):* the **5/6 send set was tier-gated** — labeled targets + unlabeled tier-A dispatch, but **tier-B/C now HOLD** (a *third* release decision awaiting a gate@5 label, not a reject — so the pipeline never auto-spends on the uncertain middle), and **handbooks send a materialized `harvest_slice`** (the high-signal `harvest_pages`) instead of the whole PDF. The gate@6 console gained per-rep council override, click-to-inspect a representation, left-pane filters, and a **verified-only** dispatch mode — labeled targets only (holding the speculative tier-A sends), for a manually-verified **training-grade** corpus, **frozen into the dispatch identity** so it never collides with a default dispatch. *Lesson: the recall-biased funnel is right for discovery but wrong at the paid seam — auto-dispatching the confident-but-unlabeled tail floods the council; a `hold` state + a verified-only mode put human judgment back in front of spend without discarding the tail.* Authority: `STAGE6_DISPATCH_DESIGN.md` §0; governance §11/§12.

### Stage 5 scoring/labeling V2: the cascade became labeling functions once it drifted at scale (REQ-113/114/115, 2026-07-01)
The V1 tier logic (a single if/elif cascade, additive score for sort only) validated at 85% tier-A precision / **zero** tier-D targets on the first 12 districts — and **drifted at 59** (measured over 440 labels): tier-A precision **69%**, and tier-D, the "safe to auto-drop" floor, **leaked 10 real targets (9%)**. Diagnosis traced the drift to three structural defects of a *sequential monolithic rule*, each fixed at **zero measured recall cost** on the 382 canonical labels: **(1)** de-chrome computed time signals over `page.main.txt` *exclusively*, silently zeroing real school hours living in the **footer** (`"Hours: 8:24 AM – 3:30 PM"`) or surviving only in an **OCR/raster** rep — 15 of 24 footer-noted records, targets stuck at tier D → fix: time signal over the **max-evidence source**, never an exclusive either/or; **(2)** tier B had **no positive requirement** (`n_times_in_window≥2`, two unrelated times on a big page) → requiring a proximity pair drops 13/38 non-targets, costs 0 targets; **(3)** the suppress floor was `n_times==0` when it should be `n_times_in_window==0` → reclassifies 35/61 tier-C non-targets, costs 0 targets. The architectural response (grounded in a two-pass research read — Snorkel weak-supervision + FrugalGPT/SUPG cascades + a K-12-hours-markup survey, in `docs/technical-notes/filtering-research/`): **replace the cascade with independent, individually-measurable DETECTORS (labeling functions) combined by a shallow transparent weighted vote** into a `send`/`suppress`/`review` routing decision (tier letters retained as a derived summary). Each detector is independently testable, tunable without perturbing a sibling, the unit the human labels against, and the unit the harness scores. Companion changes: **labeling becomes a multi-axis object** (v2.1, after a second human-factors pass with Ian) — Axis 1 the target *shape* (a 7-way radio: footer-list / bell-table / prose / hub-by-school / hub-by-band / explicit-minutes / other-shape, + `target_absent`/`unusable`, replacing the old forced single target-or-non-target choice); Axis 2 *confounding signals present* as multi-select facets (the former non-targets — a homepage can carry board + sports + a feed at once, and they're the ground truth for the negative detectors); Axis 3 *where it hides* (buried-handbook + a **print-dialog page range**, needs-vision). A fired detector *hints* ("flagged") but never auto-checks — facets stay clean per-detector ground truth. `migrate_label_v21` moved all 440 labels (128 targets preserved; git = restore point) — a migration, *not* a reset (the 202 notes stay valid). The **detail pane also went text-first** (footer/header first, with a per-rep "unique-times-vs-densest" readout) so the eye confirms a TEXT rep has the target before an image can anchor a premature check-off. **`cms_hint` is promoted** from a Stage-3-only console rollup to a first-class record signal — **not a score input but the grouping key** for per-detector accuracy (a detector reliable on one CMS template may be noisy on another, visible only if CMS is tracked — the VPC-by-vendor thesis from the tuning notes); and **Stage 3 gains iframe/embed capture** (the `embedded_feed` pollution and calendar-widget clusters are structurally an `<iframe>`/embed to a known host — a vendor-agnostic signal beating the URL/keyword guess). *Research also settled a non-starter:* schema.org `OpeningHoursSpecification` markup is near-absent on K-12 CMS (<5%), so it's detected opportunistically but not designed around. *Lessons: (a) a rule validated at small n is a hypothesis, not a law — re-measure at every scale step; a monolithic cascade hides which branch drifted, independent detectors don't. (b) The recall-biased filter's job is as much **suppressing confident negatives** as finding positives — both are measurable, and the false-negative rate of the auto-suppress tier must be audited directly (sample it), because silent recall loss is invisible otherwise. (c) **The human labeler is a component of the system too** — the pane's *presentation order* shapes its error rate (text-first prevents the image-anchoring miss; a fired detector must hint, not pre-check, or the ground truth collapses into the detector), and scoring insights from review are **recorded to a field-observations log** (`STAGE5_FILTER_DESIGN` §3a) for later measured folding, never hand-tuned in the moment.* Authority: `STAGE5_FILTER_DESIGN.md` (clean-rewritten to present state), `STAGE5_TUNING_NOTES_2026-06.md` (Part C = the weak-supervision layer); REQ-113/114/115.

### The 27-district curated GT aligned into the pipeline as `batch_00000` (2026-07-02)
The hand-curated ground truth (`data/benchmark/gt_curation_20260621T060008Z/`, 940/943 schools human-verified) predated the current Stage 1–6 pipeline and had zero district overlap with anything that had actually run through it — a real gap flagged back in the Stage 6 forward note (2026-06-29): Stage 7's first build would otherwise have no clean, site-drift-free corpus to score against. Resolution: **a third Stage-1 batch type, `batch_type="benchmark"`.** `batch_00000` injects the 27 of the 41 curated-GT districts that survived triage directly at the Stage-3 seam from frozen `gt_curation` artifacts (`gt://` URIs, no discovery/capture needed — the files already exist), then runs normally through Stages 4–6 like any other batch. It is **permanently walled off**: never Stage-9-written, never counted in funnel/enrichment stats — the point is a clean scoring corpus, not production coverage. The other 14 of the original 41 (the ones that didn't make the 27-district cut) are recorded in `data/benchmark/benchmark_holdback_18.json` with their original per-band findings, so that once they eventually flow through the full pipeline fresh, there's a then-vs-now comparison available. `batch_00000` is dispatched through Stage 5 and sits ready for gate@6, reserved for Stage 7's first real build. Code: `stage1_queue/benchmark_batch.py`. *Lesson: a benchmark/GT corpus that predates a pipeline redesign is only useful once it's actually run through the current architecture — a frozen JSON file of "known-good" answers doesn't score anything by existing, and threading it through as a real (if walled-off) batch was cheaper than building a parallel scoring harness.* Authority: `STAGE1_QUEUE_DESIGN.md` §2h, `STAGE7_EXTRACT_DESIGN.md`.

### Documentation architecture pass: genre separation + a header convention, ahead of batch_00000 → Stage 7 (2026-07-02)
With `batch_00000` (see above) ready for gate@6 and Stage 7 next, the docs tree got a full alignment pass before that build starts — the same instinct as the earlier documentation-architecture pinning (2026-06-27 entry above), pushed further. The organizing move: **separate present-state docs from decision-log docs from research/evidence docs from status-tracking**, so a reader always knows whether they're looking at "what the code does now," "why it got this way," or "a point-in-time finding," rather than one doc trying to be all three at once (the failure mode this project had already hit once, described in the 2026-06-27 entry). Concretely: all 10 `STAGE*_DESIGN_2026-06.md` notes (+ the Overview/Settings note) were rewritten present-state-first with an explicit **§0 receipt-from-prior-stage / handoff-to-next-stage** section, moving "how we got here" prose into each doc's own decision log; `PIPELINE_GOVERNANCE_AND_STATE.md` and `ACQUISITION_PIPELINE.md` had their giant build-history header paragraphs (the same anti-pattern, independently regrown in both) trimmed to a compact present-state statement + pointer, with fully-executed planning sections (`governance §8/§9/§9a`) marked historical-in-place rather than renumbered (too many live cross-references — `governance §11`, `§7a`, etc. — to risk it). `QA_DASHBOARD.md` and `SPED_SEGMENTATION_IMPLEMENTATION.md` were folded into `METHODOLOGY.md` (mechanics belong with mechanics); the Texas/California state-integration planning docs were archived (their live status now lives in `SEA_INTEGRATION_GUIDE.md`/`DATA_SOURCES.md`); `INSTRUCTIONAL_MINUTES_ACQUISITION_STRATEGY.md` was distilled into the human-QC-constraint entry above and archived. `PROJECT_CONTEXT.md` was stripped down to the mission/story/roadmap (status detail removed — that's `CLAUDE.md`'s and GitHub Issues' job now); `GETTING_STARTED.md` and `CLAUDE.md` themselves got the same status-detail strip, replaced with pointers, on the standing decision that **GitHub Issues/Projects is now the primary live-status tracker**, not a markdown file that has to be hand-updated every session. A **standard header block** (Authority / Audience / Companions / "Update this when") was applied to every rewritten doc so a reader — human or agent — can tell at a glance what a doc actually governs before reading it. Three technical-notes filenames that broke the project's own `CAPS_WITH_UNDERSCORES.md` convention (contained spaces/sentence-case) were renamed with all references fixed.

**A real accuracy bug surfaced along the way, not just formatting.** Verifying `SEA_INTEGRATION_GUIDE.md`'s "✅ Complete" claims against the live DB (Rule #6) — triggered by archiving the Texas/California planning docs — found that Texas's and California's `staff_counts`/`enrollment_by_grade` rows are **100% `nces_ccd`-sourced**, not superseded by state data as the guide's blanket "✅ Complete" table implied; Texas's real integration is the NCES↔TEA ID crosswalk only, California's is LCFF/SPED/FRPM (funding/attendance, not the staff+enrollment pair LCT actually consumes). `METHODOLOGY.md`'s own Tier-1 (7 states) vs. Tier-2 (`TX`/`CA` — "identifiers/funding only") split had this right all along; `SEA_INTEGRATION_GUIDE.md` and `DATA_SOURCES.md` did not, and both were corrected. *Lesson, the same one Rule #6 already teaches: a doc that says "✅ Complete" for a genuinely-tested, genuinely-shipped piece of work can still mislead if it doesn't say complete **for what** — "the tests pass" and "this supersedes the federal fallback in the metric the project actually publishes" are different claims, and only a DB check catches the gap between them.*

### Stage 7 built end-to-end on real data; the request-more-evidence loop designed deterministic-first; gate@7 shipped (REQ-117, 2026-07-02/03)
With `batch_00000` ready and Stage 6 stopping at the seam, Stage 7 — the paid OpenRouter council extraction — was built in vertical slices directly against real data (plumbing → council run → persistence → GT scoring → durability/resume → image-vs-text comparison → request detection → the gate@7 console), rather than designed abstractly first. Results on the full `batch_00000` run (24 districts / 83 reps): the **text council** (Gemini 2.5 Flash-Lite + Mistral Small 24B → Qwen3-235B judge) scored **95.2% band / 99.3% per-school** against the 940-time curated GT at **$0.065 total**; an **image council** run alongside scored 88.5%/98.1% (its judge, DeepSeek V3.2, turned out non-vision-capable — filed as GitHub #82, not a doc typo but a real assumption error, Ian: "Whoops! Incorrect assumption on my part").

**Two architectural corrections came from challenging the first design, not from a spec.** (1) The first batch runner persisted only after the *entire* batch completed; Ian challenged it directly mid-run ("the fact that we don't get streaming output with district granularity concerns me... is there some benefit to collecting everything at the end that I'm not seeing?") — no benefit was found, so the running job was killed and rebuilt as `run_council_streaming`: one district at a time, persisted immediately, resumable by querying already-extracted districts for the handoff hash, with a per-rep/per-district progress line ("if we hit a snag, we'll at least know when it happened"). (2) A live audit against the official OpenRouter docs (requested explicitly: "double-check... against openrouter.ai/docs") found the client wasn't using SSE streaming, was capped at `max_tokens=2000` (real risk of silent truncation on a 93-school flier), and wasn't capturing the `generation_id` needed to correlate a call against OpenRouter's own audit endpoint — all three fixed before the full run, not after.

**The request-more-evidence loop was designed before being built, specifically to survive a context wipe** (Ian: "describe the plan in the Stage 7 design note so we don't lose it"). The shape: **routing is deterministic scripts, never the model** — "the more we can rely on scripts, the better... more auditable and reduces token consumption" — the REQ-054 read-vs-decide split (models read, code decides) extended from minutes-computation to routing. Three altitudes mirror the pipeline's own hierarchy: **representation** (a rep yields 0 facts, an alternate exists → `7→6`), **URL** (all reps of a URL exhausted → `7→3`), **district** (a claimed band has 0 facts anywhere → `7→2`/`7→1`). The loop is **council-initiated, not human-initiated** — confirmed explicitly by Ian when asked: "it is council-initiated... it will also be human-reviewed and approved — but the request is not human initiated," which is the ramp-up model (governance §11b) applied to Stage 7 specifically, and prompted elevating that model from an implicit practice to a documented first-class principle (governance §11b, this CLAUDE.md). Validated against real data with **zero false positives across 20 covered districts**, correctly flagging the 4 genuine coverage gaps the GT scorecard independently showed. One real interaction surfaced during validation: Essex High's band looked "covered" only because a prompt-spray defect had fabricated a fact for it — the 0-facts detector can't distinguish a fabricated fact from a real one, so the anti-spray fix (#81) and the request loop are sequenced (fix the spray first, then the loop catches the now-genuine gap), correcting an earlier assumption that the loop alone would catch it.

**gate@7 shipped as a district-first console**, per Ian's explicit UI call ("organize by district with requests related to them... that will be a better UI organization for me when I'm reviewing") with fact/band editing explicitly scoped OUT ("Fact/band review is Stage 8: Aggregation"). Self-verified with Playwright against the live server + real data before commit (24 districts render, request cards render, 0 console errors, the Approve round-trip works). **Not yet built:** request-more-evidence *execution* (an approved request actually firing the target stage's back-edge machinery) — deferred, since it needs a real (non-benchmark-walled) batch to exercise meaningfully.

*Lessons: (a) a long-running paid job with no incremental output is a design smell worth stopping for, even mid-run — the fix (streaming persistence) was cheap once someone asked "why not?" instead of waiting it out. (b) Verifying a client against the *official* API docs, not just "it seems to work," caught three real gaps (streaming, truncation, audit correlation) that silent success would have hidden indefinitely. (c) When a detection engine says "no gap here," that's a claim about the data it can see — a fabricated fact and a real one look identical to a facts-exist check, so a masking failure mode (the spray) has to be fixed upstream, not routed around.* Authority: `STAGE7_EXTRACT_DESIGN.md` §0/§4, `PIPELINE_GOVERNANCE_AND_STATE.md` §11b; REQ-117; GitHub #80 (Council Lab), #81 (spray A/B), #82 (vision judge).

### Request-more-evidence execution shipped; the budget governor; Council Lab's first measured result; a code review found "re-implemented invariants" as a pattern (REQ-118/051/119, 2026-07-03/04)
The one piece gate@7 shipped without — an approved request actually *firing* the target stage's back-edge — was built, closing the request-more-evidence loop end to end. **The collapse from four back-edges to two mechanisms** came from a reframe, not a spec: "any requests that go to Stages 2, 3, or 4 will probably need to be wrapped in a batch using Stage 1." Only `7→6` (re-routing an **existing, already-labeled** representation) is a true direct back-edge — the gate@5 label lives on the *record*, so every representation of an already-reviewed URL inherits it, meaning no new capture and no Stage-5 round-trip. `7→2`/`7→3`/`7→1` all need genuinely **new** evidence that has never been labeled, so they converge on one mechanism: a targeted Stage-1 **follow-up batch** (`build_followup_batch`, distinct from the stratified cold-start draw) that walks the normal 1→2→3→4→5→6→7 path and stays reviewable at gate@1. gate@7 approval stays **pure review**; execution is a deliberately separate **compose** step, so approving a directive never implicitly commits to firing it.

**The REQ-051 budget governor was built as a hard prerequisite, not an afterthought**, per explicit instruction before any execution code was written. Four caps, not one: per-run (halts), per-district-per-run (skips that district), per-district-**total** across ALL handoffs (the loop-specific guard — a district that keeps failing and re-requesting can't rack up unbounded spend just because each retry is a fresh handoff), and a request-depth guard so the cyclic back-edges provably terminate.

**The Council Lab crystallized as its own concern mid-session**, not planned in advance: it emerged from Stage 6/7 conversation and was first imagined as a Stage-6 module, but its actual scope — Stage 4 reader-routing, Stage 6 council/cost config, Stage 7 prompts/judges, the Stage-8-grown GT yardstick — outgrew that home, so it got a dedicated design note and (agreed, sequenced *after* a ledger exists) its own future console view rather than being buried in a stage view. Its first real experiment doubled as a bug fix: the image council's judge, DeepSeek V3.2, was **discovered non-vision-capable** (404 on every image call, GitHub #82) — fixed by adding a curated vision-capability allowlist + a `councils.validate()` guard, and swapping in `qwen/qwen3-vl-235b-a22b-instruct` (a family already in the roster as the text judge, so no new family risk). A **judge-replay harness** (`council_lab.py`) — replay only the candidate judge on already-escalated reps, reusing the two voters' recorded facts, paying for nothing but the judge call — measured the fix for **$0.045**: 32/33 calls succeeded (vs. 0/33 for DeepSeek), resolving 21/145 disagreements and improving image-council accuracy from 88.5%/98.1% to **89.1%/98.2%** without regressing it. #82 closed on that evidence, not on the code change alone.

**REQ-119 (external AI calls must stream) was captured as a standing, provider-agnostic requirement**, prompted by a direct instruction after a background judge-replay run produced no visible output for several minutes ("this could wind up an unfortunate failure mode during automatic processing at scale"). Enforced two ways: behavioral tests on the live OpenRouter client (streaming survives keep-alive gaps, never blocks on a long generation), and an **AST source-guard** that fails CI if *any* new blocking OpenAI-SDK completion call is added anywhere in the acquisition tree — a structural guarantee, not a one-off test of one function.

**A high-effort multi-angle code review of the whole branch (8 finder angles → 41 candidates → per-candidate adversarial verification) found 13 real correctness bugs, and they shared one root cause**, named explicitly as the durable lesson (GitHub epic #133): *the new execution path had re-implemented several invariants instead of inheriting them from code that already enforced them* — the benchmark wall (`batch_00000` "permanently walled off") existed only as docstrings at the new seam; `dispatch_handoff`'s deliberate file-last commit ordering was inverted in the new alternate-rep dispatch; the `executed` status's terminal-ness was enforced only by a hidden UI button, not the API; the #82 vision guard sat at config-load time while two new code paths (a frozen-handoff re-run, the Lab's judge-replay tool) could reconstruct/replay a council without ever passing through it. All 13 fixed with regression tests same-day. **One of the fixes then broke CI itself** the same way: the fix for "don't share the transaction" (issue #143) initially put a best-effort `district_status.json` export back *inside* the dispatch's transaction — passed locally (the dev DB already had the view the export reads) but failed in CI's fresh Postgres container, aborting the transaction and cascading failures through unrelated assertions. Re-fixed to run the export **post-commit, on a separate session** — the same lesson the review had just named, caught recurring in the review's own fix.

**A large backlog-migration + a hard-won git lesson.** Separately, ~45 scattered open to-dos across the design-note prose were swept into the GitHub issue tracker as 9 epics with native sub-issues (issue #86), leaving `(tracked: #NN)` pointers in the docs and cross-ref fields in `REQUIREMENTS.yaml` (kept as the spec ledger, not migrated) — the new standing practice going forward: **bugs/deferred/planned work live in the issue tracker, not as bare doc to-dos.** And a PR that looked broken wasn't: the feature branch had never been pruned after its first PR **squash-merged** to `main`, so a second PR against the same un-pruned branch collided the already-merged commits against their own squashed selves (`CONFLICTING`). Diagnosis (`git diff <pre-merge-tip> main` was byte-empty) confirmed it was safe to `git rebase --onto origin/main <pre-merge-tip>` — replaying only the genuinely new commits — verified by an identical tree hash before/after the rebase, proving content was untouched and only reparented.

*Lessons: (a) a single well-aimed reframe ("wrap it in a batch") can collapse an N-mechanism design into a smaller, cleaner one — worth pausing to ask before building all N. (b) "the governor is a hard prerequisite, build it first" was right: every later execution path had a caller-ready enforcement point instead of retrofitting caps after the fact. (c) A fix for "this shares a transaction it shouldn't" needs to be checked against a state the dev DB doesn't have (a fresh schema) — passing locally is not evidence the isolation is real. (d) The review's own root-cause finding — re-implemented invariants — recurred inside one of the review's own fixes, which is exactly why it's captured as a standing heuristic for future reviews, not a one-off finding. (e) A squash-merged PR without branch pruning silently sets up the next PR to look broken for reasons that have nothing to do with the new code; a byte-identical-tree check before rebasing is what makes a history rewrite provably safe rather than a leap of faith.* Authority: `STAGE7_EXTRACT_DESIGN.md` §3F/§6, `COUNCIL_LAB_DESIGN.md` (new), `PIPELINE_GOVERNANCE_AND_STATE.md` §11b; REQ-051/118/119; GitHub #133 (review epic, closed children #134–146, open #147/148), #82 (closed), #86 (doc migration, closed).

### Request-loop hardening + gate@7 console maturation — a manual shakedown found a HIGH-severity data-loss bug, then a sequenced 6-chunk hardening pass closed the loop end to end (epic #163, REQ-118, 2026-07-04/05)
Ian manually exercised the just-shipped request-more-evidence execution (previous entry) against real, non-benchmark districts for the first time — a deliberate shakedown, not a scripted test — and it immediately did its job: within the first few clicks it surfaced a stale-server bug (execution ran against code that predated the #134 benchmark-wall guard) and, chasing why Marion's and Pittsylvania's discovered bell tables still yielded 0 facts, a genuine **HIGH-severity release bug (#158)**: content-hash dedup (`duplicate_of`) and shingle clustering (`is_cluster_rep`) pick their canonical record **independently**, and when they disagreed, release's `CANONICAL_RECORD_WHERE` matched **neither** member — silently dropping the whole cluster from dispatch. It triggers on the ordinary case of a schedule PDF mirrored at two URLs (a district site + a `5il.co`/thrillshare host), so it wasn't a corner case — it was quietly costing real recall on real districts. **The fix was verified with a real before/after, not a unit test:** re-dispatching Marion's now-reachable tier-A bell table recovered its middle band from empty to 425 minutes.

That one finding reframed the rest of the session from "test the loop" into a full hardening pass, run as **six sequenced, independently-reviewed chunks** — the release fix; a differentiated-query config foundation; pure detector intelligence (yield-ranked 7→6 alternates, a 7→2 that defers behind a cheaper unexhausted 7→6); the executor + follow-up-builder enrichment (bundling a district's 7→6s into one round, follow-up discovery shaping); console orchestration (a "Run extraction" trigger, a gate@1 refresh fix, follow-up auto-flow); and gate@7 lineage/visibility + an in-Stage-7 compose-preview modal. **Every functional commit got its own adversarial review before the next chunk started**, on Ian's standing instruction, rather than reviewing once at the end — and it kept finding real bugs despite each commit shipping its own green test suite: a compose-side depth guard still counting rows after the executor moved to counting rounds (would have depth-blocked a follow-up after a single real bundled round); a live-defer check that didn't exclude rounds-exhausted districts, which would have **deadlocked** Las Cruces's rediscovery forever (confirmed: it was already in that exact state); a follow-up builder counting schools from an **abandoned draft batch** as "already attempted," poisoning its own untried-schools signal; and a gate@7 card whose "deferred" note read stale detect-time params instead of the same live check compose actually runs — the precise class of bug the lineage feature exists to prevent.

**One governance decision came out of this pass, not from planning:** asked directly why gate@6 and gate@7 exist at all, Ian traced it to its origin — "gate@6 and gate@7 emerged as a result of context clears and my caution around API spending," not first-principles design, unlike the original three-gate design (gate@1/5/8, the old CP-A/B/C), which decide something genuinely new each time and are permanent. That distinction — **structural gates (1/5/8, permanent) vs. supervision gates (6/7, first to relax)** — became the basis for the follow-up **auto-flow** (REQ-118/#157): a follow-up batch carries an already-approved gate@7 decision, so re-approving it at gate@1 and re-clicking Start on Stages 2–4 is redundant; gate@1 now auto-passes and the stage chain auto-runs for a follow-up specifically, landing at gate@5 (still manual — new URLs are a genuinely new data-quality decision) with gate@6 untouched (still manual, Ian's explicit call on the spend gate). A smaller but real UX correction from the same review discipline: a fully-extracted Stage-6 handoff showed a "Re-run extraction" button that would have silently done nothing (the run is resume-by-default) — replaced with an honest "✓ extracted" marker.

Also settled along the way, by direct pushback rather than by design: a starter query-template config initially dropped a `filetype:pdf` template on the belief it conflicted with the existing domain (`site:`) scoping — Ian caught it immediately ("why drop filetype:pdf? That's not in conflict with domain scoping"), and it was restored once the actual conflict (reaching *off-domain* mirror hosts, a separate lever) was distinguished from the non-conflict (an on-domain PDF search composing fine with `site:` scoping).

**Scale + verification:** 21 commits, ~2.4k lines, PR #167 (merged to `main`); 974 DB-free + 64 govdb tests green; `lint-imports` 3 kept/0 broken; console changes self-verified live with Playwright (no JS console errors; the lineage/blocked badges, the Run-extraction buttons, and the compose modal's cancel-path all confirmed against the running server). Every sub-issue closed individually with a commit reference rather than bulk-closed against the epic, so the tracker stays a legible audit trail.

*Lessons: (a) a manual, undirected shakedown of a just-shipped feature is not redundant with its test suite — clicking through real workflows surfaced a HIGH-severity data bug that no unit test was positioned to catch, because the bug lived in an *upstream* stage's interaction with Stage 7, not in Stage 7's own logic. (b) reviewing after every commit, not once at the end, is what actually caught the recurring defects — four of six chunks had a real bug survive their own green test suite until the adversarial pass; batching review to the end would have let those compound. (c) asking "why does this gate exist" turned out to have a real, non-obvious answer (spend caution during a context clear, not a design decision) that then justified a concrete behavior change (auto-flow) — a gate's origin is worth interrogating before assuming its permanence. (d) a reviewer's confident-sounding correction ("that's a conflict") is still a claim that can be wrong in the details even when the underlying instinct is right — Ian's direct pushback on the query-template drop was correct, and taking it at face value without re-deriving *why* would have left a worse config in place.* Authority: `STAGE7_EXTRACT_DESIGN.md` §0/§3F/§4/§6, `PIPELINE_GOVERNANCE_AND_STATE.md` §11a/§11b/§11i, `ACQUISITION_PIPELINE.md` (flow diagram); REQ-118; epic #163 (closed, PR #167) and its sub-issues #152–#162, #165; #151/#122/#164 remain open follow-on work; #166 (unrelated pre-existing test drift, found + logged during the same pass).

### A 6-batch "whittle down the open issue list" hygiene campaign, sequenced from real-bug to cleanup to dedup, each landed as its own reviewed PR (2026-07-05/09)
The prior entry's shakedown of the request-more-evidence loop left a residue behind the headline fix: a backlog of smaller, real findings the shakedown and its code review had surfaced but not yet acted on, plus longer-standing dead code and test drift. Rather than one large sweep, Ian directed the work into **themed batches, sequenced by risk** — dead code first (nothing to break), then real bugs, then behavioral changes requiring before/after measurement, then pure dedup — each its own branch, its own PR, its own adversarial review pass before merge, matching the review discipline the prior entry established.

**Batch 1 (#125/#87/#126/#166, PR #177):** dead code — the pre-redesign `relevance.py` Stage-5 sniff (no importers), the deprecated non-streaming `openrouter_search`/`perplexity_search` providers (the one remaining REQ-119 streaming-guard exception — removing them let the guard run exception-free), a stale doc pointer to the already-retired `REVIEW_DB`, and Stage-4 reconcile tests that had drifted off a 3-tuple return.

**Batch 2 (#173/#169, PR #179):** the #122 live shakedown's own symptom — a single unreadable rep file had stranded districts mid-batch — fixed at two altitudes (per-rep and per-district isolation, both funneled through one `HALTING_EXCEPTIONS` tuple so billing/auth failures still halt cleanly, never silently degrade to a skip). Paired with closing silent truncation: a reply cut off by the model's own output limit now retries once at a shared ceiling, cost-summed onto the real result.

**Batch 3A (#176/#170/#175, PR #191):** the request loop stopped being coverage-blind. A live measurement (88 districts) found **~57% of follow-up spend added zero new coverage** — phantom claimed bands with no real school able to serve them, and re-dispatches on districts already fully covered. One shared `real_bands` signal (mirroring Stage 1's own band-assignment logic) now gates both the detector and, defense-in-depth, the executor's live compose-time re-check.

**Batch 3B (#180/#187, PR #193):** the *optimization* half of Batch 2's truncation fix — reply length turned out to be roster-bound at a flat ~47 completion tokens/school (measured over 840 real calls), so the first call is now sized from the roster instead of guessing low and retrying. Closed the one landmine Ian had flagged in Batch 2's own review: a shared ceiling constant means sizing and the retry can never disagree.

**Batch 4 (#147/#148, four PRs — #194/#195/#196/#197):** the dedup/efficiency tier from the 2026-07-04 code review, split by risk into four independently-reviewable pieces — Python backend invariants (spend-seed queries, depth-guard comparisons, timestamp helpers), frontend helpers + server-side route classification (closing a real XSS-adjacent escaping gap found along the way), efficiency fixes (a cached OpenRouter client, an N+1 query kill, a structural import-linter guard complementing REQ-119's AST-only check), and — held to its own PR since it was a schema change — promoting the fragile `handoff_hash NOT LIKE '%-image'` console filter to a first-class `run_kind` column, closing the exact gap the original design had flagged as a known follow-up (a second vision-council probe would otherwise shadow a district's production run). Every PR in this batch went through the same adversarial review as Batches 1-3 despite being "just cleanup" — and it kept finding real defects anyway: 4C's receipt-file picker could drop a district if its newest file was truncated; 4D's `run_kind` fix closed the extraction-row leak but initially left the request-loop itself still writing directives for a probe run, which would have surfaced a measurement experiment's findings as reviewable production work in gate@7.

**Scale + verification:** 7 PRs, all merged; 1043 DB-free + 69 govdb + 567 integration tests green by the end; `lint-imports` clean throughout. 14 issues closed (7 auto-closed by their PR title, 7 closed explicitly afterward once each fix was confirmed live in current code, not assumed from a commit message).

*Lessons: (a) sequencing by risk — dead code, then bugs, then measured behavior change, then dedup — kept each PR small enough to review properly, and meant a mistake in a later batch could never block an earlier one already merged. (b) "just a cleanup/efficiency PR" is not a reason to skip adversarial review — the 4C/4D findings were real defects with real failure scenarios, not style nits, and both slipped past a green test suite the same way earlier batches' bugs had. (c) closing the loop on tracked follow-ups (the `run_kind` gap named explicitly in the STAGE7 design doc back in July) is worth doing even when nothing is on fire — it was a known, named landmine, not a surprise, and it stayed a landmine until someone scheduled the work.* Authority: `STAGE7_EXTRACT_DESIGN.md` §0/§4(f)/§6 (the fullest mechanism/measurement detail), `PIPELINE_GOVERNANCE_AND_STATE.md` (current build state), `ACQUISITION_PIPELINE.md` (current build state + Key Files); issues #125/#87/#126/#166/#173/#169/#176/#170/#175/#180/#187/#147/#148 (all closed); PRs #177/#179/#190/#191/#193/#194/#195/#196/#197 (all merged).

### The hygiene campaign closes: Batch 5, Batch 6, and the cross-boundary fitness-function layer (2026-07-09/10)
Three more themed pieces, same discipline as the prior entry, brought the "whittle down the open issue list" campaign to zero remaining items. **Batch 5** (#168/#171, PR #198): a first-class `abandoned` batch status — retiring a superseded, never-approved draft to a TERMINAL state, gated on the *durable* `first_approved_at` (not the reopen-clearable `status`) so an approve→reopen→abandon sequence can never launder a batch's already-committed schools back out of the attempted-set (the #162 poison this status exists to prevent) — plus a gate@6 already-dispatched indicator (`n_dispatched`/`last_dispatched_at` per district) so re-selecting a dispatched district's wasted-spend risk is visible before Approve, not after. **Batch 6** (#60/#61/#108, PR #199): a measured Stage-5 scoring pass — a soft-gate for incidental prose-pairs on nonstandard-day (weather/remote/delay) pages, independent footer/header evaluation so an office footer stops downgrading a genuine school-hours header, and facet-level per-detector scoring that immediately surfaced confounder-precision the coarse target-accuracy metric had been hiding. **#124** (PR #206): the cross-boundary `arch-manifest.json` + `tests/test_arch_manifest.py` — declared ground truth (as tests, not prose) for the edges the import graph structurally cannot see: external subprocess calls, guarded entry points, client↔server rule-literal duplication, cross-stage receipt formats. Both open PRs (#199/#206) went through the same adversarial review as every batch before them and found real findings anyway — notably legacy per-district CLIs that had bypassed the new abandoned-batch guard, closed with a district-grain sibling guard.

### The four commandments reframe automation as a correctness requirement, not a convenience; epic #209 ships its first runtime guardrails (2026-07-09/10)
With the hygiene campaign closed and Stage 8/Council Lab/Stage-7-outcomes-tuning-Stage-5 all approaching, Ian named four governing priorities that now frame every automation decision on this project: **auditability** (the north star — bring insight to public K-12 debates; keep assumptions visible and challengeable), **minimize incorrect data reaching the LCT DB at scale** (a single human manually inspecting up to 20,000 districts is *not* a reasonable QC measure — which makes automated guardrails a **correctness requirement**, not a nice-to-have), **tight cash spend**, and **best use of one person's time**. The standing posture: *"as automated as is tolerable."* This reframes the existing ramp-up model (manual-first, ease toward auto as reliability is proven) rather than replacing it — the commandments are *why* the ramp exists, made explicit.

Before building, Ian commissioned deep research (three parallel prompts to four external services) synthesized into `docs/technical-notes/production-quality-control-research/FINDINGS-AND-DECISIONS.md`. Its headline finding: the **"illusion of improvement"** — a Stage-5 tuning pass measured only on the approved/labeled set is structurally blind to recall collapse in the reject pile, because the filter is *deterministic* (Swaminathan & Joachims: counterfactual correction is impossible under deterministic filtering even with infinite data — only injected stochasticity recovers the signal). This, plus the rule-of-three insight that calibration data justifying an auto-threshold accrues only *forward in time*, drove a build-the-instrument-before-you-need-it discipline for three pieces, all shipped 2026-07-10:

**#208 (PR #215) — the recall floor, finally enforced, not just reported.** A pre-existing floor was inconsistent (frontier used 0.97, the tuning ledger used 0.98) *and* non-binding (both pinned to tier-A recall, which sits ~0.89 by design since borderline targets route to review — an unmeetable target). Canonicalized to one constant defending **A+B recall** (reaches-review, not the auto-send bucket) and — the substantive fix, found by a max-effort review of the first draft — moved the enforcement point **inside** the re-ingest transaction, so a violation now rolls back the *entire* re-ingest instead of reporting a violation after the bad config's tiers were already live in the working-store DB.

**#211/REQ-120 (PR #216) — the anti-survivorship exploration quota, reframed mid-design.** Ian's own working habit changed the spec: because he census-labels every completed district (all tiers, rejects included, not just what the filter surfaces), the "illusion of improvement" hole is **not currently active** — the harness recall is already honest. The quota is therefore not a fix for today; it's the instrument that *replaces* census-labeling the day it stops (gate@5 going auto). The control law that fell out of that framing: a rolling-window randomized-sample **count** (rule of three, not a percentage — a percentage floats on stale labels and re-imports the manual-at-scale problem the commandments rule out), a **deadband** to prevent auto↔manual flapping, and **demote, never halt**, on a lapse. A review round then found the deadband's own guarantee was unenforced (a caller could invert it and cause the exact flapping it exists to prevent) and hardened it.

**#210/REQ-121 (PRs #217+#218) — the gate-decision calibration log, built then wired live.** Shipped in two deliberately separable steps matching the harness/frontier precedent (pure core first, no DB, no cash) — then wired into gate@5/6/7 in a follow-on PR, at which point a second review round caught three real corpus-corruption risks the first pass missed: gate@5's "unsure" hedge button could leak a stale confident label into the corpus; gate@6 could log a dispatch as agreed-with-auto when zero reps actually sent; gate@7's extraction lookup lacked a probe-run exclusion filter its own sibling query already had.

*Lessons: (a) a governing framework stated explicitly (the four commandments) changes what counts as "done" — automation guardrails moved from optional to required the moment 20,000-district manual QC was named as categorically infeasible. (b) the deep-research-then-decide sequence paid for itself immediately: the "illusion of improvement" finding directly produced the census-labeling reframe, which changed #211's scope before a line of live-wiring code was written. (c) the adversarial review pattern from the hygiene campaign held at a new altitude — these are infrastructure/guardrail PRs, not user-facing bugs, and review still found a transactional-enforcement gap, a deadband-inversion bug, and three calibration-corpus-poisoning paths, none of which a green test suite alone would have caught.* Authority: `production-quality-control-research/FINDINGS-AND-DECISIONS.md` (the research synthesis + decisions), `PIPELINE_GOVERNANCE_AND_STATE.md` §11b (the full guardrail design + as-built detail), `STAGE5_FILTER_DESIGN.md` §5a/§5b; issues #208/#211/#210 (epic #209); PRs #215/#216/#217/#218 (all merged).

### Epic #209 Phase 2 merges, epic #200 (shift-left test infra) is built, and a second live shakedown re-validates the hardened request loop — catching two real regressions the first pass couldn't have (2026-07-10/11)
Phase 2 of the runtime-guardrails epic landed and merged (PR #220): a group-aware non-inferiority promotion gate (#212 — LOGO-CV + a cluster bootstrap + TOST + ICC/DEFF, deliberately built on proven statistics libraries rather than hand-rolled math, per Ian's explicit call — "building our own seems much more likely to introduce defects") wired advisory into Stage 5's frontier tuning, plus safe-promotion machinery (#213 — an immutable content-addressed config artifact + `@champion`/`@fallback` DB pointers). Both ship **dormant** by design (the standing rule from this project's guardrail work: build the instrument before the auto-transition needs it, activate deliberately later — tracked as one checklist, #219). In parallel, epic #200 (shift-left defect-prevention test infrastructure — a DB-free test-job guard #201, a pre-push git hook #202, property-based state-machine tests #203, an AST mutation sweeper for the highest-stakes pure cores #204) was built and reviewed on its own branch, surfacing ~46 mis-marked tests along the way.

With both epics' code in hand, a **second live non-benchmark shakedown** (batch_00013) re-ran the request-more-evidence loop end-to-end — not because the first pass (#122, closed 2026-07-06 with a full retrospective) was incomplete, but to re-validate the loop against the now-hardened pipeline. Driven collaboratively (Ian at every console gate/button-press, the assistant observing completed state and diagnosing only — a posture corrected mid-session after the assistant twice reached for a batch-creation/server-start action that was the operator's to take), it found two genuine request-loop regressions that a green test suite had not caught: **gate@7's district view read the LATEST extraction only**, so a scoped `7→6` retry's own barren result could make an *earlier* run's solid facts (seven accepted schools, in one case) disappear from the console — data never lost, only the read wrong (#232, fixed with a new pure cumulative-merge core across all of a district's production runs, codified as **REQ-122**: follow-up rounds fill gaps, they never regress solid signal); and **the `7→6` alternate list could re-offer an already-failed rep**, because the exclusion set was scoped to the current dispatch only, not the record's whole round history (#231) — audited down to two separate layers (detection *and* execution) that both needed the same fix, closing a real gap in the execution-side protection that had silently existed since an earlier fix (#145) narrowed it to a single-file field. Both fixes shipped on the same branch as epic #200 (PR #221, not yet merged). The pass also surfaced several upstream findings across Stages 1–6 (a wrong-day-type school entering a draw, a missing confounder checkbox, a console filter bug, discovery contamination from a blank source field, initial-dispatch rep selection not reusing the retry loop's own yield-ranking) — logged for later, not fixed during the shakedown itself, matching the project's established discipline of not context-switching mid-exercise.

*Lessons: (a) the human-in-the-loop gate caught what a green test suite and code review both missed, for the third time this project has documented the pattern (the hygiene campaign, epic #209 Phase 0/1, now this) — the ramp-up model's cost (a human watching real output) is also exactly its value. (b) "the fix is on this session's branch" is not the same claim as "the issue is closed" — GitHub issues here close on merge, not on local commit, and treating them as equivalent mid-session produced a real, if harmless, tracking confusion this pass had to untangle. (c) verify a referenced issue's actual state before reasoning from it — an assistant treated a CLOSED, already-completed issue (#122) as the open umbrella for an entire session's work, an error only caught when asked to reconcile documentation against the live tracker rather than the session's own narrative.* Authority: `STAGE7_EXTRACT_DESIGN.md` §6 (the full mechanism + measurement detail), `STAGE8_AGGREGATE_DESIGN.md` (REQ-122's forward relevance to the not-yet-built Stage 8), `PIPELINE_GOVERNANCE_AND_STATE.md` (current-status banner); issues #212/#213 (epic #209 Phase 2), #201–204 (epic #200), #231/#232 (fixed)/#230/#233 (open)/#222/#223/#224/#225/#226/#227/#228/#229 (upstream, open); PR #220 (merged), PR #221 (open).

### Epic #200 merges, the batch_00013 shakedown's own follow-up batches surface four more request-loop bugs, and gate@7 gets its one deliberate auto-action — with the risk-asymmetry rule that justifies it named explicitly (2026-07-11/12)

PR #221 (epic #200: DB-free test guard, pre-push hook, property tests, mutation sweeper, plus #231/#232) merged after a max-effort adversarial review found 15 real findings in the merge candidate itself — not hypothetical nitpicks: `_sent_files_by_rec` (the execution-side "a rep that failed once is never re-offered" guard) only checked `7→6` history, asymmetric with the very `7→3`-inclusive detection-side fix (#231) the same PR shipped; `_covered_bands_now`/`_district_request_inputs` lacked a `run_kind='production'` filter, so a vision-council probe's accepted fact could auto-reject an already-*human-approved* directive at compose time. Both fixed before merge, each with a regression test. Separately, PR #239 shipped an automated `node:test` harness for `capture_discovery.mjs`'s browser-driving logic (real headless Chromium against `page.route()` in-memory fixtures — researched first, deliberately not a fixture HTTP server or a faked `page`, both explicitly against Playwright's own community guidance) and closed epic #123; its own review caught a genuine `segmentChrome` bug (header/footer/nav grabs ignored the `landmarks` argument entirely, silently masked because the current config happened to match the hardcoded selectors) and hardened the harness to fail loud in CI rather than silently skip when Chromium is missing.

Tracing batch_00013's own 7→2 follow-up batches (14–17) to completion — not a new exercise, just following the second shakedown through to its natural end — surfaced four more real defects, all fixed together in **PR #240**: **#234**, executing one council request duplicated its still-open siblings, because dedup was scoped to a single handoff and executing a `7→6` spins a brand-new one for the whole district; **#235**, the follow-up autoflow silently never ingested Stage 4's output into Stage 5 at all (traced definitively, not guessed — autoflow was simply a *second* caller of Stage 4's run function that forgot the ingest call its sibling caller already had); **#230**, Stage 6's initial rep pick ignored the retry loop's own yield-ranking, wasting a round on a thin rep while a denser one sat unsent; and **#236**/**#237**, aggregation-quality gaps (a school name double-counted under two spellings; NCES's school-count column overriding a multi-campus charter network's real per-school topology) found while tracing the same follow-up journey, filed but not yet fixed.

**#233 — should the request loop auto-withdraw a directive once a later round satisfies it — got resolved with an explicit design call, not a default.** Asked directly, Ian's answer was that the acceptable failure mode is a visible band gap, weighed against the downside of NOT auto-withdrawing: a human burning a paid round approving/executing a request whose gap a later round had already filled. Generalized into a standing rule now written into the code and the governance doc: ***auto-act in the spend-conservative direction when the failure mode is observable and reversible*** — the test for admitting an automatic action isn't "is a human in the loop," it's whether automating trades an unbounded, non-self-correcting failure for one that's cheap, visible, and one click from undoing. Codified as **REQ-123**. The adversarial review of the *first draft* of this exact fix then found it didn't fully live up to its own rule: the fillable-band computation silently fell back to unfiltered claimed bands whenever a district's real-school data came back genuinely empty — reproducing, for a different trigger, the exact "un-withdrawable forever" bug #233 was filed to close — and, more fundamentally, the withdraw check couldn't see its own transaction's just-persisted facts in production at all, because the session runs `autoflush=False` and the persist path never flushed before returning; every test had passed only because the test fixture defaults to `autoflush=True`. Both fixed, both proven by tests built specifically to distinguish "passes on the test's assumptions" from "passes on production's actual configuration" (a dedicated production-session-parity test with zero test-side flushes).

*Lessons: (a) a fix and the rule it's supposed to embody are two different things to verify — the auto-withdraw code and its "observable, reversible" justification were both written with good intent, and the adversarial review still found the code didn't yet match the intent. (b) a test suite that all passes can still be testing the wrong reality — the autoflush mismatch between the test fixture and production meant #233's actual primary use case had zero real coverage despite 100% green, until a review pass thought to ask "does the test's session behave like the real one?" (c) when a user states a governing principle in response to a specific decision, that principle usually generalizes — capturing it once, at the decision site and in memory, means the next similar call (the #104 gate-mode toggle, future runtime guardrails) doesn't have to be re-derived from scratch.* Authority: `STAGE7_EXTRACT_DESIGN.md` §0/§6 (the full mechanism + PR #240 decision-log entry), `PIPELINE_GOVERNANCE_AND_STATE.md` §11b (the risk-asymmetry rule, stated as gate@7's one deliberate exception to the ramp-up model), `docs/REQUIREMENTS.yaml` REQ-123; issues #230/#233/#234/#235 (closed, PR #240), #231/#232 (closed, PR #221), #127 (closed, PR #239), #123/#200 (epics, closed), #236/#237/#238 (open); PRs #221/#239/#240 (all merged).

### The phantom-districts hallucination — origin of Rule #6 and the DB-verify hook
This happened **twice**, which is why the safeguard is non-negotiable:
- **Dec 2024:** a reported "137 districts enriched" was found to be inflated — 135 were statutory fallback, only ~4 had real schedules. *(Source: `terminology_standardization_session_20241221.md`.)*
- **Jan 2026:** LCT CSVs falsely labeled 101 districts as having `bell_schedule` data when the true source was statutory fallback; the CSV claimed 183 while the DB had ~82–103. **The database was correct; the CSVs were contaminated.** Exact mechanism stayed inconclusive (traced to mislabeled statutory-fallback JSON). Fix: deleted all contaminated outputs and added count-vs-DB verification, content-plausibility checks, and an override audit trail (REQ-035–039). *(Source: `RECONCILIATION_REPORT_20260124.md`; the fabricated artifacts `SESSION_HANDOFF_2025-12-26.md` / `-27.md` now carry "HALLUCINATED CONTENT" banners in git.)*

**Lesson, now CLAUDE.md Rule #6:** *always verify data exists in the database before claiming enrichment counts; never trust handoff documentation.* Handoff docs propagated false numbers across sessions unchecked — that is the failure mode the rule exists to stop. The pre-commit hook that DB-verifies enrichment claims is the automated enforcement.

### "Enriched" ≠ "statutory"
Statutory state-minimum data must **never** be counted as enriched. Enforced by separate storage (`method = statutory_fallback`), required metadata, and the rule that enrichment functions **return `None` on failure rather than silently fabricating a statutory entry**. The check must be on `method`, **not** confidence level (statutory data can carry "medium" confidence). *(Source: `ENRICHMENT_SAFEGUARDS.md`.)*

### Silent failure is the recurring enemy — fail loud
A full audit found enrichment scripts shipping **template/placeholder code in production paths that "succeeded" without doing anything**, confidence-not-method enrichment flags, and a pipeline that ran enrichment *before* normalization (so it silently skipped). Recurring lesson: silent fallbacks/defaults and stub code in prod paths are the dominant failure mode — prefer fail-loud, return `None`, and validate outputs *between* pipeline steps. *(Source: `MEGATHINK_ANALYSIS_REPORT.md` + `FIX_PLAN.md`.)*

### The image-processing stall — why "local tools first" exists
The Read tool failed with "Could not process image" on a downloaded PNG bell schedule, and the session **repeatedly retried the same failing API call** instead of pivoting to already-installed tesseract — burning tokens and stalling Wyoming enrichment. Root cause: tool knowledge lived only in context, with no documented fallback. Also a smaller lesson: the assistant declared "schedules are stored as PNG images" as a *blocker* when it was merely an *observation* (images are OCR-readable) — distinguish observation from obstacle. *(Source: `stalled_session_transcript_202512211027PST.md`.)*

### Scraping ethics & the 404 heuristic — the Memphis-Shelby near-miss
Automation once hit 4+ 404s and was about to **silently fall back to statutory data and call it "enriched"**; the user caught it. This is the origin of two rules: **(1)** ≥4 404s in one district auto-flags for manual follow-up (multiple 404s usually mean WAF/Cloudflare hardening, not absent content); **(2)** on detected Cloudflare/WAF, **one search + one fetch attempt, then flag and move on** — never attempt bypass workarounds (districts block scrapers for reasons; bypass services are ethically questionable). Codified in the `enrichment_attempts` table so known-blocked districts aren't re-attempted. *(Source: `ENRICHMENT_SAFEGUARDS.md`, `ENRICHMENT_TRACKING.md`.)*

### Automated scraping has a low ceiling — design for it
A 733-attempt / 245-district Playwright run yielded only ~6.5% success. Durable realities of district websites: **80%+ publish no district-wide schedule** (data lives on individual *school* subsites → subdomain discovery is essential); 75%+ require JS rendering; a 30s timeout is too short for Finalsite/React SPAs; CMS mix ~25–30% Finalsite, 15–20% SchoolBlocks. CDN blocking is systemic, not occasional (MI = Cloudflare, VA = Akamai both block automated clients; PA/MA download cleanly). These numbers set realistic expectations for the acquisition pipeline. *(Source: `bell_schedule_automation_2026-01-22.md`, MI/VA integration logs.)*

### A small, real human checkpoint finds bugs a bigger automated check can't — and "exactly N" is usually the wrong rule (2026-06-22)
Walking Stage 1's first real batch with the human reviewing actual output (CP-A) surfaced two genuine bugs — school dilution into the wrong band, and a parser blind to NCES grade code "13" — that the automated grade-span-gap checker (Rule 7) structurally could not have caught: a diluted-but-nonzero candidate pool and a healthy one look identical to a check that only asks "is this band empty." Neither bug would have surfaced from a design review of the *code*; both surfaced from a human looking at a dozen real school names. Second lesson, layered on the first: the initial fix for the dilution bug was scoped to "exactly 2 schools" specifically to avoid disturbing three already-validated districts — but profiling the *full* corpus (not just the cases at hand) showed school-count was never the real dividing line; the actual distinguishing property (do a district's grade spans form a clean ascending partition) reclassified one of those three "already fine" districts as needing the same fix after all. **Takeaway:** prefer a rule's *real* invariant over whatever condition happens to separate the examples in front of you, and check that invariant against the full dataset before trusting a narrow fix is actually narrow. *(Source: this session's Stage 1 build, see entry above; `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE1_QUEUE_DESIGN.md` §6 for the turn-by-turn record.)*

### The empty-domain contamination chain — prevention, remedy, and cleanup shipped together, then a second adversarial pass found the prevention wasn't deep enough (2026-07-11/12)
Millard Public Schools was the one district in batch_00013 with a blank NCES `WEBSITE`, which flipped Stage 2 discovery into its unscoped, national-scope branch and pulled same-named schools nationwide into the candidate set (#227) — 102 distinct hosts over 147 captures, only 44 on the real domain. The fix shipped as three linked pieces in one PR (#242), each answering a different question: **#229** (prevention) refuses a district at Stage-1 admission when its NCES `WEBSITE` normalizes to no usable scoping host — validating the *normalized* host, not just non-emptiness, because the raw NCES column carries a large non-blank-but-junk tail (`http://N/A` → `n`, `http://375 LEE ST` → `375 lee st`) that a bare blank-check would miss; **#228** (remedy) added a gate@5 "Reset labels" action, because a page that IS a valid schedule for the *wrong* district has no honest existing label — `target_absent`/`unusable` both assert a false non-target ground truth, so `unlabeled` had to become reachable again; **#227** (cleanup) shipped a manifest-first, dry-run-by-default script for the one district that got contaminated before the guard existed. A full max-effort adversarial review of the merged PR then found 15 more real defects, the most architecturally significant being that **#229's guard only existed at the Stage-1 front door** — Stage 2's own `gate_urls()` still decided scoped-vs-unscoped with bare `bool(domain)` truthiness, so a blank domain reaching Stage 2 through *any other path* (a manual DB edit, a future batch-builder, or the remediation script's own `--domain` flag) would reproduce the exact contamination the guard was built to prevent. Fixed by making Stage 2 fail closed at the single gating chokepoint all discovery waves share, independent of whether Stage 1's guard ran at all — the review's other findings included a transaction-safety bug in the remediation script (it wrote `labels.json`/the batch receipt to disk *before* several more statements that could still roll back the DB, so a late failure would leave the precious JSON backups permanently ahead of reality) and a UI claim that didn't hold up: the PR's own description said district refusals were "surfaced at gate@1," but the console never actually read the field the server returned — three of ten independent finder angles caught that same gap.

*Lessons: (a) a guard placed only at the admission point it was motivated by is not the same as a guard on the actual hazard — the review's "altitude" angle asked not just "does this fix the reported bug" but "does the fix's depth match the mechanism," and that question found the real gap the other nine angles' bug-hunting missed. (b) writing precious-state backups to disk before a transaction commits is the same class of bug the #228/save_label code had already gotten right (commit-before-export) — a second hand-rolled implementation of the same operation is a second chance to reintroduce a bug the first one already avoided, which is also why the fix consolidated both reset-label code paths into one shared function instead of leaving two. (c) a PR description's own claims ("this surfaces X in the console") are exactly the kind of thing to verify against the actual rendered UI, not just the API response — three independent review angles converging on the identical gap is a strong signal it was real, not a false positive.* Authority: `PIPELINE_GOVERNANCE_AND_STATE.md` §11a/§11b (the domain-exclusion visibility note + Stage 2's fail-closed defense as a second, differently-shaped automatic behavior), `STAGE2_DISCOVER_DESIGN.md` (the `gate_urls` decision-log entry), `ACQUISITION_PIPELINE.md` §1/§2 (the map + flow-diagram update); issues #227/#228/#229 (closed), #236/#237/#238 (open, aggregation-quality — separate follow-on work); PR #242 (merged, three follow-up commits closing the adversarial review's 15 findings).

### Charters need structure-aware handling: #237 was mis-diagnosed as a topology bug, and the investigation reframed how the whole project treats charters (2026-07-12)
#237 was filed as "labeled_topology hard-overrides to single_school on NCES count==1, ignoring real extraction evidence for multi-campus charter networks" — the hypothesis being that NCES *undercounts* a CMO, so a real 8-school charter was being mislabeled `single_school`. A first implementation reclassified those districts to `per_school`. **The premise was wrong, and real data + external research showed it.** In NCES CCD each charter campus (Brooklyn/Bushwick/Brownsville Ascend, …) is its **own LEA** with its own LEAID; "Brownsville Ascend" genuinely IS one school (`nces_count=1`/`single_school` were correct). The inflated Stage-7 school counts were **cross-LEA contamination** — sibling charter LEAs pulled from a *shared CMO domain* (`ascendlearning.org` serves all 12 Ascend campuses, so domain-scoping "worked" yet returned the whole network), or blank-domain unscoped captures (the Millard #227 class). So the topology change was **reverted**; the real fix is a `detect_single_school_over_extraction` detector (a `nces_count==1` LEA yielding >1 distinct school is flagged for human review at gate@7, **detect-and-flag, never auto-reject** — picking the real school is unreliable because shared network names like "ascend" recur across siblings and acronyms like "DECA"="Dayton Early College Academy" fail a name match). A crude "reject any school matching a different LEA" detector was rejected outright: it trips on 15.8% of *all* facts, almost all common-name false positives (a legit "Lincoln Elementary" matching some "Lincoln" LEA) — the pipeline already attributes by LEAID and scopes by domain, so contamination only enters where domain-scoping *fails* (shared CMO domain, or blank domain), which lands exactly on single-school LEAs. A deterministic bonus signal fell out: **a `batch_district.domain` shared across >1 LEAID is a CMO network domain** (confirmed live — `summitacademies.org` → 2 LEAIDs), flaggable with no external crosswalk. **The broader reframe (Ian's, decision-level):** the project's founding choice to treat charters/CMOs as equivalent to district-managed schools does not hold at scale; charters need **structure-aware** handling, split into three layers — (1) *acquisition contamination* (this detector, done); (2) *analysis segmentation* — report charter LCT separately, never blended, the SPED-segmentation precedent and the documented equity-metric consensus (#243); (3) *the structure-C carve-out* — dependent charters reported inside a host district's LEA (CCD structure C = **20.6% of enrollment**, concentrated in the large target districts), whose staff/enrollment must be pulled out of the host before its ratio is computed (#244). Deep research (`docs/research/CMOs-and-charter-schools/`) grounded the CCD taxonomy: structures A (single-campus charter LEA), B (multi-school charter LEA), C (dependent charter under a traditional host) are all detectable from CCD (`LEA_TYPE=7` + `ccd_sch` charter-flag counts); the governing LEA is always `NCESSCH[:7]`; there is **no CMO identifier in the public CCD CSVs** (sibling-grouping needs EDFacts FS196/FS197 EIN crosswalks or NAPCS, and is not required for contamination rejection). #236 (norm_school district-suffix dedup — "Union Hill" == "Union Hill ISD") shipped alongside, independent and correct.

*Lessons: (a) a bug report's stated mechanism is a hypothesis, not a finding — verifying "is NCES undercounting, or are we over-collecting?" against the actual CCD LEA structure flipped the entire fix and prevented shipping a change that would have *legitimized* contaminated data. (b) the safe detector is the one scoped to where the failure actually occurs (single-school LEAs) rather than the general case (all facts vs. the whole LEA universe), which is what made the false-positive rate collapse from 15.8% to ~0. (c) detect-and-flag beats auto-reject when the *detection* is reliable but the *remedy* (which school to keep) is not — matching the manual-gate ramp-up posture.* Authority: issues #237 (reframed), #243/#244/#245/#246 (follow-ups filed); `docs/research/CMOs-and-charter-schools/` (the grounding research); commits `3353632` (code) + `214ce56` (research).

### The exploration quota shipped end-to-end, closing the "illusion of improvement" — epic #209's build complete (2026-07-12)
Epic #209 (runtime guardrails for the manual→auto transition) reached build-complete: Phase 0 (#208 recall floor, #210 calibration meter), Phase 1 (#211 exploration quota, #214 measured-pass), Phase 2 (#212 promotion gate, #213 safe-promotion machinery). The two Phase-1 items were the highest-value work in either guardrail epic, because the research (`FINDINGS-AND-DECISIONS.md` §0) established that **"the illusion of improvement" is a *current* blind spot, not a future risk.** Tuning the deterministic Stage-5 filter and measuring before/after only on the *approved/labeled* set is structurally blind to recall collapse — the wrongly-rejected docs never enter the measurement, so a tuning pass can certify a regression as a win (Swaminathan & Joachims: under deterministic filtering counterfactual correction is impossible even with infinite data; only injected stochasticity recovers the signal). **#211** built the instrument: a revocable autonomy *license* on gate@5 auto-suppression — a random reject-audit whose rolling window of human-labeled rejects (rule-of-three: ~300 zero-miss ⇒ 95% confident the reject FN-rate <1%) must stay full, or gate@5 auto **demotes to manual** (never halts — autonomy falls back one supervision level). Its pure control-law core (`exploration_audit.py`) was built+tested first (PR #216); the live wiring (`exploration_live.py`) followed — the reject-population query, the coverage meter, and the gate@5 demote-hook wired into `save_label` (self-healing) + a Settings-console meter, all reading the #104 `gate_mode` store; enforcement ships DORMANT (gate@5 is configured manual → the hook returns manual and writes nothing). A key design call: current-config scoping is **structural** (the window is recomputed over the live tier-D set — a rescued reject just leaves the population), so there is no reject-audit table and no persisted config generation. **#214** then closed the measurement hole the quota exposed: a single pure instrument (`harness.exploration_cohort`) threaded through all three measured-pass surfaces — the harness scorecard, `frontier` (every grid config + a champion→challenger reject-quality warning in `--gate`), and the `tuning_ledger` episode (a `reject_cohort_quality` delta + advisory `reject_quality_regressed` flag) — so **every** scoring measured-pass now reports Rejection-Quality/TNR on the pruned tail beside approved-set precision/recall. Retroactive #108 re-verify: reject-quality/TNR = 1.0 under the live config, so #108's approved-set win (0.8382→0.8444) hid no pruned-tail collapse. Verified live: 566 tier-D rejects, ~24 sampled @5%, all census-labeled zero-miss → the audit is *informational* today (census-labeling means every reject is already looked at), exactly as designed — the quota is the instrument that *replaces* census-labeling, switched on before it switches off.

*Lessons: (a) the highest-value guardrail was not a new autonomy feature but a fix to how we already measure everything — the research reframe (a "future risk" is a present blind spot) reordered the whole epic. (b) build the instrument while the ground truth is still observable (census labels still accrue), and calibrate the sampler against that truth before leaning on it — the same "build the gauge while the truth exists" logic as the calibration meter. (c) enforcement-ships-dormant (the `--assert-floor` pattern) let both #211 and #214 land with their full capability wired live yet behavior-neutral, so the switch-on (#219) is a config flip, not a build.* Authority: `FINDINGS-AND-DECISIONS.md` §0/§1, `STAGE5_FILTER_DESIGN.md` §5a (the quota) + §5d (the measured-pass fix), governance §11b; issues #211/#214 (this work), #208/#210/#212/#213 (closed), #219 (the dormant→live activation checklist, correctly outliving the epic); commits `817d78e` (#211) + `ce5ba03` (#214). Deferred by design (gated on unbuilt stages / accrued data): drift monitors, budget-governor hardening, Stage-9 write-boundary invariants, and the per-gate transition *thresholds* (blocked on #210 accruing data + gate@8).

### A max-effort review found real bugs in already-tested guardrail code, and a stacked-PR merge landed on the wrong branch — both caught before Stage 8 work began (2026-07-12/13)

Before merging the #236/#237 (aggregation-quality) and #104/#211/#214 (gate-automation) work, a 34-agent max-effort review (16 finders, 20 verifiers, 2 gap-sweeps) ran against both PRs and surfaced 15 CONFIRMED findings the full test suite hadn't caught — most severely: **`gate_mode.set_license_state`'s fresh-row INSERT hardcoded `configured_mode='manual'`, silently and permanently pinning a globally-auto-configured gate to manual on its FIRST license write** (the exploration-audit demote-hook is exactly such a writer) — a defect that would have made #211's own core inheritance model unusable the moment anyone actually used it as designed. Also confirmed: `norm_school`'s widened stopword list both **over-merged** distinct schools ("Meridian Consolidated School" == "Meridian School") and **under-stripped** hyphenated spellings ("Lincoln-Unified..." failed to normalize like "Lincoln Unified...") — opposite failure modes from the same regex change, both defeating #236's own stated purpose for common real-world name shapes; the fix made `norm_school` idempotent and had `merge_fact_runs`/the #237 detector re-normalize *persisted* keys at read time, so a future stopword-list change self-heals instead of silently fragmenting the REQ-122 cross-run merge. Also fixed: an un-isolated demote-hook transaction (a transient DB error could roll back a valid label save), an unindexed full-table-scan query running on every label click regardless of dormancy, a `javascript:` URI XSS vector in the Settings console, and a misfiled test-class insertion that orphaned a regression assertion into an unrelated test (caught independently by 5 of 16 finder agents — the strongest corroboration signal in the whole review). All 15 were fixed, verified (1211 DB-free + 187 govdb passing), and pushed before merge.

Then, merging surfaced a **second, distinct defect — in the merge process itself, not the code.** The gate-automation PR was stacked on the aggregation-quality PR's branch (to dodge a rebase conflict from 5 files both touched); its description explicitly flagged the requirement to retarget its base to `main` after the parent merged. That retarget never happened before the merge button was clicked — GitHub dutifully merged the PR's commits into the now-orphaned feature branch, which showed as "merged" in every UI signal, while `main` received none of the code. The gap was only caught because the next task (this doc-tower resync) started by verifying `main`'s actual file contents against what the docs were about to describe — `gate_mode.py` didn't exist there. Fixed by cherry-picking the identical, already-reviewed commits onto a fresh branch cut from the real `main` (content verified byte-identical via `git diff` before merging), landed as PR #250.

*Lessons: (a) a green test suite and a prior code-review pass do not substitute for a fresh, systematic adversarial pass immediately before merge — this review found a defect (the inheritance clobber) that would have silently defeated the exact feature it was reviewing, in code that already had passing unit tests written for adjacent behavior. (b) independent corroboration across many finder agents is itself a signal: the test-class corruption finding recurred in 5 of 16 unrelated angle-runs, which is strong evidence a finding is real even before formal verification — weight recurring findings accordingly. (c) "the PR shows as merged" is not the same claim as "the code is on `main`" — a stacked PR's base can silently go stale the moment its parent merges, and the only way to catch it is to verify the target branch's actual file contents, not trust the platform's merge status. (d) catching this before touching the docs prevented compounding the error: a doc-tower resync against a fictional `main` would have created a second layer of drift on top of the first.* Authority: the review's 15 findings (fixed in commits `c30aa1f`/`aaf2553`, re-landed via PR #250's cherry-picks); `PIPELINE_GOVERNANCE_AND_STATE.md` §11b (the inheritance-clobber fix + the incident note); `STAGE5_FILTER_DESIGN.md` §5a, `STAGE8_AGGREGATE_DESIGN.md` §1a (the `norm_school` rewrite); issues #211/#214 (closed 2026-07-13); PRs #247 (merged), #250 (merged, the corrected re-land).

### A cross-family external review harness applies the extraction council's own diversity thesis to code review — and iterating against real model behavior found six harness bugs before the real findings were trustworthy (2026-07-13)

Every prior review of this codebase was Claude reviewing Claude, sharing whatever blind spots Claude's training carries. `tools/crossfam_review/` (deliberately outside `infrastructure/` — it reviews the pipeline, not part of it) applies the same mechanism the extraction council already proved (REQ-056: cross-family diversity + a load-bearing third-family judge) to code review itself: **10 non-Claude OpenRouter finder families** (DeepSeek, Moonshot, Qwen, Xiaomi, MiniMax, Google, OpenAI, xAI, Mistral, Meta) each review the whole codebase, findings are deduped and filtered to those **≥2 families independently flagged** (`--min-agree`), and a **rotating 3-family judge cascade** (gemini-2.5-pro / gpt-5.6-luna / deepseek-v4-pro — rotating so no model is a permanent tie-breaker) adjudicates the corroborated set before anything is filed to the tracker.

Before the harness could be trusted with real spend, three rounds of staged smoke tests surfaced and fixed real bugs the design hadn't anticipated: **z-ai/glm-4.7-flash and a GPT-5-series finder both "reasoning-drowned"** — they stream internal reasoning in a channel the shared streaming client can't capture, burning their whole token budget before emitting an answer, returning **billed-but-empty** content (caught by a new `∅` telemetry flag, not a silent clean pass); **the finder payload initially had no line numbers**, so models miscounted lines across a multi-file shard (`server.py:766` reported as `:425`), which then misaligned dedup and the judge's code context and got every finding refuted — a broken evidence chain that looked like "the council found nothing," not "the pipeline is broken"; and a **weak-confirm bug** in the judge tally let a single surviving vote confirm a finding when the other judges had merely errored out at a spend cap, fixed by requiring ≥2 real (non-error) votes. *Lesson: an LLM-orchestration harness's own failure modes (reasoning-channel drowning, positional miscounting, silent-error-as-abstention) are exactly the kind of defect a quick "does it produce plausible output" check won't catch — they need the same adversarial, receipts-first verification discipline the pipeline applies to its own extraction.*

The campaign that followed the fixes: 2,949 raw findings → 1,833 unique → 459 corroborated → **214 confirmed**, filed as GitHub issues `#259`–`#472` under label `crossfam-review-2026-07-13`, each carrying a machine-parseable `crossfam-meta` marker (which finders found it, how the judges voted) for later effectiveness analysis. Total spend ≈$22.4 against a $25 authorization (raised mid-campaign once the finder pass ran ~2× the pre-flight estimate — the reasoning finders' internal thinking is billed as completion tokens the estimate hadn't accounted for). A `--resume-council` mode judges only the candidates a capped run left un-adjudicated, reusing the saved finder output rather than re-paying for a second full pass — built reactively when the first campaign hit its cap mid-council, then had its own resume-identity bugs (a category-less legacy record defaulting to `""` could collide two distinct un-judged findings into one; the judge rotation was keyed on list position, so a resumed candidate could land on a different voter/tiebreaker triple than an uninterrupted run would have given it) found and fixed by a full **max-effort code review of the harness itself** (10 finder angles + sweep, ~50 raw candidates → 14 deduped → 13 CONFIRMED/1 PLAUSIBLE) before the harness's own PR (#477) merged — the most severe of that batch was a **path-traversal**: `code_context()` built a filesystem path directly from an untrusted, model-supplied `file` field with no traversal guard, so a hallucinating finder could cause the judge pass to read and ship arbitrary local files (e.g. `/etc/passwd`) to three external LLM APIs.

Effectiveness analysis (`docs/technical-notes/CROSSFAM_EXTERNAL_REVIEW_2026-07-13.md`) quantified the diversity thesis directly: the two most-agreeing finder models still only overlapped on 28% of what each found (max pairwise Jaccard), and only 2 of 459 corroborated candidates were ever flagged by all 10 finders — confirming that a single-family reviewer (Claude or otherwise) would structurally miss most of what a diverse panel catches. A **naive family-bias test** (does a judge confirm its own-family finder's work more often?) looked damning at first — all three judges appeared to confirm their family's findings *less* — until controlling for finder quality (a noisy finder's candidates get confirmed less by every judge, not just its kin) reversed the read entirely: the one statistically significant effect was `deepseek-v4-pro` being *measurably stricter* on `deepseek-v4-flash`'s own findings than other judges were, and no judge showed in-group favoritism. *Lesson, the same discipline as the ICC/DEFF clustering correction in the promotion gate: an uncontrolled statistic can point exactly backwards — always ask what's confounded before trusting a headline number, especially one that "confirms" a suspicion.*

Two stray-scope incidents were caught and resolved cleanly rather than compounding: gate@8 approval receipts (real district data, unrelated to the harness) were accidentally swept onto the review branch by the pre-commit hook's precious-state auto-stage and had to be landed on `main` separately before the harness PR could stay scoped; and the PR's eventual squash-merge was verified by **content diff against `main`**, not the platform's "Merged" badge, per the standing lesson from the #247/#250 stacked-PR incident above. Authority: `tools/crossfam_review/README.md`, `docs/technical-notes/CROSSFAM_EXTERNAL_REVIEW_2026-07-13.md`; PR #477 (merged `e5c22c8`); gate@8 methodology issues #257/#258 (Coffee County band-membership) and #473/#474 (TUSD band-recovery) opened alongside the campaign; extraction-to-standalone-package tracked as #475 (deferred — mirrors the fuzzy-environmental-dependencies pattern, #476).

### The tracker became navigable, the foundations got hardened, and gate@8 grew its four editorial primitives — both motivating districts approved (2026-07-14)

A full triage of the 284 open issues reorganized the tracker around **touch-minimization** (group by the file/module a fix actually opens, not by who found the issue — the crossfam-vs-human distinction was judged not intrinsically meaningful for resolution): 3 Stage-8 build issues closed as verified-built-in-code (#88/#89/#90 — REQ-109 flipped to `tested`; the ledger had said "not yet built" about machinery that was live), 5 new epics created (#478 Stage-8 post-build, #479 DB hygiene, #480 legacy-scripts hygiene, #481 test-suite quality, #482 repo tooling), and all 241 unattached issues linked as native sub-issues under 14 epics. The agreed work sequence: **infrastructure cracks first, then present-backwards through the acquisition pipeline (8→7→5/6→1-4), then the LCT foundation (#479→#480), then Stage 9** — downstream-first because Stage-7/8 fixes verify against receipts already in the DB (free replay) while upstream fixes need paid live runs; with pre-planned pull-forwards (stage-specific console findings ride with their stage's pass) and a **liveness gate** before the legacy sweeps (a dormant file's findings get closed "superseded", not fixed).

The hardening epics that followed, in sequence: **#482** — stacked-PR guardrails for the #251 incident class (a `pr-base-guard` check red on any non-`main` base; the lint/test workflows' `branches: [main]` filter dropped — the incident PR had run *zero* CI because stacked PRs matched no workflow at all; `delete_branch_on_merge` enabled so GitHub auto-retargets child PRs) and **REQ-124** shared-config JSON Schema validation (the config-as-data knobs are a cross-language Python+Node edge no import tool sees; a malformed key now fails the suite, not a stage at runtime — datacontract-cli on stage receipts split to #484, deferred until the Stage-8 artifacts stabilize). **#481** — the test-suite quality sweep: 23 of 26 crossfam findings fixed, 2 refuted with evidence, 1 deferred pending local data. The headline finds: `tests/test_bell_schedule_enrichment.py` imported **zero production code** (every test exercised a helper defined in the test class — deleted, REQ-003/REQ-017's `tests:` citations corrected, since a "tested" status backed by theater is worse than none), the `quality-assurance/` directory had **never been collected** by pytest (salvageable tests moved to `tests/test_utilities_common.py` — 23 tests now actually run), and 15 `actual = expected` tautologies (9 filed + 6 unfiled siblings found by sweeping the same files) became explicit `pytest.skip`s naming what would activate each. *Lesson: fixing the tests **first** in a hygiene campaign converts every later sweep's `pytest` run from theater into a real regression net — and a review's findings under-count within the files it flags; sweep the whole file while you're in it.*

**Epic #478** then built gate@8's four **editorial primitives** — the human actions live district review kept demanding: **#257 exclude-school-from-band** (over-inclusion: a correct observation whose band membership is stale — district-grain precious `band_exclusion` table keyed `(district_id, band, norm_school)` so the judgment survives re-extraction, excluded facts leave the mode but render struck-through-with-reason, in the receipt + staleness fingerprint); **#258 name-vs-level mismatch detector** (the flag half — pure predicate over both the roster and extracted-fact surfaces; live data validated the two-surface design: Coffee County's *extracted* names were `zion chapel k12` (correctly no flag), the token that flags lives in the *roster* name); **#473 recover-band re-extraction** (under-inclusion: an empty band whose sibling bands came from the same captured doc — a detector flags it with the rep identity, and a one-click action re-dispatches the *named already-sent* rep; **no band-targeted prompting needed because `merge_fact_runs` is fill-gaps-never-overwrite**, so a full re-read can only fill the hole — the property-test paid for itself as a design guarantee); and **#474 cited-source human-add** (the last resort — hand-entered times require a citation + both endpoints + the same REQ-055 plausibility gate, vote in the mode, render loudly tagged; #257/#474 are mutually guarded so an exclusion and a hand-add can never fight silently). **Both motivating districts cleared the gate the same day the primitives landed**: Coffee County `0100810` (Kinston + Zion Chapel excluded, band recomputed, approved) and TUSD `3416500` (recover-band staged from gate@8 → triggered at Stage 6 → elementary recovered by the council → approved). Also in the epic pass: the #403 None-gross rollup crash (TDD'd), and crossfam #450/#263 closed-with-rationale (#263's "hardcoded actor" is provenance labeling on a console with deliberately no auth layer — the server-side-identity fix is parked on epic #103 where the multi-user era lives).

*Lessons: (a) closure-by-verification beats closure-by-recollection — #89/#90 were "open" only because the ledger lagged the code, and the reverse error (REQ-003/017 "tested" on theater) lagged the other way; both directions of drift were caught by reading the actual source. (b) The detect-and-flag posture (#237's) generalizes cleanly: every new primitive pairs a detector (surface it) with a human action (resolve it), and the receipts freeze both. (c) A verified merge-algebra property (fill-gaps-never-overwrite) is not just a correctness proof — it eliminated an entire feature (band-targeted prompting) from #473's design.* Authority: epics #478–#482; PRs #483/#485/#486/#487/#488/#489/#490; REQ-109/REQ-124 in the ledger; `STAGE8_AGGREGATE_DESIGN.md` (the primitives' design home); remaining #478 tail: #253/#254 (Santa Fe combined-scope + school-year precedence) and #91 (extract-outcome → Stage-5 tuning feedback).

### Epic #478's tail closes: a "combined-scope name" is a text problem, "unknown year" must never mean "oldest," and a corpus measurement turns a grade-band guess into a scalpel — then a code review catches the one bug the corpus measurement couldn't (2026-07-14/15)

**#253** (Santa Fe combined-scope facts + a topology-blind denominator) split into two independent fixes rather than one. The denominator moved from a frozen clean-NCES-LEVEL count to a **LIVE band-serving roster** re-derived from the current CCD on every read (a school serves a band when its LEVEL says so *or* its own grade span reaches it — Santa Fe's middle band read "4 of 2 schools · 200%" before, "4 of 9 · 44%" after, once four K-8s the old denominator didn't count were included). A `combined_scope_name()` detector caught the other half — "k8 schools" and "milagro and ortiz schools" were landing as pseudo-schools inflating the sample, a text-shaped problem regardless of the denominator fix. Both follow the #237/#257 posture: **flag, never auto-drop** — a flagged fact keeps its vote until a human disposes of it. **#254** (school-year precedence) added one v3 prompt field, `school_year`, as a REQ-054-safe *reading* (never inferred from the URL/domain/today's date — Santa Fe's own stale fact came from a live, undated webpage, so format is a hint, never a rule), and a merge-precedence rule that a known-newer year beats a known-older one — with the sharp decision recorded explicitly: **unknown year coexists, it is never treated as oldest**, because every pre-v3 fact is unknown and the inverse rule would let one freshly-dated stale page silently supersede the entire existing corpus. The v3 rollout's first live district (Southern Lehigh PA) validated the design end to end: a genuine `2025-26` reading landed correctly, nothing was inferred, consensus behavior was unchanged from v2.

**#498** (grade-band taxonomy) started as a live specimen — Southern Lehigh's Joseph P. Liberati *Intermediate* School (grades 4-6) voting in the *middle* band because NCES tags it `LEVEL=Middle` — and was resolved by **measurement before rule-writing**: profiled against the full 2024-25 CCD (85,024 clean-LEVEL schools), LEVEL agrees with the grade span 98.9% of the time, and the *entire* disagreement class is this one shape (330 schools, 0.4%). The fix is a scalpel, not an inversion — LEVEL stays primary; one corpus-profiled override (`LEVEL=Middle` on a 4-6 span → elementary) — with a same-day follow-up ruling on the orphans the first pass punted (5-5/5-6/6-6 spans are unconditionally middle), which itself required tightening `bands_for_rescue`'s elementary eligibility and produced a second corpus measurement (129 schools/123 districts had been leaking a spurious elementary membership from the old start-at-5 rule; the fix is pure dilution removal, confirmed against every previously-pinned corpus regression case).

**Then a max-effort adversarial review of the #498 PR — 8 finder angles run in parallel, findings cross-verified — found a REAL correctness bug the corpus measurement's own test suite had not caught**: `real_bands_for_district`'s aggregate signal (raw LEVEL counts, no per-school span) never applied the new carve-out, so a district whose *only* "Middle"-tagged schools were all reclassified intermediates could still claim a phantom middle band — feeding directly into Stage 7's spend gate, which would then keep paying to chase a band no real school serves (56 real corpus districts matched this shape). Fixed by threading the live roster through every caller so the span-aware signal REPLACES the blind one, plus a matching fix to `name_level_mismatch` (which had inherited the same blind spot — flagging a school against its raw NCES level instead of the carve-out-corrected one, producing exactly the false-positive noise #258's own copy rewrite existed to prevent). *Lesson: a corpus measurement proves the RULE is right; it doesn't prove every CONSUMER of the rule was updated — a second, independent adversarial pass over the same diff is what caught the multi-signal divergence, not more measurement.* **#91** (Stage-5 extract-outcome calibration) and the **#229** console UX rework (a fresh batch's 1,456-district no-domain refusal list, previously an unreadable inline wall, collapsed to a count + a Settings → Exclusions view) landed the same two days, closing epic #478 in full — both motivating Stage-8 districts long since approved, now with the taxonomy and denominator that produced their bands corrected underneath them. Authority: `STAGE8_AGGREGATE_DESIGN.md` §2a (#253/#254), `METHODOLOGY.md` (the #498 carve-out + four/five-band tables), PRs #491–#496/#500; issues #253/#254/#498/#229/#91, all closed; #499 (the roster-template/school-slot spine #253's discussion motivated — deliberately *not* deferred, back-to-front build order agreed) is the next real workstream in this area.

### Ground truth as testing infrastructure, not documentation: a retrospective requirements/tests audit over 19 merged PRs, and a from-scratch pass on the doc tower against current code (2026-07-15)

With epic #478 fully closed, two questions the fast pace of the preceding week had deferred: *does `docs/REQUIREMENTS.yaml` — the formal spec ledger — actually reflect what got built, and does the documentation a new reader or auditor would land on first still describe the system that exists?* Both were answered by treating the running code as ground truth and working backward, not by trusting memory or prior doc language.

**The requirements/tests audit** ran 6 parallel review agents, each cross-referencing a cluster of the 19 merged PRs (#250 through #500) against `REQUIREMENTS.yaml` and `tests/`. It surfaced a consistent pattern: **most of gate@8's actual behavior — the whole closing-argument build, all four editorial primitives, the band-integrity family, the calibration hook — had never been given a formal REQ entry at all**, tracked only through GitHub issues and PR history. Nineteen new entries (REQ-125 through REQ-143) closed that gap. The audit's more interesting yield was the TEST gaps it found, several of which were real, not paperwork: `gate_calibration.py`'s module docstring still called gate@8 "deferred" while `gate8_decision_record()` sat live in the same file with zero test coverage; `current_school_year()` had no regression guard against being hand-bumped back to a literal — the *exact* bug class it was built to prevent — because the existing test only proved today's value matched, which would not fail until the *next* July-1 rollover, in production; and the #498 carve-out's corpus-measured blast radius (330 schools) was recorded only in commit messages, with nothing pinning it against the real, git-tracked 2024-25 CCD. Two new standing fitness functions were added rather than one-off gap-fills: `test_ci_workflows.py` (the #251 stacked-PR guardrail was enforced by CI running, not by an assertion pytest could catch regressing) and `test_suite_hygiene.py` (a standing guard against the exact self-testing-theater pattern #486 fixed by hand a day earlier — which immediately found a *third*, previously-unflagged instance, `tests/test_nces_import.py`, genuinely importing zero production code; grandfathered as a dated punch-list rather than blocking this pass on a separate cleanup).

**The doc-tower pass** worked stage-design-notes outward: renamed 12 `*_2026-06.md` documents (living documents wrongly wearing a dated-snapshot suffix — four genuinely dated research docs deliberately kept theirs) and swept every cross-reference, which surfaced its own lesson twice — the first sweep filtered by file extension (`.py/.md/.js/.json`) and missed `REQUIREMENTS.yaml` (a `.yaml`), `pyproject.toml`, `requirements.txt`, and a `.dependency-cruiser.cjs`; only a second, **extension-less repo-wide grep** caught the stragglers, which is the check that should have run first. `docs/ACQUISITION_PIPELINE.md` — the doc whose Mermaid diagram is a primary way this project is understood at a glance — had the widest drift: Stage 8 was still drawn as a single unlabeled node captioned "algorithm live inline inside gate@7, standalone stage NOT built," months out of date. Rebuilt as a full subgraph matching the density of Stages 1–7, and validated with an actual `mermaid-cli` render rather than eyeballing the syntax — which caught a real parse bug (a bare `(#93)` inside a bracket-node label breaks Mermaid's shape parser) that a manual review would very plausibly have shipped. `README.md` — flagged specifically as stale and GitHub-facing — still described the *retired* Crawlee+Ollama local-first design as the live acquisition method, directly contradicting the very doc it linked to for detail; replaced with the current console-driven flow. *Lesson: an audit whose job is "check the paperwork" is worth running as a code-grounded exercise, not a memory exercise — half its real findings (the phantom-band bug, the calibration docstring, the Mermaid parse error, the extension-filtered rename miss) were bugs or breakage, not staleness, and none of them would have surfaced from reading the docs against each other.* Authority: `docs/REQUIREMENTS.yaml` (REQ-125–REQ-143), the renamed `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md` + `PIPELINE_GOVERNANCE_AND_STATE.md`, `docs/ACQUISITION_PIPELINE.md` (Stage 8 section + Mermaid), `README.md`/`GETTING_STARTED.md`/`TERMINOLOGY.md`/`METHODOLOGY.md`.

### Epic #499 — the roster-template/school-slot spine: coverage becomes structural, and two adversarial review rounds earn their keep (2026-07-15)

The workstream #253's band-denominator discussion motivated, built in one session across six PRs
(#502–#507, REQ-144–REQ-150): each district's full in-scope NCES hierarchy is materialized as **slots**
that discovery/extraction results attribute onto — so a coverage gap is an *identified school*, not
count arithmetic. Key design calls that will outlive the code details: the spine is **live-compute-only**
(never persisted; the gate@8 receipt is the only frozen copy, and the receipt chain doubles as the
longitudinal roster-drift record — derive-from-receipts over stamp-stored, again); only **human
dispositions** (`slot_assignment`: assign/reject/confirm_extra) are precious; resolution precedence is
**human disposition > exact name > Stage-2-intent tie-break > ambiguous-waits** ("weight, never
override"); a band-level blanket statement attaches to the **band node**, votes once, and *projects*
onto unheard slots (a visible third state); the conflict ladder (sufficiency → hub-exception → vintage)
renders **advice only**; and the roster is **never injected into prompts** (REQ-054 — v4's
`campus_names` reads the page verbatim instead, and deterministic norm-key matching does the joining).
Follow-up pursuit went slot-grain: compose prefers *identified unfilled slots* over merely-untried
schools, and the "satisfied" signal (REQ-149, the #90 pull-in) is an additional suppressor beside the
covered-bands hard gate, never a replacement.

**The review lesson is the durable part.** Two max-effort multi-agent review rounds ran against the
merged epic; 22 findings confirmed and fixed, and the second round's biggest catches were bugs the
*first round's own fixes* introduced or missed — the pattern to remember: (1) **one projection, one
read path** — a parallel hand-rolled query for the "same" view (gate@1's spine endpoint vs gate@8's
closing argument) silently diverged on every human editorial action; the fix was exposing the full
`slot_projection` in the artifact and making every consumer reshape it; (2) **reads must be reads** —
consolidating onto `load_closing_argument` wired its roster-drift audit write into a GET and a dry-run
preview; purity is now caller-declared (`record_drift_event=False`); (3) **fix the whole class, not the
instance** — round 1 guarded three of `project_slots`' four fact branches against duplicate keys; round
2 found the fourth (confirm_extra denominator double-count) plus the endpoint-level root cause (a #474
hand-add duplicating a still-accepted council fact now 409s — corrections go through the override); (4)
**a Python-side signal the UI never renders is half a fix** — `assign_shadowed`/`displaced_by` existed
in the artifact while the console showed factually wrong copy, and the grep-style UI test passed
throughout because it pinned only the call-site literal, not the per-kind text. Also fixed at the
source, downgraded from a defensive catch: `_lea_file` raising `SystemExit` for an ordinary missing
CSV (it slipped past every best-effort `except Exception`). Authority: `docs/REQUIREMENTS.yaml`
REQ-144–150, `STAGE8_AGGREGATE_DESIGN.md`, `infrastructure/acquisition/common/slot_spine.py`'s module
docstring, issues #499/#502–#507.

### A measured refutation and a second doc-tower audit: two written numbers that didn't survive contact with the code (2026-07-16)

Two threads, one lesson. **First**, building the epic-#106 recency veto (#241) surfaced that its enabling
signal — a per-record `content_school_year` — *does not exist in the codebase*. Rather than build blind, a
throwaway URL-year extractor measured what the veto would actually do on the 473 labeled tier-A records, and
the result **refuted the comprehensive review's own projection** (`STAGE5_FILTER_DESIGN.md` §3a obs. 5, which
had it as "53 false sends removed for 6 target-vetoes → 24.5%→15.2%"): at the recency floor a stale veto
removes **1** false-send while vetoing **17** real targets and *raises* the false-send rate 24.1%→24.8%; at
the intended pre-2017-18 floor it removes **0** for 4 real-target hits. Root cause: staleness and
target-absence are near-**independent** — a stale handbook usually still *contains* a real schedule (which is
why the targets were labeled). The projection never reproduced because its 53/6 figures were **mined from
human notes** (records where Ian had already written "too dated") — that is judgment, not a signal a detector
can reproduce. The design turned on this: recency splits into a pre-2017-18 **validity floor** (a REQ-026
correctness guarantee floored on the CRDC federal input, HOLD-not-reject, ~0 money — #241) and **prefer-recent
dispatch ranking** (the half that saves money, zero recall cost by construction — #107, kept whole per
STAGE6 §3G's "complementary, not duplicates"). Consequence: **#515's "money lever" headline was wrong** —
stale contributes 0; the measured lever is #519 (tune existing confounders). Recorded as obs. 6, with obs. 5's
superseded bullets marked in place rather than deleted (a reader would otherwise re-derive them).

**Second**, a full code-grounded audit of the documentation tower (all 17 docs + the 23 auto-memories),
the successor to the 2026-07-15 pass. Its largest find: the **standalone Stage 8 / gate@8 — shipped #89 on
2026-07-14 — was documented as "unbuilt / doesn't exist yet" across three docs** (STAGE8's own title,
governance, OVERVIEW), and four of its five precious tables (`band_exclusion`/`human_added_fact`/
`slot_assignment`/`gate_mode`) had no design coverage at all. Also: CLAUDE.md carried two commands that
*fail when run* (`lint-imports` "3 kept" — it's 4, and pointed at a nonexistent `.importlinter`; a
`depcruise ... lib` with no `lib/`), GETTING_STARTED's entire scraper-service block was dead Crawlee-era
text, STAGE7 predated epic #119 and still showed the v1 four-field schema (missing the built `stated_minutes`
path 2), and REQUIREMENTS.yaml's status vocabulary had drifted (`in-progress` was exactly where two stale
statuses hid). All fixed against code, with four code-side defects that can't be fixed by editing docs filed
as issues (#523/#524 lying Stage-2 docstrings, #525 the `gate_mode.py:35` comment, #526 Stage 2 reading its
batch from the on-disk receipt while Stages 3/4 read the DB — a live exception to the "JSON is never the
transport" invariant). The memory store was curated 23→19 and given a standing rule: **stop writing
`type: project` status memories** — the audit found the rot correlated *exactly* with type (every stale
memory was a status memory; every clean one a working-style principle or a measured decision), because the
repo refreshes its own status and memory does not.

*Lessons: (a) **a written number is a claim, not a fact — verify it against the code that produced it before
building on it.** Three times in one session a durable figure failed on contact: the obs. 5 projection (mined
from notes, not measured), the #519 "0.13–0.18 precision" (the corpus had tripled — `news_feed` measured
0.90), and the "Stage 8 unbuilt" status. This is the same lesson the 2026-07-15 entry names, now with a
frequency that makes it structural, not incidental. (b) **the fix for status-rot is architectural, not
diligence** — status decays wherever a human has to hand-refresh it, so the durable move was deleting the
category (project-status memories) and pointing at the self-refreshing surface (CLAUDE.md + issues), not
resolving to update memory more often. (c) **subagents are subject to the same rule** — the memory-audit
agent claimed path 2 was missing (its grep guessed wrong field names), and a doc-draft invented a test class
that didn't exist; both were caught by verifying against code before committing, exactly the discipline the
audit was enforcing on the docs.* Authority: `STAGE5_FILTER_DESIGN.md` §3a obs. 6 + change log;
`STAGE6_DISPATCH_DESIGN.md` §3G; the seven `docs(...)` / `docs(tower)` / `docs(stageN)` commits of 2026-07-16;
`docs/REQUIREMENTS.yaml` (REQ-152, the status normalization); issues #523–#526; the curated
`memory/MEMORY.md`.

### Epic #106's first wave: school-year currency ships as a floor + a ranking, and the console trio makes labeling the learning surface (2026-07-16/17)

The measured re-scoping of recency (the 2026-07-16 entry above) **shipped**: `content_school_year` (a
deterministic URL/filename school-year signal, hardened against the phantom-year traps the measurement
surfaced), the **pre-2017-18 validity floor** as a HOLD (REQ-026 correctness floored on the CRDC 2017-18
federal input — deliberately never justified on spend), and **prefer-recent** as a dispatch-time *ranking*
(newest sibling sends, stale siblings hold — zero recall cost by construction). Then the **console trio**
(#516/#521/#522 → PRs #534/#535/#536) rebuilt the Stage-5 review surface around
`project-stage5-labeling-serves-learning`: FP/FN **error-review lanes** (disagreement as the primary
product of labeling), **relevance-density navigation** (a long doc read in relevance order — the same
signed detector signals that scored the record, projected onto its char axis as bookmarks + a heat-strip),
and **content-adaptive defaults** (the evidence classification drives what's open; redundancy collapses;
nothing is removed). *Lessons:* (a) **a display layer that mirrors scoring weights is a second SSOT
waiting to drift** — resolved by serving the mirror from the detectors module and pinning it with a
no-drift test, and by documenting loudly that the combiner's weights live elsewhere (a confusion #528's
build would otherwise walk into). (b) **max-effort adversarial review earns its keep most on the
safety-critical piece**: the #536 review proved the evidence guardrail was blind to the system's
*strongest* detector and rested on a tautology — both fixed before merge; and it taught a naming rule:
**name a guard for the mechanism it checks, not the incident that motivated it** (the "Huntington class"
label implied protection #521 had already delivered by different means). (c) **build-best-then-dial-back
works, but only against real data** — the density model's keyword weight and bookmark anchoring were both
wrong in ways synthetic tests couldn't show, and a 333k-char production handbook found both in minutes.
(d) **a scope addition made by issue-comment dies silently when its carrier issue closes** — #522's
folded-in facet-vocabulary decision shipped nowhere and was only caught by a post-merge audit; re-homed
immediately as #537 (the tracker convention exists precisely so work items can't be orphaned by a close).
Authority: `STAGE5_FILTER_DESIGN.md` §8 + change log; `STAGE6_DISPATCH_DESIGN.md` §3G;
`STAGE4_PROCESS_DESIGN.md` (the now-load-bearing `\f` contract); PRs #529/#533/#534/#535/#536; issues
#528 (build-session context comment) and #537.

### #537 closes the loop: one coarse facet, a measured positional detector, and a review round that made the fix better than the first cut (2026-07-17/18)

The orphaned facet-vocabulary decision (#537, re-homed the entry above) was decided, built, and then
carried through to a measured detector pass in one arc. **The decision:** ONE Axis-2 checkbox,
"Non-Regular-Day Schedule" (key `other_schedule`), covering every not-the-regular-day shape — early
dismissal, late start, remote, summer, event times — never split into per-cause checkboxes, per
`project-stage5-labeling-serves-learning`'s coarsest-learnable-distinction principle. Naming was
deliberately "non-regular," not "wrong": a Late Start schedule isn't incorrect, it's simply not the
target, and the phrasing matched the labeler's own note vernacular almost verbatim. The relabel queue
this unlocked (posted as a checklist on the issue, worked directly against the console) took the facet
from 6 to 61 tagged labels — un-freezing `lf_nonstandard_day`'s facet-precision denominator, frozen at
0.17 since #108 for lack of a live checkbox.

**The measured detector pass this facet existed for** found the prior anywhere-in-text trigger recalled
only 12/44 on the newly-accrued ground truth, false-claiming mostly on policy prose nowhere near a
schedule. The fix was positional (a term must title a schedule or sit beside the actual times), and
**build-best-then-dial-back** played out exactly as the project's convention predicts: the first
unguarded cut bought precision by wrongly demoting 57 real targets, because real bell pages routinely
list their day-variants beside the regular rows. A rule ladder measured on exactly those load-bearing
records — not guessed — found the guard (a page that also names its regular day downgrades the
positional evidence to a mention) that recovered most of them at negligible cost.

**Then a PR-level max-effort review (10 angles, 33 sub-agents) found 17 real defects in a diff that had
already passed its own measured pass** — the clearest evidence yet that a good before/after number is
necessary but not sufficient. The two worth internalizing: (a) **a design-doc claim ("wrong-day evidence
routes to review, never suppress") had quietly gone stale the moment a second rule (the no-times suppress
floor) started outranking it in practice** — the code was arguably right, the comment was wrong, and nothing
but an adversarial read would have caught the drift between them; both are now pinned by tests asserting
each side. (b) **the review's own "guard is too coarse" finding was itself measured before being adopted**
— a dominance-override threshold was picked by sweeping a small parameter space against the same
load-bearing records, not by intuition, and it shipped only because it was free (zero added cost at the
chosen threshold). The pattern generalizes: build best, measure, dial back against a review's findings,
then measure again — the discipline doesn't stop at the first green number.

Net across the two passes: the auto false-send rate that stood at 24.3% in the 2026-07-15 comprehensive
review is now 13.9%, with the recall floor (A+B) held exactly throughout both measured passes. Authority:
`STAGE5_FILTER_DESIGN.md` change log (2026-07-17/18 entries); issues #537/#538; PR #538.

---

### Epic #106 closes: a measured-null result, a veto refuted before it was built, and two adversarial review rounds each catching a bug the green test suite couldn't — six remaining issues ship in one arc (2026-07-18)

The epic's remaining slate cleared in a single day, worked in dependency order rather than issue-number
order, and produced two results worth keeping as method, not just outcome.

**A measured null is still a finding.** #226 (bounded feed-token URL negative) widened `FEED_URL_RE`
to catch `live_feeds/<id>` permalinks and camelCase-collapsed query tokens (`smartSiteFeed`), guarding
"feeder" (a real K-12 term) and "feedback" by token-boundary discipline. The measured pass found **zero
tier/decision movement** on the current corpus — every one of the 10 newly-caught records was already
held out of tier A by prior passes. The null was the point: #226 closes the live-feed URL-pollution
*channel* at the signal level for batches not yet captured, where the #528/#530/#537 content-based passes
can't reach. Shipping a zero-movement change is still shipping, when the change's value is forward
robustness rather than a metric.

**#515 — a veto refuted twice before anyone built it.** The eligibility-veto issue was already half-dead
(obs. 6, 2026-07-16: the stale half removed 1 false-send for 17 target-vetoes — net harmful). Re-measured
post-#537 against the same live tier-A population, the irregular half died too: every buildable veto rule,
from "any wrong-day vote" down to the tightest hand-tuned cut, traded more real targets than false-sends
it removed (the best cut: 11 FPs removed for 21 targets pushed to review — a losing trade even under
HOLD semantics). The oracle ceiling — the *perfect* detector's best case — was only 18 FPs, and 8 of
those turned out to be one shape: a single CMS vendor's schedule-variant siblings (see #540 below),
a dispatch problem wearing a scoring-eligibility costume. #515 closed **without a line of production
code**, which is the entire value of measuring before building: the issue had looked like "the money
lever" in the 2026-07-15 review; two measured passes established it wasn't, at a fraction of the cost
of building and then discovering the same thing in production.

**#532 — exploration overturned its own lead hypothesis.** The issue's proposed signal
(multi-confounder co-occurrence: N≥3 negative detectors firing on one record) never reproduced —
detector breadth never exceeded 2 on any tier-A record, and at breadth 2 it traded 7 false-sends for 19
real targets. The signal that *did* work was different in kind: `url_rootish` (a bare domain root or
`/o/<slug>`) crossed with `roster_school_names_hit ≥ 3` — a landing page naming many schools is a
different *shape* of page than a confounder-dense one. Shipped as `lf_district_homepage`, joined to the
existing feed/calendar undermine class rather than a new mechanism. Tier-A precision 0.8612→0.8701,
recall held exactly.

**The first adversarial review (10 angles, 7 confirmed findings) found what a green measured pass
structurally can't see.** All three PRs (#226/#515-adjacent/#532) passed their own before/after numbers
clean, then a 10-angle review of the diffs found: a case-sensitivity gap in the new regex (an
uppercase/lowercased variant of the PR's own motivating fixture didn't match — two independent angles
found it separately), an unescaped separator character matching any character instead of a space/hyphen,
a harness diagnostic silently undercounting because a new detector was missing from a polarity map, and
a detector docstring claiming "never a suppress" that the actual code contradicted (though tracing it
further showed this was a pre-existing pattern across the whole negative-detector family, not new —
the docstring was simply more absolute than its siblings). All seven fixed same day, zero decision
movement on the corpus — these were robustness and consistency gaps, not scoring regressions, exactly
the class of defect a metrics-only measured pass has no mechanism to catch.

**The completion sweep: five more issues, worked by cluster.** #75 (REQ-097 drift detector) had been
designed and research-cited weeks earlier and re-triaged twice without building — the sequencing
condition (V2-era tuning-ledger episodes) was finally met, so it shipped: a Bernoulli CUSUM + Wilson
two-gate over the fingerprinted scorecard series, segmented by config fingerprint so a tuning move's own
effect can't be mistaken for the world drifting. Advisory only, a console badge, never auto-retunes —
the same shape that caught the 2026-06-30 V1 precision collapse *by hand* is now automatic. #109 and #83
were worked together as one Stage-6 dispatch cluster: the harvest-slice basis now prefers a human-labeled
page range over the auto-detected one (verified live — a record whose auto detection was empty got its
first-ever slice from a human range), and REQ-116 finally got the acceptance criteria it had shipped
without in 2026-07-01 (the requirement's own note flagged this as deliberate — captured by hand against
a session limit, "not an oversight to be silently filled in") — a labeled district hub now narrows a
district's first dispatch to itself, with "covers all bands" made an explicit, safety-net-backed
presumption rather than a verified fact (a wrong presumption costs one cheap 7→6 retry; a right one
saves every redundant per-school send). #517 (`schedule_link_only`) shipped as a pure recall affordance —
a page that *names* a bell schedule it doesn't contain routes to a retry receipt instead of a dead-end
absent; measured 78/78 census-labeled non-targets, zero collateral by construction. #540 closed the
loop #515 had opened: the residual 8 false-sends in #515's oracle ceiling were one CMS vendor's
schedule-variant siblings (Edlio's `/apps/bell_schedules/` app family), so Edlio was profiled and
approved into the CMS fingerprint vocabulary (the first vendor under a newly-written standing
requirement, REQ-153: *profile every CMS encountered*, not just the ones a given issue happens to name),
and a sibling-aware dispatch pass sends the best page per app family instead of one call per variant.

**The second adversarial review found a bug that would have silently defeated the guarantee #83 had
just built — and widened its own initial finding on cross-examination.** The 10-angle review of the
five completion-sweep PRs converged, across four independent angles, on the same defect: the new
sibling-variant dispatch pass ranked purely on URL shape and ran *before* the hub-priority pass in the
same function, so a human-labeled district hub sharing a CMS-app URL family with an unlabeled sibling
could be silently held before hub-priority ever got to evaluate it — the exact case #83 shipped same-day
to solve. Reproduced directly, three ways, with a concrete two-record input. Fixing it exposed a second,
worse version of the same gap under adversarial follow-up: the ranking wasn't just hub-blind, it was
*any-label*-blind (a verified, human-confirmed target could lose to a denser unlabeled duplicate) and
*school*-blind (the family key grouped by host only, so two genuinely different schools sharing one
district-level host could collapse into one family and drop a school's only send). Both reproduced
directly; both fixed by making the ranking label-aware (a human judgment always outranks the URL-shape
heuristic) and scoping the family key to `(host, school-set)`. The fix was pinned end-to-end through the
full dispatch composition, not just the isolated hold function — the isolation-level tests that already
existed for both passes were green throughout and would never have caught a composition bug between
them. **This is the second time in one day an adversarial review caught a same-day feature silently
defeating a same-day guarantee**, both times in code a green measured pass or a green test suite had
already blessed. The lesson generalizes past this epic: composition bugs between features that land
close together are a distinct failure class from both scoring regressions (caught by the measured pass)
and unit-level logic errors (caught by ordinary tests) — nothing but reading the *composed* code paths
adversarially catches them, and doing it same-day, before the interaction has a chance to run on real
traffic, is cheap compared to finding it in production.

**Net across the epic:** auto false-send rate 24.3%→**13.0%** (from the 2026-07-15 baseline), A+B recall
held at 0.9928 through every single change — roughly two dozen commits, two review rounds, one closed
issue with zero shipped code. Two housekeeping items closed alongside: **#110** (cross-config cascade)
was assessed and correctly re-homed to epic #80 (Council Lab) rather than built — only two council
configs exist and they're different *modalities*, not strength tiers, so there is nothing to escalate
to yet, and per standing policy model composition is never guessed. **#444** (a mis-filed production
correctness bug in an NCES/SEA ingestion script, sitting in the test-quality epic #481 by way of which
test file happened to exercise it) was re-homed to epic #480 by subject matter, closing #481 as a
side effect — a reminder that an epic closes when its *scope* is exhausted, not when its issue count
hits zero; the one remaining item there was never really that epic's item to begin with.

Authority: `STAGE5_FILTER_DESIGN.md` and `STAGE6_DISPATCH_DESIGN.md` change logs (2026-07-18 entries);
`docs/REQUIREMENTS.yaml` REQ-097/REQ-116/REQ-153; issues #226/#515/#532/#75/#109/#83/#517/#540/#110/#444;
PRs #539/#541/#542 (first review round) and #543–#548 (completion sweep + second review round).

### Epic #111 (Stages 1-4 hardening) ships both its planned phases in two days: a five-module correctness sweep, then the DB-batch-read migration it was sequenced ahead of — each with its own adversarial review round finding real bugs the green suites couldn't (2026-07-18/19)

With epic #106 closed, the pre-#106 sequencing plan called for #111 next. It split into two phases,
worked in the same disciplined shape epic #106 had just validated: ship, review at max effort, fix
everything the review found, re-report with outcomes.

**Phase 0 (crossfam triage) → Phase 1 (five parallel correctness sweeps).** #111's own issue list was
mostly untriaged crossfam-review findings across stage1-4 plus a handful of named feature issues;
triaging it by dependency cluster (the way #106's slate was worked) surfaced five independent module
sweeps that could ship as five parallel branches rather than one sprawling PR: Stage 2 (#265/#341/#452/
#523/#524, PR #549), Stage 1 (#264/#338/#339, PR #550), the Node scraper (#375/#416, PR #551), Stage 3/4
(#267/#347/#348/#351/#454, PR #552), and `common/` (#326/#328/#330, PR #553). The load-bearing fixes: a
merge-retry crash gap in Stage 2 where a crashed follow-up redo could silently drop the prior round's
candidates (`_prior_doc` now reads each manifest independently, live-or-newest-aside-or-empty); a
batch-scoped progress bug in Stage 1 (#339) where a freshly-created follow-up batch showed
`discovered/captured/processed = total` before its own discovery ever ran, because the progress query
joined the *global* `current_state` view instead of scoping to `(batch_id, district_id)`; a
cross-language CMS-host-matching false positive (`myfinalsite.net` matching the vendor `finalsite.net`)
closed with a shared golden-vector fixture pinning the JS and Python implementations to identical
behavior, not just a code comment claiming they agree; and malformed-manifest-entry tolerance closed on
*both* sides of Stage 3/4's read/write boundary, not just the side the original bug report happened to
hit.

**A same-day max-effort review of all five PRs (10 angles, 15 findings) caught the subtlest bug of the
batch: two features quietly defeating each other, invisible to five green isolation-level test suites.**
The review's most consequential catch wasn't in any single PR's diff — it was in how #553's fix to
`district_status.save()` had been shaped. The original #330 fix conflated two separate things: clearing
the event buffer at commit time (the real fix, preventing a retried `save()` from double-inserting) and
swallowing the `export_status()` exception (an unrelated side effect that silently broke
`server.py`'s `stage5_bookkeeping_failed` discriminator, which depends on that exception propagating).
The review separated them — keep the buffer-clear, revert the swallow — restoring the safety property
*and* the failure signal in one move, something neither Stage 4's tests nor `common/`'s own tests could
have caught in isolation, since the interaction only exists at the seam between them. Thirteen of fifteen
findings were code-fixed with new tests; one (a deliberately redundant `batch_store` count query) was
verified as already-correct and only needed a comment explaining why not to "simplify" it away; one
follow-up (#554, consolidating the remaining hand-rolled atomic-write copies onto the shared
`paths.atomic_write_json` helper #549 introduced) was filed rather than fixed in-flight, since the two
remaining copies live in files owned by different PRs in the same batch and consolidating them there
would have created cross-PR merge conflicts.

**Phase 2 (#526): Stage 2's batch read moves onto the governance DB, closing the last exception to "the
DB is the working store."** This had been a known, tracked architectural inconsistency since the
2026-07-16 doc-tower audit: every other stage's console/autoflow resolved its batch from the DB working
store, but Stage 2 alone still read the on-disk receipt (`load_batch_any`) — correct *today* only because
every DB mutation path happened to also regenerate the receipt file, an unenforced discipline rather than
a structural guarantee. The fix (`server._batch_from_db` rebased onto a new `batch_store.to_working_doc`)
mattered beyond symmetry: the resolver's prior basis (`to_view`, shared with Stage 3/4) filtered
gate@1-*rejected districts* but not gate@1-rejected *schools within an included district* — harmless for
Stage 3/4, which never read the school list, but a roster-poisoning trap for Stage 2, which builds its
search roster from exactly that field. A govdb regression test now pins the included-only shape, and a
new `arch-manifest.json` fitness function (`cli_only_loaders`) fails the suite if `load_batch_any` is ever
referenced inside the console again — the invariant that used to depend on nobody forgetting is now
enforced.

**This PR's own review round repeated the same lesson at smaller scale: the "obvious" fix for one of its
own findings would have been wrong.** A max-effort review of #526 found `_batch_from_db` fetching the
`Batch` row twice per call (confirmed via SQL-echo against live Postgres — a real, not theoretical, cost
on a path polled every ~3.5 seconds by three console views). The naive fix — return `status` from the
existing receipt-doc function — would have leaked batch status into the on-disk receipt file, contradicting
`common/batch_guard.py`'s documented invariant that a CLI loader must re-check status against the DB and
never trust the file. The actual fix split the concerns: `to_working_doc` (status included, DB-resolve
only) alongside `to_receipt_doc` (deliberately status-free, feeds only the receipt). Three other candidate
findings from the same review were refuted with concrete evidence rather than fixed reflexively — `run_batch`
dropping its internal existence check turned out to already match Stage 3/4's established
caller-validates convention; a dropped `included` flag on district dicts was never read by any consumer,
before or after; and a substring-scan fitness function that looked less rigorous than the AST-based
mechanism one section above it in the same file turned out to be the *more* conservative choice for a
whole-directory negative check, not a rigor gap.

**Net across both phases:** five independent module sweeps plus a cross-stage architecture migration
shipped in two days, each carrying its own adversarial review round, each round finding at least one bug
a green, well-tested change would not have surfaced on its own — the same pattern epic #106 established
and this epic's second PR (#555) repeated on itself. Both max-effort reviews' full finding lists, verdicts,
and fix outcomes are preserved via `ReportFindings` calls in-session; the doc tower (`ACQUISITION_PIPELINE.md`,
`PIPELINE_GOVERNANCE_AND_STATE.md`, all four `STAGE*_DESIGN.md` present-state notes) was swept against
current code the same day these PRs merged, closing every stale claim the sweep's own audit agents found —
including, in STAGE1_QUEUE_DESIGN.md's case, a claim that had gone stale within the same session that wrote
it, when the #555 review's `to_working_doc` split superseded the `to_receipt_doc`-only description the
doc had captured hours earlier. Authority: `STAGE1-4_*_DESIGN.md` change logs (2026-07-18/19 entries);
`PIPELINE_GOVERNANCE_AND_STATE.md` §1/§10/§12a; issues #264/#265/#267/#326/#328/#330/#338/#339/#341/#347/
#348/#351/#375/#416/#452/#454/#523/#524/#526/#554; PRs #549-#553, #555.

---

### A retrospective max-effort review across two epics' already-merged PRs finds the one bug none of their green suites could have caught — a feature silently defeating its own purpose the moment it touched the DB (2026-07-19)

With epic #111 code-complete except its two Ian-decision gates, the natural checkpoint before resuming
#164 PR 3b was to turn a local max-effort review (`/code-review max`, not the cloud ultrareview) on the
full merged span rather than any single PR: epic #111 Phase 4's partial-retry and crash-recovery work
(#562/#563), its two small hardening PRs (#564/#565), the facility-flag feature (#566), and all three
landed #164 geo-discovery PRs (#568/#569/#570) — eight PRs, 35 files, ~3,200 diff lines, all already on
`main`. Unlike every prior max-effort review in this project's history, this one ran entirely against
code that had already shipped and been checkpointed as done; the point was to ask the harder question —
not "does this diff look right" but "did it actually work once it hit the real DB."

**Scale matched the span:** 10 parallel finder angles (5 correctness, 3 cleanup, altitude, conventions)
surfaced 37 raw candidates; a dedup pass collapsed clusters where independent angles converged on the
same bug through different reasoning paths (three separate angles — reuse, altitude, simplification —
independently flagged the same `_scoping_domain` closure duplication; two — removed-behavior and
language-pitfall — independently found the same journal-filename sort bug by different routes); 15
survivors went through one-vote adversarial verification each, and a final gap-sweep pass added one more
the first round missed. Twelve findings survived to the report: eleven CONFIRMED, one PLAUSIBLE-but-low-
severity (a narrow, self-healing `queue_create` snapshot race, inert until #164 PR 3b's auto-advance
wiring exists).

**The standout finding — and the reason this kind of review earns its keep — never would have surfaced
from reading the diff.** `batch_store.create_batch()`'s `BatchDistrict` field list simply didn't include
the two new per-district fields #164 PR 1 added (`geo`, `domain_source`); every projection built off it
(`to_working_doc`, `to_receipt_doc`, `to_view`) silently dropped them the instant a geo-scoped or
dual-source-admitted batch round-tripped through Postgres. The existing tests never caught it because
they exercised `build_batch`'s in-memory `batch_doc` directly — nothing in the suite piped a geo district
through `create_batch` and read it back. The verifying agent didn't stop at reading code: it wrote a
disposable script against the live governance DB, round-tripped a synthetic geo district, and watched
`geo`/`domain_source` come back `None`. Downstream, that meant any geo-scoped discovery run through the
console (`_batch_from_db` → `to_working_doc`, the only production resolve path) would have rendered
every SERP query with blank city/zip tokens — the exact unscoped, cross-district-contamination query
class #164 exists to prevent — silently, with no error, the very first time the feature was used for
real. The live Millard run Ian had queued as the next gate@1 action would have hit this on contact.

**Two more genuine, independently-converged bugs, both born from the same class of failure — a fix that
handles the common case but not the one the codebase had just built infrastructure to survive.** The
#563 per-task journal's same-second rename-aside collision guard (added specifically so two crash-asides
in one second wouldn't clobber each other) named its files with a `-N` suffix that ASCII-sorts *before*
the unsuffixed file it followed — inverting "oldest first, latest wins" replay for the exact scenario the
guard was written to handle, so a stale failure record could silently overwrite a newer successful retry
during crash reconstruction. And `derive_domain`'s majority-host tiebreak picked by hostname string over
school coverage, so a tied-on-volume 1-school host could beat a 4-school host, fail the min-schools
check, and wrongly reject a Millard-class district that should have derived cleanly — reproduced live by
the sweep agent with the exact tally that triggers it.

**One finding stood out for what it revealed about deferred-work tracking, not just the bug itself.**
`compose_followup_batch` (the automatic 7→2/7→3/7→1 back-edge sweep, the *only* production caller of
`build_followup_batch`) never threaded confirmed discovered domains through, so the #164 PR 3a dual-source
guard — built explicitly, per its own code comment, as "how a Millard-class district returns to normal
domain-scoped follow-ups" — had no live path back into normal follow-ups at all. This wasn't on PR 3b's
own tracked deferral list (the 7→1 scope split, the 5→1 zero-yield composer, the auto-advance trigger,
the `geo_interleaved` draw) — a plain miss between what the guard was built to do and what its one caller
actually exercised, the kind of gap that survives specifically *because* it's adjacent to, but not
identical to, work everyone already knows is unfinished.

**All twelve were fixed the same day, each pinned by a new regression test** (ten total: a govdb
round-trip test for the persistence bug, a same-second collision test for the journal sort, a live-
reproduced tiebreak test, a govdb threading test for the follow-up composer, a cross-language
fingerprint-parity test spanning the new Python/JS plan-check pair, and five more). The `BatchDistrict`
persistence fix needed two new nullable columns (`domain_source`, `geo_json`), added via the existing
additive-migration convention. Verified clean afterward: `lint-imports` 4/0, 1744 DB-free + 264 govdb +
13 Node tests, all passing (govdb's true pre-change baseline was 262, not the 254 CLAUDE.md had recorded
— corrected in passing). Landed as a single commit (`2153a91`) directly on `main`, per Ian's call that a
branch/PR round-trip added no value for a review-response fix already carrying its own paper trail via
this session's `ReportFindings` output.

**A same-session housekeeping pass then found the local and remote branch lists were almost entirely
stale.** All 12 non-`main` local branches for prior, unrelated work (#120/#121/#246/#254/#537/#106/#119
and four #499 sub-PRs) turned out to already be on `main` — landed via GitHub squash-merge, which stamps
a *new* commit SHA and leaves the original branch pointer both un-fast-forwardable and invisible to
`git branch --merged` (ancestry-based, blind to squash). Verified by exact git-tree-hash match, not just
commit-message similarity, before deleting. The 12 remote branches for this review's own source PRs
(#556-570) turned out to already be gone — GitHub's delete-branch-on-merge setting had removed them days
earlier; the local `origin/*` refs were just stale until `git fetch --prune`. Worth remembering for this
repo specifically: a local branch surviving `--no-merged` is not evidence the work is unlanded, and
`origin/*` branch lists need a prune before they're trusted.

Authority: this session's `ReportFindings` output (12 findings, verdicts, and per-finding fix mapping);
PRs #562/#563/#564/#565/#566/#568/#569/#570; commit `2153a91`.

### 2026-07-20 — Epic #111 closed on a live fire: Millard NE proved the geo-repair design and exposed two real gaps the same day

The epic's last mile (#164 PR 3b → #118 → #518) closed in one continuous arc driven by the FIRST live
run of the geo machinery, and the run itself became the epic's best QA. The sequence, decision-level:

**The designed Millard action wasn't executable — twice.** (1) The backend gating existed but no
operator control did (curl-only, against the ramp-up model) → #572/REQ-158 built the console surface
(policy card, scope-aware create with the AGREED DESIGN's path-4 targeting, the 5→1 button, the
proposal card). (2) Even then, Millard is *already-attempted*, so no first-run draw can ever contain
it — the real path was the just-built 5→1 zero-yield escalation. Lesson reinforced: a capability
without its control surface, or a plan that ignores admission rules, only surfaces on contact with
the live gate.

**The geo design worked on first contact**: unscoped wave-1 → derive-and-re-gate folded the
per-school subdomain family (bms./rms./sandoz.…) into mpsomaha.org at 78.3%/21 schools; Ian
confirmed via the new card (decisions now accrue as an append-only training corpus — confirm AND
reject-with-reason, the future auto-confirmation's classes); Millard returned to domain-scoped flow.

**The run exposed that Critical Rule 3 was classification-only** — no code ever assigned
`security_block`, so the capture recorded 81/83 Cloudflare interstitials as `ok` while pressuring
the WAF. #578/REQ-159 enforced it in depth (per-response `detectChallenge`, the 3-consecutive
district breaker, the pre-capture probe — one request of IP exposure), the interstitials were
remediated manifest-first (restore point `3173740_20260720T145158Z`), and security-blocked
districts became ineligible for geo escalation (the WAF said no; never automatic re-pressure).
An integrity audit prompted by Ian confirmed the audit trail clean and drove the remediation-receipt
exception to be UNIFIED across the Stage-2/3/4 reconcile guards (a receipted decontamination is the
one sanctioned registry-ahead-of-disk state).

**Then the epic's two closers**: #118/REQ-160 (attribution with the #164 axes; first card's
headline — emergent one-hop capture out-yields every SERP provider at 38.1% labeled-target rate)
and #518/REQ-154's consumer (the fidelity-triage queue on Stage 3 + gate@5), closing the loop the
survey opened: flagged captures are now reviewable decisions, not silent `target_absent`s.

Authority: PRs #571/#573–#576/#579/#580/#581; issues #164/#572/#578/#118/#518/#111 (close
comments); REQ-157…160; the `3173740_20260720T145158Z` remediation manifest.

### 2026-07-20 — Doc-tower + requirements-ledger refresh: closing the epic-#111 documentation debt before the #479/#480 → #92 pivot

Epic #111's 9 PRs landed docs inconsistently — some updated the tower, sibling PRs from the same
48-hour window did not — so before a context clear ahead of Stage 9 prep, the whole tower (all 5
Stage 1–5 design notes, `PIPELINE_GOVERNANCE_AND_STATE.md`, `ACQUISITION_PIPELINE.md` incl. its
Mermaid diagram, `METHODOLOGY.md`, `TERMINOLOGY.md`, `GETTING_STARTED.md`) was brought back to
current-code-as-ground-truth. Scoping principle used throughout: ACQUISITION_PIPELINE.md is the
skeleton, the stage notes are the muscles, PIPELINE_GOVERNANCE_AND_STATE.md is the nervous
system — cross-stage mechanisms (the escalation ladder's shared threshold, `remediation_receipt`,
the discovery-scope policy) get ONE canonical home there, with stage docs cross-referencing
instead of re-deriving.

Two things found and fixed along the way worth remembering: **METHODOLOGY.md contradicted
itself** — one section still described the retired (2026-06-13) Crawlee+Ollama pipeline as
current, while a later section in the same doc correctly described today's search-led/tiered
pipeline; reconciled to point at ACQUISITION_PIPELINE.md instead of re-describing mechanics that
drift. **The Millard interstitial count (31/83 vs. 81/83) had silently forked** — CLAUDE.md and
PROJECT_HISTORY.md already carried the corrected 81/83 figure from an earlier mid-session
correction, but ACQUISITION_PIPELINE.md, STAGE3_CAPTURE_DESIGN.md, and REQUIREMENTS.yaml (both a
test docstring and an acceptance criterion) still carried the original wrong estimate — a reminder
that a correction made once in conversation needs to be swept across every doc it landed in, not
just the ones touched at the time.

**A parallel requirements-ledger audit** (prompted mid-session) found REQUIREMENTS.yaml itself was
accurate but stale in the same inconsistent way: REQ-157/158/159/160's acceptance criteria and
tests held up, but their `notes` didn't reflect a same-day, previously-uncommitted 12-finding
review-fix pass (the shared `geo_ladder_exhausted` threshold, `remediation_receipt`'s new 30-day
expiry, the `/api/discovery-policy` registry bug, the `/api/attribution` schema-bootstrap gap, and
others) — now folded in. More consequentially, **8 of those 12 fixes had shipped with zero test
coverage**; wrote the 7 missing regression tests (the 8th, a pure query-count optimization, is
already covered transitively). Also found one genuinely undocumented capability three days old
(#222's facility-named-school gate@1 review flag) and gave it REQ-161. The 12-finding fix session
itself — verified passing but never committed — landed as its own `fix(#164/#111)` commit as part
of closing this out.

Authority: this doc-tower refresh commit + the `fix(#164/#111): address 12 findings...` commit
immediately preceding it; REQ-153/154/157/158/159/160/161.

### 2026-07-20 — Epics #479/#480 executed: the LCT-core hygiene sweeps, refamiliarizing with the calculation side before Stage 9

The two crossfam-review epics (120 unverified findings across the DB layer + legacy NCES/SEA
scripts) were executed in one day as ten Stage-9-relevance-ordered work packages (PRs #583–#596),
doubling as the deliberate refamiliarization with LCT-calculation code untouched for months.
Every finding was triaged-in-code: 90 fixed, 21 closed superseded-by-retirement (the legacy
enrichment layer — batch_composer/school_discovery/enrichment_tracking/interactive_enrichment —
and the Homebrew-era docker migration tools, both archived with evidence manifests after
grimp/vulture verification), 8 closed no-change with rationale, 1 (#407) left open awaiting a
schema-migration decision (scope_all undercounts — `all_other_support_staff` never existed on
StaffCountsEffective).

Durable lessons: (1) **run the repaired reports against the live DB** — that step, not the code
review, surfaced #594 (the CA Phase-2 tables are EMPTY; the documented CA-actual SPED precedence
has been silently inert since the 2026-07 rebuild) and its latent sibling #589 (rebuild never
re-runs apply_ctc_classification); the rebuild orchestrator preserves only what its phases
explicitly re-import. (2) The **zero-pad/fixed-width id class** recurred across 9 files and two
epics; the converter registry (`excel_digits` + per-state zfill, verified against the live
crosswalk's stored widths) is now the single home. (3) The loop-closing gap for #92 is filed as
#582: the LCT reader never inspects `minutes_basis`/`method`, so Stage-9 statutory_fallback rows
would masquerade as measured bell data. (4) The arch-manifest fitness tests caught an archived
file's stale external-program declaration exactly as #124 designed.

Authority: PRs #583–#596; issues #479/#480 (disposition comments), #582, #586, #589, #594, #595;
epic checklists.

---

### 2026-07-20/21 — SEA data-collection campaign: catalog → probe → acquire → inspect, and an objective "was it worth it" answer

Before Stage 9 (#92), Ian directed a full refresh-plus-new-states pass over every state education
agency's data availability — the last assessment was six months stale. Four phases in ~36 hours:
**Phase A** (PR #601) designed a structured YAML catalog (`state_data_catalog.yaml`) as the
source of truth, replacing the old hand-maintained markdown assessment, with a fitness-test suite
(`tests/test_state_catalog.py`) keeping it honest. **Phase B** (PR #602) probed all 50
non-current entities via a fleet of parallel agents (Bright Data/Serper SERP + Playwright),
correcting a real misconception along the way: NCES CCD's own `ST_LEAID` column already *is* a
state-ID↔NCES crosswalk for every state, so the campaign's early "most states don't publish a
crosswalk" framing was a non-problem, not a gap (`meta.crosswalk_correction`). **Phase C** (PR
#603) regenerated the assessment doc and acquisition plan, added a CSV>JSON>XML>XLSX>XLS>SAS>PDF
format-preference policy (Ian's call, after a "download the single best format, not all of them"
discussion), and ran the automated Phase D acquisition (96 files, 32 states) — a pre-flight
`requests.head()` validation pass over all 102 candidate URLs caught 7 catalog bugs (wrong ArcGIS
params, several states' files recorded as `direct-download` when they were actually HTML landing
pages) before any real downloads happened. Ian did the remaining ~30 states' Tier-2/3 manual
downloads himself in parallel, dropping files straight into `data/raw/state/{state}/` with no
recorded provenance — by the time Phase D finished, the tree held 300 files across 52 of 56
jurisdictions (only Maine/Montana/North Carolina/Vermont remained fully unacquired).

The campaign's last act — and the one that actually answers "was this worth it" — was a
file-by-file inspection pass (13 parallel agents, every file opened and read, not just
filename-classified) writing/revising a `MANIFEST.md` per state and rolling the aggregate into a
new "Campaign findings" section of `STATE_DATA_AVAILABILITY_ASSESSMENT.md` (added as a literal
constant inside `gen_state_assessment.py` so the doc's staleness fitness test still holds — this
section can't be derived from the catalog's structured fields, since it's synthesis over file
*content*, not catalog metadata). The finding: only 20 of 52 jurisdictions have a genuinely clean,
district-level, raw-count SPED file as acquired (the one input where SEA data has a real
structural edge over NCES, since the federal SPED baseline is 2017-18 — eight years stale);
enrollment/staffing recency gains are mostly 0–1 year, a precision nudge the project's own
REQ-026 blend window already absorbs; and integration would be ~45 bespoke small ETL jobs (name-
only join keys, multi-sheet cover pages, mislabeled encodings, silent Socrata pagination
truncation, differing FERPA-suppression conventions), not one templated importer, with most files
carrying no recorded source URL. **Verdict: a blanket 45-state integration push doesn't clear the
bar against this project's own commandments (auditability, minimize-bad-data-at-scale, tight cash
spend, one human's time) — Ian's stated skepticism was borne out by the data, not just a hunch.**
A narrow follow-up scoped to the ~9 net-new states with a clean enrollment+staffing+SPED trio (CA,
OH, TX, NJ, NE, MO, KY, SD, KS) remains a bounded, opt-in backlog item, not a blocker on anything.

One genuine surprise survived the skeptical read: Minnesota publishes a file
(`Average Length of Instructional Days by Sch and Grade K-12 FY25.xlsx`) that reports actual
gross bell-to-bell instructional minutes per school×grade — found by Ian manually browsing MDE,
not by the automated discovery cascade, and independently arithmetic-verified twice. This is a
narrow exception to `INSTRUCTIONAL_TIME_HARVEST.md`'s "SEA central-data harvest is a dead end
for daily minutes" conclusion, not a reversal of it — filed as its own exploratory issue (#604)
rather than folded into the enrollment/staffing/SPED assessment, since it's a different kind of
input with its own precedence questions.

Durable lesson: a systematic inspection pass earns its keep even after a campaign already "looks"
complete by file count — the Phase D pre-flight catches (landing pages recorded as downloads) and
this closing pass's catches (mislabeled provenance, false negatives from earlier phases reversed,
a truncation bug in the acquisition script itself) were each invisible from the catalog's own
structured fields; only opening the files found them.

Authority: PRs #601, #602, #603; issue #604; `docs/state-integrations/state_data_catalog.yaml`,
`STATE_DATA_AVAILABILITY_ASSESSMENT.md`, `data/raw/state/*/MANIFEST.md` (gitignored, local-only).

### 2026-07-22 — Resuming the Stage 9 campaign one district at a time surfaced two real production bugs (#608, #610, #611) — going slow found what going fast would have hidden

Swinging back to #92 after the SEA campaign, the plan was to incorporate the 22 gate@8-approved
districts individually — dry-run, write, review the before/after preview, repeat — rather than batch
through all 22 and recompute once. That deliberate pace paid off immediately: it caught a live console
crash mid-review and a silent 17.5%-of-corpus data gap, either of which a blind full-batch run would
likely have masked or made much harder to isolate.

**Stage 4 segfault (#608, PR #609).** While several follow-up batches' re-discovery + re-extraction ran
concurrently, the console crashed with a bare `zsh: segmentation fault` — no Python traceback, since a
SIGSEGV bypasses exception handling entirely. Root cause: camelot's table extraction is backed by native
code (pypdfium2/PDFium + OpenCV) unsafe for concurrent multi-threaded use in one process, and
`_acquire_batch_run` (issue #47) only serializes runs of the *same* batch — different batches' Stage-4
autoflow threads could call into the same native libraries at once. Fix: Stage 4 now runs in an isolated
OS subprocess per batch (`server._run_stage4_subprocess`), so a crash kills only that batch's job, with
stderr captured to a durable log for exactly the forensics this incident's own investigation lacked. A
subsequent max-effort review of the fix itself found and closed 5 more issues in the same pass (exit-code
interpretation, log naming, temp-file cleanup, malformed-line tolerance, signal-kill test coverage) — see
REQ-163.

**Stage 9 write validated live against 3 real districts** (Brownsville Ascend NY, Lincoln MA, Coffee
County AL) — all incorporated cleanly, and each taught something the dry-run survey alone hadn't shown:
the overlap-flag mechanism (§2g/§4 of `STAGE9_INCORPORATE_DESIGN.md`) fires on *every* grade for a small
K-8-in-one-building charter (both elementary and middle bands' rosters span the same K-8 range); Lincoln
has *never* had a computable `teachers_secondary` LCT at all (zero reported secondary teachers — a K-8
town district with no local high school), which is what actually surfaced the next bug.

**`per_grade_lct_sample.py`'s "legacy" column was contaminated by the very write it was supposed to
review against (#610).** The sign-off script re-derived "legacy" live via `get_instructional_minutes()`,
whose pre-existing REQ-024 fallback (high → middle → elementary, for K-8 districts) picks up *any*
measured `bell_schedules` row — including one Stage 9 had just written for the district being sampled.
So the instant a district was incorporated, "legacy" silently stopped meaning "what's live in
`lct_calculations` right now" and started meaning "what the old formula computes today, contaminated by
today's own write." Caught reviewing Brownsville: the contaminated comparison reported Δ=0, while the
real stored production value was 330min/9.35 LCT against a true 455min/12.88 per-grade result — a real
+3.53 LCT change the bug hid entirely. Fixed by reading the stored `lct_calculations` row directly
(bulk-fetched, ordered by `year DESC` then `calculated_at DESC` — not calculated_at alone, since a
TARGET_YEAR recompute can leave an older year with a later timestamp than the newest one) and flagging
`denom_refreshed` when the stored row's staff/enrollment vintage differs from today's picks, so a
reviewer can't mistake a data refresh for the per-grade methodology effect. `main()` also gained a
None-guard: Lincoln's never-computed case (legacy=None, a real per-grade value present) had been an
untested `int - None` crash waiting to happen on exactly the scenario the tool exists for. See REQ-162.

**The 2024-25 NCES CCD ingest had silently dropped ~3,125 districts — every FIPS<10 state (#611,
PR #612).** Investigating why Coffee County's temporal blend window rejected its own freshly-written
council minutes turned up `enrollment_by_grade`/`staff_counts_effective` rows stuck at 2023-24 despite
2024-25 data being on disk. Root cause: `import_staff_and_enrollment.py` normalized LEAIDs with
`str(int(x))`, which strips the leading zero (`'0100810' -> '100810'`) — fine under the *pre-migration-015*
6-char districts table, silently wrong ever since migration 015 (2026-01-24) LPAD-standardized everything
to 7 digits. Every import after 015, including 2024-25, produced ids that failed the
`.isin(existing_districts)` match and were dropped with no error: 3,053 of 3,125 missing districts
(97.7%) had leading-zero ids, CA alone 1,985. The existing `test_normalizes_leaid_format` (REQ-002) never
caught it — it tested a test-local reimplementation, not the real importer, so REQ-002 had claimed
'tested' status against its own "captures full NCES IDs with leading zeros" acceptance criterion the
whole time the production code silently violated it. Fixed with a shared `_canonical_leaid()` (zfill(7),
never `str(int())`) plus a new `_assert_match_coverage()` guardrail that aborts an import outright if
post-normalization coverage falls below 95% — no more silent partial imports. Re-ingested 2024-25
(enrollment 14,717→17,751, staff 14,720→17,754, zero duplicates, 2023-24 untouched); Coffee County's data
came back current and its council minutes cleared the temporal window on the very next preview run. See
REQ-002.

**Lesson, stated plainly by Ian mid-session: "I'm glad we found this now!"** Both bugs were real, both
were silent, and both were found specifically *because* the campaign moved one real district at a time
with a human reading every result rather than trusting a batch run's summary line — exactly the
high-supervision-first posture `PIPELINE_GOVERNANCE_AND_STATE.md` §11b describes, applied one level up
from the acquisition pipeline to the LCT-core data it ultimately feeds.

**Also this session:** issue #577 (console left-pane progress chips) reparented from epic #92 to epic
#96 (Console UI build) via GitHub's native sub-issue API — it's a console-chip bug, not Stage-9 scope,
and #96 already holds the console-UI backlog. A full doc-sync pass followed, correcting
`ACQUISITION_PIPELINE.md` (per-grade projection was still described as "the scoped follow-up" though
built the same day) and `PIPELINE_GOVERNANCE_AND_STATE.md` (two spots still described Stage 4 as
"in-process" post-#608) against current code.

Authority: PRs #609, #610, #612; issues #608, #611; `STAGE4_PROCESS_DESIGN.md`,
`STAGE9_INCORPORATE_DESIGN.md` §4, `docs/REQUIREMENTS.yaml` REQ-002/REQ-162/REQ-163.

---

### 2026-07-22 — Stage 9 campaign continued (3 more incorporated) surfaces a staff-vintage REQ-026 case, which reopens the receipts question and produces REQ-164 + the four commandments (branch work, not yet merged)

Continuing the one-district-at-a-time rhythm from the entry above: **Santa Fe NM, Gallup NM, and Las
Cruces NM** incorporated cleanly (dry-run → write → `per_grade_lct_sample` preview → review each time),
bringing the campaign to **6 of 38 gate@8-approved districts** (32 pending) — the approved total grew
from 22 to 38 mid-session as Ian cleared more districts through gate@8 in parallel. A pre-emptive scan of
all 33-then-pending districts (replicating Stage 9's bell-year resolution + the REQ-026 window check
without writing anything) found only one other latent temporal-fallback case (Dickinson 1 ND — a genuinely
stale 2016-17 middle-school source, the find-newer-source-and-re-extract kind of fix) — reassurance that
Gallup's case, below, was the outlier, not the norm.

**Gallup's secondary LCT fell back to statutory despite current-vintage bell schedules (425 min across all
three bands) — root-caused to NCES suppressing Gallup's entire 2024-25 staff report** (`DMS_FLAG=Suppressed`
in `ccd_lea_059`), forcing the staff picker back to 2023-24 and blowing the REQ-026 ≤2-start-year blend
window once combined with 2024-25 enrollment + 2025-26/2026-27 bell years. Confirmed NOT a repeat of #611
(the suppression is spread across many states, FIPS<10 actually under-represented) and confirmed Stage 8
manual entry is the WRONG remediation (it only touches bell facts; the binding constraint is staff vintage).
Filed **#613** (policy: widen the REQ-026 window? — Ian leans against, the guardrail is doing its job — and
a counterpoint on the SEA-integration-priority question the 2026-07-20/21 campaign had left open, since NM
is one of the 8 states with no SEA staffing file collected at all).

**A related ask — "why don't stages 6-9 get per-district receipts like 1-5?" — turned out to be two
distinct, smaller gaps once actually surveyed**, not the assumed one: stages 6/7 already write proper
receipts (just centralized by hash under `data/acquisition/{handoffs,extractions}/`, not per-district
folders); Stage 8's is DB-native but twinned to git already. The one real gap: **Stage 9's
`district_grade_minutes` has no git-tracked backup at all**, and **`district_status.json` silently lags
gate@8/Stage-9 events** because neither's write path calls `DS.export_status()`/`save()` — confirmed
concretely (the tracked file predated same-session incorporations). Filed **#614** (a console progress
view for Stage 9, epic #92) and **#615** (the receipts/twin gap, epic #128).

**This became the basis for REQ-164** (`must`; every stage 1-9 leaves an always-datetime-stamped,
audit-only per-district receipt + refreshes the twin in-path) **and the four commandments encoded as
testable REQ-165…168** (`type: principle`, each with `enforced_by` deterministic children +
`verification: mixed|periodic-sweep` for the qualitative residual) — a new schema shape, Ian-approved.
Design decisions along the way: **always-stamped, no fixed-latest name** (receipts are audit-only, never
transmission — a stable "latest" filename serves tooling, not humans, who can sort by name/date); a
same-second collision tiebreak via an **8-char content hash EXCLUDING volatile fields**, **loose across
languages with a `py`-/`node`- writer tag** (not RFC-8785-strict — the two writers never touch the same
artifact in the same second under always-stamp, so cross-writer hash equality is a guarantee that's never
exercised and can only mislead if it silently drifts); legacy unstamped receipts backfilled by
gov_db `state_event.created_at`, never filesystem create-date (which the planned external-drive migration
is about to reset anyway). A companion `docs/research/POLYGLOT_PIPELINE_ARCHITECTURE_TOOLCHAIN.md`
review reframed the Node/Python receipt convention as a declared cross-language contract
(`arch-manifest.json` + a fitness test), the same pattern `#476`'s eventual fuzzy-environmental-dependencies
extraction will want — so the new arch-manifest entries were kept generalizable on purpose. A `cache_ingest`
disk-re-read finding split into its own follow-up (**#616** — eliminate the round-trip for stages 2/4,
repoint the legitimate Node→Python/benchmark disk reads at stages 3/1, per-role rather than blanket).

**Built so far on `feat/pipeline-receipts-req164` (NOT merged to main):** `common/receipts.py` (the shared
writer + `latest_receipt()`/`iter_receipts()` resolvers, 15 unit tests); Stage 9's + Stage 8's per-district
audit receipt and in-path twin refresh (commit-after-DB-commit; best-effort — a disk/twin hiccup is logged,
never a failed already-committed decision); Stage 6/7's per-district capture-dir projections + a Stage-7
non-atomic-write fix; a pytest quarantine guard (the issue-#178 pattern, extended to captures) after a
real test-pollution incident (a shared-quarantine same-second collision from a `paths`-module reload)
surfaced and was fixed with a deterministic same-second tiebreak in `iter_receipts`. Remaining
(Phases 5b/3/4/5c — arch-manifest declarations + fitness test, converting stages 2/4/5 to always-stamped,
the gov_db-sourced legacy backfill script, and the concluding doc-tower update) deferred to after a context
refresh.

Authority: issues #613/#614/#615/#616/#476; `docs/REQUIREMENTS.yaml` REQ-164/REQ-165…168;
branch `feat/pipeline-receipts-req164` (commits `456b3e1`/`745d32e`/`6eff8e5`/`eb2b1da`, unmerged);
`docs/research/POLYGLOT_PIPELINE_ARCHITECTURE_TOOLCHAIN.md`.

---

### 2026-07-22 — Documentation-tower reorganization + a 5-way parallel accuracy sync against current code

A housekeeping pass, separate from the campaign/receipts work above: file moves, then a doc-content sync,
both landing directly on `main` (no feature branch — pure documentation, low risk).

**Reorganization.** `SEA_INTEGRATION_GUIDE.md`, `PA_CTC_DATA_DISCREPANCY.md`, and
`INSTRUCTIONAL_TIME_HARVEST.md` moved into `docs/state-integrations/`, alongside the catalog/assessment
docs already there. `docs/technical-notes/stage-7-loop-reports/` renamed to `learning-loop-reports/` (more
of these are coming, not just Stage 7's) and `EXTRACTION_BENCHMARK_FINDINGS.md` +
`STAGE5_TUNING_NOTES_2026-06.md` moved in alongside it. `docs/technical-notes/refactor-20260123/` (an
unreferenced, six-months-stale one-time investigation) moved into `infrastructure/quality-assurance/docs/`.
`docs/fable_review_2026-07-01.md` — reconsidered mid-pass once Ian recalled it was *this exact review* that
prompted the original move-tracking-to-GitHub-issues decision — went to `docs/archive/` instead (the
existing home for superseded planning docs, its own "tracking moved to GitHub issues" banner now paired
with a matching archive-date banner) rather than quality-assurance. Every full-path reference to the three
relocated state-integration docs was revised to a bare filename (Ian's call); every reference broken by the
other two moves was repointed at the real new path; `docs/archive/`'s own historical citations were left
untouched on purpose (frozen-in-time by design). Also committed 7 Stage-6/7 receipt files that had been
sitting uncommitted in the working tree from earlier in the session.

**Accuracy sync.** Five parallel agents, one per target, each independently verifying claims against live
code/DB/`gh issue` state before editing, all findings then independently re-verified before commit (DB
queries re-run, `gh issue view` re-checked, `pytest` counts re-run) — nothing accepted on summary alone.
Real corrections found: **`DATABASE_SETUP.md`** had two fully fictional tables
(`grade_level_enrollment`/`grade_level_staffing` — the real ones are `enrollment_by_grade`, `staff_counts`,
`staff_counts_effective`) and a `lct_calculations` column list that didn't match the live table at all
(`scope`→`staff_scope`, `staff_count`→`instructional_staff`, missing the whole REQ-026 temporal-validation
column set); `mv_lct_summary_stats` is 4 scopes live, not the documented 7. **`PIPELINE_GOVERNANCE_AND_STATE.md`**
and the **Stage 6-9 design notes** carried a cluster of "Stage 8/9 isn't built yet" residue left over from
before #89/#92/#93 shipped, plus two stale test counts (Stage 6: 101→141, missing the console-redesign
draft suites; Stage 9: 10→11 / 9→21) and a mostly-resolved `REQ-117`/`REQ-118` ledger-drift note (both now
`tested`; one stray acceptance-criterion line is the only real residual left). `STAGE9_INCORPORATE_DESIGN.md`
picked up a live-verified campaign-status line (the 6/38/32 numbers above). **`TERMINOLOGY.md`** gained five
grounded definitions (benchmark district/`batch_00000`, receipt, handoff-vs-extraction, closing argument,
incorporate/`district_grade_minutes`/overlap flag) — deliberately scoped to what's real on `main` today,
not the unmerged receipts-branch extension. `PROJECT_CONTEXT.md` needed no changes (a light-touch check
confirmed it, correctly, per its own header, stays mission/roadmap-only). `lint-imports` 4 kept/0 broken and
the full DB-free suite (1905 passed) held throughout.

Authority: commits `8c51d1b` (reorg), `f7cad85` (sync), both on `main`.

---

### 2026-07-23 — REQ-164 receipts completed on-branch; a Stage-9 campaign run the *deterministic* way surfaces three real findings and crystallizes "the product is the pipeline, not the district"

The receipts hardening (`feat/pipeline-receipts-req164`, still unmerged) reached completion: stages 5-9
now leave always-datetime-stamped per-district audit receipts through the one shared writer, unified on
a `stage<N>_<stage_name>` basename (stage number leading, so a filename sort is pipeline-ordered); the
#616 write-then-reread round-trip was eliminated for stages 2/4; the Stage-5 `filtered.json` converted to
`stage5_filter` and 112 legacy files were backfilled live. Two scope corrections landed on investigation,
not by plan: `processed.json` turned out to share `discovery.json`'s done-marker coupling (its *existence*
drives reconcile), so it deferred alongside discovery/candidates/captures rather than converting — only
the genuinely reader-less Stage 5 converted now. The whole benchmark-vs-receipts discussion that this
opened — why benchmark injection mimics Stage-2/3 output, and that the district-keyed "Stage 9 wall" is a
*symptom* of a missing benchmark-dispatch terminus rather than the design — became **epic #617**
(provenance-scope the wall; give benchmark batches a gate@5 terminus and benchmark dispatches a gate@7
terminus; re-run batch_00000's districts fresh into LCT), with the deferred done-marker→gov_db inversion
folded in.

The session's durable lesson came from one district. Resuming the Stage 9 campaign, a stale CLAUDE.md
breadcrumb ("watch for Dickinson — stale 2016-17 source, re-extract before incorporating") led to stepping
in and hand-verifying the district by reading its captured PDFs — reaching a confident conclusion
("source is current, safe") that was **wrong**: the deterministic pipeline had it right all along
(Dickinson's middle band carries a 2016-17 vintage and the recompute correctly drops it out of the
REQ-026 window). The lesson, established with Ian and codified as a CLAUDE.md durable fact + a memory:
**the immediate product is the robust, deterministic pipeline, not any one district's outcome.** A result
reached by hand-orchestration is a process failure even when the number is right — it violates
commandments #2/#4 (manual inspection of ~20k districts does not scale) and, most sharply, #1
(auditability): a probabilistic model judgment is non-reproducible and therefore unauditable, the opposite
of a deterministic guard. A corollary on handoffs: an imperative-without-its-rationale (a terse note from
present-self to future-self) gets *re-interpreted* by a fresh context — decisions belong in durable,
deterministic homes (a tracked issue, REQUIREMENTS.yaml), consumed as data, not breadcrumbs.

Applying that, the rest of the campaign ran the deterministic way — `incorporate_batch --dry-run` →
exception list → real run, trusting the script's own guards rather than eyeballing districts — and
**that is exactly what surfaced the real findings**, none of which hand-inspection would have caught:
**#626** (a logged gate@8 override is *not* honored past the REQ-026 temporal window — Dickinson's
approved council secondary silently drops to statutory, confirmed in production at recompute; the open
decision is whether a named human override should count as an auditable "treat as current"); **#627**
(the Stage-8 `mean_tiebreak` path emits a band gross inconsistent with its own stored start/end times, a
fail-loud-blocking internal-consistency bug that halted two districts); and **#628** (the LCT recompute
is a full-corpus ~2m08s rewrite over 17k districts, timeout-prone and O(all) for an O(changed) input).
36 of 38 gate@8-approved districts are now incorporated into `lct_calculations`; 2 blocked on #627,
Dickinson's final secondary value pending #626.

Authority: branch `feat/pipeline-receipts-req164` (HEAD `625aa41`; anchors `7d8f805` Phase 5b,
`e025df7` #616, `2a40e72` Stage 5 conversion, `831dc7a` naming, `f74ff8c` the "product is the pipeline"
fact); `docs/REQUIREMENTS.yaml` REQ-164 (status `tested`); GitHub epic #617 (sub-issues #618-626) +
#627 + #628.

### 2026-07-24/25 — Stage 9 campaign closes at 38/38, #626 lands a durable temporal-exemption primitive, and a `/code-review max` sweep of the whole branch ships same-day before merge

The two blockers left open on 2026-07-23 both closed. **#627** (Stage-8 `mean_tiebreak` emitting a
gross inconsistent with its own stored start/end) was fixed at the root — `aggregate_band` now omits
representative times for a synthetic-mean band rather than pairing a synthetic value with one real
school's span — which unblocked Midview and Millard. **#626** — whether a logged gate@8 override should
be honored past the REQ-026 temporal window — was Ian's call: *"a human override should be treated as
equivalent to an in-temporal-window schedule."* That shipped as two parts: a `human_vouched` flag
(originating on `district_grade_minutes`, then relocated to `bell_schedules` — see below) that exempts a
vouched grade's vintage from the blend-window test without exempting a non-vouched sibling in the same
scope; and a vintage-derivation fix so a band's stored year tracks the *winning* value's source school,
not a losing/closed-school sample (Dickinson's middle had inherited the since-closed Hagen JH's 2016-17
URL despite winning on the current Dickinson MS's reading). Re-incorporating all 38 and recomputing
confirmed the blast radius was exactly Dickinson — every scope flipped `per_grade_statutory` →
`per_grade_bell`, secondary 350→428 — with zero collateral movement elsewhere in the corpus.

With the campaign complete, PR #629 (REQ-164 receipts + the full Stage 9 campaign) went up — and before
merging, a `/code-review max` pass across every commit since 2026-07-20 was run: nine parallel finder
angles (line-scan, removed-behavior, cross-file tracing, language pitfalls, wrapper/write-path
correctness, reuse/simplification, efficiency, altitude, convention checks), one of which died mid-run
on an API error and was cleanly respawned from a fresh agent rather than left silently absent. The
sweep surfaced ten issues (#630-639), several from two *independent* finders converging on the same
defect — the strongest signal a review can produce short of a repro. All ten were addressed the same
day, not merely triaged: **#630** (Stage 9's re-incorporation UPDATE path relied on `add_bell_schedule`'s
merge-preserve semantics and left stale times on a row whose method flipped to `mean_tiebreak` — caught
a *live* instance, `4200874` elementary, mid-fix); **#631** (the idempotency key was the frozen-receipt
fingerprint alone, so a mapper-logic fix with no receipt delta was silently inert without `--force` —
now `(fingerprint, MAPPING_VERSION)`); **#632** (an excluded/struck school's stated year could still win
band-consensus vintage, the same bug class #626's URL-vintage fix had just closed on a different path);
**#636** (`human_vouched` had been added to `district_grade_minutes` — documented as a *regenerable
projection* of `bell_schedules` — making the projection's own contract false; relocated to
`bell_schedules`, migration 028, with the projection now genuinely inheriting it); plus a subprocess
orphan/decode fix, a triage-endpoint 500, three consolidations (one HH:MM parser, one statutory-360
constant, a grade→band equivalence fitness test pinned across the import-linter boundary), and hardening
(`_sanitize_reason`'s `--`-reformation, a documented rounding choice). Two findings were refuted rather
than fixed after checking the code against its own test suite and design intent — the Node discovery
breaker's "resets only on success" was a deliberate, already-pinned choice (a WAF'd district's dead links
404 *between* challenges; resetting there would violate the one-attempt rule), and the gate@8 twin-export
"O(all districts)" concern measured at 171 districts / 0.33s, not the ~17k feared. Refuting with
evidence, not silence, is what made the closure trustworthy. Re-incorporating and recomputing after the
fixes confirmed zero LCT value changes beyond the one #630 heal — the review hardened the pipeline
without moving a single production number it didn't intend to.

The whole arc — REQ-164 receipts, the Stage 9 campaign, #626/#627, and the review follow-up — merged to
`main` as PR #629 (squash commit `a26aee9`) on 2026-07-25.

Authority: PR #629 (merged); GitHub issues #626-639 (all closed); migrations 027 (`district_grade_minutes.
human_vouched`, superseded-in-place) + 028 (`bell_schedules.human_vouched`, the surviving source of
truth); `docs/REQUIREMENTS.yaml` REQ-164 (`tested`).

### 2026-07-25 — Epic #617: a permanent exclusion of 27 districts turns out to be a GRAIN error, and the fix generalizes into a third pipeline construct

Closing the Stage 9 campaign surfaced the question that started this: **why can't `batch_00000`'s 27
curated-ground-truth districts ever be written to `lct_db`?** The answer was a guard, mirrored across
five sites, asking *"has this district EVER been in a `batch_type='benchmark'` batch?"* — and because
`batch_district` rows are never deleted, the answer is permanently yes. Those districts are among the
largest in the corpus, and a district honestly re-discovered, re-extracted and human-approved at gate@8
through an ordinary production run would still have been refused, forever.

**The diagnosis is the durable lesson: the guard keyed on DISTRICT IDENTITY where the documented
rationale was about EXTRACTION PROVENANCE.** Identity was a serviceable proxy only while those
districts had exactly one history. The moment a district can travel through the pipeline more than
once — which is the whole point of follow-ups — an identity-keyed rule starts refusing correct work.
The generalization: *a run's handling type is a property of the work, never of the district.*

Reframing it that way dissolved most of the guard. Benchmark work had never been given a **terminus**;
nothing structurally stopped it flowing toward the LCT write, so a per-district wall had been bolted on
instead. Give each harness its stopping point — a benchmark **batch** (which A/Bs Stages 2/3/4) ends at
gate@5, a benchmark **dispatch** (which A/Bs Stages 6/7) ends at gate@7 — and benchmark output becomes
*structurally* incapable of being a Stage-9 candidate, with the remaining guards demoted to defense in
depth. Ian then restated the whole picture from first principles mid-implementation, which named what
was really being built: batches and dispatches began as **human-factors** constructs (working in sets
makes supervision attention and approval clicks affordable), and the type axis is a distinct third
layer — **handling instructions**, the thing that makes it possible to test, measure and train without
experimental output reaching the database.

Four findings worth carrying, three of which corrected work already written:

- **The planning pass earned its keep by being wrong in public.** The first draft would have forced a
  dispatch to `benchmark` whenever any selected *district* had benchmark history — relocating the exact
  identity bug the epic exists to retire, one stage upstream. Ian's demand to verify four
  *mobility properties* (a district must move freely between harnesses in both directions) is what
  caught it; two of the four failed on first inspection. Mobility became the epic's acceptance test.
- **When a guard's unit is coarser than its trigger, refuse — do not coerce.** A dispatch carries one
  type, so auto-forcing it on one stale representation would wall every other district sharing it.
  Gate@6 reports the offending representations and refuses the freeze, naming them.
- **"A predicate true for A and B" hides a choice between derivation and declaration.** Deriving
  redo-eligibility from `batch_type` would have put the FIXED ground-truth corpus one console click
  from corruption: a Stage-2 run on `batch_00000` would have folded fresh SERP candidates into 27
  districts' frozen `gt://` candidate sets. Declaring it on the batch, with an absent value falling
  back to the historical rule, cost one nullable column and changed no existing batch's behavior.
- **The hole the epic warned about existed in production already.** Classifying all 39 frozen handoffs
  by *representation* provenance rather than district identity found 2 pure benchmark, 36 pure
  production — and one **mixed**: a genuine production dispatch that had pulled in three `gt://`
  curated PDFs, carrying 227 accepted facts on production extractions with no gate@8 approval. The
  retired wall was the only thing holding them. It also proved dispatch grain too coarse (tagging that
  artifact either way is wrong) and forced the Stage-9 guard to two arms — a stamped `dispatch_type`
  and a provenance derived from the frozen receipt, neither able to see what the other sees.

A methodological consequence is now disclosed in `METHODOLOGY.md`: the 27 districts' absence from
published LCT coverage is a **pipeline artifact, not a data-availability finding**, until #620's re-run
completes. The ground-truth corpus itself stays fixed and is never appended to by approvals.

Authority: GitHub epic #617 + sub-issues #618-#625, #640 (the benchmark-*batch* terminus is still
unenforced for newly-composed benchmark batches — durable per-representation batch provenance, filed
2026-07-25); `docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md`
(the full evidence record, including §10-§11's log of what the planning pass got wrong) and, beside it,
Ian's own statement of intent; `PIPELINE_GOVERNANCE_AND_STATE.md` §13 (the durable architecture).

### 2026-07-26/27 — Epic #617 Phase 3: the grain moved but the SCOPE didn't, and a 6-PR review round found the pattern repeating inside the fix itself

Phase 3 (PR #648, merged as `af1ce77`) shipped the two-arm provenance guard #619 designed: a Stage-9
write wall keyed on the receipt's own representations rather than district identity. Measured
behaviour-preserving against 83 districts holding production facts — membership and provenance agreed
on all of them, and gate@8 admitted the identical 56. On that evidence, the epic's acceptance property
("a district honestly re-run incorporates") looked satisfied.

**It wasn't, and the reason is the same shape as Phase 0-2c's own lesson, one layer up.** #619 moved
the *grain* the wall keys on (district → provenance) but never moved its *scope* (all-of-history →
this-run). Two layers sit in front of that wall — the gate@8 review queue and `merge_fact_runs` — and
both stayed scoped to "has this district EVER produced a benchmark-provenance fact," which is
permanently true once true, because `extraction`/`school_fact` are append-only and a fresh run can
only add facts, never retract the old ones. Filed as #662 once #620's actual re-run batches
(`batch_00030/31/32`, 25 districts) made the disagreement observable: **25 of 25** were walled by the
queue today, and **957 of 957** accepted benchmark facts carried no parseable `school_year`, so the
merge's year-supersede axis never engaged and the earliest (injected) fact always won. Every prior
"the grains agree" measurement had been taken in the one state — before any re-run existed — where the
three layers could not possibly disagree.

**The fix, decided by Ian as (c) reclassify + (b) precedence, turned out safer than either side had
assumed once it was measured rather than reasoned about.** The candidate sweep is 30 extractions across
exactly 27 districts, and — contrary to the caveat both #662 and the Phase-3 findings report had
carried forward from the mixed-handoff discovery — **zero of those extractions are mixed**: the one
real mixed artifact (`f33790e63820`) is mixed at *handoff* grain, not extraction grain, so relabeling
each extraction's own `run_kind` is surgical. Zero of the 27 carry a gate@8 approval or a Stage-9
event, so no frozen human judgment was at risk. And the escape hatch #662 first proposed — striking the
stale fact at gate@8 via `band_exclusion` — was withdrawn outright, not merely deprioritized: the merge
collapses to one row per `(band, school)` *before* exclusions apply, so striking the injected winner
deletes the school from the band rather than promoting the runner-up.

**The review round that followed the fix is itself the strongest evidence for the standing lesson.**
Nine independent review passes across the resulting PRs (#663-#667) surfaced roughly thirty candidate
findings; most were already-correct code the reviewers had verified rather than broken, but three
survived scrutiny and were real: `run_kind` was only ever corrected retroactively (a second benchmark
dispatch would have silently reproduced #662 with no write-time guard), the gate@6 operator dashboard
would have read all 27 districts as "never extracted" the moment the migration landed (inviting the
exact wasted re-dispatch its own signal exists to prevent), and the migration script's own dry-run
diagnostic re-ran its full query once per district while never firing on the one branch that mattered.
All three were the same family of miss as #662 itself — a fix verified against the state that existed
*before* the fix, not the state the fix was supposed to produce.

**The merge sequence itself repeated the epic's one-home lesson twice more, mechanically.** #665's
`test_one_home_fitness.py` — a declared table of consolidated-rule detectors, itself new in this
round — caught two regressions the moment later PRs rebased onto it: a `dispatch_type` check
re-inlined instead of routed through the new `is_benchmark_dispatch` helper, and two test files that
still hand-rolled the precious `handoff` INSERT chain `tests/benchmark_seed.py` exists to own. Both
were sequencing artifacts (the offending code was written on branches that predated the consolidation
it violated), and both were caught automatically rather than by a human noticing — which is the
generalization #665 built after Phase 0-2c shipped a bespoke guard for one rule and then quietly
re-created the same duplication three more times in the same round of work.

Authority: GitHub issue #662 (closed) + review sub-issues #649-#661 (closed); PRs #663-#668 (merged to
`main`); `docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md`
§10.19-§10.20 (the grain-vs-scope correction) and §12 (the Phase A/B/D implementation log); REQ-169's
SCOPE criterion in `docs/REQUIREMENTS.yaml`. Epic #617 stays open pending #620 (the campaign itself,
now unblocked) and the deferred structural backlog (#622-#625, #640, #645, #646).

---

### 2026-07-27/28 — The #620 campaign runs, and running it finds more than reading ever did

With #662 merged, the standing question was whether the retired wall would actually let a re-run
district's evidence reach `lct_db` — or whether it would clear the wall and starve somewhere else
nobody had looked. Driving the campaign rather than reasoning about it answered that, and along the
way found six things no amount of code review had surfaced.

**The merged fix had never been applied.** #662's reclassification migration
(`reclassify_benchmark_extractions.py`) was written, tested, and merged on the 26th — and the live
governance DB still held its pre-fix state on the 27th: 1,276 production-labelled facts carrying
`benchmark_gt` provenance, zero extractions at `run_kind='benchmark'`. Running `--apply` was itself
the finding — the epic's own headline acceptance test had been passing against a seeded fixture the
whole time, never against the system it was meant to describe. **Generalizes as its own standing
lesson, sibling to §10.20's:** for a change that mutates precious/live state, merged is a checkpoint,
not a finish line — CI cannot close that gap, because CI has no live DB to be un-migrated.

**Three redo batches (`batch_00030/31/32`, 25 of batch_00000's 27 districts — 2 are domain-less and
unreachable by any composer, filed as #646) then ran Stage 2 through Stage 4 cleanly and answered the
epic's actual question: 2,124 documents, 97.6% usable, and 80.9% of time-bearing evidence fresh
(production) rather than injected — not one of the 25 districts came back benchmark-only.** The
premise #617 was built on is now measured, not assumed.

**Driving the campaign also surfaced a failure class the epic's plan never modelled: the console
itself.** Three defects (#669, #670, #671), all sharing one root cause — a Stage 2/3/4 status view
computing "is this district done" from stale disk-artifact existence with no per-run receipt to
disambiguate — meant a redo district could read `done`, showing the *previous* run's numbers, for the
entire duration of the current one (measured up to 38 minutes), and a genuine capture timeout
(Orange County FL, `1201440`) could render as a clean success. On one batch the display asserted the
literal opposite of the run's actual outcome while that run was still in progress. Under the ramp-up
posture the operator's reading *is* a pipeline stage, so these are correctness defects, not
cosmetics — and they promote #622/#623 (the disk→gov_db done-marker inversion, previously deferred as
"insurance on a mechanism nobody had run") from insurance to interest.

**Gate@5 review then surfaced a structural hole in the release path, independent of the console: a
human target label unconditionally bypasses the #241 validity floor (#674).** Composed with the
standing labelling doctrine — a target label carries *shape*, never fitness-for-use, so a reviewer who
finds a correctly-shaped but pre-2017-18 document is *required* to label it — the two rules together
mean correctly following the labelling doctrine guarantees below-floor material reaches paid
extraction, with no force-hold override to stop it. Live instance: TAOS (`3500127`) froze a production
dispatch with two below-floor handbooks, both correctly labelled per doctrine. Filed under epic #92,
whose scope was reframed the same day from "build Stage 9" to its actual purpose — keeping facts that
shouldn't reach `lct_db` from being sent down the pipeline in the first place — which made #674 that
epic's most consequential open item, ahead of the console status view it was originally scoped around.

**Composing the campaign's first production dispatch then found the epic's own guard undefended one
step upstream (#679).** `release.best_send` and the REQ-116 hub-priority ranking select a "best"
representation with no knowledge that `dispatch_type` exists, so a benchmark-provenance rep can win a
selection contest the freeze guard then (correctly) refuses. On Bangor (`2302820`) this was not mere
deselect-busywork: its one fresh district-hub capture tied exactly with its injected counterpart on
both ranking terms, `max()` broke the tie by iteration order, and the injected copy won — holding the
fresh one and leaving the district with zero sends once the guard's "deselect the offending reps"
instruction is followed. This is currently the blocking item on the campaign: reconciled explicitly
with the settled badge-never-filter decision (gt:// reps stay visible; only the *default selection*
needs the provenance check), and sequenced as the immediate next fix.

**A related but separate finding on the discovery side (#672, epic #128): the 5→1 zero-yield ladder's
widened rung is not monotonically better than the rung before it.** On Wyandanch UFSD (NY, `3631800`),
widening the query vocabulary tripled SERP result volume and *diluted* the district's own domain's
vote share below the geo-derivation threshold — a share-based test, defeated by a larger denominator —
discarding 109 URLs including on-domain hits the standard rung had already used successfully. The
district's ladder then terminated at `manual_flag`, which may be an artifact of the escalation
mechanism rather than evidence the district publishes nothing.

**Housekeeping fell out of the same two days of close reading:** three `sev:critical` issues
(#260-#262, "hardcoded actor name allows impersonation") were re-triaged to `sev:minor` on the
evidence that the console binds loopback-only with no auth system to impersonate — a generic
crossfam security lens over-applied to a single-operator local tool, left open with an explicit
reactivation condition rather than closed outright. A 2026-07-13 crossfam batch (#332-#335) was
re-verified against code that had moved since filing: two of the four line references had drifted to
different files/lines entirely, one (#333) turned out to describe a site that was *already fixed*
while the same defect survived at a different call site (`stage7_run.py:887`, still open — an
explicitly-empty `sent_files` list falls back to a legacy singular field, which can resurrect a stale
filename into request history and cause the 7→6 composer to skip a representation it should retry).

Six new issues (#669-#679 minus gaps) plus three console/UX items (#675-#678) were filed, each carrying
its own "how this was determined" section per REQ-165 — the derivation, not just the claim, since the
epic's standing risk (three layers shipping green against measurements that could not fail) is only
avoided by making verification reconstructable rather than assumed. All were attached to their
governing epics via GitHub's native sub-issue relation (#96 console, #92 Stage-9/release-correctness,
#128 deferred discovery quality, #617 the guard itself) — a housekeeping pass the epic's own tracker
had been missing, since cross-reference comments alone don't produce the parent/child relation the
epic-scoped issue lists render from.

Authority: `docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md`
§13 (appended 2026-07-28, the current plan — supersedes §11); issues #669-#679 (open) and their
cross-references; #260-#262, #332-#335 (re-triaged/re-verified, comments carry the evidence). The
per-stage design notes, `PIPELINE_GOVERNANCE_AND_STATE.md`, and `docs/ACQUISITION_PIPELINE.md` were
synced to this state the same day — see each file's own dated notes for detail. Epic #617 stays open,
now blocked on #679; epic #92 absorbed #673/#674 and is no longer "nearly closed."

### 2026-07-28/29 — #679 lands, the campaign writes its first two districts, and finds two more issues on the way

#679's fix (PR #680): the eligibility check moved to BEFORE the narrowing passes, not just at freeze.
`district_release_input` now excludes benchmark-provenance reps from the default send set while
`dispatch_type='production'`, applied ahead of prefer-recent/sibling-variant/hub-priority — so none of
those passes can crown an ineligible rep and then have the freeze guard refuse the winner. Held reps
stay visible/badged (#662 decision 4 unchanged: display and selection are different axes). Verified
against the Bangor tie specifically (the fresh hub now wins) and live: Worcester composed 26/34,
Bangor composed its 1 fresh hub, both passed `assert_dispatch_type_allowed`.

**Both districts then ran the full pipeline to a real LCT write — the campaign's actual deliverable,
proven twice.** Worcester (`2513230`) went through clean: 22 accepted facts, zero gate@8 hand-edits,
elementary=365/middle=383/high=383. Bangor (`2302820`) did not, and the *why* is the session's second
finding.

**Every one of Bangor's 3 council-agreed facts stored a time that appears nowhere in the source
document (#681, epic #80).** The consensus rule (`aggregate.consensus_school_facts`) clusters two
models' (start, end) pairs within a ±15 tolerance and stores `round(mean(...))` on agreement. On
Bangor's district-hub page, the elementary section is declared as two grade ranges (PreK-3, Grades
4-5) with different bell times; one model quoted the PreK-3 line, the other quoted the Grades-4-5 line,
and the two landed inside tolerance — "agreement" between two DIFFERENT referents, not a real
consensus, and the stored 08:45 matches neither source line. The middle and high bands showed a milder
version (doors-open vs. homeroom-start on the SAME section). Ian corrected all three at gate@8 (1
`band_exclusion` + 7 per-school `human_added_fact` rows for elementary; 2 `human_determination`
corrections for middle/high) — the sanctioned mechanism, used exactly as designed. But at roughly 9
manual actions for a 9-school district, the rate doesn't scale to the remaining 23, which promotes
#681 from "worth noting" to "worth fixing before extracting many more districts." Filed against epic
#80 (Council Lab) rather than as a bugfix: the right response is a measured prompt/rule change (elicit
one row per declared schedule section instead of asking the model to pre-map to a band; or make the
agreement rule referent-aware, e.g. by checking the evidence quotes anchor to the same locus) —
exactly the kind of question the Council Lab exists to A/B against the curated GT corpus, not guess at.

**Approving Worcester also surfaced a second gap: the documented "gate@8 → Stage 9 then auto-writes"
step isn't wired (#682, epic #92).** The approve endpoint records the approval, the calibration row,
the receipt, and the JSON-twin backup, then returns — nothing calls `stage9_incorporate`. Worcester's
approval sat with zero `district_grade_minutes` rows for about 25 minutes until the CLI was run by
hand. Both districts this session were incorporated via the CLI, not the console. Filed with the fix
shape: invoke `incorporate_district` post-commit on approval, fail-loud but never failing the approval
itself (the write is idempotent and re-runnable), one shared entry point so the endpoint and CLI can
never diverge in behavior.

**Reading the falsifier against this round: it held.** "If any district needs a hand-edit or a
re-adjudicated gate@8 call, the mechanism is wrong — fix the pipeline, not the district" was written to
catch silent absorption of a pipeline gap into manual district-by-district labor. Bangor needed
hand-edits, but the response was to file #681 (the pipeline defect) rather than just clear the district
and move on — the distinction the doctrine draws.

Authority: live governance DB reads (extraction 6508 facts + evidence_json; `stage8_approval` 1557/1558;
`district_grade_minutes` before/after the CLI run) and the captured source page, all 2026-07-28/29;
issues #679 (closed via #680), #681, #682 (open) and their comments. `district_grade_minutes` grew from
38 to 40 districts. Epic #617's #620 campaign has its first 2 of 25 districts written on
production-provenance; epic #80 and epic #92 each gained one open issue.

---

## Part 3 — Live Roadmap & Carry-Forward Ideas (recorded, largely unexecuted)

### Strategy: shift from "automate everything" to "AI-assisted human efficiency"
Given automation's low ceiling, the highest-ROI play is making *human* search ~10× faster (AI generates search *queries*, not extracted *data*; batch by state; quick-entry form ~30s/district; target ~10 districts/hr). Concrete untapped leads recorded at the time:
- **State SEAs that already collect instructional hours in bulk** — e.g., **Colorado's Periodic Data Collection** covers ~180 districts in one export. Identify other centralized-SIS states + FOIA.
- **80/20 on the ~200 largest districts** (~13.6M students; was only ~26% covered) — a named top-30-missing list (Puerto Rico DOE ~240K, Pasco FL, Davidson Co TN, Fort Worth ISD, Milwaukee, …) was estimated at ~3 hrs of human work for +1.1M students.
- **Untested external APIs** — SchoolDigger (free 2K calls) and GreatSchools (14-day trial); unknown whether they carry bell schedules — worth a ~10-call probe before investing.
- **Crowdsourcing** via PTO networks with screenshot proof.

*(Source: `BELL_SCHEDULE_COLLECTION_STRATEGY.md`. Treat as a live, mostly-unexecuted backlog.)*

### Token-efficiency architecture (still the working model)
A lightweight `enrichment_reference.csv` (3 cols vs. 36) replaces loading the 9.24MB full file (~90% token reduction per lookup); batch enrichment with checkpoint/resume; pre-filter candidates (>1,000 enrollment, must span multiple grade levels — small/rural districts rarely publish schedules). This is the "why" behind the slim-file/reference-file patterns still in the codebase. *(Source: `INFRASTRUCTURE_EFFICIENCY_ANALYSIS.md`.)*

---

## Part 4 — Distilled Technical Recommendations (from external research the user gathered)

### Crawlee pop-up / consent-modal handling (fold into `docs/ACQUISITION_PIPELINE.md` when relevant)
Strategy hierarchy, best → most brittle, centralized in a reusable `dismissPopups(page)` helper called at request-handler start and after every navigation/scroll:
1. **Prevent pop-ups before they render** — `preNavigationHooks` + network-block known consent vendors (onetrust, quantcast, cookiebot, trustarc).
2. **Inject CSS once** to `display:none` overlays (`[role=dialog]`, `.modal`, `.overlay`, `.consent`) and force `body{overflow:auto}`.
3. **`page.on('dialog', d => d.dismiss())`** for native JS dialogs.
4. Prefer **semantic / `aria-label` selectors** over brittle text matching.
5. DOM removal as the nuclear option.

**Key insight:** if clicking dismiss buttons is your *primary* strategy, you're already on the fragile path — frequent pop-ups often signal you're scraping at the wrong abstraction layer (a structured API/sitemap probably exists). *(Source: `ChatGPT_and_Perplexity_advice_on_modals.md`.)*

### LCT validation safeguards — flag, don't delete (verify which landed in the pipeline)
Run against the real 14,428-district dataset; recommends flagging via `level_lct_notes` codes so the dataset stays defensible rather than silently shrinking. Empirical counts (the load-bearing, hard-to-reconstruct part — **confirm against current code**):
- `ERR_VOLATILE`: enrollment < 50 → **502 districts** (one staff change swings LCT 30–40 min).
- `ERR_FLAT_STAFF`: all 5 scopes identical → **53 districts** (only teachers reported, rest zero-filled).
- `ERR_IMPOSSIBLE_SSR`: staff/enrollment > 0.5 → **328 districts** (some physically impossible, e.g. 320:1 — data-dump errors / specialized units).
- `ERR_RATIO_OUTLIER`: teachers <20% of all staff → **192 districts**; teachers =100% → **34 districts**.
- LCT-Teachers "reasonableness zone" 5–120 min → **170 districts** outside.
- **Strict monotonicity** `teachers_only ≤ core ≤ instructional ≤ +support ≤ all` as a blocking error; check `teachers_core > teachers_only` deltas aren't Pre-K leakage (Pre-K is excluded); confirm `enrollment_k12 ≈ elementary + secondary`.

*(Source: `Proposed LCT Validation Safeguards from Gemini.md`. The current pipeline already implements several ERR_/WARN_ safeguards — see `calculate_lct_variants.py`; reconcile this list against it.)*

---

## Part 5 — System map & known latent issues (salvaged from PROJECT_SYNTHESIS, archived 2026-06-22)

`docs/PROJECT_SYNTHESIS.md` was a point-in-time reorientation doc (2026-06-05 resume). Its pipeline description (Crawlee+Ollama) is now retired and its data-state/flags were mostly resolved; it was archived. These two pieces are the durable salvage.

### The 4-layer system map (orientation)
```
LAYER 4  ACQUISITION  — search-led discovery → tiered capture → cheap-cloud council → aggregate → DB
            (the active frontier; code in infrastructure/acquisition/; see ACQUISITION_PIPELINE.md)
LAYER 3  DATA BACKBONE — PostgreSQL (Docker) + SQLAlchemy models + migrations (ledger: migrate.py)
            districts · bell_schedules · state_requirements · staff_counts(_effective) ·
            enrollment_by_grade · sped_estimates · *_crosswalk · lct_calculations
LAYER 2  LCT ENGINE   — calculate_lct_variants.py (DB-first; 10 scopes; safeguards; minutes-priority
            chain: band bell → any-band bell → statutory → 360 default)
LAYER 1  SOURCE DATA  — NCES CCD (2023-24 primary; 2024-25 school file added) · CRDC · IDEA 618 ·
            9 SEA integrations (FL TX CA NY IL MI PA VA MA)
```
Layers 1–3 are stable; Layer 4 is where active work lives. **Authoritative DB schema = `infrastructure/database/models.py`** (NOT `schema.sql` or the data dictionary).

### Known latent issues (still open as of 2026-06-22 — verified present, not yet fixed)
- **Obsolete `infrastructure/database/schema.sql`** — its `data_tier` comment diverges from the engine's actual tiering; `models.py` is authoritative. (SYNTHESIS flag #20)
- **Stale data dictionary** `docs/data-dictionaries/database_schema_latest.md` (gen. 2025-12-28) — predates migrations 003–015; missing tables/columns. Use `models.py`. (flag #19)
- **Two LCT code paths coexist** — legacy `queries.calculate_and_store_lct` (single-scope, per-grade rows) vs the modern `calculate_lct_variants.py` (scope rows, `grade_level=NULL`). Confirm only the modern engine runs in production; the legacy path writes an incompatible row shape under the current unique constraint. (flag #21)
- **Broken/inert old scraper tests** — `tests/test_scraper_resilience.py` / `test_scraper_security.py` import a deleted module and `pytest.skip` silently (false confidence). Candidates for deletion. (flag #25)

---

## Recovering the originals

All source files were removed from the working tree but remain in git history. To browse what existed:

```bash
git log --oneline --diff-filter=D -- 'docs/archive/*' 'docs/chat-history/*'
git show <commit>:docs/archive/<filename>   # view a specific archived file
```

The cleanup happened immediately after restore-point commit `59603c3`; the archived files were last present in that commit's tree.

### 2026-07-29 — Six more districts through the gates, and the backlog gets re-triaged around what they found

Three dispatches later (`d9a49bcabf0d`: Bridgeport/Bentonville/Broward; `df2b06f2f7a7`:
Essex Westford/Cleveland/Fairbanks) the campaign stands at **4 of 25 districts written** — Fairbanks
`0200600` joining Worcester and Bangor, and it is the cleanest yet: 26 accepted facts, staggered start
times from 07:30 to 09:50, and nearly every school computing to exactly 390 gross minutes. A district
running deliberate staggered bells on a uniform instructional day, which is what the metric was built
to see.

The other five did not go through, and each stall was diagnostic rather than incidental.

**The gate@8 verdict button routes nothing (#689).** Broward was sent back with a reason naming
re-discovery. Three docstrings and the console's own hint text promise a `sent_back → 8→1/8→6`
back-edge; no code composes either. The verdict half is fully auditable — precious row, frozen
receipt, state_event, Stage-9 block — and the routing half does not exist, so the reason a human
writes *is* the routing instruction, executed by hand. Filed as the sibling of #682: gate@8's two
arrows, approve→write and send-back→requeue, are both unwired.

**A district-built web app turned out to be the best data source we have met, and the pipeline could
not receive it (#686).** Broward's school-hours page embeds an AngularJS app over an open REST API
that returns 231 schools with 229 parseable `School_Hours` pairs, current year, in one document. The
capture holds six of them — the frame-text pass caught the app shell and the table header while the
XHR was still in flight; only the later `page.pdf()` artifacts caught the first viewport. The dev-URL
trail left in the shipped service file (`web01cdev`, `localhost:56084`) says district staff built it
on their own network. Ian's reading — a professional working under time and technology constraints,
not an amateur — is the one the evidence supports, and it reframes the finding: *some of the best
bell-schedule data out there was put up by people who wanted it found, in shapes no vendor
fingerprint will ever match.* Recorded with a recurrence trigger rather than a fix, since each
instance will be bespoke.

**Two districts stalled at gate@8 and produced four issues between them.** Cleveland `3904378` and
Essex Westford `5000395` both came back thin, and inspecting the records Ian had labeled explained
why:

- **#691 (`sev:critical`) — REQ-116 hub-priority narrows with no yield check.** Essex had 44
  target-labeled records; exactly one was dispatched, and the winner was page 14 of a school's
  two-year-old social-media feed, whose only relevant line points at an image the text capture never
  resolved. It displaced a 112-time list, a 61-time bell table, and a 57-time schedule document.
  Measured corpus-wide afterward: **23 of 42 hub-labeled districts are currently narrowed to exactly
  one send**, and the winner is frequently not the best evidence — Bentonville dispatches an 8-time
  page while holding a 52-time one, and **Fairbanks was incorporated on a one-rep dispatch that held a
  137-time bell schedule.** Bridgeport is the honest counter-case where the hub genuinely is best,
  which is why the fix needs a corpus measurement rather than a blanket rule change. The structural
  reading: `district_hub_by_school` asserts *shape* per the labeling doctrine, and hub-priority reads
  it as *fitness* — the #674 shape one stage later.
- **#692/#694 — gate@7 asked a coarser question than the one that matters.** Neither district raised
  a single follow-up directive despite middle bands standing on one school (1.5% coverage for
  Cleveland). `detect_requests` treats a band as covered when *one* fact lands in it. Ian identified
  the root cause: Stage 1 now carries a per-school spine forward, Stage 8 consumes it at slot grain to
  compute coverage and negative space, and Stage 7's follow-up detection was never refactored onto it
  — it receives the roster and uses it only to narrate a request it has already decided to emit, while
  `slot_assignment` is referenced nowhere in Stage 7 at all.
- **#693 — name normalization mints false disagreement.** Cleveland's cleanest instance: both council
  models read `08:35-15:35` for the same school, but one wrote "lincoln west science health" and the
  other "…science **and** health", so they grouped separately, neither reached consensus, and one
  became an accepted fact beside an unresolved phantom of itself. Essex shows the systematic form,
  acronyms against spelled-out names. This inflates `n_unresolved`, which is a headline Council Lab
  quality metric — so composition A/Bs today are partly scoring a normalizer defect as model
  disagreement.

**The backlog was re-triaged, and the diagnosis was structural rather than volumetric.** #128 had
grown to 19 open sub-issues, but they were two unrelated populations sharing a label: nine genuine
deferrals filed in early July and untouched since, and eight active-frontier defects filed in a single
day, seven of them major or critical, each with a live district as its pin. The cause was that
**#106 (Stage 5/6 filter & dispatch refinements) had closed**, leaving Stage-5/6/7 defects without a
home. Opened **#695** for them; #128 returns to its charter. In the same pass all 47 unlabeled open
issues were read — no hidden criticals, mostly unbuilt console and Council-Lab features, which is why
severity had never been applied to them. One promotion fell out of it: **#567**'s stale 2023-24 CCD
import leaves 2,051 districts without a `website_url`, **including both districts #646 treats as
"domain-less and unreachable"** — so a cheap re-point may raise the campaign's ceiling from 25 to 27.

*The methodological note worth keeping:* the decision to re-triage now rather than push on was argued
from the shape of the backlog, and the decision of **what to fix first** was settled by measurement —
#691 looked like an Essex problem until it was run across all 42 hub-labeled districts, at which point
it became a precondition for any further gate@6 freeze and raised a question the campaign had not
faced before: whether a district already written to `lct_db` should be re-composed and re-reviewed
when the evidence that was silently withheld from it comes back.

Authority: issues #683-#695 (all open, each carrying its own "how this was determined"); the
`stage8_approval` rows and `extraction` results for the two dispatches; `main` @ `b5821c7`.

**Decision (2026-07-29): districts already written through the #691 narrowing are NOT re-reviewed.**
Ian: they were reviewed at gate@8, the minutes are trusted, and future information will bring the
campaign back to them. The adopted amendment is that "eventually" became a **mechanism** — a standing
audit query, since nothing detects that a written district rests on a narrowed dispatch (17 of the 41
written do). Challenge-testing the decision also **corrected the report's own framing**: §14.7 reasoned
from what was withheld rather than what was covered, and Fairbanks turns out to be positively verified
— its elementary band is 90% sampled and *did* contradict itself (300/355/390 present, 390 winning 16
of 18), while the three high-yield held reps cover the same four middle schools already sampled, making
them redundant rather than missing. Recorded with the residual challenges and re-run triggers in
`docs/technical-notes/production-quality-control-research/2026-07-29-narrowed-dispatch-audit.md`.

### 2026-07-29/30 — Epic #695 closes in one sitting: nine fixes, and twice the measurement overturned the issue's own diagnosis

The whole pre-#620 correctness queue — #691 → #688 → #567 → #696 → #694 (+ re-measured #692) →
#683 → #684 — landed as seven sequential PRs (#697/#698/#700-#705), one per issue, each merged on
Ian's review before the next began. Epic #695 closed with all six sub-issues done, roughly 24 hours
after it was opened. The mechanics live in the issues, the PRs, and the dated reports under
`production-quality-control-research/`; what belongs here is what the batch proved about method.

**The measure-first protocol earned its cost, twice, by rejecting the fix the issue itself
prescribed.** #691's fix was picked from a corpus report across all 42 hub-labeled districts, not
from Essex's anecdote. But #684 is the clean specimen: the issue proposed widening `OFFICE_HOURS_KW`
and voting on a staff word near a time — measured over all 3,559 records, that rule is a **coin flip**
(acc 0.512) that would have demoted 59 tier-A real targets to remove 10 false sends, and the
doc-level `/employee handbook/` fallback is net-negative too (11 of its 17 labeled hits are real
targets — districts publish bell tables inside their staff handbooks). What discriminates is the
employment-obligation **clause** — staff subject → duty verb → the governed time — scored
*relationally* against student-referent language, per text basis: acc 1.000, exactly one record
corpus-wide (Bentonville, the issue's own pin), deliberately threshold-free so there is no number
tuned on a single record. Sibling #683 has the same shape: 15 firings, wrong on 13, and the bank's
worst target detector (0.4545) became its most accurate (1.0) with recall unchanged. The standing
lesson now has a positive form: *the intuitive keyword fix measures out net-negative often enough
that the measurement is not overhead — it is where the design comes from.*

**The max-review rounds kept catching the same structural class: a guard wired into one member of a
set whose other members share the property.** #705's review found `staff_day_owned()` consulted only
by `lf_heading_hours` while `lf_footer_hours` and `lf_explicit_minutes` — the other two
STRONG_STRUCTURAL detectors, which send *unconditionally* — could re-open the exact auto-send #684
closed. #703's review found the same shape in Stage 7 (compose didn't join the shared `band_done`
predicate detect/withdraw used). The countermeasure that stuck is the **closure pin**: a test that
iterates the *set* (`C.STRONG_STRUCTURAL`) and asserts every member consults the predicate, so a
fourth member can't ship unguarded. That is the #199 join-the-set discipline generalized from
registries to behavior.

**#696 was settled as a design decision, not a bug fix** — the three band relations (placement /
service-fillability / grade ownership) each keep their own consumer, the pool-vs-denominator gap is
surfaced at gate@8 rather than "fixed" (the alternative was the 200%-coverage lie), and #694's
bounded K-8 mode-check class (≤2 span-only schools per band) is the measured compromise that tests
the tie-rule assumption without chasing schools outside the pool against the no-spend guards.

**The falsifier held for the whole queue:** no district was hand-fixed; every wrong outcome became a
pipeline change with a failing-first pin. And the #662 merged-but-never-run lesson got its
counter-practice — every scoring change shipped with the full re-ingest + harness A/B + tuning-ledger
episode run *before* the PR, with the scorecard fingerprints in the report, and #705's regex
tightening was re-measured to be corpus-neutral (the identical 7-record duty-clause cohort) so the
no-re-ingest call was verified rather than assumed.

Authority: epic #695 (closed, with per-issue closing evidence); PRs #697-#705; the dated
measurement reports + rerunnable scripts under
`docs/technical-notes/production-quality-control-research/` (issues 683/684/691/694); `main` @
`f094555`.

### 2026-08-14 — The #620 campaign is traced end to end: 12 of 27 written, and checking an assertion instead of accepting it found the biggest defect of the campaign

The campaign's 27 former-benchmark districts were traced individually through production —
dispatch, extraction, directives, gate@8, Stage 9 — and the 9 districts sitting approved-unwritten
were incorporated (12 of 27 now in `district_grade_minutes`; Bridgeport had been approved and
unwritten for 16 days, waiting on #682's unbuilt wiring). The per-district detail and the evidence
for every finding live in issues #714-#722, each carrying its own reproducible "how determined"
footer. What belongs here is what the day proved about method and about the shape of the
remaining defects.

**The most consequential finding came from verifying a question rather than answering it.** Asked
whether #620 was as far as it could get before the logged issues were addressed, the honest move
was to check what was actually runnable — which surfaced #719 (`sev:critical`): the #164
escalation ladder sends a district to a GEO-scoped follow-up after *any* prior round, a geo batch
deliberately blanks the scoping domain, and Stage 2's #229 guard then refuses **every** result it
finds. Six batches, 70 targeted schools, **zero resolved** — while the providers were returning
exact hits on each district's own domain (`katesmith.washoeschools.net/our-school/bell-schedule`,
refused for "no-scoping-domain"). Geo scoping exists for the Millard class, where the district has
*no* usable domain and the job is to discover one; the ladder escalates on **round count, not
diagnosis**, so districts whose domain was never the problem got a mode whose premise is false for
them — and are then declared escalation-exhausted having learned nothing. Live since 2026-07-27.
An "is this as far as we can go?" answered from the trace summary would have said yes and been
right for the wrong reason.

**A second measurement-versus-appearance case, same day:** Washoe's run looked like a recall
failure (39 accepted / 67 unresolved) and was a *formatting* failure — both voters agreed on ~106
schools, but one echoed the document's 12-hour clock (`03:30`) where the other normalized
(`15:30`), and the canonical 24h parser put the clusters 720 minutes apart, minting agreement into
disagreement (#716). The fix is deterministic (no school day ends at 3 AM) and the recovery is
free: re-aggregating the stored receipt should return ~100 schools with no model spend. The
inverse also held — Mesa's 104 "missing" reps were the #120 mode-stability early-exit working
correctly, and Memphis's 112 unresolved were checked against this signature and cleared. Reading a
count as a verdict was wrong in both directions.

**"Limbo" became a named class rather than a list of separate bugs.** #682 (approve→write
unwired), #689 (send-back routes nothing), #718 (a gt://-only district reads ready and cannot be
reached by the follow-up loop at all), and #720 (directives that can never execute never resolve —
depth-blocked 7→2s approved for 34 days, re-blocked on every compose; an unfired 7→6 deferring its
district's new work for 41 days) are one shape: **a state a district or directive can enter that
no mechanism is responsible for exiting.** Ian routed that class to epic #96. The recurring tell is
a total failure wearing a normal outcome's clothes — 100% gate refusal recorded as an ordinary
`manual_flag_all`, a both-voters-failed extraction recorded as a clean zero.

**Infrastructure was held fixed rather than worked around.** REQ-172 was written for an invariant
that had been real, load-bearing, and undocumented since #174 — a follow-up redo captures only the
delta (Stage 3 seeds from the prior manifest; already-captured URLs are never re-fetched) while
Stage 4 rebuilds in full but local-CPU-only — with two pins for the parts unit tests could not
hold: a source-level wiring pin proving the live capture loop still consults the seen-set, and a
fitness test proving the Stage-4 package can never reach the network. Recorded ahead of Council Lab
work whose branches multiply the redo entry points. Separately, pytest was moved to 9.1.1 with
`pythonpath = .` declared in `pytest.ini` — CI installs unpinned and would have failed collection
on its next run. That work also exposed three tests red on `main` since 2026-08-11 (a fixture's
hardcoded receipt stamp aging past the 30-day trust window) which nothing surfaced because CI has
no scheduled trigger and had not run since 07-30 — fixed, and the detection gap filed as #722.

**The tracker was restructured around what the trace revealed.** Two epics were created for
workstreams that had none: **#723** (REQ-171 — receipts are evidence, gov_db is the transport;
#622/#623/#624/#645, re-homed from #617 because the receipts seam is provenance-agnostic and
leaving them there would make #617 uncloseable exactly as its charter completes) and **#724** (LCT
core — the calculation engine and its inputs, distinct from #128's deferred queue). An
epic-attachment audit over all 100 open issues left five deliberate orphans.

Authority: issues #714-#722 (epics #706/#96/#80/#482) and epics #723/#724; REQ-172 in
`docs/REQUIREMENTS.yaml`; the gov_db/lct_db reads and frozen extraction receipts each issue cites;
the per-district trace in
`docs/technical-notes/production-quality-control-research/2026-08-14-batch00000-27-district-production-trace.md`
(promoted from the scratch-paper whiteboard by Ian, 2026-08-14).

### 2026-08-15 — The "limbo" class closes: gate@8 gets its three arrows, the campaign's three unreachable districts become reachable, and a same-day review round catches a cross-file naming collision before Ian ever saw it

Six PRs landed against the 08-14 trace's findings, in the priority order Ian approved (Tranche 0 —
scheduled CI, #722; Tranche A — #719/#716/#707/#715; Tranche B — the limbo class): **#682**
(gate@8 approval now fires the Stage-9 write directly — no more remembering the CLI; a blocked or
faulted write is stamped `incorporation_blocked` instead of leaving the timeline silent at
`approved`), **#689** (send-back finally routes — 8→1 composes a follow-up batch, 8→6 seeds a
gate@6 draft, both keyed on the approval id so a second click names the existing artifact instead
of minting a duplicate), **#713** (a written district that gains evidence is flagged for
re-review and shown a delta, not re-adjudicated from scratch — gated on REQ-147 staleness rather
than "any new fact," since Fairbanks' 26 new facts moved nothing), **#720** (directives that can
never execute — depth-blocked, depth-dead, or merely stale — auto-resolve instead of re-deriving
the same block on every compose forever), and the campaign's own dead end: **#646** (a district
that is both domain-less and already-attempted had no composer that would take it — West Ada and
Lincoln) and **#718** (a `gt://`-only district read DONE-ENOUGH instead of BLOCKED, so the 5→1
zero-yield composer refused the very districts it exists for — Baldwin, and the same #646 pair).
All three of #620's "unreachable" districts are reachable again; Broward/Cleveland/Essex's
send-backs are now routable instead of requiring a hand-composed batch.

**The review-before-merge practice earned its keep at a new scale.** A max-effort multi-agent
`/code-review` of the six PRs together (Ian's request, run before he looked at any of them) found
**23 real defects** — issues #751-773 — all fixed same day, before the branches were merged. Two
are worth naming as a class: **#755**, where `n_production_sendable` was computed by two
independently-written formulas sharing one name across `server.py` and `release.py`, and they
*disagreed* live on the fix's own flagship example (Baldwin: 0 vs 2) — the same commit telling two
stories about the same district depending which file you read. And **#752/#757/#771**, where the
689 PR's send-back router had quietly reproduced three defect shapes this same review batch had
just fixed elsewhere in the pipeline (a hardcoded `scope="domain"` reproducing #646's dead end, a
falsy-OR fallback reproducing #757's phantom-band risk, a cruder unsatisfied-bands signal instead
of REQ-149's `satisfied` flag) — sibling code paths drifting out of sync with a fix landing one
file over, inside the *same* review batch. Every finding was verified against the live DB (a
rolled-back transaction re-ran the #720 sweeps and named the exact eight pinned zombies; the SQL/
Python sendability formulas were compared across all 116 live districts, zero mismatches after the
fix) before being called fixed.

**Process gap, corrected:** the review-round PRs were opened with `gh pr comment` carrying
"Closes #N" instead of the PR body — GitHub only auto-closes on a body-level closing keyword, so
none of the 23 issues closed on merge. Caught and closed by hand afterward. The lesson: closing
keywords belong in `gh pr create --body`, never a follow-up comment.

Authority: PRs #745-750 (merged) and their six review-round commits; issues #682/#689/#713/#720/
#646/#718 and #751-773 (all closed 2026-08-15); live gov_db/lct_db reads verifying each fix
(rolled-back transactions for the #720 sweeps, a 116-district sendability comparison for #755, a
Playwright pass against real send-back/re-review records for the gate@8 console surfaces).

---

### 2026-08-16/17 — Tranche C's first two steps, and four times the measurement overturned the issue that asked for the work

Two epics' worth of extraction-correctness work landed in three PRs (#774, #792, #813) plus two
review rounds (22 findings, all real). The durable lessons are not in the fixes — they are in how
often *the issue's own diagnosis was wrong*, and in one defect class that recurred four times inside
a single session.

**Identity is a correctness boundary, not a formatting detail (REQ-173).** Consensus groups facts by
school, so "what counts as the same school" decides whether two readings of one school agree or mint
a false disagreement. #693/#721 asked for name-normalization; the measurement said the proposed fix —
group by name alone — would mass-merge real schools across **35 level-collapse districts** (Apopka
Elementary/Middle/High all normalize to `apopka`). So `grade_level` STAYS in the grouping key, and
the fix became a roster-anchored resolution ladder instead: variant spellings meet, 2+ candidates are
never auto-resolved, the roster (not voter agreement) adjudicates a cross-band claim, and an
unmatched name survives as `roster_unmatched` rather than being discarded — because the pipeline's
reach exceeds its roster and refusing those facts would silently narrow coverage.

**A fix can remove a failure's visibility instead of the failure.** #714/#709 added per-model window
accounting: clamp every call to what the model can actually take, refuse pre-flight when it can't.
Correct — and on the Orange shape it converted a *loud* provider 400 into a **successful truncated
reply** that nothing downstream read. `finish_reason` reached a console line and a counter and
nothing else. The clamp was justified as "the 400 shape becomes unrepresentable"; the reason the 400
stopped appearing was that the same event now succeeded quietly. **When a change is justified by a
symptom disappearing, check whether the symptom or the failure was removed.**

**Then the same session did it again, one level up.** #793 added the truncation marker — and gated
its remedies on zero-yield, a gate that catches refusals (zero by construction) and *structurally
misses* truncations, whose normal case is a partial. Baldwin's 355-fact partial was marked and then
ignored: no remedy, no count, district reads DONE-ENOUGH. A marker without a consequence is
decoration.

**Measure an estimator against what it estimates, before "fixing" it.** #794 claimed
`size_max_tokens` should be bounded by roster size. Ground truth (rows a model actually emitted, 918
observations) said both proposed signals were *worse than the status quo in the direction that loses
data*: `roster_school_names_hit` under-predicts 570/918, `nces_school_count` 82/918, today's
`n_times/2` 56/918. And the premise — "a document can never imply more schools than the district
has" — is false: charter networks publish network-wide hubs (KIPP Durham: `nces_school_count = 1`,
50 accepted schools). #794 closed `not planned`.

**Chasing that measurement found the real defect, and falsified our own record.** The under-predicted
cases were not big rosters. Stroudsburg — a **seven-school district** — emitted 420 rows that are
`MCTI` repeated 420 times. Six of 2,340 fact-bearing calls are repetition loops, and **there is no
genuine dropped-tail truncation anywhere in the receipt store.** Everything we had written about
Baldwin and Stroudsburg "losing their tail" was wrong, in four durable artifacts. The correction was
made in place and marked as a correction. The follow-on review then found that claim had been
over-tightened the other way ("every loop IS truncated") — one of the six loops never truncated at
all, and it was the case *only* the new detector could catch: the strongest evidence for the fix,
written up as its weakest.

**#795 was stopped rather than shipped.** A deterministic pre-dispatch hub classifier tops out around
59% recall / 63% precision, misses the three biggest hubs in the corpus, and — under a *better*
matcher — false-positives on the exact document its acceptance criteria require it to reject
(level-stripping collapses a 3-school district's roster to the district's own name, which its policy
book says on every page). Shipping it would have fed routing and chunking decisions a signal wrong
precisely where those decisions matter. The honest half moved to the issue that owns the mechanism.

**The recurring defect class, now four instances in one session:** *a rule implemented twice drifts.*
The absent-`kinds` default resolved one way in the classifier and the opposite way in the remedy
wording (#798); refusal-outranks-truncation was expressed as a `!=` guard in one file and a
set-membership negation in another (#810); a per-record dict comprehension discarded a sibling rep's
marker (#799, the same shape as #785 one subsystem over); and the `ok` gate added in #816 had two
unguarded siblings in the telemetry layer. The countermeasure that keeps working: **put the rule in
the base layer as one function both callers invoke** (`model_families.strongest_kind`), and after
fixing a defect, diff every sibling code path against it — including the ones in the *same* PR.

**Also corrected: the spec ledger silently lost content.** REQ-174 briefly declared `notes:` twice;
YAML keeps only the last duplicate, so an entire rationale block vanished at parse time while the raw
text sat in the file looking fine. Now guarded ledger-wide by a duplicate-key-rejecting loader
(`tests/test_requirements_yaml_hygiene.py`) rather than a spot fix.

Authority: PRs #774/#792/#813 (merged); issues #693/#721/#714/#709/#793/#812 and the review batches
#777-791, #797-811, #814-820 (all closed); corpus measurements over 2,586 stored call records, 918
text-rep observations, and 504 district×record yield pairs, all re-runnable against the live gov_db.

### 2026-08-17/18 — Page scoping is redesigned around an absolute floor, and the measurement falsified the issue that asked for it (again), then falsified two of the session's own measurements

Two PRs (#828, #829) landed page scoping's replacement, closed two issues on measurement, filed
eight new ones, and absorbed two review rounds (#830-#840, eleven findings, all real). The durable
content is three lessons about *how the measurement is done*, and one design principle.

**A peak-relative threshold is the wrong tool for a power-law signal.** #796 asked to widen the
trigger for `harvest_schedule_pages` (keep pages ≥ 50% of the peak page's time count) so non-handbook
PDFs would be scoped too. Measured across 1,640 multi-page PDFs it **loses 26.3% of the corpus's
clock times** — 45% on Memphis, 31% on Orange, the very districts the issue named — because per-page
time counts follow a power law and a threshold set off the peak discards the tail. Widening it would
have made that loss deterministic on the documents it was written to protect. Closed `not planned`
(the ninth issue whose proposed fix measurement overturned). The replacement is an **absolute** floor:
keep a page iff it carries a clock time, or an instructional-minutes declaration (colon-free —
"495 minutes of instruction per day" scores zero clock times), or is page 1, or neighbours a
time-bearing page. Lossless on the time signal by construction (0 / 30,848); drops 43% of pages;
16.0% fewer characters dispatched corpus-wide, 88% on the 166 records it re-routes. Ian's framing was
the key: *"we're trying to ensure we don't send content that is all but certain to have no useful
information"* — that is an absolute question, and the statistical tools for a relative one are limited
when the distribution has no useful centre.

**A silent truncation was hiding under the signal the whole time.** The per-page scan was capped at
60 pages (raised once already, from 15, for this same class of miss). Memphis `00f553bcfc` read as a
3-time document; it has 838, on pp.89-91. Ten records were suppressed by `lf_no_times` purely because
their times lived past the cap. Removed rather than raised, with a guard test. The lesson is the one
already on the board — a cap that hides data is the bug, not the document — but the second-order one
is new: **the measurement that justified this session's own design was itself computed over the
truncated signal**, so "Memphis keeps 60/60 pages, the floor can't help" was the cap talking (at 154
pages it keeps 101). The conclusion held; the stated reason was wrong. Re-run the measurement after
the fix it motivated.

**Two of the session's own measurements were caught wrong by their own re-run.** Pass B, re-run
after the re-ingest, printed `VERDICT: PASS` with 0 sends changed and 0% saved — its baseline read the
live DB, which by then already held the reps the change had written, so it compared the post-state
with itself, and B6's safety block (inside `if changed`) never ran at all: every safety number was 0
because nothing was measured. The §10.11 pattern (a measurement that cannot fail) reappearing inside
the verification of a fix for another instance of it. Fixed both ways — an idempotent baseline, and
`NOTHING MEASURED` instead of `PASS` on an empty sweep. Earlier the same day a raw school-name diff
over-reported (a name on a time-free page cannot contribute a (school, start, end) triple) and a
regex spanning a page join produced a phantom loss. **A verdict that cannot fail is not a verdict;
say so in the script, not in a comment.**

**The implemented-twice-drifts class recurred a fifth time — in the PR whose commit message named
it.** "Which slice does this record get" was a hand-written predicate in ingest and another in
`best_send`, and they disagreed on 43 live records: 35 handbooks whose harvest found no peak had a
floor slice cut and then hidden by a separate `not handbookish` guard (a 1,017-page handbook sent
whole while a lossless 19-page slice sat dead on disk); 8 human-labelled records were refused by one
gate and starved by the other. The P3 byte-identity test only locked the case where the two
predicates happened to agree. Countermeasure applied at its smallest scale: `select_slice()` in the
base layer, ingest cuts what it returns, `best_send` sends only a match — mutual exclusion as a
property of the return type, not of branch order in two files. **A test that locks agreement proves
nothing about the cases where two copies of a rule diverge; the only lock is having one copy.**

**Where the output-ceiling overflow work actually went.** #714's chunking half was never built —
its "or minimally, mark degraded" clause let it close — and Ian correctly remembered it as open. But
council capacity is set by the *weakest member* (voter/voter/judge), and against the real ceilings
the text council (16,384) leaves 4 records with no fitting rep while **0 records exceed the image
council's** (32,768). A 4× text council is constructible from the approved roster. That is an
experiment set, not a scripted rule, so it went to epic #80 (#823-#825) behind a fail-loud overflow
monitor (#822) — the tripwire that says which experiment matters.

Authority: PRs #828/#829 (merged 2026-08-18); issues #796/#795 closed on measurement, #821-#827
filed, #830-#840 the review rounds (closed), #841 the surfaced segment:main disagreement (open);
measurements in `docs/technical-notes/production-quality-control-research/2026-08-17-*` (rerunnable,
read-only, live functions never re-implemented).

### 2026-08-18/19 — Five queued issues land, the live DB is re-ingested, and the re-ingest finds the thing four open issues had in common

Two PRs (#850, #865) closed nine issues and absorbed two review rounds (#851-#860 and #866-#870,
fifteen findings, thirteen real). The durable content is one architectural recognition and one
lesson about rationale as opposed to code.

**A correct fix can ship with a wrong rationale, and the rationale is what the next reader
inherits.** PR #865 was a one-line change — chrome segments (header/footer/nav) may never be the
FIRST send, only ever a signal input. The line was right and stayed. Its justification was wrong
twice, and the review caught both. It said the change affected **4** records; a full replay of
`best_send` over the 3,221 canonical records measures **244** — the "4" counted only the records
where #841's new `n_times` scoring flipped the pick, missing the ~240 where chrome had been winning
the pool's `n_chars` tie-break since REQ-091 (239 of the 244 carry *zero* clock times). All 244 are
reject-decided, which is exactly why nobody had seen it: a reject never serializes its send. The
comment also offered the reassurance that "the footer's evidence is not lost — page.txt, chrome
included, stays in the pool," which is **false on 5 live records**: `0103390:fb71b7cc63`'s footer
carries 12 clock times its own `page.txt` has none of. The corollary now standing: **a fix's
measured blast radius is part of the fix**; ship the rerunnable script, not the recollection
(#870 — `2026-08-19-chrome-first-send-measure.py`, whose C3 fails if a send-decided record ever
depends on chrome-only evidence).

**Stage 3 flattens a live, time-varying, JS-stateful DOM into text snapshots taken at arbitrary
moments — and Stage 5 then re-derives, from filenames, relations Stage 3 knew and discarded.** That
sentence is what #643, #685, #862 and #863 turned out to share, and it became **epic #864**. The
evidence arrived from the re-ingest rather than from reasoning: with segments finally scored,
`best_send` changed on 61 of 3,561 records and **5 send-decided records now send `page.main.txt`** —
on three of them Tier-1 `page.txt` holds **0** clock times while the DOM-main segment holds 26-88.
`page.main.txt` is `body.innerText` minus landmarks and `page.txt` is `body.innerText`, so main is a
subset **by construction** — but only if the two are read at the same instant, and they are not
(`page.txt` at DOM-ready+2.5s, segments at end-of-capture). Corpus-wide the two reads disagree on
**104** records; on **17**, `page.txt` has zero times and main has them (#863). #841's stated premise
("main is a strict subset of page.txt") was false in practice, and the same timing split is why
#862's tidy claim about footers was false. The epic's shape: Stage 3 records the rendered DOM **once**
at end-of-render as generic render facts (#643's sidecar, widened with visibility and landmark
membership), and `page.txt` / `main` / chrome / hidden-panel views become *derivations* Stage 4/5
compute, replay and re-cut without a browser. **Not scheduled** — #642 first, and it must land on
#623's Node seam — but filed so the interim fixes stop painting away from it.

**De-chrome's origin, recovered and put on the record**, because two fixes in a row misstated it:
REQ-091 does **not** screen chrome out. Batch_00001's gate@5 review found a global footer's
"Building Hours" injecting a fake start/end pair and a school-switcher nav inflating
`roster_school_names_hit` into a false `hub`; the answer was *segment, don't strip* — additive files
beside an untouched `page.txt`, with header/footer **kept precisely because real school hours
sometimes live there**. Chrome informs the keyword/category/roster signals; `page.txt`, chrome
included, is what a council reads. So "never send an isolated nav menu" is consistent with REQ-091,
while "chrome is screened out" is not — and the difference is what makes #862's residual gap legible
instead of self-contradictory.

**#826's acceptance criteria were re-specified against measurement, by Ian, rather than met.** The
issue's headline (Memphis 0→27, Broward 3→42, Orange 1→36) was not reproducible: the roster side had
always gone through `norm_school`, so "hits today" described a computation the code has never
performed, and the before/after columns came from two different bases. Measured under the shipped
functions: **23 / 22 / 29**, now the pinned P1. The defect was real — the *document* side was
un-normalized, an asymmetry, not an absence — and its corpus effect is +267 record-hits from
normalization, then 53 single-school districts zeroed by the district-name collision guard. Its P5
tier delta (3 changes, all traced to `roster_school_names_hit` reaching exactly 2, the hub threshold;
0 decision changes) was only answerable **after the fact** because the datetime-stamped per-district
Stage-5 receipts (REQ-164) preserved the prior state. No snapshot had been taken; the receipts are
what made a true before/after possible.

Authority: PRs #850/#865 (merged 2026-08-19); #826/#841/#710/#711/#674/#862 closed, #673 left open
for its render falsifier; #851-#860 and #866-#870 the review rounds (closed; #852/#860/#868 closed
as not-a-bug with pins); #861/#863 filed and open; epic #864 filed, unscheduled. Live governance DB
re-ingested from `main` the same day (`--assert-floor`, recall floor 0.9947 ≥ 0.98).
