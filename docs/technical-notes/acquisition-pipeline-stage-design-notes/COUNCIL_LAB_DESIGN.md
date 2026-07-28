# Council Lab — the model/council evaluation producer: present state & decision log (#80)

> **Authority:** what the Council Lab is, what it produces, and how it measures — the standing
> "producer" half of the pipeline's two-layer config model (it *measures, fits, and updates* the
> config-as-data the runtime dispatch/extract path reads). §0 maps what exists today (the ground truth);
> §1–§6 hold the design rationale + the workload backlog, with items still genuinely open flagged inline.
> **Audience:** anyone building on or debugging the Lab; anyone A/B-testing a prompt, council, judge,
> cost model, or reader-routing rule against the frozen corpus.
> **Companions:** `STAGE6_DISPATCH_DESIGN.md` §0/§3 (the runtime *consumer* — councils/routing/cost
> it reads), `STAGE7_EXTRACT_DESIGN.md` §0/§4 (extraction + the request loop it also feeds),
> `models-and-council-composition/` (the council research + the batch_00000 full-run report + the fresh
> vision/non-reasoning model catalogs), `EXTRACTION_BENCHMARK_FINDINGS.md` (model leaderboard + costs),
> `PIPELINE_GOVERNANCE_AND_STATE.md` §11b (the ramp-up model this promotes under).
> **Update this when:** the Lab's code behavior, artifacts, or workload backlog changes. Design turns and
> superseded approaches belong in §7 (Provenance / decision log), not here.

**Status: EMERGING — first experiment BUILT AND MEASURED (#82 validated + closed, 2026-07-04); DORMANT
SINCE.** The Council Lab crystallized from the Stage 6/7 build as a distinct, cross-stage concern (it was
first imagined as a Stage-6 module — STAGE6 §2a — but its scope now spans Stage 4 reader-routing, Stage 6
councils/routing/cost, Stage 7 prompts/judge/extraction quality, and the Stage-8-grown GT yardstick).
BUILT today: the config-as-data it produces (council configs + validator, the bootstrap cost model, the
prompt registry) and the **judge-replay harness** (`council_lab.py`, the #82 first workload) + the
Stage-7 GT scorer it reuses. The harness has now RUN for real: the Qwen-VL image-judge swap was measured
end-to-end (§0 "First result") and #82 closed on the evidence. **Not yet built:** the append-only run
**ledger**, the **cost benchmark** (`cost_benchmark`, §3), clean-data **composition** re-benchmarking
(§4), and the dedicated **console view** (§6 — sequenced after the ledger + a few experiments). **None of
this has moved in over a week**: two full epics (#209 Phases 0–2, #200) landed in between with zero
Council Lab activity — the backlog in §2 is unchanged since 2026-07-04. This is a priority call (the
request-loop/data-integrity bugs found by the #122 shakedowns took precedence), not a stall; treat §2's
ranking as still current but not urgent until reprioritized.

---

## 0. As-built (code is ground truth)

**What the Lab PRODUCES today (the config-as-data the runtime reads), all in `common/config/` + code:**
- `council_configs.json` (+ `stage6_handoff/councils.py` validator) — the council registry: 2 cross-family
  voters + a third-family judge, validated on load (family diversity; and, since #82, an **image-council
  vision guard** — every member of an `input_kinds:['image']` council must be vision-capable, read from the
  curated `common/model_families.VISION_CAPABLE` allowlist). **Bootstrap membership**, to be re-benchmarked
  on clean data (§4).
- `council_cost_model.json` (+ `stage6_handoff/cost.py`) — per-council $ = Σ voters + escalation·judge, on a
  labeled **bootstrap** (flat per-call). Carries `provenance` so the runtime is indifferent to
  bootstrap-vs-measured; the cost benchmark (§3) replaces the numbers underneath it.
- `stage6_handoff/prompts.py` — the versioned prompt registry (`SYSTEM_PROMPTS`, e.g. `stage6.extract.v1`,
  `stage6.extract.vision.v1`). Prompt TEXT is hardcoded here; only the id→model binding is config-as-data
  (in `council_configs.json`). A prompt A/B (#81) adds a new constant + registry entry, then flips the
  council's `prompts.default`.

**The measurement substrate (reused, pure):**
- `stage7_extract/validate.py` — `score_run`/`score_district`: per-band (modal gross ±15 min) + per-school
  hit-rate vs the curated GT, plus `gap`/`extra` counts. The Lab's scorecard producer.
- The curated GT yardstick: `data/benchmark/gt_curation_20260621T060008Z/gt_proposals.json` (27 hard-case
  districts, 940/943 schools human-verified). **This set is FIXED — gate@8 approvals do NOT append to it**
  (no such code path exists; Stage 9, the writer, is unbuilt). What grows is a separate **confirmed-fact
  base**: every district approved at gate@8 accrues a `stage8_approval` row + a frozen closing-argument
  receipt, which the pipeline learns from and improves with (realized as pipeline-improvement work, not as
  a write into the GT corpus). So every Lab result must still be **fingerprinted by the GT corpus version**
  (see §5) — the corpus is fixed today, but the fingerprint is what would catch a future intentional
  revision, never silently compared across such an event.
- The frozen receipts to replay against: `data/acquisition/extractions/extraction_<hash>_*.json` — per-call
  model/facts/tokens/cost/generation-id for handoff `a2bc80c004ca` (text, 24 districts) and
  `a2bc80c004ca-image` (vision probe, 23). `batch_type=='benchmark'` — never Stage-9-written.

**BUILT — the judge-replay harness (`process_governance/council_lab.py`, the #82 first workload):**
- `replay_judge(handoff_hash, *, judge_model, council_id, gt_path, limit)` — replays a candidate judge on
  ONLY the reps where the two voters disagreed and escalated, **reusing the voters' already-recorded facts
  from the receipts** (no voter re-call), so the run pays for nothing but the judge calls. It scores the
  SAME reconstruction twice — voters-only (baseline) vs voters+candidate-judge — against GT, isolating the
  judge's effect on both **resolution rate** (disagreements broken) and **correctness** (whether the
  tie-breaks match GT). Reuses `stage7_run`'s content resolver + paid-call path, Stage-8 consensus, and
  `validate.py`. Pure helpers unit-tested (`test_council_lab.py`); the paid replay is a CLI experiment.
- Validated faithful: the baseline reconstruction reproduces the report's exact **88.5% band / 98.1%
  school** on the image run before any judge is added.
- CLI: `python3 -m infrastructure.acquisition.process_governance.council_lab <handoff_hash> [--judge …]
  [--limit N] [--gt …]`.
- **First result (Qwen-VL image judge, #82, 2026-07-04):** replayed all 33 escalated reps, $0.045.
  The swapped-in `qwen/qwen3-vl-235b-a22b-instruct` judge made **32/33** successful calls (1 transient
  provider error, no capability 404s) vs deepseek-v3.2's **0/33** (all "no endpoints support image
  input"). It **recovered coverage without hurting accuracy** — the #82 question: GT bands 88.5%
  (12 gap) → **89.1% (9 gap)**, GT schools 98.1% → **98.2%**, resolving **21/145** disagreements (the
  tie-breaks are correct, not hallucinated). Two secondary reads: the 14.5% resolution rate concentrates
  on SMALL disagreements — big hub-table reps (18-, 37-school ties) stay unresolved because the judge
  emits few facts on dense pages (the reader-routing/hub concern, #85/#121, not a judge defect); and the
  image council overall (89.1%/98.2%) still trails the TEXT council (95.2%/99.3%) on native-digital reps,
  reinforcing the route-by-modality experiment (#132). Qwen-VL stands as a validated **stand-in**;
  benchmarking alternative vision judges is composition work (#80). Record:
  `data/acquisition/council_lab/judge_replay_a2bc80c004ca-image_partial.json`.

**The runtime/consumer side lives elsewhere** — `STAGE6_DISPATCH_DESIGN` §0/§3 (councils/routing/cost) and
`STAGE7_EXTRACT_DESIGN` §0. The Lab NEVER changes the runtime path to run; the contract is the
config-as-data artifact + its `provenance`.

**Package boundary note:** `stage6_handoff/` is a shared package — `councils.py`, `cost.py`, and
`prompts.py` are the config-as-data surface the Lab produces and this doc covers; `handoff.py`,
`models.py`, `package.py`, `requests.py`, and `routing.py` in the same directory are STAGE6_DISPATCH's
runtime-path files (the request-loop mechanics), out of scope here — see `STAGE6_DISPATCH_DESIGN.md`.

---

## 1. What the Council Lab is — the producer/consumer split

The pipeline's config machinery (the cost model, the council seeds, routing rules, prompts) is **not
one-off setup**; it is **standing infrastructure re-exercised over time** as the corpus grows, OpenRouter
prices move, and new models/configs arrive. So the system is **two layers**:

| layer | pieces | cadence | role |
|---|---|---|---|
| **Runtime path** | `councils` registry · `routing` · `cost` estimator · `package` · dispatch · gate@6/@7 · the council extraction | **per dispatch / per run** | the **consumer** — routes + prices + freezes + extracts |
| **The Council Lab** | model/judge/prompt benchmarks · the measured **token model** + live **pricing** cache · a fingerprinted **run ledger** · accuracy/agreement + routing-hypothesis tests | **periodic / on-demand** | the **producer** — measures, fits, and updates the config-as-data the runtime reads |

**The contract between the layers is the config-as-data artifact + its `provenance`** — already built into
the cost model, so the runtime path is indifferent to bootstrap-vs-measured and the Lab keeps improving the
numbers underneath it. **It mirrors the Stage-5 tuning loop** (`stage5_filter/{harness,tuning_ledger,
frontier}.py` + config-as-data + fingerprinted scorecards): **append each run to a ledger** (fingerprinted
by corpus + config + GT version + date), retain history for trend analysis, promote a "current best" —
**not** overwrite-and-forget.

**Why its own note (and, later, its own view):** it emerged from Stage 6/7 conversation and was first
imagined as a Stage-6 module, but it is genuinely **cross-stage** — Stage 4 (reader-routing, #85), Stage 6
(councils/routing/cost), Stage 7 (prompts/judge), and the Stage-8-grown yardstick — and runs on a different
(experimental, cross-run) cadence than the operational per-batch gates. Nesting it under Stage 6
misrepresents its scope. (Console view: §6.)

---

## 2. The workload backlog (leverage order)

Hypotheses to **test**, not adopt — the measured-pass discipline (never tune by eye; the Stage-5
harness/tuning_ledger precedent, memory `feedback-explore-before-scoring-changes`):

1. **Fix + validate the image judge (#82) — DONE, 2026-07-04.** deepseek-v3.2 was text-only and 404'd on
   every image escalation; swapped to the vision-capable, third-family `qwen/qwen3-vl-235b-a22b-instruct`
   (Qwen — a family already in our roster as the text judge) + the `councils.validate()` vision guard.
   The judge-replay harness (§0) measured the coverage recovered (32/33 calls ok, 21/145 disagreements
   resolved, bands 88.5%→89.1%, schools 98.1%→98.2%) — the swap is validated, not merely a stand-in;
   benchmarking further vision-judge candidates is now ordinary Council Lab composition work (#80).
2. **The cost benchmark (§3)** — replace the bootstrap cost model with a measured token model + live pricing.
3. **Reader-routing: camelot vs pdftotext for big hub tables (#85)** — does the camelot table-structured rep
   beat linearized text on dense hub tables, and which Stage-5 signal predicts it. A Stage-6 representation
   override, scored vs GT.
4. **The anti-spray prompt A/B (#81)** — `stage6.extract.v2`, measured with a **page-focus-conditioned**
   spray detector (uniform hours are mostly legit — must not suppress correct uniform-band extraction).
5. **Composition re-benchmark (§4)** — membership is a bootstrap; re-test voters/judge/panel-size on clean
   data (judge is high-leverage — ~47% escalation, ~21% of facts on batch_00000).
6. **Route-by-modality, measured** — which reps genuinely need vision vs text (text dominates native digital;
   quantify the crossover). (tracked: #132)

---

## 3. The cost benchmark (`cost_benchmark`) — DESIGNED, NOT YET RUN

> **Cost and accuracy are DECOUPLED (Ian, 2026-06-30):** cost needs no ground truth — it is tokens × price
> over *any* real representations — so this runs **cost-only on current clean reps now**. The clean-data
> accuracy/composition re-benchmark (§4) is a separate, later effort. Single-model calls here = the
> **benchmark/testing mode** (in production we dispatch to councils, not lone models).

**C.1 — The harness.** `stage6_handoff/cost_benchmark.py` (a script, *not* CI — gated on `OPENROUTER_API_KEY`).
For each (model × representation) it issues one chat completion with the **real extraction prompt** (reads
TIMES only, REQ-054), then records telemetry. Output → `data/acquisition/diagnostics/stage6_cost/` (raw
per-call JSONL) + a fitted `common/config/council_token_model.json` (measured token rates). *Pricing is a
separate live concern:* a fetcher caches OpenRouter `/api/v1/models` into `council_pricing.json`, refreshed
on its own cadence. (The shipped `council_cost_model.json` is a combined flat bootstrap; the target splits
it into the token model + the live price cache, estimator does `tokens × price`.)

**C.2 — Per call (real numbers):** `model`, `rec_key`, `source`, `file_kind`, `content_type`, `n_chars`,
`n_times`; `prompt_tokens`/`completion_tokens` (native `usage`); `total_cost` (OpenRouter per-generation
telemetry, corroboration only — stored output is TOKENS; dollars derive at estimate time from the live price
cache so a reprice doesn't invalidate measured tokens); `latency_ms`; `parsed_ok`; `n_schedules`.

**C.3 — The representation sample** (stratified, seeded, from the DB `representation`/`record` + files):

| dimension | strata | why it matters to cost |
|---|---|---|
| `file_kind` | text · pdf · image | vision tokens price differently |
| content type | school page · district hub table · handbook · image-only (`visual_text_gap`) | input size + which council |
| size (`n_chars`) | S <2k · M 2–8k · L 8–16k · XL >16k | input tokens ≈ f(size); XL = the truncation zone |
| school count (`n_times`) | low · high | OUTPUT tokens scale with schools returned |

~3–5 reps/cell, ≈ 40–60 reps to start.

**C.4 — The models.** The candidate roster on text reps; the vision-capable subset additionally on image
reps. ~300–400 calls, **a few dollars total** — cheap enough to repeat as the corpus grows.

**C.5 — The TOKEN model produced** (dollars come from live pricing): per model, `prompt_tokens ≈ α + β·n_chars`
(text) / `≈ f(image dims)` (vision); `completion_tokens ≈ γ·n_schools + δ`. → `cost(rep, council) =
Σ_voters(in·price_in + out·price_out) + escalation_rate·judge`. The **escalation_rate** is an
accuracy/agreement quantity, NOT measured by this cost-only pass — until §4 exists, a conservative assumed
rate, flagged as such.

**C.6 — Accuracy/composition is a SEPARATE later effort** (§4). Re-measure cadence + exact per-cell sample
size are open, decided after a first run.

---

## 4. Composition + accuracy re-benchmarking — DESIGNED, PARTLY UNBLOCKED

Council **membership** (`council_configs.json`) is a bootstrap seeded from the candidate roster against a
(then) polluted input pool — to be **re-benchmarked on clean data** before Stage-7 composition hardens.
This needs GT aligned INTO the pipeline: the original curation GT had human-confirmed numbers but zero
overlap with current pipeline reps. **Unblocked 2026-07-02** by `batch_00000` — the 27 curated-GT districts
injected at the Stage-3 seam (`stage1_queue/benchmark_batch.py`, `batch_type='benchmark'`, walled off from
Stage-9), so confirmed numbers now pair with current-format reps. The full batch_00000 run
(95.2%/99.3% text) is the first accuracy read-out; the composition sweep (voters/judge/panel-size on clean
data) runs through the same harness + the growing yardstick (§5). Cross-family diversity (REQ-056) is a hard
constraint on every candidate composition.

---

## 5. The run ledger + GT-corpus fingerprinting — DESIGNED, NOT BUILT

Mirror `stage5_filter/tuning_ledger.py` exactly: an **append-only JSONL under DATA_ROOT** (e.g.
`ACQUISITION/council_lab/episodes.jsonl` — a data-root history file, **never a config knob**), one object
per measured run. Each entry copies the run's fingerprints and records the deltas + the decision:
- **fingerprint = `config × GT-version × data`** (the three-part md5 scheme from the Stage-5 harness). The
  **GT-version fingerprint is load-bearing** here even though the yardstick is fixed today (§0) — it is
  what would catch a future intentional revision of the corpus, so a result stays comparable only *within*
  a GT version and any such change is a new fingerprint, never a silent mix.
- a `pure_config_move` flag (config changed, GT + data held) so a recommender never mistakes a
  yardstick-contaminated move for a config result.
- knobs touched (council/prompt/cost/judge), before/after metrics (band/school hit-rate, gap, spray count,
  cost), rationale, decided_by. Promotion = a human recording an episode (the ramp-up control surface),
  never auto-overwrite. An advisory frontier (grid under a hard floor, ranked by the cost-relevant metric)
  can rank candidates — advisory only, like `stage5_filter/frontier.py`.

### 5a. The promotion SUBSTRATE — the guardrail that must ship WITH auto-promotion (planning, 2026-07-10)

The ledger above records a *human-decided* promotion. The moment promotion becomes even semi-automated (a
recommender applies a frontier pick, or a cost-driven re-composition auto-swaps `council_configs.json`), the
runtime is **indifferent to how a config got there** — `provenance` is the only tell, and nothing enforces
it. So the guardrail is not a later add-on; it is part of the definition of "auto-promotion is allowed."
Build these *with* the Lab's promote capability, never after (the shift-left lesson from the #206 review:
enforce the invariant at the boundary, not in the reviewer's head). Tracked in the runtime-guardrail epic
(#209); details here so the Lab build carries them.

**A concrete template now exists — port it, don't design from scratch.** The identical guardrail shape
for the Stage-5 sibling (config-as-data promotion for the filter/scoring config) shipped and closed via
#212 (group-aware non-inferiority promotion gate) + #213 (safe-promotion machinery), merged 2026-07-10
(PR #220): `stage5_filter/config_artifact.py` (the immutable, fingerprinted config artifact),
`promotion_gate.py` (the non-inferiority check gating a promotion), `promotion_pointers.py` (the
`@champion`/`@fallback` pointer-swap — reversible by construction, no file mutation), and
`promotion_flow.py` (the flow tying artifact + gate + pointers together), with `tests/test_promotion_gate.py`
covering it. **It is real, working code — but DORMANT**: per CLAUDE.md's current-status banner, activation
(wiring it live into the Stage-5 path) is tracked as its own checklist, #219, and has not happened yet. So
the Council Lab's own promotion substrate below should be read as "port this pattern," not "invent an
analogous one" — but a reader should not conclude Stage-5 promotion (or, by the same token, a future
Council Lab promotion built on this template) is live or unblocked just because the modules exist on disk.

1. **Provenance + GT-fingerprint enforced ON LOAD, refuse-to-run on mismatch.** Any config the extraction
   runtime loads must carry a `provenance` (which ledger episode promoted it) and the GT-version fingerprint
   it was measured against; if that fingerprint ≠ the current GT corpus, the run **halts loudly** (the
   yardstick moved — the config's accuracy claim is stale). This is the config analog of the Stage-2/3/4
   reconcile hard-stop: a control-failure, not a warning. Today `councils.validate()` checks *structure*
   (cross-family diversity, vision-capable judge) on load — extend it to check *provenance/fingerprint*.
2. **Cost promotions require a same-GT-version accuracy read.** `cost_benchmark` is cost-only and
   `escalation_rate` is an assumed constant until §4 lands — so a cost-ranked auto-swap must be blocked
   unless it carries a *current-GT-version* accuracy number, not a bootstrap. Cost and accuracy are
   decoupled today; the guardrail re-couples them at the promotion gate.
3. **Promotion is reversible: champion-challenger with a warm standby.** Config-as-data already makes a
   config swap a reversible file/row op; formalize it — the prior "champion" config is retained, and a
   promoted "challenger" that trips a post-promotion floor/drift check (§11b of governance) **auto-reverts**
   to the champion. This is the small-scale adaptation of MLOps shadow/canary: we can't split live traffic
   (batch re-score, not a request stream), so the safety comes from the fingerprinted before/after episode +
   a bounded first production tranche + a recorded rollback, not from a % canary.

---

## 6. The console view — AGREED IN PRINCIPLE, SEQUENCED AFTER THE LEDGER

The Lab **merits its own dedicated console view** (Ian, 2026-07-04), *outside* the stage switcher — because
it is cross-stage, config-global (not batch-scoped like every stage view), runs on an experimental cadence,
and owns its own artifacts (the ledger, A/B comparisons, a model/judge leaderboard, the current-best config
with provenance). Burying it in a stage view conflates "run the pipeline" with "improve the pipeline" and
clutters the per-batch gates.

**But timing follows the CLI-first ramp-up** (governance §11: the console UI needs its own design pass;
CLI-first is the established pattern): a view is fundamentally a **reporting + promote surface over the
ledger**, so it can't exist meaningfully until the ledger does. **Sequence:** (1) land experiments as CLI +
the §5 ledger; (2) once 2–3 experiments have written episodes, build the view — show the current-best
config-as-data (councils/prompts/cost model) with provenance, the fingerprinted ledger, A/B before/afters,
and a human **"promote this config"** action. Running an experiment stays a CLI/job trigger; the view is
where you read the evidence and promote. The trade-off in full: building the view now = premature UI over an
unproven workflow; the con of waiting is only that results live in JSONL + terminal until then (acceptable).

---

## 7. References + provenance / decision log

**GitHub (the live backlog):** #80 (Council Lab infra — parent), #81 (anti-spray prompt A/B), #82 (image
judge not vision-capable — reopened, code fix landed, measurement pending), #85 (camelot reader-routing),
#132 (route-by-modality experiment, §2 item 6).

**References:** `models-and-council-composition/` (`LLM_COUNCIL_RESEARCH_2026-06.md`;
`models-and-council-composition.md` — the batch_00000 report + §6 backlog; the non-reasoning + compass model
catalogs); `EXTRACTION_BENCHMARK_FINDINGS.md` (**caveat:** as of this writing it still documents a 3-model
non-reasoning council — Gemini Flash + DeepSeek V3.2 + Mistral Small, ~$0.0029/call — and per-call costs
that predate and are superseded by the current 2-voter+judge cascade template and the
`council_cost_model.json` bootstrap rates (e.g. `mistral-small-24b-instruct-2501` at $0.00022/call,
`gemini-2.5-flash-lite` at $0.00050); read its leaderboard for model-quality signal, not its cost table);
`stage7_extract/validate.py` (scorer); the Stage-5 tuning trio (`harness`/`tuning_ledger`/`frontier`) as the
template. REQ-054/055/056 (read-times, gross, cross-family), REQ-117 (Stage 7 build). No REQ currently
tracks the Council Lab's own deliverables (the cost benchmark, the run ledger) — its status is purely
GitHub-tracked (#80 and children above), not requirements-tracked.

**Decision log:**
- **2026-06-30 — the two-layer producer/consumer split named (Ian).** Conflating the runtime dispatch path
  with the standing measurement infra was an early mistake; the Lab is the producer, the contract is
  config-as-data + provenance. Cost and accuracy decoupled — cost runs now, accuracy waits on GT alignment.
- **2026-07-03 — batch_00000 unblocks accuracy** (the 27 GT districts injected as `batch_type='benchmark'`,
  Stage-9-walled), giving the first clean accuracy read-out and the substrate for composition tests.
- **2026-07-04 — the Lab promoted to its own concern (this note).** Ian: it emerged from Stage 6/7 but
  merits its own note + (later) its own console view given its cross-stage scope. Council Lab commentary
  migrated here from `STAGE6_DISPATCH_DESIGN` (§2a producer/consumer, §3C cost benchmark) and
  `STAGE7_EXTRACT_DESIGN` (§4 config-as-data the Lab tunes); those notes now point here.
- **2026-07-04 — the yardstick grows via Stage-8** (Ian): GT is not fixed at batch_00000's 27; gate@8
  approvals accumulate verified data. Consequence: the ledger fingerprints the GT version (§5). The archived
  `data/archive/gt-benchmark-20260622T152627Z/` is the OLD noisy pre-pipeline results — the motivation for
  the pipeline, NOT a clean baseline.
- **2026-07-04 — the judge-replay harness built (#82 first workload).** A judge-only replay over frozen
  receipts — the cheapest possible signal on a judge swap (reuse recorded voter facts; pay only for judge
  calls; score baseline vs candidate to separate resolution from correctness).
