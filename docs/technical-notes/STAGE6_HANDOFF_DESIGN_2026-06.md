# Stage 6 — Handoff: routing representations to extraction councils (DESIGN, started 2026-06-27)

> **Status: DESIGN STARTING.** This is a living design note (same role `STAGE5_FILTER_DESIGN_2026-06.md`
> played for Stage 5) — a place to work through Stage 6 before any code. Sections marked **DECIDED**
> are settled (don't relitigate); **OPEN** sections are the working agenda. Authority for cross-stage
> architecture remains `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`; this note will feed back into it +
> `ACQUISITION_PIPELINE.md` + `REQUIREMENTS.yaml` once decisions settle.

**Companions / inputs:** the Stage-6 **user stories are inline in §4** (migrated 2026-06-27 from the retired
`apga_console_application_stage_view.md`); `docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md` (council research:
diversity > count, cross-family consensus, judge > voter, cost cascades); `docs/EXTRACTION_BENCHMARK_FINDINGS.md`
(model leaderboard + measured costs); `STAGE5_FILTER_DESIGN_2026-06.md` (the upstream `filtered.json`).

---

## 1. Purpose & boundary

**Stage 6 decides *what package of representations* to send to *which OpenRouter model council*, and
performs the release/dispatch.** It is **routing + release** — the gate is `gate@6`. It does **no
extraction itself** (that's Stage 7); it routes.

- **Input:** each district's **`filtered.json`** (Stage 5's event-driven projection — the canonical
  records with `decision`/`reason`, one best `send` rep per sent record + the approved alternate
  target-flagged reps).
- **Output:** an immutable **`handoff_<hash>_<timestamp>.json`** (the dispatch record) + the actual
  paid OpenRouter calls that Stage 7 consumes. A `dispatched` `state_event` references the handoff hash.

**Unit of work here:** the **handoff package** — a set of districts' chosen representations, each
district assigned a council config, dispatched together. Organized *by district/LEA* internally
(story 61). Multiple packages can exist concurrently, each advancing only when approved (story 70) —
the same "multiple batches, approve-to-advance" shape as Stage 1.

---

## 2. DECIDED / inherited (the fixed frame)

- **`filtered.json` is the input** — per-district, event-driven, carries the winner **plus** alternate
  target-flagged reps (REQ-094 follow-up, approved 2026-06-27) so `gate@6` can offer representation
  override.
- **The handoff artifact is immutable** — freezes each district's chosen reps + assigned config +
  `(config,labels,data)` fingerprints at dispatch time; a new dispatch is a new file (governance §5).
  This is what makes "what did we send on date X" recoverable across the re-extract / request-more loops.
- **`gate@6` is manual/auto** (Settings toggle). Auto = auto-assign config + dispatch **within budget**;
  manual = human reviews/overrides config + representation, approves dispatch. Auto-advance through the
  paid stages (6/7) is **cost-gated by the budget governor (REQ-051)** — full-auto must not run up
  unbounded OpenRouter spend.
- **Cost lives at Stage 6**, not Stage 5 — only here do we know the council config (the model set). The
  `filtered.json` `cost_estimate` is a stub (`n_records`/`n_files`); the real dollar estimate is computed
  here from `config × token-estimate`.
- **The INVARIANT holds (REQ-054):** the council reads **TIMES** and returns per-school
  `{start_time, end_time, grade_level, school_name}` facts only; Python computes `gross = end − start`
  and the per-band mode (Stage 8). Stage 6 never asks a model to compute minutes.
- **Council = OpenRouter, out-of-process** (governance §7a); **consensus is cross-family, on the
  per-school (start,end) pair, ±15 min** (REQ-056) — same-family agreement is not consensus.
- **The loops Stage 6 participates in** (see the flow diagram's back-edges):
  - **7→6** — re-extract existing reps via a *different* council config (story 58); also "select an
    alternate representation" (story 59) → a new handoff, no new capture.
  - **8→6** — add an existing-rep URL to a new handoff (story 80).
  - Anything needing **new** capture/discovery (recapture, re-discover, band-gap fill) routes back to
    **Stage 1** as a reviewable follow-up batch — **not** created by Stage 6/7/8 directly.
- **Completion grain = district × BAND.** A district is "satisfied" when every claimed band has confident
  minutes; routing/cost reasoning is ultimately in service of *band* coverage, with schools/reps as the
  raw material.

---

## 3. OPEN — the working agenda (what we're here to decide)

### A. What *is* a council configuration? (the heart of Stage 6)
A first-class, registered object (stories 62–66: view/create/assign/override; default assignment). Candidate schema:

| field | meaning | open question |
|---|---|---|
| `id` / `name` | handle (e.g. `cheap-trio`, `accuracy-pair`) | — |
| `models[]` | OpenRouter model ids (from the candidate 6: Gemini 2.5 Flash, Mistral Large 2512, DeepSeek V3.2, Mistral Small 24B, Gemini 2.5 Flash-Lite, Qwen3-235B) | which sets do we seed? |
| `consensus_rule` | cross-family, ±15 min (REQ-056) | **is this fixed pipeline-wide, or per-config?** |
| `judge` | a model that re-reads the page on disagreement (research: judge > extra voter) | is the judge part of the config or a fixed stage? |
| `escalation` | what happens on no-consensus — escalate to a stronger config, or flag? | ties to §B cascade |

**Storage:** a `council_config` table in the governance DB (CRUD via the console), or a versioned
config-as-data JSON (like the Stage-5 knobs)? Lean: config-as-data JSON with provenance, mirroring the
existing `common/config/` pattern — but the *assignment* and *cost* are DB/runtime.

### B. Signals → routing (default assignment) — **the foundational question**
What drives the council config a handoff/representation gets (story 66, "default assignment criteria")?
Candidate signals (all already in the governance DB): **topology** (a `hub` multi-school dump is harder
than a `single_school` page → stronger config), a **difficulty signal** (Stage-5 signals: text density,
table presence, `visual_text_gap`, `n_schools`), **band coverage**, **cost budget**.

The CLAUDE.md open decision — *Path-1 cheap-trio vs Path-2 accuracy-pair, decided by measured escalation
rate* — suggests routing is likely a **cascade** (start cheap; escalate to the accuracy config only on
no-consensus — FrugalGPT/UCCI), not a one-shot assignment.

> **OPEN #1 (decide first — it shapes the artifact + the cost model):** is the council config assigned
> **per-district**, **per-handoff**, or **per-representation**? A hard hub rep and an easy single-school
> rep *in the same district* might warrant different configs — which argues per-representation. But the
> stories ("see the config a handoff is assigned to", "organized by district") read per-district/per-handoff.

### C. Cost estimation (story 67–68)
- **v1:** OpenRouter price/1M × token estimate (input ≈ rep size; output small/bounded). Per config × per rep.
- **Actuals:** OpenRouter returns a `usage` object on each response → capture post-hoc actuals to refine
  the estimator over time. **RESEARCH (story 68):** does the OpenRouter API expose *historical* per-request
  logs/usage beyond the per-response `usage`? (Worth a probe — needed for retroactive accuracy.)
- Feeds: the handoff cost summary, the `gate@6` go/no-go, and the budget governor (REQ-051).
- **OPEN:** token-estimation method (char/4 heuristic vs a real tokenizer per model).

### D. The handoff artifact schema (mostly designed — pin it)
`handoff_<hash>_<timestamp>.json` (immutable): `districts[]`, per district the chosen reps + assigned
config + frozen `filtered.json` fingerprints; the council config(s) used; total cost estimate; created_at.
- **OPEN:** one config for the whole handoff, or per-district / per-rep configs *within* one handoff (follows §B OPEN #1).

### E. `gate@6` manual/auto + re-handoff semantics
- **manual:** review the package, assigned configs, cost; override config + representation; approve dispatch.
- **auto:** auto-assign (cascade) + dispatch within budget; **auto-with-confidence-escalation** (escalate
  or flag on no-consensus — the same pattern confirmed for Stage 5 and Stage 8), never silent on low confidence.
- **re-handoff (story 58):** a district/URL already extracted, re-sent to a *different* config → a new
  immutable handoff file; the prior one is untouched (history preserved).

---

## 4. Requirements to capture (seed from the Stage 6 user stories — not yet numbered)
- Initiate a handoff of not-yet-extracted district representations (57); re-handoff already-extracted reps
  to a different config (58); select an alternate target-flagged representation per URL (59–60).
- Handoff organized by district/LEA (61); see + override the assigned council config (62–63).
- View available council configs; create new ones from OpenRouter models; see default assignment criteria (64–66).
- Per-handoff cost estimate, refined with OpenRouter usage (67–68).
- Approve a handoff for dispatch (69); multiple handoff packages, approve-to-advance (70).

---

## 5. References
- Stage 6 user stories — now inline in §4 (migrated 2026-06-27 from the retired apga doc).
- `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §4/§5 (release/handoff), §7a (council out-of-process).
- `LLM_COUNCIL_RESEARCH_2026-06.md` — cross-family consensus, judge, cost cascade.
- `EXTRACTION_BENCHMARK_FINDINGS.md` — model leaderboard + measured costs (the config candidates).
- REQ-054 (read-times invariant), REQ-055 (gross metric), REQ-056 (cross-family consensus), REQ-051 (budget governor), REQ-094 (`filtered.json`).
