-- ============================================================================
-- Migration 026: district_grade_minutes.method CHECK constraint
-- Date: 2026-07-21
-- Issue: PR #607 max-effort review (epic #92) — the sibling bell_schedules.method
--        is chk_method-constrained; this column shipped in migration 025 without
--        the same fail-loud guard. Stage 9 writes exactly two values here; a
--        future writer typo must fail at the DB, not sit silently misclassified
--        (Rule #6).
-- ============================================================================

ALTER TABLE district_grade_minutes DROP CONSTRAINT IF EXISTS chk_dgm_method;
ALTER TABLE district_grade_minutes ADD CONSTRAINT chk_dgm_method
    CHECK (method IN ('council_extraction', 'statutory_fallback'));
