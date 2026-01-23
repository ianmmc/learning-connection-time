-- Migration 011: Create Enrichment Queue System
-- Multi-tier bell schedule enrichment with batched API processing

-- Queue table for tracking multi-tier enrichment progress
CREATE TABLE IF NOT EXISTS enrichment_queue (
    id SERIAL PRIMARY KEY,
    district_id VARCHAR(10) REFERENCES districts(nces_id) ON DELETE CASCADE,
    current_tier INTEGER DEFAULT 1,

    -- Results from each tier (JSONB for flexibility)
    tier_1_result JSONB, -- Local discovery (Playwright)
    tier_2_result JSONB, -- Local extraction (HTML parsing)
    tier_3_result JSONB, -- Local PDF/OCR
    tier_4_result JSONB, -- Claude API (batched)
    tier_5_result JSONB, -- Gemini MCP (batched)

    -- Batch tracking
    batch_id INTEGER,
    batch_type VARCHAR(50), -- 'js_heavy', 'pdf_tables', 'complex_html', 'web_search'

    -- Timestamps
    queued_at TIMESTAMP DEFAULT NOW(),
    processing_started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending', -- pending, processing, completed, failed, manual_review
    escalation_reason TEXT,
    final_success BOOLEAN,

    -- Metadata
    cms_detected VARCHAR(50), -- Finalsite, SchoolBlocks, Blackboard, etc.
    content_type VARCHAR(50), -- heavy_js, html, pdf, image
    notes TEXT,

    -- Cost tracking
    estimated_cost_cents INTEGER DEFAULT 0,
    processing_time_seconds INTEGER,

    UNIQUE(district_id) -- One queue entry per district
);

-- Indexes for efficient queries
CREATE INDEX idx_eq_status ON enrichment_queue(status);
CREATE INDEX idx_eq_tier ON enrichment_queue(current_tier);
CREATE INDEX idx_eq_batch ON enrichment_queue(batch_id);
CREATE INDEX idx_eq_batch_type ON enrichment_queue(batch_type);
CREATE INDEX idx_eq_queued_at ON enrichment_queue(queued_at);
CREATE INDEX idx_eq_cms ON enrichment_queue(cms_detected);

-- Batch tracking table
CREATE TABLE IF NOT EXISTS enrichment_batches (
    id SERIAL PRIMARY KEY,
    batch_type VARCHAR(50) NOT NULL, -- 'tier_4_claude', 'tier_5_gemini'
    tier INTEGER NOT NULL,
    district_count INTEGER NOT NULL,

    -- Composition metadata
    grouping_strategy VARCHAR(100), -- 'cms_platform', 'state', 'content_type', etc.
    shared_context TEXT, -- Context shared across batch for efficiency

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    submitted_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Status
    status VARCHAR(20) DEFAULT 'pending', -- pending, submitted, completed, failed

    -- Results
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,

    -- Cost tracking
    api_cost_cents INTEGER,
    api_tokens_used INTEGER,
    processing_time_seconds INTEGER,

    -- API details
    api_provider VARCHAR(50), -- 'claude', 'gemini'
    api_model VARCHAR(50),
    api_response JSONB
);

CREATE INDEX idx_eb_status ON enrichment_batches(status);
CREATE INDEX idx_eb_tier ON enrichment_batches(tier);
CREATE INDEX idx_eb_type ON enrichment_batches(batch_type);

-- View: Queue status summary
CREATE OR REPLACE VIEW v_enrichment_queue_status AS
SELECT
    status,
    current_tier,
    COUNT(*) as district_count,
    COUNT(*) FILTER (WHERE final_success = TRUE) as successful,
    COUNT(*) FILTER (WHERE final_success = FALSE) as failed,
    AVG(processing_time_seconds) as avg_processing_time_seconds,
    SUM(estimated_cost_cents) / 100.0 as total_cost_dollars
FROM enrichment_queue
GROUP BY status, current_tier
ORDER BY current_tier, status;

-- View: Tier success rates
CREATE OR REPLACE VIEW v_enrichment_tier_success AS
SELECT
    current_tier,
    COUNT(*) as attempts,
    COUNT(*) FILTER (WHERE final_success = TRUE) as successes,
    ROUND(100.0 * COUNT(*) FILTER (WHERE final_success = TRUE) / COUNT(*), 1) as success_rate_pct,
    AVG(processing_time_seconds) as avg_processing_time_seconds,
    SUM(estimated_cost_cents) / 100.0 as total_cost_dollars
FROM enrichment_queue
WHERE status = 'completed'
GROUP BY current_tier
ORDER BY current_tier;

-- View: Batch processing summary
CREATE OR REPLACE VIEW v_enrichment_batch_summary AS
SELECT
    batch_type,
    tier,
    COUNT(*) as batch_count,
    SUM(district_count) as total_districts,
    SUM(success_count) as total_successes,
    SUM(failure_count) as total_failures,
    ROUND(100.0 * SUM(success_count) / NULLIF(SUM(success_count) + SUM(failure_count), 0), 1) as success_rate_pct,
    SUM(api_cost_cents) / 100.0 as total_cost_dollars,
    SUM(api_tokens_used) as total_tokens
FROM enrichment_batches
WHERE status = 'completed'
GROUP BY batch_type, tier
ORDER BY tier, batch_type;

-- View: Districts ready for batching
CREATE OR REPLACE VIEW v_districts_ready_for_batching AS
SELECT
    eq.id,
    eq.district_id,
    d.name as district_name,
    d.state,
    d.enrollment,
    eq.current_tier,
    eq.batch_type,
    eq.cms_detected,
    eq.content_type,
    eq.escalation_reason
FROM enrichment_queue eq
JOIN districts d ON eq.district_id = d.nces_id
WHERE eq.status = 'pending'
  AND eq.current_tier IN (4, 5) -- Ready for API tiers
ORDER BY eq.current_tier, eq.batch_type, d.state, d.enrollment DESC;

-- Function: Get queue status dashboard
CREATE OR REPLACE FUNCTION get_queue_dashboard()
RETURNS TABLE(
    metric VARCHAR,
    value TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 'total_districts'::VARCHAR, COUNT(*)::TEXT FROM enrichment_queue
    UNION ALL
    SELECT 'completed'::VARCHAR,
           COUNT(*)::TEXT || ' (' || ROUND(100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM enrichment_queue), 0), 1)::TEXT || '%)'
    FROM enrichment_queue WHERE status = 'completed'
    UNION ALL
    SELECT 'processing'::VARCHAR,
           COUNT(*)::TEXT || ' (' || ROUND(100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM enrichment_queue), 0), 1)::TEXT || '%)'
    FROM enrichment_queue WHERE status = 'processing'
    UNION ALL
    SELECT 'pending'::VARCHAR,
           COUNT(*)::TEXT || ' (' || ROUND(100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM enrichment_queue), 0), 1)::TEXT || '%)'
    FROM enrichment_queue WHERE status = 'pending'
    UNION ALL
    SELECT 'manual_review'::VARCHAR,
           COUNT(*)::TEXT
    FROM enrichment_queue WHERE status = 'manual_review'
    UNION ALL
    SELECT 'tier_1_pending'::VARCHAR, COUNT(*)::TEXT FROM enrichment_queue WHERE current_tier = 1 AND status = 'pending'
    UNION ALL
    SELECT 'tier_2_pending'::VARCHAR, COUNT(*)::TEXT FROM enrichment_queue WHERE current_tier = 2 AND status = 'pending'
    UNION ALL
    SELECT 'tier_3_pending'::VARCHAR, COUNT(*)::TEXT FROM enrichment_queue WHERE current_tier = 3 AND status = 'pending'
    UNION ALL
    SELECT 'tier_4_ready'::VARCHAR, COUNT(DISTINCT batch_id)::TEXT || ' batches (' || COUNT(*)::TEXT || ' districts)'
    FROM enrichment_queue WHERE current_tier = 4 AND status = 'pending' AND batch_id IS NOT NULL
    UNION ALL
    SELECT 'tier_5_ready'::VARCHAR, COUNT(DISTINCT batch_id)::TEXT || ' batches (' || COUNT(*)::TEXT || ' districts)'
    FROM enrichment_queue WHERE current_tier = 5 AND status = 'pending' AND batch_id IS NOT NULL
    UNION ALL
    SELECT 'estimated_cost'::VARCHAR, '$' || ROUND(SUM(estimated_cost_cents) / 100.0, 2)::TEXT
    FROM enrichment_queue
    UNION ALL
    SELECT 'total_cost'::VARCHAR, '$' || ROUND(SUM(api_cost_cents) / 100.0, 2)::TEXT
    FROM enrichment_batches WHERE status = 'completed';
END;
$$ LANGUAGE plpgsql;

-- Function: Add districts to queue
CREATE OR REPLACE FUNCTION queue_districts_for_enrichment(
    district_ids VARCHAR[]
)
RETURNS INTEGER AS $$
DECLARE
    inserted_count INTEGER;
BEGIN
    INSERT INTO enrichment_queue (district_id, status, current_tier)
    SELECT unnest(district_ids), 'pending', 1
    ON CONFLICT (district_id) DO NOTHING;

    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RETURN inserted_count;
END;
$$ LANGUAGE plpgsql;

-- Function: Mark district for escalation
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
BEGIN
    UPDATE enrichment_queue
    SET
        current_tier = p_current_tier + 1,
        status = 'pending',
        escalation_reason = p_escalation_reason,
        batch_type = COALESCE(p_batch_type, batch_type),
        cms_detected = COALESCE(p_cms_detected, cms_detected),
        content_type = COALESCE(p_content_type, content_type),
        -- Store tier result in appropriate column
        tier_1_result = CASE WHEN p_current_tier = 1 THEN p_tier_result ELSE tier_1_result END,
        tier_2_result = CASE WHEN p_current_tier = 2 THEN p_tier_result ELSE tier_2_result END,
        tier_3_result = CASE WHEN p_current_tier = 3 THEN p_tier_result ELSE tier_3_result END,
        tier_4_result = CASE WHEN p_current_tier = 4 THEN p_tier_result ELSE tier_4_result END
    WHERE district_id = p_district_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function: Mark district as completed
CREATE OR REPLACE FUNCTION complete_enrichment(
    p_district_id VARCHAR,
    p_tier INTEGER,
    p_tier_result JSONB,
    p_success BOOLEAN,
    p_processing_time_seconds INTEGER DEFAULT NULL
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE enrichment_queue
    SET
        status = 'completed',
        completed_at = NOW(),
        final_success = p_success,
        processing_time_seconds = COALESCE(p_processing_time_seconds, processing_time_seconds),
        -- Store tier result
        tier_1_result = CASE WHEN p_tier = 1 THEN p_tier_result ELSE tier_1_result END,
        tier_2_result = CASE WHEN p_tier = 2 THEN p_tier_result ELSE tier_2_result END,
        tier_3_result = CASE WHEN p_tier = 3 THEN p_tier_result ELSE tier_3_result END,
        tier_4_result = CASE WHEN p_tier = 4 THEN p_tier_result ELSE tier_4_result END,
        tier_5_result = CASE WHEN p_tier = 5 THEN p_tier_result ELSE tier_5_result END
    WHERE district_id = p_district_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE enrichment_queue IS 'Multi-tier bell schedule enrichment queue with escalation tracking';
COMMENT ON TABLE enrichment_batches IS 'Batch processing for API-based enrichment tiers (Claude, Gemini)';
COMMENT ON FUNCTION get_queue_dashboard() IS 'Returns formatted queue status for monitoring dashboard';
COMMENT ON FUNCTION queue_districts_for_enrichment(VARCHAR[]) IS 'Add districts to enrichment queue at Tier 1';
COMMENT ON FUNCTION escalate_to_next_tier(VARCHAR, INTEGER, JSONB, TEXT, VARCHAR, VARCHAR, VARCHAR) IS 'Move district to next tier with escalation reason';
COMMENT ON FUNCTION complete_enrichment(VARCHAR, INTEGER, JSONB, BOOLEAN, INTEGER) IS 'Mark district enrichment as completed with final results';
