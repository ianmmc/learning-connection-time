# Pipeline Governance, State Model & the Stage 5→6 Release (2026-06-26)

> **Status: DESIGN + BUILD UNDERWAY (updated 2026-06-26).** Shipped: the tuning foundations
> (REQ-095 ledger, REQ-096 frontier) and **REQ-098** (acquisition tree packaged, code moved, tooling
> wired — import-linter/grimp/vulture/dependency-cruiser). **REQ-103 (Postgres governance DB) is
> functionally COMPLETE** — 103a (foundation) + **103b–f** (ingest + readers + tests migrated
> SQLite→Postgres, committed `bbd0f66`) + **103c** (cross-stage cache) + **103g** (these docs) all done;
> see §1b. **REQ-099 (state event-log) is also COMPLETE** — `district_status` → Postgres `state_event`
> append-log + `current_state` SQL view; in-memory registry contract preserved (stage scripts unchanged);
> 36-district/84-event data migrated; `district_status.json` is now the regenerable git-tracked backup
> (§3). **Next build step is REQ-094** (the `filtered.json` release generator, §4/§5). Still design-only:
> console UI (REQ-100/102), Stage 2 headless (REQ-104). This note is the architecture for three coupled decisions that outgrew
> `STAGE5_FILTER_DESIGN_2026-06.md`:
> 1. **STATE vs DATA** — migrate the cross-stage *registry* (`district_status.json`) into the DB;
>    keep the per-stage *data* artifacts as JSON on disk.
> 2. **The Stage 5→6 release** — `filtered.json` as a generated **export** of the DB's release state
>    (not the primary store), + the Stage 6 `handoff_<hash>_<timestamp>.json` immutable dispatch record.
> 3. **The app's scope** — the Stage-5-only review app → a **stage-selectable governance console**
>    at `infrastructure/acquisition/process_governance/`, the human-in-the-loop surface for CP-A / CP-B / (later) CP-C.
>
> Companions: `ACQUISITION_PIPELINE.md` (the 9 stages + checkpoints), `STAGE5_FILTER_DESIGN_2026-06.md`
> (Stage 5 signals/tiers/clustering/tuning — still authoritative for *that* content), `PROJECT_HISTORY.md`
> (high-level ADR log). Standing checkpoints (CLAUDE.md): **CP-A Queue**, **CP-B Input/Release**, **CP-C
> Output→Write**.

---

## 1. The organizing principle: STATE vs DATA

The registry currently blurs two different things. Separating them resolves the whole design:

| | what it is | authoritative home | properties |
|---|---|---|---|
| **DATA** | `discovery.json`, `candidates.json`, `captures.json`, `processed.json`, `batch_*.json` + the capture binaries | **JSON on disk**, next to captures | content; **regenerable from the web**; read natively by the Node capture half; relocatable as one tree (REQ-087) |
| **STATE** | where each district is in the pipeline; what's approved at CP-A; what's released at CP-B; the re-discovery loop | **the DB** | small, queryable, concurrently-updated, *not* a linear listing; **precious** (human decisions, not rebuildable from DATA) |
| **SIGNALS** | tiers, categories, signal vectors, clusters | the DB | **regenerable cache** — dropped + rebuilt each ingest (today's behavior) |
| **LABELS / SPLITS** | the human ground truth + cluster-split overrides | the DB | **precious** — already backed to `labels.json` / `cluster_splits.json` |

**The claim is narrow and safe:** move *STATE* into the DB, keep *DATA* authoritative on disk. We are **not**
making the DB authoritative for everything — it is a single binary blob (not git-diffable, not Node-native,
corruptible). DATA stays on disk; the DB owns STATE + the precious human signals + the regenerable cache.

**Consequence — the "DB is purely a regenerable cache" framing officially ends.** The DB now holds two
precious things (labels, *and* checkpoint/lifecycle state) beside the regenerable signal cache. Both
precious classes get the **established backup pattern**: export to a version-controlled JSON, re-importable
after a DB wipe (exactly as `labels.json` / `cluster_splits.json` work today). We extend that pattern; we
do not invent one.

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
103g** in the follow-up pass. The old `data/acquisition/stage5_review/review.db` (SQLite) is **kept
on disk as the 103f reference** — retire it (and `paths.REVIEW_DB`) once you're confident.
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
SQLite file are retained as the 103f reference until retired.

---

## 2. What is precious vs regenerable in the release (a clarifying decomposition)

The release decision is **largely a deterministic projection** of inputs we already store:

```
release_content(district)  =  f( labels , signals , tier-config )      # PURE, regenerable
```

So `filtered.json`'s *content* needs **no new precious table** — it is recomputed from labels (precious,
stored) + signals (regenerable) + config (versioned). What **is** new-precious is the **act**:

- **the CP-B release event** — "a human approved sending *this* district forward, at *this* time, at *this*
  `(config,labels,data)` fingerprint." Not derivable from labels; precious; part of lifecycle history.
- **the CP-A queue-approval event** — same shape, one stage up.
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
  event_id INTEGER PK, district_id TEXT, stage TEXT, checkpoint TEXT,   -- 'CP-A'|'CP-B'|'CP-C'|NULL
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
Serves **two consumers**: Stage 7 (the files to extract) **and** Stage 6 (district-level go/no-go needs the
topology/completeness/cost summary). District-level metadata lives **inside** each `filtered.json`
(self-contained); a thin generated **Stage-6 index** avoids re-scanning thousands of dirs at scale.

### `handoff_<hash>_<timestamp>.json` — Stage 6, IMMUTABLE dispatch record
"Which districts we sent to the council in *this* run, and exactly what." **Immutable snapshot** — a new
dispatch is a new file; never regenerated. **Freezes** each district's `filtered.json` content (or its
fingerprints) *at dispatch time*, so a later regeneration (retune / re-discovery) can't silently rewrite
history — required by the request-more-evidence loop and for "what did we actually send on date X." Carries
the council config (which models) + total cost estimate. A `dispatched` `state_event` references its hash.

---

## 6. The "Generate" trigger, menu semantics & staleness

The CP-B release is triggered from the console (a control in the header, near labeled/total + the Glossary
modal). It runs the **deterministic generator** (a script/function), writes `filtered.json` per district,
and records the CP-B `released` events. **Same function the future scheduler calls** — the button and
automation share one code path (the "ease toward full automation" goal; `actor` flips human→auto).

**Staleness via the shared fingerprint** (the convergence with the tuning loop): each `filtered.json` is
stamped with `(config,labels,data)`; **stale** = current ≠ stamped. The menu options map to states:

| menu option | meaning |
|---|---|
| new : {all,labeled} | districts with **no** `filtered.json` yet |
| new + changed : {all,labeled} | + districts whose fingerprint drifted (labels/captures **or** config) |
| all : {labeled} / all | regenerate everything (a retune invalidates all → honest but noisy) |
| selected | a scope mechanism (checkboxes) — **regenerate these districts now** |

`{labeled}` vs `{all}` = the qualification basis: **labeled** uses human labels only; **all** also lets
unlabeled-but-high-tier records flow on the auto-filter (serves the workflow evolution: label-everything →
inspect-scoring). **Open:** should a *config* retune mark districts stale (honest, noisy) or should
staleness track only labels/captures with config-version shown separately? Lean: stamp all three, let the
console filter by *which* changed.

---

## 7. App scope: the review app → stage-selectable governance console (`process_governance`)

The "Stage 5 - Capture Review" title by the wordmark becomes a **stage selector**; each stage swaps the
view/controls. Once cross-stage STATE is in the DB, the app is the governance console for every checkpoint:

- **Stage 1 / CP-A** — review & approve queued `batch_*.json` (today out-of-band); a `released`-shaped
  approval event, same interaction as CP-B.
- **Stage 5 / CP-B** — the current review/label surface + the **Generate/Release** trigger (§6).
- **(later) Stage 7 / CP-C** — approve extraction outputs before the DB write.

### Code structure (PROPOSAL — confirm)
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
Postgres migration builds the cross-stage cache now. The per-stage JSON stays authoritative on disk; the
DB caches all stages (regenerable), as it caches Stage 5 today. **Reframe (user):** the district-dir JSON
files shift role from *data carriers through a transformation* to **auditable receipts** — the DB is the
working store, the JSON is the on-disk audit trail.

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

### Stage 2 discovery goes headless via the Claude Code CLI (not the Agent SDK)

The "subagent requires a chat (Claude) open" framing is **dissolved**. Each `claude -p` invocation is a
*full headless agent*; we don't need the subagent abstraction. **Stage 2's orchestrator shells out to
`claude -p` per district**, each doing one district's WebSearch and returning JSON; the orchestrator
collects them and runs the existing deterministic Wave-2/gating/flatten logic. No chat, no human-in-loop,
**schedulable overnight**.

**Search providers are a pluggable layer (extensibility — explicit requirement).** Each provider sits
behind one contract — *given a school, return candidate URLs as JSON* — so providers can be added,
reordered, or swapped without touching gating/flatten/dedup. Today: **Wave 1 = Claude CLI WebSearch**
(subscription), **Wave 2 = OpenRouter `gpt-4o-mini-search`** (paid). Designed-for future providers:
**Bright Data, the Brave Search API, or a new cheap web-search model on OpenRouter** — the CLI is *one*
provider, not the architecture. Whether to cascade (stop at first wave that satisfies) or run several
unconditionally is a separate, still-open tuning question (ACQUISITION_PIPELINE Open-decision #7).

**Why CLI, not the Agent SDK (decisive — cost):** the CLI uses **subscription auth** (Pro/Max quota) when
logged in; the **Agent SDK requires `ANTHROPIC_API_KEY` = per-token billing** (its overview explicitly
disallows claude.ai login for SDK-built products). The whole point is leveraging the existing
subscription, so CLI wins. *Verified clean:* no Claude API account exists → no `ANTHROPIC_API_KEY` to
shadow the subscription (the only keys present are OpenRouter / Perplexity / Gemini, none of which is
Claude Code auth).

**The call (real flags, corrected from the guessed ones):**
```bash
claude -p "<stage2 search prompt>" --model haiku --effort low \
  --output-format json --allowedTools "WebSearch" --bare --max-turns 4
```
- `--allowedTools "WebSearch"` is **required** in headless (print mode can't answer a permission prompt).
- `--effort low` (not `--effortlevel`); `--bare` skips skill/hook/MCP/CLAUDE.md auto-discovery for a fast
  scripted start — so the **full search prompt is passed in**, not invoked as the `stage2-discover` skill.
- `--json-schema <file>` (print mode) can force the candidate output into our exact shape.
- Background option: `--bg` + `claude agents --json` / `claude logs <id>` (ties to choice C).

**Per-stage cost model** (feeds the cost estimates in `filtered.json`/`handoff`): **Stage 2 discovery →
subscription (≈free quota) via CLI**; **Stage 7 extraction → paid OpenRouter API**. The expensive stage is
7 — which *argues for aggressive Stage-2 recall*, since discovery is essentially free to run overnight.

**Still to verify before building the Stage-2 conversion:** WebSearch behavior + subscription rate limits
at overnight-17k-district volume. Pre-registered as its own step (REQ-104).

---

## 7b. Console — running UI notes (deferred from the plumbing; revisit at console-build, REQ-100/102)

A scratchpad of console/UI-relevant questions the plumbing work raises, captured so context resets don't
lose them. **No layouts yet** (user's call) — these are *things the eventual UI must expose or decide*,
recorded as they surface:

- **Data source flips SQLite→Postgres** (REQ-103): the console reads/writes via `session_scope` against the
  isolated `governance` DB, not a local SQLite file. The "open a file, no Docker" ergonomic of the old
  review app goes away — the console now requires the container up (already a project precondition).
- **Home view = a projection over the event log** (REQ-099): "what needs my attention" (districts awaiting
  CP-A approval / CP-B release / re-discovery) is a query over `state_event` current-state, not a static
  list. The UI's primary surface is this attention queue, not a stage tree.
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
(steps 3/5/7) → Stage 5→6 handoff (step 6). **Doc-update obligations attached to steps:**
- *Now (this pass):* `docs/DATA_SOURCES.md` gains a reference to `docs/ACQUISITION_PIPELINE.md`; the toolchain
  is recorded here in §10 (user: keep it in this note for now, not a separate file — extract later if it grows).
- *On REQ-103 completion (Postgres+Docker migration):* update `docs/DATABASE_SETUP.md` and
  `docs/GETTING_STARTED.md` for the new isolated `governance` DB (these are deferred until the migration lands).

---

## 9a. REQ-098 execution plan — package + code move + tooling (drafted & approved 2026-06-26)

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
`docs/technical-notes/Polyglot Pipeline Architecture Toolchain.md` (Perplexity deep-research) + the
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
| **Cross-boundary edges** (Python→subprocess→Node/CLI · shared `config/*.json` read by both · file-based stage handoffs) | **no tool** → a hand-declared `arch-manifest.json` + **fitness-function tests** (AST scan of `subprocess.*` / config-path reads, asserted against the manifest); `datacontract-cli` for stage-handoff schema validation | **manifest+tests grown alongside the build; datacontract-cli when REQ-094/101 land** |

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
shared-config / file-handoff edges as a *unified* graph reconciled against a declared manifest. Both the
agent's and the research's conclusion is that no production tool closes this. If our `arch-manifest.json` +
fitness-function generators prove out here (and ideally survive a second real project shape, not generalized
from N=1), they're a candidate to extract and publish. **Architect it cleanly separable; do not design *for*
publication now.** Flag the moment it's earned its generality.
