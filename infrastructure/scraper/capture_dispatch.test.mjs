// #127 / REQ-079: the pure DECISION cores the capture branch-dispatch is built on. These are the
// exact functions captureInto calls at runtime (not copies), so a passing test here is a statement
// about production routing. The browser-driving glue around them is covered in capture_browser.test.mjs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  classifyFetchKind, driveFormatOutcome, withTimeout,
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

test('withTimeout clears its timer so a resolved op leaves nothing pending on the event loop', async () => {
  // If the reject timer weren't cleared, this test file would hang ~10s after the assertions pass
  // (node:test waits for the loop to drain). Reaching the end quickly IS the assertion.
  await withTimeout(Promise.resolve(1), 10_000, 'pdf');
  assert.ok(true);
});
