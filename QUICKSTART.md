# Quick Start Guide

Get up and running with the Instructional Minute Metric project in minutes.

## First Time Setup

### 1. Python Environment
```bash
cd /Users/ianmmc/Development/instructional_minute_metric
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Verify Installation
```bash
# Test utilities module
python infrastructure/utilities/common.py

# Should see test output confirming everything works
```

### 3. Make Scripts Executable (Optional)
```bash
python infrastructure/scripts/make_executable.py
```

## Test the Pipeline with Sample Data

### Quick Test (2 minutes)
```bash
# Run complete pipeline with sample data
python pipelines/full_pipeline.py --year 2023-24 --sample
```

This will:
- ✅ Create sample data (3 districts)
- ✅ Normalize to standard schema
- ✅ Calculate LCT metrics
- ✅ Generate summary statistics

### Verify Output
```bash
# Check normalized data
ls -lh data/processed/normalized/

# Check LCT results
cat data/processed/normalized/districts_2023_24_nces_with_lct_summary.txt
```

## Your First Real Data Processing

### Step 1: Download NCES Data
```bash
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24
```

**Note**: This will attempt to download from NCES. URLs may need updating based on actual 2023-24 data availability.

### Step 2: Handle Multi-Part Files (if present)
```bash
python infrastructure/scripts/extract/split_large_files.py data/raw/federal/nces-ccd/2023_24/
```

### Step 3: Normalize the Data
```bash
python infrastructure/scripts/transform/normalize_districts.py \
  data/raw/federal/nces-ccd/2023_24/districts.csv \
  --source nces \
  --year 2023-24
```

### Step 4: Calculate LCT
```bash
python infrastructure/scripts/analyze/calculate_lct.py \
  data/processed/normalized/districts_2023_24_nces.csv \
  --summary
```

### Step 5: View Results
```bash
# CSV with all calculations
open data/processed/normalized/districts_2023_24_nces_with_lct.csv

# Summary statistics
cat data/processed/normalized/districts_2023_24_nces_with_lct_summary.txt
```

## Common Tasks

### Add a New State's Instructional Time Requirements
Edit `config/state-requirements.yaml`:
```yaml
states:
  nevada:
    elementary: 300
    middle_school: 330
    high_school: 330
    notes: "Source: NRS 388.090"
```

### Test a Script Individually
```bash
# Download script help
python infrastructure/scripts/download/fetch_nces_ccd.py --help

# Normalize with validation only (no output)
python infrastructure/scripts/transform/normalize_districts.py \
  input.csv --source nces --year 2023-24 --validate-only
```

### Run Tests
```bash
cd infrastructure/quality-assurance/tests
pytest test_utilities.py -v
```

## Exploring the Data

### Start Jupyter
```bash
jupyter lab
```

Then create a notebook in `notebooks/exploratory/`:
```python
import pandas as pd
import sys
from pathlib import Path

# Add utilities to path
sys.path.insert(0, str(Path.cwd().parent.parent / "infrastructure" / "utilities"))
from common import standardize_state, format_number

# Load LCT results
df = pd.read_csv('../../data/processed/normalized/districts_2023_24_nces_with_lct.csv')

# Explore
df.head()
df['lct_minutes'].describe()
df.groupby('state')['lct_minutes'].mean()
```

## Troubleshooting

### Scripts Not Found
Make sure you're in the project root:
```bash
cd /Users/ianmmc/Development/instructional_minute_metric
pwd  # Should show the project directory
```

### Import Errors
Activate the virtual environment:
```bash
source venv/bin/activate
which python  # Should show path to venv
```

### Permission Errors
```bash
python infrastructure/scripts/make_executable.py
```

### Data Not Found
Scripts create sample data automatically. For real data:
1. Check URLs in download scripts are current
2. Verify you have internet connection
3. Check NCES website for data availability

## Next Steps

1. **Review the full context**: Read `Claude.md` for complete project understanding
2. **Check documentation**: See `docs/PROJECT_CONTEXT.md`, `docs/METHODOLOGY.md`
3. **Start developing**: Pick a priority from the "Immediate Next Steps" in `Claude.md`

## Getting Help

- **Script usage**: `python script.py --help`
- **Comprehensive docs**: `infrastructure/scripts/README.md`
- **Project briefing**: `Claude.md`
- **Tests for examples**: `infrastructure/quality-assurance/tests/`

---

**Ready to build!** 🚀

The infrastructure is complete and tested. You can now:
- Process real data from NCES
- Add state-specific data sources
- Build district profiles
- Generate comparative analysis
- Create visualizations

Start with sample data to understand the workflow, then scale to real datasets.
