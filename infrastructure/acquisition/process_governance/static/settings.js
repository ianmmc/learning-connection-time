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
    loadModes();
    loadExplorationAudit();
  };

  function renderShell() {
    $g("#settingsview").innerHTML = `
      <section class="col col-center settings-panel">
        <h2>Gate automation <span class="muted">(ramp-up control surface)</span></h2>
        <p class="muted">Every gate starts <strong>manual</strong> (high supervision); set one
          <strong>auto</strong> only once its confidence has been earned. A gate with no override inherits
          the global default. Setting a gate here persists the decision — it does not change a gate's
          behavior until that gate's auto path is built.</p>
        <div id="settings-rows" class="settings-rows"><div class="empty">Loading…</div></div>
        <h2 class="settings-audit-h">gate@5 reject audit <span class="muted">(anti-survivorship license)</span></h2>
        <p class="muted">gate@5 auto stays licensed only while a rolling window holds ≥ N randomly-drawn,
          human-labeled rejects (the tier-D bucket auto would drop). Below the floor the license
          <strong>demotes to manual</strong> (census mode) — it never halts the pipeline. Today the audit is
          <strong>informational</strong>: gate@5 is manual (census-labeling), so the control law is inert.</p>
        <div id="settings-audit" class="settings-audit"><div class="empty">Loading…</div></div>
      </section>`;
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
