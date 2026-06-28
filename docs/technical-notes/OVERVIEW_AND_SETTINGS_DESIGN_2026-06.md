# Console — Overview & Settings: design (cross-stage surfaces)

> **Status: DESIGN.** The console's **cross-stage** surfaces — the view selector, the Pipeline Overview,
> and Settings — as distinct from the per-stage views (those live in each `STAGE*_DESIGN_*.md`). Seeded
> from the APGA console user stories (migrated here 2026-06-27 from the retired
> `docs/scratch-paper/apga_console_application_stage_view.md`). Authority for the model:
> `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §11 (gates/console) + §7/§7a/§7b (app scope, orchestration,
> the deferred UI notes). This note collects the *console-wide* user stories; the gates themselves and the
> state model are governance's.

The console is the **Acquisition Process Governance App** (`process_governance/`), today the Stage-5
review surface, growing into the stage-selectable governance console (gate@1 backend built 2026-06-27,
REQ-102). Build authority + sequencing: governance §9.

---

## 1. Console Views — the view selector
- As a user, I want to **select different console views from a menu.** The wordmark becomes a **stage
  selector**; each stage swaps its view/controls (gate@1 queue, gate@5 review, gate@6 handoff, …), and the
  cross-stage views below (Overview, Settings) are selectable too. **Open:** which stages get a *read*
  view vs an *action* surface (governance §7b).

## 2. Pipeline Overview
> **RELAXED 2026-06-27 (governance §11c):** the Overview is **"what just happened / what needs attention"
> — a projection over the `state_event` log**, NOT a live "what's processing right now" feed. The durable
> event log is deliberately completion-only (no interim in-flight markers), so the ephemeral live layer is
> dropped. **Start** kicks off full-auto advance; **Safe-Stop** lets in-flight work complete (progress
> bar); **pause dropped** (not worth the complexity). Auto-advance through the paid stages (6/7) is
> **cost-gated** (budget governor, REQ-051).

- As a user, I want to see, across the nine stages, **what just happened and what needs human attention** —
  which districts/batches are awaiting a gate, what's in flight, what's flagged. *(The attention queue is a
  query over `state_event` current-state — governance §7b "home view".)*
- As a user, I want to see **percentage yields and fallout from the chained stages 1–5, by batch.** *(The
  measurement-harness/funnel pattern surfaced per batch — governance §11f.)*
- As a user, I want to **Start** all processes (full-auto advance) and **recoverably Safe-Stop** them.
  *(Pause was dropped.)*

## 3. Settings — per-gate manual/auto
- As a user, I want to **toggle each human review gate between manual and automatic** mode (automatic =
  self-advancing/self-governing). At present that means toggles for **Stages 1, 5, 6, 7, 8** (the five
  gates; stages 2/3/4 + the Stage-9 write are ungated). **Global default + per-gate overrides;** AUTO is
  **confidence-escalating** (auto-accept high confidence, auto-escalate/flag low confidence) — governance
  §11b. This is the lever for the **ramp-up model**: manual + high supervision now, loosening as confidence
  grows.

## 4. Open
- Layouts (deferred — governance §7b: "no layouts yet"). These are *things the eventual UI must expose*,
  not designs.
- Actor identity in the UI (single-user now; the event log already carries `actor` for the multi-user
  cloud future — governance §7a-D).
- The orchestration/job view (run-next-stage triggers whose status is itself event-log rows — governance §7a-B/C).
