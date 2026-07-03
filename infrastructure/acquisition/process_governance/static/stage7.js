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
  }

  function bandTable(bands) {
    const rows = ["elementary", "middle", "high"].filter((b) => bands[b]).map((b) => {
      const v = bands[b];
      return `<tr><td>${b}</td><td><b>${v.gross_minutes}</b> min</td><td>${esc(v.start_time)}–${esc(v.end_time)}</td><td class="muted">n=${v.n_schools}</td><td class="muted">${esc(v.method)}</td></tr>`;
    }).join("");
    return rows ? `<table class="s7-tbl"><thead><tr><th>band</th><th>daily minutes</th><th>window</th><th></th><th>method</th></tr></thead><tbody>${rows}</tbody></table>`
                : `<div class="empty">No band resolved.</div>`;
  }

  function requestCard(r) {
    const badge = r.status === "approved" ? `<span class="badge badge-success">approved</span>`
                : r.status === "rejected" ? `<span class="badge badge-neutral">rejected</span>`
                : `<span class="badge badge-warn">pending</span>`;
    const actions = r.status === "pending"
      ? `<button class="btn btn-secondary btn-mini" data-review="approved" data-id="${r.request_id}">Approve</button>
         <button class="btn btn-ghost btn-mini" data-review="rejected" data-id="${r.request_id}">Reject</button>`
      : `<button class="btn btn-ghost btn-mini" data-review="pending" data-id="${r.request_id}">Reopen</button>`;
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
    const reqSection = reqs.length
      ? `<h4>Request more evidence <span class="muted">(${pending} pending / ${reqs.length})</span></h4>${reqs.map(requestCard).join("")}`
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
})();
