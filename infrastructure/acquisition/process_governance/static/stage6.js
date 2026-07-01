"use strict";
// Stage 6 (Dispatch) console view — REQ-101, gate@6. Build a dispatch package from Stage-5 release
// decisions, review the per-representation routing (which council) + the estimated cost, then
// APPROVE & FREEZE (gate@6): writes the immutable handoff_<hash>.json + records the dispatch
// (the precious index row + per-district `dispatched` state_events). Stops at the seam — NO paid
// Stage-7 calls. Vanilla JS on the MMM tokens; reuses the q-*/badge/btn styles + a few s6-* rules.
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const esc = (s) => (s == null ? "" : String(s)).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  const usd = (n) => "$" + (Number(n) || 0).toFixed(5);
  const fmt = (iso) => (iso || "").replace("T", " ").replace("Z", " UTC");
  const postJSON = (b) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
  let inited = false;
  const SELECTED = new Set();

  async function api(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(`${r.status} — ${m}`); }
    return r.json();
  }

  window.initStage6 = function () {
    if (!inited) { inited = true; renderShell(); }
    loadCandidates();
    loadHandoffs();
  };

  function renderShell() {
    $g("#stage6view").innerHTML = `
      <nav class="col col-tree q-left" aria-label="Dispatch candidates">
        <div class="q-left-head"><h3>Dispatch</h3><button id="s6-preview" class="btn btn-secondary">Preview →</button></div>
        <div id="s6-list" class="q-list"><div class="empty">Loading…</div></div>
        <div class="q-left-head"><h3>Recent dispatches</h3></div>
        <div id="s6-handoffs" class="q-list"><div class="empty">—</div></div>
      </nav>
      <section id="s6-detail" class="col col-center"><div class="empty">Select districts on the left, then <b>Preview</b> to build a dispatch package.</div></section>`;
    $g("#s6-preview").onclick = preview;
  }

  // ----------------------------- candidates -----------------------------
  async function loadCandidates() {
    const list = $g("#s6-list");
    let cands;
    try { cands = await api("/api/handoff/candidates"); }
    catch (e) { list.innerHTML = `<div class="empty err">Couldn't load candidates: ${esc(e.message)}<br/>Is Docker (governance DB) up?</div>`; return; }
    if (!cands.length) { list.innerHTML = `<div class="empty">No Stage-5 districts yet.</div>`; return; }
    list.innerHTML = "";
    cands.forEach((c) => {
      const el = document.createElement("label");
      el.className = "q-batch s6-cand";
      const tone = c.n_send > 0 ? "badge-success" : "badge-neutral";
      el.innerHTML = `<div class="s6-cand-top">
          <input type="checkbox" data-id="${esc(c.district_id)}" ${SELECTED.has(c.district_id) ? "checked" : ""}/>
          <span class="q-batch-id">${esc(c.name || c.district_id)}</span>
          <span class="badge ${tone}" title="canonical records that will be sent — labeled targets + unlabeled tier-A (preview shows exact reps + cost)">${c.n_send} send</span></div>
        <div class="q-batch-meta">${esc(c.district_id)} · ${esc(c.labeled_topology || "?")}${c.n_hold ? ` · <span title="unlabeled tier-B/C — label them in Stage 5 to dispatch">${c.n_hold} held for label</span>` : ""}</div>`;
      const cb = el.querySelector("input");
      cb.onchange = () => { cb.checked ? SELECTED.add(c.district_id) : SELECTED.delete(c.district_id); };
      list.appendChild(el);
    });
  }

  // ----------------------------- preview the package -----------------------------
  async function preview() {
    const ids = [...SELECTED];
    const det = $g("#s6-detail");
    if (!ids.length) { det.innerHTML = `<div class="empty">Select at least one district on the left.</div>`; return; }
    det.innerHTML = `<div class="empty">Building package…</div>`;
    let pkg;
    try { pkg = await api("/api/handoff/preview", postJSON({ district_ids: ids })); }
    catch (e) { det.innerHTML = `<div class="empty err">Preview failed: ${esc(e.message)}</div>`; return; }
    renderPackage(pkg, ids);
  }

  function renderPackage(pkg, ids) {
    const det = $g("#s6-detail");
    const blocks = pkg.districts.map((d) => {
      const sends = d.records.filter((r) => r.decision === "send");
      const reps = sends.flatMap((r) => r.reps.map((rep) =>
        `<div class="s6-rep"><span class="s6-kind">${esc(rep.kind)}</span>
           <code>${esc(rep.file)}</code> → <b>${rep.councils.map(esc).join(", ")}</b>
           ${rep.fidelity_suspect ? `<span class="badge badge-warn">fidelity-suspect</span>` : ""}
           <span class="s6-usd">${usd(rep.est_usd)}</span></div>`));
      return `<div class="s6-dist">
          <h4>${esc(d.district_id)} <span class="muted">${d.n_send_reps} rep(s) · ${usd(d.est_usd)}</span></h4>
          ${reps.length ? reps.join("") : `<div class="s6-rep muted">no send-eligible records</div>`}
        </div>`;
    });
    det.innerHTML = `
      <div class="s6-summary">
        <h3>Dispatch preview</h3>
        <p><b>${pkg.cost.n_reps}</b> representation(s) across <b>${pkg.districts.length}</b> district(s) ·
           estimated <b>${usd(pkg.cost.total_usd)}</b> <span class="badge badge-neutral">${esc(pkg.cost.provenance)}</span></p>
        <button id="s6-dispatch" class="btn btn-primary"${pkg.cost.n_reps ? "" : " disabled"}>Approve &amp; freeze dispatch (gate@6)</button>
        <p class="muted s6-note">Freezes the immutable dispatch record + records it. <b>No paid extraction</b> — that's Stage&nbsp;7.</p>
      </div>
      ${blocks.join("")}`;
    const btn = $g("#s6-dispatch");
    if (btn) btn.onclick = () => dispatch(ids, btn);
  }

  // ----------------------------- gate@6 approve -> freeze + record -----------------------------
  async function dispatch(ids, btn) {
    btn.disabled = true; btn.textContent = "Freezing…";
    let res;
    try { res = await api("/api/handoff/dispatch", postJSON({ district_ids: ids, actor: "ian" })); }
    catch (e) { btn.disabled = false; btn.textContent = "Approve & freeze dispatch (gate@6)"; alert("Dispatch failed: " + e.message); return; }
    $g("#s6-detail").innerHTML = `<div class="s6-summary">
        <h3>✓ Dispatch frozen &amp; recorded</h3>
        <p><code>${esc(res.handoff_id)}</code></p>
        <p><b>${res.n_reps}</b> rep(s) · ${res.n_districts} district(s) · ${usd(res.total_usd)}
           <span class="badge badge-neutral">${esc(res.provenance)}</span></p>
        <p class="muted">${esc(res.path)}</p>
        <p class="muted s6-note">Recorded as <b>dispatched</b>. The paid council extraction is Stage&nbsp;7 (out of scope here).</p>
      </div>`;
    SELECTED.clear();
    loadCandidates();
    loadHandoffs();
  }

  // ----------------------------- dispatches index -----------------------------
  async function loadHandoffs() {
    const el = $g("#s6-handoffs");
    let hs;
    try { hs = await api("/api/handoffs"); }
    catch (_) { el.innerHTML = `<div class="empty">—</div>`; return; }
    if (!hs.length) { el.innerHTML = `<div class="empty">None dispatched yet.</div>`; return; }
    el.innerHTML = "";
    hs.forEach((h) => {
      const row = document.createElement("div");
      row.className = "q-batch s6-handoff";
      row.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(h.handoff_id.slice(0, 24))}…</span>
          <span class="badge badge-success">${esc(h.status)}</span></div>
        <div class="q-batch-meta">${h.n_districts}d · ${h.n_reps}r · ${usd(h.total_usd)} ${esc(h.cost_provenance)} · ${esc(fmt(h.created_at))}</div>`;
      el.appendChild(row);
    });
  }
})();
