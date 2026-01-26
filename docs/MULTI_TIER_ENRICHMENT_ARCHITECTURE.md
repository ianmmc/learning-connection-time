# Bell Schedule Acquisition Architecture

**Date:** January 26, 2026 (Updated)
**Status:** Production Ready

---

## Overview

A two-service pipeline that uses Crawlee for intelligent web mapping and Ollama for content validation. Captures pages as PDFs before extraction, creating an audit trail.

**Core Principles:**
- Serial processing (one district at a time) for debuggability
- Two-stage Ollama filtering (URL ranking + PDF triage)
- Learning loop improves pattern matching over time
- Full restart on failure (simple recovery model)

---

## Architecture

### Two-Service Design

```
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Orchestrator (Python)                   │
│  Port 8000                                                   │
│  - Queue management                                          │
│  - Database operations                                       │
│  - Ollama calls                                              │
│  - File management                                           │
│  - Learning loop updates                                     │
│                                                              │
│  POST /acquire/district/{id}   - Start acquisition           │
│  GET  /acquire/status/{id}     - Check progress              │
│  POST /patterns/feedback       - Update patterns from feedback│
│  POST /triage/pdf              - Score PDF for bell schedule │
└─────────────────────────────────────────────────────────────┘
                         │ HTTP calls
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Fastify + Crawlee (Node.js)                     │
│  Port 3000                                                   │
│  - Website mapping with pattern filtering                    │
│  - PDF capture                                               │
│                                                              │
│  POST /map      {url, patterns} → {pages[]}                  │
│  POST /capture  {urls[], outputDir} → {pdfs[]}               │
│  GET  /health                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Pipeline Flow

```
Step 1: User queues districts
    │
Step 2: Python retrieves website_url from database
    │
Step 3: Crawlee maps district website
    │   └─→ Uses patterns.json for include/exclude filtering
    │   └─→ Collects: URL, title, snippet, keywords found
    │
Step 4: Ollama (phi3:mini) ranks URLs
    │   └─→ Scores likelihood of bell schedule content
    │   └─→ Returns filtered target list to Python
    │
Step 5: Capture targeted pages as PDFs
    │   ├─→ Google Drive URLs → GoogleDriveHandler (3-tier fallback)
    │   ├─→ Direct PDF URLs → HTTP download (fallback to Crawlee)
    │   └─→ HTML pages → Crawlee render to PDF
    │   └─→ Stored in data/raw/bell_schedule_pdfs/{state}/{district}/
    │
Step 6: pdftotext extracts text from each PDF
    │
Step 7: Ollama (llama3.1:8b) scores each PDF
    │   └─→ "Does this contain bell schedule data?" (0-1 score)
    │
Step 8: Script triages PDFs by score
    │   ├─→ Score ≥ 0.7: Keep in active/
    │   ├─→ Score 0.3-0.7: Move to quarantine/ for review
    │   └─→ Score < 0.3: Move to rejected/
    │
Step 9: User-directed ingestion (separate command)
    └─→ Review active/ PDFs
    └─→ Extract bell schedule times
    └─→ Import to database
    └─→ Feedback updates learning loop
```

---

## Model Selection

### URL Ranking (Step 4) - Speed Critical

**Model:** `phi3:mini` (3.8B params)

| Attribute | Value |
|-----------|-------|
| Task | Score URL + title for bell schedule likelihood |
| Speed | Sub-second inference |
| Memory | ~4GB with Q4_K_M quantization |
| Expected accuracy | 70-80% |

### PDF Text Triage (Step 7) - Comprehension Critical

**Model:** `llama3.1:8b` (8B params)

| Attribute | Value |
|-----------|-------|
| Task | Analyze extracted text for bell schedule content |
| Speed | 2-5 seconds per PDF |
| Memory | ~8GB with Q4_K_M quantization |
| Expected accuracy | 85-95% |

---

## Page Metadata Collection

Crawlee collects rich metadata for each page to give Ollama better signal:

```typescript
interface CrawleePageData {
  url: string;
  title: string;
  depth: number;
  metaDescription: string | null;
  h1: string | null;
  breadcrumb: string | null;
  linkTextUsedToReachPage: string;
  timePatternCount: number;
  hasSchedulePdfLink: boolean;
  keywordMatchCount: number;
  outboundLinkCount: number;
}
```

**Why these parameters matter:**

| Parameter | Signal Value | Rationale |
|-----------|--------------|-----------|
| `h1` | High | "Bell Schedule" vs "Athletic Schedule" |
| `linkTextUsedToReachPage` | High | What the district *called* the link |
| `timePatternCount` | High | Direct signal of schedule content |
| `metaDescription` | Medium-High | Human-written page summary |
| `breadcrumb` | Medium | "Academics > Bell Schedule" context |
| `hasSchedulePdfLink` | Medium | Schedules often link to PDFs |

---

## Edge Case Handling

| Scenario | Detection | Action | Implementation |
|----------|-----------|--------|----------------|
| **Google Drive URL** | `drive.google.com` or `docs.google.com` | 1. Direct download<br>2. Playwright preview<br>3. Gemini API | `acquire.py` → `GoogleDriveHandler` |
| **Direct PDF link** | URL ends in `.pdf` | 1. HTTP download<br>2. Fall back to Crawlee | `acquire.py` → `_download_direct_pdf()` |
| **Auth/login wall** | Login form or 401/403 | Mark `blocked: true`, flag for manual | `scraper.ts` → security indicators |
| **Cloudflare/WAF** | Challenge page detected | Mark `blocked: true`, flag for manual | `scraper.ts` → cloudflare patterns |
| **Site unreachable** | Connection timeout/error | Mark `unreachable: true`, flag for manual | Timeout handling |

---

## Modal/Popup Dismissal

Many school district websites display modal overlays (cookie consent, weather notices, announcements) that block content capture. The capturer implements a multi-phase dismissal strategy, ordered from most robust to most brittle:

### Strategy Hierarchy

| Phase | Approach | Robustness | Implementation |
|-------|----------|------------|----------------|
| 1 | **CSS injection** | High leverage | Hide overlays globally via `display: none !important` |
| 2 | **JS dialog handler** | Preventive | Auto-dismiss native `alert()`, `confirm()`, `prompt()` |
| 3 | **Click dismiss buttons** | Moderate | Match common button selectors (Close, Dismiss, Got it, etc.) |
| 4 | **DOM removal** | Last resort | Remove fixed/absolute positioned elements with high z-index |

### CSS Injection (Phase 1)

Injects CSS to hide common modal patterns:

```css
*[role="dialog"], *[aria-modal="true"],
.modal, .modal-backdrop, .overlay, .popup,
.cookie, .consent, .cookie-banner, .consent-modal {
  display: none !important;
  visibility: hidden !important;
}
body { overflow: auto !important; }
```

**Why this works:**

- Prevents modals from rendering visually
- Works across frameworks (React, Vue, vanilla)
- Survives A/B tests and dynamic content

### Button Clicking (Phase 3)

Tries common dismiss button selectors:

```typescript
const DISMISS_SELECTORS = [
  'button:has-text("Close")',
  'button:has-text("Dismiss")',
  'button:has-text("Got it")',
  'button:has-text("Accept All")',
  '[aria-label="Close"]',
  'button[aria-label*="close" i]',
  '#onetrust-accept-btn-handler',  // OneTrust consent
  '.btn-close',
  // ... and more
];
```

### DOM Removal (Phase 4)

As a last resort, removes overlay elements directly:

```typescript
// Target fixed/absolute positioned modals with high z-index
const overlaySelectors = [
  'div[class*="modal"][style*="position"]',
  'div[role="dialog"]',
  'div[aria-modal="true"]',
];
// Also removes backdrop elements
```

### Test Results

| District                    | Before                 | After                                        |
|-----------------------------|------------------------|----------------------------------------------|
| Davidson County (Nashville) | 32 lines (popup only)  | 316 lines (full content with bell schedules) |

The modal dismissal successfully captured Nashville's current school start times:

- High School: 7:05 AM - 2:05 PM
- Elementary: 8:00 AM - 3:00 PM
- Middle School: 8:55 AM - 3:55 PM

### Reference

Implementation based on recommendations from ChatGPT and Perplexity. See `docs/ChatGPT_and_Perplexity_advice_on_modals.md` for the full research notes.

---

## Learning Loop

### Pattern File: `data/config/crawlee_patterns.json`

```json
{
  "version": "1.0",
  "updated_at": "2026-01-26T12:00:00Z",
  "url_include_globs": [
    "**/bell*schedule*",
    "**/school*hours*",
    "**/daily*schedule*"
  ],
  "url_exclude_globs": [
    "**/news/**",
    "**/athletics/**",
    "**/bus*schedule*"
  ],
  "learned_positive": [],
  "learned_negative": []
}
```

### Learning Mechanics

**Automatic learning from Ollama scores:**
- URLs scoring > 0.8 that match no existing pattern → add to `learned_positive`
- URLs scoring < 0.2 that match no existing pattern → add to `learned_negative`

**User feedback loop:**
- User marks PDF as "valid bell schedule" → extract URL patterns, add to `learned_positive`
- User marks PDF as "not a bell schedule" → extract URL patterns, add to `learned_negative`

Crawlee reads `crawlee_patterns.json` at startup and applies globs to `enqueueLinks()`.

---

## Directory Structure

```
data/
├── config/
│   ├── crawlee_patterns.json       # Learning patterns
│   └── prompts/
│       ├── url_ranking.yaml        # Ollama prompt template
│       └── pdf_triage.yaml         # Ollama prompt template
│
└── raw/
    └── bell_schedule_pdfs/
        └── {state}/
            └── {district_id}_{district_name}/
                ├── active/         # Score ≥ 0.7
                ├── quarantine/     # Score 0.3-0.7
                ├── rejected/       # Score < 0.3
                └── metadata.json
```

**metadata.json example:**
```json
{
  "district_id": "1200390",
  "district_name": "Pasco County",
  "state": "FL",
  "website_url": "https://www.pasco.k12.fl.us",
  "acquisition_started": "2026-01-26T10:30:00Z",
  "acquisition_completed": "2026-01-26T10:35:00Z",
  "status": "triaged",
  "pages_mapped": 30,
  "urls_scored": 30,
  "pdfs_captured": 2,
  "capture_methods": {
    "google_drive": 0,
    "direct_download": 0,
    "crawlee_capture": 2
  },
  "triage_results": {
    "active": 1,
    "quarantine": 0,
    "rejected": 1
  }
}
```

---

## Key Files

| File | Purpose |
|------|---------|
| `infrastructure/api/routes/acquire.py` | Main acquisition pipeline |
| `infrastructure/api/routes/triage.py` | PDF triage endpoint |
| `infrastructure/api/routes/patterns.py` | Learning loop endpoints |
| `infrastructure/api/services/ollama_service.py` | Ollama integration |
| `infrastructure/api/services/patterns_service.py` | Semantic keyword learning |
| `infrastructure/api/services/crawlee_client.py` | HTTP client for Crawlee |
| `infrastructure/scraper/src/mapper.ts` | Crawlee website mapping |
| `infrastructure/scraper/src/capturer.ts` | PDF capture |
| `infrastructure/scripts/enrich/google_drive_handler.py` | Google Drive PDF handler |

---

## Usage

### Start Services

```bash
docker-compose up -d
```

### Acquire a District

```bash
curl -X POST http://localhost:8000/acquire/district/1200390 \
  -H "Content-Type: application/json" \
  -d '{
    "district_id": "1200390",
    "district_name": "Pasco County",
    "state": "FL",
    "website_url": "https://www.pasco.k12.fl.us"
  }'
```

### Check Status

```bash
curl http://localhost:8000/acquire/status/1200390
```

### Submit Feedback

```bash
curl -X POST http://localhost:8000/patterns/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/bell-schedule",
    "is_bell_schedule": true,
    "district_id": "1200390"
  }'
```

---

## Cost Estimation

| Component | Cost | Notes |
|-----------|------|-------|
| Crawlee mapping | $0 | Local compute |
| Ollama inference | $0 | Local compute |
| PDF capture | $0 | Local compute |
| Human review | Time | ~5 min per quarantine folder |

---

**Last Updated:** January 26, 2026
