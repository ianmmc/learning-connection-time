-- ============================================================================
-- Migration 032: per-LEA IDEA educational-environment counts on sped_lea_baseline
-- Date: 2026-10-31
-- Issue: #1004 (SPED baseline refresh T6; epic #724)
--
-- The IDEA 618 LEA environments file (beducationalenvironmentslea2024-25.csv)
-- publishes each LEA's school-age SPED count and its self-contained count (inside
-- regular class less than 40 percent of the day + separate school). Stored RAW;
-- the rule that decides when a district uses its own share instead of its state's
-- (Ian, 2026-10-31: at least 200 school-age SPED students) lives in the vintage
-- profile and is applied when the ratios are derived, so the rule stays data.
-- Suppressed cells (-8 small cell, -9 data quality, blank) are stored NULL.
-- ============================================================================

ALTER TABLE sped_lea_baseline
    ADD COLUMN IF NOT EXISTS idea_lea_year VARCHAR(10),
    ADD COLUMN IF NOT EXISTS idea_school_age_total INTEGER,
    ADD COLUMN IF NOT EXISTS idea_self_contained INTEGER;

COMMENT ON COLUMN sped_lea_baseline.idea_lea_year IS
'#1004: data year of the IDEA 618 LEA environments file the idea_* counts come from (NULL = not loaded for this vintage).';
COMMENT ON COLUMN sped_lea_baseline.idea_school_age_total IS
'#1004: IDEA school-age SPED students, all educational environments (NULL = suppressed or not reported).';
COMMENT ON COLUMN sped_lea_baseline.idea_self_contained IS
'#1004: IDEA school-age SPED students inside regular class less than 40 percent of the day + separate school (NULL when either cell is suppressed).';
