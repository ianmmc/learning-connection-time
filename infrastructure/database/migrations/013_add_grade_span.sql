-- Migration 013: Add grade span columns to districts table
-- Created: 2026-01-24
-- Description: Adds GSLO/GSHI from NCES CCD to track which grade levels each district offers

-- Add grade span columns
ALTER TABLE districts ADD COLUMN IF NOT EXISTS grade_span_low VARCHAR(3);
ALTER TABLE districts ADD COLUMN IF NOT EXISTS grade_span_high VARCHAR(3);

-- Add comments
COMMENT ON COLUMN districts.grade_span_low IS 'Lowest grade offered (PK, KG, 01-12) from NCES GSLO';
COMMENT ON COLUMN districts.grade_span_high IS 'Highest grade offered (PK, KG, 01-12) from NCES GSHI';

-- Create a function to determine expected grade levels for a district
CREATE OR REPLACE FUNCTION get_district_grade_levels(gslo VARCHAR, gshi VARCHAR)
RETURNS VARCHAR[] AS $$
DECLARE
    levels VARCHAR[] := '{}';
    low_num INTEGER;
    high_num INTEGER;
BEGIN
    -- Convert grade codes to numbers (PK=-1, KG=0, 01-12=1-12)
    CASE gslo
        WHEN 'PK' THEN low_num := -1;
        WHEN 'KG' THEN low_num := 0;
        ELSE low_num := CAST(gslo AS INTEGER);
    END CASE;

    CASE gshi
        WHEN 'PK' THEN high_num := -1;
        WHEN 'KG' THEN high_num := 0;
        ELSE high_num := CAST(gshi AS INTEGER);
    END CASE;

    -- Determine grade levels
    -- Elementary: serves any of PK-5
    IF low_num <= 5 AND high_num >= 0 THEN
        levels := array_append(levels, 'elementary');
    END IF;

    -- Middle: serves any of 6-8
    IF low_num <= 8 AND high_num >= 6 THEN
        levels := array_append(levels, 'middle');
    END IF;

    -- High: serves any of 9-12
    IF high_num >= 9 THEN
        levels := array_append(levels, 'high');
    END IF;

    RETURN levels;
EXCEPTION
    WHEN OTHERS THEN
        -- Default to all levels if parsing fails
        RETURN ARRAY['elementary', 'middle', 'high'];
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION get_district_grade_levels(VARCHAR, VARCHAR) IS 'Returns array of grade levels (elementary, middle, high) a district should have based on grade span';
