# Getting Started with Learning Connection Time

> Quick onboarding guide for new contributors

## What This Project Does

Learning Connection Time (LCT) transforms abstract student-to-teacher ratios into tangible equity metrics:

```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Example:** 5,000 students, 250 teachers, 360 min/day → **18 minutes per student per day**

This reframes "20:1 ratio" into a metric that makes resource disparities visceral and understandable.

---

## Quick Setup (5 minutes)

### 1. Clone and Install

```bash
git clone <repository-url>
cd learning-connection-time

# Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install the repo as an editable package so `infrastructure.acquisition.*` (the
# acquisition pipeline) imports work from anywhere — required since REQ-098 removed
# the sys.path shims. One-time; re-run only if packages are added/moved.
pip install -e .
```

> **Architecture checks (optional, recommended in CI):** `lint-imports` enforces the
> acquisition layering contracts (pyproject.toml), `vulture infrastructure/acquisition`
> finds dead code, and `cd infrastructure/scraper && npm run lint:deps` checks the Node
> capture layer. See `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §10.

### 2. Database Connection

The project uses PostgreSQL running in Docker. Start the database container **before any database operation**:

```bash
# Start the PostgreSQL container (required first)
docker-compose up -d

# Test connection
python3 -c "
from infrastructure.database.connection import session_scope
with session_scope() as session:
    print('Database connected successfully')
"
```

> **Critical:** Never use `brew services start postgresql` — the `.env` is configured for Docker's PostgreSQL container.

The same container also hosts a **separate, isolated `governance` database** for the acquisition
pipeline's Stage-5 review/console state (REQ-103). It's distinct from the production LCT tables
(own DB + user) so the pipeline's drop+rebuild ingest can never touch them. One-time setup +
details: [DATABASE_SETUP.md → "Two databases"](DATABASE_SETUP.md#two-databases-production-lct-vs-governance-req-103).

### 3. Run Tests

```bash
# Run all tests (831 tests)
pytest tests/ -v

# Run quick smoke tests
pytest tests/ -v -x --ignore=tests/test_*_integration.py

# Run integration tests only
pytest tests/ -v -m integration
```

---

## Key Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](../CLAUDE.md) | Project briefing for Claude Code sessions |
| [README.md](../README.md) | Project overview and commands |
| [METHODOLOGY.md](METHODOLOGY.md) | LCT calculation formulas and data safeguards |
| [TERMINOLOGY.md](TERMINOLOGY.md) | Standardized vocabulary (read first!) |
| [DATABASE_SETUP.md](DATABASE_SETUP.md) | PostgreSQL schema and setup |
| [SEA_INTEGRATION_GUIDE.md](SEA_INTEGRATION_GUIDE.md) | State education agency data integration |

---

## Project Architecture

```
learning-connection-time/
├── CLAUDE.md                    # Claude Code project briefing
├── requirements.txt              # Python dependencies (pip install -r)
├── data/
│   ├── raw/                     # Source data (never modify)
│   ├── processed/               # Cleaned and normalized
│   └── enriched/                # With calculated metrics
├── docs/
│   ├── REQUIREMENTS.yaml        # Tracked project requirements with tests
│   ├── technical-notes/         # Per-stage design notes, governance/state model, research
│   └── archive/                 # Superseded documentation
├── infrastructure/
│   ├── acquisition/             # The bell-schedule acquisition pipeline (Stages 1-9; installable package)
│   ├── database/                # SQLAlchemy models, queries, migrations
│   ├── scripts/                 # LCT-core: analyze (LCT calc) / enrich / transform / download
│   └── scraper/                 # Stage-3 Playwright capture (Node .mjs)
└── tests/                       # pytest test suite
```

---

## Common Tasks

### Calculate LCT Metrics

```bash
python3 infrastructure/scripts/analyze/calculate_lct_variants.py
```

### Query Database

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import get_districts_by_state

with session_scope() as session:
    districts = get_districts_by_state(session, 'CA')
    print(f"Found {len(districts)} California districts")
```

### Run Scraper Service

```bash
cd infrastructure/scraper
npm install
npm run build   # compile TypeScript to dist/ (required before npm start)
npm start
# Service runs on http://localhost:3000

# Or run in watch mode without a build:
# npm run dev
```

### Check Enrichment Status

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import print_enrichment_report

with session_scope() as session:
    print_enrichment_report(session)
```

### Rebuild the LCT-core database from raw NCES sources

```bash
# Full-rebuild orchestrator (NCES import -> staff/enrollment -> SPED baseline -> LCT calc).
python3 infrastructure/scripts/rebuild_database.py --dry-run   # preview; drop --dry-run to run
python3 infrastructure/scripts/reset_database.py --force       # reset (preserves schema)
# Targeted imports live in infrastructure/database/migrations/ — see DATABASE_SETUP.md.
```

---

## Development Workflow

### Test-Driven Development

1. Check [REQUIREMENTS.yaml](REQUIREMENTS.yaml) for existing requirements
2. Write tests first in `tests/`
3. Implement the feature
4. Verify tests pass: `pytest tests/ -v`

### Before Committing

```bash
# Run tests
pytest tests/ -v

# Check for type errors (if applicable)
# mypy infrastructure/

# Commit with conventional format
git commit -m "feat: Add new bell schedule parser"
```

### Conventions

- **Python:** 3.11+ (3.13 in CI), PEP 8, type hints where they help, `logging` over `print` in library code.
- **File naming:** scripts `kebab-case.py`; data `name_YYYY_YY.csv`; generated artifacts
  `name_YYYY_YY_<UTC-timestamp>.csv`; docs `CAPS_WITH_UNDERSCORES.md`.
- **Git:** conventional-commit messages, one logical change per commit.

---

## Current Status (2026-06-12 — see root `CLAUDE.md` for the live 2026-06-22 picture)

> **Freshness:** snapshot below is 2026-06-12. Current state = building the per-school acquisition pipeline (gross bell-to-bell metric, council extraction, 3 human checkpoints; code at `infrastructure/acquisition/`); see root `CLAUDE.md` *Current Status* + `docs/ACQUISITION_PIPELINE.md`.

- **Database:** 17,842 U.S. school districts; 9/9 SEA integrations (FL, TX, CA, NY, IL, MI, PA, VA, MA)
- **Phase:** Bell-schedule **extraction-quality evaluation — benchmarked.** See `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.
- **Finding:** local extraction plateaus ~35–53% (plain-text 7B best local ~42%; Claude Haiku ~53%); **input/ground-truth quality is the main limiter, not the model.**
- **Direction:** format-aware reading + dual-path consensus (human review of disagreements) + better ground truth.
- **Acquisition:** Crawlee scraper + FastAPI; extractor TBD. Local Ollama models deleted post-benchmark (re-pullable). Headless Ubuntu server planned (`/Users/ianmmc/Development/ai-server-setup/`).

---

## Getting Help

1. **Read TERMINOLOGY.md first** - Establishes shared vocabulary
2. **Check existing tests** - Examples of how modules work
3. **Review CLAUDE.md** - Current project context
4. **Look at docs/PROJECT_HISTORY.md** - Key decisions and rationale

---

## Critical Rules

1. **Never modify `data/raw/`** - Source data is immutable
2. **COVID data exclusion** - Never use 2019-20 through 2022-23 data
3. **Security blocks** - ONE-attempt rule for Cloudflare/WAF-protected sites
4. **Temporal validation** - Data from multiple sources must span ≤3 years

---

**Last Updated:** June 12, 2026
