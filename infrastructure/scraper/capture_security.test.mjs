// Unit tests for the #578 security-block enforcement (CLAUDE.md Critical Rule 3, one-attempt):
// detectChallenge (pure challenge detection over headers + body text) and updateSecurityState
// (the district circuit breaker's fold). The probe/browser wiring stays uncovered like the rest
// of the capture loop (REQ-079) -- source pins guard its presence.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'fs';
import {
  detectChallenge, updateSecurityState, SECURITY_BREAKER_N, CHALLENGE_MARKERS,
} from './capture_discovery.mjs';

// The REAL interstitial text batch_00021 recorded as `ok` 31 times -- the motivating fixture.
const MILLARD_INTERSTITIAL = `cms.mpsomaha.org
Performing security verification

This website uses a security service to protect against malicious bots. This page is displayed while the website verifies you are not a bot.

Ray ID: a1e2754d4dfb03c2
Performance and Security by Cloudflare
Privacy`;

test('the Millard batch_00021 interstitial is detected (the 31/83 incident)', () => {
  const hit = detectChallenge({}, MILLARD_INTERSTITIAL);
  assert.ok(hit && hit.includes('performing security verification'));
});

test('cf-mitigated: challenge header is the canonical signal, body not needed', () => {
  assert.ok(detectChallenge({ 'cf-mitigated': 'challenge' }, null));
  assert.ok(detectChallenge({ 'cf-mitigated': 'CHALLENGE' }, ''));
});

test('CDN presence alone is NOT a block -- a real page served via cloudflare passes', () => {
  // cdnHints('cloudflare') keys off cf-ray/server; detectChallenge must not (all of Millard's
  // REAL pages are cloudflare-fronted too).
  assert.equal(detectChallenge({ 'cf-ray': 'abc123', server: 'cloudflare' },
    'Bell Schedules\nSchool starts at 8:05 AM and dismisses at 3:38 PM.'), null);
});

test('a deep quote past the bounded head does not trip', () => {
  const page = `${'x'.repeat(4200)} just a moment...`;
  assert.equal(detectChallenge({}, page), null);
});

test('every marker is lowercase (the haystack is lowercased once)', () => {
  for (const m of CHALLENGE_MARKERS) assert.equal(m, m.toLowerCase());
});

test('breaker: trips on N consecutive challenges, an ok resets the streak', () => {
  const st = {};
  const block = { err: 'security_block (body marker)', ok: false };
  const good = { ok: true, err: undefined };
  updateSecurityState(st, block);
  updateSecurityState(st, block);
  assert.ok(!st.secHalted);
  updateSecurityState(st, good);                 // reset
  updateSecurityState(st, block);
  updateSecurityState(st, block);
  assert.ok(!st.secHalted);
  updateSecurityState(st, block);                // 3rd consecutive
  assert.ok(st.secHalted);
  assert.equal(SECURITY_BREAKER_N, 3);
});

test('breaker: a non-security err neither counts nor resets', () => {
  const st = {};
  updateSecurityState(st, { err: 'security_block (x)', ok: false });
  updateSecurityState(st, { err: 'binary_fetch_404', ok: false });
  updateSecurityState(st, { err: 'security_block (x)', ok: false });
  updateSecurityState(st, { err: 'security_block (x)', ok: false });
  assert.ok(st.secHalted);                       // 3 security_blocks total streak unbroken by 404
});

// --- source pins (the wiring the unit tests can't drive -- REQ-079 pattern) -----------------
test('capture loop wires the enforcement points', () => {
  const src = readFileSync(new URL('./capture_discovery.mjs', import.meta.url), 'utf8');
  for (const pin of [
    'security_block (district capture halted',   // breaker skip-record (non-retryable, not not_attempted)
    'pre-capture probe of',                      // the probe halt path
    'detectChallenge(response ? response.headers()', // render-path detection over the goto response
    "cf-mitigated': r.headers.get('cf-mitigated')",  // fetch-path + probe header read
  ]) assert.ok(src.includes(pin), `capture_discovery.mjs lost the #578 pin: ${pin}`);
});
