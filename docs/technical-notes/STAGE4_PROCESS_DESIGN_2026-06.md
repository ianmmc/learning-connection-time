# Stage 4 — Local processing: design & decision log

> **Status: BUILT + run live (2026-06-23)** against all 12 `batch_00001` districts: 150/150 records
> processed, 0 crashes, 10 `processed_all` + 2 `processed_partial`. Produces, per district,
> `processed.json` + per-record `extracted.txt`/`<tool>.txt`/`raster_p-<N>.png` in each
> `captures/<hash>/` — the local-text layer Stage 5 (Local filtering) consumes.
>
> **What this note is:** for the already-built Stages 1–4 the **code is authoritative**; this note is a
> **narrative of what the code currently does — to inform the console**, not a redesign. §1–§5 describe
> current behavior (verified against the script 2026-06-27); §6 is the historical decision log.
>
> **Code (grimp-confirmed, 2026-06-27):** `stage4_process/process_stage4.py` imports exactly
> `common.district_status` (no LCT DB — ungated middle stage). **Unlike Stages 2/3 it does the real
> extraction work itself** (pdftotext/pdfplumber/camelot/tesseract — all fast local calls, no browser, no
> LLM), so there is no separate worker process. *(Note: promoted from
> `infrastructure/acquisition/discovery/process_stage4.py` to `stage4_process/`; the decision log below
> reflects the original path.)*

**Companions:** `ACQUISITION_PIPELINE.md` §4 (the slim map), `acquisition_pipeline_flow.md` (the visual),
Stage 3's note (upstream `captures.json` + per-`captures/<hash>/` directory contract), Stage 5's note
(downstream — the relevance/tiering layer this stage feeds). `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
(§3 state_event, §11 gates).

---

## 1. Purpose & I/O

Reduce what Stage 7 (the paid extraction council) has to read, and what it costs — spend **free local
compute** so OpenRouter never pays to discover a captured page has no usable text. Stage 4's only question
per representation is *is there machine-readable text here at all* — **not** whether it's about a schedule
(Stage 5's job) and **not** which reader produces the cleanest table (Stage 7's council, a language model,
is better at merged/spanning cells than deterministic code).

- **Input — read, never modify:** each district's `captures.json` (Stage 3's output) + the files in each
  `captures/<hash>/`.
- **Output, written once per district:** `processed.json` (per-record `texts[]`, each entry a
  `{source, usable, text_file, error}` — **completeness, not just success**, is the audit bar) + the actual
  winning/representation text written to files (`extracted.txt`, `<tool>.txt`) and persisted rasterizations
  (`raster_p-<N>.png`) inside each `captures/<hash>/`. `text_file` is a **filename reference**, never inline
  text — resolved against that record's own directory (same convention as `captures.json`'s `files`).
- **Gate:** **none** (Stages 2/3/4 ungated). Registry outcome: `processed_all` / `processed_partial` /
  `no_usable_text_any`. The next human gate is `gate@5`.

---

## 2. The design (settled)

### 2a. Two reconciliation checks, both fail-loud at the same severity
1. **Registry consistency** (same as Stage 2/3): `processed.json` on disk IS "Stage 4 done"; disk-ahead
   reconciles up silently, **registry-ahead-of-disk halts the whole run** (CONTROL FAILURE).
2. **File-existence consistency** (`check_file_consistency`, new — finer-grained than any prior stage): for
   every `ok: true` record in `captures.json`, every filename in its `files` map must exist on disk. A
   mismatch halts the run at the same severity — a manifest claiming a file that isn't there is structural
   breakage (partial write, manual deletion, Stage 3 bug), not a content failure. `ok: false` records
   (`files: {}`) are exempt by design.

### 2b. Run every kept tool against every applicable input, always — no waterfall
This superseded a first-pass "stop at the first usable representation" design: a real test (Longfellow
Elementary's `page.pdf`) showed `pdftotext` surfacing the literal `8:20-School Begins`/`3:20-School Ends`
pair *even though* the `.txt` already looked usable — the short-circuit was discarding real signal. Same
"capture everything, decide downstream" principle as Stage 3's txt+png+pdf, applied one level further.
- **Every PDF** → all four kept methods unconditionally: `pdftotext -layout`, `pdfplumber.extract_tables()`
  (`lines` strategy), `camelot` `stream`, `camelot` `hybrid`. `pdfplumber`/`camelot` output is rendered as
  real **Markdown-table syntax** (header + `---` + rows), kept as `.txt` (the extension is invisible — the
  text is pasted into a chat-completion prompt, never uploaded as a file).
- **Every image** → Tesseract, kept as **three distinctly-named representations** that can disagree:
  `tesseract_screenshot` (`page.png`), `tesseract_image` (a `kind:"image"` download), `tesseract_raster`
  (a fresh `pdftoppm -r 200` rasterization of any PDF — tesseract can't read a PDF directly). Rasters are
  **persisted** (`raster_p-<N>.png`), not ephemeral — a separate OCR input, not a substitute for `page.png`.
- **Existing `.txt`/`.md`/`.csv`** (from Stage 3 or a Drive export) → evaluated against the same bar, no
  special priority, **referenced never rewritten**.
- **Every attempted representation gets an entry** — success, below-bar, or errored — each with its own
  `usable` boolean.

### 2c. The "usable text" bar — deliberately weaker than and separate from Stage 5's relevance check
`is_usable()`: `len ≥ USABLE_MIN_CHARS` (120 — reused from `reading.py`'s `PDF_MIN_TEXT_CHARS`, not a new
number) **and** printable-character ratio `≥ 0.85`. Stage 4 asks "is this recognizable text"; Stage 5 asks
"is this text *about* a schedule" (time-count + keyword). Conflating them would collapse two stages into
one. Validated on Marion ISD's HTML wrapper pages (~2,600 bytes of real text but `text_times: 0`): Stage 4
correctly calls them `usable: true`; Stage 5 is what rejects them as irrelevant.

### 2d. Explicit non-goals (deliberately not built)
- **No escalation to vision.** If `.txt` + both PDF readers + OCR all fail, the record is just
  `usable: false` / `source: "none"`. Vision routing is Stage 6/7's concern.
- **No duplicate-PDF dedup.** Byte-identical PDFs in two `captures/<hash>/` dirs (a shortlink + its
  resolved CDN URL) are reprocessed — a cross-directory content-hash scan is real complexity for negligible
  benefit (cheap local reads). Recorded watch-item.

### 2e. Single registry write
One `record_stage()` write per district at completion. **Redo is versioned** (rename-aside with a UTC
timestamp — a convention retrofitted into `capture_discovery.mjs`'s `captures.json` write in the same round).

---

## 3. The tool roster — resolved by an empirical spike, not from research alone
*(The prior literature survey of the candidate tools — pdfplumber/PyMuPDF/Camelot/img2table/Docling, with
citations — is `STAGE4_PDF_TOOLING_RESEARCH_2026-06.md`. The decision below was the empirical spike, not
that survey.)*

Installed every research-surfaced candidate (`pymupdf`, `camelot-py`, `img2table`, `docling`,
`paddleocr`+`paddlepaddle`, `easyocr`) and ran them against all 150 real captured PDFs. **Kept:**
`pdftotext`, `pdfplumber`-lines, `camelot`-stream, `camelot`-hybrid, `tesseract`. **Dropped on the
evidence:** PyMuPDF, `pdfplumber`-text, `camelot`-network/lattice, both `img2table` modes (found a time in
*zero* of 140 Chromium-`page.pdf` captures — CSS borders don't survive OpenCV rasterization). **Heavy ML
tools (Docling/EasyOCR/PaddleOCR) timed then rejected + uninstalled** — 6-8 hours of compute over 150 PDFs;
the user's standing call: anything needing heavy document understanding goes to the paid vision council
(Stage 7), the same tradeoff that retired local Ollama. A raw time-count is **supporting evidence, not
proof of quality** (a Pittsylvania Student-Handbook PDF false-won on `camelot_hybrid` mis-firing on prose)
— Stage 5's relevance check stays load-bearing even with five tools' input.

## 4. Console surface
Stage 4 is **ungated** — surface as status/observability: per-district outcome, per-record `usable`
representations vs. `no_usable_text` records (and *why* — genuine zero-content capture vs. tool error,
which Stage 4 reports honestly). Feeds straight into the `gate@5` (Filter) review.

**User stories (APGA, seed; migrated 2026-06-27):** as a user, I want **insights into how effective the
PDF text-harvesters and OCR tools are at yielding bell-schedule representations by the end of Stage 5** —
i.e. the measurement-harness pattern extended upstream: attribute each target-labeled record back to its
winning representation's `source` (governance §11f). Same fingerprinted-scorecard discipline as Stage 5.

### 4a. RESUME HERE — building the Stage 4 console (forward notes, 2026-06-29; not built yet)
The Stage 4 console view is the **next** console build. The Stage 2 + 3 views established a reusable
pattern — **copy Stage 3 almost verbatim**; Stage 4 is the simplest case (no external worker, no browser,
no timeouts). Concrete plan for future-me:

- **Infra already in place.** Stage 4's finish hook already upserts the **`processed_doc`** cross-stage
  cache (`common.cache_ingest.cache_processed`, wired in `process_stage4.finish_district`). `list_batches`
  already returns `progress.processed` (furthest_stage ≥ 4). `static/outcomes.js` already has
  `processed_all`/`processed_partial` labels and `progressBadge(progress,"stage4")`. So most of the
  scaffolding the Stage-3 build added is **stage-agnostic and ready**.
- **Build `stage4_process/headless.py`** mirroring `stage3_capture/headless.py`: `run_batch(batch, …)`
  (reconcile → SEQUENTIAL per-district → `dispatched`/`completed`/`failed` events) + `status_for_batch`
  (reads the `processed_doc` cache; self-heal; rollup). **Key difference from Stage 3:** Stage 4 does the
  work *in-process* (pdftotext/pdfplumber/camelot/tesseract — fast local subprocess calls with per-tool
  timeouts), NOT via a separate Node process. So there's **no node-owns-shutdown / no per-district SIGKILL
  budget** to design — a district is processed by a Python function call. (If you ever want a hard
  per-district wall, it'd be a different mechanism; the Stage-3 deadline pattern does NOT transfer.)
- **`server.py`**: add `/api/process/{batch_id}` (status) + `/api/process/{batch_id}/run` (background job),
  copy the `_CAPTURE_JOBS` pattern → `_PROCESS_JOBS`; resolve the batch from the **DB working store**
  (`_capture_batch_from_db` → make a shared `_batch_from_db`), not the receipt.
- **`static/stage4.js`** + the `index.html` selector option + the `gate1.js` switcher hook
  (`if (which==="stage4" && window.initStage4) …`) — copy `stage3.js`: shared `outcomeBadge`/`progressBadge`,
  the **left-pane chip live-sync** to the header during a run, the `.run-anim` button, list re-fetch on
  view-show. The readout: per-district `processed_all`/`processed_partial` outcome + per-record usable vs
  `no_usable_text` (and *why*), and a tool-effectiveness view is the natural Stage-4-specific extra.
- **Per-district status classification** (mirror Stage 3): `awaiting_capture` (no captures.json / nothing
  captured) · `todo` (captured, not processed) · `done` (processed.json) · `failed`. **Terminal states
  flow through:** a `manual_flag_all` (no-link) district never captures and never processes — show it
  `manual_flag_all`, the SAME label, denominator-excluded (capturable/processable = total − no-links).
  A `captured_partial` district processes only its `ok` records (`process_district` already skips
  `ok:false`/`not_attempted`/`not_recovered`), so partials flow naturally.
- **Resilience parity (smaller concern).** Stage 4 writes `processed.json` at end-of-district (like
  Stage 3's old manifest). A crash mid-district leaves it unwritten → reconcile re-runs that district
  (idempotent, fine). It is NOT subprocess-killed the way Stage 3 was, so the orphaning class is far less
  acute — but if you ever batch-kill it, the same **reconstruct-from-disk** philosophy applies (the
  per-record `<tool>.txt` files are on disk). Don't over-build this now; note it and move on.
- **Watch the static-JS no-lint caveat** (a deleted var once broke a sibling view) — diff `static/*.js`
  carefully; `node --check` catches syntax only.

## 5. Open decisions
- None blocking. Tier roster and the always-run model are settled by the spike (§3); the
  duplicate-PDF-dedup and vision-escalation non-goals (§2d) are deliberate, not deferred work.

---

## 6. Decision log (chronological — moved here from the flow diagram, 2026-06-27)

_Preserved verbatim from `acquisition_pipeline_flow.md`'s decision log; `gate@5` was "CP-B" at the time of
writing (governance §11). The original code path was `infrastructure/acquisition/discovery/process_stage4.py`
before the package promotion._

**2026-06-23 — Stage 4 (Local processing) designed, across several feedback rounds, deliberately grounded against a real captured district (`1918690_marion_independent_school_district`) rather than designed in the abstract.** The user's initial proposal (per-district walk, per-file-type passes, OCR png/PDF when no text layer, write outcomes into `captures.json`) was refined through concrete pushback:
- **File-existence consistency check added as a new, finer-grained CONTROL FAILURE**, on top of (not instead of) the existing registry-vs-disk reconciliation Stages 2/3 already use: `captures.json` claiming a file exists when it doesn't (manifest says X, disk doesn't have X) is treated with the same severity as registry-ahead-of-disk — a structural break, not a content failure — and halts the entire run. `ok: false` records (`files: {}` by design) are explicitly exempt from this check, not flagged as inconsistent.
- **"Usable text" deliberately kept weaker than, and separate from, Stage 5's relevance check.** Stage 4 asks "is this recognizable text" (length + printable-character/encoding sanity, 120-char floor reused from `reading.py`'s existing `PDF_MIN_TEXT_CHARS` precedent rather than inventing a new number); Stage 5 asks "is this text about a schedule" (time-count + keyword). Conflating them would collapse the two stages into one. **Validated against Marion ISD's real `aa1d5cfb30`/`d9e387ea42` records** — HTML wrapper pages for the VMS/MHS bell schedule with ~2,600 bytes of genuine `page.txt` content but `text_times: 0` (the actual schedule PDF lives elsewhere, found via the emergent-candidate path). Stage 4 correctly calls these `usable: true`; Stage 5 is what rejects them as irrelevant — confirmed as the intended division of labor, not a gap.
- **PDF tooling question — "why not just always use pdfplumber, since local compute is free?" — answered with a real test, not just citing the existing doc.** Ran both `pdftotext -layout` and `pdfplumber.extract_tables()` against Marion's real VMS bell-schedule PDF (`captures/f67b48e026/original.pdf`): pdfplumber found 6 real tables (this particular PDF has genuine cell borders, likely Word/Excel-generated) with roughly correct grouping; pdftotext also extracted readable content. Both stumbled on the same merged-cell ambiguity (a period spanning two grades' time slot) in different ways — confirms neither tool needs to perfectly resolve table structure, since Stage 7's council (a language model) is the right place to disentangle that, not deterministic code. Resolution: **run both unconditionally, keep the richer result** — same "capture every representation, decide downstream" principle already used for Stage 3's txt+png+pdf. Exact tool roster (whether to add PyMuPDF's `find_tables()` — whitespace/alignment-based, not requiring ruling lines, a candidate for the CSS-grid-PDF case pdfplumber is documented to miss) left **open, pending a dedicated spike** — not installed yet (`fitz`/`camelot` confirmed absent from the environment; `pdfplumber` confirmed present).
- **OCR scope corrected: not "always OCR every captured image."** OCR only runs when `.txt` and the PDF branch both fail to clear the usable-text bar for that record. For `kind: "image"` records specifically it always runs, simply because there's nothing else available to try first — not a blanket rule. An earlier restatement of this in conversation overstated it as "always OCR images"; the user's original framing was already correct. _(Later reversed to unconditional OCR on the spike evidence — see the 2026-06-23 tool-roster entry below.)_
- **Stage 4 does not escalate to vision.** If `.txt`, both PDF readers, and OCR all fail, the record is just `usable: false` / `source: "none"` — full stop. Vision routing is explicitly Stage 6/7's concern (the user: "I can imagine scenarios in Stage 7 where we reach back to the directory to retrieve an image file that hasn't been submitted, but that's something we deal with at that point").
- **Duplicate-PDF dedup deliberately NOT built.** Investigated a real case first: Marion ISD's two emergent-candidate PDF captures (`f67b48e026/original.pdf`, a `5il.co` shortlink; `a8bfb0b149/original.pdf`, its resolved CDN URL) are byte-identical (verified via md5) but live in two different `captures/<hash>/` directories within the same district. Deduping would require a cross-directory content-hash scan before processing any single directory — real added complexity (the user's stated concern: "cautious about... complicating a loop through a defined directory by having to check through a parent directory across all subdirectories") for a benefit that's currently negligible (cheap local reads, one rare occurrence so far). Same posture as Drive Tier 2 — a recorded watch-item, not a built feature.
- **`processed.json`'s `text_file` field is a reference (filename) only, never inline text** — resolved against that record's own `captures/<hash>/` directory, the same convention `captures.json` already uses for `files`. The actual winning text is written to `extracted.txt` in that directory. Clarified explicitly after the user flagged a possible mismatch between this and an earlier "processed.json needs the actual text, not just a verdict" framing — both statements agree once "the actual text" is understood as "produced and saved to a file Stage 5/6/7 can read," not "embedded as a JSON string."
- **Registry update timing confirmed**: once per district, at the conclusion of that district's processing, via `record_stage()` — same API as Stages 1-3, no schema changes. Outcome vocabulary: `processed_all` / `processed_partial` / `no_usable_text_any`.
- **CP-B's placement settled: after Stage 5 (filtering), before Stage 6 (handoff to OpenRouter)** — not right after Stage 3, as earlier doc language had implied. The human reviews legible, *relevant* candidate input right before it becomes a paid council call, not raw captures. `ACQUISITION_PIPELINE.md`'s Stage 2→3 boundary note updated to reflect this.
- Detour agreed before implementation: spike-test PyMuPDF (and possibly other PDF tools) against real captured PDFs already on disk before locking the Stage 4 PDF-reader roster, rather than deciding it from research alone.

**2026-06-23 — the "stop at first usable representation" waterfall was abandoned mid-spike, after a real test proved it throws away signal, not just redundant work.** Pulling Longfellow Elementary's `page.pdf` (a genuine CSS-rendered Chromium PDF, `text_times: 9` — exactly the kind of record that would have short-circuited at `.txt` and never touched the PDF under the original design) showed `pdftotext -layout` cleanly surfacing `8:20-School Begins` / `3:20-School Ends` — the literal gross bell-to-bell pair — even though the already-captured `.txt` looked fine on its own. The same test also showed `pdfplumber` (both `lines` and `text` strategies) garbling the same page (word-chopped fragments, a Private-Use-Area icon-webfont glyph bleeding into the output) — proving the opposite risk too: not every "extra" representation is trustworthy just because it exists. **Resolution: generate every representation from every kept tool, always; defer trust/ranking to Stage 5.** This is consistent with (not a new departure from) the "capture everything, decide downstream" principle already used for Stage 3's txt+png+pdf — just applied one level further, to local processing's own outputs.

**2026-06-23 — PDF/OCR tool roster resolved by installing and running every research-surfaced candidate against all 150 real captured PDFs across `batch_00001`, not by picking from research alone.** Installed `pymupdf`, `camelot-py`, `img2table`, `docling`, `paddleocr`+`paddlepaddle`, `easyocr` alongside the already-present `pdfplumber`/`pdftotext`/`tesseract`. Built `data/benchmark_results/stage4_pdf_tool_spike/run_spike.py` — discovers every PDF under `data/raw/lea-website-captures/*/captures/*/`, runs each candidate, records cheap per-(PDF,tool) metrics (char count, plausible-time count, table count, printable ratio, elapsed seconds, error) to `summary.jsonl`, with raw output saved per-tool alongside the real captures.
- **Heavy ML-model tools (Docling, EasyOCR, PaddleOCR) were timed before any bulk run**: Docling ≈13s (1-page) to 120s (3-page, incl. one-time model download) per PDF; EasyOCR ≈29s/page; PaddleOCR ≈56s/page (steady-state, post-download). At 150 PDFs (many multi-page) running all three would cost 6-8 hours of background compute. User's call, stated directly: "I can't imagine any scenario where I'm going to approve anything in the slow tier as a better tradeoff than the models via API. That's the same tradeoff that took us away from local LLMs." **Killed the in-progress background run** (caught before the heavy tier had even started — only the fast tier, 129/150 PDFs in, was running), **uninstalled all three packages + paddlepaddle**, stripped the corresponding code out of `run_spike.py` entirely (not just disabled), and removed them from `requirements.txt`. This is a closed architectural decision, not a "maybe later" — any input that genuinely needs heavy-model-level document understanding is explicitly routed to the paid vision council (Stage 7) instead, the same tradeoff that already retired local Ollama for this project.
- **Re-ran the fast-only sweep clean** (11 methods × 150 PDFs = 1,650 rows, only 3 graceful errors, 0 crashes): `tesseract` (60.0% hit rate) and `pdftotext` (58.7%) were the most reliable; `camelot` `hybrid` had the richest average finds (11.4 times/hit) when it hit; `pdfplumber` `lines` added genuinely new signal beyond the existing `.txt` baseline on 30/150 PDFs — more than any other tool, despite not being the single strongest performer in absolute terms. `img2table` bordered-table detection found a time in **zero** of the 140 `page.pdf` (Chromium-rendered) captures — empirically confirming the research-predicted weakness (CSS border strokes don't survive OpenCV rasterization). PyMuPDF, `pdfplumber` `text` strategy, Camelot `network`/`lattice`, and both `img2table` modes were dropped on this evidence.
- **Spot-checked the two biggest "wins" by hand before trusting the metric**: Stroudsburg's `camelot_hybrid` win (88→206 times) was real — a clean multi-variant `Period | Start Time | End Time | Length` table the flattened `.txt` had muddled. Pittsylvania's biggest win turned out to be a Student Handbook PDF, not a schedule page at all — `camelot_hybrid` was mis-firing table detection on prose, and the regex was catching incidental digit patterns. Confirms a raw time-count is supporting evidence, not proof of quality — Stage 5's relevance/keyword check is still load-bearing even with five tools' worth of input instead of one.
- **Settled, in the same conversation, that "always run" extends to OCR too** — Tesseract now runs on every available image (existing `page.png` *and* a fresh rasterization of any PDF present) unconditionally, reversing the original "OCR only when nothing else worked" rule. Justified by the same data: Tesseract had the single highest hit rate of any tool (60.0%) and beat the existing baseline on 15/150 PDFs despite usually running on records where other text already existed.
- `ACQUISITION_PIPELINE.md`'s Stage 4 section, the `STAGE4` Mermaid subgraph above, and `REQUIREMENTS.yaml` (REQ-081/082/083 updated in place, REQ-084 added) all updated to reflect the resolved roster and the "always run" model in the same pass as this entry.

**2026-06-23 — Stage 4 built and run live against all 12 real `batch_00001` districts: 150/150 records processed, zero crashes.** `infrastructure/acquisition/discovery/process_stage4.py` mirrors `discover_stage2.py`/`capture_stage3.py`'s reconcile/finish shape, but — unlike Stage 2/3 — does the real extraction work itself rather than delegating to a separate subagent/Node process, since nothing here is risky or non-Python (no browser, no LLM call). Final schema refinements made during implementation, beyond what was documented going in:
- **Tesseract OCR splits into three separately-named representations** (`tesseract_screenshot`, `tesseract_image`, `tesseract_raster`), not one generic `tesseract` entry — they're genuinely different inputs that can disagree, and collapsing them would lose exactly the comparison signal the whole "always run, don't gate" pivot was for.
- **Every attempted representation gets an entry, including failures and below-bar results** — each entry carries its own `usable` boolean and an optional `error` field, not just a record-level rollup. Validated live: 3 of 4 not-usable records across the whole batch were genuine zero-content captures (`n_chars=1`, no tool errors) rather than tool crashes — Stage 4 honestly reports "nothing here," it doesn't paper over a capture problem.
- **Rasterized PDF pages are persisted** (`raster_p-<N>.png`, pdftoppm's own numbering — note the hyphen, the doc originally said `raster_p1.png`), not discarded after OCR, matching every other representation's "keep it inspectable" treatment.
- `capture_discovery.mjs`'s `captures.json` write was retrofitted in the same round to use the same rename-aside-with-UTC-timestamp redo convention `processed.json` now uses — it previously just overwrote in place, a real gap caught while designing Stage 4's own redo behavior.
- Tests: 31 new (orchestration logic against synthetic fixtures, same style as Stage 2/3's tests, **plus** real tool-invocation tests against genuinely generated fixtures — a tiny real PDF via PyMuPDF, a tiny real image via PIL — closing the kind of gap Stage 3's browser-driving logic left open, REQ-079). Full suite: 575 passed, 22 pre-existing skips, 0 regressions.
- Production run result: 10/12 districts `processed_all`, 2 `processed_partial` (Stroudsburg, Pittsylvania) — the 4 genuinely-not-usable records out of 150 are all explainable by already-known patterns (3 Pittsylvania Student Handbook PDFs, 1 Stroudsburg `cross.jsp` cross-reference link), not new bugs.
