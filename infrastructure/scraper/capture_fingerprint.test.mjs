// Unit tests for the pure hosting/CMS fingerprint helpers in capture_discovery.mjs.
// The browser-driving parts (domFingerprint, htmlFingerprintFor, runCapture, runBackfill)
// are not covered here -- same gap as the rest of capture_discovery.mjs's render logic
// (REQ-079); these cover the deterministic header/host/CMS logic that decides the fields.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  hostOf, cdnHints, cmsHint, strippedLen, buildHtmlFingerprint, buildFetchFingerprint,
} from './capture_discovery.mjs';

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
  // a plain district domain matches nothing
  assert.equal(cmsHint(['www.marion-isd.org']), null);
  // first match across the list wins; empty/falsey hosts skipped
  assert.equal(cmsHint(['', 'www.example.org', 'foo.blackboard.com']), 'blackboard.com');
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
