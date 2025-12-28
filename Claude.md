# Claude Code Project Briefing: Instructional Minute Metric

## Project Mission

Transform abstract student-to-teacher ratios into tangible "Learning Connection Time" (LCT) metrics that tell the story of students getting shortchanged rather than teachers getting burdened.

**Core Formula:**
```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Example:** A district with 5,000 students, 250 teachers, and 360 minutes/day of instruction:
- LCT = (360 × 250) / 5000 = **18 minutes per student per day**
- This reframes "20:1 student-teacher ratio" into a more tangible equity metric

**Goal:** Analyze data from the top 100-200 largest U.S. school districts to identify and communicate educational equity disparities.

---

## Project Context

### The "Reducing the Ratio" Initiative
This is part of a larger educational equity initiative. The LCT metric is designed to be a powerful rhetorical tool for policy discussions by making resource disparities visceral and understandable.

### Current Understanding of Limitations
We acknowledge the metric has methodological challenges:
- **Individualization fallacy**: Assumes all time could be one-on-one
- **Time-as-quality assumption**: More time ≠ automatically better
- **Averaging deception**: District metrics mask within-district disparities

### Evolution Strategy (6 Phases)
1. **Phase 1**: Basic LCT using state statutory requirements
2. **Phase 1.5 (Current)**: Enrich with actual bell schedules where available
3. **Phase 2**: Add teacher quality weights
4. **Phase 3**: Account for differentiated student needs
5. **Phase 4**: Include interaction quality dimensions
6. **Phase 5**: Opportunity-to-connect scores
7. **Phase 6**: Outcome-validated connection time

We're implementing Phase 1.5, which enhances basic LCT calculations with actual instructional time data from bell schedules rather than relying solely on state statutory minimums.

---

## Important: Current Date and Data Years

**Current Date:** December 21, 2025
**Current School Year:** 2025-26 (Fall 2025 - Spring 2026)

### Data Year Strategy

**For Historical Datasets:**
- **Primary campaign dataset:** 2023-24 (NCES CCD data, enrollment/staffing)
- **Legacy collection:** 2024-25 (preliminary bell schedule work)
- Federal and state datasets are typically 1-2 years behind current year

**For Bell Schedule Web Searches - Year Preference Order:**
1. **2025-26** (current year - most likely posted on websites)
2. **2024-25** (recent year - still commonly available, preferred over 2023-24)
3. **2023-24** (acceptable - matches primary dataset year)

Schools typically post current and recent year schedules. All three years (2025-26, 2024-25, 2023-24) represent normalized post-COVID operations and can be used interchangeably as proxies for instructional time.

**Example Search Queries:**
- ✅ "District Name bell schedule 2025-26" (try first - current year)
- ✅ "District Name daily schedule school day 2025-26" (alternative terms)
- ✅ "District Name start end times dismissal arrival 2025-26" (time-focused)
- ✅ "District Name bell schedule 2024-25" (fallback to prior year)
- ✅ "District Name bell schedule 2023-24" (last resort - acceptable)

**Effective Search Terms:**
Districts use varying terminology. Include multiple terms to maximize discovery:
- **Schedule terms:** "bell schedule", "daily schedule", "school day"
- **Time terms:** "start time", "end time", "dismissal time", "arrival time", "dismissal", "start", "end"
- **Combined:** Use multiple terms in one search for better results

**CRITICAL: COVID-Era Data Exclusion**
**❌ DO NOT USE data from these school years:**
- **2019-20** (COVID-19 shutdowns began March 2020)
- **2020-21** (Remote/hybrid learning, abnormal schedules)
- **2021-22** (Continued disruptions and transitions)
- **2022-23** (Transitional year, still recovering)

These years do not represent typical instructional time due to pandemic disruptions. If data from 2023-24 and later is unavailable, prefer **2018-19** (pre-COVID) over any COVID-era year.

**Rationale:** Bell schedules are generally stable across years under normal operations. Using recent schedules (2025-26, 2024-25, or 2023-24) as a proxy for 2023-24 instructional time is methodologically sound, while COVID-era schedules would introduce systematic bias toward artificially reduced instructional time.

---

## What's Been Completed

### ✅ Infrastructure Setup
- Complete directory structure created
- All subdirectories organized by data flow: raw → processed → enriched → exports
- Configuration files for data sources and state requirements
- Documentation framework established

### ✅ Core Processing Scripts
1. **Download**: `infrastructure/scripts/download/fetch_nces_ccd.py`
   - Fetches NCES Common Core of Data
   - Supports sample data generation for testing

2. **Enrich**: `infrastructure/scripts/enrich/fetch_bell_schedules.py` ⭐ NEW
   - Fetches actual bell schedules from district/school websites
   - Three-tier methodology (detailed, automated, statutory)
   - Tracks data quality and sources
   - Optional enrichment step in pipeline
   - **Security Block Protocol**: ONE-attempt rule for Cloudflare/WAF-protected districts
     - Try ONE search + ONE fetch, then immediately add to manual follow-up if blocked
     - Respects district cybersecurity, conserves resources
     - See `docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md` for details

3. **Extract**:
   - `split_large_files.py` - Handles multi-part files (filename_1, filename_2, etc.)
   - `extract_grade_level_enrollment.py` ⭐ NEW - Extracts K-12 enrollment by grade from NCES CCD
   - `extract_grade_level_staffing.py` ⭐ NEW - Extracts teacher counts with Option C allocation (elementary direct, secondary proportional split)

4. **Transform**: `infrastructure/scripts/transform/normalize_districts.py`
   - Normalizes data from various sources to standard schema
   - Supports both federal (NCES) and state-specific formats
   - Merges grade-level enrollment and staffing data

5. **Analyze**: `infrastructure/scripts/analyze/calculate_lct.py`
   - Implements LCT calculation with grade-level support
   - Validates data quality and filters invalid districts
   - Generates derived metrics and percentiles
   - Produces summary statistics and validation reports
   - Creates publication-ready filtered outputs

### ✅ Data Optimization (December 2024) ⭐ NEW
- **Slim NCES Files**: Token-efficient versions in `data/processed/slim/`
  - 88% file size reduction (683 MB → 83 MB)
  - Directory slim: 0.7 MB (was 7.7 MB)
  - Enrollment slim: 81 MB (was 618 MB)
  - Staff slim: 1.1 MB (was 57 MB)
- **Impact**: 88% reduction in token usage for file I/O operations
- **Preserves**: All original raw files in `data/raw/` for future needs
- **Scripts updated**: Extraction scripts document slim file usage

### ✅ PostgreSQL Database Infrastructure (December 2025) ⭐ NEW
- **Database**: PostgreSQL 16 (via Homebrew)
- **ORM**: SQLAlchemy with declarative models
- **Tables**: districts (17,842), state_requirements (50), bell_schedules (214), lct_calculations, data_lineage
- **Benefits**:
  - Query specific data vs. loading entire files (token efficiency)
  - Data integrity constraints (foreign keys, check constraints)
  - JSONB for flexible nested data (schools_sampled, source_urls)
  - Same engine locally and in production (Supabase-ready)
- **Location**: `infrastructure/database/`
- **Setup**: See `docs/DATABASE_SETUP.md`

### ✅ Supporting Infrastructure
- **Utilities**: `infrastructure/utilities/common.py` - Shared functions for state standardization, safe math, validation
- **Pipeline**: `pipelines/full_pipeline.py` - End-to-end orchestration
- **Tests**: `infrastructure/quality-assurance/tests/test_utilities.py` - Unit tests
- **Documentation**: Comprehensive README in scripts directory

### ✅ Configuration Files
- `config/data-sources.yaml` - Data source definitions
- `config/state-requirements.yaml` - State instructional time requirements (240-420 min range)
- `requirements.txt` - Python dependencies

### ✅ Documentation
- `README.md` - Project overview
- `docs/PROJECT_CONTEXT.md` - Mission and background
- `docs/DATA_SOURCES.md` - Data source catalog
- `docs/METHODOLOGY.md` - Calculation methodology and limitations
- `docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md` - Bell schedule collection methodology
- `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md` - ⭐ Operational procedures, tools, and troubleshooting
- `docs/DATABASE_SETUP.md` - ⭐ PostgreSQL setup, materialized views, and query utilities (Dec 2025)
- `docs/DATABASE_MIGRATION_NOTES.md` - ⭐ Migration working notes
- `docs/QA_DASHBOARD.md` - ⭐ NEW Automated quality validation and reporting (Dec 2025)
- `docs/data-dictionaries/database_schema_latest.md` - ⭐ NEW Auto-generated schema docs (Dec 2025)

---

## Directory Structure

```
learning-connection-time/
├── config/                          # Configuration files
│   ├── data-sources.yaml
│   └── state-requirements.yaml
│
├── data/                            # All datasets
│   ├── raw/                        # Source data (never modified)
│   │   ├── federal/
│   │   │   ├── nces-ccd/          # Common Core of Data by year
│   │   │   ├── crdc/              # Civil Rights Data Collection
│   │   │   └── metadata/
│   │   └── state/                  # State-specific data
│   │       ├── california/
│   │       ├── texas/
│   │       ├── new-york/
│   │       └── florida/
│   │
│   ├── processed/                  # Cleaned and standardized
│   │   ├── normalized/            # Standard schema
│   │   ├── merged/                # Combined datasets
│   │   └── validated/             # Quality-checked
│   │
│   ├── enriched/                   # With calculated metrics
│   │   ├── lct-calculations/
│   │   ├── district-profiles/
│   │   └── comparative-analysis/
│   │
│   └── exports/                    # Final outputs
│       ├── csv/
│       ├── json/
│       └── reports/
│
├── docs/
│   ├── PROJECT_CONTEXT.md         # Mission, strategy, evolution plan
│   ├── DATA_SOURCES.md            # Where to get data
│   ├── METHODOLOGY.md             # How LCT is calculated
│   ├── chat-history/              # Development session logs
│   ├── data-dictionaries/         # Field definitions
│   └── analysis-reports/          # Research findings
│
├── infrastructure/
│   ├── database/                  # PostgreSQL infrastructure ⭐
│   │   ├── schema.sql            # Database DDL
│   │   ├── models.py             # SQLAlchemy ORM models (with CalculationRun ⭐ NEW)
│   │   ├── connection.py         # Connection utilities
│   │   ├── queries.py            # High-level query functions (extended Dec 2025 ⭐)
│   │   ├── export_json.py        # JSON export utility
│   │   └── migrations/           # Data migration scripts
│   │       ├── create_materialized_views.sql  # ⭐ NEW (Dec 2025)
│   │       └── import_all_data.py
│   ├── scripts/
│   │   ├── download/              # Data acquisition
│   │   ├── enrich/                # Data enrichment (bell schedules)
│   │   │   ├── fetch_bell_schedules.py
│   │   │   └── interactive_enrichment.py  # ⭐ NEW (Dec 2025)
│   │   ├── extract/               # Parsing and combining
│   │   ├── transform/             # Cleaning and normalization
│   │   ├── analyze/               # Metric calculations
│   │   │   ├── calculate_lct.py
│   │   │   └── calculate_lct_variants.py  # ⭐ NEW (Dec 2025, QA dashboard)
│   │   └── utilities/             # Helper functions
│   │       └── generate_data_dictionary.py  # ⭐ NEW (Dec 2025)
│   ├── quality-assurance/tests/   # Test suite
│   └── utilities/                 # Helper functions (common.py)
│
├── notebooks/                      # Jupyter for exploration
│   ├── exploratory/
│   ├── validation/
│   └── visualization/
│
├── pipelines/                      # Automated workflows
│   └── full_pipeline.py
│
├── outputs/                        # Generated artifacts
│   ├── visualizations/
│   ├── reports/
│   └── datasets/
│
└── src/                           # Core library code
    ├── python/
    │   ├── calculators/
    │   ├── processors/
    │   └── exporters/
    └── sql/queries/
```

---

## Key Technical Details

### Standard Schema for Normalized Data

After normalization, all district data follows this schema:

```python
{
    'district_id': str,           # Unique district identifier
    'district_name': str,         # District name
    'state': str,                 # Two-letter state code
    'enrollment': float,          # Total student enrollment
    'instructional_staff': float, # Number of instructional staff
    'total_staff': float,         # Total staff count (optional)
    'schools': float,             # Number of schools (optional)
    'year': str,                  # School year (e.g., "2023-24")
    'data_source': str,          # Source identifier (e.g., "nces_ccd")
}
```

### State Instructional Time Requirements

States have vastly different requirements (from `config/state-requirements.yaml`):
- **Texas**: 420 minutes/day (highest)
- **Utah**: 240 minutes/day for K-8 (lowest)
- **California**: 240-360 minutes depending on grade
- Default: 360 minutes if not specified

### Multi-Part File Handling

Many large datasets are split across multiple files with naming pattern:
- `filename_1.csv`, `filename_2.csv`, `filename_3.csv`, etc.

The `split_large_files.py` script automatically:
1. Detects files matching this pattern
2. Sorts by part number
3. Concatenates while preserving headers
4. Creates combined file with `_combined` suffix

---

## Development Workflow

### 1. Always Start with Sample Data

```bash
# Create sample data for testing
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24 --sample

# Test the full pipeline (basic)
python pipelines/full_pipeline.py --year 2023-24 --sample

# Test with bell schedule enrichment
python pipelines/full_pipeline.py --year 2023-24 --sample --enrich-bell-schedules --tier 2
```

### 2. Process Real Data Incrementally

```bash
# Download full dataset
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24

# Enrich with bell schedules (optional, for top districts)
# NOTE: For manual enrichment, see docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md
python infrastructure/scripts/enrich/fetch_bell_schedules.py \
  data/processed/normalized/top_25_districts.csv \
  --tier 1 --year 2023-24

# Handle multi-part files if present
python infrastructure/scripts/extract/split_large_files.py data/raw/federal/nces-ccd/2023_24/

# Normalize to standard schema
python infrastructure/scripts/transform/normalize_districts.py \
  data/raw/federal/nces-ccd/2023_24/districts.csv \
  --source nces --year 2023-24

# Calculate LCT with summary and filtering (recommended)
python infrastructure/scripts/analyze/calculate_lct.py \
  data/processed/normalized/districts_2023_24_nces.csv \
  --summary --filter-invalid
```

### 3. Development Principles

- **Never modify raw data**: Always work with copies in processed/
- **Document lineage**: Scripts create `_lineage.yaml` files automatically
- **Test incrementally**: Validate at each pipeline stage
- **Write tests**: Add to `infrastructure/quality-assurance/tests/`
- **Log everything**: Use Python's logging module consistently

---

## Data Sources

### Priority Federal Sources

1. **NCES Common Core of Data (CCD)**
   - Annual data for all public schools/districts
   - Includes enrollment, staff counts, demographics
   - URL: https://nces.ed.gov/ccd/
   - Best for: District-level metrics

2. **Civil Rights Data Collection (CRDC)**
   - Biennial survey
   - More detailed class-level data
   - Teacher assignments, class sizes
   - Best for: Fine-grained analysis

### Priority State Sources

Phased rollout starting with:
1. **California** - DataQuest API, excellent access
2. **Texas** - PEIMS data, comprehensive
3. **New York** - NYSED data portal
4. **Florida** - Growing population, good reporting

---

## Current Challenges & Opportunities

### Known Data Gaps

1. **Temporal Data Missing from Standards** ⭐ PARTIALLY ADDRESSED
   - Bell schedules not in OneRoster ✅ Now collected via web scraping
   - Period duration not standardized ✅ Extracted from bell schedules where available
   - Actual vs. statutory time not tracked ✅ Actual time used for Tier 1 & 2 districts
   - Remaining limitation: Not all districts have publicly available schedules

2. **Multi-Part File Reality**
   - Large datasets often split by data providers
   - Our `split_large_files.py` handles this
   - Always check for `_1`, `_2`, etc. patterns

3. **State Variation**
   - Different data formats per state
   - Different instructional time requirements
   - Need custom normalization per state

4. **Data Quality Issues** ✅ ADDRESSED
   - Some districts report zero enrollment or staff (administrative units)
   - Occasional impossible ratios (more staff than students)
   - Invalid LCT values (exceeding available time)
   - ✅ Automated filtering now implemented (`--filter-invalid` flag)
   - ✅ Validation reports provide transparency
   - ✅ Publication-ready datasets exclude ~2-3% of invalid records

### Integration Opportunities

1. **OneRoster for Live Data**
   - Project owner has OneRoster integration work
   - Could supplement public data analysis
   - Direct SIS access for select districts

2. **React Prototype**
   - Visualization tool in development
   - Could display LCT calculations in real-time
   - See related project work

---

## Immediate Next Steps

### Priority 1: Validate with Real Data
1. Download actual NCES CCD data for 2023-24
2. Test multi-part file handling on real splits
3. Validate normalization produces correct schema
4. Confirm LCT calculations match expectations

### Priority 2: Expand State Coverage
1. Research data access for California
2. Document their specific format in normalization script
3. Add California-specific column mappings
4. Test end-to-end with CA data

### Priority 3: Build District Profiles
1. Create district-level summary cards
2. Include comparison to state/national averages
3. Generate visualizations showing LCT distribution
4. Export to formats suitable for presentations

### Priority 4: Quality Assurance
1. Expand test coverage in `tests/`
2. Add integration tests for full pipeline
3. Validate against known ground truth districts
4. Document edge cases and handling

---

## Testing

### Run Unit Tests
```bash
cd infrastructure/quality-assurance/tests
pytest test_utilities.py -v
```

### Test Individual Components
```bash
# Test state standardization
python infrastructure/utilities/common.py

# Test sample data creation
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24 --sample

# Test normalization validation
python infrastructure/scripts/transform/normalize_districts.py \
  input.csv --source nces --year 2023-24 --validate-only
```

---

## Important Files to Review

### Before Making Changes
1. `docs/PROJECT_CONTEXT.md` - Understand the mission and constraints
2. `docs/METHODOLOGY.md` - Review calculation approach and known limitations
3. `infrastructure/scripts/README.md` - Comprehensive script documentation

### For Bell Schedule Enrichment ⭐
1. **`docs/QUICK_REFERENCE_BELL_SCHEDULES.md`** - START HERE for quick reference
   - One-page cheat sheet with most common commands
   - Tool priority guidelines (local > remote)
   - Quick decision trees and checklists
2. **`docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md`** - Complete operational procedures
   - Full tool inventory (tesseract, pdftotext, ocrmypdf, etc.)
   - Step-by-step SOPs for images, PDFs, HTML
   - Detailed troubleshooting decision trees
   - Token efficiency best practices
   - Prevents session stalls by encoding fallback strategies
3. `docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md` - Methodology and sampling approach
4. `infrastructure/scripts/enrich/fetch_bell_schedules.py` - Automation script

### For Common Tasks
- **Add new data source**: Edit `config/data-sources.yaml` and create download script
- **Update state requirements**: Edit `config/state-requirements.yaml`
- **Modify LCT calculation**: Edit `infrastructure/scripts/analyze/calculate_lct.py`
- **Add state-specific normalization**: Edit `infrastructure/scripts/transform/normalize_districts.py`
- **Manual bell schedule enrichment**: Follow `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md`
- **Interactive bell schedule enrichment**: Run `python infrastructure/scripts/enrich/interactive_enrichment.py --state XX` ⭐ NEW
- **Query database**: Use functions in `infrastructure/database/queries.py`
- **Export database to JSON**: Run `python infrastructure/database/export_json.py`
- **Generate data dictionary**: Run `python infrastructure/scripts/utilities/generate_data_dictionary.py` ⭐ NEW
- **View QA dashboard**: Run LCT calculation script with default settings ⭐ NEW
- **Refresh materialized views**: Run `psql -d learning_connection_time -c "SELECT refresh_all_materialized_views();"` ⭐ NEW

---

## Integration with Broader Work

### Related Projects
- **OneRoster Integration**: Project owner has SIS integration work
- **React Prototype**: Real-time LCT visualization tool
- **1EdTech Standards**: Analysis of educational data standards

### Strategic Context
This is part of "Reducing the Ratio" initiative to advance educational equity discussions through better metrics. The work aims to create institutional applications that can systematically collect and analyze this data.

---

## Code Style & Conventions

### Python
- Use Python 3.11+
- Follow PEP 8 style guidelines
- Use type hints where helpful
- Comprehensive docstrings for all functions
- Logging instead of print statements

### File Naming
- Scripts: `kebab-case.py`
- Data files: `descriptive_name_YYYY_YY.csv` (school year format)
- **Generated outputs**: Append ISO 8601 UTC timestamp: `name_YYYY_YY_<timestamp>.csv`
  - Timestamp format: `YYYYMMDDTHHMMSSZ` (e.g., `20251228T012536Z`)
  - Example: `lct_all_variants_2023_24_valid_20251228T012536Z.csv`
- Config files: `kebab-case.yaml`
- Documentation: `CAPS_WITH_UNDERSCORES.md` for important docs, `kebab-case.md` for others

### Git Commits
- Descriptive commit messages
- One logical change per commit
- Reference issue numbers if applicable

---

## Technical Stack

### Core Dependencies
- **pandas**: Data manipulation
- **dask**: Large dataset processing (optional)
- **PyYAML**: Configuration files
- **requests**: Data downloads
- **great_expectations**: Data validation (optional)
- **pytest**: Testing
- **jupyter**: Exploratory analysis

### Database Stack ⭐ NEW
- **PostgreSQL 16**: Primary data store (Docker containerized)
- **Docker Compose**: Container orchestration
- **SQLAlchemy**: ORM with declarative models
- **psycopg2**: PostgreSQL adapter

### Visualization Tools
- **Plotly/Matplotlib**: Visualizations

---

## Common Commands Reference

### Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Make Scripts Executable
```bash
python infrastructure/scripts/make_executable.py
```

### Full Pipeline
```bash
# Basic pipeline
python pipelines/full_pipeline.py --year 2023-24 --sample

# With bell schedule enrichment
python pipelines/full_pipeline.py --year 2023-24 --enrich-bell-schedules --tier 1
```

### Individual Steps
```bash
# Download
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24

# Enrich with bell schedules (optional)
python infrastructure/scripts/enrich/fetch_bell_schedules.py districts.csv --tier 1 --year 2023-24

# Extract multi-part files
python infrastructure/scripts/extract/split_large_files.py data/raw/federal/nces-ccd/2023_24/

# Normalize
python infrastructure/scripts/transform/normalize_districts.py input.csv --source nces --year 2023-24

# Calculate LCT with filtering (recommended for publication)
python infrastructure/scripts/analyze/calculate_lct.py input.csv --summary --filter-invalid

# Calculate LCT variants with QA dashboard and Parquet export ⭐ NEW (Dec 2025)
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24 --parquet
```

### Database Operations ⭐ NEW
```bash
# Check database status
psql -d learning_connection_time -c "SELECT COUNT(*) FROM districts;"

# Re-import all data
python infrastructure/database/migrations/import_all_data.py

# Export to JSON (for sharing/backup)
python infrastructure/database/export_json.py

# Query enrichment status (Python)
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import print_enrichment_report
with session_scope() as session:
    print_enrichment_report(session)
"
```

### Efficiency Tools ⭐ NEW (Dec 27-28, 2025)
```bash
# Interactive bell schedule enrichment
python infrastructure/scripts/enrich/interactive_enrichment.py --state WI
python infrastructure/scripts/enrich/interactive_enrichment.py --district 5560580
python infrastructure/scripts/enrich/interactive_enrichment.py --status

# Generate data dictionary from database schema
python infrastructure/scripts/utilities/generate_data_dictionary.py

# Refresh materialized views (after data changes)
psql -d learning_connection_time -c "SELECT refresh_all_materialized_views();"

# Query pre-computed views for fast lookups
psql -d learning_connection_time -c "SELECT * FROM mv_state_enrichment_progress ORDER BY enriched DESC LIMIT 10;"
psql -d learning_connection_time -c "SELECT * FROM mv_districts_with_lct_data WHERE state = 'WI';"

# Calculate LCT with QA dashboard
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24

# Calculate LCT with Parquet export (70-80% size reduction)
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24 --parquet

# Incremental calculation (only changed districts)
python infrastructure/scripts/analyze/calculate_lct_variants.py --year 2023-24 --incremental

# View QA report
cat data/enriched/lct-calculations/lct_qa_report_2023_24_<timestamp>.json
```

---

## Troubleshooting

### "Column not found" errors
- Check that input data matches expected schema
- Review column mappings in normalization script
- Use `--validate-only` flag to test without saving

### Memory issues
- Use `dask` for large files
- Process in chunks with pandas `chunksize`
- Consider PostgreSQL for very large datasets

### Multi-part files not detected
- Ensure naming follows `basename_N.ext` pattern
- Check pattern parameter: `--pattern "_"`
- Verify files are in same directory

---

## Getting Help

1. **Check script documentation**: All scripts have `--help` flags
2. **Review script README**: `infrastructure/scripts/README.md` has comprehensive examples
3. **Check test files**: Tests show expected usage patterns
4. **Review chat history**: `docs/chat-history/` has session context

---

## Project Status

**Current Phase**: Phase 1.5 - Bell Schedule Enrichment Campaign (December 2024)
**Active Work**: Collecting actual instructional time from U.S. school districts

### Terminology & Standards
📖 **IMPORTANT**: See `docs/TERMINOLOGY.md` for standardized vocabulary
- **Automated enrichment**: Claude-collected via web scraping/PDF extraction
- **Human-provided**: User manually collected and placed in manual_import_files/
- **Actual bell schedules**: Real data from schools (counts as enriched) ✓
- **Statutory fallback**: State minimums only (does NOT count as enriched) ✗

### Current Dataset: 2024-25 + 2025-26

**Total Enriched: 128 districts** ✅ (as of December 26, 2025)
- **Primary Storage**: PostgreSQL database (learning_connection_time) ⭐ Docker containerized
- **Backup/Export**: `data/enriched/bell-schedules/bell_schedules_manual_collection_2024_25.json`
- Dataset: 17,842 districts in database
- Enrichment rate: 0.72% (128 enriched districts)

**Enrichment Breakdown by Collection Method:**
- **State-by-state campaign**: Systematic enrichment following Option A protocol (Dec 2025+)
- **Automated enrichment campaign**: Web scraping/PDF extraction for largest districts
- **Manual imports**: User-provided bell schedules from various sources
- **Top 25 largest districts**: 25/25 collected (100% complete) ✅
  - Includes Memphis-Shelby County TN (district ID 4700148)
- **Personal choice**: San Mateo × 2, Evanston × 2, Pittsburgh
- **State campaigns**: 35 states with ≥3 districts each

**States Represented:** 43 states/territories ✅
- **Northeast** (8): CT (3), DE (3), MD (3), NH (3), PA (2), RI (3), VT (3), ME (1)
- **Southeast** (8): AL (3), AR (3), FL (7), GA (3), KY (3), LA (3), NC (2), SC (3), TN (1), VA (1)
- **Midwest** (13): IA (3), IL (3), KS (3), MN (3), MS (3), ND (3), NE (3), OK (3), SD (3), WI (3)
- **West** (13): AK (3), AZ (3), CA (7), CO (3), HI (1), ID (3), MT (5), NM (3), NV (1), OR (3), TX (4), UT (3), WY (5)
- **Other** (2): DC (3), PR (1)

**Data Quality Standards:**
- ✅ Only actual bell schedules counted in enrichment metrics
- ✅ All files use standardized JSON schema with elementary/middle/high breakdowns
- ✅ Source attribution in every file (method: automated_enrichment or human_provided)

### Legacy Dataset: 2023-24

**Wyoming Campaign:** 5 districts (separate tracking)
- Tracking file: `data/processed/normalized/enrichment_reference.csv`
- Note: 135 statutory fallback files excluded from counts (moved to tier3_statutory_fallback/)
- **Status**: Complete, archived dataset

### Infrastructure Optimizations (Dec 21-28, 2025)

**Completed:**
- ✅ Data optimization (88% token reduction via slim files)
- ✅ Process optimization (2.15-4.25M token savings)
- ✅ Lightweight enrichment reference file (90% token reduction per load)
- ✅ Batch enrichment framework with checkpoint/resume
- ✅ Real-time progress tracker (`enrichment_progress.py`)
- ✅ Smart candidate filtering (6,952 high-quality targets identified)
- ✅ Terminology standardization (`docs/TERMINOLOGY.md`)
- ✅ **PostgreSQL database migration** (Dec 25, 2025) ⭐
  - Migrated from JSON files to PostgreSQL 16 (Docker containerized)
  - 17,842 districts, 50 state requirements, 384 bell schedules (128 districts)
  - Query utilities for token-efficient data access
  - JSON export for backward compatibility
- ✅ **Docker containerization** (Dec 25, 2025)
  - PostgreSQL running in Docker container for portability
  - `docker-compose up -d` for instant setup
  - Persistent volumes for data safety
  - Same environment local → production (Supabase-ready)
- ✅ **Efficiency Enhancement Suite** (Dec 27-28, 2025) ⭐ NEW
  - **Query utilities library**: Extended `infrastructure/database/queries.py` with campaign tracking
  - **QA dashboard automation**: Auto-generates validation reports and dashboards
  - **Data dictionary generator**: `generate_data_dictionary.py` auto-generates from SQLAlchemy models
  - **Materialized views**: 4 pre-computed views for common queries (14K+ rows cached)
  - **Interactive enrichment tool**: `interactive_enrichment.py` CLI for state campaigns
  - **Parquet export**: Optional 70-80% file size reduction for large datasets
  - **Incremental calculations**: Tracks calculation runs, enables smart recalculation

### Known Limitations

1. ~~**Consolidated file size**: 41,624+ tokens~~ ✅ **RESOLVED** via PostgreSQL
   - Data now queried from database instead of loading full JSON
   - Export utility maintains backward compatibility

2. **Coverage**: 128 of 17,842 U.S. districts (0.72%)
   - 35 states with ≥3 districts (64% state coverage)
   - 43 states/territories represented
   - Focused on largest districts and strategic state-by-state sampling
   - Sufficient for robust equity analysis and methodology validation

### Campaign Strategy Notes

**Current Approach**: State-by-state enrichment with expanded candidate pool ⭐ UPDATED Dec 26, 2025

**Standard Operating Procedure (Option A):**
1. Process states in **ascending enrollment order** (from `state_enrichment_tracking.csv`)
2. For each state, query districts **ranked 1-9 by enrollment**
3. Attempt enrichment in rank order
4. **Stop when 3 successful** enrichments achieved
5. Mark any failed attempts for manual follow-up (`manual_followup_needed.json`)
6. Move to next state

**Why This Works:**
- First pass (ranks 1-3): ~44% success rate
- Expanded pool (ranks 4-9): ~83% success rate
- Combined (ranks 1-9): ~90% state completion in single pass
- Avoids context-switching overhead of revisiting states
- Token-efficient: single session per state in most cases

**Database Queries:**
```sql
-- Get districts ranked 1-9 by enrollment for a state
SELECT nces_id, name, enrollment
FROM districts
WHERE state = 'XX'
ORDER BY enrollment DESC
LIMIT 9;
```

**Python Workflow:**
```python
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import add_bell_schedule

with session_scope() as session:
    add_bell_schedule(
        session,
        district_id="XXXXXXX",
        year="2025-26",
        grade_level="elementary",
        instructional_minutes=360,
        start_time="8:00 AM",
        end_time="3:00 PM",
        lunch_duration=30,
        method="web_scraping",
        confidence="high",
        schools_sampled=["School A", "School B"],
        source_urls=["https://..."],
        notes="District-wide schedule"
    )
```

**Evaluation Checkpoints:**
- Review progress every 5-10 states
- Track success rates by state and rank
- Adjust strategy if patterns emerge

**Legacy Approach** (still supported):
- User provides files in `data/raw/manual_import_files/{State}/{District Name (STATE)}/`
- Process using `infrastructure/scripts/utilities/batch_convert.py` for PDFs/HTML
- Create individual JSON files: `{district_id}_2024-25.json`

**Future Expansion Options**:
1. Continue state-by-state completion (current priority)
2. Target underrepresented regions as coverage expands
3. Manual follow-up for blocked districts after campaign completes
4. Systematic national coverage for policy impact

---

**Last Updated**: December 28, 2025
**Project Location**: `/Users/ianmmc/Development/learning-connection-time`
**Status**: Active enrichment campaign - State-by-state coverage expansion ✅
**Primary Data Store**: PostgreSQL database (learning_connection_time) ⭐ NEW
**Dataset**: Mixed (2023-24 legacy + 2024-25 + 2025-26 current campaign)
**Milestones**:
- ✅ Top 25 largest districts: 100% complete (25/25)
- ✅ PostgreSQL database migration complete (Dec 25, 2025)
- ✅ Docker containerization complete (Dec 25, 2025)
- ✅ Wyoming legacy data migrated (5 districts, 15 schedules from 2023-24)
- ✅ **35 states with ≥3 enriched districts** (64% of 55 states/territories) - as of Dec 26, 2025
- ✅ **128 total enriched districts** across 43 states/territories (0.72% of 17,842)
- ✅ **Option A process adopted** (Dec 26, 2025) - attempt ranks 1-9 per state, stop at 3 successful
- ✅ **South Carolina, Wisconsin, Minnesota campaigns complete** (Dec 26, 2025) - 9 districts enriched
- ✅ **Efficiency Enhancement Suite** (Dec 27-28, 2025) - QA dashboard, materialized views, interactive enrichment, Parquet export, calculation tracking
**Key Additions**:
- Bell schedule search priority: 2025-26 > 2024-25 > 2023-24
- **CRITICAL**: COVID-era data exclusion (2019-20 through 2022-23) - use 2018-19 if needed
- **Data access**: Query database via `infrastructure/database/queries.py` for token efficiency
- **State tracking**: `data/processed/normalized/state_enrichment_tracking.csv`
- **Standard process**: Query ranks 1-9 per state, stop at 3 successful enrichments
