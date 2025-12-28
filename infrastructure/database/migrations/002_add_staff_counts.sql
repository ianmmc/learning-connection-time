-- Migration 002: Add Staff Counts Tables
-- Created: 2025-12-27
-- Purpose: Support multiple LCT calculation variants with granular staff data
-- Reference: docs/STAFFING_DATA_ENHANCEMENT_PLAN.md

-- ============================================================================
-- NEW TABLE: data_source_registry
-- Tracks available data sources and their status
-- ============================================================================

CREATE TABLE IF NOT EXISTS data_source_registry (
    id SERIAL PRIMARY KEY,
    source_code VARCHAR(50) UNIQUE NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_url TEXT,

    -- Coverage
    geographic_scope VARCHAR(50),
    state VARCHAR(2),

    -- Data availability
    latest_year_available VARCHAR(10),
    years_available JSONB DEFAULT '[]',

    -- Update tracking
    last_checked_at TIMESTAMP WITH TIME ZONE,
    next_expected_release VARCHAR(50),

    -- Access information
    access_method VARCHAR(50),
    access_notes TEXT,
    requires_authentication BOOLEAN DEFAULT FALSE,

    -- Quality assessment
    reliability_score INTEGER CHECK (reliability_score BETWEEN 1 AND 5),
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed initial data sources
INSERT INTO data_source_registry (source_code, source_name, source_type, geographic_scope, latest_year_available, access_method, reliability_score) VALUES
('nces_ccd', 'NCES Common Core of Data', 'federal', 'national', '2023-24', 'csv_download', 5),
('crdc', 'Civil Rights Data Collection', 'federal', 'national', '2021-22', 'csv_download', 5),
('census_school_finance', 'Census School System Finances', 'federal', 'national', '2022-23', 'csv_download', 5),
('state_il', 'Illinois Report Card', 'state', 'state', '2022-23', 'api', 5),
('state_ca', 'California DataQuest', 'state', 'state', '2022-23', 'csv_download', 5),
('state_tx', 'Texas TAPR', 'state', 'state', '2022-23', 'csv_download', 5)
ON CONFLICT (source_code) DO NOTHING;

-- ============================================================================
-- NEW TABLE: staff_counts
-- Stores granular staff counts by category from all sources (historical)
-- ============================================================================

CREATE TABLE IF NOT EXISTS staff_counts (
    id SERIAL PRIMARY KEY,

    -- Foreign key
    district_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,

    -- Source tracking
    source_year VARCHAR(10) NOT NULL,
    data_source VARCHAR(50) NOT NULL,
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
    all_other_support_staff NUMERIC(10,2),

    -- === CRDC-SPECIFIC (when available) ===
    teachers_first_year NUMERIC(10,2),
    teachers_second_year NUMERIC(10,2),
    teachers_absent_10plus_days NUMERIC(10,2),

    -- Quality tracking
    is_complete BOOLEAN DEFAULT TRUE,
    quality_notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    UNIQUE (district_id, source_year, data_source)
);

CREATE INDEX IF NOT EXISTS idx_staff_counts_district ON staff_counts(district_id);
CREATE INDEX IF NOT EXISTS idx_staff_counts_year ON staff_counts(source_year);
CREATE INDEX IF NOT EXISTS idx_staff_counts_source ON staff_counts(data_source);

-- ============================================================================
-- NEW TABLE: staff_counts_effective
-- Stores resolved "current" staff counts after precedence rules applied
-- One row per district - this is the query table for applications
-- ============================================================================

CREATE TABLE IF NOT EXISTS staff_counts_effective (
    district_id VARCHAR(10) PRIMARY KEY REFERENCES districts(nces_id) ON DELETE CASCADE,

    -- Effective year (most recent available)
    effective_year VARCHAR(10) NOT NULL,

    -- Source attribution
    primary_source VARCHAR(50) NOT NULL,
    sources_used JSONB DEFAULT '[]',

    -- === RESOLVED STAFF COUNTS ===
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

    -- === PRE-CALCULATED SCOPE VALUES ===
    -- These are computed for query performance
    scope_teachers_only NUMERIC(10,2),
    scope_teachers_core NUMERIC(10,2),
    scope_instructional NUMERIC(10,2),
    scope_instructional_plus_support NUMERIC(10,2),
    scope_all NUMERIC(10,2),

    -- Metadata
    last_resolved_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolution_notes TEXT
);

-- ============================================================================
-- NEW TABLE: enrollment_by_grade
-- Stores grade-level enrollment for LCT-Core calculations (excluding Pre-K)
-- ============================================================================

CREATE TABLE IF NOT EXISTS enrollment_by_grade (
    id SERIAL PRIMARY KEY,

    -- Foreign key
    district_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,

    -- Source tracking
    source_year VARCHAR(10) NOT NULL,
    data_source VARCHAR(50) NOT NULL DEFAULT 'nces_ccd',

    -- Enrollment by grade
    enrollment_prek NUMERIC(10,0),
    enrollment_kindergarten NUMERIC(10,0),
    enrollment_grade_1 NUMERIC(10,0),
    enrollment_grade_2 NUMERIC(10,0),
    enrollment_grade_3 NUMERIC(10,0),
    enrollment_grade_4 NUMERIC(10,0),
    enrollment_grade_5 NUMERIC(10,0),
    enrollment_grade_6 NUMERIC(10,0),
    enrollment_grade_7 NUMERIC(10,0),
    enrollment_grade_8 NUMERIC(10,0),
    enrollment_grade_9 NUMERIC(10,0),
    enrollment_grade_10 NUMERIC(10,0),
    enrollment_grade_11 NUMERIC(10,0),
    enrollment_grade_12 NUMERIC(10,0),
    enrollment_grade_13 NUMERIC(10,0),
    enrollment_ungraded NUMERIC(10,0),
    enrollment_adult_ed NUMERIC(10,0),

    -- Aggregates
    enrollment_total NUMERIC(10,0),
    enrollment_k12 NUMERIC(10,0),  -- Total minus Pre-K (for LCT-Core)

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    UNIQUE (district_id, source_year, data_source)
);

CREATE INDEX IF NOT EXISTS idx_enrollment_by_grade_district ON enrollment_by_grade(district_id);

-- ============================================================================
-- MODIFY TABLE: lct_calculations
-- Add staff_scope and component year tracking
-- ============================================================================

-- Add new columns if they don't exist
DO $$
BEGIN
    -- Add staff_scope column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'lct_calculations' AND column_name = 'staff_scope') THEN
        ALTER TABLE lct_calculations ADD COLUMN staff_scope VARCHAR(50) NOT NULL DEFAULT 'instructional';
    END IF;

    -- Add staff_source column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'lct_calculations' AND column_name = 'staff_source') THEN
        ALTER TABLE lct_calculations ADD COLUMN staff_source VARCHAR(50);
    END IF;

    -- Add staff_source_year column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'lct_calculations' AND column_name = 'staff_source_year') THEN
        ALTER TABLE lct_calculations ADD COLUMN staff_source_year VARCHAR(10);
    END IF;

    -- Add enrollment_source column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'lct_calculations' AND column_name = 'enrollment_source') THEN
        ALTER TABLE lct_calculations ADD COLUMN enrollment_source VARCHAR(50);
    END IF;

    -- Add enrollment_source_year column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'lct_calculations' AND column_name = 'enrollment_source_year') THEN
        ALTER TABLE lct_calculations ADD COLUMN enrollment_source_year VARCHAR(10);
    END IF;

    -- Add bell_schedule_source column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'lct_calculations' AND column_name = 'bell_schedule_source') THEN
        ALTER TABLE lct_calculations ADD COLUMN bell_schedule_source VARCHAR(50);
    END IF;

    -- Add bell_schedule_source_year column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'lct_calculations' AND column_name = 'bell_schedule_source_year') THEN
        ALTER TABLE lct_calculations ADD COLUMN bell_schedule_source_year VARCHAR(10);
    END IF;

    -- Add component_years JSONB for full transparency
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'lct_calculations' AND column_name = 'component_years') THEN
        ALTER TABLE lct_calculations ADD COLUMN component_years JSONB;
    END IF;
END $$;

-- Drop old unique constraint if exists and create new one including staff_scope
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_lct_calculation') THEN
        ALTER TABLE lct_calculations DROP CONSTRAINT uq_lct_calculation;
    END IF;
END $$;

-- Note: We'll create a new unique constraint that includes staff_scope
-- but we need to handle existing data first, so this is done conditionally
-- ALTER TABLE lct_calculations ADD CONSTRAINT uq_lct_calculation_v2
--     UNIQUE (district_id, year, grade_level, staff_scope);

-- Add check constraint for valid scopes
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_staff_scope') THEN
        ALTER TABLE lct_calculations ADD CONSTRAINT chk_staff_scope
            CHECK (staff_scope IN (
                'teachers_only',
                'teachers_core',
                'instructional',
                'instructional_plus_support',
                'all'
            ));
    END IF;
END $$;

-- ============================================================================
-- COMMENTS for documentation
-- ============================================================================

COMMENT ON TABLE staff_counts IS 'Historical staff counts by category from all sources. Multiple rows per district (one per source+year).';
COMMENT ON TABLE staff_counts_effective IS 'Resolved current staff counts after precedence rules. One row per district. Primary query table for applications.';
COMMENT ON TABLE enrollment_by_grade IS 'Grade-level enrollment for LCT-Core calculations (excludes Pre-K from denominator).';
COMMENT ON TABLE data_source_registry IS 'Registry of available data sources with metadata about coverage and access.';

COMMENT ON COLUMN staff_counts_effective.scope_teachers_only IS 'Pre-calculated: teachers_total';
COMMENT ON COLUMN staff_counts_effective.scope_teachers_core IS 'Pre-calculated: teachers_elementary + teachers_secondary + teachers_kindergarten';
COMMENT ON COLUMN staff_counts_effective.scope_instructional IS 'Pre-calculated: teachers_total + instructional_coordinators + paraprofessionals';
COMMENT ON COLUMN staff_counts_effective.scope_instructional_plus_support IS 'Pre-calculated: scope_instructional + counselors_total + psychologists + student_support_services';
COMMENT ON COLUMN staff_counts_effective.scope_all IS 'Pre-calculated: lea_staff_total';

COMMENT ON COLUMN lct_calculations.staff_scope IS 'Which staff definition used: teachers_only, teachers_core, instructional, instructional_plus_support, all';
COMMENT ON COLUMN lct_calculations.component_years IS 'JSON tracking source years for each component: {enrollment, staffing, bell_schedule}';
