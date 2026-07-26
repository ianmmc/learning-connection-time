# Epic #617 — the benchmark model, the Stage-9 wall, and harness mobility: findings & plan

> **Authority:** the exploration record and implementation plan for epic #617 (sub-issues #618–#625),
> produced 2026-07-25 during a planning pass over the whole benchmark/wall surface. This is a
> **point-in-time findings report**, not a living design note — where it disagrees with
> `STAGE1_QUEUE_DESIGN.md` / `STAGE6_DISPATCH_DESIGN.md` / `STAGE9_INCORPORATE_DESIGN.md` /
> `PIPELINE_GOVERNANCE_AND_STATE.md` after implementation lands, **those are authoritative and this is
> history**.
> **Audience:** whoever implements or reviews #617; auditors asking why the district-keyed wall was
> retired and on what evidence; future work touching batch types, dispatch provenance, or the Stage-2/3/4
> done-markers.
> **Companions:** GitHub #617 (epic) + #618–#625 · `STAGE1_QUEUE_DESIGN.md` §2h (the wall's stated
> rationale) · `STAGE9_INCORPORATE_DESIGN.md` §2g (the standing walls) · `COUNCIL_LAB_DESIGN.md`
> (benchmark dispatches are #80's evaluation instrument) · `docs/REQUIREMENTS.yaml` REQ-117/151/162/164/166.
> **Update this when:** never, except to append to §10 (the implementation log) as phases land, and to
> correct a §1-§9 claim that implementation *disproved* — with the correction marked, not silently
> rewritten, since the value of this document is partly the record of what the planning pass got
> wrong. Corrections to *present state* belong in the design notes.

---

## 1. The core reframe: the wall is a symptom of a missing terminus

Benchmark work in this pipeline never got a defined **terminus** — no answer to "where does a benchmark
run stop?" Because nothing structurally prevented benchmark data from flowing toward the LCT write, a
per-district guard was bolted on instead. Five sites now each ask some version of:

> *"Has this district EVER been a member of any `batch_type='benchmark'` batch?"*

`batch_district` rows are never deleted, so the answer is **permanently yes** for all 27 of
`batch_00000`'s districts. A district that is later honestly re-discovered, re-captured, re-extracted and
human-approved at gate@8 through a real production batch is still refused at Stage 9 — forever. Its
correct, freshly-sourced minutes can never reach the LCT DB.

The guard keys on **district identity**. The documented rationale is about **extraction provenance**.
`STAGE1_QUEUE_DESIGN.md` §2h gives exactly two reasons:

1. batch_00000 entered by *injecting frozen `gt_curation_*` files directly at the Stage-3 seam with no
   discovery*, and "several source documents are deliberately older school years."
2. It is "an accuracy yardstick … not coverage" — counting it in funnel/enrichment stats would
   misrepresent real coverage.

Both are satisfied by scoping to provenance. Neither requires a permanent per-district lockout. The
district-keyed form is a proxy that was correct only as long as those districts had exactly one history.

**Give the two harnesses their natural stopping points and the wall largely dissolves:**

| harness | what it A/B tests | terminus |
|---|---|---|
| **benchmark batch** | Stages 2/3/4 — search queries, SERP providers, capture tools, processing tools — against known-good Stage-5 output | **gate@5** |
| **benchmark dispatch** | Stages 6/7 — which representations to which councils, and the resulting yield | **gate@7** |

Neither reaches Stage 8/9, so benchmark output becomes *structurally* incapable of being a Stage-9
candidate. The guard that remains is defence-in-depth rather than the load-bearing rule.

---

## 2. The guard census (code-verified 2026-07-25)

Four sites key on `batch_type='benchmark'`; exactly one keys on the `batch_00000` **id literal**.

> **Refined during implementation (§10.2):** counting *guard sites* understates the duplication.
> Counting **spellings of the SQL** there were **five**: the three the epic named (Stage 9, Stage 7
> execution, `server.py`) plus two the epic did not — an inline copy in
> `stage7_run._early_exit_targets` and another in `maintenance/backfill_receipts.load_benchmark_ids`.
> Site #4 below (`compose_zero_yield`) is not a copy — it is an ORM attribute compare on a batch row,
> and is genuinely batch-grain, so it stays.

| # | site | file:line | posture |
|---|---|---|---|
| 1 | `_is_benchmark_district` | `stage9_incorporate/incorporate.py:85`, called once at `:259` | The Stage-9 wall. **Fail-closed** — only `ProgrammingError` (missing table ⇒ fresh DB) returns False; any other error propagates, so a transient DB fault can never let a benchmark district through (PR #607 R2). |
| 2 | `_benchmark_district_ids` | `process_governance/stage7_execute.py:289`; callers `:355` (`_gather`), `:806` (`_bundle_alternate`), `:910` (`_dispatch_recover_band`) | The request-execution wall (#134). Excluded rows surface as `benchmark_excluded`, threaded through every `compose_followup_batch` return. |
| 3 | `IS_BENCHMARK_SQL` | `process_governance/server.py:2438`; used `:2008` (advisory badge on the gate@6 candidate list) and `:2671` (the real gate@8 review-queue exclusion) | Its own comment states the principle: *"Keys on `batch_type='benchmark'` membership, never the `batch_00000` id literal."* |
| 4 | `compose_zero_yield` | `process_governance/stage5_followup.py:95` | Refuses a 5→1 escalation **from** a benchmark batch. Genuinely batch-grain — asks about the source batch, not district history. Correct as-is. |
| 5 | **`_early_exit_targets`** | **`process_governance/stage7_run.py:188`** | **The lone `batch_00000` literal** — issue #621. |

Also correct today and worth preserving as the pattern: `maintenance/backfill_receipts.py:66`
(`load_benchmark_ids`), whose docstring already says *"Keys on batch_type, never the batch_00000 literal
— the yardstick grows into new benchmark batches."*

### 2a. Finding: Stage 9 cannot import the shared definition, so it hand-copies it

`incorporate.py:87-88` states it outright: *"mirrors `stage7_execute._benchmark_district_ids`, which
Stage 9 cannot import: `process_governance` sits ABOVE this layer."* `server.py:2433-2435` argues the
opposite way — that a rule this load-bearing gets ONE definition — and then defines a *third* copy.

So the codebase has three hand-maintained copies of one predicate, each with a comment explaining why it
should have one definition. The layering constraint is real; the resolution is to put the predicate in
`common/` (the base layer every stage may import), which is what the plan does.

### 2b. Finding: the "never counted in funnel/enrichment stats" rule is almost entirely prose

It is asserted in five places — `benchmark_batch.py:23-26` and its persisted `"wall"` meta string at
`:138-139`, `stage7_execute.py:290-292`, `CLAUDE.md`, `docs/TERMINOLOGY.md`, `ACQUISITION_PIPELINE.md`.
In **code** it is enforced only *transitively*: benchmark never reaches gate@8 (`server.py:2671`), so it
never reaches Stage 9 (`incorporate.py:259`), so it never lands in `bell_schedules` — and therefore no
LCT-side coverage query (`infrastructure/database/queries.py:802/836/879`, `verification.py:277`) can
count it. Those queries have no notion of "benchmark" at all.

**Two genuine leaks exist today**, unrelated to this epic but worth recording so they are not silently
inherited as "fixed":

- `process_governance/attribution.py` (the #118/REQ-160 Stage-2/Stage-4 effectiveness scorecard) has **no
  benchmark filter whatsoever**. It explicitly attributes benchmark captures as a discovery source —
  `benchmark_gt` is a named attribution bucket at `:10` and `:61`, and `district_axes:132` reads
  `batch_type` as an *axis*, not a filter.
- `stage7_execute._attempted_schools:184-204` filters on `b.status NOT IN ('draft','abandoned')`, **not**
  on `batch_type`. `batch_00000` is `approved`, so its 27 districts' schools count as "attempted."

Neither is a Stage-9 correctness problem; both are measurement-hygiene problems. Filed here rather than
folded into #617's scope.

---

## 3. The mobility requirement — the organizing principle, and the two properties that failed

Ian's framing (2026-07-25) reduced the epic to **four bidirectional-mobility properties**. A district must
be able to move between harnesses in *both* directions:

1. a benchmark-batch district → later in a **follow-up batch**
2. a first-run/follow-up district → later in a **benchmark batch**
3. a benchmark-dispatch district → later in a **production dispatch**
4. a production-dispatch district → later in a **benchmark dispatch**

This turned out to be the single most useful test of the plan: **two of the four did not hold** under the
first draft, and one of the failures was a bug in the plan itself rather than a gap in the code. The
matrix and its evidence:

### Property 1 — benchmark → follow-up batch: ⚠️ gap (missing composer, not a guard)

Provenance-scoping the guards (#619) removes the *refusal*, but nothing an operator can reach can
*express* the batch. `build_followup_batch` (`stage1_queue/queue_batch.py:335`) is exactly right — its
docstring says it *"deliberately RE-INCLUDES already-attempted districts … so the eligible_pool exclusions
do NOT apply here"* — but its only two production callers are automatic, directive-driven back-edges:

- `process_governance/stage7_execute.py:608` — the 7→1 sweep
- `process_governance/stage5_followup.py:135` — the 5→1 zero-yield escalation

`POST /api/batches/create` (`server.py:1150-1240`) unconditionally routes to `build_batch`. So *"put these
27 districts in a follow-up batch"* is not an expressible operation today, by console or CLI.

**First-run cannot substitute**, for a structural reason rather than a preference one. `build_batch` →
`eligible_pool` (`:77-103`) → `already_attempted` (`common/district_status.py:142-146`,
`ATTEMPTED_THRESHOLD_STAGE = 3`) drops every district at `furthest_stage >= 3`. All 27 batch_00000
districts currently sit at `furthest_stage = 7`. And the #572 "targeted" path is applied **after** the
pool filter (`queue_batch.py:271-277`, whose own comment says *"an id outside the pool is reported, never
force-included"*), so a hand-targeted first-run batch reports all 27 as `targeted["missing"]` and 409s at
`server.py:1209`.

Admitting them via first-run would mean weakening `already_attempted` — the one predicate that makes
first-run a *cold-start* draw. That is a corpus-wide semantic change to serve a 27-district need.
Follow-up is also the better semantic fit on the merits: it re-includes attempted districts by design, it
is what flips the reconciles into merge/redo, and it *shapes* its own discovery (untried-schools-first,
else a widened SERP query set — #160/#162), which matters a great deal for districts whose prior
"discovery" was injected rather than real.

One wrinkle: follow-up normally targets *unsatisfied* bands, and batch_00000's bands are largely satisfied
(95.2% band / 99.3% per-school against GT). `build_followup_batch` does not check satisfaction — it only
drops a band with no NCES school-level coverage — so passing all real bands explicitly works.

### Property 2 — first-run/follow-up → benchmark batch: ❌ gap (two blockers)

- **No composer.** A console-created `batch_type='benchmark'` batch would route through `build_batch` →
  `eligible_pool` and exclude every already-attempted district, exactly as in property 1. The only
  existing benchmark-batch builder is `benchmark_batch.build_batch_doc:98`, which sidesteps the filter by
  calling `eligible_pool(year, {"districts": {}})` — an **empty registry**, making the attempted check a
  no-op by construction. That is the *injection* path, not a real pipeline run.
- **The redo lever is `follow-up`-only.** Three sites, all `batch_type == "follow-up"`:
  `stage2_discover/headless.py:308` (`merge=`), `stage3_capture/headless.py:257` (`redo=`),
  `stage4_process/headless.py:274` (`redo=`). A benchmark batch would therefore **skip** every
  already-attempted district in Stages 2/3/4 even if a composer admitted it.

### Property 3 — benchmark dispatch → production dispatch: ⚠️ the plan's own bug

The first draft's forcing rule was: *"if any selected **district** is benchmark-batch-provenance, the
dispatch is forced benchmark."* That is the **same district-identity bug the epic exists to kill**, moved
one stage upstream — and it breaks property 3 outright: a batch_00000 district could never again compose
a production dispatch, no matter how fresh its representations.

The rule must be **representation-grain**, which required verifying that rep-grain provenance is
recoverable at all. It is — see §4.

### Property 4 — production dispatch → benchmark dispatch: ✅ holds

Explicit human opt-in: set `dispatch_type='benchmark'` on a draft over production representations. This
is the Council Lab (#80) A/B path, and it is the reason "explicit opt-in" belongs alongside the derived
rule rather than being replaced by it.

### Terminology correction

There is **no such thing as a "follow-up dispatch."** Dispatches carry no first-run/follow-up axis —
batches organize Stages 1–4, dispatches organize Stages 6–7 (Ian's own clarification in #617: *"districts
are the unit of discovery; batches organize stages 1-4, dispatches organize stages 6-7"*). After this work
the only dispatch axis is `dispatch_type ∈ {production, benchmark}`, so properties 3 and 4 are the two
directions of one axis.

### Status of the matrix as phases land

**Properties 3 and 4 are LANDED** (Phase 2b, §10.3): rep-grain refusal at freeze plus the explicit
Council Lab opt-in, each with a named test —
`test_mobility_3_a_benchmark_batch_district_composes_a_production_dispatch_on_fresh_reps` is the
property-3 one, and `test_the_same_district_is_still_refused_on_its_stale_injected_rep` is its converse
(rep-grain must not become a loophole).

**Properties 1 and 2 are LANDED** (Phase 2c, §10.5): the targeted composer is reachable from
`POST /api/queue/create` (and from the gate@1 console), and the redo lever is now a declared batch
attribute. Named tests:
`test_mobility_1_a_benchmark_batch_district_composes_a_targeted_follow_up_batch` and
`test_mobility_2_an_attempted_district_composes_a_benchmark_batch_and_redoes`, with
`test_the_drawn_composer_still_refuses_an_already_attempted_district` as the baseline that makes both
meaningful. Demonstrated on real data too: Baldwin County (`0100270`, a batch_00000 district at
`furthest_stage = 7`) is refused by `build_batch` and composed with all three bands by the targeted
path. Property 1's gap was clarified along the way as *the missing composer, not the batch-type
choice* — see §10.4.

**All four mobility properties now hold.** The §7 plan's remaining phases (2d/2e onward) change what
the guards *judge*, not what an operator can *express*.

> **Correction to §3's property-2 finding.** It named **three** redo-lever sites (the two Stage-2/3
> `merge=`/`redo=` call sites plus Stage 4's). There are **five**: `discover_stage2.py::reconcile`
> holds the `followup` flag that makes the todo/skip decision *itself* — the most consequential of
> the five, since the two `merge=` sites only matter for districts reconcile already admitted — and
> the Stage-2 legacy CLI carries a sixth-of-a-kind copy of `merge=`. The undercount came from
> grepping the call sites named in the epic rather than the whole `batch_type ==` surface; the same
> mistake as §2's guard undercount, one axis over.

---

## 4. The provenance-grain finding (the fact the whole design rests on)

For a representation-grain forcing rule to be implementable, *"which batch produced this representation"*
must be answerable. Checking the Stage-5 signal schema (`stage5_filter/build_signals.py:736-765`):

```
CREATE TABLE record (rec_key, district_id, district_dir, url, hash, kind, final_url,
                     content_hash, duplicate_of, tier, sort_score, category_hypothesis,
                     signals_json, cluster_id, ...)          -- no batch_id
CREATE TABLE representation (rec_key, source, filename, file_kind, n_chars, n_times, usable)
CREATE TABLE district (district_id PK, ..., batch_id, ...)   -- ONE, overwritten
CREATE TABLE district_target (district_id PK, batch_id, ...) -- ONE, overwritten
```

**`record` and `representation` carry no `batch_id` at all.** Only `district` and `district_target` do,
and each is keyed on `district_id` — a single current value, overwritten on re-ingest. So after a
follow-up re-run, `district.batch_id` names the *follow-up* batch and the benchmark association is simply
gone from the signal tables.

`representation.source` is a red herring for this purpose: it is the **processing-tool** source
(`pdftotext`, `camelot_*`, `tesseract_*`, `raster`, `txt`, `harvest_slice`), not the discovery/capture
origin.

**The one durable representation-grain signal is `capture.source`** —
`common/cache_ingest.py:47-52` defines `capture(district_id, hash, url, final_url, ok, kind, source,
found_on, tools_json, ...)`, and `benchmark_batch.capture_record:74-89` stamps injected records
`"source": "benchmark_gt"` (URL scheme `gt://gt_curation_.../<dir>/<file>`). `attribution.py:61` already
consumes it as an attribution bucket, so it is a load-bearing, exercised field rather than a vestige.

It also **survives a follow-up re-run**: `cache_ingest` does a per-district DELETE-then-UPSERT from the
district's `captures.json`, and a follow-up run *unions* prior and new records into that file (the #174
merge path), so `benchmark_gt` rows persist alongside fresh ones. That is the desired behavior: mixed
provenance stays visible and per-rep, which is precisely what lets a human deselect the stale injected
reps at gate@6 rather than being forced into a benchmark dispatch.

> **Design consequence.** The forcing rule keys on `capture.source='benchmark_gt'` (and, generally, the
> representation's originating batch's `batch_type`). A district that is a batch_00000 *member* but whose
> selected reps are all fresh composes a **production** dispatch freely — property 3 holds.

### 4a. `handoff._identity` is the right home, and it comes with a free win

`stage6_handoff/handoff.py:38-62` computes the price-independent identity hash, and already folds in
`verified_only` with a comment that is an exact template for `dispatch_type`:

> *"`verified_only` is part of identity: a training-grade dispatch (labeled targets only) is a distinct
> artifact from a default one even when the reps happen to coincide (no hash collision)."*

Adding `dispatch_type` there makes a benchmark and a production dispatch of *the same representations*
hash-distinct artifacts. And because `package_identity()` (`:66-73`, the gate@6 preview→freeze staleness
token, issue #37) is implemented as `_identity(package, {}, {})`, the change is automatically covered by
the staleness check — a type flip between preview and freeze produces a 409 rather than a silent
substitution. No extra machinery.

`DispatchDraft` (`stage6_handoff/draft_models.py:31-48`) already carries `verified_only` as a real column
plus a `meta_json` field commented *"room for future per-draft settings … without a migration"* — so the
draft side has both a precedent column and an escape hatch.

---

## 5. The `batch_type`-string-equality anti-pattern

The unifying defect behind properties 1 and 2, and behind #621:

> **Behavior is derived by comparing `batch_type` to a string literal, in a dozen scattered places, over a
> column with no enum, no CHECK constraint, and no validation.**

`stage1_queue/models.py:31` is a plain `String` with `default="first-run"`; the three legal values exist
only in an inline comment. `batch_store.create_batch:24` and `queue_batch.persist_batch:472` accept any
string; `server.py:1155` reads it straight from the request payload. The *only* validation touching it is
`validate_scope_combo` (`queue_batch.py:211-217`), which checks a scope/type *combination*, not the type.

The behavioral branches keyed on that string:

| comparison | sites | what breaks with a new type |
|---|---|---|
| `== "follow-up"` | `stage2_discover/headless.py:308`, `stage3_capture/headless.py:257`, `stage4_process/headless.py:274`, `batch_store.py:298` | a new type silently never redoes an attempted district |
| `== "benchmark"` | the five guards in §2, `stage5_followup.py:95`, `gate1.js:98` (client mirror), `queue_batch.py:211` | a new benchmark-flavored type silently bypasses every wall |
| `== 'batch_00000'` | `stage7_run.py:188` | **#621** — a future benchmark batch loses REQ-151's full-census exemption and measures the shortcut instead of the pipeline |

#621 is the same bug one level more specific: a literal where a type belongs, latent only because
`batch_00000` is currently the sole benchmark batch. It becomes real the moment this epic makes a second
one possible — which is why it is sequenced first and standalone.

**The fix pattern:** declared attributes, not string equality. `batch_store.batch_redoes_attempted(batch)`
(true for `follow-up` and `benchmark`), a single `common/benchmark.py` provenance predicate, and actual
allowed-value validation on `batch_type` so a typo cannot mint a fourth type that bypasses every guard.

---

## 6. The done-marker inversion (#622/#623): the design and its traps

Four fixed-name artifacts must become stamped receipts under the unified `stage<N>_<stage_name>`
convention (decided 2026-07-23): `discovery.json`→`stage2_discover`,
`candidates.json`→`stage2_candidates`, `captures.json`→`stage3_capture`,
`processed.json`→`stage4_process`. Each one's **existence** is currently a stage-done marker read by fixed
name, so a rename breaks the reconcile state machines.

Scale: ~133 filename references, but only **44 Python + 12 Node real code sites** (the rest are prose),
plus ~90 test-fixture sites across 16 test files.

### 6a. The framing that de-risks it

The three reconciles already evaluate **two independent predicates**, and the post-inversion truth table
is provably identical:

| | today | after |
|---|---|---|
| A | `done_on_disk` = fixed filename `.exists()` | `artifact_present` = `latest_receipt(...) is not None` |
| B | `reg_says_done` = `furthest_stage >= N` | `stage_done` = `DS.stage_reached(registry, did, N)` — *the same expression* |
| `¬A ∧ B` | remediation hatch, else `SystemExit` | unchanged |
| `A ∧ ¬B` | `reconciled_from_disk`, skipped | unchanged |
| `A ∧ B` / `¬A ∧ ¬B` / `redo` | skipped / todo / todo | unchanged |

So "inversion" is **not** a change to the branch logic. It is a change of *declared authority* — gov_db
becomes the routing truth, the file demotes to a corroborating integrity probe — and the consequence that
unlocks everything: once B is authoritative, A is free to be a **glob** rather than a canonical filename.

Practical upshot: the inversion step can land with **zero test changes and zero behavior change**, and all
the real risk lives in the *probe implementation* (fixed name → `latest_receipt`), not the logic.

### 6b. The predicate must be `furthest_stage >=`, not "a stage-N event exists"

`remediate_contamination.execute()` writes a `stage=5 / event_type='remediated'` row, bumping
`furthest_stage` to 5. Under a per-stage-event predicate a remediated district would read "stage 2 done"
**and** have no receipt on disk — silently changing which branch fires. Under `furthest_stage >=` the
`¬A ∧ B` branch fires correctly and the existing `district_status.remediation_receipt` hatch (#572)
handles it unchanged. `furthest_stage = MAX(stage)` is monotone by construction (`current_state` view), so
a district at Stage 7 correctly reads "Stage 2 done."

### 6c. Eleven regression traps a naive rename would hit

Recorded in full because they are the highest-value artifact of this pass for a future implementer:

1. **`latest_receipt` resolves the wrong directory under every existing stage test.** `iter_receipts` →
   `district_capture_dir` → `_capture_root()` (`receipts.py:44-55`) redirects to a pytest quarantine dir
   whenever `PYTEST_CURRENT_TEST` is set and `paths.RAW_CAPTURES` is still default. Every stage test
   monkeypatches the **module-level `RAW_DIR`**, never `paths.RAW_CAPTURES`. A bare `latest_receipt` call
   would find nothing and report every district todo — or `SystemExit` the suite. ⇒ `ddir=` override on
   `iter_receipts`/`latest_receipt` is **mandatory and must land first**.
2. **Commit-before-receipt must be deliberately INVERTED for these four.** REQ-164's rule (receipt after
   the gov_db commit) is safe for Stages 5–9, but these four are the cross-check for the
   registry-ahead-of-disk branch: a crash in that window leaves gov_db ahead of disk and the next run
   raises `CONTROL FAILURE` and halts the whole batch. Today's order (file first) is the safe one —
   preserve it and document the divergence rather than "harmonizing" it.
3. **Three `arch-manifest.json` fitness tests break, one structurally.** `_audit_receipt_calls()` is a
   Python-AST-only scan; `stage3_capture` will be Node-written and therefore invisible. And
   `test_audit_receipt_producer_matches_bidirectionally` asserts *exactly one* producer per basename —
   violated three ways (`stage3_capture` has a Node producer *and* `capture_stage3.write_manifest`;
   `benchmark_batch.inject_district` is a producer of all three of `stage2_discover`/`stage2_candidates`/
   `stage3_capture`). ⇒ allow list-valued `producer`, add a Node scan.
4. **Six "refuse to overwrite" guards become silent no-ops.** Under always-stamp `path.exists()` is never
   true for a fresh write: `capture_stage3.reconstruct_captures:302`, `capture_stage3.write_manifest:346`,
   `benchmark_batch.inject_district:153`. Miss these and `reconstruct` fabricates a degraded manifest over
   a healthy district — the exact failure it was written to prevent.
5. **`batch_guard.assert_district_runnable:41-53` fails OPEN if missed**, and no current test would
   notice — it returns early ("makes no batch claim") when `discovery.json` is absent, so a missed
   conversion turns the #168/#206 abandoned-batch guard permanently dark on the district-grain CLIs.
6. **`build_signals.ingest_district:1062` fails CLOSED and silently** — a missed conversion drops the
   district from the Stage-5 ingest entirely, and `cache_ingest`'s DELETE-then-UPSERT then leaves it with
   no `record` rows. Blast radius: gate@5 labels.
7. **`find_districts` conflates "is done" with "carries the header fields."** Three sites use
   `discovery.json` for both the Stage-2-complete gate *and* the `district_id/name/state/domain` header.
   Splitting them naively yields districts with no header. Keep both conditions.
8. **`_prior_doc`'s aside-glob loses its crash-orphan fallback** — it globs `discovery.*.json`; post-rename
   the basename is `stage2_discover` and the legacy asides are `discovery.<ts>.json`, with no overlap.
9. **The #267 corrupt-manifest wedge changes character** — `latest_receipt` returns the *newest* receipt,
   which is the corrupt one, and no rename-aside path exists to demote it. The recovery instructions
   embedded in that `RuntimeError` must be updated.
10. **Node's three maintenance sweeps flip from patch-in-place to append-a-receipt** — strictly better
    (the pre-patch state stays readable), but the `if (dirty)` guard must be kept or every district gets a
    redundant receipt on every no-op sweep.
11. **`backfill_receipts._already_backfilled` anchors on `".py-"`** and can never be satisfied by a live
    `node-`-tagged receipt; must become writer-agnostic.

### 6d. #623's stated scope is short — a correction to the issue

The issue names a `stage3_capture` **writer** and a `stage2_candidates` **resolver**. Node in fact needs a
`stage3_capture` **resolver** too, at four sites: `capture_discovery.mjs:701` (the load-bearing #174
follow-up-redo prior-round seed) plus the three maintenance sweeps (`:1066`, `:1131`, `:1191`). Without it
a follow-up redo silently loses the prior round's records, and Stage 5's per-district delete-and-rebuild
then erases the district's existing records and orphans their gate@5 labels — the exact failure the #174
comment at `:697-700` documents.

### 6e. The safe ordering: resolve-then-either

Both naive orders lose data on a live tree. Rename-first darkens every still-fixed-name reader;
convert-first strands districts that never re-run (their only artifact is the legacy fixed file, and a
repointed reader returns `None`). The resolution is a **transitional legacy-aware resolver**
(`common/artifact_resolve.py` + a Node mirror) introduced *before* either — after which writer-flip order
and backfill order stop mattering, and the backfill can run at any time on a live tree, idempotently. It
is deleted in one commit at the end.

### 6f. Cross-language lockstep has an existing pattern to clone

#623 insists on "a shared, documented spec — not two drifting implementations." The repo already solves
this exact problem for the CMS-host matcher (#34/#416): a config-as-data case table read by **both**
`tests/test_cms_host_parity.py` and `capture_fingerprint.test.mjs`, whose docstring states the property
directly — *"a future rule change in one language fails the other's suite until both are updated."* Clone
it as `common/config/receipt_naming.json` carrying golden filename + resolver vectors. Exclude
non-ASCII/float/bignum payloads from the hash vectors: cross-language hash agreement is explicitly *not*
required (`receipts.py:12-15`), so pinning those would manufacture false alarms.

---

## 7. The plan

Phases, in dependency order. The full plan (with per-phase file:line detail) is the approved plan file;
this is the shape.

| phase | issue | content |
|---|---|---|
| 1 | **#621** | Key `_early_exit_targets` on `batch_type='benchmark'`. Small, standalone, lands first. Add the missing direct test (today it is only monkeypatched). |
| 2 | **#618** | (a) one shared predicate in `common/benchmark.py`; (b) `dispatch_type` on `DispatchDraft`+`Handoff`, folded into `_identity`, **forced at representation grain**; (c) **batch mobility** — generalize the redo lever, add operator-reachable follow-up + benchmark composers, validate `batch_type`; (d) the two termini; (e) batch_00000 reclassified, injector retained. |
| 3 | **#619** | Re-key all five guards from district-membership history to the provenance of the thing being judged (`school_fact` → `extraction.handoff_hash` → `handoff.dispatch_type`). Fail-closed posture preserved. |
| 4 | **#625** | REQ-117/151/162/164 reworded; REQ-166 confirmed unchanged. Fix `COUNCIL_LAB_DESIGN.md:54`'s "the yardstick GROWS," which contradicts CLAUDE.md's "this set is FIXED." |
| 5 | **#622/#623** | The done-marker inversion, six independently-green steps, one artifact per PR. |
| 6 | **#624** | Retroactive stage 6–9 receipts (83/83/38/6). Needs a `ts` override on `write_receipt`; every reconstruction self-identifies as backfilled. |
| 7 | **#620** | Re-run batch_00000's 27 districts via a targeted follow-up batch, on fresh provenance. Depends on 2c (composer + redo lever), 3 (the guard), and 5 (artifact distinguishability). |

**Sequencing constraints that matter:** #618 must land before #619 (retiring the wall before the termini
exist opens a hole); #620 depends on all three of 2c / 3 / 5; #621 is independent.

### 7a. Acceptance = the four mobility properties, one named test each

1. a batch_00000 district composes into a targeted follow-up batch and its Stages 2/3/4 actually redo
2. a district at `furthest_stage>=3` from a production batch composes into a benchmark batch and redoes
3. a district with a prior benchmark dispatch freezes a **production** dispatch over fresh reps — and
   freezing one that still selects a `benchmark_gt` rep refuses
4. a production-rep draft accepts an explicit `dispatch_type='benchmark'` and hashes distinctly from the
   same reps dispatched as production

Plus #619's own: a district with a batch_00000 `batch_district` row **and** a fresh production-dispatch
extraction incorporates successfully, while a benchmark-dispatch fact for the same district is still
refused.

---

## 8. Verified vs. assumed

**Verified by reading code this session** (file:line in the sections above): all five guard sites and
their call paths; the `batch`/`batch_district` schema and the absence of `batch_type` validation;
`_PRECIOUS_ALTERS` as the governance migration mechanism (there is no governance migrations directory —
`infrastructure/database/migrations/001-028` is the LCT DB); the absence of any `dispatch_type` anywhere;
`handoff._identity`'s `verified_only` precedent and `package_identity`'s reuse of it; `DispatchDraft`'s
columns and `meta_json` comment; the `record`/`representation`/`district`/`district_target` DDL and the
absence of `batch_id` on the first two; `capture.source` and its `benchmark_gt` value; the three
`== "follow-up"` redo-lever sites; `build_followup_batch`'s callers (grepped repo-wide);
`POST /api/batches/create`'s unconditional route to `build_batch` and its 409 on a fully-excluded targeted
draw; `eligible_pool`'s five filters and `already_attempted`'s threshold; `common/receipts.py` in full
(including the absence of a `ts` override); `backfill_receipts.py` in full; `arch-manifest.json`'s
`file_dispatches` section; the Node artifact read/write sites in `capture_discovery.mjs`; the absence of a
central "may advance" function and `batch_guard.assert_runnable` as the only batch-grain chokepoint.

**Asserted from sub-agent exploration, not independently re-read**: the precise line numbers inside
`stage7_execute.py`'s `_gather` threading of `benchmark_excluded`; the `stage8_approval` /
`state_event` payload shapes cited for #624's backfill sources; the exact contents of the 27-district
list; `benchmark_holdback_18.json`'s record shape. None of these change a design decision; all should be
re-checked at implementation time.

**Promoted to verified during implementation (2026-07-25):** `handoff._identity`'s `verified_only` fold
and `package_identity`'s reuse of it (read directly — it is what makes the staleness check free);
`DispatchDraft`'s columns and `meta_json` comment; that identity is only ever compared fresh-vs-fresh
(grepped, so no stored hash is invalidated); `capture.source` as the rep-grain signal and its five
measured properties (§10.3); `seedFromPriorCaptures`'s verbatim carry-forward; and the
`batch_type == "follow-up"` redo-lever sites — ~~three~~ **five**, see the correction at the end of §3
(the count above was wrong, and the missed site was the load-bearing one). The 1954/337/249/90 test
counts in CLAUDE.md were also unverified at planning time and are now confirmed for the two suites
this work touches: the DB-free suite started at **1954 passed / 1 skipped** and govdb at **337**,
matching. The integration suite does **not** match: CLAUDE.md says 249, and the measured baseline —
confirmed by stashing all of this branch's changes and re-running — is **252 passed / 149 skipped**.
Pre-existing doc drift, not caused by this work; fold the correction into CLAUDE.md's
resume-essentials when the epic lands.

**Explicitly not verified**: that the 1954 / 337 / 249 / 90 test counts in CLAUDE.md still hold (no suite
was run this session — the pass was read-only).

## 9. Open questions carried into implementation

- **Should a benchmark batch draw from the full corpus or an explicit list only?** The plan assumes
  explicit-list-only (mirroring `build_followup_batch`), which is the conservative choice. A stratified
  benchmark draw is a different instrument and is not needed for #617.
- **What happens to a mixed-provenance district at gate@6?** ~~The plan surfaces per-rep provenance so a
  human can deselect stale `benchmark_gt` reps.~~ **RESOLVED in Phase 2b (§10.3):** preview reports the
  benchmark reps, freeze refuses while the dispatch is production, and the human either deselects them
  or opts the whole dispatch in as benchmark. The narrower question — whether a stale injected rep
  should be *release-eligible at all* after a fresh run, i.e. suppressed upstream at Stage 5 rather than
  caught at gate@6 — is still open and is a gate@5 policy call, not settled here.
- **`benchmark_holdback_18.json` has an arithmetic discrepancy** — the file says `n_districts: 18` with an
  18-long list, but `PROJECT_HISTORY.md:143` says "the other 14 of the original 41" (41 − 27 = 14). One is
  wrong; resolve during #620, which is the standing comparison obligation that file exists to serve.
- **The two measurement leaks in §2b** (`attribution.py`, `_attempted_schools`) are unfiled. Decide
  whether they become issues or are accepted as intended behavior for an effectiveness scorecard.
- **The gate@6 console changes are not yet Playwright-verified** against a live draft containing a
  benchmark rep. They are static-source-pinned only (no JS harness in the repo — a documented
  deferral), so the warning banner, the type toggle and the two badges have been asserted to *exist*,
  not to *render correctly*. Do this before gate@6 is driven for real in #620.

---

*Produced 2026-07-25 during the #617 planning pass. Exploration was read-only; no code was changed. The
mobility matrix in §3 exists because Ian tested the plan against it and two properties failed — that
exchange is the most load-bearing part of this document.*

---

## 10. Implementation log — what actually happened

Appended as phases land. The point of this section is the **deltas from the plan**: where implementation
disproved a §1-§9 claim, and what the code forced that the design pass missed. A phase that landed
exactly as planned gets one line.

### 10.1 Phase 1 — #621, the `batch_00000` literal (commit `f4a8d47`)

Landed as planned: the literal became the same `batch_district JOIN batch … batch_type='benchmark'`
shape as every other guard. Semantics are strictly *broader* (batch_00000 IS a benchmark batch), so no
district loses its exemption.

**Learning — the test was worth more than the fix.** `_early_exit_targets` had no direct test at all:
`tests/test_stage7_mode_stability.py` monkeypatches it wholesale and only mentions the exemption in
prose. Two govdb tests were added against real Postgres, using benchmark batch ids deliberately **not**
`batch_00000` — then **reverted the SQL and confirmed both fail red** before passing green. A guard test
that would have passed against the pre-fix code is worthless, and this class of fix (swap one predicate
for a broader one) makes that failure mode easy to ship.

**Process note.** REQ-151's acceptance criterion literally read *"batch_00000 members are exempt"*,
which the fix made false as written. It was corrected in the same commit rather than deferred to #625:
leaving it would have let the ledger contradict the code for the duration of the epic, and the ledger
is what a reviewer or auditor reads first.

### 10.2 Phase 2a — one home for the predicate (commit `a66f356`)

Pure refactor: the five spellings (see §2's refinement note) now delegate to
`infrastructure/acquisition/common/benchmark.py`.

**Preserved asymmetry, now documented as deliberate.** `is_benchmark_district` tolerates ONLY a missing
table (fresh DB) and lets everything else propagate — Stage 9's wall can never fail open (PR #607 R2).
The set-valued readers carry no such tolerance. That difference existed before and read as accidental;
it is now stated, because a future "consistency" cleanup would otherwise be very likely to unify them
in the fail-open direction.

**Learning — a fitness function nobody has falsified is decoration.** The consolidation shipped with a
test asserting no module may re-inline the JOIN. Running that detector against the **four real removed
copies** found two defects in the detector itself:

1. A line-by-line scan caught only 1 of 3. The predicate is written as *adjacent string literals across
   source lines*, so `batch_type = 'benchmark'` and `batch_district` never appear on the same line —
   i.e. it missed exactly the copies that had just been deleted.
2. After switching to a normalizer that joins adjacent literals, it still missed the backfill copy: the
   join step consumed the value's own closing quote where `'benchmark'` abutted the enclosing string's
   quote (`… = 'benchmark'"))` → `… = 'benchmark))`). The pattern now treats the quotes as optional.

**Learning — a git-derived test corpus is a time bomb.** The first version read the removed copies via
`git show $(git merge-base HEAD origin/main):<path>`. That silently stops testing anything the moment
the branch merges (the merge-base advances past the consolidation and those paths hold the *new*
content), and breaks outright in a shallow CI clone. The corpus is now embedded as literals. Generalize:
**a regression corpus must not be resolved through a moving ref.**

### 10.3 Phase 2b — `dispatch_type` (commit `bcb4e26`)

**The plan was wrong, and the mobility matrix is what caught it.** §3's draft forcing rule read *"if any
selected DISTRICT is benchmark-provenance, force benchmark"* — the district-identity bug this epic
exists to retire, relocated one stage upstream. It breaks property 3 outright: a batch_00000 district
could never compose a production dispatch again regardless of how fresh its representations were. The
rule is now **representation grain**. This is the single most important correction in the epic so far,
and it was found by testing the plan against a stated property rather than by reading the code again.

**Empirical verification before building on the assumption.** Rep-grain is only implementable if rep
provenance is recoverable. Measured against the live governance DB:

| check | result |
|---|---|
| `capture.source` distribution | discovered 1450 · emergent 206 · **benchmark_gt 95** · manual 1 |
| benchmark-batch districts with a non-`benchmark_gt` capture | **0** |
| `benchmark_gt` captures outside a benchmark batch | **0** |
| benchmark-batch districts with no capture rows at all | **0 of 27** |
| `record` → `capture` join on `(district_id, hash)` | **1489 / 1489** |

Two consequences worth carrying forward. First, **rep-grain and district-grain return identical answers
today** — so the change is a provable no-op on current data and diverges only once #620's re-run creates
the mixed case. That is the ideal shape for a guard change: no behavioral risk at landing, correctness
only when it starts to matter. Second, `record`/`representation` carry **no** `batch_id` and
`district`/`district_target` hold a single *overwritten* one, so `capture.source` is not merely the best
signal — it is the **only** durable rep-grain provenance in the schema.

**Mixing is real, and code-verified.** `capture_discovery.mjs::seedFromPriorCaptures` pushes prior
records **verbatim** (`district.records.push(rec)`) into the new manifest; only a *failed* prior record
whose URL is re-planned is dropped. So `source: 'benchmark_gt'` survives a follow-up re-run and
`cache_ingest` upserts the union. A re-run district legitimately holds stale `gt://` reps alongside fresh
ones — which is exactly why the rep-grain rule is load-bearing rather than pedantic: without it a
reviewer could pull a stale injected rep into a production dispatch and, post-#619, write deliberately
older-school-year data into the LCT DB.

**Design change: REFUSE, never silently force.** The plan said force. Implementation changed it after
considering blast radius: a dispatch carries ONE type, so auto-forcing on a single benchmark rep would
wall **every other district in that dispatch** off from the Stage-9 write — one operator slip silently
costing unrelated districts their LCT minutes. The landed shape splits report from refuse:

- **preview reports** (`benchmark_reps` on the draft view), mirroring the existing
  `missing_from_release` pattern, so the console can still render a draft that currently cannot be
  frozen — which is what lets the human see the problem and fix it;
- **freeze refuses**, naming the offending reps and stating the alternative;
- an explicit `dispatch_type='benchmark'` always passes, and may contain production reps — mixing is the
  point of an A/B.

Generalize: **when a guard's unit is coarser than its trigger, refuse; do not coerce.** Coercion at the
coarse unit silently penalizes everything else sharing it.

**A free win from an existing design.** `package_identity()` is implemented as `_identity(package, {},
{})`, so folding `dispatch_type` into `_identity` made the gate@6 preview→freeze staleness check (#37)
cover a type flip with no new machinery — preview-as-production / freeze-as-benchmark now 409s instead
of silently substituting. Confirmed by grep that identity is only ever compared **fresh-vs-fresh**, so
no stored hash is invalidated (the same reasoning `verified_only` and `pages` relied on).

**Incidental defect found.** The legacy `/api/handoff/dispatch` endpoint had **no `ValueError`
handler**, so even the pre-existing #53 empty-selection refusal was surfacing as an unhandled 500 rather
than a 400. Fixed while threading the new refusal through it. Wiring a new raise through an old path is
a good moment to check what that path already fails to catch.

**Testing note — do not let a new guard get stubbed into inertness.** Three DB-free tests in
`test_stage6_dispatch.py` pass `session=None` and monkeypatch every DB accessor; the new guard's query
broke them. The tempting fix — skip the check when `session is None` — is **fail-open**, and a
production caller passing None would silently bypass the wall. Instead the tests stub the guard's
provenance *read*, leaving `assert_dispatch_type_allowed`'s own logic running for real.

**Manifest over ad-hoc assertion.** The "client must not re-decide provenance" rule is declared in
`arch-manifest.json`'s `forbidden_client_comparisons` rather than asserted in the test file. The first,
ad-hoc version flagged its own explanatory comment as a violation; the manifest's fitness test already
distinguishes a *decision* on a literal from a comment or display string mentioning it.

### 10.4 Decisions taken during implementation

- **The mode-stability early-exit re-keys to dispatch provenance at #619** (Ian, 2026-07-25). Its
  benchmark exemption is district-membership today, which after #620 would make all 27 re-run districts
  pay full-census extraction on every future production run, forever. REQ-151's actual measurement case
  is already covered by the two disablers at `stage7_run.py:447-449` (`run_kind != production`,
  `gt_data is None`); district membership is a third belt firing on runs that measure nothing.
  `test_early_exit_exempts_a_district_in_both_a_benchmark_and_a_production_batch` is the pre-#619 pin
  and **inverts** at #619.
- **Property 1's gap was the missing composer, not the batch-type choice** (clarified with Ian,
  2026-07-25). `build_followup_batch` is already correct — it deliberately re-includes attempted
  districts — but its only production callers are the two directive-driven back-edges, and
  `POST /api/batches/create` unconditionally routes to `build_batch`. First-run cannot substitute:
  `already_attempted` (threshold 3) drops all 27, and the #572 targeted path is applied *after* the pool
  filter, so it 409s. Admitting them via first-run would mean weakening the predicate that makes
  first-run a cold-start draw — a corpus-wide change for a 27-district need. Follow-up also fits on the
  merits (it re-includes by design, triggers merge/redo, and shapes its own discovery, which matters
  when the prior "discovery" was injected). One wrinkle recorded for #620: follow-up normally targets
  *unsatisfied* bands and batch_00000's are largely satisfied, but `build_followup_batch` does not check
  satisfaction — it only drops bands with no NCES school coverage — so passing all real bands works.

### 10.5 Phase 2c — batch mobility, the declared redo lever (commit `d8f4704`)

Properties 1 and 2. Two plan corrections, one of them the most consequential finding of the phase.

**CORRECTION — the plan's home for the predicate was import-illegal.** The plan specified
`batch_store.batch_redoes_attempted(batch)`, in `stage1_queue`. But `stage1_queue` and
`stage2_discover`/`3`/`4` are *siblings* in the layering contract's third layer (separated by `|` =
independent, may not import each other), so none of the five call sites could have imported it. This
was caught by reading `common/batch_guard.py`, whose docstring states the rule outright: *"a guard
shared across stage2/3/4 must sit in the base layer."* The predicate went to
`common/batch_types.py`. Cheap to catch by reading the neighbour that solved the same problem —
expensive to catch after writing five call sites against an import that `lint-imports` then rejects.

**CORRECTION — deriving redo from `batch_type` would have put the FIXED yardstick one click from
corruption.** The plan said *"a batch-level predicate true for `follow-up` AND `benchmark`"*, which
reads as a type derivation. Measured before implementing: all 27 batch_00000 districts hold frozen
`discovery.json` + `candidates.json` on disk carrying their hand-verified `gt://` artifacts (27 of 116
district dirs, `discovery.json.benchmark == true`). Under a type derivation, one Stage-2 run on
batch_00000 — an *approved* batch, one console click, no special intent required — would have re-run
discovery over all 27 and, because the same lever drives `merge=`, folded fresh SERP candidates into
those frozen candidate sets. `benchmark_batch.inject_district`'s `FileExistsError` guard covers only
the *initial* injection, so nothing else would have stopped it.

The fix is the plan's own words taken literally — *"redo-eligibility becomes a declared batch
attribute"* — with a three-valued read:

| declared | reads as | who |
|---|---|---|
| `true` / `false` | believed, whatever the type | every new composer (`default_redo_attempted`) |
| `NULL` / key absent | the historical `batch_type == 'follow-up'` rule | all 30 existing batch rows, every existing receipt |

`redo_attempted` is therefore **nullable with no default and no backfill** — the opposite of #618's
`dispatch_type` (`NOT NULL DEFAULT 'production'`), and deliberately so. `dispatch_type`'s two values
are exhaustive and its default is the safe one; here the safe answer for an undeclared batch *depends
on its type*, and a two-valued column would have had to pick one and be wrong for the other. Verified
against the live governance DB after the ALTER: `benchmark 1 / first-run 10 / follow-up 19`, all
`NULL`. The projection **omits** the key rather than emitting `null`, so every existing receipt
regenerates byte-identically.

**The falsification test the plan implied.** All suites passed with **zero fixture changes** —
1987 DB-free / 352 govdb / 252 integration / 90 npm — which is the empirical form of the
backward-compatibility claim, in the same spirit as Phase 5's "step 1 must pass with unchanged
fixtures" gate. Had the fallback been wrong for any real batch, the stage suites would have said so.

**The composer gap, and what `build_followup_batch` actually is.** The endpoint now routes any
non-first-run type to it. The function is misnamed by history: it is **the targeted builder**, not
the follow-up builder — the composer for any batch whose district list is *named* rather than
*drawn*, which is follow-up and benchmark alike (only `batch_type` at persist differs). Recorded in
its docstring rather than renamed, since the name has many callers and the risk is not worth the
churn. `all_bands_targets` fills in the bands when the operator named only districts.

Verified end-to-end on real data with **zero writes** — Baldwin County (`0100270`, batch_00000,
`furthest_stage = 7`): `build_batch` returns `[]`, `build_followup_batch` composes it with all three
bands and no skips, and both `follow-up` and `benchmark` declare `redoes_attempted → True`. The live
`POST` was deliberately *not* run: `persist_batch` records `stage=1 queued` state events, which is
precious-state mutation on a benchmark district and belongs to Phase 7's gated campaign, not to a
mid-phase smoke test.

**`batch_type` is now validated**, at `create_batch` — the one chokepoint every composer passes
through (CLI, console, the 5→1 and 7→1 escalation builders, the benchmark injector). It shipped
unconstrained with its legal values in a comment, which is precisely how the five literals became
load-bearing; the same reasoning `validate_dispatch_type` recorded at #618.

**Console.** gate@1's create dialog gains a batch-type selector and a re-run warning, and the review
payload resolves `redo_attempted` (never the raw nullable column). The warning is the only place a
human is told that approving a targeted batch spends on districts that already have artifacts — which
is the ramp-up posture's requirement, not a nicety. Static-source pins only; no JS harness (§9).

**Fitness function, falsified.** `test_no_stage_re_derives_the_redo_lever_from_a_batch_type_literal`
is parametrized over the four files. Falsified by reverting `stage3_capture/headless.py` to
`redo=batch.get("batch_type") == "follow-up")` — the test failed, and only that parametrization did.
Per the §10.2 lesson, a fitness function nobody has falsified is decoration.

**Generalizable lesson.** *When a plan says "a predicate true for A and B," check whether it means a
derivation or a declaration.* Here the two differ only for batches that already exist — and that is
exactly the population a derivation silently reclassifies. The declaration costs one nullable column
and buys a guarantee that no historical batch changes behavior.

### 10.6 Phases 0-2c merged — and the one defect that only a fresh DB could show (commit `f5d09b0`, PR #641 = `9865666`)

Phases 0-2c landed on `main` 2026-07-26. One post-hoc fix was needed, and it is worth recording
because **every local gate was green when it shipped**: `dispatch_type` (Phase 2b) declared an
ORM-side `default="production"` but no `server_default`, so on a **fresh** DB — where `create_all()`
builds the table from the model rather than the `_PRECIOUS_ALTERS` string — the column landed
`NOT NULL` with no server default, and raw `text()` INSERTs omitting it failed. 352 govdb green
locally, 1 failed + 4 errors on CI, same commit.

The durable invariant now lives in `PIPELINE_GOVERNANCE_AND_STATE.md` §"a `_PRECIOUS_ALTERS` column's
DDL must be declared TWICE, identically," enforced DB-free by
`tests/test_precious_alters_parity.py`. Falsified against both real defects before landing, per §10.2.

**Two lessons that generalize past this epic:**

1. **A migrated DB cannot verify a schema change; only a fresh one can.** The local DB had already
   run the ALTER, so it tested the path that was *not* broken. Reproducing meant standing up a
   throwaway governance DB — after which the defect was immediate and obvious. Any new precious
   column should be verified that way before the PR, not after CI says so.
2. **The same pass found a second, older instance** — `batch.discovery_scope` (#164), the same class
   in the other direction (the ALTER declares `DEFAULT` without `NOT NULL`; the model declares
   `NOT NULL`). It was masked twice: its test is **skipped on CI** (it needs the LCT DB) and passes
   locally on a migrated DB. *A defect whose only two observation points are both blind stays
   invisible indefinitely* — which is the argument for the fitness function over two point fixes.

---

## 11. Re-anchoring the concept (Ian, 2026-07-25) — what it confirmed, and the gap it exposed

> **Primary source:** Ian's write-up is preserved verbatim in
> `ian's_comments_on_benchmark_batches_and_dispatches_2026-07-25.md` (this directory). Read it for the
> intent in the author's own words. **Two points in it were resolved differently by the end of the
> same conversation and are recorded in §11.3** — the dispatch axis stayed **two**-valued, and
> "follow-up is more automated by default" turned out to describe where the decision sits rather than
> a gate setting. Treat that file as the statement of intent, and this section as where it landed.

Mid-epic, Ian restated the whole picture from first principles: NCES CCD gives the district list; the
goal is banded daily instructional minutes in `lct_db`; batches (Stages 1-4) and dispatches (Stages
6-7) exist as **human-factors constructs** — working in sets rather than one district at a time, so
supervision attention and approval clicks scale during the high-supervision phase of the ramp-up; and
the *type* axis was then added as a third construct, **handling instructions for the pipeline**, so
that testing, measuring and training could happen without experimental output reaching `lct_db`.

That framing is worth recording verbatim in spirit because **it earned its keep**: it confirmed most
of the design and falsified one shipped assumption.

### 11.1 What it confirmed

- Benchmark's defining property is *"simply isn't on a pathway to get integrated into lct_db"* — the
  terminus model (§1), not a per-district wall.
- *"A benchmark dispatch can draw from representations that emerged from any batch type … the two
  constructs are conceptually related but functionally independent."* This is exactly why Phase 2b
  keys the freeze guard on **representation** provenance rather than district identity, and why the
  plan's first draft was wrong (§3, property 3).
- Non-preclusion in both directions — the four mobility properties, all landed.
- Follow-up's purpose as *"collect information a first run wasn't able to surface"* — literally
  `build_followup_batch`'s untried-schools-first / widen-queries shaping (#160/#162).

### 11.2 The gap it exposed — the benchmark-BATCH terminus has no enforcement

Filed as **#640**. #618's freeze guard keys on `capture.source = 'benchmark_gt'`, a value written
**only** by the one-shot GT injector. A benchmark batch composed through Phase 2c's targeted composer
captures real URLs, which Node records as `'discovered'` / `'emergent'` — indistinguishable at rep
grain from first-run output. Measured live: `discovered 1450 · emergent 206 · benchmark_gt 95 ·
manual 1`.

> **Correction to §7's Phase 2d.** The plan claimed the benchmark-batch terminus would be *"enforced
> by 2b's forcing rule, so the terminus and the type derivation are ONE rule, not two that can
> disagree."* That is true **only for the injected corpus**. The planned belt
> (`batch_guard.assert_runnable` refusing Stage-6+ for a benchmark batch) cannot cover it either:
> dispatch composition selects `record` rows across districts and is **not batch-scoped at all**, so
> there is no batch for that guard to see. The terminus is, today, unenforced for anything but
> batch_00000.

Two constraints make it bigger than a Phase-2d line item, and both are the kind of thing that only
shows up by reading the write path rather than the read path:

1. **It cannot be a DB-only column.** `cache_ingest.upsert_capture_rows` does
   `DELETE FROM capture WHERE district_id=:d` then re-inserts from `captures.json`, and the
   cross-stage cache is regenerable from disk by design. Provenance not present *on the receipt* is
   erased by the next re-ingest — the "DB is the working store, JSON files are the receipts"
   invariant, cutting the other way for once. `captures.json` is written by **Node**, which has no
   notion of a batch (`grep batch_id|batchId capture_discovery.mjs` → nothing). So it is a
   cross-language change, sequenced into #623's seam.
2. **One representation can have MORE THAN ONE producing batch.** `capture`'s PK is
   `(district_id, hash)` and the hash derives from the URL, so a district in both a benchmark and a
   production batch that captures the same page has **one row, two producers**. A single `batch_id`
   column is semantically wrong from the start.

**Decided semantics (Ian):** a rep is walled iff it has producers and **every** producer is a
benchmark batch. Benchmark-only → walled; benchmark + production → allowed; no producers recorded →
allowed (every pre-stamp row, today's behavior). Rejected: *any benchmark producer walls it* (a
production batch gets penalized because an experiment found the same page — the #617 district-identity
pattern, one grain down) and *first producer wins* (the answer depends on run order, an accident
rather than a fact about the representation).

### 11.3 Two clarifications recorded, no work

- **The dispatch axis stays TWO-valued** (`production | benchmark`), confirmed with Ian. His
  re-anchoring described three types for *both* constructs; in code, first-run vs follow-up carries
  no distinct dispatch behavior and is derivable from a district's dispatch history, so a third value
  would be a label with no behavior — the `batch_type`-string-equality anti-pattern in pure form, and
  against the derive-over-stamp convention. The asymmetry between the constructs is therefore
  deliberate, and `common/benchmark.py` says so.
- **"Follow-up is more automated by default"** describes where the *decision* sits, not a gate
  setting. Verified: `gate_mode` is keyed by gate alone (`'default' | 'gate@1'..'gate@8'`), with no
  type dimension, so a gate is manual-or-auto for everything passing through it. What is genuinely
  automated for a follow-up is its **composition** — the 5→1 and 7→1 back-edges execute a targeting
  decision a human already approved at gate@5/gate@7, where a first run needs a human to set and
  review a stratified draw of unknown districts. Precise detail worth knowing: an escalation-composed
  follow-up still lands as a **draft and passes gate@1** — `approve_batch` is called by
  `benchmark_batch.py` and nowhere else. No work; recorded so the next reader doesn't mistake the
  posture for a gate-mode feature.

### 11.4 The mixed handoff — the concrete instance of the hole #619 opens

Classifying all **39** frozen handoffs by the rep provenance of their contents (not by district
identity) gives a strikingly clean picture, and one exception that changes the Phase-3 design:

| class | n | detail |
|---|---|---|
| all reps benchmark | **2** | `a2bc80c004ca` (91 reps / 24 districts) + `cb8fabfc32ae` (8 reps / 3 districts) — together **exactly** batch_00000's 27 |
| no benchmark reps | **36** | pure production, 0 benchmark districts each |
| **mixed** | **1** | `f33790e63820` — 231 reps across **9** districts, of which **3 reps** in **3** districts are benchmark |

That mixed artifact is a genuine production dispatch that pulled in three `gt://` curated-GT PDFs:

```
0503060:e6086818dc  gt://…/0503060_BENTONVILLE_SCHOOL_DISTRICT/School Start and Stop Times….pdf
0509000:09ebf46708  gt://…/0509000_Little Rock/2025-2026-SCHOOL-CALENDAR-updated-09-19-2025.pdf
1200180:52b4f372cd  gt://…/1200180_BROWARD/FY_25-26_Opening_and_Closing_School_Bell_Times.pdf
```

Its three extractions are `run_kind='production'` and hold **227 accepted facts** (25 / 1 / 201).
None of the three districts has a `stage8_approval` row, so nothing has reached Stage 9 — the
district-keyed wall is what has been holding them, which is precisely the wall #619 retires. Post-#619
those 227 facts, sourced from hand-curated PDFs of deliberately mixed school years, become gate@8
reviewable and Stage-9 writable. **This is the epic's own sequencing warning, instantiated in real
data.**

**Under Phase 2b's guard this dispatch could not be frozen today** — it would be refused, naming the
three reps. It predates the guard.

#### What it proves about grain

- **Dispatch grain is too coarse.** Tagging `f33790e63820` as a benchmark dispatch would wall all
  231 reps across all 9 districts — penalizing 6 legitimate production districts for 3 reps they had
  nothing to do with. That is the "a guard whose unit is coarser than its trigger" harm from §10.3,
  which is exactly why *freeze* refuses rather than coerces. A retroactive tag would coerce.
- **The finest grain actually available is `(handoff × district)`.** `extraction` is one row per
  `(handoff_hash, district_id)` and carries **no** rep link; `school_fact` links only to
  `extraction_id`. So fact→rep is not traversable — but the frozen artifact holds each district's
  `rec_key` list, so `(handoff, district) → reps → capture.source` is. That grain isolates the three
  tainted districts and leaves the other six clean.

> **Correction to §7's Phase 3.** The plan had `incorporate.py` ask *"did this district's approved
> facts come from a benchmark **dispatch**?"* Dispatch grain gives the wrong answer for
> `f33790e63820` in whichever direction it is tagged. The guard needs **two arms**:
>
> 1. `handoff.dispatch_type = 'benchmark'` — the stamped arm (#618). Covers a future Council Lab A/B
>    composed entirely of *production* reps, which carries no rep-level signal at all.
> 2. this `(handoff, district)`'s reps carry benchmark provenance — the **derived** arm, read from the
>    frozen artifact. Covers every historical dispatch and correctly isolates the mixed one.
>
> Neither arm is redundant: arm 1 cannot see the mixed case, arm 2 cannot see an all-production-rep
> benchmark dispatch.

#### Consequence: Phase 2e's retroactive tagging is unnecessary — and would have been wrong

The plan called for backfilling `dispatch_type='benchmark'` onto batch_00000's historical handoffs.
Arm 2 **derives** the same answer for all 39 with no mutation, and derivation is the better posture
here for a specific reason: the two pure-benchmark artifacts are **immutable frozen files that predate
the `dispatch_type` field**, so stamping the DB row would leave the row and its own artifact
disagreeing — with the artifact, which is the auditable record, saying nothing. Deriving keeps the
receipt authoritative (`feedback-derive-provenance-from-receipts`). Verified: arm 2 classifies all 39
correctly, including the mixed one at district grain (3 tainted of 9).
