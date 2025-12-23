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

## 📚 Essential Documentation

### For Developers
- **[Claude.md](Claude.md)** - Complete project briefing (comprehensive)
- **[.claude/SESSION_HANDOFF.md](.claude/SESSION_HANDOFF.md)** - Current session status
- **[Terminology Guide](docs/TERMINOLOGY.md)** - Standardized vocabulary ⭐ READ FIRST
- **[Infrastructure Scripts README](infrastructure/scripts/README.md)** - Script documentation

### For Bell Schedule Enrichment
- **[Operations Guide](docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md)** - Detailed procedures
- **[Quick Reference](docs/QUICK_REFERENCE_BELL_SCHEDULES.md)** - One-page cheat sheet
- **[Sampling Methodology](docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md)** - What to collect and why

### For Understanding the Analysis
- **[Methodology](docs/METHODOLOGY.md)** - LCT calculation approach and limitations
- **[Data Sources](docs/DATA_SOURCES.md)** - Data source catalog
- **[Project Context](docs/PROJECT_CONTEXT.md)** - Mission and strategy

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

## 📊 Current Status (December 2024)

### Phase 1.5: Bell Schedule Enrichment Campaign

📖 **Terminology Guide:** See `docs/TERMINOLOGY.md` for standardized vocabulary
- **Automated enrichment** = Claude-collected via web scraping/PDF extraction
- **Human-provided** = User manually collected and placed in `manual_import_files/`
- **Actual bell schedules** = Real data from schools (counts as enriched ✓)
- **Statutory fallback** = State minimums only (does NOT count as enriched ✗)

**Current Dataset (2023-24):**
- **Districts enriched:** 4/19,637 (0.02%)
- **Wyoming progress:** 4 districts with actual bell schedules
  - ✅ Natrona County SD #1 (automated)
  - ✅ Campbell County SD #1 (automated)
  - ✅ Sweetwater County SD #1 (human-provided)
  - ✅ Albany County SD #1 (human-provided)
  - ❌ Laramie County SD #1 (missing - needs investigation)
- **Manual follow-up:** 0 pending
- **Quality standard:** Statutory fallback NOT counted as enriched (135 files moved to tier3_statutory_fallback/)

**Legacy Dataset (2024-25):**
- **Preliminary collection:** 29 districts in `bell_schedules_manual_collection_2024_25.json`
- Top 25 largest districts + 4 user-selected districts
- Separate from current campaign tracking

**Optimization Status:**
- ✅ Data optimization complete (88% size reduction via slim files)
- ✅ Process optimization complete (2.15-4.25M token savings)
- ✅ Enrichment infrastructure ready (3x efficiency improvement)
- ✅ Terminology standardized (docs/TERMINOLOGY.md)
- ✅ Data quality cleanup (statutory fallback properly separated)

**Next Steps:**
- Resolve missing districts (Laramie County + 1 from 2024-25 collection)
- Clarify campaign direction (2023-24 state campaign vs 2024-25 expansion)
- Resume enrichment work with clear targets

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

### Optimization Tools (New - Dec 2024)

**Lightweight Enrichment Reference** (90% token reduction)
```bash
# Fast district lookup for enrichment
python3 << 'EOF'
import pandas as pd
df = pd.read_csv('data/processed/normalized/enrichment_reference.csv')
# Only 1.27 MB vs 4.2 MB, loads in 1-2K tokens vs 15-20K
EOF
```

**Smart District Filtering** (64% efficiency improvement)
```bash
# Filter to 6,952 high-quality candidates (from 19,502)
python infrastructure/scripts/enrich/filter_enrichment_candidates.py --stats
```

**Batch Enrichment** (checkpoint/resume capability)
```bash
# Process multiple districts with automatic checkpointing
python infrastructure/scripts/enrich/batch_enrich_bell_schedules.py --state WY --batch-size 10
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
- Automated filtering of invalid records (~2-3% filtered out)
- Validation reports for transparency
- Publication-ready datasets (`*_valid.csv` files)
- Manual follow-up tracking for challenging cases

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
- **Civil Rights Data Collection (CRDC)** - Biennial detailed data

### State Sources (Phased Rollout)
1. California - DataQuest API
2. Texas - PEIMS data
3. New York - NYSED data portal
4. Florida - Growing population, good reporting

### Actual Bell Schedules (Campaign)
- Web scraping from district/school websites
- 135 districts enriched with actual data
- Following state population order
- Target: 3 per state = ~153 districts

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

### Current: Phase 1.5 (Bell Schedule Enrichment)
- ✅ Infrastructure complete (90% token reduction)
- 🔄 Campaign in progress (135/~153 target)
- Next: Complete Wyoming, scale to Vermont and beyond

### Future Phases
- **Phase 2:** Add teacher quality weights
- **Phase 3:** Account for differentiated student needs
- **Phase 4:** Include interaction quality dimensions
- **Phase 5:** Opportunity-to-connect scores
- **Phase 6:** Outcome-validated connection time

---

**Last Updated:** December 21, 2024
**Current Focus:** Bell schedule enrichment campaign with optimized infrastructure
**Project Status:** Active development with 3x efficiency improvement
