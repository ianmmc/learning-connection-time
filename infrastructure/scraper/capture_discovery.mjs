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
//   node capture_discovery.mjs district <ROOT> <DISTRICT_DIR> [CONC] [DEADLINE_S] [retryable-only] [plan-sha256=<hex>]
//       -- capture ONE district dir (the console's batch-scoped, per-district runner -- never
//       re-captures the rest of ROOT). DEADLINE_S>0 = node-owns-shutdown: write a partial manifest on
//       the deadline, never orphan. `retryable-only` (#116 partial retry): seed from the prior manifest
//       but re-attempt ONLY retryable failures (not_attempted/not_recovered) -- a security_block or
//       oauth failure carries verbatim (the one-attempt rule).
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
import { readFileSync, writeFileSync, appendFileSync, mkdirSync, readdirSync, existsSync, renameSync, unlinkSync } from 'fs';
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

// #225: goto wait strategy. `networkidle` burned its FULL 30s timeout on most school-CMS pages
// (live feeds / trackers never go idle: 17/20 Jefferson AL and 15/15 Gallup NM sample URLs timed
// out), truncating big districts at the per-district deadline (Jefferson captured 85/112).
// `domcontentloaded` + the existing 2.5s settle measured ZERO content loss across 47 URLs on 3
// districts / multiple CMS vendors (identical innerText clock-time counts row-for-row) at a
// 2.4-8.7x mean speedup — the late-hydrated-content risk is absorbed by the settle window plus
// the Tier 2.5/3 visual backstop. Measurements: issue #225 (2026-07-19 spike).
const GOTO_WAIT = { waitUntil: 'domcontentloaded', timeout: 15000 };

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

// --- Security-block detection (#578 -- CLAUDE.md Critical Rule 3, the one-attempt WAF rule) ---
// A WAF/bot-mitigation CHALLENGE is not content: recording the interstitial as `ok` poisons the
// data AND means the run keeps hammering a host that has already said no (the Millard batch_00021
// incident: 31/83 captures were 266-byte Cloudflare interstitials recorded ok). Detection is
// deliberately two-signal: the `cf-mitigated: challenge` response header (Cloudflare's canonical
// marker) plus a small explicit body-marker list -- presence of a CDN (cdnHints 'cloudflare') is
// NOT a block and must never trip this.
//
// #575 review (altitude): this list is Cloudflare-heavy because Cloudflare is the ONLY vendor
// we've hit live (Millard NE, twice) — the project already lived through the failure mode this
// list exists to prevent. A district behind a different WAF that emits none of these markers is
// STILL invisible to the one-attempt rule; this is a documented, bounded gap (a finite marker
// list can never claim exhaustive WAF coverage), not a silent one. The entries below for other
// major vendors are their well-documented, stable challenge/block-page strings — added
// preemptively, unverified against a live incident, so the FIRST time one of them is hit it's
// already caught rather than requiring its own #574-style live remediation first.
export const CHALLENGE_MARKERS = [
  'performing security verification',
  'checking your browser before accessing',
  'just a moment...',
  'challenge-platform',                       // the cf challenge script path
  'verify you are human',
  'attention required! | cloudflare',
  'ddos protection by',
  'incapsula incident id',                    // Imperva/Incapsula
  'access to this page has been denied because we believe you are using automation tools',   // PerimeterX/HUMAN
  'sucuri website firewall',                  // Sucuri
  'the request could not be satisfied',       // AWS CloudFront/WAF generic block
];

// Pure, unit-testable: headers (plain lowercase-keyed object) + rendered/served body text ->
// the matched challenge signal, or null. Body scan is bounded to the head of the text --
// interstitials are tiny; a real page quoting these phrases deep in an article must not trip.
export function detectChallenge(headers, bodyText) {
  const h = headers || {};
  if (String(h['cf-mitigated'] || '').toLowerCase().includes('challenge')) return 'cf-mitigated header';
  const t = String(bodyText || '').slice(0, 4000).toLowerCase();
  if (!t) return null;
  for (const m of CHALLENGE_MARKERS) if (t.includes(m)) return `body marker "${m}"`;
  return null;
}

// The district circuit breaker's threshold: this many challenges UNBROKEN BY A SUCCESSFUL CAPTURE
// halts the district's remaining captures (the un-attempted URLs record a non-retryable
// security_block variant -- deliberately NOT not_attempted, which the #116 retry would re-hammer).
// Interleaved 404s/timeouts do NOT reset the streak (#635): a WAF'd district's dead links 404
// between challenges, and only a real successful capture is evidence the wall is down.
export const SECURITY_BREAKER_N = 3;

// Fold one finished record into the district's breaker state ({secConsec, secHalted}); pure over
// the small state object so the rule is unit-testable apart from the capture loop.
export function updateSecurityState(state, rec) {
  if (rec.err && String(rec.err).startsWith('security_block')) {
    state.secConsec = (state.secConsec || 0) + 1;
    if (state.secConsec >= SECURITY_BREAKER_N) state.secHalted = true;
  } else if (rec.ok) {
    // #635 considered-and-kept: ONLY a successful capture resets the streak. A 404/timeout
    // neither counts nor resets (pinned by capture_security.test.mjs) — a WAF'd district's dead
    // links 404 between challenges, and resetting on those would keep hammering a protected
    // district (the ONE-attempt rule, Critical Rule #3). The spend/safety asymmetry favors
    // tripping early: a false trip costs recall on a few URLs; a missed trip risks an IP ban.
    state.secConsec = 0;
  }
  return state;
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
             resource_hosts: Object.keys(hosts), iframe_hosts: Object.keys(iframeHosts) };
  }).catch(() => ({ meta_generator: null, resource_hosts: [], iframe_hosts: [] }));
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
    // #863: `full` is body.innerText read in THIS SAME evaluate, one statement before the chrome
    // removal -- so `main` is a subset of `full` BY CONSTRUCTION, not by an assumption about when
    // the two reads happened. It is what captureInto persists as page.txt (main-frame half). The
    // defect it closes: page.txt used to be read at domcontentloaded+2.5s and the segments at
    // end-of-capture, so on a lazily-rendering page (Finalsite tab/accordion widgets) `main` could
    // be a strict SUPERSET of the file it is nominally a subset of -- measured on 104 records, 17
    // of them with 0 clock times in page.txt and >0 in main. NOT a DOM mutation before the read
    // (#685's constraint): only an extra read of the tree we were already standing in.
    const full = (document.body && document.body.innerText ? document.body.innerText : '').trim();
    if (removeSel) { try { document.querySelectorAll(removeSel).forEach((el) => el.remove()); } catch { /* ignore */ } }
    const main = (document.body && document.body.innerText ? document.body.innerText : '').trim();
    return { full, main, header, footer, nav };
    // #874: the catch returns NULL, not an all-empty object. A page whose body is legitimately
    // empty at the late instant and an evaluate that REJECTED (destroyed execution context after
    // the screenshot/pdf, SPA route remount) are different facts, and the old all-empty object
    // made them indistinguishable — so the caller's truthiness test on `full` discarded a
    // successful late read, silently reverting page.txt to the early one and reproducing #863 on
    // exactly the pages most likely to trigger it. `null` = the read did not happen;
    // `{full: '', ...}` = the read happened and the page really was empty.
  }, { removeSel, buckets }).catch(() => null);
}

// WHICH read ends up in page.txt, decided in ONE pure place (#874/#875). Inline branching here
// was where both review findings landed, so the decision is a function with a name and a test
// rather than three conditions spread through captureInto.
//
//   seg === null            the late read did NOT happen (evaluate rejected / timed out) -> early
//   late text is non-empty  the normal post-#863 path                                    -> final
//   late text empty, early  the page went blank under us (navigation, SPA remount): keep the
//     had content           content we have. Overwriting real text with nothing is a loss,
//                           not a fix.                                                   -> early
//   both empty              nothing to preserve; the late read is still the truthful one -> final
//
// `lateRead` records WHY we fell back, because "no error recorded anywhere" was the substance of
// #874. It is absent on the normal path.
export function resolvePersistedText({ seg, lateOtherText = '', earlyText = '' }) {
  if (!seg) return { text: earlyText, phase: 'early', lateRead: 'failed' };
  const lateText = `\n${seg.full || ''}${lateOtherText}`;
  if (lateText.trim() || !earlyText.trim()) return { text: lateText, phase: 'final' };
  return { text: earlyText, phase: 'early', lateRead: 'empty' };
}

// The ONE frame-scoped visible-text read (#518 scoped `text` and `hasPassword` together so a
// login widget in a same-origin iframe can't hide from the fidelity flags; #863 needs the SAME
// read shape a second time, late). Exported and shared rather than re-spelled at the second call
// site -- the repo's implemented-twice-drifts class is what a hand-copied frame loop becomes.
// `skipMainFrame` exists because the late read takes the main frame from segmentChrome's `full`
// instead (same evaluate as `main`, hence the by-construction subset relation).
export async function readFrameText(page, { skipMainFrame = false } = {}) {
  let text = '';
  let hasPassword = false;
  const mainFrame = page.mainFrame ? page.mainFrame() : null;
  for (const fr of page.frames()) {
    if (skipMainFrame && mainFrame && fr === mainFrame) continue;
    try {
      const r = await fr.evaluate(() => ({
        text: document.body ? document.body.innerText : '',
        hasPassword: !!document.querySelector('input[type="password"]'),
      }));
      text += `\n${r.text || ''}`;
      hasPassword = hasPassword || r.hasPassword;
    } catch { /* cross-origin frame */ }
  }
  return { text, hasPassword };
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

export function buildHtmlFingerprint({ finalHost, headers, dom, jsDependent, hasPassword }) {
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
    has_password: !!hasPassword,   // #518 raw signal (login_wall input; recomputable); frame-scoped
                                    // identically to `text` -- see the captureInto call site
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
// #116: the err classes a partial retry may re-attempt. Deliberately narrow -- crash/deadline
// remnants only, where nothing about the target site was ever actually asked. NOT retryable:
// security_block (the one-attempt WAF rule -- CLAUDE.md Critical Rule 3), needs_oauth_reauth
// (fails identically until Drive Tier 2 exists -- #115), binary_fetch_* (the origin already
// answered; a retry gets the same status). Python mirror: headless.RETRYABLE_ERR_PREFIXES.
export function isRetryableErr(err) {
  return typeof err === 'string' && (err.startsWith('not_attempted') || err.startsWith('not_recovered'));
}

export function seedFromPriorCaptures(district, priorRecords, candidateUrls, retryableOnly = false) {
  for (const rec of priorRecords || []) {
    const u = rec.url ? stripFragment(rec.url) : null;
    // A failed prior record whose URL is planned again this round is dropped (the fresh record
    // replaces it). In retryable-only mode (#116 partial retry, same candidates as the prior
    // round) that drop is narrowed to the retryable err classes -- a security_block or oauth
    // failure carries verbatim instead of being re-attempted.
    if (rec.ok === false && u && candidateUrls.has(u)
        && (!retryableOnly || isRetryableErr(rec.err))) continue; // retried this round -> replaced
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
    const response = await page.goto(url, GOTO_WAIT).catch(() => null);
    const rawHtml = response ? await response.text().catch(() => '') : '';
    await page.waitForTimeout(2500);
    await dismissModals(page);
    // #876: the SAME shared frame read as the mainline capture. This was a hand-spelled third copy
    // of the loop, which is precisely the drift `readFrameText` was extracted to prevent — a
    // future change to frame-read behaviour applied to the two mainline call sites would silently
    // have skipped this backfill path (REQ-182: one exported predicate, and a copy is a call site).
    const { text: rendered, hasPassword } = await readFrameText(page);
    const dom = await domFingerprint(page);
    const jsDependent = strippedLen(rawHtml) < 200 && rendered.trim().length >= SUBSTANTIAL_TEXT_CHARS;
    return buildHtmlFingerprint({ finalHost: hostOf(page.url()), headers: response ? response.headers() : {}, dom, jsDependent, hasPassword });
  } finally {
    await page.close();
  }
}

// ============================ NORMAL CAPTURE ============================
export function planSha256(candidates) {
  // #116 review: the capture-plan fingerprint — sha256 over the SORTED UNIQUE fragment-stripped
  // candidate URLs. Python's retry selection computes the same (headless._plan_sha256) over the
  // candidates.json it decided on; this run recomputes over its own read. districts can sit in
  // two batches at once (follow-ups re-include by design) with only per-batch run locks, so a
  // concurrent Stage-2 rewrite between the two reads is reachable — mismatch must fail LOUDLY,
  // never silently conflate two discovery rounds' plans in one manifest.
  const urls = [...new Set(candidates.map((c) => stripFragment(c.url)))].sort();
  return createHash('sha256').update(urls.join('\n')).digest('hex');
}

// #670: the per-district completeness summary — ONE construction site. Printed as the
// CAPTURE_SUMMARY stdout line the Python runner (stage3_capture/headless._capture_one)
// cross-checks against the manifest and stamps onto the stage-3 outcome state_event, so
// "was this capture everything it intended?" is answerable from gov_db, not inferred from
// artifact existence. A future receipt writer (#623) must reuse THIS function — never
// respell the fold (the implemented-twice-drifts class).
export function captureSummary(did, st, tasks) {
  const recs = st.records;
  const notAttempted = recs.filter((r) => (r.err || '').startsWith('not_attempted')).length;
  return {
    dir: did,
    intended: st.intended,                                              // candidates in the plan
    planned_this_run: tasks.reduce((n, t) => n + (t.did === did ? 1 : 0), 0),  // post-dedup/seed delta
    n_records: recs.length,                                             // what the manifest holds
    n_ok: recs.filter((r) => r.ok).length,
    n_failed: recs.filter((r) => !r.ok).length,                         // includes not_attempted
    n_not_attempted: notAttempted,
    deadline_hit: notAttempted > 0,
  };
}

async function runCapture(ROOT, CONC, only = null, deadlineMs = 0, retryableOnly = false, planSha = null) {
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
    if (retryableOnly && planSha && planSha !== planSha256(meta.candidates)) {
      // The plan changed between Python's retry selection and this read (a concurrent Stage-2
      // rewrite from another batch) -- abort loudly; the runner records `failed` and a re-run
      // re-selects against the current plan.
      console.error(`${did}: candidates.json changed since retry selection (plan fingerprint mismatch) -- aborting; re-run retry`);
      process.exit(3);
    }
    const capDir = path.join(ROOT, did, 'captures');
    mkdirSync(capDir, { recursive: true });
    // #117: the per-task journal. One JSONL line per record as it COMPLETES, so a hard kill
    // (SIGKILL before the end-of-run manifest) preserves full-fidelity records -- including
    // EMERGENT ones, whose URL is otherwise unrecoverable (md5 is one-way). A leftover journal
    // from a crashed run is renamed aside (never clobbered) -- reconstruct consumes it from
    // either name; the live journal is deleted once the real manifest lands (it supersedes it).
    const journalPath = path.join(ROOT, did, 'captures.journal.jsonl');
    if (existsSync(journalPath)) {
      // Uniqueness guard (review): tsSuffix is second-resolution and renameSync overwrites --
      // two rename-asides in the same second must not clobber an earlier crash journal.
      let aside = path.join(ROOT, did, `captures.journal.${tsSuffix()}.jsonl`);
      for (let n = 1; existsSync(aside); n += 1) {
        aside = path.join(ROOT, did, `captures.journal.${tsSuffix()}-${n}.jsonl`);
      }
      renameSync(journalPath, aside);
    }
    byDistrict[did] = { capDir, records: [], seen: new Set(), emergent: 0, journalPath,
      intended: meta.candidates.length };
    // #174 (follow-up redo): a prior round's captures.json seeds records + seen so this run
    // captures only the delta and the written manifest stays the district's complete union.
    // First runs are untouched (no manifest exists until end-of-run). An unreadable prior
    // manifest degrades to a fresh full capture -- writeVersioned still preserves the file.
    const priorPath = path.join(ROOT, did, 'captures.json');
    if (existsSync(priorPath)) {
      const candidateUrls = new Set(meta.candidates.map((c) => stripFragment(c.url)));
      try {
        seedFromPriorCaptures(byDistrict[did], JSON.parse(readFileSync(priorPath)), candidateUrls, retryableOnly);
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

  // #578: the PRE-CAPTURE security probe -- one lightweight GET of each district's dominant
  // planned host BEFORE any capture pressure. A challenged probe halts the whole district with
  // exactly one request of IP exposure. A clean probe is necessary-not-sufficient (rate-based
  // rules can trigger mid-run) -- the in-run breaker remains the guarantee. A probe NETWORK
  // failure is not a block signal: capture proceeds and surfaces its own errors.
  for (const did of Object.keys(byDistrict)) {
    const planned = tasks.filter((t) => t.did === did);
    if (!planned.length) continue;
    const hostCounts = {};
    for (const t of planned) { const h = hostOf(t.url); if (h) hostCounts[h] = (hostCounts[h] || 0) + 1; }
    const domHost = Object.entries(hostCounts).sort((a, b) => b[1] - a[1])[0];
    if (!domHost) continue;
    try {
      const r = await fetch(`https://${domHost[0]}/`, { redirect: 'follow', signal: AbortSignal.timeout(15000) });
      const body = (await r.text().catch(() => '')).slice(0, 8000).replace(/<[^>]+>/g, ' ');
      const challenge = detectChallenge({ 'cf-mitigated': r.headers.get('cf-mitigated') || '' }, body);
      if (challenge) {
        byDistrict[did].secHalted = true;
        byDistrict[did].secHaltReason = `pre-capture probe of ${domHost[0]} challenged (${challenge})`;
        console.error(`  ${did}: SECURITY BLOCK -- pre-capture probe of ${domHost[0]} returned a `
          + `challenge (${challenge}); skipping ALL ${planned.length} planned captures (one-attempt rule)`);
      } else {
        console.log(`  ${did}: security probe of ${domHost[0]} clean`);
      }
    } catch { /* probe network failure: proceed; the capture itself will surface real errors */ }
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
        // #578: a challenged fetch is a security block, not content -- one-attempt (Rule 3).
        const fetchChallenge = detectChallenge({ 'cf-mitigated': r.headers.get('cf-mitigated') || '' }, null);
        if (fetchChallenge) {
          rec.err = `security_block (${fetchChallenge})`;
          rec.fetch_status = r.status;
          return;
        }
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
        // #575 review: re-check the district breaker immediately before the SECOND, more
        // expensive network contact (a full Playwright render) — a sibling task for this same
        // district may have tripped the breaker while THIS task's fetch() was in flight (the
        // top-of-processTask check only guards the FIRST contact per task). This narrows, but
        // does not eliminate, the TOCTOU window: a sibling's fetch() that was ALREADY in flight
        // when the breaker trips still completes — there is no cross-task cancellation here.
        if (byDistrict[did].secHalted) {
          rec.err = `security_block (district capture halted -- ${byDistrict[did].secHaltReason}; one-attempt rule)`;
          return;
        }
        const page = await ctx.newPage();
        setupPageDialogHandler(page);
        try {
          const response = await page.goto(url, GOTO_WAIT).catch(() => null);
          const rawHtml = response ? await response.text().catch(() => '') : '';
          await page.waitForTimeout(2500);
          rec.final_url = page.url();
          noteFinalUrl(byDistrict[did], rec.final_url);

          // Modal dismissal sequenced AFTER the 2.5s wait, giving slow/deliberately-delayed
          // cookie-consent banners a window to actually render before dismissal is attempted.
          const modalsDismissed = await dismissModals(page);
          rec.modals_dismissed = modalsDismissed;
          if (modalsDismissed) await page.waitForTimeout(500);

          // #518: hasPassword scans the SAME frames as `text` below (page.evaluate alone is
          // main-frame-only and would miss an iframe-embedded SSO/login widget -- a login wall
          // whose password field lives in a same-origin iframe, common on portal-gated CMS
          // homepages, must not be scoped more narrowly than the text fidelityFlags reads it against).
          // #863: this EARLY read stays exactly where it was, because two consumers need it here
          // and only here -- detectChallenge (a challenge interstitial must abort the capture
          // BEFORE we spend a screenshot/pdf on it, one-attempt Rule 3) and `hasPassword`/
          // `jsDependent`, whose values feed the fingerprint basis (backward-compatibility rule:
          // changing what a fingerprint is derived from forces a mass re-review). What #863 moves
          // is only what gets PERSISTED as page.txt -- see the late re-read after segmentation.
          const early = await readFrameText(page);
          const earlyText = early.text;
          const hasPassword = early.hasPassword;
          // #578: a rendered CHALLENGE interstitial is a security block, not content -- record the
          // err, save NOTHING as ok, scan no anchors (one-attempt, Rule 3). Checked over the same
          // frame-scoped text the fidelity flags read, plus the goto response's headers.
          const challenge = detectChallenge(response ? response.headers() : {}, earlyText);
          if (challenge) {
            rec.err = `security_block (${challenge})`;
            if (response) rec.fetch_status = response.status();
            rec.fingerprint = buildHtmlFingerprint({
              finalHost: hostOf(rec.final_url),
              headers: response ? response.headers() : {},
              dom: {}, jsDependent: false, hasPassword: false,
            });
            return;
          }
          // Written from the EARLY read first so page.txt exists no matter what fails downstream
          // (screenshot, pdf, domFingerprint, segmentation). The late re-read below overwrites it
          // when segmentation succeeds; if anything throws in between, the capture still has the
          // file it has always had. Strictly additive safety -- never a path where page.txt is lost.
          writeFileSync(path.join(recDir, 'page.txt'), earlyText);
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

          // Hosting/CMS fingerprint -- gathered from the goto Response (headers we used to
          // discard) + a single DOM evaluate + a JS-dependency proxy (served-HTML text near
          // empty but rendered text substantial -> content came from JS).
          const dom = await domFingerprint(page);
          rec.fingerprint = buildHtmlFingerprint({
            finalHost: hostOf(rec.final_url),
            headers: response ? response.headers() : {},
            dom,
            // #863 deliberately does NOT move this to the late read: js_dependent is a FINGERPRINT
            // input, and the fingerprint basis must stay backward-compatible (a changed basis
            // re-hashes every record and forces a mass re-review). The early read is also the
            // semantically right one here -- "was the served HTML empty and the RENDERED text
            // substantial" is answered fine by the first rendered read.
            jsDependent: strippedLen(rawHtml) < 200 && earlyText.trim().length >= SUBSTANTIAL_TEXT_CHARS,
            hasPassword,
          });
          // #863: read the NON-MAIN frames now, BEFORE segmentation removes chrome from the live
          // DOM. Order matters -- an <iframe> nested inside a <footer>/<nav> landmark is detached
          // by that removal and its frame dies, so reading the iframes afterwards would silently
          // drop text that page.txt has always carried.
          const lateOther = await readFrameText(page, { skipMainFrame: true });
          // DOM segmentation (REQ-091): de-chrome the page for Stage 5 signals (additive; page.txt kept).
          // #875: a segment READ that succeeded and a segment WRITE that failed are different
          // facts, and both are recorded. `segmented` describes whether the segment FILES are on
          // disk; `text_phase` describes which read is in page.txt. A write failure (ENOSPC/EACCES)
          // after a good read leaves `segmented:false` with `text_phase:'final'` — that pair is
          // ACCURATE, not inconsistent: the late read really is what page.txt holds, and throwing
          // away a good read because an unrelated write failed would forfeit the whole point of
          // #863. Pinned by test so this is not re-litigated as a contradiction.
          let seg = null;
          try {
            seg = await segmentWithTimeout(page);
            if (seg) { writeSegments(recDir, seg); rec.segmented = true; }
            else { rec.segmented = false; }
          } catch { rec.segmented = false; }
          // #863: page.txt is re-persisted from the LATE read -- `seg.full` (the main frame, read
          // one statement before the chrome removal that produces `main`) plus the non-main frames
          // read just above. Same frame scope as before, later instant. This is what makes
          // `page.main.txt <= page.txt` true by construction instead of by coincidence.
          // `text_phase` records WHICH read is on disk, so Stage 5 can tell a post-fix capture from
          // a legacy split-read one without guessing from filenames (#864's larger point; this is
          // the one-field down payment, not the sidecar). Segmentation failing/timing out leaves
          // the early text in place and says so.
          const resolved = resolvePersistedText(
            { seg, lateOtherText: lateOther.text, earlyText });
          const text = resolved.text;
          rec.text_phase = resolved.phase;
          if (resolved.lateRead) rec.late_read = resolved.lateRead;
          if (resolved.phase === 'final') writeFileSync(path.join(recDir, 'page.txt'), text);
          rec.text_times = (text.match(TIME) || []).length;
          // Capture-fidelity flags (#518): login wall / soft-404 classification over persisted
          // facts (url/final_url, page text, hasPassword -- all frame-scoped identically to `text`,
          // gathered together above). Flag, never drop -- the record still processes; downstream
          // sees "suspect". Re-derivable via recompute-fidelity.
          // #863: computed over the text that was actually PERSISTED. The flags' own contract is
          // "derived ONLY from persisted facts (url/final_url, page.txt, has_password)", and
          // runRecomputeFidelity re-derives them by reading page.txt off disk -- so leaving this on
          // the early text would make the live and recompute paths disagree on every record whose
          // page changed between the reads. Same detector, same inputs, one answer.
          //
          // #873 (review of PR #872) asked for the opposite: `hasPassword` is read EARLY and `text`
          // is now LATE, so a login wall whose chrome renders late could cross
          // SUBSTANTIAL_TEXT_CHARS and escape the `login_wall` flag. The mechanism is real, but
          // note what it is NOT -- reading hasPassword late as well would produce the IDENTICAL
          // outcome, because the clause that misses is the LENGTH test, not the password test. So
          // "same instant" is not the fix; using the shorter read would be, and that is what breaks
          // live/recompute agreement, since recompute only ever sees page.txt.
          // MEASURED over the live corpus before deciding: 11 html captures carry
          // has_password, 7 have an early page.txt under 600 chars, and 0 of those reach 600 by
          // the late read (they sit at ~110-150 chars -- genuine walls with almost no content).
          // Population zero, so no change. The rerunnable watchdog is section C5 of
          // 2026-08-21-read-timing-split-measure.py; if it ever reports a non-zero population,
          // revisit with the min(early, late) rule and persist the early length so recompute can
          // still reproduce it.
          const flags = fidelityFlags({ url, finalUrl: rec.final_url, text, hasPassword });
          if (flags.length) rec.fidelity = flags;
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
    // #578: the district circuit breaker -- once tripped (probe, or SECURITY_BREAKER_N
    // consecutive challenges), the remaining URLs are recorded WITHOUT any network contact.
    // Deliberately not `not_attempted`: the #116 retry must never re-hammer a WAF (Rule 3).
    if (byDistrict[t.did].secHalted) {
      rec.hash = createHash('md5').update(t.url).digest('hex').slice(0, 10);
      rec.err = `security_block (district capture halted -- ${byDistrict[t.did].secHaltReason}; one-attempt rule)`;
      byDistrict[t.did].records.push(rec);
      try { appendFileSync(byDistrict[t.did].journalPath, `${JSON.stringify(rec)}\n`); } catch { /* best-effort */ }
      return rec;
    }
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
      // #578: fold this record into the breaker state; announce the halt once.
      const st = byDistrict[t.did];
      const wasHalted = st.secHalted;
      updateSecurityState(st, rec);
      if (st.secHalted && !wasHalted) {
        st.secHaltReason = `${st.secConsec} challenges with no successful capture between`;
        console.error(`  ${t.did}: SECURITY BLOCK -- halting this district's remaining captures `
          + `after ${st.secConsec} challenges unbroken by a successful capture (one-attempt rule, Rule 3)`);
      }
      byDistrict[t.did].records.push(rec);
      // #117: journal the completed record NOW -- appendFileSync is per-line durable, so a
      // SIGKILL between tasks loses at most the in-flight page, never completed work. A journal
      // write failure must never fail the task (the manifest is still the end-of-run authority).
      try { appendFileSync(byDistrict[t.did].journalPath, `${JSON.stringify(rec)}\n`); }
      catch { /* journal is best-effort; captures.json remains the authority */ }
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
        // #117: a LANDED manifest supersedes every journal for the district -- the live one AND
        // any renamed-aside crash leftovers (this run seeded from the prior manifest and re-covered
        // the plan, so a crashed run's journaled work is redone, not lost). Sweeping them here is
        // what keeps a FUTURE reconstruct from resurrecting stale records (review finding). A failed
        // manifest write keeps everything, so reconstruct still has full fidelity.
        for (const f of readdirSync(path.join(ROOT, did))) {
          if (f === 'captures.journal.jsonl' || (f.startsWith('captures.journal.') && f.endsWith('.jsonl'))) {
            try { unlinkSync(path.join(ROOT, did, f)); } catch { /* best-effort sweep */ }
          }
        }
        // #670: emitted ONLY after a successful manifest write — a missing line tells the Python
        // runner the write never landed (it raises -> `failed` event, loud, never inferred).
        console.log(`CAPTURE_SUMMARY ${JSON.stringify(captureSummary(did, byDistrict[did], tasks))}`);
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

// ============================ RECOMPUTE (shared skeleton) ============================
// Re-derive ONE field, in place, from facts already on disk -- a pure recompute, NO browser,
// NO network. The mechanism for applying a human-approved classification change (a CMS_HOSTS
// vocabulary edit, a LOGIN_URL_RE/SOFT404_RE tuning) to already-captured data without
// re-capturing: the raw signals never changed, only the function over them. Writes via
// versioned-redo only for districts that actually changed. `eligible(rec)` decides which
// records carry the inputs the recompute needs; `recompute(rec, did)` returns the new value
// (or undefined/null to mean "clear"); `changed(next, prev)` decides whether to write it.
function runRecompute(ROOT, label, { eligible, recompute, changed: hasChanged }) {
  const dirs = readdirSync(ROOT).filter((d) => existsSync(path.join(ROOT, d, 'captures.json')));
  let changedCount = 0;
  let scanned = 0;
  for (const did of dirs) {
    const capPath = path.join(ROOT, did, 'captures.json');
    const records = JSON.parse(readFileSync(capPath));
    let dirty = false;
    for (const rec of records) {
      if (!eligible(rec)) continue;
      scanned += 1;
      const { prev, next } = recompute(rec, did);
      if (hasChanged(next, prev)) { changedCount += 1; dirty = true; }
    }
    if (dirty) writeVersioned(capPath, JSON.stringify(records, null, 2));
  }
  console.log(`RECOMPUTE ${label} DONE — ${changedCount} of ${scanned} eligible records updated across ${dirs.length} districts`);
}

function runRecomputeCmsHint(ROOT) {
  runRecompute(ROOT, 'cms_hint', {
    eligible: (rec) => rec.fingerprint && !rec.fingerprint.error,
    recompute: (rec) => {
      const fp = rec.fingerprint;
      const prev = fp.cms_hint ?? null;
      const next = cmsHint([fp.final_host, ...(fp.resource_hosts || [])]);
      if (next !== prev) fp.cms_hint = next;
      return { prev, next };
    },
    changed: (next, prev) => next !== prev,
  });
}

function runRecomputeFidelity(ROOT) {
  runRecompute(ROOT, 'fidelity', {
    eligible: (rec) => rec.ok && rec.kind === 'html' && !!rec.hash,
    recompute: (rec, did) => {
      const txtPath = path.join(ROOT, did, 'captures', rec.hash, rec.files?.txt || 'page.txt');
      let text = '';
      try { text = readFileSync(txtPath, 'utf8').slice(0, 3000); } catch { /* no page.txt -> URL/password signals only */ }
      const prev = rec.fidelity || [];
      const next = fidelityFlags({
        url: rec.url, finalUrl: rec.final_url, text,
        hasPassword: !!(rec.fingerprint && rec.fingerprint.has_password),
      });
      if (JSON.stringify(next) !== JSON.stringify(prev)) {
        if (next.length) rec.fidelity = next; else delete rec.fidelity;
      }
      return { prev, next };
    },
    changed: (next, prev) => JSON.stringify(next) !== JSON.stringify(prev),
  });
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
        // Match runCapture (#225: shared GOTO_WAIT): CATCH a goto timeout and segment whatever
        // rendered (the DOM is present) rather than aborting.
        await page.goto(t.target, GOTO_WAIT).catch(() => null);
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
      parseInt(argv[4] || '0', 10) * 1000, argv[5] === 'retryable-only',
      (argv[6] || '').startsWith('plan-sha256=') ? argv[6].slice('plan-sha256='.length) : null);
  } else {
    await runCapture(argv[0], parseInt(argv[1] || '5', 10));
  }
}
