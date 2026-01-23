# Multi-Tier Bell Schedule Enrichment Architecture

**Date:** January 22, 2026
**Status:** Design Complete - Implementation Next

---

## Overview

A cost-optimized, queue-based system for bell schedule enrichment that escalates through increasingly expensive tiers only when necessary.

## Tier Structure

### Tier 1: Local Discovery (Playwright)
**Purpose:** Find district websites and map individual school sites
**Cost:** Minimal (local compute only)
**Tools:** Crawlee + Playwright scraper service

**Tasks:**
- Fetch district homepage
- Discover individual school subsites (subdomain/path patterns)
- Test common URL patterns: `/bell-schedule`, `/daily-schedule`, `/information/bell-schedule`, `/about-*/bell-schedule`
- Identify CMS platform (Finalsite, SchoolBlocks, Blackboard, etc.)

**Success Criteria:**
- Homepage loads successfully
- School sites discovered (if applicable)
- Basic schedule URLs attempted

**Output:**
```json
{
  "tier": 1,
  "success": false,
  "district_url": "https://example.k12.state.us",
  "schools_found": [...],
  "urls_attempted": [...],
  "cms_detected": "finalsite",
  "content_type": "heavy_js",
  "escalation_reason": "bell_schedule_page_found_but_no_data_extracted"
}
```

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

**Success Criteria:**
- Start time extracted
- End time extracted
- Total minutes calculated OR source document identified (PDF/image)

**Escalation Triggers:**
- ✅ Schedule page found but data in PDF → Go to Tier 3 (PDF/OCR)
- ✅ Schedule page found but complex JS rendering → Go to Tier 4 (Claude API)
- ✅ No schedule page found but homepage accessible → Go to Tier 5 (Gemini search)

---

### Tier 3: Local PDF/OCR Extraction
**Purpose:** Extract bell schedules from PDF documents and images
**Cost:** Minimal (local compute only)
**Tools:** pdftotext, tesseract, ocrmypdf

**Tasks:**
- Download PDF (handle Google Drive links with `uc?export=download`)
- Extract text with pdftotext
- If text extraction fails, OCR with tesseract
- Parse extracted text for time patterns
- Handle common PDF layouts (tables, lists)

**Google Drive Handling:**
```bash
# Convert view link to download link
# From: https://drive.google.com/file/d/ABC123/view
# To:   https://drive.google.com/uc?export=download&id=ABC123
```

**Success Criteria:**
- Text extracted from PDF
- Time patterns identified
- Start/end times parsed

**Escalation Triggers:**
- ✅ PDF is scanned image with poor OCR results → Go to Tier 4 (Claude vision)
- ✅ PDF has complex table layout that can't be parsed → Go to Tier 4 (Claude API)

---

### Tier 4: Claude Desktop Processing (Batched)
**Purpose:** Complex extraction when confident data exists
**Cost:** Included in Claude subscription (no additional API costs)
**Tools:** Claude Code (this session) with full tool access

**Batch Composition Strategy:**
Group by processing characteristics for optimal shared context:

1. **JS-Heavy Sites Batch** (Finalsite, SchoolBlocks)
   - Share context about SPA extraction techniques
   - Common patterns across same CMS

2. **PDF Table Extraction Batch**
   - Share context about table parsing strategies
   - Common formatting patterns

3. **Complex HTML Batch** (nested tables, inconsistent markup)
   - Share context about DOM navigation strategies

**Batch Size:** 10-20 districts per batch

**Request Format:**
```json
{
  "batch_type": "pdf_table_extraction",
  "districts": [
    {
      "nces_id": "1234567",
      "name": "Example District",
      "url": "https://example.org/schedule.pdf",
      "content_type": "pdf",
      "tier_2_attempt": {
        "extracted_text": "... raw PDF text ...",
        "confidence": "low"
      }
    },
    // ... 9-19 more districts
  ],
  "shared_context": "These PDFs all use table-based bell schedule layouts..."
}
```

**Success Criteria:**
- Structured schedule data extracted
- Start/end times validated
- Confidence score ≥ 0.7

**Escalation Trigger:**
- ✅ Claude API fails or low confidence → Go to Tier 5 (Gemini search)

---

### Tier 5: Gemini Web Search (Batched)
**Purpose:** Find schedule URLs that we missed, alternative sources
**Cost:** Variable (MCP provider dependent - batched to reduce calls)
**Tools:** Gemini MCP with web search

**Batch Composition Strategy:**
Group by state and district size for geographic/contextual efficiency:

**Batch Size:** 10-20 districts per batch

**Request Format:**
```json
{
  "task": "web_search_bell_schedules",
  "districts": [
    {
      "nces_id": "1234567",
      "name": "Belgrade Elementary SD #44",
      "state": "MT",
      "district_url": "https://www.bsd44.org",
      "schools": [
        {"name": "Belgrade High School", "url": "https://hs.bsd44.org"},
        {"name": "Belgrade Middle School", "url": "https://ms.bsd44.org"}
      ],
      "tier_1_attempted_urls": [...]
    },
    // ... 9-19 more districts in same state
  ],
  "search_instructions": "For each district/school, search for bell schedules using terms: 'bell schedule', 'daily schedule', 'school hours', 'start time', 'dismissal time'. Return the URL and extracted schedule data."
}
```

**Success Criteria:**
- New schedule URLs discovered
- Schedule data extracted via Gemini's web navigation
- Source URL provided for verification

**Final Escalation:**
- ❌ Gemini also fails → Mark for manual review

---

## Queue System Architecture

### Database Schema Extension

```sql
-- Queue table for batched processing
CREATE TABLE enrichment_queue (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(10) REFERENCES districts(nces_id),
    current_tier INTEGER DEFAULT 1,
    tier_1_result JSONB,
    tier_2_result JSONB,
    tier_3_result JSONB,
    tier_4_result JSONB,
    tier_5_result JSONB,
    batch_id INTEGER,
    batch_type VARCHAR(50),
    queued_at TIMESTAMP DEFAULT NOW(),
    processing_started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending', -- pending, processing, completed, failed, manual_review
    escalation_reason TEXT,
    final_success BOOLEAN,
    notes TEXT
);

CREATE INDEX idx_queue_status ON enrichment_queue(status);
CREATE INDEX idx_queue_tier ON enrichment_queue(current_tier);
CREATE INDEX idx_queue_batch ON enrichment_queue(batch_id);
```

### Processing Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     Enrichment Queue                        │
│  Districts pending: 245 | In progress: 20 | Completed: 63   │
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
│ Tier 2: Local Extraction (Parsing)                          │
│ • Parse HTML for time patterns                              │
│ • Extract from tables                                       │
│ • Identify PDF/image links                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
           ┌──────────────────┴──────────────────┐
           │                                     │
        PDF Found                         No PDF, complex HTML
           │                                     │
           ↓                                     ↓
┌──────────────────────────┐      ┌────────────────────────────┐
│ Tier 3: PDF/OCR          │      │ Add to Tier 4 Batch Queue  │
│ • Download PDF           │      │ Group by CMS/content type  │
│ • Extract text           │      └────────────────────────────┘
│ • OCR if needed          │                   │
│ • Parse time patterns    │                   │
└──────────────────────────┘                   │
           │                                    │
           ↓                                    ↓
    Success? ──Yes─→ ✅                  Batch full (10-20)?
           │                                    │
          No                                   Yes
           │                                    ↓
           └─────────────→ Add to Tier 4 Batch Queue
                                                │
                                                ↓
┌─────────────────────────────────────────────────────────────┐
│ Tier 4: Claude API (Batched)                                │
│ • Process batch of 10-20 districts                          │
│ • Share context across similar extraction tasks             │
│ • Return structured data + confidence scores                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
           ┌──────────────────┴──────────────────┐
           │                                     │
    Confidence ≥ 0.7                      Confidence < 0.7
           │                                     │
           ↓                                     ↓
        ✅ Done                    Add to Tier 5 Batch Queue
                                                │
                                    Batch full (10-20)?
                                                │
                                               Yes
                                                ↓
┌─────────────────────────────────────────────────────────────┐
│ Tier 5: Gemini Web Search (Batched)                         │
│ • Process batch of 10-20 districts                          │
│ • Group by state for geographic context                     │
│ • Web search for missing schedule URLs                      │
│ • Extract data from discovered pages                        │
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
        ✅ Done                         ⚠️ Manual Review Queue
```

---

## Implementation Components

### 1. Queue Manager (`enrichment_queue_manager.py`)

```python
class EnrichmentQueueManager:
    """Manages the multi-tier enrichment queue"""

    def add_districts(self, district_ids: List[str]):
        """Add districts to queue at Tier 1"""

    def process_tier_1(self, batch_size: int = 50):
        """Process Tier 1 (local discovery) in parallel"""

    def process_tier_2(self, batch_size: int = 50):
        """Process Tier 2 (local extraction) in parallel"""

    def process_tier_3(self, batch_size: int = 20):
        """Process Tier 3 (PDF/OCR) in parallel"""

    def prepare_tier_4_batches(self) -> List[Batch]:
        """Group districts for Claude API batching"""

    def process_tier_4_batch(self, batch: Batch):
        """Send batch to Claude API"""

    def prepare_tier_5_batches(self) -> List[Batch]:
        """Group districts for Gemini web search batching"""

    def process_tier_5_batch(self, batch: Batch):
        """Send batch to Gemini MCP"""

    def get_status_summary(self) -> Dict:
        """Return queue status for monitoring"""
```

### 2. Batch Composer (`batch_composer.py`)

```python
class BatchComposer:
    """Intelligent batch composition for API efficiency"""

    def compose_claude_batches(
        self,
        districts: List[Dict],
        batch_size: int = 15
    ) -> List[Batch]:
        """
        Group districts by:
        1. CMS platform (Finalsite together, SchoolBlocks together)
        2. Content type (PDF tables, JS-heavy HTML, etc.)
        3. District size (similar enrollment ranges)
        """

    def compose_gemini_batches(
        self,
        districts: List[Dict],
        batch_size: int = 15
    ) -> List[Batch]:
        """
        Group districts by:
        1. State (geographic context)
        2. District size
        3. Previous tier results (similar failure patterns)
        """
```

### 3. Tier Processors

Each tier gets a dedicated processor module:

- `tier_1_processor.py` - Local discovery with Playwright
- `tier_2_processor.py` - Local HTML/pattern extraction
- `tier_3_processor.py` - PDF/OCR extraction
- `tier_4_processor.py` - Claude API batched requests
- `tier_5_processor.py` - Gemini MCP batched requests

---

## Reasonable Confidence Criteria

Escalate from Tier 2 → Tier 3 when:
- ✅ Found URL containing "bell-schedule" or "daily-schedule"
- ✅ Found link to PDF document
- ✅ Page title mentions "schedule" or "hours"

Escalate from Tier 2 → Tier 4 when:
- ✅ Found schedule page but data in complex table
- ✅ Heavy JS rendering detected (Finalsite, SchoolBlocks)
- ✅ Schedule visible to human but not extractable by parser

Escalate from Tier 3 → Tier 4 when:
- ✅ PDF extracted but table layout too complex
- ✅ OCR quality poor (scanned image PDF)
- ✅ Text extracted but no time patterns found

Escalate from Tier 4 → Tier 5 when:
- ✅ Claude API confidence score < 0.7
- ✅ Claude API failed to extract data
- ✅ No schedule page found in Tier 1/2

Send to Manual Review when:
- ❌ All tiers exhausted
- ❌ Gemini also failed
- ❌ Security block detected (Cloudflare)
- ❌ Website consistently times out

---

## Tracking & Logging

All attempts logged to `enrichment_attempts` table with:

```python
{
    "district_id": "1234567",
    "tier_reached": 5,
    "tier_succeeded": 5,
    "tier_1_result": {...},
    "tier_2_result": {...},
    "tier_3_result": {...},
    "tier_4_result": {...},
    "tier_5_result": {...},
    "total_cost_estimate": "$0.15",
    "processing_time_seconds": 45,
    "batch_id": "batch_20260122_001"
}
```

---

## Cost Estimation

Based on 245 districts from swarm run:

| Tier | Expected Success Rate | Districts | Cost per District | Total Cost |
|------|----------------------|-----------|-------------------|------------|
| Tier 1 | 10% | 25 | $0 | $0 |
| Tier 2 | 30% | 66 | $0 | $0 |
| Tier 3 | 20% | 44 | $0 | $0 |
| Tier 4 | 60% | 66 | $0.10 | $6.60 |
| Tier 5 | 80% | 44 | $0.05 | $2.20 |
| **Total** | **95%** | **233/245** | - | **$8.80** |

**Manual review:** ~12 districts (5%)

---

## Monitoring Dashboard

Real-time queue status:

```
┌─────────────────────────────────────────────────────────┐
│           Bell Schedule Enrichment Queue                │
├─────────────────────────────────────────────────────────┤
│ Total Districts: 245                                    │
│ ✅ Completed: 63 (25.7%)                                │
│ 🔄 Processing: 20 (8.2%)                                │
│ ⏳ Pending: 162 (66.1%)                                 │
│                                                         │
│ Tier Distribution:                                      │
│   Tier 1 (Local): 150 pending                          │
│   Tier 2 (Extract): 8 pending                          │
│   Tier 3 (PDF/OCR): 3 pending                          │
│   Tier 4 (Claude): 1 batch ready (12 districts)        │
│   Tier 5 (Gemini): 0 batches ready                     │
│                                                         │
│ Success Rate by Tier:                                   │
│   Tier 1: 12/150 (8.0%)                                │
│   Tier 2: 25/138 (18.1%)                               │
│   Tier 3: 15/113 (13.3%)                               │
│   Tier 4: 8/98 (8.2%)                                  │
│   Tier 5: 3/90 (3.3%)                                  │
│                                                         │
│ Estimated Cost: $8.80                                   │
│ Estimated Time: 4.5 hours                               │
└─────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Implement database schema** - Add `enrichment_queue` table
2. **Build queue manager** - Core orchestration logic
3. **Implement Tier 1-3 processors** - Local processing (no API costs)
4. **Test on 10 districts** - Validate tier escalation logic
5. **Implement batch composers** - Intelligent grouping for API efficiency
6. **Implement Tier 4 processor** - Claude API integration
7. **Implement Tier 5 processor** - Gemini MCP integration
8. **Full test on swarm candidates** - 14 school-level discovery districts
9. **Scale to full 245 district set** - Complete swarm results
10. **Monitor & optimize** - Adjust batch sizes, escalation criteria

---

**Status:** Ready for Implementation
**Priority:** High - Needed for large-scale bell schedule enrichment
