"use strict";
// Shared status/outcome labels for the console stage views (REQ-110 follow-up). ONE source of truth for
// every per-district badge so a label change propagates to Stage 2, 3, and 4 at once — e.g. renaming the
// terminal "no links found" state (currently `manual_flag_all`) to something without underscores is a
// single edit here. Stage views import `outcomeBadge` (per-district) + `progressBadge` (left-pane fraction).
(function () {
  // outcome/status key -> { label (display text), tone (MMM badge class) }. To rename a state's display,
  // edit its `label` here only — the backend key (e.g. "manual_flag_all") is unchanged.
  const BADGES = {
    // Stage 2 — discovery outcomes
    found_all:          { label: "found_all", tone: "badge-success" },
    found_partial:      { label: "found_partial", tone: "badge-lavender" },
    // Terminal "discovered but no links — needs manual follow-up". The SAME badge in every stage.
    manual_flag_all:    { label: "manual_flag_all", tone: "badge-red" },
    // Stage 3 — capture outcomes
    captured_all:       { label: "captured_all", tone: "badge-success" },
    captured_partial:   { label: "captured_partial", tone: "badge-lavender" },
    capture_failed_all: { label: "capture_failed_all", tone: "badge-red" },
    // Stage 4 — process outcomes
    processed_all:      { label: "processed_all", tone: "badge-success" },
    processed_partial:  { label: "processed_partial", tone: "badge-lavender" },
    // Processed, but no representation cleared the usable-text bar — honest, NOT a failure (the captures
    // were genuinely empty / image-only; Stage 4 reports it rather than papering over it).
    no_usable_text_any: { label: "no_usable_text", tone: "badge-red" },
    // Generic per-stage lifecycle
    awaiting_discovery: { label: "awaiting discovery", tone: "badge-neutral" },
    // captured but not processed yet — the upstream gate for Stage 4 (Stage 3 still owes this district)
    awaiting_capture:   { label: "awaiting capture", tone: "badge-neutral" },
    todo:               { label: "queued", tone: "badge-neutral" },
    // district-level stage failures (retriable, distinct from a per-URL fail). timed_out is called out
    // separately so the cause is apparent at a glance.
    failed:             { label: "failed", tone: "badge-red" },
    timed_out:          { label: "Timed out", tone: "badge-red" },
    error:              { label: "error", tone: "badge-red" },
  };

  const { esc } = window.LCT;

  // Per-district status badge. `key` is a backend status/outcome string.
  window.outcomeBadge = function (key) {
    const b = BADGES[key] || { label: key || "?", tone: "badge-neutral" };
    return `<span class="badge ${b.tone}">${esc(b.label)}</span>`;
  };

  // Left-pane, stage-contextual progress badge for a batch. `progress` = {total, discovered, captured,
  // processed, flagged} (from /api/queue) or null; `stage` = "stage2" | "stage3" | "stage4". A batch's
  // stage is COMPLETE when every district is resolved — captured/processed OR terminally `flagged`
  // (no-link). Shows "not started" / "X/Y <verb>" / "✓ <verb> · N flagged".
  window.progressBadge = function (progress, stage) {
    const chip = (label, tone) => `<span class="badge ${tone}">${label}</span>`;
    if (!progress) return chip("—", "badge-neutral");
    const total = progress.total || 0;
    const flagged = progress.flagged || 0;   // no-link (manual_flag_all) districts — terminal at Stage 2
    let done, denom, verb;
    if (stage === "stage2")      { done = progress.discovered || 0; denom = total;           verb = "discovered"; }
    else if (stage === "stage3") { done = progress.captured   || 0; denom = total - flagged; verb = "captured"; }
    else if (stage === "stage4") { done = progress.processed  || 0; denom = total - flagged; verb = "processed"; }
    else return chip("—", "badge-neutral");
    // The flagged (no-link) districts are reported SEPARATELY, never folded into the verb count — we don't
    // claim captures that didn't happen. Capture/process exclude them from the denominator (never
    // capturable); discovery counts the whole batch (a no-link district WAS discovered).
    const flagNote = flagged ? ` · ${flagged} no-links` : "";
    if (denom <= 0) return chip(`${flagged} no-links`, "badge-neutral");        // nothing capturable
    if (done === 0 && flagged === 0) return chip("not started", "badge-neutral");
    if (done >= denom) return chip(`✓ ${verb}${flagNote}`, "badge-success");
    return chip(`${done}/${denom} ${verb}${flagNote}`, "badge-lavender");
  };

  // #118 (REQ-160): the shared Stage-2/4 effectiveness panel — labeled-corpus attribution,
  // lazy-fetched from /api/attribution on first expand (the card takes a few seconds; a view
  // load must never pay for it). ONE home for both stages, like outcomeBadge itself.
  window.attributionPanel = function (container, kind) {
    const { esc, api } = window.LCT;
    const det = document.createElement("details");
    det.className = "q-domain-excluded s-attr";
    det.setAttribute("data-feat", `attr-panel-${kind}`);
    det.innerHTML = `<summary class="muted">Effectiveness — labeled-corpus attribution (#118, expand)</summary>
      <div class="s-attr-body muted" style="overflow-x:auto">Loading…</div>`;
    const pct = (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
    const render2 = (card) => {
      const rows = Object.entries(card.stage2.per_tool).map(([t, b]) =>
        `<tr><td>${esc(t)}</td><td>${b.n_candidates}</td><td>${b.n_records}</td>
         <td>${b.n_labeled}</td><td>${b.n_target}</td><td>${pct(b.target_rate_labeled)}</td></tr>`).join("");
      const geo = Object.values(card.district_axes).filter((a) =>
        Object.keys(a.runs).some((k) => k.endsWith(":geo"))).length;
      const disc = Object.values(card.district_axes).filter((a) => a.domain_source === "discovered").length;
      return `<table class="s2-table"><thead><tr><th>Discovery tool</th><th>Cand</th><th>Rec</th>
          <th>Labeled</th><th>Target</th><th>Target rate</th></tr></thead><tbody>${rows}</tbody></table>
        <p class="muted">Axes (#164): ${Object.keys(card.district_axes).length} attributed district(s) ·
          ${geo} with a geo-scoped run · ${disc} scoped by a discovered domain ·
          fingerprints ${esc(card.fingerprints.label_set)}/${esc(card.fingerprints.plan)}</p>`;
    };
    const render4 = (card) => {
      const win = Object.entries(card.stage4.winning_source).map(([s, n]) =>
        `<tr><td>${esc(s)}</td><td>${n}</td></tr>`).join("");
      const use = Object.entries(card.stage4.usable_by_source)
        .sort((a, b) => b[1].n_reps - a[1].n_reps).slice(0, 12).map(([s, u]) =>
        `<tr><td>${esc(s)}</td><td>${u.n_usable}/${u.n_reps}</td><td>${pct(u.usable_rate)}</td></tr>`).join("");
      return `<p class="muted">Winning representation source over <b>${card.stage4.n_target_records}</b>
          human-labeled TARGET records (release.decide()'s send files):</p>
        <table class="s2-table"><thead><tr><th>Source</th><th>Wins</th></tr></thead><tbody>${win}</tbody></table>
        <p class="muted">Usable rate by source (corpus-wide):</p>
        <table class="s2-table"><thead><tr><th>Source</th><th>Usable</th><th>Rate</th></tr></thead><tbody>${use}</tbody></table>`;
    };
    det.addEventListener("toggle", async () => {
      if (!det.open || det.getAttribute("data-loaded")) return;
      det.setAttribute("data-loaded", "1");
      const body = det.querySelector(".s-attr-body");
      let card;
      try { card = await api("/api/attribution"); }
      catch (e) { body.textContent = "Attribution unavailable: " + e.message; return; }
      body.innerHTML = kind === "stage2" ? render2(card) : render4(card);
    });
    container.appendChild(det);
  };

  // #518: the capture-fidelity TRIAGE panel — the flag CONSUMER (login_wall / soft_404 /
  // time_blind / security_block), lazy-fetched. Mounted on Stage 3 (governance §11f: capture
  // health lives there) AND the gate@5 left pane (the reviewer must see "capture suspect"
  // where labeling happens). Recovery affordance: flag the district for manual follow-up
  // (the existing gate@5 top attention tier); retryable errs stay #116's batch-level retry.
  window.fidelityTriagePanel = function (container) {
    const { esc, api, postJSON, safeUrl } = window.LCT;
    const det = document.createElement("details");
    det.className = "q-domain-excluded s-attr";
    det.setAttribute("data-feat", "fidelity-triage-panel");
    det.innerHTML = `<summary class="muted">Capture-fidelity triage — suspect captures (#518, expand)</summary>
      <div class="s-triage-body muted" style="overflow-x:auto">Loading…</div>`;
    const render = (d) => {
      if (!d.n_districts) return `<p class="muted">No suspect captures — nothing to triage.</p>`;
      const sum = Object.entries(d.summary).map(([c, n]) => `${esc(c)}: <b>${n}</b>`).join(" · ");
      const blocks = d.districts.map((b) => {
        const cls = Object.entries(b.classes).map(([c, n]) => `${esc(c)}×${n}`).join(", ");
        const rows = b.rows.map((r) => `<div class="q-smeta">${r.classes.map(esc).join("+")} — ${
          safeUrl(r.url) ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url)}</a>` : esc(r.url || r.hash)}</div>`).join("");
        const more = b.n_total > b.rows.length ? `<div class="q-smeta muted">…and ${b.n_total - b.rows.length} more</div>` : "";
        const flag = b.open_followup_flag
          ? `<span class="badge badge-lavender">already flagged</span>`
          : `<button class="btn btn-mini" data-feat="triage-flag" data-did="${esc(b.district_id)}" data-name="${esc(b.name)}">Flag district…</button>`;
        return `<details class="s-triage-d"><summary><b>${esc(b.name)}</b> <span class="muted">(${esc(b.district_id)})</span> — ${cls} ${flag}</summary>${rows}${more}</details>`;
      }).join("");
      return `<p class="muted">${sum} across <b>${d.n_districts}</b> district(s). A suspect capture may
        hide a real schedule (the #518 recall leak) — review, then flag for manual follow-up or use the
        Stage-3 retry for retryable errs (#116). Security blocks are one-attempt (Rule 3): never re-pressure.</p>${blocks}`;
    };
    det.addEventListener("toggle", async () => {
      if (!det.open || det.getAttribute("data-loaded")) return;
      det.setAttribute("data-loaded", "1");
      const body = det.querySelector(".s-triage-body");
      let d;
      try { d = await api("/api/fidelity-triage"); }
      catch (e) { body.textContent = "Triage unavailable: " + e.message; return; }
      body.innerHTML = render(d);
      body.querySelectorAll('[data-feat="triage-flag"]').forEach((btn) => btn.onclick = async () => {
        const directive = prompt(`Flag ${btn.dataset.name} (${btn.dataset.did}) for manual follow-up?\n\nDirective (what should be done):`);
        if (directive === null) return;
        try {
          await api("/api/followup", postJSON({ scope: "district", target_id: btn.dataset.did,
            directive: directive || "capture-fidelity triage (#518)", actor: "ian" }));
          btn.outerHTML = `<span class="badge badge-lavender">flagged</span>`;
        } catch (e) { alert("Flag failed: " + e.message); }
      });
    });
    container.appendChild(det);
  };
})();
