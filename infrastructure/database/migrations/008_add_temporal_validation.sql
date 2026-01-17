-- Migration 008: Temporal Data Validation - 3-Year Blending Window
-- Created: 2026-01-16
-- Description: Adds temporal validation infrastructure for multi-year data blending
--
-- Rule: Data from multiple sources must span ≤3 consecutive school years
-- Exception: SPED baseline ratios (2017-18 IDEA 618/CRDC) are exempt as ratio proxies

-- ============================================================================
-- 1. School Year Utilities
-- ============================================================================

-- Convert school year string to numeric for calculations
-- e.g., '2023-24' -> 2023, '2024-25' -> 2024
CREATE OR REPLACE FUNCTION school_year_to_numeric(year_str VARCHAR(10))
RETURNS INTEGER AS $$
BEGIN
    -- Handle formats: '2023-24', '2023', '2023-2024'
    IF year_str IS NULL OR year_str = '' THEN
        RETURN NULL;
    END IF;

    -- Extract first 4 digits (the starting year)
    RETURN CAST(SUBSTRING(year_str FROM 1 FOR 4) AS INTEGER);
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Calculate year span between two school years
-- e.g., span('2023-24', '2025-26') -> 3
CREATE OR REPLACE FUNCTION year_span(year1 VARCHAR(10), year2 VARCHAR(10))
RETURNS INTEGER AS $$
DECLARE
    y1 INTEGER;
    y2 INTEGER;
BEGIN
    y1 := school_year_to_numeric(year1);
    y2 := school_year_to_numeric(year2);

    IF y1 IS NULL OR y2 IS NULL THEN
        RETURN NULL;
    END IF;

    -- Span is the difference + 1 (inclusive)
    RETURN ABS(y2 - y1) + 1;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Check if a calculation's component years are within the 3-year window
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
    -- Collect non-null years
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

    -- If fewer than 2 years, no span to check
    IF array_length(years, 1) IS NULL OR array_length(years, 1) < 2 THEN
        RETURN TRUE;
    END IF;

    -- Calculate span
    SELECT MIN(y), MAX(y) INTO min_year, max_year FROM unnest(years) AS y;
    span := max_year - min_year + 1;

    RETURN span <= 3;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- 2. Add Temporal Validation Columns to LCT Calculations
-- ============================================================================

-- Add computed span column
ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS year_span INTEGER;

-- Add within-window flag
ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS within_3year_window BOOLEAN DEFAULT TRUE;

-- Add temporal validation flag (for flagging span violations)
ALTER TABLE lct_calculations
ADD COLUMN IF NOT EXISTS temporal_flags TEXT[];

-- ============================================================================
-- 3. Update Existing Calculations with Span Info
-- ============================================================================

-- Update year_span for existing records
UPDATE lct_calculations
SET year_span = (
    SELECT MAX(y) - MIN(y) + 1
    FROM (
        SELECT school_year_to_numeric(enrollment_source_year) AS y
        WHERE enrollment_source_year IS NOT NULL
        UNION ALL
        SELECT school_year_to_numeric(staff_source_year)
        WHERE staff_source_year IS NOT NULL
        UNION ALL
        SELECT school_year_to_numeric(bell_schedule_source_year)
        WHERE bell_schedule_source_year IS NOT NULL
    ) AS years
    WHERE y IS NOT NULL
)
WHERE year_span IS NULL;

-- Update within_3year_window flag
UPDATE lct_calculations
SET within_3year_window = is_within_3year_window(
    enrollment_source_year,
    staff_source_year,
    bell_schedule_source_year
)
WHERE within_3year_window IS NULL;

-- ============================================================================
-- 4. Temporal Data Quality Flags
-- ============================================================================

-- Flag definitions:
-- WARN_YEAR_GAP: Sources span 2-3 years (valid but notable)
-- ERR_SPAN_EXCEEDED: Sources span >3 years (requires resolution)
-- INFO_CROSS_YEAR: Different years used for different components
-- INFO_RATIO_BASELINE: Uses SPED ratio baseline (2017-18, exempt from rule)

-- Update temporal_flags for existing records
UPDATE lct_calculations
SET temporal_flags = ARRAY[]::TEXT[]
WHERE temporal_flags IS NULL;

-- Add WARN_YEAR_GAP flag where span is 2-3 years
UPDATE lct_calculations
SET temporal_flags = array_append(
    COALESCE(temporal_flags, ARRAY[]::TEXT[]),
    'WARN_YEAR_GAP'
)
WHERE year_span BETWEEN 2 AND 3
  AND NOT ('WARN_YEAR_GAP' = ANY(COALESCE(temporal_flags, ARRAY[]::TEXT[])));

-- Add ERR_SPAN_EXCEEDED flag where span > 3 years
UPDATE lct_calculations
SET temporal_flags = array_append(
    COALESCE(temporal_flags, ARRAY[]::TEXT[]),
    'ERR_SPAN_EXCEEDED'
)
WHERE year_span > 3
  AND NOT ('ERR_SPAN_EXCEEDED' = ANY(COALESCE(temporal_flags, ARRAY[]::TEXT[])));

-- ============================================================================
-- 5. View: Calculations with Temporal Validation
-- ============================================================================

CREATE OR REPLACE VIEW v_lct_temporal_validation AS
SELECT
    lc.id,
    lc.district_id,
    d.name AS district_name,
    d.state,
    lc.year AS target_year,
    lc.enrollment_source_year,
    lc.staff_source_year,
    lc.bell_schedule_source_year,
    lc.year_span,
    lc.within_3year_window,
    lc.temporal_flags,
    lc.lct_value,
    lc.staff_scope,
    CASE
        WHEN lc.year_span IS NULL THEN 'UNKNOWN'
        WHEN lc.year_span = 1 THEN 'SAME_YEAR'
        WHEN lc.year_span <= 3 THEN 'VALID_BLEND'
        ELSE 'SPAN_EXCEEDED'
    END AS temporal_status
FROM lct_calculations lc
LEFT JOIN districts d ON lc.district_id = d.nces_id;

-- ============================================================================
-- 6. Function: Validate Calculation Before Insert
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_lct_temporal()
RETURNS TRIGGER AS $$
DECLARE
    span INTEGER;
    flags TEXT[];
BEGIN
    -- Calculate span
    span := (
        SELECT MAX(y) - MIN(y) + 1
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

    -- Set span
    NEW.year_span := span;

    -- Check 3-year window
    NEW.within_3year_window := (span IS NULL OR span <= 3);

    -- Initialize flags array if null
    IF NEW.temporal_flags IS NULL THEN
        NEW.temporal_flags := ARRAY[]::TEXT[];
    END IF;

    -- Add appropriate flags
    IF span BETWEEN 2 AND 3 THEN
        IF NOT ('WARN_YEAR_GAP' = ANY(NEW.temporal_flags)) THEN
            NEW.temporal_flags := array_append(NEW.temporal_flags, 'WARN_YEAR_GAP');
        END IF;
    END IF;

    IF span > 3 THEN
        IF NOT ('ERR_SPAN_EXCEEDED' = ANY(NEW.temporal_flags)) THEN
            NEW.temporal_flags := array_append(NEW.temporal_flags, 'ERR_SPAN_EXCEEDED');
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for automatic validation
DROP TRIGGER IF EXISTS trg_lct_temporal_validation ON lct_calculations;
CREATE TRIGGER trg_lct_temporal_validation
    BEFORE INSERT OR UPDATE ON lct_calculations
    FOR EACH ROW
    EXECUTE FUNCTION validate_lct_temporal();

-- ============================================================================
-- 7. SPED Baseline Exemption Tracking
-- ============================================================================

-- Add exemption note to SPED baseline records
COMMENT ON COLUMN lct_calculations.temporal_flags IS
'Temporal validation flags:
- WARN_YEAR_GAP: Sources span 2-3 years (valid but notable)
- ERR_SPAN_EXCEEDED: Sources span >3 years (requires resolution)
- INFO_CROSS_YEAR: Different years used for different components
- INFO_RATIO_BASELINE: Uses SPED ratio baseline (2017-18, exempt from 3-year rule)';

-- ============================================================================
-- Migration Complete
-- ============================================================================

COMMENT ON FUNCTION school_year_to_numeric IS 'Convert school year string (e.g., 2023-24) to numeric year (2023)';
COMMENT ON FUNCTION year_span IS 'Calculate the span in years between two school years';
COMMENT ON FUNCTION is_within_3year_window IS 'Check if component years are within the 3-year blending window';
COMMENT ON VIEW v_lct_temporal_validation IS 'LCT calculations with temporal validation status';
