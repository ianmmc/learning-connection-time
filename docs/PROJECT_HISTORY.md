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
NCES CCD has **no** SPED-teacher categories and IDEA 618 personnel data is state-level only — **CRDC is the only federal source with district-level SPED teacher counts.** Segmentation was triggered by observed **LCT inflation** (median ~25 min vs. expected ~18): SPED teachers serve smaller caseloads, so counting them inflates apparent connection time. **2017-18** was chosen as the most recent pre-COVID clean biennial (2020-21/2021-22 COVID-tainted; 2023-24 not yet released). The method computes ratios (`sped_teachers/total_teachers`) and applies them proportionally to current CCD, so the ~5-year gap is acceptable because the *ratios* are stable; validated against IDEA 618 Child Count with a **correlation threshold ≥0.70**. Caveat: CRDC includes Section 504 students, IDEA 618 is IDEA-only — a definitional mismatch to keep in mind. *(Source: `SPED_SEGMENTATION_HANDOFF_*`, Jan 2026. The current `docs/SPED_SEGMENTATION_IMPLEMENTATION.md` documents the method; the "why 0.70 / why 2017-18 / inflation trigger" rationale is here.)*

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

---

### Extraction quality benchmarked — no silver bullet (2026-06)
A provider-agnostic benchmark (`infrastructure/scripts/benchmark/`) compared reading methods — plain text/OCR, **table-aware** (pdfplumber), and **vision** (qwen2.5-VL) — × models, scored on grade-band *modal instructional minutes* (±15 min) vs the DB's `human_provided` ground truth. **All approaches plateau ~35–53%.** Plain text on a 7B model (mistral/qwen2.5) is the best *local* approach (~42%); table-aware and vision did **not** beat it on aggregate (table-aware is more *precise* when it hits; vision fixates on early-release columns). **Claude Haiku (cloud) edged the locals (~53%)** — a modest model lift, not a fix. **Lesson: the dominant limiter is input + ground-truth quality** (corrupt source PDFs, HTML schedules not in parseable tables, transposed tables, single-band GT) — *not* the model or reading method. *Direction set:* format-aware reading + **dual-path consensus with human review of disagreements** + better multi-band ground truth. This answers the "is local extraction good enough?" question that paused the project (no — ~42% local, ~50% even with a capable model) and reframes the work from model-selection to input/GT quality + QC. Full record: `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.

### Multi-provider bake-off + discovery architecture (2026-06-13) — *partly supersedes the entry above*
A second, much wider bake-off (the local models had been deleted; cloud APIs now in play) ran ~20 models on the **full 41** districts via two new multi-model conduits (Perplexity Agent API `pplx:`, OpenRouter `openrouter:` in `extractors.py`; native Gemini direct API; Claude via subagents). It overturned the "modest model lever / ~53% ceiling" framing:
- **A capable cloud model ~doubles the best local.** Full-41 leaders: **Gemini 2.5 Flash 68.9%** (cheapest *and* best), Mistral Large 2512 / Qwen3.7-Max 67.6%, DeepSeek V3.2 66.2%, **Mistral Small 24B 63.5% (~$0.05/1M)**, Opus 62.3%; **Granite 4.1 8B 51.4%** (tiny, self-hostable, beats Sonnet). **Cheap wins; bigger ≠ better** (DeepSeek V4-Pro 45.9%, GPT-5.5 < GPT-5.4).
- **Decision:** default extractor = **Gemini 2.5 Flash**; council partner = a cross-family model (**DeepSeek V3.2 / Mistral**); local/self-host = **Granite 4.1 8B**. No per-modality routing — one cheap model generalizes; route by **confidence** (consensus auto-accept) instead.
- **Lesson — input is the ceiling (quantified).** A district×model crosstab + difficulty analysis showed **20% of districts are solved by zero models**, but on tractable inputs (difficulty > 0.70) the top models re-score to **~95–100%**. Failure-mode analysis: **22 of 23 hard inputs already contained the schedule as text** (it was *not* an OCR problem) — they failed on **granularity/noise** (giant multi-school dumps, single-band GT) or were the *wrong page*. So the path past ~69% is **better inputs**, dominated by **per-school targeting** (small, focused, current, single-schedule artifacts).
- **Discovery validated (search, not crawling).** Blind Crawlee crawling fails (probe: glob-targeting matched zero links; broad crawl missed every schedule). **Domain-scoped search** (Perplexity `search_domain_filter`, OpenRouter `site:`, Claude `allowed_domains`) eliminates the wrong-district problem and reaches school subdomains. **Google grounding dropped** (its tool has only `exclude_domains`, no site-restriction). New bottleneck = **capture fidelity** on JS school-CMS pages → tiered capture (text-layer preferred; screenshot+OCR/vision fallback). **Crawlee re-cast as terrain-mapper/one-hop off-site fetcher**, not schedule-finder. Relevance gate stays a deliberately-cheap `pdftotext` sniff; high-fidelity reading (pdfplumber/vision) is the extraction stage's job.
- Requirements added: **REQ-043…053** (discovery, relevance gate, multi-format capture, net-minutes extraction, grade-band assignment, consensus, fail-loud fallback, provenance, budget governor, sampling, grounded-extraction+provider-abstraction). Full record: `docs/technical-notes/EXTRACTION_AND_DISCOVERY_LEARNINGS_2026-06.md`, `docs/EXTRACTION_BENCHMARK_FINDINGS.md` (Updates 1–3).

### Discovery scaled, per-school pipeline built, council + metric pinned (2026-06-20)
The acquisition design was carried from proof-of-concept to a concrete, partly-validated pipeline. Canonical doc: `docs/ACQUISITION_PIPELINE.md` (now the single source of truth; `INSTRUCTIONAL_MINUTES_ACQUISITION_STRATEGY.md` reduced to a decision-record pointer; the old "production-ready" Crawlee+Ollama description was replaced).
- **Discovery scaled to the full 41 (honest hit-rate).** Domain-scoped search + tiered capture (text-layer → screenshot+OCR fallback) found an on-domain schedule page for **37/41 = 90%** (71% on a literally schedule-named URL). Per-tool: OpenRouter `gpt-4o-mini-search` 33/41 (best), Claude WebSearch 32/41, Perplexity 31/41 (worst, hub-skewed). **OCR tier essential** — 20 of 152 relevant pages were image-only (eChalk). Tools are complementary (union 37); **OpenRouter/Claude reach school subdomains, Perplexity skews to the district hub.**
- **Discovery = waves, not council.** Discovery is a recall problem (any tool finding the page wins; capture verifies), so it runs cost-ascending waves with stop-when-found: **Claude WebSearch (Haiku subagent, sunk subscription cost) → OpenRouter `gpt-4o-mini-search` → flag for manual. Perplexity dropped** (lowest coverage, hub-skewed). Extraction stays a *council* (correctness). **Wave 1 can only run from inside the agent** (it spawns a WebSearch subagent), so the pipeline is orchestrated by a **skill** (`.claude/skills/per-school-acquire/`) that glues waves and calls `.py` workers — **agent-in-the-loop, not lights-out** (subscription leverage and unattended operation are mutually exclusive).
- **Extraction council pinned (research-backed).** Deep-research synthesis (`docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md`): diversity > count, **consensus only counts cross-family** (two wrong LLMs agree ~60% vs 33% chance; same-family share blind spots → false consensus), 2–4 models is the sweet spot, a **judge that re-reads the page** beats adding voters, cascades cut cost (FrugalGPT/UCCI). Grok 4.3 & Qwen3.7-Max **removed** (reasoning-token cost 4–70× via real OpenRouter logs; not 100% on difficulty>0.70). Two candidate configs to A/B (decision = measured escalation rate): **Path 1** cheap trio (Mistral Small + Gemini Flash-Lite + Qwen3-235B) + DeepSeek judge; **Path 2** accuracy pair (Mistral Large + Gemini Flash) + DeepSeek judge.
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
- Outcome: `infrastructure/acquisition/discovery/queue_batch.py`, `district_status.py`, and `school_sampling.py` (extended) produced a real, validated `batch_00001.json`; REQ-061 through REQ-067 added with 27→31 real (non-stub) tests; `training_batch.py` archived to `data/archive/training_batch_py-superseded-20260622/`. Full record: `docs/ACQUISITION_PIPELINE.md` (Stage 1 section), `docs/diagrams/acquisition_pipeline_flow.md` (the turn-by-turn decision log), `METHODOLOGY.md` Rules 6–7.
- **`recursive_band_groups()` rewritten a second time, same day: position-based middle/high assignment → per-segment overlap check.** A further CP-A pass over `batch_00001` caught The Bridge Academy (CT) — a single LEVEL=High, 07-12 school — wrongly listed in the **elementary** band, because the first rewrite still assigned middle/high by *position* ("first remaining segment = middle, rest = high"; a lone non-leading segment was unconditionally dropped into elementary too). Tracing the old code by hand surfaced a second real bug of the same shape (Sequoia Union Elementary CA: an 08-08 LEVEL=Middle school pulled into the **high** pool just for coming last after an elem+middle-merged leading segment) and confirmed one case the old rule already handled correctly (Quitman County GA: a PK-08 elementary's middle-coverage does NOT spuriously pull a trailing 09-12 high school into middle — kept as a regression case, not a fix). **Fix:** elementary stays a positional prefix-collapse, but middle/high now check each segment's *own* grade span independently of position. 3 new tests, REQ-066 updated in place; 34 tests passing. Full record: `docs/diagrams/acquisition_pipeline_flow.md`.
- **`district_status.already_attempted()` threshold bug found while trying to re-confirm the fix above in place.** Re-running `queue_batch.py` to regenerate `batch_00001` silently excluded all 12 of its districts — `already_attempted()` fired on *any* registry presence (any stage), even though Stage 1's own design intent (stated in the decision log as "'Through Stage 3' exclusion") was always Stage 3 (Capture)+; none of the 12 had progressed past Stage 1. **Fix:** `ATTEMPTED_THRESHOLD_STAGE = 3` — a district stays eligible for redraw until it's actually been captured, not merely queued or searched. 2 new tests; REQ-062/REQ-067 updated in place; 36 tests passing. Regenerating after both fixes produced a **different** 12 districts, not the same ones — the per-segment fix also changed Rule 7's grade-span-gap exclusion count (985 → 1,439 nationally), shifting the eligible pool itself. The new batch was reviewed in full: every cross-band overlap traced to a genuinely forced case (single-school districts, explicit Jr/Sr- or Elem/Middle-combined school names, one non-clean-partition fallback case structurally identical to Breathitt County, one ambiguous-LEVEL multi-band school) — no Bridge-Academy-style false positive remained. Judged ready to advance to Stage 2.

---

## Part 2 — Hard-Won Lessons (cautionary tales)

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
Walking Stage 1's first real batch with the human reviewing actual output (CP-A) surfaced two genuine bugs — school dilution into the wrong band, and a parser blind to NCES grade code "13" — that the automated grade-span-gap checker (Rule 7) structurally could not have caught: a diluted-but-nonzero candidate pool and a healthy one look identical to a check that only asks "is this band empty." Neither bug would have surfaced from a design review of the *code*; both surfaced from a human looking at a dozen real school names. Second lesson, layered on the first: the initial fix for the dilution bug was scoped to "exactly 2 schools" specifically to avoid disturbing three already-validated districts — but profiling the *full* corpus (not just the cases at hand) showed school-count was never the real dividing line; the actual distinguishing property (do a district's grade spans form a clean ascending partition) reclassified one of those three "already fine" districts as needing the same fix after all. **Takeaway:** prefer a rule's *real* invariant over whatever condition happens to separate the examples in front of you, and check that invariant against the full dataset before trusting a narrow fix is actually narrow. *(Source: this session's Stage 1 build, see entry above; `docs/diagrams/acquisition_pipeline_flow.md` for the turn-by-turn record.)*

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
