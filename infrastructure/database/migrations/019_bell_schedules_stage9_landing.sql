-- ============================================================================
-- Migration 019: bell_schedules Stage-9 landing zone
-- Date: 2026-07-02
-- Issue: #19 (minutes_basis label + council_extraction method)
--
-- The acquisition pipeline (Stage 9) writes per-band GROSS bell-to-bell minutes
-- (REQ-055) with method='council_extraction'. This migration:
--   1. Adds minutes_basis to label what a row's instructional_minutes MEANS.
--      NULL = unlabeled pre-pipeline legacy row (slated for a separate wipe —
--      do NOT backfill). New writes always set it.
--   2. Extends chk_method with 'council_extraction'. The existing value list is
--      kept verbatim (verified against SELECT DISTINCT method: human_provided,
--      automated_enrichment, pdf_extraction, web_scraping are actually present)
--      so no existing row violates the re-added CHECK.
-- ============================================================================

ALTER TABLE bell_schedules
    ADD COLUMN IF NOT EXISTS minutes_basis VARCHAR(30);

ALTER TABLE bell_schedules DROP CONSTRAINT IF EXISTS chk_minutes_basis;
ALTER TABLE bell_schedules ADD CONSTRAINT chk_minutes_basis
    CHECK (minutes_basis IN ('gross_bell_to_bell', 'statutory') OR minutes_basis IS NULL);

COMMENT ON COLUMN bell_schedules.minutes_basis IS
'What instructional_minutes measures. gross_bell_to_bell = end-start, no deductions (REQ-055, the metric); statutory = state statutory minimum fallback. NULL = unlabeled pre-pipeline legacy row, slated for removal (decided 2026-07: legacy rows will be wiped, not backfilled). New writes must set this.';

-- Extend chk_method: previous list (from the live constraint) + council_extraction.
ALTER TABLE bell_schedules DROP CONSTRAINT IF EXISTS chk_method;
ALTER TABLE bell_schedules ADD CONSTRAINT chk_method CHECK (method IN (
    'automated_enrichment',
    'human_provided',
    'statutory_fallback',
    'web_scraping',
    'fallback_statutory',
    'pdf_extraction',
    'manual_data_collection',
    'district_policy',
    'school_sample',
    'district_standardized_schedule',
    'school_specific_schedules',
    'school_hours_with_estimation',
    'state_requirement_with_validation',
    'tier_1_firecrawl_regex',
    'tier_1_firecrawl_table',
    'tier_1_firecrawl_map',
    'tier_1_pattern',
    'tier_1_scraper',
    'tier_1_fallback',
    'tier_2_pattern',
    'tier_2_html',
    'tier_2_scraper',
    'tier_3_pdf',
    'tier_3_ocr',
    'tier_3_document',
    'tier_4_claude',
    'tier_4_auto',
    'tier_4_api',
    'tier_5_gemini',
    'tier_5_web_search',
    'tier_5_mcp',
    'council_extraction'
));
