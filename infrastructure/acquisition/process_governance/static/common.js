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

  return { esc, postJSON, api };
})();
