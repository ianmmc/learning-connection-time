-- ============================================================================
-- Migration 029: multi-vintage SPED baseline tables
-- Date: 2026-10-31
-- Issue: #999 (IDEA 618 / CRDC SPED baseline refresh, T1; epic #724)
--
-- sped_state_baseline was keyed by state alone and sped_lea_baseline by lea_id
-- alone, so they could hold ONE vintage: importing the refreshed IDEA/CRDC data
-- would have overwritten 2017-18 with no side-by-side and no rollback but a dump.
--
-- Now each row is keyed by (state|lea_id, baseline_year). A baseline vintage is a
-- SET of components whose own data years differ (the 2024-25 set pairs 2023-24
-- personnel with the 2024-25 child count and 2023-24 CRDC + CCD), so each
-- component's year is recorded separately. Plan + acceptance (A1):
-- docs/technical-notes/production-quality-control-research/2026-10-31-idea-crdc-sped-baseline-refresh-plan.md
--
-- Renames (no consumer outside the SPED importer/model reads them):
--   source_year             -> baseline_year       (both tables; it names the set)
--   sped_students_ages_6_21 -> sped_students_school_age      (band in school_age_band)
--   sped_students_ages_3_5  -> sped_students_early_childhood (since 2020-21 IDEA
--                              moves kindergarten 5-year-olds into school age)
-- Every existing row is 2017-18 in every component, on the 6-21 band; values are
-- otherwise untouched (A1: 2017-18 rows unchanged value for value).
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'sped_state_baseline' AND column_name = 'source_year') THEN
        ALTER TABLE sped_state_baseline RENAME COLUMN source_year TO baseline_year;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'sped_state_baseline' AND column_name = 'sped_students_ages_6_21') THEN
        ALTER TABLE sped_state_baseline RENAME COLUMN sped_students_ages_6_21 TO sped_students_school_age;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'sped_state_baseline' AND column_name = 'sped_students_ages_3_5') THEN
        ALTER TABLE sped_state_baseline RENAME COLUMN sped_students_ages_3_5 TO sped_students_early_childhood;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'sped_lea_baseline' AND column_name = 'source_year') THEN
        ALTER TABLE sped_lea_baseline RENAME COLUMN source_year TO baseline_year;
    END IF;
END $$;

-- ---------------------------------------------------------------- sped_state_baseline
ALTER TABLE sped_state_baseline
    ADD COLUMN IF NOT EXISTS personnel_year VARCHAR(10),
    ADD COLUMN IF NOT EXISTS child_count_year VARCHAR(10),
    ADD COLUMN IF NOT EXISTS school_age_band VARCHAR(10),
    ADD COLUMN IF NOT EXISTS sped_students_age_5_school_age INTEGER;

UPDATE sped_state_baseline SET personnel_year = baseline_year WHERE personnel_year IS NULL;
UPDATE sped_state_baseline SET child_count_year = baseline_year WHERE child_count_year IS NULL;
UPDATE sped_state_baseline SET school_age_band = '6-21' WHERE school_age_band IS NULL;

ALTER TABLE sped_state_baseline
    ALTER COLUMN personnel_year SET NOT NULL,
    ALTER COLUMN child_count_year SET NOT NULL,
    ALTER COLUMN school_age_band SET NOT NULL;

ALTER TABLE sped_state_baseline DROP CONSTRAINT IF EXISTS chk_sped_state_school_age_band;
ALTER TABLE sped_state_baseline ADD CONSTRAINT chk_sped_state_school_age_band
    CHECK (school_age_band IN ('6-21', '5-21'));

ALTER TABLE sped_state_baseline DROP CONSTRAINT IF EXISTS sped_state_baseline_pkey;
ALTER TABLE sped_state_baseline ADD CONSTRAINT sped_state_baseline_pkey PRIMARY KEY (state, baseline_year);

COMMENT ON COLUMN sped_state_baseline.baseline_year IS
'#999: the baseline vintage this row belongs to (a SET of components; each component''s own year is personnel_year / child_count_year). apply_sped_estimates --baseline-year selects on it.';
COMMENT ON COLUMN sped_state_baseline.school_age_band IS
'#1000: ages the school-age counts cover — ''6-21'' (the 2017-18 definition) or ''5-21'' (IDEA ''School Age'' since 2020-21, kindergarten 5-year-olds included).';
COMMENT ON COLUMN sped_state_baseline.sped_students_self_contained IS
'Self-contained SPED students (school age, on school_age_band): the inside-regular-class-less-than-40-percent row + the school-age separate-school row (#970; Separate Class is an early-childhood setting)';

-- ---------------------------------------------------------------- sped_lea_baseline
ALTER TABLE sped_lea_baseline
    ADD COLUMN IF NOT EXISTS crdc_year VARCHAR(10),
    ADD COLUMN IF NOT EXISTS ccd_year VARCHAR(10),
    ADD COLUMN IF NOT EXISTS crdc_schools_reserved INTEGER;

UPDATE sped_lea_baseline SET crdc_year = baseline_year WHERE crdc_year IS NULL;
UPDATE sped_lea_baseline SET ccd_year = baseline_year WHERE ccd_year IS NULL;

ALTER TABLE sped_lea_baseline
    ALTER COLUMN crdc_year SET NOT NULL,
    ALTER COLUMN ccd_year SET NOT NULL;

ALTER TABLE sped_lea_baseline DROP CONSTRAINT IF EXISTS sped_lea_baseline_pkey;
ALTER TABLE sped_lea_baseline ADD CONSTRAINT sped_lea_baseline_pkey PRIMARY KEY (lea_id, baseline_year);

COMMENT ON COLUMN sped_lea_baseline.baseline_year IS
'#999: the baseline vintage this row belongs to; the CRDC and CCD components'' own years are crdc_year / ccd_year.';
COMMENT ON COLUMN sped_lea_baseline.crdc_schools_reserved IS
'#960: schools excluded pairwise (from SPED AND total) for carrying a CRDC reserve code. NULL = imported before the exclusion existed.';
