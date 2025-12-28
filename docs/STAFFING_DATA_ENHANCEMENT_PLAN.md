# Staffing Data Enhancement Plan

**Document Created:** December 27, 2025
**Status:** Planning - Awaiting approval before implementation
**Authors:** Ian McCullough, Claude Code

---

## Executive Summary

This document outlines the planned enhancement to the Learning Connection Time (LCT) project's staffing data infrastructure. The goal is to:

1. Support **multiple LCT calculation variants** using different staffing scope definitions
2. Integrate **multiple data sources** (NCES CCD, CRDC, Census, State-level)
3. Enable **data source precedence** based on recency with NCES CCD as foundational fallback
4. Provide **rhetorical flexibility** for the "Reducing the Ratio" campaign

---

## Table of Contents

1. [Background and Motivation](#1-background-and-motivation)
2. [LCT Calculation Variants](#2-lct-calculation-variants)
3. [Data Sources](#3-data-sources)
4. [Data Precedence Rules](#4-data-precedence-rules)
5. [Database Schema Changes](#5-database-schema-changes)
6. [Implementation Phases](#6-implementation-phases)
7. [Technical Specifications](#7-technical-specifications)
8. [Open Questions](#8-open-questions)
9. [Success Criteria](#9-success-criteria)
10. [Risk Mitigation](#10-risk-mitigation)

---

## 1. Background and Motivation

### Current State

The LCT metric is currently calculated using a single `instructional_staff` field from NCES CCD:

```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Limitations of current approach:**
- Single staffing definition doesn't tell the full story
- "Instructional staff" is ambiguous - includes various roles
- No ability to compare different scope definitions
- Missing granular staff category data

### Desired State

Support multiple LCT variants that answer different questions:
- "How much time with **classroom teachers only**?"
- "How much time with **all instructional staff**?"
- "How much time with **all student-facing adults**?"

This provides rhetorical flexibility for different policy discussions and audiences.

### Strategic Context

This enhancement is part of Phase 1.5 of the "Reducing the Ratio" initiative:
- Phase 1: Basic LCT using state statutory requirements ✅
- Phase 1.5: Enrich with actual bell schedules ✅ and granular staffing data 🔄
- Phase 2+: Teacher quality weights, differentiated student needs, etc.

---

## 2. LCT Calculation Variants

### Overview

Five LCT variants, ordered from most conservative to most inclusive:

| Variant | Scope Name | Staff Included | Use Case |
|---------|------------|----------------|----------|
| LCT-Teachers | `teachers_only` | Total classroom teachers | Purest classroom teacher measure |
| LCT-Core | `teachers_core` | Elementary + Secondary + Kindergarten teachers | K-12 focus, excludes Pre-K |
| LCT-Instructional | `instructional` | Teachers + Coordinators + Paraprofessionals | **Primary recommended metric** |
| LCT-Support | `instructional_plus_support` | Above + Counselors + Psychologists + Student Support | Holistic learning support |
| LCT-All | `all` | Total LEA staff | Maximum theoretical resources |

### Detailed Definitions

#### LCT-Teachers (Most Conservative)
```
Formula: (instructional_minutes × teachers_total) / enrollment

Staff Included:
- Teachers (Total FTE from NCES)

Story: "How much theoretical one-on-one time could students get with
       actual classroom teachers?"

Best For: Conservative policy discussions, comparing to historical data
```

#### LCT-Core (K-12 Focus)
```
Formula: (instructional_minutes × [elem + sec + kinder teachers]) / enrollment

Staff Included:
- Elementary Teachers
- Secondary Teachers
- Kindergarten Teachers
- (Excludes Pre-K teachers and Ungraded teachers)

Story: "Core K-12 teacher availability, excluding Pre-K programs"

Best For: Comparing districts with different Pre-K offerings

Note: Consider whether Pre-K enrollment should also be excluded
      from the denominator for consistency (see Open Questions)
```

#### LCT-Instructional (Recommended Primary)
```
Formula: (instructional_minutes × [teachers + coordinators + paras]) / enrollment

Staff Included:
- Teachers (Total)
- Instructional Coordinators and Supervisors
- Paraprofessionals/Instructional Aides

Story: "Time with all staff directly involved in instruction delivery"

Best For: Primary metric for policy discussions
         Recognizes team teaching, co-teaching, and instructional aides

Note: Most closely matches current "instructional_staff" definition
```

#### LCT-Support (Holistic Learning)
```
Formula: (instructional_minutes × [instructional + support staff]) / enrollment

Staff Included:
- All from LCT-Instructional, plus:
- Guidance Counselors (Total)
- School Psychologists
- Student Support Services Staff

Story: "Time with all adults supporting student learning and development"

Best For: Discussions of comprehensive student support
         Equity analyses (support staff often inequitably distributed)
```

#### LCT-All (Maximum Resources)
```
Formula: (instructional_minutes × total_lea_staff) / enrollment

Staff Included:
- All LEA staff (administrators, support, maintenance, etc.)

Story: "Maximum theoretical adult attention if all district staff
       could work with students"

Best For: Upper bound for resource discussions
         Shows total human capital investment per student

Note: Not realistic but rhetorically useful for budget discussions
```

---

## 3. Data Sources

### 3.1 NCES Common Core of Data (CCD) - FOUNDATIONAL

**Status:** Available NOW (2023-24)
**Coverage:** All 18,000+ U.S. public school districts
**Role:** Foundational data source; fallback when others unavailable

**Staff Categories Available (24 total):**

```
TIER 1 - CLASSROOM TEACHERS:
├── Teachers (Total)                    [18,914 districts]
├── Elementary Teachers                 [18,455 districts]
├── Kindergarten Teachers               [18,189 districts]
├── Secondary Teachers                  [18,078 districts]
├── Pre-kindergarten Teachers           [17,151 districts]
└── Ungraded Teachers                   [9,352 districts]

TIER 2 - INSTRUCTIONAL SUPPORT:
├── Instructional Coordinators          [18,788 districts]
├── Librarians/Media Specialists        [18,788 districts]
├── Library/Media Support Staff         [18,788 districts]
└── Paraprofessionals/Aides             [18,788 districts]

TIER 3 - STUDENT SUPPORT:
├── Guidance Counselors (Total)         [18,914 districts]
├── Elementary School Counselors        [18,346 districts]
├── Secondary School Counselors         [17,650 districts]
├── School Psychologists                [18,777 districts]
└── Student Support Services Staff      [18,777 districts]

TIER 4 - ADMINISTRATIVE:
├── LEA Administrators                  [19,403 districts]
├── School Administrators               [18,921 districts]
├── LEA Administrative Support          [19,403 districts]
└── School Administrative Support       [18,921 districts]

AGGREGATES:
├── LEA Staff Total
├── School Staff Total
└── Other Staff
```

**Source File:** `data/raw/federal/nces-ccd/2023_24/ccd_lea_059_2324_l_1a_073124.csv`

---

### 3.2 Civil Rights Data Collection (CRDC)

**Status:** 2023-24 data expected 2026; earlier years available
**Coverage:** All districts (biennial survey)
**Role:** Supplementary teacher-specific data

**Staff Data Available:**
- FTE first-year teachers
- FTE second-year teachers
- Teachers absent >10 days
- Teacher demographics (race/ethnicity, sex)
- Teacher certification status

**Value:** Teacher experience and quality indicators not in NCES CCD

**Integration Strategy:**
- Use most recent available (2021-22 currently)
- Assume year-over-year staffing stability
- Monitor for 2023-24 release

---

### 3.3 Census Annual Survey of School System Finances

**Status:** 2023 data available (fiscal year, corresponds to 2022-23 school year)
**Coverage:** All districts
**Role:** Financial and salary data

**Staff Data Available:**
- Staff counts by function
- Salary expenditures by position type
- Full-time equivalent calculations
- Benefits expenditures

**Value:** Complements NCES with financial perspective
**Limitation:** Less granular role breakdown than NCES CCD

---

### 3.4 State-Level Data Sources

**Status:** Varies by state; 2022-23 widely available, 2023-24 coming mid-2025
**Coverage:** State-specific
**Role:** Highest-quality, most recent data where available

**Priority States (by data quality and student population):**

| Priority | State | Portal | API? | 2023-24 Expected |
|----------|-------|--------|------|------------------|
| 1 | Illinois | Illinois Report Card | YES | Mid-2025 |
| 2 | California | DataQuest | No | Mid-2025 |
| 3 | Texas | TAPR | No | Mid-2025 |
| 4 | Michigan | MI School Data | No | Mid-2025 |
| 5 | New York | NYSED Data | No | Mid-2025 |
| 6 | Florida | EdStats | No | Mid-2025 |
| 7 | Pennsylvania | PDE Data | No | Mid-2025 |
| 8 | Ohio | Report Cards | No | Mid-2025 |
| 9 | Georgia | K-12 Report Card | No | Mid-2025 |
| 10 | North Carolina | NC Report Cards | No | Mid-2025 |

**Coverage Note:** Top 10 states represent 41% of U.S. students

---

## 4. Data Precedence Rules

**Scope:** These rules apply to **both staffing AND enrollment data**. The same principles govern all LCT components.

### Primary Rule: Recency Wins

For any given district and data category (staffing or enrollment), prefer the **most recent data** regardless of source.

### Fallback Rule: NCES CCD as Foundation

When multiple sources have the same year, or when recency is ambiguous:
1. Use NCES CCD as the foundational/default source
2. State data supplements or validates NCES CCD
3. CRDC and Census provide additional dimensions not in NCES

### Conflict Resolution

```
SCENARIO 1: Different Years
├── State has 2024-25, NCES has 2023-24
└── DECISION: Use State data (more recent)

SCENARIO 2: Same Year, Different Values
├── State has 500 teachers, NCES has 520 teachers (both 2023-24)
└── DECISION: Use NCES CCD as foundational; flag discrepancy for review

SCENARIO 3: Partial Data
├── State has teacher counts but not paraprofessionals
└── DECISION: [See Open Question #3 - needs resolution]

SCENARIO 4: Missing Data
├── Source has NULL for a category
└── DECISION: Fall back to next source in precedence order
```

### Source Precedence Order (for same year)

1. State-level data (when available and complete)
2. NCES CCD (foundational)
3. CRDC (supplementary)
4. Census (supplementary)

### Tracking Requirements

Every staff count record MUST include:
- `data_source`: Which source provided the data
- `source_year`: School year of the data (e.g., "2023-24")
- `retrieved_at`: When we retrieved/imported the data
- `source_url`: Where the data came from (if applicable)

### Enrollment Data Strategy

Enrollment data follows the same precedence rules as staffing:

**Available Sources:**
- **NCES CCD Membership (LEA 052)**: Grade-level enrollment, October snapshot
- **Census Annual Survey of School System Finances**: May include enrollment counts
- **State-level data**: Often more current, may have different counting methodologies

**Key Principle: Use Consistent Source Per District**

For any given district's LCT calculation, enrollment must come from the same source philosophy as staffing:
- If using state staffing data → use state enrollment if available
- If using NCES staffing data → use NCES enrollment

**Grade-Level Enrollment Requirements:**

For LCT-Core variant, we need:
- Pre-K enrollment (to exclude from K-12 calculation)
- K-12 enrollment (total minus Pre-K)

The `enrollment_by_grade` table tracks:
- `enrollment_total`: Sum of all grades
- `enrollment_prek`: Pre-Kindergarten only
- `enrollment_k12`: Calculated as `enrollment_total - enrollment_prek`

---

## 5. Database Schema Changes

### 5.1 New Table: `staff_counts`

Stores granular staff counts by category from all sources.

```sql
CREATE TABLE staff_counts (
    id SERIAL PRIMARY KEY,

    -- Foreign key
    district_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,

    -- Source tracking
    source_year VARCHAR(10) NOT NULL,           -- "2023-24"
    data_source VARCHAR(50) NOT NULL,           -- "nces_ccd", "state_ca", "crdc", "census"
    source_url TEXT,
    retrieved_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- === TIER 1: CLASSROOM TEACHERS ===
    teachers_total NUMERIC(10,2),
    teachers_elementary NUMERIC(10,2),
    teachers_kindergarten NUMERIC(10,2),
    teachers_secondary NUMERIC(10,2),
    teachers_prek NUMERIC(10,2),
    teachers_ungraded NUMERIC(10,2),

    -- === TIER 2: INSTRUCTIONAL SUPPORT ===
    instructional_coordinators NUMERIC(10,2),
    librarians NUMERIC(10,2),
    library_support NUMERIC(10,2),
    paraprofessionals NUMERIC(10,2),

    -- === TIER 3: STUDENT SUPPORT ===
    counselors_total NUMERIC(10,2),
    counselors_elementary NUMERIC(10,2),
    counselors_secondary NUMERIC(10,2),
    psychologists NUMERIC(10,2),
    student_support_services NUMERIC(10,2),

    -- === TIER 4: ADMINISTRATIVE ===
    lea_administrators NUMERIC(10,2),
    school_administrators NUMERIC(10,2),
    lea_admin_support NUMERIC(10,2),
    school_admin_support NUMERIC(10,2),

    -- === AGGREGATES ===
    lea_staff_total NUMERIC(10,2),
    school_staff_total NUMERIC(10,2),
    other_staff NUMERIC(10,2),

    -- === CRDC-SPECIFIC (when available) ===
    teachers_first_year NUMERIC(10,2),
    teachers_second_year NUMERIC(10,2),
    teachers_absent_10plus_days NUMERIC(10,2),

    -- Quality tracking
    is_complete BOOLEAN DEFAULT TRUE,           -- All expected fields populated?
    quality_notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    UNIQUE (district_id, source_year, data_source)
);

-- Index for common queries
CREATE INDEX idx_staff_counts_district ON staff_counts(district_id);
CREATE INDEX idx_staff_counts_year ON staff_counts(source_year);
CREATE INDEX idx_staff_counts_source ON staff_counts(data_source);
```

### 5.2 New Table: `staff_counts_effective`

Materialized view or table storing the "effective" staff counts after precedence rules applied.

```sql
CREATE TABLE staff_counts_effective (
    district_id VARCHAR(10) PRIMARY KEY REFERENCES districts(nces_id),

    -- Effective year (most recent available)
    effective_year VARCHAR(10) NOT NULL,

    -- Source attribution (may be hybrid)
    primary_source VARCHAR(50) NOT NULL,
    sources_used JSONB DEFAULT '[]',            -- List of all sources contributing

    -- === RESOLVED STAFF COUNTS ===
    -- (Same columns as staff_counts, but with resolved values)
    teachers_total NUMERIC(10,2),
    teachers_elementary NUMERIC(10,2),
    teachers_kindergarten NUMERIC(10,2),
    teachers_secondary NUMERIC(10,2),
    teachers_prek NUMERIC(10,2),
    teachers_ungraded NUMERIC(10,2),
    instructional_coordinators NUMERIC(10,2),
    librarians NUMERIC(10,2),
    library_support NUMERIC(10,2),
    paraprofessionals NUMERIC(10,2),
    counselors_total NUMERIC(10,2),
    counselors_elementary NUMERIC(10,2),
    counselors_secondary NUMERIC(10,2),
    psychologists NUMERIC(10,2),
    student_support_services NUMERIC(10,2),
    lea_administrators NUMERIC(10,2),
    school_administrators NUMERIC(10,2),
    lea_admin_support NUMERIC(10,2),
    school_admin_support NUMERIC(10,2),
    lea_staff_total NUMERIC(10,2),
    school_staff_total NUMERIC(10,2),
    other_staff NUMERIC(10,2),

    -- Computed scope values (for query performance)
    scope_teachers_only NUMERIC(10,2),          -- = teachers_total
    scope_teachers_core NUMERIC(10,2),          -- = elem + sec + kinder
    scope_instructional NUMERIC(10,2),          -- = teachers + coords + paras
    scope_instructional_plus_support NUMERIC(10,2),
    scope_all NUMERIC(10,2),                    -- = lea_staff_total

    -- Metadata
    last_resolved_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolution_notes TEXT
);
```

### 5.3 Modified Table: `lct_calculations`

Add staff scope tracking:

```sql
ALTER TABLE lct_calculations
ADD COLUMN staff_scope VARCHAR(50) NOT NULL DEFAULT 'instructional',
ADD COLUMN staff_source VARCHAR(50),
ADD COLUMN staff_source_year VARCHAR(10);

-- Update unique constraint to include scope
ALTER TABLE lct_calculations
DROP CONSTRAINT IF EXISTS uq_lct_calculation;

ALTER TABLE lct_calculations
ADD CONSTRAINT uq_lct_calculation
UNIQUE (district_id, year, grade_level, staff_scope);

-- Add check constraint for valid scopes
ALTER TABLE lct_calculations
ADD CONSTRAINT chk_staff_scope
CHECK (staff_scope IN (
    'teachers_only',
    'teachers_core',
    'instructional',
    'instructional_plus_support',
    'all'
));
```

### 5.4 Modified Table: `districts`

Add relationship to staff_counts:

```sql
-- No schema change needed; relationship established via foreign key in staff_counts
-- Update the SQLAlchemy model to include the relationship
```

### 5.5 New Table: `data_source_registry`

Track available data sources and their status:

```sql
CREATE TABLE data_source_registry (
    id SERIAL PRIMARY KEY,
    source_code VARCHAR(50) UNIQUE NOT NULL,    -- "nces_ccd", "state_ca", "crdc"
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,           -- "federal", "state", "other"
    source_url TEXT,

    -- Coverage
    geographic_scope VARCHAR(50),               -- "national", "state", "district"
    state VARCHAR(2),                           -- For state-specific sources

    -- Data availability
    latest_year_available VARCHAR(10),
    years_available JSONB DEFAULT '[]',

    -- Update tracking
    last_checked_at TIMESTAMP WITH TIME ZONE,
    next_expected_release VARCHAR(50),          -- "Mid-2025", "2026", etc.

    -- Access information
    access_method VARCHAR(50),                  -- "api", "csv_download", "web_scrape"
    access_notes TEXT,
    requires_authentication BOOLEAN DEFAULT FALSE,

    -- Quality assessment
    reliability_score INTEGER CHECK (reliability_score BETWEEN 1 AND 5),
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Initial seed data
INSERT INTO data_source_registry (source_code, source_name, source_type, geographic_scope, latest_year_available, access_method, reliability_score) VALUES
('nces_ccd', 'NCES Common Core of Data', 'federal', 'national', '2023-24', 'csv_download', 5),
('crdc', 'Civil Rights Data Collection', 'federal', 'national', '2021-22', 'csv_download', 5),
('census_school_finance', 'Census School System Finances', 'federal', 'national', '2022-23', 'csv_download', 5),
('state_il', 'Illinois Report Card', 'state', 'state', '2022-23', 'api', 5),
('state_ca', 'California DataQuest', 'state', 'state', '2022-23', 'csv_download', 5),
('state_tx', 'Texas TAPR', 'state', 'state', '2022-23', 'csv_download', 5);
```

---

## 6. Implementation Phases

### Phase 1: NCES CCD Staff Enhancement (IMMEDIATE)

**Duration:** 2-3 days
**Prerequisites:** None - data already available
**Deliverables:**
1. Database schema changes (new tables)
2. NCES CCD staff extraction script
3. Populated `staff_counts` table (17,842 districts)
4. Populated `staff_counts_effective` table
5. Updated LCT calculations with all 5 variants
6. Comparison report

**Steps:**
```
1.1 Create database migration script
    - Add staff_counts table
    - Add staff_counts_effective table
    - Add data_source_registry table
    - Modify lct_calculations table

1.2 Write NCES CCD staff extraction script
    - Parse ccd_lea_059_2324_l_1a_073124.csv
    - Map columns to new schema
    - Handle missing values and data quality

1.3 Import NCES CCD data
    - Load all 24 staff categories
    - Populate staff_counts with source="nces_ccd"
    - Generate staff_counts_effective (initially = staff_counts)

1.4 Recalculate LCT with all variants
    - Calculate 5 LCT values per district per grade level
    - Store in lct_calculations with staff_scope
    - Generate summary statistics

1.5 Generate comparison report
    - Distribution of each LCT variant
    - Variance between variants by district
    - Identify districts where scope matters most
```

### Phase 2: State-Level Integration (HIGH PRIORITY)

**Duration:** 1-2 weeks
**Prerequisites:** Phase 1 complete
**Deliverables:**
1. Illinois API connector
2. California DataQuest scraper
3. State data import pipeline
4. Cross-source validation report

**Steps:**
```
2.1 Build Illinois Report Card API connector
    - Authenticate (if needed)
    - Extract 2022-23 staffing data
    - Map to common schema
    - Import to staff_counts with source="state_il"

2.2 Build California DataQuest extraction
    - Download staff assignment files
    - Parse and normalize
    - Import to staff_counts with source="state_ca"

2.3 Update precedence resolution
    - Rebuild staff_counts_effective
    - Apply recency rules
    - Log source decisions

2.4 Cross-source validation
    - Compare NCES vs state for same districts
    - Identify and document discrepancies
    - Assess data quality
```

### Phase 3: Additional States (MEDIUM PRIORITY)

**Duration:** 2-3 weeks
**Prerequisites:** Phase 2 complete
**Deliverables:**
1. Extraction scripts for TX, FL, NY, PA, MI, OH, GA, NC
2. Expanded staff_counts coverage
3. 41% of U.S. students with state-level data

### Phase 4: CRDC and Census Integration (LOWER PRIORITY)

**Duration:** 1 week
**Prerequisites:** Phase 1 complete
**Deliverables:**
1. CRDC import pipeline (2021-22 data)
2. Census import pipeline (2022-23 data)
3. Additional data dimensions in staff_counts

### Phase 5: Monitoring and Refresh (ONGOING)

**Duration:** Quarterly
**Deliverables:**
1. Automated checks for new data releases
2. Refresh scripts for updated data
3. Data quality monitoring

---

## 7. Technical Specifications

### 7.1 NCES CCD Column Mappings

From `ccd_lea_059_2324_l_1a_073124.csv`:

```python
NCES_CCD_COLUMN_MAPPINGS = {
    # Identifiers
    'LEAID': 'district_id',

    # Teachers
    'TEACHERS': 'teachers_total',
    'TEACHERS_ELEM': 'teachers_elementary',
    'TEACHERS_KGTN': 'teachers_kindergarten',
    'TEACHERS_SEC': 'teachers_secondary',
    'TEACHERS_PREK': 'teachers_prek',
    'TEACHERS_UG': 'teachers_ungraded',

    # Instructional Support
    'INST_COORD': 'instructional_coordinators',
    'LIBRARIANS': 'librarians',
    'LIBSUP': 'library_support',
    'PARAS': 'paraprofessionals',

    # Student Support
    'GUID_COUNS': 'counselors_total',
    'GUID_ELEM': 'counselors_elementary',
    'GUID_SEC': 'counselors_secondary',
    'PSYCH': 'psychologists',
    'STUDSUPP': 'student_support_services',

    # Administrative
    'LEA_ADMIN': 'lea_administrators',
    'SCH_ADMIN': 'school_administrators',
    'LEA_ADMSUP': 'lea_admin_support',
    'SCH_ADMSUP': 'school_admin_support',

    # Aggregates
    'STAFF_LEA': 'lea_staff_total',
    'STAFF_SCH': 'school_staff_total',
    'STAFF_OTH': 'other_staff',
}
```

**Note:** Actual column names need verification against file header.

### 7.2 Scope Calculation Logic

```python
def calculate_scope_values(staff: StaffCounts) -> dict:
    """Calculate all scope values from detailed staff counts."""

    def safe_sum(*values):
        """Sum values, treating None as 0."""
        return sum(v or 0 for v in values)

    return {
        'scope_teachers_only': staff.teachers_total,

        'scope_teachers_core': safe_sum(
            staff.teachers_elementary,
            staff.teachers_secondary,
            staff.teachers_kindergarten
        ),

        'scope_instructional': safe_sum(
            staff.teachers_total,
            staff.instructional_coordinators,
            staff.paraprofessionals
        ),

        'scope_instructional_plus_support': safe_sum(
            staff.teachers_total,
            staff.instructional_coordinators,
            staff.paraprofessionals,
            staff.counselors_total,
            staff.psychologists,
            staff.student_support_services
        ),

        'scope_all': staff.lea_staff_total
    }
```

### 7.3 LCT Calculation with Scope

```python
def calculate_lct(
    instructional_minutes: int,
    enrollment: int,
    staff_count: float,
    scope: str
) -> float:
    """
    Calculate LCT for a given scope.

    Args:
        instructional_minutes: Daily instructional minutes
        enrollment: Student enrollment (consider adjusting for scope)
        staff_count: Staff count for the specified scope
        scope: One of the 5 defined scopes

    Returns:
        LCT value in minutes per student per day
    """
    if enrollment <= 0 or staff_count <= 0:
        raise ValueError("Enrollment and staff must be positive")

    return (instructional_minutes * staff_count) / enrollment
```

---

## 8. Design Decisions (Resolved)

The following questions were resolved on December 27, 2025:

### Decision 1: Storage Strategy ✅

**Question:** Should we store all 5 LCT variants per district, or calculate on-demand?

**Decision:** Store raw data in project directory (`data/raw/`), pre-calculated values in database.
- Raw source files preserved for reproducibility
- Database contains resolved/effective values for queries
- No live queries to external sources (data changes at most annually)

---

### Decision 2: Recency vs Foundation Clarification ✅

**Question:** When NCES CCD is "foundational" but precedence is "recency-based," how do we reconcile?

**Decision:**
- **Different years:** More recent data wins regardless of source
- **Same year:** NCES CCD wins as foundational source

**Examples:**
- NCES CCD 2024-25 + State 2025-26 → Use State (more recent)
- NCES CCD 2024-25 + State 2024-25 → Use NCES CCD (foundational, same year)

---

### Decision 3: Partial Data Handling ✅

**Question:** If a state source has teacher counts but not paraprofessional counts, do we create a hybrid?

**Decision:** NO HYBRIDS. Use NCES entirely if state data is incomplete.

**Rationale:** All calculations for any given district should come from just one data source. This ensures consistency and simplifies data lineage tracking.

**Rule:** A state source must provide ALL staff categories needed for our 5 LCT variants to be used. Otherwise, fall back to NCES CCD for that district.

---

### Decision 4: LCT-Core Enrollment Adjustment ✅

**Question:** For LCT-Core (excluding Pre-K teachers), should we also exclude Pre-K enrollment?

**Decision:** YES - exclude Pre-K enrollment from the denominator for consistency.

**Rationale:** Mathematical consistency requires matching numerator and denominator scope. If we exclude Pre-K teachers, we must exclude Pre-K students.

**Implementation Note:** Verify Pre-K enrollment is available separately in NCES grade-level enrollment data.

---

### Decision 5: Multiple Years Storage ✅

**Question:** Should we maintain separate LCT calculations for each year we have data?

**Decision:** Present only the MOST RECENT year's LCT calculations.

**Rationale:** Given that we accept mixed-year data (enrollment from year X, staffing from year Y, bell schedule from year Z), attempting to show historical calculations would be confusing and potentially misleading.

**Future Consideration:** Leave schema flexible for future multi-year analysis if data alignment improves. Document this limitation clearly.

---

### Decision 6: Dataset Update Strategy ✅

**Added December 27, 2025**

**Principle:** Design for regular dataset updates as new versions become available.

**Requirements:**
1. Schema must support multiple years of raw data per source
2. Clear versioning/dating of when data was retrieved
3. Ability to re-run calculations when any source updates
4. Archive old effective values before overwriting (for audit trail)
5. Document the "as of" date for any published metrics

---

### Decision 7: Data Archiving Strategy ✅

**Added December 27, 2025**

**Question:** When new data becomes available, how do we handle the old data?

**Decision:** Accumulate historical data in `staff_counts`, with `staff_counts_effective` always reflecting resolved current values.

**Rationale:**
- Supports future trend analysis
- Volume is manageable (~700K rows max over 10 years)
- Public-facing queries hit `staff_counts_effective` (one row per district)
- Historical `staff_counts` is for research/audit only

**Performance Assurance:**
- `staff_counts_effective` provides O(1) lookups per district
- All 5 scope values pre-calculated and stored
- Proper indexing on `district_id`, `source_year`
- PostgreSQL handles millions of rows efficiently

---

### Decision 8: Mixed-Year Labeling ✅

**Added December 27, 2025**

**Question:** When LCT uses enrollment from year X, staffing from year Y, and bell schedule from year Z, how do we label it?

**Decision:** Show all component years in metadata for full transparency.

**Rationale:** This work may influence public policy discussions and will be audited/challenged. Complete transparency about data sources and years is essential.

**Implementation:**
```json
{
  "calculated_at": "2025-12-27",
  "component_years": {
    "enrollment": "2023-24",
    "staffing": "2024-25",
    "bell_schedule": "2025-26"
  },
  "data_sources": {
    "enrollment": "nces_ccd",
    "staffing": "state_ca",
    "bell_schedule": "automated_enrichment"
  }
}
```

---

### Decision 9: State Completeness Definition ✅

**Added December 27, 2025**

**Question:** What constitutes "complete" state data for use instead of NCES CCD?

**Decision:** A state is "complete" if it provides ALL categories needed for ALL 5 LCT scopes.

**Required Categories:**
1. `teachers_total` (for LCT-Teachers)
2. `teachers_elementary`, `teachers_secondary`, `teachers_kindergarten` (for LCT-Core)
3. `instructional_coordinators`, `paraprofessionals` (for LCT-Instructional)
4. `counselors_total`, `psychologists`, `student_support_services` (for LCT-Support)
5. `lea_staff_total` (for LCT-All)

**Rule:** If state data is missing ANY of these categories, use NCES CCD for that district entirely. No hybrid calculations - staffing data must be consistent across all 5 LCT calculations for a given district.

---

### Decision 10: Pre-K Enrollment Verification ✅

**Added December 27, 2025**

**Verification Status:** CONFIRMED - Pre-K enrollment is separately available.

**Data Source:** NCES CCD Membership File (`ccd_lea_052_2324_l_1a_073124.csv`)

**Coverage:**
| Grade Level | Districts with Data |
|-------------|-------------------|
| Pre-Kindergarten | 11,425 |
| Kindergarten | 16,322 |
| Grade 1 | 16,262 |

**Notes:**
- Lower Pre-K coverage is expected (not all districts offer Pre-K)
- Data in long format: aggregate `STUDENT_COUNT` where `GRADE = "Pre-Kindergarten"`
- For LCT-Core: `K-12 Enrollment = Total Enrollment - Pre-K Enrollment`
- Districts without Pre-K have no Pre-K to exclude (handled gracefully)

---

## 9. Success Criteria

### Phase 1 Success Criteria

- [ ] All 24 NCES CCD staff categories imported for 17,842+ districts
- [ ] `staff_counts` table populated with source tracking
- [ ] `staff_counts_effective` table populated with scope calculations
- [ ] 5 LCT variants calculated for all valid districts
- [ ] Comparison report generated showing distribution of each variant
- [ ] No data loss from current `instructional_staff` field

### Overall Success Criteria

- [ ] Multiple data sources integrated with clear precedence
- [ ] All 5 LCT variants queryable and exportable
- [ ] Data lineage traceable for any value
- [ ] State-level data for top 10 states (41% of students)
- [ ] Documentation sufficient for campaign use
- [ ] Schema stable for future enhancements

---

## 10. Risk Mitigation

### Risk 1: Data Inconsistency Between Sources

**Mitigation:**
- Always track source in database
- Generate discrepancy reports
- Flag significant differences for review
- Document known issues

### Risk 2: Schema Changes Breaking Existing Pipeline

**Mitigation:**
- Create migration scripts
- Test on copy of database first
- Maintain backward compatibility where possible
- Keep existing `instructional_staff` field populated

### Risk 3: State Data Formats Vary Widely

**Mitigation:**
- Build flexible parsers
- Document each state's format
- Create validation checks
- Allow for partial imports

### Risk 4: Future Sessions Losing Context

**Mitigation:**
- This document serves as authoritative reference
- Update document after each phase
- Log all decisions in `data_lineage` table
- Commit planning documents to git

---

## Appendix A: Current Database State

As of December 27, 2025:

| Table | Record Count | Notes |
|-------|-------------|-------|
| districts | 17,842 | NCES CCD 2023-24 |
| state_requirements | 50 | All 50 states + DC |
| bell_schedules | 384 | 128 districts × 3 grade levels |
| lct_calculations | (pending) | To be recalculated |
| data_lineage | (varies) | Audit trail |

---

## Appendix B: Related Documentation

- `CLAUDE.md` - Project overview and context
- `docs/METHODOLOGY.md` - LCT calculation methodology
- `docs/DATABASE_SETUP.md` - PostgreSQL setup guide
- `docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md` - Bell schedule collection procedures
- `infrastructure/database/models.py` - SQLAlchemy ORM models
- `infrastructure/database/schema.sql` - Database DDL

---

## Appendix C: Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-12-27 | Claude Code | Initial draft |
| 2025-12-27 | Ian McCullough + Claude Code | Resolved all 10 design decisions; verified Pre-K enrollment availability |

---

**END OF DOCUMENT**
