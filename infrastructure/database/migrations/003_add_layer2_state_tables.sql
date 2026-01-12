-- Migration 003: Add Layer 2 State-Level Enhancement Tables
-- Created: 2026-01-09
-- Description: Adds California and multi-state tables for SPED, socioeconomic, and funding data

-- ============================================================================
-- 1. California SPED District Environments
-- ============================================================================

CREATE TABLE IF NOT EXISTS ca_sped_district_environments (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    cds_code VARCHAR(7) NOT NULL,
    year VARCHAR(10) NOT NULL,
    data_source VARCHAR(50) DEFAULT 'ca_cde_sped',

    -- Total SPED enrollment
    sped_enrollment_total INTEGER,

    -- Educational environment breakdowns
    sped_mainstreamed INTEGER,
    sped_mainstreamed_80_plus INTEGER,  -- PS_RCGT80_N
    sped_mainstreamed_40_79 INTEGER,    -- PS_RC4079_N
    sped_self_contained INTEGER,
    sped_self_contained_lt_40 INTEGER,  -- PS_RCL40_N
    sped_separate_school INTEGER,       -- PS_SSOS_N
    sped_preschool INTEGER,             -- PS_PSS_N
    sped_missing INTEGER,               -- PS_MUK_N

    -- Calculated proportion
    self_contained_proportion NUMERIC(10, 6),

    -- Quality tracking
    confidence VARCHAR(20) DEFAULT 'high',
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_ca_sped_environment UNIQUE (nces_id, year),
    CONSTRAINT chk_ca_sped_confidence CHECK (confidence IN ('high', 'medium', 'low'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_ca_sped_nces_id ON ca_sped_district_environments(nces_id);
CREATE INDEX IF NOT EXISTS ix_ca_sped_year ON ca_sped_district_environments(year);
CREATE INDEX IF NOT EXISTS ix_ca_sped_cds_code ON ca_sped_district_environments(cds_code);

-- ============================================================================
-- 2. District Socioeconomic Data (Multi-State)
-- ============================================================================

CREATE TABLE IF NOT EXISTS district_socioeconomic (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    year VARCHAR(10) NOT NULL,
    state VARCHAR(2) NOT NULL,

    -- Core poverty indicator
    poverty_indicator_type VARCHAR(50) NOT NULL,
    poverty_percent NUMERIC(10, 6),
    poverty_count INTEGER,
    enrollment INTEGER,  -- For validation

    -- Tiered/categorical data
    tier_1_count INTEGER,
    tier_2_count INTEGER,
    tier_3_count INTEGER,
    tier_4_count INTEGER,
    tier_5_count INTEGER,
    tier_metadata JSONB,

    -- Funding-related flags
    title_i_eligible BOOLEAN,
    schoolwide_program BOOLEAN,

    -- Source documentation
    data_source VARCHAR(50) NOT NULL,
    source_url VARCHAR(500),
    collection_method VARCHAR(100),

    -- Quality tracking
    certification_status VARCHAR(20),
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_district_socioeconomic UNIQUE (nces_id, year, poverty_indicator_type, data_source),
    CONSTRAINT chk_poverty_percent CHECK (poverty_percent BETWEEN 0 AND 1)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_socioeconomic_nces_id ON district_socioeconomic(nces_id);
CREATE INDEX IF NOT EXISTS ix_socioeconomic_year ON district_socioeconomic(year);
CREATE INDEX IF NOT EXISTS ix_socioeconomic_state ON district_socioeconomic(state);
CREATE INDEX IF NOT EXISTS ix_socioeconomic_poverty_type ON district_socioeconomic(poverty_indicator_type);

-- ============================================================================
-- 3. District Funding Data (Multi-State)
-- ============================================================================

CREATE TABLE IF NOT EXISTS district_funding (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    year VARCHAR(10) NOT NULL,
    state VARCHAR(2) NOT NULL,

    -- Federal funding
    title_i_allocation NUMERIC(12, 2),
    idea_allocation NUMERIC(12, 2),
    title_iii_allocation NUMERIC(12, 2),
    other_federal NUMERIC(12, 2),

    -- State funding (flexible structure)
    state_formula_type VARCHAR(50),
    base_allocation NUMERIC(12, 2),
    equity_adjustment NUMERIC(12, 2),
    equity_adjustment_type VARCHAR(100),
    total_state_funding NUMERIC(12, 2),

    -- Local funding
    local_revenue NUMERIC(12, 2),

    -- Per-pupil calculations
    total_per_pupil NUMERIC(10, 2),
    instructional_per_pupil NUMERIC(10, 2),

    -- Source documentation
    data_source VARCHAR(50) NOT NULL,
    source_url VARCHAR(500),
    fiscal_year VARCHAR(10),

    -- Quality tracking
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_district_funding UNIQUE (nces_id, year, data_source)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_funding_nces_id ON district_funding(nces_id);
CREATE INDEX IF NOT EXISTS ix_funding_year ON district_funding(year);
CREATE INDEX IF NOT EXISTS ix_funding_state ON district_funding(state);
CREATE INDEX IF NOT EXISTS ix_funding_data_source ON district_funding(data_source);

-- ============================================================================
-- 4. California LCFF Funding (California-Specific)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ca_lcff_funding (
    id SERIAL PRIMARY KEY,
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    year VARCHAR(10) NOT NULL,

    -- LCFF Components
    base_grant NUMERIC(12, 2),
    supplemental_grant NUMERIC(12, 2),
    concentration_grant NUMERIC(12, 2),
    total_lcff NUMERIC(12, 2),

    -- Funded ADA
    funded_ada NUMERIC(10, 2),

    -- Unduplicated Pupil Count (UPC)
    unduplicated_pupil_count INTEGER,
    upc_percentage NUMERIC(10, 6),

    -- Grade span breakdowns
    base_tk_3 NUMERIC(12, 2),
    base_4_6 NUMERIC(12, 2),
    base_7_8 NUMERIC(12, 2),
    base_9_12 NUMERIC(12, 2),

    -- Source documentation
    data_source VARCHAR(50) DEFAULT 'ca_cde_lcff',
    source_url VARCHAR(500),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_ca_lcff_funding UNIQUE (nces_id, year),
    CONSTRAINT chk_upc_percentage CHECK (upc_percentage BETWEEN 0 AND 1)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_lcff_nces_id ON ca_lcff_funding(nces_id);
CREATE INDEX IF NOT EXISTS ix_lcff_year ON ca_lcff_funding(year);

-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Add comments to tables
COMMENT ON TABLE ca_sped_district_environments IS 'California SPED enrollment by educational environment (Layer 2)';
COMMENT ON TABLE district_socioeconomic IS 'Multi-state socioeconomic indicators (Layer 2)';
COMMENT ON TABLE district_funding IS 'Multi-state funding data (Layer 2)';
COMMENT ON TABLE ca_lcff_funding IS 'California LCFF funding details (Layer 2)';
