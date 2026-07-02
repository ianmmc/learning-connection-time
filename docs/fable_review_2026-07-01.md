# Fable Review — Findings & Recommendations (2026-07-01)

> **⚑ TRACKING MOVED TO GITHUB ISSUES (2026-07-01).** Every finding below is filed as an issue —
> [`label:fable-review-2026-07`](https://github.com/ianmmc/learning-connection-time/issues?q=label%3Afable-review-2026-07)
> (75 issues, #4–#78; `sev:*` severity + `area:*` labels; `stage7-prep` marks Stage 7–9 blockers;
> findings fixed during the review session were created closed). **This document is the frozen
> narrative snapshot — don't track completion here; the issues are the live status.**

> A fresh-eyes review of the whole project — the LCT-core (federal/state ingest + statutory
> calculations) **and** the acquisition pipeline (Stages 1–6 as built) — plus concrete design
> proposals for Stages 7/8/9. Conducted by Claude Fable 5 with four parallel code-sweep agents;
> every Critical/Major finding below was verified against source (file:line quoted).
>
> **Verification evidence at review time:** `lint-imports` 3 kept / 0 broken ·
> `pytest -q -m "not integration"` → **677 passed, 20 skipped** · Docker + `pip install -e .` clean.
> The suite being green while this many defects exist is itself a finding — see §4.4
> (test-coverage gaps): several passing suites test mocks defined inside the test file, not the
> production code.

---

## 1. Executive summary — the ten findings that matter most

| # | Finding | Where | Why it matters |
|---|---|---|---|
| 1 ✅ | **Label save wipes `flags_json`** — active data loss during Ian's current re-tagging | `process_governance/server.py:140` | 31 labels carry flags in the DB right now; each re-save destroys them. 9 `duplicate` flags have no facet equivalent — genuinely lost (git-recoverable today). |
| 2 ✅ | **`docs/REQUIREMENTS.yaml` is not valid YAML** | line 2653 (REQ-114) | The requirements ledger — the project's context-window-survival mechanism — can't be machine-read; `/requirements` tooling silently broken. |
| 3 | **Temporal-validation trigger is inert** — REQ-026's DB enforcement never fires | `migrations/008:215-222` vs `models.py` | Trigger reads `*_source_year` columns the ORM write path never populates (not even mapped in `LCTCalculation`); every row passes. COVID/3-year rules are aspirational at the DB layer. |
| 4 | **Elementary LCT uses the high-school bell schedule** | `calculate_lct_variants.py:518-519,551` | One `get_instructional_minutes(..., "high")` call feeds `lct_elementary`, `lct_secondary`, and all base scopes. Elementary days are 30–60 min shorter → systematic inflation wherever a real HS schedule exists. |
| 5 | **NCES/SEA precedence is inverted AND incoherent** | `migrations/merge_sea_precedence.py:287-323` | SEA unconditionally overwrites NCES within the 3-year window (even *older* SEA, via `abs()`); then `calculate_scopes()` (`models.py:855-859`) recomputes `teachers_k12` from stale NCES per-level fields — `primary_source` says SEA while every scope is NCES. The precedence test suite tests a mock defined inside the test file. |
| 6 | **Phantom `page.png` on screenshot timeout permanently bricks Stage-4 runs** | `capture_discovery.mjs:483-503` + `process_stage4.py:94-119` | Screenshot failure swallowed but `rec.files.png` set unconditionally (the pdf path does it right); Stage 4's `check_file_consistency` then raises a run-halting CONTROL FAILURE on *every* future run — it never self-heals. |
| 7 | **Bright Data → Serper failover doesn't fire on outages** | `stage2_discover/headless.py:222-231`, `common/discover.py:139-148` | Failover catches only `SystemExit` (401/402/429). Timeouts, 5xx, connection errors — the actual outage case the failover exists for — degrade every school to zero URLs, indistinguishable from "nothing found". |
| 8 | **Stage-9 landing zone will reject the pipeline's output as-is** | `models.py:257-269`, `queries.py:233-247`, `verification.py:585` | `chk_method` has no council value; no `minutes_basis` column (gross written into a net-documented column); the time validator requires AM/PM while the pipeline emits 24-hour HH:MM → every Stage-9 insert through `add_bell_schedule` raises. Migration needed **before** Stage 9 (§5.4). |
| 9 | **`net` minutes script still live** — violates REQ-055 if ever run | `enrich/calculate_minutes.py:165-172` | Deducts lunch when day > 330 min; writes net values into the same column as gross under `automated_enrichment`. |
| 10 | **Wave provenance mislabeled in candidates.json** | `discover_stage2.py:235` | SERP results tagged `"claude"`, Claude results tagged `"openrouter"` — silently corrupting the discovery-attribution analysis (`candidate_tools_json`) the measurement discipline depends on, and cheap to fix now vs. backfill later. |

**Overall shape:** the acquisition pipeline's architecture is genuinely strong — the
DB-as-working-store/JSON-as-receipt split, the reconcile/fail-loud pattern, the pure-core/app-shell
Stage-6 layering, and the measurement-before-tuning discipline all held up under adversarial
reading. The bugs cluster in three places: (a) **seams where an architecture change outran a
consumer** (v2.1 facets vs. the flags readers; the SERP cascade vs. wave provenance labels), (b)
**the LCT-core, where enforcement of documented rules was built but never wired into the live
read/write paths**, and (c) **error-path handling** (failover triggers, subprocess exit codes,
partial-run manifests).

---

## 2. Bugs — Urgent (act before more data flows)

### 2.1 v2.1 label save wipes `flags_json` (active during the current re-tagging)
`server.py:139-143` writes `"flags_json": json.dumps(payload.get("flags", []))` on every label
save — but the v2.1 UI (`static/app.js:587-596`) posts only `{primary_label, facets, note, status}`;
no `flags` key exists anywhere in app.js. The cluster-cascade save (`server.py:149-153`) does the
same. Verified in the governance DB: **31 labels currently carry non-empty `flags_json`**
(9 `duplicate` · 12 `building_hours_visible` · 6 `buried_in_long_doc` · 4 `target_image_only`).

Severity calibration (verified against `build_signals.py:714-736`): the v2.1 migration already
folded three flag types into facets, so for those the flags column is legacy. But:
- **`duplicate` deliberately stays a flag** ("a dedup mechanism, not a content facet") — those 9
  are genuinely destroyed on re-save; and
- `release.best_send` (`release.py:79`) still routes image reps off the **flag**
  `target_image_only` (see 2.2) — a wiped flag silently drops those 4 records out of vision routing.

*Fix direction:* in `save_label`, only overwrite `flags_json` when the payload contains a `flags`
key — or finish the flags→facets convergence and delete the flags read entirely (preferred; see
§4.1 "three overlapping label stores"). Pre-wipe values recoverable from `labels.json` git history.

### 2.2 `release.best_send` keys image routing on the retired flag, not the v2.1 facet
`release.py:79`: `if ("target_image_only" in flags or signals.get("visual_text_gap")) and images:`.
v2.1 moved this judgment to `facets["needs_vision"]`; the UI writes only the facet, and
`load_district_records` (`release.py:196-197`) doesn't even select `facets_json`. A human ticking
"needs vision" on a newly-tagged record does **not** route it to the image rep. *Fix:* read
`facets_json` in the release descent; treat `needs_vision == "yes"` as the trigger.

### 2.3 `ingest_batch` can truncate the labels.json backup
`build_signals.py:1068-1093`: the full `ingest()` runs `import_labels()` before `export_labels()`;
`ingest_batch` runs `import_splits()` then `export_labels()` with **no `import_labels()`**. On a
fresh/wiped governance DB, the first Stage-4→5 incremental handoff creates only unlabeled rows and
then atomically overwrites `labels.json` with `[]`. Git history is the only recovery. *Fix:* mirror
the full path — `import_labels(sess)` before the export (a no-op on a healthy DB).

---

## 3. Bugs — Critical & Major

### 3.1 LCT-core (federal/state ingest + statutory calculations)

The systemic pattern: **the rule was built, then the write path moved.** COVID exclusion, the
3-year window, and NCES-over-SEA precedence each exist as documentation, helper functions, or
triggers — none is wired into the live read/write paths.

**CRITICAL**
- **C-1. Temporal trigger inert** (exec summary #3). `migrations/008:215-222` reads
  `NEW.enrollment_source_year / staff_source_year / bell_schedule_source_year`; the ORM
  `LCTCalculation` doesn't map those columns (verified — zero grep hits in `models.py` /
  `calculate_lct_variants.py`), so span is always NULL → `within_3year_window` always TRUE.
  *Fix:* point the trigger at columns the write path populates (`instructional_minutes_year`,
  `staff_year`, + add an enrollment-year column), and add the 008 columns to `models.py`.
- **C-2. No production COVID/span enforcement.** `calculate_year_span`
  (`calculate_lct_variants.py:413`) is never called; `get_instructional_minutes` (:153-171) takes
  the most recent bell year with no COVID filter; `sea_import_utils.is_covid_year`/
  `validate_data_year` (:463-493) have **zero call sites**; `fetch_nces_ccd.py:55` actively offers
  2022-23 for download; `get_most_recent_ca_sped` accepts the advertised 2022-23 CA SPED data
  unfiltered. Critical Rules #2/#4 are currently aspirational.
- **C-3. Elementary uses high-school minutes** (exec summary #4). `calculate_lct_variants.py:518-519`
  fetches minutes once with `"high"`; :551 feeds it to `lct_elementary`. *Fix:* per-band fetch —
  the precedence helper already supports `grade_level="elementary"`.
- **C-4. SEA merge inverted + internally incoherent** (exec summary #5). Also: `abs()` span means
  *older* SEA (incl. COVID years) overwrites newer NCES; suppressed SEA values become 0 (see M-3)
  and then win the merge.
- **C-5. `calculate_minutes.py` deducts lunch** (exec summary #9) — retire or convert to gross +
  240–510 gate before any reuse.
- **C-6. Full rebuild silently wipes the crosswalk.** `reset_database.py:34-72` +
  `rebuild_database.py:129`: `TRUNCATE districts CASCADE` cascades into
  `state_district_crosswalk` (FK `ON DELETE CASCADE`, `007:18`) — absent from `TRUNCATION_ORDER`,
  never counted, never verified, despite being "the single source of truth for all state mappings".
  Phase 6 re-imports only `manual_import_files/` at hardcoded 2025-26; `automated_enrichment` rows
  and other-year human entries are permanently gone.
- **C-7. Texas import: same positional column for total and G12 enrollment.**
  `import_texas_tapr_data.py:226/242` both read `row.iloc[27]` (`DPETALLC` vs `DPETG12C` comments) —
  one is wrong; if total = G12 headcount, every TX LCT denominator is catastrophically off. All TX
  fields are `iloc`-positional (a column reorder next year shifts everything silently). *Fix:* read
  by column name, `dtype=str`.

**MAJOR**
- **M-1. NCES-ID normalization goes the wrong direction post-015.** `queries.py:28,111,203` does
  `nces_id.lstrip("0")` against a DB that migration 015 zero-padded to 7 digits — unpadded input
  returns None. *Fix:* `zfill(7)`.
- **M-2. Three-way schema drift; ledger can lie.** `EnrichmentAttempt` lacks
  `skip_future_attempts` (required by raw SQL at `queries.py:837` → UndefinedColumn on any
  `init_db()`-created DB); `models.py` omits the 008 temporal columns; `schema.sql` predates
  migrations 002–017. The ten `apply_*.py` scripts never insert into `schema_migrations`; two of
  them create schema in no numbered file at all; `017` re-apply fails (no `IF EXISTS` on the PK
  drop). *Fix:* regenerate `schema.sql` from `pg_dump --schema-only` or retire it; make `apply_*`
  scripts write the ledger.
- **M-3. Suppression sentinels coerced to 0.** `import_florida_data.py:202-204`
  (`safe_float(...) or 0`), `import_new_york_data.py:262-264,339,403`: a `'*'`-masked teacher count
  becomes a stored 0 — which then wins the SEA merge (C-4). `SUPPRESSED_VALUES` lacks numeric
  sentinels (TAPR `-1` imports as negative FTE).
- **M-4. Crosswalk ID-format bugs silently drop districts.** IL: numeric RCDTS loses leading zeros
  for regions 01–09 (`import_illinois_data.py:196`); MI: `str(safe_int(DCODE))` strips zeros that
  the crosswalk stores padded; MA: the converter returns `'0000'` for its own documented example.
  *Fix:* `dtype=str` + canonical per-state zfill.
- **M-5. Year handling is the systemic weakness.** ≥5 different "current year" literals across
  defaults; TX/CA `--year` flags accepted but paths hardcoded; MA labels 2024-25 FTE as 2025-26
  (`import_massachusetts_data.py:53/57/300`); `verify_enrichment.py:66` defaults to 2024-25 while
  the import paths default 2025-26 (the mandated post-enrichment verification checks the wrong
  year); `get_instructional_minutes` fabricates `"2023-24"` as the year of statutory/default
  minutes (:181,184). *Fix:* one shared `CURRENT_YEAR` constant module.
- **M-6. Blended-mode idempotency rests on a table wipe.** `calculate_lct_variants.py:1160-1183`
  writes `grade_level=None` rows (NULLs distinct in Postgres → `uq_lct_calculation_v2` never
  fires); idempotency comes only from `clear_lct_calculations` (:1393) wiping the whole table —
  which also makes `calculation_runs` lineage cosmetic. Also `--incremental` is parsed but unused
  (:1292), and `round(lct_value, 2)` happens before the DB write, violating rounding-at-export.
- **M-7. Divergent bell-schedule writers.** `queries.add_bell_schedule` (validates, upserts, logs
  lineage) vs. three script-local raw-insert paths with different validation and duplicate
  semantics. The `add_bell_schedule` update path (:233-247) overwrites unspecified fields with
  None. Fuzzy district matching (`import_manual_bell_schedules.py:298-315`:
  `ilike(f'{first_word}%')` + `.first()`, no ORDER BY) can attach a schedule to the wrong
  "Washington…" district at `method='human_provided', confidence='high'` — the system's
  highest-trust label.
- **M-8. Two LCT write paths, one column, two meanings** (PROJECT_HISTORY Part-5 flag #21,
  confirmed live). `queries.calculate_and_store_lct` writes `staff_scope='teachers_only'` rows
  using the broader `instructional_staff` aggregate, and its `data_tier` means
  "1 = human_provided" while `calculate_lct_variants.get_data_tier` means "1 = bell schedule for
  requested band". Same column, incompatible semantics depending on writer.
- **M-9. Dead-but-armed Crawlee/Ollama-era scripts.** `enrich/run_batch_pipeline.py:140-151`
  deletes ALL bell rows for a district (every year/method, incl. human_provided) before re-import
  from the retired `:8000` Ollama API; `retry_failed_districts.py`, `ollama_selector`,
  `regex_extract_times` (bare hour < 7 assumed PM → a 6:45 AM start becomes 18:45),
  `import_bell_schedules_from_pdfs` (crashes on pre-schema field names). *Fix:* archive sweep —
  this removes real risk, not just clutter.

### 3.2 Acquisition Stages 1–4

**CRITICAL**
- **C-8. Phantom `files.png` bricks Stage 4** (exec summary #6, verified in source). The screenshot
  `withTimeout(...).catch(() => {})` swallows the failure but `rec.files.png = 'page.png'` is set
  unconditionally (`capture_discovery.mjs:483-503`) — the adjacent `page.pdf()` does it correctly
  in `.then()`. Stage 4's `check_file_consistency` (`process_stage4.py:94-110`) raises
  `SystemExit("CONTROL FAILURE …")` and `reconcile` (:117-119) runs it over **every** district
  including already-processed ones — one slow page bricks the batch's Stage-4 runs forever (the
  bad manifest lives in write-once `data/raw/`). *Fix:* mirror the pdf pattern; and tier the
  blast radius — a missing screenshot is a per-record degradation, not a run-halting control
  failure (see §4.2).

**MAJOR**
- **M-10. Failover doesn't fire on outages** (exec summary #7). `brightdata_search` raises
  `SystemExit` only on 401/402/429 (`discover.py:139-141`); network errors / 5xx /
  "zone returned non-JSON" propagate as plain exceptions that `run_wave1`
  (`discover_stage2.py:180-183`) swallows into `urls = []`. *Fix:* fail over on
  `requests.RequestException`/`RuntimeError`/5xx too; also split 429 (retriable, back off) from
  401/402 (halt) — today a transient Serper rate-limit halts the whole run
  (`BILLING_AUTH_STATUS_CODES = {401, 402, 429}`, `discover.py:72`).
- **M-11. Wave provenance mislabeled** (exec summary #10). `discover_stage2.py:235` still tags
  `("claude", wave1_gated)` / `("openrouter", wave2_gated)` from the pre-SERP architecture →
  `candidate.tools_json` → Stage-5 `candidate_tools_json` all wrong. Cheap now, expensive to
  backfill after more batches.
- **M-12. Secrets loaded CWD-relative.** `common/discover.py:50`
  `SECRETS_FILE = Path("config/secrets.local.json")` — load-bearing for the live Stage-2
  providers, running in the console server's background thread. Launched off repo-root:
  `Bearer None` → 401 → SystemExit → failover → Serper `X-API-KEY: None` raises → all schools
  degrade to zero URLs. The exact bug class `paths.py` (REQ-087) was written to kill; the stage3/4
  CLI `RAW_DIR` defaults (`capture_stage3.py:32`, `process_stage4.py:48`) are the same class.
  *Fix:* anchor to `paths.REPO_ROOT`.
- **M-13. Stage-4 `_run` ignores exit codes.** `process_stage4.py:143-145` returns
  `p.stdout or ""` — a crashed `pdftotext`/`tesseract` records a non-errored empty representation
  and writes an empty `<tool>.txt` into the write-once dir. "Tool crashed" and "no text in
  document" are conflated in `processed.json`, the tool-effectiveness readout, and eventually
  Stage 7's inputs. *Fix:* check `returncode`, record `error=f"exit {rc}: {stderr[:120]}"`.
- **M-14. Cross-stage DB cache has no deletion story.** `common/cache_ingest.py` is UPSERT-only; a
  deliberate re-discovery/re-capture leaves removed URLs' rows in `candidate`/`capture`/
  `processed_doc` forever. Counts drift now; once Stages 7–9 read these tables, ghosts become
  paid-call inputs. *Fix:* per-district `DELETE` before each district's upserts (ingest is already
  per-district + transactional).
- **M-15. Suffix matching without dot boundary.** `discover.py:37-39` `h.endswith(n)`: a district
  at `halifax.com` is rejected as news (`x.com`); `evilschoolwires.com` matches CMS_HOSTS. Node
  side `capture_discovery.mjs:127` has a third clause (`host.endsWith(cms)`) that defeats its own
  dot-boundary check. *Fix:* `h == n or h.endswith("." + n)` in both languages.
- **M-16. One task exception aborts all Node manifests.** `capture_discovery.mjs:400-408`: the
  per-task try/catch excludes the preamble (`mkdirSync`, hash) and push; a throw there rejects
  `Promise.all` (:559) → no `captures.json` written for any district in the run (violates the
  node-owns-shutdown principle). *Fix:* wrap the whole task body; `Promise.allSettled` + write
  manifests in `finally`.

**MINOR (stages 1–4, condensed)** — full detail preserved from the sweep:
`school_sampling.py:172-176` fast-path filename slice bug (`year[7:9]` → `""`; glob fallback
always taken; bare `StopIteration` on empty dir) · `run_wave2` default is the retired
`openrouter_search` (`discover_stage2.py:192`, reachable via the CLI `finish` subcommand) ·
reconstructed Drive exports keyed `"file"` not `"bin"` so Stage 4 skips them
(`capture_stage3.py:145-148`) · Python/Node URL-hash normalization mismatch breaks `reconstruct`
(`capture_stage3.py:113` vs `mjs:329-337`) · emergent dedup ignores redirects (`mjs:528-533`) ·
`run_tesseract_multi` unbounded + all-or-nothing per doc; stale rasters silently reused
(`process_stage4.py:207-225`) · duplicate-batch race on create (`server.py:504-508`) ·
daemon-thread jobs orphan the Node child; no cross-stage per-batch mutual exclusion
(`server.py:689/769/845`) · `serve_file` uses the known-broken `startswith` containment idiom
(`server.py:456`) · O(N²) `district_status.json` exports during batch runs
(`district_status.py:195-206`) · non-atomic `write_receipt` · `progress()` can report
labeled > total after a shrinking re-ingest.

### 3.3 Stage 5 / Stage 6 / console

(2.1–2.3 above are the urgent ones. The rest:)

**MAJOR**
- **M-17. Council family-validation hole (Mistral prefix).** `councils.py:21-39`: catalog maps
  `mistralai/* → "mistral"` but the fallback family is `model_id.split("/", 1)[0]` = `"mistralai"`
  for any *uncatalogued* Mistral model — so two Mistral voters can pass `validate()`, exactly the
  same-family false consensus REQ-056 forbids. Only Mistral is exposed (google/deepseek/qwen
  prefixes equal their family strings), and it's the family most likely to gain a model. *Fix:*
  prefix-normalize (`{"mistralai": "mistral"}`) or refuse uncatalogued ids.
- **M-18. gate@6 preview→freeze staleness.** `handoff_dispatch` (`server.py:923-945`) →
  `dispatch_handoff` (`stage6_dispatch.py:124-148`) rebuilds the package from the live DB at
  approve time; labels/splits/follow-ups are editable in the same app in between. What Ian
  approves is not verifiably what freezes. *Fix:* return the identity hash with the preview,
  require it on `/api/handoff/dispatch`, 409 on mismatch.
- **M-19. `pages` harvest hint dropped at package assembly.** `release.best_send` emits
  `{"file": pdf, "kind": "pdf", "pages": harvest}` (`release.py:77-78`) but
  `package.assemble_record` (`package.py:40-43`) drops `pages` — it never reaches the frozen
  handoff or `plan_requests`. The cost-containment payload (send pp.2–4, not the 60-page handbook)
  doesn't survive to the paid call. *Fix:* carry `pages` through `assemble_record`, `_identity`,
  `plan_requests`.
- **M-20. `district_status.json` exported from uncommitted state during dispatch.**
  `stage6_dispatch._record_dispatched_events` (:108-113) exports after flush, before
  `HND.write` (:147); if the write raises, the session rolls back but the git-swept backup already
  contains phantom `dispatched` events. *Fix:* export after the file write succeeds / after commit.

**MINOR (stage 5/6, condensed)**:
`handoff._identity` order-sensitive (sort district blocks) · empty dispatch freezable
(`stage6_dispatch.py:136-137`) · unknown council override silently ignored
(`package.py:33`) · vision reps priced on floors once the measured token model lands
(`build_signals.py:992` inserts `n_chars=None`) · `frontier.py:58` still grid-searches the retired
V1 `tier_and_category` (tunes dead code) · `followup_flags.json` not git-tracked;
`cluster_splits.json` not in the pre-commit sweep · `build_signals.py:982` writes
`harvest_slice.txt` into `data/raw/` (against the never-modify rule) · `migrate_labels_v21` re-run
can undo human facet corrections (idempotent vs v2.0, not vs subsequent edits) ·
`lf_nonstandard_day` is soft — a 2-hour-delay page with a prose pair still auto-sends tier-A ·
`lf_footer_hours` merges footer+header into one office verdict (`detectors.py:65-74`) ·
`server.py:881` `_TARGET_IN` frozen at import **and** string-interpolated into SQL (bind a list
param) · harness `f1` treats a legitimate 0.0 precision/recall as "not computable"
(`harness.py:55`) · cluster cascade copies `facets._pages` to every member.

### 3.4 Requirements & documentation hygiene

- **REQUIREMENTS.yaml broken** (exec summary #2): unquoted continuation text after REQ-114's
  closed description scalar (lines 2653–2659). One-line fix; add a CI parse check
  (`yaml.safe_load`) so it can't regress.
- **Status lag on shipped work:** REQ-101 (Stage 6, merged PR #2) and REQ-102 (gate@1 console)
  still `accepted`; REQ-113 `in_progress` / REQ-115 `planned` despite PR #3 merged (cde04e9).
  REQ-101's notes still carry "OPEN #1 council-config grain" — resolved per-representation by the
  build.
- **REQ-058 is stale-and-live:** still `accepted`, still specifying the retired
  Claude-WebSearch/OpenRouter wave discovery (and its tests encode the old wave order). It missed
  the `[SUPERSEDED]` banner pattern 042/046/048/057 got. REQ-104's own acceptance criteria
  (:2509-2512) still describe the abandoned `claude -p` Wave-1 design.
- **REQ-096 depends on the deleted V1 `tier_and_category`**; REQ-093's "main-only de-chrome
  signal" target is inverted by V2's max-evidence fix. Both need reconciling with REQ-113.
- **REQ-034 missing** (only ID gap; CLAUDE.md says 001…115). **REQ-097's deferral expired**
  ("until batch 2 exists" — batches 00002–00007 exist).
- **Part-5 flags still open, verified:** inert `tests/test_scraper_resilience.py`/
  `test_scraper_security.py` (silently skip; delete candidates), stale `schema.sql` (#20), stale
  data dictionary (#19), the two LCT write paths (#21 — now confirmed as finding M-8).
- **Doc drift** (fix approved 2026-07-01, applied alongside this review): TERMINOLOGY.md's Stage-2
  waves + CP-A/B/C + "de-chrome PLANNED"; ACQUISITION_PIPELINE.md's Path-1/2 council configs
  (superseded by the decided pair+judge template) + Key-files rows pointing at the obsolete
  `stage2-discover` skill; GETTING_STARTED.md / PROJECT_CONTEXT.md June-12/13 snapshots.
- `docs/DATABASE_SETUP.md:204` documents the minutes CHECK as 0–600 (actual 100–600). **Five
  inconsistent plausibility bands** exist for the same quantity (DB CHECK 100–600; verification.py
  300–480 warn; content_parser 240–540; validate_bell_data >480 error; REQ-055 240–510) — pick one
  constants module.

---

## 4. Opportunities for improvement (beyond point fixes)

### 4.1 Converge the label object on facets
The label is now **three overlapping stores** — `primary_label`, `flags_json` (legacy, still
load-bearing in `release.py`), `facets_json` (v2.1) — and the three consumers (UI, release
descent, harness fingerprints) each read a different subset. Findings 2.1/2.2 are both symptoms.
Migrating `duplicate` to a first-class mechanism (or a facet), repointing `release.py` at facets,
and deleting the flags read removes the whole bug class.

### 4.2 Tier the CONTROL-FAILURE blast radius
The reconcile/fail-loud pattern is right, but registry-ahead-of-disk (a genuine control failure)
and one missing screenshot file (a per-record degradation) currently get the same run-halting
treatment — and the check runs over already-processed districts. A per-district quarantine
("inconsistent, skipped, surfaced in status") preserves the safety property without the
denial-of-service failure mode (C-8's second half).

### 4.3 Finish the CWD migration and the cache deletion story
`paths.py` is the right idea and the headless runners use it; `common/discover.py` (secrets!) and
the stage3/4 CLI defaults don't (M-12). The DB cache needs per-district DELETE-before-upsert
(M-14) *before* Stages 7–9 start reading it for paid work.

### 4.4 Test the production code, not mocks
The most instructive gap of the review: `test_data_precedence.py` tests a mock
`_apply_precedence_rule` **defined inside the test file** — the real `merge_sea_precedence.py` is
never imported, which is why C-4 survived with a green suite. Same pattern:
`test_sped_segmentation.py` (never imports `SpedEstimate.calculate_estimates`),
`test_temporal_validation.py` (reimplements the SQL in Python; the integration variant skips when
008 is absent; no test inserts a row and asserts the trigger populated `year_span` — the one test
that would have caught C-1). High-value missing tests, in order:
1. Insert an `lct_calculations` row via the ORM; assert `year_span`/flags populated (catches C-1).
2. Run the real `merge_sea_precedence` on a fixture; assert NCES wins year-matched (catches C-4).
3. Save a label without a `flags` key; assert `flags_json` preserved (catches 2.1).
4. `ingest_batch` against an empty label table; assert `labels.json` not truncated (catches 2.3).
5. Adversarial council config: uncatalogued `mistralai/*` voter + catalogued Mistral voter must
   fail `validate()` (catches M-17).
6. `pages` survives `assemble_package` → `freeze` → `plan_requests` (catches M-19); `_identity`
   order-insensitivity; preview-hash staleness; empty-selection freeze.
7. `get_instructional_minutes` unit tests per band (catches C-3); IL/MI/MA ID converters with
   leading-zero inputs (catches M-4).

### 4.5 Retire the V1 scoring remnants
`tier_and_category` + `DEFAULT_TIER_PARAMS` + `frontier.py` + `test_tuning_frontier.py` all still
exist and pass, but nothing in the ingest path calls them — a standing invitation to tune the
wrong thing. Re-point frontier at `DEFAULT_DETECTOR_PARAMS` (per-detector facet scoring, already
the planned follow-on) or archive it.

### 4.6 One CURRENT_YEAR, one plausibility band, one schema authority
Three constants modules would kill three classes of drift: the school-year literals (M-5), the
five plausibility bands (§3.4), and the schema authorities (`models.py` is declared authoritative —
regenerate or retire `schema.sql`, and make the `apply_*` scripts write the migration ledger).

### 4.7 Precious-state backup completeness
The pre-commit sweep covers `labels.json` + `district_status.json`. `cluster_splits.json` is
tracked but unswept; `followup_flags.json` is **not tracked at all** — a follow-up directive
doesn't survive a clone. Add both to the hook; also fix the export-before-commit ordering (M-20).

---

## 5. Stages 7 / 8 / 9 — concrete design proposals

Grounded in: `STAGE6_DISPATCH_DESIGN` §0/§3F (the as-built seam), `LLM_COUNCIL_RESEARCH`
(judge > vote; shared-bad-input false consensus; calibrated cascades), governance §11/§12 (gates,
back-edges, completion grain), REQ-049/050/051/053/054/055/056, and the Stage-9 landing-zone audit
(§3.1/M-7, §5.4). Each proposal names its blockers from §2–3.

### 5.0 Build order (recommended)

1. **Stage-9 landing-zone migration first** (§5.4.1) — it's cheap, blocks nothing, and unblocks
   honest end-to-end tests of 7→8→9 on synthetic data before any paid call.
2. **`dispatch_item` ledger + Stage-7 executor core** (§5.1.1–5.1.3) on a **mock transport** —
   the consensus comparator, judge materialization, and persistence are all testable for $0.
3. **First paid run = the council lab's cost-only pass** (§5.5) — it exercises the same OpenRouter
   client, produces the measured token model, and costs a few dollars.
4. **Live Stage 7 on one small dispatched batch** (verified-only mode — training-grade, already
   built at gate@6) → Stage 8 → gate@8 → Stage 9 write.
5. GT alignment (`batch_00000`) + composition re-benchmark when accuracy questions arrive.

### 5.1 Stage 7 — Extract (the paid council + judge loop)

**Package:** `stage7_extract/` mirroring Stage 6's pure-core/app-shell split — `client.py`
(OpenRouter POST, retries, telemetry), `consensus.py` (pure comparator), `runner.py`
(per-rep state machine), with the app-layer bridge in `process_governance/` and the import-linter
contract extended (`stage7_extract` imports `common` + `stage6_handoff` request shapes only).

**5.1.1 The record-level dispatch ledger (the missing spine).** The as-built seam has no
per-record state: `handoff.status` is always `"dispatched"`, nothing marks a rep as
sent/answered/escalated, and the same district can be frozen into N handoffs → double paid spend.
Proposal — a **`dispatch_item` table** (precious):

```
dispatch_item(handoff_hash, rec_key, file, council_id,
              state:      planned | sent | voted | judged | consensus | no_consensus
                          | evidence_requested | failed,
              per-call:   request_id, model, prompt_tokens, completion_tokens, cost_usd,
                          latency_ms, parsed_ok,
              result:     facts_json (the per-school {school,start,end,band} rows, per model),
              consensus_json (agreed pairs + which models + judge involvement),
              updated_at)
```

This gives: idempotent resume (re-running a handoff skips `state >= voted` items — REQ-051's
"resumable, idempotent per district"); the 7→6/7→1 back-edges something to key on; the budget
governor a real spend ledger; and the council lab its telemetry for free. It also answers
"already dispatched?" at gate@6 (surface a per-district "n_already_sent" so partial approvals
don't double-send).

**5.1.2 The executor state machine (per rep × council).**
```
sent(voter A) ─┬─ sent(voter B)          [parallel; both from the frozen request plan]
               ▼
        compare (consensus.py, pure):
          per school: cross-family (start,end) pair within ±15 min  → consensus school
          school matching: normalized name (REQ open-decision #6 — do NOT loosen;
            unresolved schools held out, never wrong-counted)
        ├─ all schools consensus AND NOT fidelity_suspect → state=consensus
        ├─ any disagreement OR fidelity_suspect            → materialize the judge
        │    judge = 3rd family, re-reads the SAME rep (vision judge for image council),
        │    prompt includes both voters' facts + the plausibility gate (240–510, start 6:30–9:30)
        │    ├─ judge agrees with a voter (±15) → consensus (judge-resolved, logged)
        │    └─ judge produces a third value / fails gate → no_consensus → gate@7 queue
        └─ parse failure / API error → bounded retry → failed → gate@7 queue
```
Key rules carried from the research + REQ-056: same-family agreement is never consensus (the
`councils.validate()` guarantee — fix M-17 first); `fidelity_suspect` reps **never auto-accept on
2-voter agreement** (the flag is already in the frozen rep dict — the executor must honor it, the
one place the New Haven lesson becomes code); log **which models formed each consensus**
(monoculture audit — the ledger's `consensus_json`).

**5.1.3 The response schema — preserve BOTH paths to minutes.** The ported prompt reads start/end
times only. Per the standing note (`two-paths-to-instructional-minutes`), the schema must also
carry the "golden nugget": an **explicitly published minutes statement**
(Dunseith: "elementary 435 min / high 450 min"). Proposal:
```json
{"schedules": [{"school_name","grade_level","start_time","end_time","confidence"}],
 "stated_minutes": [{"scope","grade_level","minutes","quote","gross_or_net_if_stated"}]}
```
`stated_minutes` is a *fact read from the page* (a quote), not a computation — it honors REQ-054
(the model computes nothing; it transcribes a printed number). Stage 8 treats it as a separate
evidence type with its own gross/net caveat. **Build obligation carried from REQ-054's notes:**
the prompt-side invariant test (no "compute minutes", no "pick typical") must be re-established
against the live Stage-7 prompt — it lost its test when the archived extractors broke.

**5.1.4 Input handling — the lessons already paid for.**
- **Never truncate; chunk + union** (the Orange `MAX_TEXT_LEN` lesson): any text rep over the size
  threshold is sent in page/section chunks, per-school facts unioned. Since aggregation is
  per-school anyway, union loses nothing.
- **`kind:"pdf"` needs a defined read path** (Stage-7 readiness gap): the frozen doc can carry pdf
  reps but `prompts.user_message` only handles text/image. Decide at Stage 6 (materialize
  `pdftotext -layout` text + the page range at freeze — preferred, keeps Stage 7 dumb) or spec the
  conversion in `requests.py`. Blocked on M-19 (`pages` must survive to the seam either way).
- **Content resolution:** freeze `district_dir` into the district block of the handoff (readiness
  gap #1) so Stage 7 never reverse-maps hashes via glob.
- **Band-from-school-name** as a disambiguation signal in the consensus comparator (the Broward
  fix candidate): when a hub rep's positional grouping is ambiguous, "… High School" in the
  school_name field binds the row to the high band.

**5.1.5 The request-more-evidence protocol (§3F made concrete).** A council/judge outcome may be
`evidence_requested` with a typed request:
- `more_text_reps` → Stage 6 re-dispatch of additional stored reps (no new capture; 7→6);
- `the_image` → the same URL's PNG to the image council (7→6);
- `more_data` → a row in a **`followup_request`** queue that gate@7 reviews; approved requests
  become a Stage-1 follow-up batch (7→1 — never minted by Stage 7 directly, per governance §11d).
On the OpenRouter session question (§3F OPEN): **assume no session persistence** — reconstitute
context from the immutable dispatch + a follow-up prompt template per council config. That's the
only design that survives a judge running days after the voters; the frozen artifact exists
precisely for this.

**5.1.6 Budget governor (REQ-051) — enforce at the executor, not the gate.** gate@6 shows an
estimate; nothing enforces. Proposal: `budget.py` in `common/` — per-run cap + per-district cap
(config-as-data with provenance), checked before each POST against the `dispatch_item` spend sum;
breach → halt cleanly (`state=planned` items resume later), never mid-rep. Auto-gate@6/7 stay
blocked on this existing (governance §11b already says so).

**5.1.7 gate@7 console.** The queue = `no_consensus` + `failed` + `evidence_requested` items.
Per item: the rep (text/image inline — the inspect endpoint exists), each model's facts
side-by-side, the judge's read, and actions: accept-a-model's-facts (with reason → recorded like
a gate@8 override), approve/deny evidence requests, re-dispatch to a different config (7→6),
statutory-fallback the district-band (REQ-049: labeled, never counted as enriched).

### 5.2 Stage 8 — Aggregate (per-band, deterministic)

`stage8_aggregate/aggregate.py` (the mode-then-mean prototype) is the right core — pure, tested.
What's missing is the record around it.

**5.2.1 The aggregation record (persist the distribution, not just the answer).** Proposal — a
precious **`band_result`** table:
```
band_result(district_id, band, school_year,
            minutes_gross, basis: mode | mean_tie | stated_minutes | manual_override,
            n_schools_consensus, n_schools_unresolved,
            distribution_json ({minutes: count}),          -- the auditable histogram
            source_rec_keys[], handoff_hashes[],
            override_reason (NOT NULL when basis=manual_override),
            confidence: high | medium | low,               -- see 5.2.3
            gate8_actor, gate8_at)
```
This is the REQ-050 provenance record ("reconstruct and re-verify months later") and the gate@8
review surface in one. The user stories' manual edit-with-required-reason maps to
`basis=manual_override` + `override_reason`.

**5.2.2 Evidence precedence within a band.** With 5.1.3 there are two evidence types:
1. **Consensus per-school pairs** → exact mode over schools (tie → mean; REQ-056 exactly — never
   a tolerance-cluster mean);
2. **`stated_minutes`** for the band (Dunseith) → usable directly *if* labeled gross-or-unstated;
   a stated **net** figure is stored but flagged (`basis=stated_minutes`, noted) — never silently
   mixed with gross pairs.
When both exist and disagree beyond ±15: gate@8 item, not an auto-pick. **Band mapping:**
per-school bands come from Stage 1's `bands_for` (NCES grade spans) — a K-8 school's consensus
pair contributes to both elementary and middle modes. Only the three enum bands are ever written
down (the `chk_grade_level` reality, §5.4).

**5.2.3 Per-band confidence = the satisfaction signal.** The open question ("what makes a band
satisfied") doubles as the confidence enum:
- **high**: ≥3 consensus schools (or a census of a smaller band) agreeing on the mode, no judge
  involvement, no fidelity_suspect sources;
- **medium**: mode from ≥2 schools, or judge-resolved, or `stated_minutes` source;
- **low**: single school, or mean-on-tie, or any fidelity_suspect input surviving;
- **unsatisfied**: no value → follow-up-batch candidate (8→1) or statutory fallback.
This feeds gate@8 auto mode later (auto-accept high, escalate the rest — governance §11b), the
follow-up batch creation (REQ-109), and the drift detector (REQ-097, whose deferral has expired).

**5.2.4 Mode-stability early-exit** (the open half of the sampling policy): process the queued
schools; after each, if the band's modal value is unchanged over the last 5 schools **and** lead ≥3
over the runner-up, stop dispatching that band's remaining schools. Implemented in the Stage-7
runner (it decides whether to send the next school), driven by Stage-8's running mode —
one more reason the `dispatch_item` ledger and `band_result` must share the DB. Measure the
savings on the first real batches before trusting it at scale (it's an optimization, not a
correctness feature — ship Stage 7 without it).

### 5.3 gate@8 console
Per district: bands with `band_result` values, the distribution histogram, per-school consensus
rows (click-through to the rep — the inspect endpoint), unresolved schools with reasons, and
actions: approve (→ Stage 9 auto-writes), override (reason required), re-queue band (8→1
follow-up), add-URL-to-dispatch (8→6). Approval emits a `gate@8` state_event per district; Stage 9
consumes approved `band_result` rows only.

### 5.4 Stage 9 — Incorporate (the write across the boundary)

**5.4.1 The landing-zone migration (do this first — it blocks honest testing of everything above).**
The audit (§3.1, "Stage 9 landing zone") found the current `bell_schedules` table rejects the
pipeline's output:
- **`minutes_basis` column** (`gross_bell_to_bell` | `net_legacy` | `statutory`): today the column
  is documented as net (`schema.sql:131` "excluding lunch, passing, recess") while REQ-055 data is
  gross, and legacy rows are a mix (anything `calculate_minutes.py` produced was net). Backfill
  audit of existing rows required; without this, gross and net silently mix in cross-district
  comparisons — the exact "honest labeling" failure the project's rules exist to prevent.
- **`chk_method`** must gain a value for council extraction (proposal: `council_extraction`,
  keeping `automated_enrichment` for legacy) — else Stage 9 either masquerades or violates the
  CHECK.
- **`chk_confidence`**: map §5.2.3's enum (it already fits high/medium/low; `unsatisfied` never
  writes).
- **Time-format fix:** `verification.py:585`'s `TIME_PATTERN` requires AM/PM;
  `schedule_aggregation._to_minutes` canonicalizes 24-hour HH:MM. **Every Stage-9 insert through
  `queries.add_bell_schedule` currently raises ValueError.** Extend the pattern (accept both) or
  normalize at the seam.
- **Plausibility alignment:** pick the 240–510 gate (REQ-055) as the single band; the DB CHECK
  (100–600) stays as the outer sanity bound.

**5.4.2 The write itself.** One path only: through `queries.add_bell_schedule` (after fixing its
partial-update-overwrites-with-None behavior, M-7) — never a fourth divergent writer. Payload from
the approved `band_result`: minutes (unrounded — rounding at export, fixing the current M-6
violation on the legacy path too), `year` = the school year of the *source schedule* (validated:
post-COVID allowlist at the seam — the single highest-leverage validation to add),
`schools_sampled` = the consensus school list, `source_urls` = the rep URLs,
`method=council_extraction`, `minutes_basis=gross_bell_to_bell`, notes = distribution summary +
`handoff_hashes`.
- **Idempotency:** the `(district_id, year, grade_level)` unique constraint + upsert = re-runs
  update in place; a corrected aggregation (new gate@8 approval) overwrites with full provenance
  of the correction in `band_result` (the LCT row holds the current truth; `band_result` holds
  history).
- **Rule #6 verify-in-DB:** after the write, re-select and compare; mismatch → fail loud, no
  `incorporated` event.
- **`state_event`:** yes — emit `incorporated` (stage=9) per district-band; it closes the
  lifecycle, feeds the Overview projection and the completion grain (district × band, REQ-109),
  and makes "enriched" counts DB-derivable (the pre-commit hook's count verification keys off
  this).
- **Statutory fallback path (REQ-049):** a gate@8 "no defensible value" decision writes
  `method=statutory_fallback, minutes_basis=statutory` via the same single path — labeled, never
  counted as enriched, with the failure reason in `enrichment_attempts`.

**5.4.3 The read side.** `get_instructional_minutes` needs two changes before Stage-9 data lands:
(a) prefer `minutes_basis=gross_bell_to_bell` rows and expose the basis to callers (the LCT
reports must label which basis produced each number); (b) apply the COVID/staleness filter (C-2)
so a legacy 2019-20 row can't outrank statutory. And C-3 (per-band fetch) must be fixed or Stage
9's carefully-built elementary values will never be read for elementary LCT — **the single
highest-irony bug in this review: the pipeline's whole product is per-band minutes, and the
consumer currently throws the band away.**

### 5.5 The council lab (unblocks composition; cost pass needs no GT)
Endorse the §3C design as-is; two additions from this review: (a) the bridge never populates
`n_schools` and image reps carry `n_chars=None` — the lab's stratified sample must include
image/pdf cells with real dimension telemetry or the fitted token model prices the biggest calls
on floors (minor finding, §3.3); (b) emit per-call rows into the same `dispatch_item`-shaped
telemetry so lab and production share one ledger format. GT alignment (`batch_00000`) stays the
gate for accuracy/composition — endorse deferring it; cost-only now.

---

## 6. Prioritized recommendations

**Do before Ian's next labeling session** (both are two-line patches + a test):
1. Preserve `flags_json` on save when the payload omits `flags` (2.1).
2. `import_labels()` before `export_labels()` in `ingest_batch` (2.3).

**Do before the next batch runs stages 2–4:**
3. Screenshot-timeout manifest fix + tiered consistency check (C-8).
4. Failover on network/5xx errors; split 429 from billing (M-10).
5. Wave-provenance labels (M-11 — every batch run deepens the corruption).
6. Anchor `SECRETS_FILE` + CLI RAW_DIRs to `paths.REPO_ROOT` (M-12).
7. `_run` exit-code checking (M-13); dot-boundary suffix matching (M-15).

**Do before Stage 7 is built:**
8. Stage-9 landing-zone migration (5.4.1) + `dispatch_item` ledger (5.1.1).
9. `pages` through the package (M-19); preview-hash staleness check (M-18); Mistral family
   normalization (M-17); facets-based image routing (2.2).
10. Cache deletion story (M-14).

**LCT-core, before the next published LCT run:**
11. Per-band minutes in `calculate_lct_variants` (C-3).
12. Wire COVID/span enforcement into the live paths (C-1/C-2 — trigger columns + read filters).
13. Fix or quarantine the SEA merge (C-4) and the TX iloc columns (C-7); suppression sentinels (M-3).
14. Crosswalk protection in reset/rebuild (C-6); archive the dead-but-armed enrich/ scripts (M-9).

**Hygiene (cheap, high leverage):**
15. Fix REQUIREMENTS.yaml + add a CI parse check; bump REQ-101/102/113/115 statuses; supersede
    REQ-058; reconcile REQ-093/096/104.
16. Add `cluster_splits.json` + `followup_flags.json` to the pre-commit sweep; fix the
    dispatch-time export ordering (M-20).
17. The §4.4 test list — item 1 (trigger) and item 2 (real merge) first.

---

*Review conducted 2026-07-01 by Claude Fable 5. Method: four parallel code-sweep agents
(REQUIREMENTS/HISTORY digest · stages 1–4 + Node scraper · stage 5/6 + console · LCT-core +
database), each finding verified against quoted source; criticals independently re-verified in
the main session. Suite state at review: 677 passed / 20 skipped, lint-imports 3 kept / 0 broken.*
