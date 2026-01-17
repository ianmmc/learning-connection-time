-- Migration 006: Florida Integration - Add Florida-Specific Tables
-- Created: 2026-01-16
-- Description: Adds Florida Department of Education (FLDOE) data tables and views
-- Note: Florida uses 2-digit district codes (e.g., "13" for Miami-Dade County)

-- ============================================================================
-- 1. Florida District Identifiers (Crosswalk Reference)
-- ============================================================================

-- Store FLDOE-specific identifiers and metadata
-- This supplements the districts table with Florida-specific data
CREATE TABLE IF NOT EXISTS fl_district_identifiers (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,

    -- FLDOE identifiers
    fldoe_district_no VARCHAR(2) NOT NULL,  -- 2-digit FLDOE district number (e.g., "13")
    district_name_fldoe VARCHAR(255),       -- Official FLDOE district name

    -- District classifications
    district_type VARCHAR(50),              -- Type of district
    is_charter BOOLEAN DEFAULT FALSE,

    -- Geographic information
    county_name VARCHAR(100),               -- County name

    -- Metadata
    data_source VARCHAR(50) DEFAULT 'fldoe',
    source_year VARCHAR(10),                -- Year of data (e.g., "2024-25")
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_fl_fldoe_district_no UNIQUE (fldoe_district_no),
    CONSTRAINT uq_fl_nces_id UNIQUE (nces_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_fl_fldoe_district_no ON fl_district_identifiers(fldoe_district_no);
CREATE INDEX IF NOT EXISTS ix_fl_nces_id ON fl_district_identifiers(nces_id);

-- ============================================================================
-- 2. Florida Staff Data (Layer 2 Enrichment)
-- ============================================================================

-- Store FLDOE staff counts to validate/enrich NCES CCD data
CREATE TABLE IF NOT EXISTS fl_staff_data (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    year VARCHAR(10) NOT NULL,
    data_source VARCHAR(50) DEFAULT 'fldoe',

    -- Instructional staff counts
    total_instructional_staff DECIMAL(10, 2),
    classroom_teachers DECIMAL(10, 2),
    ese_teachers DECIMAL(10, 2),            -- Exceptional Student Education
    media_specialists DECIMAL(10, 2),
    guidance_counselors DECIMAL(10, 2),
    instructional_coaches DECIMAL(10, 2),
    other_instructional DECIMAL(10, 2),

    -- Administrative staff
    administrators DECIMAL(10, 2),

    -- Quality tracking
    confidence VARCHAR(20) DEFAULT 'high',
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_fl_staff UNIQUE (nces_id, year, data_source),
    CONSTRAINT chk_fl_staff_confidence CHECK (confidence IN ('high', 'medium', 'low'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_fl_staff_nces_id ON fl_staff_data(nces_id);
CREATE INDEX IF NOT EXISTS ix_fl_staff_year ON fl_staff_data(year);

-- ============================================================================
-- 3. Florida Enrollment Data (Layer 2 Enrichment)
-- ============================================================================

-- Store FLDOE enrollment counts to validate/enrich NCES CCD data
CREATE TABLE IF NOT EXISTS fl_enrollment_data (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    year VARCHAR(10) NOT NULL,
    data_source VARCHAR(50) DEFAULT 'fldoe',

    -- Total enrollment
    total_enrollment INTEGER,

    -- Membership counts
    pk_12_membership INTEGER,              -- Pre-K through 12
    pk_membership INTEGER,                 -- Pre-K only
    k_12_membership INTEGER,               -- K-12 only

    -- Demographic breakdowns (if available)
    demographics JSONB,                    -- Flexible structure for various demographics

    -- Quality tracking
    confidence VARCHAR(20) DEFAULT 'high',
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_fl_enrollment UNIQUE (nces_id, year, data_source),
    CONSTRAINT chk_fl_enrollment_confidence CHECK (confidence IN ('high', 'medium', 'low'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_fl_enrollment_nces_id ON fl_enrollment_data(nces_id);
CREATE INDEX IF NOT EXISTS ix_fl_enrollment_year ON fl_enrollment_data(year);

-- ============================================================================
-- 4. View: Florida Districts with Full Data
-- ============================================================================

-- Create a view joining districts with Florida data for easy querying
CREATE OR REPLACE VIEW v_florida_districts AS
SELECT
    d.nces_id,
    d.name AS district_name_nces,
    fl_id.district_name_fldoe,
    fl_id.fldoe_district_no,
    fl_id.county_name,
    fl_id.is_charter,
    d.state,
    d.st_leaid,
    d.enrollment AS nces_enrollment,
    d.total_staff AS nces_staff,
    fl_enr.total_enrollment AS fldoe_enrollment,
    fl_staff.total_instructional_staff AS fldoe_instructional_staff,
    fl_staff.classroom_teachers AS fldoe_classroom_teachers,
    fl_staff.ese_teachers AS fldoe_ese_teachers,
    d.year
FROM districts d
LEFT JOIN fl_district_identifiers fl_id ON d.nces_id = fl_id.nces_id
LEFT JOIN fl_enrollment_data fl_enr ON d.nces_id = fl_enr.nces_id AND d.year = fl_enr.year
LEFT JOIN fl_staff_data fl_staff ON d.nces_id = fl_staff.nces_id AND d.year = fl_staff.year
WHERE d.state = 'FL';

-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Add comments to tables
COMMENT ON TABLE fl_district_identifiers IS 'Florida Department of Education district identifiers and crosswalk (Layer 2)';
COMMENT ON TABLE fl_staff_data IS 'Florida staff data from FLDOE (Layer 2)';
COMMENT ON TABLE fl_enrollment_data IS 'Florida enrollment data from FLDOE (Layer 2)';
COMMENT ON VIEW v_florida_districts IS 'Consolidated view of Florida districts with FLDOE data';
