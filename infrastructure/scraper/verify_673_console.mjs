// #673 console verification — the gate@5 vintage surface, against the REAL TAOS records.
//
// Deliberately NOT a `*.test.mjs`: `npm test` globs `*.test.mjs`, and this needs a LIVE console server
// and the governance DB, so it must never run unattended in CI. This is the end-to-end render pass the
// issue was left OPEN for after PR #850 shipped the implementation ("leaving OPEN for the falsifier in
// box 1, which is a Playwright render check I have not run").
//
// Run:  python3 -c "import uvicorn; from infrastructure.acquisition.process_governance.server import app; \
//         uvicorn.run(app, host='127.0.0.1', port=8015)" &
//       cd infrastructure/scraper && node verify_673_console.mjs        # BASE=… to point elsewhere
// (Scratch PORT only — never the :8005 the human's console is on. Needs the canonical governance DB:
// the TAOS records are live rows, not seeds.)
//
// The records (issue #673's own table, re-verified in the DB before this was written):
//   3500127:47750e00fb  — the 2014-15 Parent-Student-Handbook, the ONLY record with a derived vintage;
//                          below the 2017-18 validity floor. Human-target-labeled per the doctrine
//                          ("the label carries SHAPE, not fitness-for-use"), so it may read SEND — the
//                          vintage line, not the decision, is what this verifies.
//   any None record      — vintage underivable from the URL (e.g. /apps/bell_schedules/…); must read
//                          "unknown", visibly distinct from both a derived year and a below-floor year.
//
// Asserts (issue #673 acceptance box 1 + Arm 2's control):
//   1. the below-floor record's vintage readout shows the year INSIDE <b class="warn"> with the
//      "BELOW the … validity floor" reason — held-state and why, at the point of review;
//   2. a None record reads "unknown" in muted styling — distinct from derived AND from below-floor;
//   3. the Arm-2 facet control (data-feat="vintage-facets") renders on both, carrying the
//      "flagged" det-hint on the below-floor record and NOT on the unknown one — the hint is the
//      floor, and unknown does NOT hint (that would launder #642's gap into a human suggestion).
//      NB the hint is an <em class="det-hint"> marker, NEVER an auto-ticked checkbox — #241
//      measured the automatic recency veto actively harmful (1 false-send removed, 17 real
//      targets vetoed), so the human confirms or ignores; this script must not assert a tick;
//   4. no client console errors while rendering either record.
//
// FALSIFIER (issue box 1: "this must fail against today's client" — 'today' = pre-#850): run with
// FALSIFY=1 (exactly "1" — #894: a bare truthiness check made FALSIFY=0 ENABLE the mode it reads
// as disabling) to assert the pre-#850 client (git e270099^) LACKS both data-feat hooks this script keys
// on — i.e. every DOM assertion above is unsatisfiable against that client. Source-level rather than
// a live serve of the old client, so the falsification never swaps files under the human's :8005
// server, which serves the same static dir from disk.
import { execFileSync } from "node:child_process";
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:8015";
const BELOW = "3500127:47750e00fb";           // 2014-15 handbook — the one derived vintage
const out = [];
const ok = (name, cond, detail = "") =>
  out.push(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);

if (process.env.FALSIFY === "1") {
  // Pre-#850 client from git — the DOM hooks must be ABSENT, so checks 1-3 cannot pass against it.
  // #892: a git failure (outside a working tree, shallow clone missing e270099) must land as a
  // FAIL line in this script's own accounting, never as a raw uncaught stack trace.
  let old = null, gitErr = "";
  try {
    old = execFileSync("git",
      ["show", "e270099^:infrastructure/acquisition/process_governance/static/app.js"],
      { cwd: "..", encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
  } catch (e) {
    gitErr = String(e.stderr || e.message || e).split("\n")[0];
  }
  ok("pre-#850 client readable from git", old !== null, gitErr);
  ok("pre-#850 client lacks vintage-readout hook", !!old && !old.includes("vintage-readout"));
  ok("pre-#850 client lacks vintage-facets hook", !!old && !old.includes("vintage-facets"));
  ok("pre-#850 client never mentions content_school_year", !!old && !old.includes("content_school_year"));
  console.log(out.join("\n"));
  process.exit(out.some((l) => l.startsWith("FAIL")) ? 1 : 0);
}

const b = await chromium.launch();
const p = await b.newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));
p.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

async function openRecord(rec) {
  // search by DISTRICT id, not the record hash — a hash query filters the list to one row, which
  // would hide the sibling records check 2 needs (first-run bug of this very script)
  await p.goto(`${BASE}/?q=${encodeURIComponent(rec.split(":")[0])}`, { waitUntil: "networkidle" });
  // #898: poll for the state, never sleep a fixed interval — a fixed wait is slow on a fast run
  // and a false FAIL on a slow one. (The older verify_*_console.mjs scripts keep their fixed
  // waits: their headers record "last run N/N PASS" under that timing, and rewriting them
  // without re-running would falsify the record.)
  try {
    await p.waitForSelector(`.rec-row[data-rec-key="${rec}"]`, { timeout: 15000 });
  } catch {
    return { ok: false, rows: await p.evaluate(() => document.querySelectorAll(".rec-row").length) };
  }
  const clicked = await p.evaluate(async (r) => {
    const li = document.querySelector(`.rec-row[data-rec-key="${r}"]`);
    if (!li) return { ok: false, rows: document.querySelectorAll(".rec-row").length };
    await selectRecord(r, li);
    return { ok: true };
  }, rec);
  try {
    await p.waitForSelector('[data-feat="vintage-readout"]', { timeout: 15000 });
  } catch { /* readVintage() reports found:false as its own FAIL line */ }
  return clicked;
}

function readVintage() {
  return p.evaluate(() => {
    const ro = document.querySelector('[data-feat="vintage-readout"]');
    const fac = document.querySelector('[data-feat="vintage-facets"]');
    const boxes = fac ? [...fac.querySelectorAll('input[type="checkbox"]')] : [];
    return {
      found: !!ro,
      text: ro ? ro.innerText.replace(/\s+/g, " ").trim() : null,
      warnYear: ro?.querySelector("b.warn")?.innerText ?? null,   // below-floor styling
      mutedUnknown: /unknown/i.test(ro?.querySelector("span.muted")?.innerText ?? ""),
      facets: { found: !!fac, n: boxes.length,
                hinted: fac ? fac.querySelectorAll("em.det-hint").length : 0 },
    };
  });
}

// ---- the below-floor record -------------------------------------------------------------------
const c1 = await openRecord(BELOW);
ok("below-floor record opened", c1.ok, JSON.stringify(c1));
const v1 = await readVintage();
ok("vintage readout renders", v1.found, v1.text ?? "<absent>");
ok("2014-15 shown in below-floor warn styling", v1.warnYear === "2014-15", `warn=<${v1.warnYear}>`);
ok("held-reason stated: BELOW the validity floor", /BELOW the .*validity floor/i.test(v1.text ?? ""));
ok("Arm-2 vintage facet control renders", v1.facets.found, `${v1.facets.n} checkbox(es)`);
ok("below-floor record carries the 'flagged' det-hint (a hint, never an auto-tick — #241)",
  v1.facets.hinted >= 1, `${v1.facets.hinted} hinted`);

// ---- an unknown-vintage record (any other TAOS row) -------------------------------------------
const unk = await p.evaluate((below) => {
  const rows = [...document.querySelectorAll(".rec-row")].map((r) => r.dataset.recKey);
  return rows.find((k) => k && k.startsWith("3500127:") && k !== below) || null;
}, BELOW);
ok("an unknown-vintage TAOS sibling exists in the list", !!unk, unk ?? "<none>");
if (unk) {
  const c2 = await openRecord(unk);
  ok("unknown-vintage record opened", c2.ok, unk);
  const v2 = await readVintage();
  ok("unknown reads as muted 'unknown', not a year and not warn",
    v2.found && v2.mutedUnknown && v2.warnYear === null, v2.text ?? "<absent>");
  ok("unknown explains the #642 limit (URL-derived, document never opened)",
    /#642/.test(v2.text ?? "") || /never opened/i.test(v2.text ?? ""));
  ok("facet control renders on unknown with NO det-hint (unknown must not hint — #642)",
    v2.facets.found && v2.facets.hinted === 0, `${v2.facets.hinted} hinted`);
}

ok("no client console errors", errors.length === 0, errors.slice(0, 3).join(" | "));
await b.close();
console.log(out.join("\n"));
const fails = out.filter((l) => l.startsWith("FAIL")).length;
console.log(`\n${out.length - fails}/${out.length} PASS`);
process.exit(fails ? 1 : 0);
