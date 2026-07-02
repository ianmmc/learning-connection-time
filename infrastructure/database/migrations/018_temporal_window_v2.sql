-- ============================================================================
-- Migration 018: Temporal blend window v2 + LCT idempotency backstop
-- Date: 2026-07-02
-- Issues: #11 (inert trigger — companion code change populates *_source_year),
--         #12 (COVID exclusion), #25 (unique-constraint backstop for scope rows)
--
-- Window semantics (decided by Ian 2026-07-01, supersedes 008's span<=3):
--   Data blended into one calculation may span at most THREE CONSECUTIVE school
--   years — max start-year span = 2. {2023-24, 2024-25, 2025-26} is valid;
--   {2022-23 .. 2025-26} (span 3 = four school years) is not. COVID exclusion
--   (2019-20 .. 2022-23) applies FIRST and is enforced in the trigger too:
--   a COVID source year is an error regardless of span. The SPED 2017-18
--   baseline is exempt (it is a ratio proxy carried in staff_source via the
--   sped_estimate path, not in these three source-year columns).
--
-- Flags: span 0-1 -> none · span 2 -> WARN_YEAR_GAP (valid, notable) ·
--        span >2 -> ERR_SPAN_EXCEEDED · any COVID year -> ERR_COVID_YEAR.
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_lct_temporal()
RETURNS TRIGGER AS $$
DECLARE
    span INTEGER;
    covid_years TEXT[] := ARRAY['2019-20', '2020-21', '2021-22', '2022-23'];
BEGIN
    span := (
        SELECT MAX(y) - MIN(y)
        FROM (
            SELECT school_year_to_numeric(NEW.enrollment_source_year) AS y
            WHERE NEW.enrollment_source_year IS NOT NULL
            UNION ALL
            SELECT school_year_to_numeric(NEW.staff_source_year)
            WHERE NEW.staff_source_year IS NOT NULL
            UNION ALL
            SELECT school_year_to_numeric(NEW.bell_schedule_source_year)
            WHERE NEW.bell_schedule_source_year IS NOT NULL
        ) AS years
        WHERE y IS NOT NULL
    );

    NEW.year_span := span;
    NEW.within_3year_window := (span IS NULL OR span <= 2);

    IF NEW.temporal_flags IS NULL THEN
        NEW.temporal_flags := ARRAY[]::TEXT[];
    END IF;

    IF span = 2 AND NOT ('WARN_YEAR_GAP' = ANY(NEW.temporal_flags)) THEN
        NEW.temporal_flags := array_append(NEW.temporal_flags, 'WARN_YEAR_GAP');
    END IF;

    IF span > 2 AND NOT ('ERR_SPAN_EXCEEDED' = ANY(NEW.temporal_flags)) THEN
        NEW.temporal_flags := array_append(NEW.temporal_flags, 'ERR_SPAN_EXCEEDED');
    END IF;

    -- COVID exclusion (Rule #2): a COVID-era source year is invalid outright
    IF (NEW.enrollment_source_year = ANY(covid_years)
        OR NEW.staff_source_year = ANY(covid_years)
        OR NEW.bell_schedule_source_year = ANY(covid_years)) THEN
        NEW.within_3year_window := FALSE;
        IF NOT ('ERR_COVID_YEAR' = ANY(NEW.temporal_flags)) THEN
            NEW.temporal_flags := array_append(NEW.temporal_flags, 'ERR_COVID_YEAR');
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- (trigger trg_lct_temporal_validation from 008 keeps firing this replaced function)

COMMENT ON COLUMN lct_calculations.temporal_flags IS
'Temporal validation flags (year_span = max-min of source start years; semantics v2, 2026-07-01):
- No flags: span 0-1 (same or adjacent school years)
- WARN_YEAR_GAP: span 2 — three consecutive school years blended (valid, notable)
- ERR_SPAN_EXCEEDED: span >2 — exceeds the 3-consecutive-school-year window
- ERR_COVID_YEAR: a COVID-era source year (2019-20..2022-23) — invalid regardless of span
- INFO_RATIO_BASELINE: SPED 2017-18 ratio baseline (exempt from the window)';

-- Idempotency backstop (issue #25): scope-based rows carry grade_level = NULL, and NULLs are
-- distinct in a unique CONSTRAINT — so uq_lct_calculation_v2 never fired for them. This partial
-- unique INDEX makes a double-write of the same (district, year, scope) row impossible even if
-- the clear step is ever skipped.
CREATE UNIQUE INDEX IF NOT EXISTS uq_lct_scope_rows
    ON lct_calculations (district_id, year, staff_scope)
    WHERE grade_level IS NULL;

-- The standalone helper from 008 (used by v_lct_temporal_validation and tests) gets the
-- same v2 boundary: 3 consecutive school years = span <= 2.
CREATE OR REPLACE FUNCTION is_within_3year_window(
    enrollment_year VARCHAR(10),
    staffing_year VARCHAR(10),
    bell_schedule_year VARCHAR(10)
)
RETURNS BOOLEAN AS $$
DECLARE
    years INTEGER[];
    min_year INTEGER;
    max_year INTEGER;
    span INTEGER;
BEGIN
    years := ARRAY[]::INTEGER[];
    IF enrollment_year IS NOT NULL THEN
        years := array_append(years, school_year_to_numeric(enrollment_year));
    END IF;
    IF staffing_year IS NOT NULL THEN
        years := array_append(years, school_year_to_numeric(staffing_year));
    END IF;
    IF bell_schedule_year IS NOT NULL THEN
        years := array_append(years, school_year_to_numeric(bell_schedule_year));
    END IF;
    IF array_length(years, 1) IS NULL OR array_length(years, 1) < 2 THEN
        RETURN TRUE;
    END IF;
    SELECT MIN(y), MAX(y) INTO min_year, max_year FROM unnest(years) AS y;
    span := max_year - min_year;
    RETURN span <= 2;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
