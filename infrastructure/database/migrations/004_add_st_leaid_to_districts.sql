-- Migration 004: Add st_leaid to districts table
-- Created: 2026-01-09
-- Description: Adds ST_LEAID field for California CDS crosswalk

-- Add st_leaid column
ALTER TABLE districts ADD COLUMN IF NOT EXISTS st_leaid VARCHAR(20);

-- Add index for California district lookups
CREATE INDEX IF NOT EXISTS ix_districts_st_leaid ON districts(st_leaid) WHERE st_leaid IS NOT NULL;

-- Add comment
COMMENT ON COLUMN districts.st_leaid IS 'State-assigned LEA ID (e.g., CA-6275796 for California CDS codes)';
