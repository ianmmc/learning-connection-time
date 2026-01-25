# Multi-Tier Bell Schedule Enrichment Architecture

**Date:** January 22, 2026
**Updated:** January 25, 2026
**Status:** Implementation Complete (Tier 5/Gemini Removed)

---

## Implementation Status

| Stage | Implementation | Key Code |
|-------|----------------|----------|
| Tier 1 | Firecrawl local discovery | `tier_1_processor.py` |
| Tier 2 | Playwright + Crawlee extraction | `tier_2_processor.py` |
| Tier 3 | PDF/OCR (pdftotext, tesseract) | `tier_3_processor.py` |
| Claude Review | Interactive Claude Code session | `tier_4_processor.py` |
| Manual Review | Human review (terminal state) | Queue status: `manual_review` |

**Note:** Tier 5 (Gemini MCP) was removed on 2026-01-25 due to unreliable results (~28-56% error rate on verifiable data). Districts that fail Claude Review now go directly to Manual Review.

**Additional Features:**
- **Staged mode:** Default processing completes each tier before advancing
- **Security blocking:** Districts with Cloudflare/WAF/403 are permanently blocked
- **Auto-testing:** Tests run automatically when queue clears

**Run Commands:**
```bash
# Run automated tiers (1-3)
python infrastructure/scripts/enrich/run_multi_tier_enrichment.py

# Prepare Claude Review batch
python infrastructure/scripts/enrich/run_multi_tier_enrichment.py --claude-review

# Process specific tier only
python infrastructure/scripts/enrich/run_multi_tier_enrichment.py --tier 1
```

---

## Overview

A cost-optimized, queue-based system for bell schedule enrichment that escalates through increasingly sophisticated methods only when necessary.

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     Enrichment Queue                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Tier 1: Local Discovery (Playwright)                        │
│ • Fetch homepage, discover schools                          │
│ • Try common URL patterns                                   │
│ • Detect CMS platform                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
                    Success? ────Yes──→ ✅ Done
                              │
                             No
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Tier 2: Local Extraction (HTML Parsing)                     │
│ • Parse HTML for time patterns                              │
│ • Extract from tables                                       │
│ • Identify PDF/image links                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
           ┌──────────────────┴──────────────────┐
           │                                     │
        PDF Found                         No PDF
           │                                     │
           ↓                                     ↓
┌──────────────────────────┐      ┌────────────────────────────┐
│ Tier 3: PDF/OCR          │      │ Escalate to Claude Review   │
│ • Download PDF           │      └────────────────────────────┘
│ • Extract text           │                   │
│ • OCR if needed          │                   │
│ • Parse time patterns    │                   │
└──────────────────────────┘                   │
           │                                    │
           ↓                                    │
    Success? ──Yes─→ ✅ Done                   │
           │                                    │
          No                                    │
           │                                    │
           └─────────────→ Claude Review Queue ←┘
                                   │
                                   ↓
┌─────────────────────────────────────────────────────────────┐
│ Claude Review (Interactive)                                 │
│ • User runs --claude-review to get batch                    │
│ • Claude Code processes with full tool access               │
│ • Uses WebFetch, Read, Bash to find schedules               │
│ • Calls record_schedule_from_session() to persist           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
                         Success?
                              │
           ┌──────────────────┴──────────────────┐
           │                                     │
          Yes                                   No
           │                                     │
           ↓                                     ↓
        ✅ Done                         ⚠️ Manual Review
```

---

## Tier Details

### Tier 1: Local Discovery (Playwright)
**Purpose:** Find district websites and map individual school sites
**Cost:** Minimal (local compute only)
**Tools:** Crawlee + Playwright scraper service

**Tasks:**
- Fetch district homepage
- Discover individual school subsites (subdomain/path patterns)
- Test common URL patterns: `/bell-schedule`, `/daily-schedule`, etc.
- Identify CMS platform (Finalsite, SchoolBlocks, Blackboard, etc.)

---

### Tier 2: Local Extraction (Playwright + Patterns)
**Purpose:** Extract bell schedules from HTML using known patterns
**Cost:** Minimal (local compute only)
**Tools:** Playwright, cheerio/jsdom, regex patterns

**Tasks:**
- Parse HTML for time patterns (HH:MM AM/PM)
- Extract from common table structures
- Check for embedded calendars/widgets
- Detect PDF/image schedule links

---

### Tier 3: Local PDF/OCR Extraction
**Purpose:** Extract bell schedules from PDF documents and images
**Cost:** Minimal (local compute only)
**Tools:** pdftotext, tesseract, ocrmypdf

**Tasks:**
- Download PDF (handle Google Drive links)
- Extract text with pdftotext
- If text extraction fails, OCR with tesseract
- Parse extracted text for time patterns

---

### Claude Review (Interactive Processing)
**Purpose:** Complex extraction with human oversight
**Cost:** $0 (included in Claude Max subscription)
**Tools:** Claude Code with full tool access (WebFetch, Read, Bash, etc.)

**Workflow:**
1. Run `python run_multi_tier_enrichment.py --claude-review`
2. Script outputs batch of pending districts
3. In Claude Code session, process each district
4. Use `record_schedule_from_session()` to save found data
5. Failed districts move to Manual Review

**Usage in Claude Code Session:**
```python
from infrastructure.scripts.enrich.tier_4_processor import Tier4Processor
from infrastructure.database.connection import session_scope

with session_scope() as session:
    processor = Tier4Processor(session)
    result = processor.record_schedule_from_session(
        district_id='0100005',
        schedules=[
            {'grade_level': 'elementary', 'start_time': '8:00 AM', 'end_time': '2:30 PM'},
            {'grade_level': 'middle', 'start_time': '8:30 AM', 'end_time': '3:30 PM'},
            {'grade_level': 'high', 'start_time': '7:30 AM', 'end_time': '2:30 PM'}
        ],
        source_url='https://district.org/schedules',
        notes='Found on district calendar page'
    )
    print(result)
```

---

### Manual Review (Terminal State)
**Purpose:** Human review for districts that all automated methods failed on
**Status:** `manual_review` in enrichment_queue

Districts reach Manual Review when:
- All automated tiers (1-3) failed
- Claude Review could not extract schedule
- Security block detected (Cloudflare, WAF, 403)
- Website consistently times out

---

## Queue System

### Database Schema

```sql
CREATE TABLE enrichment_queue (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(10) REFERENCES districts(nces_id),
    current_tier INTEGER DEFAULT 1,
    tier_1_result JSONB,
    tier_2_result JSONB,
    tier_3_result JSONB,
    tier_4_result JSONB,  -- Claude Review result
    status VARCHAR(20) DEFAULT 'pending',
    -- Status values: pending, processing, completed, manual_review
    escalation_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### Queue Manager Methods

```python
class EnrichmentQueueManager:
    def add_districts(district_ids: List[str])
    def process_tier_1_batch(batch_size: int)
    def process_tier_2_batch(batch_size: int)
    def process_tier_3_batch(batch_size: int)
    def prepare_claude_review_batches() -> List[Batch]
    def record_tier_success(district_id, tier, result)
    def record_tier_escalation(district_id, tier, result, reason)
    def record_manual_review(district_id, result, reason)
    def mark_permanently_blocked(district_id, tier, result, reason)
```

---

## Escalation Criteria

**Tier 1 → Tier 2:**
- Homepage accessible but no schedule found

**Tier 2 → Tier 3:**
- Found URL linking to PDF document

**Tier 2 → Claude Review:**
- Heavy JS rendering (Finalsite, SchoolBlocks)
- Schedule visible but not extractable

**Tier 3 → Claude Review:**
- PDF extracted but complex table layout
- OCR quality poor

**Claude Review → Manual Review:**
- All extraction attempts failed
- No schedule URLs discoverable

**Any Tier → Manual Review (Blocked):**
- Security block detected (Cloudflare, WAF, 403)
- Rate limiting
- CAPTCHA required

---

## Cost Estimation

| Stage | Cost | Notes |
|-------|------|-------|
| Tier 1-3 | $0 | Local compute only |
| Claude Review | $0 | Included in Claude Max subscription |
| Manual Review | Human time | ~5-10 min per district |

---

## Why Tier 5 (Gemini) Was Removed

On 2026-01-25, Tier 5 (Gemini MCP) was removed after verification revealed:
- **~28-56% error rate** on verifiable bell schedule data
- **Plausible hallucinations** - errors looked correct without verification
- **No source accountability** - unlike Perplexity, no citations provided

The Claude Review step with human oversight proved more reliable than fully automated Gemini queries.

---

**Status:** Production Ready
**Last Updated:** January 25, 2026
