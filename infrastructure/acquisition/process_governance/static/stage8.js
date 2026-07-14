"use strict";
// Stage 8 (Aggregate) console view — gate@8, the "closing argument" (STAGE8_AGGREGATE_DESIGN §2).
// Review one district's WHOLE per-band determination and render, for each band: the claim, the sampling
// sufficiency, the dereferenced evidence (URL / reader / capture / models / verbatim council quote), and
// the negative space — then approve (Stage 9 may write every band) or send it back (all-or-nothing, §2e).
//
// MUST-BE-VISIBLE features (regression-guarded in the Playwright/DOM check — do not silently drop):
//   F1 per-band determination: gross minutes + start–end + method            [data-feat="claim"]
//   F2 per-band sampling: n_sampled/n_total + coverage% + plurality%         [data-feat="sampling"]
//   F3 per-school evidence: source URL, reader, models, verbatim quote       [data-feat="evidence"]
//   F4 capture time(s)                                                       [data-feat="capture"]
//   F5 negative space: unresolved / contamination / unsatisfied / gaps       [data-feat="negative-space"]
//   F6 decision status + Approve / Send-back verdict controls                [data-feat="verdict"]
//   F7 per-school override control (required reason)                         [data-feat="override"]
// Vanilla JS on the shared window.LCT helpers; reuses q-*/badge/btn classes for visual consistency.
(function () {
  const $g = (s, r = document) => r.querySelector(s);
  const { esc, postJSON, api, safeUrl } = window.LCT;
  const pct = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
  // REVIEWED_FP: the fingerprint of the closing argument the reviewer is LOOKING at (from the GET).
  // Echoed to the decision POST, which 409s if the live facts moved after page-load — the verdict can
  // only ever attach to the picture the human actually read (PR #252 review round).
  let inited = false, CURRENT = null, REVIEWED_FP = null;

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
    if (!ds.length) { list.innerHTML = `<div class="empty">No districts are ready for gate@8 yet — a district appears once it has extracted facts and its gate@7 request loop is quiet.</div>`; return; }
    list.innerHTML = "";
    ds.forEach((d) => list.appendChild(districtRow(d)));
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
    det.innerHTML = renderDetail(x);
    wire(det, did);
  }

  function renderDetail(x) {
    const ca = x.closing_argument, dec = x.decision || {};
    const bands = ca.bands || {};
    const order = ["elementary", "middle", "high"].filter((b) => bands[b]);
    return `
      ${renderHeader(ca, dec)}
      ${renderVerdict(dec)}
      <div class="s8-bands">${order.map((b) => renderBand(b, bands[b])).join("") || `<div class="empty">No accepted band facts.</div>`}</div>
      ${renderNegativeSpace(ca.negative_space || {}, ca.capture_events || [])}`;
  }

  function renderHeader(ca, dec) {
    let status = `<span class="badge badge-neutral">not yet decided</span>`;
    if (dec.decided) {
      status = dispositionBadge(dec.disposition);
      if (dec.is_stale) status += ` <span class="badge badge-warn" title="A re-extraction changed the facts since this decision — re-review before it can authorize a write.">stale — re-review</span>`;
    }
    return `<div class="s8-head"><h2 style="margin:0">${esc(ca.district_id)}</h2> ${status}</div>`;
  }

  // F6 — the verdict controls
  function renderVerdict(dec) {
    const approvedNote = dec.is_approved
      ? `<span class="s8-note">Approved — Stage 9 may write all bands.</span>` : "";
    return `<div class="s8-verdict" data-feat="verdict">
      <button class="btn btn-primary" data-decide="approved">Approve district → Stage 9</button>
      <button class="btn" data-decide="sent_back">Send back (needs a reason)</button>
      ${approvedNote}
      <p class="s8-note">All-or-nothing at the district (§2e): approval publishes every band together; an unsatisfied band means send it back.</p>
    </div>`;
  }

  function renderBand(band, b) {
    const s = b.sampling || {};
    return `<section class="s8-band">
      <div class="s8-band-head" data-feat="claim">
        <h3>${esc(band)}</h3>
        <span class="s8-claim"><strong>${b.gross_minutes} min/day</strong> · ${esc(b.start_time)}–${esc(b.end_time)} · <span class="s8-method">${esc(b.method)}</span></span>
      </div>
      <div class="s8-sampling" data-feat="sampling">
        Sampled <strong>${s.n_sampled}</strong> of <strong>${s.n_total == null ? "?" : s.n_total}</strong> schools ·
        coverage ${pct(s.coverage)} · school agreement (plurality) ${pct(s.plurality_share)}
      </div>
      <table class="s8-schools"><thead><tr><th>School</th><th>Times</th><th>Gross</th><th>Models</th><th>Evidence</th><th></th></tr></thead>
        <tbody>${(b.schools || []).map((sc) => renderSchool(sc, band)).join("")}</tbody></table>
    </section>`;
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
    const times = `${esc(sc.start_time)}–${esc(sc.end_time)}`;
    // #257: an excluded school renders struck-through WITH its reason — a recorded, auditable human
    // decision (out of the mode/count, never out of sight). The action flips to Restore.
    const excl = sc.excluded
      ? `<div class="s8-excluded-note" data-feat="excluded-reason">⊘ excluded from ${esc(band)} — ${esc(sc.excluded.reason)} (${esc(sc.excluded.actor)})</div>` : "";
    const action = sc.excluded
      ? `<button class="btn btn-small" data-feat="restore-exclusion" data-restore-excl data-band="${esc(band)}" data-school="${esc(sc.school)}">Restore</button>`
      : `<button class="btn btn-small" data-feat="override" ${sc.fact_id == null ? "disabled" : `data-override="${esc(sc.fact_id)}"`} data-school="${esc(sc.school)}">Override</button>
         <button class="btn btn-small" data-feat="exclude" data-exclude data-band="${esc(band)}" data-school="${esc(sc.school)}">Exclude</button>`;
    return `<tr${sc.excluded ? ' class="s8-excluded" data-feat="excluded-row"' : ""}>
      <td>${esc(sc.school)}</td>
      <td>${applied ? `<span class="s8-override" title="human override — council read ${esc(sc.council_start_time)}–${esc(sc.council_end_time)}">✎ ${times}</span>` : times}</td>
      <td>${applied ? `<span class="s8-override">${esc(sc.gross)}</span>` : esc(sc.gross)}</td>
      <td class="s8-muted">${(sc.models || []).map((m) => esc(m.split("/").pop())).join(", ")}</td>
      <td data-feat="evidence">${url}${reader}${quote}${stated}${overrideMark}${ovErr}${excl}</td>
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
    if ((ns.band_exclusions || []).length)
      rows.push(`<li data-feat="band-exclusions"><strong>Human band-exclusions (#257):</strong> ${ns.band_exclusions.map((e) => `${esc(e.school)} ⊘ ${esc(e.band)} — ${esc(e.reason)}`).join("; ")}.</li>`);
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

  async function decide(did, disposition) {
    let reason = null;
    if (disposition === "sent_back") {
      reason = window.prompt("Why is this district not publishable? (which band is unsatisfied / what's wrong)");
      if (reason == null || !reason.trim()) return;   // cancelled or empty — no-op (server also enforces)
    } else if (!window.confirm("Approve this district's whole picture? Stage 9 may then write every band's minutes to the LCT DB.")) {
      return;
    }
    // expected_fingerprint = the picture the reviewer actually read (PR #252 review round). The server
    // 409s if the live facts moved after page-load — reload, re-review, decide again.
    try {
      await api(`/api/aggregate/decision/${did}`,
                postJSON({ disposition, reason, actor: "ian", expected_fingerprint: REVIEWED_FP }));
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
