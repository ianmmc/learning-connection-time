# Console — Overview & Settings

> **Authority:** the console's **cross-stage** surfaces — the view selector, the Pipeline Overview, and
> Settings — as distinct from the per-stage views (those live in each `STAGE*_DESIGN_*.md`). The gate
> model and state schema themselves are `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`'s authority; this note
> covers only the console-wide UI built on top of them.
> **Audience:** whoever builds or extends the Overview/Settings surfaces.
> **Companions:** `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §11 (gates/console) + §7/§7a/§7b (app scope,
> orchestration); the per-stage `STAGE*_DESIGN_*.md` notes (each stage's own view).
> **Update this when:** the Overview or Settings surface is built, or the view-selector mechanism changes.
> **Disambiguation:** "Settings" in this doc means the still-unbuilt per-gate manual/auto UI (§2b) — not
> the separate, already-mature config-as-data knob system (`common/config_loader.py` + 11 knob files under
> `common/config/*.json`, e.g. `budget.json`, `council_configs.json`, `stage5_attention.json`; REQ-088).
> That knob system is edited by hand/PR, has no console UI, and is out of scope here.

The console is the **Acquisition Process Governance App** (`infrastructure/acquisition/process_governance/`).

---

## 1. Present state

**Built:** a stage view switcher. `static/gate1.js`'s `applyView()` swaps the visible stage panel
(`static/{gate1,stage2,stage3,stage4,stage6,stage7}.js` each own one stage's DOM + API calls); Stage 5's
view (`static/app.js`) is reached through the same switcher and re-fetches on show (`window.loadStage5`).
`static/stage7.js` is the gate@7 console view (REQ-117) — registered the same way as the other stages
(`gate1.js`'s `VIEWS` includes `stage7`, and `applyView()` calls `window.initStage7` on show).

**Not built:** a Pipeline Overview view, a Settings view, any manual/auto gate toggle, and any
Start/Safe-Stop control. Nothing in `server.py` exposes `/api/overview` or `/api/settings`. Every gate
today is **manual only** for its standard approve/reject action — gate@1, gate@6, and gate@7
(`STAGE7_EXTRACT_DESIGN_2026-06.md` §0) require an explicit console approval; gate@5 is per-record
labeling; gate@8 doesn't exist yet as a console/gate (Stage 8's aggregation logic itself is now partially
built — see §2a's cross-reference below). There is no code path that reads or writes a per-gate
manual/auto **flag**. gate@7 does carry one narrow, additive auto-*behavior* on top of that manual
default — see "gate@7 auto-withdraw" below — but it is a specific carve-out, not a general toggle.

**Gate-decision calibration log now live (REQ-121 / #210).** `gate_calibration.py` (in
`process_governance`, not `common/`, since it translates the console's decision vocabulary — a label, a
dispatch click, a directive approve/reject — into the calibration vocabulary of accept/reject/escalate)
builds a record per human gate decision; `common/calibration.py`'s `record_calibration`/`build_record`
persist it on the SAME transaction as the gate's existing write. It's wired at three of the human-review
gates: gate@5 label (`server.py` imports at lines 30-31, the write at lines 278-285), gate@6 dispatch, and
gate@7's terminal request review (`server.py` lines 1608-1625). Each record pairs a continuous proxy (e.g.
gate@5's combiner `sort_score`, gate@7's council agreement ratio `n_accepted/(n_accepted+n_unresolved)`)
with what the tier/detector's auto recommendation would have been, so the corpus can later show whether
that proxy predicts the human's decision. This is the data-collection groundwork the eventual Settings
auto-mode (§2b) needs to set thresholds responsibly — §2b is still unbuilt, but it is no longer starting
from zero evidence.

**gate@7 auto-withdraw — the one existing auto-gate precedent (REQ-123 / #233).** Once cumulative
pipeline state satisfies a pending request-more-evidence directive's premise (e.g. the band now has a
cumulative accepted fact, or every fillable band is covered — `stage7_run.py` lines ~829-833), gate@7
auto-withdraws that directive rather than waiting for a human to reject it as moot. This is a deliberate,
narrow exception to the manual-first ramp-up posture, justified by risk asymmetry: auto-act in the
spend-conservative direction when the failure mode is observable and reversible (a withdrawn directive can
be reopened; per its premise-recheck logic, reopening a directive whose premise is still satisfied
immediately re-withdraws it with a fresh note rather than resurrecting stale work). It is a case study for
§2b's design, not a replacement for it — every other gate, and gate@7's own approve/reject action, remains
manual-only today.

---

## 2. Planned (not yet built) — design intent, seeded from the APGA console user stories

### 2a. Pipeline Overview (tracked: #97)
**"What just happened / what needs attention" — a projection over the `state_event` log**, NOT a live
"what's processing right now" feed (governance §11c: the durable event log is deliberately
completion-only, no interim in-flight markers, so an ephemeral live layer was explicitly dropped). Planned
controls: **Start** (kick off full-auto advance) and **Safe-Stop** (let in-flight work complete, with a
progress bar) — **Pause** was considered and dropped as not worth the complexity. Auto-advance through the
paid stages (6/7) would be cost-gated by the budget governor — the governor's core is now BUILT
(`common/budget.py`): a global `per_run_usd` ceiling, a `per_district_usd` per-run cap, a
`max_request_rounds` depth guard (`budget.py` lines 34-52, 103-105) that bounds how many re-request
rounds a district×band may fire so the 7→6/3/2/1 request loop provably terminates, and — the mechanism
that actually defends the request loop across follow-up rounds — `per_district_total_usd` (`budget.py`
lines 16-20, 95-101), a per-district cap seeded from that district's CUMULATIVE recorded spend across ALL
handoffs, so a hard district that keeps failing and re-requesting can't rack up unbounded spend one fresh
handoff at a time. All four are wired into Stage 7's `run_council_streaming` and `stage7_execute`. It's the
Overview's auto-advance UI itself (and the per-gate manual/auto toggle below) that is not built.

Stage 8 (aggregation) itself is not yet a console/gate, but its logic module now exists —
`stage8_aggregate/aggregate.py` (incl. `merge_fact_runs`, used to fix #232/REQ-122's cumulative-facts bug)
— which is the module the eventual gate@8 will sit on top of.

User stories this would satisfy:
- See, across the nine stages, what just happened and what needs human attention — which
  districts/batches are awaiting a gate, what's flagged (an attention-queue query over `state_event`
  current-state — governance §7b "home view").
- See percentage yields and fallout from the chained stages 1–5, by batch (the measurement-harness/funnel
  pattern surfaced per batch — governance §11f).

### 2b. Settings — per-gate manual/auto (tracked: #104)
Toggle each human review gate (governance §11a: gate@1/5/6/7/8) between **manual** (human acts) and
**automatic** (self-advancing). **Global default + per-gate overrides**; auto would be
**confidence-escalating** (auto-accept high confidence, auto-escalate/flag low confidence — governance
§11b) — the lever for the ramp-up model (manual + high supervision now, loosening as confidence grows).
No gate has this manual/auto flag implemented; this section remains design intent — but it is no longer
starting from nothing. Two pieces of the eventual toggle already exist: the gate-decision calibration log
above is the input data an auto threshold would need to be set responsibly, and gate@7's auto-withdraw
above is a working (if narrow, single-purpose) precedent for what an auto-mode action looks like at a
gate. Neither is the toggle itself.

### 2c. Open questions (unresolved, not yet worth a decision)
- Which stages get a *read* view vs an *action* surface once Overview exists (governance §7b).
- Layouts (governance §7b: "no layouts yet" — these are things the eventual UI must expose, not designs).
- Actor identity in the UI (single-user today; the event log already carries `actor` for a multi-user
  future — governance §7a-D).
- The orchestration/job view (run-next-stage triggers whose status is itself event-log rows — governance
  §7a-B/C).

---

## 3. Decision log

- **2026-06-27 — Overview scope relaxed** (governance §11c). Originally conceived as a live "what's
  processing right now" feed; the durable event log's completion-only design made that infeasible without
  a second ephemeral layer, so the scope narrowed to "what just happened" + the attention queue. Pause was
  considered alongside Start/Safe-Stop and dropped.
- **2026-06-27 — this note's user stories seeded** from the retired
  `docs/scratch-paper/apga_console_application_stage_view.md` (migrated in, source retired).
