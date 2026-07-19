// Unit tests for fidelityFlags (#518) -- the pure capture-fidelity detector -- plus a
// static-source pin on the #415 r.ok guard (the fetch flow itself is browser/network-driving
// and stays uncovered, same as the rest of the capture loop -- REQ-079).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'fs';
import { fidelityFlags } from './capture_discovery.mjs';

// --- login_wall ---------------------------------------------------------------------------

test('login_wall: the motivating Huntington gateway URL (#518 survey)', () => {
  assert.deepEqual(fidelityFlags({
    url: 'https://www.huntingtonisd.com/gateway/Login.aspx?returnUrl=%2fschools%2fhuntington_middle_school%2fabout_us%2fbell_schedules',
    finalUrl: 'https://www.huntingtonisd.com/gateway/Login.aspx?returnUrl=%2f...',
    text: 'User Name Password Sign In',
  }), ['login_wall']);
});

test('login_wall: post-redirect final URL is a login endpoint even when the request URL is clean', () => {
  assert.deepEqual(fidelityFlags({
    url: 'https://district.org/bell-schedules',
    finalUrl: 'https://district.org/portal/signin?next=/bell-schedules',
    text: 'Welcome back',
  }), ['login_wall']);
});

test('login_wall: a password field on a near-empty page flags; on a content page it does not', () => {
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/p', text: 'Log in to view', hasPassword: true }),
    ['login_wall']);
  const contentPage = `Bell Schedule 8:00 AM - 3:00 PM ${'lunch periods and dismissal details '.repeat(20)}`;
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/p', text: contentPage, hasPassword: true }), []);
});

test('login_wall: "login" must be a path/query token, not a substring of a word', () => {
  // e.g. a school named "Loginville" or a /blogindex/ path must not trip the URL pattern
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/blogindex/bell-schedule', text: 'ok' }), []);
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/about/technology', text: 'ok' }), []);
});

// --- soft_404 -----------------------------------------------------------------------------

test('soft_404: the verified morey.sburg.org shape ("Page Not Found" + "Status : 404")', () => {
  assert.deepEqual(fidelityFlags({
    url: 'https://morey.sburg.org/about-us/bell-schedule',
    text: 'District Home\nB.F. Morey Elementary School\nPage Not Found\nStatus : 404, Server #: w14a',
  }), ['soft_404']);
});

test('soft_404: only the head of the text is scanned -- a long article mentioning 404 does not trip', () => {
  const article = `${'School board meeting minutes and district news coverage. '.repeat(60)}\nThe old page returned a 404 error before the redesign.`;
  assert.ok(article.length > 3000);
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/news', text: article }), []);
});

test('a normal schedule page carries no flags', () => {
  assert.deepEqual(fidelityFlags({
    url: 'https://hamilton.sburg.org/apps/bell_schedules/index.jsp?id=7565',
    finalUrl: 'https://hamilton.sburg.org/apps/bell_schedules/index.jsp?id=7565',
    text: 'Bell Schedules\nClass Times\nBreakfast 8:55 AM 9:05 AM\nDismissal 3:43 PM',
  }), []);
});

test('flags compose: a login page whose text also says page not found carries both', () => {
  assert.deepEqual(fidelityFlags({
    url: 'https://x.org/gateway/Login.aspx?returnUrl=%2fbell',
    text: 'Page Not Found',
  }), ['login_wall', 'soft_404']);
});

// --- #415 static-source pin ----------------------------------------------------------------

test('#415 pin: the direct-fetch binary write is gated on r.ok', () => {
  const src = readFileSync(new URL('./capture_discovery.mjs', import.meta.url), 'utf8');
  assert.match(src, /cls\.binary && r\.ok/,
    'the non-2xx guard on the binary fetch path (#415) must not be simplified away');
});
