-- Migration 016: per-school schedule sampling + district aggregation distribution
-- Created: 2026-06-06
-- Purpose: Support enrollment-weighted-mean instructional minutes per district grade band,
--          computed from a SAMPLE of schools, with (min, mode, max) distribution captured
--          for transparency (the "averaging deception" governing principle).
--
-- Model: school_schedules holds raw per-school observations; bell_schedules holds the
--        district grade-band aggregate (its instructional_minutes becomes the weighted mean,
--        and the new columns expose the distribution + sample provenance).
--
-- NOTE: per-school enrollment (the weights) requires NCES CCD school-level membership, which
--       is not yet imported. Until then, aggregation falls back to a simple mean.

CREATE TABLE IF NOT EXISTS school_schedules (
    id                     SERIAL PRIMARY KEY,
    district_id            VARCHAR(10) NOT NULL REFERENCES districts(nces_id),
    school_id              VARCHAR(20),          -- NCES school id, when known
    school_name            TEXT,
    year                   VARCHAR(10),
    grade_level            VARCHAR(20),          -- band: elementary | middle | high
    start_time             VARCHAR(10),          -- HH:MM 24-hour
    end_time               VARCHAR(10),          -- HH:MM 24-hour
    lunch_minutes          INTEGER,
    passing_minutes        INTEGER,
    instructional_minutes  INTEGER,              -- computed daily instructional minutes
    enrollment             INTEGER,              -- school enrollment (weight); null until CCD school import
    source_file            TEXT,
    source_url             TEXT,
    method                 VARCHAR(40),
    confidence             VARCHAR(20),
    notes                  TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_school_schedules_district
    ON school_schedules(district_id, grade_level);

-- District grade-band aggregate: distribution + sample provenance
ALTER TABLE bell_schedules ADD COLUMN IF NOT EXISTS minutes_weighted_mean NUMERIC;
ALTER TABLE bell_schedules ADD COLUMN IF NOT EXISTS minutes_min           INTEGER;
ALTER TABLE bell_schedules ADD COLUMN IF NOT EXISTS minutes_mode          INTEGER;
ALTER TABLE bell_schedules ADD COLUMN IF NOT EXISTS minutes_max           INTEGER;
ALTER TABLE bell_schedules ADD COLUMN IF NOT EXISTS schools_in_sample     INTEGER;
ALTER TABLE bell_schedules ADD COLUMN IF NOT EXISTS enrollment_in_sample  INTEGER;
ALTER TABLE bell_schedules ADD COLUMN IF NOT EXISTS aggregation_method    VARCHAR(40);

COMMENT ON TABLE school_schedules IS
    'Per-school sampled bell schedules; aggregated to district grade-band values in bell_schedules.';
COMMENT ON COLUMN bell_schedules.minutes_weighted_mean IS
    'Enrollment-weighted mean of per-school instructional minutes (the district grade-band value).';
COMMENT ON COLUMN bell_schedules.minutes_mode IS
    'Most common per-school instructional-minutes value in the sample (transparency).';
COMMENT ON COLUMN bell_schedules.aggregation_method IS
    'How the grade-band value was derived: enrollment_weighted_mean | simple_mean | single_school.';
