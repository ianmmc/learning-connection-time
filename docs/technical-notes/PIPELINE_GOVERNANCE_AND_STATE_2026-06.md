# Pipeline Governance, State Model & the Stage 5→6 Release (2026-06-26)

> **Status: DESIGN (design-first, no code yet).** This note is the architecture for three coupled
> decisions that outgrew `STAGE5_FILTER_DESIGN_2026-06.md`:
> 1. **STATE vs DATA** — migrate the cross-stage *registry* (`district_status.json`) into the DB;
>    keep the per-stage *data* artifacts as JSON on disk.
> 2. **The Stage 5→6 release** — `filtered.json` as a generated **export** of the DB's release state
>    (not the primary store), + the Stage 6 `handoff_<hash>_<timestamp>.json` immutable dispatch record.
> 3. **The app's scope** — `review_app` (Stage-5-only) → a **stage-selectable governance console**
>    under `common/`, the human-in-the-loop surface for CP-A / CP-B / (later) CP-C.
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

## 3. State schema (PROPOSAL — confirm the granularity)

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

## 7. App scope: `review_app` → stage-selectable governance console

The "Stage 5 - Capture Review" title by the wordmark becomes a **stage selector**; each stage swaps the
view/controls. Once cross-stage STATE is in the DB, the app is the governance console for every checkpoint:

- **Stage 1 / CP-A** — review & approve queued `batch_*.json` (today out-of-band); a `released`-shaped
  approval event, same interaction as CP-B.
- **Stage 5 / CP-B** — the current review/label surface + the **Generate/Release** trigger (§6).
- **(later) Stage 7 / CP-C** — approve extraction outputs before the DB write.

### Code structure (PROPOSAL — confirm)
- **Move the app** `stage5_filter/review_app/` (server + `static/`) → **`common/console/`** (cross-stage now).
- **Keep stage logic with its stage:** `build_signals.py` is Stage 5 ingest/signal logic, not app logic →
  move it to **`stage5_filter/build_signals.py`** (out of the `review_app/` subfolder). The thin console
  imports each stage's logic; per-stage ingest/views live with their stage.
- **Update the `sys.path`/imports** that reach into `review_app` today: `stage5_filter/harness.py`,
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
3. **Code-move decomposition** (§7): app→`common/console/`, `build_signals`→`stage5_filter/`, names.
4. **Stage-6 index** (§5): a generated index file vs scan-the-dirs (lean: index, for scale).
5. (Parked from `STAGE5_FILTER_DESIGN` §"Path to filtered.json") the exact REJECT rule + rank order for
   the auto-filter — unchanged in intent, now lands in the generator of §4/§6.

---

## 9. Sequencing (proposed — prove the data model before the console UI)

Don't stall the actual goal (representations → council) behind an app re-architecture. Order:

1. **Code move first** (§7): `review_app`→`common/console/`, `build_signals`→`stage5_filter/`, fix imports,
   green the 36 tests. Mechanical, isolated, reversible. *(REQ-098)*
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
