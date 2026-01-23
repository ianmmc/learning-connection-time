-- Migration 010: Create enrichment_attempts table
-- Purpose: Track all bell schedule enrichment attempts (success and failure)
-- Date: 2026-01-22
--
-- This table logs every attempt to scrape/fetch bell schedule data, including:
-- - Successful fetches (redundant with bell_schedules but provides audit trail)
-- - Security blocks (Cloudflare, WAF, CAPTCHA)
-- - 404 errors, timeouts, and other failures
-- - Retry tracking to avoid repeated failed attempts
--
-- Use case: "Don't revisit districts that block us"

-- =============================================================================
-- DROP EXISTING TABLE (for development/testing)
-- =============================================================================

DROP TABLE IF EXISTS enrichment_attempts CASCADE;

-- =============================================================================
-- CREATE TABLE
-- =============================================================================

CREATE TABLE enrichment_attempts (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(10) NOT NULL REFERENCES districts(nces_id) ON DELETE CASCADE,

    -- URL attempted (may be district site or school site)
    url TEXT NOT NULL,
    attempted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Attempt outcome
    status VARCHAR(20) NOT NULL,  -- See constraint below for valid values
    block_type VARCHAR(30),       -- Type of security block (if status='blocked')

    -- HTTP response details
    http_status_code INTEGER,
    error_message TEXT,
    timing_ms INTEGER,            -- Response time in milliseconds

    -- Retry management
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMP WITH TIME ZONE,
    skip_future_attempts BOOLEAN DEFAULT FALSE,  -- Flag: don't try this district again
    skip_reason TEXT,             -- Why skipped (e.g., "cloudflare_block_3_attempts")

    -- Additional context
    scraper_version VARCHAR(20),  -- Version of scraper service
    enrichment_tier VARCHAR(10),  -- 'tier1', 'tier2', 'tier3' from enrichment campaign
    notes TEXT,
    response_details JSONB,       -- Full scraper response for debugging

    -- Constraints
    CONSTRAINT chk_status CHECK (status IN (
        'success',      -- Successfully fetched and extracted data
        'blocked',      -- Security block detected (Cloudflare/WAF/CAPTCHA)
        'not_found',    -- HTTP 404
        'timeout',      -- Request timeout
        'error',        -- Other error (network, parsing, etc.)
        'queue_full'    -- Scraper queue full (temporary)
    )),
    CONSTRAINT chk_block_type CHECK (block_type IS NULL OR block_type IN (
        'cloudflare',   -- Cloudflare challenge/verification page
        'waf',          -- Web Application Firewall (403)
        'captcha'       -- CAPTCHA challenge
    )),
    CONSTRAINT chk_retry_count CHECK (retry_count >= 0)
);

-- =============================================================================
-- INDEXES
-- =============================================================================

-- Query: "Which districts are blocked?"
CREATE INDEX idx_enrichment_attempts_district ON enrichment_attempts(district_id);
CREATE INDEX idx_enrichment_attempts_status ON enrichment_attempts(status);
CREATE INDEX idx_enrichment_attempts_skip ON enrichment_attempts(skip_future_attempts)
    WHERE skip_future_attempts = TRUE;

-- Query: "Show all Cloudflare blocks"
CREATE INDEX idx_enrichment_attempts_block_type ON enrichment_attempts(block_type)
    WHERE block_type IS NOT NULL;

-- Query: "Recent attempts for debugging"
CREATE INDEX idx_enrichment_attempts_time ON enrichment_attempts(attempted_at DESC);

-- Composite index for "Should I skip this district?"
CREATE INDEX idx_enrichment_attempts_district_skip ON enrichment_attempts(district_id, skip_future_attempts);

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE enrichment_attempts IS
    'Audit log of all bell schedule enrichment attempts (success and failure)';

COMMENT ON COLUMN enrichment_attempts.status IS
    'Outcome: success, blocked, not_found, timeout, error, queue_full';

COMMENT ON COLUMN enrichment_attempts.block_type IS
    'Type of security block: cloudflare, waf, or captcha';

COMMENT ON COLUMN enrichment_attempts.skip_future_attempts IS
    'If TRUE, don''t attempt this district again (marked after repeated failures)';

COMMENT ON COLUMN enrichment_attempts.response_details IS
    'Full JSON response from scraper service for debugging';

-- =============================================================================
-- HELPER VIEWS
-- =============================================================================

-- View: Districts to skip (have blocking or repeated failures)
CREATE VIEW v_districts_to_skip AS
SELECT DISTINCT
    district_id,
    d.name AS district_name,
    d.state,
    MAX(attempted_at) AS last_attempt,
    COUNT(*) AS attempt_count,
    STRING_AGG(DISTINCT block_type, ', ') AS block_types,
    BOOL_OR(skip_future_attempts) AS marked_skip
FROM enrichment_attempts ea
JOIN districts d ON ea.district_id = d.nces_id
WHERE
    skip_future_attempts = TRUE
    OR (status = 'blocked' AND retry_count >= 2)
    OR (status = 'not_found' AND retry_count >= 3)
GROUP BY district_id, d.name, d.state;

COMMENT ON VIEW v_districts_to_skip IS
    'Districts that should not be attempted again due to blocking or repeated failures';

-- View: Recent blocks for monitoring
CREATE VIEW v_recent_blocks AS
SELECT
    ea.attempted_at,
    ea.district_id,
    d.name AS district_name,
    d.state,
    ea.url,
    ea.block_type,
    ea.http_status_code,
    ea.retry_count
FROM enrichment_attempts ea
JOIN districts d ON ea.district_id = d.nces_id
WHERE
    ea.status = 'blocked'
    AND ea.attempted_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
ORDER BY ea.attempted_at DESC;

COMMENT ON VIEW v_recent_blocks IS
    'Security blocks detected in last 30 days';

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function: Should we skip this district?
CREATE OR REPLACE FUNCTION should_skip_district(p_district_id VARCHAR(10))
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM enrichment_attempts
        WHERE district_id = p_district_id
        AND skip_future_attempts = TRUE
    );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION should_skip_district IS
    'Returns TRUE if district is flagged to skip future enrichment attempts';

-- Function: Mark district for skipping
CREATE OR REPLACE FUNCTION mark_district_skip(
    p_district_id VARCHAR(10),
    p_reason TEXT DEFAULT 'repeated_failures'
) RETURNS VOID AS $$
UPDATE enrichment_attempts
SET
    skip_future_attempts = TRUE,
    skip_reason = p_reason
WHERE district_id = p_district_id
AND skip_future_attempts = FALSE;
$$ LANGUAGE sql;

COMMENT ON FUNCTION mark_district_skip IS
    'Mark all attempts for a district as skip_future_attempts=TRUE';

-- =============================================================================
-- SUMMARY STATISTICS VIEW
-- =============================================================================

CREATE VIEW v_enrichment_attempt_summary AS
SELECT
    status,
    block_type,
    COUNT(*) AS attempt_count,
    COUNT(DISTINCT district_id) AS unique_districts,
    AVG(timing_ms) AS avg_timing_ms,
    MIN(attempted_at) AS earliest_attempt,
    MAX(attempted_at) AS latest_attempt
FROM enrichment_attempts
GROUP BY status, block_type
ORDER BY attempt_count DESC;

COMMENT ON VIEW v_enrichment_attempt_summary IS
    'Summary statistics of enrichment attempts by status and block type';

-- =============================================================================
-- GRANT PERMISSIONS (if needed)
-- =============================================================================

-- Uncomment if you have specific user roles
-- GRANT SELECT, INSERT ON enrichment_attempts TO enrichment_service;
-- GRANT SELECT ON v_districts_to_skip TO enrichment_service;
