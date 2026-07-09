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
})();
