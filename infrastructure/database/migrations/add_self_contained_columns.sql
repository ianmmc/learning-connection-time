-- Migration: Add self-contained SPED columns
-- Date: January 3, 2026
-- Purpose: Support two-step ratio for self-contained SPED estimation

-- Add self-contained columns to sped_state_baseline
ALTER TABLE sped_state_baseline
ADD COLUMN IF NOT EXISTS sped_students_self_contained INTEGER,
ADD COLUMN IF NOT EXISTS sped_students_mainstreamed INTEGER,
ADD COLUMN IF NOT EXISTS ratio_self_contained_proportion NUMERIC(10, 6);

-- Add self-contained columns to sped_estimates
ALTER TABLE sped_estimates
ADD COLUMN IF NOT EXISTS ratio_state_self_contained_proportion NUMERIC(10, 6),
ADD COLUMN IF NOT EXISTS estimated_self_contained_sped INTEGER;

-- Add comments for documentation
COMMENT ON COLUMN sped_state_baseline.sped_students_self_contained IS 'Self-contained SPED students: Separate Class + Separate School + <40% in regular class';
COMMENT ON COLUMN sped_state_baseline.sped_students_mainstreamed IS 'Mainstreamed SPED students: 80%+ and 40-79% in regular class';
COMMENT ON COLUMN sped_state_baseline.ratio_self_contained_proportion IS 'Self-Contained / All SPED ratio for LEA estimation';
COMMENT ON COLUMN sped_estimates.ratio_state_self_contained_proportion IS 'State self-contained proportion used for estimation';
COMMENT ON COLUMN sped_estimates.estimated_self_contained_sped IS 'Estimated self-contained SPED students (for LCT calculation)';
