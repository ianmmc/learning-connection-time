// #717 console verification — the gate@6 already-extracted held rows + the re-extraction cost split.
//
// Deliberately NOT a `*.test.mjs`: `npm test` globs those, and this needs a LIVE console server + the
// governance DB, so it must never run unattended in CI. Follows verify_822_console.mjs / _684 / _673:
// the logic is pinned DB-free elsewhere (tests/test_stage6_already_extracted_delta.py, 20 tests),
// and THIS is the end-to-end pass proving it RENDERS.
//
// WHY THIS ONE NEEDS NO SEEDING — unlike #822's. The delta is computed LIVE at request time from the
// immutable handoff receipts + the extraction/school_fact tables, and four real districts already
// exercise it: batch_00043's Little Rock, New Haven Unified, Washoe and Sweetwater compose to ZERO
// sends because everything they offer was bought by a prior production run. So the fixture is the
// production corpus itself. A CLONE is still required, because building a draft WRITES
// (dispatch_draft + a draft_add_district event) and must never touch the human's DB.
//
// THE FAILURE THIS EXISTS TO CATCH. stage6.js has no generic held-record row — it renders one block
// per KNOWN reason string. An unpinned reason is therefore not a cosmetic miss but total
// invisibility: Little Rock would render a bare "no send-eligible records", and the reviewer could
// not tell "we found nothing" from "we already have it". Source-pinning alone cannot prove the block
// actually reaches the DOM, which is what this file does.
//
// Run:
//   docker exec lct_postgres psql -U lct_user -d postgres \
//     -c "DROP DATABASE IF EXISTS gov_717_scratch;" \
//     -c "CREATE DATABASE gov_717_scratch TEMPLATE governance OWNER governance_user;"
//   GOVERNANCE_DB_NAME=gov_717_scratch python3 -m uvicorn \
//     infrastructure.acquisition.process_governance.server:app --port 8015 &
//   cd infrastructure/scraper && node verify_717_console.mjs
//   docker exec lct_postgres psql -U lct_user -d postgres -c "DROP DATABASE gov_717_scratch;"
// (Scratch PORT 8015, never the :8005 the human's console is on. Reload the browser for static/*.js;
// restart the server for Python changes.)
//
// The verifier BUILDS ITS OWN DRAFT over the two districts that make the two cases, so it is
// self-contained and rerunnable: 0509000 Little Rock (ALL 3 reps already bought -> zero sends) and
// 0902790 New Haven CT (6 of 16 bought -> a partial district that must still send its 10 new reps).
//
// REQ-176: cloning does NOT protect the git-tracked JSON twins — every exporter rebuilds them
// WHOLESALE from the connected DB. Expect
//   [paths] NON-CANONICAL governance DB 'gov_717_scratch' (#822) — district_status.json export
//           quarantined to .../lct-test-quarantine/district_status.json
// in the server log. Seeing that line is the guard WORKING. If you do NOT see it while running
// against a clone, stop and check `git status data/acquisition/` before continuing.
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:8015";
const EMPTY_DID = process.env.EMPTY_DID || "0509000";    // Little Rock — every rep already bought
const PARTIAL_DID = process.env.PARTIAL_DID || "0902790"; // New Haven CT — 6 bought, 10 new
const REASON = "already-extracted:prior-production-run";

const out = [];
const ok = (name, cond, detail = "") =>
  out.push(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);

const post = (path, body) =>
  fetch(BASE + path, { method: "POST", headers: { "content-type": "application/json" },
                       body: JSON.stringify(body) }).then((r) => r.json());

// ---------------------------------------------------------------- build the fixture draft
const draft = await post("/api/dispatch/create", { actor: "verify717" });
const draftId = draft.draft_id;
for (const did of [EMPTY_DID, PARTIAL_DID])
  await post(`/api/dispatch/${draftId}/edit`, { op: "add_district", district_id: did, actor: "verify717" });

const view = await fetch(`${BASE}/api/dispatch/${draftId}`).then((r) => r.json());
const pkg = view.package || {};
const blockOf = (did) => (pkg.districts || []).find((d) => d.district_id === did) || {};
const heldOf = (did) => (blockOf(did).records || []).filter((r) => r.reason === REASON);

// ---------------------------------------------------------------- SERVER: the payload is right
ok("server: the zero-send district composes 0 send reps",
   blockOf(EMPTY_DID).n_send_reps === 0, `n_send_reps=${blockOf(EMPTY_DID).n_send_reps}`);
ok("server: ...and holds every one of them with the delta's reason",
   heldOf(EMPTY_DID).length === 3, `${heldOf(EMPTY_DID).length} held`);
ok("server: the partial district STILL SENDS its new reps (no over-subtraction)",
   blockOf(PARTIAL_DID).n_send_reps === 10, `n_send_reps=${blockOf(PARTIAL_DID).n_send_reps}`);
ok("server: ...while holding the already-bought ones",
   heldOf(PARTIAL_DID).length === 6, `${heldOf(PARTIAL_DID).length} held`);
ok("server: the cost preview separates re-extraction from new spend",
   (pkg.cost?.reextraction?.n_reps || 0) === 9 && pkg.cost.reextraction.usd > 0,
   JSON.stringify(pkg.cost?.reextraction));
ok("server: redo is stamped on the package so preview and freeze agree",
   pkg.redo === false, `redo=${pkg.redo}`);

// The delta must be a pure subtraction: new + avoided reconstructs what a redo would buy. Asserted
// against the LIVE redo build, not a recollection — a rep may be counted as new or as avoided,
// never as neither (silent loss) nor as both (double-counted savings).
const redoPkg = await post("/api/handoff/preview",
  { district_ids: [EMPTY_DID, PARTIAL_DID], redo: true });
const redoReps = redoPkg.package?.cost?.n_reps ?? redoPkg.cost?.n_reps;
ok("server: new + avoided == the redo total (the delta only ever subtracts)",
   pkg.cost.n_reps + pkg.cost.reextraction.n_reps === redoReps,
   `${pkg.cost.n_reps} + ${pkg.cost.reextraction.n_reps} vs redo ${redoReps}`);

// ---------------------------------------------------------------- DOM: it actually renders
const b = await chromium.launch();
const p = await b.newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));
p.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

// Stage selection is a <select>, not a route (verify_822's pattern).
await p.goto(BASE, { waitUntil: "networkidle" });
await p.evaluate(() => {
  const el = document.querySelector("#stageSelect");
  el.value = "stage6";
  el.dispatchEvent(new Event("change"));
});
await p.waitForSelector(`#s6-list .q-batch[data-id="${draftId}"]`, { timeout: 15000 });
await p.click(`#s6-list .q-batch[data-id="${draftId}"]`);
await p.waitForSelector(`.s6-dist[data-did="${EMPTY_DID}"]`, { timeout: 15000 });

const summaries = await p.locator('[data-feat="s6-already-extracted-summary"]').count();
const rows = await p.locator('[data-feat="s6-already-extracted"]').count();
ok("DOM: a summary row renders for each district the delta touched", summaries === 2, `${summaries}`);
ok("DOM: every held record renders its own row", rows === 9, `${rows} rows`);

const emptyBlock = p.locator(`.s6-dist[data-did="${EMPTY_DID}"]`);
const emptyText = await emptyBlock.innerText();
// The empty state must AGREE with the held rows beneath it. The first run of this verifier caught
// the district printing "no send-eligible records" AND the already-extracted rows together — a
// contradiction the reviewer would have to adjudicate.
ok("DOM: the zero-send district EXPLAINS itself rather than reading 'no send-eligible records'",
   emptyText.includes("already extracted") && !emptyText.includes("no send-eligible records"),
   JSON.stringify(emptyText.slice(0, 120)));
ok("DOM: ...via the dedicated all-already-extracted note",
   await emptyBlock.locator('[data-feat="s6-all-already-extracted"]').count() === 1);
ok("DOM: ...and it is still VISIBLE, not dropped from the draft",
   await emptyBlock.count() === 1);
ok("DOM: the held rows name the document, so the reviewer can check the call",
   (await emptyBlock.locator('[data-feat="s6-already-extracted"] code').first().innerText()).length > 0);

const rx = p.locator('[data-feat="s6-reextraction-avoided"]');
ok("DOM: the re-extraction split renders in the summary", await rx.count() === 1);
const rxText = await rx.first().innerText();
ok("DOM: ...naming the rep count and the avoided dollars",
   /\b9\b/.test(rxText) && /\$/.test(rxText), JSON.stringify(rxText.slice(0, 110)));
ok("DOM: the redo affordance points at the real path",
   rxText.includes("redo") || (await p.locator('[data-feat="s6-already-extracted-summary"]')
     .first().innerText()).includes("redo"),
   "the summary must name the control that re-admits the reps");

// #903: the declared-redo toggle — DRIVEN, not just present. Before #903 the draft workflow could
// never set redo=True (no field, no edit op), so a gate@8 8->6 send-back redispatch composed to
// zero new sends with no console override. Ticking it must re-admit the held reps live.
const redoToggle = p.locator('[data-feat="s6-redo-toggle"] input#s6-redo');
ok("DOM: the #903 redo toggle renders on the draft", await redoToggle.count() === 1);
await redoToggle.check();
await p.waitForSelector('[data-feat="s6-redo"]', { timeout: 15000 });
const emptyReps = await p.locator(`.s6-dist[data-did="${EMPTY_DID}"] .s6-rep-click`).count();
ok("DOM: ticking redo re-admits the reps (the zero-send district now sends)",
   emptyReps === 3, `${emptyReps} send rows`);
ok("DOM: under redo the avoided line is gone (every rep priced as new)",
   await p.locator('[data-feat="s6-reextraction-avoided"]').count() === 0);
ok("DOM: the draft header badges the redo so the mode cannot be missed",
   await p.locator('[data-feat="s6-redo"]').count() === 1);

ok("DOM: no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));

await b.close();
await post(`/api/dispatch/${draftId}/abandon`, { actor: "verify717", reason: "verifier cleanup" });

console.log(out.join("\n"));
const failed = out.filter((l) => l.startsWith("FAIL")).length;
console.log(`\n${out.length - failed}/${out.length} PASS`);
process.exit(failed ? 1 : 0);
