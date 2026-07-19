// Unit tests for the pure hosting/CMS fingerprint helpers in capture_discovery.mjs.
// The browser-driving parts (domFingerprint, htmlFingerprintFor, runCapture, runBackfill)
// are not covered here -- same gap as the rest of capture_discovery.mjs's render logic
// (REQ-079); these cover the deterministic header/host/CMS logic that decides the fields.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import {
  hostOf, cdnHints, cmsHint, hostMatches, strippedLen, buildHtmlFingerprint,
  buildFetchFingerprint, categorizeEmbedHost, embedCategories,
} from './capture_discovery.mjs';

test('categorizeEmbedHost buckets social/calendar/doc-viewer, else other (REQ-115)', () => {
  assert.equal(categorizeEmbedHost('www.facebook.com'), 'social');
  assert.equal(categorizeEmbedHost('widgets.sociablekit.com'), 'social');
  assert.equal(categorizeEmbedHost('teamup.com'), 'calendar');
  assert.equal(categorizeEmbedHost('calendar.google.com'), 'calendar');
  assert.equal(categorizeEmbedHost('docs.google.com'), 'doc-viewer');
  assert.equal(categorizeEmbedHost('issuu.com'), 'doc-viewer');
  assert.equal(categorizeEmbedHost('example.k12.us'), 'other');
  assert.equal(categorizeEmbedHost(''), 'other');
});

test('embedCategories dedups + sorts the distinct classes on a page (REQ-115)', () => {
  assert.deepEqual(embedCategories(['www.facebook.com', 'twitter.com', 'teamup.com']), ['calendar', 'social']);
  assert.deepEqual(embedCategories([]), []);
});

test('buildHtmlFingerprint carries categorized embed hosts + presence (REQ-115)', () => {
  const fp = buildHtmlFingerprint({
    finalHost: 'ms.dryden.k12.ny.us', headers: {}, jsDependent: true,
    dom: { resource_hosts: [], iframe_hosts: ['www.facebook.com', 'teamup.com'] },
  });
  assert.deepEqual(fp.embed_hosts, ['calendar', 'social']);
  assert.equal(fp.embed_present, true);
});

test('hostOf extracts a lowercase hostname, empty on garbage', () => {
  assert.equal(hostOf('https://WWW.Marion-ISD.org/o/vms/page'), 'www.marion-isd.org');
  assert.equal(hostOf('not a url'), '');
});

test('cdnHints detects platforms from characteristic headers', () => {
  assert.deepEqual(cdnHints({ 'cf-ray': 'abc', server: 'cloudflare' }), ['cloudflare']);
  assert.deepEqual(cdnHints({ 'x-amz-cf-id': 'x', 'x-amz-request-id': 'y' }), ['aws']);
  assert.deepEqual(cdnHints({ 'x-github-request-id': '1' }), ['github-pages']);
  assert.deepEqual(cdnHints({ server: 'GSE', 'x-goog-generation': '1' }), ['google']);
  assert.deepEqual(cdnHints({}), []);
});

test('cmsHint matches CMS_HOSTS by suffix, like discover.py gate()', () => {
  // a Finalsite-hosted asset host
  assert.equal(cmsHint(['cmsv2-assets.finalsite.net']), 'finalsite.net');
  // a SchoolWires/Blackboard district host
  assert.equal(cmsHint(['cmsv2.schoolwires.com']), 'schoolwires.com');
  // a Google Sites page
  assert.equal(cmsHint(['sites.google.com']), 'sites.google.com');
  // the 2026-06-24 school-district-vendor additions
  assert.equal(cmsHint(['cdnsm1-ss18.sharpschool.com']), 'sharpschool.com');
  assert.equal(cmsHint(['cmsv2-assets.apptegy.net']), 'apptegy.net');
  assert.equal(cmsHint(['counter.educationalnetworks.net']), 'educationalnetworks.net');
  // a general host/CDN is deliberately NOT in the list (pollution guard)
  assert.equal(cmsHint(['core-docs.s3.amazonaws.com']), null);
  // a plain district domain matches nothing
  assert.equal(cmsHint(['www.marion-isd.org']), null);
  // first match across the list wins; empty/falsey hosts skipped
  assert.equal(cmsHint(['', 'www.example.org', 'foo.blackboard.com']), 'blackboard.com');
});

test('hostMatches agrees with the shared cross-language golden vectors (#34/#416 parity)', () => {
  // The same fixture tests/test_cms_host_parity.py runs through Python's _host_matches —
  // a rule change in one language fails the other's suite until both are updated.
  const f = path.join(path.dirname(fileURLToPath(import.meta.url)),
                      '..', 'acquisition', 'common', 'config', 'cms_host_match_cases.json');
  const { cases } = JSON.parse(readFileSync(f, 'utf8'));
  assert.ok(cases.length >= 10, 'fixture must carry the full vector set');
  for (const c of cases) {
    assert.equal(hostMatches(c.host, c.suffix), c.match, `${c.host} ~ ${c.suffix}: ${c.why}`);
  }
});

test('cmsHint requires a dot boundary — a dotless superstring host must NOT match (#416)', () => {
  // pre-fix: host.endsWith(cms) let `myfinalsite.net` claim `finalsite.net` — and cms_hint is
  // dispatch-load-bearing since #540 (Edlio sibling-variant dedup), so a false hint has
  // behavioral downstream. Same rule as discover.py's _host_matches.
  assert.equal(cmsHint(['myfinalsite.net']), null);
  assert.equal(cmsHint(['evilschoolwires.com']), null);
  assert.equal(cmsHint(['notapptegy.net']), null);
  // the exact host and dotted-subdomain forms still match
  assert.equal(cmsHint(['finalsite.net']), 'finalsite.net');
  assert.equal(cmsHint(['assets.finalsite.net']), 'finalsite.net');
});

test('strippedLen measures visible text length, ignoring tags/script/style', () => {
  assert.equal(strippedLen('<html><body>hello world</body></html>'), 'hello world'.length);
  // a JS shell: lots of markup, no real text
  assert.ok(strippedLen('<div id="root"></div><script>var x=1;</script>') < 5);
});

test('buildHtmlFingerprint assembles fields, drops own host, caps resource hosts', () => {
  const fp = buildHtmlFingerprint({
    finalHost: 'www.district.org',
    headers: { server: 'nginx', 'x-powered-by': 'PHP/8', 'cf-ray': 'z' },
    dom: {
      meta_generator: 'WordPress 6.5',
      resource_hosts: ['www.district.org', 'cdn.finalsite.net', 'fonts.gstatic.com'],
    },
    jsDependent: false,
  });
  assert.equal(fp.final_host, 'www.district.org');
  assert.equal(fp.server, 'nginx');
  assert.equal(fp.powered_by, 'PHP/8');
  assert.deepEqual(fp.cdn_hints, ['cloudflare']);
  assert.equal(fp.meta_generator, 'WordPress 6.5');
  assert.ok(!fp.resource_hosts.includes('www.district.org')); // own host dropped
  assert.deepEqual(fp.resource_hosts, ['cdn.finalsite.net', 'fonts.gstatic.com']);
  assert.equal(fp.js_dependent, false);
  assert.equal(fp.cms_hint, 'finalsite.net'); // from the resource host
});

test('buildHtmlFingerprint carries hasPassword as has_password (#518 review-round-2)', () => {
  // hasPassword is now an explicit param (frame-scoped identically to `text` at the call site,
  // not gathered inside domFingerprint's main-frame-only evaluate) -- pin the plumbing.
  const withPw = buildHtmlFingerprint({
    finalHost: 'x.org', headers: {}, dom: {}, jsDependent: false, hasPassword: true,
  });
  assert.equal(withPw.has_password, true);
  const withoutPw = buildHtmlFingerprint({
    finalHost: 'x.org', headers: {}, dom: {}, jsDependent: false, hasPassword: false,
  });
  assert.equal(withoutPw.has_password, false);
  const omitted = buildHtmlFingerprint({ finalHost: 'x.org', headers: {}, dom: {}, jsDependent: false });
  assert.equal(omitted.has_password, false);
});

test('buildFetchFingerprint gives a reduced (no-DOM) fingerprint from a fetch Response', () => {
  const fakeResponse = {
    url: 'https://files-backend.assets.thrillshare.com/documents/x/Bell_Schedule.pdf',
    headers: new Map([['server', 'cloudflare'], ['cf-ray', 'abc'], ['content-type', 'application/pdf']]),
  };
  const fp = buildFetchFingerprint(fakeResponse);
  assert.equal(fp.final_host, 'files-backend.assets.thrillshare.com');
  assert.equal(fp.server, 'cloudflare');
  assert.deepEqual(fp.cdn_hints, ['cloudflare']);
  assert.equal(fp.meta_generator, null);
  assert.deepEqual(fp.resource_hosts, []);
  assert.equal(fp.js_dependent, null); // N/A without a DOM
});
