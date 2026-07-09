"use strict";
// Stage 2 (Discover) console view — REQ-104. Stage 2 is UNGATED, so this is STATUS/observability plus
// the orchestration trigger: a Bright Data SERP Wave-1 run (Serper failover; Claude WebSearch on the
// residual), a background job whose live progress + durable outcome (discovery.json + the state_event
// log) project here. Vanilla JS on the MMM tokens; mirrors gate1.js conventions and reuses its styles.
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const { esc, postJSON, api } = window.LCT;
  const fmt = (iso) => (iso || "").replace("T", " ").replace("Z", " UTC");
  let CURRENT = null;   // batch_id
  let POLL = null;      // poll timer while a run is in flight
  let inited = false;


  // lazy-init from the shared switcher (gate1.js) on first show; guard re-entry
  window.initStage2 = function () {
    if (!inited) { inited = true; renderShell(); }
    loadBatches();   // re-fetch on every show, so a batch approved later in Stage 1 appears here
  };

  function renderShell() {
    $g("#stage2view").innerHTML = `
      <nav class="col col-tree q-left" aria-label="Batches">
        <div class="q-left-head"><h3>Discovery</h3></div>
        <div id="s2-list" class="q-list"><div class="empty">Loading…</div></div>
      </nav>
      <section id="s2-detail" class="col col-center"><div class="empty">Select an approved batch to view Stage 2 discovery status.</div></section>`;
  }

  // ----------------------------- batch list -----------------------------
  async function loadBatches() {
    const list = $g("#s2-list");
    let batches;
    try { batches = await api("/api/queue"); }
    catch (e) { list.innerHTML = `<div class="empty err">Couldn't load batches: ${esc(e.message)}<br/>Is Docker (governance DB) up?</div>`; return; }
    if (!batches.length) { list.innerHTML = `<div class="empty">No batches yet — create one in Stage&nbsp;1.</div>`; return; }
    list.innerHTML = "";
    batches.forEach((b) => list.appendChild(batchRow(b)));
    if (CURRENT) loadStatus(CURRENT);
  }

  function batchRow(b) {
    const el = document.createElement("div");
    el.className = "q-batch" + (b.batch_id === CURRENT ? " active" : "");
    el.dataset.id = b.batch_id;
    // Stage-contextual badge: a draft can't be discovered (show it as a blocker); else this batch's
    // Stage-2 progress fraction — not the stale gate@1 "approved".
    const badge = b.status === "approved"
      ? window.progressBadge(b.progress, "stage2")
      : `<span class="badge badge-neutral">${esc(b.status)}</span>`;
    el.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(b.batch_id)}</span>${badge}</div>
      <div class="q-batch-meta">${esc(b.batch_type)} · ${b.n_districts} district${b.n_districts === 1 ? "" : "s"} · ${esc(b.nces_year)}</div>`;
    el.onclick = () => loadStatus(b.batch_id);
    return el;
  }

  // ----------------------------- detail + status -----------------------------
  async function loadStatus(id) {
    CURRENT = id;
    document.querySelectorAll("#s2-list .q-batch").forEach((x) => x.classList.toggle("active", x.dataset.id === id));
    let s;
    try { s = await api(`/api/discover/${id}`); }
    catch (e) { $g("#s2-detail").innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
    renderDetail(s);
    // keep polling while a run is in flight; otherwise stop
    if (s.job && s.job.state === "running") startPoll(); else stopPoll();
  }

  // Per-district badge via the shared label map (outcomes.js) — `done` shows the discovery outcome,
  // otherwise the lifecycle status. One source of truth across stages.
  const outcomeBadge = (d) => window.outcomeBadge(d.status === "done" ? d.outcome : d.status);

  function renderDetail(s) {
    const r = s.rollup;
    const approved = s.batch_status === "approved";
    const running = s.job && s.job.state === "running";
    const canRun = approved && r.todo > 0 && !running;

    let actionHtml;
    if (!approved) actionHtml = `<span class="s2-note">Approve this batch at gate@1 (Stage&nbsp;1) before discovery.</span>`;
    else if (r.todo === 0 && !running) actionHtml = `<span class="s2-note">All districts discovered.</span>`;
    else actionHtml = `<button id="s2-run" class="btn btn-primary${running ? " run-anim" : ""}"${canRun ? "" : " disabled"}>${running ? "Discovery running…" : "Run discovery ▶"}</button>`;

    // Header badge = the SAME stage-contextual progress badge as the left pane (not the stale gate@1
    // "approved"); an unapproved batch still shows its lifecycle status as a blocker.
    const headBadge = approved
      ? window.progressBadge({ total: r.total, discovered: r.done, flagged: r.manual_flag_all }, "stage2")
      : `<span class="badge badge-neutral">${esc(s.batch_status || "—")}</span>`;
    let html = `<div class="q-detail-head">
        <div><h2>${esc(s.batch_id)} ${headBadge}</h2>
          <div class="q-sub">Stage&nbsp;2 · Discover (ungated) · <b>${r.done}/${r.total}</b> districts discovered
            ${r.done ? ` · ${r.found_all} found-all · ${r.found_partial} partial · ${r.manual_flag_all} flag-all · ${r.manual_flag_schools} flagged schools` : ""}</div></div>
        <div class="q-actions">${actionHtml}</div></div>`;

    if (s.job) html += jobFeed(s.job);

    html += `<table class="s2-table"><thead><tr>
        <th>District</th><th>Status</th><th>W1</th><th>W2</th><th>Cand</th><th>Manual flags</th></tr></thead><tbody>`;
    html += s.districts.map((d) => {
      const flags = d.manual_flags && d.manual_flags.length
        ? `<span title="${esc(d.manual_flags.join(', '))}">${d.manual_flags.length} school${d.manual_flags.length === 1 ? "" : "s"}</span>` : "—";
      const cells = d.status === "todo"
        ? `<td>—</td><td>—</td><td>—</td><td>—</td>`
        : `<td>${d.wave1_found}</td><td>${d.wave2_found}</td><td>${d.n_candidates == null ? "—" : d.n_candidates}</td><td>${flags}</td>`;
      return `<tr><td class="s2-dname">${esc(d.name)} <span class="q-smeta">${esc(d.state)}${d.domain ? " · " + esc(d.domain) : ""}</span></td>
        <td>${outcomeBadge(d)}</td>${cells}</tr>`;
    }).join("");
    html += `</tbody></table>`;

    $g("#s2-detail").innerHTML = html;
    const run = $g("#s2-run"); if (run && canRun) run.onclick = runDiscovery;

    // Keep THIS batch's left-pane chip in sync with the header during a live run (the list is only
    // re-fetched on view-show; the detail polls). Same badge, same source; no extra /api/queue fetch.
    if (approved) {
      const chip = document.querySelector(`#s2-list .q-batch[data-id="${CSS.escape(s.batch_id)}"] .q-batch-top .badge`);
      if (chip) chip.outerHTML = headBadge;
    }
  }

  function jobFeed(job) {
    const stateTone = { running: "badge-lavender", done: "badge-success", error: "badge-red", halted: "badge-red" }[job.state] || "badge-neutral";
    const evs = (job.events || []).slice(-12).reverse().map((e) => {   // newest first
      const who = e.name || e.district_id || "";
      const extra = e.outcome ? ` → ${esc(e.outcome)}` : e.error ? ` → ${esc(e.error)}` : "";
      return `<li><span class="s2-ev-kind">${esc(e.kind)}</span> ${esc(who)}${extra}</li>`;
    }).join("");
    const summary = job.summary
      ? `<div class="s2-job-sum">done: ${job.summary.results.filter((x) => x.outcome !== "error").length}/${job.summary.todo} ok · ${job.summary.skipped} skipped</div>` : "";
    const err = job.error ? `<div class="empty err">${esc(job.error)}</div>` : "";
    return `<div class="s2-job">
        <div class="s2-job-head"><span class="badge ${stateTone}">${esc(job.state)}</span>
          <span class="q-smeta">run by ${esc(job.actor)} · started ${esc(fmt(job.started_at))}${job.finished_at ? " · finished " + esc(fmt(job.finished_at)) : ""}</span></div>
        ${summary}${err}
        <ul class="s2-ev">${evs || "<li class=\"q-smeta\">starting…</li>"}</ul></div>`;
  }

  async function runDiscovery() {
    if (!confirm("Run Stage 2 discovery for this batch?\n\nWave 1 = Bright Data SERP (real Google, recurring-free tier), with Serper as failover if Bright Data is unavailable. Any school Google has no page for falls back to a Claude WebSearch pass. Runs in the background — progress streams here.")) return;
    try { await api(`/api/discover/${CURRENT}/run`, postJSON({ actor: "ian" })); }
    catch (e) { alert("Couldn't start discovery: " + e.message); return; }
    startPoll();
    loadStatus(CURRENT);
  }

  // ----------------------------- polling -----------------------------
  function startPoll() { if (!POLL) POLL = setInterval(() => { if (CURRENT) loadStatus(CURRENT); }, 3500); }
  function stopPoll() { if (POLL) { clearInterval(POLL); POLL = null; } }

  // if this module loads while Stage 2 is already the selected view, show it
  if ($g("#stageSelect") && $g("#stageSelect").value === "stage2") {
    window.initStage2();
    if (window.__applyStageView) window.__applyStageView();
  }
})();
