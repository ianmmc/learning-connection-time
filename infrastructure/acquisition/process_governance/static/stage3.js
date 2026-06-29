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
    if (!inited) { inited = true; renderShell(); }
    loadBatches();   // re-fetch on every show, so a batch approved later in Stage 1 appears here
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
    // Stage-contextual badge: this batch's Stage-3 progress (captured + flagged / total), not the
    // stale gate@1 "approved". A draft shows as a blocker.
    const badge = b.status === "approved"
      ? window.progressBadge(b.progress, "stage3")
      : `<span class="badge badge-neutral">${esc(b.status)}</span>`;
    el.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(b.batch_id)}</span>${badge}</div>
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

  // Per-district badge via the shared label map (outcomes.js): `done` shows the capture outcome,
  // otherwise the lifecycle status (awaiting_discovery / manual_flag_all / todo) — the SAME
  // manual_flag_all badge Stage 2 uses (replaces the old, misleading "uncached").
  const outcomeBadge = (d) => window.outcomeBadge(d.status === "done" ? d.outcome : d.status);

  function renderDetail(s) {
    const r = s.rollup;
    const running = s.job && s.job.state === "running";
    const retriable = (r.todo || 0) + (r.failed || 0);   // failed districts re-dispatch on the next run
    const canRun = retriable > 0 && !running;

    let actionHtml;
    if (retriable === 0 && r.awaiting_discovery > 0 && !running)
      actionHtml = `<span class="s2-note">${r.awaiting_discovery} district${r.awaiting_discovery === 1 ? "" : "s"} await Stage&nbsp;2 discovery before capture.</span>`;
    else if (retriable === 0 && !running) actionHtml = `<span class="s2-note">All capturable districts captured.</span>`;
    else actionHtml = `<button id="s3-run" class="btn btn-primary${running ? " run-anim" : ""}"${canRun ? "" : " disabled"}>${running ? "Capture running…" : (r.failed ? "Run / retry capture ▶" : "Run capture ▶")}</button>`;

    // Header badge = the SAME stage-contextual progress badge as the left pane (not the stale gate@1
    // "approved"); a draft still shows as a blocker.
    const headBadge = s.batch_status === "approved"
      ? window.progressBadge({ total: r.total, captured: r.done, flagged: r.manual_flag_all }, "stage3")
      : `<span class="badge badge-neutral">${esc(s.batch_status || "—")}</span>`;
    const capturable = r.total - r.manual_flag_all;
    const flagNote = r.manual_flag_all ? ` · ${r.manual_flag_all} no-links` : "";
    const failNote = r.failed ? ` · <span class="s3-fail">${r.failed} failed (retriable)</span>` : "";
    let html = `<div class="q-detail-head">
        <div><h2>${esc(s.batch_id)} ${headBadge}</h2>
          <div class="q-sub">Stage&nbsp;3 · Capture (ungated) · <b>${r.done}/${capturable} captured</b>${flagNote}${failNote}
            ${r.done ? ` · ${r.captured_all} all · ${r.captured_partial} partial · ${r.capture_failed_all} all-URLs-failed · ${r.n_captures} captures · ${r.n_failed} failed URLs · ${r.n_emergent} emergent` : ""}</div></div>
        <div class="q-actions">${actionHtml}</div></div>`;

    if (s.job) html += jobFeed(s.job);

    html += `<table class="s2-table"><thead><tr>
        <th>District</th><th>Status</th><th>Captures</th><th>OK</th><th>Failed</th><th>Emergent</th><th>Errors</th></tr></thead><tbody>`;
    const isFail = (st) => st === "failed" || st === "timed_out";
    html += s.districts.map((d) => {
      const errStr = isFail(d.status) && d.error
        ? `<span title="${esc(d.error)}">${esc(d.error.slice(0, 80))}…</span>`
        : (d.errs && Object.keys(d.errs).length
            ? Object.entries(d.errs).map(([k, v]) => `${v}&nbsp;${esc(k)}`).join(", ") : "—");
      const cells = d.status === "done"
        ? `<td>${d.n_captures}</td><td>${d.n_ok}</td><td>${d.n_failed}</td><td>${d.n_emergent}</td><td class="s3-errs">${errStr}</td>`
        : `<td>—</td><td>—</td><td>—</td><td>—</td><td class="s3-errs">${isFail(d.status) ? errStr : "—"}</td>`;
      return `<tr><td class="s2-dname">${esc(d.name)} <span class="q-smeta">${esc(d.state)}${d.domain ? " · " + esc(d.domain) : ""}</span></td>
        <td>${outcomeBadge(d)}</td>${cells}</tr>`;
    }).join("");
    html += `</tbody></table>`;

    html += hostPanel(s.hosts, s.cms);

    $g("#s3-detail").innerHTML = html;
    const run = $g("#s3-run"); if (run && canRun) run.onclick = runCapture;

    // Keep THIS batch's left-pane chip in sync with the header during a live run: the list is only
    // re-fetched on view-show, but the detail polls — so push the header's (disk-accurate) badge onto
    // the chip. Same badge, same source; no extra /api/queue fetch.
    if (s.batch_status === "approved") {
      const chip = document.querySelector(`#s3-list .q-batch[data-id="${CSS.escape(s.batch_id)}"] .q-batch-top .badge`);
      if (chip) chip.outerHTML = headBadge;
    }
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
