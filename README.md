# Learning Connection Time Analysis

> Transforming student-teacher ratios into tangible equity metrics

---

## 🎯 Project Mission

Transform abstract student-to-teacher ratios into tangible "Learning Connection Time" (LCT) metrics that tell the story of students getting shortchanged rather than teachers getting burdened.

**Formula:**
```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Example:**
- District: 5,000 students, 250 teachers, 360 min/day instruction
- **LCT = (360 × 250) / 5,000 = 18 minutes per student per day**

This reframes "20:1 student-teacher ratio" into a more visceral equity metric.

---

## 📚 Documentation Map

> **Note:** Documentation describes methodology (WHAT/HOW), not calculation results (which live in `data/enriched/lct-calculations/` and `outputs/`)

### Quick Reference
- **[CLAUDE.md](CLAUDE.md)** - Current project status, milestones, campaign progress (THE working document)
- **[TERMINOLOGY.md](docs/TERMINOLOGY.md)** - Standardized vocabulary ⭐ READ FIRST
- **This README** - Quick start and commands

### Methodology & Analysis (Canonical Sources)
- **[METHODOLOGY.md](docs/METHODOLOGY.md)** - LCT formulas, data safeguards, validation rules
- **[SPED_SEGMENTATION_IMPLEMENTATION.md](docs/SPED_SEGMENTATION_IMPLEMENTATION.md)** - SPED methodology (core_sped, teachers_gened, instructional_sped)
- **[DATA_SOURCES.md](docs/DATA_SOURCES.md)** - Data source details (NCES, CRDC, IDEA 618)
- **[PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md)** - Mission, evolution strategy (Phases 1-6)

### Operations & Infrastructure
- **[DATABASE_SETUP.md](docs/DATABASE_SETUP.md)** - PostgreSQL schema, queries, setup
- **[QA_DASHBOARD.md](docs/QA_DASHBOARD.md)** - Automated quality validation
- **[Infrastructure Scripts README](infrastructure/scripts/README.md)** - Script documentation

### Bell Schedule Enrichment
- **[Acquisition Pipeline](docs/ACQUISITION_PIPELINE.md)** ⭐ - Search-led discovery (waves) → tiered capture → cheap-cloud council extraction → modal aggregation. Target = **gross bell-to-bell** instructional minutes. (Supersedes the retired Crawlee+Ollama local-first design.)

### Where to Find Results
- **Current LCT values:** `data/enriched/lct-calculations/lct_all_variants_*.csv`
- **QA reports:** `data/enriched/lct-calculations/lct_qa_report_*.json`
- **Enrichment counts:** [CLAUDE.md](CLAUDE.md#project-status)
- **Data dictionary:** `docs/data-dictionaries/database_schema_latest.md`

---

## 🚀 Quick Start

### Setup
```bash
# 1. Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Start the database (Docker)
docker-compose up -d

# 3. Calculate LCT metrics from the database
python3 infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24
```

### Check Current Campaign Progress
```bash
# Overall status
python infrastructure/scripts/enrich/enrichment_progress.py --campaign

# State-specific progress
python infrastructure/scripts/enrich/enrichment_progress.py --state WY
```

---

## 🛠️ Infrastructure

### Complete Processing Pipeline

**1. Download** - Acquire data
```bash
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24
```

**2. Enrich** - Acquire actual bell schedules (optional)
```bash
# Search-led discovery + tiered capture + cheap-cloud council extraction (gross bell-to-bell)
# Orchestrated by the per-school-acquire skill. See: docs/ACQUISITION_PIPELINE.md
```

**3. Extract** - Handle multi-part files
```bash
python infrastructure/scripts/extract/split_large_files.py data/raw/federal/nces-ccd/2023_24/
```

**4. Transform** - Normalize to standard schema
```bash
python infrastructure/scripts/transform/normalize_districts.py input.csv --source nces --year 2023-24
```

**5. Analyze** - Calculate LCT metrics (DB-first)
```bash
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24
```

**6. Track Progress** - Monitor enrichment campaign
```bash
python infrastructure/scripts/enrich/enrichment_progress.py --campaign
```

### Database Operations (PostgreSQL)

**Check Database Status**
```bash
psql -d learning_connection_time -c "SELECT COUNT(*) FROM districts;"
```

**Re-import All Data**
```bash
python infrastructure/database/migrations/import_all_data.py
```

**Export to JSON** (for sharing/backup)
```bash
python infrastructure/database/export_json.py
```

**Query Enrichment Status**
```bash
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import print_enrichment_report
with session_scope() as session:
    print_enrichment_report(session)
"
```

**Refresh Materialized Views** (after data changes)
```bash
psql -d learning_connection_time -c "SELECT refresh_all_materialized_views();"
```

### Enrichment & Analysis Tools

**Interactive Bell Schedule Enrichment**
```bash
# State-by-state enrichment
python infrastructure/scripts/enrich/interactive_enrichment.py --state WI

# Specific district
python infrastructure/scripts/enrich/interactive_enrichment.py --district 5560580

# Check status
python infrastructure/scripts/enrich/interactive_enrichment.py --status
```

**Calculate LCT with QA Dashboard**
```bash
# All variants with quality validation
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24

# With Parquet export (70-80% size reduction)
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24 --parquet

# Incremental calculation (only changed districts)
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24 --incremental
```

**Generate Data Dictionary**
```bash
# Auto-generate from SQLAlchemy models
python infrastructure/scripts/utilities/generate_data_dictionary.py
```

---

## 📁 Project Structure

```
learning-connection-time/
├── data/                   # Data pipeline: raw → processed → enriched → exports
│   ├── raw/               # Source data (never modified)
│   ├── processed/         # Cleaned and standardized
│   │   ├── slim/         # Token-optimized files (88% smaller)
│   │   └── normalized/   # Standard schema
│   ├── enriched/          # With calculated metrics
│   │   ├── bell-schedules/     # Actual instructional time data
│   │   └── lct-calculations/   # Learning Connection Time metrics
│   └── exports/           # Final outputs
│
├── docs/                  # Documentation
│   ├── ACQUISITION_PIPELINE.md            # Search-led discovery + council extraction ⭐
│   ├── METHODOLOGY.md                     # LCT calculation details
│   ├── PROJECT_HISTORY.md                 # Decisions, lessons, system map & latent issues
│   ├── state-integrations/               # Per-state data integration plans
│   └── archive/          # Historical documentation
│
├── infrastructure/        # Data processing scripts
│   ├── scripts/
│   │   ├── download/     # Data acquisition
│   │   ├── enrich/       # Bell schedule enrichment (+ new tools)
│   │   ├── extract/      # Parsing and combining
│   │   ├── transform/    # Cleaning and normalization
│   │   └── analyze/      # Metric calculations
│   ├── utilities/        # Common functions
│   └── quality-assurance/tests/
│
├── pipelines/             # End-to-end workflows
├── outputs/               # Generated artifacts (reports, visualizations)
└── .claude/               # Claude Code configuration and handoff docs
```

---

## 🔧 Key Features

### ✅ Multi-Part File Handling
Automatically detects and concatenates split files:
- `filename_1.csv` + `filename_2.csv` → `filename_combined.csv`

### ✅ Actual vs. Statutory Instructional Time
**Minutes-source priority (highest to lowest):**
- **Actual bell schedule** — acquired from district/school websites via search-led discovery + cheap-cloud council extraction (gross bell-to-bell minutes)
- **State statutory requirement** — fallback when no schedule is found
- **Default (360 min)** — last-resort fallback

**Quality tracking:**
- Confidence levels: high, medium, low, assumed
- Source documentation for transparency
- Validation at every step

### ✅ Grade-Level Analysis
- Separate calculations for elementary, middle, and high school
- Accounts for different instructional time by level
- Option C staffing allocation (elementary direct, secondary proportional)

### ✅ Data Quality & Validation
- Automated filtering of invalid records
- 7 data safeguard flags (ERR and WARN categories)
- Validation reports for transparency
- Publication-ready datasets (`*_valid.csv` files)
- QA dashboard with auto-generated validation reports
- See [METHODOLOGY.md](docs/METHODOLOGY.md#data-safeguards) for complete safeguard definitions

### ✅ SPED Segmentation (v3 - Self-Contained Focus)
- Separates self-contained SPED from mainstreamed SPED students
- Three LCT scopes: core_sped (SPED teachers / self-contained), teachers_gened (GenEd teachers / GenEd enrollment), instructional_sped (SPED teachers + paras / self-contained)
- Two-step ratio estimation using state-level baselines (IDEA 618 + CRDC 2017-18)
- Audit validation passes (weighted average = overall LCT)
- See [SPED_SEGMENTATION_IMPLEMENTATION.md](docs/SPED_SEGMENTATION_IMPLEMENTATION.md) for full methodology and results

### ✅ Token-Optimized Infrastructure (New)
- **Slim files:** 88% size reduction for NCES data
- **Lightweight reference:** 90% token reduction per load
- **Smart filtering:** 64% fewer wasted attempts
- **Batch processing:** 3x efficiency improvement

---

## 📈 Data Sources

### Federal Sources
- **NCES Common Core of Data (CCD)** - Annual district data
  - Directory: District identification and characteristics
  - Membership: Student enrollment by grade
  - Staff: Teacher and staff FTE counts
- **Civil Rights Data Collection (CRDC)** - Biennial detailed data, LEA-level SPED enrollment
- **IDEA 618 Personnel & Environments** - State-level SPED teachers, paras, and educational environments (2017-18 baseline)

### State Sources (Layer 2 Integration)
State-specific data integrations provide enhanced detail beyond federal sources. See [CLAUDE.md](CLAUDE.md) for current integration status.

### Bell Schedules

Actual instructional time data collected via local-first web scraping from district websites. See [ACQUISITION_PIPELINE.md](docs/ACQUISITION_PIPELINE.md) for methodology.

---

## 🎓 Methodology Highlights

### Learning Connection Time Calculation
```python
# For each district
for level in ['elementary', 'middle', 'high']:
    instructional_minutes = get_actual_or_statutory(district, level)
    staff = get_level_staff(district, level)
    enrollment = get_level_enrollment(district, level)

    lct_minutes = (instructional_minutes * staff) / enrollment
    lct_hours = lct_minutes / 60
```

### Known Limitations
- **Individualization fallacy:** Assumes all time could be one-on-one
- **Time-as-quality assumption:** More time ≠ automatically better
- **Averaging deception:** District metrics mask within-district disparities

**See [METHODOLOGY.md](docs/METHODOLOGY.md) for complete details and evolution strategy.**

---

## 🔍 Usage Examples

### Bell Schedule Acquisition (local-first)
```bash
# Start the acquisition services (FastAPI :8000 + Crawlee :3000), then queue
# districts. Crawlee maps the site, Ollama ranks/triages, results are captured
# locally — no per-token API cost. Full workflow and endpoints:
#   docs/ACQUISITION_PIPELINE.md
```

### Campaign Progress Tracking
```bash
# Overall campaign dashboard
python infrastructure/scripts/enrich/enrichment_progress.py --campaign

# Next 20 districts to enrich
python infrastructure/scripts/enrich/enrichment_progress.py --next 20

# Export progress report
python infrastructure/scripts/enrich/enrichment_progress.py --export progress_report.txt
```

### Smart Candidate Selection
```bash
# Apply filtering to identify high-quality candidates
python infrastructure/scripts/enrich/filter_enrichment_candidates.py --stats

# Export top 500 candidates
python infrastructure/scripts/enrich/filter_enrichment_candidates.py --export candidates.csv --top-n 500
```

---

## 📝 Contributing

This project follows systematic development with comprehensive documentation:

1. **Read** `CLAUDE.md` for complete project context
2. **Follow** the operations guide for bell schedule enrichment
3. **Test** changes with sample data first
4. **Document** new features and decisions
5. **Update** session handoff when making significant changes

### Quality Standards
- Only actual bell schedules count as "enriched" (statutory fallback ≠ enriched)
- All data transformations must preserve lineage
- Validation at every pipeline stage
- Publication-ready datasets must exclude invalid records

---

## 📞 Support & Documentation

### Getting Help
- **Script documentation:** All scripts have `--help` flags
- **Project history:** See `docs/PROJECT_HISTORY.md` for key decisions & lessons
- **Acquisition guide:** Complete procedures in `docs/ACQUISITION_PIPELINE.md`

### Report Issues
Document issues in the relevant doc or as a new entry in `docs/PROJECT_HISTORY.md`

---

## 📜 License & Acknowledgments

**Project:** Learning Connection Time Analysis
**Initiative:** "Reducing the Ratio" educational equity initiative
**Mission:** Making resource disparities visceral and understandable

**Data Sources:**
- NCES Common Core of Data (public domain)
- State education agencies (varies by state)
- District/school websites (public information)

---

## 🎯 Roadmap

See [PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md#evolution-strategy) for the evolution roadmap and [CLAUDE.md](CLAUDE.md) for current project status.
