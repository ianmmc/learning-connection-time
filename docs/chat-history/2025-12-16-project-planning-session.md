# Instructional Minute Metric Project Structure Plan

## Project Overview
Creating a data pipeline for calculating Learning Connection Time (LCT) and related metrics from Federal and State education datasets.

## Directory Structure

```
/Development/learning-connection-time/
├── README.md
├── .gitignore
├── config/
│   ├── data-sources.yaml          # Configuration for all data sources
│   ├── state-requirements.yaml    # State-specific instructional time requirements
│   └── processing-rules.yaml      # Data transformation rules
│
├── data/
│   ├── raw/                       # Untouched source data
│   │   ├── federal/
│   │   │   ├── nces-ccd/         # Common Core of Data
│   │   │   │   ├── 2022-23/
│   │   │   │   ├── 2023-24/
│   │   │   │   └── README.md
│   │   │   ├── crdc/             # Civil Rights Data Collection
│   │   │   │   ├── 2020-21/
│   │   │   │   ├── 2021-22/
│   │   │   │   └── README.md
│   │   │   └── metadata/
│   │   │       ├── data-dictionaries/
│   │   │       └── schemas/
│   │   │
│   │   └── state/
│   │       ├── california/
│   │       ├── texas/
│   │       ├── new-york/
│   │       └── [other-states]/
│   │
│   ├── processed/                 # Cleaned, standardized data
│   │   ├── normalized/           # Standard schema across sources
│   │   ├── merged/               # Combined datasets
│   │   └── validated/            # Quality-checked data
│   │
│   ├── enriched/                  # Data with calculated metrics
│   │   ├── lct-calculations/
│   │   ├── district-profiles/
│   │   └── comparative-analysis/
│   │
│   └── exports/                   # Final outputs for analysis
│       ├── csv/
│       ├── json/
│       └── reports/
│
├── docs/
│   ├── PROJECT_CONTEXT.md
│   ├── DATA_SOURCES.md           # Comprehensive list of data sources
│   ├── METHODOLOGY.md            # LCT calculation methodology
│   ├── data-dictionaries/        # Unified data dictionaries
│   ├── analysis-reports/         # Research findings
│   └── chat-history/             # Development session logs
│
├── infrastructure/
│   ├── scripts/
│   │   ├── download/             # Data acquisition scripts
│   │   │   ├── fetch-nces-ccd.py
│   │   │   ├── fetch-crdc.py
│   │   │   └── fetch-state-data.py
│   │   │
│   │   ├── extract/              # Data extraction from various formats
│   │   │   ├── parse-excel.py
│   │   │   ├── parse-csv.py
│   │   │   ├── parse-text.py
│   │   │   └── split-large-files.py
│   │   │
│   │   ├── transform/            # Data cleaning and normalization
│   │   │   ├── normalize-schema.py
│   │   │   ├── clean-data.py
│   │   │   ├── validate-data.py
│   │   │   └── merge-datasets.py
│   │   │
│   │   └── analyze/              # Metric calculations
│   │       ├── calculate-lct.py
│   │       ├── generate-profiles.py
│   │       └── compare-districts.py
│   │
│   ├── quality-assurance/
│   │   ├── tests/
│   │   │   ├── test-data-integrity.py
│   │   │   ├── test-calculations.py
│   │   │   └── test-transformations.py
│   │   └── validation-rules.yaml
│   │
│   └── utilities/
│       ├── file-utils.py
│       ├── state-mappings.py
│       └── logging-config.py
│
├── notebooks/                     # Jupyter notebooks for exploration
│   ├── exploratory/
│   ├── validation/
│   └── visualization/
│
├── src/                          # Core library code
│   ├── python/
│   │   ├── __init__.py
│   │   ├── data_loader.py
│   │   ├── processors/
│   │   │   ├── __init__.py
│   │   │   ├── nces_processor.py
│   │   │   ├── crdc_processor.py
│   │   │   └── state_processor.py
│   │   ├── calculators/
│   │   │   ├── __init__.py
│   │   │   ├── lct_calculator.py
│   │   │   └── metrics.py
│   │   └── exporters/
│   │       ├── __init__.py
│   │       └── report_generator.py
│   │
│   └── sql/                      # SQL queries for data processing
│       ├── schema.sql
│       └── queries/
│
├── pipelines/                    # Automated data pipelines
│   ├── full-refresh.py
│   ├── incremental-update.py
│   └── schedule-config.yaml
│
└── outputs/                      # Generated artifacts
    ├── visualizations/
    ├── reports/
    └── datasets/
```

## Key Design Principles

### 1. **Separation of Raw and Processed Data**
- Never modify raw data files
- All raw data includes README.md with source, date, and acquisition method
- Processed data lives in separate directories with clear lineage

### 2. **Multi-part File Handling**
As you noted, some datasets are split across multiple files (e.g., `_1`, `_2`, `_3`):
- Store multi-part files in subdirectories: `data/raw/federal/nces-ccd/2023-24/enrollment/`
- Include a manifest file listing all parts and their order
- Scripts automatically detect and concatenate multi-part files

### 3. **State-by-State Organization**
Each state gets its own directory under `data/raw/state/[state-name]/` containing:
- Raw data files
- State-specific metadata
- Instructional time requirements
- District mapping files

### 4. **Metadata First**
Every data directory includes:
- README.md with source attribution and dates
- Schema documentation
- Data dictionary
- Known issues or limitations

### 5. **Incremental Processing**
Scripts designed to:
- Process new data without re-processing everything
- Validate before overwriting
- Maintain processing logs
- Support resume-on-failure

## Initial Data Sources Priority

### Federal (Highest Priority)
1. **NCES Common Core of Data (CCD)**
   - District-level enrollment
   - Staff counts by role
   - School characteristics
   
2. **Civil Rights Data Collection (CRDC)**
   - Detailed enrollment by demographics
   - Teacher assignments
   - Class sizes

### State (Phased Approach)
Start with states that have:
1. Good data availability
2. Large populations (impact)
3. Variety in instructional time requirements

Suggested Phase 1 states:
- California (largest population, good data)
- Texas (large, different requirements)
- New York (large, good reporting)
- Florida (large, growing)

## Technology Stack

### Core Processing
- **Python 3.11+** (primary)
- **pandas** for data manipulation
- **dask** for large datasets
- **sqlalchemy** for database operations

### Data Storage
- **PostgreSQL** (optional, for complex queries)
- **CSV/Parquet** for intermediate files
- **JSON** for configuration

### Quality Assurance
- **pytest** for testing
- **great_expectations** for data validation
- **pre-commit** hooks for code quality

## Getting Started Checklist

1. ✅ Create directory structure
2. ⬜ Set up Python virtual environment
3. ⬜ Create data source configuration
4. ⬜ Download sample datasets
5. ⬜ Build extraction scripts
6. ⬜ Develop normalization pipeline
7. ⬜ Implement LCT calculations
8. ⬜ Create validation tests
9. ⬜ Generate first district profiles
10. ⬜ Document findings

## Next Steps

1. **Review this structure** - adjust based on needs
2. **Execute setup script** - creates all directories
3. **Configure data sources** - document where to get each dataset
4. **Start with sample data** - test with 1-2 districts before scaling
5. **Build incrementally** - get one source working before adding others

---

*Created: December 16, 2025*
*Related Project: Reducing the Ratio (Learning Connection Time initiative)*
