# Console — Overview & Settings

> **Authority:** the console's **cross-stage** surfaces — the view selector, the Pipeline Overview, and
> Settings — as distinct from the per-stage views (those live in each `STAGE*_DESIGN_*.md`). The gate
> model and state schema themselves are `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`'s authority; this note
> covers only the console-wide UI built on top of them.
> **Audience:** whoever builds or extends the Overview/Settings surfaces.
> **Companions:** `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §11 (gates/console) + §7/§7a/§7b (app scope,
> orchestration); the per-stage `STAGE*_DESIGN_*.md` notes (each stage's own view).
> **Update this when:** the Overview or Settings surface is built, or the view-selector mechanism changes.

The console is the **Acquisition Process Governance App** (`infrastructure/acquisition/process_governance/`).

---

## 1. Present state

**Built:** a stage view switcher. `static/gate1.js`'s `applyView()` swaps the visible stage panel
(`static/{gate1,stage2,stage3,stage4,stage6}.js` each own one stage's DOM + API calls); Stage 5's view
(`static/app.js`) is reached through the same switcher and re-fetches on show (`window.loadStage5`).

**Not built:** a Pipeline Overview view, a Settings view, any manual/auto gate toggle, and any
Start/Safe-Stop control. Nothing in `server.py` exposes `/api/overview` or `/api/settings`. Every gate
today is **manual only** — gate@1, gate@6 require an explicit console approval; gate@5 is per-record
labeling; gates@7/8 don't exist yet (Stages 7/8 aren't built). There is no code path that reads or writes
a per-gate manual/auto flag.

---

## 2. Planned (not yet built) — design intent, seeded from the APGA console user stories

### 2a. Pipeline Overview
**"What just happened / what needs attention" — a projection over the `state_event` log**, NOT a live
"what's processing right now" feed (governance §11c: the durable event log is deliberately
completion-only, no interim in-flight markers, so an ephemeral live layer was explicitly dropped). Planned
controls: **Start** (kick off full-auto advance) and **Safe-Stop** (let in-flight work complete, with a
progress bar) — **Pause** was considered and dropped as not worth the complexity. Auto-advance through the
paid stages (6/7) would be cost-gated by the budget governor (REQ-051, also not built).

User stories this would satisfy:
- See, across the nine stages, what just happened and what needs human attention — which
  districts/batches are awaiting a gate, what's flagged (an attention-queue query over `state_event`
  current-state — governance §7b "home view").
- See percentage yields and fallout from the chained stages 1–5, by batch (the measurement-harness/funnel
  pattern surfaced per batch — governance §11f).

### 2b. Settings — per-gate manual/auto
Toggle each human review gate (governance §11a: gate@1/5/6/7/8) between **manual** (human acts) and
**automatic** (self-advancing). **Global default + per-gate overrides**; auto would be
**confidence-escalating** (auto-accept high confidence, auto-escalate/flag low confidence — governance
§11b) — the lever for the ramp-up model (manual + high supervision now, loosening as confidence grows).
No gate currently has an auto mode implemented; this section is 100% design intent.

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
