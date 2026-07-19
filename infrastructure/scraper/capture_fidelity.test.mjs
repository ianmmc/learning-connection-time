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

test('login_wall: hyphenated login-endpoint forms match (/login-page, /log-in, /sign-in-form)', () => {
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/staff-login-page', text: 'ok' }), ['login_wall']);
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/staff/log-in', text: 'ok' }), ['login_wall']);
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/portal/sign-in-form', text: 'ok' }), ['login_wall']);
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/district/login', text: 'ok' }), ['login_wall']);
});

test('fidelityFlags() with no argument returns [] instead of throwing', () => {
  assert.deepEqual(fidelityFlags(), []);
});

// --- soft_404 -----------------------------------------------------------------------------

test('soft_404: the verified morey.sburg.org shape ("Page Not Found" + "Status : 404")', () => {
  assert.deepEqual(fidelityFlags({
    url: 'https://morey.sburg.org/about-us/bell-schedule',
    text: 'District Home\nB.F. Morey Elementary School\nPage Not Found\nStatus : 404, Server #: w14a',
  }), ['soft_404']);
});

test('soft_404: phrase variants and non-ASCII separators (nbsp/<br> innerText) match', () => {
  // Next.js-style: '404 | This page could not be found.'
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/p', text: '404 | This page could not be found.' }),
    ['soft_404']);
  // <h1>Page&nbsp;Not&nbsp;Found</h1> -> innerText with  ; <br>-separated -> \n
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/p', text: 'Page Not Found' }), ['soft_404']);
  assert.deepEqual(fidelityFlags({ url: 'https://x.org/p', text: 'Page\nNot\nFound' }), ['soft_404']);
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

// --- #415 static-source pins -----------------------------------------------------------------

test('#415 pin: a non-2xx binary is a visible per-record err, never a render fallback', () => {
  const src = readFileSync(new URL('./capture_discovery.mjs', import.meta.url), 'utf8');
  // The write is gated on r.ok inside the binary branch (comment growth between the two
  // conditions is fine -- the window is generous on purpose)...
  assert.match(src, /if \(cls\.binary\) \{[\s\S]{0,2000}?if \(r\.ok\) \{/,
    'the non-2xx guard on the binary fetch path (#415) must not be simplified away');
  // ...and the non-2xx arm records the err and RETURNS (a render of a binary URL would
  // produce a blank ok:true html record -- worse than a visible failure). Order/spacing of
  // the assignments is deliberately NOT pinned.
  assert.match(src, /rec\.err = `binary_fetch_\$\{r\.status\}`;[\s\S]{0,300}?return;/,
    'non-2xx binary must err+return, not fall through to the render path');
});

test('review-round-2 pin: hasPassword scans the SAME frames as text, not just the main frame', () => {
  // A prior version gathered has_password via a main-frame-only page.evaluate while `text`
  // (fed into the SAME fidelityFlags call) iterated page.frames() -- an iframe-embedded
  // login wall (e.g. an SSO widget) would silently escape detection. Pin: the password check
  // must live inside the SAME per-frame loop that builds `text`.
  const src = readFileSync(new URL('./capture_discovery.mjs', import.meta.url), 'utf8');
  assert.match(src, /document\.querySelector\('input\[type="password"\]'\)/,
    'the password probe must still exist');
  assert.doesNotMatch(src, /has_password: !!document\.querySelector/,
    'the password probe must not live in a standalone main-frame-only page.evaluate again');
});
