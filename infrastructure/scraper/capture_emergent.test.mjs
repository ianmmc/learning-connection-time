// #127 / REQ-079: the pure emergent-scan cores. findEmergentLinks decides WHICH anchors are
// schedule-bearing; selectEmergentTargets decides which of those actually get queued (dedup + the
// per-district cap). captureInto calls both at runtime, so these tests pin the real one-hop behavior.
// The DOM-reading step that produces the anchor list is covered in capture_browser.test.mjs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { findEmergentLinks, selectEmergentTargets } from './capture_discovery.mjs';

// ----------------------------- findEmergentLinks: keyword match over anchors -----------------------------
test('findEmergentLinks matches a schedule keyword in the anchor TEXT', () => {
  const anchors = [
    { text: 'Bell Schedule', href: 'https://d.org/a' },
    { text: 'Athletics', href: 'https://d.org/b' },
  ];
  assert.deepEqual(findEmergentLinks(anchors), ['https://d.org/a']);
});

test('findEmergentLinks matches a keyword in the HREF even when the text does not', () => {
  const anchors = [{ text: 'Click here', href: 'https://d.org/daily-schedule.pdf' }];
  assert.deepEqual(findEmergentLinks(anchors), ['https://d.org/daily-schedule.pdf']);
});

test('findEmergentLinks is case-insensitive and covers the full keyword set', () => {
  for (const kw of ['bell', 'schedule', 'hours', 'start-time', 'start_time',
    'daily-schedule', 'times', 'school-day', 'schoolday']) {
    assert.deepEqual(findEmergentLinks([{ text: kw.toUpperCase(), href: 'https://d.org/x' }]),
      ['https://d.org/x'], `keyword '${kw}' must match regardless of case`);
  }
});

test('findEmergentLinks strips the fragment so #anchor self-links are not re-queued', () => {
  const anchors = [{ text: 'Bell Schedule', href: 'https://d.org/page#bell' }];
  assert.deepEqual(findEmergentLinks(anchors), ['https://d.org/page']);
});

test('findEmergentLinks returns nothing when no anchor is schedule-bearing', () => {
  assert.deepEqual(findEmergentLinks([{ text: 'Home', href: 'https://d.org/' }]), []);
  assert.deepEqual(findEmergentLinks([]), []);
});

// ----------------------------- selectEmergentTargets: dedup + per-district cap -----------------------------
test('selectEmergentTargets queues fresh links and advances the counter', () => {
  const seen = new Set();
  const out = selectEmergentTargets(['https://d.org/a', 'https://d.org/b'], seen, 0, 25);
  assert.deepEqual(out.targets, ['https://d.org/a', 'https://d.org/b']);
  assert.equal(out.emergent, 2);
  assert.ok(seen.has('https://d.org/a') && seen.has('https://d.org/b'), 'queued links join the seen-set');
});

test('selectEmergentTargets skips already-seen links (no re-capture across the one hop)', () => {
  const seen = new Set(['https://d.org/a']);
  const out = selectEmergentTargets(['https://d.org/a', 'https://d.org/b'], seen, 1, 25);
  assert.deepEqual(out.targets, ['https://d.org/b'], 'the already-seen link is not re-queued');
  assert.equal(out.emergent, 2);
});

test('selectEmergentTargets stops at the per-district cap (a link-dense page cannot explode the queue)', () => {
  const seen = new Set();
  const links = Array.from({ length: 10 }, (_, i) => `https://d.org/${i}`);
  const out = selectEmergentTargets(links, seen, 23, 25); // 2 slots left under the cap of 25
  assert.deepEqual(out.targets, ['https://d.org/0', 'https://d.org/1']);
  assert.equal(out.emergent, 25);
});

test('selectEmergentTargets already at the cap queues nothing', () => {
  const seen = new Set();
  const out = selectEmergentTargets(['https://d.org/a'], seen, 25, 25);
  assert.deepEqual(out.targets, []);
  assert.equal(out.emergent, 25);
  assert.equal(seen.size, 0, 'nothing is even marked seen once the cap is reached');
});

test('selectEmergentTargets dedups repeats WITHIN one call', () => {
  const seen = new Set();
  const out = selectEmergentTargets(['https://d.org/a', 'https://d.org/a'], seen, 0, 25);
  assert.deepEqual(out.targets, ['https://d.org/a'], 'the same link twice in one page counts once');
  assert.equal(out.emergent, 1);
});
