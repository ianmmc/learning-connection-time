"use strict";
// Stage 7 (Extract) console view — REQ-117, gate@7. Review the council-extraction RESULTS per district
// (computed band rollup + accepted/unresolved per-school facts) and the deterministic
// request-more-evidence directives (7->6/3/2/1), approving/rejecting each under the ramp-up model
// (governance §11b). Read + the request accept/reject action; extraction fact/band review is Stage 8
// (gate@8). Vanilla JS on the MMM tokens; reuses q-*/badge/btn styles + a few s7-* rules.
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const esc = (s) => (s == null ? "" : String(s)).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  const usd = (n) => "$" + (Number(n) || 0).toFixed(4);
  const postJSON = (b) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
  let inited = false, CURRENT = null;

  async function api(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(`${r.status} — ${m}`); }
    return r.json();
  }

  window.initStage7 = function () {
    if (!inited) { inited = true; renderShell(); }
    loadDistricts();                                     // re-fetch on every show (badges reflect reviews)
  };

  function renderShell() {
    $g("#stage7view").innerHTML = `
      <nav class="col col-tree q-left" aria-label="Extracted districts">
        <div class="q-left-head"><h3>Extractions · gate@7</h3></div>
        <div id="s7-list" class="q-list"><div class="empty">Loading…</div></div>
      </nav>
      <section id="s7-detail" class="col col-center"><div class="empty">Select a district to review its extraction &amp; requests.</div></section>`;
  }

  // ----------------------------- left pane: districts -----------------------------
  async function loadDistricts() {
    const list = $g("#s7-list");
    let ds;
    try { ds = await api("/api/extract/districts"); }
    catch (e) { list.innerHTML = `<div class="empty err">Couldn't load: ${esc(e.message)}<br/>Is Docker (governance DB) up, and any Stage-7 run persisted?</div>`; return; }
    if (!ds.length) { list.innerHTML = `<div class="empty">No extractions yet — run Stage 7 with <code>--persist</code>.</div>`; return; }
    list.innerHTML = "";
    ds.forEach((d) => list.appendChild(districtRow(d)));
  }

  function districtRow(d) {
    const el = document.createElement("div");
    el.className = "q-batch" + (d.district_id === CURRENT ? " active" : "");
    el.dataset.id = d.district_id;
    const pend = d.n_pending > 0 ? `<span class="badge badge-warn">${d.n_pending} req</span>` : "";
    el.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(d.name || d.district_id)}</span>${pend}</div>
      <div class="q-batch-meta">${esc(d.district_id)}${d.state ? " · " + esc(d.state) : ""} · ${d.n_accepted} school${d.n_accepted === 1 ? "" : "s"} · ${d.n_unresolved} unres · ${usd(d.cost_usd)}</div>`;
    el.onclick = () => openDistrict(d.district_id);
    return el;
  }

  // ----------------------------- detail -----------------------------
  async function openDistrict(did) {
    CURRENT = did;
    document.querySelectorAll("#s7-list .q-batch").forEach((e) => e.classList.toggle("active", e.dataset.id === did));
    const det = $g("#s7-detail");
    det.innerHTML = `<div class="empty">Loading ${esc(did)}…</div>`;
    let x;
    try { x = await api(`/api/extract/district/${did}`); }
    catch (e) { det.innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
    det.innerHTML = renderDetail(x);
    det.querySelectorAll("[data-review]").forEach((btn) => {
      btn.onclick = () => reviewRequest(Number(btn.dataset.id), btn.dataset.review, did);
    });
    det.querySelectorAll("[data-execute]").forEach((btn) => {
      btn.onclick = () => executeRequest(Number(btn.dataset.execute), did);
    });
    det.querySelectorAll("[data-compose]").forEach((btn) => {
      btn.onclick = () => composeFollowup(btn.dataset.compose, did);
    });
  }

  function bandTable(bands) {
    const rows = ["elementary", "middle", "high"].filter((b) => bands[b]).map((b) => {
      const v = bands[b];
      return `<tr><td>${b}</td><td><b>${v.gross_minutes}</b> min</td><td>${esc(v.start_time)}–${esc(v.end_time)}</td><td class="muted">n=${v.n_schools}</td><td class="muted">${esc(v.method)}</td></tr>`;
    }).join("");
    return rows ? `<table class="s7-tbl"><thead><tr><th>band</th><th>daily minutes</th><th>window</th><th></th><th>method</th></tr></thead><tbody>${rows}</tbody></table>`
                : `<div class="empty">No band resolved.</div>`;
  }

  // Routes needing NEW capture/discovery are wrapped in a Stage-1 follow-up batch (a SWEEP action, not
  // per-card); 7->6 re-routes an EXISTING rep, so it executes on its own. (REQ-118; mirrors §3F.)
  const isNewWork = (route) => route === "7->2" || route === "7->3" || route === "7->1";

  function requestCard(r) {
    const badge = r.status === "approved" ? `<span class="badge badge-success">approved</span>`
                : r.status === "rejected" ? `<span class="badge badge-neutral">rejected</span>`
                : r.status === "executed" ? `<span class="badge badge-accent">executed</span>`
                : `<span class="badge badge-warn">pending</span>`;
    let actions;
    if (r.status === "pending") {
      actions = `<button class="btn btn-secondary btn-mini" data-review="approved" data-id="${r.request_id}">Approve</button>
         <button class="btn btn-ghost btn-mini" data-review="rejected" data-id="${r.request_id}">Reject</button>`;
    } else if (r.status === "approved" && r.route === "7->6") {
      // existing-rep re-dispatch — a single-directive action, fires a new Stage-6 dispatch
      actions = `<button class="btn btn-primary btn-mini" data-execute="${r.request_id}">Execute re-dispatch</button>
         <button class="btn btn-ghost btn-mini" data-review="pending" data-id="${r.request_id}">Reopen</button>`;
    } else if (r.status === "approved" && isNewWork(r.route)) {
      actions = `<span class="muted s7-hint">→ queued for a follow-up batch (use “Compose follow-up batch”)</span>
         <button class="btn btn-ghost btn-mini" data-review="pending" data-id="${r.request_id}">Reopen</button>`;
    } else if (r.status === "executed") {
      actions = r.executed_ref ? `<span class="muted s7-hint">→ ${esc(r.executed_ref)}</span>` : "";
    } else {
      actions = `<button class="btn btn-ghost btn-mini" data-review="pending" data-id="${r.request_id}">Reopen</button>`;
    }
    const rev = r.reviewed_by ? `<div class="s7-rev muted">${esc(r.status)} by ${esc(r.reviewed_by)}${r.reviewed_at ? " · " + esc(r.reviewed_at) : ""}</div>` : "";
    return `<div class="s7-req">
      <div class="s7-req-top"><span class="s7-route">${esc(r.route)}</span> <span class="muted">${esc(r.altitude)}${r.band ? " · " + esc(r.band) : ""}</span> ${badge}</div>
      <div class="s7-req-reason">${esc(r.reason)}</div>
      <div class="btn-row">${actions}</div>${rev}</div>`;
  }

  function factRows(facts) {
    return facts.map((f) => `<tr><td>${esc(f.band)}</td><td>${esc(f.school)}</td><td>${esc(f.start_time)}–${esc(f.end_time)}</td><td>${f.gross_minutes} min</td><td class="muted">${esc(f.method)}</td></tr>`).join("");
  }

  function renderDetail(x) {
    const e = x.extraction, reqs = x.requests || [];
    const pending = reqs.filter((r) => r.status === "pending").length;
    // a "Compose follow-up batch" sweep is offered when ≥1 approved NEW-work (7->2/3/1) directive awaits
    const approvedNewWork = reqs.filter((r) => r.status === "approved" && isNewWork(r.route)).length;
    const composeBtn = approvedNewWork
      ? `<button class="btn btn-primary btn-mini" data-compose="${esc(e.handoff_hash || "")}">Compose follow-up batch (${approvedNewWork} approved)</button>`
      : "";
    const reqSection = reqs.length
      ? `<h4>Request more evidence <span class="muted">(${pending} pending / ${reqs.length})</span> ${composeBtn}</h4>${reqs.map(requestCard).join("")}`
      : `<h4>Request more evidence</h4><div class="empty">None — all claimed bands covered, no barren reps.</div>`;
    const acc = x.accepted || [], unres = x.unresolved || [];
    return `
      <div class="s7-head">
        <h3>${esc(e.district_id)}</h3>
        <div class="muted">${acc.length} accepted · ${unres.length} unresolved · ${usd(e.cost_usd)} · ${e.n_reps} rep${e.n_reps === 1 ? "" : "s"} · run ${esc(e.created_at)}</div>
      </div>
      <h4>Band rollup <span class="muted">(computed — Stage 8 owns the authoritative value)</span></h4>
      ${bandTable(x.bands || {})}
      ${reqSection}
      <h4>Accepted schools <span class="muted">(${acc.length})</span></h4>
      <table class="s7-tbl"><thead><tr><th>band</th><th>school</th><th>window</th><th>gross</th><th>method</th></tr></thead><tbody>${factRows(acc) || `<tr><td colspan="5" class="muted">none</td></tr>`}</tbody></table>
      ${unres.length ? `<h4>Unresolved <span class="muted">(${unres.length} — held out, not counted)</span></h4>
        <div class="s7-unres">${unres.map((u) => `<span class="s7-chip">${esc(u.band)}/${esc(u.school)}</span>`).join("")}</div>` : ""}`;
  }

  async function reviewRequest(id, status, did) {
    try { await api(`/api/extract/request/${id}`, postJSON({ status, actor: "ian" })); }
    catch (e) { alert("Review failed: " + e.message); return; }
    openDistrict(did);          // re-render detail with the new status
    loadDistricts();            // refresh the left-pane pending badge
  }

  // 7->6: fire an approved alternate-rep re-dispatch (a new Stage-6 dispatch; re-enters Stage 7).
  async function executeRequest(id, did) {
    if (!confirm("Re-dispatch the alternate representation? This creates a new Stage-6 dispatch to re-extract (a subsequent, budget-gated Stage-7 run).")) return;
    let out;
    try { out = await api(`/api/extract/execute/${id}`, postJSON({ actor: "ian" })); }
    catch (e) { alert("Execute failed: " + e.message); return; }
    alert(`Re-dispatched ${out.alt_file || "the alternate rep"} → new handoff ${out.handoff_hash}. Run Stage 7 on it to extract (budget-gated).`);
    openDistrict(did);
    loadDistricts();
  }

  // 7->2/7->3/7->1: sweep approved NEW-work directives (this run) into ONE draft follow-up batch.
  async function composeFollowup(handoffHash, did) {
    if (!confirm("Compose a follow-up batch from the approved 7->2/7->3/7->1 directives? It lands as a DRAFT for review at gate@1 (Stage 1).")) return;
    let out;
    try { out = await api(`/api/extract/compose-followup`, postJSON({ handoff_hash: handoffHash || null, actor: "ian" })); }
    catch (e) { alert("Compose failed: " + e.message); return; }
    if (!out.batch_id) { alert("Nothing composed — no approved NEW-work directives."); }
    else {
      let msg = `Draft follow-up ${out.batch_id}: ${out.n_districts} district(s), ${out.n_requests} directive(s) executed. Review at gate@1.`;
      if (out.spilled && out.spilled.length) msg += `\nSpilled ${out.spilled.length} district(s) past the 12-cap (compose again for the next batch).`;
      if (out.blocked && out.blocked.length) msg += `\nBlocked ${out.blocked.length} by the depth guard.`;
      alert(msg);
    }
    openDistrict(did);
    loadDistricts();
  }
})();
