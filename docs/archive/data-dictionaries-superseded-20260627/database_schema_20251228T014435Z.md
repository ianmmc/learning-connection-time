# Database Data Dictionary

*Auto-generated: 2025-12-28T01:44:35Z*

This document describes all database tables, columns, and relationships
for the Learning Connection Time project.

## Table of Contents

- [districts](#districts)
- [state_requirements](#state_requirements)
- [bell_schedules](#bell_schedules)
- [staff_counts](#staff_counts)
- [staff_counts_effective](#staff_counts_effective)
- [enrollment_by_grade](#enrollment_by_grade)
- [lct_calculations](#lct_calculations)
- [calculation_runs](#calculation_runs)
- [data_lineage](#data_lineage)
- [data_source_registry](#data_source_registry)

## districts

School district from NCES Common Core of Data.

Represents a single school district with enrollment and staffing data.
Primary source is the NCES CCD directory file.

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `nces_id` | VARCHAR(10) | No | PK |  |
| `name` | VARCHAR(255) | No |  |  |
| `state` | VARCHAR(2) | No |  |  |
| `enrollment` | INTEGER | Yes |  |  |
| `instructional_staff` | NUMERIC(10, 2) | Yes |  |  |
| `total_staff` | NUMERIC(10, 2) | Yes |  |  |
| `schools_count` | INTEGER | Yes |  |  |
| `year` | VARCHAR(10) | No |  |  |
| `data_source` | VARCHAR(50) | No |  | nces_ccd |
| `created_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af24180> |
| `updated_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af242c0> |

### Relationships

- **bell_schedules** → `BellSchedule` (ONETOMANY)
- **lct_calculations** → `LCTCalculation` (ONETOMANY)
- **staff_counts** → `StaffCounts` (ONETOMANY)
- **staff_counts_effective** → `StaffCountsEffective` (ONETOMANY)
- **enrollment_by_grade** → `EnrollmentByGrade` (ONETOMANY)

---

## state_requirements

State statutory requirements for instructional time.

Contains minimum daily instructional minutes by grade level.
Source: State education codes and regulations.

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `state` | VARCHAR(2) | No | PK |  |
| `state_name` | VARCHAR(50) | No |  |  |
| `elementary_minutes` | INTEGER | Yes |  |  |
| `middle_minutes` | INTEGER | Yes |  |  |
| `high_minutes` | INTEGER | Yes |  |  |
| `default_minutes` | INTEGER | Yes |  |  |
| `annual_days` | INTEGER | Yes |  |  |
| `annual_hours` | NUMERIC(6, 2) | Yes |  |  |
| `notes` | TEXT | Yes |  |  |
| `source` | VARCHAR(255) | Yes |  |  |
| `updated_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af26b60> |

---

## bell_schedules

Enriched bell schedule data with actual instructional time.

Contains actual start/end times and instructional minutes
collected from district/school websites and documents.

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `id` | INTEGER | No | PK |  |
| `district_id` | VARCHAR(10) | No | FK → districts.nces_id |  |
| `year` | VARCHAR(10) | No |  |  |
| `grade_level` | VARCHAR(20) | No |  |  |
| `instructional_minutes` | INTEGER | No |  |  |
| `start_time` | VARCHAR(20) | Yes |  |  |
| `end_time` | VARCHAR(20) | Yes |  |  |
| `lunch_duration` | INTEGER | Yes |  |  |
| `passing_periods` | INTEGER | Yes |  |  |
| `recess_duration` | INTEGER | Yes |  |  |
| `schools_sampled` | JSONB | Yes |  | <function list at 0x10af50040> |
| `source_urls` | JSONB | Yes |  | <function list at 0x10af500e0> |
| `confidence` | VARCHAR(10) | No |  | high |
| `method` | VARCHAR(30) | No |  |  |
| `source_description` | TEXT | Yes |  |  |
| `notes` | TEXT | Yes |  |  |
| `raw_import` | JSONB | Yes |  |  |
| `created_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af50180> |
| `updated_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af50220> |

### Relationships

- **district** → `District` (MANYTOONE)
- **lct_calculations** → `LCTCalculation` (ONETOMANY)

### Constraints

- `uq_bell_schedule` (UniqueConstraint)
- `chk_grade_level` (CheckConstraint)
- `chk_confidence` (CheckConstraint)
- `chk_method` (CheckConstraint)
- `chk_instructional_minutes` (CheckConstraint)

---

## staff_counts

Historical staff counts by category from all sources.

Multiple rows per district (one per source+year).
Contains granular staff data for LCT calculations.

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `id` | INTEGER | No | PK |  |
| `district_id` | VARCHAR(10) | No | FK → districts.nces_id |  |
| `source_year` | VARCHAR(10) | No |  |  |
| `data_source` | VARCHAR(50) | No |  |  |
| `source_url` | TEXT | Yes |  |  |
| `retrieved_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af8b2e0> |
| `teachers_total` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_elementary` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_kindergarten` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_secondary` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_prek` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_ungraded` | NUMERIC(10, 2) | Yes |  |  |
| `instructional_coordinators` | NUMERIC(10, 2) | Yes |  |  |
| `librarians` | NUMERIC(10, 2) | Yes |  |  |
| `library_support` | NUMERIC(10, 2) | Yes |  |  |
| `paraprofessionals` | NUMERIC(10, 2) | Yes |  |  |
| `counselors_total` | NUMERIC(10, 2) | Yes |  |  |
| `counselors_elementary` | NUMERIC(10, 2) | Yes |  |  |
| `counselors_secondary` | NUMERIC(10, 2) | Yes |  |  |
| `psychologists` | NUMERIC(10, 2) | Yes |  |  |
| `student_support_services` | NUMERIC(10, 2) | Yes |  |  |
| `lea_administrators` | NUMERIC(10, 2) | Yes |  |  |
| `school_administrators` | NUMERIC(10, 2) | Yes |  |  |
| `lea_admin_support` | NUMERIC(10, 2) | Yes |  |  |
| `school_admin_support` | NUMERIC(10, 2) | Yes |  |  |
| `lea_staff_total` | NUMERIC(10, 2) | Yes |  |  |
| `school_staff_total` | NUMERIC(10, 2) | Yes |  |  |
| `other_staff` | NUMERIC(10, 2) | Yes |  |  |
| `all_other_support_staff` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_first_year` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_second_year` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_absent_10plus_days` | NUMERIC(10, 2) | Yes |  |  |
| `is_complete` | BOOLEAN | No |  | True |
| `quality_notes` | TEXT | Yes |  |  |
| `created_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af8b6a0> |
| `updated_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af8b7e0> |

### Relationships

- **district** → `District` (MANYTOONE)

### Constraints

- `uq_staff_counts` (UniqueConstraint)

---

## staff_counts_effective

Resolved current staff counts after precedence rules.

One row per district. Primary query table for applications.
Contains pre-calculated scope values for all 5 LCT variants.

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `district_id` | VARCHAR(10) | No | PK |  |
| `effective_year` | VARCHAR(10) | No |  |  |
| `primary_source` | VARCHAR(50) | No |  |  |
| `sources_used` | JSONB | Yes |  | <function list at 0x10afc5a80> |
| `teachers_total` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_elementary` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_kindergarten` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_secondary` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_prek` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_ungraded` | NUMERIC(10, 2) | Yes |  |  |
| `instructional_coordinators` | NUMERIC(10, 2) | Yes |  |  |
| `librarians` | NUMERIC(10, 2) | Yes |  |  |
| `library_support` | NUMERIC(10, 2) | Yes |  |  |
| `paraprofessionals` | NUMERIC(10, 2) | Yes |  |  |
| `counselors_total` | NUMERIC(10, 2) | Yes |  |  |
| `counselors_elementary` | NUMERIC(10, 2) | Yes |  |  |
| `counselors_secondary` | NUMERIC(10, 2) | Yes |  |  |
| `psychologists` | NUMERIC(10, 2) | Yes |  |  |
| `student_support_services` | NUMERIC(10, 2) | Yes |  |  |
| `lea_administrators` | NUMERIC(10, 2) | Yes |  |  |
| `school_administrators` | NUMERIC(10, 2) | Yes |  |  |
| `lea_admin_support` | NUMERIC(10, 2) | Yes |  |  |
| `school_admin_support` | NUMERIC(10, 2) | Yes |  |  |
| `lea_staff_total` | NUMERIC(10, 2) | Yes |  |  |
| `school_staff_total` | NUMERIC(10, 2) | Yes |  |  |
| `other_staff` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_k12` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_elementary_k5` | NUMERIC(10, 2) | Yes |  |  |
| `teachers_secondary_6_12` | NUMERIC(10, 2) | Yes |  |  |
| `scope_teachers_only` | NUMERIC(10, 2) | Yes |  |  |
| `scope_teachers_core` | NUMERIC(10, 2) | Yes |  |  |
| `scope_instructional` | NUMERIC(10, 2) | Yes |  |  |
| `scope_instructional_plus_support` | NUMERIC(10, 2) | Yes |  |  |
| `scope_all` | NUMERIC(10, 2) | Yes |  |  |
| `last_resolved_at` | DATETIME | No |  | <function datetime.utcnow at 0x10afc5c60> |
| `resolution_notes` | TEXT | Yes |  |  |

### Relationships

- **district** → `District` (MANYTOONE)

---

## enrollment_by_grade

Grade-level enrollment for LCT-Core calculations.

Allows excluding Pre-K from the denominator when using
teachers_core (which excludes Pre-K teachers).

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `id` | INTEGER | No | PK |  |
| `district_id` | VARCHAR(10) | No | FK → districts.nces_id |  |
| `source_year` | VARCHAR(10) | No |  |  |
| `data_source` | VARCHAR(50) | No |  | nces_ccd |
| `enrollment_prek` | INTEGER | Yes |  |  |
| `enrollment_kindergarten` | INTEGER | Yes |  |  |
| `enrollment_grade_1` | INTEGER | Yes |  |  |
| `enrollment_grade_2` | INTEGER | Yes |  |  |
| `enrollment_grade_3` | INTEGER | Yes |  |  |
| `enrollment_grade_4` | INTEGER | Yes |  |  |
| `enrollment_grade_5` | INTEGER | Yes |  |  |
| `enrollment_grade_6` | INTEGER | Yes |  |  |
| `enrollment_grade_7` | INTEGER | Yes |  |  |
| `enrollment_grade_8` | INTEGER | Yes |  |  |
| `enrollment_grade_9` | INTEGER | Yes |  |  |
| `enrollment_grade_10` | INTEGER | Yes |  |  |
| `enrollment_grade_11` | INTEGER | Yes |  |  |
| `enrollment_grade_12` | INTEGER | Yes |  |  |
| `enrollment_grade_13` | INTEGER | Yes |  |  |
| `enrollment_ungraded` | INTEGER | Yes |  |  |
| `enrollment_adult_ed` | INTEGER | Yes |  |  |
| `enrollment_total` | INTEGER | Yes |  |  |
| `enrollment_k12` | INTEGER | Yes |  |  |
| `enrollment_elementary` | INTEGER | Yes |  |  |
| `enrollment_secondary` | INTEGER | Yes |  |  |
| `created_at` | DATETIME | No |  | <function datetime.utcnow at 0x10afc7e20> |
| `updated_at` | DATETIME | No |  | <function datetime.utcnow at 0x10b000040> |

### Relationships

- **district** → `District` (MANYTOONE)

### Constraints

- `uq_enrollment_by_grade` (UniqueConstraint)

---

## lct_calculations

Computed Learning Connection Time metrics.

LCT = (instructional_minutes * instructional_staff) / enrollment

This represents the theoretical average time each student could
receive individual attention from a teacher per day.

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `id` | INTEGER | No | PK |  |
| `district_id` | VARCHAR(10) | No | FK → districts.nces_id |  |
| `bell_schedule_id` | INTEGER | Yes | FK → bell_schedules.id |  |
| `year` | VARCHAR(10) | No |  |  |
| `grade_level` | VARCHAR(20) | Yes |  |  |
| `instructional_minutes` | INTEGER | No |  |  |
| `enrollment` | INTEGER | No |  |  |
| `instructional_staff` | NUMERIC(10, 2) | No |  |  |
| `lct_value` | NUMERIC(10, 4) | No |  |  |
| `data_tier` | INTEGER | No |  |  |
| `notes` | TEXT | Yes |  |  |
| `calculated_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af51d00> |

### Relationships

- **district** → `District` (MANYTOONE)
- **bell_schedule** → `BellSchedule` (MANYTOONE)

### Constraints

- `uq_lct_calculation` (UniqueConstraint)
- `chk_data_tier` (CheckConstraint)
- `chk_lct_positive` (CheckConstraint)
- `chk_enrollment_positive` (CheckConstraint)
- `chk_staff_positive` (CheckConstraint)

---

## calculation_runs

Tracks LCT calculation runs for incremental processing.

Enables efficient recalculation by tracking what was processed when.

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `run_id` | VARCHAR(50) | No | PK |  |
| `year` | VARCHAR(10) | No |  |  |
| `run_type` | VARCHAR(30) | No |  |  |
| `status` | VARCHAR(20) | No |  |  |
| `districts_processed` | INTEGER | No |  | 0 |
| `districts_skipped` | INTEGER | No |  | 0 |
| `calculations_created` | INTEGER | No |  | 0 |
| `input_hash` | VARCHAR(64) | Yes |  |  |
| `previous_run_id` | VARCHAR(50) | Yes |  |  |
| `started_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af534c0> |
| `completed_at` | DATETIME | Yes |  |  |
| `output_files` | JSONB | Yes |  | <function list at 0x10af53560> |
| `error_message` | TEXT | Yes |  |  |
| `qa_summary` | JSONB | Yes |  |  |

---

## data_lineage

Audit trail for data changes and imports.

Tracks the provenance of data for transparency and debugging.

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `id` | INTEGER | No | PK |  |
| `entity_type` | VARCHAR(50) | No |  |  |
| `entity_id` | VARCHAR(50) | No |  |  |
| `operation` | VARCHAR(30) | No |  |  |
| `source_file` | VARCHAR(500) | Yes |  |  |
| `details` | JSONB | Yes |  |  |
| `created_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af88ae0> |
| `created_by` | VARCHAR(100) | No |  | system |

---

## data_source_registry

Registry of available data sources with metadata.

Tracks federal, state, and other sources for staffing and enrollment data.

### Columns

| Column | Type | Nullable | Key | Default |
|--------|------|----------|-----|---------|
| `id` | INTEGER | No | PK |  |
| `source_code` | VARCHAR(50) | No |  |  |
| `source_name` | VARCHAR(255) | No |  |  |
| `source_type` | VARCHAR(50) | No |  |  |
| `source_url` | TEXT | Yes |  |  |
| `geographic_scope` | VARCHAR(50) | Yes |  |  |
| `state` | VARCHAR(2) | Yes |  |  |
| `latest_year_available` | VARCHAR(10) | Yes |  |  |
| `years_available` | JSONB | Yes |  | <function list at 0x10af89800> |
| `last_checked_at` | DATETIME | Yes |  |  |
| `next_expected_release` | VARCHAR(50) | Yes |  |  |
| `access_method` | VARCHAR(50) | Yes |  |  |
| `access_notes` | TEXT | Yes |  |  |
| `requires_authentication` | BOOLEAN | No |  | False |
| `reliability_score` | INTEGER | Yes |  |  |
| `notes` | TEXT | Yes |  |  |
| `created_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af89a80> |
| `updated_at` | DATETIME | No |  | <function datetime.utcnow at 0x10af89bc0> |

---

## Metadata

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | December 2025 | Added CalculationRun, level-based enrollment/staffing |
| 1.5 | December 2025 | Added StaffCountsEffective with scope calculations |
| 1.0 | December 2025 | Initial PostgreSQL migration |

### Data Sources

- **NCES CCD**: Primary source for districts, enrollment, staffing
- **Bell Schedules**: Collected via web scraping and manual research
- **State Requirements**: Compiled from state education codes
