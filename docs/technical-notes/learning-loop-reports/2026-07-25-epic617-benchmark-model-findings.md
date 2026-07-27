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

> **SUPERSEDED 2026-07-26 by §11.** Kept verbatim as the record of what was planned before Ian's
> re-anchoring (§10.7), the mixed handoff (§10.8), the review backlog (§10.19) and #662 (§10.20).
> Phases 1-3 landed close to this shape; the *ordering* below is wrong in one consequential way —
> it treats #620 as the epic's last chore rather than its only validation (§11.2). Read §11 for the
> live plan; read this for what the design pass believed going in.

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

> **Consolidated 2026-07-26.** This log was previously split across three top-level sections — §10
> (phases 1-2c), §11 (Ian's re-anchoring), §12 (phase 3) — which made "what happened, in order" a
> three-stop read and let the same lesson get recorded twice. They are now one section. **Nothing was
> rewritten or deleted in the merge**; only headings and cross-references changed, so the corrections
> and their dates stand exactly as they were first written. Old → new: §11 → §10.7 · §11.4 → §10.8 ·
> §12.1-12.9 → §10.10-10.18. §10.1-10.6 are unchanged. Ian's re-anchoring (§10.7) is an *input*, not a
> phase, but it sits here because it landed mid-implementation and changed what followed — which is
> precisely what an implementation log is for.

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

### 10.7 Interlude — Ian re-anchors the concept (2026-07-25): what it confirmed, and the gap it exposed

> **Primary source:** Ian's write-up is preserved verbatim in
> `ian's_comments_on_benchmark_batches_and_dispatches_2026-07-25.md` (this directory). Read it for the
> intent in the author's own words. **Two points in it were resolved differently by the end of the
> same conversation and are recorded in §10.7** — the dispatch axis stayed **two**-valued, and
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

#### What it confirmed

- Benchmark's defining property is *"simply isn't on a pathway to get integrated into lct_db"* — the
  terminus model (§1), not a per-district wall.
- *"A benchmark dispatch can draw from representations that emerged from any batch type … the two
  constructs are conceptually related but functionally independent."* This is exactly why Phase 2b
  keys the freeze guard on **representation** provenance rather than district identity, and why the
  plan's first draft was wrong (§3, property 3).
- Non-preclusion in both directions — the four mobility properties, all landed.
- Follow-up's purpose as *"collect information a first run wasn't able to surface"* — literally
  `build_followup_batch`'s untried-schools-first / widen-queries shaping (#160/#162).

#### The gap it exposed — the benchmark-BATCH terminus has no enforcement

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

#### Two clarifications recorded, no work

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

### 10.8 The mixed handoff — the concrete instance of the hole #619 opens

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

---

### 10.9 Phase 3 — #619, the two-arm provenance guard (2026-07-26)

Landed: the write-eligibility guards move from district MEMBERSHIP to fact PROVENANCE, with the
two-arm predicate §10.8 specified. Three corrections to that spec, one of them to a load-bearing
premise.

### 10.10 CORRECTION to §10.8 — fact→rep IS traversable; the grain is finer than stated

§10.8 says: *"`extraction` is one row per `(handoff_hash, district_id)` and carries **no** rep link;
`school_fact` links only to `extraction_id`. So fact→rep is not traversable — but the frozen artifact
holds each district's `rec_key` list."* The first half is right about `extraction`; the conclusion is
wrong. **`school_fact.rec_key` exists** (`stage7_extract/models.py`, "provenance + review": *"# source
rep"*), and measured against the live governance DB it is **100% populated — 2782 of 2782 rows**,
both statuses, both run kinds. So the available grain is the **fact**, one step finer than the
`(handoff × district)` the report settled for, and it is readable from the DB with no artifact glob.

This matters beyond tidiness, for three reasons:

1. **The frozen receipt already carries it.** `bands[*].schools[*]` holds both `rec_key` and
   `fact_id` (355 of 356 schools across all 38 approved receipts). So the guard can interrogate *the
   artifact Stage 9 actually writes from* — question and write with the same subject — rather than a
   parallel lookup. That is `feedback-derive-provenance-from-receipts` satisfied more directly than
   the artifact-glob plan would have.
2. **The artifact path would have FAILED OPEN.** `closing_argument._load_handoff_by_hash` returns
   `None` when no handoff file matches ("an older run whose receipt was pruned"). A wall built on
   reading frozen handoffs would have silently answered *not-benchmark* for exactly the districts
   whose receipts went missing. The receipt+DB path has no such hole.
3. **It is what makes the escape hatch work** (§10.12).

### 10.11 The measurement that made the re-key safe to land

Before writing code, both rules were run against every district holding production facts:

| | result |
|---|---|
| districts with production facts | **83** |
| walled by district membership | **27** |
| walled by rep provenance (arm 2) | **27** |
| **disagreements** | **0** |
| benchmark districts whose facts are *entirely* benchmark-provenance | **27 of 27** (`any` == `all`) |
| gate@8 queue admits, old fragment vs new | **56 vs 56**, identical sets |

So Phase 3 is **behaviour-preserving today** — the empirical form of the claim, the same falsification
gate Phase 2c used ("all suites pass with zero fixture changes"). Nothing is newly admitted and
nothing newly refused, *including the mixed handoff's three districts*: their 227 accepted facts stay
walled, now by arm 2 rather than by identity. §10.8 recorded that exposure as an accepted consequence
of #619 ("post-#619 those 227 facts become gate@8 reviewable and Stage-9 writable"); at fact grain
**they do not**, and the hole the report flagged never opens.

The two grains diverge only when #620's re-run mints fresh reps for a district that also holds
injected ones — which is the case the epic exists to unblock. Arm 1 fires on **nothing** today: all 39
`handoff` rows are `dispatch_type='production'`, the two pure-benchmark artifacts included, exactly as
the retirement of Phase 2e's back-stamping intends. Arm 1 is the forward-looking arm.

### 10.12 The escape hatch, and why the wall is ANY-of rather than a district ban

The wall refuses on ANY benchmark-provenance evidence rather than dropping the tainted fact — one
injected rep taints the band value it feeds, and silently dropping it would change an approved number
(#618's "refuse, never coerce"). That raises the obvious question: how does a re-run district ever
clear provenance it no longer relies on?

**Through a recorded human decision, not a code exception.** A school struck at gate@8
(`band_exclusion`, #257) is applied *before* the mode, so it is not a source of the band's value;
`collect_write_bearing_sources` skips excluded schools for exactly the reason `collect_source_urls`
does (#632). Striking a stale injected school is therefore the auditable path that satisfies the wall
— which is the ramp-up posture working as designed: the deterministic guard holds, and the human's
override is itself a precious, git-backed record.

A school carrying **neither** identifier is a human-added fact (#626) — no capture, so no benchmark
provenance to check, and it must not be read as *unknown* and refused. Verified: the one such school
across all 38 receipts is the single real `human_added_fact` row, which carries its own `source_url`.

### 10.13 The full-surface grep found EIGHT sites, not the three #619 names

The epic's standing lesson (§2, §3: it undercounted twice by grepping only the sites the issue listed)
held a third time. Disposition of every site:

| site | asks | disposition |
|---|---|---|
| `incorporate.py` Stage-9 wall | may these facts be written? | **re-keyed** to the two-arm predicate, and MOVED to after the receipt loads — it now interrogates the artifact it writes from |
| `server.py::aggregate_districts` (gate@8 queue) | may this district be reviewed? | **re-keyed** via the new `IS_BENCHMARK_PROVENANCE_SQL` |
| `stage7_run._early_exit_targets` | full census or shortcut? | **membership check REMOVED**; intent re-homed at run level (§10.14) |
| `server.py` gate@6 `is_benchmark` badge | display | **kept on membership** — "part of the yardstick corpus" is true and useful to an operator |
| `stage7_execute` ×3 (`_gather`, `_bundle_alternate`, `_dispatch_recover_band`) | may this spawn new PAID work? | **left on membership — open decision, §10.15** |
| `stage5_followup.compose_zero_yield` | escalate from this batch? | genuinely batch-grain, correct as-is (unchanged from §2) |
| `backfill_receipts.load_benchmark_ids` | tooling: `_benchmark` basename | corpus-wide sweep, batch-grain, correct as-is |

**Why the gate@8 queue had to land WITH the Stage-9 wall, not after it.** CLAUDE.md sequenced the
`aggregate_districts` rescope as the step *after* #619. It cannot be: gate@8 is the only door to a
Stage-9 write, so re-keying Stage 9 while the queue still excluded by membership would have left the
fix **unreachable** — an honestly re-run district could never have been approved in the first place,
and #619's stated acceptance property would have been vacuous. The two are one terminus.

### 10.14 The early-exit inversion, and a predicate extracted so a test could pin it

The mode-stability exemption's intent (REQ-151: a *measurement* run wants the full census, or the
shortcut measures the shortcut) is a property of **the run**, not of a district. It moved to the call
site as a third disabler beside `run_kind == 'production'` and `gt_data is None` — now
`dispatch_type != 'benchmark'`, read off the frozen handoff, which is also the only form that can see
a Council Lab A/B built entirely from production reps.

Both pre-#619 pins inverted, as §10.4 predicted for one of them (the second,
`test_early_exit_exempts_any_benchmark_batch_not_just_batch_00000`, was #621's regression guard and
inverts for the same reason — the epic predicted one of the two). The run-level condition was
**extracted into `_early_exit_enabled`** rather than left inline: pinned inline, the test would have
asserted against a *copy* of the condition rather than the code, which is the failure mode where a
test passes while the shipped path drifts.

### 10.15 The #134 request-execution wall — deferred to #620, and NOT for the reason first given

`stage7_execute`'s three sites refuse to spawn new work (7→6 / 7→3 / 7→2 / 7→1) for a
benchmark-membership district. Same district-permanent shape #619 retires, and the same re-key is
available and cheap (`extraction_request.handoff_hash` feeds arm 1; its `target` rec_key feeds arm 2).
Decided with Ian 2026-07-26: **re-key them to provenance inside #620**, where the need is real and
observable, rather than speculatively now.

> **CORRECTION to this section's first draft.** It argued the deferral was safe because these are a
> *spend* decision rather than a write decision, and "the wall currently failing closed costs nothing."
> **That is wrong, and §10.17 is why:** the membership wall is currently the only thing keeping
> benchmark districts away from two freeze paths that bypass #618's provenance refusal. It is not
> inert — it is accidentally load-bearing. The deferral stands, but #644 is now its **blocking
> prerequisite**, and the ordering matters in a way the first draft did not see.

Worth recording that #134's own stated rationale is now obsolete in its premises: it exists to stop
compose from "evading the funnel-stats and **Stage-9 walls that key off batch_type**" — the very wall
#619 just retired. The guard outlived the thing it was guarding, which is exactly the review that
Ian's re-anchoring invites (progressive definition earns a revisit).

Also considered and NOT chosen for now: giving the back-edge composer a **declared** dispatch/batch
type (the `redo_attempted` "declared, not derived" precedent), letting an operator compose benchmark
back-edges deliberately and removing the need for any wall. Correct in shape, but speculative until
the Council Lab actually wants benchmark back-edges (#80/#103, parked) — default production plus a
working freeze refusal covers today's need.

### 10.16 FINDING — #618's freeze guard has two bypass paths (#644)

Surfaced by asking what #134's wall would actually be protecting once re-keyed.
`assert_dispatch_type_allowed` is called at **exactly one** site (`stage6_dispatch.py:399`, the normal
gate@6 freeze), but **three** paths freeze a dispatch. The two gate@7 back-edges —
`stage7_execute._bundle_alternate:854` and `_dispatch_recover_band:947` — call `HND.freeze(...)`
directly and never set `dispatch_type`, so it defaults to `production`.

A 7→6 directive names its alternate reps by `rec_key` from the district's live reps, and a
batch_00000 district holds `benchmark_gt` captures (95 across the 27). So these paths **can mint a
production dispatch containing injected `gt://` reps** — precisely what #618 refuses on the path it
guards.

It has never fired because #134's membership wall keeps benchmark districts away from both paths. That
is the finding: **a district-identity accident is load-bearing for a provenance rule**, which is the
coupling this epic exists to retire, and it breaks the moment #134 is touched. Filed as **#644**, with
a fitness test asserting every `HND.freeze` call site is guard-preceded — the defect is a *missing call
site*, so counting them is the only durable fix.

**The generalizable lesson, third instance in this epic.** §2 undercounted guard spellings, §3
undercounted redo-lever sites, §10.13 found 8 guard sites where #619 named 3 — each time from
enumerating the sites an issue listed instead of the sites that exist. This one is the same error in a
new shape: not "how many places assert the rule" but **"how many places must the rule fire, and does
it?"** Grep the *guarded operation* (`HND.freeze`), not just the guard.

**FIXED same day.** Both back-edges now call the guard through `_refuse_benchmark_reps`, a declared
adapter returning `stage7_execute`'s `{"ok": False, "reason": …}` contract rather than raising — the
exception form stays right at gate@6, where a raise rolls the session back with nothing written.

The durable part is the fitness test, and its shape follows directly from the defect: testing the
*guard* again could never have found this, because the guard was correct everywhere it was applied.
So the test walks the AST and asserts that **every function containing an `HND.freeze` call also
calls the guard, above it** — per-function, not per-module, since a module-level count would pass on
a file that guards one path twice and another not at all, which is precisely this defect's shape. It
is falsified against the verbatim pre-fix body of `_bundle_alternate`. Sanctioned wrappers are named
explicitly rather than pattern-matched, so a new indirection has to be added deliberately — that
addition is the review point.

The test also earned its keep immediately: it failed on first run *after* the fix, because both
call sites reach the guard through the adapter. That is the detector refusing to accept an
indirection it had not been told about — the correct default for a rule this load-bearing.

### 10.17 Test surface

+14 DB-free, +7 govdb, +3 integration. The named acceptance test is
`test_benchmark_batch_membership_alone_no_longer_refuses` — a district seeded into a benchmark batch,
honestly re-run, **incorporates**. Both arms are pinned independently and adversarially (each proven
to see the case the *other* arm is blind to), the fitness function that keeps the predicate in one
home now covers the provenance arms too, and its falsification corpus carries **both polarities** —
the three real prose/error-string forms that an earlier draft of the detector wrongly flagged are
pinned as must-NOT-fire, because a detector that cries wolf gets ignored.

### 10.18 The blocker #620 hit immediately — and the grain error it turned out to be (#647, #646)

With the guards re-keyed, the next step was to actually move the 27 districts: three targeted
follow-up batches (`batch_00030`/`00031`/`00032`, 9+8+8 = 25 districts — see #646 below for the
missing two), composed with `redo_attempted = true`. Ian approved all three at gate@1 and reported
that **Stage 2 showed every district as already discovered, with no way to action the batch** —
reasonably read at the time as "we are still bound by some of the batch_00000 locks."

**It was not a lock.** Nothing in the retired wall or its replacements was involved. The console's
`status_for_batch` computed done-ness from *the presence of `discovery.json` on disk*, which is a
fact about a **district**, being used to answer a question about **this batch's work**. `stage2.js`
gates its Run control on `canRun = approved && r.todo > 0`, so a redo batch — whose entire purpose is
to re-run districts that are already done — reported `todo: 0` and hid its own button. Meanwhile the
*runner* (`reconcile`) had been taught to read `redoes_attempted` in Phase 2c and would have
processed all 9 districts happily. **A view/run disagreement, not a wall**: the console was refusing
to offer work the pipeline was ready to do.

**This is the epic's own error, one surface over.** Phase 2c made redo a *declared property of the
batch*, but only the write side learned to read it. Every read-side surface that asks "is this
district done?" from a district-grain artifact inherits exactly the identity-vs-work confusion #619
exists to retire. The undercount pattern also struck a fourth time (§10.13 was the third): Stage 2 was
fixed first, and only a check-ahead found Stages 3 and 4 showing the same symptom.

**Stages 3 and 4 had the same symptom and a DIFFERENT root cause — and the obvious fix was wrong.**
The natural move was to copy Stage 2's pattern: scope done-ness to the completion `state_event` for
this batch. Measured against live data before committing, completion events carry `batch_id` on
**28/147** stage-3 rows and **0/128** stage-4 rows — `finish_district` had never been passed the
batch, so only the run loop's `dispatched`/`failed` events ever carried it. That fix would have
declared all **18 historical follow-up batches never run**, inviting a re-pay for capture and
processing already completed. It was caught by building a regression table across all 30 pre-existing
batches *before* committing rather than after, which is the only reason it cost nothing.

What shipped instead is two-part, and the split matters:

- **Going forward**, `batch_id` is threaded into `finish_district` in both `capture_stage3.py` and
  `process_stage4.py`, so completion events start carrying it. This fixes the data, not the read.
- **For the status computation**, use a signal that has *always* been reliable: intersect on-disk
  artifact existence with "this batch actually **dispatched** this district" (`state_event`
  `event_type='dispatched'`, which has carried `batch_id` for its whole history). This is a **proxy**
  and is named as one in the code — it answers "did this batch do work on this district" rather than
  "did this batch finish it," and it is correct precisely because dispatch precedes completion.

Two smaller things fell out. Stage 2's fix also cleared a latent bug in `batch_00025` (approved but
never run, silently hiding its own Run control — the same `todo: 0` symptom with no redo involved).
And the shared helper landed in `common/district_status.py::dispatched_by_batch`, **not** in
`stage3_capture/headless.py` where the first draft put it: stage 3 and stage 4 are independent
siblings and cannot import each other. `lint-imports` caught it before the commit. The Phase 2c
lesson, repeated.

**#646, filed and NOT fixed:** a district with no confirmed domain that has already been attempted
(`furthest_stage >= 3`) is unreachable by *every* Stage-1 composer — the first-run pool excludes it as
attempted, and the targeted composers need a domain to scope discovery. Two of `batch_00000`'s 27 sit
in exactly that state, which is why #620's re-run covers 25. It is a composer-reachability gap, not a
benchmark question, and it is the second time this epic has found a district stranded by a rule that
was never meant to be permanent.

**Relationship to #622/#623:** this whole class of bug is the disease those issues cure. Disk-artifact
existence *as* the stage-done marker is the premise being inverted. #647's fix is a scoped patch on
the read side that keeps #620 moving; it does not remove the premise, and should be revisited (and
likely deleted) when the done-markers move to gov_db.

### 10.19 The adversarial review of PRs #641 + #648 — 13 issues, and what they say about the epic

With PR #648 open and green (6/6 CI), both PRs were put through a max-effort multi-agent review: ~11
finder angles (line-by-line diff, cross-file trace, removed-behavior audit, language pitfalls,
duplication, simplification, efficiency, altitude, conventions) plus their children — 48 subagent
transcripts, ~1.9M subagent tokens. **Thirteen issues were filed, #649-#661**, all as sub-issues of
#617. This is the first end-to-end adversarial pass over the epic's own output, and the results split
cleanly into a reassurance and a rebuke.

**The reassurance: no functional regression in the thing that mattered.** Every angle that went
looking for a hole in the two-arm predicate, the Stage-9 wall, the gate@8 queue, the freeze guards, or
the mode-stability inversion came back with the same answer — the guards are correctly wired, the
five original call sites all route through the shared predicate, gate@8 approval is still required
before any write, and the `band_exclusion` escape hatch requires an explicit human action. The
measured claims in §10.11 (83/83 agreement, 56 = 56) held under independent re-derivation.

**The rebuke: the epic solved its own instance and did not generalize the fix.** #617 exists because
one rule lived in five hand-maintained copies. It built one home for that rule and a falsified fitness
function to keep it there. But the review found that rules **this epic itself introduced** have the
same disease and none of the medicine:

| new rule | copies | fitness function? |
|---|---|---|
| the benchmark predicate (the epic's subject) | 1 home | yes, falsified both polarities |
| `dispatch_type` default-normalization (#618) | **8 inline copies** (#650) | none |
| the `redo_attempted` lever (#2c) | 1 home + **2 call sites bypassing it** (#658) | one — and it does not cover these two sites |
| batch-scoped "is this district done" (#647) | 1 helper + **1 hand-rolled twin** (#655) | none |

The consolidation was scoped to *the rule that hurt*, not to *the class of rule*. Each new copy was
introduced by the same reasoning the epic set out to retire — "it's two words, inline is clearer" —
and each is one edit away from the same divergence. **Generalizable: when an epic's finding is "this
rule had N copies," the fix is not only to unify that rule; it is to ask which rule you are creating
in the fix, and give it a home before it has two.**

**Documentation drifted faster than code, and one comment is actively inverted.** Three docstrings
still describe the retired district-membership wall as current behavior (#652), REQ-169's own
acceptance criteria still lists the #134 re-key as open when it shipped in the same PR (#649) — and
worst, `draft_models.py`'s `dispatch_type` comment describes the design the epic **explicitly
rejected**: *"any benchmark_gt rep forces it"* where the code refuses instead (#657). §10.3 recorded
"refuse, never coerce" as the phase's most important design change; the column comment records the
opposite. A stale comment costs a reader a minute. An inverted one invites a future engineer to
"restore" the documented behavior and reintroduce the exact bug — which is why it is the only one of
the thirteen rated `sev:major`.

**Guard scoping is inconsistent across siblings that answer the same question.** `IS_BENCHMARK_-
PROVENANCE_SQL` scopes both arms to `run_kind='production'`; three sibling fragments answering the
same class of question do not (#651). `_early_exit_enabled` consults arm 1 only, so the shortcut can
still fire for the mixed handoff's three districts — the case REQ-151 exists to prevent (#653). None
is exploitable today, each by a different accident (probe hashes are suffixed; the mixed handoff is
historical). **That is the §10.16 lesson recurring: a rule held correct by an accident elsewhere is
not held at all.**

**On the review method itself — the raw output is a candidate list, not a findings list.** A material
fraction of what the agents surfaced did not survive verification against the actual code, and two
cases are worth naming because they cut in opposite directions:

- **Refuted.** An agent reported that deleting `_refuse_benchmark_reps` from `_bundle_alternate` would
  go uncaught, because `test_stage6_dispatch_type.py` only tests the adapter in isolation. True of
  that file — but `test_every_freeze_call_site_is_preceded_by_the_provenance_guard` (§10.16) walks the
  AST of every function containing `HND.freeze` and would fail immediately. **The fitness function
  written for #644 answered a review question about #644 four days later**, which is the clearest
  return this epic's testing discipline has produced.
- **Undercounted.** The same review that catalogued the duplication reported "7 sites" for the
  `dispatch_type` idiom; the actual count is 8. The epic's signature error — enumerating the sites
  someone listed rather than the sites that exist — reproduced itself *inside the audit written to
  catch it.*

Both were caught by re-deriving each claim against the current file before filing. **Generalizable:
an adversarial review's yield is proportional to how much of it you refuse to believe.** Filing the
raw list would have put a refuted finding and a wrong count into the tracker, where they would have
read as verified.

**Disposition.** None of the thirteen blocks PR #648: all are pre-existing, latent, or cosmetic, and
none touches the write path's correctness. They are the epic's own cleanup backlog, sequenced in §11.

### 10.20 CORRECTION to §10.11 — the three layers do not agree, and #620 is blocked (#662)

§10.11 measured the re-key as behaviour-preserving and concluded: *"The two grains diverge only when
#620's re-run mints fresh reps for a district that also holds injected ones — which is the case the
epic exists to unblock."* **That claim is true for Stage 9's wall and false for the two layers in
front of it.** Verified against the live governance DB 2026-07-26, before starting #620's Stage 3:

| layer | scope | after an honest re-run |
|---|---|---|
| Stage 9 wall (`_is_benchmark_receipt`) | the **receipt**'s write-bearing `rec_key`/`fact_id` | correctly **passes** |
| gate@8 queue (`IS_BENCHMARK_PROVENANCE_SQL`) | the **district**, across all production extractions ever | **refuses forever** |
| `merge_fact_runs` (what the receipt would contain) | all production facts, earliest-wins | **old benchmark facts win** |

**Measured:** all **25 of 25** re-run districts are walled by the queue predicate today, on **1198**
`benchmark_gt`-sourced production facts (extractions 2026-07-03 → 07-12). `extraction` and
`school_fact` are append-only, so a fresh run cannot retract them and the `EXISTS` fires permanently.
And of the accepted ones, **957 of 957 carry `school_year = NULL`** — so the year-supersede rule,
which by design compares only two *known* years, never engages, and precedence falls through to
earliest-`extraction_id`. The injected artifact wins against a fresh fact for every school it covers.

**This is the epic's own defect in a new key.** #617 exists because a guard keyed on a fact that is
permanently true (`batch_district` rows are never deleted). The replacement keys on a different fact
that is *also* permanently true (an append-only fact table's history). The grain moved from district
to provenance, which was right; what did not move is the **scope** — "ever" versus "this run."

**How the measurement missed it.** Every number in §10.11 was taken against the *pre*-#620 state — the
one state in which all three layers necessarily agree, because no district yet holds both fresh and
injected reps. A behaviour-preserving check answers "did I break today"; it cannot answer "will the
thing I built for tomorrow work." **Generalizable: when a change is justified by "it diverges only in
the future case," the future case is the one that has to be constructed and tested, not reasoned
about.** The cheap version here was one seeded district and three assertions; it would have cost
minutes and would have caught all three layers.

The decision it forces — how a re-run supersedes prior benchmark facts (strike at gate@8 · provenance
precedence in the merge · reclassify the historical extractions' `run_kind` · scope the closing
argument to the run) — is recorded with tradeoffs in **#662** and is Ian's call. It is the head of the
revised plan (§11), because until it is answered #620 cannot complete and the epic's acceptance
property stays vacuous.

---

## 11. Revised plan — completing #617, then #92 (2026-07-26)

§7's plan is superseded. It was written before Ian's re-anchoring (§10.7), before the mixed handoff
(§10.8), before the review backlog (§10.19), and before #662 (§10.20). This section replaces it.

### 11.1 Where the epic actually stands

**Built and green, not merged:** PR #648 — #619's two-arm guard, #644's freeze-path fix, #134's
re-key, #647's batch-scoped status, plus #620's three composed batches. 6/6 CI.

**Built and merged:** PR #641 — #621, one home for the predicate, `dispatch_type`, batch mobility.

**In flight:** #620's `batch_00030/31/32` (25 districts) are approved with `redo_attempted=true` and
**Stage 2 is complete for all 25**. Their `discovery.json`/`candidates.json` were rotated to
timestamped backups and rewritten; the frozen `gt://` candidates survived the merge (Baldwin County:
12 `gt://` + 23 fresh). Stage 3 is the next console action — **and it should not start until §11.4
resolves**, because everything captured after it feeds a merge that currently cannot produce a
writable closing argument.

**Open on the epic:** 12 pre-existing (#618, #619, #620, #622, #623, #624, #625, #640, #644, #645,
#646, #647) + 14 from the review and the blocker (#649-#662). #618/#619/#644/#647 are *code-complete*
and close on merge.

### 11.2 The critical path is not what CLAUDE.md currently says

CLAUDE.md sequences #625 → #622/#623 → #640 → #624 → #620, with #620 last. **Invert it.** #620 is not
the epic's final chore; it is the epic's **only validation**. Every guard #617 built is unexercised
until a district with mixed provenance actually moves, and §10.20 is the proof: three layers were
wrong and all three measured green, because the only state ever measured was the one where they
cannot disagree. The structural work (#622/#623/#640/#645) is real and needed, but it is *insurance
on a mechanism nobody has yet run end-to-end.*

So: **prove one district, then generalize, then clean up.** The standing lesson — the product is the
pipeline, not the district — is not violated by this ordering, because the deliverable of Phase C is a
*mechanism* plus a *test*, not 25 hand-walked districts.

### 11.3 Phase A — land what is built

**PR #648 merges as-is on the merits.** #662 does not invalidate it: the two-arm predicate is correct
and necessary, and #662 is a *scope* defect in the layer in front of it. Blocking the merge would
strand #644's genuine security fix (two unguarded freeze paths) for no gain.

**Fold in only the text that this PR's own behavior makes false** — #649 (REQ-169's criteria still
call the #134 re-key open, in the PR that shipped it) and #657 (the `dispatch_type` comment describes
the coercion design this epic explicitly rejected). Both are comment/ledger-only, zero code risk, one
CI re-run. Shipping a PR whose own spec ledger contradicts it is precisely the failure §10.19 records;
fixing it costs minutes now and a confused session later. #652's three stale docstrings ride along.

Then close #618, #619, #644, #647, and #621's already-merged sibling work.

**Acceptance:** `main` carries the provenance guards; `gh issue list` for the epic shrinks by four.

### 11.4 Phase B — decide #662, and build the test that would have caught it

**This is a hard gate. Nothing in #620 proceeds until Ian picks a supersession mechanism.** The fork,
with tradeoffs, is in #662; my recommendation is **(c) + (b)**: reclassify the historical benchmark
extractions' `run_kind` so they leave the production pool at the source, and add provenance precedence
to `merge_fact_runs` as the durable forward rule, keeping gate@8's `band_exclusion` as the per-case
hatch. (c) is a declared, audited migration over precious rows and must exclude the mixed handoff
(§10.8), whose production reps are genuine — that exclusion is the risky part and deserves its own
review.

**Before any of it, write the acceptance test, and watch it fail.** The property has been declared
since §7a and has never been executable:

> Seed a district with benchmark-provenance history, run it honestly, and assert it (i) appears in the
> gate@8 queue, (ii) builds a closing argument whose write-bearing evidence is the **fresh** reps, and
> (iii) incorporates.

Today it fails at (i). That failing test is the epic's actual acceptance criterion, and its absence is
why three layers shipped green. **No fix lands before the test that fails on the unfixed code** — the
§10.1/§10.2 falsification discipline, applied to the epic's own headline property.

**Acceptance:** the test above passes; #662 closes; the mechanism is documented in
`PIPELINE_GOVERNANCE_AND_STATE.md` §13 as a durable rule, not a #620 workaround.

### 11.5 Phase C — #620, the campaign

Ian drives the console; I prepare, verify, and fix the pipeline. Order:

1. **One district end-to-end** — Stage 3 → 4 → gate@5 → 6 → 7 → 8 → 9, chosen for a clean mix of
   fresh and injected reps. This is the first real exercise of every guard #617 built.
2. **Decide the gate@5 policy the campaign walks into** (§9, still open): should a stale injected rep
   be *release-eligible at all* after a fresh run — suppressed at Stage 5, or carried and refused at
   gate@6? With (c) chosen in Phase B the pressure drops, but the question is real and #620 is where
   it becomes concrete.
3. **#660 if it bites** — a district needing the `band_exclusion` hatch must be *visible* to use it.
   Under option (c) most districts will not need it; keep #660 hot, not pre-emptive.
4. **The remaining 24**, in batch.
5. **#646** to reach 27/27 — two districts are domain-less *and* already-attempted, reachable by no
   composer.

**Acceptance:** ≥1 district's honest, fresh minutes in `bell_schedules` with production provenance and
a frozen gate@8 receipt naming only fresh reps; then 25; then 27. **Falsifier:** if any district
requires a hand-edit, a re-adjudicated gate@8 decision, or a per-district exception, the mechanism is
wrong and Phase B is not finished — stop and fix the pipeline.

### 11.6 Phase D — the review backlog, in four PRs

Grouped so each PR has one reviewable idea. None blocks #620; all are cheap.

| PR | issues | idea |
|---|---|---|
| guard scoping | #651, #653, #654 | make the sibling predicates agree with `IS_BENCHMARK_PROVENANCE_SQL` on `run_kind` and arms, or document why not — each is currently held correct by an accident elsewhere |
| one home, again | #650, #658, #655, #661 | the rules *this epic introduced* get the treatment the epic gave the rule it was about — plus **one fitness function over the class**, not a fourth per-rule test |
| docs truth | #652, #656 (+#649/#657 if not folded in Phase A) | the ledger and the comments say what the code does |
| gate@6/8 surface | #659, #660 | stop assembling the package twice; make the withheld set visible |

**Acceptance for "one home, again":** a single falsified detector that fails when *any* declared
benchmark/batch rule is re-inlined — the generalization §10.19 says was missed the first time.

### 11.7 Phase E — the structural work

Unchanged in content from CLAUDE.md's list, now correctly placed *after* validation:

**#623** (Node receipts: `stage3_capture` writer + `stage2_candidates` resolver) → **#622** (invert the
done-markers to gov_db; #622 needs #623's Node half) → **#640** (durable rep-grain batch provenance —
build *inside* #623, the seam is already open) → **#645** (the frozen handoff's per-record payload
into gov_db; the REQ-171 blocker) → **#624** (retroactive stage 6-9 receipts, 83/83/38/6) → **#625**
(the REQ sweep, deliberately **last**, so it records the true final state rather than a moving one).

Two carry-forwards: #647's read-side patch should be **revisited and likely deleted** when #622 lands
(§10.18), and #655's Stage-2 divergence resolves itself in the same change. REQ-171 moves from
`proposed` to met when #622/#623/#645 are all in.

### 11.8 Phase F — epic #92 (Stage 9)

#92 is nearly closed already: #93/#94/#95 are done and the 38/38 campaign ran. **One open sub-issue:
#614** — the console's Stage-9 progress/status view. Two adjacent issues belong with it: **#615**
(`district_grade_minutes` has no git-tracked receipt twin, so `district_status.json` goes silently
stale after a write) and **#628** (LCT recompute is a full-corpus ~2m08s rewrite for an O(changed)
input, plus `--dry-run`).

**Sequencing:** all three land *after* Phase C, and #614 in particular is worth little before it —
a status view with 38 historical rows and nothing moving is a different design problem than one
watching 27 districts incorporate. Verified: `stage9_incorporate` does **not** trigger a recompute
itself, so #628 is a convenience for the campaign's tail, not a blocker for it.

**#92's acceptance:** an operator can see, from the console alone, which districts have incorporated,
which are pending, and which failed and why — without running the CLI.

### 11.9 What this plan changes, and the standing risk

**Changed from §7 and from CLAUDE.md's ordering:** #620 moves from last to first-after-merge, because
it is the only validation; #625 moves to last, because a REQ sweep over a moving target is wasted; the
review backlog is triaged as *not* blocking; and a hard decision gate (#662) is inserted ahead of all
campaign work.

**The standing risk is the one this section exists to name.** Three layers of this epic shipped green
against measurements that could not fail. The mitigation is structural, not diligence: **every
remaining phase states an acceptance property that is executable, and no fix lands before a test that
fails without it.** Where that is not possible, the phase says so out loud.

---

## 12. Implementation log — Phases A, B and D (2026-07-26)

Appended, not rewritten (the standing convention in this report): §11 stays as the plan that was
accepted, and this section records what actually happened against it.

### 12.1 Phase A — PR #648 merged (`af1ce77`)

Squash-merged to `main` after folding in only the text the PR itself made false: **#649** (REQ-169's
criterion still called the #134 re-key open, when it shipped on that branch in `4563efe`), **#652**
(three docstrings still framing the wall as "batch_00000 districts are REFUSED"), **#657** (the
`dispatch_type` column comment describing provenance as *forcing* the type when the code refuses —
the design REQ-169 explicitly rejected). Closed: #618, #619, #644, #647, #649, #652, #657.

### 12.2 Phase B — the acceptance test exists and fails (PR #663)

`tests/test_benchmark_rerun_acceptance.py`. Seed a district whose only prior facts came from injected
`benchmark_gt` reps, run it again over ordinary discovered reps, assert the fresh work reaches
production. It had been declared since §7a and had never been executable.

| layer | verdict, measured |
|---|---|
| gate@8 review queue | REFUSES — strict `xfail` |
| `merge_fact_runs` | returns the OLD 400-min fact, not the fresh 420 — strict `xfail` |
| Stage 9's wall | admits — passes |

A fourth test pins the *disagreement itself*, so whichever mechanism #662 lands has to collapse it
deliberately rather than by accident. Both xfails are `strict=True`: when the fix lands they become
XPASS, which pytest reports as a failure, so it cannot land quietly and the markers cannot be left
behind. REQ-169 gains a **SCOPE** criterion (NOT MET, #662) carrying the two measurements: 25 of 25
#620 districts walled today; 957 of 957 accepted benchmark facts with `school_year=NULL`.

**Phase C remains blocked on Ian's decision.** Nothing in the campaign proceeded.

### 12.3 Phase D — the review backlog, four PRs

**#664, guard scoping (#651/#653/#654).** #651 read as "three fragments are missing the production
filter." Verified: **only one of the three should have it**, and giving it to the other two would fail
*open*. The distinction — now written down in `common/benchmark.py` — is what the query enumerates. A
query that sweeps a district's HISTORY must scope to production; a query asked about identifiers the
CALLER ALREADY SELECTED must not, because narrowing there only removes rows the caller asked about.
Both polarities pinned. #653 added arm 2 to the mode-stability disabler (arm 1 is handoff-wide and
blind to the mixed case), degrading conservatively — a lookup failure costs paid calls, never silence.
#654 narrowed a fail-closed `except ProgrammingError` to SQLSTATE 42P01 in **both** predicates; the
docstrings had always promised "only a missing table" and the code caught renamed columns too.

**#665, one home again (#650/#658/#655/#661) — and the generalization the epic missed.** The epic
consolidated one rule and guarded it, then introduced three more and hand-copied every one. All four
are now single-homed. The durable change is `tests/test_one_home_fitness.py`: a **declared table** of
seven one-home rules, each with a home, a scope, a forbid pattern, and a falsification corpus of
copies that really existed. Four tests over the table — no re-spelling in scope; the detector catches
every real removed copy; it does *not* fire on a mere mention (every negative is verbatim prose or an
operator error string that tripped an earlier draft); and every detector still matches its own home,
so a renamed rule cannot leave a dead guard passing forever. The two bespoke detectors in
`test_benchmark_predicate.py` moved in as rows — one home applied to the guards themselves.

*One correction surfaced here:* #655's premise ("Stage 2's completion events have always carried
`batch_id`, so the hand-rolled twin is safe") is not quite true — **12 of 147** `found_all` rows carry
none, while **126 of 126** `dispatched` rows do. The twin could read a completed redo district as
`todo`. Measured before converging: on the three live #620 redo batches both rules agree on all 25.

**#666, docs truth (#656).** `arch-manifest.json` restored to literal punctuation and its
serialization pinned. Nothing emits this file programmatically, so the test *is* the fix.

**#667, gate@6-8 surface (#659/#660).** #659 was filed as efficiency; it is also correctness. The
staleness gate hashed one build and froze an independently rebuilt second one, so a change landing
between them passed the gate and was frozen unseen — the window issue #37 exists to close. Now one
`ReleaseBundle` is built, hashed, and passed through; every path assembles exactly once, pinned in
both directions. #660 surfaced the withheld set: the gate@8 queue hid benchmark-provenance districts
entirely, so REQ-169's named remedy (`band_exclusion`) had **no route to it** — and #620 walks
straight into that population. Playwright-verified against the live DB: 26 withheld / 47 queued, and
the first withheld district opens to a closing argument whose evidence path is a `gt_curation_*.pdf`.

### 12.4 What this round confirms about §10.19

The review's own output needed the same discipline it was measuring. Of the findings acted on here,
**two were materially wrong as filed** — #651 named three fragments where one was correct, and #655's
stated premise was false in a direction that made the bug *worse* than described, not better. Both
were only resolvable by measuring rather than by reading. That is the same failure mode as §10.20, one
level up: a claim about the code, plausible on its face, that had never been checked against the data.

**The generalization now has a home rather than a lesson.** §10.19 observed that the epic guarded a
rule instead of a class; `test_one_home_fitness.py` is that observation made executable, and adding a
consolidated rule to `common/` without a row in it is now a visible omission.

### 12.5 #662 resolved — decided, and two of its own claims corrected (2026-07-26)

**Decision (Ian): (c) + (b).** Reclassify the historical harness extractions out of the production
pool; add provenance precedence to `merge_fact_runs` as the durable forward rule. Four sub-decisions:
`run_kind='benchmark'` as a third value (not a reuse of `probe`, which means a council-VARIANT
measurement); the queue predicate's *shape* left alone because #644 sealed the source that mints such
facts; #617 closes at **25/27** with #646 following; and `gt://` reps **badged** at gate@5/6, never
filtered.

**Option (a) withdrawn — for a worse reason than "it doesn't scale."** #662 offered "strike them at
gate@8 (`band_exclusion`)" as correct-in-shape but ~957 human decisions. Measured, it is not correct
in shape either: `merge_fact_runs` collapses to ONE row per `(band, school)` *before* exclusions are
applied (closing_argument.py:220), and exclusion filters by `(band, norm_school)` with no fallback to
the runner-up. Striking the stale winner therefore **deletes the school from the band** — the fresh
reading never appears. `band_exclusion` remains what #257 built it for: a per-case hatch for a school
that genuinely shouldn't count.

**Two of this report's own claims were wrong, both stated at the wrong grain:**

1. §10.8 and #662's option (c) both warned the sweep "must exclude the mixed handoff whose production
   reps are genuine." **Zero extractions are mixed.** `f33790e63820` is mixed at HANDOFF level (9
   districts, 3 holding `gt://` reps); every individual extraction is cleanly all-injected or
   all-discovered. The caveat that made (c) look risky simply does not exist at extraction grain.
2. The implied auditability risk — reclassifying rows underneath signed decisions — is also absent:
   **0** of the 27 carry a `stage8_approval` and **0** have any Stage-9 event.

Both were resolvable only by querying. Neither was resolvable by reading the code, which is how they
survived three drafts of this document.

**Two defects that only running the thing surfaced.** They belong here because both are the same
lesson as §10.20 in miniature — a thing that looked right and had never been executed:

* The migration's `--dry-run` **wrote receipts**. Receipts are datetime-stamped, so three rehearsals
  left 81 files across 27 districts and the manifest of a real change would have been
  indistinguishable from the litter of the rehearsals. Now a dry run writes nothing at all.
* The gate@5 `gt://` badge shipped **invisible**. The flag was added to `/api/tree`; the console
  renders `/api/stage5/districts`, whose record projection is an explicit ALLOWLIST that silently
  dropped it. A payload test against `/api/tree` passed. Playwright against the real console found it
  in one run. (A third, smaller one: a "receipt landed in the wrong district's directory" alarm was my
  own error — two `find` invocations returned different orderings and I compared a path from one
  against a payload from the other. 81/81 were correct.)

**Honest scope on (b).** Post-(c), and with #644 having closed all three freeze paths, **no production
code path can reach the provenance axis** — the historical rows are relabelled and gate@6 refuses a
production freeze holding an injected rep. It is defence in depth: the merge's correctness no longer
depends on that guard being perfect, and a future injection mechanism (a new GT corpus, a different
`capture.source`) would otherwise re-create #662 silently. Per §10.19's standard the case is
constructed and tested directly rather than asserted as a future possibility.

**Phase C is unblocked.** Stage 3 on `batch_00030/31/32` can start once PR #663 merges.
