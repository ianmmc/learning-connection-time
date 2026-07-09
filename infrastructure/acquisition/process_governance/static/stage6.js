"use strict";
// Stage 6 (Dispatch) console view — REQ-101, gate@6. Build a dispatch package from Stage-5 release
// decisions, review the per-representation routing (which council) + the estimated cost, then
// APPROVE & FREEZE (gate@6): writes the immutable handoff_<hash>.json + records the dispatch
// (the precious index row + per-district `dispatched` state_events). Stops at the seam — NO paid
// Stage-7 calls. Vanilla JS on the MMM tokens; reuses the q-*/badge/btn styles + a few s6-* rules.
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const { esc, postJSON, api } = window.LCT;
  const usd = (n) => "$" + (Number(n) || 0).toFixed(5);
  const fmt = (iso) => (iso || "").replace("T", " ").replace("Z", " UTC");
  let inited = false;
  const SELECTED = new Set();
  let CANDIDATES = [];                                   // all loaded candidates (client-side filtering)
  const FILTER = { q: "", topology: "", sendOnly: false, heldOnly: false, hideDispatched: false };
  let VERIFIED_ONLY = false;                             // gate@6 training-grade mode: labeled targets only
  let COUNCILS = [];                                     // council registry (override <select> options)
  const OVERRIDES = {};                                  // "<rec_key>::<file>" -> council_id (gate@6 manual override)
  let PREVIEW_IDENTITY = null;                           // the previewed package's identity hash (issue #37)
  const effSend = (c) => (VERIFIED_ONLY ? (c.n_verified || 0) : (c.n_send || 0));   // what THIS mode dispatches


  window.initStage6 = function () {
    if (!inited) { inited = true; renderShell(); loadCouncils(); }
    loadCandidates();
    loadHandoffs();
  };

  async function loadCouncils() {
    try { COUNCILS = await api("/api/handoff/councils"); } catch (_) { COUNCILS = []; }
  }

  function renderShell() {
    $g("#stage6view").innerHTML = `
      <nav class="col col-tree q-left" aria-label="Dispatch candidates">
        <div class="q-left-head"><h3>Dispatch</h3><button id="s6-preview" class="btn btn-secondary">Preview →</button></div>
        <div id="s6-filters" class="s6-filters"></div>
        <div id="s6-list" class="q-list"><div class="empty">Loading…</div></div>
        <div class="q-left-head"><h3>Recent dispatches</h3></div>
        <div id="s6-handoffs" class="q-list"><div class="empty">—</div></div>
      </nav>
      <section id="s6-detail" class="col col-center"><div class="empty">Select districts on the left, then <b>Preview</b> to build a dispatch package.</div></section>
      <div id="s6-lightbox" class="s6-lightbox hidden">
        <div class="s6-lb-card"><div class="s6-lb-head"><span id="s6-lb-title" class="s6-lb-title"></span>
          <button id="s6-lb-close" class="btn btn-ghost">Close</button></div>
          <div id="s6-lb-body" class="s6-lb-body"></div></div>
      </div>`;
    $g("#s6-preview").onclick = preview;
    $g("#s6-lb-close").onclick = closeLightbox;
    $g("#s6-lightbox").onclick = (e) => { if (e.target.id === "s6-lightbox") closeLightbox(); };
  }

  // ----------------------------- candidates + filters -----------------------------
  async function loadCandidates() {
    let cands;
    try { cands = await api("/api/handoff/candidates"); }
    catch (e) { $g("#s6-list").innerHTML = `<div class="empty err">Couldn't load candidates: ${esc(e.message)}<br/>Is Docker (governance DB) up?</div>`; return; }
    CANDIDATES = cands;
    renderFilters();
    renderCandidates();
  }

  function renderFilters() {
    const topos = [...new Set(CANDIDATES.map((c) => c.labeled_topology).filter(Boolean))].sort();
    const bar = $g("#s6-filters");
    bar.innerHTML = `
      <input id="s6-q" class="s6-fi" type="search" placeholder="Filter name / id / state…" value="${esc(FILTER.q)}"/>
      <select id="s6-topo" class="s6-fi"><option value="">All topologies</option>${
        topos.map((t) => `<option value="${esc(t)}" ${FILTER.topology === t ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
      <label class="s6-fl"><input type="checkbox" id="s6-sendonly" ${FILTER.sendOnly ? "checked" : ""}/> has send</label>
      <label class="s6-fl"><input type="checkbox" id="s6-heldonly" ${FILTER.heldOnly ? "checked" : ""}/> has held</label>
      <label class="s6-fl" title="Hide districts already dispatched in a prior handoff — re-sending re-extracts (wasted spend). (#171)">
        <input type="checkbox" id="s6-hidedispatched" ${FILTER.hideDispatched ? "checked" : ""}/> hide already-dispatched</label>
      <label class="s6-fl s6-mode" title="Dispatch ONLY human-labeled target representations — drops the speculative unlabeled tier-A auto-sends. Builds training-grade, manually-verified data.">
        <input type="checkbox" id="s6-verified" ${VERIFIED_ONLY ? "checked" : ""}/> verified only (labeled targets)</label>`;
    bar.querySelector("#s6-q").oninput = (e) => { FILTER.q = e.target.value.toLowerCase(); renderCandidates(); };
    bar.querySelector("#s6-topo").onchange = (e) => { FILTER.topology = e.target.value; renderCandidates(); };
    bar.querySelector("#s6-sendonly").onchange = (e) => { FILTER.sendOnly = e.target.checked; renderCandidates(); };
    bar.querySelector("#s6-heldonly").onchange = (e) => { FILTER.heldOnly = e.target.checked; renderCandidates(); };
    bar.querySelector("#s6-hidedispatched").onchange = (e) => { FILTER.hideDispatched = e.target.checked; renderCandidates(); };
    bar.querySelector("#s6-verified").onchange = (e) => {
      VERIFIED_ONLY = e.target.checked; renderCandidates(); if (SELECTED.size) preview();   // re-price in the new mode
    };
  }

  function passesFilter(c) {
    if (FILTER.topology && c.labeled_topology !== FILTER.topology) return false;
    if (FILTER.sendOnly && !(effSend(c) > 0)) return false;   // "has send" respects the active mode
    if (FILTER.heldOnly && !(c.n_hold > 0)) return false;
    if (FILTER.hideDispatched && c.n_dispatched > 0) return false;   // #171: drop already-sent districts
    if (FILTER.q && !`${c.name || ""} ${c.district_id} ${c.state || ""}`.toLowerCase().includes(FILTER.q)) return false;
    return true;
  }

  function renderCandidates() {
    const list = $g("#s6-list");
    if (!CANDIDATES.length) { list.innerHTML = `<div class="empty">No Stage-5 districts yet.</div>`; return; }
    const shown = CANDIDATES.filter(passesFilter);
    if (!shown.length) { list.innerHTML = `<div class="empty">No districts match the filter.</div>`; return; }
    list.innerHTML = "";
    shown.forEach((c) => {
      const el = document.createElement("label");
      el.className = "q-batch s6-cand";
      const n = effSend(c);
      const tone = n > 0 ? "badge-success" : "badge-neutral";
      const badge = VERIFIED_ONLY
        ? `<span class="badge ${tone}" title="human-labeled target records — what a verified-only dispatch sends (preview shows exact reps + cost)">${n} verified</span>`
        : `<span class="badge ${tone}" title="canonical records that will be sent — labeled targets + unlabeled tier-A${c.n_verified ? `, of which ${c.n_verified} human-verified` : ""} (preview shows exact reps + cost)">${n} send</span>`;
      const verifiedMeta = (!VERIFIED_ONLY && c.n_verified) ? ` · <span title="human-labeled targets — the verified-only subset">${c.n_verified} verified</span>` : "";
      // #171: dispatch-history markers so fresh vs. already-sent districts are distinguishable at a glance.
      // is_benchmark is server-computed by batch_type membership (matches the dispatch wall), #198 review.
      const bench = c.is_benchmark
        ? `<span class="badge badge-accent" title="benchmark district (batch_type=benchmark) — dispatch-walled; generally do not re-send">benchmark</span>` : "";
      const disp = c.n_dispatched > 0
        ? `<span class="badge badge-warn" title="already dispatched ${c.n_dispatched}×${c.last_dispatched_at ? ` — last ${esc(fmt(c.last_dispatched_at))}` : ""}; re-selecting re-dispatches + re-extracts (wasted spend)">dispatched</span>` : "";
      const ext = c.n_extracted > 0
        ? `<span class="badge badge-neutral" title="${c.n_extracted} production extraction${c.n_extracted === 1 ? "" : "s"} with accepted facts on record for this district">✓ extracted</span>` : "";
      el.innerHTML = `<div class="s6-cand-top">
          <input type="checkbox" data-id="${esc(c.district_id)}" ${SELECTED.has(c.district_id) ? "checked" : ""}/>
          <span class="q-batch-id">${esc(c.name || c.district_id)}</span>
          ${badge}${disp}${ext}${bench}</div>
        <div class="q-batch-meta">${esc(c.state || "?")} · ${esc(c.district_id)} · ${esc(c.labeled_topology || "?")}${verifiedMeta}${c.n_hold ? ` · <span title="unlabeled tier-B/C — label them in Stage 5 to dispatch">${c.n_hold} held for label</span>` : ""}</div>`;
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
    try { pkg = await api("/api/handoff/preview", postJSON({ district_ids: ids, overrides: OVERRIDES, verified_only: VERIFIED_ONLY })); }
    catch (e) { det.innerHTML = `<div class="empty err">Preview failed: ${esc(e.message)}</div>`; return; }
    PREVIEW_IDENTITY = pkg.preview_identity || null;   // echoed back on dispatch (issue #37 staleness gate)
    renderPackage(pkg);
  }

  function repRow(did, recKey, rep) {
    const key = `${recKey}::${rep.file}`;
    const current = rep.councils[0] || "";
    const opts = COUNCILS.map((c) => `<option value="${esc(c.id)}" ${c.id === current ? "selected" : ""}>${esc(c.id)}</option>`).join("");
    // the file text is the inspect click target; the <select> is the council override (stops propagation)
    return `<div class="s6-rep" data-did="${esc(did)}">
        <span class="s6-kind">${esc(rep.kind)}</span>
        <code class="s6-rep-click" data-did="${esc(did)}" data-reckey="${esc(recKey)}" data-file="${esc(rep.file)}"
              data-kind="${esc(rep.kind)}" title="click to inspect this representation">${esc(rep.file)}</code> →
        <select class="s6-council-sel" data-key="${esc(key)}" title="council override">${opts}</select>
        ${rep.fidelity_suspect ? `<span class="badge badge-warn">fidelity-suspect</span>` : ""}
        <span class="s6-usd">${usd(rep.est_usd)}</span></div>`;
  }

  function renderPackage(pkg) {
    const det = $g("#s6-detail");
    const blocks = pkg.districts.map((d) => {
      const sends = d.records.filter((r) => r.decision === "send");
      const reps = sends.flatMap((r) => r.reps.map((rep) => repRow(d.district_id, r.rec_key, rep)));
      const head = `${esc(d.name || d.district_id)}${d.state ? ` · ${esc(d.state)}` : ""}
          <span class="muted">${esc(d.district_id)} · ${esc(d.topology || "?")} · ${d.n_send_reps} rep(s) · ${usd(d.est_usd)}</span>`;
      return `<div class="s6-dist" data-did="${esc(d.district_id)}">
          <h4>${head} <button class="s6-remove" data-did="${esc(d.district_id)}" title="remove this district from the dispatch">✕</button></h4>
          ${reps.length ? reps.join("") : `<div class="s6-rep muted">no send-eligible records</div>`}
        </div>`;
    });
    det.innerHTML = `
      <div class="s6-summary">
        <h3>Dispatch preview ${pkg.verified_only ? `<span class="badge badge-accent" title="only human-labeled target representations — training-grade">verified only</span>` : ""}</h3>
        <p><b>${pkg.cost.n_reps}</b> representation(s) across <b>${pkg.districts.length}</b> district(s) ·
           estimated <b>${usd(pkg.cost.total_usd)}</b> <span class="badge badge-neutral">${esc(pkg.cost.provenance)}</span></p>
        <button id="s6-dispatch" class="btn btn-primary"${pkg.cost.n_reps ? "" : " disabled"}>Approve &amp; freeze dispatch (gate@6)</button>
        <p class="muted s6-note">Freezes the immutable dispatch record + records it. <b>No paid extraction</b> — that's Stage&nbsp;7.</p>
      </div>
      ${blocks.join("")}`;
    const btn = $g("#s6-dispatch");
    if (btn) btn.onclick = () => dispatch(btn);
    det.querySelectorAll(".s6-remove").forEach((b) => { b.onclick = () => removeDistrict(b.dataset.did); });
    det.querySelectorAll(".s6-rep-click").forEach((r) => {
      r.onclick = () => openInspect(r.dataset.did, r.dataset.reckey, r.dataset.file, r.dataset.kind);
    });
    det.querySelectorAll(".s6-council-sel").forEach((sel) => {
      sel.onchange = () => { OVERRIDES[sel.dataset.key] = sel.value; preview(); };   // re-price with the override
    });
  }

  function removeDistrict(did) {
    SELECTED.delete(did);
    const cb = $g(`#s6-list input[data-id="${did}"]`);
    if (cb) cb.checked = false;
    preview();   // re-preview with the remaining selection (shows "select…" if now empty)
  }

  // ----------------------------- inspect a representation (lightbox) -----------------------------
  async function openInspect(did, recKey, file, kind) {
    const lb = $g("#s6-lightbox"), body = $g("#s6-lb-body"), title = $g("#s6-lb-title");
    title.textContent = `${did} · ${file}`;
    const url = `/api/handoff/inspect?district_id=${encodeURIComponent(did)}&rec_key=${encodeURIComponent(recKey)}&file=${encodeURIComponent(file)}`;
    body.innerHTML = `<div class="empty">Loading…</div>`;
    lb.classList.remove("hidden");
    if (kind === "image") { body.innerHTML = `<img src="${url}" alt="${esc(file)}" class="s6-lb-img"/>`; return; }
    if (kind === "pdf") { body.innerHTML = `<iframe src="${url}" class="s6-lb-frame" title="${esc(file)}"></iframe>`; return; }
    try { const r = await fetch(url); body.innerHTML = `<pre class="s6-lb-text">${esc(await r.text())}</pre>`; }
    catch (e) { body.innerHTML = `<div class="empty err">Couldn't load: ${esc(e.message)}</div>`; }
  }

  function closeLightbox() {
    $g("#s6-lightbox").classList.add("hidden");
    $g("#s6-lb-body").innerHTML = "";
  }

  // ----------------------------- gate@6 approve -> freeze + record -----------------------------
  async function dispatch(btn) {
    const ids = [...SELECTED];
    if (!ids.length) return;
    btn.disabled = true; btn.textContent = "Freezing…";
    let res;
    try {
      res = await api("/api/handoff/dispatch", postJSON({ district_ids: ids, actor: "ian", overrides: OVERRIDES,
        verified_only: VERIFIED_ONLY, expected_identity: PREVIEW_IDENTITY }));
    } catch (e) {
      btn.disabled = false; btn.textContent = "Approve & freeze dispatch (gate@6)";
      if (e.message.startsWith("409")) {   // stale preview (issue #37) — re-preview, don't freeze blind
        alert("Dispatch blocked: " + e.message + "\n\nRebuilding the preview from the current release now — review it, then approve again.");
        preview();
        return;
      }
      alert("Dispatch failed: " + e.message); return;
    }
    $g("#s6-detail").innerHTML = `<div class="s6-summary">
        <h3>✓ Dispatch frozen &amp; recorded ${res.verified_only ? `<span class="badge badge-accent">verified only</span>` : ""}</h3>
        <p><code>${esc(res.handoff_id)}</code></p>
        <p><b>${res.n_reps}</b> rep(s) · ${res.n_districts} district(s) · ${usd(res.total_usd)}
           <span class="badge badge-neutral">${esc(res.provenance)}</span></p>
        <p class="muted">${esc(res.path)}</p>
        <p class="muted s6-note">Recorded as <b>dispatched</b>. The paid council extraction is Stage&nbsp;7 (out of scope here).</p>
      </div>`;
    SELECTED.clear();
    PREVIEW_IDENTITY = null;
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
      // #152: run the PAID Stage-7 extraction for this dispatched handoff (gate@6 was the go-ahead).
      // The run is resume-by-default (already-extracted districts skip), so a FULLY-extracted handoff
      // gets an honest done marker, not a button — a "Re-run" would skip everything and do nothing.
      const done = h.n_extracted >= h.n_districts && h.n_districts > 0;
      const extractedNote = h.n_extracted > 0 ? ` · <span class="muted">${h.n_extracted}/${h.n_districts} extracted</span>` : "";
      const control = done
        ? `<span class="badge badge-neutral" title="all districts extracted for this handoff">✓ extracted</span>`
        : `<button class="btn btn-secondary btn-mini s6-extract" data-hash="${esc(h.handoff_hash)}" ${h.running ? "disabled" : ""}>${h.running ? "running…" : (h.n_extracted > 0 ? "Resume extraction" : "Run extraction ▶")}</button>`;
      row.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(h.handoff_id.slice(0, 24))}…</span>
          <span class="badge badge-success">${esc(h.status)}</span></div>
        <div class="q-batch-meta">${h.n_districts}d · ${h.n_reps}r · ${usd(h.total_usd)} ${esc(h.cost_provenance)} · ${esc(fmt(h.created_at))}${extractedNote}</div>
        <div class="btn-row">${control}</div>`;
      const btn = row.querySelector(".s6-extract");
      if (btn) btn.onclick = (e) => { e.stopPropagation(); runExtraction(h.handoff_hash); };
      el.appendChild(row);
    });
  }

  // #152: fire the extraction background job, then poll status into the handoff row until done.
  async function runExtraction(hash) {
    if (!confirm("Run the paid Stage-7 council extraction for this dispatched handoff? It re-enters the pipeline at Stage 7 (budget-gated, resumable — already-extracted districts are skipped).")) return;
    try { await api(`/api/extract/${hash}/run`, postJSON({ actor: "ian" })); }
    catch (e) { alert("Couldn't start extraction: " + e.message); return; }
    loadHandoffs();                      // reflect "running…" immediately
    pollExtraction(hash);
  }

  async function pollExtraction(hash) {
    let st;
    try { st = await api(`/api/extract/run/${hash}`); }
    catch (_) { return; }
    if (st.state === "running") { setTimeout(() => pollExtraction(hash), 2500); return; }
    loadHandoffs();                      // refresh counts/labels on terminal state
    if (st.state === "done") alert(`Extraction complete: ${st.summary ? st.summary.n_districts : "?"} district(s) this run. Review at gate@7.`);
    else if (st.state === "partial") {                    // #173: some districts failed, batch continued
      const s = st.summary || {}, failed = (s.failed || []).map(f => f.district_id).join(", ");
      alert(`Extraction finished PARTIAL: ${s.n_districts || 0} district(s) extracted, ${s.n_failed || 0} failed (${failed}). The good districts are durable; re-run to retry the failed ones. Review at gate@7.`);
    }
    else if (st.state === "halted") alert("Extraction halted (control failure): " + (st.error || ""));
    else if (st.state === "error") alert("Extraction error: " + (st.error || ""));
  }
})();
