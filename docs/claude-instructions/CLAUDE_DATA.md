# CLAUDE_DATA.md - Data Architecture and SEA Integrations

Load this appendix when working with data sources, SEA integrations, or crosswalks.

---

## Data Architecture: Layered Integration

```
┌─────────────────────────────────────────────────────┐
│                    Layer 2: SEA Data                │
│   (FLDOE, TEA, CDE, NYSED - state-specific data)   │
├─────────────────────────────────────────────────────┤
│              Layer 1: NCES CCD Foundation           │
│     (17,842 districts, enrollment, staffing)        │
└─────────────────────────────────────────────────────┘
```

**Why This Architecture?**
1. **Consistency**: NCES CCD provides uniform baseline
2. **Enrichment**: SEA data adds state-specific details
3. **Validation**: Cross-reference federal and state data
4. **Flexibility**: States added incrementally

---

## Data Sources

### Federal Sources
| Source | Description | Best For |
|--------|-------------|----------|
| NCES CCD | Annual data for all public schools/districts | District-level metrics |
| CRDC | Biennial survey, class-level detail | Fine-grained analysis |

### State Sources (Priority)
1. **California** - DataQuest API
2. **Texas** - PEIMS data
3. **New York** - NYSED data portal
4. **Florida** - Good reporting

---

## District ID Crosswalk

| State | ID Format | Example |
|-------|-----------|---------|
| FL | 2-digit | `"13"` (Miami-Dade) |
| TX | TX-XXXXXX | `"TX-101912"` (Houston ISD) |
| CA | XX-XXXXX | `"19-64733"` (Los Angeles Unified) |
| NY | 12-digit | `"310200010000"` (NYC) |
| IL | RR-CCC-DDDD-TT | `"15-016-2990-25"` (Chicago) |
| MI | 5-digit | `"82015"` (Detroit) |
| PA | 9-digit AUN | `"126515001"` (Philadelphia) |
| VA | 3-digit | `"029"` (Fairfax County) |
| MA | 4-digit | `"0035"` (Boston) |

**NCES LEAID**: 7-digit federal identifier (e.g., `"0622710"` for LA Unified)

---

## SEA Integrations (9 Complete)

| State | Agency | Test File | Districts | Coverage |
|-------|--------|-----------|-----------|----------|
| FL | FLDOE | `test_florida_integration.py` | 82 | ~95% |
| TX | TEA | `test_texas_integration.py` | 1,234 | TBD |
| CA | CDE | `test_california_integration.py` | 1,037 | TBD |
| NY | NYSED | `test_new_york_integration.py` | 800+ | TBD |
| IL | ISBE | `test_illinois_integration.py` | 858 | TBD |
| MI | MDE | `test_michigan_integration.py` | 836 | 93.9% |
| PA | PDE | `test_pennsylvania_integration.py` | 777 | 99.5% |
| VA | VDOE | `test_virginia_integration.py` | 131 | 100% |
| MA | DESE | `test_massachusetts_integration.py` | ~400 | 100% |

---

## Complex Districts

### New York City
- **33 geographic districts** (Community School Districts 1-32 + District 75)
- District 75: citywide special education
- Watch for: charter schools, multiple NCES entries

### Chicago
- "City of Chicago School District 299"
- Single largest in Illinois (~320K students)
- Watch for: charter schools reported separately

---

## SEA Data Files

```
data/raw/state/
├── california/
│   ├── lcff_2023_24.xlsx               # Local Control Funding
│   ├── sped_2023_24.txt                # Special Education
│   └── frpm_2023_24.xlsx               # Free/Reduced Meals
├── florida/
│   ├── ARInstructionalDistStaff2425.xlsx
│   └── 2425MembInFLPublicSchools.xlsx
├── texas/
│   └── texas_nces_tea_crosswalk_2018_19.csv
├── new-york/
│   ├── ny_staffing_2023_24.xlsx
│   ├── ny_enrollment_district_2023_24.xlsx
│   └── ny_enrollment_sped_2023_24.xlsx
├── illinois/
│   └── il_report_card_2023_24.xlsx
├── michigan/
│   ├── mi_staffing_2023_24.xlsx
│   ├── Spring_2024_Headcount.xlsx
│   └── mi_special_ed_2023_24.xlsx
├── pennsylvania/
│   ├── pa_staffing_2024_25.xlsx
│   └── pa_enrollment_2024_25.xlsx
├── virginia/
│   ├── fall_membership_statistics.csv
│   ├── staffing_and_vacancy_report_statistics.csv
│   └── dec_1_statistics (Special Education Enrollment).csv
└── massachusetts/
    ├── ma_enrollment_all_years.csv
    └── MA 2024-25 teacherdata.xlsx
```

---

## SEA Integration Test Framework

### Quick Reference
- **Base class**: `tests/test_sea_integration_base.py`
- **Shared utilities**: `infrastructure/database/migrations/sea_import_utils.py`
- **Generator**: `infrastructure/scripts/utilities/generate_sea_integration.py`

### Adding a New State
```bash
python infrastructure/scripts/utilities/generate_sea_integration.py \
    --state XX --state-name "State Name" --sea-name "Agency" \
    --data-dir data/raw/state/newstate --output-dir tests/
```

### Running Tests
```bash
pytest tests/test_*_integration.py -v              # All states
pytest tests/test_florida_integration.py -v        # Single state
pytest tests/test_*_integration.py -v -k "crosswalk"  # Category
```

---

## State Instructional Time Requirements

From `config/state-requirements.yaml`:

| State | Minutes/Day | Notes |
|-------|-------------|-------|
| TX | 420 | Highest |
| UT | 240 | Lowest (K-8) |
| CA | 240-360 | Grade-dependent |
| Default | 360 | If not specified |

---

## Current Challenges

### Data Gaps
1. **Temporal data**: Bell schedules not in OneRoster (collected via scraping)
2. **Multi-part files**: Use `split_large_files.py`
3. **State variation**: Different formats per state

### Data Quality
- Some districts report zero enrollment (administrative units)
- Occasional impossible ratios
- Automated filtering with `--filter-invalid`

### Opportunities
1. **OneRoster**: Project owner has integration work
2. **React Prototype**: Visualization tool in development
