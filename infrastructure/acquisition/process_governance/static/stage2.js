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
    window.attributionPanel($g("#stage2view").querySelector(".q-left"), "stage2");   // #118
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
      : window.LCT.statusBadge(b.status);   // #198 review: shared tone (abandoned -> red, not draft-neutral)
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
    if (s.batch_status === "abandoned") actionHtml = `<span class="s2-note">This batch is abandoned (retired at gate@1) — it never runs.</span>`;   // #198 review
    else if (!approved) actionHtml = `<span class="s2-note">Approve this batch at gate@1 (Stage&nbsp;1) before discovery.</span>`;
    else if (r.todo === 0 && !running) actionHtml = `<span class="s2-note">All districts discovered.</span>`;
    else actionHtml = `<button id="s2-run" class="btn btn-primary${running ? " run-anim" : ""}"${canRun ? "" : " disabled"}>${running ? "Discovery running…" : "Run discovery ▶"}</button>`;

    // Header badge = the SAME stage-contextual progress badge as the left pane (not the stale gate@1
    // "approved"); an unapproved batch still shows its lifecycle status (abandoned -> red) as a blocker.
    const headBadge = approved
      ? window.progressBadge({ total: r.total, discovered: r.done, flagged: r.manual_flag_all }, "stage2")
      : window.LCT.statusBadge(s.batch_status || "—");   // #198 review: shared tone
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

    // #572: the derived-domain PROPOSAL cards (GEO batches only) — the decision renders WHERE THE
    // EVIDENCE LIVES (this run's tally), and governs FUTURE domain-scoped composition, never this
    // batch's own capture. Confirm upserts the operative discovered domain; Reject (reason
    // required) records the negative class — both land in the append-only decision corpus the
    // future auto-confirmation trains on.
    html += s.districts.filter((d) => d.geo_proposal).map((d) => {
      const g = d.geo_proposal;
      const pct = g.share != null ? (g.share * 100).toFixed(1) + "%" : "?";
      const top = (g.top_tally || []).map(([h, n]) => `${esc(h)} <span class="muted">(${n})</span>`).join(" · ");
      const decided = d.domain_decision
        ? `<div class="s2-note" data-feat="s2-domain-decided">Latest decision: <b>${esc(d.domain_decision.decision)}</b> ${esc(d.domain_decision.domain)}${d.domain_decision.reason ? ` — “${esc(d.domain_decision.reason)}”` : ""} <span class="muted">by ${esc(d.domain_decision.actor)} ${esc(fmt(d.domain_decision.created_at))}</span>${d.confirmed_domain ? ` · operative discovered domain: <b>${esc(d.confirmed_domain)}</b>` : ""}</div>` : "";
      const buttons = g.derived_host && !d.domain_decision
        ? `<button class="btn btn-primary btn-mini" data-feat="s2-confirm-domain" data-did="${esc(d.district_id)}" data-domain="${esc(g.derived_host)}">Confirm discovered domain</button>
           <button class="btn btn-secondary btn-mini" data-feat="s2-reject-domain" data-did="${esc(d.district_id)}" data-domain="${esc(g.derived_host)}">Reject…</button>`
        : "";
      const body = g.derived_host
        ? `Derived <b>${esc(g.derived_host)}</b> — ${pct} of ${g.total_results} gate-eligible results across <b>${g.n_schools}</b> distinct schools. <span class="muted">Top hosts: ${top}</span>`
        : `<span class="muted">No derivation (${esc(g.outcome || "below threshold")}) — fail-closed, nothing kept; the district resolves manual_flag.</span>`;
      return `<div class="q-locked" data-feat="s2-geo-proposal"><b>${esc(d.name)}</b> — discovered-domain proposal (#164):<br/>
        ${body}<br/>${decided}<div style="margin-top:.4em">${buttons}</div>
        <span class="muted">Confirming returns this district to normal domain-scoped flow (source recorded as “discovered”; NCES never modified). This batch's own capture does not depend on it.</span></div>`;
    }).join("");

    $g("#s2-detail").innerHTML = html;
    const run = $g("#s2-run"); if (run && canRun) run.onclick = runDiscovery;
    $g("#s2-detail").querySelectorAll("[data-feat='s2-confirm-domain'],[data-feat='s2-reject-domain']").forEach((b) => {
      b.onclick = async () => {
        const reject = b.getAttribute("data-feat") === "s2-reject-domain";
        const d = s.districts.find((x) => x.district_id === b.dataset.did) || {};
        const tally = (d.geo_proposal || {}).tally || null;
        let reason = "";
        if (reject) {
          reason = prompt(`Reject the proposal ${b.dataset.domain} for ${d.name || b.dataset.did}?\n\nReason (required — it is the training signal):`);
          if (reason === null) return;
          if (!reason.trim()) { alert("A rejection needs a reason."); return; }
        } else if (!confirm(`Confirm ${b.dataset.domain} as the discovered domain for ${d.name || b.dataset.did}?\n\nThis returns the district to normal domain-scoped flow (audited; NCES unmodified).`)) return;
        try {
          await api("/api/discovered-domain", postJSON({
            district_id: b.dataset.did, domain: b.dataset.domain,
            decision: reject ? "reject" : "confirm", reason,
            derived_in_batch: s.batch_id, tally, actor: "ian" }));
        } catch (e) { alert("Decision failed: " + e.message); return; }
        loadStatus(CURRENT);
      };
    });

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
      // #734: a geo run whose derivation failed had 100% of its provider hits #229-refused — a
      // defect signature (#719), never an ordinary outcome; render it loud on the feed.
      if (e.kind === "geo_derivation_failed") {
        const ds = (e.districts || []).map((d) => `${esc(d.district_id)} (${d.geo_refused} refused)`).join(", ");
        return `<li><span class="s2-ev-kind badge-red">geo_derivation_failed</span> ⚠ ${ds} — providers found hits, ALL refused no-scoping-domain (#719)</li>`;
      }
      const who = e.name || e.district_id || "";
      const refused = e.geo_refused ? ` ⚠ ${e.geo_refused} refused (no-scoping-domain #719)` : "";
      const extra = e.outcome ? ` → ${esc(e.outcome)}${refused}` : e.error ? ` → ${esc(e.error)}` : "";
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
