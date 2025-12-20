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

3. **Extract**: `infrastructure/scripts/extract/split_large_files.py`
   - Handles multi-part files (filename_1, filename_2, etc.)
   - Automatically concatenates with proper header handling

4. **Transform**: `infrastructure/scripts/transform/normalize_districts.py`
   - Normalizes data from various sources to standard schema
   - Supports both federal (NCES) and state-specific formats

5. **Analyze**: `infrastructure/scripts/analyze/calculate_lct.py`
   - Implements LCT calculation
   - Generates derived metrics and percentiles
   - Produces summary statistics

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
│   ├── scripts/
│   │   ├── download/              # Data acquisition
│   │   ├── enrich/                # Data enrichment (bell schedules)
│   │   ├── extract/               # Parsing and combining
│   │   ├── transform/             # Cleaning and normalization
│   │   └── analyze/               # Metric calculations
│   ├── quality-assurance/tests/   # Test suite
│   └── utilities/                 # Helper functions
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
python infrastructure/scripts/enrich/fetch_bell_schedules.py \
  data/processed/normalized/top_25_districts.csv \
  --tier 1 --year 2023-24

# Handle multi-part files if present
python infrastructure/scripts/extract/split_large_files.py data/raw/federal/nces-ccd/2023_24/

# Normalize to standard schema
python infrastructure/scripts/transform/normalize_districts.py \
  data/raw/federal/nces-ccd/2023_24/districts.csv \
  --source nces --year 2023-24

# Calculate LCT with summary
python infrastructure/scripts/analyze/calculate_lct.py \
  data/processed/normalized/districts_2023_24_nces.csv \
  --summary
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

### For Common Tasks
- **Add new data source**: Edit `config/data-sources.yaml` and create download script
- **Update state requirements**: Edit `config/state-requirements.yaml`
- **Modify LCT calculation**: Edit `infrastructure/scripts/analyze/calculate_lct.py`
- **Add state-specific normalization**: Edit `infrastructure/scripts/transform/normalize_districts.py`

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
- Data files: `descriptive_name_YYYY_MM.csv`
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

### Optional Tools
- **PostgreSQL**: For complex queries (not yet implemented)
- **Plotly/Matplotlib**: Visualizations
- **SQLAlchemy**: Database abstraction

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

# Calculate LCT
python infrastructure/scripts/analyze/calculate_lct.py input.csv --summary
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

**Current Phase**: Infrastructure complete, ready for data processing
**Next Milestone**: Complete analysis of top 25 largest districts
**Timeline**: User-determined based on priorities

---

**Last Updated**: December 16, 2025
**Project Location**: `/Users/ianmmc/Development/learning-connection-time`
**Status**: Ready for active development with Claude Code
