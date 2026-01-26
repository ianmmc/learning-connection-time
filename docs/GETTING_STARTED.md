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
```

### 2. Database Connection

The project uses PostgreSQL. Ensure you have access to the `learning_connection_time` database:

```bash
# Test connection (requires psql or use Python)
python3 -c "
from infrastructure.database.connection import session_scope
with session_scope() as session:
    print('Database connected successfully')
"
```

### 3. Run Tests

```bash
# Run all tests (789 tests)
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
├── REQUIREMENTS.yaml            # Tracked requirements with tests
├── data/
│   ├── raw/                     # Source data (never modify)
│   ├── processed/               # Cleaned and normalized
│   └── enriched/                # With calculated metrics
├── docs/
│   ├── claude-instructions/     # Modular Claude context files
│   └── archive/                 # Historical documentation
├── infrastructure/
│   ├── database/                # SQLAlchemy models, queries
│   ├── scripts/
│   │   ├── analyze/             # LCT calculations
│   │   ├── enrich/              # Bell schedule enrichment
│   │   └── transform/           # Data normalization
│   └── scraper/                 # Playwright scraper service (TypeScript)
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
cd scraper
npm install
npm start
# Service runs on http://localhost:3000
```

### Check Enrichment Status

```python
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import print_enrichment_report

with session_scope() as session:
    print_enrichment_report(session)
```

---

## Development Workflow

### Test-Driven Development

1. Check [REQUIREMENTS.yaml](../REQUIREMENTS.yaml) for existing requirements
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

---

## Current Status (January 2026)

- **Database:** 17,842 U.S. school districts
- **SEA Integrations:** 9/9 complete (FL, TX, CA, NY, IL, MI, PA, VA, MA)
- **Scraper Service:** Playwright-based, operational
- **Test Suite:** 789 tests passing
- **Phase:** Bell schedule acquisition with Crawlee + Ollama pipeline

---

## Getting Help

1. **Read TERMINOLOGY.md first** - Establishes shared vocabulary
2. **Check existing tests** - Examples of how modules work
3. **Review CLAUDE.md** - Current project context
4. **Look at docs/archive/** - Historical decisions and rationale

---

## Critical Rules

1. **Never modify `data/raw/`** - Source data is immutable
2. **COVID data exclusion** - Never use 2019-20 through 2022-23 data
3. **Security blocks** - ONE-attempt rule for Cloudflare/WAF-protected sites
4. **Temporal validation** - Data from multiple sources must span ≤3 years

---

**Last Updated:** January 26, 2026
