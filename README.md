# Instructional Minute Metric

> Calculating Learning Connection Time (LCT) from public education datasets

---

## 📋 Essential Resources

- **[QUICKSTART.md](QUICKSTART.md)** - Get running in 2 minutes with sample data
- **[Claude.md](Claude.md)** - Complete project briefing for Claude Code
- **[Infrastructure Scripts README](infrastructure/scripts/README.md)** - Comprehensive script documentation

---

## Overview

This project processes Federal and State education data to calculate meaningful metrics about student access to individual teacher attention, reframing traditional student-to-teacher ratios into more tangible "Learning Connection Time" measurements.

## Project Mission

Transform abstract student-to-teacher ratios into tangible metrics that tell the story of students getting shortchanged rather than teachers getting burdened.

## Learning Connection Time (LCT)

**Formula**: 
```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Example**:
- District: 5,000 students, 250 teachers, 360 min/day instruction
- LCT = (360 × 250) / 5000 = **18 minutes per student per day**

This reframes "20:1 student-teacher ratio" into a more tangible equity metric.

## Quick Start

```bash
# Set up environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test with sample data (2 minutes)
python3 pipelines/full_pipeline.py --year 2023-24 --sample

# View results
cat data/processed/normalized/districts_2023_24_nces_with_lct_summary.txt
```

**See [QUICKSTART.md](QUICKSTART.md) for detailed setup and first steps.**

## Project Structure

```
learning-connection-time/
├── data/               # Raw → processed → enriched → exports
├── docs/               # Documentation and analysis reports
├── infrastructure/     # Data pipeline scripts
│   ├── scripts/       # Download, extract, transform, analyze
│   ├── utilities/     # Common functions
│   └── quality-assurance/tests/
├── pipelines/         # End-to-end workflows
├── notebooks/         # Jupyter for exploration
├── outputs/           # Generated artifacts
└── src/               # Core library code
```

## Key Features

### ✅ Complete Processing Pipeline
- **Download**: Fetch NCES CCD and state data
- **Enrich**: Gather actual bell schedules from district websites ⭐ NEW
- **Extract**: Handle multi-part files automatically
- **Transform**: Normalize to standard schema
- **Analyze**: Calculate LCT with derived metrics

### ✅ Multi-Part File Handling
Automatically detects and concatenates files split across multiple parts:
- `filename_1.csv`, `filename_2.csv`, `filename_3.csv` → `filename_combined.csv`

### ✅ Actual vs. Statutory Instructional Time
- **Tier 1**: Detailed bell schedule collection from top districts
- **Tier 2**: Automated web search with fallback
- **Tier 3**: State statutory requirements (240-420 min/day range)
- Quality tracking with confidence levels
- Phased rollout: CA, TX, NY, FL first

### ✅ Data Quality
- Validation at every pipeline stage
- Comprehensive test suite
- Processing logs and lineage tracking

## Data Sources

### Priority Federal Sources
- **NCES Common Core of Data (CCD)**: Annual district enrollment, staff counts
- **Civil Rights Data Collection (CRDC)**: Biennial, detailed class-level data

### Priority State Sources
1. **California** - DataQuest API
2. **Texas** - PEIMS data
3. **New York** - NYSED data portal
4. **Florida** - State reports

## Development Workflow

### For New Development
1. **Start here**: Read [Claude.md](Claude.md) for full context
2. **Test with sample data**: See [QUICKSTART.md](QUICKSTART.md)
3. **Review scripts**: Check [infrastructure/scripts/README.md](infrastructure/scripts/README.md)
4. **Write tests**: Add to `infrastructure/quality-assurance/tests/`
5. **Document**: Log sessions in `docs/chat-history/`

### Running the Pipeline

**Sample data (testing):**
```bash
python pipelines/full_pipeline.py --year 2023-24 --sample
```

**Real data (production):**
```bash
# Full pipeline (basic)
python pipelines/full_pipeline.py --year 2023-24

# Full pipeline with bell schedule enrichment
python pipelines/full_pipeline.py --year 2023-24 --enrich-bell-schedules --tier 1

# Or step-by-step:
python infrastructure/scripts/download/fetch_nces_ccd.py --year 2023-24
python infrastructure/scripts/enrich/fetch_bell_schedules.py districts.csv --tier 1 --year 2023-24
python infrastructure/scripts/extract/split_large_files.py data/raw/federal/nces-ccd/2023_24/
python infrastructure/scripts/transform/normalize_districts.py input.csv --source nces --year 2023-24
python infrastructure/scripts/analyze/calculate_lct.py input.csv --summary
```

## Documentation

### Essential Reading
- **[PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md)** - Mission, strategy, evolution plan
- **[METHODOLOGY.md](docs/METHODOLOGY.md)** - Calculation approach and limitations
- **[BELL_SCHEDULE_SAMPLING_METHODOLOGY.md](docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md)** - Bell schedule collection methodology ⭐ NEW
- **[DATA_SOURCES.md](docs/DATA_SOURCES.md)** - Where to get data
- **[Scripts README](infrastructure/scripts/README.md)** - All scripts documented

### Configuration
- `config/data-sources.yaml` - Data source URLs and access
- `config/state-requirements.yaml` - State instructional time requirements

## Testing

```bash
# Run test suite
cd infrastructure/quality-assurance/tests
pytest test_utilities.py -v

# Test individual utilities
python infrastructure/utilities/common.py
```

## VS Code Tasks

Press `Cmd+Shift+P` → "Run Task" to access:
- **Run Sample Pipeline** - Quick test with sample data
- **Run Full Pipeline** - Process real data
- **Download NCES Sample Data** - Get test data
- **Run Tests** - Execute test suite
- **Make Scripts Executable** - Fix permissions

## Related Projects

- **OneRoster Integration**: Direct SIS access for live calculations
- **React Prototype**: Real-time LCT visualization
- **Reducing the Ratio**: Educational equity initiative

## Methodology & Limitations

We acknowledge the LCT metric has methodological challenges:
- **Individualization fallacy**: Assumes all time could be one-on-one
- **Time-as-quality assumption**: More time ≠ automatically better  
- **Averaging deception**: District metrics mask within-district disparities

See [METHODOLOGY.md](docs/METHODOLOGY.md) for the 6-phase evolution strategy addressing these limitations.

## Technology Stack

- **Python 3.11+** - Core processing
- **pandas/dask** - Data manipulation
- **PyYAML** - Configuration
- **pytest** - Testing
- **Jupyter** - Exploration
- **PostgreSQL** - Optional for complex queries

## Current Status

**Infrastructure**: ✅ Complete
**Sample Pipeline**: ✅ Tested
**Real Data Processing**: 🔄 Ready for development
**Next Milestone**: Complete analysis of top 25 largest districts

## Contributing

1. Work on one data source at a time
2. Test with sample data first
3. Document in `docs/chat-history/`
4. Run tests before committing
5. Follow existing code patterns

## License

Educational research purposes. Data subject to original source licenses.

---

**Created**: December 16, 2025  
**Last Updated**: December 16, 2025  
**Status**: Ready for active development  
**Target**: Top 100-200 U.S. school districts

**Need help?** Start with [QUICKSTART.md](QUICKSTART.md) or [Claude.md](Claude.md)
