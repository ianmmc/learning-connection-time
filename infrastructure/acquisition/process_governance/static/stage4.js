"use strict";
// Stage 4 (Process) console view — REQ-111. Stage 4 is UNGATED, so this is STATUS/observability (a
// processing-health readout read FROM THE DB cross-stage cache: per-district process outcome, usable vs
// no-usable-text doc counts, and the usable-representations-by-tool distribution) plus the orchestration
// trigger (the local harvesters, run IN-PROCESS as a background job). Mirrors stage3.js; the only
// structural difference upstream is that Stage 4 does the work in-process (no Node, no node-owns-shutdown).
// Vanilla JS on the MMM tokens; reuses the q-*/s2-*/s3-* styles.
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const esc = (s) => (s == null ? "" : String(s)).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  const fmt = (iso) => (iso || "").replace("T", " ").replace("Z", " UTC");
  const postJSON = (b) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
  let CURRENT = null;   // batch_id
  let POLL = null;      // poll timer while a run is in flight
  let inited = false;

  async function api(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(`${r.status} — ${m}`); }
    return r.json();
  }

  window.initStage4 = function () {
    if (!inited) { inited = true; renderShell(); }
    loadBatches();   // re-fetch on every show, so a batch captured later appears here
  };

  function renderShell() {
    $g("#stage4view").innerHTML = `
      <nav class="col col-tree q-left" aria-label="Batches">
        <div class="q-left-head"><h3>Process</h3></div>
        <div id="s4-list" class="q-list"><div class="empty">Loading…</div></div>
      </nav>
      <section id="s4-detail" class="col col-center"><div class="empty">Select a batch to view Stage 4 processing status.</div></section>`;
  }

  // ----------------------------- batch list -----------------------------
  async function loadBatches() {
    const list = $g("#s4-list");
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
    // Stage-contextual badge: this batch's Stage-4 progress (processed + flagged / total), not the
    // stale gate@1 "approved". A draft shows as a blocker.
    const badge = b.status === "approved"
      ? window.progressBadge(b.progress, "stage4")
      : `<span class="badge badge-neutral">${esc(b.status)}</span>`;
    el.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(b.batch_id)}</span>${badge}</div>
      <div class="q-batch-meta">${esc(b.batch_type)} · ${b.n_districts} district${b.n_districts === 1 ? "" : "s"} · ${esc(b.nces_year)}</div>`;
    el.onclick = () => loadStatus(b.batch_id);
    return el;
  }

  // ----------------------------- detail + status -----------------------------
  async function loadStatus(id) {
    CURRENT = id;
    document.querySelectorAll("#s4-list .q-batch").forEach((x) => x.classList.toggle("active", x.dataset.id === id));
    let s;
    try { s = await api(`/api/process/${id}`); }
    catch (e) { $g("#s4-detail").innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
    renderDetail(s);
    if (s.job && s.job.state === "running") startPoll(); else stopPoll();
  }

  // Per-district badge via the shared label map (outcomes.js): `done` shows the process outcome,
  // otherwise the lifecycle status (awaiting_discovery / manual_flag_all / awaiting_capture / todo).
  const outcomeBadge = (d) => window.outcomeBadge(d.status === "done" ? d.outcome : d.status);

  function renderDetail(s) {
    const r = s.rollup;
    const running = s.job && s.job.state === "running";
    const retriable = (r.todo || 0) + (r.failed || 0);   // todo + failed districts (re)process on a run
    const canRun = retriable > 0 && !running;

    let actionHtml;
    if (retriable === 0 && r.awaiting_capture > 0 && !running)
      actionHtml = `<span class="s2-note">${r.awaiting_capture} district${r.awaiting_capture === 1 ? "" : "s"} await Stage&nbsp;3 capture before processing.</span>`;
    else if (retriable === 0 && r.awaiting_discovery > 0 && !running)
      actionHtml = `<span class="s2-note">${r.awaiting_discovery} district${r.awaiting_discovery === 1 ? "" : "s"} await Stage&nbsp;2 discovery first.</span>`;
    else if (retriable === 0 && !running) actionHtml = `<span class="s2-note">All processable districts processed.</span>`;
    else actionHtml = `<button id="s4-run" class="btn btn-primary${running ? " run-anim" : ""}"${canRun ? "" : " disabled"}>${running ? "Processing…" : (r.failed ? "Run / retry processing ▶" : "Run processing ▶")}</button>`;

    // Header badge = the SAME stage-contextual progress badge as the left pane (not the stale gate@1
    // "approved"); a draft still shows as a blocker.
    const headBadge = s.batch_status === "approved"
      ? window.progressBadge({ total: r.total, processed: r.done, flagged: r.manual_flag_all }, "stage4")
      : `<span class="badge badge-neutral">${esc(s.batch_status || "—")}</span>`;
    const processable = r.total - r.manual_flag_all;
    const flagNote = r.manual_flag_all ? ` · ${r.manual_flag_all} no-links` : "";
    const failNote = r.failed ? ` · <span class="s3-fail">${r.failed} failed (retriable)</span>` : "";
    let html = `<div class="q-detail-head">
        <div><h2>${esc(s.batch_id)} ${headBadge}</h2>
          <div class="q-sub">Stage&nbsp;4 · Process (ungated) · <b>${r.done}/${processable} processed</b>${flagNote}${failNote}
            ${r.done ? ` · ${r.processed_all} all · ${r.processed_partial} partial · ${r.no_usable_text_any} no-usable-text · ${r.n_docs} docs · ${r.n_usable} usable · ${r.n_not_usable} not usable` : ""}</div></div>
        <div class="q-actions">${actionHtml}</div></div>`;

    if (s.job) html += jobFeed(s.job);

    html += `<table class="s2-table"><thead><tr>
        <th>District</th><th>Status</th><th>Docs</th><th>Usable</th><th>Not&nbsp;usable</th></tr></thead><tbody>`;
    html += s.districts.map((d) => {
      const errCell = d.status === "failed" && d.error
        ? `<td colspan="3" class="s3-errs"><span title="${esc(d.error)}">${esc(d.error.slice(0, 90))}…</span></td>`
        : (d.status === "done"
            ? `<td>${d.n_docs}</td><td>${d.n_usable}</td><td>${d.n_not_usable}</td>`
            : `<td>—</td><td>—</td><td>—</td>`);
      return `<tr><td class="s2-dname">${esc(d.name)} <span class="q-smeta">${esc(d.state)}${d.domain ? " · " + esc(d.domain) : ""}</span></td>
        <td>${outcomeBadge(d)}</td>${errCell}</tr>`;
    }).join("");
    html += `</tbody></table>`;

    html += toolPanel(s.sources);

    $g("#s4-detail").innerHTML = html;
    const run = $g("#s4-run"); if (run && canRun) run.onclick = runProcess;

    // Keep THIS batch's left-pane chip in sync with the header during a live run (same badge, same
    // source as Stage 3 — the list is only re-fetched on view-show, but the detail polls).
    if (s.batch_status === "approved") {
      const chip = document.querySelector(`#s4-list .q-batch[data-id="${CSS.escape(s.batch_id)}"] .q-batch-top .badge`);
      if (chip) chip.outerHTML = headBadge;
    }
  }

  // Tool-effectiveness readout (the Stage-4-specific extra; the analog of Stage 3's host/CMS panel):
  // across every district's USABLE representations, which harvester/OCR source produced them.
  function toolPanel(sources) {
    if (!sources || !sources.length) return "";
    const chips = sources.map(([k, v]) => `<span class="badge badge-neutral s3-host">${esc(k)} <b>${v}</b></span>`).join(" ");
    return `<div class="s3-hosts"><div class="s3-host-grp">
        <div class="q-smeta">Usable representations by tool (which harvesters/OCR are yielding usable text)</div>${chips}</div></div>`;
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

  async function runProcess() {
    if (!confirm("Run Stage 4 processing for this batch?\n\nRuns every local text harvester (pdftotext, pdfplumber, camelot) and OCR (tesseract) against each captured page — fast, free, local. Already-processed districts are skipped. Runs in the background — progress streams here.")) return;
    try { await api(`/api/process/${CURRENT}/run`, postJSON({ actor: "ian" })); }
    catch (e) { alert("Couldn't start processing: " + e.message); return; }
    startPoll();
    loadStatus(CURRENT);
  }

  // ----------------------------- polling -----------------------------
  function startPoll() { if (!POLL) POLL = setInterval(() => { if (CURRENT) loadStatus(CURRENT); }, 3500); }
  function stopPoll() { if (POLL) { clearInterval(POLL); POLL = null; } }

  // if this module loads while Stage 4 is already the selected view, show it
  if ($g("#stageSelect") && $g("#stageSelect").value === "stage4") {
    window.initStage4();
    if (window.__applyStageView) window.__applyStageView();
  }
})();
