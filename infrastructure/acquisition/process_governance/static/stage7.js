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
    const lin = r.lineage || null;                       // #154: where it went / why it can't
    const blocked = lin && lin.blocked;
    let actions;
    if (blocked) {
      // a depth-exhausted (zombie) 7->6 — never executable; only rejectable/reopenable
      actions = `<button class="btn btn-ghost btn-mini" data-review="rejected" data-id="${r.request_id}">Reject</button>`;
    } else if (r.status === "pending") {
      actions = `<button class="btn btn-secondary btn-mini" data-review="approved" data-id="${r.request_id}">Approve</button>
         <button class="btn btn-ghost btn-mini" data-review="rejected" data-id="${r.request_id}">Reject</button>`;
    } else if (r.status === "approved" && r.route === "7->6") {
      // existing-rep re-dispatch — executes the district's approved 7->6s as ONE bundle (#153)
      actions = `<button class="btn btn-primary btn-mini" data-execute="${r.request_id}">Execute re-dispatch</button>
         <button class="btn btn-ghost btn-mini" data-review="pending" data-id="${r.request_id}">Reopen</button>`;
    } else if (r.status === "approved" && isNewWork(r.route)) {
      actions = `<span class="muted s7-hint">→ queued for a follow-up batch (use “Compose follow-up batch”)</span>
         <button class="btn btn-ghost btn-mini" data-review="pending" data-id="${r.request_id}">Reopen</button>`;
    } else if (r.status === "executed") {
      actions = "";                                      // lineage line below shows where it went
    } else {
      actions = `<button class="btn btn-ghost btn-mini" data-review="pending" data-id="${r.request_id}">Reopen</button>`;
    }
    // lineage line: executed -> its target + live state; blocked/deferred -> why it can't fire
    let lineage = "";
    if (lin && lin.kind === "handoff") {
      lineage = `<div class="s7-lineage muted">→ handoff <code>${esc(lin.ref)}</code> · ${esc(lin.state)}${lin.n_districts ? ` (${lin.n_extracted}/${lin.n_districts})` : ""}</div>`;
    } else if (lin && lin.kind === "batch") {
      lineage = `<div class="s7-lineage muted">→ follow-up <code>${esc(lin.ref)}</code> · ${esc(lin.state)}</div>`;
    } else if (blocked) {
      lineage = `<div class="s7-lineage s7-blocked">⛔ ${esc(lin.reason)}</div>`;
    } else if (lin && lin.deferred) {
      lineage = `<div class="s7-lineage s7-deferred">⏸ ${esc(lin.reason)}</div>`;
    }
    const rev = r.reviewed_by ? `<div class="s7-rev muted">${esc(r.status)} by ${esc(r.reviewed_by)}${r.reviewed_at ? " · " + esc(r.reviewed_at) : ""}</div>` : "";
    return `<div class="s7-req${blocked ? " s7-req-blocked" : ""}">
      <div class="s7-req-top"><span class="s7-route">${esc(r.route)}</span> <span class="muted">${esc(r.altitude)}${r.band ? " · " + esc(r.band) : ""}</span> ${badge}</div>
      <div class="s7-req-reason">${esc(r.reason)}</div>
      ${lineage}
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

  // 7->6: fire the district's approved alternate-rep re-dispatches as ONE BUNDLE (#153: a single
  // new Stage-6 dispatch = one depth-guard round; re-enters Stage 7). The consent copy must say so —
  // clicking Execute on one card executes ALL of this district's approved 7->6s together.
  async function executeRequest(id, did) {
    if (!confirm("Execute this district's approved 7->6 re-dispatches as ONE bundle? All approved alternate-rep directives for this district ride a single new Stage-6 dispatch (= one depth-guard round), re-extracted by a subsequent, budget-gated Stage-7 run.")) return;
    let out;
    try { out = await api(`/api/extract/execute/${id}`, postJSON({ actor: "ian" })); }
    catch (e) { alert("Execute failed: " + e.message); return; }
    const files = (out.alt_files || []).join(", ") || "the alternate rep(s)";
    let msg = `Bundled ${out.n_bundled || 1} re-dispatch(es) (${files}) → new handoff ${out.handoff_hash} = one round. Run Stage 7 on it to extract (budget-gated).`;
    if (out.skipped && out.skipped.length) msg += `\nSkipped ${out.skipped.length} directive(s) with no dispatchable alternate left.`;
    alert(msg);
    openDistrict(did);
    loadDistricts();
  }

  // 7->2/7->3/7->1: PREVIEW the follow-up in a modal (#154), then compose on confirm (cancel = no-op).
  async function composeFollowup(handoffHash, did) {
    let prev;
    try { prev = await api(`/api/extract/compose-followup/preview`, postJSON({ handoff_hash: handoffHash || null, actor: "ian" })); }
    catch (e) { alert("Compose preview failed: " + e.message); return; }
    showComposeModal(prev, handoffHash, did);
  }

  let composeEscHandler = null;   // one live ESC handler per open modal — removed on ANY close path
  function closeComposeModal() {
    const m = $g("#s7-compose-modal"); if (m) m.remove();
    if (composeEscHandler) { document.removeEventListener("keydown", composeEscHandler); composeEscHandler = null; }
  }

  function showComposeModal(prev, handoffHash, did) {
    closeComposeModal();
    const districts = (prev.preview || []).map((d) => {
      const bands = d.bands.map((b) => `${esc(b.band)}${b.query_strategy === "widen_queries" ? " <span class=\"s7-strat\">widen queries</span>" : b.query_strategy === "new_schools" ? " <span class=\"s7-strat\">new schools</span>" : ""} <span class=\"muted\">(${b.n_schools})</span>`).join(", ");
      const seeds = (d.seed_urls && d.seed_urls.length) ? ` · ${d.seed_urls.length} seed URL(s)` : "";
      return `<li><b>${esc(d.name || d.district_id)}</b> <span class="muted">${esc(d.state)}</span> — ${bands}${seeds}</li>`;
    }).join("");
    const notes = [];
    if (prev.spilled && prev.spilled.length) notes.push(`${prev.spilled.length} district(s) spill past the 12-cap (compose again for the next batch)`);
    if (prev.deferred && prev.deferred.length) notes.push(`${prev.deferred.length} deferred — execute the district's 7->6 first (#159)`);
    if (prev.blocked && prev.blocked.length) notes.push(`${prev.blocked.length} blocked by the depth guard`);
    if (prev.benchmark_excluded && prev.benchmark_excluded.length) notes.push(`${prev.benchmark_excluded.length} benchmark-walled (batch_00000)`);
    const nothing = !prev.batch_id || !prev.n_districts;
    const body = nothing
      ? `<div class="empty">Nothing to compose — no approved NEW-work directives make it into a batch.${notes.length ? "<br/>" + esc(notes.join("; ")) + "." : ""}</div>`
      : `<p>This will compose <b>${prev.batch_id}</b>: <b>${prev.n_districts}</b> district(s), <b>${prev.n_requests}</b> directive(s), then <b>auto-flow to gate@5</b> (gate@1 auto-pass → discovery → capture → process; gate@6 dispatch stays manual).</p>
         <ul class="s7-compose-list">${districts}</ul>
         ${notes.length ? `<div class="s7-compose-notes muted">Also: ${esc(notes.join("; "))}.</div>` : ""}`;
    const overlay = document.createElement("div");
    overlay.id = "s7-compose-modal";
    overlay.className = "s7-modal";
    overlay.innerHTML = `<div class="s7-modal-card">
      <div class="s7-modal-head"><span class="s7-modal-title">Compose follow-up batch</span>
        <button class="btn btn-ghost btn-mini" data-close>Close</button></div>
      <div class="s7-modal-body">${body}</div>
      <div class="s7-modal-foot">
        <button class="btn btn-ghost" data-cancel>Cancel</button>
        ${nothing ? "" : `<button class="btn btn-primary" data-confirm>Compose &amp; auto-flow to gate@5</button>`}
      </div></div>`;
    overlay.querySelector("[data-close]").onclick = closeComposeModal;
    overlay.querySelector("[data-cancel]").onclick = closeComposeModal;   // cancel: no side effect
    overlay.onclick = (e) => { if (e.target === overlay) closeComposeModal(); };  // click-out cancels
    const confirmBtn = overlay.querySelector("[data-confirm]");
    if (confirmBtn) confirmBtn.onclick = () => { closeComposeModal(); doCompose(handoffHash, did); };
    composeEscHandler = (ev) => { if (ev.key === "Escape") closeComposeModal(); };
    document.addEventListener("keydown", composeEscHandler);
    (VIEWS_stage7() || document.body).appendChild(overlay);
  }

  function VIEWS_stage7() { return document.getElementById("stage7view"); }

  async function doCompose(handoffHash, did) {
    let out;
    try { out = await api(`/api/extract/compose-followup`, postJSON({ handoff_hash: handoffHash || null, actor: "ian" })); }
    catch (e) { alert("Compose failed: " + e.message); return; }
    let msg = `Draft follow-up ${out.batch_id}: ${out.n_districts} district(s), ${out.n_requests} directive(s) executed.`;
    if (out.autoflow_started) msg += `\n\nAuto-flowing to gate@5 in the background… (watch Stage 1/2/3/4, review at gate@5).`;
    alert(msg);
    if (out.autoflow_started) pollAutoflow(out.batch_id);
    openDistrict(did);
    loadDistricts();
  }

  // #157: poll the follow-up auto-flow until it lands at gate@5 (or halts), then notify.
  async function pollAutoflow(batchId) {
    let st;
    try { st = await api(`/api/followup/autoflow/${batchId}`); }
    catch (_) { return; }
    if (st.state === "running") { setTimeout(() => pollAutoflow(batchId), 3000); return; }
    if (st.state === "done") alert(`Follow-up ${batchId} reached gate@5 (discovery→capture→process done). Review + label at Stage 5, then dispatch at gate@6.`);
    else if (st.state === "halted") alert(`Follow-up ${batchId} auto-flow HALTED: ${st.error || ""}`);
    else if (st.state === "error") alert(`Follow-up ${batchId} auto-flow error: ${st.error || ""}`);
  }
})();
