// #127 / REQ-079: the pure DECISION cores the capture branch-dispatch is built on. These are the
// exact functions captureInto calls at runtime (not copies), so a passing test here is a statement
// about production routing. The browser-driving glue around them is covered in capture_browser.test.mjs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  classifyFetchKind, driveFormatOutcome, withTimeout, segmentBuckets, resolvePersistedText,
} from './capture_discovery.mjs';

// ----------------------------- classifyFetchKind: fetch-branch dispatch -----------------------------
test('classifyFetchKind routes PDF content to the binary-save path', () => {
  assert.deepEqual(classifyFetchKind('application/pdf'), { binary: true, kind: 'pdf', ext: 'pdf' });
  assert.deepEqual(classifyFetchKind('application/pdf; charset=binary'),
    { binary: true, kind: 'pdf', ext: 'pdf' }, 'a charset param must not change the routing');
});

test('classifyFetchKind routes images to binary-save with the subtype as extension', () => {
  assert.deepEqual(classifyFetchKind('image/png'), { binary: true, kind: 'image', ext: 'png' });
  assert.deepEqual(classifyFetchKind('image/jpeg; charset=x'),
    { binary: true, kind: 'image', ext: 'jpeg' }, 'a trailing param is stripped from the ext');
  assert.equal(classifyFetchKind('image/').ext, 'img', 'a missing subtype falls back to img, never blank');
});

test('classifyFetchKind sends everything else to the HTML render path', () => {
  assert.deepEqual(classifyFetchKind('text/html'), { binary: false, kind: 'html', ext: null });
  assert.deepEqual(classifyFetchKind(''), { binary: false, kind: 'html', ext: null },
    'an empty/absent content-type renders as HTML (the safe default)');
});

test('classifyFetchKind is case-insensitive on the content-type', () => {
  assert.equal(classifyFetchKind('APPLICATION/PDF').kind, 'pdf');
  assert.equal(classifyFetchKind('Image/PNG').kind, 'image');
});

test('both dispatch cores accept a NULL content-type (Headers.get() returns null, not undefined)', () => {
  // PR #239 review: a `= ""` default only substitutes on strict undefined -- these are exported
  // reusable cores, so a raw Headers.get('content-type') passed straight through must not throw.
  assert.deepEqual(classifyFetchKind(null), { binary: false, kind: 'html', ext: null });
  assert.deepEqual(classifyFetchKind(undefined), { binary: false, kind: 'html', ext: null });
  assert.deepEqual(driveFormatOutcome(null, 'auto'), { skip: false, ext: 'bin' });
  assert.deepEqual(driveFormatOutcome(null, 'pdf'), { skip: false, ext: 'pdf' });
});

// ----------------------------- driveFormatOutcome: Drive export routing -----------------------------
test('driveFormatOutcome skips an HTML interstitial (the requested format was unavailable)', () => {
  assert.deepEqual(driveFormatOutcome('text/html', 'pdf'), { skip: true, ext: null });
  assert.deepEqual(driveFormatOutcome('text/html; charset=utf-8', 'auto'), { skip: true, ext: null });
});

test('driveFormatOutcome keeps a named format as its own extension', () => {
  assert.deepEqual(driveFormatOutcome('application/pdf', 'pdf'), { skip: false, ext: 'pdf' });
  assert.deepEqual(driveFormatOutcome('image/png', 'png'), { skip: false, ext: 'png' },
    'a named format wins even if the content subtype differs');
});

test('driveFormatOutcome sniffs auto: pdf vs the content subtype', () => {
  assert.deepEqual(driveFormatOutcome('application/pdf', 'auto'), { skip: false, ext: 'pdf' });
  assert.deepEqual(driveFormatOutcome('image/jpeg', 'auto'), { skip: false, ext: 'jpeg' });
  assert.equal(driveFormatOutcome('application/octet-stream', 'auto').ext, 'octet-stream');
  assert.equal(driveFormatOutcome('', 'auto').ext, 'bin', 'a blank content-type in auto falls back to bin');
});

// ----------------------------- withTimeout: the page.pdf()/screenshot resilience race --------------
test('withTimeout resolves with the wrapped value when it wins the race', async () => {
  // This also proves the reject timer is CLEARED on settle: if it weren't, this file would hang
  // ~10s after the assertion passes (node:test waits for the event loop to drain).
  const v = await withTimeout(Promise.resolve('done'), 10_000, 'pdf');
  assert.equal(v, 'done');
});

test('withTimeout rejects with a labeled error when the operation outlasts the budget', async () => {
  const hang = new Promise(() => {}); // never settles -- the page.pdf()-hangs case
  await assert.rejects(withTimeout(hang, 20, 'pdf'), /pdf timed out after 20ms/);
});

test('withTimeout propagates the wrapped rejection unchanged', async () => {
  await assert.rejects(
    withTimeout(Promise.reject(new Error('boom')), 10_000, 'screenshot'),
    /boom/,
  );
});

// ----------------------------- segmentBuckets: the de-chrome grab derivation -----------------------
test('segmentBuckets reproduces the segment split for the live config defaults', () => {
  const b = segmentBuckets(['header', 'footer', 'nav',
    '[role="banner"]', '[role="contentinfo"]', '[role="navigation"]']);
  assert.deepEqual(b, {
    header: ['header', '[role="banner"]'],
    footer: ['footer', '[role="contentinfo"]'],
    nav: ['nav', '[role="navigation"]'],
  });
});

test('segmentBuckets routes widened heuristics to their segment (the config note anticipates these)', () => {
  const b = segmentBuckets(['.site-footer', '#colophon', '.main-nav', '.masthead']);
  assert.deepEqual(b.footer, ['.site-footer', '#colophon']);
  assert.deepEqual(b.nav, ['.main-nav']);
  assert.deepEqual(b.header, ['.masthead']);
});

test('segmentBuckets leaves an unclassifiable selector out of every named segment', () => {
  // Still removed from main by segmentChrome (removeSel covers ALL landmarks) -- just unattributed.
  const b = segmentBuckets(['.some-widget']);
  assert.deepEqual(b, { header: [], footer: [], nav: [] });
});

// ------------- #874/#875: which read ends up in page.txt, and what gets recorded -------------
// Both findings came from PR #872's review. The inline branching they landed on is now one pure
// function, so every branch is testable without a browser.
test('#874: a FAILED late read (seg === null) keeps the early text and records why', () => {
  const r = resolvePersistedText({ seg: null, lateOtherText: '\niframe words', earlyText: '\nearly words' });
  assert.equal(r.phase, 'early');
  assert.equal(r.text, '\nearly words');
  assert.equal(r.lateRead, 'failed', '"no error recorded anywhere" was the substance of #874');
});

test('#874: an EMPTY main frame is not a failure -- the late read still wins, carrying the iframes', () => {
  // The exact regression #874 named: `if (seg && seg.full)` treated full==='' as failure and
  // discarded lateOther.text, which HAD been read successfully, reverting page.txt to the early
  // read and reproducing #863 on the pages most likely to trigger it.
  const r = resolvePersistedText({
    seg: { full: '', main: '', header: '', footer: '', nav: '' },
    lateOtherText: '\nBell schedule 8:05 AM lives in an iframe',
    earlyText: '\nshort early text',
  });
  assert.equal(r.phase, 'final', 'an empty main frame must not discard a good iframe read');
  assert.match(r.text, /8:05 AM/);
  assert.equal(r.lateRead, undefined, 'the normal path records no fallback reason');
});

test('#874: a page that went BLANK under us keeps the content we already had', () => {
  const r = resolvePersistedText({
    seg: { full: '', main: '' }, lateOtherText: '', earlyText: '\nreal content we already captured',
  });
  assert.equal(r.phase, 'early', 'overwriting real text with nothing is a loss, not a fix');
  assert.equal(r.lateRead, 'empty');
});

test('#874: when BOTH reads are empty the late read is still the truthful one', () => {
  const r = resolvePersistedText({ seg: { full: '', main: '' }, lateOtherText: '', earlyText: '   ' });
  assert.equal(r.phase, 'final', 'nothing to preserve, so do not claim the early read');
});

test('#874: the normal post-863 path -- late main plus the non-main frames', () => {
  const r = resolvePersistedText({
    seg: { full: 'MAIN 8:05 AM', main: 'MAIN 8:05 AM' },
    lateOtherText: '\nFRAME 3:10 PM', earlyText: '\nstale',
  });
  assert.equal(r.phase, 'final');
  assert.equal(r.text, '\nMAIN 8:05 AM\nFRAME 3:10 PM');
});

test('#875: a segment WRITE failure does not invalidate the segment READ', () => {
  // The review called `segmented:false` + `text_phase:'final'` an inconsistent receipt. It is not:
  // the two fields describe different facts -- whether the segment FILES reached disk, and which
  // read is in page.txt. A good read is still a good read when an unrelated ENOSPC/EACCES stops
  // the write, and discarding it would forfeit the whole point of #863. Pinned so the pair is not
  // re-litigated as a contradiction.
  const seg = { full: 'MAIN 8:05 AM', main: 'MAIN 8:05 AM' };
  const r = resolvePersistedText({ seg, lateOtherText: '', earlyText: '\nstale' });
  assert.equal(r.phase, 'final',
    'text_phase is decided by the READ; the write outcome is carried separately by `segmented`');
});
