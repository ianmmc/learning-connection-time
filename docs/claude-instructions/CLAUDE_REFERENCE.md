# CLAUDE_REFERENCE.md - Historical and Structural Information

Load this appendix when you need historical context, directory structure, or technical stack details.

---

## What's Been Completed

### Infrastructure Setup
- Complete directory structure (raw → processed → enriched → exports)
- Configuration files for data sources and state requirements
- Documentation framework

### Core Processing Scripts
| Stage | Script | Purpose |
|-------|--------|---------|
| Download | `fetch_nces_ccd.py` | Fetches NCES Common Core of Data |
| Enrich | `fetch_bell_schedules.py` | Bell schedules from district websites |
| Extract | `split_large_files.py` | Handles multi-part files |
| Extract | `extract_grade_level_enrollment.py` | K-12 enrollment by grade |
| Extract | `extract_grade_level_staffing.py` | Teacher counts with Option C allocation |
| Transform | `normalize_districts.py` | Standard schema normalization |
| Analyze | `calculate_lct.py` | LCT calculation with grade-level support |

### Data Optimization (Dec 2024)
- **Slim NCES Files**: 88% reduction (683 MB → 83 MB) in `data/processed/slim/`

### PostgreSQL Database (Dec 2025)
- PostgreSQL 16 via Homebrew
- SQLAlchemy ORM with declarative models
- Tables: districts (17,842), state_requirements (50), bell_schedules (214), lct_calculations, data_lineage

### Bell Schedule Scraper Service (Jan 2026)
- Location: `scraper/`
- Technology: Express.js + Playwright
- Features: Browser pool (5 concurrent), rate limiting, security block detection
- Ethical: respects blocks, no bypass attempts

### SEA Integration Test Framework (Jan 2026)
- Base class: `tests/test_sea_integration_base.py`
- 9 states: FL, TX, CA, NY, IL, MI, PA, VA, MA (375 tests passed)
- 8 test categories: DataLoading, Crosswalk, Staff, Enrollment, LCT, DataIntegrity, DataQuality, RegressionPrevention

### Master Crosswalk Table (Jan 2026)
- Migration 007: `state_district_crosswalk` table
- 17,842 entries for all districts

### Temporal Validation (Jan 2026)
- Migration 008: 3-year blending window rule
- Flags: WARN_YEAR_GAP, ERR_SPAN_EXCEEDED
- SPED baseline (2017-18) exempt

---

## Directory Structure

```
learning-connection-time/
├── config/                          # Configuration files
│   ├── data-sources.yaml
│   └── state-requirements.yaml
├── data/
│   ├── raw/                        # Source data (never modified)
│   │   ├── federal/nces-ccd/       # Common Core of Data
│   │   └── state/                  # State-specific data
│   ├── processed/                  # Cleaned and standardized
│   ├── enriched/                   # With calculated metrics
│   └── exports/                    # Final outputs
├── docs/
│   ├── claude-instructions/        # Modular briefing files
│   ├── chat-history/               # Session logs
│   └── data-dictionaries/          # Field definitions
├── infrastructure/
│   ├── database/                   # PostgreSQL infrastructure
│   │   ├── models.py              # SQLAlchemy ORM
│   │   ├── queries.py             # Query functions
│   │   └── migrations/            # Data migrations
│   ├── scripts/
│   │   ├── download/              # Data acquisition
│   │   ├── enrich/                # Bell schedule enrichment
│   │   ├── extract/               # Parsing
│   │   ├── transform/             # Normalization
│   │   └── analyze/               # Metric calculations
│   └── utilities/                 # Helper functions
├── scraper/                       # Bell schedule scraper service
│   ├── src/
│   │   ├── server.ts             # Express HTTP server
│   │   ├── scraper.ts            # Playwright scraper
│   │   └── pool.ts               # Browser pool
│   └── Dockerfile
├── tests/                         # Test suite
└── pipelines/                     # Automated workflows
```

---

## Technical Stack

### Core Dependencies
- **pandas**: Data manipulation
- **PyYAML**: Configuration files
- **requests**: Data downloads
- **pytest**: Testing

### Database Stack
- **PostgreSQL 16**: Primary data store
- **SQLAlchemy**: ORM with declarative models
- **psycopg2**: PostgreSQL adapter

### Scraper Stack
- **Node.js/TypeScript**: Runtime
- **Express.js**: HTTP server
- **Playwright**: Browser automation
- **p-queue**: Rate limiting

---

## Standard Schema

After normalization, all district data follows:

```python
{
    'district_id': str,           # Unique identifier
    'district_name': str,
    'state': str,                 # Two-letter code
    'enrollment': float,
    'instructional_staff': float,
    'year': str,                  # "2023-24"
    'data_source': str,           # "nces_ccd"
}
```

---

## Code Style & Conventions

### Python
- Python 3.11+
- PEP 8 style
- Type hints where helpful
- Logging instead of print statements

### File Naming
- Scripts: `kebab-case.py`
- Data: `name_YYYY_YY.csv`
- Generated: `name_YYYY_YY_YYYYMMDDTHHMMSSZ.csv`
- Docs: `CAPS_WITH_UNDERSCORES.md`

### Git
- Descriptive commit messages
- One logical change per commit
