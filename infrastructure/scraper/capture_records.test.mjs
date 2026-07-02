// Unit tests for the pure record-bookkeeping helpers in capture_discovery.mjs:
//   noteFileResult (#18: no phantom files{} entries when a write/screenshot fails)
//   noteFinalUrl   (#44: emergent dedup includes the post-redirect final_url)
//   stripFragment  (exported for parity with capture_stage3.py's _strip_fragment, #43)
// The browser-driving capture loop itself stays uncovered (REQ-079), same as the
// fingerprint helpers' tests -- these cover the deterministic manifest logic.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { noteFileResult, noteFinalUrl, stripFragment } from './capture_discovery.mjs';

test('noteFileResult records a files{} entry only on success (#18)', () => {
  const rec = { files: {} };
  noteFileResult(rec, 'pdf', 'page.pdf');
  assert.deepEqual(rec.files, { pdf: 'page.pdf' });
  assert.equal(rec.pdf_err, undefined);
});

test('noteFileResult on failure records <key>_err and NO phantom files{} entry (#18)', () => {
  const rec = { files: { txt: 'page.txt' } };
  noteFileResult(rec, 'png', 'page.png', new Error('screenshot timed out after 45000ms'));
  assert.equal('png' in rec.files, false); // the phantom files.png of issue #18
  assert.match(rec.png_err, /screenshot timed out/);
  assert.ok(rec.png_err.length <= 80); // same truncation as the pdf_err precedent
  assert.deepEqual(rec.files, { txt: 'page.txt' }); // other entries untouched
});

test('noteFinalUrl adds the fragment-stripped final_url to the seen set (#44)', () => {
  const district = { seen: new Set(['https://x.org/start']) };
  // capture of /start redirected here:
  noteFinalUrl(district, 'https://x.org/bell-schedules/#top');
  assert.ok(district.seen.has('https://x.org/bell-schedules/'));
  // an emergent anchor pointing straight at the redirect target now dedups:
  assert.ok(district.seen.has(stripFragment('https://x.org/bell-schedules/#middle')));
});

test('noteFinalUrl ignores a missing final_url (#44)', () => {
  const district = { seen: new Set() };
  noteFinalUrl(district, undefined);
  noteFinalUrl(district, '');
  assert.equal(district.seen.size, 0);
});

test('stripFragment normalizes like new URL(): case, default port, empty path (#43 parity)', () => {
  assert.equal(stripFragment('HTTPS://X.Org:443/a#f'), 'https://x.org/a');
  assert.equal(stripFragment('http://x.org:80/p?q=1#z'), 'http://x.org/p?q=1');
  assert.equal(stripFragment('https://x.org'), 'https://x.org/');
  assert.equal(stripFragment('https://x.org:8080/a'), 'https://x.org:8080/a');
  assert.equal(stripFragment('https://x.org/a b'), 'https://x.org/a%20b');
  assert.equal(stripFragment('https://x.org/a/../b'), 'https://x.org/b');
  assert.equal(stripFragment('not a url#frag'), 'not a url'); // catch branch: raw split
});
