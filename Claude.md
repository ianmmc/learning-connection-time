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

**Current Date:** January 17, 2026
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

### ✅ SEA Integration Test Framework (January 2026) ⭐ NEW
- **Base class**: `tests/test_sea_integration_base.py` - Abstract base with mixin classes
- **State tests**: FL (71 tests), TX (54 tests), CA (58 tests), temporal (33 tests) - 480 total tests passing
- **Template Method pattern**: Common test logic in base, state-specific values in subclasses
- **7 test categories**: DataLoading, Crosswalk, Staff, Enrollment, LCT, DataIntegrity, RegressionPrevention
- **Purpose**: Prevent regressions when SEA data is updated, validate crosswalks

### ✅ Master Crosswalk Table (January 2026) ⭐ NEW
- **Migration 007**: `state_district_crosswalk` table stores all NCES ↔ State ID mappings
- **Populated from**: NCES CCD ST_LEAID field for all 50 states + territories
- **Coverage**: 17,842 entries covering all districts in database
- **Refactored scripts**: Florida, California, and Texas import scripts now use crosswalk as source of truth
- **Benefits**: Single source of truth, validates against existing mappings, logs discrepancies

### ✅ Temporal Validation (January 2026) ⭐ NEW
- **Migration 008**: 3-year blending window rule for multi-source data
- **Rule**: Data from multiple sources must span ≤3 consecutive school years
- **Columns added**: `year_span`, `within_3year_window`, `temporal_flags` to lct_calculations
- **Flags**: WARN_YEAR_GAP (2-3 year span), ERR_SPAN_EXCEEDED (>3 years)
- **Exception**: SPED baseline (2017-18 IDEA 618/CRDC) exempt as ratio proxy
- **Trigger**: `trg_lct_temporal_validation` auto-validates on INSERT/UPDATE
- **View**: `v_lct_temporal_validation` for validation summary

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

## Data Architecture: Layered Integration ⭐ NEW (January 2026)

### Overview

The project uses a **layered data architecture** where NCES CCD serves as the foundation layer, with State Education Agency (SEA) data integrated as enrichment layers above it.

```
┌─────────────────────────────────────────────────────┐
│                    Layer 2: SEA Data                │
│   (FLDOE, TEA, CDE, NYSED - state-specific data)   │
├─────────────────────────────────────────────────────┤
│              Layer 1: NCES CCD Foundation           │
│     (17,842 districts, enrollment, staffing)        │
└─────────────────────────────────────────────────────┘
```

### Why This Architecture?

1. **Consistency**: NCES CCD provides uniform baseline data across all states
2. **Enrichment**: SEA data adds state-specific details (ADA, SPED breakdowns, funding)
3. **Validation**: Cross-reference federal and state data to catch discrepancies
4. **Flexibility**: States can be added incrementally without affecting the foundation

### District ID Crosswalk

Each state uses different district identifiers. The crosswalk maps between:
- **NCES LEAID**: 7-digit federal identifier (e.g., `"0622710"` for LA Unified)
- **State District ID**: State-specific format

| State | ID Format | Example |
|-------|-----------|---------|
| FL | 2-digit | `"13"` (Miami-Dade) |
| TX | TX-XXXXXX | `"TX-101912"` (Houston ISD) |
| CA | XX-XXXXX | `"19-64733"` (Los Angeles Unified) |

### Implemented SEA Integrations

| State | Agency | Status | Test File | Key Data |
|-------|--------|--------|-----------|----------|
| California | CDE | ✅ Complete | `test_california_integration.py` | LCFF, ADA, SPED, FRPM |
| Texas | TEA | ✅ Complete | `test_texas_integration.py` | NCES crosswalk via ST_LEAID |
| Florida | FLDOE | ✅ Complete | `test_florida_integration.py` | Staff, enrollment, 82 districts |
| New York | NYSED | 🔜 Next | - | NYC (33 sub-districts), upstate |
| Illinois | ISBE | 🔜 Next | - | Chicago (City of Chicago SD 299) |

### ⚠️ Complex Districts: NYC and Chicago

**New York City** requires special handling:
- NYC is administratively divided into **33 geographic districts** (Community School Districts 1-32 + District 75 citywide SPED)
- NCES may report as single LEA or multiple depending on data vintage
- State ID format: NY-XXXXXXX (7-digit)
- Watch for: District 75 (citywide special education), charter schools

**Chicago** requires special handling:
- Officially "City of Chicago School District 299"
- Single largest district in Illinois (~320K students)
- State ID format: IL-XXXXXXX (typically IL-15-016-2990-26)
- Watch for: Charter schools reported separately, selective enrollment schools

### SEA Data Files

Located in `data/raw/state/{state}/`:

```
data/raw/state/
├── california/
│   ├── lcff_snapshot_2023_24.csv      # Local Control Funding Formula
│   ├── sped_counts_2023_24.csv        # Special Education counts
│   └── frpm_counts_2023_24.csv        # Free/Reduced Price Meals
├── texas/
│   └── texas_nces_tea_crosswalk_2018_19.csv
└── florida/
    ├── florida_staff_2024_25.csv
    └── florida_enrollment_2024_25.csv
```

---

## SEA Integration Test Framework ⭐ NEW (January 2026)

### Architecture

The test framework uses a **Template Method pattern** with abstract base class and mixin classes:

```
SEAIntegrationTestBase (Abstract)
    ├── SEADataLoadingTests (Mixin)
    ├── SEACrosswalkTests (Mixin)
    ├── SEAStaffValidationTests (Mixin)
    ├── SEAEnrollmentValidationTests (Mixin)
    ├── SEALCTCalculationTests (Mixin)
    ├── SEADataIntegrityTests (Mixin)
    └── SEARegressionPreventionTests (Mixin)
```

### Base Class Properties

Each state test class must define:

```python
class StateSEAConfig(SEAIntegrationTestBase):
    STATE_CODE = "XX"              # Two-letter code
    STATE_NAME = "State Name"      # Full name
    SEA_NAME = "Agency"            # e.g., "FLDOE", "TEA", "CDE"
    DATA_YEAR = "2023-24"          # School year

    EXPECTED_DISTRICTS = {
        "District Name": {
            "nces_leaid": "XXXXXXX",
            "state_district_id": "XX-XXXXX",
            "enrollment": 150000,
            "total_teachers": 8000,
            "expected_lct_teachers_only": 19.2,
            "instructional_minutes": 360,
        },
    }

    CROSSWALK = {
        "XXXXXXX": "XX-XXXXX",  # NCES LEAID -> State ID
    }
```

### Test Categories

| Category | Tests | Purpose |
|----------|-------|---------|
| DataLoading | 5 | Verify SEA files exist and load correctly |
| Crosswalk | 4 | Validate NCES ↔ State ID mappings |
| StaffValidation | 1 | Teacher counts within 5% tolerance |
| EnrollmentValidation | 1 | Enrollment within 5% tolerance |
| LCTCalculation | 2 | Formula validation and range checks |
| DataIntegrity | 2 | No duplicates, reasonable ratios |
| RegressionPrevention | 3 | Prevent type coercion and zero-value bugs |

### Adding a New State

1. **Create SEA data directory**: `data/raw/state/{state}/`
2. **Download SEA data files** (staff, enrollment, crosswalk)
3. **Create test file**: `tests/test_{state}_integration.py`

```python
# tests/test_newstate_integration.py
import pytest
from pathlib import Path
import pandas as pd
from tests.test_sea_integration_base import (
    SEAIntegrationTestBase,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEARegressionPreventionTests,
)

class NewStateSEAConfig(SEAIntegrationTestBase):
    STATE_CODE = "NS"
    STATE_NAME = "New State"
    SEA_NAME = "NSDOE"
    DATA_YEAR = "2023-24"

    EXPECTED_DISTRICTS = {
        # Add 3-5 key districts with expected values
    }

    CROSSWALK = {
        # NCES LEAID -> State ID mappings
    }

    def get_data_files(self):
        base = Path("data/raw/state/newstate")
        return {
            "staff": base / "staff_2023_24.csv",
            "enrollment": base / "enrollment_2023_24.csv",
        }

    def load_staff_data(self):
        return pd.read_csv(self.get_data_files()["staff"])

    def load_enrollment_data(self):
        return pd.read_csv(self.get_data_files()["enrollment"])

class TestNewStateIntegration(
    NewStateSEAConfig,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEARegressionPreventionTests,
):
    """Integration tests for New State SEA data."""
    pass
```

4. **Run tests**: `pytest tests/test_newstate_integration.py -v`
5. **Document in DATA_SOURCES.md**

### Running SEA Integration Tests

```bash
# Run all SEA integration tests
pytest tests/test_*_integration.py -v

# Run specific state
pytest tests/test_florida_integration.py -v

# Run specific test category across all states
pytest tests/test_*_integration.py -v -k "crosswalk"

# See test counts by state
pytest tests/test_*_integration.py --collect-only | grep "test session"
```

### Current Test Coverage

| Category | Tests | Status |
|----------|-------|--------|
| Florida Integration | 71 | ✅ Pass |
| Texas Integration | 54 | ✅ Pass |
| California Integration | 58 | ✅ Pass |
| State Integration (general) | 31 | ✅ Pass |
| Temporal Validation | 33 | ✅ Pass |
| Other Tests | 233 | ✅ Pass |
| **Total** | **480** | ✅ All Pass |

*Test categories include: bell schedule enrichment, constraints, data safeguards, LCT calculations, validation, export, and more.*

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

### Run SEA Integration Tests ⭐ NEW
```bash
# Run all SEA integration tests (179 tests across 3 states)
pytest tests/test_*_integration.py -v

# Run specific state integration tests
pytest tests/test_florida_integration.py -v
pytest tests/test_texas_integration.py -v
pytest tests/test_california_integration.py -v

# Run specific test category across all states
pytest tests/test_*_integration.py -v -k "crosswalk"
pytest tests/test_*_integration.py -v -k "enrollment"
pytest tests/test_*_integration.py -v -k "lct"

# Quick validation (collect only, no execution)
pytest tests/test_*_integration.py --collect-only
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

### For SEA Integration ⭐ NEW
1. **`tests/test_sea_integration_base.py`** - Base class and mixin definitions
   - Abstract base class `SEAIntegrationTestBase`
   - 7 mixin classes for test categories
   - Helper functions for LCT and tolerance calculations
2. **`tests/test_florida_integration.py`** - Florida reference implementation (71 tests)
3. **`tests/test_texas_integration.py`** - Texas with TEA crosswalk (54 tests)
4. **`tests/test_california_integration.py`** - California with CDE data (58 tests)
5. **`data/raw/state/{state}/`** - SEA data files by state

### For Common Tasks
- **Add new data source**: Edit `config/data-sources.yaml` and create download script
- **Update state requirements**: Edit `config/state-requirements.yaml`
- **Modify LCT calculation**: Edit `infrastructure/scripts/analyze/calculate_lct.py`
- **Add state-specific normalization**: Edit `infrastructure/scripts/transform/normalize_districts.py`
- **Manual bell schedule enrichment**: Follow `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md`
- **Add new SEA integration**: Create `tests/test_{state}_integration.py` using base class ⭐ NEW
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

**Total Enriched: 182 districts** ✅ (as of January 2026)
- **Primary Storage**: PostgreSQL database (learning_connection_time) ⭐ Docker containerized
- **Backup/Export**: `data/enriched/bell-schedules/bell_schedules_manual_collection_2024_25.json`
- Dataset: 17,842 districts in database
- Enrichment rate: 1.02% (182 enriched districts)

**Enrichment Breakdown by Collection Method:**
- **State-by-state campaign**: Systematic enrichment following Option A protocol (completed January 2026) ✅
- **Automated enrichment campaign**: Web scraping/PDF extraction for largest districts
- **Manual imports**: User-provided bell schedules from various sources
- **Top 25 largest districts**: 25/25 collected (100% complete) ✅
  - Includes Memphis-Shelby County TN (district ID 4700148)
- **Personal choice**: San Mateo × 2, Evanston × 2, Pittsburgh
- **State campaigns**: 50 U.S. states with ≥3 districts each (HI has 1, PR has 1)

**States Represented:** 52 states/territories ✅
- **Northeast** (9): CT (3), DE (3), MA (5), MD (3), ME (3), NH (3), NJ (3), PA (3), RI (3), VT (3)
- **Southeast** (10): AL (3), AR (3), FL (7), GA (3), KY (3), LA (3), MS (4), NC (3), SC (3), TN (3), VA (3), WV (3)
- **Midwest** (12): IA (3), IL (5), IN (3), KS (3), MI (3), MN (3), MO (3), ND (3), NE (5), OH (5), SD (3), WI (3)
- **West** (13): AK (3), AZ (3), CA (7), CO (3), HI (1), ID (5), MT (5), NM (3), NV (3), OR (3), TX (4), UT (3), WA (3), WY (5)
- **Other** (2): DC (3), PR (1)
- **Not addressed**: BI, MP, VI (territories)

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
  - 17,842 districts, 50 state requirements, 546 bell schedules (182 districts × 3 grade levels)
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
- ✅ **SPED Segmentation (v3 Self-Contained Focus)** (Jan 3, 2026) ⭐ NEW
  - Segments LCT by SPED (Special Education) vs GenEd (General Education)
  - Uses 2017-18 baseline ratios from IDEA 618 + CRDC federal data
  - **Three LCT scopes** (v3 self-contained approach):
    - `core_sped` - SPED teachers / self-contained SPED students
    - `teachers_gened` - GenEd teachers / GenEd enrollment (includes mainstreamed SPED)
    - `instructional_sped` - SPED teachers + paraprofessionals / self-contained students
  - **Key insight**: Self-contained SPED students (~6.7% of all SPED) have distinct teacher-student ratios
  - **Audit validation**: Weighted average of core_sped + teachers_gened = overall teachers_only LCT
  - Database tables: `sped_state_baseline`, `sped_lea_baseline`, `sped_estimates`
  - **Results**: See `data/enriched/lct-calculations/` for current LCT values by scope
  - **Methodology**: See `docs/SPED_SEGMENTATION_IMPLEMENTATION.md` for full details
- ✅ **Data Safeguards** (Jan 3, 2026) ⭐ NEW
  - 6 validation flags for data quality assessment
  - **Error flags** (ERR_): Likely data quality issues (flat staffing, impossible ratios, volatile enrollment, ratio ceiling)
  - **Warning flags** (WARN_): Unusual but potentially valid (extreme LCT values)
  - **Transparency-focused**: Flags data vs filtering, allows user-defined thresholds
  - **Flag definitions and usage**: See `docs/METHODOLOGY.md#data-safeguards`
  - **Current flag counts**: See QA reports in `data/enriched/lct-calculations/lct_qa_report_*.json`
  - **Analysis**: See `docs/Proposed LCT Validation Safeguards from Gemini.md`

### Known Limitations

1. ~~**Consolidated file size**: 41,624+ tokens~~ ✅ **RESOLVED** via PostgreSQL
   - Data now queried from database instead of loading full JSON
   - Export utility maintains backward compatibility

2. **Coverage**: 182 of 17,842 U.S. districts (1.02%)
   - 50 U.S. states with ≥3 districts (91% state coverage) ✅
   - 52 states/territories represented (HI and PR have 1 each)
   - BI, MP, VI territories not addressed
   - Focused on largest districts and strategic state-by-state sampling
   - Sufficient for robust equity analysis and methodology validation

### Campaign Strategy Notes

**Campaign Status**: ✅ **COMPLETE** (January 2026) - 50 U.S. states with ≥3 districts each

**Standard Operating Procedure (Option A) - Used for Completed Campaign:**
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

**Future Expansion Options** (post-campaign):
1. Manual follow-up for blocked districts (see `manual_followup_needed.json`)
2. Expand HI and PR to 3+ districts each
3. Address territories (BI, MP, VI) if needed for policy impact
4. Deepen coverage in high-priority states (e.g., top 10-20 districts per state)
5. Update schedules periodically to track changes over time

---

**Last Updated**: January 17, 2026
**Project Location**: `/Users/ianmmc/Development/learning-connection-time`
**Status**: Active development - SEA integrations (NY, IL next); FL/TX/CA complete ✅
**Primary Data Store**: PostgreSQL database (learning_connection_time) ⭐ Docker containerized
**Dataset**: Mixed (2023-24 legacy + 2024-25 + 2025-26 current campaign)
**Test Suite**: 480 tests passing (4 skipped for optional data files)

**Recent Milestones**:
- ✅ **Florida FLDOE Integration** (Jan 16-17, 2026) - 82 districts, LCT calculations complete
- ✅ **Master Crosswalk Table** (Jan 16, 2026) - Migration 007, 17,842 NCES ↔ State ID mappings
- ✅ **Temporal Validation** (Jan 16, 2026) - Migration 008, 3-year blending window rule
- ✅ **SEA Integration Test Framework** (Jan 16, 2026) - 480 tests across FL/TX/CA, base class + mixins
- ✅ **SPED Segmentation v3** (Jan 3, 2026) - Self-contained focus with three LCT scopes
- ✅ **Data Safeguards** (Jan 3, 2026) - 7 validation flags for quality transparency

**Completed Infrastructure**:
- ✅ PostgreSQL database migration (Dec 25, 2025)
- ✅ Docker containerization (Dec 25, 2025)
- ✅ Bell schedule enrichment campaign: 182 districts across 52 states/territories
- ✅ Efficiency Enhancement Suite (Dec 27-28, 2025)

**Upcoming Work**:
- 🔜 **New York State (NYSED)** - Complex: NYC has 33 sub-districts + District 75 citywide SPED
- 🔜 **Illinois (ISBE)** - Complex: Chicago SD 299 is single largest district (~320K students)

**Key Reference**:
- **Crosswalk table**: `state_district_crosswalk` - single source of truth for all state mappings
- **Temporal validation**: Data must span ≤3 consecutive school years (SPED 2017-18 baseline exempt)
- **Data safeguards**: 7 flags (ERR_FLAT_STAFF, ERR_IMPOSSIBLE_SSR, ERR_VOLATILE, ERR_RATIO_CEILING, WARN_LCT_LOW, WARN_LCT_HIGH, WARN_SPED_RATIO_CAP)
- **SPED segmentation (v3)**: core_sped, teachers_gened, instructional_sped scopes
- **COVID exclusion**: 2019-20 through 2022-23 data excluded
