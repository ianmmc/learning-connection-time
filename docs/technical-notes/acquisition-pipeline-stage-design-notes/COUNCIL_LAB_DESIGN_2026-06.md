# Council Lab — the model/council evaluation producer: present state & decision log (#80)

> **Authority:** what the Council Lab is, what it produces, and how it measures — the standing
> "producer" half of the pipeline's two-layer config model (it *measures, fits, and updates* the
> config-as-data the runtime dispatch/extract path reads). §0 maps what exists today (the ground truth);
> §1–§6 hold the design rationale + the workload backlog, with items still genuinely open flagged inline.
> **Audience:** anyone building on or debugging the Lab; anyone A/B-testing a prompt, council, judge,
> cost model, or reader-routing rule against the frozen corpus.
> **Companions:** `STAGE6_DISPATCH_DESIGN_2026-06.md` §0/§3 (the runtime *consumer* — councils/routing/cost
> it reads), `STAGE7_EXTRACT_DESIGN_2026-06.md` §0/§4 (extraction + the request loop it also feeds),
> `models-and-council-composition/` (the council research + the batch_00000 full-run report + the fresh
> vision/non-reasoning model catalogs), `EXTRACTION_BENCHMARK_FINDINGS.md` (model leaderboard + costs),
> `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §11b (the ramp-up model this promotes under).
> **Update this when:** the Lab's code behavior, artifacts, or workload backlog changes. Design turns and
> superseded approaches belong in §7 (Provenance / decision log), not here.

**Status: EMERGING — first experiment BUILT.** The Council Lab crystallized from the Stage 6/7 build as a
distinct, cross-stage concern (it was first imagined as a Stage-6 module — STAGE6 §2a — but its scope now
spans Stage 4 reader-routing, Stage 6 councils/routing/cost, Stage 7 prompts/judge/extraction quality, and
the Stage-8-grown GT yardstick). BUILT today: the config-as-data it produces (council configs + validator,
the bootstrap cost model, the prompt registry) and the **judge-replay harness** (`council_lab.py`, the #82
first workload) + the Stage-7 GT scorer it reuses. **Not yet built:** the append-only run **ledger**, the
**cost benchmark** (`cost_benchmark`, §3), clean-data **composition** re-benchmarking (§4), and the
dedicated **console view** (§6 — sequenced after the ledger + a few experiments).

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
  districts, 940/943 schools human-verified). **The yardstick GROWS** — anything human-approved at gate@8
  (Stage 8) becomes additional verified GT; we are not limited to these 27. So every Lab result must be
  **fingerprinted by the GT corpus version** (see §5), never silently compared across a growth event.
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

1. **Fix + validate the image judge (#82) — IN PROGRESS.** deepseek-v3.2 was text-only and 404'd on every
   image escalation; swapped to the vision-capable, third-family `qwen/qwen3-vl-235b-a22b-instruct`
   (Qwen — a family already in our roster as the text judge) + the `councils.validate()` vision guard. A
   **stand-in** pending measurement — the judge-replay harness (§0) quantifies the coverage recovered.
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
  **GT-version fingerprint is load-bearing** here: the yardstick grows via Stage-8 approvals, so a result is
  comparable only *within* a GT version — a growth event is a new fingerprint, never a silent mix.
- a `pure_config_move` flag (config changed, GT + data held) so a recommender never mistakes a
  yardstick-contaminated move for a config result.
- knobs touched (council/prompt/cost/judge), before/after metrics (band/school hit-rate, gap, spray count,
  cost), rationale, decided_by. Promotion = a human recording an episode (the ramp-up control surface),
  never auto-overwrite. An advisory frontier (grid under a hard floor, ranked by the cost-relevant metric)
  can rank candidates — advisory only, like `stage5_filter/frontier.py`.

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
judge not vision-capable — reopened, code fix landed, measurement pending), #85 (camelot reader-routing).

**References:** `models-and-council-composition/` (`LLM_COUNCIL_RESEARCH_2026-06.md`;
`models-and-council-composition.md` — the batch_00000 report + §6 backlog; the non-reasoning + compass model
catalogs); `EXTRACTION_BENCHMARK_FINDINGS.md`; `stage7_extract/validate.py` (scorer); the Stage-5 tuning
trio (`harness`/`tuning_ledger`/`frontier`) as the template. REQ-054/055/056 (read-times, gross, cross-family),
REQ-117 (Stage 7 build).

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
