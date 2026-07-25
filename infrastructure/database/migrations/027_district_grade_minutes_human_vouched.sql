-- ============================================================================
-- Migration 027: district_grade_minutes.human_vouched
-- Date: 2026-07-24
-- Issue: #626 (epic #617) — a gate@8 human override/approval is an auditable
--        human determination that should render a fact acceptable even when its
--        source vintage technically violates the REQ-026 temporal window.
--
-- Ian's decision (2026-07-24): "a human override should be treated as equivalent
-- to an in-temporal-window schedule." The LCT calc (per_grade_lct) exempts a
-- vouched grade's `year` from the blend-window test, so an approved council value
-- no longer silently drops to statutory purely because a sampled source is old
-- (anchor case: Dickinson 1 ND `3800038`, middle band vouched, Hagen source 2016-17).
--
-- Set at incorporation from the frozen receipt (any band school carrying a
-- human_override / applied override / human_added fact). Default FALSE; existing
-- rows are non-vouched until re-incorporated.
-- ============================================================================

ALTER TABLE district_grade_minutes
    ADD COLUMN IF NOT EXISTS human_vouched BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN district_grade_minutes.human_vouched IS
'#626: TRUE when a human vouched for this grade''s source band at gate@8 (an override note, an applied times-override, or a hand-added cited fact). The LCT calc treats a vouched grade as equivalent to an in-temporal-window schedule — its year is exempt from the REQ-026 blend-window test, so an auditable human determination stands in for a current vintage.';
