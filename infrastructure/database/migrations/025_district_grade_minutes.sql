-- ============================================================================
-- Migration 025: district_grade_minutes — the LEA-level per-grade projection
-- Date: 2026-07-21
-- Issue: #605 (epic #92) — the artifact that lets LCT consume the pipeline's
--        3-band minutes against 2-band staffing.
--
-- Stage 9 projects each approved band's modal minutes DOWN to the individual
-- grade (grade -> owning band -> minutes), using the band's live grade span
-- (GSLO/GSHI). One current row per (district, grade); the LCT calc (#606) reads
-- this table and sums per-grade minutes x per-grade enrollment to any scope.
--
-- Derived + regenerable from bell_schedules + the live roster; re-incorporation
-- UPSERTs and reconciles vanished grades. NOT a source of truth (bell_schedules
-- is) — a materialized projection kept for auditability + cheap LCT reads.
-- ============================================================================

CREATE TABLE IF NOT EXISTS district_grade_minutes (
    id                    SERIAL PRIMARY KEY,
    district_id           VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,
    grade                 VARCHAR(4)  NOT NULL,   -- 'KG','01'..'12' (LCT range; PK excluded, 13 rides high)
    instructional_minutes INTEGER     NOT NULL,
    source_band           VARCHAR(20) NOT NULL,   -- elementary | middle | high (the band that owns this grade)
    method                VARCHAR(30) NOT NULL,   -- council_extraction | statutory_fallback (inherited from the band)
    minutes_basis         VARCHAR(30),            -- gross_bell_to_bell | statutory
    year                  VARCHAR(10),            -- the source band's school year (a blend component for #606)
    overlap_flag          TEXT,                   -- NULL, or why a tie-rule chose the band (grade served by >1 band)
    provenance            JSONB,                  -- {facts_fingerprint, approval_id, serving_bands, actor, ...}
    created_at            TIMESTAMPTZ DEFAULT now(),
    updated_at            TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_district_grade_minutes UNIQUE (district_id, grade),
    CONSTRAINT chk_dgm_source_band CHECK (source_band IN ('elementary','middle','high')),
    CONSTRAINT chk_dgm_minutes_basis CHECK (minutes_basis IN ('gross_bell_to_bell','statutory') OR minutes_basis IS NULL),
    CONSTRAINT chk_dgm_minutes CHECK (instructional_minutes BETWEEN 100 AND 600)
);

CREATE INDEX IF NOT EXISTS idx_district_grade_minutes_district
    ON district_grade_minutes(district_id);

COMMENT ON TABLE district_grade_minutes IS
'LEA-level per-grade instructional minutes: each grade takes its owning band''s modal minutes (Stage 9 projection, #605). Derived from bell_schedules + the live roster; one current row per (district, grade). Read by the LCT calc (#606) which weights per-grade minutes by per-grade enrollment to any staffing scope.';

COMMENT ON COLUMN district_grade_minutes.overlap_flag IS
'NULL when exactly one band serves the grade. Otherwise the deterministic tie-rule note (grade served by >=2 bands with different minutes — e.g. a floating 7-9 middle overlapping a 9-12 high at grade 9); the band whose LEVEL cleanly owns the grade wins, and this records that it was a tie.';
