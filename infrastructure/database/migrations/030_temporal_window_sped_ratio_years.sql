-- ============================================================================
-- Migration 030: the SPED ratio vintages enter the REQ-026 window
-- Date: 2026-10-31
-- Issue: #1003 (IDEA 618 / CRDC SPED baseline refresh, T5; epic #724)
--
-- Until now the SPED baseline was EXEMPT from the blend window — "a ratio proxy, not
-- blended data" — and nothing checked its vintage: every SPED row carried only the
-- estimate year (the CCD year the ratios were applied to), so a 2017-18 ratio set was
-- invisible to the span. Ian, 2026-10-31: retire the exemption.
--
-- calculate_lct_variants now writes, on every SPED-scope row,
--     component_years = {"sped_ratio": [<the baseline's component data years>]}
-- (IDEA personnel + child count, CRDC + CCD — from sped_state_baseline /
-- sped_lea_baseline, #999). This trigger folds those years into the span and the
-- COVID check exactly like the three *_source_year columns. component_years was
-- declared in migration 002 for this purpose and never written before.
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_lct_temporal()
RETURNS TRIGGER AS $$
DECLARE
    span INTEGER;
    covid_years TEXT[] := ARRAY['2019-20', '2020-21', '2021-22', '2022-23'];
    ratio_years TEXT[];
BEGIN
    ratio_years := CASE
        WHEN jsonb_typeof(NEW.component_years -> 'sped_ratio') = 'array'
        THEN ARRAY(SELECT jsonb_array_elements_text(NEW.component_years -> 'sped_ratio'))
        ELSE ARRAY[]::TEXT[]
    END;

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
            UNION ALL
            SELECT school_year_to_numeric(r) FROM unnest(ratio_years) AS r
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
        OR NEW.bell_schedule_source_year = ANY(covid_years)
        OR ratio_years && covid_years) THEN
        NEW.within_3year_window := FALSE;
        IF NOT ('ERR_COVID_YEAR' = ANY(NEW.temporal_flags)) THEN
            NEW.temporal_flags := array_append(NEW.temporal_flags, 'ERR_COVID_YEAR');
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON COLUMN lct_calculations.component_years IS
'Extra source-year components the temporal trigger windows (migration 030, #1003): {"sped_ratio": [years]} on SPED-scope rows — the applied SPED baseline vintage''s IDEA personnel / child count and CRDC / CCD data years.';
