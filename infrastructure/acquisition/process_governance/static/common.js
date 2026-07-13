"use strict";
// Shared console helpers (issue #147): the HTML-escape guard + the fetch wrappers, previously copied
// into every stage view — and DRIFTING (outcomes.js's `esc` had dropped the double-quote escape, an
// XSS-adjacent gap for any value interpolated into a `"`-quoted attribute). ONE home so the guard can't
// fork. Loaded FIRST in index.html (before app.js + the stage scripts); each view aliases what it needs
// off `window.LCT`, so its call sites (`esc(...)`, `api(...)`, `postJSON(...)`) are unchanged.
window.LCT = (function () {
  // Escape the 3 HTML-significant chars for safe text interpolation into innerHTML. `"` IS escaped so a
  // value dropped inside a double-quoted attribute can't break out — the divergence outcomes.js carried.
  const esc = (s) => (s == null ? "" : String(s)).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

  // fetch-init for a JSON POST body.
  const postJSON = (b) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });

  // fetch + JSON, surfacing the server's `detail` message on a non-2xx (FastAPI's error shape).
  async function api(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(`${r.status} — ${m}`); }
    return r.json();
  }

  // Shared batch-status pill (#168/#198 review) — ONE home so the tone mapping can't fork across the
  // stage views (gate1 + stage2/3/4 each had their own inline copy; abandoned was added to gate1 only,
  // so the other panes rendered a retired batch in the neutral draft tone). approved -> success,
  // abandoned -> red (terminal, retired), anything else (draft/reserving) -> neutral.
  const statusBadge = (s) => {
    const tone = s === "approved" ? "badge-success" : s === "abandoned" ? "badge-red" : "badge-neutral";
    return `<span class="badge ${tone}">${esc(s)}</span>`;
  };

  // Scheme allow-list for DB-sourced URLs rendered into a raw href (PR #248 review; promoted here in
  // the PR #252 review round): esc() only HTML-escapes — a `javascript:` URI passes it untouched and
  // executes on click. Any view rendering a stored URL as a clickable link MUST gate it through this;
  // a non-http(s) value degrades to visible plain text (the operator still sees what the record
  // claims). Was a settings.js-local helper, which is exactly why stage8.js reintroduced the same bug —
  // ONE home, like esc() itself.
  const safeUrl = (u) => typeof u === "string" && /^https?:\/\//i.test(u);

  // Cost formatter (PR #256 review) — stage6 and stage7 each carried a local copy at DIFFERENT
  // precisions (5 vs 4 dp), so the same est_usd/cost_usd rendered differently per view. ONE home,
  // like esc(). 5 dp: per-rep costs run ~$0.001xx — 4 dp truncates the real trailing digit.
  const usd = (n) => "$" + (Number(n) || 0).toFixed(5);

  return { esc, postJSON, api, statusBadge, safeUrl, usd };
})();
