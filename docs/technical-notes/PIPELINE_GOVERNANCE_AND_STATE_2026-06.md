# Pipeline Governance, State Model & the Stage 5→6 Release

> **Authority:** the cross-stage architecture — DB-vs-disk split, state-event log, gate/console model,
> the Stage 5→6 release mechanics. Per-stage present-state detail lives in each `STAGE*_DESIGN_2026-06.md`;
> this doc is what ties them together.
> **Audience:** anyone building or reasoning about a pipeline stage, the console, or the DB schema.
> **Companions:** `ACQUISITION_PIPELINE.md` (the 9-stage map + flow diagram), every `STAGE*_DESIGN_2026-06.md`
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

**Current build state (2026-07-09):** REQ-098/099/103/094 (packaging, state-event log, Postgres governance
DB, event-driven `filtered.json`) are all COMPLETE — see §1b, §3, §6. The console is built and run live
through **`gate@7`**: gate@1 (REQ-102), Stage 2 (REQ-104), Stage 3 (REQ-110), Stage 4 + the Stage 4→5
incremental handoff (REQ-111, §12), the Stage 5 district-driven console (REQ-112), Stage 6 dispatch/freeze
through the Stage 6→7 seam (REQ-101), and Stage 7 council extraction + the gate@7 review console (REQ-117:
extraction results + the request-more-evidence **detect/rank/defer/review** loop — see
`STAGE7_EXTRACT_DESIGN_2026-06.md` §0/§4), and the request-more-evidence **execution + console maturation**
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
measurement detail: `STAGE7_EXTRACT_DESIGN_2026-06.md` §6 (decision log).
**Not yet built: Stage 8/9.** (tracked: #89, #93) **Gates are stage-numbered (§11):**
`gate@1` (queue) · `gate@5` (per-URL review) · `gate@6` (dispatch) · `gate@7` (council requests) · `gate@8`
(results) — **1/5/8 structural (permanent), 6/7 supervision (first to relax) — §11i.** §8, §9, and §9a
below are **historical** — fully executed planning/sequencing docs kept in place because their section
numbers (`governance §9a`, etc.) are cross-referenced elsewhere; see the banners on each. **Council Lab
BUILT, first experiment MEASURED (2026-07-04)** — the judge-replay harness (`council_lab.py`) validated the
Qwen-VL image-judge swap (#82, closed); see `COUNCIL_LAB_DESIGN_2026-06.md`. Next: a clean live
non-benchmark end-to-end pass of the now-hardened request loop (tracked: #122 — the natural next exercise
now that the hygiene campaign is done), Stage 8 (aggregation), or the Lab's remaining backlog
(`cost_benchmark`, prompt A/B, tracked: #80/#81); still open: REQ-100 (staleness) (tracked: #100), gate@6
auto mode (tracked: #104), the gate@7 inline PNG/PDF viewer (tracked: #151), a first-class "abandoned"
batch status + gate@6 already-dispatched indicator (tracked: #168/#171), and the arch-manifest/fitness-test
infra (tracked: #124, deliberately parked until the hygiene campaign's remaining scoring-detector batch
lands).

---

## 1. The organizing principle: the DB is the working store; disk holds binaries + receipts

**The governance DB is the working store and the pipeline's reflection of state.** Each stage projects its
slice into the DB, and the next stage (and the console) reads it from there — **data flows DB→DB, not
file→file.** Disk holds two things the DB deliberately does not: the **capture binaries** (too large for a
DB, regenerable from the web) and the **regenerable JSON files** the stages emit. Those JSON files are
**auditable receipts** — for state-confirmation, human inspection, and recovery — **not** the medium that
carries data between stages. (That file-as-transmitter model was the original 2026-06-26 framing; it was
retired when the cross-stage cache became a live working store — REQ-110/111/112; build history in §7a-A / §12.)

| class | what it is | home | properties |
|---|---|---|---|
| **STATE** | pipeline position; gate@1 approvals; gate@5 release; the re-discovery loop | **DB** (working store) | the `state_event` append-log + `current_state` view (§3); **precious** — JSON-backed, re-importable |
| **SIGNALS** | signal vectors, detector votes + the send/suppress/review decision, tier, category, clusters, attention (REQ-113 V2) | **DB** (working store) | regenerable; a **never-dropped live store on the incremental path** (REQ-110/111/112) — full drop+rebuild only for schema changes / recovery |
| **FACETS** (v2.1) | the human's target-shape + confounder + location answers (`label.facets_json`, REQ-114) | **DB** (working store) | **precious** — JSON-backed with the label; the per-detector ground truth |
| **CROSS-STAGE DATA** | the queryable projection of every stage's output — `discovery_school` / `candidate` / `capture` / `processed_doc` (`common/cache_ingest.py`) + `record` / `representation` / `district_target` (Stage 5) | **DB** (working store) | regenerable from disk; **what each stage reads to drive the next**, kept fresh by each stage's finish hook |
| **LABELS / SPLITS / BATCHES / FLAGS** | human ground truth, cluster-split overrides, the queued/approved batch, follow-up flags | **DB** | **precious** — never in the ingest drop list; JSON-backed |
| **CAPTURE BINARIES** | the captured PDFs / PNGs / extracted text files | **disk**, authoritative | regenerable from the **web** (not the DB); referenced by `filename` from `representation`; relocatable as one tree (REQ-087) |
| **JSON RECEIPTS** | `discovery.json` / `candidates.json` / `captures.json` / `processed.json` / `filtered.json` / `batch_*.json` | **disk** | regenerable; the auditable record of each stage's output + the DB-recovery source (`batch_*.json` / `filtered.json` are generated *from* the DB); **NOT stage-to-stage transmitters** |

**Precious vs regenerable is the load-bearing line — not DB vs disk.** The DB holds precious things (labels,
lifecycle state, batches, flags) *and* the regenerable working store (signals + the cross-stage data
projection). Every **precious** class gets the **established backup pattern**: export to a version-controlled
JSON, re-importable after a DB wipe (exactly as `labels.json` / `cluster_splits.json` work today). Every
**regenerable** class can be rebuilt from disk (the binaries + the receipts) at any time. We extend that
pattern; we do not invent one. The DB is not a blob store: binaries stay on disk and are referenced by path.

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
governance DB. Supersedes the SQLite decision in `STAGE5_FILTER_DESIGN_2026-06.md` (§Architecture).

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
`STAGE6_DISPATCH_DESIGN_2026-06.md`.)*

### `handoff_<hash>_<timestamp>.json` — Stage 6, IMMUTABLE dispatch record
"Which districts we sent to the council in *this* run, and exactly what." **Immutable snapshot** — a new
dispatch is a new file; never regenerated. **Freezes** each district's `filtered.json` content (or its
fingerprints) *at dispatch time*, so a later regeneration (retune / re-discovery) can't silently rewrite
history — required by the request-more-evidence loop and for "what did we actually send on date X." Carries
the council config (which models) + total cost estimate + the **`verified_only`** dispatch-mode flag (a
gate@6 toggle for a labeled-targets-only, training-grade dispatch — folded into the identity hash so a
training-grade dispatch never collides with a default one). A `dispatched` `state_event` references its hash.
*(As-built detail: `STAGE6_DISPATCH_DESIGN_2026-06.md` §0/§3D/§3E.)*

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
architecture (authority: `STAGE2_DISCOVER_DESIGN_2026-06.md` §7):**
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
Data offers unlimited concurrency. Detail: `STAGE2_DISCOVER_DESIGN_2026-06.md` §7.

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
- **Tuning console surface** (§10 / REQ-095/096/097): where drift alerts, the advisory frontier (with
  which-records-move), and ledger history live in the UI — a distinct surface from per-district review.
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
- **Independence:** the stage packages do not import each other.
- **Forbidden + exceptions:** `infrastructure.acquisition` must not import `infrastructure.database` internals
  *except* the sanctioned `stage1_queue` enrollment read (and future `stage9` write) — encode via
  `ignore_imports`.
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
| **Cross-boundary edges** (Python→subprocess→Node/CLI · shared `config/*.json` read by both · file-based stage dispatches) | **no tool** → a hand-declared `arch-manifest.json` + **fitness-function tests** (AST scan of `subprocess.*` / config-path reads, asserted against the manifest); `datacontract-cli` for stage-dispatch schema validation | **FIRST INCREMENT BUILT (#124, 2026-07-09):** `arch-manifest.json` (repo root) + `tests/test_arch_manifest.py` — AST-scan fitness functions asserting (1) every external-process edge (argv-list head, surviving the injectable `_run` seam — `claude`/`node`/`pdftotext`/`pdftoppm`/`pdfinfo`/`tesseract`) is declared, (2) an invariant guard (`assert_runnable`) is reached by every declared entry point, (3) no client JS compares against a server-authoritative literal (`batch_00000`), (4) a shared client helper (`statusBadge`) is defined once, (5) each stage receipt's producer references its filename. Each check was proven to FAIL on a deliberate drift then revert. **Still to add:** `config/*.json` schema validation + `datacontract-cli` on the stage-dispatch artifacts (a bigger, separable piece; the artifacts are declared in the manifest's `file_dispatches` ready for schema refs). |

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
stories were migrated 2026-06-27 into the per-stage `STAGE*_DESIGN_*.md` notes + `OVERVIEW_AND_SETTINGS_DESIGN_2026-06.md`,
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
| **gate@6** | 6 Dispatch | approve routing/dispatch (which reps → which council config); optional **verified-only** (labeled-targets-only) mode | *new* | supervision |
| **gate@7** | 7 Extract | review extraction results + council requests/recommendations | *new, BUILT* | supervision |
| **gate@8** | 8 Aggregate | review per-band results; override needs a reason | *effective CP-C* | structural |

**gate@8 is the effective CP-C** — once results are approved there, Stage 9 writes to the LCT DB mechanically.
**Structural vs. supervision — see §11i (decided 2026-07-04):** 1/5/8 were the ORIGINAL three-gate design
(CP-A/B/C) and decide something genuinely new each time; they're permanent. 6/7 emerged later, from
API-spend caution during a context-clear cycle, not first-principles design — they're the first to relax.

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
detector, **built and validated** (`STAGE7_EXTRACT_DESIGN_2026-06.md` §0/§4); a human reviews/approves it
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
  a 7→3 recapture (dormant plumbing). See `STAGE7_EXTRACT_DESIGN_2026-06.md` §3F.

### 11e. The pipeline is CYCLIC (back-edges) — detail in the flow diagram
**As originally sketched, then as BUILT (REQ-118, updated 2026-07-05):** the four back-edges off Stage 7
are **7→6** (direct alternate-rep re-dispatch, bundled per district), **7→3** (recapture the URL), **7→2**
(targeted rediscover for a band), and **7→1** (a follow-up batch adding schools) — all built, all routing
through a Stage-1 follow-up batch except 7→6 (§3F/§11d). The Stage-8 back-edges this subsection originally
anticipated (8→1, 8→6) are **not yet real** — Stage 8 isn't built (tracked #89) — and will be documented
here once designed; don't treat them as built today. See the flow diagram in `ACQUISITION_PIPELINE.md`.
The immutable Stage-6 dispatch freeze is what keeps "what we sent" recoverable across these loops.

### 11f. Per-stage console notes
- **Stage 3** — a thin **health / emergent readout**: emergent URLs, capture failures (WAF/security
  blocks), and the **CMS/host distribution** from the `capture` table's `final_host`/`fingerprint_json`
  (REQ-103c). NOT a live PNG feed (cute, low governance value). **BUILT + RUN LIVE 2026-06-28/29 (REQ-110)**
  — reads the DB cache (incl. `capture.err` for the failure breakdown + per-district `manual_flag_all` /
  `failed` / `timed_out` / `captured_partial` states), + a per-district Node-capture run trigger.
  See `STAGE3_CAPTURE_DESIGN_2026-06.md` §7.
- **Stage 4** — same shape (ungated status + run trigger); **BUILT + RUN LIVE 2026-06-29 (REQ-111)**.
  In-process (no node-owns-shutdown); reads the `processed_doc` cache; per-district usable/not-usable doc
  counts + a **usable-representations-by-tool** readout; `no_usable_text_any`/`awaiting_capture` badges.
  A process run that **resolves the whole batch** then runs the **Stage 4→5 incremental handoff** (§12).
  See `STAGE4_PROCESS_DESIGN_2026-06.md` §4a/§4b.
- **Stages 2 & 4 effectiveness** — the **measurement-harness pattern extended upstream**: attribute each
  target-labeled record back to its discovery tool (`candidate_tools_json`) and its winning representation's
  source (`representation.source`). Same fingerprinted-scorecard discipline as Stage 5, applied to discovery
  and processing (tracked: #118).
- **Stage 6** — routing / release; **BUILT to the seam (REQ-101, merged 2026-06-30)**: the gate@6 console
  (preview the routed/priced package → Approve & freeze) → the immutable dispatch + a precious `handoff` index
  row + a per-district `dispatched` state_event; manual approve today (auto mode deferred) (tracked: #104). See
  `STAGE6_DISPATCH_DESIGN_2026-06.md` §0.
- **Stage 7** — council extraction; **BUILT (REQ-117, 2026-07-03)**: the gate@7 console (district-first —
  band rollup, accepted/unresolved facts, request-more-evidence cards with Approve/Reject/Reopen); read +
  review only, no fact/band editing (that's gate@8). See `STAGE7_EXTRACT_DESIGN_2026-06.md` §0.

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
  PRECIOUS tables (`stage1_queue/models.py`): **`batch`** (lifecycle `draft → approved` + actor/timestamps
  + prose meta), **`batch_district`** (`included` soft-reject + `ord` for a stable receipt), **`batch_school`**
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
  lint/`no-undef` gate, unlike the Python side.)
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
  the usable-reps-by-tool panel, read from the DB `processed_doc` cache) + an in-process run trigger. The
  batch resolves from the DB working store via the shared `_batch_from_db`. **No node-owns-shutdown** (the
  work is a Python call; a crash just leaves `processed.json` unwritten → reconcile re-runs). A local
  `stage2_complete` disk-scan replaced an import of Stage 3's `find_districts` (the independence contract).
- **Stage 4→5 incremental handoff BUILT (REQ-111)** — the seam where the batch hands to Stage 5. See **§12**.
- **Stage-5 console rework BUILT (REQ-112, 2026-06-29)** — the district-driven, attention-first faceted
  console; the app's origin, finally on the current architecture. See **§12c** + `STAGE5_FILTER_DESIGN` §A–D.
- **Stage 6 + gate@6 routing BUILT to the seam (REQ-101, merged PR #2, 2026-06-30)** — the `stage6_handoff/`
  package (per-rep routing data-driven off `input_kinds` + the capture-fidelity gate; cost estimator on a
  bootstrap model; immutable dispatch with a price-independent hash; OpenRouter request assembly) + the gate@6
  console view (`static/stage6.js` + `/api/handoff/*`: preview the routed/priced package → Approve & freeze).
  Approval records the index row + a per-district `dispatched` state_event **atomically**, freezes the
  immutable artifact, and **stops at the seam — no paid call** (Stage 7). Manual approve today; auto mode +
  the budget-governor cost-gate (REQ-051) deferred (tracked: #104). See `STAGE6_DISPATCH_DESIGN_2026-06.md` §0.
- **Stage 7 + gate@7 BUILT + HARDENED (REQ-117/REQ-118, 2026-07-03 through epic #163, 2026-07-05)** — the
  council extraction (per-rep council → cross-family consensus → judge-on-disagreement, durable/resumable
  per-district streaming, GT-scored 95.2%/99.3% band/per-school on `batch_00000`) + the deterministic
  request-more-evidence **detect → rank/defer → review → execute** loop (§0/§3F/§4/§6 of
  `STAGE7_EXTRACT_DESIGN_2026-06.md` for the full build + decision log). Execution: 7→6 bundles a
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
  reviewed before the next). #147/#148 (cleanup/efficiency) remain open. **Not yet built:** Stage 8/9
  (tracked: #89, #93). **Not yet run:** a clean live non-benchmark end-to-end pass of the fully-corrected
  loop in one sitting (#122) — exercised repeatedly in pieces against real districts during epic #163's
  shakedown, which is what surfaced most of what it then fixed.
- **Council Lab BUILT, first experiment MEASURED (2026-07-04)** — its own note now,
  `COUNCIL_LAB_DESIGN_2026-06.md`: the judge-replay harness (`council_lab.py`) validated the image
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
consistently. See `STAGE7_EXTRACT_DESIGN_2026-06.md` §3F for the built auto-flow supervisor
(`process_governance/server.py`'s `_autoflow_followup`) and its govdb tests.

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
