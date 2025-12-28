# Infrastructure Scripts

This directory contains the data processing pipeline scripts for the Instructional Minute Metric project.

## Directory Structure

```
scripts/
├── download/         # Data acquisition from external sources
├── extract/          # File parsing and multi-part file handling
├── transform/        # Data cleaning and normalization
├── analyze/          # Metric calculations and analysis
└── make_executable.py  # Utility to set script permissions
```

## Quick Start

### 1. Make Scripts Executable

```bash
cd infrastructure/scripts
python make_executable.py
```

### 2. Run Sample Pipeline

```bash
cd ../../pipelines
python full_pipeline.py --year 2023-24 --sample
```

This will:
- Create sample data
- Process it through the full pipeline
- Calculate LCT metrics
- Generate summary reports

## Scripts Reference

### Download Scripts

#### `download/fetch_nces_ccd.py`

Download NCES Common Core of Data files.

**Usage:**
```bash
# Download full dataset
python fetch_nces_ccd.py --year 2023-24

# Create sample data for testing
python fetch_nces_ccd.py --year 2023-24 --sample

# Download specific tables
python fetch_nces_ccd.py --year 2023-24 --tables district_directory district_staff
```

**Arguments:**
- `--year`: School year (required)
- `--tables`: Specific tables to download (optional)
- `--sample`: Create sample data instead of downloading
- `--output-dir`: Custom output directory

**Outputs:**
- Raw data files in `data/raw/federal/nces-ccd/{year}/`
- README.md with metadata

---

### Extract Scripts

#### `extract/split_large_files.py`

Handle multi-part files (filename_1, filename_2, etc.) and concatenate them.

**Usage:**
```bash
# Process all multi-part files in directory
python split_large_files.py data/raw/federal/nces-ccd/2023-24/

# Use custom separator pattern
python split_large_files.py data/raw/federal/crdc/ --pattern "_part"

# Dry run to see what would happen
python split_large_files.py data/raw/ --dry-run

# Custom output directory
python split_large_files.py data/raw/ --output-dir data/processed/
```

**Arguments:**
- `directory`: Directory containing multi-part files (required)
- `--output-dir`: Where to save combined files (default: same as input)
- `--pattern`: Part number separator (default: "_")
- `--dry-run`: Show what would be done without doing it

**Outputs:**
- Combined files with `_combined` suffix
- Original files are preserved

**How It Works:**
1. Scans directory for files matching pattern (e.g., `file_1.csv`, `file_2.csv`)
2. Groups files by base name
3. Sorts by part number
4. Concatenates in order
5. Handles CSV headers automatically (keeps header from first file only)

---

### Transform Scripts

#### `transform/normalize_districts.py`

Normalize district data from various sources to a standard schema.

**Usage:**
```bash
# Normalize NCES data
python normalize_districts.py data/raw/federal/nces-ccd/2023-24/districts.csv \
  --source nces \
  --year 2023-24

# Normalize state data
python normalize_districts.py data/raw/state/california/districts.csv \
  --source state \
  --state CA \
  --year 2023-24

# Validate without saving
python normalize_districts.py input.csv --source nces --year 2023-24 --validate-only
```

**Arguments:**
- `input_file`: Raw data file (required)
- `--source`: Data source type: `nces` or `state` (required)
- `--state`: State abbreviation (required for state data)
- `--year`: School year (required)
- `--output`: Custom output file (optional)
- `--validate-only`: Only validate without saving

**Outputs:**
- Normalized CSV in `data/processed/normalized/`
- Lineage YAML file documenting processing

**Standard Schema:**
```
district_id             # Unique identifier
district_name           # District name
state                   # Two-letter state code
enrollment              # Total students
instructional_staff     # Number of instructional staff
total_staff             # Total staff (optional)
schools                 # Number of schools (optional)
year                    # School year
data_source             # Source identifier
```

---

### Analyze Scripts

#### `analyze/calculate_lct.py`

Calculate Learning Connection Time (LCT) for districts (legacy single-scope version).

**Usage:**
```bash
# Basic calculation
python calculate_lct.py data/processed/normalized/districts_2023_24.csv

# With custom output
python calculate_lct.py input.csv --output data/enriched/lct-calculations/results.csv

# Generate summary statistics
python calculate_lct.py input.csv --summary

# Use custom state requirements
python calculate_lct.py input.csv --state-config config/my-requirements.yaml
```

**Arguments:**
- `input_file`: Normalized district data (required)
- `--output`: Output file path (optional)
- `--state-config`: Custom state requirements YAML (optional)
- `--summary`: Generate summary statistics report

**Outputs:**
- CSV with LCT calculations and derived metrics
- Summary text file (if `--summary` used)

**Calculated Fields:**
- `lct_minutes`: Learning Connection Time in minutes/student/day
- `lct_hours`: LCT converted to hours
- `student_teacher_ratio`: Traditional ratio for comparison
- `lct_percentile`: Percentile ranking
- `lct_category`: Categorical level (Very Low, Low, Moderate, High, Very High)

**Formula:**
```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

#### `analyze/calculate_lct_variants.py` ⭐ NEW (December 2025)

Calculate all 7 LCT variants with QA dashboard and advanced features.

**Usage:**
```bash
# Calculate all variants from database
python calculate_lct_variants.py --year 2023-24

# With Parquet export (70-80% size reduction)
python calculate_lct_variants.py --year 2023-24 --parquet

# Incremental calculation (only changed districts)
python calculate_lct_variants.py --year 2023-24 --incremental

# Disable run tracking
python calculate_lct_variants.py --year 2023-24 --no-track
```

**Arguments:**
- `--year`: School year (required)
- `--parquet`: Export in Parquet format (optional, requires pyarrow)
- `--incremental`: Only calculate changed districts (optional)
- `--no-track`: Don't track run in database (optional)

**Outputs:**
- `lct_all_variants_<year>_<timestamp>.csv` - All 7 variants in one file
- `lct_all_variants_<year>_valid_<timestamp>.csv` - Filtered valid calculations
- `lct_variants_report_<year>_<timestamp>.txt` - Summary statistics
- `lct_qa_report_<year>_<timestamp>.json` - QA validation report ⭐ NEW
- `*.parquet` versions (if `--parquet` flag used)

**Features:**
- **7 LCT Variants**: teachers_only, teachers_elementary, teachers_secondary, teachers_core, instructional, instructional_plus_support, all
- **QA Dashboard**: Real-time validation with hierarchy checks (see `docs/QA_DASHBOARD.md`)
- **Incremental Processing**: Tracks runs in database, only recalculates when data changes
- **Parquet Export**: Optional columnar format for large datasets
- **Calculation Tracking**: Stores run metadata, QA results, and output files in database

**QA Dashboard Output:**
```
============================================================
QA DASHBOARD
============================================================
Status: PASS
Pass Rate: 99.46%

Hierarchy Checks:
  ✓ Secondary < Overall Teachers
  ✓ Teachers < Elementary
  ✓ Teachers < Core
  ✓ Core < Instructional
  ✓ Instructional < Support
  ✓ Support < All

Outliers Detected: 20
State Coverage: 48 states/territories
============================================================
```

See `docs/QA_DASHBOARD.md` for detailed QA documentation.

---

### Enrich Scripts

#### `enrich/interactive_enrichment.py` ⭐ NEW (December 2025)

Interactive CLI for efficient bell schedule collection during state campaigns.

**Usage:**
```bash
# Run state campaign (Option A protocol)
python interactive_enrichment.py --state WI

# Enrich single district
python interactive_enrichment.py --district 5560580

# Show campaign status
python interactive_enrichment.py --status

# Custom target and year
python interactive_enrichment.py --state CA --year 2025-26 --target 5
```

**Arguments:**
- `--state`: State code for campaign mode (e.g., WI)
- `--district`: District NCES ID for single enrichment
- `--year`: School year (default: 2025-26)
- `--target`: Districts per state (default: 3)
- `--status`: Show overall campaign status

**Features:**
- **Auto-query**: Fetches top 9 districts by enrollment from database
- **Pre-populate**: Generates search queries automatically
- **Interactive prompts**: Single-command data entry for elementary/middle/high
- **Auto-commit**: Saves directly to database
- **Progress tracking**: Shows enrichment progress in real-time
- **Firewall detection**: Handles blocked districts gracefully

**Workflow:**
1. Script queries database for top unenriched districts in state
2. For each district, displays info and search query
3. User collects bell schedule data from web
4. Interactive prompts for instructional minutes, start/end times
5. Auto-saves to database
6. Continues until 3 successful enrichments or user quits

**Example Session:**
```
============================================================
State Campaign: WI
============================================================
Current progress: 0/3 districts enriched

Found 9 candidates (ranks 1-9 by enrollment)

[Rank #1] Milwaukee Public Schools (WI)
  NCES ID: 5560580
  Enrollment: 75,568

  Search query: "Milwaukee Public Schools" bell schedule 2025-26

  [E]nrich, [S]kip, [B]locked, [Q]uit? e

📋 Collecting schedule data for Milwaukee Public Schools...
   Year: 2025-26
   Enter 's' to skip a level, 'b' if blocked by firewall

  ELEMENTARY:
  Instructional minutes: 360
  Start time (e.g., 8:00 AM): 8:00 AM
  End time (e.g., 3:00 PM): 3:00 PM

  MIDDLE:
  Instructional minutes: 365
  ...

  Source URL (optional): https://mps.milwaukee.k12.wi.us/bell-schedule

  ✓ Saved 3 schedule(s) to database

  Progress: 1/3
```

See `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md` for manual collection procedures.

---

### Utility Scripts

#### `utilities/generate_data_dictionary.py` ⭐ NEW (December 2025)

Auto-generate Markdown data dictionary from SQLAlchemy database models.

**Usage:**
```bash
# Generate data dictionary
python generate_data_dictionary.py

# Check output
cat docs/data-dictionaries/database_schema_latest.md
```

**Outputs:**
- `docs/data-dictionaries/database_schema_<timestamp>.md` - Timestamped version
- `docs/data-dictionaries/database_schema_latest.md` - Symlink to latest

**Generated Documentation:**
- Table descriptions
- Column names, types, constraints
- Primary and foreign keys
- Relationships between tables
- Check constraints
- Index information

**Features:**
- **Automatic**: Introspects SQLAlchemy models
- **Up-to-date**: Always reflects current schema
- **Versioned**: Timestamped copies for history
- **Formatted**: Clean Markdown tables

**Example Output:**
```markdown
## districts

Primary table containing all U.S. school districts.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| nces_id | VARCHAR(20) | NO | - | Primary key, NCES district ID |
| name | VARCHAR(255) | NO | - | District name |
| state | VARCHAR(2) | NO | - | Two-letter state code |
| enrollment | INTEGER | YES | - | Total K-12 enrollment |
...

**Relationships:**
- Has many: bell_schedules, lct_calculations

**Indexes:**
- idx_districts_state (state)
- idx_districts_enrollment (enrollment)
```

**When to Run:**
- After schema changes (new tables, columns)
- Before major releases (documentation update)
- For onboarding (share with collaborators)

---

## Pipelines

### `pipelines/full_pipeline.py`

Run the complete data processing pipeline.

**Usage:**
```bash
# Full pipeline with sample data
python full_pipeline.py --year 2023-24 --sample

# Full pipeline with real data
python full_pipeline.py --year 2023-24

# Skip download (use existing data)
python full_pipeline.py --year 2023-24 --skip-download

# Save log to file
python full_pipeline.py --year 2023-24 --log-file pipeline.log
```

**Pipeline Steps:**
1. **Download**: Fetch data from NCES
2. **Extract**: Combine multi-part files if present
3. **Normalize**: Convert to standard schema
4. **Calculate**: Compute LCT metrics

**Arguments:**
- `--year`: School year (required)
- `--sample`: Use sample data
- `--skip-download`: Skip download step
- `--log-file`: Save log output to file

---

## Utilities

### `infrastructure/utilities/common.py`

Shared utility functions used across scripts.

**Key Functions:**

#### State Handling
```python
from common import standardize_state, get_state_name

standardize_state('California')  # Returns 'CA'
get_state_name('CA')  # Returns 'California'
```

#### Data Validation
```python
from common import validate_required_columns

if validate_required_columns(df, ['enrollment', 'staff'], 'my_data'):
    # Process data
```

#### Safe Operations
```python
from common import safe_divide, format_number

lct = safe_divide(total_minutes, enrollment, default=0)
print(format_number(1234567, 2))  # "1,234,567.00"
```

#### Configuration
```python
from common import load_yaml_config, save_yaml_config

config = load_yaml_config('config/settings.yaml')
save_yaml_config(data, 'output/results.yaml')
```

#### Data Processing Base Class
```python
from common import DataProcessor

class MyProcessor(DataProcessor):
    def process(self, input_file):
        df = self.load_data(input_file)
        # ... processing ...
        self.save_data(df, output_file)
```

---

## Development Workflow

### Testing Individual Scripts

Test each script with sample data before running on full datasets:

```bash
# 1. Create sample data
python download/fetch_nces_ccd.py --year 2023-24 --sample

# 2. Test normalization
python transform/normalize_districts.py \
  data/raw/federal/nces-ccd/2023_24/sample_districts.csv \
  --source nces --year 2023-24

# 3. Test LCT calculation
python analyze/calculate_lct.py \
  data/processed/normalized/districts_2023_24_nces.csv \
  --summary
```

### Running Tests

```bash
cd infrastructure/quality-assurance/tests
pytest test_utilities.py -v
```

### Debugging

Use Python's logging for debugging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or set environment variable:
```bash
export LOG_LEVEL=DEBUG
python script.py
```

---

## Common Workflows

### Process New Year of Data

```bash
# Download latest NCES data
python download/fetch_nces_ccd.py --year 2024-25

# Check for multi-part files
python extract/split_large_files.py data/raw/federal/nces-ccd/2024_25/

# Normalize
python transform/normalize_districts.py \
  data/raw/federal/nces-ccd/2024_25/districts_combined.csv \
  --source nces --year 2024-25

# Calculate LCT
python analyze/calculate_lct.py \
  data/processed/normalized/districts_2024_25_nces.csv \
  --summary
```

### Add State Data

```bash
# 1. Download state data (manual or custom script)
# 2. Place in data/raw/state/{state_name}/

# 3. Normalize with state-specific mapping
python transform/normalize_districts.py \
  data/raw/state/california/districts_2024.csv \
  --source state --state CA --year 2023-24

# 4. Combine with federal data (manual merge or custom script)
```

### Update State Requirements

Edit `config/state-requirements.yaml`:

```yaml
states:
  new_state:
    elementary: 300
    high_school: 330
    notes: "Source: State Ed Code Section 123"
```

Then recalculate LCT for affected districts.

---

## Troubleshooting

### Multi-Part Files Not Detected

Ensure files follow naming pattern: `basename_N.ext` where N is a number.

Examples that work:
- `districts_1.csv`, `districts_2.csv`
- `enrollment_part1.txt`, `enrollment_part2.txt`

Examples that don't work:
- `districtsA.csv`, `districtsB.csv` (letters, not numbers)
- `districts-1.csv` (dash instead of underscore)

### Column Not Found Errors

Check that your source data matches expected column names. Update column mappings in `normalize_districts.py` for your specific data format.

### Memory Issues with Large Files

Use `dask` for very large datasets:

```python
import dask.dataframe as dd
df = dd.read_csv('large_file.csv')
```

Or process in chunks:

```python
for chunk in pd.read_csv('file.csv', chunksize=10000):
    process(chunk)
```

---

## Best Practices

1. **Always test with sample data first**
2. **Check data lineage files** for processing history
3. **Validate at each step** before proceeding
4. **Keep raw data unchanged** - only modify processed copies
5. **Document custom state mappings** in code comments
6. **Use consistent year format** (YYYY-YY, e.g., 2023-24)
7. **Run tests** after modifying utility functions

---

## Adding New Scripts

When creating new scripts:

1. **Use standard template**:
```python
#!/usr/bin/env python3
"""
Script description

Usage:
    python script.py <args>
"""

import argparse
import logging
from pathlib import Path
import sys

# Add utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "infrastructure" / "utilities"))
from common import setup_logging

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="...")
    # ... arguments ...
    args = parser.parse_args()
    
    setup_logging()
    logger.info("Starting...")
    
    # ... processing ...
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

2. **Add to pipeline** if appropriate
3. **Write tests** in `infrastructure/quality-assurance/tests/`
4. **Document** in this README
5. **Make executable**: `chmod +x script.py`

---

## Getting Help

- Check script docstring: `python script.py --help`
- Review example usage in this README
- Look at test files for usage examples
- Check project documentation in `docs/`

---

## Recent Additions (December 2025)

### Efficiency Enhancement Suite (Dec 27-28, 2025)

Seven new capabilities added to improve workflow efficiency:

1. **`calculate_lct_variants.py`** - All 7 LCT variants with QA dashboard
2. **`interactive_enrichment.py`** - Interactive CLI for state campaigns
3. **`generate_data_dictionary.py`** - Auto-generate schema documentation
4. **Materialized views** - Pre-computed queries for fast lookups
5. **Parquet export** - 70-80% file size reduction for large datasets
6. **Incremental calculations** - Smart recalculation of changed data only
7. **Calculation tracking** - Database-backed run history and QA reports

**Impact**:
- Token efficiency: Query-specific data vs. loading full files
- Campaign efficiency: Single-session state completion (Option A protocol)
- QA automation: Real-time validation with hierarchy checks
- Documentation: Auto-generated, always up-to-date

See `docs/QA_DASHBOARD.md` and `docs/DATABASE_SETUP.md` for detailed documentation.

---

*Last Updated: December 28, 2025*
