-- Migration 014: Add staff_scope to lct_calculations
-- Created: 2026-01-24
-- Purpose: Support scope-based LCT calculations (teachers_only, instructional, etc.)

-- Add staff_scope column to lct_calculations
-- This allows storing different LCT variants (teachers_only, teachers_core, etc.)
-- alongside traditional grade-level calculations
ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS staff_scope VARCHAR(50) DEFAULT 'teachers_only';

-- Add staff source tracking
ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS staff_source VARCHAR(100);

ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS staff_year VARCHAR(10);

-- Add minutes source tracking
ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS instructional_minutes_source VARCHAR(100);

ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS instructional_minutes_year VARCHAR(10);

-- Add enrollment type for SPED segmentation
ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS enrollment_type VARCHAR(50) DEFAULT 'k12';

-- Add run_id to link calculations to their calculation run
ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS run_id VARCHAR(50);

-- Update constraint to allow multiple scopes per district/year/grade
-- Drop the old constraint first
ALTER TABLE lct_calculations
DROP CONSTRAINT IF EXISTS uq_lct_calculation;

-- Create new unique constraint that includes staff_scope
ALTER TABLE lct_calculations
ADD CONSTRAINT uq_lct_calculation_v2
UNIQUE (district_id, year, grade_level, staff_scope);

-- Create index for common queries
CREATE INDEX IF NOT EXISTS idx_lct_staff_scope ON lct_calculations(staff_scope);
CREATE INDEX IF NOT EXISTS idx_lct_run_id ON lct_calculations(run_id);

-- Add valid scope check constraint
ALTER TABLE lct_calculations
DROP CONSTRAINT IF EXISTS chk_staff_scope;

ALTER TABLE lct_calculations
ADD CONSTRAINT chk_staff_scope CHECK (
    staff_scope IN (
        'teachers_only',
        'teachers_core',
        'teachers_elementary',
        'teachers_secondary',
        'instructional',
        'instructional_plus_support',
        'all',
        'core_sped',
        'teachers_gened',
        'instructional_sped'
    )
);

-- Update data_tier constraint to allow more flexibility
ALTER TABLE lct_calculations
DROP CONSTRAINT IF EXISTS chk_data_tier;

-- Data tier now represents:
-- 1 = Bell schedule from district website (highest quality)
-- 2 = Bell schedule from any available level fallback
-- 3 = State statutory minimum (fallback)
ALTER TABLE lct_calculations
ADD CONSTRAINT chk_data_tier CHECK (data_tier IN (1, 2, 3));

COMMENT ON COLUMN lct_calculations.staff_scope IS 'LCT staff scope variant (teachers_only, instructional, etc.)';
COMMENT ON COLUMN lct_calculations.staff_source IS 'Source of staff data (nces_ccd, sped_estimate_2017-18, etc.)';
COMMENT ON COLUMN lct_calculations.staff_year IS 'Year of staff data (2023-24, etc.)';
COMMENT ON COLUMN lct_calculations.instructional_minutes_source IS 'Source of minutes (bell_schedule, state_requirement, default)';
COMMENT ON COLUMN lct_calculations.instructional_minutes_year IS 'Year of bell schedule data';
COMMENT ON COLUMN lct_calculations.enrollment_type IS 'Type of enrollment used (k12, elementary_k5, secondary_6_12, self_contained_sped, gened)';
COMMENT ON COLUMN lct_calculations.run_id IS 'Link to calculation_runs.run_id for this calculation';
