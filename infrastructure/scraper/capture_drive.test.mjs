import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isGoogleUrl, extractFileId, driveExportCandidates } from './capture_drive.mjs';

test('isGoogleUrl recognizes drive.google.com and docs.google.com only', () => {
  assert.equal(isGoogleUrl('https://drive.google.com/file/d/abc123/view'), true);
  assert.equal(isGoogleUrl('https://docs.google.com/document/d/xyz/edit'), true);
  assert.equal(isGoogleUrl('https://example.org/bell-schedule.pdf'), false);
  assert.equal(isGoogleUrl('not a url'), false, 'garbage input must not throw');
});

test('extractFileId matches each known single-resource pattern', () => {
  assert.deepEqual(
    extractFileId('https://drive.google.com/file/d/ABC123xyz/view?usp=sharing'),
    { id: 'ABC123xyz', kind: 'drive_file' },
  );
  assert.deepEqual(
    extractFileId('https://docs.google.com/document/d/DEF456abc/edit'),
    { id: 'DEF456abc', kind: 'doc' },
  );
  assert.deepEqual(
    extractFileId('https://docs.google.com/spreadsheets/d/SHEET1/edit'),
    { id: 'SHEET1', kind: 'sheet' },
  );
  assert.deepEqual(
    extractFileId('https://docs.google.com/presentation/d/SLIDE1/edit'),
    { id: 'SLIDE1', kind: 'slide' },
  );
  assert.deepEqual(
    extractFileId('https://drive.google.com/open?id=GHI789xyz'),
    { id: 'GHI789xyz', kind: 'drive_file' },
  );
});

test('extractFileId returns null for a folder URL -- must escalate to Tier 2, never guess', () => {
  assert.equal(extractFileId('https://drive.google.com/drive/folders/FOLDER123'), null);
});

test('driveExportCandidates: Docs export PDF + Markdown', () => {
  const cands = driveExportCandidates('https://docs.google.com/document/d/DEF456abc/edit');
  assert.equal(cands.length, 2);
  assert.ok(cands.some((c) => c.format === 'pdf'));
  assert.ok(cands.some((c) => c.format === 'md'));
});

test('driveExportCandidates: Sheets export CSV + PDF (PDF catches an embedded image a CSV would lose)', () => {
  const cands = driveExportCandidates('https://docs.google.com/spreadsheets/d/SHEET1/edit');
  assert.equal(cands.length, 2);
  assert.ok(cands.some((c) => c.format === 'csv'));
  assert.ok(cands.some((c) => c.format === 'pdf'));
});

test('driveExportCandidates: Slides export PDF only', () => {
  const cands = driveExportCandidates('https://docs.google.com/presentation/d/SLIDE1/edit');
  assert.equal(cands.length, 1);
  assert.equal(cands[0].format, 'pdf');
});

test('driveExportCandidates: a generic Drive file is auto-format direct download (real type varies, inferred from content-type at fetch time)', () => {
  const cands = driveExportCandidates('https://drive.google.com/file/d/ABC123xyz/view');
  assert.equal(cands.length, 1);
  assert.equal(cands[0].format, 'auto');
});

test('driveExportCandidates returns null for a folder URL -- caller must escalate to Tier 2', () => {
  assert.equal(driveExportCandidates('https://drive.google.com/drive/folders/FOLDER123'), null);
});
