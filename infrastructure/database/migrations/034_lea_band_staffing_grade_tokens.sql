-- ============================================================================
-- Migration 034: lea_band_staffing.grade_lo / grade_hi are K-12 grade tokens
-- Date: 2026-11-03
-- Issue: #1088 (PR #1050 review; #1022 T4, epic #724)
--
-- The band's served span was a free VARCHAR(4): 'KG' sorts AFTER '12' as text and nothing stopped a
-- stray token. Same vocabulary as chk_lgtf_grade on lea_grade_teacher_fte. Declared twice (here and
-- in models.py LEABandStaffing) per the PR #641 invariant; tests/test_migration_033_parity.py compares
-- the two. Idempotent: DROP IF EXISTS, then ADD. The table is empty until T6 (#1040) derives it.
-- ============================================================================

ALTER TABLE lea_band_staffing DROP CONSTRAINT IF EXISTS chk_lbs_grade_lo;
ALTER TABLE lea_band_staffing ADD CONSTRAINT chk_lbs_grade_lo
    CHECK (grade_lo IN ('KG','01','02','03','04','05','06','07','08','09','10','11','12'));

ALTER TABLE lea_band_staffing DROP CONSTRAINT IF EXISTS chk_lbs_grade_hi;
ALTER TABLE lea_band_staffing ADD CONSTRAINT chk_lbs_grade_hi
    CHECK (grade_hi IN ('KG','01','02','03','04','05','06','07','08','09','10','11','12'));
