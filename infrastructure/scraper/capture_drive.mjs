// Tier 1 (unauthenticated) Google Drive/Docs/Sheets/Slides export-URL handling. No OAuth
// needed for this tier -- confirmed via research (Gemini MCP + a citation-backed
// Perplexity cross-check) this still works reliably today for "anyone with the link"
// content. Tier 2 (OAuth Drive API -- the only path for folder enumeration, and the
// fallback when Tier 1 fails for an individual file) lives separately; see
// docs/ACQUISITION_PIPELINE.md Stage 3 for the full design.

const FILE_PATTERNS = [
  { re: /drive\.google\.com\/file\/d\/([a-zA-Z0-9_-]+)/, kind: 'drive_file' },
  { re: /drive\.google\.com\/open\?id=([a-zA-Z0-9_-]+)/, kind: 'drive_file' },
  { re: /docs\.google\.com\/document\/d\/([a-zA-Z0-9_-]+)/, kind: 'doc' },
  { re: /docs\.google\.com\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/, kind: 'sheet' },
  { re: /docs\.google\.com\/presentation\/d\/([a-zA-Z0-9_-]+)/, kind: 'slide' },
];

export function isGoogleUrl(url) {
  try {
    const h = new URL(url).hostname;
    return h === 'drive.google.com' || h === 'docs.google.com';
  } catch {
    return false;
  }
}

// Exported for testing -- the caller (capture_discovery.mjs) only needs driveExportCandidates(),
// but the id/kind extraction is the part worth testing in isolation against real URL shapes.
export function extractFileId(url) {
  for (const { re, kind } of FILE_PATTERNS) {
    const m = url.match(re);
    if (m) return { id: m[1], kind };
  }
  try {
    const qid = new URL(url).searchParams.get('id');
    if (qid) return { id: qid, kind: 'drive_file' };
  } catch {
    /* not a parseable URL at all */
  }
  return null;
}

// Per the Stage 3 design decision (ACQUISITION_PIPELINE.md): Docs -> PDF+Markdown,
// Slides -> PDF, Sheets -> CSV+PDF (PDF as the safety net for an image pasted into a
// cell, which CSV alone would silently lose), generic Drive file -> direct download
// (format 'auto' -- the real file type varies, inferred from content-type at fetch time,
// not assumed). Returns null for a folder URL or any unrecognized pattern -- the caller
// must escalate to Tier 2 in that case, never guess.
export function driveExportCandidates(url) {
  const found = extractFileId(url);
  if (!found) return null;
  const { id, kind } = found;
  switch (kind) {
    case 'doc':
      return [
        { format: 'pdf', fetchUrl: `https://docs.google.com/document/d/${id}/export?format=pdf` },
        { format: 'md', fetchUrl: `https://docs.google.com/document/d/${id}/export?format=md` },
      ];
    case 'slide':
      return [{ format: 'pdf', fetchUrl: `https://docs.google.com/presentation/d/${id}/export/pdf` }];
    case 'sheet':
      return [
        { format: 'csv', fetchUrl: `https://docs.google.com/spreadsheets/d/${id}/export?format=csv` },
        { format: 'pdf', fetchUrl: `https://docs.google.com/spreadsheets/d/${id}/export?format=pdf` },
      ];
    case 'drive_file':
      return [{ format: 'auto', fetchUrl: `https://drive.google.com/uc?export=download&id=${id}` }];
    default:
      return null;
  }
}
