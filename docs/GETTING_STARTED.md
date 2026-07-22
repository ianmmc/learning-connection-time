# Getting Started with Learning Connection Time

> **Authority:** dev setup, repo orientation, common tasks, conventions — how to get a fresh checkout
> running and find your way around, for a human or an AI agent.
> **Audience:** anyone completely new to this repo.
> **Companions:** `docs/PROJECT_CONTEXT.md` (the mission/story — read that for *why*, this doc for *how*),
> root `CLAUDE.md` (current build status + durable operating rules for AI sessions), `docs/TERMINOLOGY.md`
> (vocabulary — read first), `docs/ACQUISITION_PIPELINE.md` (the 9-stage pipeline map).
> **Update this when:** setup steps, repo layout, or conventions change — NOT for build progress, which
> lives in `CLAUDE.md` and GitHub Issues/Projects.

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
> capture layer. See `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md` §10.

### 1a. System dependencies (NOT pip-installable)

Stage 4 (Process) shells out to several **system binaries** that `requirements.txt` cannot
install — pip only covers the Python wrappers (`pdfplumber`, `camelot-py`). Without these, Stage 4
fails per-district with `FileNotFoundError` (the run isolates the district as `failed`, retriable,
rather than crashing — but no text is harvested). Stage 3 (Capture) additionally needs Node.

| Binary | Stage 4 use | macOS (brew) | Debian/Ubuntu (apt) |
|--------|-------------|--------------|---------------------|
| `pdftotext`, `pdftoppm` | Tier-1 text extract + rasterize-for-OCR | `poppler` | `poppler-utils` |
| `tesseract` | OCR (invoked directly, no `pytesseract`) | `tesseract` | `tesseract-ocr` |
| `gs` (ghostscript) | camelot's PDF backend | `ghostscript` | `ghostscript` |
| `node` | Stage 3 Playwright capture (`.mjs`) | `node` | see nodejs.org |

```bash
# macOS
brew install poppler tesseract ghostscript node

# Debian / Ubuntu
sudo apt-get install -y poppler-utils tesseract-ocr ghostscript nodejs

# Verify all are on PATH
for b in pdftotext pdftoppm tesseract gs node; do command -v "$b" || echo "MISSING: $b"; done
```

### 1b. Git hooks (one-time)

The repo ships a **tracked** pre-commit hook in `.githooks/`. Git can't auto-enable a hook on clone
(by design — security), so point git at it once:

```bash
git config core.hooksPath .githooks
```

What **pre-commit** does: (1) sweeps the **precious-state JSON backups** into every commit so they never
drift behind the governance DB — currently **nine** twins: `labels.json` (the `label` table),
`cluster_splits.json`, `followup_flags.json`, `district_status.json` (the `state_event` log), and the
gate@8 human-judgment set (`stage8_approvals.json`, `band_exclusions.json`, `human_added_facts.json`,
`slot_assignments.json`, `gate_modes.json`). All are written automatically on save/ingest; the hook
guarantees they reach version control, managed **symmetrically**. (`.githooks/pre-commit` is the source of
truth for the live list — it grows as precious tables are added.) (2) verifies any enrichment counts
in staged docs against the DB (Rule #6 — no hallucinated counts). Editing `.githooks/pre-commit` is the
single source of truth; a stale local `.git/hooks/pre-commit` is ignored once `core.hooksPath` is set.

The same `core.hooksPath` also activates a tracked **pre-push** hook (#202): before every push it runs the
CI-equivalent DB-free gates locally — `lint-imports` (the CI `lint` job) + `pytest -m "not integration"`
(the CI `test` job, ~5s, which already includes the #124 arch-manifest fitness tests) — so a preventable
red CI is caught at the desk instead of a round-trip. It does **not** run the govdb suite (that needs
Postgres; CI's `governance-db` job covers it). Bypass for a WIP/docs-only push with `SKIP_PREPUSH=1 git push`.

**Stacked PRs (#251):** a PR based on another PR's branch is fine *while the parent is open*, but its base
MUST be retargeted to `main` before merge — merging into the stale parent branch shows "merged" in every UI
while `main` receives nothing (the #250 incident). Two guardrails enforce this: the `pr-base-guard` CI check
stays red on any PR whose base isn't `main`, and the repo's *auto-delete head branches* setting makes GitHub
retarget child PRs to `main` automatically when the parent's branch is deleted at merge.

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
# Fast, resource-free suite (what CI's first job runs; ~1760 tests as of 2026-07-20 — check
# CLAUDE.md's resume-essentials for the live count, it grows with every merged PR)
pytest -q -m "not integration"

# Governance-DB suite (needs Docker Postgres up; CI's second job; ~296 tests as of 2026-07-20, same caveat)
pytest -q -m govdb

# Everything, verbose
pytest tests/ -v

# Integration tests only (network/system-dependent)
pytest tests/ -v -m integration
```

---

## Key Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](../CLAUDE.md) | Project briefing + current build status for Claude Code sessions |
| [README.md](../README.md) | Project overview and commands |
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | The mission, the reframe, the 6-phase evolution roadmap — the *story* |
| [METHODOLOGY.md](METHODOLOGY.md) | LCT calculation formulas, SPED segmentation, QA dashboard, data safeguards |
| [TERMINOLOGY.md](TERMINOLOGY.md) | Standardized vocabulary (read first!) |
| [DATABASE_SETUP.md](DATABASE_SETUP.md) | PostgreSQL schema and setup |
| [ACQUISITION_PIPELINE.md](ACQUISITION_PIPELINE.md) | The 9-stage bell-schedule acquisition pipeline map |
| [SEA_INTEGRATION_GUIDE.md](state-integrations/SEA_INTEGRATION_GUIDE.md) | State education agency data integration |
| [PROJECT_HISTORY.md](PROJECT_HISTORY.md) | Decision log — how the project got to where it is |

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

### The Node capture layer (`infrastructure/scraper`)

**Not a service** — there is no build step, no `npm start`, and nothing listening on a port. The retired
Crawlee+Ollama scraper *service* was archived 2026-06-25 (`data/archive/crawlee-ollama-era-superseded-20260625/`).
What lives here now is a flat set of Playwright `.mjs` modules (`capture_discovery.mjs` et al.) that the
**Python Stage-3 capture code invokes directly** — see `STAGE3_CAPTURE_DESIGN.md`.

```bash
cd infrastructure/scraper
npm install            # playwright is the only dependency
npm test               # node --test *.test.mjs (~86 tests as of 2026-07-20)
npm run lint:deps      # depcruise over the flat *.mjs (the Node side of the layering check)
```

These are the only two scripts `package.json` defines. Playwright also drives self-verification of console
UI changes (CLAUDE.md: the Python playwright isn't installed — drive this Node one).

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
- **File naming:** Python modules/scripts `snake_case.py` (0 of the 28 files under `infrastructure/scripts/`
  are hyphenated — this line said `kebab-case.py` until 2026-07-16, contradicting the whole codebase);
  Node capture modules `snake_case.mjs`; data `name_YYYY_YY.csv`; generated artifacts
  `name_YYYY_YY_<UTC-timestamp>.csv`; docs `CAPS_WITH_UNDERSCORES.md`.
- **Git:** conventional-commit messages, one logical change per commit.

---

## Current Build Status

Not tracked here — it changes too fast for a static doc to keep up. Root `CLAUDE.md` is the live-status
authority (what's built, what's running, what's next); day-to-day task tracking is in GitHub Issues/Projects.
For the pipeline architecture itself (stable, not status): `docs/ACQUISITION_PIPELINE.md` (the map),
`docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md` (governance/DB/gate model), and each
`docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md` (per-stage present state).

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
