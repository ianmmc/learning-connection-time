// #682/#689 console verification — gate@8's two arrows against REAL districts: the Stage-9 write badge
// on an approved one, and the send-back routing controls on a sent-back one.
//
// Deliberately NOT a `*.test.mjs`: `npm test` globs `*.test.mjs`, and this needs a LIVE console server
// plus the governance DB, so it must never run unattended in CI. The wiring is pinned DB-free by
// tests/test_stage8_api.py (#682 block); this is the end-to-end pass proving the badge actually renders
// on real records — the rerunnable pattern established by verify_684_console.mjs.
//
// Run:  python3 -c "import uvicorn; from infrastructure.acquisition.process_governance.server import app; \
//         uvicorn.run(app, host='127.0.0.1', port=8015)" &
//       cd infrastructure/scraper && node verify_682_console.mjs        # BASE=… / DID=… to point elsewhere
// (Scratch PORT :8015, never the human's :8005. Reload the browser for static/*.js; restart the server
// for Python changes — the detail endpoint is what carries `incorporation`.)
//
// Asserts the F8 surface: an approved+written district reads "written" (not merely "approved"), the
// badge carries data-feat="incorporation", and the detail API answers the two questions the badge is
// derived from (what the write did, and whether it matches TODAY's facts).
// Last run 2026-08-15 on 0503060 (Bentonville, approved + incorporated) and 1200180 (Broward, the
// live send-back pin): 11/11 PASS.
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:8015";
const DID = process.env.DID || "0503060";
const out = [];
const ok = (name, cond, detail = "") =>
  out.push(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);

const b = await chromium.launch();
const p = await b.newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(String(e)));
p.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

// 1. the API half — the badge can only be as honest as what the detail endpoint reports
const api = await (await fetch(`${BASE}/api/aggregate/district/${DID}`)).json();
const inc = api.incorporation;
ok("detail endpoint carries `incorporation`", inc != null, JSON.stringify(inc));
ok("it names WHAT HAPPENED (incorporated | incorporation_blocked)",
  inc && ["incorporated", "incorporation_blocked"].includes(inc.kind), inc && inc.kind);
ok("and whether it matches TODAY's facts (`current`)",
  inc && typeof inc.current === "boolean",
  inc && `current=${inc.current} written_fp=${String(inc.fingerprint).slice(0, 8)} live_fp=${String(api.fingerprint).slice(0, 8)}`);

// 2. the DOM half — open gate@8 and the district, then read the header badges
await p.goto(BASE, { waitUntil: "networkidle" });
await p.evaluate(() => { document.querySelector('[data-view="stage8"], #tab-stage8, [href="#stage8"]')?.click(); });
await p.waitForTimeout(1500);
const opened = await p.evaluate(async (did) => {
  if (typeof window.initStage8 === "function") window.initStage8();
  await new Promise((r) => setTimeout(r, 1200));
  const row = [...document.querySelectorAll("#s8-list [data-did], #s8-list li, #s8-list .q-batch")]
    .find((el) => (el.dataset.did || el.textContent || "").includes(did));
  if (!row) return { ok: false, rows: document.querySelectorAll("#s8-list li").length };
  row.click();
  await new Promise((r) => setTimeout(r, 1800));
  return { ok: true };
}, DID);

const badge = await p.evaluate(() => {
  const el = document.querySelector('[data-feat="incorporation"]');
  return el ? { text: el.textContent.trim(), title: el.getAttribute("title"), cls: el.className } : null;
});
ok("district opened at gate@8", opened.ok, JSON.stringify(opened));
ok("the write badge renders beside the decision", badge != null, JSON.stringify(badge));
ok("and it says what production actually holds",
  badge != null && /written|not written/.test(badge.text), badge && badge.text);
// 3. #689 — a SENT-BACK district must show where it can go. Broward 1200180 is the live pin: sent
//    back 2026-07-29 with a reason that names the 8->1 route, and nothing routed anywhere since.
const SB_DID = process.env.SB_DID || "1200180";
const sbApi = await (await fetch(`${BASE}/api/aggregate/district/${SB_DID}`)).json();
ok("a sent-back district reports its routing state",
  sbApi.decision && sbApi.decision.disposition === "sent_back"
  && "send_back_routing" in sbApi,
  `disposition=${sbApi.decision && sbApi.decision.disposition} routing=${JSON.stringify(sbApi.send_back_routing)}`);

const unrouted = await (await fetch(`${BASE}/api/aggregate/send-backs`)).json();
ok("and the forgotten ones are queryable as a list",
  Array.isArray(unrouted) && (sbApi.send_back_routing != null
    || unrouted.some((r) => r.district_id === SB_DID)),
  `${unrouted.length} unrouted: ${unrouted.map((r) => r.district_id).join(", ")}`);

const sbOpened = await p.evaluate(async (did) => {
  const row = [...document.querySelectorAll("#s8-list [data-did], #s8-list li, #s8-list .q-batch")]
    .find((el) => (el.dataset.did || el.textContent || "").includes(did));
  if (!row) return { ok: false };
  row.click();
  await new Promise((r) => setTimeout(r, 1800));
  const el = document.querySelector('[data-feat="send-back-route"]');
  return { ok: !!el, text: el ? el.textContent.trim().slice(0, 160) : null,
           routes: [...document.querySelectorAll("[data-route]")].map((b) => b.dataset.route) };
}, SB_DID);
ok("the routing controls render at gate@8", sbOpened.ok, JSON.stringify(sbOpened).slice(0, 240));
ok("both back-edges are offered (or the routing is already recorded)",
  (sbOpened.routes && sbOpened.routes.length === 2) || /re-routed/.test(sbOpened.text || ""),
  JSON.stringify(sbOpened.routes));

ok("no page errors", errors.length === 0, errors.join(" | "));

console.log(out.join("\n"));
await b.close();
process.exit(out.some((l) => l.startsWith("FAIL")) ? 1 : 0);
