-- ============================================================================
-- Migration 031: correct the staff_counts_effective.scope_teachers_only comment
-- Date: 2026-10-31
-- Issue: #974 (epic #724)
--
-- Migration 002 described the column as "Pre-calculated: teachers_total", while
-- the model has always defined it as teachers_k12 (elementary + secondary +
-- kindergarten — no Pre-K, no ungraded), about 8 percent smaller. The stale comment is a
-- plausible origin of #974 (the SPED partition was carved from teachers_total
-- while the headline scope divides scope_teachers_only). 002 is applied and
-- checksummed, so the correction lands here rather than as an edit to it.
-- ============================================================================

COMMENT ON COLUMN staff_counts_effective.scope_teachers_only IS
'teachers_k12: elementary + secondary + kindergarten teachers (NO Pre-K, NO ungraded) — the teachers_only LCT numerator, and since #974 the SPED partition''s teacher base. NOT teachers_total.';
