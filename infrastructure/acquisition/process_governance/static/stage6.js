"use strict";
// Stage 6 (Dispatch) console view — REQ-101, gate@6. Redesigned (2026) to mirror gate@1's Batch pattern:
// a persisted, reopenable DRAFT dispatch (add/remove districts, per-rep council overrides, verified-only
// toggle) that a human builds up before freezing — replacing the old ephemeral checkbox-selection +
// manual-Preview flow. One unified left-pane list (drafts + frozen dispatches together, drafts first);
// the center pane is ALWAYS populated on click: an editable tree for a draft, a read-only package view
// for a frozen dispatch. Each frozen dispatch carries a DERIVED `origin` ('stage7' | 'console' | 'draft')
// — computed server-side from receipts (`extraction_request.executed_ref`/`route` + `dispatch_draft`),
// never stored — so a true Stage 7->6 back-edge reads "from Stage 7" while genuine console/first-run
// dispatches (incl. all pre-draft history) read "console". Vanilla JS on the MMM tokens; reuses q-*/badge/btn.
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const { esc, postJSON, api, statusBadge, usd } = window.LCT;
  const fmt = (iso) => (iso || "").replace("T", " ").replace("Z", " UTC");

  // Origin badge/note for a frozen dispatch — driven by the server-derived `origin`. 'draft' (the normal
  // new console flow) shows nothing; only the two "no editable draft behind this" origins are called out.
  function originBadge(origin) {
    if (origin === "stage7")
      return `<span class="badge badge-accent" title="Produced by the Stage 7→6 back-edge — verified from an extraction_request receipt, not inferred.">from Stage 7</span>`;
    if (origin === "console")
      return `<span class="badge badge-neutral s6-origin-console" title="Console / first-run / follow-up-batch dispatch (no Stage-6 draft, no 7→6 back-edge link). Derived from receipts.">console</span>`;
    return "";   // 'draft' — the normal drafted flow, no badge needed
  }
  function originNote(origin) {
    if (origin === "stage7")
      return `<div class="q-locked" data-feat="s6-origin-note">Produced by the Stage 7→6 back-edge — verified from an <code>extraction_request</code> receipt (route <code>7-&gt;6</code>). No Stage-6 draft exists for it.</div>`;
    if (origin === "console")
      return `<div class="q-locked" data-feat="s6-origin-note">Console / first-run / follow-up-batch dispatch — no Stage-6 draft and no 7→6 back-edge link. (Dispatches predating draft tracking read this way.)</div>`;
    return "";   // 'draft' — frozen from a Stage-6 draft; nothing to flag
  }
  let inited = false;
  let CURRENT = null;          // { kind: "draft"|"handoff", id }
  let COUNCILS = [];           // council registry (override <select> options)
  let DRAFT_VIEW = null;       // last loaded draft-detail payload (GET /api/dispatch/{id})
  let BM_KEYS = new Set();     // #662: "<did>::<rec_key>" of injected gt:// reps in this view

  window.initStage6 = function () {
    if (!inited) { inited = true; renderShell(); loadCouncils(); }
    loadList(CURRENT && CURRENT.kind === "draft" ? CURRENT.id : null);
  };

  async function loadCouncils() {
    try { COUNCILS = await api("/api/handoff/councils"); } catch (_) { COUNCILS = []; }
  }

  function renderShell() {
    $g("#stage6view").innerHTML = `
      <nav class="col col-tree q-left" aria-label="Dispatches" data-feat="s6-draft-list">
        <div class="q-left-head"><h3>Dispatch</h3><button id="s6-new" class="btn btn-secondary">+ New dispatch</button></div>
        <div id="s6-list" class="q-list"><div class="empty">Loading…</div></div>
      </nav>
      <section id="s6-detail" class="col col-center"><div class="empty">Select a dispatch on the left, or create one.</div></section>
      <div id="s6-lightbox" class="s6-lightbox hidden">
        <div class="s6-lb-card"><div class="s6-lb-head"><span id="s6-lb-title" class="s6-lb-title"></span>
          <button id="s6-lb-close" class="btn btn-ghost">Close</button></div>
          <div id="s6-lb-body" class="s6-lb-body"></div></div>
      </div>`;
    $g("#s6-new").onclick = createDraft;
    $g("#s6-lb-close").onclick = closeLightbox;
    $g("#s6-lightbox").onclick = (e) => { if (e.target.id === "s6-lightbox") closeLightbox(); };
  }

  // ----------------------------- unified left-pane list -----------------------------
  async function loadList(selectDraftId) {
    const list = $g("#s6-list");
    let rows;
    try { rows = await api("/api/dispatch"); }
    catch (e) { list.innerHTML = `<div class="empty err">Couldn't load: ${esc(e.message)}<br/>Is Docker (governance DB) up?</div>`; return; }
    if (!rows.length) { list.innerHTML = `<div class="empty">No dispatches yet — create one ↑</div>`; }
    else { list.innerHTML = ""; rows.forEach((r) => list.appendChild(dispatchRow(r))); }
    if (selectDraftId) openDispatch(selectDraftId, "draft");
  }

  function dispatchRow(r) {
    const el = document.createElement("div");
    const active = CURRENT && ((r.kind === "draft" && CURRENT.kind === "draft" && CURRENT.id === r.draft_id)
      || (r.kind === "handoff" && CURRENT.kind === "handoff" && CURRENT.id === r.handoff_id));
    el.className = "q-batch" + (active ? " active" : "");
    if (r.kind === "draft") {
      el.dataset.kind = "draft"; el.dataset.id = r.draft_id;
      const badge = r.status === "abandoned" ? statusBadge("abandoned") : `<span class="badge badge-neutral">draft</span>`;
      el.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(r.draft_id)}</span>${badge}</div>
        <div class="q-batch-meta">${r.n_districts} district${r.n_districts === 1 ? "" : "s"} · ${r.verified_only ? "verified-only" : "standard"}${r.dispatch_type === "benchmark" ? " · benchmark" : ""} · ${esc(fmt(r.created_at))}</div>`;
      el.onclick = () => openDispatch(r.draft_id, "draft");
    } else {
      el.dataset.kind = "handoff"; el.dataset.id = r.handoff_id;
      el.innerHTML = `<div class="q-batch-top s6-handoff-top"><span class="q-batch-id">${esc(r.handoff_id.slice(0, 24))}…</span>
          <span class="badge badge-success">${esc(r.status)}</span>${originBadge(r.origin)}</div>
        <div class="q-batch-meta">${r.n_districts}d · ${r.n_reps}r · ${usd(r.total_usd)} ${esc(r.cost_provenance)} · ${esc(fmt(r.created_at))}${r.n_extracted ? ` · ${r.n_extracted}/${r.n_districts} extracted` : ""}</div>`;
      el.onclick = () => openDispatch(r.handoff_id, "handoff");
    }
    return el;
  }

  async function createDraft() {
    try {
      const v = await api("/api/dispatch/create", postJSON({ actor: "ian" }));
      await loadList(v.draft_id);
    } catch (e) { alert("Create failed: " + e.message); }
  }

  // ----------------------------- always-populated center pane -----------------------------
  async function openDispatch(id, kind) {
    CURRENT = { kind, id };
    document.querySelectorAll("#s6-list .q-batch").forEach((el) =>
      el.classList.toggle("active", el.dataset.kind === kind && el.dataset.id === id));
    if (kind === "draft") await openDraft(id); else await openHandoff(id);
  }

  // Staleness guard for every await-then-render path: if the user clicked a DIFFERENT row while a
  // fetch was in flight, the late response must not overwrite the pane (or DRAFT_VIEW) — the visible
  // detail would silently mismatch the highlighted selection.
  const isCurrent = (kind, id) => CURRENT && CURRENT.kind === kind && CURRENT.id === id;

  async function openDraft(id) {
    const det = $g("#s6-detail");
    det.innerHTML = `<div class="empty">Loading ${esc(id)}…</div>`;
    let v;
    try { v = await api(`/api/dispatch/${id}`); }
    catch (e) { if (isCurrent("draft", id)) det.innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
    if (!isCurrent("draft", id)) return;   // user moved on while this was in flight
    DRAFT_VIEW = v;
    renderDraftDetail(v);
  }

  async function openHandoff(id) {
    const det = $g("#s6-detail");
    det.innerHTML = `<div class="empty">Loading ${esc(id)}…</div>`;
    let h;
    try { h = await api(`/api/handoffs/${id}`); }
    catch (e) { if (isCurrent("handoff", id)) det.innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
    if (!isCurrent("handoff", id)) return;
    renderHandoffDetail(h);
  }

  // ----------------------------- draft detail (editable) -----------------------------
  function renderDraftDetail(v) {
    const det = $g("#s6-detail");
    const draft = v.status === "draft";
    const abandoned = v.status === "abandoned";
    const pkg = v.package || { districts: [], cost: { n_reps: 0, total_usd: 0, provenance: "unknown" } };
    const actions = draft
      ? `<button id="s6-freeze" class="btn btn-primary" data-feat="s6-freeze-btn"${pkg.cost.n_reps ? "" : " disabled"}>Freeze dispatch (gate@6)</button>
         <button id="s6-abandon" class="btn btn-secondary">Abandon…</button>`
      : "";
    const byline = abandoned ? ` · abandoned by ${esc(v.abandoned_by)} ${esc(fmt(v.abandoned_at))}`
      : v.dispatched_at ? ` · dispatched by ${esc(v.dispatched_by)} ${esc(fmt(v.dispatched_at))}`
      : ` · created by ${esc(v.created_by)} ${esc(fmt(v.created_at))}`;
    let html = `<div class="q-detail-head">
        <div><h2>${esc(v.draft_id)} ${statusBadge(v.status)}</h2>
          <div class="q-sub">${v.districts.filter((d) => d.included).length} district(s) · ${v.verified_only ? "verified-only" : "standard"}${v.dispatch_type === "benchmark" ? ` · <span class="badge badge-accent" data-feat="s6-dispatch-type">benchmark dispatch</span>` : ""}${byline}</div></div>
        <div class="q-actions">${actions}</div></div>`;
    if (abandoned) {
      html += `<div class="q-locked">Abandoned${v.abandon_reason ? ` — ${esc(v.abandon_reason)}` : ""}. Terminal.</div>`;
    } else if (draft) {
      html += `<div class="s6-toggle-row">
          <label class="s6-fl s6-mode" title="Dispatch ONLY human-labeled target representations — drops the speculative unlabeled tier-A auto-sends.">
            <input type="checkbox" id="s6-verified" ${v.verified_only ? "checked" : ""}/> verified only (labeled targets)</label>
          <label class="s6-fl s6-mode" data-feat="s6-dispatch-type-toggle" title="A BENCHMARK dispatch is the Stages 6/7 A/B harness (which representations to which councils, and the yield). It TERMINATES AT gate@7 — its results are never written to the LCT DB. Turn this on to run a Council Lab experiment over these representations on purpose.">
            <input type="checkbox" id="s6-dispatch-type" ${v.dispatch_type === "benchmark" ? "checked" : ""}/> benchmark dispatch (stops at gate@7)</label>
          <button id="s6-add-district" class="btn btn-mini add">+ Add district</button>
        </div>`;
    }
    // A district in the draft but silently absent from the priced package (its release input vanished
    // after it was added) — warn, don't let two disagreeing counts sit on the same screen unexplained.
    const gone = v.missing_from_release || [];
    if (gone.length) {
      // `.s6-remove[data-did]` rides wireDraftDetail's existing generic remove wiring — these
      // districts have no package block (hence no normal ✕), so the warning carries its own.
      const items = gone.map((g) => `${esc(g)}${draft ? ` <button class="s6-remove" data-did="${esc(g)}" title="remove from draft">✕</button>` : ""}`).join(", ");
      html += `<div class="q-locked" data-feat="s6-missing-release">⚠ ${gone.length} district(s) in this draft no longer have Stage-5 release data and will NOT be dispatched: ${items}</div>`;
    }
    // #618: representations carrying benchmark provenance (capture source 'benchmark_gt'). These
    // REFUSE the freeze while this is a production dispatch — surfaced here, not raised, so the human
    // can see exactly what to deselect (or opt the whole dispatch in as benchmark).
    const bmReps = v.benchmark_reps || [];
    // #662 decision 4: badge the individual records too, not only this aggregate banner — the banner
    // says WHICH reps block the freeze, but you deselect in the district blocks below, and reading a
    // rec_key off a list to find it in a long block is exactly the manual step this console exists to
    // remove. Badged, never filtered: a pool that silently differs by dispatch type is the kind of
    // invisible scoping epic #617 keeps getting bitten by.
    BM_KEYS = new Set(bmReps.map((b) => `${b.district_id}::${b.rec_key}`));
    if (bmReps.length && v.dispatch_type !== "benchmark") {
      const items = bmReps.map((b) => `${esc(b.district_id)}:<code>${esc(b.rec_key)}</code>`).join(", ");
      html += `<div class="q-locked" data-feat="s6-benchmark-reps">⚠ ${bmReps.length} representation(s) carry benchmark provenance and will BLOCK this freeze: ${items}. Deselect those records, or tick “benchmark dispatch” to run this as a Council Lab A/B on purpose.</div>`;
    }
    const blocks = pkg.districts.map((d) => renderDistrictBlock(d, draft));
    html += `<div class="s6-summary">
        <p><b>${pkg.cost.n_reps}</b> representation(s) across <b>${pkg.districts.length}</b> district(s) ·
           estimated <b>${usd(pkg.cost.total_usd)}</b> <span class="badge badge-neutral">${esc(pkg.cost.provenance)}</span></p>
      </div>${blocks.join("") || `<div class="empty">No districts in this draft yet — "+ Add district" above.</div>`}`;
    det.innerHTML = html;
    wireDraftDetail(v.draft_id, draft);
  }

  function renderDistrictBlock(d, editable) {
    const sends = d.records.filter((r) => r.decision === "send");
    const reps = sends.flatMap((r) => r.reps.map((rep) => repRow(d.district_id, r.rec_key, rep, editable)));
    // #679: benchmark-provenance reps excluded from a production dispatch's DEFAULT selection are
    // HELD server-side, not hidden — render them so the reviewer sees what was excluded and why
    // (#662 decision 4: badged, never filtered). The reason is a server-computed decision field;
    // the client never re-derives provenance (arch-manifest rule).
    const bmHeld = d.records.filter((r) => r.reason === "benchmark-rep:ineligible-for-production");
    const heldRows = bmHeld.map((r) => `<div class="s6-rep muted" data-feat="s6-bm-ineligible">
        <span class="badge badge-red" title="injected curated-GT representation (capture source 'benchmark_gt')">gt:// injected</span>
        <code title="${esc(r.rec_key)}">${esc(r.url || r.rec_key)}</code>
        <span class="muted">held — ineligible for a production dispatch; tick “benchmark dispatch” to re-admit</span>
      </div>`);
    // #691: records held by REQ-116 hub-priority narrowing (server-computed reason, same display
    // rule as the #679 rows above — badged, never hidden). The reviewer is the only party who can
    // see that a labeled "hub" is actually a news feed; this is where they see what it suppressed.
    const hubHeld = d.records.filter((r) => (r.reason || "").startsWith("hub-priority:first-dispatch-narrowed-to:"));
    const hubLabeled = hubHeld.filter((r) => r.label).length;
    if (hubHeld.length) {
      heldRows.push(`<div class="s6-rep muted" data-feat="s6-hub-held-summary">
          <span class="badge badge-warn">hub-priority</span>
          <b>${hubHeld.length}</b> record(s) held — first dispatch narrowed to the labeled hub
          (${hubLabeled} labeled target(s) among them; held reps stay available to the 7→6 back-edge)
        </div>`);
      heldRows.push(...hubHeld.map((r) => `<div class="s6-rep muted" data-feat="s6-hub-held">
          <span class="badge badge-warn" title="held by hub-priority narrowing — a labeled sibling at ≥2× the hub's in-window times would send instead (#691 yield floor)">hub-priority held</span>
          ${r.label ? `<span class="s6-kind">${esc(r.label)}</span>` : ""}
          <code title="${esc(r.rec_key)}">${esc(r.url || r.rec_key)}</code>
        </div>`));
    }
    const remove = editable
      ? `<button class="s6-remove" data-did="${esc(d.district_id)}" title="remove this district from the draft">✕</button>` : "";
    const head = `${esc(d.name || d.district_id)}${d.state ? ` · ${esc(d.state)}` : ""}
        <span class="muted">${esc(d.district_id)} · ${esc(d.topology || "?")} · ${d.n_send_reps} rep(s) · ${usd(d.est_usd)}</span>`;
    return `<div class="s6-dist" data-did="${esc(d.district_id)}">
        <h4>${head} ${remove}</h4>
        ${reps.length ? reps.join("") : `<div class="s6-rep muted">no send-eligible records</div>`}
        ${heldRows.join("")}
      </div>`;
  }

  // #822: does this rep's estimated output exceed the assigned council's ceiling (its weakest
  // member's usable window)? TRI-STATE, and the third state gets its OWN rendering: `null` means
  // un-assessable (an image rep carries no countable clock times), which is NOT "fits". Rendering
  // un-assessable as clean is precisely how the vision tier read as fine while being unmeasured.
  function overflowBadge(rep) {
    if (rep.overflow === true) {
      return `<span class="badge badge-red" data-feat="overflow-badge" data-overflow="true"
        title="estimated output exceeds this council's ceiling (weakest member's usable window) — the call cannot return a complete roster (#822)">output-overflow</span>`;
    }
    if (rep.overflow === null || rep.overflow === undefined) {
      return `<span class="badge badge-warn" data-feat="overflow-badge" data-overflow="unassessable"
        title="output size cannot be assessed for this rep (no countable clock times — binary/image). Not a clean fit: unmeasured (#822)">overflow: un-assessable</span>`;
    }
    return "";
  }

  function repRow(did, recKey, rep, editable) {
    const key = `${recKey}::${rep.file}`;
    const current = rep.councils[0] || "";
    const councilCell = editable
      ? `<select class="s6-council-sel" data-did="${esc(did)}" data-key="${esc(key)}" title="council override">${
          COUNCILS.map((c) => `<option value="${esc(c.id)}" ${c.id === current ? "selected" : ""}>${esc(c.id)}</option>`).join("")}</select>`
      : `<span class="s6-council-fixed">${esc(current)}</span>`;
    return `<div class="s6-rep" data-did="${esc(did)}">
        <span class="s6-kind">${esc(rep.kind)}</span>
        <code class="s6-rep-click" data-did="${esc(did)}" data-reckey="${esc(recKey)}" data-file="${esc(rep.file)}"
              data-kind="${esc(rep.kind)}" title="click to inspect this representation">${esc(rep.file)}</code> →
        ${councilCell}
        ${rep.fidelity_suspect ? `<span class="badge badge-warn">fidelity-suspect</span>` : ""}
        ${overflowBadge(rep)}
        ${BM_KEYS.has(`${did}::${recKey}`) ? `<span class="badge badge-red" title="injected curated-GT representation (capture source 'benchmark_gt') — blocks a production freeze">gt:// injected</span>` : ""}
        <span class="s6-usd">${usd(rep.est_usd)}</span></div>`;
  }

  function wireDraftDetail(draftId, editable) {
    const det = $g("#s6-detail");
    const freeze = $g("#s6-freeze"); if (freeze) freeze.onclick = () => doFreeze(draftId);
    const abandon = $g("#s6-abandon"); if (abandon) abandon.onclick = () => doAbandon(draftId);
    const verified = $g("#s6-verified");
    if (verified) verified.onchange = (e) => draftEdit(draftId, { op: "set_verified_only", verified_only: e.target.checked });
    const dtype = $g("#s6-dispatch-type");
    if (dtype) dtype.onchange = (e) => draftEdit(draftId, { op: "set_dispatch_type", dispatch_type: e.target.checked ? "benchmark" : "production" });
    const addBtn = $g("#s6-add-district"); if (addBtn) addBtn.onclick = () => openAddDistrictPicker(draftId);
    det.querySelectorAll(".s6-remove").forEach((b) => {
      b.onclick = () => draftEdit(draftId, { op: "remove_district", district_id: b.dataset.did });
    });
    det.querySelectorAll(".s6-rep-click").forEach((r) => {
      r.onclick = () => openInspect(r.dataset.did, r.dataset.reckey, r.dataset.file, r.dataset.kind);
    });
    if (editable) {
      det.querySelectorAll(".s6-council-sel").forEach((sel) => {
        sel.onchange = () => {
          const [recKey, file] = sel.dataset.key.split("::");
          draftEdit(draftId, { op: "set_override", district_id: sel.dataset.did, rec_key: recKey, file, council_id: sel.value });
        };
      });
    }
  }

  async function draftEdit(draftId, payload) {
    let v;
    try { v = await api(`/api/dispatch/${draftId}/edit`, postJSON(payload)); }
    catch (e) { alert("Edit failed: " + e.message); return; }
    if (!isCurrent("draft", draftId)) return;   // same staleness rule as openDraft
    DRAFT_VIEW = v;
    renderDraftDetail(v);
    loadList();   // counts on the left may have changed
  }

  async function doFreeze(draftId) {
    if (!confirm("Freeze this draft into an immutable dispatch (gate@6)? No paid extraction happens here — that's Stage 7.")) return;
    const btn = $g("#s6-freeze");
    if (btn) { btn.disabled = true; btn.textContent = "Freezing…"; }
    try {
      const res = await api(`/api/dispatch/${draftId}/freeze`, postJSON({
        actor: "ian", expected_identity: DRAFT_VIEW ? DRAFT_VIEW.preview_identity : null }));
      await loadList();
      openDispatch(res.handoff_id, "handoff");
    } catch (e) {
      if (btn) { btn.disabled = false; btn.textContent = "Freeze dispatch (gate@6)"; }
      if (e.message.startsWith("409")) {
        alert("Freeze blocked: " + e.message + "\n\nReloading the draft with the current release now — review it, then freeze again.");
        openDraft(draftId);
        return;
      }
      alert("Freeze failed: " + e.message);
    }
  }

  async function doAbandon(draftId) {
    const reason = prompt("Abandon this draft?\n\nIt becomes terminal — can't be edited or frozen.\n\nReason (optional):");
    if (reason === null) return;
    try { DRAFT_VIEW = await api(`/api/dispatch/${draftId}/abandon`, postJSON({ actor: "ian", reason })); }
    catch (e) { alert("Abandon failed: " + e.message); return; }
    renderDraftDetail(DRAFT_VIEW);
    loadList();
  }

  // ----------------------------- add-district picker -----------------------------
  async function openAddDistrictPicker(draftId) {
    let cands;
    try { cands = await api(`/api/dispatch/${draftId}/candidates`); }
    catch (e) { alert("Couldn't load candidates: " + e.message); return; }
    renderPickerModal(draftId, cands);
  }

  function renderPickerModal(draftId, cands, filter) {
    filter = filter || { q: "", topology: "", sendOnly: false, heldOnly: false, hideDispatched: false };
    let m = $g("#s6-picker");
    if (!m) { m = document.createElement("div"); m.id = "s6-picker"; m.className = "modal"; document.body.appendChild(m); }
    // Mode-aware count (the old preview flow's effSend): a verified-only draft SENDS only the
    // human-labeled subset, so the picker must show/filter by n_verified — an unlabeled '5 send'
    // district contributes 0 reps to a verified-only draft, and showing '5 send' would silently
    // contradict the draft detail right after adding it.
    const vOnly = !!(DRAFT_VIEW && DRAFT_VIEW.verified_only);
    const effSend = (c) => (vOnly ? c.n_verified : c.n_send);
    const topos = [...new Set(cands.map((c) => c.labeled_topology).filter(Boolean))].sort();
    const shown = cands.filter((c) => {
      if (filter.topology && c.labeled_topology !== filter.topology) return false;
      if (filter.sendOnly && !(effSend(c) > 0)) return false;
      if (filter.heldOnly && !(c.n_hold > 0)) return false;
      if (filter.hideDispatched && c.n_dispatched > 0) return false;
      if (filter.q && !`${c.name || ""} ${c.district_id} ${c.state || ""}`.toLowerCase().includes(filter.q)) return false;
      return true;
    });
    const rows = shown.length
      ? shown.map((c) => {
          const bench = c.is_benchmark ? `<span class="badge badge-accent">benchmark</span>` : "";
          const disp = c.n_dispatched > 0 ? `<span class="badge badge-warn">dispatched</span>` : "";
          // #718: a `gt://` curation artifact counts toward n_send but production can NEVER receive
          // it (the Stage-9 wall). A district whose targets are ALL gt:// used to read as ready —
          // the inverse of the truth. #762: the remedy must match the blocker — Baldwin's real
          // records are HELD tier-C awaiting a gate@5 label, and this badge used to say "needs
          // discovery" for it, contradicting zero_yield_reason's own conclusion for the identical
          // district. Only when nothing held could EVER reach production is discovery the answer.
          let unsendable = "";
          if (c.n_send > 0 && !(c.n_send_production > 0)) {
            unsendable = c.n_production_sendable > 0
              ? `<span class="badge badge-warn" data-feat="benchmark-only" title="${c.n_benchmark_only} target(s) are gt:// curation artifacts — unsendable to production — but ${c.n_production_sendable} held real record(s) await a gate@5 label. Label those first; discovery is not the blocker.">0 sendable now · ${c.n_production_sendable} held — label at gate@5</span>`
              : `<span class="badge badge-red" data-feat="benchmark-only" title="All ${c.n_benchmark_only} of this district's targets are gt:// curation artifacts — unsendable to production, and nothing held could reach it either. It needs discovery, not dispatch.">0 sendable · ${c.n_benchmark_only} benchmark-only</span>`;
          }
          return `<label class="add-item">
              <input type="checkbox" value="${esc(c.district_id)}"/>
              <span class="q-sname">${esc(c.name || c.district_id)}</span>
              <span class="q-smeta">${esc(c.state || "?")} · ${effSend(c)} ${vOnly ? "verified" : "send"} · ${esc(c.labeled_topology || "?")}</span>
              ${disp}${bench}${unsendable}</label>`;
        }).join("")
      : `<div class="empty">No eligible districts match the filter.</div>`;
    m.innerHTML = `<div class="modal-card">
        <div class="modal-head"><h2>Add district(s) to ${esc(draftId)}</h2><button class="btn btn-secondary" data-x>Close</button></div>
        <div class="modal-body add-body">
          <div class="s6-filters">
            <input id="s6-pick-q" class="s6-fi" type="search" placeholder="Filter name / id / state…" value="${esc(filter.q)}"/>
            <select id="s6-pick-topo" class="s6-fi"><option value="">All topologies</option>${
              topos.map((t) => `<option value="${esc(t)}" ${filter.topology === t ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
            <label class="s6-fl"><input type="checkbox" id="s6-pick-sendonly" ${filter.sendOnly ? "checked" : ""}/> has ${vOnly ? "verified" : "send"}</label>
            <label class="s6-fl"><input type="checkbox" id="s6-pick-heldonly" ${filter.heldOnly ? "checked" : ""}/> has held</label>
            <label class="s6-fl"><input type="checkbox" id="s6-pick-hidedispatched" ${filter.hideDispatched ? "checked" : ""}/> hide already-dispatched</label>
          </div>
          ${rows}
        </div>
        <div class="modal-foot"><button class="btn btn-primary" data-ok>Add selected</button></div>
      </div>`;
    m.classList.remove("hidden");
    const close = () => m.classList.add("hidden");
    m.querySelector("[data-x]").onclick = close;
    m.onclick = (e) => { if (e.target === m) close(); };
    const rerender = () => {
      const next = {
        q: m.querySelector("#s6-pick-q").value.toLowerCase(),
        topology: m.querySelector("#s6-pick-topo").value,
        sendOnly: m.querySelector("#s6-pick-sendonly").checked,
        heldOnly: m.querySelector("#s6-pick-heldonly").checked,
        hideDispatched: m.querySelector("#s6-pick-hidedispatched").checked,
      };
      renderPickerModal(draftId, cands, next);
    };
    m.querySelector("#s6-pick-q").oninput = rerender;
    m.querySelector("#s6-pick-topo").onchange = rerender;
    m.querySelector("#s6-pick-sendonly").onchange = rerender;
    m.querySelector("#s6-pick-heldonly").onchange = rerender;
    m.querySelector("#s6-pick-hidedispatched").onchange = rerender;
    m.querySelector("[data-ok]").onclick = async () => {
      // scoped to .add-item checkboxes only — the modal's own filter checkboxes (send/held/hide-
      // dispatched) live in the same DOM and would otherwise get swept in by a bare :checked query,
      // each contributing the browser's default checkbox value "on" as a bogus "district_id".
      const picks = [...m.querySelectorAll(".add-item input[type=checkbox]:checked")].map((i) => i.value);
      close();
      for (const did of picks) {
        try { await api(`/api/dispatch/${draftId}/edit`, postJSON({ op: "add_district", district_id: did })); }
        catch (e) { alert(`Couldn't add ${did}: ` + e.message); }
      }
      openDraft(draftId);
      loadList();
    };
  }

  // ----------------------------- frozen/handoff detail (read-only) -----------------------------
  function renderHandoffDetail(h) {
    const det = $g("#s6-detail");
    const pkg = h.package || { districts: [], cost: { n_reps: 0, total_usd: 0, provenance: "unknown" } };
    const origin = originNote(h.origin);
    const done = h.n_extracted >= h.n_districts && h.n_districts > 0;
    const extractControl = done
      ? `<span class="badge badge-neutral" data-feat="s6-run-extraction" title="all districts extracted for this handoff">✓ extracted</span>`
      : `<button class="btn btn-secondary btn-mini s6-extract" data-feat="s6-run-extraction" data-hash="${esc(h.handoff_hash)}" ${h.running ? "disabled" : ""}>${h.running ? "running…" : (h.n_extracted > 0 ? "Resume extraction" : "Run extraction ▶")}</button>`;
    const blocks = pkg.districts.map((d) => renderDistrictBlock(d, false));
    det.innerHTML = `<div class="q-detail-head">
        <div><h2>${esc(h.handoff_id)} <span class="badge badge-success">${esc(h.status)}</span>${h.verified_only ? ` <span class="badge badge-accent">verified only</span>` : ""}${h.dispatch_type === "benchmark" ? ` <span class="badge badge-accent" data-feat="s6-dispatch-type">benchmark</span>` : ""}</h2>
          <div class="q-sub">${pkg.cost.n_reps} rep(s) · ${pkg.districts.length} district(s) · ${usd(pkg.cost.total_usd)} <span class="badge badge-neutral">${esc(pkg.cost.provenance)}</span> · ${esc(fmt(h.created_at))}</div></div>
        <div class="q-actions">${extractControl}</div></div>
      ${origin}${blocks.join("")}`;
    det.querySelectorAll(".s6-rep-click").forEach((r) => {
      r.onclick = () => openInspect(r.dataset.did, r.dataset.reckey, r.dataset.file, r.dataset.kind);
    });
    const btn = det.querySelector(".s6-extract");
    if (btn) btn.onclick = () => runExtraction(h.handoff_hash);
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

  // #152: fire the extraction background job, then poll status into the detail pane until done.
  async function runExtraction(hash) {
    if (!confirm("Run the paid Stage-7 council extraction for this dispatched handoff? It re-enters the pipeline at Stage 7 (budget-gated, resumable — already-extracted districts are skipped).")) return;
    try { await api(`/api/extract/${hash}/run`, postJSON({ actor: "ian" })); }
    catch (e) { alert("Couldn't start extraction: " + e.message); return; }
    if (CURRENT && CURRENT.kind === "handoff") openHandoff(CURRENT.id);   // reflect "running…" immediately
    loadList();
    pollExtraction(hash);
  }

  async function pollExtraction(hash) {
    let st;
    try { st = await api(`/api/extract/run/${hash}`); }
    catch (_) { return; }
    if (st.state === "running") { setTimeout(() => pollExtraction(hash), 2500); return; }
    loadList();
    if (CURRENT && CURRENT.kind === "handoff") openHandoff(CURRENT.id);   // refresh counts/labels on terminal state
    if (st.state === "done") alert(`Extraction complete: ${st.summary ? st.summary.n_districts : "?"} district(s) this run. Review at gate@7.`);
    else if (st.state === "partial") {
      const s = st.summary || {}, failed = (s.failed || []).map(f => f.district_id).join(", ");
      alert(`Extraction finished PARTIAL: ${s.n_districts || 0} district(s) extracted, ${s.n_failed || 0} failed (${failed}). The good districts are durable; re-run to retry the failed ones. Review at gate@7.`);
    }
    else if (st.state === "halted") alert("Extraction halted (control failure): " + (st.error || ""));
    else if (st.state === "error") alert("Extraction error: " + (st.error || ""));
  }
})();
