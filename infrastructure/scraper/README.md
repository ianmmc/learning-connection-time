# LCT Stage 3 — Capture (Playwright)

Direct-invocation Playwright capture scripts for **Stage 3 (Capture)** of the acquisition
pipeline. These are run as plain Node ESM modules (no HTTP service, no Crawlee) against the
`candidates.json` produced by Stage 2, writing per-URL artifacts under
`data/raw/lea-website-captures/<district>/captures/<hash>/`.

> The earlier Crawlee + Express HTTP-service design (`src/`, `dist/`, the `:3000` server, the
> Docker `scraper` service) was retired and archived to
> `data/archive/crawlee-ollama-era-superseded-20260625/`. Only the scripts below are live.

## Live scripts

| File | Role |
|------|------|
| `capture_discovery.mjs` | Main Stage 3 capture: per-candidate render (innerText → `.txt`, screenshot → `.png`, `page.pdf()` → `.pdf`), modal dismissal, one-hop emergent-candidate discovery, per-record hosting/CMS fingerprint. Also exposes `backfill-fingerprints` (and `recompute-cms-hint`) modes. |
| `capture_drive.mjs` | Google Drive/Docs/Sheets/Slides Tier-1 unauthenticated export-URL logic (`isGoogleUrl`, `driveExportCandidates`, `extractFileId`). |
| `capture_fingerprint.test.mjs`, `capture_drive.test.mjs` | `node:test` unit tests for the helpers above. |

See `docs/ACQUISITION_PIPELINE.md` (Stage 3) for the full design.

## Setup & run

```bash
npm install                      # installs playwright only
npx playwright install chromium  # browser binary

node --test *.test.mjs           # run the unit tests
```

Capture runs are orchestrated by `infrastructure/acquisition/.../capture_stage3.py`, which shells
out to these scripts — see the Stage 3 section of the pipeline doc for invocation.

## Ethical constraints (unchanged)

Honest user-agent, no bot evasion or fingerprint spoofing; Cloudflare/WAF/CAPTCHA blocks are
flagged for manual collection, never bypassed; all attempts and outcomes are recorded.
