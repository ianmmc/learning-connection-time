-- Migration 009: Update calculation_runs for temporal blending support
-- Created: 2026-01-20
-- Description: Adds calculation_mode enum and updates schema for REQ-026 compliant calculations
--
-- Changes:
-- 1. Create calculation_mode_enum type
-- 2. Add calculation_mode column (default: 'blended')
-- 3. Rename 'year' to 'target_year' and make nullable
-- 4. Add data_year_min and data_year_max for tracking actual data range
-- 5. Add constraint: TARGET_YEAR mode requires target_year to be set

-- ============================================================================
-- 1. Create Enum Type
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'calculation_mode_enum') THEN
        CREATE TYPE calculation_mode_enum AS ENUM ('blended', 'target_year');
    END IF;
END$$;

-- ============================================================================
-- 2. Add calculation_mode column
-- ============================================================================

ALTER TABLE calculation_runs
ADD COLUMN IF NOT EXISTS calculation_mode calculation_mode_enum NOT NULL DEFAULT 'blended';

-- ============================================================================
-- 3. Rename year to target_year and make nullable
-- ============================================================================

-- Check if 'year' column exists (might already be renamed)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'calculation_runs' AND column_name = 'year'
    ) THEN
        ALTER TABLE calculation_runs RENAME COLUMN year TO target_year;
    END IF;
END$$;

-- Make target_year nullable
ALTER TABLE calculation_runs ALTER COLUMN target_year DROP NOT NULL;

-- ============================================================================
-- 4. Add data range tracking columns
-- ============================================================================

ALTER TABLE calculation_runs
ADD COLUMN IF NOT EXISTS data_year_min VARCHAR(10);

ALTER TABLE calculation_runs
ADD COLUMN IF NOT EXISTS data_year_max VARCHAR(10);

-- ============================================================================
-- 5. Add constraint for TARGET_YEAR mode
-- ============================================================================

-- Drop constraint if it exists (for idempotent migrations)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'chk_target_year_required'
    ) THEN
        ALTER TABLE calculation_runs DROP CONSTRAINT chk_target_year_required;
    END IF;
END$$;

-- Add constraint: TARGET_YEAR mode requires target_year to be set
ALTER TABLE calculation_runs
ADD CONSTRAINT chk_target_year_required
CHECK (
    calculation_mode = 'blended'
    OR (calculation_mode = 'target_year' AND target_year IS NOT NULL)
);

-- ============================================================================
-- 6. Update existing records
-- ============================================================================

-- Set calculation_mode to 'target_year' for records that have a year set
UPDATE calculation_runs
SET calculation_mode = 'target_year'
WHERE target_year IS NOT NULL
  AND calculation_mode = 'blended';

-- ============================================================================
-- 7. Add helpful comments
-- ============================================================================

COMMENT ON COLUMN calculation_runs.calculation_mode IS
'Calculation mode: blended (most recent within REQ-026 window) or target_year (enrollment anchored)';

COMMENT ON COLUMN calculation_runs.target_year IS
'Target year for enrollment anchor (required for target_year mode, optional for blended)';

COMMENT ON COLUMN calculation_runs.data_year_min IS
'Earliest source year actually used in this calculation run';

COMMENT ON COLUMN calculation_runs.data_year_max IS
'Latest source year actually used in this calculation run';

-- ============================================================================
-- Migration Complete
-- ============================================================================

COMMENT ON TABLE calculation_runs IS
'Tracks LCT calculation runs. Supports blended (REQ-026 compliant) and target_year modes.';
