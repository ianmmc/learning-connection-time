"use strict";
// Stage 3 (Capture) console view — REQ-110. Stage 3 is UNGATED, so this is STATUS/observability (a
// health + emergent readout read FROM THE DB cross-stage cache: per-district capture outcome, failures,
// emergent URLs, and the CMS/host distribution) plus the orchestration trigger (per-district Node
// Playwright capture, a background job whose live progress + durable outcome project here). Vanilla JS
// on the MMM tokens; mirrors stage2.js conventions and reuses its styles (q-*, s2-* table/job classes).
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

  window.initStage3 = function () {
    if (inited) return;
    inited = true;
    renderShell();
    loadBatches();
  };

  function renderShell() {
    $g("#stage3view").innerHTML = `
      <nav class="col col-tree q-left" aria-label="Batches">
        <div class="q-left-head"><h3>Capture</h3></div>
        <div id="s3-list" class="q-list"><div class="empty">Loading…</div></div>
      </nav>
      <section id="s3-detail" class="col col-center"><div class="empty">Select a batch to view Stage 3 capture status.</div></section>`;
  }

  // ----------------------------- batch list -----------------------------
  async function loadBatches() {
    const list = $g("#s3-list");
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
    const tone = b.status === "approved" ? "badge-success" : "badge-neutral";
    el.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(b.batch_id)}</span>
        <span class="badge ${tone}">${esc(b.status)}</span></div>
      <div class="q-batch-meta">${esc(b.batch_type)} · ${b.n_districts} district${b.n_districts === 1 ? "" : "s"} · ${esc(b.nces_year)}</div>`;
    el.onclick = () => loadStatus(b.batch_id);
    return el;
  }

  // ----------------------------- detail + status -----------------------------
  async function loadStatus(id) {
    CURRENT = id;
    document.querySelectorAll("#s3-list .q-batch").forEach((x) => x.classList.toggle("active", x.dataset.id === id));
    let s;
    try { s = await api(`/api/capture/${id}`); }
    catch (e) { $g("#s3-detail").innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
    renderDetail(s);
    if (s.job && s.job.state === "running") startPoll(); else stopPoll();
  }

  function outcomeBadge(d) {
    if (d.status === "awaiting_discovery") return `<span class="badge badge-neutral">awaiting discovery</span>`;
    if (d.status === "todo") return `<span class="badge badge-neutral">queued</span>`;
    const tone = d.outcome === "captured_all" ? "badge-success"
      : d.outcome === "capture_failed_all" ? "badge-red" : "badge-lavender";
    return `<span class="badge ${tone}">${esc(d.outcome || "?")}</span>`;
  }

  function renderDetail(s) {
    const r = s.rollup;
    const running = s.job && s.job.state === "running";
    const canRun = r.todo > 0 && !running;

    let actionHtml;
    if (r.todo === 0 && r.awaiting_discovery > 0 && !running)
      actionHtml = `<span class="s2-note">${r.awaiting_discovery} district${r.awaiting_discovery === 1 ? "" : "s"} await Stage&nbsp;2 discovery before capture.</span>`;
    else if (r.todo === 0 && !running) actionHtml = `<span class="s2-note">All discovered districts captured.</span>`;
    else actionHtml = `<button id="s3-run" class="btn btn-primary"${canRun ? "" : " disabled"}>${running ? "Capture running…" : "Run capture ▶"}</button>`;

    let html = `<div class="q-detail-head">
        <div><h2>${esc(s.batch_id)} <span class="badge ${s.batch_status === "approved" ? "badge-success" : "badge-neutral"}">${esc(s.batch_status || "—")}</span></h2>
          <div class="q-sub">Stage&nbsp;3 · Capture (ungated) · <b>${r.done}/${r.total}</b> districts captured
            ${r.done ? ` · ${r.captured_all} all · ${r.captured_partial} partial · ${r.capture_failed_all} failed · ${r.n_captures} captures · ${r.n_failed} failed · ${r.n_emergent} emergent` : ""}</div></div>
        <div class="q-actions">${actionHtml}</div></div>`;

    if (s.job) html += jobFeed(s.job);

    html += `<table class="s2-table"><thead><tr>
        <th>District</th><th>Status</th><th>Captures</th><th>OK</th><th>Failed</th><th>Emergent</th><th>Errors</th></tr></thead><tbody>`;
    html += s.districts.map((d) => {
      const errStr = d.errs && Object.keys(d.errs).length
        ? Object.entries(d.errs).map(([k, v]) => `${v}&nbsp;${esc(k)}`).join(", ") : "—";
      const cells = d.status === "done"
        ? `<td>${d.n_captures}</td><td>${d.n_ok}</td><td>${d.n_failed}</td><td>${d.n_emergent}</td><td class="s3-errs">${errStr}</td>`
        : `<td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>`;
      const stale = d.status === "done" && d.cached === false
        ? ` <span class="badge badge-neutral" title="captures.json on disk but not yet in the DB cache — re-run capture or a Stage-5 ingest">uncached</span>` : "";
      return `<tr><td class="s2-dname">${esc(d.name)} <span class="q-smeta">${esc(d.state)}${d.domain ? " · " + esc(d.domain) : ""}</span></td>
        <td>${outcomeBadge(d)}${stale}</td>${cells}</tr>`;
    }).join("");
    html += `</tbody></table>`;

    html += hostPanel(s.hosts, s.cms);

    $g("#s3-detail").innerHTML = html;
    const run = $g("#s3-run"); if (run && canRun) run.onclick = runCapture;
  }

  function hostPanel(hosts, cms) {
    if ((!hosts || !hosts.length) && (!cms || !cms.length)) return "";
    const chips = (rows) => rows.map(([k, v]) => `<span class="badge badge-neutral s3-host">${esc(k)} <b>${v}</b></span>`).join(" ");
    return `<div class="s3-hosts">
        ${hosts && hosts.length ? `<div class="s3-host-grp"><div class="q-smeta">Hosting (final host of OK captures)</div>${chips(hosts)}</div>` : ""}
        ${cms && cms.length ? `<div class="s3-host-grp"><div class="q-smeta">CMS hint</div>${chips(cms)}</div>` : ""}</div>`;
  }

  function jobFeed(job) {
    const stateTone = { running: "badge-lavender", done: "badge-success", error: "badge-red", halted: "badge-red" }[job.state] || "badge-neutral";
    const evs = (job.events || []).slice(-12).map((e) => {
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

  async function runCapture() {
    if (!confirm("Run Stage 3 capture for this batch?\n\nFetches and persists every candidate page (text + screenshot + PDF + Drive exports), one district at a time via headless Playwright. Already-captured districts are skipped. Runs in the background — progress streams here.")) return;
    try { await api(`/api/capture/${CURRENT}/run`, postJSON({ actor: "ian" })); }
    catch (e) { alert("Couldn't start capture: " + e.message); return; }
    startPoll();
    loadStatus(CURRENT);
  }

  // ----------------------------- polling -----------------------------
  function startPoll() { if (!POLL) POLL = setInterval(() => { if (CURRENT) loadStatus(CURRENT); }, 3500); }
  function stopPoll() { if (POLL) { clearInterval(POLL); POLL = null; } }

  // if this module loads while Stage 3 is already the selected view, show it
  if ($g("#stageSelect") && $g("#stageSelect").value === "stage3") {
    window.initStage3();
    if (window.__applyStageView) window.__applyStageView();
  }
})();
