-- Create Materialized Views for Common Joins
-- These views pre-compute expensive joins for faster querying.
-- Refresh after data updates using: REFRESH MATERIALIZED VIEW view_name;

-- ============================================================================
-- VIEW 1: Districts with LCT Data
-- ============================================================================
-- Pre-joins districts with staff, enrollment, and bell schedules for LCT calculations

DROP MATERIALIZED VIEW IF EXISTS mv_districts_with_lct_data;

CREATE MATERIALIZED VIEW mv_districts_with_lct_data AS
SELECT
    d.nces_id,
    d.name AS district_name,
    d.state,
    d.enrollment AS district_enrollment,
    d.year AS district_year,

    -- Staff data
    s.effective_year AS staff_year,
    s.primary_source AS staff_source,
    s.teachers_k12,
    s.teachers_elementary_k5,
    s.teachers_secondary_6_12,
    s.scope_teachers_only,
    s.scope_teachers_core,
    s.scope_instructional,
    s.scope_instructional_plus_support,
    s.scope_all,

    -- Enrollment data
    e.source_year AS enrollment_year,
    e.enrollment_k12,
    e.enrollment_elementary,
    e.enrollment_secondary,
    e.enrollment_prek,

    -- Bell schedule flags
    CASE WHEN EXISTS (
        SELECT 1 FROM bell_schedules b
        WHERE b.district_id = d.nces_id
        AND b.year IN ('2024-25', '2025-26')
    ) THEN true ELSE false END AS has_bell_schedule,

    -- State requirements
    sr.elementary_minutes AS state_elementary_minutes,
    sr.middle_minutes AS state_middle_minutes,
    sr.high_minutes AS state_high_minutes,
    sr.default_minutes AS state_default_minutes

FROM districts d
LEFT JOIN staff_counts_effective s ON d.nces_id = s.district_id
LEFT JOIN enrollment_by_grade e ON d.nces_id = e.district_id AND e.source_year = '2023-24'
LEFT JOIN state_requirements sr ON d.state = sr.state
WHERE s.scope_teachers_only IS NOT NULL
  AND e.enrollment_k12 IS NOT NULL
  AND e.enrollment_k12 > 0;

-- Create index for fast lookups
CREATE INDEX idx_mv_districts_lct_state ON mv_districts_with_lct_data(state);
CREATE INDEX idx_mv_districts_lct_nces_id ON mv_districts_with_lct_data(nces_id);

-- ============================================================================
-- VIEW 2: State Enrichment Progress
-- ============================================================================
-- Summary of enrichment campaign progress by state

DROP MATERIALIZED VIEW IF EXISTS mv_state_enrichment_progress;

CREATE MATERIALIZED VIEW mv_state_enrichment_progress AS
SELECT
    d.state,
    COUNT(DISTINCT d.nces_id) AS total_districts,
    COUNT(DISTINCT b.district_id) AS enriched_districts,
    ROUND(100.0 * COUNT(DISTINCT b.district_id) / NULLIF(COUNT(DISTINCT d.nces_id), 0), 2) AS enrichment_pct,
    SUM(d.enrollment) AS total_enrollment,
    3 AS target_per_state,
    CASE
        WHEN COUNT(DISTINCT b.district_id) >= 3 THEN 'complete'
        WHEN COUNT(DISTINCT b.district_id) > 0 THEN 'in_progress'
        ELSE 'not_started'
    END AS campaign_status
FROM districts d
LEFT JOIN bell_schedules b ON d.nces_id = b.district_id AND b.year IN ('2024-25', '2025-26')
GROUP BY d.state
ORDER BY COUNT(DISTINCT b.district_id) DESC, SUM(d.enrollment) DESC;

-- Create index
CREATE INDEX idx_mv_state_enrichment_state ON mv_state_enrichment_progress(state);

-- ============================================================================
-- VIEW 3: Top Districts by Enrollment (Unenriched)
-- ============================================================================
-- Fast lookup of largest districts still needing enrichment

DROP MATERIALIZED VIEW IF EXISTS mv_unenriched_districts;

CREATE MATERIALIZED VIEW mv_unenriched_districts AS
SELECT
    d.nces_id,
    d.name AS district_name,
    d.state,
    d.enrollment,
    ROW_NUMBER() OVER (PARTITION BY d.state ORDER BY d.enrollment DESC) AS state_rank
FROM districts d
WHERE d.enrollment IS NOT NULL
  AND d.enrollment > 0
  AND NOT EXISTS (
    SELECT 1 FROM bell_schedules b
    WHERE b.district_id = d.nces_id
    AND b.year IN ('2024-25', '2025-26')
  );

-- Create indexes
CREATE INDEX idx_mv_unenriched_state ON mv_unenriched_districts(state);
CREATE INDEX idx_mv_unenriched_enrollment ON mv_unenriched_districts(enrollment DESC);
CREATE INDEX idx_mv_unenriched_state_rank ON mv_unenriched_districts(state, state_rank);

-- ============================================================================
-- VIEW 4: LCT Summary Statistics by Scope
-- ============================================================================
-- Pre-computed statistics for dashboard display

DROP MATERIALIZED VIEW IF EXISTS mv_lct_summary_stats;

CREATE MATERIALIZED VIEW mv_lct_summary_stats AS
WITH scope_data AS (
    SELECT
        'teachers_only' AS scope,
        d.nces_id,
        (360.0 * s.scope_teachers_only) / e.enrollment_k12 AS lct_value
    FROM districts d
    JOIN staff_counts_effective s ON d.nces_id = s.district_id
    JOIN enrollment_by_grade e ON d.nces_id = e.district_id AND e.source_year = '2023-24'
    WHERE s.scope_teachers_only > 0 AND e.enrollment_k12 > 0

    UNION ALL

    SELECT
        'teachers_core' AS scope,
        d.nces_id,
        (360.0 * s.scope_teachers_core) / e.enrollment_k12 AS lct_value
    FROM districts d
    JOIN staff_counts_effective s ON d.nces_id = s.district_id
    JOIN enrollment_by_grade e ON d.nces_id = e.district_id AND e.source_year = '2023-24'
    WHERE s.scope_teachers_core > 0 AND e.enrollment_k12 > 0

    UNION ALL

    SELECT
        'instructional' AS scope,
        d.nces_id,
        (360.0 * s.scope_instructional) / e.enrollment_k12 AS lct_value
    FROM districts d
    JOIN staff_counts_effective s ON d.nces_id = s.district_id
    JOIN enrollment_by_grade e ON d.nces_id = e.district_id AND e.source_year = '2023-24'
    WHERE s.scope_instructional > 0 AND e.enrollment_k12 > 0

    UNION ALL

    SELECT
        'all' AS scope,
        d.nces_id,
        (360.0 * s.scope_all) / e.enrollment_k12 AS lct_value
    FROM districts d
    JOIN staff_counts_effective s ON d.nces_id = s.district_id
    JOIN enrollment_by_grade e ON d.nces_id = e.district_id AND e.source_year = '2023-24'
    WHERE s.scope_all > 0 AND e.enrollment_k12 > 0
)
SELECT
    scope,
    COUNT(*) AS district_count,
    ROUND(AVG(lct_value)::numeric, 2) AS mean_lct,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lct_value)::numeric, 2) AS median_lct,
    ROUND(STDDEV(lct_value)::numeric, 2) AS std_lct,
    ROUND(MIN(lct_value)::numeric, 2) AS min_lct,
    ROUND(MAX(lct_value)::numeric, 2) AS max_lct
FROM scope_data
WHERE lct_value > 0 AND lct_value <= 360
GROUP BY scope;

-- ============================================================================
-- Refresh Function
-- ============================================================================
-- Call this after data updates

CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW mv_districts_with_lct_data;
    REFRESH MATERIALIZED VIEW mv_state_enrichment_progress;
    REFRESH MATERIALIZED VIEW mv_unenriched_districts;
    REFRESH MATERIALIZED VIEW mv_lct_summary_stats;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Usage Examples
-- ============================================================================
--
-- Get next enrichment candidates for a state:
--   SELECT * FROM mv_unenriched_districts
--   WHERE state = 'CA' AND state_rank <= 9;
--
-- Get campaign progress:
--   SELECT * FROM mv_state_enrichment_progress
--   WHERE campaign_status != 'complete'
--   ORDER BY total_enrollment DESC;
--
-- Get LCT summary:
--   SELECT * FROM mv_lct_summary_stats ORDER BY scope;
--
-- Refresh all views:
--   SELECT refresh_all_materialized_views();
