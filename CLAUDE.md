# Claude Code Project Briefing: Learning Connection Time

## Project Mission

Transform student-to-teacher ratios into "Learning Connection Time" (LCT) metrics that tell the story of students getting shortchanged.

**Core Formula:**
```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Example:** 5,000 students, 250 teachers, 360 min/day → LCT = 18 min/student/day

**Goal:** Analyze data from the largest U.S. school districts to identify educational equity disparities.

---

## Project Context

Part of "Reducing the Ratio" educational equity initiative. Currently implementing **Phase 1.5**: enriching basic LCT with actual bell schedules from district websites.

**Known Limitations:** Individualization fallacy, time-as-quality assumption, averaging deception. See `docs/METHODOLOGY.md`.

---

## Current Status (2026-06-12)

Bell-schedule **extraction quality** — the open problem for Phase 1.5 — has been benchmarked. Full results: `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.

**Conclusion: no silver bullet — extraction plateaus ~35–53%** on the grade-band modal-minutes metric:
- **Plain text on a 7B model (mistral/qwen2.5) is the best *local* approach (~42%)**; vision (qwen2.5-VL) and table-aware (pdfplumber) did NOT beat it on aggregate (table-aware is more *precise* when it hits; vision locks onto early-release columns).
- A capable cloud model (**Claude Haiku ~53%**) edges the locals — modest, not production-ready.
- Much of the gap is **input/ground-truth quality** (corrupt source PDFs, HTML schedules not in parseable tables, transposed tables, single-band GT) — *not* the model.

**Direction:** format-aware reading (table-aware for digital PDFs, OCR/vision for images, targeted HTML) + **dual-path consensus with human review of disagreements** + better multi-band ground truth. Benchmark harness lives in `infrastructure/scripts/benchmark/`.

**Notes:** Local Ollama models were **deleted** after the benchmark (all re-pullable; none met the bar). A headless Ubuntu AI server (the old 2017 MBP) is planned to host heavy/unattended work — briefing at `/Users/ianmmc/Development/ai-server-setup/SETUP_BRIEFING.md` (separate project). Ollama gotchas: use the official binary (Homebrew build was missing `llama-server`); bake `num_ctx` into a Modelfile for VLMs; throttle local inference with `taskpolicy -b` + run in `tmux`.

> **SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory minimums / day-counts, not actual daily minutes. Web-scraping district bell schedules remains the primary acquisition path. See `docs/INSTRUCTIONAL_TIME_HARVEST.md`.

---

## Current Data Years

**Current School Year:** 2025-26

### Data Year Strategy

| Data Type | Year | Notes |
|-----------|------|-------|
| Primary dataset | 2023-24 | NCES CCD enrollment/staffing |
| Bell schedules | 2025-26, 2024-25, 2023-24 | Any acceptable, search current first |
| COVID exclusion | 2019-20 through 2022-23 | Never use - abnormal schedules |

**Search Order:** 2025-26 → 2024-25 → 2023-24 (all post-COVID, interchangeable)


---

## Database Quick Reference

```bash
# Bell schedule count (source of truth)
python3 -c "
from infrastructure.database.connection import session_scope
from sqlalchemy import text
with session_scope() as s:
    print(s.execute(text('SELECT COUNT(DISTINCT district_id) FROM bell_schedules')).scalar())
"

# Query enrichment status
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import print_enrichment_report
with session_scope() as session:
    print_enrichment_report(session)
"
```

**Key Tables:** `districts`, `bell_schedules`, `state_requirements`, `lct_calculations`, `state_district_crosswalk`

---

## Essential Commands

```bash
# Calculate LCT (recommended)
python3 infrastructure/scripts/analyze/calculate_lct_variants.py

# Interactive enrichment
python3 infrastructure/scripts/enrich/interactive_enrichment.py --state WI

# Run SEA integration tests
pytest tests/test_*_integration.py -v

# VERIFICATION - Run after enrichment!
python3 infrastructure/scripts/verify_enrichment.py --quick
```

---

## Key Files

| Task | File |
|------|------|
| **Extraction benchmark findings** | `docs/EXTRACTION_BENCHMARK_FINDINGS.md` |
| **Benchmark harness** | `infrastructure/scripts/benchmark/` |
| Decisions & lessons (history) | `docs/PROJECT_HISTORY.md` |
| Architecture map & flagged issues | `docs/PROJECT_SYNTHESIS.md` |
| Bell schedule acquisition | `docs/ACQUISITION_PIPELINE.md` |
| Data methodology | `docs/METHODOLOGY.md` |
| Database setup | `docs/DATABASE_SETUP.md` |
| SEA integration guide | `docs/SEA_INTEGRATION_GUIDE.md` |
| LCT calculation | `infrastructure/scripts/analyze/calculate_lct_variants.py` |
| Database migrations + ledger | `infrastructure/database/migrations/` (`migrate.py status`) |
| Database queries | `infrastructure/database/queries.py` |

---

## Load Additional Context When Needed

This is the core briefing (~115 lines). For detailed information, load these appendices:

| Context Needed | Load File |
|----------------|-----------|
| Historical progress, directory structure, technical stack | `docs/claude-instructions/CLAUDE_REFERENCE.md` |
| Development workflow, testing, common commands | `docs/claude-instructions/CLAUDE_WORKFLOWS.md` |
| Data architecture, SEA integrations, crosswalks | `docs/claude-instructions/CLAUDE_DATA.md` |

**Token Efficiency:** Only load appendices relevant to the current task. This modular structure reduces context consumption by ~80% compared to the previous monolithic file.

---

## Critical Rules

1. **Docker Required**: Always use `docker-compose up -d` before database operations. Never use `brew services start postgresql` - the `.env` is configured for Docker's PostgreSQL container.
2. **COVID Data Exclusion**: Never use 2019-20 through 2022-23 data
3. **Security Blocks**: ONE-attempt rule for Cloudflare/WAF-protected districts
4. **Temporal Validation**: Data from multiple sources must span ≤3 years
5. **Raw Data**: Never modify files in `data/raw/`
6. **Data Verification**: ALWAYS verify data exists in database before claiming enrichment counts. Never trust handoff documentation without database verification.

---

## Technical Reference

- **Crosswalk table**: `state_district_crosswalk` - single source of truth for all state mappings
- **SPED baseline**: 2017-18 IDEA 618/CRDC exempt from temporal rule
- **Acquisition API**: FastAPI (port 8000) + Crawlee (port 3000)
- **Bell schedule pipeline**: Crawlee mapping → Ollama ranking → PDF capture → Ollama triage

For detailed reference, load the appropriate appendix above.
