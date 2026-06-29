"use strict";
// gate@1 (Stage 1 Queue) console view — REQ-102. Vanilla JS, mirrors app.js conventions; built on the
// MMM design tokens + components (Badge = uppercase status pill; Select; Card; Button variants).
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const BANDS = ["elementary", "middle", "high"];
  let CURRENT = null;   // batch_id
  let VIEW = null;      // last loaded to_view payload

  const postJSON = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const esc = (s) => (s == null ? "" : String(s)).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  const fmt = (iso) => (iso || "").replace("T", " ").replace("Z", " UTC");
  const fmtnum = (n) => (n == null ? "?" : Number(n).toLocaleString());

  async function api(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(`${r.status} — ${m}`); }
    return r.json();
  }

  function statusBadge(s) {
    const tone = s === "approved" ? "badge-success" : "badge-neutral";
    return `<span class="badge ${tone}">${esc(s)}</span>`;
  }

  // ----------------------------- view switching (the shared stage switcher) -----------------------------
  // gate1.js hosts the one console switcher (per STAGE2 §4a). Each stage view is its own <main> + JS
  // module, lazily initialized on first show. stage2.js registers window.initStage2; future stages
  // follow the same convention (a container id + an init hook by name) — no second #stageSelect listener.
  const sel = $g("#stageSelect"), prog = $g("#progress");
  const VIEWS = { stage1: $g("#stage1view"), stage2: $g("#stage2view"),
                  stage3: $g("#stage3view"), stage4: $g("#stage4view"), stage5: $g("#stage5view") };
  let loaded1 = false;
  function applyView() {
    const which = sel.value;
    Object.entries(VIEWS).forEach(([k, el]) => { if (el) el.classList.toggle("hidden", k !== which); });
    if (prog) prog.style.display = which === "stage5" ? "" : "none";   // the labeled-count is Stage-5 only
    if (which === "stage1" && !loaded1) { loaded1 = true; renderShell(); loadBatches(); }
    if (which === "stage2" && window.initStage2) window.initStage2();  // stage2.js guards its own re-init
    if (which === "stage3" && window.initStage3) window.initStage3();  // stage3.js guards its own re-init
    if (which === "stage4" && window.initStage4) window.initStage4();  // stage4.js guards its own re-init
  }
  sel.addEventListener("change", applyView);
  window.__applyStageView = applyView;   // so stage2.js can self-show if it loads while already selected
  applyView();   // honor whatever option is initially selected

  // ----------------------------- shell -----------------------------
  function renderShell() {
    VIEWS.stage1.innerHTML = `
      <nav class="col col-tree q-left" aria-label="Batches">
        <div class="q-left-head"><h3>Batches</h3><button id="q-create" class="btn btn-secondary">+ Create batch</button></div>
        <div id="q-list" class="q-list"><div class="empty">Loading…</div></div>
      </nav>
      <section id="q-detail" class="col col-center"><div class="empty">Select a batch on the left, or create one.</div></section>`;
    $g("#q-create").onclick = createBatch;
  }

  // ----------------------------- batch list -----------------------------
  async function loadBatches(selectId) {
    const list = $g("#q-list");
    let batches;
    try { batches = await api("/api/queue"); }
    catch (e) { list.innerHTML = `<div class="empty err">Couldn't load batches: ${esc(e.message)}<br/>Is Docker (governance DB) up?</div>`; return; }
    if (!batches.length) { list.innerHTML = `<div class="empty">No batches yet — create one ↑</div>`; }
    else { list.innerHTML = ""; batches.forEach((b) => list.appendChild(batchRow(b))); }
    if (selectId) openBatch(selectId);
  }

  function batchRow(b) {
    const el = document.createElement("div");
    el.className = "q-batch" + (b.batch_id === CURRENT ? " active" : "");
    el.dataset.id = b.batch_id;
    el.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(b.batch_id)}</span>${statusBadge(b.status)}</div>
      <div class="q-batch-meta">${esc(b.batch_type)} · ${b.n_districts} district${b.n_districts === 1 ? "" : "s"} · ${esc(b.nces_year)}</div>`;
    el.onclick = () => openBatch(b.batch_id);
    return el;
  }

  // ----------------------------- detail -----------------------------
  async function openBatch(id) {
    CURRENT = id;
    document.querySelectorAll(".q-batch").forEach((x) => x.classList.toggle("active", x.dataset.id === id));
    try { VIEW = await api(`/api/queue/${id}`); }
    catch (e) { $g("#q-detail").innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
    renderDetail(VIEW);
  }

  function renderDetail(v) {
    const draft = v.status === "draft";
    const incl = v.districts.filter((d) => d.included).length;
    const actions = draft
      ? `<button id="q-approve" class="btn btn-primary">Approve batch · gate@1</button>`
      : `<button id="q-reopen" class="btn btn-secondary">Re-open for editing</button>`;
    let html = `<div class="q-detail-head">
        <div><h2>${esc(v.batch_id)} ${statusBadge(v.status)}</h2>
          <div class="q-sub">${esc(v.batch_type)} · <b>${incl}/${v.districts.length}</b> districts included · ${esc(v.nces_year)}
          ${v.approved_at ? ` · approved by ${esc(v.approved_by)} ${esc(fmt(v.approved_at))}`
                          : ` · created by ${esc(v.created_by)} ${esc(fmt(v.created_at))}`}</div></div>
        <div class="q-actions">${actions}</div></div>`;
    if (!draft) html += `<div class="q-locked">Approved — editing is locked. Re-open to make changes.</div>`;
    html += v.districts.map((d) => districtBlock(d, draft)).join("");
    $g("#q-detail").innerHTML = html;
    wireDetail();
  }

  function districtBlock(d, draft) {
    const denom = d.nces_school_counts && d.nces_school_counts.total != null ? `${d.nces_school_counts.total} NCES schools` : "";
    const toggle = !draft ? "" : d.included
      ? `<button class="btn btn-mini reject" data-act="reject_district" data-did="${d.district_id}">Reject district</button>`
      : `<button class="btn btn-mini restore" data-act="restore_district" data-did="${d.district_id}">Restore district</button>`;
    const bands = d.included
      ? BANDS.filter((b) => d.schools_by_band[b]).map((b) => bandBlock(d, b, draft)).join("")
      : "";
    return `<div class="q-district${d.included ? "" : " excluded"}">
      <div class="q-district-head">
        <div class="q-dtitle"><span class="q-dname">${esc(d.name)}</span>
          <span class="q-dmeta">${esc(d.state)} · enr ${fmtnum(d.enrollment_k12)} · ${denom}</span>
          ${d.included ? "" : `<span class="badge badge-red">rejected</span>`}</div>
        ${toggle}</div>
      ${bands}</div>`;
  }

  function bandBlock(d, band, draft) {
    const bd = d.schools_by_band[band];
    const rows = bd.schools.map((s) => schoolRow(d.district_id, s, draft)).join("");
    const add = draft ? `<button class="btn btn-mini add" data-act="add_open" data-did="${d.district_id}" data-band="${band}">+ add school</button>` : "";
    const cand = bd.n_candidates != null ? ` / ${bd.n_candidates} cand` : "";
    return `<div class="q-band"><div class="q-band-head">
        <span class="q-band-name">${band}</span><span class="q-band-meta">${bd.n_selected} selected${cand}</span>${add}</div>
      <div class="q-schools">${rows || `<div class="q-empty">none selected</div>`}</div></div>`;
  }

  function schoolRow(did, s, draft) {
    const src = s.source === "manual_add" ? `<span class="badge badge-lavender">added</span>` : "";
    const btn = !draft ? "" : s.included
      ? `<button class="btn btn-mini reject" data-act="reject_school" data-did="${did}" data-sid="${s.school_id}">reject</button>`
      : `<button class="btn btn-mini restore" data-act="restore_school" data-did="${did}" data-sid="${s.school_id}">restore</button>`;
    return `<div class="q-school${s.included ? "" : " excluded"}">
      <span class="q-sname" title="${esc(s.name)}">${esc(s.name)}</span>
      <span class="q-smeta">${esc(s.level || "?")} ${esc(s.gslo || "")}–${esc(s.gshi || "")}</span>${src}${btn}</div>`;
  }

  function wireDetail() {
    const ap = $g("#q-approve"); if (ap) ap.onclick = approve;
    const ro = $g("#q-reopen"); if (ro) ro.onclick = reopen;
    $g("#q-detail").querySelectorAll("[data-act]").forEach((b) => {
      const { act, did, sid, band } = b.dataset;
      b.onclick = act === "add_open" ? () => openAddPicker(did, band)
                                     : () => edit({ op: act, district_id: did, school_id: sid });
    });
  }

  // ----------------------------- mutations -----------------------------
  async function edit(payload) {
    try { VIEW = await api(`/api/queue/${CURRENT}/edit`, postJSON(payload)); }
    catch (e) { alert("Edit failed: " + e.message); return; }
    renderDetail(VIEW); loadBatches();
  }
  async function approve() {
    if (!confirm("Approve this batch (gate@1)? It advances to discovery; editing locks until you re-open.")) return;
    try { VIEW = await api(`/api/queue/${CURRENT}/approve`, postJSON({ actor: "ian" })); }
    catch (e) { alert("Approve failed: " + e.message); return; }
    renderDetail(VIEW); loadBatches();
  }
  async function reopen() {
    try { VIEW = await api(`/api/queue/${CURRENT}/reopen`, postJSON({ actor: "ian" })); }
    catch (e) { alert("Re-open failed: " + e.message); return; }
    renderDetail(VIEW); loadBatches();
  }

  async function createBatch() {
    if (!confirm("Create a new first-run batch (12 districts, 2024-25)?\n\nThis draws a stratified sample from the full NCES corpus + DB enrollment and takes ~10–20s.")) return;
    showOverlay("Building batch — stratified draw across the full NCES corpus + DB enrollment. ~10–20s…");
    try {
      const v = await api("/api/queue/create", postJSON({ n: 12, nces_year: "2024_25", batch_type: "first-run", actor: "ian" }));
      hideOverlay();
      await loadBatches(v.batch_id);
    } catch (e) { hideOverlay(); alert("Create failed: " + e.message); }
  }

  // ----------------------------- add-school picker -----------------------------
  async function openAddPicker(did, band) {
    showOverlay(`Loading eligible ${band} schools for ${did} (reads NCES)…`);
    let data;
    try { data = await api(`/api/queue/${CURRENT}/district/${did}/candidates`); }
    catch (e) { hideOverlay(); alert("Couldn't load candidates: " + e.message); return; }
    hideOverlay();
    const cands = (data.candidates_by_band || {})[band] || [];
    const body = cands.length
      ? cands.map((c) => `<label class="add-item"><input type="checkbox" value="${esc(c.school_id)}"
            data-name="${esc(c.name)}" data-level="${esc(c.level || "")}" data-gslo="${esc(c.gslo || "")}" data-gshi="${esc(c.gshi || "")}"/>
          <span class="q-sname">${esc(c.name)}</span><span class="q-smeta">${esc(c.level || "?")} ${esc(c.gslo || "")}–${esc(c.gshi || "")}</span></label>`).join("")
      : `<div class="empty">No remaining eligible ${band} schools for this district (all already selected).</div>`;
    showModal(`Add ${band} school — ${esc(did)}`, body, async (root) => {
      const picks = [...root.querySelectorAll("input:checked")];
      for (const p of picks) {
        await api(`/api/queue/${CURRENT}/edit`, postJSON({
          op: "add_school", district_id: did, bands: [band],
          school: { school_id: p.value, name: p.dataset.name, level: p.dataset.level, gslo: p.dataset.gslo, gshi: p.dataset.gshi },
        }));
      }
      VIEW = await api(`/api/queue/${CURRENT}`); renderDetail(VIEW); loadBatches();
    });
  }

  // ----------------------------- overlay + modal -----------------------------
  function showOverlay(msg) {
    let o = $g("#q-overlay");
    if (!o) { o = document.createElement("div"); o.id = "q-overlay"; document.body.appendChild(o); }
    o.className = "q-overlay";
    o.innerHTML = `<div class="q-overlay-card"><div class="spinner"></div><div class="q-overlay-msg">${esc(msg)}</div></div>`;
  }
  function hideOverlay() { const o = $g("#q-overlay"); if (o) o.classList.add("hidden"); }

  function showModal(title, body, onConfirm) {
    let m = $g("#q-modal");
    if (!m) { m = document.createElement("div"); m.id = "q-modal"; m.className = "modal"; document.body.appendChild(m); }
    m.innerHTML = `<div class="modal-card"><div class="modal-head"><h2>${esc(title)}</h2><button class="btn btn-secondary" data-x>Close</button></div>
      <div class="modal-body add-body">${body}</div>
      <div class="modal-foot"><button class="btn btn-primary" data-ok>Add selected</button></div></div>`;
    m.classList.remove("hidden");
    const close = () => m.classList.add("hidden");
    m.querySelector("[data-x]").onclick = close;
    m.onclick = (e) => { if (e.target === m) close(); };
    m.querySelector("[data-ok]").onclick = async () => { try { await onConfirm(m); } catch (e) { alert(e.message); } close(); };
  }
})();
