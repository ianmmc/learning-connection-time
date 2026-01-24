# Learning Connection Time Analysis

> Transforming student-teacher ratios into tangible equity metrics

[![Status](https://img.shields.io/badge/status-active_development-green.svg)]()
[![Phase](https://img.shields.io/badge/phase-1.5_bell_schedule_enrichment-blue.svg)]()
[![Data Quality](https://img.shields.io/badge/data_quality-validated-brightgreen.svg)]()

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
- **[Operations Guide](docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md)** - Detailed procedures
- **[Quick Reference](docs/QUICK_REFERENCE_BELL_SCHEDULES.md)** - One-page cheat sheet
- **[Sampling Methodology](docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md)** - Collection approach

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

# 2. Test with sample data
python pipelines/full_pipeline.py --year 2023-24 --sample

# 3. View results
cat data/processed/normalized/districts_2023_24_nces_with_lct_summary.txt
```

### Check Current Campaign Progress
```bash
# Overall status
python infrastructure/scripts/enrich/enrichment_progress.py --campaign

# State-specific progress
python infrastructure/scripts/enrich/enrichment_progress.py --state WY
```

---

## 📊 Current Status (January 2026)

### Phase 1.5: Bell Schedule Enrichment Campaign

📖 **Terminology Guide:** See `docs/TERMINOLOGY.md` for standardized vocabulary
- **Automated enrichment** = Claude-collected via web scraping/PDF extraction
- **Human-provided** = User manually collected and placed in `manual_import_files/`
- **Actual bell schedules** = Real data from schools (counts as enriched ✓)
- **Statutory fallback** = State minimums only (does NOT count as enriched ✗)

**Current Dataset:**
- **Data Store:** PostgreSQL database (learning_connection_time)
- **Campaign Progress:** See [CLAUDE.md](CLAUDE.md#project-status) for current enrichment counts and milestones
- **State Campaigns:** Following Option A protocol (ranks 1-9, stop at 3 successful)

**Infrastructure Enhancements:**
- ✅ PostgreSQL database migration (Dec 2025)
- ✅ Docker containerization complete
- ✅ Layer 2 state integrations: California (Migration 003), Texas (Migration 005)
- ✅ SPED segmentation implemented (v3 self-contained focus)
- ✅ Data safeguards implemented (7 flags for quality validation)
- ✅ QA dashboard automation (auto-generated validation reports)
- ✅ Materialized views for fast queries (14K+ cached rows)
- ✅ Interactive enrichment tool (state campaign CLI)
- ✅ Data optimization complete (88% size reduction via slim files)
- ✅ Terminology standardized (docs/TERMINOLOGY.md)

**Recent Milestones:**
- ✅ Texas Layer 2 integration (Jan 2026)
  - NCES ↔ TEA crosswalk for 1,207 districts
  - ST_LEAID discovery (applies to all 50 states)
  - Infrastructure ready for PEIMS enhancement
  - See `TEXAS_INTEGRATION_COMPLETE.md` for details
- ✅ Self-contained SPED segmentation (Jan 2026)
  - Three LCT scopes: core_sped, teachers_gened, instructional_sped
  - See [SPED_SEGMENTATION_IMPLEMENTATION.md](docs/SPED_SEGMENTATION_IMPLEMENTATION.md) for methodology
  - Results in `data/enriched/lct-calculations/`
- ✅ Data quality safeguards (Jan 2026)
  - 7 validation flags for quality transparency
  - See [METHODOLOGY.md](docs/METHODOLOGY.md#data-safeguards) for details
- ✅ Efficiency Enhancement Suite (Dec 2025)
  - Interactive enrichment, Parquet export, incremental calculations

---

## 🛠️ Infrastructure

### Complete Processing Pipeline

**1. Download** - Acquire data
```bash
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24
```

**2. Enrich** - Gather actual bell schedules (optional)
```bash
# Manual enrichment via operations guide
# See: docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md
```

**3. Extract** - Handle multi-part files
```bash
python infrastructure/scripts/extract/split_large_files.py data/raw/federal/nces-ccd/2023_24/
```

**4. Transform** - Normalize to standard schema
```bash
python infrastructure/scripts/transform/normalize_districts.py input.csv --source nces --year 2023-24
```

**5. Analyze** - Calculate LCT metrics
```bash
python infrastructure/scripts/analyze/calculate_lct.py input.csv --summary --filter-invalid
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

### Optimization Tools (Dec 2024-Jan 2026)

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
│   ├── BELL_SCHEDULE_OPERATIONS_GUIDE.md  # Operational procedures ⭐
│   ├── QUICK_REFERENCE_BELL_SCHEDULES.md  # One-page cheat sheet
│   ├── METHODOLOGY.md                     # LCT calculation details
│   ├── OPTIMIZATION_IMPLEMENTATION_SUMMARY.md  # Recent improvements
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
**Three-tier methodology:**
- **Tier 1:** Detailed manual-assisted search (top districts)
- **Tier 2:** Automated search with fallback (districts 26-100)
- **Tier 3:** State statutory requirements (remaining districts)

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
1. ✅ **California** - DataQuest API, SPED environments, FRPM, LCFF funding (Migration 003)
2. ✅ **Texas** - NCES ↔ TEA crosswalk, ready for PEIMS enhancement (Migration 005)
3. 🔄 **Florida** - Next priority state
4. 🔄 **New York** - Next priority state

### Actual Bell Schedules (Campaign)
- Web scraping from district/school websites
- 182 districts enriched with actual data
- Campaign COMPLETE (50 U.S. states with ≥3 districts each)
- 546 bell schedule records (182 districts × 3 grade levels)

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

### Full Pipeline
```bash
# Complete pipeline with bell schedule enrichment
python pipelines/full_pipeline.py --year 2023-24 --enrich-bell-schedules --tier 2
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

1. **Read** `Claude.md` for complete project context
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
- **Session history:** See `docs/chat-history/` for development logs
- **Operations guide:** Complete procedures in `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md`

### Report Issues
Document in session handoff or create detailed notes in `docs/chat-history/`

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

### Current: Phase 1.5 (Bell Schedule Enrichment & SPED Segmentation)
- ✅ Infrastructure complete (database, optimizations, QA dashboard)
- ✅ State-by-state enrichment campaign COMPLETE (50 states with ≥3 districts)
- 🔄 SPED analysis and equity insights

### Future Phases
See [PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md#evolution-strategy) for complete evolution roadmap (Phases 2-6)

---

**Last Updated:** January 23, 2026
**Current Focus:** Bell schedule automation with multi-tier enrichment pipeline
**Project Status:** Active development with PostgreSQL database (17,842 districts), 9/9 SEA integrations complete (FL, TX, CA, NY, IL, MI, PA, VA, MA), Playwright scraper service operational, 789 tests passing
