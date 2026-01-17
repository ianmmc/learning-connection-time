-- Migration 007: State District Crosswalk - Master Crosswalk Table
-- Created: 2026-01-16
-- Description: Creates unified crosswalk table for NCES ↔ State district ID mappings
--
-- Architecture:
--   - Master crosswalk table holds ID mappings only
--   - State-specific tables (fl_district_identifiers, etc.) hold state metadata
--   - ST_LEAID from NCES CCD is the primary source (format: {STATE}-{STATE_ID})

-- ============================================================================
-- 1. State District Crosswalk Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS state_district_crosswalk (
    id SERIAL PRIMARY KEY,

    -- Core mapping
    nces_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    state VARCHAR(2) NOT NULL,
    state_district_id VARCHAR(20) NOT NULL,  -- State's own ID (parsed from ST_LEAID)

    -- Source tracking
    id_system VARCHAR(50) NOT NULL DEFAULT 'st_leaid',  -- 'st_leaid', 'fldoe', 'tea_peims', 'cde_cds'
    source VARCHAR(100),                                 -- 'nces_ccd_2023_24', 'fldoe_staff_2024_25'
    source_year VARCHAR(10),                             -- Year of source data

    -- Verification
    verification_date DATE,
    confidence VARCHAR(20) DEFAULT 'high',
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_crosswalk_nces_system UNIQUE (nces_id, id_system),
    CONSTRAINT uq_crosswalk_state_id_system UNIQUE (state, state_district_id, id_system),
    CONSTRAINT chk_crosswalk_confidence CHECK (confidence IN ('high', 'medium', 'low'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_crosswalk_nces_id ON state_district_crosswalk(nces_id);
CREATE INDEX IF NOT EXISTS ix_crosswalk_state ON state_district_crosswalk(state);
CREATE INDEX IF NOT EXISTS ix_crosswalk_state_district_id ON state_district_crosswalk(state, state_district_id);

-- ============================================================================
-- 2. Populate from ST_LEAID (Primary Source)
-- ============================================================================

-- Parse ST_LEAID format: {STATE}-{STATE_ID} (e.g., 'FL-13', 'TX-101912', 'CA-1964733')
INSERT INTO state_district_crosswalk (nces_id, state, state_district_id, id_system, source, source_year, confidence)
SELECT
    nces_id,
    state,
    -- Extract state ID after the hyphen
    SUBSTRING(st_leaid FROM POSITION('-' IN st_leaid) + 1) AS state_district_id,
    'st_leaid' AS id_system,
    'nces_ccd' AS source,
    year AS source_year,
    'high' AS confidence
FROM districts
WHERE st_leaid IS NOT NULL
  AND st_leaid LIKE '%-%'
  AND LENGTH(st_leaid) > 3
ON CONFLICT (nces_id, id_system) DO UPDATE SET
    state_district_id = EXCLUDED.state_district_id,
    source_year = EXCLUDED.source_year,
    updated_at = CURRENT_TIMESTAMP;

-- ============================================================================
-- 3. View: Districts with Crosswalk
-- ============================================================================

CREATE OR REPLACE VIEW v_districts_with_crosswalk AS
SELECT
    d.nces_id,
    d.name,
    d.state,
    d.enrollment,
    d.instructional_staff,
    d.st_leaid,
    c.state_district_id,
    c.id_system,
    c.source,
    c.source_year,
    c.confidence,
    d.year AS nces_year
FROM districts d
LEFT JOIN state_district_crosswalk c ON d.nces_id = c.nces_id AND c.id_system = 'st_leaid';

-- ============================================================================
-- 4. Function: Get State District ID
-- ============================================================================

CREATE OR REPLACE FUNCTION get_state_district_id(
    p_nces_id VARCHAR(10),
    p_id_system VARCHAR(50) DEFAULT 'st_leaid'
) RETURNS VARCHAR(20) AS $$
DECLARE
    v_state_id VARCHAR(20);
BEGIN
    SELECT state_district_id INTO v_state_id
    FROM state_district_crosswalk
    WHERE nces_id = p_nces_id AND id_system = p_id_system;

    RETURN v_state_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 5. Function: Get NCES ID from State ID
-- ============================================================================

CREATE OR REPLACE FUNCTION get_nces_id(
    p_state VARCHAR(2),
    p_state_district_id VARCHAR(20),
    p_id_system VARCHAR(50) DEFAULT 'st_leaid'
) RETURNS VARCHAR(10) AS $$
DECLARE
    v_nces_id VARCHAR(10);
BEGIN
    SELECT nces_id INTO v_nces_id
    FROM state_district_crosswalk
    WHERE state = p_state
      AND state_district_id = p_state_district_id
      AND id_system = p_id_system;

    RETURN v_nces_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Migration Complete
-- ============================================================================

COMMENT ON TABLE state_district_crosswalk IS 'Master crosswalk table mapping NCES LEAIDs to state-specific district IDs';
COMMENT ON VIEW v_districts_with_crosswalk IS 'Districts with their state crosswalk information';
COMMENT ON FUNCTION get_state_district_id IS 'Look up state district ID from NCES ID';
COMMENT ON FUNCTION get_nces_id IS 'Look up NCES ID from state district ID';
