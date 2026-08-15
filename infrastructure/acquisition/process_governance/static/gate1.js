"use strict";
// gate@1 (Stage 1 Queue) console view — REQ-102. Vanilla JS, mirrors app.js conventions; built on the
// MMM design tokens + components (Badge = uppercase status pill; Select; Card; Button variants).
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const BANDS = ["elementary", "middle", "high"];
  let CURRENT = null;   // batch_id
  let VIEW = null;      // last loaded to_view payload

  const { esc, postJSON, api, statusBadge } = window.LCT;   // statusBadge shared (#198 review)
  const fmt = (iso) => (iso || "").replace("T", " ").replace("Z", " UTC");
  const fmtnum = (n) => (n == null ? "?" : Number(n).toLocaleString());

  // ----------------------------- view switching (the shared stage switcher) -----------------------------
  // gate1.js hosts the one console switcher (per STAGE2 §4a). Each stage view is its own <main> + JS
  // module, lazily initialized on first show. stage2.js registers window.initStage2; future stages
  // follow the same convention (a container id + an init hook by name) — no second #stageSelect listener.
  const sel = $g("#stageSelect"), prog = $g("#progress");
  const VIEWS = { stage1: $g("#stage1view"), stage2: $g("#stage2view"),
                  stage3: $g("#stage3view"), stage4: $g("#stage4view"), stage5: $g("#stage5view"),
                  stage6: $g("#stage6view"), stage7: $g("#stage7view"), stage8: $g("#stage8view"),
                  settings: $g("#settingsview") };
  let loaded1 = false;
  function applyView() {
    const which = sel.value;
    Object.entries(VIEWS).forEach(([k, el]) => { if (el) el.classList.toggle("hidden", k !== which); });
    if (prog) prog.style.display = which === "stage5" ? "" : "none";   // the labeled-count is Stage-5 only
    // #156: render the shell ONCE, but re-fetch the batch list on EVERY show — else a batch created
    // after first page-load (a compose-followup, or another session) is invisible until a full reload.
    // (Mirrors stage2/5's re-fetch-on-show; keeps CURRENT selection via loadBatches' active-row logic.)
    if (which === "stage1") {
      if (!loaded1) { loaded1 = true; renderShell(); }
      loadBatches(CURRENT);
    }
    if (which === "stage2" && window.initStage2) window.initStage2();  // stage2.js guards its own re-init
    if (which === "stage3" && window.initStage3) window.initStage3();  // stage3.js guards its own re-init
    if (which === "stage4" && window.initStage4) window.initStage4();  // stage4.js guards its own re-init
    if (which === "stage5" && window.loadStage5) window.loadStage5();  // re-fetch the faceted list on show
    if (which === "stage6" && window.initStage6) window.initStage6();  // stage6.js guards its own re-init
    if (which === "stage7" && window.initStage7) window.initStage7();  // stage7.js guards its own re-init
    if (which === "stage8" && window.initStage8) window.initStage8();  // stage8.js guards its own re-init
    if (which === "settings" && window.initSettings) window.initSettings();  // settings.js guards its own re-init
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
    const scope = b.discovery_scope === "geo" ? " · <b>geo</b>" : "";   // #572 scope badge
    el.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(b.batch_id)}</span>${statusBadge(b.status)}</div>
      <div class="q-batch-meta">${esc(b.batch_type)}${scope} · ${b.n_districts} district${b.n_districts === 1 ? "" : "s"} · ${esc(b.nces_year)}</div>`;
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
    const abandoned = v.status === "abandoned";
    const incl = v.districts.filter((d) => d.included).length;
    // Draft: Approve + Abandon. Approved: Re-open (abandon is draft-only, so reopen first). Abandoned: terminal, no actions.
    // #572: the 5->1 zero-yield escalation entry (#164 PR 3b) lives here because its OUTPUT is a
    // gate@1 draft — a ran (ever-approved), non-benchmark batch can be checked for districts that
    // came through with nothing dispatchable. Fuller gate@5 surfacing remains #518.
    const zeroYield = (!draft && !abandoned && v.batch_type !== "benchmark")
      ? `<button id="q-zero-yield" class="btn btn-secondary" data-feat="q-zero-yield"
           title="#164 5→1: find districts with zero dispatchable Stage-5 records (no retryable errs, no fidelity flags) and compose a geo-scoped escalation draft">5→1 zero-yield check…</button>` : "";
    const actions = draft
      ? `<button id="q-approve" class="btn btn-primary">Approve batch · gate@1</button>
         <button id="q-abandon" class="btn btn-secondary">Abandon…</button>`
      : abandoned ? ""
      : `<button id="q-reopen" class="btn btn-secondary">Re-open for editing</button>${zeroYield}`;
    const byline = abandoned
      ? ` · abandoned by ${esc(v.abandoned_by)} ${esc(fmt(v.abandoned_at))}`
      : v.approved_at ? ` · approved by ${esc(v.approved_by)} ${esc(fmt(v.approved_at))}`
      : ` · created by ${esc(v.created_by)} ${esc(fmt(v.created_at))}`;
    // #572: the scope is a first-class axis — a GEO batch renders unmistakably (badge + how it
    // was composed: the interleave draw record and/or the path-4 targeting record from meta).
    const scopeBadge = v.discovery_scope === "geo"
      ? ` <span class="badge badge-lavender" data-feat="q-scope-badge">GEO-scoped</span>` : "";
    let html = `<div class="q-detail-head">
        <div><h2>${esc(v.batch_id)} ${statusBadge(v.status)}${scopeBadge}</h2>
          <div class="q-sub">${esc(v.batch_type)} · <b>${incl}/${v.districts.length}</b> districts included · ${esc(v.nces_year)}${byline}</div></div>
        <div class="q-actions">${actions}</div></div>`;
    if (v.discovery_scope === "geo") {
      html += `<div class="q-locked" data-feat="q-geo-note">GEO-scoped batch (#164): discovery runs
        geo-rendered queries (city/zip tokens, no <code>site:</code>) with derive-and-re-gate
        containment — a run without a derived majority host keeps nothing. The derived host surfaces
        as a discovered-domain PROPOSAL for your confirmation.</div>`;
    }
    if (v.scope_draw) {
      html += `<div class="q-locked" data-feat="q-scope-draw">Scope drawn by policy
        (<b>${esc(v.scope_draw.policy)}</b>): <b>${esc(v.scope_draw.drawn)}</b> — weights
        ${fmtnum(v.scope_draw.weights.domain)} domained vs ${fmtnum(v.scope_draw.weights.geo)} blank-domain.</div>`;
    }
    if (v.targeted) {
      html += `<div class="q-locked" data-feat="q-targeted">Targeted draw (path 4 — dev/manual on
        direction, not SOP): requested ${v.targeted.requested.map(esc).join(", ")}${
        v.targeted.missing.length ? ` · <b>not in pool:</b> ${v.targeted.missing.map(esc).join(", ")}` : ""}.</div>`;
    }
    if (abandoned) html += `<div class="q-locked">Abandoned${v.abandon_reason ? ` — ${esc(v.abandon_reason)}` : ""}. Terminal: this batch can't be edited, approved, or re-opened.</div>`;
    else if (!draft) html += `<div class="q-locked">Approved — editing is locked. Re-open to make changes.</div>`;
    // #229: districts refused at draw time for a blank/junk NCES domain (they'd run UNSCOPED
    // discovery — the Millard contamination class, #227). Persisted in Batch.meta_json, so this
    // renders on every open, not just at create — the draw is never silently short. COLLAPSED to
    // the count by default (Ian, 2026-07-14: scrolling hundreds of refused names on every batch is
    // a human-factors cost, not auditability — the full receipt is one click away here, and the
    // STANDING corpus reads in Settings → Exclusions).
    if (v.domain_excluded && v.domain_excluded.length) {
      html += `<details class="q-locked q-domain-excluded" data-feat="domain-excluded-collapsed">
        <summary><b>${v.domain_excluded.length} district${v.domain_excluded.length === 1 ? "" : "s"} refused — no usable NCES domain (#229)</b>
          <span class="muted">— expand for this batch's refusal receipt; the standing corpus lives in Settings → Exclusions</span></summary>
        ${v.domain_excluded.map((e) => `${esc(e.name)} [${esc(e.state)}] (${esc(e.district_id)}, website=${esc(JSON.stringify(e.website))})`).join(" · ")}
      </details>`;
    }
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
    // #499 REQ-150: the roster spine — the district's full live NCES hierarchy, visible from
    // the start (lazy-fetched on expand; selected schools marked from the batch's own rows).
    const spine = d.included
      ? `<details class="q-roster-spine" data-feat="s1-roster-spine" data-did="${d.district_id}">
           <summary class="muted">Roster spine — every in-scope NCES school, live (expand)</summary>
           <div class="q-spine-body muted">Loading…</div></details>` : "";
    return `<div class="q-district${d.included ? "" : " excluded"}">
      <div class="q-district-head">
        <div class="q-dtitle"><span class="q-dname">${esc(d.name)}</span>
          <span class="q-dmeta">${esc(d.state)} · enr ${fmtnum(d.enrollment_k12)} · ${denom}${
            d.geo ? ` · <span data-feat="q-geo-tokens">geo: ${esc(d.geo.city || "?")} ${esc(d.geo.zip || "")}</span>` : ""}${
            d.domain_source === "discovered" ? ` · <span class="badge badge-lavender" title="scoped by a human-confirmed discovered domain (#164) — NCES data unmodified">discovered domain</span>` : ""}</span>
          ${d.included ? "" : `<span class="badge badge-red">rejected</span>`}</div>
        ${toggle}</div>
      ${bands}${spine}</div>`;
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
    // #222: facility-named school (juvenile/detention/correctional) — NCES mis-codes these as
    // Regular; the badge is the gate@1 attention cue (flag, never auto-exclude; reviewer decides).
    const fac = (s.review_flags || []).includes("facility_name")
      ? `<span class="badge badge-warn" data-feat="s1-facility-flag" title="facility-type name (juvenile/detention/correctional) — verify this is a conventional instructional day (#222)">facility?</span>` : "";
    const btn = !draft ? "" : s.included
      ? `<button class="btn btn-mini reject" data-act="reject_school" data-did="${did}" data-sid="${s.school_id}">reject</button>`
      : `<button class="btn btn-mini restore" data-act="restore_school" data-did="${did}" data-sid="${s.school_id}">restore</button>`;
    return `<div class="q-school${s.included ? "" : " excluded"}">
      <span class="q-sname" title="${esc(s.name)}">${esc(s.name)}</span>
      <span class="q-smeta">${esc(s.level || "?")} ${esc(s.gslo || "")}–${esc(s.gshi || "")}</span>${fac}${src}${btn}</div>`;
  }

  function wireDetail() {
    // #499 REQ-150: lazy-load a district's roster spine on first expand (one call per district,
    // only when the human asks — a batch render never fans out N roster reads).
    $g("#q-detail").querySelectorAll("[data-feat='s1-roster-spine']").forEach((det) => {
      det.addEventListener("toggle", async () => {
        if (!det.open || det.dataset.loaded) return;
        det.dataset.loaded = "1";
        const body = det.querySelector(".q-spine-body");
        const selected = new Set();
        ((VIEW && VIEW.districts) || []).forEach((d) => {
          if (d.district_id !== det.dataset.did) return;
          Object.values(d.schools_by_band || {}).forEach((bd) =>
            (bd.schools || []).forEach((s) => { if (s.included) selected.add(s.school_id); }));
        });
        try {
          const r = await api(`/api/queue/${CURRENT}/roster/${det.dataset.did}`);
          // slot_state comes from the SAME projection gate@8 renders (exclusions, human adds,
          // dispositions, band-fact "projected" all applied) — the two gates can't disagree.
          const TITLES = { unfilled: "no accepted fact has ever matched this school",
                           projected: "covered by a band-level blanket statement, not individually observed" };
          const chip = (s) => `<span class="q-spine-slot${s.slot_state === "unfilled" ? " q-spine-unfilled" : ""}${s.slot_state === "projected" ? " q-spine-projected" : ""}${selected.has(s.school_id) ? " q-spine-selected" : ""}"
              data-feat="${s.slot_state === "unfilled" ? "s1-slot-unfilled" : "s1-slot-filled"}"${selected.has(s.school_id) ? ' data-feat2="s1-slot-selected"' : ""}
              title="${TITLES[s.slot_state] || "has an accepted fact"}${selected.has(s.school_id) ? " · selected in THIS batch" : ""}">${esc(s.roster_school)}${selected.has(s.school_id) ? " ✓" : ""}${s.is_charter === "Yes" ? ` <span class="q-spine-ch">ch</span>` : ""} <span class="muted">${esc(s.gslo || "")}–${esc(s.gshi || "")}</span></span>`;
          body.innerHTML = Object.entries(r.bands).map(([b, m]) =>
            `<div class="q-spine-band"><b>${esc(b)}</b> <span class="muted">(${m.stats.n_filled} filled / ${m.stats.n_unfilled} unfilled of ${m.stats.n_slots})</span><br/>${m.slots.map(chip).join(" ")}</div>`).join("")
            + `<p class="muted q-spine-criteria">${esc(r.criteria)} (live NCES ccd_sch ${esc(r.nces_year)})</p>`;
        } catch (e) { body.textContent = `Roster unavailable: ${e.message}`; }
      });
    });
    const ap = $g("#q-approve"); if (ap) ap.onclick = approve;
    const ab = $g("#q-abandon"); if (ab) ab.onclick = abandon;
    const ro = $g("#q-reopen"); if (ro) ro.onclick = reopen;
    const zy = $g("#q-zero-yield"); if (zy) zy.onclick = zeroYieldCheck;
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
  async function abandon() {
    // prompt doubles as confirm (null = cancel) + reason capture. Abandon is terminal & draft-only.
    const reason = prompt("Abandon this batch (gate@1)?\n\nIt becomes terminal — can't be edited, approved, or re-opened. Its schools stay un-attempted (a never-ran draft).\n\nReason (optional):");
    if (reason === null) return;
    try { VIEW = await api(`/api/queue/${CURRENT}/abandon`, postJSON({ actor: "ian", reason })); }
    catch (e) { alert("Abandon failed: " + e.message); return; }
    renderDetail(VIEW); loadBatches();
  }

  // #572: the 5->1 zero-yield escalation (#164 PR 3b) — dry-run survey first, compose on confirm.
  // #719: scope is a DIAGNOSIS — domain-having districts compose a DOMAIN-scoped widened draft,
  // domain-less ones a GEO-scoped draft (up to two scope-pure batches), reviewed here at gate@1
  // (never auto-flowed).
  async function zeroYieldCheck() {
    showOverlay("Surveying this batch's districts for zero yield (live Stage-5 read)…");
    let prev;
    try { prev = await api(`/api/filter/${CURRENT}/compose-zero-yield`, postJSON({ actor: "ian", dry_run: true })); }
    catch (e) { hideOverlay(); alert("Zero-yield survey failed: " + e.message); return; }
    hideOverlay();
    const rung = (did) => esc((prev.ladder || {})[did] || "");
    const composable = Object.keys(prev.targets || {});
    const parts = [];
    const dname = (did) => esc((prev.names || {})[did] || "");   // #572: human-readable labels
    const scopeLabel = (prev.batches || []).map((c) => `<b>${esc(c.batch_id)}</b> (${esc(c.scope).toUpperCase()}-scoped, ${c.n_districts})`).join(" + ") || `<b>${esc(prev.batch_id)}</b>`;
    if (composable.length) parts.push(`<p>Would compose ${scopeLabel} — draft(s) reviewed here at gate@1, never auto-flowed (#719: scope is a diagnosis — GEO only for domain-less districts):</p>
      <ul class="s7-compose-list">${composable.map((d) => `<li><b>${dname(d) || esc(d)}</b> <span class="muted">(${esc(d)})</span> — ${rung(d)}</li>`).join("")}</ul>`);
    if ((prev.flagged || []).length) parts.push(`<p class="muted">Ladder-exhausted → manual flag: ${prev.flagged.map((f) => `${esc(f.district_id)} ${esc(f.name)}`).join(", ")}</p>`);
    if ((prev.ineligible || []).length) parts.push(`<details class="q-domain-excluded"><summary class="muted">${prev.ineligible.length} district(s) not zero-yield (expand)</summary>
      ${prev.ineligible.map((x) => `<div class="muted">${esc(x.district_id)} ${esc(x.name)} — ${esc(x.reason)}</div>`).join("")}</details>`);
    if (!composable.length) {
      showModal("5→1 zero-yield check", parts.join("") || `<div class="empty">No zero-yield districts in this batch.</div>`, null);
      return;
    }
    showModal("5→1 zero-yield check", parts.join(""), async () => {
      showOverlay("Composing the geo escalation draft…");
      let out;
      try { out = await api(`/api/filter/${CURRENT}/compose-zero-yield`, postJSON({ actor: "ian" })); }
      catch (e) { hideOverlay(); alert("Compose failed: " + e.message); return; }
      hideOverlay();
      await loadBatches(out.batch_id);
    }, "Compose escalation draft");
  }

  async function createBatch() {
    // #572: the scope-aware create dialog. The policy gates which scopes are offered (the same
    // gate the server enforces — this is presentation, the 409 is the law); geo composes from the
    // blank-domain pool (geo_all: any district). "Drawn by policy" posts NO scope so the server
    // runs the recorded geo_interleaved draw. Target IDs = the AGREED DESIGN's path 4 (dev/manual
    // batches on direction — exception path, not SOP; recorded in batch meta).
    let pol = { policy: "domain_only", pools: null };
    showOverlay("Reading discovery policy + pool sizes…");
    try { pol = await api("/api/discovery-policy?pools=true"); } catch (_) { /* degrade to domain-only */ }
    hideOverlay();
    const geoAllowed = pol.policy !== "domain_only";
    const pools = pol.pools ? ` <span class="muted">(${fmtnum(pol.pools.domain)} domained · ${fmtnum(pol.pools.geo)} blank-domain)</span>` : "";
    const geoLabel = pol.policy === "geo_all" ? "Geo-scoped (any district — geo_all experiment)" : "Geo-scoped (blank-domain pool)";
    const body = `
      <p><b>Batch type</b> <span class="muted">— first-run DRAWS districts; follow-up and benchmark
        take a district list you name, and RE-RUN districts that already have artifacts (#617).</span></p>
      <label class="add-item"><input type="radio" name="q-btype" value="first-run" checked
        data-feat="q-create-type"/>
        <span class="q-sname">First-run <span class="muted">— stratified draw, excludes already-attempted</span></span></label>
      <label class="add-item"><input type="radio" name="q-btype" value="follow-up"/>
        <span class="q-sname">Follow-up (targeted) <span class="muted">— re-target named districts; Stages 2/3/4 redo and MERGE into the prior round</span></span></label>
      <label class="add-item"><input type="radio" name="q-btype" value="benchmark"/>
        <span class="q-sname">Benchmark (targeted) <span class="muted">— the Stages-2/3/4 A/B harness; terminates at gate@5, never Stage-9-written</span></span></label>
      <p id="q-create-redo-warn" data-feat="q-create-redo-warn" class="muted" style="display:none">
        ⚠ This batch RE-RUNS discovery, capture and processing for every district you name — real SERP
        spend, and Stage 2 merges the new round into that district's existing candidate set.</p>
      <hr/>
      <p>Stratified draw from the full NCES corpus + DB enrollment (~10–20s). Policy:
        <b>${esc(pol.policy)}</b>${pools} <span class="muted">— change it in Settings.</span></p>
      <label class="add-item"><input type="radio" name="q-scope" value="domain" checked/>
        <span class="q-sname">Domain-scoped (standard)</span></label>
      <label class="add-item"${geoAllowed ? "" : ' title="discovery_scope_policy is domain_only — enable a geo position in Settings"'}>
        <input type="radio" name="q-scope" value="geo" data-feat="q-create-scope-geo" ${geoAllowed ? "" : "disabled"}/>
        <span class="q-sname">${geoLabel}${geoAllowed ? "" : " <span class='muted'>(policy is domain_only)</span>"}</span></label>
      ${pol.policy === "geo_interleaved" ? `<label class="add-item"><input type="radio" name="q-scope" value=""/>
        <span class="q-sname">Drawn by policy (geo_interleaved — the seeded weighted draw, recorded on the batch)</span></label>` : ""}
      <p style="margin-top:0.8em"><label>Districts <input id="q-create-n" type="number" min="1" max="12" value="12" style="width:4em"/></label>
        <span class="muted">(12-district hard cap — governance §11d)</span></p>
      <p><label>Target district IDs <span class="muted">(optional, comma-separated — path 4: dev/manual batch on direction, recorded in batch meta; not SOP)</span><br/>
        <input id="q-create-targets" type="text" placeholder="e.g. 3173740" style="width:100%" data-feat="q-create-targets"/></label></p>`;
    showModal("Create batch", body, async (root) => {
      const btype = (root.querySelector("input[name='q-btype']:checked") || {}).value || "first-run";
      const targeted = btype !== "first-run";
      const scope = (root.querySelector("input[name='q-scope']:checked") || {}).value;
      const n = parseInt(root.querySelector("#q-create-n").value, 10) || 12;
      const targets = (root.querySelector("#q-create-targets").value || "")
        .split(",").map((s) => s.trim()).filter(Boolean);
      // #617 Phase 2c: a targeted batch is composed FROM the named list — an empty one would 400 at
      // the server; refuse here so the human gets the reason instead of a bare error.
      if (targeted && !targets.length) {
        alert(`A ${btype} batch is composed from an explicit district list — enter one or more `
              + "target district IDs.");
        return;
      }
      const payload = { n, nces_year: "2024_25", batch_type: btype, actor: "ian" };
      if (scope) payload.discovery_scope = scope;              // "" = drawn by policy (server draws)
      if (targets.length) payload.district_ids = targets;
      showOverlay(targeted
        ? `Composing the ${btype} batch over ${targets.length} named district(s)…`
        : "Building batch — stratified draw across the full NCES corpus + DB enrollment. ~10–20s…");
      try {
        const v = await api("/api/queue/create", postJSON(payload));
        hideOverlay();
        await loadBatches(v.batch_id);
      } catch (e) { hideOverlay(); alert("Create failed: " + e.message); }
    }, "Create batch");
    // #617 Phase 2c: the re-run warning follows the type selection. showModal renders synchronously,
    // so the nodes exist by here. The warning is the ONLY place a human is told that approving a
    // targeted batch spends on districts that already have artifacts.
    const modal = $g("#q-modal");
    const warn = modal && modal.querySelector("#q-create-redo-warn");
    if (warn) {
      modal.querySelectorAll("input[name='q-btype']").forEach((r) => {
        r.onchange = () => { warn.style.display = r.value === "first-run" ? "none" : ""; };
      });
    }
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

  function showModal(title, body, onConfirm, okLabel = "Add selected") {
    let m = $g("#q-modal");
    if (!m) { m = document.createElement("div"); m.id = "q-modal"; m.className = "modal"; document.body.appendChild(m); }
    // #572: onConfirm may be null (an informational modal — no footer button).
    m.innerHTML = `<div class="modal-card"><div class="modal-head"><h2>${esc(title)}</h2><button class="btn btn-secondary" data-x>Close</button></div>
      <div class="modal-body add-body">${body}</div>
      ${onConfirm ? `<div class="modal-foot"><button class="btn btn-primary" data-ok>${esc(okLabel)}</button></div>` : ""}</div>`;
    m.classList.remove("hidden");
    const close = () => m.classList.add("hidden");
    m.querySelector("[data-x]").onclick = close;
    m.onclick = (e) => { if (e.target === m) close(); };
    const ok = m.querySelector("[data-ok]");
    if (ok) ok.onclick = async () => { try { await onConfirm(m); } catch (e) { alert(e.message); } close(); };
  }
})();
