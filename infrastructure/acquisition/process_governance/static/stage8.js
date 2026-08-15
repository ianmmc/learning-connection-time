"use strict";
// Stage 8 (Aggregate) console view — gate@8, the "closing argument" (STAGE8_AGGREGATE_DESIGN §2).
// Review one district's WHOLE per-band determination and render, for each band: the claim, the sampling
// sufficiency, the dereferenced evidence (URL / reader / capture / models / verbatim council quote), and
// the negative space — then approve (which FIRES the Stage-9 write, #682) or send it back (§2e).
//
// MUST-BE-VISIBLE features (regression-guarded in the Playwright/DOM check — do not silently drop):
//   F1 per-band determination: gross minutes + start–end + method            [data-feat="claim"]
//   F2 per-band sampling: n_sampled/n_total + coverage% + plurality%         [data-feat="sampling"]
//   F3 per-school evidence: source URL, reader, models, verbatim quote       [data-feat="evidence"]
//   F4 capture time(s)                                                       [data-feat="capture"]
//   F5 negative space: unresolved / contamination / unsatisfied / gaps       [data-feat="negative-space"]
//   F6 decision status + Approve / Send-back verdict controls                [data-feat="verdict"]
//   F7 per-school override control (required reason)                         [data-feat="override"]
//   F8 what the Stage-9 write DID after the approval (#682)                   [data-feat="incorporation"]
//   F9 where a send-back GOES — the 8→1 / 8→6 routing controls (#689)         [data-feat="send-back-route"]
// Vanilla JS on the shared window.LCT helpers; reuses q-*/badge/btn classes for visual consistency.
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const { esc, postJSON, api, safeUrl } = window.LCT;
  const pct = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
  // REVIEWED_FP: the fingerprint of the closing argument the reviewer is LOOKING at (from the GET).
  // Echoed to the decision POST, which 409s if the live facts moved after page-load — the verdict can
  // only ever attach to the picture the human actually read (PR #252 review round).
  let inited = false, CURRENT = null, REVIEWED_FP = null, LAST_BANDS = null;

  window.initStage8 = function () {
    if (!inited) { inited = true; renderShell(); }
    loadDistricts();                                     // re-fetch on every show (badges reflect decisions)
  };

  function renderShell() {
    $g("#stage8view").innerHTML = `
      <nav class="col col-tree q-left" aria-label="Districts awaiting gate@8">
        <div class="q-left-head"><h3>Closing arguments · gate@8</h3></div>
        <div id="s8-list" class="q-list"><div class="empty">Loading…</div></div>
      </nav>
      <section id="s8-detail" class="col col-center"><div class="empty">Select a district to review its closing argument.</div></section>`;
  }

  // ----------------------------- left pane -----------------------------
  async function loadDistricts() {
    const list = $g("#s8-list");
    let ds;
    try { ds = await api("/api/aggregate/districts"); }
    catch (e) { list.innerHTML = `<div class="empty err">Couldn't load: ${esc(e.message)}<br/>Is Docker (governance DB) up?</div>`; return; }
    // #660: a withheld district never appears in the queue, so a human could not reach the gate@8
    // escape hatch (band_exclusion) that REQ-169 names as the way to clear a stale injected rep.
    // Best-effort — a failure here must never blank the queue itself.
    let withheld = [];
    try { withheld = await api("/api/aggregate/withheld"); } catch (e) { withheld = []; }
    if (!ds.length && !withheld.length) { list.innerHTML = `<div class="empty">No districts are ready for gate@8 yet — a district appears once it has extracted facts and its gate@7 request loop is quiet.</div>`; return; }
    list.innerHTML = "";
    if (!ds.length) list.innerHTML = `<div class="empty">No districts are ready for gate@8 right now.</div>`;
    ds.forEach((d) => list.appendChild(districtRow(d)));
    if (withheld.length) list.appendChild(withheldSection(withheld));
  }

  function withheldSection(ws) {
    const wrap = document.createElement("div");
    wrap.className = "q-withheld";
    wrap.innerHTML = `<div class="q-left-head"><h3>Withheld · benchmark provenance (${ws.length})</h3></div>
      <div class="q-batch-meta q-withheld-note">These hold at least one fact traced to an injected <code>gt://</code> representation, so a Stage-9 write is refused. Open one and strike the stale evidence at gate@8 (band exclusion) to clear it — the wall keys on the work, not the district.</div>`;
    ws.forEach((d) => {
      const row = districtRow(d);
      row.classList.add("q-batch-muted");
      wrap.appendChild(row);
    });
    return wrap;
  }

  function dispositionBadge(disp) {
    if (disp === "approved") return `<span class="badge badge-success">approved</span>`;
    if (disp === "sent_back") return `<span class="badge badge-red">sent back</span>`;
    return `<span class="badge badge-neutral">pending</span>`;
  }

  function districtRow(d) {
    const el = document.createElement("div");
    el.className = "q-batch" + (d.district_id === CURRENT ? " active" : "");
    el.dataset.id = d.district_id;
    el.innerHTML = `<div class="q-batch-top"><span class="q-batch-id">${esc(d.name || d.district_id)}</span>${dispositionBadge(d.disposition)}</div>
      <div class="q-batch-meta">${esc(d.district_id)}${d.state ? " · " + esc(d.state) : ""} · ${d.n_accepted} school${d.n_accepted === 1 ? "" : "s"} · ${d.n_unresolved} unresolved</div>`;
    el.onclick = () => openDistrict(d.district_id);
    return el;
  }

  // ----------------------------- detail -----------------------------
  async function openDistrict(did) {
    CURRENT = did;
    document.querySelectorAll("#s8-list .q-batch").forEach((e) => e.classList.toggle("active", e.dataset.id === did));
    const det = $g("#s8-detail");
    det.innerHTML = `<div class="empty">Loading ${esc(did)}…</div>`;
    let x;
    try { x = await api(`/api/aggregate/district/${did}`); }
    catch (e) { det.innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
    REVIEWED_FP = x.fingerprint || null;   // the picture the reviewer is now looking at
    LAST_BANDS = (x.closing_argument || {}).bands || {};   // #499: slot lookups for the disposition prompts
    det.innerHTML = renderDetail(x);
    wire(det, did);
  }

  function renderDetail(x) {
    const ca = x.closing_argument, dec = x.decision || {};
    const bands = ca.bands || {};
    const order = ["elementary", "middle", "high"].filter((b) => bands[b]);
    return `
      ${renderHeader(ca, dec, x.incorporation)}
      ${renderVerdict(dec)}
      ${renderSendBackRoute(dec, x.send_back_routing)}
      <div class="s8-bands">${order.map((b) => renderBand(b, bands[b])).join("") || `<div class="empty">No accepted band facts.</div>`}</div>
      ${renderDenominatorCriteria((ca.provenance || {}).denominator)}
      ${renderNegativeSpace(ca.negative_space || {}, ca.capture_events || [])}`;
  }

  function renderHeader(ca, dec, inc) {
    let status = `<span class="badge badge-neutral">not yet decided</span>`;
    if (dec.decided) {
      status = dispositionBadge(dec.disposition);
      if (dec.is_stale) status += ` <span class="badge badge-warn" title="A re-extraction changed the facts since this decision — re-review before it can authorize a write.">stale — re-review</span>`;
      // #682: the write is a SECOND record beside the decision — an approved district that production
      // never received must not read as done. Only shown once a decision exists (before that there is
      // nothing a write could have acted on).
      if (dec.disposition === "approved") status += incorporationBadge(inc);
    }
    return `<div class="s8-head"><h2 style="margin:0">${esc(ca.district_id)}</h2> ${status}</div>`;
  }

  // F6 — the verdict controls
  function renderVerdict(dec) {
    const approvedNote = dec.is_approved
      ? `<span class="s8-note">Approved — Stage 9 writes all bands (the badge above says whether it did).</span>` : "";
    return `<div class="s8-verdict" data-feat="verdict">
      <button class="btn btn-primary" data-decide="approved">Approve district → Stage 9</button>
      <button class="btn" data-decide="sent_back">Send back (needs a reason)</button>
      ${approvedNote}
      <p class="s8-note">All-or-nothing at the district (§2e): approval publishes every band together; an unsatisfied band means send it back.</p>
    </div>`;
  }

  // F9 (#689) — where a send-back actually GOES. The reason a reviewer types IS the routing
  // instruction; until now nothing consumed it, so a sent-back district just sat at stage 8. The
  // human still picks the route (or neither) — the console executes the choice and records it.
  function renderSendBackRoute(dec, routing) {
    if (!dec.decided || dec.disposition !== "sent_back") return "";
    if (routing) {
      return `<div class="s8-verdict" data-feat="send-back-route">
        <span class="badge badge-success">re-routed ${esc(routing.route)} → ${esc(routing.artifact || "")}</span>
        <span class="s8-note">${esc(routing.note || "")}</span></div>`;
    }
    return `<div class="s8-verdict" data-feat="send-back-route">
      <span class="badge badge-red">sent back — not re-routed</span>
      <button class="btn" data-route="8-&gt;1">Re-discover → Stage 1 follow-up batch</button>
      <button class="btn" data-route="8-&gt;6">Re-dispatch → new gate@6 draft</button>
      <p class="s8-note">8→1 goes looking for better/newer evidence (a gate@1-reviewable draft batch, never auto-flowed); 8→6 keeps the evidence and picks different representations. Preview first — nothing fires on send-back by itself.</p>
    </div>`;
  }

  // #253: the denominator-criteria disclaimer (Ian, 2026-07-14) — the auditor must see WHAT the
  // coverage denominators count, since virtual/alternative/adult campuses are deliberately absent.
  function renderDenominatorCriteria(d) {
    if (!d || !d.criteria) return "";
    return `<p class="s8-note" data-feat="denominator-criteria">Denominator criteria: ${esc(d.criteria)}${d.source === "band_roster" && d.nces_year ? ` <span class="s8-muted">(live NCES ccd_sch ${esc(d.nces_year)})</span>` : d.source === "nces_level" ? ` <span class="s8-muted">(clean-LEVEL counts — live roster unavailable)</span>` : ""}</p>`;
  }

  function renderBand(band, b) {
    const s = b.sampling || {};
    // #253: the denominator's own provenance rides beside the coverage stat — a band-SERVING count
    // (a K-8 counts toward middle) split by source, with the old clean-LEVEL count kept visible
    // when it differs (the Santa Fe 4-of-2 → 4-of-9 correction must be legible, not silent).
    const d = s.denominator || {};
    const denomDetail = d.source === "band_roster" && d.by_source
      ? ` <span class="s8-muted" data-feat="denominator-provenance">(${d.by_source.level_clean} by LEVEL + ${d.by_source.grade_span} by grade span${d.by_source.level_override ? ` + ${d.by_source.level_override} reclassified (#498)` : ""}${s.n_total_level_only != null && s.n_total_level_only !== s.n_total ? `; LEVEL alone read ${s.n_total_level_only}` : ""})</span>`
      : d.source === "nces_level"
      ? ` <span class="s8-muted" data-feat="denominator-provenance">(clean-LEVEL count)</span>` : "";
    return `<section class="s8-band">
      <div class="s8-band-head" data-feat="claim">
        <h3>${esc(band)}</h3>
        ${b.satisfied && b.satisfied.satisfied ? `<span class="badge badge-success" data-feat="band-satisfied" title="REQ-149: confident determination (basis: ${esc(b.satisfied.basis)}) — follow-up spend for this band is suppressed">satisfied · ${esc(b.satisfied.basis)}</span>` : ""}
        <span class="s8-claim"><strong>${b.gross_minutes} min/day</strong> · ${b.start_time && b.end_time ? `${esc(b.start_time)}–${esc(b.end_time)}` : `<span class="s8-muted" title="#627: a mean_tiebreak value is the average of schools with distinct schedules — it matches no single school's start/end, so no representative times are shown. Per-school times are in the roster below.">synthesized average — no single schedule</span>`} · <span class="s8-method">${esc(b.method)}</span></span>
      </div>
      <div class="s8-sampling" data-feat="sampling">
        Sampled <strong>${s.n_sampled}</strong> of <strong>${s.n_total == null ? "?" : s.n_total}</strong> schools${denomDetail} ·
        coverage ${pct(s.coverage)} · school agreement (plurality) ${pct(s.plurality_share)}
      </div>
      ${s.n_outside_pool > 0 && s.n_total != null ? `<p class="s8-note" data-feat="pool-gap">⚠ <strong>${s.n_outside_pool}</strong> of the ${s.n_total} schools in this denominator sit outside this band's Stage-1 sampling pool (queue-time snapshot) — placed in another band by anti-dilution (a K-8 serving middle sits in elementary's pool) and/or dropped by the ≤12/band cap — so discovery and follow-up never target them for this band. Indirect evidence (a district-wide hub page, a human add) can still fill them; any left unfilled inherit this band's modal minutes via the Stage-9 tie rule (#696).</p>` : ""}
      ${renderSlots(band, b)}
      <table class="s8-schools"><thead><tr><th>School</th><th>Times</th><th>Gross</th><th>Models</th><th>Evidence</th><th></th></tr></thead>
        <tbody>${(b.schools || []).map((sc) => renderSchool(sc, band)).join("")}</tbody></table>
      <button class="btn btn-small" data-feat="human-add" data-ha-add data-band="${esc(band)}">Add school by hand (cited — last resort, #474)</button>
    </section>`;
  }

  // #499 (REQ-144): the band's roster SLOTS — the live NCES roster crossed with the accepted facts,
  // so the gap is identified schools, not count arithmetic. Filled slots are the table rows below;
  // this strip names the slots never heard from, ambiguous matches awaiting a disposition (PR-B),
  // and unmatched-extras (a fact naming a school NCES doesn't list — the roster can be wrong; the
  // overlay is never a cage). Charter slots carry the REQ-060 tag (the #243 Structure-C surface).
  function renderSlots(band, b) {
    const st = b.slot_stats, slots = b.slots || [], extras = b.slot_extras || [];
    if (!st) return "";
    const unfilled = slots.filter((s) => s.slot_state === "unfilled" && !(s.match && s.match.confidence === "ambiguous"));
    const projected = slots.filter((s) => s.slot_state === "projected");
    const ambiguous = slots.filter((s) => s.match && s.match.confidence === "ambiguous");
    const chip = (s) =>
      `<span class="s8-slot s8-slot-unfilled" data-feat="slot-unfilled" title="no accepted fact matches this NCES roster school">${esc(s.roster_school)}${s.is_charter === "Yes" ? ` <span class="s8-slot-charter" title="NCES charter (REQ-060: tagged, never excluded)">ch</span>` : ""}${s.gslo && s.gshi ? ` <span class="s8-muted">${esc(s.gslo)}–${esc(s.gshi)}</span>` : ""}</span>`;
    const unfilledRow = unfilled.length
      ? `<div class="s8-slot-row">Never heard from: ${unfilled.map(chip).join(" ")}</div>` : "";
    // #499 REQ-145: an ambiguous fact gets a Resolve (assign to ONE candidate) + Not-this-slot
    // (reject a candidate) pair; the projection refuses to guess, the human decides.
    const ambRow = ambiguous.length
      ? `<div class="s8-slot-row">Ambiguous match: ${[...new Set(ambiguous.map((s) => s.match.school_display))].map((n) => `<span class="s8-slot s8-slot-ambiguous" data-feat="slot-ambiguous">${esc(n)}</span>
          <button class="btn btn-small" data-feat="slot-assign" data-slot-assign data-band="${esc(band)}" data-school="${esc(n)}">Resolve…</button>
          <button class="btn btn-small" data-feat="slot-reject" data-slot-reject data-band="${esc(band)}" data-school="${esc(n)}">Not a slot…</button>`).join(" ")} — one extracted name matches several roster schools; assign it or reject candidates.</div>` : "";
    // #499 REQ-145: an extra can be assigned to an unfilled slot (a name NCES spells differently)
    // or confirmed REAL (the escape hatch: NCES missed the school; denominator +1). The Stage-2
    // discovery-intent hint says which school's query surfaced the page it came from.
    // Review round 2: a displaced or duplicate extra is NOT "not in NCES" — say why it's here.
    // displaced_by: its slot was claimed by a human assign for another fact (review THAT assign,
    // don't re-assign this one blind). duplicate_vote: a second fact with the identical key (a
    // hand-add duplicating a council fact) — retire the hand-add, no assign/confirm affordances.
    const extraRow = extras.length
      ? `<div class="s8-slot-row">Not in NCES roster: ${extras.map((x) => x.confidence === "duplicate_vote"
          ? `<span class="s8-slot s8-slot-extra" data-feat="slot-extra-duplicate" title="a second fact with the same normalized name as the slot's current match — a duplicate vote (likely a hand-add duplicating a council fact); retire one of the two">${esc(x.school_display)} <span class="s8-muted">duplicate of the slot's current fact</span></span>`
          : `<span class="s8-slot s8-slot-extra" data-feat="slot-extra" title="extracted fact matching no roster school — NCES may be wrong, or the name may need a disposition">${esc(x.school_display)}</span>${x.displaced_by ? ` <span class="s8-muted" data-feat="slot-extra-displaced" title="this fact exact-matched its roster slot, but a human assign bound a different fact there — review that assign before re-disposing this one">(displaced by the assign carrying “${esc(x.displaced_by)}”)</span>` : ""}${(x.intent_schools || []).length ? ` <span class="s8-muted" data-feat="slot-intent-hint" title="Stage-2 discovery intent: the page this fact came from was found by querying for these roster schools">(found via ${x.intent_schools.map(esc).join(", ")})</span>` : ""}
          <button class="btn btn-small" data-feat="slot-assign" data-slot-assign data-band="${esc(band)}" data-school="${esc(x.school_display)}">Assign to slot…</button>
          <button class="btn btn-small" data-feat="slot-extra-confirm" data-slot-confirm data-band="${esc(band)}" data-school="${esc(x.school_display)}">Confirm real (not in NCES)</button>`).join(" ")}</div>` : "";
    // #499 REQ-146: the band-grain fact — a blanket statement lives on the BAND, votes once,
    // and projects onto the slots never individually heard from (a visible third state).
    const bf = b.band_fact;
    const bfRow = bf
      ? `<div class="s8-slot-row" data-feat="band-fact">Band-level statement: <strong>“${esc(bf.school_display)}”</strong> ${esc(bf.start_time)}–${esc(bf.end_time)} (${esc(bf.gross)} min)${bf.school_year ? ` <span class="s8-muted">${esc(bf.school_year)}</span>` : ""} — one vote in the mode${(bf.projection || {}).n_projected ? `, projected onto ${bf.projection.n_projected} unheard slot(s)` : ""}${(bf.campuses || []).length ? `; names campuses: ${bf.campuses.map(esc).join(", ")}` : ""}.</div>` : "";
    const projRow = projected.length
      ? `<div class="s8-slot-row">Covered by the statement (not individually observed): ${projected.map((s) => `<span class="s8-slot s8-slot-projected" data-feat="slot-projected" title="no direct fact — the band-level statement claims this school">${esc(s.roster_school)}</span>`).join(" ")}</div>` : "";
    return `<div class="s8-slots" data-feat="slot-view">
      <div data-feat="slot-stats"><span data-feat="slot-filled">${st.n_filled}</span> of ${st.n_slots} roster slots filled${st.n_projected ? ` · ${st.n_projected} projected` : ""}${st.n_ambiguous ? ` · ${st.n_ambiguous} ambiguous` : ""}${extras.length ? ` · ${extras.length} extra` : ""} <span class="s8-muted">(slot coverage ${pct(st.slot_coverage)})</span></div>
      ${bfRow}${unfilledRow}${ambRow}${projRow}${extraRow}
    </div>`;
  }

  function renderSchool(sc, band) {
    const ev = sc.evidence, ce = sc.council_evidence, ov = sc.human_override;
    // safeUrl gates the raw href (PR #252 review round — the settings.js javascript:-URI fix, reused):
    // a stored non-http(s) URL renders as visible plain text, never a clickable link.
    const url = ev && ev.url
      ? (safeUrl(ev.url)
          ? `<a href="${esc(ev.url)}" target="_blank" rel="noopener">${esc(shortUrl(ev.url))}</a>`
          : `<span class="s8-muted">${esc(shortUrl(ev.url))}</span>`)
      : `<span class="s8-muted">no source link</span>`;
    const reader = ev && ev.source_file ? ` · read via ${esc(ev.source_file)}` : "";
    const quote = ce && ce.quote ? `<div class="s8-quote" data-feat="evidence">“${esc(ce.quote)}”${ce.locus ? ` <span class="s8-muted">(${esc(ce.locus)})</span>` : ""}</div>` : "";
    // Three-state agreement (PR #252 review round): true = >=2 models read the same stated number;
    // false = they read different ones; null = a single model read it — honest "single source", never
    // implied agreement.
    const statedCaveat = ce && ce.stated_minutes_agree === false ? " (models disagree)"
      : ce && ce.stated_minutes_agree == null ? " (single source)" : "";
    const stated = ce && ce.stated_minutes != null
      ? `<div class="s8-muted">page states ${ce.stated_minutes} min${statedCaveat} — corroboration</div>` : "";
    // The Times/Gross columns show the OVERRIDE-EFFECTIVE value (what the band mode now uses).
    // `override_applied`/`override_error` are SERVER-computed (one derivation, closing_argument.py) —
    // the console never re-derives override state from raw fields (15c67c4 review). An applied override
    // renders the WHOLE times/gross cell in the override treatment (not just a trailing glyph), so a
    // reviewer scanning the column can't mistake a human correction for a council reading; an invalid
    // stored override renders a loud warning and the council values stand.
    const applied = !!sc.override_applied;
    const ovErr = sc.override_error
      ? `<div class="s8-override-error" data-feat="override-error">⚠ override invalid (${esc(sc.override_error.replace("override_", ""))}) — council reading shown; re-enter valid HH:MM times</div>` : "";
    const overrideMark = ov
      ? `<div class="s8-override" data-feat="override-applied">✎ human override${applied
          ? ` (council read ${esc(sc.council_start_time)}–${esc(sc.council_end_time)}, ${esc(sc.council_gross)} min)` : ""} — ${esc(ov.reason || ov.note || "")}</div>` : "";
    // #254: the school year the page ITSELF stated (council consensus reading) — a muted chip
    // beside the times; absent for pre-v3 facts and pages that don't print one (the honest null).
    const yr = sc.school_year
      ? ` <span class="s8-muted s8-year-chip" data-feat="school-year" title="school year as stated on the page (council consensus)">${esc(sc.school_year)}</span>` : "";
    const times = `${esc(sc.start_time)}–${esc(sc.end_time)}`;
    // #257: an excluded school renders struck-through WITH its reason — a recorded, auditable human
    // decision (out of the mode/count, never out of sight). The action flips to Restore.
    const excl = sc.excluded
      ? `<div class="s8-excluded-note" data-feat="excluded-reason">⊘ excluded from ${esc(band)} — ${esc(sc.excluded.reason)} (${esc(sc.excluded.actor)})</div>` : "";
    // #474: a hand-entered school is visibly tagged with its REQUIRED citation — single-source, no
    // council behind it, so the tag + source must be impossible to miss in the record and receipt.
    const humanAdd = sc.human_added
      ? `<div class="s8-human-added" data-feat="human-added">✚ human-added (${esc(sc.human_added.actor)}) — source: ${safeUrl(sc.human_added.source_url) ? `<a href="${esc(sc.human_added.source_url)}" target="_blank" rel="noopener">${esc(shortUrl(sc.human_added.source_url))}</a>` : esc(sc.human_added.source_url)} — ${esc(sc.human_added.reason)}</div>` : "";
    // #253: a combined-scope name is a GROUP description counted as one pseudo-school — flagged
    // loudly (it distorts the mode + n_sampled) but it KEEPS its vote until the reviewer disposes
    // (exclude via #257 when redundant; the roster-template slot-projection is the future home).
    const cs = sc.combined_scope
      ? `<div class="s8-combined-scope" data-feat="combined-scope">⧉ combined-scope name (${esc(csKind(sc.combined_scope.kind))}${csSource(sc.combined_scope.source)})${(sc.combined_scope.campuses || []).length ? ` — resolves to: ${sc.combined_scope.campuses.map(esc).join(", ")}` : ""} — a group description counted as ONE school; exclude (#257) if redundant with individual rows</div>` : "";
    const action = sc.excluded
      ? `<button class="btn btn-small" data-feat="restore-exclusion" data-restore-excl data-band="${esc(band)}" data-school="${esc(sc.school)}">Restore</button>`
      : sc.human_added
      ? `<button class="btn btn-small" data-feat="human-add-remove" data-ha-remove data-band="${esc(band)}" data-school="${esc(sc.school)}">Remove</button>`
      : `<button class="btn btn-small" data-feat="override" ${sc.fact_id == null ? "disabled" : `data-override="${esc(sc.fact_id)}"`} data-school="${esc(sc.school)}">Override</button>
         <button class="btn btn-small" data-feat="exclude" data-exclude data-band="${esc(band)}" data-school="${esc(sc.school)}">Exclude</button>`;
    return `<tr${sc.excluded ? ' class="s8-excluded" data-feat="excluded-row"' : ""}>
      <td>${esc(sc.school)}</td>
      <td>${applied ? `<span class="s8-override" title="human override — council read ${esc(sc.council_start_time)}–${esc(sc.council_end_time)}">✎ ${times}</span>` : times}${yr}</td>
      <td>${applied ? `<span class="s8-override">${esc(sc.gross)}</span>` : esc(sc.gross)}</td>
      <td class="s8-muted">${(sc.models || []).map((m) => esc(m.split("/").pop())).join(", ")}</td>
      <td data-feat="evidence">${url}${reader}${quote}${stated}${overrideMark}${ovErr}${cs}${excl}${humanAdd}</td>
      <td>${action}</td>
    </tr>`;
  }

  // F5 — the honest negative space
  function renderNegativeSpace(ns, captures) {
    const rows = [];
    if ((ns.unsatisfied_bands || []).length)
      rows.push(`<li><strong>Unsatisfied bands:</strong> ${ns.unsatisfied_bands.map(esc).join(", ")} — a district can't be approved until every claimed band has confident minutes (send back → 8→1).</li>`);
    if (ns.contamination)
      rows.push(`<li><strong>Contamination flag (#237):</strong> a single-school LEA with ${ns.contamination.n_distinct_schools} distinct schools — ${ns.contamination.distinct_schools.map(esc).join(", ")}.</li>`);
    if ((ns.unresolved || []).length)
      rows.push(`<li><strong>${ns.unresolved.length} unresolved</strong> (band, school) pair(s) — the council couldn't reach cross-family consensus.</li>`);
    if ((ns.degenerate_school_facts || []).length)
      rows.push(`<li><strong>${ns.degenerate_school_facts.length} degenerate school name(s)</strong> dropped (#245).</li>`);
    // One renderer for the simple flag lists (PR #500 review round: the idiom was copy-pasted per
    // flag type — a bug in the shared shape (escaping, separator, empty-guard) had to be fixed N
    // times). Each call site keeps its feat token as a LITERAL: the UI-visibility regression test
    // greps for it.
    const pushFlag = (feat, label, items, itemFn, trailing = ".") => {
      if ((items || []).length)
        rows.push(`<li data-feat="${feat}"><strong>${label}</strong> ${items.map(itemFn).join("; ")}${trailing}</li>`);
    };
    pushFlag("band-exclusions", "Human band-exclusions (#257):", ns.band_exclusions,
      (e) => `${esc(e.school)} ⊘ ${esc(e.band)} — ${esc(e.reason)}`);
    if ((ns.recoverable_bands || []).length)
      rows.push(`<li data-feat="recoverable-band"><strong>Recoverable band(s) (#473):</strong> ${ns.recoverable_bands.map((r) => {
        const rep = (r.from_reps || [])[0] || {};
        return `<em>${esc(r.band)}</em> is empty but sibling bands were extracted from ${esc(shortUrl(rep.url || rep.rec_key || "a captured rep"))} — the data may be in that doc.
          <button class="btn btn-small" data-feat="recover-band" data-recover data-band="${esc(r.band)}" data-reckey="${esc(rep.rec_key)}" data-file="${esc(rep.source_file || "")}">Re-extract for ${esc(r.band)}</button>
          <button class="btn btn-small" data-feat="human-add" data-ha-add data-band="${esc(r.band)}">Add by hand (fallback, #474)</button>`;
      }).join("<br>")}</li>`);
    // #498: the intermediate carve-out — an NCES 'Middle' tag on an upper-elementary span is
    // reclassified by rule; every application is shown (never a silent reclassification).
    pushFlag("level-override", "Grade-band overrides (#498):", ns.level_overrides,
      (o) => `${esc(o.school)} counted as ${esc(o.band)} (NCES says ${esc(o.nces_level)}, but grades ${esc(o.gslo)}–${esc(o.gshi)} is an intermediate/upper-elementary span)`);
    // #498 staleness (PR #500 review round): the Stage-1 roster snapshot disagrees with the live
    // classification for this school — the batch predates the carve-out; re-queue refreshes it.
    pushFlag("stale-roster-band", "Stale Stage-1 band placements (#498):", ns.stale_roster_bands,
      (s) => `${esc(s.school)} was queued under ${esc(s.stage1_band)} but the live classification says ${esc(s.live_band)} (NCES ${esc(s.nces_level)}, grades ${esc(s.gslo)}–${esc(s.gshi)})`,
      " — this batch predates the #498 ruling; coverage math uses the live roster, the Stage-1 snapshot refreshes on re-queue.");
    pushFlag("combined-scope-facts", "Combined-scope facts (#253):", ns.combined_scope_facts,
      (m) => `${esc(m.school)} in ${esc(m.band)} (${esc(csKind(m.kind))}${csSource(m.source)}${(m.campuses || []).length ? `: ${m.campuses.map(esc).join(", ")}` : ""})${m.excluded ? " — already excluded" : ""}`,
      " — group descriptions counted as one school each; still voting in the mode until disposed.");
    // #254: year-superseded facts — WHY the stale rows left the mode (both years, both grosses).
    pushFlag("superseded-facts", "Year-superseded facts (#254):", ns.superseded_facts,
      (f) => `${esc(f.school)} in ${esc(f.band)}: ${esc(f.school_year || "?")} @ ${esc(f.gross)} min superseded by ${esc((f.superseded_by || {}).school_year || "?")} @ ${esc((f.superseded_by || {}).gross)} min`,
      " — a page stating a NEWER school year displaced these from the mode; they remain in the record.");
    // #254: year-conflict flags — groups mixing year knowledge; source_file is a format HINT for
    // the reviewer, never an automatic rule (a live webpage can host stale facts — Santa Fe).
    pushFlag("year-conflicts", "School-year conflicts (#254):", ns.year_conflicts,
      (c) => `${esc(c.school)} in ${esc(c.band)} mixes ${c.years.map(esc).join(" vs ")}${c.mixes_unknown ? " vs undated" : ""} (${(c.sides || []).map((s) => `${esc(s.school_year || "undated")}${s.source_file ? ` via ${esc(s.source_file)}` : ""}`).join("; ")})${c.resolved ? " — resolved by year precedence" : " — unresolved: undated facts coexist"}`,
      " — the source format is a hint, not a rule; verify which reading is current.");
    // Copy rephrased (Ian, 2026-07-14): the flag's most common TRUE case is legitimate — a 7-12
    // "High" school genuinely serves the middle band — so the text states that possibility (with
    // the school's actual span when known) instead of implying contradiction. The failure case
    // it exists for (Coffee County: a stale NCES tag after reconfiguration) is named explicitly.
    pushFlag("name-level-mismatch", "Name/level notes (#258):", ns.name_level_mismatches,
      (m) => `${esc(m.school)} is named ${m.implied_bands.map(esc).join("/")} but serves ${esc(m.band)}${m.nces_level || (m.gslo && m.gshi) ? ` (NCES: ${[m.nces_level && esc(m.nces_level), m.gslo && m.gshi && `grades ${esc(m.gslo)}–${esc(m.gshi)}`].filter(Boolean).join(", ")})` : ""}`,
      " — often legitimate: a school can serve bands its name doesn't say (a 7-12 high school covers middle). The failure case is a stale NCES tag after a grade reconfiguration — #257 exclude if that's what you see.");
    // #499: slots never heard from, per band — includes bands with NO accepted facts at all
    // (they render no band section above, but their whole roster is unheard).
    const unheard = Object.entries(ns.unheard_slots || {});
    if (unheard.length)
      rows.push(`<li data-feat="slot-unheard"><strong>Unheard roster slots (#499):</strong> ${unheard.map(([b, n]) => `${esc(b)}: ${n}`).join(", ")} — NCES roster schools with no accepted fact (named per band above).</li>`);
    // #499: roster drift vs the LAST APPROVED receipt — schools closing / opening / reclassifying
    // since the last human sign-off (school_id-keyed; the receipt chain is the longitudinal record).
    const rd = ns.roster_drift || {};
    pushFlag("slot-drift-added", "Roster drift — schools ADDED since last approval (#499):", rd.added,
      (s) => `${esc(s.name)} (${(s.bands || []).map(esc).join("/")})`,
      " — new in the live NCES roster; the signed receipt predates them.");
    pushFlag("slot-drift-removed", "Roster drift — schools REMOVED since last approval (#499):", rd.removed,
      (s) => `${esc(s.name)} (${(s.bands || []).map(esc).join("/")})`,
      " — in the signed receipt but gone from the live NCES roster (closed or reclassified out).");
    pushFlag("slot-conflict", "Slot conflicts (#499):", ns.slot_conflicts,
      (c) => `${esc(c.roster_school)} in ${esc(c.band)}: direct reading ${esc(c.direct_gross)} min vs blanket “${esc(c.band_fact_display)}” ${esc(c.band_fact_gross)} min — <span data-feat="conflict-rung">${esc(c.rung)}</span>${c.leans ? ` leans ${esc(c.leans === "direct" ? "the direct reading" : "the blanket")}` : ""} (${esc(c.note)})`,
      " — the ladder's ADVICE (sufficiency → hub-exception → vintage); both facts keep their votes until you dispose (override / exclude / more data).");
    // Review round 2: per-KIND copy — the old binary ternary told a reviewer the school
    // "closed/reclassified" even for an assign_shadowed (the slot is alive, two assigns
    // collide) — a factually wrong basis for the Retire decision.
    const ORPHAN_MSG = {
      extra_now_in_roster: () => "the confirmed-extra now EXISTS in the NCES roster (retire it or the denominator double-counts)",
      assign_shadowed: (o) => `its slot now carries a DIFFERENT fact (“${esc(o.slot_carries || "")}”) — two standing assigns collide on one slot; retire the one that's wrong`,
      assign_fact_absent: () => "its assigned fact is no longer among the band's included facts (excluded, rejected, or superseded) — the assign binds nothing until re-extraction, or retire it",
      slot_gone_from_roster: (o) => o.still_in_district_roster
        ? "its roster slot moved to ANOTHER band (reclassified) — re-dispose under the new band"
        : "its roster slot is not in the live NCES roster (closed — or the slot id was never valid)",
    };
    pushFlag("slot-orphaned-disposition", "Orphaned slot dispositions (#499):", ns.orphaned_slot_dispositions,
      (o) => `${esc(o.school)} in ${esc(o.band)} — ${(ORPHAN_MSG[o.kind] || ORPHAN_MSG.slot_gone_from_roster)(o)} <button class="btn btn-small" data-feat="slot-disposition-remove" data-slot-retire data-band="${esc(o.band)}" data-school="${esc(o.school)}" data-slotid="${esc(o.roster_school_id || "")}">Retire</button>`,
      " — dispositions are precious: surfaced for human retirement, never auto-deleted.");
    pushFlag("slot-drift-band-moved", "Roster drift — band membership MOVED since last approval (#499):", rd.band_moved,
      (s) => `${esc(s.name)}: ${(s.from || []).map(esc).join("/")} → ${(s.to || []).map(esc).join("/")}`,
      " — the school's serving-band set changed; re-review before the approval authorizes a write.");
    const gaps = Object.entries(ns.coverage_gaps || {});
    if (gaps.length)
      rows.push(`<li><strong>Coverage gaps:</strong> ${gaps.map(([b, g]) => `${esc(b)} ${g.n_sampled}/${g.n_total}`).join(", ")} — bands resting on a thin sample.</li>`);
    const unattr = Object.entries(ns.unattributed_level_schools || {});
    if (unattr.length)
      rows.push(`<li class="s8-muted">${unattr.map(([lvl, n]) => `${n} ${esc(lvl)}`).join(", ")} school(s) not attributed to any band (ambiguous NCES level).</li>`);
    const capLine = captures.length
      ? captures.map((c) => esc((c.created_at || "").replace("T", " ").replace("Z", ""))).join(", ")
      : "unknown";
    return `<section class="s8-negative" data-feat="negative-space">
      <h3>What we know — and what we don't</h3>
      ${rows.length ? `<ul>${rows.join("")}</ul>` : `<p class="s8-note">No open gaps flagged — every claimed band has confident minutes.</p>`}
      <p class="s8-note" data-feat="capture">Pages captured: ${capLine}.</p>
    </section>`;
  }

  // #253/#254: one home for the combined-scope flag's wording — kind names the shape, source names
  // WHO raised it (the deterministic name detector, the council's applies_to reading, or both).
  function csKind(kind) {
    return kind === "group_descriptor" ? "grade-band group"
      : kind === "council_scope" ? "page states a multi-school scope" : "multiple campuses";
  }
  function csSource(source) {
    return source === "council" ? "; council reading" : source === "name+council" ? "; name + council reading" : "";
  }

  function shortUrl(u) {
    try { const p = new URL(u); return p.hostname.replace(/^www\./, "") + (p.pathname.length > 1 ? p.pathname : ""); }
    catch (_) { return u.length > 60 ? u.slice(0, 57) + "…" : u; }
  }

  // ----------------------------- actions -----------------------------
  function wire(det, did) {
    det.querySelectorAll("[data-decide]").forEach((btn) =>
      (btn.onclick = () => decide(did, btn.dataset.decide)));
    det.querySelectorAll("[data-override]").forEach((btn) =>
      (btn.onclick = () => override(did, btn.dataset.override, btn.dataset.school)));
    det.querySelectorAll("[data-exclude]").forEach((btn) =>
      (btn.onclick = () => excludeSchool(did, btn.dataset.band, btn.dataset.school)));
    det.querySelectorAll("[data-restore-excl]").forEach((btn) =>
      (btn.onclick = () => restoreExclusion(did, btn.dataset.band, btn.dataset.school)));
    det.querySelectorAll("[data-ha-add]").forEach((btn) =>
      (btn.onclick = () => humanAdd(did, btn.dataset.band)));
    det.querySelectorAll("[data-ha-remove]").forEach((btn) =>
      (btn.onclick = () => humanAddRemove(did, btn.dataset.band, btn.dataset.school)));
    det.querySelectorAll("[data-recover]").forEach((btn) =>
      (btn.onclick = () => recoverBand(did, btn.dataset.band, btn.dataset.reckey, btn.dataset.file)));
    det.querySelectorAll("[data-slot-assign]").forEach((btn) =>
      (btn.onclick = () => slotAssign(did, btn.dataset.band, btn.dataset.school)));
    det.querySelectorAll("[data-slot-reject]").forEach((btn) =>
      (btn.onclick = () => slotReject(did, btn.dataset.band, btn.dataset.school)));
    det.querySelectorAll("[data-slot-confirm]").forEach((btn) =>
      (btn.onclick = () => slotConfirmExtra(did, btn.dataset.band, btn.dataset.school)));
    det.querySelectorAll("[data-slot-retire]").forEach((btn) =>
      (btn.onclick = () => slotRetire(did, btn.dataset.band, btn.dataset.school, btn.dataset.slotid)));
    det.querySelectorAll("[data-route]").forEach((btn) =>
      (btn.onclick = () => routeSendBack(did, btn.dataset.route)));
  }

  // #689: preview, then commit — a compose is cheap to preview and awkward to undo, and the operator
  // should see WHAT would be built (which bands, which batch id) before a draft batch exists.
  async function routeSendBack(did, route) {
    let prev;
    try {
      prev = await api(`/api/aggregate/send-back/${did}/route`,
                       postJSON({ route, actor: "ian", dry_run: true }));
    } catch (e) { alert("Preview failed: " + e.message); return; }
    const what = route === "8->1"
      ? `Stage-1 follow-up batch ${prev.artifact} targeting: ${(prev.targets || []).join(", ")}`
      : prev.plan;
    if (!window.confirm(`Route this send-back ${route}?\n\n${what}\n\n` +
                        `Reason on record: ${prev.reason_given || "(none)"}\n\n` +
                        `It lands as a DRAFT for you to review — nothing runs or spends yet.`)) return;
    try {
      const out = await api(`/api/aggregate/send-back/${did}/route`,
                            postJSON({ route, actor: "ian" }));
      alert(`Routed ${out.route} → ${out.artifact}.\n\n` +
            (route === "8->1" ? "Review it at gate@1 (escalation batches are never auto-flowed)."
                              : "Pick the representations at gate@6."));
    } catch (e) { alert("Routing failed: " + e.message); return; }
    await openDistrict(did);
  }

  // #499 REQ-145: the slot-disposition actions. Candidate/slot pickers are numbered prompts over
  // the CURRENT closing argument (LAST_BANDS) — the human picks a number, the POST carries the
  // NCESSCH id; reason is REQUIRED (the resolving knowledge, same rule as #257).
  function slotChoices(band, factName) {
    const b = LAST_BANDS[band] || {};
    const amb = (b.slots || []).find((s) => s.match && s.match.confidence === "ambiguous" && s.match.school_display === factName);
    if (amb) return amb.match.candidates || [];
    return (b.slots || []).filter((s) => s.slot_state === "unfilled")
      .map((s) => ({ school_id: s.school_id, roster_school: s.roster_school }));
  }

  function pickSlot(band, factName, verb) {
    const choices = slotChoices(band, factName);
    if (!choices.length) { alert("No candidate slots available."); return null; }
    const menu = choices.map((c, i) => `${i + 1}. ${c.roster_school} (${c.school_id})`).join("\n");
    const raw = window.prompt(`${verb} “${factName}” — pick a roster slot:\n${menu}\n\nEnter a number:`);
    if (raw == null || !raw.trim()) return null;
    const idx = Number(raw.trim()) - 1;
    if (!Number.isInteger(idx) || idx < 0 || idx >= choices.length) { alert(`"${raw}" isn't a listed number.`); return null; }
    return choices[idx];
  }

  async function slotAssign(did, band, school) {
    const c = pickSlot(band, school, "Assign");
    if (!c) return;
    const reason = window.prompt(`Why does “${school}” belong to ${c.roster_school}? (required)`);
    if (reason == null || !reason.trim()) { if (reason != null) alert("A disposition requires a reason."); return; }
    try {
      await api("/api/aggregate/slot-assign", postJSON({ district_id: did, band, school,
        roster_school_id: c.school_id, disposition: "assign", reason: reason.trim(), actor: "ian" }));
    } catch (e) { alert("Assign failed: " + e.message); return; }
    await openDistrict(did);
  }

  async function slotReject(did, band, school) {
    const c = pickSlot(band, school, "Reject a candidate for");
    if (!c) return;
    const reason = window.prompt(`Why is “${school}” NOT ${c.roster_school}? (required)`);
    if (reason == null || !reason.trim()) { if (reason != null) alert("A disposition requires a reason."); return; }
    try {
      await api("/api/aggregate/slot-assign", postJSON({ district_id: did, band, school,
        roster_school_id: c.school_id, disposition: "reject", reason: reason.trim(), actor: "ian" }));
    } catch (e) { alert("Reject failed: " + e.message); return; }
    await openDistrict(did);
  }

  async function slotConfirmExtra(did, band, school) {
    const reason = window.prompt(`Confirm “${school}” is a REAL school NCES missed — evidence? (required; it will count in the ${band} denominator)`);
    if (reason == null || !reason.trim()) { if (reason != null) alert("A disposition requires a reason."); return; }
    try {
      await api("/api/aggregate/slot-assign", postJSON({ district_id: did, band, school,
        disposition: "confirm_extra", reason: reason.trim(), actor: "ian" }));
    } catch (e) { alert("Confirm failed: " + e.message); return; }
    await openDistrict(did);
  }

  async function slotRetire(did, band, school, slotId) {
    if (!window.confirm(`Retire the slot disposition for “${school}” in ${band}?`)) return;
    try {
      await api("/api/aggregate/slot-assign/remove", postJSON({ district_id: did, band, school,
        roster_school_id: slotId }));
    } catch (e) { alert("Retire failed: " + e.message); return; }
    await openDistrict(did);
  }

  // #474: hand-enter a school (LAST RESORT — #473 re-extraction first). Citation is REQUIRED; the
  // server enforces HH:MM + the REQ-055 plausibility gate on the pair, same as extracted values.
  async function humanAdd(did, band) {
    const school = window.prompt(`Hand-add a school to the ${band} band — school name (as the source states it):`);
    if (school == null || !school.trim()) return;
    const start = window.prompt(`START time for ${school} (HH:MM, required):`);
    if (start == null || !start.trim()) return;
    const end = window.prompt(`END time for ${school} (HH:MM, required):`);
    if (end == null || !end.trim()) return;
    const source = window.prompt("CITED SOURCE (required — the URL/artifact where you read these times):");
    if (source == null || !source.trim()) { alert("A hand-entered value requires a cited source (#474)."); return; }
    const reason = window.prompt("Why is hand-entry needed (required — e.g. \"table unreadable by council; re-extraction failed\"):");
    if (reason == null || !reason.trim()) { alert("A hand-entry requires a reason."); return; }
    try {
      await api("/api/aggregate/human-add", postJSON({
        district_id: did, band, school: school.trim(), start_time: start.trim(), end_time: end.trim(),
        source_url: source.trim(), reason: reason.trim(), actor: "ian" }));
    } catch (e) { alert("Hand-add failed: " + e.message); return; }
    await openDistrict(did);
  }

  async function humanAddRemove(did, band, school) {
    try {
      await api("/api/aggregate/human-add/remove", postJSON({ district_id: did, band, school }));
    } catch (e) { alert("Remove failed: " + e.message); return; }
    await openDistrict(did);
  }

  // #473: stage a re-extraction of the already-captured rep for an empty band. Spends nothing here —
  // the paid council run happens at gate@7 (budget-gated), where the new dispatch appears.
  async function recoverBand(did, band, recKey, file) {
    if (!recKey || !file) { alert("No usable rep reference on this flag — use the hand-add fallback."); return; }
    if (!window.confirm(`Stage a re-extraction of ${file} targeting the ${band} band? (Creates a new dispatch — trigger the run from the Stage 6 console; results land at gate@7.)`)) return;
    let out;
    try {
      out = await api("/api/aggregate/recover-band", postJSON({ district_id: did, band, rec_key: recKey, file, actor: "ian" }));
    } catch (e) { alert("Recover-band failed: " + e.message); return; }
    alert(`Dispatch staged (handoff ${out.handoff_hash}). Next: ${out.next}`);
    await openDistrict(did);
  }

  // #257: record / lift a standing band-exclusion. Reason is REQUIRED on exclude (the resolving
  // knowledge — e.g. "presents as a high school on the district site, 2025-26"); the server
  // recomputes the band mode immediately and the exclusion enters the receipt + fingerprint.
  async function excludeSchool(did, band, school) {
    const reason = window.prompt(`Exclude ${school} from the ${band} band — why? (required; e.g. “reconfigured to high school per district site 2025-26”)`);
    if (reason == null || !reason.trim()) { if (reason != null) alert("An exclusion requires a reason."); return; }
    try {
      await api("/api/aggregate/exclude", postJSON({ district_id: did, band, school, reason: reason.trim(), actor: "ian" }));
    } catch (e) { alert("Exclude failed: " + e.message); return; }
    await openDistrict(did);
  }

  async function restoreExclusion(did, band, school) {
    try {
      await api("/api/aggregate/exclude/restore", postJSON({ district_id: did, band, school }));
    } catch (e) { alert("Restore failed: " + e.message); return; }
    await openDistrict(did);
  }

  // #682: what the Stage-9 write did, told to the operator at the moment of the click. Silent on the
  // happy path (the badge already says "written"); loud on anything else, because "approved but never
  // written" is precisely the state that used to go unnoticed for 25 minutes.
  function reportIncorporation(did, inc) {
    if (!inc || inc.status === "incorporated" || inc.status === "already_incorporated") return;
    alert(`Approved — but Stage 9 did NOT write this district.\n\n` +
          `${inc.status}: ${inc.reason || "(no reason given)"}\n\n` +
          `The approval stands and is recorded. The write is idempotent and retryable:\n` +
          `python3 -m infrastructure.acquisition.stage9_incorporate ${did} --dry-run`);
  }

  // #682: the write half of the district's status line — approval and incorporation are two records.
  function incorporationBadge(inc) {
    if (!inc) return ` <span class="badge badge-neutral" data-feat="incorporation" title="Stage 9 has never attempted a write for this district.">not written</span>`;
    if (inc.kind === "incorporated") {
      return inc.current
        ? ` <span class="badge badge-success" data-feat="incorporation" title="Stage 9 wrote this district's bands to the LCT DB from exactly these facts.">written</span>`
        : ` <span class="badge badge-warn" data-feat="incorporation" title="Stage 9 wrote this district, but from an EARLIER set of facts — production is behind the picture below.">written — from earlier facts</span>`;
    }
    return ` <span class="badge badge-red" data-feat="incorporation" title="${esc(inc.note || "")}">approved, not written</span>`;
  }

  async function decide(did, disposition) {
    let reason = null;
    if (disposition === "sent_back") {
      reason = window.prompt("Why is this district not publishable? (which band is unsatisfied / what's wrong)");
      if (reason == null || !reason.trim()) return;   // cancelled or empty — no-op (server also enforces)
    } else if (!window.confirm("Approve this district's whole picture? Stage 9 then writes every band's minutes to the LCT DB.")) {
      return;
    }
    // expected_fingerprint = the picture the reviewer actually read (PR #252 review round). The server
    // 409s if the live facts moved after page-load — reload, re-review, decide again.
    try {
      const out = await api(`/api/aggregate/decision/${did}`,
                            postJSON({ disposition, reason, actor: "ian", expected_fingerprint: REVIEWED_FP }));
      // #682: the approval now FIRES the Stage-9 write, so the click has a second outcome to report.
      // A blocked/failed write never invalidates the (committed, precious) approval — it is stated
      // plainly and the district is left showing "approved, not written" rather than looking done.
      reportIncorporation(did, out.incorporation);
    } catch (e) {
      alert("Decision failed: " + e.message);
      // await (#337): fire-and-forget left an unhandled rejection if the reload itself failed
      if (String(e.message).startsWith("409")) await openDistrict(did);   // facts moved — reload the picture
      return;
    }
    await loadDistricts();
    openDistrict(did);
  }

  async function override(did, factId, school) {
    // fail loudly on a malformed data-override attribute rather than posting NaN (PR #252 review round)
    const fid = Number(factId);
    if (!Number.isInteger(fid)) { alert(`Can't override ${school}: no usable fact id (${factId}).`); return; }
    // HH:MM format check at entry time (15c67c4 review: a typo like "3pm" used to be stored verbatim
    // and silently fail three layers downstream). The server independently re-validates format AND the
    // REQ-055 plausibility of the effective pair — this is just the fastest feedback.
    const HHMM = /^\d{1,2}:\d{2}$/;
    const start = window.prompt(`Override START time for ${school} (HH:MM), or leave blank to keep:`);
    if (start == null) return;
    if (start.trim() && !HHMM.test(start.trim())) { alert(`"${start}" isn't HH:MM (e.g. 15:00) — override not saved.`); return; }
    const end = window.prompt(`Override END time for ${school} (HH:MM), or leave blank to keep:`);
    if (end == null) return;
    if (end.trim() && !HHMM.test(end.trim())) { alert(`"${end}" isn't HH:MM (e.g. 15:00) — override not saved.`); return; }
    const reason = window.prompt("Reason for the override (required):");
    if (reason == null || !reason.trim()) { alert("An override requires a reason."); return; }
    try {
      await api("/api/aggregate/override", postJSON({
        fact_id: fid, start_time: start.trim() || null, end_time: end.trim() || null,
        reason: reason.trim(), actor: "ian" }));
    } catch (e) { alert("Override failed: " + e.message); return; }
    openDistrict(did);   // re-render: the override mark + the new fingerprint both come from the fresh GET
  }
})();
