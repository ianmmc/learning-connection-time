// Tiered discovery capture (concurrent): Google Drive/Docs/Sheets/Slides via unauthenticated
// export URL (Tier 1 -- see capture_drive.mjs; Tier 2 OAuth Drive API not wired here yet,
// see ACQUISITION_PIPELINE.md Stage 3); direct-download PDFs/images; for HTML render ->
// innerText (main+iframes) as .txt, full-page screenshot as .png, AND page.pdf()
// UNCONDITIONALLY as .pdf. Relevance/extraction picks the best source.
//
// Emergent candidates: while an HTML page is rendered, its DOM is scanned for anchors
// whose text/href match SCHED_KW -- exactly one hop, never recursively chained. This is
// explicitly meant to catch CDN-hosted materials (Finalsite, BoardDocs, S3, etc. --
// discover.py's CMS_HOSTS) that Discovery's domain-scoped search would never surface
// directly, not just same-domain links.
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from 'fs';
import { createHash } from 'crypto';
import path from 'path';
import { isGoogleUrl, driveExportCandidates } from './capture_drive.mjs';

const ROOT = process.argv[2];
const CONC = parseInt(process.argv[3] || '5', 10);
const TIME = /\b\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?/g;

// Same keyword list discover.py's SCHED_KW already uses for ranking schedule-named URLs --
// reused here, not duplicated, so "what counts as a schedule link" stays one source of truth.
const SCHED_KW = ['bell', 'schedule', 'hours', 'start-time', 'start_time', 'daily-schedule', 'times', 'school-day', 'schoolday'];

// --- Modal dismissal, ported from infrastructure/scraper/src/capturer.ts -- verified pure
// Playwright with zero coupling to the dead Crawlee/Express-server architecture, so this is
// a near-verbatim port, not a rewrite. Strategy hierarchy (most robust to most brittle):
// 1. CSS injection to hide overlays globally (high leverage) 2. click dismiss buttons
// 3. DOM removal as last resort.
const MODAL_HIDING_CSS = `
  *[role="dialog"], *[aria-modal="true"], .modal, .modal-backdrop, .overlay, .popup,
  .cookie, .consent, .cookie-banner, .consent-modal,
  [class*="modal-overlay"], [class*="popup-overlay"], [class*="Backdrop"] {
    display: none !important; visibility: hidden !important;
  }
  body { overflow: auto !important; }
`;

const DISMISS_SELECTORS = [
  'button:has-text("Close")', 'button:has-text("Dismiss")', 'button:has-text("Got it")',
  'button:has-text("OK")', 'button:has-text("Accept")', 'button:has-text("Accept All")',
  'button:has-text("Agree")', 'button:has-text("Continue")', 'button:has-text("No Thanks")',
  "button:has-text(\"Don't Show Again\")", 'a:has-text("Close")', 'a:has-text("Dismiss")',
  '[aria-label="Close"]', '[aria-label="close"]', '[aria-label="Dismiss"]',
  '[aria-label="Close dialog"]', '[aria-label="Close modal"]', '[aria-label="accept cookies"]',
  'button[aria-label*="close" i]', 'button[aria-label*="dismiss" i]',
  '#onetrust-accept-btn-handler', 'button#acceptCookie', 'button[aria-label="dismiss cookie message"]',
  '.cookie-banner button:first-of-type', '.close-button', '.modal-close', '.popup-close',
  '.dialog-close', '.btn-close', 'button.close', '.modal button:has-text("×")', '.popup button:has-text("×")',
];

function setupPageDialogHandler(page) {
  page.on('dialog', async (dialog) => { await dialog.dismiss().catch(() => {}); });
}

async function dismissModals(page) {
  let dismissed = false;
  try { await page.addStyleTag({ content: MODAL_HIDING_CSS }); dismissed = true; } catch {}
  for (const selector of DISMISS_SELECTORS) {
    try {
      const el = page.locator(selector).first();
      if (await el.isVisible({ timeout: 500 })) {
        await el.click({ timeout: 1000 });
        dismissed = true;
        await page.waitForTimeout(300);
        break;
      }
    } catch { /* not found/not clickable, try next selector */ }
  }
  try {
    const removed = await page.evaluate(() => {
      let n = 0;
      for (const sel of ['div[class*="modal"][style*="position"]', 'div[class*="popup"][style*="position"]',
        'div[class*="overlay"][style*="position"]', 'div[role="dialog"]', 'div[aria-modal="true"]']) {
        document.querySelectorAll(sel).forEach((el) => {
          const s = window.getComputedStyle(el);
          if ((s.position === 'fixed' || s.position === 'absolute') && parseInt(s.zIndex || '0') > 100) { el.remove(); n++; }
        });
      }
      for (const sel of ['.modal-backdrop', '.overlay-backdrop', '[class*="backdrop"]', '[class*="Backdrop"]',
        '#cookieModal', '.cookie-modal', '.cookie-banner', '.consent-modal']) {
        document.querySelectorAll(sel).forEach((el) => { el.remove(); n++; });
      }
      return n;
    });
    if (removed > 0) dismissed = true;
  } catch {}
  return dismissed;
}

// --- Setup: load every district's candidates.json, build the initial task queue ---
const dirs = readdirSync(ROOT).filter((d) => existsSync(path.join(ROOT, d, 'candidates.json')));
const byDistrict = {};
const tasks = [];
for (const did of dirs) {
  const meta = JSON.parse(readFileSync(path.join(ROOT, did, 'candidates.json')));
  const capDir = path.join(ROOT, did, 'captures');
  mkdirSync(capDir, { recursive: true });
  byDistrict[did] = { capDir, records: [], seen: new Set() };
  for (const c of meta.candidates) {
    const u = stripFragment(c.url);
    byDistrict[did].seen.add(u);
    tasks.push({ did, url: u, tools: c.tools, source: 'discovered', found_on: null, capDir });
  }
}

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: 'Mozilla/5.0 (research; bell-schedule discovery)' });

// A URL fragment (#pageTitle, #nav_items_0, etc.) never represents different
// server-side content -- it's purely client-side same-page navigation. Found on the
// first real run: Stroudsburg's bell-schedule pages link to themselves via fragment
// anchors, and without stripping these, the same page got queued and re-captured 2-3
// times under fragment-different URLs.
function stripFragment(url) {
  try {
    const u = new URL(url);
    u.hash = '';
    return u.toString();
  } catch {
    return url.split('#')[0];
  }
}

function findEmergentLinks(anchors) {
  const out = [];
  for (const a of anchors) {
    const hay = `${a.text} ${a.href}`.toLowerCase();
    if (SCHED_KW.some((k) => hay.includes(k))) out.push(stripFragment(a.href));
  }
  return out;
}

async function processTask(t) {
  const { did, url, tools, source, found_on, capDir } = t;
  const h = createHash('md5').update(url).digest('hex').slice(0, 10);
  // One subdirectory per captured URL (named by its hash) -- not flat hash-prefixed files
  // sharing the district's captures/ folder. The whole point of hashing the URL was so a
  // human reviewing CP-B output can open one folder and see everything for that one page,
  // not have to mentally regroup files by matching prefixes.
  const recDir = path.join(capDir, h);
  mkdirSync(recDir, { recursive: true });
  const rec = { url, tools: tools || [], source, found_on, hash: h, ok: false, files: {} };
  try {
    // --- Google Drive / Docs / Sheets / Slides: Tier 1 only (Tier 2 OAuth not wired yet) ---
    if (isGoogleUrl(url)) {
      const drive = driveExportCandidates(url);
      if (drive) {
        let any = false;
        for (const { format, fetchUrl } of drive) {
          try {
            const r = await fetch(fetchUrl, { redirect: 'follow', signal: AbortSignal.timeout(20000) });
            const ct = (r.headers.get('content-type') || '').toLowerCase();
            if (ct.includes('html')) continue; // interstitial/error page -- this format failed, try the next
            const ext = format === 'auto' ? (ct.includes('pdf') ? 'pdf' : (ct.split('/')[1] || 'bin').split(';')[0]) : format;
            const buf = Buffer.from(await r.arrayBuffer());
            const filename = format === 'auto' ? `file.${ext}` : `${format}.${ext}`;
            writeFileSync(path.join(recDir, filename), buf);
            rec.files[format === 'auto' ? 'bin' : format] = filename;
            any = true;
          } catch { /* this format failed, try the next */ }
        }
        if (any) {
          rec.kind = 'drive_export';
          rec.ok = true;
          byDistrict[did].records.push(rec);
          return rec;
        }
      }
      // Tier 1 didn't pan out (folder URL, unrecognized pattern, or every format failed).
      // Per the Stage 3 design: a per-item flag, NOT a run-halting control failure -- one
      // stuck Drive item says nothing about the rest of the batch. Tier 2 (OAuth Drive
      // API) is not implemented in this script yet; until it is, this is the real outcome,
      // not a placeholder.
      rec.err = 'needs_oauth_reauth';
      byDistrict[did].records.push(rec);
      return rec;
    }

    let ct = '';
    try {
      const r = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(20000) });
      ct = (r.headers.get('content-type') || '').toLowerCase();
      rec.final_url = r.url;
      if (ct.includes('pdf') || ct.includes('image')) {
        const ext = ct.includes('pdf') ? 'pdf' : ((ct.split('/')[1] || 'img').split(';')[0]);
        writeFileSync(path.join(recDir, `original.${ext}`), Buffer.from(await r.arrayBuffer()));
        rec.kind = ct.includes('pdf') ? 'pdf' : 'image';
        rec.files.bin = `original.${ext}`;
        rec.ok = true;
      }
    } catch { /* fall through to render */ }

    if (!rec.ok) {
      const page = await ctx.newPage();
      setupPageDialogHandler(page);
      try {
        await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
        await page.waitForTimeout(2500);
        rec.final_url = page.url();

        // Modal dismissal sequenced AFTER the 2.5s wait, giving slow/deliberately-delayed
        // cookie-consent banners a window to actually render before dismissal is attempted.
        const modalsDismissed = await dismissModals(page);
        rec.modals_dismissed = modalsDismissed;
        if (modalsDismissed) await page.waitForTimeout(500);

        let text = '';
        for (const fr of page.frames()) {
          try { text += `\n${(await fr.evaluate(() => (document.body ? document.body.innerText : ''))) || ''}`; } catch {}
        }
        writeFileSync(path.join(recDir, 'page.txt'), text);
        await page.screenshot({ path: path.join(recDir, 'page.png'), fullPage: true }).catch(() => {});
        // Unconditional -- no multi-column-detection trigger. Local compute is free; the
        // decision of which representation to actually use moves downstream to Stage 4/7.
        await page
          .pdf({
            path: path.join(recDir, 'page.pdf'),
            format: 'Letter',
            scale: 0.9,
            margin: { top: '0.5in', bottom: '0.5in', left: '0.5in', right: '0.5in' },
            printBackground: true,
          })
          .then(() => { rec.files.pdf = 'page.pdf'; })
          .catch((e) => { rec.pdf_err = String(e).slice(0, 80); });

        rec.kind = 'html';
        rec.files.txt = 'page.txt';
        rec.files.png = 'page.png';
        rec.text_times = (text.match(TIME) || []).length;
        rec.ok = true;

        // --- Emergent candidates: exactly one hop, never recursive. An emergent
        // candidate's own page is never scanned for further emergent candidates. ---
        if (source === 'discovered') {
          const anchors = await page
            .evaluate(() => Array.from(document.querySelectorAll('a[href]')).map((a) => ({ text: a.innerText || '', href: a.href })))
            .catch(() => []);
          for (const eu of findEmergentLinks(anchors)) {
            if (byDistrict[did].seen.has(eu)) continue;
            byDistrict[did].seen.add(eu);
            tasks.push({ did, url: eu, tools: [], source: 'emergent', found_on: rec.final_url, capDir });
          }
        }
      } finally {
        await page.close();
      }
    }
  } catch (e) {
    rec.err = String(e).slice(0, 120);
  }
  byDistrict[did].records.push(rec);
  return rec;
}

let idx = 0;
let done = 0;
async function worker() {
  while (idx < tasks.length) {
    const t = tasks[idx++];
    await processTask(t);
    if (++done % 25 === 0) console.log(`  ...${done}/${tasks.length} captured`);
  }
}
console.log(`capturing ${tasks.length} candidate URLs across ${dirs.length} districts (concurrency ${CONC})`);
await Promise.all(Array.from({ length: CONC }, () => worker()));

for (const did of Object.keys(byDistrict)) {
  writeFileSync(path.join(ROOT, did, 'captures.json'), JSON.stringify(byDistrict[did].records, null, 2));
}
await browser.close();
console.log(`CAPTURE DONE — ${done} URLs (incl. emergent), ${dirs.length} districts`);
