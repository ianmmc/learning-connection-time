# Getting Started with Instructional Minute Metric

## Welcome!

This guide will help you get the project up and running and begin calculating Learning Connection Time (LCT) for school districts.

## Prerequisites

- **Python 3.11+** installed
- **Git** installed (for version control)
- Basic familiarity with command line
- Text editor or IDE (VS Code, PyCharm, etc.)

## Step 1: Complete Directory Structure

The project has been initialized, but you need to create the full directory structure:

```bash
cd /Users/ianmmc/Development/instructional_minute_metric
python3 setup_structure.py
```

This will create all necessary directories for data, scripts, notebooks, etc.

## Step 2: Set Up Python Environment

### Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Verify activation (should show venv in prompt)
which python
```

### Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt
```

This will take several minutes as it installs pandas, dask, and other data tools.

## Step 3: Initialize Git Repository

```bash
# Initialize git
git init

# Add all files
git add .

# First commit
git commit -m "Initial project structure"

# Optional: Create GitHub repo and push
```

## Step 4: Review Documentation

Before diving into code, familiarize yourself with:

### Core Documents
- `README.md` - Project overview
- `docs/PROJECT_CONTEXT.md` - Mission and background
- `docs/DATA_SOURCES.md` - Where to get data
- `docs/METHODOLOGY.md` - How LCT is calculated

### Configuration Files
- `config/data-sources.yaml` - Data source configuration
- `config/state-requirements.yaml` - Instructional time by state

## Step 5: Download Your First Dataset

### Option A: Manual Download (Recommended for first time)

1. Visit [NCES CCD Download Page](https://nces.ed.gov/ccd/files.asp)
2. Select year 2022-23
3. Download these files:
   - **Directory** (district information)
   - **Membership** (enrollment data)
   - **Staff** (teacher counts)
4. Save to: `data/raw/federal/nces-ccd/2022-23/`

### Option B: Implement Download Script

Create `infrastructure/scripts/download/fetch-nces-ccd.py`:

```python
#!/usr/bin/env python3
"""Download NCES CCD data"""

import requests
from pathlib import Path

# Implementation needed
# See docs/DATA_SOURCES.md for URLs and formats
```

## Step 6: Handle Multi-Part Files

Many NCES files are split into parts (e.g., `membership_1.txt`, `membership_2.txt`).

The project includes a utility script to handle this:

```bash
# Example usage (once you have data)
python3 infrastructure/scripts/extract/split-large-files.py \
    data/raw/federal/nces-ccd/2022-23/
```

This will combine multi-part files into single files for processing.

## Step 7: Start with a Sample District

Rather than processing all districts at once, start with a few for testing:

### Create a Sample Dataset

```bash
# Create a test directory
mkdir -p data/raw/test/

# Manually create a small CSV with a few districts:
# - Los Angeles Unified
# - New York City DOE
# - Chicago Public Schools
```

Example `test-districts.csv`:
```csv
leaid,district_name,state,enrollment,teachers
0600001,Los Angeles Unified,CA,420000,21000
3600001,New York City DOE,NY,900000,75000
1700001,Chicago Public Schools,IL,330000,21000
```

## Step 8: Build Your First Processing Script

Create `infrastructure/scripts/transform/normalize-basic.py`:

```python
#!/usr/bin/env python3
"""
Normalize basic district data into standard schema
"""

import pandas as pd
from pathlib import Path

def normalize_ccd_data(input_path, output_path):
    """
    Read CCD files and create normalized dataset
    """
    # Implementation here
    pass

if __name__ == "__main__":
    # Test with sample data
    normalize_ccd_data(
        "data/raw/test/test-districts.csv",
        "data/processed/normalized/districts-basic.csv"
    )
```

## Step 9: Calculate Your First LCT

Use the provided calculator:

```bash
# View the calculator code
cat src/python/calculators/lct_calculator.py

# Create a simple script to test it
python3 -c "
from src.python.calculators import lct_calculator

# Example: 5000 students, 250 teachers, 360 min/day
lct = lct_calculator.calculate_lct(5000, 250, 360)
print(f'LCT: {lct} minutes per student per day')
print(f'LCT: {lct/60:.1f} hours per student per day')
"
```

## Step 10: Start a Jupyter Notebook

Jupyter notebooks are great for exploration:

```bash
# Start Jupyter Lab
jupyter lab

# Navigate to notebooks/exploratory/
# Create a new notebook: "01-initial-exploration.ipynb"
```

In your notebook:

```python
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load your test data
df = pd.read_csv('data/raw/test/test-districts.csv')

# Calculate LCT
# (Implementation)

# Visualize
plt.figure(figsize=(10, 6))
sns.barplot(data=df, x='district_name', y='lct')
plt.title('Learning Connection Time by District')
plt.ylabel('Minutes per student per day')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```

## Common Workflows

### Daily Development Workflow

```bash
# 1. Activate environment
source venv/bin/activate

# 2. Pull latest (if using git)
git pull

# 3. Work on scripts or notebooks

# 4. Run tests
pytest infrastructure/quality-assurance/tests/

# 5. Commit progress
git add .
git commit -m "Description of work"

# 6. Deactivate when done
deactivate
```

### Data Processing Workflow

```
1. Download raw data → data/raw/federal/nces-ccd/[year]/
2. Extract/combine → Use split-large-files.py
3. Normalize → data/processed/normalized/
4. Merge datasets → data/processed/merged/
5. Calculate LCT → data/enriched/lct-calculations/
6. Generate reports → data/exports/reports/
```

## Development Tips

### Start Small
- Begin with 3-5 test districts
- Get one data source working completely
- Then scale to more districts/sources

### Document as You Go
- Keep notes in `docs/chat-history/`
- Document issues in `infrastructure/quality-assurance/issues/`
- Update configuration files as you learn

### Use Version Control
- Commit often with clear messages
- Create branches for experimental work
- Tag releases when you reach milestones

### Test Everything
- Write tests in `infrastructure/quality-assurance/tests/`
- Validate data at every stage
- Use sample data for development

## Next Milestones

### Milestone 1: Basic Pipeline
- [ ] Download NCES CCD data for one year
- [ ] Handle multi-part files
- [ ] Normalize to standard schema
- [ ] Calculate LCT for top 10 districts
- [ ] Create basic visualization

### Milestone 2: Multiple Years
- [ ] Process 2020-21, 2021-22, 2022-23
- [ ] Track year-over-year changes
- [ ] Identify trends

### Milestone 3: Add CRDC Data
- [ ] Download CRDC 2020-21
- [ ] Merge with CCD data
- [ ] Calculate school-level LCT where possible

### Milestone 4: Add State Data
- [ ] California
- [ ] Texas
- [ ] New York
- [ ] Florida

### Milestone 5: Analysis & Reporting
- [ ] Generate district profiles
- [ ] Create comparative analysis
- [ ] Build dashboard/visualization
- [ ] Write analysis report

## Troubleshooting

### "Module not found" errors
```bash
# Make sure venv is activated
source venv/bin/activate

# Reinstall requirements
pip install -r requirements.txt
```

### Data file encoding issues
```bash
# Try specifying encoding when reading
pd.read_csv('file.csv', encoding='latin-1')
```

### Memory issues with large files
```bash
# Use dask instead of pandas
import dask.dataframe as dd
df = dd.read_csv('large_file.csv')
```

## Getting Help

- **Documentation**: Check the `docs/` folder first
- **Issues**: Look at `infrastructure/quality-assurance/issues/`
- **Project Context**: Review `docs/PROJECT_CONTEXT.md` for methodology questions
- **Data Sources**: See `docs/DATA_SOURCES.md` for data access help

## Quick Reference

### Key Commands

```bash
# Activate environment
source venv/bin/activate

# Run a script
python3 infrastructure/scripts/download/fetch-nces-ccd.py

# Start Jupyter
jupyter lab

# Run tests
pytest

# Check code style
black src/
flake8 src/
```

### Key Directories

```
data/raw/              # Downloaded data (never modified)
data/processed/        # Cleaned and normalized
data/enriched/         # With calculated LCT
infrastructure/scripts/  # All processing scripts
notebooks/             # Jupyter notebooks
src/python/            # Core library code
```

### Key Files

```
config/data-sources.yaml        # Data source configuration
config/state-requirements.yaml  # Instructional time by state
docs/METHODOLOGY.md            # LCT calculation details
docs/DATA_SOURCES.md           # Where to get data
```

---

**Ready to begin!** Start with Step 1 and work through sequentially.

**Questions?** Review the documentation in `docs/` or check the project context.

---

*Created: December 16, 2025*  
*Project: Instructional Minute Metric*  
*Status: Ready for development*
