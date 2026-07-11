// #127 / REQ-079: the browser-driving harness. Drives a REAL headless Chromium (the same
// `playwright` the capture uses) against in-memory HTML fixtures served via page.route().fulfill()
// -- no fixture HTTP server, no network, fully offline and deterministic. This is the idiomatic
// Playwright approach ("prefer the browser model Playwright already knows how to drive"): the four
// smoke-only behaviors named in #127 -- modal dismissal, the emergent scan's DOM read, page.pdf(),
// and (bonus) the DOM fingerprint + de-chrome segmentation -- run against actual DOM, not a fake page.
//
// Self-skips cleanly if the Chromium binary isn't installed (so `npm test` on a bare checkout stays
// green); CI installs it. Install locally with:  npx playwright install chromium
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, rmSync } from 'fs';
import os from 'os';
import path from 'path';
import { chromium } from 'playwright';
import {
  dismissModals, findEmergentLinks, readAnchors, domFingerprint, segmentChrome,
  withTimeout, noteFileResult, DE_CHROME_LANDMARKS,
} from './capture_discovery.mjs';

// Serve one HTML string for every request this page makes (main doc + any subresource), so the test
// is fully offline. Mirrors how captureInto navigates, minus the network. Favicon gets an explicit
// 404 -- without it, the browser's automatic /favicon.ico request would be mis-served the fixture
// HTML as text/html (harmless today, but a surprise for any future subresource-sensitive fixture).
async function loadFixture(page, html) {
  await page.route('**/*', (route) => {
    if (route.request().url().endsWith('/favicon.ico')) return route.fulfill({ status: 404 });
    return route.fulfill({ contentType: 'text/html', body: html });
  });
  await page.goto('https://fixture.test/', { waitUntil: 'load' });
}

let browser = null;
let skipReason = null;

before(async () => {
  try {
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  } catch (e) {
    // In CI, an unlaunchable Chromium is a broken environment, not an optional feature: fail LOUD.
    // Skipped tests exit 0 (`node --test` passes on all-skip), so a silent skip here would let an
    // environment regression quietly disable this whole file while the job stays green.
    if (process.env.CI) throw e;
    skipReason = `Chromium unavailable (${String(e).split('\n')[0]}); run: npx playwright install chromium`;
  }
});

after(async () => { if (browser) await browser.close(); });

async function withPage(t, fn) {
  if (!browser) return t.skip(skipReason);
  const page = await browser.newPage();
  try { await fn(page); } finally { await page.close(); }
}

// ----------------------------- modal dismissal -----------------------------
test('dismissModals fires the CLICK path: an Accept button removes its banner', async (t) => {
  await withPage(t, async (page) => {
    // #banner has no modal/overlay class and no high z-index, so neither the CSS-hide nor the
    // DOM-removal path touches it -- only clicking "Accept" (via DISMISS_SELECTORS) removes it.
    await loadFixture(page, `<!doctype html><html><body>
      <div id="banner">We use cookies.
        <button onclick="document.getElementById('banner').remove()">Accept</button></div>
      <main>Real page content</main></body></html>`);
    // NOTE: dismissModals' boolean return is trivially true whenever the CSS injection succeeds
    // (see the no-modal test below), so it proves nothing about the click -- the DOM is the witness.
    await dismissModals(page);
    assert.equal(await page.locator('#banner').count(), 0, 'the Accept click removed the banner');
    assert.equal(await page.locator('main').count(), 1, 'real content is untouched');
  });
});

test('dismissModals fires the DOM-REMOVAL path: a .cookie-banner with no button is stripped', async (t) => {
  await withPage(t, async (page) => {
    await loadFixture(page, `<!doctype html><html><body>
      <div class="cookie-banner">We use cookies.</div>
      <main>Real page content</main></body></html>`);
    await dismissModals(page);   // return value is vacuous (see CLICK-path note); assert on the DOM
    assert.equal(await page.locator('.cookie-banner').count(), 0, 'the consent banner was removed');
    assert.equal(await page.locator('main').count(), 1);
  });
});

test('dismissModals is non-destructive on a page with no modal at all', async (t) => {
  await withPage(t, async (page) => {
    await loadFixture(page, `<!doctype html><html><body>
      <main>Just the bell schedule, no modal.</main></body></html>`);
    const dismissed = await dismissModals(page);
    assert.equal(dismissed, true, 'the hide-CSS injection alone counts as handled');
    assert.match(await page.locator('main').innerText(), /bell schedule/i, 'real content survives');
  });
});

// ----------------------------- emergent scan (DOM read + pure match) -----------------------------
test('the emergent scan reads anchors off a real DOM and keeps only schedule-bearing links', async (t) => {
  await withPage(t, async (page) => {
    await loadFixture(page, `<!doctype html><html><body>
      <a href="/bell-schedule.pdf">Bell Schedule</a>
      <a href="/athletics">Athletics</a>
      <a href="/office-hours">Office Hours</a>
      <a href="https://other.org/schedule">External Schedule</a></body></html>`);
    // THE production DOM read (readAnchors), not a hand-copied evaluate -- an edit to the
    // production selector/fields is caught here (PR #239 review).
    const anchors = await readAnchors(page);
    assert.deepEqual(findEmergentLinks(anchors), [
      'https://fixture.test/bell-schedule.pdf',
      'https://fixture.test/office-hours',
      'https://other.org/schedule',
    ], 'Athletics (no keyword) is dropped; hrefs are resolved absolute in DOM order');
  });
});

// ----------------------------- page.pdf() (the unconditional render-to-PDF path) -----------------------------
test('page.pdf() writes a real PDF and noteFileResult records it only on success', async (t) => {
  await withPage(t, async (page) => {
    await loadFixture(page, '<!doctype html><html><body><main>Print me to PDF</main></body></html>');
    const tmp = mkdtempSync(path.join(os.tmpdir(), 'lct-pdf-'));
    const pdfPath = path.join(tmp, 'page.pdf');
    const rec = { files: {} };
    try {
      await withTimeout(page.pdf({ path: pdfPath, format: 'Letter', printBackground: true }), 45_000, 'pdf')
        .then(() => noteFileResult(rec, 'pdf', 'page.pdf'))
        .catch((e) => noteFileResult(rec, 'pdf', 'page.pdf', e));
      assert.equal(rec.files.pdf, 'page.pdf', 'the manifest records the file only after a successful write');
      assert.equal(rec.pdf_err, undefined, 'no error note on the success path');
      assert.equal(readFileSync(pdfPath).subarray(0, 5).toString(), '%PDF-', 'a valid PDF landed on disk');
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});

// ----------------------------- DOM fingerprint + de-chrome segmentation (bonus coverage) -----------------------------
test('domFingerprint extracts the <meta generator> and off-domain iframe hosts', async (t) => {
  await withPage(t, async (page) => {
    await loadFixture(page, `<!doctype html><html><head>
      <meta name="generator" content="Finalsite"></head><body>
      <iframe src="https://cdn.example.net/calendar-widget"></iframe></body></html>`);
    const dom = await domFingerprint(page);
    assert.equal(dom.meta_generator, 'Finalsite');
    assert.ok(dom.iframe_hosts.includes('cdn.example.net'), 'the embed host is captured as a structural signal');
  });
});

test('segmentChrome captures header/footer/nav and excludes them from main', async (t) => {
  await withPage(t, async (page) => {
    await loadFixture(page, `<!doctype html><html><body>
      <header>District Home Banner</header>
      <nav>Menu Home About Athletics</nav>
      <main>First bell 8:05 AM dismissal 3:10 PM UNIQUEBODY</main>
      <footer>Copyright 2026 Example USD</footer></body></html>`);
    const seg = await segmentChrome(page, DE_CHROME_LANDMARKS);
    assert.match(seg.header, /District Home Banner/);
    assert.match(seg.nav, /Menu Home About/);
    assert.match(seg.footer, /Copyright 2026/);
    assert.match(seg.main, /UNIQUEBODY/, 'the body content is in main');
    assert.doesNotMatch(seg.main, /Copyright 2026/, 'chrome (footer) is stripped from main -- no false Stage-5 signal');
  });
});

test('segmentChrome honors a WIDENED landmarks list -- new chrome leaves main AND lands in its segment', async (t) => {
  // PR #239 review: header/footer/nav grabs used to be hardcoded, so the old test passed only
  // because the config coincidentally matched. This widened list diverges from the defaults on
  // purpose: .site-footer must flow through to BOTH main-exclusion and the footer segment.
  await withPage(t, async (page) => {
    await loadFixture(page, `<!doctype html><html><body>
      <div class="site-footer">District Office Hours 8:00-4:30 WIDEFOOTER</div>
      <main>First bell 8:05 AM UNIQUEBODY</main></body></html>`);
    const seg = await segmentChrome(page, [...DE_CHROME_LANDMARKS, '.site-footer']);
    assert.match(seg.footer, /WIDEFOOTER/, 'the widened selector is attributed to the footer segment');
    assert.doesNotMatch(seg.main, /WIDEFOOTER/, 'and stripped from main');
    assert.match(seg.main, /UNIQUEBODY/);
  });
});
