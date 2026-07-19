// Unit tests for the pure record-bookkeeping helpers in capture_discovery.mjs:
//   noteFileResult (#18: no phantom files{} entries when a write/screenshot fails)
//   noteFinalUrl   (#44: emergent dedup includes the post-redirect final_url)
//   stripFragment  (exported for parity with capture_stage3.py's _strip_fragment, #43)
// The browser-driving capture loop itself stays uncovered (REQ-079), same as the
// fingerprint helpers' tests -- these cover the deterministic manifest logic.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'fs';
import { noteFileResult, noteFinalUrl, stripFragment, seedFromPriorCaptures, isRetryableErr } from './capture_discovery.mjs';

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

test('seedFromPriorCaptures carries prior records + seeds seen/emergent (#174)', () => {
  const district = { records: [], seen: new Set(), emergent: 0 };
  const prior = [
    { url: 'https://x.org/bell', final_url: 'https://x.org/bell-final', ok: true,
      source: 'discovered', files: { txt: 'page.txt' } },
    { url: 'https://x.org/found-link', ok: true, source: 'emergent', files: { txt: 'page.txt' } },
  ];
  seedFromPriorCaptures(district, prior, new Set(['https://x.org/new-this-round']));
  assert.equal(district.records.length, 2);           // both carried into the new manifest
  assert.ok(district.seen.has('https://x.org/bell')); // never re-hit (one-attempt rule)
  assert.ok(district.seen.has('https://x.org/bell-final')); // redirect target seeded too
  assert.equal(district.emergent, 1);                 // emergent budget resumes, not doubled
});

test('seedFromPriorCaptures drops a FAILED prior record whose url is retried this round (#174)', () => {
  const district = { records: [], seen: new Set(), emergent: 0 };
  const prior = [
    { url: 'https://x.org/slow', ok: false, source: 'discovered', files: {},
      err: 'not_attempted (capture deadline reached)' },
  ];
  seedFromPriorCaptures(district, prior, new Set(['https://x.org/slow']));
  assert.equal(district.records.length, 0);            // replaced by the retry's fresh record
  assert.equal(district.seen.has('https://x.org/slow'), false); // retry NOT blocked
});

test('seedFromPriorCaptures keeps a FAILED prior record whose url is NOT retried (#174)', () => {
  const district = { records: [], seen: new Set(), emergent: 0 };
  const prior = [
    { url: 'https://x.org/dead', ok: false, source: 'discovered', files: {}, err: 'nav timeout' },
  ];
  seedFromPriorCaptures(district, prior, new Set(['https://x.org/other']));
  assert.equal(district.records.length, 1);            // manifest completeness preserved
  assert.ok(district.seen.has('https://x.org/dead'));
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

test('isRetryableErr: crash/deadline remnants retry; one-attempt classes do not (#116)', () => {
  assert.equal(isRetryableErr('not_attempted (capture deadline reached)'), true);
  assert.equal(isRetryableErr('not_recovered (capture interrupted before completion)'), true);
  assert.equal(isRetryableErr('security_block'), false);      // one-attempt WAF rule
  assert.equal(isRetryableErr('needs_oauth_reauth'), false);  // fails identically until #115
  assert.equal(isRetryableErr('binary_fetch_403'), false);    // the origin already answered
  assert.equal(isRetryableErr(null), false);
});

test('seedFromPriorCaptures retryable-only mode: retryable failures retry, one-attempt failures carry (#116)', () => {
  const district = { records: [], seen: new Set(), emergent: 0 };
  const prior = [
    { url: 'https://x.org/slow', ok: false, source: 'discovered', files: {},
      err: 'not_attempted (capture deadline reached)' },                      // retryable -> dropped
    { url: 'https://x.org/waf', ok: false, source: 'discovered', files: {},
      err: 'security_block' },                                                // one-attempt -> carried
    { url: 'https://x.org/good', ok: true, source: 'discovered', files: { txt: 'page.txt' } },
  ];
  const candidates = new Set(['https://x.org/slow', 'https://x.org/waf', 'https://x.org/good']);
  seedFromPriorCaptures(district, prior, candidates, true);
  assert.deepEqual(district.records.map((r) => r.url).sort(),
    ['https://x.org/good', 'https://x.org/waf']);              // waf + good carried
  assert.equal(district.seen.has('https://x.org/slow'), false); // retry NOT blocked
  assert.equal(district.seen.has('https://x.org/waf'), true);   // never re-hit (one-attempt)
});

test('seedFromPriorCaptures default mode is unchanged by the #116 param (any failed candidate retries)', () => {
  const district = { records: [], seen: new Set(), emergent: 0 };
  const prior = [{ url: 'https://x.org/waf', ok: false, source: 'discovered', files: {}, err: 'security_block' }];
  seedFromPriorCaptures(district, prior, new Set(['https://x.org/waf']));
  assert.equal(district.records.length, 0);                    // #174 follow-up semantics preserved
});

test('#117 pins: the per-task journal is appended per record, renamed aside at start, deleted after the manifest', () => {
  // The journal write sites live in the browser-driving loop (uncovered by convention, REQ-079);
  // pin the three load-bearing behaviors as source shapes instead.
  const src = readFileSync(new URL('./capture_discovery.mjs', import.meta.url), 'utf8');
  // 1. appended in processTask's finally, best-effort (a journal failure must not fail the task)
  assert.match(src, /appendFileSync\(byDistrict\[t\.did\]\.journalPath, `\$\{JSON\.stringify\(rec\)\}\\n`\)/,
    'each completed record must be journaled');
  // 2. a crash leftover is renamed aside, never clobbered
  assert.match(src, /renameSync\(journalPath, path\.join\(ROOT, did, `captures\.journal\.\$\{tsSuffix\(\)\}\.jsonl`\)\)/,
    'a leftover journal must be preserved aside');
  // 3. deleted only after the manifest write LANDED (inside the same try, after writeVersioned)
  assert.match(src, /writeVersioned\(path\.join\(ROOT, did, 'captures\.json'\)[\s\S]{0,400}?unlinkSync\(byDistrict\[did\]\.journalPath\)/,
    'the journal is deleted only once captures.json supersedes it');
});
