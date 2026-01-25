-- Migration 014: Security Blocking for Cloudflare/WAF/403 Sites
-- Created: 2026-01-24
-- Description: Adds permanent blocking for districts with security-protected websites
--
-- When a district's website is protected by Cloudflare, WAF, or returns 403,
-- it should be marked for manual review and permanently excluded from automated scraping.

-- ============================================================================
-- 1. Add Security Blocking Column
-- ============================================================================

-- Add column to track permanently blocked districts
ALTER TABLE enrichment_queue
ADD COLUMN IF NOT EXISTS security_blocked BOOLEAN DEFAULT FALSE;

ALTER TABLE enrichment_queue
ADD COLUMN IF NOT EXISTS security_block_reason TEXT;

COMMENT ON COLUMN enrichment_queue.security_blocked IS 'True if district website is protected by Cloudflare/WAF/403 and should never be auto-scraped';
COMMENT ON COLUMN enrichment_queue.security_block_reason IS 'Reason for security block (cloudflare, waf, captcha, 403, rate_limit)';

-- ============================================================================
-- 2. Function: Mark District as Security Blocked
-- ============================================================================

CREATE OR REPLACE FUNCTION mark_security_blocked(
    p_district_id VARCHAR,
    p_current_tier INTEGER,
    p_tier_result JSONB,
    p_block_reason TEXT
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE enrichment_queue
    SET
        status = 'manual_review',
        security_blocked = TRUE,
        security_block_reason = p_block_reason,
        escalation_reason = 'security_blocked: ' || p_block_reason,
        -- Store tier result
        tier_1_result = CASE WHEN p_current_tier = 1 THEN p_tier_result ELSE tier_1_result END,
        tier_2_result = CASE WHEN p_current_tier = 2 THEN p_tier_result ELSE tier_2_result END,
        tier_3_result = CASE WHEN p_current_tier = 3 THEN p_tier_result ELSE tier_3_result END
    WHERE district_id = p_district_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION mark_security_blocked(VARCHAR, INTEGER, JSONB, TEXT) IS
'Mark district as permanently blocked due to security protection (Cloudflare/WAF/403)';

-- ============================================================================
-- 3. Update escalate_to_next_tier for Tier 5 → manual_review
-- ============================================================================

-- Drop and recreate to handle Tier 5 edge case
CREATE OR REPLACE FUNCTION escalate_to_next_tier(
    p_district_id VARCHAR,
    p_current_tier INTEGER,
    p_tier_result JSONB,
    p_escalation_reason TEXT,
    p_batch_type VARCHAR DEFAULT NULL,
    p_cms_detected VARCHAR DEFAULT NULL,
    p_content_type VARCHAR DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_next_tier INTEGER;
    v_new_status VARCHAR;
BEGIN
    -- Determine next tier and status
    IF p_current_tier >= 5 THEN
        -- Tier 5 is the last tier - go to manual review
        v_next_tier := 5;  -- Keep at 5
        v_new_status := 'manual_review';
    ELSE
        v_next_tier := p_current_tier + 1;
        v_new_status := 'pending';
    END IF;

    UPDATE enrichment_queue
    SET
        current_tier = v_next_tier,
        status = v_new_status,
        escalation_reason = p_escalation_reason,
        batch_type = COALESCE(p_batch_type, batch_type),
        cms_detected = COALESCE(p_cms_detected, cms_detected),
        content_type = COALESCE(p_content_type, content_type),
        -- Store tier result in appropriate column
        tier_1_result = CASE WHEN p_current_tier = 1 THEN p_tier_result ELSE tier_1_result END,
        tier_2_result = CASE WHEN p_current_tier = 2 THEN p_tier_result ELSE tier_2_result END,
        tier_3_result = CASE WHEN p_current_tier = 3 THEN p_tier_result ELSE tier_3_result END,
        tier_4_result = CASE WHEN p_current_tier = 4 THEN p_tier_result ELSE tier_4_result END,
        tier_5_result = CASE WHEN p_current_tier = 5 THEN p_tier_result ELSE tier_5_result END
    WHERE district_id = p_district_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 4. Index for Security Blocked Queries
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_enrichment_queue_security_blocked
ON enrichment_queue(security_blocked)
WHERE security_blocked = TRUE;

-- ============================================================================
-- Migration Complete
-- ============================================================================

COMMENT ON FUNCTION escalate_to_next_tier(VARCHAR, INTEGER, JSONB, TEXT, VARCHAR, VARCHAR, VARCHAR) IS
'Move district to next tier with escalation reason. Tier 5 failure goes to manual_review.';
