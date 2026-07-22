# Pipeline Governance, State Model & the Stage 5→6 Release

> **Authority:** the cross-stage architecture — DB-vs-disk split, state-event log, gate/console model,
> the Stage 5→6 release mechanics. Per-stage present-state detail lives in each `acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md`;
> this doc is what ties them together.
> **Audience:** anyone building or reasoning about a pipeline stage, the console, or the DB schema.
> **Companions:** `ACQUISITION_PIPELINE.md` (the 9-stage map + flow diagram), every `acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md`
> (per-stage detail — each links back here for its gate/console/DB contract), `PROJECT_HISTORY.md`
> (high-level ADR log; §8/§9/§9a below are the detailed build history behind those entries).
> **Update this when:** a cross-stage architectural decision changes (DB schema, gate model, the
> DB-is-working-store/disk-is-receipts split, console scope) — NOT for per-stage implementation detail,
> which belongs in that stage's own design note.

This note is the architecture for three coupled decisions that span every stage:
1. **The DB is the working store; disk holds binaries + receipts** — the cross-stage registry *and*
   every stage's data live in the DB (what the next stage reads); the per-stage JSON files are
   auditable receipts, not transmitters (§1).
2. **The Stage 5→6 release** — `filtered.json` as a generated **export** of the DB's release state
   (not the primary store), + the Stage 6 `handoff_<hash>_<timestamp>.json` immutable dispatch record (§5–§6).
3. **The app's scope** — a single **stage-selectable governance console** at
   `infrastructure/acquisition/process_governance/`, the human-in-the-loop surface for every gate (§7, §11).

**Current build state (2026-07-20):** since 2026-07-18, landed: the discovery-scope-policy/discovered-domain
console control surface (#572/#164, §11j), `queue_create`'s scope-aware rewrite (§11k), the one-attempt
security-block enforcement (#578), the #518 fidelity-triage consumer (§11f), the #118 attribution card
(§11f), and the shared `geo_ladder_exhausted` threshold bug fix (#575, §11e). REQ-098/099/103/094
(packaging, state-event log, Postgres governance
DB, event-driven `filtered.json`) are all COMPLETE — see §1b, §3, §6. The console is built and run live
**through `gate@8`** (the standalone Stage 8 / gate@8 shipped #89, 2026-07-14 — see below and
`STAGE8_AGGREGATE_DESIGN.md` §0a). Through **`gate@7`**: gate@1 (REQ-102), Stage 2 (REQ-104), Stage 3 (REQ-110), Stage 4 + the Stage 4→5
incremental handoff (REQ-111, §12), the Stage 5 district-driven console (REQ-112), Stage 6 dispatch/freeze
through the Stage 6→7 seam (REQ-101), and Stage 7 council extraction + the gate@7 review console (REQ-117:
extraction results + the request-more-evidence **detect/rank/defer/review** loop — see
`STAGE7_EXTRACT_DESIGN.md` §0/§4), and the request-more-evidence **execution + console maturation**
(REQ-118, hardened epic #163, PR #167 merged 2026-07-05: 7→6 bundles a district's approved alternate-rep
re-dispatches into one round + 7→2/7→3/7→1 via a shaped Stage-1 follow-up batch that auto-flows to gate@5,
under the REQ-051 budget governor + a per-district rounds depth guard — STAGE7 §3F; gate@7 now has
execute/compose buttons, request lineage, and a preview modal, §11h/§11i).
**A live #122 shakedown of that loop (2026-07-05/09) then drove a 6-batch hygiene campaign** (PRs #177,
#179, #191, #193, #194–#197, all merged) that found and fixed real defects the shakedown + code review
surfaced: run-abort robustness (#173 — one bad rep no longer strands the whole batch), silent
truncation/tail-loss (#169) then eliminated at the source by pre-sizing `max_tokens` from the roster
(#180/#187), the request loop suppressing follow-ups that can't add coverage (phantom/already-covered
bands, #176/#170/#175 — measured ~57% of follow-up spend was previously wasted), plus a duplication/
efficiency sweep (#147/#148) that promoted the fragile `handoff_hash NOT LIKE '%-image'` console filter to
a first-class `run_kind` column (STAGE7 §0/§6) so a second vision-council probe can never shadow a
district's production run. Dead code + test drift (#125/#87/#126/#166) also retired. Full mechanism/
measurement detail: `STAGE7_EXTRACT_DESIGN.md` §6 (decision log).
**Stage 8 gate@8 BUILT (#89, 2026-07-14; console + approve/send-back + the 4 human-judgment tables + frozen
receipt — `STAGE8_AGGREGATE_DESIGN.md` §0a/§0b). **Stage-9 write BUILT (#93/#94/#95, 2026-07-21 —
`STAGE9_INCORPORATE_DESIGN.md`).** Still unbuilt: the 8→1/8→6 back-edges and gate@8 auto mode.**
**Gates are stage-numbered (§11):**
`gate@1` (queue) · `gate@5` (per-URL review) · `gate@6` (dispatch) · `gate@7` (council requests) · `gate@8`
(results) — **1/5/8 structural (permanent), 6/7 supervision (first to relax) — §11i.** §8, §9, and §9a
below are **historical** — fully executed planning/sequencing docs kept in place because their section
numbers (`governance §9a`, etc.) are cross-referenced elsewhere; see the banners on each. **Council Lab
BUILT, first experiment MEASURED (2026-07-04)** — the judge-replay harness (`council_lab.py`) validated the
Qwen-VL image-judge swap (#82, closed); see `COUNCIL_LAB_DESIGN.md`.

**The "whittle down open issues" hygiene campaign is fully CLOSED (2026-07-09/10):** Batch 5 (#168 a
first-class "abandoned" batch status + #171 gate@6 already-dispatched indicator, PR #198), Batch 6 (#60
`lf_nonstandard_day` soft-gate + #61 footer/header independence + #108 facet-level scoring, PR #199, a
measured pass), and #124 (the cross-boundary `arch-manifest.json` + fitness-function suite, PR #206) — all
merged. Full detail: each stage's own design note change log; `PROJECT_HISTORY.md`.

**Runtime guardrails for the manual→auto transition, epic #209 — Phase 0/1/2 all BUILT + MERGED
(2026-07-13, PR #250):** all born from `production-quality-control-research/FINDINGS-AND-DECISIONS.md`'s
synthesis. Phase 0/1: **(1)** the canonical recall floor (`harness.RECALL_FLOOR=0.98`/`FLOOR_TIER="A+B"`)
now **enforced inside** `build_signals.ingest()`'s transaction via `--assert-floor` (#208, PR #215 — a
violation rolls back the *whole* re-ingest, not a post-hoc report); **(2)** the anti-survivorship
exploration quota, pure control-law core (REQ-120/#211, PR #216) through **live wiring** (`exploration_live.py`
— reject-population query, coverage meter, gate@5 demote-hook wired into BOTH `save_label` and
`reset_labels` inside a SAVEPOINT for isolation, plus `GET /api/exploration-audit`; enforcement DORMANT
while gate@5 stays configured manual) — issues #211 **CLOSED** 2026-07-13; **(3)** the gate-decision
calibration log — schema built (REQ-121/#210, PR #217) and **wired live** at gate@5/6/7 (PR #218), so the
corpus is now accruing forward from every gate action; **(3a)** #214's measured-pass fix — every scoring
measured-pass now ALSO reports Rejection-Quality/TNR on the exploration cohort (the pruned tier-D tail),
closing the "illusion of improvement" hole (`STAGE5_FILTER_DESIGN.md` §5d) — issue #214 **CLOSED**
2026-07-13. Phase 2 (merged PR #220): **(4)** the group-aware non-inferiority promotion gate — LOGO-CV +
cluster bootstrap + TOST + ICC/DEFF, proven stats libraries not hand-rolled (#212), wired advisory into
`frontier gate()`; **(5)** safe-promotion machinery — an immutable content-addressed config artifact +
@champion/@fallback pointers + the shadow→gate→swap→record flow (#213), shipped **DORMANT** (nothing reads
the champion pointer live yet). Full detail: §11b below and each stage's own design note; activation of the
dormant pieces tracked as one checklist (#219, stays open by design). **Epic #209 is CLOSED (2026-07-13)** —
all three phases shipped and merged; #219 (dormant→live activation) stays open by design as the
forward-looking follow-on.

> **A real incident, worth recording here since it's exactly the kind of cross-stage state-integrity lesson
> this doc exists to capture.** The PR meant to land #104/#211/#214 was stacked on the PR landing #236/#237
> (to avoid a rebase conflict from overlapping files) and its base was never retargeted to `main` before
> merge — so it merged its 12 commits into the now-orphaned FEATURE BRANCH, not `main`. `main` briefly had
> none of this epic's code (`gate_mode.py`/`exploration_live.py` didn't exist there) despite the PR showing
> as "merged." Caught before any doc work proceeded against the stale state; corrected by cherry-picking the
> identical, already-reviewed commits onto a fresh branch off the real `main` (content verified byte-
> identical via `git diff` before merge) and landing that as PR #250. **Lesson: after a stacked PR's base
> merges, verify the dependent PR's base was actually retargeted — "shows as merged" is not the same as
> "landed on `main`."**

**Epic #200 (shift-left defect-prevention infra) BUILT + MERGED (2026-07-11, PR #221):** the DB-free
test-job guard (#201), a pre-push git hook running the DB-free suite + lint-imports (#202), property-based
(hypothesis) state-machine tests for the batch lifecycle + request-loop directives (#203), and an AST
mutation sweeper for the highest-stakes pure cores (#204). A max-effort adversarial review of the merge
candidate found 15 real findings before it landed — most notably that `_sent_files_by_rec` (the
execution-side `7→6` history check) only unioned `7→6` lineage, not `7→3`, asymmetric with the
detection-side #231 fix in the very same PR, and that `_covered_bands_now`/`_district_request_inputs`
lacked a `run_kind='production'` join, so a vision-council probe's accepted fact could auto-reject an
already-approved directive at compose time. **#127 (an automated node:test harness for
`capture_discovery.mjs`'s browser-driving logic, real Chromium via `page.route` fixtures — no fixture
server, no faked page) merged 2026-07-12 (PR #239)**, closing epic #123 (tech-debt/hygiene cleanup); its
own adversarial review caught a latent `segmentChrome` bug (header/footer/nav grabs ignored the
`landmarks` argument) and hardened the harness to fail loud in CI rather than silently skip if Chromium
is unavailable.

**#122 (the first live non-benchmark end-to-end pass of the request loop) CLOSED 2026-07-06** — 23 fresh
districts, both back-edges proven end-to-end; full report:
`docs/technical-notes/stage-7-loop-reports/2026-07-06T0458Z-stage7-loop-report.md`. **A SECOND live
shakedown ran 2026-07-11** (batch_00013) to re-validate the loop against the epic #200/#209-hardened
pipeline, finding **six** real request-loop/pipeline regressions, fixed across two merged PRs (a third,
unrelated PR closed out epic #123 the same day — see below):
- **PR #221 (2026-07-11):** **#231** — the `7→6` alternate list could re-offer an already-failed rep
  across rounds; **#232** — gate@7's view/rollup read latest-extraction-only, so a scoped retry could make
  an earlier run's solid facts disappear — fixed via a new cumulative merge, codified as **REQ-122**.
- **PR #240 (2026-07-12), request-loop integrity:** **#234** — executing one request duplicated its
  still-open siblings (dedup was scoped to one handoff; a `7→6` execution spins a new one); **#235** — the
  follow-up autoflow never called the Stage 4→5 ingest at all (batches 00014–00017's evidence silently
  never reached gate@5; fixed at the source — `run_stage4_with_ingest()` is now the ONE operation every
  caller uses, CI-enforced); **#230** — Stage 6's initial rep pick ignored the retry loop's own
  yield-ranking; **#233/REQ-123** — gate@7 now **auto-withdraws** an open request once its premise is
  satisfied under the cumulative state (§11b below — a deliberate exception to the manual-gate
  posture, and the review of the first draft found the fillable-band logic silently reproduced the exact
  bug it was fixing for an all-phantom/empty-real-bands district, plus a production-only staleness bug
  where the withdraw check couldn't see its own round's just-persisted facts under `autoflush=False`).

**PR #239 (2026-07-12), unrelated to the shakedown above:** the #127 `node:test` harness for
`capture_discovery.mjs`'s browser-driving logic (real Chromium via `page.route()` fixtures, no fixture
server) — closes epic #123 (tech-debt/hygiene cleanup); its own review caught a latent `segmentChrome` bug
(header/footer/nav grabs ignored the `landmarks` argument) and hardened the harness to fail loud in CI
rather than silently skip if Chromium is unavailable.

**A separate contamination-chain finding from the same shakedown was fixed one PR later:**
- **PR #242 (2026-07-11/12), the empty-domain contamination chain — the three items previously tracked as
  "not yet fixed" are now shipped:** **#229** (prevention) — Stage 1's `build_batch`/`build_followup_batch`
  refuse a district whose NCES `WEBSITE` yields no usable scoping domain (new `common/discover.py` helpers
  `domain_of`/`is_scoping_domain`, surfaced in the gate@1 console as a `domain_excluded` refusal list) as
  the admission-time guard, **plus Stage 2's `gate_urls()` fails closed as defense-in-depth** — a blank/junk
  domain now rejects every URL with an explicit reason instead of falling through to the old unscoped
  branch that kept everything (that fallthrough was the actual Millard mechanism, #227); benchmark
  (`batch_00000`) is exempt by structure (never routes through `build_batch`). **#228** (remedy) — a
  gate@5 "Reset labels" console action + `POST /api/reset-labels`, backed by the one shared
  `build_signals.reset_labels_bulk` (an UPDATE-to-unlabeled, not a delete), for the case a label asserts
  a false non-target ground truth (a valid schedule for the *wrong* district) that neither `target_absent`
  nor `unusable` can honestly express. **#227** (cleanup) — `remediate_contamination.py`, a manifest-first,
  dry-run-by-default tool generalized from the Millard one-off: resets the exact enumerated rec_keys,
  purges the district's regenerable signal + cross-stage-cache rows, corrects `batch_district.domain`,
  and records a `state_event` — all after a verified restore point, and only after the reset transaction
  commits does it re-export `labels.json`/regenerate the batch receipt (never leaves disk ahead of a
  rolled-back DB). It does not re-spend on discovery; the scoped re-run still goes through the normal
  gated console flow.
- Upstream findings from the same shakedown, each stage's own doc: #222/#225 (Stage 1/3), #223/#224/#226
  (Stage 5, still open); also #236/#237 — **CLOSED 2026-07-12** (Stage 5/7/8 aggregation-quality: #236
  shipped as designed, a school-name-suffix dedup fix; #237 was mis-diagnosed as a topology/NCES-undercount
  bug and resolved instead via `detect_single_school_over_extraction`, a detect-and-flag cross-LEA
  contamination detector at gate@7 — see `STAGE8_AGGREGATE_DESIGN.md` §1a and
  `docs/PROJECT_HISTORY.md`'s 2026-07-12 entry for the full investigation) — and #238 (deferred efficiency
  follow-ups, still open). #237 spun off a structure-aware charter track: #243/#244/#245/#246, the current
  backlog in this area. Full detail: `STAGE7_EXTRACT_DESIGN.md` §6 (decision log).

Next (as of 2026-07-18): **Stage 8 gate@8 has SHIPPED** (#89; the standalone console + approve/send-back +
the 4 human-judgment tables + frozen receipt — `STAGE8_AGGREGATE_DESIGN.md` §0a), and the #499 slot program
(REQ-144…150) + epic #478's overrides with it. Epic #119 (Stage 7 extraction quality, PRs #508–#511) also
CLOSED. **Epic #106 (Stage 5/6 filter & dispatch refinements) is now CLOSED** — its full slate shipped:
the school-year-currency work (#107/#241/#531 → PR #529/#533 — `content_school_year`, the pre-2017-18
validity floor, prefer-recent dispatch holds), the #530 combiner refinement (lone times-table on a
feed/calendar page → review), the console trio (#516/#521/#522 → PRs #534–#536), the #528 calendar-scalar
cut, the #537 confounder facet-vocabulary decision + measured detector pass, the #515 eligibility vetoes
(measured net-negative post-#537, closed without shipping the veto — see `STAGE5_FILTER_DESIGN.md` §3a),
#109 (human-labeled page range outranks auto `harvest_pages` for the handbook slice), #517
(`schedule_link_only` — the one-hop-away schedule link routes to a retry receipt), **#75/REQ-097 (the
Stage-5 drift detector** — CUSUM + Wilson two-gate over the fingerprinted scorecard series,
`stage5_filter/drift.py`, an advisory "retune recommended" badge on `/api/progress`; never auto-retunes —
see §11b's guardrail model and REQUIREMENTS.yaml REQ-097, `tested`), and **#83/REQ-116 (hub-priority
dispatch** — a labeled district hub narrows the first dispatch to itself; every other surviving send HOLDs
for the 7→6 back-edge; `tested`). A late #106 addition, **#540/REQ-153 (CMS-vendor profiling as a standing
expectation** — profile and fingerprint every CMS encountered; Edlio is the first vendor approved, adding
sibling-variant dedup to Stage-6 dispatch and two `cms_hosts.json` entries; REQ-153 `approved`, tests
pending). **Stage-6 `district_release_input` now runs FOUR sequential hold-passes** (base `decide()` +
`verified_only` downgrade → #107 prefer-recent → #540 sibling-variant → REQ-116 hub-priority; detail:
`STAGE6_DISPATCH_DESIGN.md`). The **Stage-9 write** is now **BUILT** (#93/#94/#95, 2026-07-21). Still
genuinely unbuilt downstream: the **8→1/8→6 back-edges** and gate@8 **auto** mode. **#518 (the Stage 3/4 capture-fidelity recall leak — login walls,
0-byte PDFs, security blocks, truncation) is now BUILT (2026-07-20):** `GET /api/fidelity-triage` is the
consumer REQ-154's fidelity columns were missing — see §11f. Other open tracks: **#110** (Stage 7 cross-config cascade escalation on
no-consensus, re-homed to epic #80 Council Lab — genuinely blocked on that lab producing a measured
config), the rest of the Council Lab backlog (`cost_benchmark`, prompt A/B, #81); the charter-segmentation
track (#243/#244/#245); #238 (deferred efficiency follow-ups). The live gate-mode (manual/auto) persistence
+ console toggle (#104 part a) and **#211/#214 are now all SHIPPED** (epic #209's Phase 0/1/2
build-complete, merged 2026-07-13 via PR #250 — see above); #104 part b (per-gate confidence-escalating
auto beyond gate@5) remains open, future work. Still open: REQ-100 (staleness, tracked: #100), the gate@7
inline PNG/PDF viewer (tracked: #151).

---

## 1. The organizing principle: the DB is the working store; disk holds binaries + receipts

**The governance DB is the working store and the pipeline's reflection of state.** Each stage projects its
slice into the DB, and the next stage (and the console) reads it from there — **data flows DB→DB, not
file→file.** Disk holds two things the DB deliberately does not: the **capture binaries** (too large for a
DB, regenerable from the web) and the **regenerable JSON files** the stages emit. Those JSON files are
**auditable receipts** — for state-confirmation, human inspection, and recovery — **not** the medium that
carries data between stages. (That file-as-transmitter model was the original 2026-06-26 framing; it was
retired when the cross-stage cache became a live working store — REQ-110/111/112; build history in §7a-A / §12.)
**Now unconditional across every stage (#526, closed 2026-07-18):** Stage 2's console/autoflow batch
read was the one standing exception — it consumed the on-disk receipt (`load_batch_any`) rather than
the DB, tracked as a live gap in this doc's own prior revisions. It now resolves via `server.
_batch_from_db` → `batch_store.to_working_doc`, the same DB-resolve contract Stages 3/4 already used;
`arch-manifest.json`'s `cli_only_loaders` fitness function fails the suite if `load_batch_any` is ever
referenced inside `process_governance/` again.

| class | what it is | home | properties |
|---|---|---|---|
| **STATE** | pipeline position; gate@1 approvals; gate@5 release; the re-discovery loop | **DB** (working store) | the `state_event` append-log + `current_state` view (§3); **precious** — JSON-backed, re-importable |
| **SIGNALS** | signal vectors, detector votes + the send/suppress/review decision, tier, category, clusters, attention (REQ-113 V2) | **DB** (working store) | regenerable; a **never-dropped live store on the incremental path** (REQ-110/111/112) — full drop+rebuild only for schema changes / recovery |
| **FACETS** (v2.1) | the human's target-shape + confounder + location answers (`label.facets_json`, REQ-114) | **DB** (working store) | **precious** — JSON-backed with the label; the per-detector ground truth |
| **CROSS-STAGE DATA** | the queryable projection of every stage's output — `discovery_school` / `candidate` / `capture` / `processed_doc` (`common/cache_ingest.py`) + `record` / `representation` / `district_target` (Stage 5) | **DB** (working store) | regenerable from disk; **what each stage reads to drive the next**, kept fresh by each stage's finish hook |
| **LABELS / SPLITS / BATCHES / FLAGS** | human ground truth, cluster-split overrides, the queued/approved batch (incl. `batch_district.domain`), follow-up flags | **DB** | **precious** — never in the ingest drop list; JSON-backed; a label's honest terminal states are `target_present` / `target_absent` / `unusable` / **`unlabeled`** — #228's `reset_labels_bulk` (a plain UPDATE, not a delete) is the one shared path back to `unlabeled` when a label turns out to assert a false non-target ground truth, the case a Millard-style contamination (#227) forces |
| **CAPTURE BINARIES** | the captured PDFs / PNGs / extracted text files | **disk**, authoritative | regenerable from the **web** (not the DB); referenced by `filename` from `representation`; relocatable as one tree (REQ-087) |
| **JSON RECEIPTS** | `discovery.json` / `candidates.json` / `captures.json` / `processed.json` / `filtered.json` / `batch_*.json` | **disk** | regenerable; the auditable record of each stage's output + the DB-recovery source (`batch_*.json` / `filtered.json` are generated *from* the DB); **NOT stage-to-stage transmitters** |

**Precious vs regenerable is the load-bearing line — not DB vs disk.** The DB holds precious things (labels,
lifecycle state, batches, flags) *and* the regenerable working store (signals + the cross-stage data
projection). Every **precious** class gets the **established backup pattern**: export to a version-controlled
JSON, re-importable after a DB wipe (exactly as `labels.json` / `cluster_splits.json` work today). Every
**regenerable** class can be rebuilt from disk (the binaries + the receipts) at any time. We extend that
pattern; we do not invent one. The DB is not a blob store: binaries stay on disk and are referenced by path.

**`TRACKED_BACKUPS` — the current 12-file precious-JSON-twin roster (`common/paths.py`).** Every PRECIOUS
DB table above gets exactly one git-tracked JSON twin, swept into every commit by `.githooks/pre-commit`
(both lists verified 1:1, path-for-path, 2026-07-20 — no drift):

| JSON twin (`data/acquisition/...`) | DB source table | what triggers the export |
|---|---|---|
| `status/district_status.json` | `state_event` (via `current_state`) | `district_status.save()`/`export()` on every state-event write |
| `stage5_review/labels.json` | `label` | a label save / `build_signals` ingest |
| `stage5_review/cluster_splits.json` | `cluster_split` | a cluster split action |
| `stage5_review/followup_flags.json` | `followup_flag` | a flag create/resolve (#57) |
| `status/gate_modes.json` | `gate_mode` | `POST /api/gate-mode` (#104/REQ-108) |
| `status/stage8_approvals.json` | `stage8_approval` | gate@8 approve/send-back (#89) |
| `status/band_exclusions.json` | `band_exclusion` | gate@8 band-exclude (#257) |
| `status/human_added_facts.json` | `human_added_fact` | gate@8 human-add (#474) |
| `status/slot_assignments.json` | `slot_assignment` | gate@8 slot disposition (#499/REQ-145) |
| `status/discovered_domains.json` | `discovered_domain` | `POST /api/discovered-domain` confirm (#164/#572, §11j) |
| `status/discovered_domain_decisions.json` | `discovered_domain_decision` | `POST /api/discovered-domain` confirm or reject (#572, §11j) |
| `status/discovery_policy.json` | `discovery_policy_event` | `POST /api/discovery-policy`, or the pool-drained auto-advance at compose time (#164/#572, §11j/§11k) |

This is a good machine-checkable ground-truth table for a future audit: `TRACKED_BACKUPS` (`common/paths.py`)
and the `PRECIOUS_BACKUPS` array in `.githooks/pre-commit` should always be the same 12 paths — a drift
between them means a precious table's export either never got wired to the hook or got wired without
registering in `TRACKED_BACKUPS` (which also governs pytest's export quarantine, `guard_tracked_backup`).

---

## 1a. Database engine: Postgres (isolated `governance` DB) — DECIDED 2026-06-26

The review DB moves **SQLite → Postgres now**, into a **dedicated `governance` database inside the existing
`lct_postgres` container, with its own DB user** (not commingled with the production LCT tables). Decided
after weighing a genuine SQLite steelman; the premise that justified SQLite ("a throwaway, single-stage
review cache") no longer holds once the app becomes the central, precious-state-bearing governance console.

**Why move now:**
- **Consolidation.** The project already runs Postgres 16 (Docker `lct_postgres`) + SQLAlchemy
  (`session_scope`) + a numbered migrations framework (`infrastructure/database/migrations/`, through 011) +
  `DATABASE_URL`/Supabase support in `connection.py`. SQLite was a *parallel* DB universe (own schema, own
  backup machinery). A now-central component should ride the project's primary stack — one engine, one
  migration story, one connection pattern.
- **Cloud / multi-machine readiness** is an existing road on Postgres (`connection.py` already reads
  `DATABASE_URL` "for production/cloud, e.g., Supabase") and a dead end on a file-bound SQLite.
- **Switching cost is lowest now** (review.db is 364 KB; the bulk — 345 MB of capture binaries — is on
  disk, engine-independent).

**Why a SEPARATE `governance` database (the isolation that kept the best SQLite argument):**
- The Stage-5 ingest does `DROP TABLE … CREATE TABLE` on the regenerable signal tables **every run**. In a
  dedicated database with its own user, that drop+rebuild **cannot reach** `districts` / `bell_schedules` /
  `lct_calculations`. One container to run; isolation preserved at the database boundary.

**What carries over unchanged:**
- **The JSON-backup pattern stays** (`labels.json`, `cluster_splits.json`, soon a state-events backup) —
  it is our **git-diffable portability + audit layer**, independent of engine. Not a reason to stay on
  SQLite; a keeper regardless.
- **Friction objection dissolves:** Docker is already a standing precondition for the project (CLAUDE.md
  Critical Rule #1), so the console needing it is not *new* friction.

**Migration scope** (its own step, §9): stand up the `governance` DB + user; port the current SQLite schema
(signals cache + precious `label`/`cluster_split`) to SQLAlchemy models + a migration; move the existing
data in from `review.db` (or rebuild cache + re-import the JSON backups); repoint `build_signals` / `server`
/ `harness` / `frontier` to `session_scope`. The drop+rebuild-on-ingest pattern stays, now scoped to the
governance DB. Supersedes the SQLite decision in `STAGE5_FILTER_DESIGN.md` (§Architecture).

---

## 1b. REQ-103 status — COMPLETE (2026-06-26)

**Decisions (locked, as built):** scope = **port + cross-stage cache together**; ORM =
**models for PRECIOUS tables, ingest-managed DDL for the REGENERABLE cache**; tests = **a real
Postgres fixture** (no SQLite stand-in). The governance DB connection lives in the acquisition tree
(`common/db.py`) and **never imports `infrastructure.database`** (the import-linter contract
enforces this — keep it that way).

**All of REQ-103 is now done.** 103a committed `3c725f3`; **103b–f committed `bbd0f66`**; **103c +
103g** in the follow-up pass. The old `data/acquisition/stage5_review/review.db` (SQLite) 103f reference
and `paths.REVIEW_DB` have since been **retired** (#126) — the governance Postgres DB is the sole working store.
**Next build step: REQ-099** (state event-log; §3).

### ✅ 103a DONE & committed (3c725f3) — additive, the live SQLite path is untouched
- **`governance` database + `governance_user`** exist in the `lct_postgres` container (verified).
  Recreate idempotently (lct_user is superuser) if ever needed:
  ```bash
  docker exec lct_postgres psql -U lct_user -d learning_connection_time -c \
    "CREATE ROLE governance_user LOGIN PASSWORD 'governance_pw'"      # guard: pg_roles
  docker exec lct_postgres psql -U lct_user -d learning_connection_time -c \
    "CREATE DATABASE governance OWNER governance_user"                # guard: pg_database
  docker exec lct_postgres psql -U lct_user -d learning_connection_time -c \
    "GRANT ALL PRIVILEGES ON DATABASE governance TO governance_user"
  ```
- **`infrastructure/acquisition/common/db.py`** — `Base`, `get_engine`, `session_scope`,
  `init_precious_schema()`. Config: `GOVERNANCE_DATABASE_URL` (cloud) or `GOVERNANCE_DB_*`
  (defaults → local container: host localhost, port 5432, name `governance`, user `governance_user`,
  pw `governance_pw`). Driver psycopg2, `postgresql://` URL.
- **`infrastructure/acquisition/stage5_filter/models.py`** — precious `Label` + `ClusterSplit`
  models on `Base`. `init_precious_schema()` create_all's them (caller imports the models so
  `common/` stays stage-agnostic). Verified create_all stands up `label`+`cluster_split`.
  **`init_precious_schema()` (`common/db.py:156-159`) now also imports the COMMON-level precious modules
  itself** — `calibration`, `gate_mode`, `discovery_policy`, `discovered_domain` — so `calibration_event`,
  `gate_mode`, `discovery_policy_event`, `discovered_domain`/`discovered_domain_decision` register on
  `Base.metadata` regardless of which caller reaches `init_precious_schema()` first (a common→common
  import is inside the base layer, so the layering contract permits it). A forgotten import used to
  surface as a bare "relation does not exist" at first write — the #217 review's finding that
  `calibration_event` was registered nowhere in the live app. STAGE-level precious models (like
  `Label`/`ClusterSplit` above) stay each caller's own responsibility; `common/` still doesn't import a
  stage module.

### ✅ As built
- **103b — `build_signals.ingest()`** runs in one `session_scope` transaction (atomic re-ingest).
  PRECIOUS `label`/`cluster_split` via `init_precious_schema()` (models, never dropped); the
  REGENERABLE cache via Postgres drop+rebuild DDL. `?`→named `text()` params; `INSERT OR IGNORE`→
  `ON CONFLICT DO NOTHING`; `executescript`→discrete execs; `REAL`→`double precision`. `models.py`
  gained `label.status server_default="unlabeled"` so the raw insert gets the DB-level default.
- **103c — cross-stage cache** (`ingest_cross_stage_cache`): `discovery_school` (Stage-2 funnel per
  school, with rolled-up wave counts + raw JSON), `candidate` (Stage-2 plan per URL), `capture`
  (Stage-3 receipt per hash — **incl. captures that never processed**), `processed_doc` (Stage-4
  thin; texts stay in `representation`). Regenerable; verified row counts match the source JSON
  (53 / 112 / 150 / 150 on `batch_00001`).
- **103d — readers** (`harness.py`, `frontier.py`, `process_governance/server.py`) on the governance
  session; server uses `.mappings()` to keep `r["col"]`/`dict(r)`, and `commit()`s before the JSON
  export so the backup only reflects committed state. Obsolete `--db` file flags dropped.
- **103e — tests:** `gov_session` fixture (`tests/conftest.py`) = real governance Postgres +
  connection-scoped **TEMP tables** (auto-dropped, skips if Docker down). `test_harness` +
  `test_tuning_frontier` migrated off in-memory SQLite; `test_stage5_cross_stage_cache.py` added.
- **103f — verified:** new ingest matches the reference `review.db` exactly (12 districts / 150
  records / 120 canonical / 150 labeled / 2207 representations / 12 district_target; tiers
  A47/B29/C15/D59; 9 clusters; identical labeled_topology). `labels.json` round-trips byte-identical.
- **103g — docs:** `DATABASE_SETUP.md` ("Two databases" section) + `GETTING_STARTED.md` pointer.

**The 4 (now 5) governance-DB consumers:** `build_signals.py`, `harness.py`, `frontier.py`,
`process_governance/server.py` (+ the `gov_session` test fixture). `paths.REVIEW_DB` / the old
SQLite file have been retired (#126).

---

## 2. What is precious vs regenerable in the release (a clarifying decomposition)

The release decision is **largely a deterministic projection** of inputs we already store:

```
release_content(district)  =  f( labels , signals , tier-config )      # PURE, regenerable
```

So `filtered.json`'s *content* needs **no new precious table** — it is recomputed from labels (precious,
stored) + signals (regenerable) + config (versioned). What **is** new-precious is the **act**:

- **the gate@5 release event** — "a human approved sending *this* district forward, at *this* time, at *this*
  `(config,labels,data)` fingerprint." Not derivable from labels; precious; part of lifecycle history.
- **the gate@1 queue-approval event** — same shape, one stage up.
- **(optional) explicit human representation overrides** — only if we ever support "hand-pick which reps
  go" (see §6 "selected"); deferred, since the current lean is *selected = scope, not override*.

This means: **the button computes the regenerable projection, writes `filtered.json`, and records a precious
release event.** Content is reproducible; the decision-to-send is durable history.

---

## 3. State schema — BUILT (REQ-099, 2026-06-26)

> **Built as designed below: Option B event log + a `current_state` SQL view** (both confirmed
> 2026-06-26). The log is **unified** (stage-progression + checkpoint events, one timeline);
> `current_state` derives the snapshot with **furthest_stage = MAX(stage)** (monotonic). The model +
> view + the migrated `district_status.py` live in `infrastructure/acquisition/common/district_status.py`;
> the in-memory `registry` contract is preserved (`record_stage`/`already_attempted` stay pure dict
> ops — no DB — so the stage scripts are unchanged; only `load()`/`save()` touch the DB). The existing
> 36-district / 84-event `district_status.json` was migrated in with zero snapshot mismatch, and that
> JSON is now the regenerable, git-tracked **backup** (re-importable via `import_status_json`). Tests:
> `tests/test_state_event.py`. The `event_type` vocabulary lands as: progression events use the
> `outcome` as `event_type`; checkpoint events use `approved`/`released`/… with `checkpoint` set.
> **A third shape (`remediate_contamination.py`, §11l):** `remediated`/`decontaminated` as the
> `event_type`/`outcome` pair, with neither `stage` nor `checkpoint` set — recording a decontamination run
> as its own distinct event kind, outside both the stage-progression and the gate vocabularies, so it can
> never be mistaken for either.

The user flagged that state "gets scattered" — a district can be *released for what we have* **and**
*re-queued for more discovery* at once. A single status-per-district row breaks on that. Two options:

- **Option A — current-state row per district** (`district_state(district_id, stage, status, updated_at)`).
  Simple; but the multi-state / re-discovery case forces awkward enum gymnastics, and there's no history.
- **Option B — event log + derived current state** (event-sourced). Append lifecycle **events**; "current
  state" is a projection/view over them. Re-discovery is just another event, not a contradiction; full
  audit history falls out for free.

**Recommendation: Option B.** It matches the project's strong lineage/transparency theme (the tuning ledger,
fingerprinted scorecards, label backups) and handles "scattered" natively. Sketch:

```
-- PRECIOUS (backed to a versioned JSON, re-importable):
state_event(
  event_id INTEGER PK, district_id TEXT, stage TEXT, checkpoint TEXT,   -- 'gate@1'|'gate@5'|'gate@6'|'gate@7'|'gate@8'|NULL (§11; was CP-A/B/C)
  event_type TEXT,        -- queued | approved | released | re_discovery_requested | dispatched | ...
  fingerprints_json TEXT, -- (config,labels,data) at the moment, when relevant
  actor TEXT,             -- 'human' | 'auto'  (eases toward automation: same rows, actor flips)
  note TEXT, created_at TEXT)

-- DERIVED VIEW (regenerable from the log):
current_state(district_id) = latest projection per (stage, checkpoint)
```

A district re-sent to discovery has a `re_discovery_requested` event *after* a `released` event — both true,
no conflict; the view shows both facets. **Open:** exact `event_type` vocabulary + whether `current_state`
is a SQL view or a materialized table. Confirm before building.

**This is the migration target for `district_status.py`.** Its current functions (cross-stage registry,
1→5) become writers/readers over `state_event`; the old `district_status.json` is demoted to a generated
**index/view** (or retired). `district_status.py` already lives in `common/`, so this is a function
migration, not a code move.

---

## 4. The record→representation descent (the deterministic release rule)

Settled with the user (2026-06-26): **send ONE best representation per qualifying canonical record.** The
scale math forces it — 12 districts = **2,206 representations / 345 MB**; at ~17k districts ≈ **3.1M reps /
~490 GB**, of which the council should see ~40–60 files. The **"council can request more evidence in Stage
7"** mechanism is the pressure valve: the initial send is aggressively minimal because under-sending is
recoverable.

**The descent (deterministic, no AI — the Stage 5 binding constraint):**
1. **Qualifying records** = canonical (cluster rep / singleton, non-duplicate) records that pass the
   release rule (label says target where labeled; else the recall-biased auto-filter on tier/score —
   REJECT only the high-precision negatives, per the recall-bias stance in `STAGE5_FILTER_DESIGN`).
2. **One best representation per record:**
   - default → the single best **text** rep (max usable time-density), *not* all text reps (the council's
     value is cross-*model* consensus, not cross-*extraction* redundancy);
   - `visual_text_gap` / `target_image_only` → the **image** instead (text never captured the content);
   - **handbook** → the `harvest_pages` slice(s) (the schedule page image/text), never the whole doc.
3. **Carry per record:** tier, the de-chromed signals, category hypothesis, cluster membership (rep only),
   `harvest_pages`, `emergent`, `intended_schools`, honest label (`gross_bell_to_bell`, REQ-055).

Representation-level human override (e.g. "text is garbage, send the image") is carried today by the
`target_image_only` flag; **start with the existing flag vocabulary** (user: "comfortable with where we're
at") and extend only if labeling reveals a gap.

---

## 5. Artifacts: `filtered.json` (per district) + `handoff` (per dispatch)

Council = **OpenRouter API calls** from our laptop orchestrator → external, so a structured hand-off is
warranted even though the orchestrator is in-process (auditability, DB-schema decoupling, the request-more
loop). Two artifacts, two lifetimes:

### `filtered.json` — per district dir, REGENERABLE export
The materialized release projection for one district. Lives beside the other per-district JSON. Overwritten
on regenerate. Stamped with `(config,labels,data)` fingerprints so staleness is detectable (§6). Shape
(sketch):
```
{ district_id, generated_at, fingerprints:{config,labels,data},
  topology, completeness, nces_denominator, cost_estimate,
  records:[ { rec_key, url, tier, category, emergent, intended_schools,
              send:[ {representation_file, kind, page?} ], harvest_pages? } ] }
```
It is the human-auditable **receipt** of the release decision, not a stage-to-stage transmitter — Stage 6
reads the working data (records / representations / the release decision) from the DB, with the binaries on
disk by path; `filtered.json` mirrors that decision for inspection and carries the district-level
**go/no-go summary** (topology / completeness / cost) Stage 6 needs. District-level metadata lives
**inside** each `filtered.json` (self-contained); a thin generated **Stage-6 index** avoids re-scanning
thousands of dirs at scale. *(Stage 6's exact read-path + the dispatch freeze are settled in
`STAGE6_DISPATCH_DESIGN.md`.)*

### `handoff_<hash>_<timestamp>.json` — Stage 6, IMMUTABLE dispatch record
"Which districts we sent to the council in *this* run, and exactly what." **Immutable snapshot** — a new
dispatch is a new file; never regenerated. **Freezes** each district's `filtered.json` content (or its
fingerprints) *at dispatch time*, so a later regeneration (retune / re-discovery) can't silently rewrite
history — required by the request-more-evidence loop and for "what did we actually send on date X." Carries
the council config (which models) + total cost estimate + the **`verified_only`** dispatch-mode flag (a
gate@6 toggle for a labeled-targets-only, training-grade dispatch — folded into the identity hash so a
training-grade dispatch never collides with a default one). A `dispatched` `state_event` references its hash.
*(As-built detail: `STAGE6_DISPATCH_DESIGN.md` §0/§3D/§3E.)*

---

## 6. filtered.json is EVENT-DRIVEN — no manual trigger (REVISED 2026-06-26, REQ-094)

> **Supersedes the earlier "Generate button" framing.** `filtered.json` is **not** human-triggered and
> is **not** the CP-B release record. It is a continuously-maintained, regenerable **projection** of the
> governance DB — `content = f(labels, signals, config)` — that the events log keeps fresh. The *release*
> (which package of representations goes to which OpenRouter model set/config) is a **separate Stage-6
> routing decision (REQ-100)**, not an act of generating this file.

**The granularity shift that forces this (user, 2026-06-26):** at Stage 5 the **batch dissolves as a
meaningful unit** — work is per-URL/per-representation. **CP-B is the per-URL review of representations**
(the human labeling surface), not a batch-level "release" gate. So there is nothing to "press a button
for": each per-URL judgment is an event, and the district's projection should simply reflect the latest
events at all times.

**What generates / updates `filtered.json` (all events — built REQ-094):**
| event | mechanism | covers |
|---|---|---|
| **a Stage-4 batch completes (the handoff)** | `build_signals.ingest_batch(district_ids)` runs the **incremental** ingest + `release.generate(district_id=…)` for just that batch (§12) | the first scoring pass for a freshly-processed batch — batch-scoped, no full-corpus rebuild |
| **a human label is applied / a cluster is split** | `server.save_label` / `split` call `release.generate(district)` for that district | CP-B per-URL judgments flow into the projection immediately |
| **new URLs/representations from more discovery** | a re-ingest (capture→process→`build_signals`) regenerates | additional evidence changes the canonical set |
| **a full rebuild** | `python3 -m …stage5_filter.build_signals` (`ingest()` then `release.generate()` over all) | schema changes / recovery — the all-districts drop+rebuild |

`release.generate()` is the **single shared code path** (the function the ingest hook, the label hook, and
a future `state_event` projector all call); `python3 -m …stage5_filter.release` remains as a manual
full-regen utility. The descent is deterministic, no AI (governance §4).

**Staleness is still a fact, for the console to surface — not a trigger.** Each `filtered.json` is stamped
with **per-district `(config,labels,data)` fingerprints** (scoped to that district so a change elsewhere
doesn't mark it stale). Because generation is event-driven, a district is normally never stale; the
fingerprint stamp exists so the console (REQ-100) and the **Stage-6 dispatch** can detect drift between
*what was generated* and *what was last dispatched to the council* (the request-more-evidence loop). A
fuller `state_event`-subscription projector (regenerate exactly the affected districts off the log) is the
natural REQ-100 generalization of today's two inline hooks (tracked: #100).

**Open (deferred to REQ-100):** should a *config* retune eagerly regenerate all districts (honest, noisy)
or be surfaced as a separate "config drifted" signal? Lean: stamp all three fingerprints, let the console
decide. The `{labeled}` vs `{all}` qualification basis (human labels only vs. also letting unlabeled
high-tier records flow on the recall-biased auto-filter) is a property of `release.decide()`, already built.

---

## 7. App scope: the review app → stage-selectable governance console (`process_governance`)

The "Stage 5 - Capture Review" title by the wordmark becomes a **stage selector**; each stage swaps the
view/controls. Once cross-stage STATE is in the DB, the app is the governance console for every gate
(see §11 for the full gate model):

- **Stage 1 / gate@1** — review & approve queued `batch_*.json` (today out-of-band); an approval event.
- **Stage 5 / gate@5** — the **district-driven, attention-first** review/label console (REQ-112, 2026-06-29;
  scoring V2 = labeling functions + combiner, REQ-113; **v2.1 three-axis labeling** — target shape / confounder
  facets / location — REQ-114, 2026-07-01). District-driven on purpose (the batch dissolved). `filtered.json`
  is an event-driven projection, not a Generate button (§6). Detail: `STAGE5_FILTER_DESIGN` (present-state rewrite).
- **Stage 6 / gate@6** — approve the dispatch (which reps → which council config).
- **Stage 7 / gate@7** — review the council's requests/recommendations.
- **(later) Stage 8 / gate@8** — review per-band results before the mechanical Stage-9 DB write (the effective old "CP-C").

### Code structure — DONE (REQ-098)
- **Move the app** the Stage-5 review app (server + `static/`) → **`infrastructure/acquisition/process_governance/`** (a top app layer, cross-stage). *(Done in REQ-098: relocated out of `common/` after import-linter flagged the common-imports-stages inversion; renamed console→process_governance for a slightly broader scope.)*
- **Keep stage logic with its stage:** `build_signals.py` is Stage 5 ingest/signal logic, not app logic →
  move it to **`stage5_filter/build_signals.py`** (out of the app's subfolder). The thin console
  imports each stage's logic; per-stage ingest/views live with their stage.
- **Update the `sys.path`/imports** that reach into `process_governance` today: `stage5_filter/harness.py`,
  `stage5_filter/frontier.py`, `tests/test_tuning_frontier.py`, `tests/test_stage5_scoring.py`.
- **Risk:** this touches the tested tuning code we just shipped (REQ-095/096). Do it as one mechanical,
  test-guarded move (the 36 Stage-5 tests are the safety net), **before** new feature work — not interleaved.

---

## 7a. The governance app: orchestration, jobs & Stage 2 headless discovery — DECIDED 2026-06-26

The app's six surfaces (overview/lifecycle · stage selector · checkpoint actions · tuning console ·
funnel dashboards · orchestration triggers) align with the user's mental model. Four architecture
choices its shape forces, all decided:

**A. Cross-stage cache — YES.** The DB ingests *all* stages' artifacts (discovery/candidates/capture/
process) as queryable tables, not just Stage 5 — surfaces 1/2/5 need it. This **scopes REQ-103**: the
Postgres migration builds the cross-stage cache now. The DB holds the working store for all stages
(regenerable from disk), as it does for Stage 5 today; the per-stage JSON + binaries on disk are the
regenerable receipt/recovery layer. **Reframe (user):** the district-dir JSON files shift role from *data
carriers through a transformation* to **auditable receipts** — the DB is the working store, the JSON is the
on-disk audit trail.

> **UPDATE 2026-06-28 (REQ-110) — the cross-stage cache became a LIVE working store, not a
> dropped-each-ingest cache.** As first built (103c), the cache was populated *only* by the monolithic
> Stage-5 `build_signals.ingest()` (`DROP`+rebuild over every district with all of discovery+captures+
> processed), so for an in-flight batch the console had nothing fresh to read — Stage 2's console fell back
> to parsing `discovery.json` off disk, leaving the cache unused for its stated "surfaces 1/2/5 need it"
> purpose. The fix made the cache match this section's intent: schema + per-district UPSERTs moved to
> **`common/cache_ingest.py`** (stages are independent siblings — the ingest can't live in `stage5_filter`);
> the four tables are `CREATE IF NOT EXISTS` + **never dropped** (still rebuildable from disk, the
> authoritative source); and **each stage's `finish` hook** projects its district's slice in. The console
> now reads the DB working store (Stage 3 from the start; Stage 2 repointed, self-healing for pre-hook
> batches). Disk stays authoritative for DATA (§1); the DB is the queryable projection, now kept live.

**B. Orchestration = callable functions, polyglot.** Triggers invoke stage logic as **functions** so the
app *and* a future scheduler share one path (`actor` flips human→auto, no code change). Stages 2–3 are
Node → the orchestration layer manages subprocesses across languages. Goal: maximize deterministic
auto-advance; humans gate only at checkpoints, loosening over time.

**C. Job runner — simple now.** Long stages (discovery/capture/extraction) run as background work with
status as **events in the log** (`dispatched`/`completed`/`failed` → the job board is a projection). No
Celery/Redis yet; revisit when we have data on concurrent high-volume behavior. *Option noted:* the
Claude Code CLI ships a background-session **supervisor** (`claude … --bg`, `claude agents --json`,
`claude logs <id>`, `claude stop <id>`, `claude daemon status`) we could lean on instead of rolling our own.

**D. Actor identity — rich from day one.** The `state_event.actor` field holds *identity*
(`ian`, `auto:scheduler`, `auto:drift-detector`), not just `human|auto` — cheap insurance for the
multi-user cloud future (Supabase path) so "who did this" is always captured.

### Stage 2 discovery — UPDATED 2026-06-28: deterministic SERP cascade (claude -p demoted to Wave 2)

**SUPERSEDED:** the "Stage 2 = headless `claude -p` Wave-1 per district" design below was BUILT, then a
five-provider bake-off (53-school known-positive set, `data/acquisition/diagnostics/`) overturned the
Wave-1 choice. The pluggable-provider layer was the right call; the *provider* was wrong. **Current
architecture (authority: `STAGE2_DISCOVER_DESIGN.md` §7):**
- **Wave 1 = Bright Data SERP** (`discover.brightdata_search`) — real Google, `site:`-scoped, 5,000/mo
  **recurring** free tier (98% recall) — with **Serper failover** (`serper_search`, banked credits, 100%)
  ONLY on a Bright Data API failure. Same Google index, so Serper is uptime backup, not recall.
- **Wave 2 = Claude WebSearch** (`claude -p`, the headless helpers below) on the genuine residual — a
  *different* index, speculative; degrades to manual_flag.
- **Stage 2 is now fully DETERMINISTIC** — no agent in the Wave-1 loop, no structured-output flake.
- **Cost reframe:** Stage 2 is no longer "≈free subscription quota." Bright Data/Serper are cheap REAL
  cash (~$0.001–0.0015/query, ~$21 per full 17k pass); only the residual Claude tier is subscription.
- **Index lesson:** raw Google wins; own-index providers (Perplexity 43%) crater on long-tail K-12.
- **Run live** through the console on batch_00002 + batch_00003 (2026-06-28).

The `claude -p` design below is **retained because Claude is now the Wave-2 residual provider** (and the
`scripts/stage2_cli_reliability.py` diagnostic harness). The cost/auth reasoning still applies to that tier:

The "subagent requires a chat (Claude) open" framing is **dissolved**. Each `claude -p` invocation is a
*full headless agent*; we don't need the subagent abstraction. The Wave-2 residual orchestrator shells out
to `claude -p` (one call over a district's residual schools), returning JSON; the deterministic
gating/flatten logic is unchanged. No chat, no human-in-loop, **schedulable overnight**.

**Search providers are a pluggable layer (extensibility — explicit requirement).** Each provider sits
behind one contract — *given a school, return candidate URLs* — so providers can be added, reordered, or
swapped without touching gating/flatten/dedup. **This is exactly what let Bright Data/Serper replace the
Claude/OpenRouter waves** with no change to the deterministic tail.

**Why CLI, not the Agent SDK (decisive — cost):** the CLI uses **subscription auth** (Pro/Max quota) when
logged in; the **Agent SDK requires `ANTHROPIC_API_KEY` = per-token billing** (its overview explicitly
disallows claude.ai login for SDK-built products). The whole point is leveraging the existing
subscription, so CLI wins. *Verified clean:* no Claude API account exists → no `ANTHROPIC_API_KEY` to
shadow the subscription (the only keys present are OpenRouter / Perplexity / Gemini / Serper / Bright Data,
none of which is Claude Code auth).

**The call (VERIFIED against CLI 2.1.71 + a live smoke test, 2026-06-27 — the earlier `--bare`/
`--max-turns` were guessed and DO NOT EXIST; this is what's actually built in `stage2_discover/headless.py`):**
```bash
# prompt is piped on STDIN (robust to long rosters), not passed as an argv positional
printf '%s' "<stage2 search prompt>" | claude -p --model haiku --effort low \
  --output-format json --allowedTools "WebSearch" \
  --json-schema '<WAVE1_SCHEMA>' --strict-mcp-config --disable-slash-commands
```
- `--allowedTools "WebSearch"` is **required** in headless (print mode can't answer a permission prompt).
  Confirmed live: WebSearch fires (`modelUsage[*].webSearchRequests` ≥ 1 — note the top-level
  `usage.server_tool_use.web_search_requests` can read 0; the per-model counter is the accurate one).
- `--effort <low|medium|high>` (NOT `--effortlevel`).
- **`--bare` and `--max-turns` do not exist.** The lean-scripted-start intent is served by
  `--strict-mcp-config` (ignore MCP) + `--disable-slash-commands` (no skills); the full search prompt is
  passed in, not invoked as the `stage2-discover` skill. (CLAUDE.md still auto-loads from cwd — minor.)
- **`--json-schema '<schema>'`** forces structured output. CONFIRMED: with `--output-format json` it
  lands on a dedicated **`structured_output`** envelope key (the `result` field is only the agent's prose
  summary) — `headless._extract_result_payload` reads `structured_output`.
- **Reliability caveat (measured):** Haiku intermittently returns subtype
  `error_max_structured_output_retries` (exit 1 *with* a valid JSON error envelope) — a non-deterministic
  flake, NOT a hard failure. `run_claude_cli` parses-stdout-first and bounded-retries it; the effort×schema
  recall/flake tradeoff is being measured (`scripts/stage2_cli_reliability.py` → `data/acquisition/diagnostics/`).
- A denied WebSearch is caught explicitly (would otherwise look like a genuine empty result — the
  batch_00001 Wave-1 under-report failure class).
- Background option: `--bg` + `claude agents --json` / `claude logs <id>` (ties to choice C).

**Per-stage cost model** (REVISED 2026-06-28, feeds `filtered.json`/`handoff` estimates): **Stage 2
discovery → cheap REAL cash via Bright Data/Serper SERP** (~$0.001–0.0015/query; ~$17–21 per full 17k
pass; Bright Data's 5,000/mo free tier covers batch-scale), only the residual Claude tier is subscription;
**Stage 7 extraction → paid OpenRouter API** (still the expensive stage). Recall is still cheap relative to
extraction, so *aggressive Stage-2 recall* remains the right posture.

**REQ-104 BUILT 2026-06-28** (run live on batch_00002/batch_00003). The original open item (claude -p
WebSearch rate limits at 17k overnight volume) is moot — Claude is no longer the Wave-1 provider; Bright
Data offers unlimited concurrency. Detail: `STAGE2_DISCOVER_DESIGN.md` §7.

---

## 7b. Console — running UI notes (deferred from the plumbing; revisit at console-build, REQ-100/102)

A scratchpad of console/UI-relevant questions the plumbing work raises, captured so context resets don't
lose them. **No layouts yet** (user's call) — these are *things the eventual UI must expose or decide*,
recorded as they surface:

- **Data source flips SQLite→Postgres** (REQ-103): the console reads/writes via `session_scope` against the
  isolated `governance` DB, not a local SQLite file. The "open a file, no Docker" ergonomic of the old
  review app goes away — the console now requires the container up (already a project precondition).
- **Home view = a projection over the event log** (REQ-099): "what needs my attention" is a query, not a
  static list. **REALIZED for Stage 5 (REQ-112):** the left pane is an **attention queue** — districts
  sorted by the inverted-confidence attention score (`STAGE5_FILTER_DESIGN` §A), not a stage tree. (A
  cross-stage Overview attention queue is still the Overview's job.)
- **Stage selector** (the wordmark combo box) swaps views per stage; CP-A (queue), CP-B (release), later
  CP-C (write). Open: which stages get a *read* view vs an *action* surface.
- **Generate/Release trigger + staleness** (REQ-100/§6): each district shows new/current/stale from the
  three stamped fingerprints (config,labels,data) — the UI must let the human filter by *which* changed.
- **Tuning console surface** (§10 / REQ-095/096): the advisory frontier (with which-records-move) and
  ledger history — where they live in the UI is still open. **REQ-097 (drift) shipped narrower than this
  note anticipated:** not a tuning-console surface, an advisory "retune recommended" badge on
  `/api/progress` (`stage5_filter/drift.py`) — pure-read, never auto-retunes.
- **Orchestration triggers** (§7a-B/C): "run next stage" buttons dispatch background work whose status is
  itself event-log rows; the UI needs a job/attention view fed by those events.
- **Actor identity** (§7a-D): single-user now, but the event log carries identity — the UI should capture
  "who" (login/operator) once multi-user (cloud) arrives.

---

## 8. Open decisions

> **HISTORICAL — fully resolved.** Every item below was open during the design phase and is now decided
> (folded into §1–§7); kept in place (not renumbered) because `governance §8` is cross-referenced elsewhere.
> Read as a retrospective, not a live decision queue.

**RESOLVED 2026-06-26:** ~~Database engine~~ → Postgres, isolated `governance` DB (§1a). ~~Council
in/out-of-process~~ → out-of-process (OpenRouter); `filtered.json` + `handoff` warranted (§5).
~~record→rep descent~~ → one best rep (§4). ~~`filtered.json` role~~ → regenerable export, not primary
store (§2/§5). ~~State model granularity~~ → **Option B, event log** (§3). ~~Staleness policy~~ → **stamp
all three fingerprints (config,labels,data); console filters by which changed** (§6). ~~Cross-stage cache~~
→ **YES, all stages (§7a-A)**. ~~Orchestration~~ → **callable functions, polyglot (§7a-B)**. ~~Job runner~~
→ **simple/events-as-log now (§7a-C)**. ~~Actor identity~~ → **rich `actor` from day one (§7a-D)**.
~~Stage 2 chat-bound~~ → **headless `claude -p`, subscription-billed (§7a)**.

**Still open (gating the build):**
1. **State model granularity** — RESOLVED Option B; `event_type` vocabulary still to finalize during §3 build.
2. **Staleness policy** — RESOLVED stamp-all-three.
3. **Code-move decomposition** (§7): app→`process_governance/`, `build_signals`→`stage5_filter/`, names.
4. **Stage-6 index** (§5): a generated index file vs scan-the-dirs (lean: index, for scale).
5. (Parked from `STAGE5_FILTER_DESIGN` §"Path to filtered.json") the exact REJECT rule + rank order for
   the auto-filter — unchanged in intent, now lands in the generator of §4/§6.

---

## 9. Sequencing (proposed — prove the data model before the console UI)

> **HISTORICAL — fully executed.** All 8 steps below shipped (REQ-098/103/099/094/100/101/102/104); this
> is the build-order plan as it was proposed and then revised in-place, kept for the reasoning trail. Kept
> in place (not renumbered) because `governance §9` is cross-referenced elsewhere.

Don't stall the actual goal (representations → council) behind an app re-architecture. Order:

1. **Package + code move + tooling baseline** (§7, §10): convert `infrastructure/acquisition/` to a proper
   installable package (`pyproject.toml`, real imports, **kill the `sys.path.insert` shims**) — packaging is
   the highest-leverage prerequisite for the static-analysis tools (§10); then the review app → `process_governance/`,
   `build_signals`→`stage5_filter/`, fix imports, green the tests; then wire the proven tool baseline
   (import-linter + grimp + vulture; dependency-cruiser for the `.mjs` side). *(REQ-098)*
2. **Postgres migration + cross-stage cache** (§1a, §7a-A): stand up the isolated `governance` DB + user;
   port the schema to SQLAlchemy models + a migration; **ingest all stages' artifacts (not just Stage 5)**;
   move existing data in (or rebuild cache + re-import JSON backups); repoint `build_signals`/`server`/
   `harness`/`frontier` to `session_scope`; green the tests. *(REQ-103)*
3. **State schema + migrate `district_status.py`** to `state_event` + backup/restore (§3), in Postgres. *(REQ-099)*
4. **The release generator + `filtered.json` export** (the record→rep descent, §4/§5) — *this hits the
   council-payload goal* — written tests-first, scored against labels via the harness. *(REQ-094, refit)*
5. **The Generate trigger + staleness UI** in the console (§6). *(REQ-100)*
6. **Stage-6 `handoff` + index** (§5). *(REQ-101)*
7. **CP-A view / stage selector** (§7) — the console UI, onto a state model already proven by 3–5. *(REQ-102)*
8. **Stage 2 headless conversion** (§7a) — orchestrator shells out to `claude -p` per district; retire the
   chat-bound subagent model; verify WebSearch/subscription rate limits at volume first. *(REQ-104)*

Steps 1–2 are foundational and **independent of the still-open decisions** (§8 #1 state-model, #2
staleness) — they can proceed while those settle. Steps 3+ need those rulings. REQ numbers provisional
(094 reused for the now-DB-backed release; 098/099/103/100–102 new). Each pre-registered tests-first per
the workflow. Drift detector (REQ-097) still waits for batch 2.

**Confirmed build order (user, 2026-06-26):** install tools (step 1) → CP-B App → Governance App evolution
(steps 3/5/7) → Stage 5→6 dispatch (step 6). **Doc-update obligations attached to steps:**
- *Now (this pass):* `docs/DATA_SOURCES.md` gains a reference to `docs/ACQUISITION_PIPELINE.md`; the toolchain
  is recorded here in §10 (user: keep it in this note for now, not a separate file — extract later if it grows).
- *On REQ-103 completion (Postgres+Docker migration):* update `docs/DATABASE_SETUP.md` and
  `docs/GETTING_STARTED.md` for the new isolated `governance` DB (these are deferred until the migration lands).

**SHARPENED 2026-06-27 — `batch_00002` is the FORCING FUNCTION; build is console-first, stage-by-stage.**
Steps 1–4 are DONE (REQ-098/103/099/094, all `tested`). The §9 lean toward "prove the data model before the
console UI / don't stall the goal behind the app" is now **superseded for `batch_00002`**: rather than
hand-running scripts to reach the council fast, we deliberately drive **console development stage view by
stage view**, with `batch_00002` as the vehicle that forces each view to exist. The batch-of-record is
**created and advanced ONLY through the console** (hand-run `queue_batch.py` is dev/test only). Goal: a
**self-governing, self-sustaining** app via the **ramp-up model** (manual gates + high supervision now,
easing back later). Order from here: **gate@1 console view (REQ-102, first deliverable) → create
`batch_00002` there → walk it: Stage 2/3/4 status + orchestration triggers → gate@5 (integrate the existing
review surface) + the REQ-044 recency gate → Stage 6 + gate@6 (REQ-101).** Scope ends at **gate@6 approval —
no paid dispatch** (Stage 7 out of scope this pass). The four steps 5–8 REQs are now registered (no longer
"provisional"): REQ-100 (staleness view), REQ-101 (Stage 6 dispatch), REQ-102 (gate@1 view), REQ-104 (Stage 2
headless). **Correction:** the *currency/recency* gate is **REQ-044** (a Stage-5 filter enhancement), not
REQ-104 — REQ-104 is the Stage 2 headless conversion.

> **BUILD PROGRESS (updated 2026-06-28): gate@1 FULLY built — backend + frontend (REQ-102), §9 step 7
> DONE.** The batch is a first-class governance-DB entity (the working store) + the gate@1 console API +
> the queue-review UI; **`batch_00002` was created, edited, and approved end-to-end through the console**
> (the forcing-function milestone). See **§11h**. Next on the data path: walk `batch_00002` into Stage 2,
> then REQ-100 (staleness view), REQ-101 (Stage 6 dispatch).

---

## 9a. REQ-098 execution plan — package + code move + tooling (drafted & approved 2026-06-26)

> **HISTORICAL — fully executed.** REQ-098 shipped (the package move, absolute imports, the
> import-linter/grimp/vulture/dependency-cruiser tooling in §10). Kept for the reasoning trail behind that
> migration; kept in place (not renumbered) because `governance §9a` is cross-referenced elsewhere.

The detailed sub-plan for §9 step 1. Persisted so a cold start can execute it.

**The key enabling insight:** an **editable install** (`pip install -e .`) registers `infrastructure` as an
importable package, so an absolute import (`from infrastructure.acquisition.common import paths`) resolves
*regardless of cwd or how a script is launched*. Therefore `python3 infrastructure/acquisition/.../x.py`
keeps working unchanged — **no invocation churn across the ~12 docs/skills** that reference that pattern.
The only new setup step is a one-time `pip install -e .`.

**Grounding facts (from the 2026-06-26 audit):**
- Acquisition is a clean internal DAG: `common/` (paths → config_loader/discover/district_status) is the
  base; stages depend on common, not each other; `aggregate.py` is a pure leaf.
- **Sanctioned cross-cluster imports already exist and are THE POINT of the pipeline:** `stage1_queue`
  reads `infrastructure.database.{connection,models}` (enrollment for the queue); `stage9` will *write*
  minutes back. These are named boundaries in the contracts, not violations.
- `infrastructure/` is currently a namespace package (no `__init__.py`) that works only because pytest runs
  from repo root — the fragility the editable install removes.
- Rewrite scope: ~13 acquisition modules + ~14 test files swap bare imports (`import paths`) for absolute;
  33 `sys.path.insert` shims get deleted.

**Steps (suite green at 0 and 3+; mid-2 is transiently mixed, all git-reversible):**
0. **Scaffold** — `pyproject.toml` (minimal: metadata + setuptools find `infrastructure*`; deps stay in
   requirements.txt for now), `__init__.py` in `infrastructure/` + every acquisition subpackage,
   `pip install -e .`, smoke-test `python -c "import infrastructure.acquisition.stage5_filter.harness"`.
   *(Validate the editable install resolves the package cleanly — the one early risk; fallback is the
   `infrastructure/__init__.py` we're adding anyway → plain regular package.)*
1. **Moves (git mv):** the Stage-5 review app `{server.py,static/}` → `process_governance/`;
   `build_signals.py` → `stage5_filter/build_signals.py`. Moves first → rewrite once.
2. **Rewrite intra-acquisition imports to absolute** (final layout), file-by-file (modules, then tests),
   leaving the redundant `sys.path.insert` lines temporarily; run relevant tests per file.
3. **Strip all 33 `sys.path.insert` shims.** Full suite green (997).
4. **Wire Python tools** — dev-deps `import-linter`/`grimp`/`vulture`; `.importlinter` contracts (below);
   run `lint-imports` + a `vulture` sweep; fix/encode findings.
5. **Wire Node tool** — `dependency-cruiser` npm dev-dep in `infrastructure/scraper/` + rules config; run.
6. **Docs** — add `pip install -e .` to GETTING_STARTED; confirm no invocation references broke.

**import-linter contracts to encode (step 4):**
- **Layers/forbidden:** `common` is the base — stages may import it; `common` must NOT import any stage.
- **Independence:** the stage packages 1–8 do not import each other. **Stage 9 is the exception:** it is a
  layer *above* the independent group (it consumes gate@8's `approval`/`closing_argument` — the canonical
  readers whose `fingerprint` logic it must match, not duplicate); nothing earlier may import it.
- **Forbidden + exceptions:** `infrastructure.acquisition` must not import `infrastructure.database` internals
  *except* the sanctioned `stage1_queue` enrollment read and the `stage9_incorporate.incorporate` write
  (BUILT 2026-07-21) — encode via `ignore_imports`.
- **Forbidden (reverse):** the LCT side (`infrastructure.database`, `infrastructure.scripts`) must not import
  `infrastructure.acquisition` — keeps the two clusters decoupled (the separation confirmed in the
  requirements review).

**Import-rewrite map (bare → absolute):** `paths`/`config_loader`/`discover`/`district_status` →
`infrastructure.acquisition.common.*`; `school_sampling`/`queue_batch` → `…stage1_queue.*`;
`discover_stage2` → `…stage2_discover.*`; `capture_stage3` → `…stage3_capture.*`; `process_stage4` →
`…stage4_process.*`; `build_signals`/`harness`/`frontier`/`tuning_ledger` → `…stage5_filter.*`; `aggregate`
→ `…stage8_aggregate.*`; `console/server.py` imports `…stage5_filter.build_signals`.

---

## 10. Tooling: dependency tracing, dead-code & architecture enforcement — DECIDED 2026-06-26

Adopted to **equip the agent to monitor/manage** the codebase (machine-readable, CLI/CI-driven — not
browser dashboards) and to keep this infrastructure investment from eroding. Research basis (saved):
`docs/technical-notes/POLYGLOT_PIPELINE_ARCHITECTURE_TOOLCHAIN.md` (Perplexity deep-research) + the
earlier scratch-paper passes. Kept in this note for now (user's call) — extract to its own note only if
it grows.

**The prerequisite — packaging (highest leverage).** The acquisition tree's pervasive `sys.path.insert`
+ in-function imports make static import-analysis coverage of inter-stage dependencies *near zero*.
Converting to a proper installable package (real `import` paths) is **categorical**, not incremental, for
tool accuracy — so it's folded into REQ-098 step 1, before the tools are wired. A pre-packaging tool spike
would mostly surface `sys.path` noise; **package first, then the tools light up.**

**Three-layer model (no single tool spans it — confirmed by both the agent and the research):**

| layer | covered by | adopt |
|---|---|---|
| **Intra-Python graph + contracts** | `import-linter` (contracts: layers/forbidden/independence) on `grimp` (queryable graph); `vulture` (dead code) | **now** (REQ-098) |
| **Intra-Node graph + contracts** | `dependency-cruiser` (rule engine + schema-validated JSON; the import-linter analog for `.mjs`/TS) | **now** (REQ-098) |
| **Cross-boundary edges** (Python→subprocess→Node/CLI · shared `config/*.json` read by both · file-based stage dispatches) | **no tool** → a hand-declared `arch-manifest.json` + **fitness-function tests** (AST scan of `subprocess.*` / config-path reads, asserted against the manifest); `datacontract-cli` for stage-dispatch schema validation | **FIRST INCREMENT BUILT (#124, 2026-07-09):** `arch-manifest.json` (repo root) + `tests/test_arch_manifest.py` — fitness functions asserting (1) every external-process edge (argv-list head, surviving the injectable `_run` seam — `claude`/`node`/`pdftotext`/`pdftoppm`/`pdfinfo`/`tesseract`) is declared, (2) an invariant guard (`assert_runnable`) is reached by every declared entry point (AST-scanned), (3) no client JS compares against a server-authoritative literal (`batch_00000`), (4) a shared client helper (`statusBadge`) is defined once, (5) each stage receipt's producer references its filename, **(6) a receipt loader declared `cli_only` is never referenced outside its CLI (#526, 2026-07-18) — `load_batch_any`'s only current entry, a name-presence scan over `process_governance/` rather than an AST call-graph walk, deliberately: it's a whole-directory negative check with no single function to anchor an AST walk on, and the broader scan is the more conservative choice for that shape.** Each check was proven to FAIL on a deliberate drift then revert. **Still to add:** `config/*.json` schema validation (now largely covered separately — see `shared_config` in the manifest + `tests/test_config_schemas.py`) + `datacontract-cli` on the stage-dispatch artifacts (a bigger, separable piece; the artifacts are declared in the manifest's `file_dispatches` ready for schema refs). |

**Concrete contracts to encode (import-linter), once packaged:** stage *layering* (1→…→9); *forbidden* —
no stage imports the production LCT/database layer's internals (enforces the STATE-vs-DATA + DB isolation
boundary); *independence* among stages that shouldn't know each other; `common` is a base layer everything
may import but which imports no stage.

**Chosen over the alternatives (proven > novel, for an agent driver):** `import-linter` over **Tach**
(longer history, denser docs, stable CLI/config); `dependency-cruiser` over **madge/skott** (rule
enforcement + schema-validated JSON, not just visualization). **Deferred / evaluate-later:** the MCP
code-intelligence servers (`codebase-memory-mcp`, `Code Pathfinder`, …) — the most direct "give the agent
a queryable cross-language graph" path, but too new (2026) and license-varied (GitNexus is noncommercial)
to bet the architecture on; revisit as a separate spike. Browser visualization (pydeps/Tach UI) explicitly
**not** a priority.

**Possible open-source give-back (noted, not acted on — same build-for-us-first discipline).** The one
genuinely underserved piece is the **cross-boundary layer**: auto-extracting + enforcing subprocess /
shared-config / file-dispatch edges as a *unified* graph reconciled against a declared manifest. Both the
agent's and the research's conclusion is that no production tool closes this. If our `arch-manifest.json` +
fitness-function generators prove out here (and ideally survive a second real project shape, not generalized
from N=1), they're a candidate to extract and publish. **Architect it cleanly separable; do not design *for*
publication now.** Flag the moment it's earned its generality.

---

## 11. Console & gate model — DECIDED 2026-06-27 (from the APGA user-stories review)

Formalizes the console-design session that worked through the APGA console user-stories review (those
stories were migrated 2026-06-27 into the per-stage `STAGE*_DESIGN_*.md` notes + `OVERVIEW_AND_SETTINGS_DESIGN.md`,
and the source doc retired). The flow diagram (now in `ACQUISITION_PIPELINE.md`) already reflects the
structural pieces (gates, back-edges, batch types); this is the authoritative prose. The console UI
itself (stage selector, Overview, Settings, Stages 1–4 views) is **principle-set here, not yet
wireframed — it needs its own design pass before build.**

### 11a. Gates are STAGE-NUMBERED (`gate@N`) — replaces CP-A/B/C
The 3 checkpoints become **5 stage-numbered gates**; the deterministic stages (2/3/4) and the mechanical
Stage-9 DB write are ungated:

| gate | stage | the human judgment | was | kind (§11i) |
|---|---|---|---|---|
| **gate@1** | 1 Queue | approve the batch (right districts/schools/bands) | CP-A | structural |
| **gate@5** | 5 Filter | per-URL representation review (labeling) | CP-B | structural |
| **gate@6** | 6 Dispatch | approve routing/dispatch (which reps → which council config) over an already-narrowed send set (prefer-recent + sibling-variant + hub-priority holds — `STAGE6_DISPATCH_DESIGN.md`); optional **verified-only** (labeled-targets-only) mode | *new* | supervision |
| **gate@7** | 7 Extract | review extraction results + council requests/recommendations | *new, BUILT* | supervision |
| **gate@8** | 8 Aggregate | review per-band results; override needs a reason | *effective CP-C* | structural |

**gate@8 is the effective CP-C** — once results are approved there, Stage 9 writes to the LCT DB mechanically.
**Structural vs. supervision — see §11i (decided 2026-07-04):** 1/5/8 were the ORIGINAL three-gate design
(CP-A/B/C) and decide something genuinely new each time; they're permanent. 6/7 emerged later, from
API-spend caution during a context-clear cycle, not first-principles design — they're the first to relax.

**gate@1 also now surfaces automatic *refusals*, not just the reviewable pool (#229, 2026-07-11/12).** A
district whose NCES `WEBSITE` yields no usable scoping domain is dropped from the batch before it ever
reaches the human — there's no alternate domain source to fall back to, so this is a hard exclusion, not a
judgment call the gate is meant to make. The gate@1 console renders these as a distinct `domain_excluded`
list (name/state/district_id/raw `website` value) alongside the normal queue, so the human still sees *why*
a district didn't make it in, without being asked to approve or reject something that was never admissible.
This is refusal-visibility, not a relaxation of gate@1's own approve/reject judgment.

### 11b. Settings: per-gate manual/auto (global default + overrides); AUTO is confidence-escalating

**The ramp-up model (the governing philosophy — Ian, standing since 2026-06-22).** The gate toggles
serve a deliberate strategy: **start with high human supervision (every gate manual) and ease toward
automation only as each gate's reliability is measured** — the destination is a **self-governing,
self-sustaining** pipeline, reached carefully, not assumed. Manual is the default posture *now*; a gate
goes auto only once its confidence-escalation has earned it. Two consequences: **(1)** a judgment that a
gate's output "looks right" is a **recommendation for human sign-off, never a fait accompli**, until
that gate is explicitly set to auto (the human inspects real output at each gate — reading a real
`batch_NNNNN.json` / extraction result line by line — and catches real-data bugs pure code review
misses); **(2)** every new gate is **built manual-first**, its auto path (confidence thresholds,
escalation) added and tuned afterward. gate@7's council-initiated **request-more-evidence loop** is this
model applied to Stage 7: the *council* authors the request (the 7→6/3/2/1 back-edges) via a deterministic
detector, **built and validated** (`STAGE7_EXTRACT_DESIGN.md` §0/§4); a human reviews/approves it
at gate@7 (**built**) under today's high-supervision setting; the toggle relaxes that to auto
(confidence-escalating) later. **Execution** — an approved directive firing the target stage's back-edge —
is **built and hardened** (REQ-118, STAGE7 §3F, epic #163, 2026-07-04/05): **7→6** bundles a district's
approved alternate-rep re-dispatches into ONE round and picks the yield-ranked alternate (not
image-first), and **7→2/7→3/7→1** wrap in a Stage-1 follow-up batch that **shapes its own discovery**
(untried-schools-first, else a widened SERP query set) and **defers** live while a cheaper 7→6 remedy is
still executable — both under the **REQ-051 budget governor** (`common/budget.py`) + a per-district
**rounds** depth guard (not rows — a hardening fix). Approval stays pure review; a **separate compose
step** materializes the batch (so gate@7 isn't coupled to batch creation), and now **previews** it
(dry-run, no persistence) before the operator commits. The toggle below is the ramp-up's control surface.

**The one deliberate exception TO A GATE'S OWN JUDGMENT: gate@7's auto-withdraw (#233/REQ-123,
2026-07-11/12).** Every gate above is manual-until-earned — EXCEPT retiring a request-more-evidence
directive once the cumulative production state has satisfied its premise
(`stage7_run.withdraw_satisfied_requests`), which runs with **no human sign-off at all**, always, not
confidence-gated. Ian's rule for admitting this exception: ***auto-act in the spend-conservative direction
when the failure mode is observable and reversible.*** The test isn't "is a human in the loop" — it's the
RISK ASYMMETRY between the two failure modes:
- **Not auto-withdrawing** risks a human approving/executing an already-satisfied directive — real,
  unbounded, non-self-correcting **paid** council spend, directly against the four commandments' tight-
  cash-spend priority (§0 above).
- **Auto-withdrawing wrongly** only ever leaves a band gap that stays **visible** (the action never
  touches `school_fact` — the ground-truth facts are untouched), **re-emits** on the next production round
  (`withdrawn` is not an OPEN status, so #234's dedup doesn't suppress a fresh detection), and is **one
  Reopen-click** from returning — Reopen re-runs the exact same premise check server-side, so a
  still-satisfied directive re-withdraws immediately with a fresh audit note rather than silently
  resurrecting finished work.

Apply this same test to future auto-mode decisions (the #104 gate-mode toggle, further runtime guardrails
below): does automating bias toward the cheaper failure, and is that failure observable + reversible? If
yes, auto is *consistent with* the ramp-up model here, not a violation of it — the model's actual claim is
"don't automate a judgment you haven't earned confidence in," not "a human must always act first." A
deterministic, reversible bookkeeping action retiring stale work is a different kind of decision than a
judgment call on extraction quality — see REQ-123 and `STAGE7_EXTRACT_DESIGN.md` §0/§6 for the
full mechanism and the review that found (and closed) two real defects in the first draft's actual
implementation of this rule.

**A second, differently-shaped automatic behavior: Stage 2's fail-closed domain guard (#229, 2026-07-11/12).**
`stage2_discover/discover_stage2.py`'s `gate_urls()` now refuses **every** URL, unconditionally and with no
human involved, the instant its district's domain fails `is_scoping_domain()` — it never falls through to
the old unscoped branch that used to keep everything (that fallthrough was the actual mechanism behind the
Millard cross-district contamination, #227). This is not the same kind of exception as gate@7's
auto-withdraw — it isn't a gate relaxing its own judgment at all; `gate_urls()` sits *inside* stage logic,
below any gate, and Stage 1's `build_batch`/`build_followup_batch` already refuse the same districts earlier
still (§11a above). It's included here because it passes the same risk-asymmetry test by construction:
refusing is the fail-**safe**, spend-conservative direction (an unscoped run risks contaminating the
candidate set with nationwide same-named-school noise, a data-quality failure that is expensive to detect
and clean up after — see #227/#228 above), and a wrongly-refused district is trivially visible (it shows up
as a `domain_excluded` refusal, or Stage 2 yielding zero candidates for a district that should have some) and
reversible (fix the domain, re-run). The two defenses — Stage 1 admission, Stage 2 defense-in-depth — are
deliberately redundant: a domain problem reaching Stage 2 through any *other* path (a manual DB edit, a future
batch builder, a remediation script) still can't contaminate a run, because the fail-closed check is the
single gating chokepoint for all discovery waves, not a rule that only fires when Stage 1 is on the path.

Each gate toggles **manual** (human acts) / **auto** (self-advance), via a **global default + per-gate
overrides**. **Auto is never blind: auto-with-confidence-escalation** — auto-accept the high-confidence,
auto-escalate-or-flag the low-confidence to manual (the same pattern as Stage 5, and the conceptual shape
of Stage 8). Especially gate@8: extracted minutes never reach the LCT DB without confidence. **Auto-advance
through the paid stages (6/7) is cost-gated by the budget governor (REQ-051)** — full-auto must not run up
unbounded OpenRouter spend.

**REQ-119 — external AI calls must stream (built, tested), a cross-cutting constraint.** Every external
generative call anywhere in the acquisition tree issues `stream: true` and is not caller-toggleable to a
blocking call; enforced two ways — behavioral tests on the live client, and an AST source-guard
(`tests/test_streaming_contract.py`) that fails CI on any *new* blocking OpenAI-SDK completion call added
anywhere in the tree. Applies pipeline-wide (any future paid stage/provider), not just Stage 7.

**Guardrails for the manual→auto transition — the RUNTIME tier (planning direction, 2026-07-10).** The
ramp-up's destination (self-governing pipeline + Council Lab auto-promotion + Stage-7/8 outcomes tuning
Stage-5) is a **different risk category** than the dev-time defect-prevention of epic #200 — it is the ML
"hidden feedback loop / CACE" surface (Sculley et al.). As the human leaves a gate, the guardrail must move
from *test-time* to *runtime*: drift monitors, confidence gating, revert-to-last-known-good, and — the one
the recall floor structurally CANNOT catch — an **anti-survivorship exploration quota** (Stage-5 only sees
paid outcomes for reps it approved, so it can entrench a wrong prune; a random sample of would-be-pruned
reps must still be extracted to keep the pruned tail observable). Cataloged in **epic #209** (runtime
guardrails), a sibling to #200. **Two ordering constraints are load-bearing:** (a) gate@8's calibrated
confidence gate must exist *before* the supervision gates (6/7) relax — it is the last backstop before the
mechanical Stage-9 LCT write; (b) the guardrail ships *with* the automating feature (Council Lab promotion
substrate = COUNCIL_LAB §5a), never bolted on after.

**The exploration-quota control law — a revocable autonomy license (#211, design session 2026-07-10).**
The anti-survivorship quota is not a metric we watch; it is a **control law that licenses gate@5's
autonomy and revokes it automatically.** The one-sentence form: *the filter may run only as autonomously
as its reject audit is currently validating it — and the moment that validation lapses, autonomy falls
back one supervision level rather than the pipeline halting.* Three points are easy to get wrong and are
load-bearing. **(1) It is not a current hole.** Today the operator census-labels every completed district
— all tiers, rejects included — so the reject bucket is fully observed and the harness recall (A+B 0.9961,
#208) is already honest, measured over labeled tier-D records, not a survivor-only set. The hole opens at
exactly one moment: **when gate@5 goes auto and census-labeling stops.** So the quota is the instrument
that *replaces* census-labeling, switched on before it switches off — the gate on relaxing Stage-5
supervision, built and calibrated *now* against census truth (run the random sampler retrospectively over
fully-labeled districts; confirm a 3–5% draw reproduces the census reject-quality before relying on it —
completed districts are attention-sorted, so that is a worst-case calibration). **(2) The invariant is a
COUNT over a rolling window of current-config rejects, not a cumulative percentage.** *Auto-suppression at
gate@5 stays licensed only while the window holds ≥ N randomly-selected, human-labeled rejects from the
current config generation* — N set by the rule of three (~300 zero-miss rejects ⇒ 95% confidence FN-rate
< 1%), fed by a p%-of-flow sampler (p sets the flow, N the sufficiency). A cumulative % floats above the
bar on stale labels; % is too thin on small streams and re-imports the manual-at-100k-scale problem
(commandment 2) on big ones. Selection randomness is enforced at draw time (a dedicated
`run_kind = exploration_audit` queue the human works top-down) — "labeled" must mean "*randomly* labeled"
or the estimate is biased and the license is theater. **(3) Breach DEMOTES, it does not HALT.** Below the
bar, gate@5 auto reverts to **manual** (census mode) — the safe direction, self-healing (manual review
regenerates exactly the labels that restore coverage), and scoped to Stage-5 auto-suppress alone
(discovery/capture/extraction keep draining). The **restart bar is refilling the audit sample, not
clearing the reject backlog**; a **deadband** (demote < N, re-promote only above ~1.2·N or a clean window)
prevents auto↔manual flapping. Diagnostics stratify by the suspected bias axes (reader-tier / CMS-family /
doc-format) to catch *correlated* misses, but the hard gate is on the aggregate plus flagged strata only
(per-stratum hard gates multiply human cost). Like every #209 guardrail the enforcement **ships dormant** —
the demote-hook is a no-op until gate@5 is actually set to auto. Full spec: `STAGE5_FILTER_DESIGN.md`
§5a; issue #211.

**As BUILT (`exploration_audit.py`, PR #216 + its review round, 2026-07-10):** the pure control-law core —
`rule_of_three_upper_bound`, `rejection_quality`, `select_audit_sample`, `next_license_state`/
`resolve_gate_mode` — is tested (17 tests), with three invariants hardened past a first draft:
`promote_threshold`/`next_license_state` now **raise** on a collapsed/inverted deadband (`factor <= 1` or
an explicit `promote_n <= floor_n`), an unrecognized mode string now **raises** rather than silently
demoting (a typo'd stored state must surface, not masquerade as a conservative decision), and the sampler
uses the codebase's own `random.Random(seed)` string-seeding pattern (matching `stage1_queue.queue_batch`),
not a hand-rolled hash.

**As BUILT — the live wiring (`exploration_live.py`, #211/REQ-120, 2026-07-12; corrected/hardened via a PR
#248 review round, landed on `main` 2026-07-13 via PR #250).** `resolve_gate_mode` now has live callers —
**not zero** (see the #219 checklist note below, which this replaces a stale claim in). The DB half binds
the pure core to the governance store: `reject_population` (the live tier-D SUPPRESS bucket — imports its
canonical-record predicate from `release.py`'s `CANONICAL_RECORD_WHERE` rather than re-inlining it, a PR
#248 fix), `audit_sample`/`coverage` (the pure sampler bound to that population + `rejection_quality`
window), and **`resolve_gate5_mode`** — THE gate@5 demote-hook. It reads `configured_mode` FIRST via a cheap
point-read; on a **dormant fast path** (configured manual, today always, and no coverage precomputed) it
returns immediately WITHOUT running `reject_population`'s query — the hook fires on every gate@5 label save
(below), and the full tier-D scan was dead work while dormant (`build_signals.py` also gained
`ix_record_tier`, since the query was previously unindexed, for when a gate actually is auto). When
configured auto, it computes the live `window_count`, applies the deadband law, and **persists the
transition back to `license_state`** (the deadband's hysteresis memory). Wired into BOTH `save_label`
(self-healing: each gate@5 label re-evaluates the license) AND `reset_labels` (#228 — removing audited
labels also re-evaluates it, so a stale license can't outlive the coverage that earned it) — **both inside
a `con.begin_nested()` SAVEPOINT + swallow**, a PR #248 fix: the demote-hook is advisory to the human's
write, and an earlier un-isolated version could roll back a valid label save on a transient hook failure.
Read-only status at `GET /api/exploration-audit` → a Settings-console coverage meter, now backed by a
SINGLE `audit_sample` draw (a PR #248 fix — it used to query the population twice per request, which also
let a mid-request commit desync the meter from the pending list). **Enforcement stays DORMANT** — gate@5 is
configured manual, so the hook returns "manual" and writes nothing; it goes live the moment a human sets
gate@5 auto in Settings (the §11b ramp-up surface #104 shipped). One more load-bearing correctness fix from
the same review round: `gate_mode.configured_mode` is **NULLABLE — NULL means "inherit the global
default,"** not "manual." An earlier version hardcoded `configured_mode='manual'` on `set_license_state`'s
fresh-row INSERT, which silently and permanently pinned a globally-auto-configured gate to manual the
moment its FIRST license transition wrote — since `get_configured_mode` stops falling through to the global
default once a gate's own row has any non-null value. **Current-config scoping is STRUCTURAL,
not a stored fingerprint:** the window is recomputed over the live tier-D set every call, so a rescued
reject simply leaves the population — no reject-audit table, no persisted config generation, and the draw
still replays from `(seed, the DB's current reject set)` for the auditability north star. Verified live
(566 rejects, 24 sampled @5%, all census-labeled zero-miss → quality 1.0, window 24/300 — informational
while census-labeling is still on). **Still deferred:** a dedicated `run_kind=exploration_audit` queue MODE
in the Stage-5 tree (the Settings pending list suffices today), Tier B, and the retrainer fast-follow.
Detail: `STAGE5_FILTER_DESIGN.md` §5a.

**The recall floor's enforcement mechanism, precisely (#208, built 2026-07-10).** `harness.assert_floor(con)`
is called **from inside** `build_signals.ingest()`'s DB transaction (via `--assert-floor`) — a violation
raises `SystemExit` *before* the transaction commits, so the entire re-ingest (every record's re-tiered
signals) rolls back atomically, not a post-hoc report against an already-committed bad config. Detail:
`STAGE5_FILTER_DESIGN.md` §5b.

**Milestone criteria: DEFERRED; the meter that sets them: STARTS NOW (Ian + assistant, 2026-07-10).** We
lack the data to chart "gate@N goes auto when confidence θ yields human-agreement ≥ X" — so the *criteria*
wait. But calibration data accrues only **forward in time** (the #108 facet-accrual lesson: you cannot
measure a threshold you never instrumented). So the decision was to **start the gate-decision calibration
log now** — and it is now BUILT and WIRED LIVE (REQ-121/#210, PRs #217+#218, 2026-07-10).

**As BUILT — not what the paragraph above originally sketched.** The design session's first draft imagined
this as "a small extension of the existing `state_event` writes." What actually shipped is a dedicated
**sibling table**, `calibration_event` (`common/calibration.py`), at the ITEM grain (one row per gate
decision — gate@5 acts on records, gate@7 on extractions, a different grain than `state_event`'s
per-district lifecycle rows), never a column bolted onto `state_event`. Each row carries: the gate id +
item id; the **continuous** confidence proxy value (never a bucket, so any θ can be swept post-hoc) —
gate@5 the combiner's `sort_score`, gate@6 `n_send` (records that actually dispatched a rep, not merely
decision-labeled `send` with none), gate@7 the district's council agreement ratio
(`n_accepted/(n_accepted+n_unresolved)`); the human's terminal decision (`accept`/`reject`/`modified` — a
**whitelist**: gate@5's hook only fires on a genuinely confident `labeled` status, never the console's
`unsure` hedge, which can arrive carrying a stale label); what auto currently would do
(`accept`/`reject`/`escalate`) and an `agreed` flag defined *only* where auto would act unilaterally (None
when auto would escalate — the human-in-the-loop region isn't a calibration data point); the slice keys
(state/capture_path/batch_type/run_kind/school_level) needed to certify the *worst* slice, not just the
aggregate; and a `blinded` flag for an automation-bias-free subsample. `sweep_worst_slice()` is the
post-hoc θ-sweep the schema exists to enable, without baking in a θ at log time.

**Wiring (PR #218, live as of 2026-07-10):** `process_governance/gate_calibration.py` translates console
vocabulary into the calibration vocabulary (deliberately kept OUT of `common/` — that translation is the
wiring layer's job, not the base layer's) and is called from `save_label` (gate@5), `_record_dispatched_events`
(gate@6), and `extract_request_review` (gate@7), each on the SAME transaction as the gate's existing write —
**the corpus is accruing now, not a dormant instrument.** Two decisions worth recording: **(a)** a label
that cascades to cluster members logs exactly ONE row (the representative), never one per member — members
are near-duplicates, and logging them separately would pseudo-replicate a single human judgment N times in
rule-of-three math that assumes independent trials. **(b)** gate@8 — approving the council's extracted
**times** (`school_fact.human_determination`) — is explicitly **NOT** part of this wiring: it is a Stage-8
activity, and Stage 8 isn't built (#88/#89), so that hook is deferred until it lands, not conflated with
gate@7's request-directive review. Detail: `STAGE5_FILTER_DESIGN.md` §4,
`STAGE6_DISPATCH_DESIGN.md` §0, `STAGE7_EXTRACT_DESIGN.md` §3.

**Phase 2 — the group-aware promotion gate + safe-promotion machinery (#212/#213, built 2026-07-10).** The
config-tuning analogue of the supervision gates: when a Stage-5 config change becomes even semi-automated,
the recall floor (§5b) is a necessary but insufficient guard (a single hard number, blind to noise and to
the clustering that makes the naive test lie — DEFF≈2.4). Phase 2 adds **`promotion_gate.py`** — a
group-aware **non-inferiority** gate (LOGO fold guard + a cluster/"cases" bootstrap over per-district A+B
recall deltas + TOST against a *pre-declared* Δ, ICC/DEFF reported), built on proven libraries
(statsmodels/scipy/sklearn; ICC(1) is the anchored ANOVA estimator with pingouin as its balanced-case test
oracle — pingouin's own ICC listwise-deletes unbalanced clusters, a PR #220 review find) and wired **advisory** into
`frontier gate()`/`--gate` + a `tuning_ledger` episode block — and the **safe-promotion machinery**
(`config_artifact.py` immutable fingerprinted artifact that finally brings `DEFAULT_DETECTOR_PARAMS` under
versioning; `promotion_pointers.py` @champion/@fallback atomic pointer swaps with N-cycle retention;
`promotion_flow.py` shadow→gate→swap→record). Storage split per Ian's decision: **artifacts in git**
(`CONFIG_DIR/promotion/artifacts/`), **pointers in the DB** (`config_pointer` singleton, atomic swap). Full
detail: `STAGE5_FILTER_DESIGN.md` §5c.

**Gate-mode persistence — the store + console toggle shipped (#104/REQ-108, 2026-07-12); per-gate AUTO
behavior still deferred.** The "global default + per-gate overrides" toggle described in §11b's opening now
has a backing store: a precious `gate_mode` table (`common/gate_mode.py`) holding `configured_mode`
(manual|auto, the human toggle) + `license_state` (the #211 demote-hook's deadband state) per key
('default' + 'gate@1'..'gate@8'), read via `effective_gate_mode(con, gate)` (own override → global default
→ manual), set via `GET`/`POST /api/gate-mode` and a console **Settings** panel, git-backed as the precious
`gate_modes.json`. **What remains NOT built:** every gate EXCEPT gate@5 still behaves manually regardless of
its stored toggle — `effective_gate_mode` returns the configured mode with a manual default, but only
gate@5 has a live handler (`exploration_live.resolve_gate5_mode`) branching on it; setting gate@1/6/7/8
'auto' persists the intent without altering behavior yet, pending each gate's own confidence-escalating
auto path (#104 part b). `exploration_audit.resolve_gate_mode()` (the gate@5 license layering over
`license_state` + a live `window_count`) **now has live callers** — `save_label`, `reset_labels`, and the
`GET /api/exploration-audit` status endpoint (all shipped 2026-07-13, PR #250; detail above). The store was
the prerequisite the exploration-quota and calibration-log guardrails were waiting on to go from dormant to
live; it now exists, and gate@5's guardrail is the first to actually use it.

**Dormant-guardrail inventory (remember to activate — #219).** Every #209 guardrail ships *built but inert*
(the `--assert-floor` pattern: ship the guard with the capability it guards, never before). That is correct
discipline but it accumulates dormant safety code, all blocked on the same prerequisite. The running
**guardrail-activation checklist is issue #219**: #208 `--assert-floor` (opt-in), #211's exploration-quota
demote-hook (**live wiring shipped, WITH live callers** — `save_label`/`reset_labels`/the status endpoint —
but its enforcement stays dormant while gate@5 is configured manual: this replaces an earlier draft of this
sentence that said "zero live callers," which was already wrong by the time it was written — see §11b
above for the actual wiring), #210's gate@8 calibration hook (deferred to Stage 8), and #213's
pointer-drives-live-config actuation + the minor/major re-ingest shadow — all gated on gate-mode persistence,
with the load-bearing ordering (persistence first; gate@8's calibrated gate before 6/7 relax). When the
manual→auto transition begins, #219 is the checklist we run so nothing is silently left inert.

The **ML-Test-Score-style per-gate readiness rubric** (config-as-data checklist: data / decision-quality /
infra / monitoring) is the companion plumbing — schema now, per-gate pass-bar deferred with the milestones.
Both this and the calibration log are the instrumentation half of #209's gate-transition items; the
policy/threshold half is explicitly blocked on the transition-governance plan.

### 11c. Pipeline Overview = "what just happened" (an event-log projection)
The Overview visualizes the **`state_event` log** — per stage, what just completed + the **attention queue**
(§7b). It is **NOT a live in-flight feed**: the durable log is deliberately completion-only (no interim
markers), and the ephemeral "what's processing right now" layer is **dropped** (user, 2026-06-27).
Controls: **Start** (kick off full-auto advance) + **Safe-Stop** (let in-flight work complete, with a
progress bar). **Pause dropped** (not worth the complexity).

### 11d. Two batch types; completion grain = district × BAND
- **first-run** (cold-start stratified draw; excludes already-attempted districts) vs **follow-up**
  (re-discovery / gap-fill; deliberately re-includes attempted districts, targeting **unsatisfied bands**).
  A district can recur across batches. **12-district hard cap on both** — a stages-1–4 blast-radius control
  (representations don't exist yet at queue time, so a break shouldn't spiral; the cap also stops automated
  follow-up creation running away — spillover starts the next batch). The **cost/representation ceiling is
  the separate Stage-6 dispatch control**, where representations exist.
- **Completion grain = district × BAND** (not district × school). Schools are **instrumental** — raw
  material for search queries + expected sampling units — but once a captured page states the band-level
  answer (Dunseith: "elementary 435 min / high 450 min"), the schools are moot. A district is **satisfied**
  when every claimed band has confident minutes; re-queue targets unsatisfied **bands**. Per-band
  eligibility leans on `discovery_school` (per-school discovery outcomes) + the extracted results.
- **Directions route through Stage 1.** Anything needing NEW capture/discovery (re-discover, recapture,
  band-gap fill) returns to Stage 1, where the follow-up `batch_*.json` is created and stays reviewable at
  gate@1 — 7/8 never create a batch straight to discovery. Only re-routing EXISTING representations bypasses
  Stage 1 (7→6 re-extract via a different config; 8→6, once Stage 8 exists, would add an existing-rep URL
  to a new dispatch the same way). **Built (REQ-118, epic #163):** the follow-up batch now shapes its own
  discovery rather than repeating the same query blind — prefers untried NCES schools for the re-targeted
  band, falls back to a widened SERP query set when none remain, and can carry pre-specified seed URLs for
  a 7→3 recapture (dormant plumbing). See `STAGE7_EXTRACT_DESIGN.md` §3F.

### 11e. The pipeline is CYCLIC (back-edges) — detail in the flow diagram
**As originally sketched, then as BUILT (REQ-118, updated 2026-07-05):** the four back-edges off Stage 7
are **7→6** (direct alternate-rep re-dispatch, bundled per district), **7→3** (recapture the URL), **7→2**
(targeted rediscover for a band), and **7→1** (a follow-up batch adding schools) — all built, all routing
through a Stage-1 follow-up batch except 7→6 (§3F/§11d). The Stage-8 back-edges this subsection originally
anticipated (8→1, 8→6) are **not yet real** — Stage 8 isn't built (tracked #89) — and will be documented
here once designed; don't treat them as built today. See the flow diagram in `ACQUISITION_PIPELINE.md`.
The immutable Stage-6 dispatch freeze is what keeps "what we sent" recoverable across these loops.

**5→1 (BUILT 2026-07-19, #164 PR 3b):** the ZERO-YIELD back-edge — a district that lands at gate@5
with nothing dispatchable (no send/hold records, no retryable capture errs to route to the #116
retry, no fidelity flags to triage) escalates to a GEO-scoped rediscovery
(`process_governance/stage5_followup.py`, app layer): the #164 hypothesis is that the DOMAIN was
the bottleneck. Ladder position is DERIVED from ever-approved follow-up history
(`batch_store.followup_rounds` — never a stored counter): 0 geo rounds → geo + standard vocabulary,
1 → geo + widened, ≥2 → manual flag (`followup_flag`, auto-deduped), no compose. The composed batch
is a scope-pure geo DRAFT at gate@1 — escalation batches are individually gate@1'd, never
auto-flowed. The 7→1 compose has the matching SECOND-LOOP scope split (0 prior rounds → domain
batch, ≥1 → geo+widened batch, geo already ran → flag): one compose can emit up to two scope-pure
batches, each directive's `executed_ref` = its district's batch, one transaction.

**The shared exhaustion threshold (#575).** Both composers' "ladder exhausted" branch — 5→1's `≥2 →
manual flag` and 7→1's `geo already ran → flag` above — now read the SAME function,
`stage1_queue/batch_store.geo_ladder_exhausted()` (`GEO_LADDER_EXHAUSTED_AT = 2` — ever-approved geo
rounds, one standard + one widened attempt), not two independently-written inline checks. A #575 review
found they used to disagree: 7→1 exhausted a district at `geo>=1`, while 5→1 offered a second
"geo+widened" rung at `geo==1` — so a district sitting at exactly one approved geo round got a different
verdict depending on which composer reached it first. The threshold was extracted into this one shared
function precisely so the two composers can't diverge again. Both composers also call the same shared
auto-flag writer, `process_governance/stage7_execute.py:_flag_escalation_exhausted` (lines 465–485): it
dedupes on an already-open auto flag (`scope='district'`, `actor='auto:escalation-ladder'`, unresolved) so
a re-compose never stacks a second marker, and a human resolving the flag re-arms it — a later exhaustion
is a fresh event worth a fresh flag.

### 11f. Per-stage console notes
- **Stage 3** — a thin **health / emergent readout**: emergent URLs, capture failures (WAF/security
  blocks), and the **CMS/host distribution** from the `capture` table's `final_host`/`fingerprint_json`
  (REQ-103c). NOT a live PNG feed (cute, low governance value). **BUILT + RUN LIVE 2026-06-28/29 (REQ-110)**
  — reads the DB cache (incl. `capture.err` for the failure breakdown + per-district `manual_flag_all` /
  `failed` / `timed_out` / `captured_partial` states), + a per-district Node-capture run trigger.
  See `STAGE3_CAPTURE_DESIGN.md` §7.
- **Stage 4** — same shape (ungated status + run trigger); **BUILT + RUN LIVE 2026-06-29 (REQ-111)**.
  Reads the `processed_doc` cache; per-district usable/not-usable doc counts + a
  **usable-representations-by-tool** readout; `no_usable_text_any`/`awaiting_capture` badges. A process run
  that **resolves the whole batch** then runs the **Stage 4→5 incremental handoff** (§12). **Run in an
  ISOLATED SUBPROCESS per batch, not in-process (issue #608, 2026-07-22):** camelot's table extraction is
  backed by native code (pypdfium2/PDFium + OpenCV) that can segfault under concurrent multi-threaded use
  — a live segfault took down the whole console when several batches' autoflow ran Stage 4 concurrently on
  in-process threads. `server._run_stage4_subprocess` now launches the CLI as its own OS process per batch,
  so a crash kills only that batch's job. See §11h below and `STAGE4_PROCESS_DESIGN.md`.
  See `STAGE4_PROCESS_DESIGN.md` §4a/§4b.
- **Stage 3/4 capture-fidelity triage — BUILT (#518, REQ-154's missing consumer, 2026-07-20).**
  `GET /api/fidelity-triage` is the queue the fidelity columns were write-only without: every `capture`
  whose flags say `login_wall`/`soft_404`, or whose `err` is a `security_block` (#578), or every
  `processed_doc` whose Stage-4 `time_blind` flag fired — each says "a real schedule may be hiding behind
  this" — grouped per district with recovery-affordance context (an already-open `followup_flag` covering
  the district, per-class counts, bounded per-district row listing). Before this surface existed, a
  flagged capture degraded silently to `target_absent` — the exact recall leak #518 quantified.
  Self-bootstraps to an honestly empty queue on a fresh DB rather than 500ing on a missing cache/signal
  table.
- **Stages 2 & 4 effectiveness** — the **measurement-harness pattern extended upstream**: attribute each
  target-labeled record back to its discovery tool (`candidate_tools_json`) and its winning representation's
  source (`representation.source`). Same fingerprinted-scorecard discipline as Stage 5, applied to discovery
  and processing. **BUILT (#118/REQ-160, 2026-07-20):** `process_governance/attribution.py` (app layer —
  cross-stage by definition) + `GET /api/attribution` + lazy Effectiveness panels on the Stage 2/4 views;
  the card also carries the **#164 axes** per district (every ever-approved batch_type × discovery_scope
  run, derived ladder position, scoping-domain source) so the geo-vs-domain comparison has attribution
  from day one. First card's headline: emergent one-hop capture is the highest-yield non-GT discovery
  source (38.1% labeled-target rate).
- **Stage 5** — the district-driven, attention-first labeling console (REQ-112/REQ-114); the default
  stage view. **Console trio SHIPPED 2026-07-16/17 (the labeling-that-drives-learning surface,
  per `project-stage5-labeling-serves-learning`):** **#516** (PR #534) — FP/FN **error-review lanes**
  (FP = tier-A ∩ `target_absent` via `release.MONEY_LEAK_WHERE`, the SSOT shared with `decide()`;
  FN = the fixed-seed reject-audit sample; disagreement is the primary product of labeling) + `rec_key`
  as the searchable entry-ID + right-pane reorder. **#521** (PR #535) — **relevance-density evidence
  navigation** for long reps: the same signed detector signals that scored the record, projected onto
  the char axis → ranked bookmarks + heat-strip; weights served from `detectors.EVENT_WEIGHTS` via
  `/api/detector-weights` (display-only mirror, no-drift-tested — combiner weights stay
  `DEFAULT_DETECTOR_PARAMS`). **#522** (PR #536) — **content-adaptive center-pane defaults**: the
  evidence classification drives the default open states (densest + unique-adders + instructional/
  period-phrasing carriers open; ⊆-densest collapsed; never removed — show-all restores everything);
  rasters demoted to one lazy gallery; the source-PDF iframe is the default visual, steered to a
  bookmark's page via pdftotext's `\f` separators; a hidden-evidence pointer guards the collapse rules
  (scope: the client-checkable detector surface — documented in-code). Guardrail across the trio: the
  default view never silently contradicts the score. See `STAGE5_FILTER_DESIGN.md` §8 + Change log.
- **Stage 6** — routing / release; **BUILT to the seam (REQ-101, merged 2026-06-30; console REDESIGNED
  around a persisted draft dispatch 2026-07-13, PR #256)**: a reopenable `dispatch_draft` a human builds up
  (add/remove districts, council overrides, verified-only) → **freeze** → the immutable dispatch + a
  precious `handoff` index row + a per-district `dispatched` state_event; manual approve today (auto mode
  deferred) (tracked: #104). See `STAGE6_DISPATCH_DESIGN.md` §0/§0b.
- **Stage 7** — council extraction; **BUILT (REQ-117, 2026-07-03; extraction quality epic #119 CLOSED
  2026-07-15)**: the gate@7 console (district-first — band rollup, accepted/unresolved facts,
  request-more-evidence cards with Approve/Reject/Reopen, the #237 contamination banner); read +
  review only, no fact/band editing (that's gate@8). See `STAGE7_EXTRACT_DESIGN.md` §0.
- **Stage 8** — aggregation + the "closing argument"; **BUILT (#89, 2026-07-14)**: the gate@8 console
  (review queue, per-school override, band-exclusion / human-add / slot-assignment, the approve/send-back
  verdict with a frozen fingerprinted receipt). This is where fact/band editing lives. Still unbuilt: the
  8→1/8→6 back-edges. See `STAGE8_AGGREGATE_DESIGN.md` §0a/§0b.
- **Stage 9** — the sanctioned write of the approved per-band minutes into the LCT `bell_schedules` DB;
  **BUILT (#93/#94/#95, 2026-07-21)**: reads the frozen gate@8 receipt, UPSERTs per band (council or
  statutory-fallback), verifies-in-DB, reconciles year-change orphans, and stamps an `incorporated`
  `state_event`. The one cross-DB crossing (a layer above stages 1–8; only `incorporate.py` touches
  `infrastructure.database`). The **per-grade projection** (#605/#606) is also BUILT: Stage 9 writes
  `district_grade_minutes` and the LCT calc weights per-grade minutes × per-grade enrollment to any scope
  (secondary = mid+high, not high-only) — the one-time recompute gated on sign-off. See
  `STAGE9_INCORPORATE_DESIGN.md` §4.

### 11g. Implications for what's built
- `state_event.checkpoint` vocabulary: **`gate@1` | `gate@5` | `gate@6` | `gate@7` | `gate@8`** (was
  CP-A/B/C). Free-string column → no schema change; update recorded values + docs as gates get wired.
  **`gate@1`, `gate@6`, and `gate@7` are now live** (in-band console approvals — gate@6 records a
  `dispatched` event referencing the immutable dispatch hash; gate@7 records approve/reject/reopen on each
  request-more-evidence directive; see 11h).
- `filtered.json` carries **alternate target-flagged reps** (the winner + alternates) so gate@6 can offer
  representation override (REQ-094 follow-up; un-defers §4's "representation override deferred" lean).
- The **console UI build needs its own design pass** (stage-by-stage, as we designed the pipeline) before
  coding — Overview, Settings, the stage selector, and the Stage-1–4 views are principle-set, not designed.

### 11h. gate@1 console + the batch as a first-class DB entity — BUILT 2026-06-27 (REQ-102, backend)
The first stage view's **backend** is built; it's also the first concrete instance of the §7a-A receipts
reframe and the batch_00002-forcing-function plan (the batch-of-record advances only through the console).
- **The batch is now a first-class entity in the governance DB — the working store.** New normalized
  PRECIOUS tables (`stage1_queue/models.py`): **`batch`** (lifecycle `draft → approved`, plus a terminal
  `abandoned` exit for a never-approved draft and a `reserving` id-placeholder status — #168, built
  2026-07-09; see `STAGE1_QUEUE_DESIGN.md` §6a/§6c — + actor/timestamps + prose meta),
  **`batch_district`** (`included` soft-reject + `ord` for a stable receipt), **`batch_school`**
  (`bands`, `included`, `source` = stratified|manual_add). Normalized, **not a JSON blob** — so edits are
  real row ops and the cross-batch queries the user stories need fall out. **PRECIOUS** = never in the
  Stage-5 `REBUILD_DDL` drop list (a re-ingest can't wipe a queued/approved batch). `batch_NNNNN.json` is
  the **receipt regenerated from the rows** (`batch_store.write_receipt`), not the working store.
- **Approval is BATCH-level** (the unit that advances): a `batch` row transition, plus per-district
  `gate@1` `state_event`s for the auditable timeline. Editing (reject district/school, add school) is
  **soft + audited** (`included` flips / inserts; a `gate@1 "edited"` event each), **locked when approved**
  (`reopen` to edit again).
- **Orchestration = functions** (§7a-B): `queue_batch.build_batch()` (pure) + `persist_batch()` (DB write +
  receipt + events), shared by the CLI and the console `POST /api/queue/create` (synchronous draw, ~10–20s).
- **API** on `process_governance/server.py`: `create` · `list` · `get` · `edit` (reject/restore/add) ·
  `approve`/`reopen` · `district/{id}/candidates`. Tests: `test_stage1_batch_store.py` (10) + `test_gate1_api.py` (6).
- **Frontend BUILT 2026-06-28** (`process_governance/static/` — stage selector + the queue view, on the
  **MMM Design System** imported via **DesignSync**). Edits are reversible (reject/restore). Validated
  end-to-end: **`batch_00002` created → edited → approved through the UI**, all surfaces consistent.
  *(A CWD-independence fix landed with it: NCES + `.env` reads anchored to the repo, not the launch dir —
  a server-robustness lesson for every later stage's file reads.)*
- **Stage 2 console view BUILT + RUN LIVE 2026-06-28** (`static/stage2.js` + `/api/discover/*`): the
  ungated status/observability view + the "Run Discovery" trigger (background job, events-as-log feed).
  `batch_00002` (11) and `batch_00003` (12, with add/reject-school edits) both ran through the UI end to
  end — the second console stage view, following the gate@1 build pattern. (A switcher refactor to add it
  briefly broke the Stage-1 view via a deleted `v1` var — fixed; a reminder that the static JS has no
  lint/`no-undef` gate, unlike the Python side.) **Batch resolution stayed receipt-based here until #526
  (2026-07-18)** — unlike the cache repoint below, which fixed *signal* reads, the underlying batch dict
  itself kept coming from `load_batch_any` (the on-disk receipt) rather than the DB working store Stages
  3/4 already used; see §1's updated principle statement.
- **Stage 3 console view BUILT + RUN LIVE 2026-06-28/29 (REQ-110)** (`static/stage3.js` + `/api/capture/*` +
  `stage3_capture/headless.py`): the ungated health/emergent readout (read from the DB cross-stage cache)
  + a per-district Node-Playwright capture run trigger. Load-bearing infra change underneath it: the
  **cross-stage cache graduated to a live working store** maintained by each stage's finish hook
  (`common/cache_ingest.py`), so the console reads fresh DB rows for an in-flight batch (§7a-A). Stage 2's
  console was repointed to the cache too (self-healing). Batch resolved from the DB working store, not the
  receipt. **Hardened over live runs (batch_00002–00005) — detail in `STAGE3_CAPTURE_DESIGN` §7:** no-link
  districts skip Playwright; failures/timeouts surface + are retriable; **shared status labels +
  left-pane progress fractions** (`static/outcomes.js` — one rename point; honest "0/10 captured · 2
  no-links" counts; chip live-synced to the header during a run; `list_batches` carries per-stage
  progress); and the capture-resilience principle below.
- **Resilience principle — a partial run preserves work, never orphans it (REQ-110).** A capture timeout
  used to SIGKILL Node before it wrote its end-of-run manifest, orphaning all completed per-URL captures.
  Fix: **node-owns-shutdown** (Node writes a PARTIAL `captures.json` on its own deadline → `captured_partial`;
  Python's subprocess timeout is a backstop) + a **reconstruct-from-disk** recovery tool for already-orphaned
  districts (also the interim manual-follow-up path — it can fold in a human-sourced file as a
  `source:"manual"` record). The general rule for any external-worker stage: **the worker owns its
  shutdown and always writes a complete manifest; a timeout is a partial outcome, not a failure.**
- **Stage 4 console view BUILT + RUN LIVE 2026-06-29 (REQ-111)** (`static/stage4.js` + `/api/process/*` +
  `stage4_process/headless.py`): the ungated status readout (per-district usable/not-usable doc counts +
  the usable-reps-by-tool panel, read from the DB `processed_doc` cache) + a run trigger. The batch
  resolves from the DB working store via the shared `_batch_from_db`. `headless.run_batch` itself is
  unchanged — still sequential, in-process Python (**no node-owns-shutdown**: the work is a plain function
  call; a crash mid-district just leaves `processed.json` unwritten → reconcile re-runs that district next
  time). **What changed (issue #608, 2026-07-22): the CONSOLE no longer calls `run_batch` in-process.**
  camelot's table extraction (pypdfium2/PDFium + OpenCV, native code) can segfault, and a segfault bypasses
  Python's exception handling entirely — with two batches' Stage-4 threads calling into the same native
  libraries concurrently (autoflow can trigger this for several batches at once), a live segfault took
  down the whole console mid-session. `server._run_stage4_subprocess` now launches `headless.py`'s CLI as
  an isolated OS subprocess per batch — a crash there kills only that batch's job. The resolved batch dict
  crosses the process boundary via a temp file (never the on-disk queue receipt, per #526); stdout streams
  `[kind] {...}` JSON-lines for live progress; stderr is captured to a durable per-run log under
  `paths.PROCESS_LOGS_DIR` for post-crash forensics. A local `stage2_complete` disk-scan replaced an import
  of Stage 3's `find_districts` (the independence contract).
- **Stage 4→5 incremental handoff BUILT (REQ-111)** — the seam where the batch hands to Stage 5. See **§12**.
- **Stage-5 console rework BUILT (REQ-112, 2026-06-29)** — the district-driven, attention-first faceted
  console; the app's origin, finally on the current architecture. See **§12c** + `STAGE5_FILTER_DESIGN` §A–D.
- **Stage 6 + gate@6 routing BUILT to the seam (REQ-101, merged PR #2, 2026-06-30)** — the `stage6_handoff/`
  package (per-rep routing data-driven off `input_kinds` + the capture-fidelity gate; cost estimator on a
  bootstrap model; immutable dispatch with a price-independent hash; OpenRouter request assembly) + the gate@6
  console view (`static/stage6.js` + `/api/handoff/*`: preview the routed/priced package → Approve & freeze).
  Approval records the index row + a per-district `dispatched` state_event **atomically**, freezes the
  immutable artifact, and **stops at the seam — no paid call** (Stage 7). Manual approve today; auto mode +
  the budget-governor cost-gate (REQ-051) deferred (tracked: #104). See `STAGE6_DISPATCH_DESIGN.md` §0.
- **gate@6 console REDESIGNED around a persisted draft dispatch (2026-07-13, PR #256)** — the original
  build's ephemeral client-side district checklist + separate flat dispatch list is replaced by the
  `stage1_queue`-`Batch`-shaped pattern: a persisted, reopenable `dispatch_draft`/`dispatch_draft_district`
  entity a human builds up (add/remove districts, per-rep council overrides, verified-only toggle) before
  freezing, on `POST /api/dispatch/{draft_id}/freeze` (a thin wrapper reusing the unchanged
  `stage6_dispatch.dispatch_handoff`). One unified left-pane list (drafts + frozen dispatches); an
  always-populated center pane (editable draft tree / read-only frozen view). Each frozen dispatch carries
  a 3-value `origin` (`draft`/`stage7`/`console`) **derived live from receipts on every read, never
  stored** — `extraction_request.executed_ref`/`route` proves a Stage-7→6 back-edge origin, a
  `dispatch_draft` match proves a console-draft origin, neither proves a genuine first-run/batch console
  dispatch (an earlier cut inferred origin from draft-*absence* alone, which wrongly badged ~12 genuine
  console dispatches as "from Stage 7" — replaced with the receipt-derived form for auditability). All
  draft mutators take a `FOR UPDATE` row lock (a concurrent double-freeze TOCTOU, found + fixed in review).
  The `/api/handoff/{preview,dispatch,candidates,councils,inspect}` routes from the original build are
  KEPT as a documented "dispatch without a draft" escape hatch, not retired. See
  `STAGE6_DISPATCH_DESIGN.md` §0b for the full architecture + the PR #256 review-fix log.
- **Stage 7 + gate@7 BUILT + HARDENED (REQ-117/REQ-118, 2026-07-03 through epic #163, 2026-07-05)** — the
  council extraction (per-rep council → cross-family consensus → judge-on-disagreement, durable/resumable
  per-district streaming, GT-scored 95.2%/99.3% band/per-school on `batch_00000`) + the deterministic
  request-more-evidence **detect → rank/defer → review → execute** loop (§0/§3F/§4/§6 of
  `STAGE7_EXTRACT_DESIGN.md` for the full build + decision log). Execution: 7→6 bundles a
  district's approved alternate-rep re-dispatches into ONE round (picking the yield-ranked alternate, not
  image-first) + 7→2/7→3/7→1 collect into a Stage-1 follow-up batch that shapes its own discovery
  (untried-schools-first, else widened SERP queries) and defers live while a cheaper 7→6 remedy is
  unexhausted — under the **REQ-051 budget governor** + a per-district **rounds** depth guard. The gate@7
  console now has execute/compose buttons, request lineage (where an executed directive went + its live
  state), blocked/deferred badges, and an in-Stage-7 preview modal; Stage 6's dispatch list has a "Run
  extraction" trigger; a follow-up's compose auto-flows gate@1 + Stages 2→3→4 to gate@5 (§11i). Two
  hardening passes: the 2026-07-04 review (epic #133, children #134–#146, all closed; root theme: the new
  execution path had re-implemented invariants instead of inheriting them) and epic #163 (2026-07-04/05,
  PR #167, 21 commits — the console-maturation + loop-correctness pass, each commit adversarially
  reviewed before the next). #147/#148 (cleanup/efficiency) remain open. **Now built:** Stage 8 (#89) and
  the Stage-9 write (#93/#94/#95). **Not yet run:** a clean live non-benchmark end-to-end pass of the fully-corrected
  loop in one sitting (#122) — exercised repeatedly in pieces against real districts during epic #163's
  shakedown, which is what surfaced most of what it then fixed.
- **Council Lab BUILT, first experiment MEASURED (2026-07-04)** — its own note now,
  `COUNCIL_LAB_DESIGN.md`: the judge-replay harness (`council_lab.py`) validated the image
  council's Qwen-VL judge swap (#82, closed — the prior DeepSeek V3.2 judge was non-vision-capable and
  404'd on every image call). Remaining backlog (tracked: #80/#81): `cost_benchmark` — measured token
  rates + live OpenRouter pricing; composition re-benchmark.
- **Then:** **Stage 8 (aggregate)** + REQ-100 (staleness).
  Per-stage detail: `STAGE1_QUEUE_DESIGN` §6 (gate@1), `STAGE2_DISCOVER_DESIGN` §7 (the SERP cascade),
  `STAGE3_CAPTURE_DESIGN` §7, `STAGE4_PROCESS_DESIGN` §4a/§4b, `STAGE5_FILTER_DESIGN` §A–D,
  `STAGE6_DISPATCH_DESIGN` §0, `STAGE7_EXTRACT_DESIGN` §0.

### 11i. Gate taxonomy — structural vs. supervision; the follow-up gate posture (DECIDED 2026-07-04, epic #163)

**Structural vs. supervision gates.** The *canonical* gate design was only **three checkpoints — gate@1,
gate@5, gate@8** (the original CP-A/B/C, §11a). Each decides something genuinely NEW every time it fires
(the right targets / is this URL real schedule data / is this the final answer) — they are **permanent**,
surviving even into a fully self-governing pipeline. **gate@6 and gate@7 EMERGED later**, from API-spend
caution during a context-clear cycle, not first-principles design (Ian, confirming this directly: "gate@6
and gate@7 emerged as a result of context clears and my caution around API spending"). They are
**supervision gates** — still "the right thing to have when running with high supervision," but the FIRST
candidates to relax as reliability is proven, per the ramp-up model (§11b).

**Follow-up gate posture — a prior approval justifies auto-advancing REDUNDANT gates, never new-decision
ones.** A follow-up batch (7→2/7→3/7→1 → Stage 1) originates from an **already-approved gate@7 decision** —
re-approving it downstream is redundant *where the downstream gate would re-decide the same thing*, but
not where it decides something new:
- **gate@1 auto-passes for a follow-up**, and the Stage 1→2→3→4 de-facto "click Start" gates auto-chain
  (the follow-up **auto-flow**, REQ-118/#157, built) — the targets were deterministically derived from the
  approved request; there's nothing new to approve.
- **gate@5 stays manual** — a follow-up produces brand-new, never-labeled URLs; this is the one truly
  structural, data-quality gate in the chain, and auto-advancing it would be re-deciding something new
  without review. (gate@5 already auto-passes tier-A records per its OWN defined rule, `release.decide()`
  — confirmed still correctly enforced during epic #163's audit; that is gate@5's existing selective
  automation, not a new relaxation.)
- **gate@6 stays manual** — the spend gate, Ian's explicit call, unrelated to the follow-up-origin logic.
- **Receipts are written at every stage regardless of auto-advance** — the auto-flow doesn't trade away
  transparency, only the click.

This is NOT "follow-ups get weaker supervision" — it's the general principle that **a gate whose decision
was already made upstream can auto-advance; a gate deciding something genuinely new cannot**, applied
consistently. See `STAGE7_EXTRACT_DESIGN.md` §3F for the built auto-flow supervisor
(`process_governance/server.py`'s `_autoflow_followup`) and its govdb tests.

### 11j. Discovery-scope policy & discovered domains — the #164/#572 console control surface — BUILT 2026-07-20

**`common/discovery_policy.py` — the 4-position discovery-scope policy state machine.** Governs FIRST-RUN
batch composition ONLY — the 5→1/7→1 escalation ladders (§11e) are failure-driven follow-ups, individually
gate@1'd, and are deliberately NOT gated by this policy: gating them would block the very repair mechanism
that makes staying on the conservative default safe. Four positions, in escalation order:
**`domain_only`** (geo first-run composition refused — the high-supervision default) →
**`geo_for_blank`** (geo first-runs allowed for blank-domain districts; the operator picks per batch) →
**`geo_interleaved`** (the standard draw picks each batch's scope probabilistically, weighted by the
remaining blank-vs-domained eligible populations, recorded on the batch — §11k) → **`geo_all`** (geo
composition allowed for ANY district — the measured geo-vs-domain comparison mode, feeding the #118
attribution card, §11f). Stored as an **append-only `discovery_policy_event` audit log** (PRECIOUS,
git-twinned to `discovery_policy.json` — §1) — the current policy is simply the latest row; an empty table
reads as `domain_only`. `get_policy`/`set_policy` are the read/write pair; `set_policy` is **idempotent**
(a no-op, no event row, when the requested policy already holds) and is **serialized via a
transaction-scoped `pg_advisory_xact_lock`** (`hashtext('discovery_scope_policy')`) — a real design
decision worth naming, because the pool-drained auto-advance (§11k) is a genuine SECOND writer alongside a
human's console set, and an unserialized read-modify-append could fork the audit chain's `previous`
linkage. `advance_one_step` is the #164 one-step auto-advance — exactly `domain_only → geo_for_blank`,
never further, a no-op from any other position. The module's own header comment frames the whole design as
issue #164's "AGREED DESIGN (2026-07-19)".

**`common/discovered_domain.py` — the confirmed-domain store + its training corpus.** `DiscoveredDomain` is
a **one-row-per-district** PRECIOUS table (git-twinned to `discovered_domains.json`) holding a
human-confirmed scoping domain a geo discovery run derived — a **third domain source**, alongside NCES
`WEBSITE` and the #229 admission guard, for a district whose NCES domain is blank or junk (the Millard
`mpsomaha.org` motivating case, #227/#229). `DiscoveredDomainDecision` is the **append-only confirm/reject
training corpus** (git-twinned to `discovered_domain_decisions.json`): every human decision on a geo run's
derived-host PROPOSAL, `confirm` or `reject`, with a **reason required on reject** — the negative class a
future auto-confirmation trains on, the same propose-with-evidence/human-decides discipline as
`CMS_HOSTS` additions. `record_decision` appends one row (a changed mind is a NEW row, never an update, per
the labeling-serves-learning principle — disagreement is the primary product); `confirm` upserts the
operative `DiscoveredDomain` row (validated against `is_scoping_domain`); `all_confirmed` is the #229
admission guard's second source; `latest_decisions` is the Stage-2 discovery card's "already decided"
lookup.

**Console surface (`process_governance/server.py`).** `GET /api/discovery-policy` returns the current
policy, the 4 positions (with UI copy), and the recent event history; **`?pools=true`** additionally runs a
**live blank-vs-domained eligible-count query** (`Q1.scope_pool_counts`, an NCES-corpus pass, seconds-scale)
— best-effort, degrading to `null` when the CCD CSVs aren't on disk, and off by default (the batch-create
dialog asks for it; the plain Settings card load does not, to stay cheap). `POST /api/discovery-policy`
sets the policy — an audited governance decision — and refreshes the `discovery_policy.json` twin
post-commit. `POST /api/discovered-domain` (`discovered_domain_decide`) records a confirm/reject decision
and, on confirm, also upserts the operative `discovered_domain` row; both twins refresh post-commit,
deliberately AFTER the decision transaction commits, so a backup-write failure can never roll back the
human's decision.

### 11k. `queue_create`'s scope-aware rewrite — BUILT 2026-07-19/20 (#164/#572)

`POST /api/queue/create` (`queue_create`, `process_governance/server.py`) composes a batch under three
scope-aware behaviors layered onto the #164 axes:
- **`district_ids` operator targeting** — an optional explicit district-id list in the payload restricts
  the draw to exactly those districts (#572 path 4: "dev/manual batches on direction," an exception path,
  not the SOP). A targeted draw that matches nothing is reported as an operator-input miss (a 409 naming
  the missing ids) rather than silently persisting an empty batch — and this path never trips the
  pool-drained auto-advance below.
- **The `geo_interleaved` weighted draw** — when the policy is `geo_interleaved` and the caller didn't pass
  an explicit `discovery_scope`, the batch's scope is DRAWN (`Q1.draw_interleaved_scope`), weighted by the
  remaining blank-vs-domained eligible populations (`Q1.scope_pool_counts`), and **seeded by `batch_id`**
  — the same weights against the same batch id always draw the same scope, so the composition is
  reproducible from the receipt's own terms, never a hidden coin flip. The draw + its weights are recorded
  in `batch.meta_json` (`scope_draw`) for the audit trail.
- **Pool-drained auto-advance at compose time** — a domain-scoped first-run batch that draws NOTHING while
  blank-domain districts remain (`_domain_excluded` non-empty) is the moment the conservative `domain_only`
  default stops meaning anything: the endpoint fires `DPOL.advance_one_step` (auto-advancing
  `domain_only → geo_for_blank`) and returns a **409** whose notice names the auto-advance (or, if the
  policy already allows geo, simply reports how many blank-domain districts remain). This passes the same
  §11b risk-asymmetry test as gate@7's auto-withdraw and #229's fail-closed guard: observable (the event
  row + the 409 notice), reversible (`set_policy`), and spend-conservative (it composes nothing by
  itself — a human still composes the geo batch as a deliberate next action).

Policy + the confirmed-domains snapshot are read **once**, before `build_batch`'s ~10–20s pure compose
runs — deliberately un-locked (a domain confirmed or a policy flipped mid-build isn't reflected in *this*
batch, only the next one — bounded and self-healing).

### 11l. `district_status.remediation_receipt()` — the canonical registry-ahead-of-disk excuse — BUILT (#572)

`common/district_status.py`'s `remediation_receipt(district_id)` is, per its own docstring, **"the ONE
shared home (#572) for the check every stage reconcile consults"** — the function each stage's own
`reconcile()` calls before treating a registry-says-done-but-disk-is-missing state as a CONTROL FAILURE
halt. It looks for the newest on-disk decontamination restore point
(`data/acquisition/remediation/<district_id>_<ts>/`, written by `remediate_contamination.py` BEFORE it
mutates anything) and, if one exists within its trust window, excuses the halt: remediation deliberately
strips a district's artifacts while PRESERVING its state history (auditability — §1's north star), so
registry-ahead-of-disk is that path's expected, receipted end state — the stage redoes the work fresh
(merge mode) instead of halting on an assumption that something is silently missing.

**Now TIME-BOUND** (`REMEDIATION_RECEIPT_MAX_AGE_DAYS = 30`, #575 narrowing): a receipt older than 30 days
no longer excuses a halt — parsed straight from the receipt directory's own timestamp (no DB read, so the
deliberately DB-free reconciles stay DB-free). Past that window a desync surfaces as a genuine halt again,
on the theory that a receipt this old is more likely coincidence than the explanation.

**Documented KNOWN RESIDUAL:** the check is **not stage-scoped** — a receipt from a Stage-2 remediation
still excuses a Stage-3/4 desync for the *same district*. This is a deliberate, bounded trade-off, not an
oversight (bounded to redundant spend either way — the sanctioned path always REDOES the stage, nothing
missing is ever assumed done — never silent trust). Full stage/recency tightening (compare the receipt
timestamp against the district's latest stage-N `state_event`) would need a DB read inside the deliberately
DB-free reconciles, and is deferred until remediation volume grows past a handful of districts.

**3 call sites** — Stage 2 (`stage2_discover/discover_stage2.py`), Stage 3 (`stage3_capture/capture_stage3.py`),
and Stage 4 (`stage4_process/process_stage4.py`), each in their own `reconcile()`. A stage's own design note
should cross-reference back to `PIPELINE_GOVERNANCE_AND_STATE.md` §11l rather than re-explaining the
mechanism.

---

## 12. The Stage 4 → Stage 5 seam: where the batch dissolves and the district takes over — BUILT (REQ-111, 2026-06-29)

This is the most important structural fact for whoever picks up Stage 5. **The console was BORN as a
Stage-5 review tool** (the labeling surface for the deterministic signals) and only *later* grew upward
into the stage-selectable governance console for Stages 1–4. Stages 1–4 are all **batch-shaped**: a batch
is the unit that's queued (gate@1), discovered, captured, processed — and the left pane of each of those
views is a *list of batches*. **Stage 5 is deliberately NOT batch-shaped.** At Stage 5 the work is
per-URL/per-representation, the driving entity is the **district** (and below it, the record/representation),
and the batch **dissolves as a meaningful unit** (§6 already records this: "at Stage 5 the batch dissolves;
CP-B is the per-URL review"). The Stage-5 view's left pane is districts→records, not batches. **This
difference is on purpose — do not try to make Stage 5 look like Stages 1–4.**

**§12a — The dispatch mechanism (what fires the transition).** When a Stage-4 process run resolves the whole
batch (`status_for_batch` rollup `resolved == total`, and the run did work `todo>0`), the orchestration
layer's `process_governance/server._ingest_stage5_if_complete`:
1. runs **`build_signals.ingest_batch(district_ids)`** — the **incremental, batch-scoped** Stage-5 ingest
   (ensures the signal schema, re-ingests ONLY this batch's districts via per-district DELETE+INSERT,
   regenerates their `filtered.json`). Prior batches untouched; **cost ∝ batch, not corpus** — the reason
   the full `ingest()` DROP+rebuild was rejected as the routine dispatch (it would re-grow the very lag we
   removed). PRECIOUS `label`/`cluster_split` survive (rec_key stable).
2. records a **Stage-5 progression `state_event` per district** (`stage=5`, `stage_name="filter"`,
   `outcome="ingested"`, `actor="auto:stage5"`) → `furthest_stage` → 5 ("done through Stage 4 / in Stage 5").
3. emits a `stage5_ingested` job event (or `stage5_ingest_failed`, logged — best-effort, never fails the
   already-durable Stage-4 job).
The trigger lives in the **app layer, not `stage4_process`** — `stage4_process`→`stage5_filter` would break
the import-linter independence contract; `process_governance` may import every stage.

**Registry save/export semantics this dispatch relies on (#330, epic #111 Phase 1, PR #553):**
`district_status.save()` clears `registry["_events"] = []` immediately after the `state_event` insert
commits, and *before* the (unguarded) `export_status()` call — so a caller retrying `save()` after an
export failure can't double-insert, and `export_status`'s failure now correctly **propagates** rather
than being swallowed. `server._ingest_stage5_if_complete` (and its sibling `stage5_bookkeeping_failed`
discriminator) relies on that propagation to distinguish a real bookkeeping failure from a clean run.
The same Phase-1 sweep also consolidated the tmp-file+`os.replace` atomic-write pattern into one shared
`common/paths.atomic_write_json` helper (used today by Stage 2's manifest writes; `batch_store.
write_receipt` and `district_status.export_status` still hand-roll their own copy, tracked #554), and
added a secrets pre-flight (`common/discover._require_secrets`) that halts Wave-1's Bright Data/Serper
calls with a precise "key not set" message *before* any HTTP request, rather than a reactive patch at
the 401 site.

**§12b — Why this design (the choice we made, for future-me).** The user's instinct was "precompute the
Stage-5 ingest at batch completion so the Stage-5 view loads with no lag." Correct — but a *full-corpus*
rebuild at batch completion just relocates the lag and makes it grow with history. So the build is
**incremental** (Option B in the design discussion): `ingest()` was refactored to share an `ingest_district()`
unit with the new `ingest_batch()`; the signal-table DDL split into drop + `CREATE IF NOT EXISTS`. This is
the **first piece of the Stage-5 rework** — the signal tables moved (for the batch path) from drop+rebuild
to per-district UPSERT, exactly mirroring what the cross-stage cache (REQ-110) already did. The full
`python3 -m …stage5_filter.build_signals` remains for schema changes / recovery.

**§12c — The Stage-5 console rework — BUILT (REQ-112, 2026-06-29).** The dedicated Stage-5 pass landed. **Done:**
the **district-driven attention queue is the home view** (§7b realized) — the default is no-grouping, districts
sorted **attention-first** (the inverted-confidence "needs my judgment" score, `STAGE5_FILTER_DESIGN` §A), with
**facet grouping** (pipeline_state / state / topology, collapsible mini-dashboard headers), **record-facet
filtering** (label/tier/reason — district stays visible), **multi-key sort** asc/desc, a **follow-up-flag**
action (top attention tier), **DB-backed saved views**, and **re-fetch-on-show**. The gate@5 per-URL review is
the (unchanged) center/right panes, now reached through this list. The plumbing finished too (SQLite vestige
retired; signal tables a never-dropped live working store on the incremental path). **Still open (carried):**
the **recency gate (REQ-044)**; a full **`state_event`-subscription projector** generalizing the two inline
`release.generate` hooks (§6) (tracked: #100); the **harness attention-ordering metric** (deferred — attention ≠ target-precision;
needs a reason×label cross-tab); the **"District Investigator"** holistic-journey view (the data model — `district_id`
+ the event log — already supports it; out of scope here) (tracked: #101). NCES **locale** facet descoped (not in our CCD data).
Authority for the as-built: `STAGE5_FILTER_DESIGN` §A–D.
