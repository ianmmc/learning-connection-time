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
//
// Hosting/CMS fingerprint (added 2026-06-24): every record carries a `fingerprint` block of
// RAW signals about how/where the page is hosted (host, response headers, CDN hints, <meta
// generator>, off-domain resource hosts, a JS-dependency flag, and one cheap cms_hint from
// CMS_HOSTS). Facts only -- no real CMS classification here; that's a later pure function
// over these signals, refinable retroactively without re-capture. Same "capture facts,
// decide downstream" invariant as the rest of the pipeline.
//
// Modes:
//   node capture_discovery.mjs <ROOT> [CONC]                       -- capture every district under ROOT
//   node capture_discovery.mjs district <ROOT> <DISTRICT_DIR> [CONC] [DEADLINE_S] -- capture ONE
//       district dir (the console's batch-scoped, per-district runner -- never re-captures the rest of
//       ROOT). DEADLINE_S>0 = node-owns-shutdown: write a partial manifest on the deadline, never orphan.
//   node capture_discovery.mjs backfill-fingerprints <ROOT> [CONC] -- re-visit existing
//       records and patch in `fingerprint` only (does NOT re-render/re-save page.* or touch
//       Stage 4 outputs -- additive, keeps processed.json valid). For parity on pre-2026-06-24
//       captures that predate fingerprinting.
//   node capture_discovery.mjs recompute-cms-hint <ROOT>           -- re-derive ONLY cms_hint
//       from each record's already-stored fingerprint (no browser, no network). Apply a
//       human-approved CMS_HOSTS change to already-captured data without re-capturing.
//   node capture_discovery.mjs recompute-fidelity <ROOT>            -- re-derive ONLY the #518
//       fidelity flags from facts already on disk (url/final_url, page.txt head,
//       fingerprint.has_password) -- apply a LOGIN/SOFT404 regex tuning without re-capturing.
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync, renameSync } from 'fs';
import { createHash } from 'crypto';
import path from 'path';
import { pathToFileURL, fileURLToPath } from 'url';
import { isGoogleUrl, driveExportCandidates } from './capture_drive.mjs';

// Matches discover_stage2.py's write_discovery() convention exactly (Python's
// datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")) -- an existing captures.json is
// never overwritten in place, it's renamed aside with a UTC timestamp suffix first. data/raw/
// is write-once in spirit; this was a real gap (capture_discovery.mjs used to just
// writeFileSync over whatever was there), found while designing Stage 4's own redo
// convention and fixed here to match Stage 2's, not invent a second one.
function tsSuffix() {
  return new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
}

function writeVersioned(filePath, content) {
  if (existsSync(filePath)) {
    const ts = tsSuffix();
    const dir = path.dirname(filePath);
    const base = path.basename(filePath, '.json');
    renameSync(filePath, path.join(dir, `${base}.${ts}.json`));
  }
  writeFileSync(filePath, content);
}

const TIME = /\b\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?/g;

// Schedule-link keywords for the emergent-candidate scan (REQ-084): an anchor whose text/href hits
// one of these gets queued as a one-hop emergent capture. This is now the list's ONLY home —
// discover.py's Python twin (SCHED_KW, once used by the retired candidate-ranking bench) was
// deleted with #87.
const SCHED_KW = ['bell', 'schedule', 'hours', 'start-time', 'start_time', 'daily-schedule', 'times', 'school-day', 'schoolday'];

// Bound operations that lack an effective native timeout: page.pdf() has NONE, and a full-page
// screenshot can crawl on infinite-scroll pages. One hung page must not consume the whole per-district
// budget (Brookwood SD 167 burned 1800s this way). The lingering op is aborted by the page.close() in
// the per-task finally. The per-district budget (stage3 headless CAPTURE_TIMEOUT_S) is the backstop.
const OP_TIMEOUT_MS = 45000;
// Exported for unit testing (#127/REQ-079). The reject timer is CLEARED once the race settles, so a
// fast-resolving op leaves no 45s timer dangling on the event loop (also lets node:test exit cleanly).
export const withTimeout = (p, ms, label) => {
  let timer;
  const timeout = new Promise((_, rej) => {
    timer = setTimeout(() => rej(new Error(`${label} timed out after ${ms}ms`)), ms);
  });
  return Promise.race([p, timeout]).finally(() => clearTimeout(timer));
};
// Cap emergent (one-hop) candidates per district so a link-dense page can't explode the task queue.
const EMERGENT_CAP = 25;

// CMS_HOSTS is the shared config-as-data knob `cms_hosts` -- the SAME JSON file discover.py reads,
// so the two can no longer drift (REQ-089, ending the prior hand-synced duplication). Domain
// SUFFIXES signalling a known K-12 CMS / content host, matched via endsWith. Governance +
// per-entry provenance live in the config file. Path resolved from this module (CWD-independent):
// infrastructure/scraper/ -> ../acquisition/common/config/cms_hosts.json.
function loadConfigValues(name) {
  // Read a config-as-data knob (REQ-088) in either shape: {entries:[{value}]} or
  // {values:[...], additions:[{value}]}. Path resolved from this module (CWD-independent).
  const f = path.join(path.dirname(fileURLToPath(import.meta.url)),
                      '..', 'acquisition', 'common', 'config', `${name}.json`);
  const doc = JSON.parse(readFileSync(f, 'utf8'));
  if (doc.entries) return doc.entries.map((e) => e.value);
  return (doc.values || []).concat((doc.additions || []).map((a) => a.value));
}

const CMS_HOSTS = loadConfigValues('cms_hosts');
// De-chrome landmark selectors (REQ-091) — the SAME config knob Stage 5 documents. innerText of
// these is captured as page.header/footer/nav.txt; page.main.txt = body minus these (the de-chromed
// text Stage 5 tiers on, so footer building-hours / school-switcher nav can't inject false signal).
export const DE_CHROME_LANDMARKS = loadConfigValues('de_chrome_landmarks');

// --- Capture-fidelity flags (#518) --------------------------------------------------------
// Detect captures that succeed mechanically (ok:true) but whose CONTENT is not what the URL
// promised -- a login wall or a styled soft-404 page. Flag, never drop: the record still
// captures and processes normally; the flag makes the fidelity problem queryable downstream
// (Stage 5 must see "capture suspect", not a silent target_absent). Sized by the 2026-07-19
// corpus survey on #518: 2 login walls + 9 soft-404s among 1,471 live records, all ok:true.
// Derived ONLY from persisted facts (url/final_url, page.txt, fingerprint.has_password), so
// `recompute-fidelity` can re-derive flags after a regex change without re-capturing --
// the same capture-facts/classify-downstream split as cms_hint.
// Boundary groups allow `-`/`_`/word-break forms (/login-page, /log-in, /sign-in-form) --
// under-flagging is the costlier error at flag-not-drop semantics. The bare `returnurl=`
// alternative can false-positive on CMS breadcrumb params carried by non-login pages; accepted
// deliberately (flag-not-drop + the gate@5 human review absorbs the rare over-flag).
const LOGIN_URL_RE = /login\.aspx|[/._-]log[-_]?[io]n([/.?_-]|$)|[/._-]sign[-_]?in([/.?_-]|$)|[?&]returnurl=/i;
// \s+ separators: innerText renders &nbsp;/<br> between the words as  /\n, both matched by \s.
const SOFT404_RE = /page\s+(?:not|cannot\s+be|could\s+not\s+be)\s+found|status\s*:?\s*404|error\s*:?\s*404|404\s+error/i;
// "A real content page": shared with the js_dependent fingerprint signal so login-wall detection
// and JS-dependence classification can't silently disagree about whether a page has substance.
const SUBSTANTIAL_TEXT_CHARS = 600;

export function fidelityFlags({ url = '', finalUrl = '', text = '', hasPassword = false } = {}) {
  const flags = [];
  // Login wall: the URL itself is a login endpoint (Huntington's gateway/Login.aspx?returnUrl=...),
  // or the rendered page is password-gated with almost no content of its own.
  if (LOGIN_URL_RE.test(finalUrl) || LOGIN_URL_RE.test(url)
      || (hasPassword && text.trim().length < SUBSTANTIAL_TEXT_CHARS)) flags.push('login_wall');
  // Soft-404: a styled "Page Not Found" served 200 (verified visually on morey/arlington.sburg.org
  // bell-schedule URLs). Scan only the head of the text so a long article MENTIONING a 404 can't trip it.
  if (SOFT404_RE.test(text.slice(0, 3000))) flags.push('soft_404');
  return flags;
}

// --- Fingerprint helpers (raw signals only, no classification) ---------------------------
// The pure ones are exported for unit testing (capture_fingerprint.test.mjs); the
// browser-driving ones are not.
export function hostOf(u) {
  try { return new URL(u).hostname.toLowerCase(); } catch { return ''; }
}

// Presence-detect well-known CDN/host platforms from response headers. Deliberately a small,
// explicit list -- not an exhaustive ruleset (that's a later analysis concern, refinable over
// the accumulated raw headers). `headers` is a plain object with lowercase keys.
export function cdnHints(headers) {
  const out = [];
  const server = (headers['server'] || '').toLowerCase();
  if (headers['cf-ray'] || server.includes('cloudflare')) out.push('cloudflare');
  if (Object.keys(headers).some((k) => k.startsWith('x-amz'))) out.push('aws');
  if (headers['x-vercel-id'] || headers['x-vercel-cache']) out.push('vercel');
  if (headers['x-github-request-id']) out.push('github-pages');
  if (server.includes('netlify') || headers['x-nf-request-id']) out.push('netlify');
  if (headers['x-served-by'] || server.includes('fastly')) out.push('fastly');
  if (server.includes('windows-azure') || headers['x-ms-blob-type'] || headers['x-azure-ref']) out.push('azure');
  if (server.includes('gse') || headers['x-goog-generation'] || headers['x-guploader-uploadid']) out.push('google');
  return out;
}

// Dot-boundary host-suffix predicate -- the JS twin of discover.py's `_host_matches` (#416/#34):
// exact host or dot-boundary suffix ONLY (a dotless endsWith would let `myfinalsite.net` claim
// `finalsite.net`). The RULE is parity-pinned across both languages by the shared golden-vector
// fixture `common/config/cms_host_match_cases.json` (consumed by capture_fingerprint.test.mjs
// AND tests/test_cms_host_parity.py) -- change the rule in one language and the other's suite
// fails, closing the drift class that let #34's Python fix ship 16 days before #416's JS one.
export function hostMatches(host, suffix) {
  return host === suffix || host.endsWith('.' + suffix);
}

// The ONE cheap inline classification: a host-suffix match against CMS_HOSTS. cms_hint is
// dispatch-load-bearing since #540 (Edlio sibling-variant dedup). Richer classification stays
// a later pure function over the raw signals.
export function cmsHint(hosts) {
  for (const host of hosts) {
    if (!host) continue;
    for (const cms of CMS_HOSTS) {
      if (hostMatches(host, cms)) return cms;
    }
  }
  return null;
}

// Crude tag-strip + length, for the js_dependent proxy only (does the served HTML carry the
// content, or is it a near-empty shell hydrated by JS?). Not used for any captured text.
export function strippedLen(html) {
  return (html || '')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim().length;
}

// DOM-level signals, gathered in one page.evaluate: the <meta generator> declaration (high
// precision when present) and the set of distinct resource hostnames (script/link/img srcs --
// vendor CDN bundles betray the platform). Ephemeral: innerText can't reconstruct these once
// the page closes, so they MUST be read at render time.
export async function domFingerprint(page) {
  return page.evaluate(() => {
    const gen = document.querySelector('meta[name="generator" i]');
    const hosts = {};
    for (const el of document.querySelectorAll('script[src],link[href],img[src]')) {
      const raw = el.getAttribute('src') || el.getAttribute('href');
      if (!raw) continue;
      try { const hn = new URL(raw, location.href).hostname.toLowerCase(); if (hn) hosts[hn] = 1; } catch { /* skip unparseable */ }
    }
    // REQ-115: iframe/embed/object src hostnames — a STRUCTURAL signal for feed/calendar widgets that
    // Stage 5's URL/keyword guessing can't see reliably. Stored categorized in the fingerprint.
    const iframeHosts = {};
    for (const el of document.querySelectorAll('iframe[src],embed[src],object[data]')) {
      const raw = el.getAttribute('src') || el.getAttribute('data');
      if (!raw) continue;
      try { const hn = new URL(raw, location.href).hostname.toLowerCase(); if (hn) iframeHosts[hn] = 1; } catch { /* skip */ }
    }
    return { meta_generator: gen ? (gen.getAttribute('content') || null) : null,
             resource_hosts: Object.keys(hosts), iframe_hosts: Object.keys(iframeHosts),
             // #518: raw signal for the login_wall fidelity flag -- stored on the fingerprint so
             // recompute-fidelity can re-derive the flag without a re-capture.
             has_password: !!document.querySelector('input[type="password"]') };
  }).catch(() => ({ meta_generator: null, resource_hosts: [], iframe_hosts: [], has_password: false }));
}

// Pure, unit-testable: categorize an embed/iframe host into the class Stage 5 routes on (REQ-115).
// Deliberately small + high-precision; unknown hosts -> 'other' (not treated as a negative signal).
export function categorizeEmbedHost(hostname) {
  const h = (hostname || '').toLowerCase();
  if (/facebook|twitter|x\.com|instagram|tiktok|youtube|linkedin|juicer|curator|elfsight|sociablekit|livewhale/.test(h)) return 'social';
  if (/calendar|(?:^|\.)cal\.|teamup|localist|trumba|helloasso|fullcalendar|google\.com\/calendar/.test(h)) return 'calendar';
  if (/docs\.google|drive\.google|scribd|issuu|flipsnack|smore|padlet|box\.com|onedrive|sharepoint|acrobat|documentcloud/.test(h)) return 'doc-viewer';
  return 'other';
}

// The distinct categories present among a page's iframe/embed hosts (deduped, ordered).
export function embedCategories(iframeHosts) {
  const cats = new Set((iframeHosts || []).map(categorizeEmbedHost));
  return [...cats].sort();
}

// DOM segmentation (REQ-091): split the rendered page into MAIN (body minus chrome) + the chrome
// segments (header/footer/nav). MUST run at render time -- innerText can't reconstruct the DOM
// structure once the page closes, exactly like the fingerprint above. `main` = body.innerText after
// removing the landmark (chrome) elements from the live DOM; the named segments are the chrome
// elements' innerText, grabbed before removal. innerText throughout = VISIBLE text, mirroring page.txt.
// Pure, unit-testable (PR #239 review): bucket the landmark selectors into the named segments the
// grabs below read. Previously header/footer/nav were HARDCODED selector strings that ignored the
// `landmarks` argument — so widening de_chrome_landmarks.json (its governance note anticipates
// adding .site-footer/#colophon/.main-nav-style heuristics) would have stripped the new chrome from
// `main` while page.header/footer/nav.txt silently missed it. Buckets by substring; a selector that
// matches no bucket is still removed from main, its text just isn't attributed to a named segment.
export function segmentBuckets(landmarks) {
  const b = { header: [], footer: [], nav: [] };
  for (const sel of landmarks || []) {
    const s = sel.toLowerCase();
    if (s.includes('footer') || s.includes('contentinfo') || s.includes('colophon')) b.footer.push(sel);
    else if (s.includes('header') || s.includes('banner') || s.includes('masthead')) b.header.push(sel);
    else if (s.includes('nav')) b.nav.push(sel);
  }
  return b;
}

export async function segmentChrome(page, landmarks) {
  const removeSel = landmarks.join(',');
  const buckets = segmentBuckets(landmarks);   // grabs + removal now share ONE source: `landmarks`
  return page.evaluate(({ removeSel, buckets }) => {
    const grab = (sel) => {
      if (!sel) return '';
      try { return Array.from(document.querySelectorAll(sel)).map((e) => e.innerText || '').join('\n').trim(); }
      catch { return ''; }
    };
    // VISIBLE text (innerText), mirroring page.txt. Grab the chrome segments FIRST, then remove the
    // chrome from the LIVE dom and read body.innerText for main. innerText needs layout, so it must
    // run on the live tree -- a detached clone's textContent pulls in hidden menus/modals/JSON-LD
    // (caught on real Marion data: 98KB of hidden cruft vs 3KB visible). Mutating the live dom is
    // safe -- the page is already captured/throwaway by now.
    const header = grab(buckets.header.join(','));
    const footer = grab(buckets.footer.join(','));
    const nav = grab(buckets.nav.join(','));
    if (removeSel) { try { document.querySelectorAll(removeSel).forEach((el) => el.remove()); } catch { /* ignore */ } }
    const main = (document.body && document.body.innerText ? document.body.innerText : '').trim();
    return { main, header, footer, nav };
  }, { removeSel, buckets }).catch(() => ({ main: '', header: '', footer: '', nav: '' }));
}

// The ONE segmentChrome invocation shape (#375): page.evaluate gets no deadline from Playwright,
// so a wedged page main thread would hang the worker forever -- segmentChrome's own .catch
// handles rejection, not a hang. Shared by the mainline capture and the backfill so the two
// sites can't drift on the timeout/label.
const segmentWithTimeout = (page) =>
  withTimeout(segmentChrome(page, DE_CHROME_LANDMARKS), OP_TIMEOUT_MS, 'segment');

// Persist the segments (only non-empty ones) as page.main/header/footer/nav.txt. Stage 5 reads
// page.main.txt when present and tiers on it; full page.txt is always kept, so this is additive.
function writeSegments(recDir, seg) {
  const files = { main: 'page.main.txt', header: 'page.header.txt', footer: 'page.footer.txt', nav: 'page.nav.txt' };
  for (const [k, fname] of Object.entries(files)) {
    if (seg && seg[k]) writeFileSync(path.join(recDir, fname), seg[k]);
  }
}

export function buildHtmlFingerprint({ finalHost, headers, dom, jsDependent }) {
  // Off-domain resource hosts are the signal; drop the page's own host, cap to keep the
  // record small even on asset-heavy pages.
  const resourceHosts = (dom.resource_hosts || []).filter((hn) => hn && hn !== finalHost).slice(0, 20);
  return {
    final_host: finalHost || null,
    server: headers['server'] || null,
    powered_by: headers['x-powered-by'] || null,
    cdn_hints: cdnHints(headers),
    meta_generator: dom.meta_generator || null,
    resource_hosts: resourceHosts,
    js_dependent: jsDependent,
    cms_hint: cmsHint([finalHost, ...resourceHosts]),
    // REQ-115: categorized iframe/embed presence — a structural feed/calendar/doc-viewer signal for Stage 5.
    iframe_hosts: (dom.iframe_hosts || []).slice(0, 20),
    embed_hosts: embedCategories(dom.iframe_hosts),
    embed_present: (dom.iframe_hosts || []).length > 0,
    has_password: !!dom.has_password,   // #518 raw signal (login_wall input; recomputable)
  };
}

// Reduced fingerprint for a direct byte fetch (PDF/image/Drive export) -- no DOM, so no
// meta_generator / resource_hosts / js_dependent. `response` is a WHATWG fetch Response.
export function buildFetchFingerprint(response) {
  const headers = Object.fromEntries(response.headers); // fetch headers are already lowercased
  const finalHost = hostOf(response.url);
  return {
    final_host: finalHost || null,
    server: headers['server'] || null,
    powered_by: headers['x-powered-by'] || null,
    cdn_hints: cdnHints(headers),
    meta_generator: null,
    resource_hosts: [],
    js_dependent: null,
    cms_hint: cmsHint([finalHost]),
  };
}

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

export async function dismissModals(page) {
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

// A URL fragment (#pageTitle, #nav_items_0, etc.) never represents different
// server-side content -- it's purely client-side same-page navigation. Found on the
// first real run: Stroudsburg's bell-schedule pages link to themselves via fragment
// anchors, and without stripping these, the same page got queued and re-captured 2-3
// times under fragment-different URLs.
export function stripFragment(url) {
  try {
    const u = new URL(url);
    u.hash = '';
    return u.toString();
  } catch {
    return url.split('#')[0];
  }
}

// Pure, unit-testable manifest bookkeeping (#18): a files{} entry is recorded ONLY when the
// underlying write actually succeeded; a failure records a short `<key>_err` note instead --
// so captures.json never claims a file that isn't on disk (Stage 4's consistency check treats
// a phantom entry as an inconsistency and quarantines the district).
export function noteFileResult(rec, key, filename, err = null) {
  if (err == null) rec.files[key] = filename;
  else rec[`${key}_err`] = String(err).slice(0, 80);
  return rec;
}

// Pure, unit-testable (#44): once a capture resolves, its FINAL url (post-redirect) joins the
// district's seen-set, so an emergent anchor pointing directly at a redirect TARGET isn't
// captured a second time under its other name. Must be called before the page's emergent scan.
export function noteFinalUrl(district, finalUrl) {
  if (finalUrl) district.seen.add(stripFragment(finalUrl));
}

// Pure, unit-testable (#174, follow-up redo): seed a district's bookkeeping from the prior
// round's captures.json so a re-run captures only the DELTA. Prior records are carried into
// the new manifest verbatim (Stage 5 ingests ONLY the current manifest -- per-district
// delete+rebuild -- so a slice-only manifest would erase the district's existing records and
// orphan their gate@5 labels at the next ingest); their urls + final_urls join the seen-set so
// an already-captured candidate is never re-hit (the one-attempt rule); the emergent counter
// resumes from the prior round's count so a redo can't double the emergent budget. The one
// exception: a prior FAILED record (ok === false, e.g. not_attempted at the deadline) whose
// url is being re-attempted this round is DROPPED, not carried -- the retry's fresh record
// replaces it instead of sitting behind it forever.
export function seedFromPriorCaptures(district, priorRecords, candidateUrls) {
  for (const rec of priorRecords || []) {
    const u = rec.url ? stripFragment(rec.url) : null;
    if (rec.ok === false && u && candidateUrls.has(u)) continue; // retried this round -> replaced
    district.records.push(rec);
    if (u) district.seen.add(u);
    if (rec.final_url) district.seen.add(stripFragment(rec.final_url));
    if (rec.source === 'emergent') district.emergent += 1;
  }
}

// The emergent scan's DOM read: every anchor's visible text + resolved href. Exported so the
// browser harness exercises THIS code (not a hand-copied evaluate) -- a future edit to the selector
// or mapped fields is then caught by the test (PR #239 review).
export async function readAnchors(page) {
  return page
    .evaluate(() => Array.from(document.querySelectorAll('a[href]')).map((a) => ({ text: a.innerText || '', href: a.href })))
    .catch(() => []);
}

// Pure, unit-testable (#127/REQ-079): the emergent-scan DECISION -- from a page's anchors
// ({text, href}), the fragment-stripped hrefs whose text or href hits a schedule keyword. The
// browser-driving part (reading the anchors off the DOM) is readAnchors above.
export function findEmergentLinks(anchors) {
  const out = [];
  for (const a of anchors) {
    const hay = `${a.text} ${a.href}`.toLowerCase();
    if (SCHED_KW.some((k) => hay.includes(k))) out.push(stripFragment(a.href));
  }
  return out;
}

// Pure, unit-testable (#127/REQ-079): the emergent one-hop SELECTION -- take the schedule-matching
// links not already seen, up to the per-district cap, mutating `seen` and returning the new targets
// plus the advanced counter. captureInto calls THIS, so the tested logic is the production logic.
export function selectEmergentTargets(links, seen, emergent, cap) {
  const targets = [];
  for (const eu of links) {
    if (emergent >= cap) break;
    if (seen.has(eu)) continue;
    seen.add(eu);
    emergent += 1;
    targets.push(eu);
  }
  return { targets, emergent };
}

// The shared subtype-to-extension rule: "text after the slash, minus any ;charset param". ONE
// definition for both dispatch cores below, so a future parsing fix (e.g. +xml suffixes) can't
// silently diverge the direct-fetch and Drive-export paths (PR #239 review).
const subtypeExt = (ct, fallback) => (ct.split('/')[1] || fallback).split(';')[0];

// Pure, unit-testable (#127/REQ-079): the fetch-branch DISPATCH -- given a Content-Type, decide
// whether the bytes are a directly-savable binary (PDF/image, no browser render) or need the HTML
// render path, and the extension to save under. Mirrors captureInto's routing via this call.
// `contentType` may be null (Headers.get() returns null when absent) -- normalized, never thrown on.
export function classifyFetchKind(contentType) {
  const ct = (contentType || '').toLowerCase();
  if (ct.includes('pdf')) return { binary: true, kind: 'pdf', ext: 'pdf' };
  if (ct.includes('image')) return { binary: true, kind: 'image', ext: subtypeExt(ct, 'img') };
  return { binary: false, kind: 'html', ext: null };
}

// Pure, unit-testable (#127/REQ-079): a Google Drive export fetch returns HTML when the requested
// format isn't available (interstitial/error) -- that format is skipped, never saved. Otherwise the
// extension: 'auto' sniffs pdf vs the content subtype; a named format is its own extension.
// `contentType` may be null, same normalization as classifyFetchKind.
export function driveFormatOutcome(contentType, format) {
  const ct = (contentType || '').toLowerCase();
  if (ct.includes('html')) return { skip: true, ext: null };
  const ext = format === 'auto' ? (ct.includes('pdf') ? 'pdf' : subtypeExt(ct, 'bin')) : format;
  return { skip: false, ext };
}

// Re-visit a single HTML URL and return ONLY its fingerprint (no file writes). Shared by the
// backfill path; the live path inlines the equivalent gather alongside its file writes.
async function htmlFingerprintFor(ctx, url) {
  const page = await ctx.newPage();
  setupPageDialogHandler(page);
  try {
    const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => null);
    const rawHtml = response ? await response.text().catch(() => '') : '';
    await page.waitForTimeout(2500);
    await dismissModals(page);
    let rendered = '';
    for (const fr of page.frames()) {
      try { rendered += `\n${(await fr.evaluate(() => (document.body ? document.body.innerText : ''))) || ''}`; } catch { /* cross-origin frame */ }
    }
    const dom = await domFingerprint(page);
    const jsDependent = strippedLen(rawHtml) < 200 && rendered.trim().length >= SUBSTANTIAL_TEXT_CHARS;
    return buildHtmlFingerprint({ finalHost: hostOf(page.url()), headers: response ? response.headers() : {}, dom, jsDependent });
  } finally {
    await page.close();
  }
}

// ============================ NORMAL CAPTURE ============================
async function runCapture(ROOT, CONC, only = null, deadlineMs = 0) {
  // `only` (a Set of district-dir basenames) scopes the run to specific districts -- the console's
  // batch-scoped, per-district runner uses it so a capture run touches only the batch in flight, never
  // re-captures every district already under ROOT. null = capture every dir with a candidates.json.
  // `deadlineMs` (>0) = NODE-OWNS-SHUTDOWN: once it passes, workers stop pulling NEW tasks, in-flight
  // pages finish (each bounded by the per-op timeouts), the un-started candidates are recorded
  // `not_attempted`, and captures.json is written REGARDLESS -- so a slow/stalled district yields a
  // PARTIAL manifest (captured_partial) instead of being SIGKILLed with its work orphaned. The Python
  // runner sets deadlineMs below its own subprocess backstop, so Node shuts itself down cleanly first.
  const deadline = deadlineMs > 0 ? Date.now() + deadlineMs : Infinity;
  let dirs = readdirSync(ROOT).filter((d) => existsSync(path.join(ROOT, d, 'candidates.json')));
  if (only) dirs = dirs.filter((d) => only.has(d));
  const byDistrict = {};
  const tasks = [];
  for (const did of dirs) {
    const meta = JSON.parse(readFileSync(path.join(ROOT, did, 'candidates.json')));
    const capDir = path.join(ROOT, did, 'captures');
    mkdirSync(capDir, { recursive: true });
    byDistrict[did] = { capDir, records: [], seen: new Set(), emergent: 0 };
    // #174 (follow-up redo): a prior round's captures.json seeds records + seen so this run
    // captures only the delta and the written manifest stays the district's complete union.
    // First runs are untouched (no manifest exists until end-of-run). An unreadable prior
    // manifest degrades to a fresh full capture -- writeVersioned still preserves the file.
    const priorPath = path.join(ROOT, did, 'captures.json');
    if (existsSync(priorPath)) {
      const candidateUrls = new Set(meta.candidates.map((c) => stripFragment(c.url)));
      try {
        seedFromPriorCaptures(byDistrict[did], JSON.parse(readFileSync(priorPath)), candidateUrls);
      } catch (e) {
        console.error(`  ${did}: unreadable prior captures.json (${e}) -- capturing fresh`);
      }
    }
    for (const c of meta.candidates) {
      const u = stripFragment(c.url);
      if (byDistrict[did].seen.has(u)) continue;   // already captured in a prior round (#174)
      byDistrict[did].seen.add(u);
      tasks.push({ did, url: u, tools: c.tools, source: 'discovered', found_on: null, capDir });
    }
  }

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: 'Mozilla/5.0 (research; bell-schedule discovery)' });

  // The capture work for one task. Early `return`s are fine -- the caller (processTask) owns
  // the record push and the catch-all, so a throw ANYWHERE in here (including fs errors)
  // becomes a per-record err, never a rejected worker.
  async function captureInto(t, rec, recDir) {
    const { did, url, source, capDir } = t;
    {   // (kept block: preserves the original body's indentation for a reviewable diff)
      // --- Google Drive / Docs / Sheets / Slides: Tier 1 only (Tier 2 OAuth not wired yet) ---
      if (isGoogleUrl(url)) {
        const drive = driveExportCandidates(url);
        if (drive) {
          let any = false;
          for (const { format, fetchUrl } of drive) {
            try {
              const r = await fetch(fetchUrl, { redirect: 'follow', signal: AbortSignal.timeout(20000) });
              const ct = (r.headers.get('content-type') || '').toLowerCase();
              const outcome = driveFormatOutcome(ct, format);
              if (outcome.skip) continue; // interstitial/error page -- this format failed, try the next
              const ext = outcome.ext;
              const buf = Buffer.from(await r.arrayBuffer());
              const filename = format === 'auto' ? `file.${ext}` : `${format}.${ext}`;
              writeFileSync(path.join(recDir, filename), buf);
              rec.files[format === 'auto' ? 'bin' : format] = filename;
              if (!rec.fingerprint) rec.fingerprint = buildFetchFingerprint(r);
              any = true;
            } catch { /* this format failed, try the next */ }
          }
          if (any) {
            rec.kind = 'drive_export';
            rec.ok = true;
            return;
          }
        }
        // Tier 1 didn't pan out (folder URL, unrecognized pattern, or every format failed).
        // Per the Stage 3 design: a per-item flag, NOT a run-halting control failure -- one
        // stuck Drive item says nothing about the rest of the batch. Tier 2 (OAuth Drive
        // API) is not implemented in this script yet; until it is, this is the real outcome,
        // not a placeholder.
        rec.err = 'needs_oauth_reauth';
        return;
      }

      let ct = '';
      try {
        const r = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(20000) });
        ct = (r.headers.get('content-type') || '').toLowerCase();
        rec.final_url = r.url;
        noteFinalUrl(byDistrict[did], rec.final_url);
        const cls = classifyFetchKind(ct);
        if (cls.binary) {
          // #415 (folded into #518): never write a non-2xx body as original.* -- a 404/403 served
          // with a PDF/image content-type would land HTML error bytes in a file Stage 4's pdftotext
          // then chokes on. And never fall through to the render path either: page.goto on a true
          // binary URL aborts as a download and would produce a BLANK ok:true html record --
          // worse than a visible failure. A non-2xx binary is a per-record err (queryable via
          // capture.err, same as needs_oauth_reauth), picked up by retry paths, never silent.
          if (r.ok) {
            writeFileSync(path.join(recDir, `original.${cls.ext}`), Buffer.from(await r.arrayBuffer()));
            rec.kind = cls.kind;
            rec.files.bin = `original.${cls.ext}`;
            rec.fingerprint = buildFetchFingerprint(r);
            rec.ok = true;
          } else {
            rec.err = `binary_fetch_${r.status}`;
            rec.fetch_status = r.status;
            return;
          }
        }
      } catch { /* fall through to render */ }

      if (!rec.ok) {
        const page = await ctx.newPage();
        setupPageDialogHandler(page);
        try {
          const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => null);
          const rawHtml = response ? await response.text().catch(() => '') : '';
          await page.waitForTimeout(2500);
          rec.final_url = page.url();
          noteFinalUrl(byDistrict[did], rec.final_url);

          // Modal dismissal sequenced AFTER the 2.5s wait, giving slow/deliberately-delayed
          // cookie-consent banners a window to actually render before dismissal is attempted.
          const modalsDismissed = await dismissModals(page);
          rec.modals_dismissed = modalsDismissed;
          if (modalsDismissed) await page.waitForTimeout(500);

          let text = '';
          for (const fr of page.frames()) {
            try { text += `\n${(await fr.evaluate(() => (document.body ? document.body.innerText : ''))) || ''}`; } catch { /* cross-origin frame */ }
          }
          writeFileSync(path.join(recDir, 'page.txt'), text);
          rec.files.txt = 'page.txt'; // only after the write succeeded (a throw lands in processTask's catch)
          // #18: files.png only on a SUCCESSFUL screenshot -- mirroring the pdf pattern below.
          // The old unconditional `rec.files.png = 'page.png'` after a swallowed .catch()
          // manifested phantom entries that Stage 4's consistency check then tripped on.
          await withTimeout(
            page.screenshot({ path: path.join(recDir, 'page.png'), fullPage: true }),
            OP_TIMEOUT_MS, 'screenshot',
          )
            .then(() => noteFileResult(rec, 'png', 'page.png'))
            .catch((e) => noteFileResult(rec, 'png', 'page.png', e));
          // Unconditional -- no multi-column-detection trigger. Local compute is free; the
          // decision of which representation to actually use moves downstream to Stage 4/7.
          await withTimeout(
            page.pdf({
              path: path.join(recDir, 'page.pdf'),
              format: 'Letter',
              scale: 0.9,
              margin: { top: '0.5in', bottom: '0.5in', left: '0.5in', right: '0.5in' },
              printBackground: true,
            }),
            OP_TIMEOUT_MS, 'pdf',
          )
            .then(() => noteFileResult(rec, 'pdf', 'page.pdf'))
            .catch((e) => noteFileResult(rec, 'pdf', 'page.pdf', e));

          rec.kind = 'html';
          rec.text_times = (text.match(TIME) || []).length;

          // Hosting/CMS fingerprint -- gathered from the goto Response (headers we used to
          // discard) + a single DOM evaluate + a JS-dependency proxy (served-HTML text near
          // empty but rendered text substantial -> content came from JS). #518's has_password
          // raw signal rides the SAME evaluate -- no second DOM round-trip.
          const dom = await domFingerprint(page);
          rec.fingerprint = buildHtmlFingerprint({
            finalHost: hostOf(rec.final_url),
            headers: response ? response.headers() : {},
            dom,
            jsDependent: strippedLen(rawHtml) < 200 && text.trim().length >= SUBSTANTIAL_TEXT_CHARS,
          });
          // Capture-fidelity flags (#518): login wall / soft-404 classification over persisted
          // facts (url/final_url, page text, fingerprint.has_password). Flag, never drop -- the
          // record still processes; downstream sees "suspect". Re-derivable via recompute-fidelity.
          const flags = fidelityFlags({
            url, finalUrl: rec.final_url, text, hasPassword: dom.has_password,
          });
          if (flags.length) rec.fidelity = flags;
          // DOM segmentation (REQ-091): de-chrome the page for Stage 5 signals (additive; page.txt kept).
          try { writeSegments(recDir, await segmentWithTimeout(page)); rec.segmented = true; }
          catch { rec.segmented = false; }
          rec.ok = true;

          // --- Emergent candidates: exactly one hop, never recursive. An emergent
          // candidate's own page is never scanned for further emergent candidates. ---
          if (source === 'discovered') {
            const anchors = await readAnchors(page);
            const { targets, emergent } = selectEmergentTargets(
              findEmergentLinks(anchors), byDistrict[did].seen, byDistrict[did].emergent, EMERGENT_CAP);
            byDistrict[did].emergent = emergent;
            for (const eu of targets) {
              tasks.push({ did, url: eu, tools: [], source: 'emergent', found_on: rec.final_url, capDir });
            }
          }
        } finally {
          await page.close();
        }
      }
    }
  }

  // #35: the ENTIRE task -- preamble (hash, mkdir), capture body, AND the record push -- runs
  // inside this try/catch/finally, so a throw anywhere becomes a per-record err entry instead
  // of rejecting a worker (which used to reject Promise.all and leave EVERY district of the
  // run without a captures.json).
  async function processTask(t) {
    const rec = { url: t.url, tools: t.tools || [], source: t.source, found_on: t.found_on,
      hash: null, ok: false, files: {} };
    try {
      // One subdirectory per captured URL (named by its hash) -- not flat hash-prefixed files
      // sharing the district's captures/ folder. The whole point of hashing the URL was so a
      // human reviewing CP-B output can open one folder and see everything for that one page,
      // not have to mentally regroup files by matching prefixes.
      const h = createHash('md5').update(t.url).digest('hex').slice(0, 10);
      rec.hash = h;
      const recDir = path.join(t.capDir, h);
      mkdirSync(recDir, { recursive: true });
      await captureInto(t, rec, recDir);
    } catch (e) {
      if (!rec.err) rec.err = String(e).slice(0, 120);
    } finally {
      byDistrict[t.did].records.push(rec);
    }
    return rec;
  }

  let idx = 0;
  let done = 0;
  async function worker() {
    // Deadline is checked BETWEEN tasks (an in-flight page always finishes — bounded by the per-op
    // timeouts). On break, tasks[idx..] are un-started -> recorded not_attempted below.
    while (idx < tasks.length) {
      if (Date.now() > deadline) break;
      const t = tasks[idx++];
      await processTask(t);
      if (++done % 25 === 0) console.log(`  ...${done}/${tasks.length} captured`);
    }
  }
  console.log(`capturing ${tasks.length} candidate URLs across ${dirs.length} districts (concurrency ${CONC})`);
  // #35: allSettled + a finally around the manifest writes -- node owns its shutdown, so the
  // per-district manifests are ALWAYS written even if a worker somehow rejects (processTask
  // already converts task throws into per-record err entries, so this is the second belt).
  let notAttemptedCount = 0;
  try {
    const settled = await Promise.allSettled(Array.from({ length: CONC }, () => worker()));
    for (const s of settled) {
      if (s.status === 'rejected') console.error(`worker crashed (its in-flight task may be missing from the manifest): ${s.reason}`);
    }
  } finally {
    // Un-started tasks (deadline reached / worker crash) -> a not_attempted record each, so the
    // manifest lists EVERY candidate (completeness) and the district resolves captured_partial
    // rather than vanishing.
    const notAttempted = tasks.slice(idx);
    notAttemptedCount = notAttempted.length;
    for (const t of notAttempted) {
      const h = createHash('md5').update(t.url).digest('hex').slice(0, 10);
      byDistrict[t.did].records.push({ url: t.url, tools: t.tools || [], source: t.source,
        found_on: t.found_on, hash: h, ok: false, files: {}, err: 'not_attempted (capture deadline reached)' });
    }

    for (const did of Object.keys(byDistrict)) {
      try {
        writeVersioned(path.join(ROOT, did, 'captures.json'), JSON.stringify(byDistrict[did].records, null, 2));
      } catch (e) {
        console.error(`manifest write FAILED for ${did}: ${e}`); // keep writing the other districts'
      }
    }
    await browser.close().catch(() => {});
  }
  const tag = notAttemptedCount ? ` — ${notAttemptedCount} not attempted (deadline)` : '';
  console.log(`CAPTURE DONE — ${done} URLs captured, ${dirs.length} districts${tag}`);
}

// ============================ FINGERPRINT BACKFILL ============================
// Re-visit each existing ok:true record, compute ONLY its fingerprint, and patch it into the
// record. Does not re-render/re-save page.* or touch any Stage 4 output -- additive, leaving
// processed.json valid (Stage 4 never reads fingerprints). For parity on captures that
// predate fingerprinting. Records that already carry a fingerprint, and ok:false records
// (no content was captured), are skipped.
async function runBackfill(ROOT, CONC) {
  const dirs = readdirSync(ROOT).filter((d) => existsSync(path.join(ROOT, d, 'captures.json')));
  const tasks = [];
  const byDistrict = {};
  for (const did of dirs) {
    const records = JSON.parse(readFileSync(path.join(ROOT, did, 'captures.json')));
    byDistrict[did] = { records, dirty: false };
    records.forEach((rec, i) => {
      if (!rec.ok || rec.fingerprint) return;
      const target = rec.final_url || rec.url;
      if (!target) return;
      tasks.push({ did, i, rec, target });
    });
  }

  const total = tasks.length;
  if (total === 0) {
    console.log('BACKFILL: nothing to do (every ok record already has a fingerprint).');
    return;
  }

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: 'Mozilla/5.0 (research; bell-schedule discovery)' });

  let idx = 0;
  let done = 0;
  async function worker() {
    while (idx < tasks.length) {
      const t = tasks[idx++];
      try {
        if (t.rec.kind === 'html') {
          t.rec.fingerprint = await htmlFingerprintFor(ctx, t.target);
        } else {
          // pdf / image / drive_export -- reduced fingerprint from a direct byte fetch.
          const r = await fetch(t.target, { redirect: 'follow', signal: AbortSignal.timeout(20000) });
          t.rec.fingerprint = buildFetchFingerprint(r);
        }
        byDistrict[t.did].dirty = true;
      } catch (e) {
        t.rec.fingerprint = { error: String(e).slice(0, 120) };
        byDistrict[t.did].dirty = true;
      }
      if (++done % 25 === 0) console.log(`  ...${done}/${total} fingerprinted`);
    }
  }
  console.log(`backfilling fingerprints for ${total} records across ${dirs.length} districts (concurrency ${CONC})`);
  await Promise.all(Array.from({ length: CONC }, () => worker()));

  for (const did of Object.keys(byDistrict)) {
    if (byDistrict[did].dirty) {
      writeVersioned(path.join(ROOT, did, 'captures.json'), JSON.stringify(byDistrict[did].records, null, 2));
    }
  }
  await browser.close();
  console.log(`BACKFILL DONE — ${done}/${total} records fingerprinted across ${dirs.length} districts`);
}

// ============================ RECOMPUTE cms_hint ============================
// Re-derive ONLY cms_hint, in place, from each record's already-stored fingerprint
// (final_host + resource_hosts) -- a pure recompute over facts already on disk, NO browser,
// NO network. This is the mechanism for applying a (human-approved) CMS_HOSTS change to
// already-captured data without re-capturing: the raw signals never changed, only the
// classification function over them. Writes via versioned-redo only for districts that
// actually changed.
function runRecomputeCmsHint(ROOT) {
  const dirs = readdirSync(ROOT).filter((d) => existsSync(path.join(ROOT, d, 'captures.json')));
  let changed = 0;
  let scanned = 0;
  for (const did of dirs) {
    const capPath = path.join(ROOT, did, 'captures.json');
    const records = JSON.parse(readFileSync(capPath));
    let dirty = false;
    for (const rec of records) {
      const fp = rec.fingerprint;
      if (!fp || fp.error) continue;
      scanned += 1;
      const next = cmsHint([fp.final_host, ...(fp.resource_hosts || [])]);
      if (next !== (fp.cms_hint ?? null)) { fp.cms_hint = next; dirty = true; changed += 1; }
    }
    if (dirty) writeVersioned(capPath, JSON.stringify(records, null, 2));
  }
  console.log(`RECOMPUTE cms_hint DONE — ${changed} of ${scanned} fingerprinted records updated across ${dirs.length} districts`);
}

// ============================ RECOMPUTE fidelity (#518) ============================
// Re-derive ONLY the fidelity flags, in place, from facts already on disk (url/final_url,
// the head of page.txt, fingerprint.has_password) -- a pure recompute, NO browser, NO network,
// mirroring recompute-cms-hint: a LOGIN_URL_RE/SOFT404_RE tuning applies to already-captured
// data without a re-capture. Only ok html records carry the inputs; others are skipped.
function runRecomputeFidelity(ROOT) {
  const dirs = readdirSync(ROOT).filter((d) => existsSync(path.join(ROOT, d, 'captures.json')));
  let changed = 0;
  let scanned = 0;
  for (const did of dirs) {
    const capPath = path.join(ROOT, did, 'captures.json');
    const records = JSON.parse(readFileSync(capPath));
    let dirty = false;
    for (const rec of records) {
      if (!rec.ok || rec.kind !== 'html' || !rec.hash) continue;
      scanned += 1;
      const txtPath = path.join(ROOT, did, 'captures', rec.hash, rec.files?.txt || 'page.txt');
      let text = '';
      try { text = readFileSync(txtPath, 'utf8').slice(0, 3000); } catch { /* no page.txt -> URL/password signals only */ }
      const next = fidelityFlags({
        url: rec.url, finalUrl: rec.final_url, text,
        hasPassword: !!(rec.fingerprint && rec.fingerprint.has_password),
      });
      const prev = rec.fidelity || [];
      if (JSON.stringify(next) !== JSON.stringify(prev)) {
        if (next.length) rec.fidelity = next; else delete rec.fidelity;
        dirty = true; changed += 1;
      }
    }
    if (dirty) writeVersioned(capPath, JSON.stringify(records, null, 2));
  }
  console.log(`RECOMPUTE fidelity DONE — ${changed} of ${scanned} ok html records updated across ${dirs.length} districts`);
}

// ============================ SEGMENT BACKFILL (de-chrome, REQ-091) ============================
// Re-visit each existing ok HTML record, run DOM segmentation, and write page.main/header/footer/
// nav.txt into the record's capture dir. ADDITIVE: never touches page.txt/png/pdf or any Stage 4
// output -- Stage 5 reads page.main.txt when present (tiers on it), else falls back to the full
// page. The mechanism for applying de-chrome to already-captured data without a full re-capture,
// mirroring backfill-fingerprints. Only HTML records carry a DOM to segment.
async function runBackfillSegments(ROOT, CONC) {
  const dirs = readdirSync(ROOT).filter((d) => existsSync(path.join(ROOT, d, 'captures.json')));
  const tasks = [];
  const byDistrict = {};
  for (const did of dirs) {
    const records = JSON.parse(readFileSync(path.join(ROOT, did, 'captures.json')));
    byDistrict[did] = { records, dirty: false };
    records.forEach((rec) => {
      if (!rec.ok || rec.kind !== 'html') return;
      const target = rec.final_url || rec.url;
      if (!target || !rec.hash) return;
      tasks.push({ did, rec, target, recDir: path.join(ROOT, did, 'captures', rec.hash) });
    });
  }
  const total = tasks.length;
  if (total === 0) { console.log('SEGMENT BACKFILL: nothing to do (no ok html records).'); return; }

  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, userAgent: 'Mozilla/5.0 (research; bell-schedule discovery)' });
  let idx = 0;
  let done = 0;
  async function worker() {
    while (idx < tasks.length) {
      const t = tasks[idx++];
      const page = await ctx.newPage();
      try {
        // Match runCapture: networkidle often never settles on JS-heavy school CMSs, so CATCH the
        // timeout and segment whatever rendered (the DOM is present) rather than aborting.
        await page.goto(t.target, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => null);
        await page.waitForTimeout(2500);
        // #375: a hung evaluate here stalled the worker AND lost the whole run's manifest
        // writes (they only happen after Promise.all resolves).
        writeSegments(t.recDir, await segmentWithTimeout(page));
        t.rec.segmented = true;
      } catch (e) {
        t.rec.segment_err = String(e).slice(0, 120);
      } finally {
        await page.close().catch(() => {});
        byDistrict[t.did].dirty = true;
      }
      if (++done % 25 === 0) console.log(`  ...${done}/${total} segmented`);
    }
  }
  console.log(`segmenting ${total} html records across ${dirs.length} districts (concurrency ${CONC})`);
  await Promise.all(Array.from({ length: CONC }, () => worker()));
  for (const did of Object.keys(byDistrict)) {
    if (byDistrict[did].dirty) writeVersioned(path.join(ROOT, did, 'captures.json'), JSON.stringify(byDistrict[did].records, null, 2));
  }
  await browser.close();
  console.log(`SEGMENT BACKFILL DONE — ${done}/${total} html records segmented across ${dirs.length} districts`);
}

// ============================ DISPATCH ============================
// Only run when executed directly (node capture_discovery.mjs ...), never when imported by a
// test that just wants the pure helpers -- otherwise the import would kick off a capture run.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const argv = process.argv.slice(2);
  if (argv[0] === 'backfill-fingerprints') {
    await runBackfill(argv[1], parseInt(argv[2] || '5', 10));
  } else if (argv[0] === 'backfill-segments') {
    await runBackfillSegments(argv[1], parseInt(argv[2] || '5', 10));
  } else if (argv[0] === 'recompute-cms-hint') {
    runRecomputeCmsHint(argv[1]);
  } else if (argv[0] === 'recompute-fidelity') {
    runRecomputeFidelity(argv[1]);
  } else if (argv[0] === 'district') {
    // Capture ONE district dir under ROOT (the console's per-district runner):
    //   node capture_discovery.mjs district <ROOT> <DISTRICT_DIR> [CONC] [DEADLINE_S]
    // DEADLINE_S>0 enables node-owns-shutdown (partial manifest on deadline) — the console passes it.
    await runCapture(argv[1], parseInt(argv[3] || '5', 10), new Set([argv[2]]),
      parseInt(argv[4] || '0', 10) * 1000);
  } else {
    await runCapture(argv[0], parseInt(argv[1] || '5', 10));
  }
}
