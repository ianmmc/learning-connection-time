# Console — Overview & Settings

> **Authority:** the console's **cross-stage** surfaces — the view selector, the Pipeline Overview, and
> Settings — as distinct from the per-stage views (those live in each `STAGE*_DESIGN_*.md`). The gate
> model and state schema themselves are `PIPELINE_GOVERNANCE_AND_STATE.md`'s authority; this note
> covers only the console-wide UI built on top of them.
> **Audience:** whoever builds or extends the Overview/Settings surfaces.
> **Companions:** `PIPELINE_GOVERNANCE_AND_STATE.md` §11 (gates/console) + §7/§7a/§7b (app scope,
> orchestration); the per-stage `STAGE*_DESIGN_*.md` notes (each stage's own view).
> **Update this when:** the Overview surface is built, the view-selector mechanism changes, or a gate's
> Settings toggle gains real auto-behavior (today the toggle persists intent only — see §1).
> **Disambiguation:** "Settings" in this doc means the per-gate manual/auto UI (§1, BUILT 2026-07-12) — not
> the separate, already-mature config-as-data knob system (`common/config_loader.py` + 11 knob files under
> `common/config/*.json`, e.g. `budget.json`, `council_configs.json`, `stage5_attention.json`; REQ-088).
> That knob system is edited by hand/PR, has no console UI, and is out of scope here.

The console is the **Acquisition Process Governance App** (`infrastructure/acquisition/process_governance/`).

---

## 1. Present state

**Built: a stage view switcher.** `static/gate1.js`'s `applyView()` swaps the visible stage panel
(`static/{gate1,stage2,stage3,stage4,stage6,stage7,settings}.js` each own one panel's DOM + API calls);
Stage 5's view (`static/app.js`) is reached through the same switcher and re-fetches on show
(`window.loadStage5`). `static/stage7.js` is the gate@7 console view (REQ-117); `static/settings.js` is the
Settings view (§1a below) — both registered the same way as the other stages (`gate1.js`'s `VIEWS` list +
`applyView()` calling the panel's own `window.init*` on show).

**Built: gate-decision calibration log (REQ-121 / #210).** `gate_calibration.py` (in `process_governance`,
not `common/`, since it translates the console's decision vocabulary — a label, a dispatch click, a
directive approve/reject — into the calibration vocabulary of accept/reject/escalate) builds a record per
human gate decision; `common/calibration.py`'s `record_calibration`/`build_record` persist it on the SAME
transaction as the gate's existing write. It's wired at three of the human-review gates: gate@5 label
(`server.py` imports at lines 30-31, the write at lines 278-285), gate@6 dispatch, and gate@7's terminal
request review (`server.py` lines 1608-1625). Each record pairs a continuous proxy (e.g. gate@5's combiner
`sort_score`, gate@7's council agreement ratio `n_accepted/(n_accepted+n_unresolved)`) with what the
tier/detector's auto recommendation would have been, so the corpus can later show whether that proxy
predicts the human's decision. This is the data the calibrated per-gate auto thresholds (§1a) will
eventually need to set responsibly — it accrues regardless of whether any gate is auto today.

**Built: gate@7 auto-withdraw — the first narrow auto-behavior (REQ-123 / #233).** Once cumulative
pipeline state satisfies a pending request-more-evidence directive's premise (e.g. the band now has a
cumulative accepted fact, or every fillable band is covered — `stage7_run.py` lines ~829-833), gate@7
auto-withdraws that directive rather than waiting for a human to reject it as moot. This is a deliberate,
narrow exception to the manual-first ramp-up posture, justified by risk asymmetry: auto-act in the
spend-conservative direction when the failure mode is observable and reversible (a withdrawn directive can
be reopened; per its premise-recheck logic, reopening a directive whose premise is still satisfied
immediately re-withdraws it with a fresh note rather than resurrecting stale work). It predates and directly
informed §1a's general per-gate toggle design.

### 1a. Settings — per-gate manual/auto (BUILT 2026-07-12; #104 part a, #211)

Toggles each human review gate (governance §11a: gate@1/5/6/7/8) between **manual** (human acts) and
**automatic** (self-advancing) — the ramp-up model's control surface. **This is now built and live**,
though behavior-neutral by design: setting a gate `auto` persists the human's decision, but only gate@5 has
a control law that actually reads it (below); every other gate stays manual-only for its standard
approve/reject action regardless of the stored toggle, until that gate earns its own auto path.

**Backing store** (`infrastructure/acquisition/common/gate_mode.py`, REQ-108): a precious `gate_mode` table,
one row per key — `'default'` (the global default) + `'gate@1'..'gate@8'` overrides (`gate@8` is BUILT —
the standalone stage/gate shipped #89, 2026-07-14; the `gate_mode.py:35` inline comment still says
"not built yet", tracked #525). Two fields per row: `configured_mode` (the human's
toggle) and `license_state` (the live deadband state a gate's control law demotes/re-promotes, §1b).
`configured_mode` is **NULLABLE — NULL means "inherit the global default"**, not "manual." This is load-
bearing: a license-only write (§1b, from the demote-hook's first transition) must never materialize a
configured toggle the human didn't set. An earlier version hardcoded `configured_mode='manual'` on a
license-only row's fresh INSERT, which silently and permanently pinned a globally-auto-configured gate to
manual the moment its control law first wrote a license transition — a real bug a PR #248 review round
found and fixed (`gate_mode.py`'s `set_license_state` now inserts `configured_mode=NULL`; `get_configured_mode`
and `all_modes` correctly read a NULL row as "not an override"). Every gate defaults **manual**
(high-supervision-first) when no row exists at all.

**Console surface:** `GET`/`POST /api/gate-mode` (`server.py` ~589-611) + `static/settings.js`'s "Gate
automation" panel — a Manual/Auto button pair per gate, showing "(inherits default)" when a gate has no own
override. Setting a gate persists via `POST /api/gate-mode` and re-renders both the mode rows and the
gate@5 audit panel (§1b) immediately, since gate@5's license readout tracks its configured toggle.

### 1b. gate@5's exploration-audit quota — live wiring shipped, enforcement dormant (#211, REQ-120)

The anti-survivorship exploration-quota control law (`exploration_audit.py`, the pure core) is fully wired
to live DB state in `infrastructure/acquisition/stage5_filter/exploration_live.py`:

- `reject_population(con)` — the audit universe: the current tier-D (SUPPRESS) reject bucket, canonical
  (non-duplicate, cluster-representative) rows only. Imports the canonical-record predicate from
  `release.py`'s `CANONICAL_RECORD_WHERE` (a PR #248 review fix — this module used to hand-inline the same
  predicate, a drift risk against Stage 6's release population using the same string).
- `audit_sample`/`coverage` — the randomized draw + the coverage meter (`window_count` vs. the rule-of-
  three floor, plus `rejection_quality`/TNR over the audited sample's human labels).
- `resolve_gate5_mode` — **the gate@5 demote-hook**, the live caller of `exploration_audit.resolve_gate_mode`.
  Reads `configured_mode` FIRST via a cheap point-read; when the gate is configured manual (today, always)
  and no precomputed `cov` was supplied, it returns **immediately** without touching the reject-population
  query at all — `window_count`/`quality`/etc. come back `None` (skipped, not computed-and-discarded). This
  fast path exists because the hook fires on every gate@5 label save (below): without it, every save would
  pay for a full `record ⋈ label` scan over the whole tier-D bucket just to discover the feature is
  dormant. (`build_signals.py` also gained `ix_record_tier` — the query was previously unindexed — so the
  scan is cheap on the rarer occasions a gate actually is auto.) When configured **auto**, the law is live:
  auto while the audit validates the filter, demoted to manual the instant coverage lapses below the floor,
  promoted back only above the deadband (never flaps). The transition persists to `license_state`.

**Wired into the console's write path**, both symmetrically and safely:
- `save_label` (every gate@5 label click) and `reset_labels` (#228's "Reset labels," which REMOVES audited
  rejects from the coverage window) both call `EAL.resolve_gate5_mode(con)` — self-healing: labeling or
  un-labeling a reject re-evaluates the license off the live coverage on the spot, in either direction.
- Both calls run inside `con.begin_nested()` (a SAVEPOINT) wrapped in a broad try/except that swallows and
  logs. This is deliberate isolation: the demote-hook is advisory to the label/reset write, and a transient
  DB error or corrupt `gate_mode` row inside it must never roll back the human's already-applied write. An
  earlier version ran the hook un-isolated on the same transaction as the write — a defect a PR #248 review
  round found and fixed.
- `GET /api/exploration-audit` (`server.py` ~614-629) is the read-only status endpoint backing the console
  panel: **one** `audit_sample` draw serves the coverage numbers, the resolved mode, AND the pending queue
  (an earlier version ran the population query twice per request — once inside `resolve_gate5_mode`, once
  again for the pending list — which also let a mid-request commit produce two inconsistent snapshots; a
  PR #248 review fix).

**Console panel:** `static/settings.js`'s "gate@5 reject audit" section — population/sample counts, reject-
cohort quality (with the rule-of-three FN-rate ceiling), a coverage bar vs. the floor, and the pending
randomized-draw queue. Two PR #248 review fixes worth noting for anyone extending this panel: (a) the
"live license: X" badge renders only while `configured_mode === 'auto'` — `license_state` is deadband
memory that survives a demotion to manual by design, so an ungated badge previously kept advertising a live
auto license beside an active Manual toggle; (b) the pending-list's `<a href>` for each record's URL is
restricted to `http(s)://` (`safeUrl` in `settings.js`) — `esc()` alone HTML-escapes but doesn't block a
`javascript:` URI, and this is the one place in the console that renders a raw DB-sourced URL into `href`
(every other view uses `href="#"` + a `data-` attribute + JS-side navigation instead).

**Enforcement remains DORMANT today**: gate@5 is configured `manual` by default and no PR has flipped it —
so `resolve_gate5_mode` always returns `"manual"`, nothing auto-suppresses, and the whole apparatus above is
proven-live but inert. See `PIPELINE_GOVERNANCE_AND_STATE.md` §11b for the epic #209 build status
and #219's dormant→live activation checklist.

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
Overview's auto-advance UI itself that is not built — the per-gate toggle it would drive (§1a) already is.

Stage 8 (aggregation) is now a **standalone console/gate — BUILT #89, 2026-07-14** (`static/stage8.js` +
`server.py`'s `/api/aggregate/*` block; see `STAGE8_AGGREGATE_DESIGN.md` §0a). Its algorithm had been live
inline inside gate@7's endpoint since early July — `stage8_aggregate/aggregate.py`
(`district_bands_from_facts`, `merge_fact_runs` for REQ-122's cumulative-facts fix, and
`detect_single_school_over_extraction` for #237's cross-LEA contamination flag) — and the standalone gate@8
was then built around it: the review queue, per-school override, the four human-judgment tables
(`band_exclusion`/`human_added_fact`/`slot_assignment` + `gate_mode`), the approve/send-back verdict with a
frozen fingerprinted receipt, and the gate@8 calibration hook. Still unbuilt downstream: the Stage-9 write
(#93) and the 8→1/8→6 back-edges.

User stories this would satisfy:
- See, across the nine stages, what just happened and what needs human attention — which
  districts/batches are awaiting a gate, what's flagged (an attention-queue query over `state_event`
  current-state — governance §7b "home view").
- See percentage yields and fallout from the chained stages 1–5, by batch (the measurement-harness/funnel
  pattern surfaced per batch — governance §11f).

### 2b. Confidence-escalating auto, beyond gate@5 (tracked: #104 part b)
§1a's toggle is built and gate@5 has a real control law behind it (§1b). The remaining work is per-gate:
gate@1/6/7/8 each need their OWN calibrated auto path (governance §11b: **confidence-escalating** —
auto-accept high confidence, auto-escalate/flag low confidence) before their toggle means anything beyond
persisted intent. This is explicitly gated on the calibration log (§1, above) accruing enough decisions per
gate to certify a threshold (rule of three — see `PIPELINE_GOVERNANCE_AND_STATE.md` §11b). The ordering
constraint that gate@8 must EXIST before gates 6/7 relax is now satisfied — gate@8 shipped (#89), and its
calibration hook logs from day one, so the decisions needed to certify its own threshold are already
accruing. (The runtime-guardrail epic that framed this, #209, is CLOSED.)

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
- **2026-07-12 — Settings (§1a) + gate@5's exploration-audit quota (§1b) shipped** (#104 part a, #211).
  Moved from §2 (planned) to §1 (built). A PR #248 review round found and fixed three real defects in the
  first cut: the license-write inheritance clobber (`configured_mode` is now nullable), an un-isolated
  demote-hook transaction (now SAVEPOINT-wrapped), and a double-computing status endpoint (now one draw).
  Landing required a second corrective PR (#250) after the original PR merged into a stale feature branch
  instead of `main` — see `PIPELINE_GOVERNANCE_AND_STATE.md` §11b and `docs/PROJECT_HISTORY.md`'s
  2026-07-13 entry for the incident.
