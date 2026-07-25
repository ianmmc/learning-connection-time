-- ============================================================================
-- Migration 028: bell_schedules.human_vouched
-- Date: 2026-07-24
-- Issue: #636 (review of #626) — the gate@8 human determination lived ONLY on
--        district_grade_minutes, a table documented as a regenerable projection
--        "derived from bell_schedules + the live roster". That contract was
--        false for human_vouched (derivable only from the frozen receipt), so a
--        receipt-less projection rebuild would silently zero every vouch and
--        reintroduce the #626 bug.
--
-- Fix: the vouch now lives on bell_schedules (the per-band SOURCE OF TRUTH),
-- set by Stage 9 from the frozen receipt; the projection inherits it from the
-- band write — making district_grade_minutes genuinely regenerable again.
-- Backfilled by re-incorporating all approved districts (--force).
-- ============================================================================

ALTER TABLE bell_schedules
    ADD COLUMN IF NOT EXISTS human_vouched BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN bell_schedules.human_vouched IS
'#626/#636: TRUE when a human vouched for this band''s value at gate@8 (an override note, an applied times-override, or a hand-added cited fact). The LCT calc treats a vouched band as equivalent to an in-temporal-window schedule (REQ-026 exemption). Source of truth for the district_grade_minutes.human_vouched projection column.';
