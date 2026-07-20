"use strict";
// Settings console view — per-gate manual/auto mode (REQ-108, #104). The ramp-up model's control
// surface: a global default + per-gate overrides (gate@1/5/6/7/8, plus a forward-looking gate@8). Every
// gate defaults MANUAL (high-supervision-first); flipping one to AUTO is the deliberate ramp-up decision.
// This panel PERSISTS the toggle (POST /api/gate-mode, git-backed) — it does NOT itself change any gate's
// runtime behavior (each gate stays manual until its own auto path is built, e.g. #211 for gate@5).
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const { esc, postJSON, api } = window.LCT;
  let inited = false;

  // Display order + labels. 'default' is the global default; the rest are the stage-numbered gates.
  const GATES = [
    ["default", "Global default"],
    ["gate@1", "gate@1 · Queue"],
    ["gate@5", "gate@5 · Capture Review"],
    ["gate@6", "gate@6 · Dispatch"],
    ["gate@7", "gate@7 · Extract"],
    ["gate@8", "gate@8 · Aggregate"],
  ];

  window.initSettings = function () {
    if (!inited) { inited = true; renderShell(); }
    loadDataYears();
    loadModes();
    loadDiscoveryPolicy();
    loadModeStability();
    loadExplorationAudit();
    loadExclusions();
  };

  function renderShell() {
    // Two-pane shape (Ian, 2026-07-14): the left pane is a settings-GROUP nav. Two groups today:
    // General Settings and Exclusions (#229 UX rework — the standing excluded corpus reads here,
    // not as a wall of names inline in every gate@1 batch view).
    $g("#settingsview").innerHTML = `
      <nav class="col settings-nav" aria-label="Settings groups">
        <div class="settings-nav-item active" data-group="general">General Settings</div>
        <div class="settings-nav-item" data-group="exclusions" data-feat="exclusions-nav">Exclusions</div>
      </nav>
      <section class="col col-center settings-panel" data-group-panel="general">
        <h2>Data years <span class="muted">(derived — nothing here is hand-bumped except the NCES vintage)</span></h2>
        <div id="settings-years" class="settings-years"><div class="empty">Loading…</div></div>
        <h2 class="settings-audit-h">Gate automation <span class="muted">(ramp-up control surface)</span></h2>
        <p class="muted">Every gate starts <strong>manual</strong> (high supervision); set one
          <strong>auto</strong> only once its confidence has been earned. A gate with no override inherits
          the global default. Setting a gate here persists the decision — it does not change a gate's
          behavior until that gate's auto path is built.</p>
        <div id="settings-rows" class="settings-rows"><div class="empty">Loading…</div></div>
        <h2 class="settings-audit-h">Discovery scope policy <span class="muted">(#164 — geo first-run composition)</span></h2>
        <p class="muted">Governs FIRST-RUN batch composition only — the failure-driven escalation
          loops (5→1 / 7→1) are always available and individually gate@1'd. Every change is an
          append-only, git-twinned audit event; the pool-drained moment auto-advances
          <strong>domain_only → geo_for_blank</strong> exactly one step. Compose a geo batch from
          Stage 1 · Queue → <strong>+ Create batch</strong> once a geo position is set.</p>
        <div id="settings-discovery-policy" class="settings-rows" data-feat="discovery-policy-card"><div class="empty">Loading…</div></div>
        <h2 class="settings-audit-h">Stage 7 mode-stability early-exit <span class="muted">(#120 — spend shortcut)</span></h2>
        <p class="muted">Stage 7 stops paying for a district's remaining reps once every fillable band's
          running mode is stable; skipped reps are recorded and visible at gate@7, and stay dispatchable
          (7→6). This switch is the operational <strong>kill-switch</strong> only — the numeric
          parameters are config-as-data (<code>stage7_mode_stability.json</code>), changed by PR, never here.</p>
        <div id="settings-modestab" class="settings-rows"><div class="empty">Loading…</div></div>
        <h2 class="settings-audit-h">gate@5 reject audit <span class="muted">(anti-survivorship license)</span></h2>
        <p class="muted">gate@5 auto stays licensed only while a rolling window holds ≥ N randomly-drawn,
          human-labeled rejects (the tier-D bucket auto would drop). Below the floor the license
          <strong>demotes to manual</strong> (census mode) — it never halts the pipeline. Today the audit is
          <strong>informational</strong>: gate@5 is manual (census-labeling), so the control law is inert.</p>
        <div id="settings-audit" class="settings-audit"><div class="empty">Loading…</div></div>
      </section>
      <section class="col col-center settings-panel hidden" data-group-panel="exclusions">
        <h2>Exclusions <span class="muted">(the standing pre-queue refusals — derived live from NCES)</span></h2>
        <p class="muted">Districts and schools every batch draw excludes by rule. The per-batch refusal
          receipt still renders (collapsed) on each batch at gate@1; this is the corpus-wide view, so a
          new batch never needs scrolling a wall of names to understand what was refused.</p>
        <div id="settings-exclusions" class="settings-years"><div class="empty">Loading…</div></div>
      </section>`;
    // Group switching: the nav is the one source of which panel shows (grows by adding a nav item
    // + a matching data-group-panel section — no layout rework per group).
    $g("#settingsview").querySelectorAll(".settings-nav-item").forEach((it) =>
      it.addEventListener("click", () => {
        $g("#settingsview").querySelectorAll(".settings-nav-item").forEach((e) =>
          e.classList.toggle("active", e === it));
        $g("#settingsview").querySelectorAll("[data-group-panel]").forEach((p) =>
          p.classList.toggle("hidden", p.dataset.groupPanel !== it.dataset.group));
      }));
  }

  // Settings → Exclusions (#229 UX rework): the standing excluded corpus + the rules, read-only.
  async function loadExclusions() {
    const box = $g("#settings-exclusions");
    if (!box) return;
    try {
      const d = await api("/api/exclusions");
      if (!d.available) {
        box.innerHTML = `<div class="empty">Live corpus unavailable — ${esc(d.reason || "NCES files not on disk")}.</div>`;
        return;
      }
      const nd = d.no_domain || {}, gg = d.grade_span_gap || {};
      const states = Object.entries(nd.by_state || {}).sort((a, b) => b[1] - a[1]);
      box.innerHTML = `
        <div class="audit-grid">
          <div class="audit-stat"><span class="audit-k">No usable NCES domain (#229)</span>
            <span class="audit-v">${nd.count} district${nd.count === 1 ? "" : "s"} <span class="muted">(would run unscoped discovery — hard refusal)</span></span></div>
          <div class="audit-stat"><span class="audit-k">Grade-span integrity gap</span>
            <span class="audit-v">${gg.count} district${gg.count === 1 ? "" : "s"} <span class="muted">(a claimed band with no NCES school to fill it)</span></span></div>
          <div class="audit-stat"><span class="audit-k">NCES vintage</span>
            <span class="audit-v">${esc(d.nces_year)} <span class="muted">(live derivation)</span></span></div>
        </div>
        <p class="muted" data-feat="exclusions-criteria">School-level criteria: ${esc(d.school_criteria)}</p>
        <details data-feat="exclusions-no-domain"><summary><strong>No-domain districts by state</strong> — ${states.map(([s, n]) => `${esc(s)} ${n}`).join(" · ")}</summary>
          <ul class="audit-list">${(nd.districts || []).map((e) =>
            `<li>${esc(e.name)} <span class="muted">[${esc(e.state)}] ${esc(e.district_id)} · website=${esc(JSON.stringify(e.website))}</span></li>`).join("")}</ul>
        </details>
        <details data-feat="exclusions-gap"><summary><strong>Grade-span-gap districts</strong> (${gg.count})</summary>
          <ul class="audit-list">${(gg.districts || []).map((e) =>
            `<li>${esc(e.name)} <span class="muted">[${esc(e.state)}] ${esc(e.district_id)} · gap: ${(e.gap_bands || []).map(esc).join(", ")}</span></li>`).join("")}</ul>
        </details>`;
    } catch (_) {
      box.innerHTML = `<div class="empty">Failed to load the exclusions corpus.</div>`;
    }
  }

  // Data-year facts (/api/data-years): the derived current school year + the NCES CCD vintage.
  // Read-only display — the current year rolls itself over each July 1 (utilities/school_year.py);
  // seeing it here is the check that it did.
  async function loadDataYears() {
    const box = $g("#settings-years");
    if (!box) return;
    try {
      const d = await api("/api/data-years");
      box.innerHTML = `
        <div class="audit-grid">
          <div class="audit-stat"><span class="audit-k">Current school year</span>
            <span class="audit-v">${esc(d.current_school_year)} <span class="muted">(derived, July-1 rollover)</span></span></div>
          <div class="audit-stat"><span class="audit-k">NCES primary dataset</span>
            <span class="audit-v">${esc(d.nces_primary_year)} <span class="muted">(CCD enrollment/staffing — bumped on ingest)</span></span></div>
          <div class="audit-stat"><span class="audit-k">Acceptable bell years</span>
            <span class="audit-v">${(d.acceptable_bell_years || []).map(esc).join(" · ")}</span></div>
        </div>`;
    } catch (_) {
      box.innerHTML = `<div class="empty">Failed to load data-year facts.</div>`;
    }
  }

  // #572: the discovery scope policy control (#164) — position buttons + the audited event history.
  async function loadDiscoveryPolicy() {
    const box = $g("#settings-discovery-policy");
    if (!box) return;
    try {
      const d = await api("/api/discovery-policy");
      const rows = (d.positions || []).map((p) => `
        <div class="settings-row${p.policy === d.policy ? " settings-row-default" : ""}">
          <div class="settings-gate"><strong>${esc(p.label)}</strong> <span class="muted">(${esc(p.policy)})</span><br/>
            <span class="muted">${esc(p.desc)}</span></div>
          <div class="settings-toggle">
            ${p.policy === d.policy
              ? `<span class="badge badge-lavender" data-feat="discovery-policy-current">current</span>`
              : `<button class="btn btn-mini" data-feat="discovery-policy-set" data-policy="${esc(p.policy)}">Set</button>`}
          </div>
        </div>`).join("");
      const hist = (d.events || []).length
        ? `<details class="q-domain-excluded" data-feat="discovery-policy-history">
             <summary class="muted">Policy event history (${d.events.length} recent — append-only audit log)</summary>
             ${d.events.map((e) => `<div class="muted">${esc(e.created_at)} · ${esc(e.previous)} → <b>${esc(e.policy)}</b> · ${esc(e.actor)}${e.trigger ? ` · ${esc(e.trigger)}` : ""}</div>`).join("")}
           </details>`
        : `<p class="muted">No policy changes yet — the empty log reads as <b>domain_only</b> (the high-supervision default).</p>`;
      box.innerHTML = rows + hist;
      box.querySelectorAll('[data-feat="discovery-policy-set"]').forEach((b) => b.onclick = async () => {
        if (!confirm(`Set discovery_scope_policy → ${b.dataset.policy}?\n\nThis is an audited governance event (append-only, git-twinned). It governs first-run composition only.`)) return;
        try { await api("/api/discovery-policy", postJSON({ policy: b.dataset.policy, actor: "ian" })); }
        catch (e) { alert("Set failed: " + e.message); return; }
        loadDiscoveryPolicy();
      });
    } catch (_) {
      box.innerHTML = `<div class="empty">Failed to load the discovery scope policy.</div>`;
    }
  }

  // #120: the mode-stability early-exit — params read-only, `enabled` is the one flippable field.
  async function loadModeStability() {
    const box = $g("#settings-modestab");
    if (!box) return;
    try {
      const d = await api("/api/stage7/mode-stability");
      const p = d.params || {};
      const prov = d.toggled_by ? `<span class="muted">last toggled by ${esc(d.toggled_by)}${d.toggled_at ? " · " + esc(d.toggled_at) : ""}</span>` : "";
      box.innerHTML = `
        <div class="audit-grid">
          <div class="audit-stat"><span class="audit-k">Early-exit</span>
            <span class="audit-v"><strong>${p.enabled ? "ON" : "OFF"}</strong>
              <button class="btn ${p.enabled ? "btn-ghost" : "btn-secondary"} btn-mini" data-feat="mode-stability-toggle">${p.enabled ? "Turn off" : "Turn on"}</button> ${prov}</span></div>
          <div class="audit-stat"><span class="audit-k">Parameters (read-only)</span>
            <span class="audit-v">window=${p.window} · min_n=${p.min_n} · min_share=${p.min_share} <span class="muted">(config-as-data — change by PR)</span></span></div>
        </div>`;
      box.querySelector('[data-feat="mode-stability-toggle"]').onclick = async () => {
        try { await api("/api/stage7/mode-stability", postJSON({ enabled: !p.enabled, actor: "ian" })); }
        catch (e) { alert("Toggle failed: " + e.message); return; }
        loadModeStability();
      };
    } catch (_) {
      box.innerHTML = `<div class="empty">Failed to load the mode-stability knob.</div>`;
    }
  }

  async function loadModes() {
    const box = $g("#settings-rows");
    try {
      const data = await api("/api/gate-mode");
      const s = data.settings || {};
      box.innerHTML = "";
      GATES.forEach(([gate, label]) => {
        const row = s[gate] || { configured_mode: "manual", is_override: false, license_state: null };
        box.appendChild(rowEl(gate, label, row, gate === "default"));
      });
    } catch (_) {
      box.innerHTML = `<div class="empty">Failed to load gate settings.</div>`;
    }
  }

  function rowEl(gate, label, row, isDefault) {
    const el = document.createElement("div");
    el.className = "settings-row" + (isDefault ? " settings-row-default" : "");
    el.dataset.gate = gate;
    const inherited = !isDefault && !row.is_override;
    // The license badge shows ONLY while the gate is configured auto (PR #248 review): demoting a gate
    // back to manual doesn't clear the stored license_state (by design — it's the deadband memory), so
    // an ungated badge kept advertising "live license: auto" beside an active Manual toggle. Inert
    // state must not render as live (the ramp-up posture: never present more autonomy than is in force).
    const lic = row.license_state && row.configured_mode === "auto"
      ? ` <span class="muted settings-lic">live license: ${esc(row.license_state)}</span>` : "";
    el.innerHTML = `
      <div class="settings-gate">${esc(label)}${inherited ? ' <span class="muted">(inherits default)</span>' : ""}${lic}</div>
      <div class="settings-toggle" role="group" aria-label="${esc(label)} mode">
        <button class="btn btn-mini toggle-manual${row.configured_mode === "manual" ? " active" : ""}"
                data-gate="${esc(gate)}" data-mode="manual">Manual</button>
        <button class="btn btn-mini toggle-auto${row.configured_mode === "auto" ? " active" : ""}"
                data-gate="${esc(gate)}" data-mode="auto">Auto</button>
      </div>`;
    el.querySelectorAll("button[data-mode]").forEach((b) =>
      b.addEventListener("click", () => setMode(b.dataset.gate, b.dataset.mode)));
    return el;
  }

  async function setMode(gate, mode) {
    try {
      await api("/api/gate-mode", postJSON({ gate, mode, actor: "ian" }));
      loadModes();   // re-render: an inherited gate must reflect a changed global default immediately
      loadExplorationAudit();   // gate@5's license readout tracks its configured toggle
    } catch (_) { /* leave the UI unchanged on failure */ }
  }

  // Scheme allow-list for DB-sourced URLs rendered into href (PR #248 review) — now the SHARED
  // window.LCT.safeUrl (promoted in the PR #252 review round, after stage8.js reintroduced the exact
  // javascript:-URI bug this used to fix locally). One home, like esc() itself.
  const safeUrl = window.LCT.safeUrl;

  // gate@5 reject-audit coverage meter (#211/REQ-120). Read-only status of the anti-survivorship license:
  // window coverage vs the rule-of-three floor, the reject-cohort quality, and the pending randomized draw.
  async function loadExplorationAudit() {
    const box = $g("#settings-audit");
    if (!box) return;
    try {
      const d = await api("/api/exploration-audit");
      const q = d.quality || {};
      const pct = d.floor_n ? Math.min(100, Math.round((d.window_count / d.floor_n) * 100)) : 0;
      const met = d.window_count >= d.floor_n;
      const qualityTxt = q.rejection_quality == null
        ? "—" : `${(q.rejection_quality * 100).toFixed(2)}%`;
      const bound = q.fnr_upper_bound_95 == null
        ? "" : ` <span class="muted">(FN-rate &lt; ${(q.fnr_upper_bound_95 * 100).toFixed(2)}% @95%)</span>`;
      const pend = d.pending || [];
      box.innerHTML = `
        <div class="audit-grid">
          <div class="audit-stat"><span class="audit-k">Effective mode</span>
            <span class="audit-v">${esc(d.effective_mode)} <span class="muted">(configured ${esc(d.configured_mode)})</span></span></div>
          <div class="audit-stat"><span class="audit-k">Reject bucket (tier D)</span>
            <span class="audit-v">${d.population_size} records · ${d.sample_size} sampled (${(d.sample_rate * 100).toFixed(0)}%)</span></div>
          <div class="audit-stat"><span class="audit-k">Reject-cohort quality</span>
            <span class="audit-v">${qualityTxt}${bound}</span></div>
        </div>
        <div class="audit-cov">
          <div class="audit-cov-label">Window coverage <strong>${d.window_count} / ${d.floor_n}</strong>
            ${met ? '<span class="audit-ok">✓ floor met</span>' : `<span class="muted">re-promote at ${d.promote_n}</span>`}</div>
          <div class="audit-bar"><div class="audit-bar-fill${met ? " met" : ""}" style="width:${pct}%"></div></div>
        </div>
        <div class="audit-pending">
          <div class="audit-cov-label">Pending audit draw <span class="muted">(${d.n_pending} unlabeled — the queue to work top-down)</span></div>
          ${pend.length === 0
            ? '<div class="empty">No pending draws — the sampled rejects are all labeled.</div>'
            : `<ul class="audit-list">${pend.slice(0, 25).map((r) =>
                `<li><code>${esc(r.rec_key)}</code>${safeUrl(r.url) ? ` <a href="${esc(r.url)}" target="_blank" rel="noopener" class="muted">${esc(r.url)}</a>` : (r.url ? ` <span class="muted">${esc(r.url)}</span>` : "")}</li>`).join("")}</ul>`}
        </div>`;
    } catch (_) {
      box.innerHTML = `<div class="empty">Failed to load reject-audit status.</div>`;
    }
  }
})();
