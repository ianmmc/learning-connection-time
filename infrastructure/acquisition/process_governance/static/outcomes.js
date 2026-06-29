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
    // Stage 4 — process outcomes (used when the Stage 4 view lands)
    processed_all:      { label: "processed_all", tone: "badge-success" },
    processed_partial:  { label: "processed_partial", tone: "badge-lavender" },
    // Generic per-stage lifecycle
    awaiting_discovery: { label: "awaiting discovery", tone: "badge-neutral" },
    todo:               { label: "queued", tone: "badge-neutral" },
    // district-level stage failures (retriable, distinct from a per-URL fail). timed_out is called out
    // separately so the cause is apparent at a glance.
    failed:             { label: "failed", tone: "badge-red" },
    timed_out:          { label: "Timed out", tone: "badge-red" },
    error:              { label: "error", tone: "badge-red" },
  };

  const esc = (s) => (s == null ? "" : String(s)).replace(/&/g, "&amp;").replace(/</g, "&lt;");

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
    if (!progress) return `<span class="badge badge-neutral">—</span>`;
    const total = progress.total || 0;
    const flagged = progress.flagged || 0;
    let done, verb;
    if (stage === "stage2") { done = progress.discovered || 0; verb = "discovered"; }
    else if (stage === "stage3") { done = (progress.captured || 0) + flagged; verb = "captured"; }
    else if (stage === "stage4") { done = (progress.processed || 0) + flagged; verb = "processed"; }
    else return `<span class="badge badge-neutral">—</span>`;
    if (total === 0 || done === 0) return `<span class="badge badge-neutral">not started</span>`;
    const flagNote = flagged ? ` · ${flagged} flagged` : "";
    if (done >= total) return `<span class="badge badge-success">✓ ${verb}${flagNote}</span>`;
    return `<span class="badge badge-lavender">${done}/${total} ${verb}${flagNote}</span>`;
  };
})();
