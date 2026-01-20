# SEA Integration Guide

Guide for integrating State Education Agency (SEA) data into the Learning Connection Time project.

**Related Files:**
- `tests/test_sea_integration_base.py` - Base class and mixin definitions
- `infrastructure/database/migrations/sea_import_utils.py` - Shared utility functions
- `infrastructure/scripts/utilities/generate_sea_integration.py` - Generator script for new states

---

## Data Architecture: Layered Integration

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
| NY | 12-digit | `"310200010000"` (NYC) |
| IL | RR-CCC-DDDD-TT | `"15-016-2990-25"` (Chicago) |
| MI | 5-digit | `"82015"` (Detroit) |
| PA | 9-digit AUN | `"126515001"` (Philadelphia) |
| VA | 3-digit (zero-padded) | `"029"` (Fairfax County) |
| MA | 4-digit (zero-padded) | `"0035"` (Boston) |

### Implemented SEA Integrations

| State | Agency | Status | Test File | Key Data |
|-------|--------|--------|-----------|----------|
| California | CDE | ✅ Complete | `test_california_integration.py` | LCFF, ADA, SPED, FRPM |
| Texas | TEA | ✅ Complete | `test_texas_integration.py` | NCES crosswalk via ST_LEAID |
| Florida | FLDOE | ✅ Complete | `test_florida_integration.py` | Staff, enrollment, 82 districts |
| New York | NYSED | ✅ Complete | `test_new_york_integration.py` | NYC (33 sub-districts), upstate |
| Illinois | ISBE | ✅ Complete | `test_illinois_integration.py` | Chicago (City of Chicago SD 299) |
| Michigan | MDE | ✅ Complete | `test_michigan_integration.py` | Staff, enrollment, SPED, 836 districts |
| Pennsylvania | PDE | ✅ Complete | `test_pennsylvania_integration.py` | Staff, enrollment, 777 districts |
| Virginia | VDOE | ✅ Complete | `test_virginia_integration.py` | Staff, enrollment, SPED, 131 divisions |
| Massachusetts | DESE | ✅ Complete | `test_massachusetts_integration.py` | Staff, enrollment, ~400 districts |

### Complex Districts: NYC and Chicago

**New York City** requires special handling:
- NYC is administratively divided into **33 geographic districts** (Community School Districts 1-32 + District 75 citywide SPED)
- NCES may report as single LEA or multiple depending on data vintage
- State ID format: 12-digit (e.g., `"310200010000"`)
- Watch for: District 75 (citywide special education), charter schools

**Chicago** requires special handling:
- Officially "City of Chicago School District 299"
- Single largest district in Illinois (~320K students)
- State ID format: RR-CCC-DDDD-TT (e.g., `"15-016-2990-25"`)
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
├── florida/
│   ├── florida_staff_2024_25.csv
│   └── florida_enrollment_2024_25.csv
├── new-york/
│   ├── ny_staffing_2023_24.xlsx
│   ├── ny_enrollment_district_2023_24.xlsx
│   └── ny_enrollment_sped_2023_24.xlsx
├── illinois/
│   └── il_report_card_2023_24.xlsx
├── michigan/
│   ├── mi_staffing_2023_24.xlsx        # Teacher FTE, SPED staff
│   ├── Spring_2024_Headcount.xlsx      # Enrollment by grade
│   └── mi_special_ed_2023_24.xlsx      # IEP counts, SPED %
├── pennsylvania/
│   ├── pa_staffing_2024_25.xlsx        # Classroom teachers, professional staff
│   └── pa_enrollment_2024_25.xlsx      # K-12 enrollment by grade
└── virginia/
    ├── fall_membership_statistics.csv  # Enrollment (FT, PT, total)
    ├── staffing_and_vacancy_report_statistics.csv  # Staff FTE by position type
    └── dec_1_statistics (Special Education Enrollment).csv  # SPED counts
```

---

## SEA Integration Test Framework

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
    ├── SEADataQualityTests (Mixin)
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
| DataQuality | 3 | Suppressed values, SPED-intensive districts |
| RegressionPrevention | 3 | Prevent type coercion and zero-value bugs |

---

## Adding a New State

### Option 1: Use the Generator Script (Recommended)

```bash
# Analyze SEA data files and generate scaffolding
python infrastructure/scripts/utilities/generate_sea_integration.py \
    --state XX \
    --state-name "State Name" \
    --sea-name "Agency Name" \
    --data-dir data/raw/state/newstate \
    --output-dir tests/

# The script will:
# 1. Discover Excel/CSV column names
# 2. Generate test file scaffolding
# 3. Generate import script scaffolding
# 4. Create sample EXPECTED_DISTRICTS template
```

### Option 2: Manual Creation

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
    SEADataQualityTests,
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
    SEADataQualityTests,
    SEARegressionPreventionTests,
):
    """Integration tests for New State SEA data."""
    pass
```

4. **Create import script**: `infrastructure/database/migrations/import_{state}_data.py`

Use shared utilities from `sea_import_utils.py`:

```python
from infrastructure.database.migrations.sea_import_utils import (
    safe_float, safe_int, safe_pct,
    load_state_crosswalk, get_nces_id,
    format_state_id, log_import_summary,
)
```

5. **Run tests**: `pytest tests/test_newstate_integration.py -v`

6. **Document in DATA_SOURCES.md**

---

## Shared Utilities

### `sea_import_utils.py`

Common functions for SEA data imports:

```python
# Safe value conversion (handles suppressed values like '*', '-', '')
safe_float(val)      # Returns Optional[float]
safe_int(val)        # Returns Optional[int]
safe_pct(val)        # Returns Optional[float] (converts 0-100 to 0-1)

# Crosswalk operations
load_state_crosswalk(session, state_code)  # Returns Dict[state_id, nces_id]
get_nces_id(crosswalk, state_id)           # Returns Optional[str]

# State ID formatting
format_state_id(state_code, raw_id)        # Applies state-specific formatting

# Logging
log_import_summary(logger, state, counts)  # Standardized import summary
```

### State ID Format Registry

```python
SEA_ID_FORMATS = {
    'FL': {'converter': lambda x: str(int(x)).zfill(2)},
    'NY': {'converter': lambda x: str(int(x)).strip()},
    'IL': {'converter': lambda rcdts: f'{str(rcdts)[0:2]}-{str(rcdts)[2:5]}-{str(rcdts)[5:9]}-{str(rcdts)[9:11]}'},
    'CA': {'converter': lambda x: str(x)},
    'TX': {'converter': lambda x: str(x)},
}
```

---

## Running SEA Integration Tests

```bash
# Run all SEA integration tests
pytest tests/test_*_integration.py -v

# Run specific state
pytest tests/test_florida_integration.py -v
pytest tests/test_new_york_integration.py -v
pytest tests/test_illinois_integration.py -v

# Run specific test category across all states
pytest tests/test_*_integration.py -v -k "crosswalk"
pytest tests/test_*_integration.py -v -k "enrollment"
pytest tests/test_*_integration.py -v -k "lct"
pytest tests/test_*_integration.py -v -k "data_quality"

# See test counts by state
pytest tests/test_*_integration.py --collect-only | grep "test session"

# Quick validation (collect only, no execution)
pytest tests/test_*_integration.py --collect-only
```

---

## Current Test Coverage

| Category | Tests | Status |
|----------|-------|--------|
| Florida Integration | 71 | ✅ Pass |
| Texas Integration | 54 | ✅ Pass |
| California Integration | 58 | ✅ Pass |
| New York Integration | 37 | ✅ Pass |
| Illinois Integration | 32 | ✅ Pass |
| Michigan Integration | 71 | ✅ Pass |
| Pennsylvania Integration | 27 | ✅ Pass |
| Virginia Integration | 28 | ✅ Pass |
| Massachusetts Integration | 27 | ✅ Pass |
| **Total SEA Integration Tests** | **375 passed** | **✅ Pass (100%)** |

*Test counts updated as of January 19, 2026 (IL RCDTS format fix applied).*

---

## SPED-Intensive District Handling

Some districts (e.g., special education cooperatives, alternative schools) have unusual staff-to-student ratios. Mark these with skip flags:

```python
EXPECTED_DISTRICTS = {
    "SPED_Cooperative": {
        "nces_leaid": "XXXXXXX",
        "state_district_id": "XX-XXXXX",
        "enrollment": 500,
        "total_teachers": 100,
        "expected_lct_teachers_only": 72.0,  # Very high LCT
        "skip_ratio_validation": True,       # Skip ratio check
        "skip_lct_range_validation": True,   # Skip LCT range check
        "sped_intensive": True,              # Mark as SPED-intensive
    },
}
```

---

## Troubleshooting

### Module Import Errors

If you see `No module named 'sea_import_utils'`:
```python
# Use full path:
from infrastructure.database.migrations.sea_import_utils import safe_float
```

### JSONB Parameter Binding

For SQLAlchemy with PostgreSQL JSONB:
```python
# Correct:
session.execute(text("INSERT ... VALUES (:json_data::jsonb)"), {"json_data": json.dumps(data)})

# Also correct:
session.execute(text("INSERT ... VALUES (CAST(:json_data AS jsonb))"), {"json_data": json.dumps(data)})
```

### Suppressed Value Handling

State agencies use various markers for suppressed data:
- `'*'` - Privacy suppression (small N)
- `'-'` - Not applicable
- `''` - Missing data
- `'N/A'`, `'null'` - Various null representations

The `safe_float()` and `safe_int()` functions handle all of these.

---

**Last Updated**: January 17, 2026
