// #684 console verification — gate@5 against the REAL Bentonville employee-handbook record.
//
// Deliberately NOT a `*.test.mjs`: `npm test` globs `*.test.mjs`, and this needs a LIVE console server
// and the governance DB, so it must never run unattended in CI. The DOM/source invariants it checks are
// separately pinned DB-free by tests/test_684_staff_day_confusable.py; this is the end-to-end pass that
// proves they actually render on a real record — the thing the repo's outstanding-work list keeps losing
// because past console verifications left nothing rerunnable behind.
//
// Run:  python3 -c "import uvicorn; from infrastructure.acquisition.process_governance.server import app; \
//         uvicorn.run(app, host='127.0.0.1', port=8015)" &
//       cd infrastructure/scraper && node verify_684_console.mjs        # BASE=… to point elsewhere
// (Run it on a scratch PORT, not the :8005 the human's console is on. Restart the server after any
// Python change — /api/detector-weights is server-rendered.)
//
// Asserts: the staff-day evidence is visible in the objective Signals panel with its counts, the
// office/building-hours confounder checkbox is pre-checked by lf_staff_day (not lf_office_hours alone),
// the glossary + row tooltip define the shape, and the relevance-density strip paints staff_duty at the
// duty clauses — but ONLY when the server voted (the #521 mirrors-never-re-derives guardrail).
// Last run 2026-07-29 on `0503060:a5f32ff869`: 11/11 PASS.
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:8015";
const REC = "0503060:a5f32ff869";
const out = [];
const ok = (name, cond, detail = "") =>
  out.push(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);

const b = await chromium.launch();
const p = await b.newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));
p.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

await p.goto(`${BASE}/?q=${encodeURIComponent(REC.split(":")[1])}`, { waitUntil: "networkidle" });
await p.waitForTimeout(2000);

// the console keys record rows by data-rec-key and exposes selectRecord(recKey, li)
const clicked = await p.evaluate(async (rec) => {
  const li = document.querySelector(`.rec-row[data-rec-key="${rec}"]`);
  if (!li) return { ok: false, rows: document.querySelectorAll(".rec-row").length };
  await selectRecord(rec, li);
  return { ok: true };
}, REC);
await p.waitForTimeout(2500);

const body = await p.evaluate(() => document.body.innerText);
ok("record opened", clicked.ok && /tier\s*B/i.test(body), JSON.stringify(clicked));

// 1. the staff-day evidence is surfaced in the OBJECTIVE signals panel (the demoting evidence must be
//    visible to the labeler, not only implied by a pre-checked box)
const sigRow = (body.match(/staff duty-day times[^\n]*\n?[^\n]*/i) || [""])[0].replace(/\s+/g, " ");
ok("staff duty-day signal row visible with its counts",
  /staff duty-day times/i.test(body) && /9 governed by report\/remain clauses/i.test(body),
  sigRow || "<no match>");

// 2. the office/building-hours checkbox is pre-checked (hinted by lf_staff_day)
const checkState = await p.evaluate(() => {
  const el = document.querySelector('#facet_office_building_hours, [id*="office_building_hours"], '
    + '[name*="office_building_hours"], [value="office_building_hours"]');
  if (!el) {
    const lab = [...document.querySelectorAll("label")].find((l) =>
      /Building \/ office hours/i.test(l.textContent));
    const inp = lab && lab.querySelector("input");
    return inp ? { found: true, checked: inp.checked, via: "label" } : { found: false };
  }
  return { found: true, checked: !!el.checked, via: el.id || el.name };
});
ok("office/building-hours confounder pre-checked by lf_staff_day",
  checkState.found && checkState.checked, JSON.stringify(checkState));

// 3. the client-side registries carry the new event + the ported regexes
const clientState = await p.evaluate(() => ({
  weight: (typeof DWEIGHTS !== "undefined" && DWEIGHTS && DWEIGHTS.staff_duty) || null,
  hasHelper: typeof dnStaffDutyOffsets === "function",
  dutyOffsets: typeof dnStaffDutyOffsets === "function"
    ? dnStaffDutyOffsets("Elementary staff with a school start time of 7:30 a.m. are to report to "
      + "work by 7:15 a.m. and remain until 3:00 p.m.").length
    : -1,
  studentOffsets: typeof dnStaffDutyOffsets === "function"
    ? dnStaffDutyOffsets("Students must report to the office after 8:05 a.m. for a tardy pass.").length
    : -1,
}));
ok("dnStaffDutyOffsets exists and finds the staff clauses",
  clientState.hasHelper && clientState.dutyOffsets >= 1, JSON.stringify(clientState));
ok("dnStaffDutyOffsets rejects a student 'report to' clause",
  clientState.studentOffsets === 0, `student offsets=${clientState.studentOffsets}`);
ok("server-supplied staff_duty weight reached the client (#521: ONE weight source)",
  clientState.weight && clientState.weight.polarity === -1 && clientState.weight.weight === 0.7,
  JSON.stringify(clientState.weight));

// 3b. the heat-strip actually PAINTS the event — and only when the server voted lf_staff_day
const painted = await p.evaluate(async () => {
  const W = await (typeof detectorWeights === "function" ? detectorWeights()
    : Promise.resolve(typeof DWEIGHTS !== "undefined" ? DWEIGHTS : null));
  const txt = "Elementary staff with a school start time of 7:30 a.m. are to report to work by "
    + "7:15 a.m. and remain until 3:00 p.m.";
  const voted = dnEvents(txt, { detectors: [{ name: "lf_staff_day", strength: "strong" }] }, W);
  const notVoted = dnEvents(txt, { detectors: [] }, W);
  const n = (ev) => ev.filter((e) => e.type === "staff_duty");
  return { voted: n(voted).length, notVoted: n(notVoted).length,
           weight: n(voted).length ? n(voted)[0].weight : null };
});
ok("heat-strip paints staff_duty at the duty clauses when the server voted",
  painted.voted >= 1 && painted.weight === -0.7, JSON.stringify(painted));
ok("heat-strip paints NOTHING when the server did not vote (#521: mirrors, never re-derives)",
  painted.notVoted === 0, JSON.stringify(painted));

// 4. the glossary definition names the staff-day shape (the labeler's reference for the checkbox)
await p.click("#glossaryBtn");
await p.waitForTimeout(400);
const gloss = await p.evaluate(() => {
  const el = document.querySelector("#glossaryBody");
  const t = el ? el.innerText : "";
  const i = t.search(/EMPLOYEE\/STAFF day/i);
  return { open: !document.querySelector("#glossary").classList.contains("hidden"),
           snippet: i >= 0 ? t.slice(Math.max(0, i - 30), i + 110).replace(/\s+/g, " ") : null };
});
ok("glossary defines the employee/staff-day shape", gloss.open && !!gloss.snippet,
  gloss.snippet || "<not found>");
// and the signal row's own tooltip carries the same definition
const tip = await p.evaluate(() => {
  document.querySelector("#glossaryClose").click();
  const el = [...document.querySelectorAll("[title]")].find((n) => /EMPLOYEE\/STAFF day/i.test(n.title));
  return el ? el.title.slice(0, 90).replace(/\s+/g, " ") : null;
});
ok("signals-panel row is tooltipped with the definition", !!tip, tip || "<not found>");

ok("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));

await p.screenshot({ path: "/tmp/684-gate5-bentonville.png", fullPage: false });
await b.close();
console.log(out.join("\n"));
console.log(out.some((l) => l.startsWith("FAIL")) ? "\nRESULT: FAIL" : "\nRESULT: ALL PASS");
