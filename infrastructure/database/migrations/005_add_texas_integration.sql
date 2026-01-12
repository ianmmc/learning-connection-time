-- Migration 005: Texas Integration - Add State LEA IDs and Texas-Specific Tables
-- Created: 2026-01-11
-- Description: Adds st_leaid field to districts table and prepares for Texas data integration
-- Note: Texas will primarily use NCES CCD federal data (enrollment, staffing, SPED)
--       with TEA district identifiers for crosswalk purposes

-- ============================================================================
-- 1. Add State LEA ID to Districts Table (Multi-State Enhancement)
-- ============================================================================

-- Add st_leaid column to store state-assigned district identifiers
-- Format varies by state (e.g., TX-227901 for Texas, CA-01-12345 for California)
ALTER TABLE districts
ADD COLUMN IF NOT EXISTS st_leaid VARCHAR(20);

-- Index for efficient lookups by state LEA ID
CREATE INDEX IF NOT EXISTS ix_districts_st_leaid ON districts(st_leaid);

-- Add comment documenting field
COMMENT ON COLUMN districts.st_leaid IS 'State-assigned LEA identifier from NCES CCD (e.g., TX-227901 for Texas, varies by state)';

-- ============================================================================
-- 2. Texas District Identifiers (Crosswalk Reference)
-- ============================================================================

-- Store TEA-specific identifiers and metadata
-- This supplements the districts table with Texas-specific data
CREATE TABLE IF NOT EXISTS tx_district_identifiers (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,

    -- TEA identifiers
    tea_district_no VARCHAR(6) NOT NULL,  -- 6-digit TEA district number (e.g., "227901")
    st_leaid VARCHAR(20) NOT NULL,        -- Full ST_LEAID from NCES (e.g., "TX-227901")

    -- TEA district classifications
    tea_district_type VARCHAR(1),         -- TEA 9-category type (A-I)
    tea_district_type_text VARCHAR(100),  -- Description (e.g., "Major Urban")

    -- Charter school flag
    is_charter BOOLEAN DEFAULT FALSE,
    charter_type VARCHAR(50),             -- Type of charter if applicable

    -- Geographic information
    county_district_no VARCHAR(10),       -- Combined county-district code if available
    education_service_center INTEGER,     -- ESC region number (1-20)

    -- Metadata
    data_source VARCHAR(50) DEFAULT 'nces_ccd',
    source_year VARCHAR(10),              -- Year of crosswalk data (e.g., "2018-19")
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_tx_tea_district_no UNIQUE (tea_district_no),
    CONSTRAINT uq_tx_nces_id UNIQUE (nces_id),
    CONSTRAINT uq_tx_st_leaid UNIQUE (st_leaid)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_tx_tea_district_no ON tx_district_identifiers(tea_district_no);
CREATE INDEX IF NOT EXISTS ix_tx_nces_id ON tx_district_identifiers(nces_id);
CREATE INDEX IF NOT EXISTS ix_tx_st_leaid ON tx_district_identifiers(st_leaid);
CREATE INDEX IF NOT EXISTS ix_tx_district_type ON tx_district_identifiers(tea_district_type);

-- ============================================================================
-- 3. Texas SPED Data (Placeholder for Future Enhancement)
-- ============================================================================

-- Note: Initially we'll use federal NCES data for SPED enrollment
-- This table is reserved for future Texas-specific SPED data if needed
-- (e.g., PEIMS disability categories, educational settings from TEA)

CREATE TABLE IF NOT EXISTS tx_sped_district_data (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    year VARCHAR(10) NOT NULL,
    data_source VARCHAR(50) DEFAULT 'peims',

    -- Total SPED enrollment (cross-check with NCES)
    sped_enrollment_total INTEGER,

    -- PEIMS disability categories (if available)
    disability_categories JSONB,  -- Flexible structure for various categories

    -- Educational settings (if available from TEA)
    settings JSONB,  -- Flexible structure for placement data

    -- Quality tracking
    confidence VARCHAR(20) DEFAULT 'medium',
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_tx_sped UNIQUE (nces_id, year, data_source),
    CONSTRAINT chk_tx_sped_confidence CHECK (confidence IN ('high', 'medium', 'low'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_tx_sped_nces_id ON tx_sped_district_data(nces_id);
CREATE INDEX IF NOT EXISTS ix_tx_sped_year ON tx_sped_district_data(year);

-- ============================================================================
-- 4. View: Texas Districts with Full Identifiers
-- ============================================================================

-- Create a view joining districts with Texas identifiers for easy querying
CREATE OR REPLACE VIEW v_texas_districts AS
SELECT
    d.nces_id,
    d.name AS district_name,
    d.state,
    d.st_leaid,
    tx.tea_district_no,
    tx.tea_district_type,
    tx.tea_district_type_text,
    tx.is_charter,
    tx.charter_type,
    tx.education_service_center,
    d.enrollment,
    d.total_staff,
    d.year
FROM districts d
LEFT JOIN tx_district_identifiers tx ON d.nces_id = tx.nces_id
WHERE d.state = 'TX';

-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Add comments to tables
COMMENT ON TABLE tx_district_identifiers IS 'Texas Education Agency district identifiers and crosswalk (Layer 2)';
COMMENT ON TABLE tx_sped_district_data IS 'Texas SPED data from PEIMS (Layer 2, future use)';
COMMENT ON VIEW v_texas_districts IS 'Consolidated view of Texas districts with TEA identifiers';

-- Document the migration (removed - data_lineage table has different schema)
