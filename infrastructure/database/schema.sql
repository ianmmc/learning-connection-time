-- Learning Connection Time Database Schema
-- PostgreSQL 16+
-- Created: December 25, 2025

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

-- Enable UUID generation if needed in future
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- DROP EXISTING TABLES (for clean rebuilds during development)
-- =============================================================================

DROP TABLE IF EXISTS data_lineage CASCADE;
DROP TABLE IF EXISTS lct_calculations CASCADE;
DROP TABLE IF EXISTS bell_schedules CASCADE;
DROP TABLE IF EXISTS state_requirements CASCADE;
DROP TABLE IF EXISTS districts CASCADE;

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Districts: All U.S. school districts from NCES Common Core of Data
-- -----------------------------------------------------------------------------
CREATE TABLE districts (
    nces_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    state CHAR(2) NOT NULL,
    enrollment INTEGER,
    instructional_staff NUMERIC(10, 2),
    total_staff NUMERIC(10, 2),
    schools_count INTEGER,
    year VARCHAR(10) NOT NULL,  -- "2023-24" format
    data_source VARCHAR(50) DEFAULT 'nces_ccd',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_districts_state ON districts(state);
CREATE INDEX idx_districts_enrollment ON districts(enrollment DESC NULLS LAST);
CREATE INDEX idx_districts_year ON districts(year);
CREATE INDEX idx_districts_state_enrollment ON districts(state, enrollment DESC NULLS LAST);

-- Comments
COMMENT ON TABLE districts IS 'U.S. school districts from NCES Common Core of Data';
COMMENT ON COLUMN districts.nces_id IS 'NCES 7-digit district identifier';
COMMENT ON COLUMN districts.year IS 'School year in YYYY-YY format (e.g., 2023-24)';
COMMENT ON COLUMN districts.instructional_staff IS 'Full-time equivalent instructional staff count';

-- -----------------------------------------------------------------------------
-- State Requirements: Statutory instructional time minimums by state
-- -----------------------------------------------------------------------------
CREATE TABLE state_requirements (
    state CHAR(2) PRIMARY KEY,
    state_name VARCHAR(50) NOT NULL,
    elementary_minutes INTEGER,
    middle_minutes INTEGER,
    high_minutes INTEGER,
    default_minutes INTEGER,  -- Fallback if grade-specific not defined
    annual_days INTEGER,
    annual_hours NUMERIC(6, 2),
    notes TEXT,
    source VARCHAR(255),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Comments
COMMENT ON TABLE state_requirements IS 'State statutory minimums for instructional time';
COMMENT ON COLUMN state_requirements.elementary_minutes IS 'Daily instructional minutes for elementary (K-5/6)';
COMMENT ON COLUMN state_requirements.middle_minutes IS 'Daily instructional minutes for middle school (6-8)';
COMMENT ON COLUMN state_requirements.high_minutes IS 'Daily instructional minutes for high school (9-12)';

-- -----------------------------------------------------------------------------
-- Bell Schedules: Enriched actual instructional time data
-- -----------------------------------------------------------------------------
CREATE TABLE bell_schedules (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    year VARCHAR(10) NOT NULL,  -- "2024-25" format
    grade_level VARCHAR(20) NOT NULL,

    -- Core schedule data
    instructional_minutes INTEGER NOT NULL,
    start_time VARCHAR(20),
    end_time VARCHAR(20),
    lunch_duration INTEGER,
    passing_periods INTEGER,
    recess_duration INTEGER,  -- Typically elementary only

    -- Source documentation
    schools_sampled JSONB DEFAULT '[]'::jsonb,
    source_urls JSONB DEFAULT '[]'::jsonb,
    confidence VARCHAR(10) NOT NULL DEFAULT 'high',
    method VARCHAR(30) NOT NULL,
    source_description TEXT,
    notes TEXT,

    -- Preserve original import data for reference
    raw_import JSONB,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT chk_grade_level CHECK (grade_level IN ('elementary', 'middle', 'high')),
    CONSTRAINT chk_confidence CHECK (confidence IN ('high', 'medium', 'low')),
    CONSTRAINT chk_method CHECK (method IN ('automated_enrichment', 'human_provided', 'statutory_fallback')),
    CONSTRAINT chk_instructional_minutes CHECK (instructional_minutes BETWEEN 100 AND 600),
    CONSTRAINT chk_lunch_duration CHECK (lunch_duration IS NULL OR lunch_duration BETWEEN 10 AND 90),

    -- Unique constraint: one record per district/year/grade_level
    CONSTRAINT uq_bell_schedule UNIQUE (district_id, year, grade_level)
);

-- Indexes
CREATE INDEX idx_bell_schedules_district ON bell_schedules(district_id);
CREATE INDEX idx_bell_schedules_year ON bell_schedules(year);
CREATE INDEX idx_bell_schedules_district_year ON bell_schedules(district_id, year);
CREATE INDEX idx_bell_schedules_method ON bell_schedules(method);
CREATE INDEX idx_bell_schedules_confidence ON bell_schedules(confidence);

-- Comments
COMMENT ON TABLE bell_schedules IS 'Enriched bell schedule data with actual instructional time';
COMMENT ON COLUMN bell_schedules.grade_level IS 'Grade level category: elementary, middle, or high';
COMMENT ON COLUMN bell_schedules.instructional_minutes IS 'Daily instructional minutes (excluding lunch, passing, recess)';
COMMENT ON COLUMN bell_schedules.method IS 'Collection method: automated_enrichment, human_provided, or statutory_fallback';
COMMENT ON COLUMN bell_schedules.raw_import IS 'Original JSON from import for reference and debugging';

-- -----------------------------------------------------------------------------
-- LCT Calculations: Computed Learning Connection Time metrics
-- -----------------------------------------------------------------------------
CREATE TABLE lct_calculations (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    year VARCHAR(10) NOT NULL,
    grade_level VARCHAR(20),  -- NULL for district-wide calculation

    -- Input values (denormalized for query performance)
    instructional_minutes INTEGER NOT NULL,
    enrollment INTEGER NOT NULL,
    instructional_staff NUMERIC(10, 2) NOT NULL,

    -- Calculated metric
    lct_value NUMERIC(10, 4) NOT NULL,  -- Minutes per student per day

    -- Data quality indicators
    data_tier INTEGER NOT NULL,  -- 1=actual bell schedule, 2=automated, 3=statutory
    bell_schedule_id INTEGER REFERENCES bell_schedules(id),

    -- Timestamps
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,

    -- Constraints
    CONSTRAINT chk_data_tier CHECK (data_tier IN (1, 2, 3)),
    CONSTRAINT chk_lct_positive CHECK (lct_value > 0),
    CONSTRAINT chk_enrollment_positive CHECK (enrollment > 0),
    CONSTRAINT chk_staff_positive CHECK (instructional_staff > 0),

    -- Unique constraint: one calculation per district/year/grade_level
    CONSTRAINT uq_lct_calculation UNIQUE (district_id, year, grade_level)
);

-- Indexes
CREATE INDEX idx_lct_district ON lct_calculations(district_id);
CREATE INDEX idx_lct_year ON lct_calculations(year);
CREATE INDEX idx_lct_value ON lct_calculations(lct_value);
CREATE INDEX idx_lct_data_tier ON lct_calculations(data_tier);

-- Comments
COMMENT ON TABLE lct_calculations IS 'Computed Learning Connection Time metrics';
COMMENT ON COLUMN lct_calculations.lct_value IS 'LCT = (instructional_minutes * instructional_staff) / enrollment';
COMMENT ON COLUMN lct_calculations.data_tier IS '1=actual bell schedule, 2=automated enrichment, 3=statutory fallback';

-- -----------------------------------------------------------------------------
-- Data Lineage: Provenance tracking for audit and debugging
-- -----------------------------------------------------------------------------
CREATE TABLE data_lineage (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,  -- 'district', 'bell_schedule', 'lct_calculation'
    entity_id VARCHAR(50) NOT NULL,    -- Reference to the entity
    operation VARCHAR(30) NOT NULL,    -- 'create', 'update', 'import', 'calculate', 'migrate'
    source_file VARCHAR(500),
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT 'system'  -- 'migration', 'manual', 'pipeline', 'claude'
);

-- Indexes
CREATE INDEX idx_lineage_entity ON data_lineage(entity_type, entity_id);
CREATE INDEX idx_lineage_operation ON data_lineage(operation);
CREATE INDEX idx_lineage_created_at ON data_lineage(created_at);

-- Comments
COMMENT ON TABLE data_lineage IS 'Audit trail for data changes and imports';
COMMENT ON COLUMN data_lineage.entity_type IS 'Type of entity: district, bell_schedule, lct_calculation';
COMMENT ON COLUMN data_lineage.operation IS 'Operation performed: create, update, import, calculate, migrate';

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply to tables with updated_at
CREATE TRIGGER update_districts_updated_at
    BEFORE UPDATE ON districts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_bell_schedules_updated_at
    BEFORE UPDATE ON bell_schedules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_state_requirements_updated_at
    BEFORE UPDATE ON state_requirements
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- VIEWS FOR COMMON QUERIES
-- =============================================================================

-- View: Districts with enriched bell schedules
CREATE OR REPLACE VIEW v_enriched_districts AS
SELECT DISTINCT
    d.nces_id,
    d.name,
    d.state,
    d.enrollment,
    d.instructional_staff,
    bs.year AS schedule_year,
    COUNT(DISTINCT bs.grade_level) AS grade_levels_enriched,
    MAX(bs.confidence) AS max_confidence,
    MAX(bs.method) AS collection_method
FROM districts d
INNER JOIN bell_schedules bs ON d.nces_id = bs.district_id
WHERE bs.method != 'statutory_fallback'
GROUP BY d.nces_id, d.name, d.state, d.enrollment, d.instructional_staff, bs.year;

COMMENT ON VIEW v_enriched_districts IS 'Districts that have actual bell schedule data (not statutory fallback)';

-- View: State-level summary statistics
CREATE OR REPLACE VIEW v_state_summary AS
SELECT
    d.state,
    COUNT(DISTINCT d.nces_id) AS total_districts,
    COUNT(DISTINCT bs.district_id) AS enriched_districts,
    ROUND(100.0 * COUNT(DISTINCT bs.district_id) / COUNT(DISTINCT d.nces_id), 2) AS enrichment_pct,
    SUM(d.enrollment) AS total_enrollment,
    AVG(lct.lct_value) AS avg_lct
FROM districts d
LEFT JOIN bell_schedules bs ON d.nces_id = bs.district_id AND bs.method != 'statutory_fallback'
LEFT JOIN lct_calculations lct ON d.nces_id = lct.district_id
GROUP BY d.state
ORDER BY d.state;

COMMENT ON VIEW v_state_summary IS 'State-level aggregation of district and enrichment data';

-- View: Top districts by enrollment
CREATE OR REPLACE VIEW v_top_districts AS
SELECT
    d.nces_id,
    d.name,
    d.state,
    d.enrollment,
    d.instructional_staff,
    CASE WHEN bs.id IS NOT NULL THEN true ELSE false END AS is_enriched,
    bs.method AS enrichment_method,
    lct.lct_value
FROM districts d
LEFT JOIN bell_schedules bs ON d.nces_id = bs.district_id
LEFT JOIN lct_calculations lct ON d.nces_id = lct.district_id
WHERE d.enrollment IS NOT NULL
ORDER BY d.enrollment DESC;

COMMENT ON VIEW v_top_districts IS 'Districts ordered by enrollment with enrichment status';

-- =============================================================================
-- INITIAL DATA VERIFICATION QUERIES (for testing after migration)
-- =============================================================================

-- These can be run after migration to verify data integrity:
-- SELECT COUNT(*) AS district_count FROM districts;  -- Expect: 19,637
-- SELECT COUNT(DISTINCT district_id) AS enriched_count FROM bell_schedules WHERE method != 'statutory_fallback';  -- Expect: 77
-- SELECT state, COUNT(*) FROM districts GROUP BY state ORDER BY state;  -- Verify state distribution
-- SELECT method, COUNT(*) FROM bell_schedules GROUP BY method;  -- Verify method distribution

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
