// #670 — the per-district completeness summary: ONE construction site (captureSummary),
// printed as the CAPTURE_SUMMARY stdout line the Python runner cross-checks against the
// manifest and stamps onto the stage-3 outcome state_event. These tests cover the fold's
// arithmetic; the wiring (that runCapture actually prints it, after the manifest write,
// from THIS function) is source-pinned like the rest of the capture loop (REQ-079).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'fs';
import { captureSummary } from './capture_discovery.mjs';

const mkSt = (records, intended) => ({ records, intended });

test('counts ok / failed / not_attempted from the records the manifest will hold', () => {
  const st = mkSt([
    { url: 'http://d/a', ok: true },
    { url: 'http://d/b', ok: false, err: 'timeout' },
    { url: 'http://d/c', ok: false, err: 'not_attempted (capture deadline reached)' },
  ], 3);
  const tasks = [{ did: 'x' }, { did: 'x' }, { did: 'x' }, { did: 'other' }];
  const s = captureSummary('x', st, tasks);
  assert.deepEqual(s, {
    dir: 'x', intended: 3, planned_this_run: 3, n_records: 3,
    n_ok: 1, n_failed: 2, n_not_attempted: 1, deadline_hit: true,
  });
});

test('clean run: no not_attempted, deadline_hit false, planned scoped to the district', () => {
  const st = mkSt([{ url: 'http://d/a', ok: true }], 1);
  const s = captureSummary('x', st, [{ did: 'x' }, { did: 'y' }, { did: 'y' }]);
  assert.equal(s.planned_this_run, 1);
  assert.equal(s.n_not_attempted, 0);
  assert.equal(s.deadline_hit, false);
});

test('redo delta: seeded prior records count in n_records while planned_this_run is the delta', () => {
  // #174: on a redo the manifest is the district's complete union (seeded prior records +
  // this run's delta) — n_records describes the manifest, planned_this_run this run's work.
  const st = mkSt([
    { url: 'http://d/a', ok: true },              // seeded from the prior manifest
    { url: 'http://d/b', ok: true },              // captured this run
  ], 2);
  const s = captureSummary('x', st, [{ did: 'x' }]);   // only /b was queued
  assert.equal(s.n_records, 2);
  assert.equal(s.planned_this_run, 1);
  assert.equal(s.intended, 2);
});

// Source pins: the un-unit-testable wiring. The summary line must be emitted (a) inside
// runCapture's finally, (b) AFTER the writeVersioned manifest write in the same per-district
// try (so a failed write never prints a summary — the Python runner treats the missing line
// as the loud failure), and (c) from captureSummary itself — never a respelled fold.
const src = readFileSync(new URL('./capture_discovery.mjs', import.meta.url), 'utf8');

test('source pin: the summary line is printed from captureSummary, after the manifest write', () => {
  const emit = src.match(/writeVersioned\(path\.join\(ROOT, did, 'captures\.json'\)[\s\S]*?CAPTURE_SUMMARY \$\{JSON\.stringify\(captureSummary\(/);
  assert.ok(emit, 'CAPTURE_SUMMARY must be emitted after writeVersioned, built by captureSummary()');
});

test('source pin: exactly one CAPTURE_SUMMARY emission site', () => {
  const sites = src.match(/CAPTURE_SUMMARY \$\{/g) || [];
  assert.equal(sites.length, 1, 'one construction/emission site — never a second spelling');
});
