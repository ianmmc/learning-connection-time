// #822 console verification — the gate@7 degraded banner and the gate@6 overflow badge.
//
// Deliberately NOT a `*.test.mjs`: `npm test` globs those, and this needs a LIVE console server + the
// governance DB, so it must never run unattended in CI. Follows verify_684_console.mjs / _682's shape:
// the logic is pinned DB-free elsewhere (tests/test_model_windows.py::TestOverflowDegrades822,
// tests/test_stage7_api.py::test_822_*), and THIS is the end-to-end pass proving it renders.
//
// WHY THIS NEEDS A SEEDED DB. The gate@7 banner reads a STORED column (extraction.degraded_json).
// Every live row is '{}' until a Stage-7 run executes post-#822, so against the real DB the banner
// correctly renders nothing — which cannot distinguish "works, correctly hidden" from "dead, never
// fires". A green check over all-empty data is not a check. So: clone the governance DB and degrade
// one row IN THE CLONE. The gate@6 badge needs no seeding — it is computed live at request time.
//
// Run:
//   docker exec lct_postgres psql -U lct_user -d postgres \
//     -c "DROP DATABASE IF EXISTS gov_822_scratch;" \
//     -c "CREATE DATABASE gov_822_scratch TEMPLATE governance OWNER governance_user;"
//   docker exec lct_postgres psql -U governance_user -d gov_822_scratch -c \
//     "UPDATE extraction SET degraded_json='{\"n\":2,\"kinds\":{\"output_overflow\":1,
//      \"window_truncated\":1},\"unassessable\":3}' WHERE district_id='3904378';"
//   GOVERNANCE_DB_NAME=gov_822_scratch python3 -m uvicorn \
//     infrastructure.acquisition.process_governance.server:app --port 8015 &
//   cd infrastructure/scraper && node verify_822_console.mjs
//   docker exec lct_postgres psql -U lct_user -d postgres -c "DROP DATABASE gov_822_scratch;"
// (Scratch PORT 8015, never the :8005 the human's console is on. Restart the server after any
// Python change — the gate@7 SELECT is server-side.)
//
// NOTE — cloning the DB does NOT by itself protect the git-tracked JSON twins: they are files on
// disk, and every exporter rebuilds them WHOLESALE from the connected DB's log. The first run of
// this verifier leaked a `draft_add_district` event into district_status.json for exactly that
// reason. REQ-176 now quarantines a tracked export whenever the process is on a non-canonical
// governance DB, printing e.g.
//   [paths] NON-CANONICAL governance DB 'gov_822_scratch' (#822) — district_status.json export
//           quarantined to /tmp/lct-test-quarantine/district_status.json
// Seeing that line is the guard working. If you ever DON'T see it while running against a clone,
// stop and check `git status data/acquisition/` before continuing.
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:8015";
const DID = process.env.DID || "3904378";      // the district degraded in the clone
const out = [];
const ok = (name, cond, detail = "") =>
  out.push(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);

const b = await chromium.launch();
const p = await b.newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));
p.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

// ---------------------------------- gate@7 banner ----------------------------------
await p.goto(BASE, { waitUntil: "networkidle" });
await p.evaluate(() => { document.querySelector("#stageSelect").value = "stage7"; });
await p.evaluate(() => document.querySelector("#stageSelect").dispatchEvent(new Event("change")));
await p.waitForTimeout(2000);
const opened = await p.evaluate(async (did) => {
  const el = [...document.querySelectorAll("#s7-list .q-batch")].find((e) => e.dataset.id === did);
  if (!el) return { ok: false, n: document.querySelectorAll("#s7-list .q-batch").length };
  el.click();
  return { ok: true };
}, DID);
await p.waitForTimeout(2500);

const banner = await p.evaluate(() => {
  const el = document.querySelector('[data-feat="degraded-banner"]');
  if (!el) return { present: false };
  return {
    present: true,
    n: el.getAttribute("data-degraded"),
    role: el.getAttribute("role"),
    text: el.innerText.replace(/\s+/g, " ").trim(),
    unassessable: !!el.querySelector('[data-feat="degraded-unassessable"]'),
  };
});
ok("gate@7 district opened", opened.ok, JSON.stringify(opened));
ok("degraded banner renders on a degraded run", banner.present, JSON.stringify(banner).slice(0, 200));
ok("banner carries the data-degraded count hook", banner.n === "2", `data-degraded=${banner.n}`);
ok("banner is an accessibility alert", banner.role === "alert", `role=${banner.role}`);
ok("banner names the OVERFLOW kind in human words",
  /exceeded the council's ceiling/.test(banner.text || ""), (banner.text || "").slice(0, 120));
ok("banner names the co-occurring truncation kind",
  /cut short/.test(banner.text || ""), (banner.text || "").slice(0, 160));
ok("un-assessable reps are surfaced SEPARATELY, not folded into the degraded count",
  banner.unassessable && /Unmeasured, not clean/.test(banner.text || ""),
  `unassessable-block=${banner.unassessable}`);
// The whole point of #822: this run shows facts, but a reviewer must not read its zeros as clean.
ok("the banner sits above the fact tables (seen before the data it qualifies)",
  await p.evaluate(() => {
    const ban = document.querySelector('[data-feat="degraded-banner"]');
    const tbl = document.querySelector("#s7-detail .s7-tbl");
    if (!ban || !tbl) return false;
    return !!(ban.compareDocumentPosition(tbl) & Node.DOCUMENT_POSITION_FOLLOWING);
  }));

// A banner that always fires is as useless as one that never does: prove it HIDES on a clean run.
const clean = await p.evaluate(async (skip) => {
  const els = [...document.querySelectorAll("#s7-list .q-batch")].filter((e) => e.dataset.id !== skip);
  if (!els.length) return { skipped: true };
  els[0].click();
  await new Promise((r) => setTimeout(r, 2500));
  return { did: els[0].dataset.id,
           present: !!document.querySelector('[data-feat="degraded-banner"]') };
}, DID);
ok("banner is ABSENT on an undegraded run (it discriminates)",
  clean.skipped || clean.present === false, JSON.stringify(clean));

// ---------------------------------- gate@6 badge ----------------------------------
// No seeding needed for the VALUE: `assemble_record` computes overflow live at request time. We do
// need a draft to render it in; DRAFT_ID is created against the clone by the runbook above.
const DRAFT = process.env.DRAFT_ID || "draft_00011";
await p.evaluate(() => { document.querySelector("#stageSelect").value = "stage6"; });
await p.evaluate(() => document.querySelector("#stageSelect").dispatchEvent(new Event("change")));
await p.waitForTimeout(2000);
const s6 = await p.evaluate(async (draft) => {
  const el = [...document.querySelectorAll(".q-batch")].find((e) => e.dataset.id === draft);
  if (!el) return { opened: false, seen: [...document.querySelectorAll(".q-batch")].map((e) => e.dataset.id) };
  el.click();
  await new Promise((r) => setTimeout(r, 3000));
  const bad = document.querySelector('[data-feat="overflow-badge"][data-overflow="true"]');
  const row = bad && bad.closest(".s6-rep");
  return {
    opened: true,
    present: !!bad,
    text: bad ? bad.textContent.trim() : null,
    title: bad ? (bad.getAttribute("title") || "").slice(0, 60) : null,
    // the badge must sit ON the offending rep's row, not floating in the district header
    onRepRow: !!row,
    repFile: row ? (row.querySelector("code") || {}).textContent : null,
    // and a fitting rep in the same view must NOT be badged
    totalReps: document.querySelectorAll(".s6-rep").length,
    badgedReps: document.querySelectorAll('.s6-rep [data-feat="overflow-badge"][data-overflow="true"]').length,
  };
}, DRAFT);
ok("gate@6 draft opened", s6.opened, JSON.stringify(s6).slice(0, 160));
ok("overflow badge renders on the offending rep", s6.present, JSON.stringify(s6).slice(0, 200));
ok("badge is attached to the rep row it describes", s6.onRepRow, `rep=${s6.repFile}`);
ok("badge explains the ceiling in its tooltip",
  /exceeds this council's ceiling/.test(s6.title || ""), s6.title || "<none>");
ok("badge discriminates (not every rep is badged)",
  s6.totalReps > 0 && s6.badgedReps < s6.totalReps || s6.totalReps === s6.badgedReps && s6.totalReps === 1,
  `${s6.badgedReps}/${s6.totalReps} reps badged`);

ok("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));

console.log(out.join("\n"));
console.log(`\n${out.filter((l) => l.startsWith("PASS")).length}/${out.length} PASS`);
await b.close();
process.exit(out.some((l) => l.startsWith("FAIL")) ? 1 : 0);
