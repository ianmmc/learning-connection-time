# Stage 4 — Local processing: present state & decision log

> **Authority:** Stage 4's purpose, I/O, the always-run-every-tool processing model, the tool roster, the
> console + the Stage 4→5 incremental handoff — what the code does today.
> **Audience:** anyone building on or debugging Stage 4; anyone tracing why a representation is/isn't
> usable, or why a district's Stage-4 run halted or quarantined.
> **Companions:** `ACQUISITION_PIPELINE.md` §4 (the slim map + flow diagram), Stage 3's note (upstream
> `captures.json` contract), Stage 5's note (downstream — the relevance/tiering layer this stage feeds).
> `PIPELINE_GOVERNANCE_AND_STATE.md` (§3 state_event, §11/§12 gates + the Stage 4→5 seam).
> **Update this when:** Stage 4's code behavior changes. Design turns and superseded approaches belong in
> §6 (Decision log), not here.

**Status: BUILT + run live**, including the console (status + run trigger + tool-effectiveness readout),
the Stage 4→5 incremental handoff, follow-up-batch redo (reconcile's `redo` kwarg, #174, 2026-07-05), and
the batch-guard/district-guard mutual-exclusion machinery shared with Stage 2/3 (#168, #206). Produces, per
district, `processed.json` + per-record `extracted.txt`/`<tool>.txt`/`raster_p-<N>.png` in each
`captures/<hash>/` — the local-text layer Stage 5 consumes.

**Code:** `stage4_process/process_stage4.py` imports exactly `common.district_status` (no LCT DB — ungated
middle stage). **Unlike Stages 2/3 it does the real extraction work itself** (pdftotext/pdfplumber/
camelot/tesseract — fast local calls, no browser, no LLM), so there is no separate worker process.
`stage4_process/headless.py` is the batch runner the console drives.

---

## 0. Receipt from prior stage / Handoff to next stage

**Receipt from prior stage:** each district's `captures.json` (Stage 3's output) + the files in each
`captures/<hash>/`, read but never modified.

**Handoff to next stage:** `processed.json` + the representation text files are Stage 5's input — but
unlike Stages 1→2→3→4, this handoff is **active**, not passive. When a Stage 4 run resolves a whole batch,
the orchestration layer triggers the **incremental Stage 4→5 ingest** (§4b) automatically — the Stage-5
view has no lag waiting for a manual trigger. This is also **the seam where the batch dissolves**: Stage 5
is district-driven, not batch-driven (governance §12).

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
  **Read-side tolerance (#347/#348):** the console's status/rollup path never trusts `processed.json`'s
  shape blindly — `headless._load_processed(ddir)` is the ONE parse (`[]` on absent/unreadable/non-list),
  and `_winning_from(docs)` filters both a malformed TOP-LEVEL entry (a stray `None`/string instead of a
  dict where a doc-list entry belongs) and a malformed nested `texts[]` entry, so a corrupt or hand-edited
  file degrades to "no usable text found" for that record rather than crashing the batch-status endpoint.
- **Gate:** **none** (Stages 2/3/4 ungated). Registry outcome: `processed_all` / `processed_partial` /
  `no_usable_text_any`. The next human gate is `gate@5`.

---

## 2. The design (settled)

### 2a. Two reconciliation checks — tiered, not equal severity
1. **Registry consistency** (same as Stage 2/3): `processed.json` on disk IS "Stage 4 done"; disk-ahead
   reconciles up silently, **registry-ahead-of-disk halts the whole run** (CONTROL FAILURE) — a registry
   claiming completion the filesystem can't back up signals lost data or a bad migration. **Bypassed by a
   receipted exception (#572):** before raising, `reconcile()` checks `DS.remediation_receipt(did)` — the
   same receipted exception Stage 2/3's reconciles use — and if a decontamination restore point exists for
   that district, the halt is skipped and the district processes fresh instead (the full mechanism:
   `PIPELINE_GOVERNANCE_AND_STATE.md` §11l).
2. **File-existence consistency** (`check_file_consistency`): for every `ok: true` record in
   `captures.json`, every filename in its `files` map must exist on disk. **A mismatch QUARANTINES only
   that district** (`inconsistent`, a `failed` process state_event, retriable) — it no longer halts the
   whole run (fable review issue #78: a single missing screenshot file used to brick every future Stage-4
   run for the batch). The check runs **only on districts about to be processed**, not retroactively on
   already-processed ones. `ok: false` records (`files: {}`) are exempt by design. **A second, independent
   failure mode (#351):** before the `.exists()` check even runs, a `files{}` value that isn't a
   non-empty string is flagged as its own inconsistency (`"captures.json has a non-string files entry
   {fname!r} in {record_dir}"`) — a malformed manifest entry quarantines the district the same way a
   missing file does, rather than reaching the `.exists()` call and raising a type error. `finish_district`
   (the direct `run <id>` CLI path) still raises a district-scoped `InconsistentCapturesError`.

### 2a-i. `reconcile()`'s `redo` parameter — follow-up batches must not no-op on an existing `processed.json`
`reconcile(districts, registry, *, redo=False)` (process_stage4.py:124): normally `done_on_disk` (a
`processed.json` already on disk) means "skip, already done" — the check in §2a above. But for a
**follow-up batch** (`batch.get("batch_type") == "follow-up"`, wired at `headless.py`'s `run_batch`, which
passes `redo=batch.get("batch_type") == "follow-up"` into `reconcile`), that shortcut is wrong: Stage
2/3 have already **union-merged** new discovery/capture results into the district's on-disk
`captures.json`, so an old `processed.json` is now stale — it doesn't reflect the new records the
follow-up run added. With `redo=True`, `done_on_disk` no longer skips the district; it goes back to
`todo`, and `process_district` rebuilds `processed.json` from scratch against the union-merged
`captures.json` (the old file is renamed aside, per §2e's redo-versioning convention). This is an
orthogonal axis from the disk-vs-registry consistency checks above (§2a still applies unchanged once a
district is in `todo`) — `redo` only changes whether an existing `processed.json` counts as "done."
Fixed as issue #174 (2026-07-05, commit 63e16e5): before this fix, a follow-up batch would silently
no-op straight through Stage 2/3/4 whenever a district already had prior-run artifacts on disk, so the
new discovery/capture work a follow-up batch exists to make never got processed — a real, previously
unnoticed bug in the request-loop machinery (#122).

### 2b. Run every kept tool against every applicable input, always — no waterfall
**Malformed `files{}` entries degrade, not crash (#351):** `process_record` filters
`{k: v for k, v in (rec.get("files") or {}).items() if isinstance(v, str) and v}` before touching any
tool — a non-string or empty `files{}` value now silently reads as "that representation is absent"
instead of raising `AttributeError` on the first `.lower()`/path call downstream.

This superseded a first-pass "stop at the first usable representation" design: a real test (Longfellow
Elementary's `page.pdf`) showed `pdftotext` surfacing the literal `8:20-School Begins`/`3:20-School Ends`
pair *even though* the `.txt` already looked usable — the short-circuit was discarding real signal. Same
"capture everything, decide downstream" principle as Stage 3's txt+png+pdf, applied one level further.
- **Every PDF** → all four kept methods unconditionally: `pdftotext -layout`, `pdfplumber.extract_tables()`
  (`lines` strategy), `camelot` `stream`, `camelot` `hybrid`. `pdfplumber`/`camelot` output is rendered as
  real **Markdown-table syntax** (header + `---` + rows), kept as `.txt` (the extension is invisible — the
  text is pasted into a chat-completion prompt, never uploaded as a file). **A now-load-bearing property of
  the `pdftotext` output: it keeps `\f` form-feed page separators** (one per page, page content before its
  `\f`) — the Stage-5 console's bookmark→PDF-page map (#522) splits on them client-side. Pinned by a
  real-toolchain test (`tests/test_stage4_tools.py::TestPdftotextPageSeparators`, skips where gs/poppler
  absent) so a poppler upgrade that changes `\f` emission fails loudly instead of silently mislabeling pages.
- **Every image** → Tesseract, kept as **three distinctly-named representations** that can disagree:
  `tesseract_screenshot` (`page.png`), `tesseract_image` (a `kind:"image"` download), `tesseract_raster`
  (a fresh `pdftoppm -r 200` rasterization of any PDF — tesseract can't read a PDF directly). Rasters are
  **persisted** (`raster_p-<N>.png`), not ephemeral — a separate OCR input, not a substitute for `page.png`.
- **Existing `.txt`/`.md`/`.csv`** (from Stage 3 or a Drive export) → evaluated against the same bar, no
  special priority, **referenced never rewritten**.
- **Every attempted representation gets an entry** — success, below-bar, or errored — each with its own
  `usable` boolean. **Tool exit codes are honored** (fable review issue #32): a nonzero exit with empty
  stdout records `error=f"exit {rc}: {stderr[:120]}"` rather than a silent empty "success" — a crashed
  `pdftotext`/`tesseract` is now distinguishable from a document that genuinely has no text. A nonzero
  exit *with* substantial stdout still counts as success (some tools warn on stderr and exit nonzero while
  emitting perfectly usable text).
- **OCR raster generation is hardened** (fable review issue #45): stale `raster_p*.png` files from a prior
  failed run are cleared before re-rasterizing; `pdftoppm`'s own exit code is checked (nonzero + zero
  pages produced is an error; nonzero + a partial page set proceeds with what rendered); a page cap
  (`OCR_RASTER_PAGE_CAP = 40`) bounds a pathological multi-hundred-page handbook, with per-page error
  tolerance so one bad page doesn't discard the rest of a document's OCR.

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

### 2f. `batch_guard` — refusing to run a stage on a terminal `abandoned` batch
`infrastructure/acquisition/common/batch_guard.py` is a shared guard, deliberately living in `common`
because stage2/3/4 are independent siblings under the import-linter layering contract and may not import
each other — a check shared across stages has to sit in the base layer, using raw SQL by table name
rather than importing any stage module. It has two grains:
- **`assert_runnable(sess, batch_id)`** — batch-grain: SystemExit if `batch_id`'s DB status is
  `abandoned`; a no-op for any other status, including a batch this DB has never seen (a receipt-only dev
  batch stays runnable). Called at the top of `headless.py`'s `run_batch` (headless.py:219).
- **`assert_district_runnable(sess, district_dir)`** — district-grain: reads the district's own
  `discovery.json` for the `batch_id` that produced it, and defers to `assert_runnable` on that batch; a
  dir with no `discovery.json`/no `batch_id` makes no batch claim and stays runnable. Called from
  `process_stage4.py`'s CLI `run --all` (process_stage4.py:466-471, inside `gdb.session_scope()`, checked
  for every district in `todo` before any work starts) and `run <district_id>` (process_stage4.py:487-488).

Both raise `SystemExit`, matching the existing hard-stop convention for control failures (§2a). The
batch-grain guard alone (from issue #168) left Stage 3/4's older per-district legacy CLIs unguarded —
those operate on one on-disk district dir with no batch argument, so they need the district-grain form
instead; issue #206 extended the module with `assert_district_runnable` specifically to close that gap.
What it prevents: running a pipeline stage against a batch that's already been retired (`abandoned`),
which would record discovery/state events and processed results for districts excluded from the
attempted-set the request loop tracks — the #162 double-queue-poison risk (working data reappearing for a
batch the system has already written off).

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
**BUILT — see §4c.**

### 4a. The Stage 4 console — AS BUILT (REQ-111, 2026-06-29)
Built by copying the Stage 3 view; Stage 4 was the simplest case (no external worker, no browser, no
timeouts). What landed (code is authoritative — this records the shape + the decisions):

- **`stage4_process/headless.py`** — `run_batch(batch, …)` (guard → reconcile → SEQUENTIAL per-district →
  `dispatched`/`completed`/`failed` events) + `status_for_batch` (reads the `processed_doc` cache;
  self-heal; rollup) + `_rollup`. **The structural difference from Stage 3: the work is IN-PROCESS** —
  `run_batch` calls `process_stage4.finish_district` directly (pdftotext/pdfplumber/camelot/tesseract are
  fast local subprocess calls), NOT a separate long-lived worker. So there is **no node-owns-shutdown / no
  per-district SIGKILL budget** and **no injectable `_run`** — a district is a Python function call; a
  crash mid-district just leaves `processed.json` unwritten so reconcile re-runs it (idempotent). The
  Stage-3 deadline/partial-manifest pattern deliberately does NOT transfer. `run_batch` opens with
  `BG.assert_runnable(_con, batch_id)` (`batch_guard`, §2f) — refuses to do any work on an `abandoned`
  batch — before reconcile ever runs. `reconcile` itself is called with
  `redo=batch.get("batch_type") == "follow-up"` (§2a-i): a follow-up batch's districts go back to `todo`
  even with an existing `processed.json`, so the union-merged captures.json actually gets (re)processed.
- **`stage2_complete(root)` is a LOCAL helper, not an import of Stage 3.** The status view needs the
  Stage-2-complete universe (discovery + candidates on disk) to classify `awaiting_capture` vs
  `manual_flag_all`, which is what `stage3_capture.find_districts` returns — but importing it broke the
  import-linter independence contract (stages must not import each other). So `headless.stage2_complete`
  re-scans for `discovery.json`+`candidates.json` locally. **Lesson for every future stage view: copy the
  small disk-scan helper, don't reach across stages.**
- **The status view reads the DB working store, never parses captures.json.** Per-district outcome +
  usable/not-usable doc counts come from `processed_doc` (self-healing, like Stage 3's `capture` read).
  captures.json/processed.json get only an `.exists()` stat to separate `awaiting_capture`/`todo`/`done`;
  the *only* disk **parse** is `processed.json` for the **tool-effectiveness panel** (the per-text
  `source` is not in the live cache — only `n_texts`/`usable` per doc are). The actual processing WORK
  (process_stage4) of course reads captures.json + the binaries off disk — that's its input.
- **`server.py`** — `GET /api/process/{batch_id}` (status) + `POST /api/process/{batch_id}/run`
  (background job, `_PROCESS_JOBS`); the batch is resolved from the **DB working store** via the shared
  **`_batch_from_db`** (renamed from `_capture_batch_from_db`; now used by capture + process).
  `process_run` also calls **`_acquire_batch_run(batch_id)`** (defined `server.py:~136`, issue #47) before
  starting the job — the same cross-stage per-batch mutex `capture_run` uses, preventing e.g. a
  concurrent capture-run and process-run from both operating on the same `batch_id`. Unlike `capture_run`,
  `process_run`'s `_work()` closure has no `_run=_tracked_run` injection — there's no Node child process to
  track (Stage 4 has no subprocess worker to babysit, consistent with headless.py's "no injectable `_run`"
  above): it's plain in-process Python, so `run_stage4_with_ingest` is called directly.
- **`static/stage4.js`** + the `index.html` selector option + the `gate1.js` switcher hook
  (`if (which==="stage4" && window.initStage4) …`) — copied `stage3.js` (shared
  `outcomeBadge`/`progressBadge`, left-pane chip live-sync, `.run-anim` button, list re-fetch on
  view-show). Columns: District · Status · Docs · Usable · Not usable, plus the **"Usable representations
  by tool"** panel (the Stage-4-specific extra — the §4 user story). `outcomes.js` gained two badges:
  `no_usable_text_any` (honest "processed, nothing cleared the usable bar" — NOT a failure) and
  `awaiting_capture`.
- **Per-district status:** `awaiting_discovery` · `manual_flag_all` (no-link, terminal, denominator-
  excluded: processable = total − no-links) · `awaiting_capture` (Stage 3 still owes it) · `todo` ·
  `failed` (a process error left no processed.json; retriable) · `done` (→ `processed_all` /
  `processed_partial` / `no_usable_text_any`). A `captured_partial` district processes only its `ok`
  records, so partials flow naturally.
- **Static-JS caveat still applies** (no lint/`no-undef` gate; `node --check` catches syntax only).
  A reverse-the-event-feed pass (`slice(-12).reverse()` → newest-first) landed across stage 2/3/4 here too.

### 4b. The Stage 4 → Stage 5 handoff — incremental, batch-scoped (REQ-111, 2026-06-29)
**The seam where the batch hands off to Stage 5.** When a Stage 4 process run **resolves the whole batch**
(every district processed or terminally no-link), the server's `_ingest_stage5_if_complete` runs the
**incremental** Stage-5 ingest for just that batch and records the transition — so switching to the Stage 5
view is instant, with no full-corpus rebuild and no perceived lag (the design goal).

- **`build_signals.ingest_batch(district_ids)`** (new, beside the unchanged full `ingest()`): ensures the
  signal-table schema (CREATE IF NOT EXISTS — never drops) and re-ingests ONLY the batch's districts via a
  per-district DELETE+INSERT (`delete_district_signal_rows` + the extracted `ingest_district`), resolving
  dirs in O(batch) (`root.glob("<did>_*")`). **Prior batches are untouched; cost is proportional to the
  batch, not the corpus** — this is why the full DROP+rebuild was unacceptable as the routine handoff (it
  would re-relocate and *grow* the very lag we're killing). PRECIOUS `label`/`cluster_split` survive
  (rec_key is stable; the delete never touches them). Then it regenerates `filtered.json` for just those
  districts.
- **Trigger placement = the orchestration layer, not Stage 4.** `_ingest_stage5_if_complete` lives in
  `process_governance/server.py` (the app layer that may import every stage); `stage4_process` importing
  `stage5_filter` would break the independence contract. It fires only when `run_batch` did work
  (`todo>0`) AND `status_for_batch` rollup shows `resolved == total`. **Best-effort:** an ingest hiccup is
  emitted as a `stage5_ingest_failed` event and logged, but never fails the (already-durable) Stage-4 job.
- **The transition is recorded as a Stage-5 progression event per district** (`stage=5`,
  `stage_name="filter"`, `outcome="ingested"`, `actor="auto:stage5"`) → `furthest_stage` advances to 5
  ("done through Stage 4 / in Stage 5"), and a `stage5_ingested` job event surfaces it in the feed.
- **Still manual elsewhere:** the full `python3 -m …stage5_filter.build_signals` remains the all-districts
  rebuild (schema changes, recovery). The console handoff is the batch-scoped fast path.

### 4c. Tool-effectiveness attribution — AS BUILT (#118, 2026-07-20)
The §4 user story is live: `process_governance/attribution.py`'s `stage4_attribution()` answers "which
processing tool actually yields bell-schedule representations." For every human-labeled TARGET record, it
takes `release.decide()`'s winning send-files and maps each one back to that representation row's `source`
(`pdftotext`, `camelot_stream`, `camelot_hybrid`, `pdfplumber_lines`, `tesseract_screenshot`/
`tesseract_image`/`tesseract_raster`, …) — a per-source **win rate** over target records — alongside a
**corpus-wide usable-rate per source** (`n_reps`/`n_usable`/`usable_rate` from the `representation` table)
for context, independent of labeling. Served at `GET /api/attribution`, rendered client-side by the shared
`attributionPanel()` (`static/outcomes.js`, lazy-fetched on first expand) — mounted on both `stage2.js` and
`stage4.js`, the same panel surfacing Stage 2's discovery-tool attribution alongside Stage 4's. Same
fingerprinted-scorecard discipline as Stage 5 (`write_card()` persists a receipt beside the harness
scorecards).

## 5. Open decisions
- None blocking. Tool roster and the always-run model are settled by the spike (§3); the
  duplicate-PDF-dedup and vision-escalation non-goals (§2d) are deliberate, not deferred work. The Stage
  4→5 handoff (§4b) is built and the Stage-5 console rework it feeds is also done (district-driven,
  attention-first — see `STAGE5_FILTER_DESIGN.md`).

---

## 6. Decision log (chronological — moved here from the flow diagram, 2026-06-27)

_Preserved verbatim from the retired flow diagram's decision log (now in `ACQUISITION_PIPELINE.md`); `gate@5` was "CP-B" at the time of
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

**2026-07-02 — CONTROL-FAILURE blast radius tiered; tool exit codes honored; OCR hardened (fable review
issues #78, #32, #45).** Adversarial review found three real gaps: (1) the file-existence consistency
check (§2a) treated a single district's structural inconsistency as a whole-run halt, and re-checked
already-processed districts on every future run — a district with one bad manifest entry permanently
bricked the batch's Stage-4 runs; fixed by quarantining just that district and scoping the check to
about-to-be-processed districts only. (2) `_run()` returned subprocess stdout regardless of exit code, so
a crashed tool recorded a non-errored empty representation, indistinguishable from "no text in this
document"; fixed to check the return code. (3) `run_tesseract_multi`/`rasterize` were unbounded (a
100-page handbook meant 100 sequential 60s-timeout calls) and all-or-nothing (one page's timeout discarded
every prior page's OCR), and ignored `pdftoppm`'s exit code, silently reusing stale rasters from a failed
prior run; fixed with a page cap, per-page tolerance, and a returncode check + stale-raster clear. See §2a
and §2b for the present-state description.

**2026-07-18/19 — epic #111 Phase 1 correctness sweep (PR #552, #347/#348/#351): manifest-entry
robustness closes on both the write side and the read side.** #347/#348 consolidated the console's
processed.json consumers (`_disk_doc_count`, `winning_sources`) onto one shared parse
(`_load_processed`/`_winning_from`), which tolerates a malformed TOP-LEVEL list entry — not just a
malformed nested `texts[]` entry, the only shape the prior code guarded against — so a corrupt or
hand-edited `processed.json` degrades to "no usable text" for that record instead of a 500 on the
batch-status endpoint. #351 closed the write-side counterpart in `check_file_consistency`/
`process_record`: a non-string/empty `files{}` value is now its own detected inconsistency (quarantining
the district, same as a missing file) rather than reaching an `.exists()` call or a `.lower()` call on
the wrong type and raising. See §1, §2a, and §2b for the present-state description.

**2026-07-05 — follow-up-batch redo (#174).** A follow-up batch's districts were silently skipping Stage
2/3/4 entirely whenever prior-run artifacts already existed on disk — `processed.json` present read as
"already done," so the new discovery/capture work the follow-up batch exists to process never actually
got processed. Fixed by adding `reconcile()`'s `redo` keyword, wired from `headless.py`'s
`batch.get("batch_type") == "follow-up"`: a follow-up batch's districts go back to `todo` regardless of an
existing `processed.json`, and `process_district` rebuilds it from the union-merged `captures.json`. See
§2a-i.

**2026-07-05/07-06 — batch-runnability guard added, then extended to the per-district legacy CLIs
(#168, #206).** The headless CLI runners loaded batches straight from the on-disk receipt, which carries
no status, so they had no way to refuse a terminal `abandoned` batch — risking the #162
double-queue-poison failure mode. #168 added `common/batch_guard.assert_runnable` (batch-grain), wired
into `headless.py`'s `run_batch`. The #206 review found this left Stage 3/4's older per-district CLIs
(`run --all` / `run <district_id>`, which take a district dir, not a batch_id) unguarded; extended the
module with the district-grain `assert_district_runnable`, which resolves the producing batch via the
district's own `discovery.json`. See §2f.

**2026-07-19 — #518 `time_blind` fidelity flag (epic #111 Phase 4).** `process_record` now flags the
one SILENT fidelity shape Stage 4 can see: a schedule-promising URL (`SCHED_URL_RE` over
`url`/`final_url` — capture metadata, deliberately NOT the text, preserving the is_usable docstring's
Stage-4/5 aboutness boundary) whose usable reps all recovered zero clock times →
`fidelity: ["time_blind"]` on the processed record, projected to `processed_doc.fidelity_json`
(cache_ingest). Unusable/errored records are not flagged — their failure is already visible via
`usable`. Sized by the 2026-07-19 survey: 61 in-corpus records (CMS document-viewer pages whose
linked PDF was never fetched, soft-404s, login walls). Tests: TestTimeBlindFidelity.
