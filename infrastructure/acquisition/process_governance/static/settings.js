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
    const lic = row.license_state
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
    } catch (_) { /* leave the UI unchanged on failure */ }
  }
})();
