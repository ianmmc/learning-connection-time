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

## Current Status (2026-06-13)

Phase 1.5 pipeline **validated end-to-end** (extraction *and* discovery). Full learnings: `docs/technical-notes/EXTRACTION_AND_DISCOVERY_LEARNINGS_2026-06.md`; leaderboards: `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.

**Extraction — a capable cloud model ~doubles the best local; cheap wins.** Full-41 leader **Gemini 2.5 Flash 68.9%** (cheapest *and* best); Mistral Large/Qwen3.7-Max 67.6%; DeepSeek V3.2 66.2%; **Mistral Small 24B 63.5% (~$0.05/1M)**; **Granite 4.1 8B 51.4%** (tiny, self-hostable). Bigger ≠ better (DeepSeek V4-Pro, GPT-5.5, Opus trail cheaper models). The old "~35–53% / no silver bullet" framing was an artifact of testing only Haiku on 5 districts.

**The ceiling is INPUT quality, not the model.** 20% of districts are solved by zero models, but on *good* inputs (difficulty > 0.70) the top models hit **~95–100%**. Hard inputs failed on **granularity/noise (giant multi-school dumps, single-band GT), NOT OCR** — 22/23 already had the schedule as text. **#1 lever: per-school targeting** (small, focused, current, single-schedule artifacts).

**Discovery — search-led works.** Domain-scoped search (Perplexity `search_domain_filter` / OpenRouter `gpt-4o-mini-search` `site:` / Claude WebSearch `allowed_domains`) eliminates the wrong-district problem and reaches school subdomains. **Blind Crawlee crawling fails**; Crawlee is re-cast as a **terrain-mapper / one-hop off-site fetcher**. **Google grounding dropped** (no site-restriction). New bottleneck = capture fidelity on JS pages → **tiered capture** (text-layer preferred; screenshot+OCR/vision fallback). Relevance gate = cheap `pdftotext` sniff; pdfplumber/vision is the extraction stage.

**Direction / architecture:** per-school targeting → tiered capture → cheap-cloud **council** consensus (Gemini 2.5 Flash + a cross-family model: DeepSeek V3.2 / Mistral; cheap members Flash-Lite, Mistral Medium 3.1) → fail-loud **statutory fallback**. Multi-model conduits `pplx:` / `openrouter:` wired in `extractors.py`. Requirements: **REQ-043…053**. Keys in gitignored `config/secrets.local.json` + `.env`.

**Notes:** Local Ollama models were **deleted** (re-pullable); paid-cloud extraction is *cheap* (~$0.05–0.30/1M) and far more accurate, so the local-first premise no longer binds. Headless Ubuntu AI server (old 2017 MBP) planned for self-hosted work — **Granite 4.1 8B** is the local-model candidate; briefing at `/Users/ianmmc/Development/ai-server-setup/SETUP_BRIEFING.md` (separate project).

> **SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition path. See `docs/INSTRUCTIONAL_TIME_HARVEST.md`.

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
| **Benchmark harness** | `infrastructure/acquisition/` |
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
