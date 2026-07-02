-- =============================================================================
-- Learning Connection Time — LIVE SCHEMA SNAPSHOT (GENERATED — do not hand-edit)
--
-- Regenerate:
--   docker exec lct_postgres pg_dump -U lct_user -d learning_connection_time \
--     --schema-only --no-owner --no-privileges > infrastructure/database/schema.sql
--   (then re-prepend this header)
--
-- Authority chain (issue #21, fable review §3.1 M-2):
--   1. infrastructure/database/models.py       — the ORM authority (PROJECT_HISTORY Part 5)
--   2. infrastructure/database/migrations/     — how the live DB got here (migrate.py status)
--   3. this file                               — a dated pg_dump snapshot for reference ONLY
--
-- The previous hand-written schema.sql (Dec 2025) predated migrations 002-017 and had
-- drifted in both directions; it was replaced by this generated snapshot 2026-07-02.
-- =============================================================================

--
-- PostgreSQL database dump
--

\restrict CD0bk9qnDbPwTYsFaGLURipdHwhg8t3JS0cKKBXX9Vs8AgqRn46K9NgQzRM8l9Y

-- Dumped from database version 16.11
-- Dumped by pg_dump version 16.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: calculation_mode_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.calculation_mode_enum AS ENUM (
    'blended',
    'target_year'
);


--
-- Name: complete_enrichment(character varying, integer, jsonb, boolean, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.complete_enrichment(p_district_id character varying, p_tier integer, p_tier_result jsonb, p_success boolean, p_processing_time_seconds integer DEFAULT NULL::integer) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
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
$$;


--
-- Name: FUNCTION complete_enrichment(p_district_id character varying, p_tier integer, p_tier_result jsonb, p_success boolean, p_processing_time_seconds integer); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.complete_enrichment(p_district_id character varying, p_tier integer, p_tier_result jsonb, p_success boolean, p_processing_time_seconds integer) IS 'Mark district enrichment as completed with final results';


--
-- Name: escalate_to_next_tier(character varying, integer, jsonb, text, character varying, character varying, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.escalate_to_next_tier(p_district_id character varying, p_current_tier integer, p_tier_result jsonb, p_escalation_reason text, p_batch_type character varying DEFAULT NULL::character varying, p_cms_detected character varying DEFAULT NULL::character varying, p_content_type character varying DEFAULT NULL::character varying) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
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
$$;


--
-- Name: FUNCTION escalate_to_next_tier(p_district_id character varying, p_current_tier integer, p_tier_result jsonb, p_escalation_reason text, p_batch_type character varying, p_cms_detected character varying, p_content_type character varying); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.escalate_to_next_tier(p_district_id character varying, p_current_tier integer, p_tier_result jsonb, p_escalation_reason text, p_batch_type character varying, p_cms_detected character varying, p_content_type character varying) IS 'Move district to next tier with escalation reason. Tier 5 failure goes to manual_review.';


--
-- Name: get_nces_id(character varying, character varying, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_nces_id(p_state character varying, p_state_district_id character varying, p_id_system character varying DEFAULT 'st_leaid'::character varying) RETURNS character varying
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_nces_id VARCHAR(10);
BEGIN
    SELECT nces_id INTO v_nces_id
    FROM state_district_crosswalk
    WHERE state = p_state
      AND state_district_id = p_state_district_id
      AND id_system = p_id_system;

    RETURN v_nces_id;
END;
$$;


--
-- Name: FUNCTION get_nces_id(p_state character varying, p_state_district_id character varying, p_id_system character varying); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.get_nces_id(p_state character varying, p_state_district_id character varying, p_id_system character varying) IS 'Look up NCES ID from state district ID';


--
-- Name: get_queue_dashboard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_queue_dashboard() RETURNS TABLE(metric character varying, value text)
    LANGUAGE plpgsql
    AS $_$
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
$_$;


--
-- Name: FUNCTION get_queue_dashboard(); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.get_queue_dashboard() IS 'Returns formatted queue status for monitoring dashboard';


--
-- Name: get_state_district_id(character varying, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_state_district_id(p_nces_id character varying, p_id_system character varying DEFAULT 'st_leaid'::character varying) RETURNS character varying
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_state_id VARCHAR(20);
BEGIN
    SELECT state_district_id INTO v_state_id
    FROM state_district_crosswalk
    WHERE nces_id = p_nces_id AND id_system = p_id_system;

    RETURN v_state_id;
END;
$$;


--
-- Name: FUNCTION get_state_district_id(p_nces_id character varying, p_id_system character varying); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.get_state_district_id(p_nces_id character varying, p_id_system character varying) IS 'Look up state district ID from NCES ID';


--
-- Name: is_within_3year_window(character varying, character varying, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.is_within_3year_window(enrollment_year character varying, staffing_year character varying, bell_schedule_year character varying) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE
    years INTEGER[];
    min_year INTEGER;
    max_year INTEGER;
    span INTEGER;
BEGIN
    -- Collect non-null years
    years := ARRAY[]::INTEGER[];

    IF enrollment_year IS NOT NULL THEN
        years := array_append(years, school_year_to_numeric(enrollment_year));
    END IF;

    IF staffing_year IS NOT NULL THEN
        years := array_append(years, school_year_to_numeric(staffing_year));
    END IF;

    IF bell_schedule_year IS NOT NULL THEN
        years := array_append(years, school_year_to_numeric(bell_schedule_year));
    END IF;

    -- If fewer than 2 years, no span to check
    IF array_length(years, 1) IS NULL OR array_length(years, 1) < 2 THEN
        RETURN TRUE;
    END IF;

    -- Calculate span (absolute difference, no +1)
    SELECT MIN(y), MAX(y) INTO min_year, max_year FROM unnest(years) AS y;
    span := max_year - min_year;

    RETURN span <= 3;
END;
$$;


--
-- Name: FUNCTION is_within_3year_window(enrollment_year character varying, staffing_year character varying, bell_schedule_year character varying); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.is_within_3year_window(enrollment_year character varying, staffing_year character varying, bell_schedule_year character varying) IS 'Check if component years are within the 3-year blending window';


--
-- Name: mark_district_skip(character varying, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.mark_district_skip(p_district_id character varying, p_reason text DEFAULT 'repeated_failures'::text) RETURNS void
    LANGUAGE sql
    AS $$
UPDATE enrichment_attempts
SET
    skip_future_attempts = TRUE,
    skip_reason = p_reason
WHERE district_id = p_district_id
AND skip_future_attempts = FALSE;
$$;


--
-- Name: FUNCTION mark_district_skip(p_district_id character varying, p_reason text); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.mark_district_skip(p_district_id character varying, p_reason text) IS 'Mark all attempts for a district as skip_future_attempts=TRUE';


--
-- Name: mark_security_blocked(character varying, integer, jsonb, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.mark_security_blocked(p_district_id character varying, p_current_tier integer, p_tier_result jsonb, p_block_reason text) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
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
$$;


--
-- Name: FUNCTION mark_security_blocked(p_district_id character varying, p_current_tier integer, p_tier_result jsonb, p_block_reason text); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.mark_security_blocked(p_district_id character varying, p_current_tier integer, p_tier_result jsonb, p_block_reason text) IS 'Mark district as permanently blocked due to security protection (Cloudflare/WAF/403)';


--
-- Name: queue_districts_for_enrichment(character varying[]); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.queue_districts_for_enrichment(district_ids character varying[]) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    inserted_count INTEGER;
BEGIN
    INSERT INTO enrichment_queue (district_id, status, current_tier)
    SELECT unnest(district_ids), 'pending', 1
    ON CONFLICT (district_id) DO NOTHING;

    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RETURN inserted_count;
END;
$$;


--
-- Name: FUNCTION queue_districts_for_enrichment(district_ids character varying[]); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.queue_districts_for_enrichment(district_ids character varying[]) IS 'Add districts to enrichment queue at Tier 1';


--
-- Name: refresh_all_materialized_views(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.refresh_all_materialized_views() RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    REFRESH MATERIALIZED VIEW mv_districts_with_lct_data;
    REFRESH MATERIALIZED VIEW mv_state_enrichment_progress;
    REFRESH MATERIALIZED VIEW mv_unenriched_districts;
    REFRESH MATERIALIZED VIEW mv_lct_summary_stats;
END;
$$;


--
-- Name: school_year_to_numeric(character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.school_year_to_numeric(year_str character varying) RETURNS integer
    LANGUAGE plpgsql IMMUTABLE
    AS $$
BEGIN
    -- Handle formats: '2023-24', '2023', '2023-2024'
    IF year_str IS NULL OR year_str = '' THEN
        RETURN NULL;
    END IF;

    -- Extract first 4 digits (the starting year)
    RETURN CAST(SUBSTRING(year_str FROM 1 FOR 4) AS INTEGER);
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;


--
-- Name: FUNCTION school_year_to_numeric(year_str character varying); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.school_year_to_numeric(year_str character varying) IS 'Convert school year string (e.g., 2023-24) to numeric year (2023)';


--
-- Name: should_skip_district(character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.should_skip_district(p_district_id character varying) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM enrichment_attempts
        WHERE district_id = p_district_id
        AND skip_future_attempts = TRUE
    );
END;
$$;


--
-- Name: FUNCTION should_skip_district(p_district_id character varying); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.should_skip_district(p_district_id character varying) IS 'Returns TRUE if district is flagged to skip future enrichment attempts';


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


--
-- Name: validate_lct_temporal(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.validate_lct_temporal() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    span INTEGER;
BEGIN
    span := (
        SELECT MAX(y) - MIN(y)
        FROM (
            SELECT school_year_to_numeric(NEW.enrollment_source_year) AS y
            WHERE NEW.enrollment_source_year IS NOT NULL
            UNION ALL
            SELECT school_year_to_numeric(NEW.staff_source_year)
            WHERE NEW.staff_source_year IS NOT NULL
            UNION ALL
            SELECT school_year_to_numeric(NEW.bell_schedule_source_year)
            WHERE NEW.bell_schedule_source_year IS NOT NULL
        ) AS years
        WHERE y IS NOT NULL
    );
    NEW.year_span := span;
    NEW.within_3year_window := (span IS NULL OR span <= 3);
    IF NEW.temporal_flags IS NULL THEN
        NEW.temporal_flags := ARRAY[]::TEXT[];
    END IF;
    IF span BETWEEN 2 AND 3 THEN
        IF NOT ('WARN_YEAR_GAP' = ANY(NEW.temporal_flags)) THEN
            NEW.temporal_flags := array_append(NEW.temporal_flags, 'WARN_YEAR_GAP');
        END IF;
    END IF;
    IF span > 3 THEN
        IF NOT ('ERR_SPAN_EXCEEDED' = ANY(NEW.temporal_flags)) THEN
            NEW.temporal_flags := array_append(NEW.temporal_flags, 'ERR_SPAN_EXCEEDED');
        END IF;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: year_span(character varying, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.year_span(year1 character varying, year2 character varying) RETURNS integer
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE
    y1 INTEGER;
    y2 INTEGER;
BEGIN
    y1 := school_year_to_numeric(year1);
    y2 := school_year_to_numeric(year2);

    IF y1 IS NULL OR y2 IS NULL THEN
        RETURN NULL;
    END IF;

    -- Span is the absolute difference in start years (no +1)
    -- 0 = same year, 1 = adjacent years, 2+ = gap between years
    RETURN ABS(y2 - y1);
END;
$$;


--
-- Name: FUNCTION year_span(year1 character varying, year2 character varying); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.year_span(year1 character varying, year2 character varying) IS 'Calculate the span in years between two school years';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: bell_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bell_schedules (
    id integer NOT NULL,
    district_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    grade_level character varying(20) NOT NULL,
    instructional_minutes integer NOT NULL,
    start_time character varying(50),
    end_time character varying(50),
    lunch_duration integer,
    passing_periods integer,
    recess_duration integer,
    schools_sampled jsonb DEFAULT '[]'::jsonb,
    source_urls jsonb DEFAULT '[]'::jsonb,
    confidence character varying(10) DEFAULT 'high'::character varying NOT NULL,
    method character varying(50) NOT NULL,
    source_description text,
    notes text,
    raw_import jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    minutes_weighted_mean numeric,
    minutes_min integer,
    minutes_mode integer,
    minutes_max integer,
    schools_in_sample integer,
    enrollment_in_sample integer,
    aggregation_method character varying(40),
    CONSTRAINT chk_confidence CHECK (((confidence)::text = ANY ((ARRAY['high'::character varying, 'medium'::character varying, 'low'::character varying])::text[]))),
    CONSTRAINT chk_grade_level CHECK (((grade_level)::text = ANY ((ARRAY['elementary'::character varying, 'middle'::character varying, 'high'::character varying])::text[]))),
    CONSTRAINT chk_instructional_minutes CHECK (((instructional_minutes >= 100) AND (instructional_minutes <= 600))),
    CONSTRAINT chk_lunch_duration CHECK (((lunch_duration IS NULL) OR ((lunch_duration >= 10) AND (lunch_duration <= 90)))),
    CONSTRAINT chk_method CHECK (((method)::text = ANY ((ARRAY['automated_enrichment'::character varying, 'human_provided'::character varying, 'statutory_fallback'::character varying, 'web_scraping'::character varying, 'fallback_statutory'::character varying, 'pdf_extraction'::character varying, 'manual_data_collection'::character varying, 'district_policy'::character varying, 'school_sample'::character varying, 'district_standardized_schedule'::character varying, 'school_specific_schedules'::character varying, 'school_hours_with_estimation'::character varying, 'state_requirement_with_validation'::character varying, 'tier_1_firecrawl_regex'::character varying, 'tier_1_firecrawl_table'::character varying, 'tier_1_firecrawl_map'::character varying, 'tier_1_pattern'::character varying, 'tier_1_scraper'::character varying, 'tier_1_fallback'::character varying, 'tier_2_pattern'::character varying, 'tier_2_html'::character varying, 'tier_2_scraper'::character varying, 'tier_3_pdf'::character varying, 'tier_3_ocr'::character varying, 'tier_3_document'::character varying, 'tier_4_claude'::character varying, 'tier_4_auto'::character varying, 'tier_4_api'::character varying, 'tier_5_gemini'::character varying, 'tier_5_web_search'::character varying, 'tier_5_mcp'::character varying])::text[])))
);


--
-- Name: TABLE bell_schedules; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.bell_schedules IS 'Enriched bell schedule data with actual instructional time';


--
-- Name: COLUMN bell_schedules.grade_level; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.bell_schedules.grade_level IS 'Grade level category: elementary, middle, or high';


--
-- Name: COLUMN bell_schedules.instructional_minutes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.bell_schedules.instructional_minutes IS 'Daily instructional minutes (excluding lunch, passing, recess)';


--
-- Name: COLUMN bell_schedules.method; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.bell_schedules.method IS 'Collection method: automated_enrichment, human_provided, or statutory_fallback';


--
-- Name: COLUMN bell_schedules.raw_import; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.bell_schedules.raw_import IS 'Original JSON from import for reference and debugging';


--
-- Name: COLUMN bell_schedules.minutes_weighted_mean; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.bell_schedules.minutes_weighted_mean IS 'Enrollment-weighted mean of per-school instructional minutes (the district grade-band value).';


--
-- Name: COLUMN bell_schedules.minutes_mode; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.bell_schedules.minutes_mode IS 'Most common per-school instructional-minutes value in the sample (transparency).';


--
-- Name: COLUMN bell_schedules.aggregation_method; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.bell_schedules.aggregation_method IS 'How the grade-band value was derived: enrollment_weighted_mean | simple_mean | single_school.';


--
-- Name: bell_schedules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bell_schedules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bell_schedules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bell_schedules_id_seq OWNED BY public.bell_schedules.id;


--
-- Name: ca_enrollment_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ca_enrollment_data (
    nces_id character varying(10) NOT NULL,
    cds_code character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    total_k12 integer,
    data_source character varying(50) DEFAULT 'cde_staff_ratios'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE ca_enrollment_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.ca_enrollment_data IS 'California enrollment data from CDE files';


--
-- Name: ca_lcff_funding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ca_lcff_funding (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    base_grant numeric(12,2),
    supplemental_grant numeric(12,2),
    concentration_grant numeric(12,2),
    total_lcff numeric(12,2),
    funded_ada numeric(10,2),
    unduplicated_pupil_count integer,
    upc_percentage numeric(10,6),
    base_tk_3 numeric(12,2),
    base_4_6 numeric(12,2),
    base_7_8 numeric(12,2),
    base_9_12 numeric(12,2),
    data_source character varying(50) NOT NULL,
    source_url character varying(500),
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT chk_upc_percentage CHECK (((upc_percentage >= (0)::numeric) AND (upc_percentage <= (1)::numeric)))
);


--
-- Name: ca_lcff_funding_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ca_lcff_funding_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ca_lcff_funding_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ca_lcff_funding_id_seq OWNED BY public.ca_lcff_funding.id;


--
-- Name: ca_sped_district_environments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ca_sped_district_environments (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    cds_code character varying(7) NOT NULL,
    year character varying(10) NOT NULL,
    data_source character varying(50) NOT NULL,
    sped_enrollment_total integer,
    sped_mainstreamed integer,
    sped_mainstreamed_80_plus integer,
    sped_mainstreamed_40_79 integer,
    sped_self_contained integer,
    sped_self_contained_lt_40 integer,
    sped_separate_school integer,
    sped_preschool integer,
    sped_missing integer,
    self_contained_proportion numeric(10,6),
    confidence character varying(20) NOT NULL,
    notes text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT chk_ca_sped_confidence CHECK (((confidence)::text = ANY ((ARRAY['high'::character varying, 'medium'::character varying, 'low'::character varying])::text[])))
);


--
-- Name: ca_sped_district_environments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ca_sped_district_environments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ca_sped_district_environments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ca_sped_district_environments_id_seq OWNED BY public.ca_sped_district_environments.id;


--
-- Name: ca_staff_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ca_staff_data (
    nces_id character varying(10) NOT NULL,
    cds_code character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    teachers_fte numeric(10,2),
    admin_fte numeric(10,2),
    pupil_services_fte numeric(10,2),
    other_staff_fte numeric(10,2),
    data_source character varying(50) DEFAULT 'cde_staff_ratios'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE ca_staff_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.ca_staff_data IS 'California staff data from CDE Staff Ratio files';


--
-- Name: calculation_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.calculation_runs (
    run_id character varying(50) NOT NULL,
    target_year character varying(10),
    run_type character varying(30) NOT NULL,
    status character varying(20) NOT NULL,
    districts_processed integer DEFAULT 0,
    districts_skipped integer DEFAULT 0,
    calculations_created integer DEFAULT 0,
    input_hash character varying(64),
    previous_run_id character varying(50),
    started_at timestamp with time zone DEFAULT now(),
    completed_at timestamp with time zone,
    output_files jsonb DEFAULT '[]'::jsonb,
    error_message text,
    qa_summary jsonb,
    calculation_mode public.calculation_mode_enum DEFAULT 'blended'::public.calculation_mode_enum NOT NULL,
    data_year_min character varying(10),
    data_year_max character varying(10),
    CONSTRAINT chk_target_year_required CHECK (((calculation_mode = 'blended'::public.calculation_mode_enum) OR ((calculation_mode = 'target_year'::public.calculation_mode_enum) AND (target_year IS NOT NULL))))
);


--
-- Name: TABLE calculation_runs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.calculation_runs IS 'Tracks LCT calculation runs. Supports blended (REQ-026 compliant) and target_year modes.';


--
-- Name: COLUMN calculation_runs.target_year; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.calculation_runs.target_year IS 'Target year for enrollment anchor (required for target_year mode, optional for blended)';


--
-- Name: COLUMN calculation_runs.calculation_mode; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.calculation_runs.calculation_mode IS 'Calculation mode: blended (most recent within REQ-026 window) or target_year (enrollment anchored)';


--
-- Name: COLUMN calculation_runs.data_year_min; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.calculation_runs.data_year_min IS 'Earliest source year actually used in this calculation run';


--
-- Name: COLUMN calculation_runs.data_year_max; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.calculation_runs.data_year_max IS 'Latest source year actually used in this calculation run';


--
-- Name: data_lineage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_lineage (
    id integer NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id character varying(50) NOT NULL,
    operation character varying(30) NOT NULL,
    source_file character varying(500),
    details jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_by character varying(100) DEFAULT 'system'::character varying
);


--
-- Name: TABLE data_lineage; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.data_lineage IS 'Audit trail for data changes and imports';


--
-- Name: COLUMN data_lineage.entity_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.data_lineage.entity_type IS 'Type of entity: district, bell_schedule, lct_calculation';


--
-- Name: COLUMN data_lineage.operation; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.data_lineage.operation IS 'Operation performed: create, update, import, calculate, migrate';


--
-- Name: data_lineage_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.data_lineage_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: data_lineage_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.data_lineage_id_seq OWNED BY public.data_lineage.id;


--
-- Name: data_source_registry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_source_registry (
    id integer NOT NULL,
    source_code character varying(50) NOT NULL,
    source_name character varying(255) NOT NULL,
    source_type character varying(50) NOT NULL,
    source_url text,
    geographic_scope character varying(50),
    state character varying(2),
    latest_year_available character varying(10),
    years_available jsonb DEFAULT '[]'::jsonb,
    last_checked_at timestamp with time zone,
    next_expected_release character varying(50),
    access_method character varying(50),
    access_notes text,
    requires_authentication boolean DEFAULT false,
    reliability_score integer,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT data_source_registry_reliability_score_check CHECK (((reliability_score >= 1) AND (reliability_score <= 5)))
);


--
-- Name: TABLE data_source_registry; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.data_source_registry IS 'Registry of available data sources with metadata about coverage and access.';


--
-- Name: data_source_registry_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.data_source_registry_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: data_source_registry_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.data_source_registry_id_seq OWNED BY public.data_source_registry.id;


--
-- Name: district_funding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.district_funding (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    state character varying(2) NOT NULL,
    title_i_allocation numeric(12,2),
    idea_allocation numeric(12,2),
    title_iii_allocation numeric(12,2),
    other_federal numeric(12,2),
    state_formula_type character varying(50),
    base_allocation numeric(12,2),
    equity_adjustment numeric(12,2),
    equity_adjustment_type character varying(100),
    total_state_funding numeric(12,2),
    local_revenue numeric(12,2),
    total_per_pupil numeric(10,2),
    instructional_per_pupil numeric(10,2),
    data_source character varying(50) NOT NULL,
    source_url character varying(500),
    fiscal_year character varying(10),
    notes text,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: district_funding_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.district_funding_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: district_funding_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.district_funding_id_seq OWNED BY public.district_funding.id;


--
-- Name: district_socioeconomic; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.district_socioeconomic (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    state character varying(2) NOT NULL,
    poverty_indicator_type character varying(50) NOT NULL,
    poverty_percent numeric(10,6),
    poverty_count integer,
    enrollment integer,
    tier_1_count integer,
    tier_2_count integer,
    tier_3_count integer,
    tier_4_count integer,
    tier_5_count integer,
    tier_metadata jsonb,
    title_i_eligible boolean,
    schoolwide_program boolean,
    data_source character varying(50) NOT NULL,
    source_url character varying(500),
    collection_method character varying(100),
    certification_status character varying(20),
    notes text,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT chk_poverty_percent CHECK (((poverty_percent >= (0)::numeric) AND (poverty_percent <= (1)::numeric)))
);


--
-- Name: district_socioeconomic_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.district_socioeconomic_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: district_socioeconomic_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.district_socioeconomic_id_seq OWNED BY public.district_socioeconomic.id;


--
-- Name: districts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.districts (
    nces_id character varying(10) NOT NULL,
    name character varying(255) NOT NULL,
    state character(2) NOT NULL,
    enrollment integer,
    instructional_staff numeric(10,2),
    total_staff numeric(10,2),
    schools_count integer,
    year character varying(10) NOT NULL,
    data_source character varying(50) DEFAULT 'nces_ccd'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    st_leaid character varying(20),
    is_career_technical_center boolean DEFAULT false,
    is_shared_service_entity boolean DEFAULT false,
    website_url character varying(500)
);


--
-- Name: TABLE districts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.districts IS 'U.S. school districts from NCES Common Core of Data';


--
-- Name: COLUMN districts.nces_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.districts.nces_id IS 'NCES 7-digit district identifier';


--
-- Name: COLUMN districts.instructional_staff; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.districts.instructional_staff IS 'Full-time equivalent instructional staff count';


--
-- Name: COLUMN districts.year; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.districts.year IS 'School year in YYYY-YY format (e.g., 2023-24)';


--
-- Name: COLUMN districts.st_leaid; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.districts.st_leaid IS 'State-assigned LEA ID (e.g., CA-6275796 for California CDS codes)';


--
-- Name: enrichment_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.enrichment_attempts (
    id integer NOT NULL,
    district_id character varying(10) NOT NULL,
    url text NOT NULL,
    attempted_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    status character varying(20) NOT NULL,
    block_type character varying(30),
    http_status_code integer,
    error_message text,
    timing_ms integer,
    retry_count integer DEFAULT 0,
    last_retry_at timestamp with time zone,
    skip_future_attempts boolean DEFAULT false,
    skip_reason text,
    scraper_version character varying(20),
    enrichment_tier character varying(10),
    notes text,
    response_details jsonb,
    CONSTRAINT chk_block_type CHECK (((block_type IS NULL) OR ((block_type)::text = ANY ((ARRAY['cloudflare'::character varying, 'waf'::character varying, 'captcha'::character varying])::text[])))),
    CONSTRAINT chk_retry_count CHECK ((retry_count >= 0)),
    CONSTRAINT chk_status CHECK (((status)::text = ANY ((ARRAY['success'::character varying, 'blocked'::character varying, 'not_found'::character varying, 'timeout'::character varying, 'error'::character varying, 'queue_full'::character varying])::text[])))
);


--
-- Name: TABLE enrichment_attempts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.enrichment_attempts IS 'Audit log of all bell schedule enrichment attempts (success and failure)';


--
-- Name: COLUMN enrichment_attempts.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.enrichment_attempts.status IS 'Outcome: success, blocked, not_found, timeout, error, queue_full';


--
-- Name: COLUMN enrichment_attempts.block_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.enrichment_attempts.block_type IS 'Type of security block: cloudflare, waf, or captcha';


--
-- Name: COLUMN enrichment_attempts.skip_future_attempts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.enrichment_attempts.skip_future_attempts IS 'If TRUE, don''t attempt this district again (marked after repeated failures)';


--
-- Name: COLUMN enrichment_attempts.response_details; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.enrichment_attempts.response_details IS 'Full JSON response from scraper service for debugging';


--
-- Name: enrichment_attempts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.enrichment_attempts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: enrichment_attempts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.enrichment_attempts_id_seq OWNED BY public.enrichment_attempts.id;


--
-- Name: enrichment_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.enrichment_batches (
    id integer NOT NULL,
    batch_type character varying(50) NOT NULL,
    tier integer NOT NULL,
    district_count integer NOT NULL,
    grouping_strategy character varying(100),
    shared_context text,
    created_at timestamp without time zone DEFAULT now(),
    submitted_at timestamp without time zone,
    completed_at timestamp without time zone,
    status character varying(20) DEFAULT 'pending'::character varying,
    success_count integer DEFAULT 0,
    failure_count integer DEFAULT 0,
    api_cost_cents integer,
    api_tokens_used integer,
    processing_time_seconds integer,
    api_provider character varying(50),
    api_model character varying(50),
    api_response jsonb
);


--
-- Name: TABLE enrichment_batches; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.enrichment_batches IS 'Batch processing for API-based enrichment tiers (Claude, Gemini)';


--
-- Name: enrichment_batches_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.enrichment_batches_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: enrichment_batches_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.enrichment_batches_id_seq OWNED BY public.enrichment_batches.id;


--
-- Name: enrichment_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.enrichment_queue (
    id integer NOT NULL,
    district_id character varying(10),
    current_tier integer DEFAULT 1,
    tier_1_result jsonb,
    tier_2_result jsonb,
    tier_3_result jsonb,
    tier_4_result jsonb,
    tier_5_result jsonb,
    batch_id integer,
    batch_type character varying(50),
    queued_at timestamp without time zone DEFAULT now(),
    processing_started_at timestamp without time zone,
    completed_at timestamp without time zone,
    status character varying(20) DEFAULT 'pending'::character varying,
    escalation_reason text,
    final_success boolean,
    cms_detected character varying(50),
    content_type character varying(50),
    notes text,
    estimated_cost_cents integer DEFAULT 0,
    processing_time_seconds integer,
    security_blocked boolean DEFAULT false,
    security_block_reason text
);


--
-- Name: TABLE enrichment_queue; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.enrichment_queue IS 'Multi-tier bell schedule enrichment queue with escalation tracking';


--
-- Name: COLUMN enrichment_queue.security_blocked; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.enrichment_queue.security_blocked IS 'True if district website is protected by Cloudflare/WAF/403 and should never be auto-scraped';


--
-- Name: COLUMN enrichment_queue.security_block_reason; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.enrichment_queue.security_block_reason IS 'Reason for security block (cloudflare, waf, captcha, 403, rate_limit)';


--
-- Name: enrichment_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.enrichment_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: enrichment_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.enrichment_queue_id_seq OWNED BY public.enrichment_queue.id;


--
-- Name: enrollment_by_grade; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.enrollment_by_grade (
    id integer NOT NULL,
    district_id character varying(10) NOT NULL,
    source_year character varying(10) NOT NULL,
    data_source character varying(50) DEFAULT 'nces_ccd'::character varying NOT NULL,
    enrollment_prek numeric(10,0),
    enrollment_kindergarten numeric(10,0),
    enrollment_grade_1 numeric(10,0),
    enrollment_grade_2 numeric(10,0),
    enrollment_grade_3 numeric(10,0),
    enrollment_grade_4 numeric(10,0),
    enrollment_grade_5 numeric(10,0),
    enrollment_grade_6 numeric(10,0),
    enrollment_grade_7 numeric(10,0),
    enrollment_grade_8 numeric(10,0),
    enrollment_grade_9 numeric(10,0),
    enrollment_grade_10 numeric(10,0),
    enrollment_grade_11 numeric(10,0),
    enrollment_grade_12 numeric(10,0),
    enrollment_grade_13 numeric(10,0),
    enrollment_ungraded numeric(10,0),
    enrollment_adult_ed numeric(10,0),
    enrollment_total numeric(10,0),
    enrollment_k12 numeric(10,0),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    enrollment_elementary numeric(10,0),
    enrollment_secondary numeric(10,0)
);


--
-- Name: TABLE enrollment_by_grade; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.enrollment_by_grade IS 'Grade-level enrollment for LCT-Core calculations (excludes Pre-K from denominator).';


--
-- Name: enrollment_by_grade_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.enrollment_by_grade_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: enrollment_by_grade_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.enrollment_by_grade_id_seq OWNED BY public.enrollment_by_grade.id;


--
-- Name: fl_district_identifiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fl_district_identifiers (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    fldoe_district_no character varying(2) NOT NULL,
    district_name_fldoe character varying(255),
    district_type character varying(50),
    is_charter boolean DEFAULT false,
    county_name character varying(100),
    data_source character varying(50) DEFAULT 'fldoe'::character varying,
    source_year character varying(10),
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE fl_district_identifiers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.fl_district_identifiers IS 'Florida Department of Education district identifiers and crosswalk (Layer 2)';


--
-- Name: fl_district_identifiers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fl_district_identifiers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fl_district_identifiers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fl_district_identifiers_id_seq OWNED BY public.fl_district_identifiers.id;


--
-- Name: fl_enrollment_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fl_enrollment_data (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    data_source character varying(50) DEFAULT 'fldoe'::character varying,
    total_enrollment integer,
    pk_12_membership integer,
    pk_membership integer,
    k_12_membership integer,
    demographics jsonb,
    confidence character varying(20) DEFAULT 'high'::character varying,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_fl_enrollment_confidence CHECK (((confidence)::text = ANY ((ARRAY['high'::character varying, 'medium'::character varying, 'low'::character varying])::text[])))
);


--
-- Name: TABLE fl_enrollment_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.fl_enrollment_data IS 'Florida enrollment data from FLDOE (Layer 2)';


--
-- Name: fl_enrollment_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fl_enrollment_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fl_enrollment_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fl_enrollment_data_id_seq OWNED BY public.fl_enrollment_data.id;


--
-- Name: fl_staff_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fl_staff_data (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    data_source character varying(50) DEFAULT 'fldoe'::character varying,
    total_instructional_staff numeric(10,2),
    classroom_teachers numeric(10,2),
    ese_teachers numeric(10,2),
    media_specialists numeric(10,2),
    guidance_counselors numeric(10,2),
    instructional_coaches numeric(10,2),
    other_instructional numeric(10,2),
    administrators numeric(10,2),
    confidence character varying(20) DEFAULT 'high'::character varying,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_fl_staff_confidence CHECK (((confidence)::text = ANY ((ARRAY['high'::character varying, 'medium'::character varying, 'low'::character varying])::text[])))
);


--
-- Name: TABLE fl_staff_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.fl_staff_data IS 'Florida staff data from FLDOE (Layer 2)';


--
-- Name: fl_staff_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fl_staff_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fl_staff_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fl_staff_data_id_seq OWNED BY public.fl_staff_data.id;


--
-- Name: il_district_identifiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.il_district_identifiers (
    nces_id character varying(10) NOT NULL,
    isbe_rcdts character varying(20) NOT NULL,
    district_name_isbe character varying(255),
    source_year character varying(10),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: il_enrollment_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.il_enrollment_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    total_enrollment integer,
    pct_white numeric(5,2),
    pct_black numeric(5,2),
    pct_hispanic numeric(5,2),
    pct_asian numeric(5,2),
    pct_low_income numeric(5,2),
    pct_iep numeric(5,2),
    pct_el numeric(5,2),
    students_with_disabilities integer,
    iep_students integer,
    data_source character varying(50) DEFAULT 'isbe_report_card'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: il_staff_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.il_staff_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    total_teacher_fte numeric(10,2),
    counselor_fte numeric(10,2),
    nurse_fte numeric(10,2),
    psychologist_fte numeric(10,2),
    social_worker_fte numeric(10,2),
    ptr_elementary numeric(5,2),
    ptr_high_school numeric(5,2),
    teacher_retention_rate numeric(5,2),
    teacher_avg_salary numeric(10,2),
    data_source character varying(50) DEFAULT 'isbe_report_card'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: lct_calculations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lct_calculations (
    id integer NOT NULL,
    district_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    grade_level character varying(20),
    instructional_minutes integer NOT NULL,
    enrollment integer NOT NULL,
    instructional_staff numeric(10,2) NOT NULL,
    lct_value numeric(10,4) NOT NULL,
    data_tier integer NOT NULL,
    bell_schedule_id integer,
    calculated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    notes text,
    staff_scope character varying(50) DEFAULT 'instructional'::character varying NOT NULL,
    staff_source character varying(50),
    staff_source_year character varying(10),
    enrollment_source character varying(50),
    enrollment_source_year character varying(10),
    bell_schedule_source character varying(50),
    bell_schedule_source_year character varying(10),
    component_years jsonb,
    year_span integer,
    within_3year_window boolean DEFAULT true,
    temporal_flags text[],
    staff_year character varying(10),
    instructional_minutes_source character varying(100),
    instructional_minutes_year character varying(10),
    enrollment_type character varying(50) DEFAULT 'k12'::character varying,
    run_id character varying(50),
    CONSTRAINT chk_data_tier CHECK ((data_tier = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT chk_enrollment_positive CHECK ((enrollment > 0)),
    CONSTRAINT chk_lct_positive CHECK ((lct_value > (0)::numeric)),
    CONSTRAINT chk_staff_positive CHECK ((instructional_staff > (0)::numeric)),
    CONSTRAINT chk_staff_scope CHECK (((staff_scope)::text = ANY ((ARRAY['teachers_only'::character varying, 'teachers_core'::character varying, 'teachers_elementary'::character varying, 'teachers_secondary'::character varying, 'instructional'::character varying, 'instructional_plus_support'::character varying, 'all'::character varying, 'core_sped'::character varying, 'teachers_gened'::character varying, 'instructional_sped'::character varying])::text[])))
);


--
-- Name: TABLE lct_calculations; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.lct_calculations IS 'Computed Learning Connection Time metrics';


--
-- Name: COLUMN lct_calculations.lct_value; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.lct_value IS 'LCT = (instructional_minutes * instructional_staff) / enrollment';


--
-- Name: COLUMN lct_calculations.data_tier; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.data_tier IS '1=actual bell schedule, 2=automated enrichment, 3=statutory fallback';


--
-- Name: COLUMN lct_calculations.staff_scope; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.staff_scope IS 'LCT staff scope variant (teachers_only, instructional, etc.)';


--
-- Name: COLUMN lct_calculations.staff_source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.staff_source IS 'Source of staff data (nces_ccd, sped_estimate_2017-18, etc.)';


--
-- Name: COLUMN lct_calculations.component_years; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.component_years IS 'JSON tracking source years for each component: {enrollment, staffing, bell_schedule}';


--
-- Name: COLUMN lct_calculations.temporal_flags; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.temporal_flags IS 'Temporal validation flags (based on year_span = |year1_start - year2_start|):
- No flags: span 0-1 (same year or adjacent years, e.g., 2024-25 and 2023-24)
- WARN_YEAR_GAP: Sources span 2-3 years (1-2 year gap, valid but notable)
- ERR_SPAN_EXCEEDED: Sources span >3 years (exceeds blending window, requires resolution)
- INFO_CROSS_YEAR: Different years used for different components
- INFO_RATIO_BASELINE: Uses SPED ratio baseline (2017-18, exempt from 3-year rule)';


--
-- Name: COLUMN lct_calculations.staff_year; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.staff_year IS 'Year of staff data (2023-24, etc.)';


--
-- Name: COLUMN lct_calculations.instructional_minutes_source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.instructional_minutes_source IS 'Source of minutes (bell_schedule, state_requirement, default)';


--
-- Name: COLUMN lct_calculations.instructional_minutes_year; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.instructional_minutes_year IS 'Year of bell schedule data';


--
-- Name: COLUMN lct_calculations.enrollment_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.enrollment_type IS 'Type of enrollment used (k12, elementary_k5, secondary_6_12, self_contained_sped, gened)';


--
-- Name: COLUMN lct_calculations.run_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lct_calculations.run_id IS 'Link to calculation_runs.run_id for this calculation';


--
-- Name: lct_calculations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.lct_calculations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: lct_calculations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.lct_calculations_id_seq OWNED BY public.lct_calculations.id;


--
-- Name: ma_district_identifiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ma_district_identifiers (
    nces_id character varying(10) NOT NULL,
    dese_district_code character varying(10) NOT NULL,
    district_name_dese character varying(255),
    source_year character varying(10),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: ma_enrollment_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ma_enrollment_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    total_enrollment integer,
    pk_enrollment integer,
    k_enrollment integer,
    sped_count integer,
    sped_pct numeric(5,3),
    el_count integer,
    el_pct numeric(5,3),
    low_income_count integer,
    low_income_pct numeric(5,3),
    data_source character varying(50) DEFAULT 'dese_e2c_hub'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: ma_staff_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ma_staff_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    teachers_fte numeric(10,2),
    pct_licensed numeric(5,2),
    student_teacher_ratio numeric(5,2),
    pct_experienced numeric(5,2),
    data_source character varying(50) DEFAULT 'dese_profiles'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: mi_district_identifiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mi_district_identifiers (
    nces_id character varying(10) NOT NULL,
    mde_district_code character varying(10) NOT NULL,
    district_name_mde character varying(255),
    source_year character varying(10),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: mi_enrollment_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mi_enrollment_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    total_k12 numeric(10,2),
    k_enrollment numeric(10,2),
    g1_enrollment numeric(10,2),
    g2_enrollment numeric(10,2),
    g3_enrollment numeric(10,2),
    g4_enrollment numeric(10,2),
    g5_enrollment numeric(10,2),
    g6_enrollment numeric(10,2),
    g7_enrollment numeric(10,2),
    g8_enrollment numeric(10,2),
    g9_enrollment numeric(10,2),
    g10_enrollment numeric(10,2),
    g11_enrollment numeric(10,2),
    g12_enrollment numeric(10,2),
    male_count numeric(10,2),
    female_count numeric(10,2),
    data_source character varying(50) DEFAULT 'mde_headcount'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: mi_special_ed_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mi_special_ed_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    students_with_iep integer,
    sped_percentage numeric(5,2),
    data_source character varying(50) DEFAULT 'mde_special_ed'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: mi_staff_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mi_staff_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    total_teacher_fte numeric(10,2),
    sped_instructional_fte numeric(10,2),
    instructional_aide_fte numeric(10,2),
    instructional_support_fte numeric(10,2),
    data_source character varying(50) DEFAULT 'mde_staffing'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: staff_counts_effective; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_counts_effective (
    district_id character varying(10) NOT NULL,
    effective_year character varying(10) NOT NULL,
    primary_source character varying(50) NOT NULL,
    sources_used jsonb DEFAULT '[]'::jsonb,
    teachers_total numeric(10,2),
    teachers_elementary numeric(10,2),
    teachers_kindergarten numeric(10,2),
    teachers_secondary numeric(10,2),
    teachers_prek numeric(10,2),
    teachers_ungraded numeric(10,2),
    instructional_coordinators numeric(10,2),
    librarians numeric(10,2),
    library_support numeric(10,2),
    paraprofessionals numeric(10,2),
    counselors_total numeric(10,2),
    counselors_elementary numeric(10,2),
    counselors_secondary numeric(10,2),
    psychologists numeric(10,2),
    student_support_services numeric(10,2),
    lea_administrators numeric(10,2),
    school_administrators numeric(10,2),
    lea_admin_support numeric(10,2),
    school_admin_support numeric(10,2),
    lea_staff_total numeric(10,2),
    school_staff_total numeric(10,2),
    other_staff numeric(10,2),
    scope_teachers_only numeric(10,2),
    scope_teachers_core numeric(10,2),
    scope_instructional numeric(10,2),
    scope_instructional_plus_support numeric(10,2),
    scope_all numeric(10,2),
    last_resolved_at timestamp with time zone DEFAULT now(),
    resolution_notes text,
    teachers_k12 numeric(10,2),
    teachers_elementary_k5 numeric(10,2),
    teachers_secondary_6_12 numeric(10,2)
);


--
-- Name: TABLE staff_counts_effective; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.staff_counts_effective IS 'Resolved current staff counts after precedence rules. One row per district. Primary query table for applications.';


--
-- Name: COLUMN staff_counts_effective.scope_teachers_only; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.staff_counts_effective.scope_teachers_only IS 'Pre-calculated: teachers_total';


--
-- Name: COLUMN staff_counts_effective.scope_teachers_core; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.staff_counts_effective.scope_teachers_core IS 'Pre-calculated: teachers_elementary + teachers_secondary + teachers_kindergarten';


--
-- Name: COLUMN staff_counts_effective.scope_instructional; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.staff_counts_effective.scope_instructional IS 'Pre-calculated: teachers_total + instructional_coordinators + paraprofessionals';


--
-- Name: COLUMN staff_counts_effective.scope_instructional_plus_support; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.staff_counts_effective.scope_instructional_plus_support IS 'Pre-calculated: scope_instructional + counselors_total + psychologists + student_support_services';


--
-- Name: COLUMN staff_counts_effective.scope_all; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.staff_counts_effective.scope_all IS 'Pre-calculated: lea_staff_total';


--
-- Name: state_requirements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.state_requirements (
    state character(2) NOT NULL,
    state_name character varying(50) NOT NULL,
    elementary_minutes integer,
    middle_minutes integer,
    high_minutes integer,
    default_minutes integer,
    annual_days integer,
    annual_hours numeric(6,2),
    notes text,
    source character varying(255),
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE state_requirements; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.state_requirements IS 'State statutory minimums for instructional time';


--
-- Name: COLUMN state_requirements.elementary_minutes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.state_requirements.elementary_minutes IS 'Daily instructional minutes for elementary (K-5/6)';


--
-- Name: COLUMN state_requirements.middle_minutes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.state_requirements.middle_minutes IS 'Daily instructional minutes for middle school (6-8)';


--
-- Name: COLUMN state_requirements.high_minutes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.state_requirements.high_minutes IS 'Daily instructional minutes for high school (9-12)';


--
-- Name: mv_districts_with_lct_data; Type: MATERIALIZED VIEW; Schema: public; Owner: -
--

CREATE MATERIALIZED VIEW public.mv_districts_with_lct_data AS
 SELECT d.nces_id,
    d.name AS district_name,
    d.state,
    d.enrollment AS district_enrollment,
    d.year AS district_year,
    s.effective_year AS staff_year,
    s.primary_source AS staff_source,
    s.teachers_k12,
    s.teachers_elementary_k5,
    s.teachers_secondary_6_12,
    s.scope_teachers_only,
    s.scope_teachers_core,
    s.scope_instructional,
    s.scope_instructional_plus_support,
    s.scope_all,
    e.source_year AS enrollment_year,
    e.enrollment_k12,
    e.enrollment_elementary,
    e.enrollment_secondary,
    e.enrollment_prek,
        CASE
            WHEN (EXISTS ( SELECT 1
               FROM public.bell_schedules b
              WHERE (((b.district_id)::text = (d.nces_id)::text) AND ((b.year)::text = ANY ((ARRAY['2024-25'::character varying, '2025-26'::character varying])::text[]))))) THEN true
            ELSE false
        END AS has_bell_schedule,
    sr.elementary_minutes AS state_elementary_minutes,
    sr.middle_minutes AS state_middle_minutes,
    sr.high_minutes AS state_high_minutes,
    sr.default_minutes AS state_default_minutes
   FROM (((public.districts d
     LEFT JOIN public.staff_counts_effective s ON (((d.nces_id)::text = (s.district_id)::text)))
     LEFT JOIN public.enrollment_by_grade e ON ((((d.nces_id)::text = (e.district_id)::text) AND ((e.source_year)::text = '2023-24'::text))))
     LEFT JOIN public.state_requirements sr ON ((d.state = sr.state)))
  WHERE ((s.scope_teachers_only IS NOT NULL) AND (e.enrollment_k12 IS NOT NULL) AND (e.enrollment_k12 > (0)::numeric))
  WITH NO DATA;


--
-- Name: mv_lct_summary_stats; Type: MATERIALIZED VIEW; Schema: public; Owner: -
--

CREATE MATERIALIZED VIEW public.mv_lct_summary_stats AS
 WITH scope_data AS (
         SELECT 'teachers_only'::text AS scope,
            d.nces_id,
            ((360.0 * s.scope_teachers_only) / e.enrollment_k12) AS lct_value
           FROM ((public.districts d
             JOIN public.staff_counts_effective s ON (((d.nces_id)::text = (s.district_id)::text)))
             JOIN public.enrollment_by_grade e ON ((((d.nces_id)::text = (e.district_id)::text) AND ((e.source_year)::text = '2023-24'::text))))
          WHERE ((s.scope_teachers_only > (0)::numeric) AND (e.enrollment_k12 > (0)::numeric))
        UNION ALL
         SELECT 'teachers_core'::text AS scope,
            d.nces_id,
            ((360.0 * s.scope_teachers_core) / e.enrollment_k12) AS lct_value
           FROM ((public.districts d
             JOIN public.staff_counts_effective s ON (((d.nces_id)::text = (s.district_id)::text)))
             JOIN public.enrollment_by_grade e ON ((((d.nces_id)::text = (e.district_id)::text) AND ((e.source_year)::text = '2023-24'::text))))
          WHERE ((s.scope_teachers_core > (0)::numeric) AND (e.enrollment_k12 > (0)::numeric))
        UNION ALL
         SELECT 'instructional'::text AS scope,
            d.nces_id,
            ((360.0 * s.scope_instructional) / e.enrollment_k12) AS lct_value
           FROM ((public.districts d
             JOIN public.staff_counts_effective s ON (((d.nces_id)::text = (s.district_id)::text)))
             JOIN public.enrollment_by_grade e ON ((((d.nces_id)::text = (e.district_id)::text) AND ((e.source_year)::text = '2023-24'::text))))
          WHERE ((s.scope_instructional > (0)::numeric) AND (e.enrollment_k12 > (0)::numeric))
        UNION ALL
         SELECT 'all'::text AS scope,
            d.nces_id,
            ((360.0 * s.scope_all) / e.enrollment_k12) AS lct_value
           FROM ((public.districts d
             JOIN public.staff_counts_effective s ON (((d.nces_id)::text = (s.district_id)::text)))
             JOIN public.enrollment_by_grade e ON ((((d.nces_id)::text = (e.district_id)::text) AND ((e.source_year)::text = '2023-24'::text))))
          WHERE ((s.scope_all > (0)::numeric) AND (e.enrollment_k12 > (0)::numeric))
        )
 SELECT scope,
    count(*) AS district_count,
    round(avg(lct_value), 2) AS mean_lct,
    round((percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((lct_value)::double precision)))::numeric, 2) AS median_lct,
    round(stddev(lct_value), 2) AS std_lct,
    round(min(lct_value), 2) AS min_lct,
    round(max(lct_value), 2) AS max_lct
   FROM scope_data
  WHERE ((lct_value > (0)::numeric) AND (lct_value <= (360)::numeric))
  GROUP BY scope
  WITH NO DATA;


--
-- Name: mv_state_enrichment_progress; Type: MATERIALIZED VIEW; Schema: public; Owner: -
--

CREATE MATERIALIZED VIEW public.mv_state_enrichment_progress AS
 SELECT d.state,
    count(DISTINCT d.nces_id) AS total_districts,
    count(DISTINCT b.district_id) AS enriched_districts,
    round(((100.0 * (count(DISTINCT b.district_id))::numeric) / (NULLIF(count(DISTINCT d.nces_id), 0))::numeric), 2) AS enrichment_pct,
    sum(d.enrollment) AS total_enrollment,
    3 AS target_per_state,
        CASE
            WHEN (count(DISTINCT b.district_id) >= 3) THEN 'complete'::text
            WHEN (count(DISTINCT b.district_id) > 0) THEN 'in_progress'::text
            ELSE 'not_started'::text
        END AS campaign_status
   FROM (public.districts d
     LEFT JOIN public.bell_schedules b ON ((((d.nces_id)::text = (b.district_id)::text) AND ((b.year)::text = ANY ((ARRAY['2024-25'::character varying, '2025-26'::character varying])::text[])))))
  GROUP BY d.state
  ORDER BY (count(DISTINCT b.district_id)) DESC, (sum(d.enrollment)) DESC
  WITH NO DATA;


--
-- Name: mv_unenriched_districts; Type: MATERIALIZED VIEW; Schema: public; Owner: -
--

CREATE MATERIALIZED VIEW public.mv_unenriched_districts AS
 SELECT nces_id,
    name AS district_name,
    state,
    enrollment,
    row_number() OVER (PARTITION BY state ORDER BY enrollment DESC) AS state_rank
   FROM public.districts d
  WHERE ((enrollment IS NOT NULL) AND (enrollment > 0) AND (NOT (EXISTS ( SELECT 1
           FROM public.bell_schedules b
          WHERE (((b.district_id)::text = (d.nces_id)::text) AND ((b.year)::text = ANY ((ARRAY['2024-25'::character varying, '2025-26'::character varying])::text[])))))))
  WITH NO DATA;


--
-- Name: ny_district_identifiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ny_district_identifiers (
    nces_id character varying(10) NOT NULL,
    nysed_district_id character varying(20) NOT NULL,
    district_name_nysed character varying(255),
    source_year character varying(10),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: ny_enrollment_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ny_enrollment_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    subgroup character varying(100) NOT NULL,
    enrollment_prek12 integer,
    enrollment_by_grade jsonb,
    data_source character varying(50) DEFAULT 'nysed_sirs'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: ny_staff_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ny_staff_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    staff_category character varying(100) NOT NULL,
    fte numeric(10,2),
    enrollment_k12 integer,
    district_ratio numeric(10,2),
    data_source character varying(50) DEFAULT 'nysed_pmf'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: pa_district_identifiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pa_district_identifiers (
    nces_id character varying(10) NOT NULL,
    pde_aun character varying(10) NOT NULL,
    district_name_pde character varying(255),
    lea_type character varying(10),
    county character varying(50),
    source_year character varying(10),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: pa_enrollment_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pa_enrollment_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    total_k12 numeric(10,2),
    prekf_enrollment numeric(10,2),
    k5f_enrollment numeric(10,2),
    g1_enrollment numeric(10,2),
    g2_enrollment numeric(10,2),
    g3_enrollment numeric(10,2),
    g4_enrollment numeric(10,2),
    g5_enrollment numeric(10,2),
    g6_enrollment numeric(10,2),
    g7_enrollment numeric(10,2),
    g8_enrollment numeric(10,2),
    g9_enrollment numeric(10,2),
    g10_enrollment numeric(10,2),
    g11_enrollment numeric(10,2),
    g12_enrollment numeric(10,2),
    data_source character varying(50) DEFAULT 'pde_enrollment'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: pa_staff_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pa_staff_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    classroom_teachers_fte numeric(10,2),
    professional_personnel_fte numeric(10,2),
    administrators_fte numeric(10,2),
    coordinate_services_fte numeric(10,2),
    other_professional_fte numeric(10,2),
    data_source character varying(50) DEFAULT 'pde_professional_staff'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version text NOT NULL,
    checksum text,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_by text,
    note text
);


--
-- Name: TABLE schema_migrations; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.schema_migrations IS 'Ledger of applied NNN_*.sql migrations. Managed by migrate.py.';


--
-- Name: school_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.school_schedules (
    id integer NOT NULL,
    district_id character varying(10) NOT NULL,
    school_id character varying(20),
    school_name text,
    year character varying(10),
    grade_level character varying(20),
    start_time character varying(10),
    end_time character varying(10),
    lunch_minutes integer,
    passing_minutes integer,
    instructional_minutes integer,
    enrollment integer,
    source_file text,
    source_url text,
    method character varying(40),
    confidence character varying(20),
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE school_schedules; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.school_schedules IS 'Per-school sampled bell schedules; aggregated to district grade-band values in bell_schedules.';


--
-- Name: school_schedules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.school_schedules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: school_schedules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.school_schedules_id_seq OWNED BY public.school_schedules.id;


--
-- Name: sped_estimates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sped_estimates (
    id integer NOT NULL,
    district_id character varying(10) NOT NULL,
    estimate_year character varying(10) NOT NULL,
    baseline_year character varying(10) NOT NULL,
    current_total_enrollment integer,
    current_total_teachers numeric(10,2),
    ratio_state_sped_teachers_per_student numeric(10,6),
    ratio_lea_sped_proportion numeric(10,6),
    used_state_average_for_proportion boolean NOT NULL,
    estimated_sped_enrollment integer,
    estimated_gened_enrollment integer,
    estimated_sped_teachers numeric(10,2),
    estimated_gened_teachers numeric(10,2),
    estimation_method character varying(50) NOT NULL,
    confidence character varying(20) NOT NULL,
    notes text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    ratio_state_sped_instructional_per_student numeric(10,6),
    estimated_sped_instructional numeric(10,2),
    ratio_state_self_contained_proportion numeric(10,6),
    estimated_self_contained_sped integer,
    CONSTRAINT chk_sped_confidence CHECK (((confidence)::text = ANY ((ARRAY['high'::character varying, 'medium'::character varying, 'low'::character varying])::text[])))
);


--
-- Name: COLUMN sped_estimates.ratio_state_self_contained_proportion; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sped_estimates.ratio_state_self_contained_proportion IS 'State self-contained proportion used for estimation';


--
-- Name: COLUMN sped_estimates.estimated_self_contained_sped; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sped_estimates.estimated_self_contained_sped IS 'Estimated self-contained SPED students (for LCT calculation)';


--
-- Name: sped_estimates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sped_estimates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sped_estimates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sped_estimates_id_seq OWNED BY public.sped_estimates.id;


--
-- Name: sped_lea_baseline; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sped_lea_baseline (
    lea_id character varying(10) NOT NULL,
    lea_name character varying(255),
    state character varying(2) NOT NULL,
    source_year character varying(10) NOT NULL,
    crdc_sped_enrollment_m integer,
    crdc_sped_enrollment_f integer,
    crdc_sped_enrollment_total integer,
    crdc_total_enrollment_m integer,
    crdc_total_enrollment_f integer,
    crdc_total_enrollment integer,
    ccd_total_enrollment integer,
    ratio_sped_proportion numeric(10,6),
    crdc_source_file character varying(255),
    ccd_source_file character varying(255),
    data_quality_notes text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: sped_state_baseline; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sped_state_baseline (
    state character varying(2) NOT NULL,
    source_year character varying(10) NOT NULL,
    sped_teachers_certified numeric(10,2),
    sped_teachers_not_certified numeric(10,2),
    sped_teachers_total numeric(10,2),
    sped_paraprofessionals_total numeric(10,2),
    sped_students_ages_3_5 integer,
    sped_students_ages_6_21 integer,
    sped_students_total integer,
    ratio_sped_teachers_per_student numeric(10,6),
    personnel_source_file character varying(255),
    child_count_source_file character varying(255),
    data_quality_notes text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    sped_paras_qualified numeric(10,2),
    sped_paras_not_qualified numeric(10,2),
    sped_paras_total numeric(10,2),
    sped_instructional_total numeric(10,2),
    ratio_sped_instructional_per_student numeric(10,6),
    sped_students_self_contained integer,
    sped_students_mainstreamed integer,
    ratio_self_contained_proportion numeric(10,6)
);


--
-- Name: COLUMN sped_state_baseline.sped_students_self_contained; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sped_state_baseline.sped_students_self_contained IS 'Self-contained SPED students: Separate Class + Separate School + <40% in regular class';


--
-- Name: COLUMN sped_state_baseline.sped_students_mainstreamed; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sped_state_baseline.sped_students_mainstreamed IS 'Mainstreamed SPED students: 80%+ and 40-79% in regular class';


--
-- Name: COLUMN sped_state_baseline.ratio_self_contained_proportion; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sped_state_baseline.ratio_self_contained_proportion IS 'Self-Contained / All SPED ratio for LEA estimation';


--
-- Name: staff_counts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_counts (
    id integer NOT NULL,
    district_id character varying(10) NOT NULL,
    source_year character varying(10) NOT NULL,
    data_source character varying(50) NOT NULL,
    source_url text,
    retrieved_at timestamp with time zone DEFAULT now(),
    teachers_total numeric(10,2),
    teachers_elementary numeric(10,2),
    teachers_kindergarten numeric(10,2),
    teachers_secondary numeric(10,2),
    teachers_prek numeric(10,2),
    teachers_ungraded numeric(10,2),
    instructional_coordinators numeric(10,2),
    librarians numeric(10,2),
    library_support numeric(10,2),
    paraprofessionals numeric(10,2),
    counselors_total numeric(10,2),
    counselors_elementary numeric(10,2),
    counselors_secondary numeric(10,2),
    psychologists numeric(10,2),
    student_support_services numeric(10,2),
    lea_administrators numeric(10,2),
    school_administrators numeric(10,2),
    lea_admin_support numeric(10,2),
    school_admin_support numeric(10,2),
    lea_staff_total numeric(10,2),
    school_staff_total numeric(10,2),
    other_staff numeric(10,2),
    all_other_support_staff numeric(10,2),
    teachers_first_year numeric(10,2),
    teachers_second_year numeric(10,2),
    teachers_absent_10plus_days numeric(10,2),
    is_complete boolean DEFAULT true,
    quality_notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE staff_counts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.staff_counts IS 'Historical staff counts by category from all sources. Multiple rows per district (one per source+year).';


--
-- Name: staff_counts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.staff_counts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: staff_counts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.staff_counts_id_seq OWNED BY public.staff_counts.id;


--
-- Name: state_district_crosswalk; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.state_district_crosswalk (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    state character varying(2) NOT NULL,
    state_district_id character varying(20) NOT NULL,
    id_system character varying(50) DEFAULT 'st_leaid'::character varying NOT NULL,
    source character varying(100),
    source_year character varying(10),
    verification_date date,
    confidence character varying(20) DEFAULT 'high'::character varying,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_crosswalk_confidence CHECK (((confidence)::text = ANY ((ARRAY['high'::character varying, 'medium'::character varying, 'low'::character varying])::text[])))
);


--
-- Name: TABLE state_district_crosswalk; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.state_district_crosswalk IS 'Master crosswalk table mapping NCES LEAIDs to state-specific district IDs';


--
-- Name: state_district_crosswalk_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.state_district_crosswalk_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: state_district_crosswalk_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.state_district_crosswalk_id_seq OWNED BY public.state_district_crosswalk.id;


--
-- Name: tx_district_identifiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tx_district_identifiers (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    tea_district_no character varying(6) NOT NULL,
    st_leaid character varying(20) NOT NULL,
    tea_district_type character varying(1),
    tea_district_type_text character varying(100),
    is_charter boolean DEFAULT false,
    charter_type character varying(50),
    county_district_no character varying(10),
    education_service_center integer,
    data_source character varying(50) DEFAULT 'nces_ccd'::character varying,
    source_year character varying(10),
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE tx_district_identifiers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.tx_district_identifiers IS 'Texas Education Agency district identifiers and crosswalk (Layer 2)';


--
-- Name: tx_district_identifiers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tx_district_identifiers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tx_district_identifiers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tx_district_identifiers_id_seq OWNED BY public.tx_district_identifiers.id;


--
-- Name: tx_enrollment_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tx_enrollment_data (
    nces_id character varying(10) NOT NULL,
    tea_district_no character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    total_enrollment integer,
    enrollment_pk integer,
    enrollment_k integer,
    enrollment_g1 integer,
    enrollment_g2 integer,
    enrollment_g3 integer,
    enrollment_g4 integer,
    enrollment_g5 integer,
    enrollment_g6 integer,
    enrollment_g7 integer,
    enrollment_g8 integer,
    enrollment_g9 integer,
    enrollment_g10 integer,
    enrollment_g11 integer,
    enrollment_g12 integer,
    enrollment_sped integer,
    enrollment_ell integer,
    enrollment_econ_disadvantaged integer,
    data_source character varying(50) DEFAULT 'tea_tapr'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE tx_enrollment_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.tx_enrollment_data IS 'Texas enrollment data from TEA TAPR reports';


--
-- Name: tx_sped_district_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tx_sped_district_data (
    id integer NOT NULL,
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    data_source character varying(50) DEFAULT 'peims'::character varying,
    sped_enrollment_total integer,
    disability_categories jsonb,
    settings jsonb,
    confidence character varying(20) DEFAULT 'medium'::character varying,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_tx_sped_confidence CHECK (((confidence)::text = ANY ((ARRAY['high'::character varying, 'medium'::character varying, 'low'::character varying])::text[])))
);


--
-- Name: TABLE tx_sped_district_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.tx_sped_district_data IS 'Texas SPED data from PEIMS (Layer 2, future use)';


--
-- Name: tx_sped_district_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tx_sped_district_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tx_sped_district_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tx_sped_district_data_id_seq OWNED BY public.tx_sped_district_data.id;


--
-- Name: tx_staff_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tx_staff_data (
    nces_id character varying(10) NOT NULL,
    tea_district_no character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    teachers_total_fte numeric(10,2),
    teachers_special_ed_fte numeric(10,2),
    teachers_regular_fte numeric(10,2),
    teachers_bilingual_fte numeric(10,2),
    teachers_gifted_fte numeric(10,2),
    data_source character varying(50) DEFAULT 'tea_tapr'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: TABLE tx_staff_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.tx_staff_data IS 'Texas staff data from TEA TAPR reports';


--
-- Name: v_districts_ready_for_batching; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_districts_ready_for_batching AS
 SELECT eq.id,
    eq.district_id,
    d.name AS district_name,
    d.state,
    d.enrollment,
    eq.current_tier,
    eq.batch_type,
    eq.cms_detected,
    eq.content_type,
    eq.escalation_reason
   FROM (public.enrichment_queue eq
     JOIN public.districts d ON (((eq.district_id)::text = (d.nces_id)::text)))
  WHERE (((eq.status)::text = 'pending'::text) AND (eq.current_tier = ANY (ARRAY[4, 5])))
  ORDER BY eq.current_tier, eq.batch_type, d.state, d.enrollment DESC;


--
-- Name: v_districts_to_skip; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_districts_to_skip AS
 SELECT DISTINCT ea.district_id,
    d.name AS district_name,
    d.state,
    max(ea.attempted_at) AS last_attempt,
    count(*) AS attempt_count,
    string_agg(DISTINCT (ea.block_type)::text, ', '::text) AS block_types,
    bool_or(ea.skip_future_attempts) AS marked_skip
   FROM (public.enrichment_attempts ea
     JOIN public.districts d ON (((ea.district_id)::text = (d.nces_id)::text)))
  WHERE ((ea.skip_future_attempts = true) OR (((ea.status)::text = 'blocked'::text) AND (ea.retry_count >= 2)) OR (((ea.status)::text = 'not_found'::text) AND (ea.retry_count >= 3)))
  GROUP BY ea.district_id, d.name, d.state;


--
-- Name: VIEW v_districts_to_skip; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_districts_to_skip IS 'Districts that should not be attempted again due to blocking or repeated failures';


--
-- Name: v_districts_with_crosswalk; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_districts_with_crosswalk AS
 SELECT d.nces_id,
    d.name,
    d.state,
    d.enrollment,
    d.instructional_staff,
    d.st_leaid,
    c.state_district_id,
    c.id_system,
    c.source,
    c.source_year,
    c.confidence,
    d.year AS nces_year
   FROM (public.districts d
     LEFT JOIN public.state_district_crosswalk c ON ((((d.nces_id)::text = (c.nces_id)::text) AND ((c.id_system)::text = 'st_leaid'::text))));


--
-- Name: VIEW v_districts_with_crosswalk; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_districts_with_crosswalk IS 'Districts with their state crosswalk information';


--
-- Name: v_enrichment_attempt_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_enrichment_attempt_summary AS
 SELECT status,
    block_type,
    count(*) AS attempt_count,
    count(DISTINCT district_id) AS unique_districts,
    avg(timing_ms) AS avg_timing_ms,
    min(attempted_at) AS earliest_attempt,
    max(attempted_at) AS latest_attempt
   FROM public.enrichment_attempts
  GROUP BY status, block_type
  ORDER BY (count(*)) DESC;


--
-- Name: VIEW v_enrichment_attempt_summary; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_enrichment_attempt_summary IS 'Summary statistics of enrichment attempts by status and block type';


--
-- Name: v_enrichment_batch_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_enrichment_batch_summary AS
 SELECT batch_type,
    tier,
    count(*) AS batch_count,
    sum(district_count) AS total_districts,
    sum(success_count) AS total_successes,
    sum(failure_count) AS total_failures,
    round(((100.0 * (sum(success_count))::numeric) / (NULLIF((sum(success_count) + sum(failure_count)), 0))::numeric), 1) AS success_rate_pct,
    ((sum(api_cost_cents))::numeric / 100.0) AS total_cost_dollars,
    sum(api_tokens_used) AS total_tokens
   FROM public.enrichment_batches
  WHERE ((status)::text = 'completed'::text)
  GROUP BY batch_type, tier
  ORDER BY tier, batch_type;


--
-- Name: v_enrichment_queue_status; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_enrichment_queue_status AS
 SELECT status,
    current_tier,
    count(*) AS district_count,
    count(*) FILTER (WHERE (final_success = true)) AS successful,
    count(*) FILTER (WHERE (final_success = false)) AS failed,
    avg(processing_time_seconds) AS avg_processing_time_seconds,
    ((sum(estimated_cost_cents))::numeric / 100.0) AS total_cost_dollars
   FROM public.enrichment_queue
  GROUP BY status, current_tier
  ORDER BY current_tier, status;


--
-- Name: v_enrichment_tier_success; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_enrichment_tier_success AS
 SELECT current_tier,
    count(*) AS attempts,
    count(*) FILTER (WHERE (final_success = true)) AS successes,
    round(((100.0 * (count(*) FILTER (WHERE (final_success = true)))::numeric) / (count(*))::numeric), 1) AS success_rate_pct,
    avg(processing_time_seconds) AS avg_processing_time_seconds,
    ((sum(estimated_cost_cents))::numeric / 100.0) AS total_cost_dollars
   FROM public.enrichment_queue
  WHERE ((status)::text = 'completed'::text)
  GROUP BY current_tier
  ORDER BY current_tier;


--
-- Name: v_florida_districts; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_florida_districts AS
 SELECT d.nces_id,
    d.name AS district_name_nces,
    fl_id.district_name_fldoe,
    fl_id.fldoe_district_no,
    fl_id.county_name,
    fl_id.is_charter,
    d.state,
    d.st_leaid,
    d.year AS nces_year,
    d.enrollment AS nces_enrollment,
    d.total_staff AS nces_staff,
    fl_enr.year AS fldoe_year,
    fl_enr.total_enrollment AS fldoe_enrollment,
    fl_staff.total_instructional_staff AS fldoe_instructional_staff,
    fl_staff.classroom_teachers AS fldoe_classroom_teachers,
    fl_staff.ese_teachers AS fldoe_ese_teachers
   FROM (((public.districts d
     LEFT JOIN public.fl_district_identifiers fl_id ON (((d.nces_id)::text = (fl_id.nces_id)::text)))
     LEFT JOIN public.fl_enrollment_data fl_enr ON (((d.nces_id)::text = (fl_enr.nces_id)::text)))
     LEFT JOIN public.fl_staff_data fl_staff ON (((d.nces_id)::text = (fl_staff.nces_id)::text)))
  WHERE (d.state = 'FL'::bpchar);


--
-- Name: v_lct_temporal_validation; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_lct_temporal_validation AS
 SELECT lc.id,
    lc.district_id,
    d.name AS district_name,
    d.state,
    lc.year AS target_year,
    lc.enrollment_source_year,
    lc.staff_source_year,
    lc.bell_schedule_source_year,
    lc.year_span,
    lc.within_3year_window,
    lc.temporal_flags,
    lc.lct_value,
    lc.staff_scope,
        CASE
            WHEN (lc.year_span IS NULL) THEN 'UNKNOWN'::text
            WHEN (lc.year_span = 0) THEN 'SAME_YEAR'::text
            WHEN (lc.year_span <= 3) THEN 'VALID_BLEND'::text
            ELSE 'SPAN_EXCEEDED'::text
        END AS temporal_status
   FROM (public.lct_calculations lc
     LEFT JOIN public.districts d ON (((lc.district_id)::text = (d.nces_id)::text)));


--
-- Name: VIEW v_lct_temporal_validation; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_lct_temporal_validation IS 'LCT calculations with temporal validation status';


--
-- Name: v_recent_blocks; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_recent_blocks AS
 SELECT ea.attempted_at,
    ea.district_id,
    d.name AS district_name,
    d.state,
    ea.url,
    ea.block_type,
    ea.http_status_code,
    ea.retry_count
   FROM (public.enrichment_attempts ea
     JOIN public.districts d ON (((ea.district_id)::text = (d.nces_id)::text)))
  WHERE (((ea.status)::text = 'blocked'::text) AND (ea.attempted_at > (CURRENT_TIMESTAMP - '30 days'::interval)))
  ORDER BY ea.attempted_at DESC;


--
-- Name: VIEW v_recent_blocks; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_recent_blocks IS 'Security blocks detected in last 30 days';


--
-- Name: v_texas_districts; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_texas_districts AS
 SELECT d.nces_id,
    d.name AS district_name,
    d.state,
    d.st_leaid,
    tx.tea_district_no,
    tx.tea_district_type,
    tx.tea_district_type_text,
    tx.is_charter,
    tx.charter_type,
    tx.education_service_center,
    d.enrollment,
    d.total_staff,
    d.year
   FROM (public.districts d
     LEFT JOIN public.tx_district_identifiers tx ON (((d.nces_id)::text = (tx.nces_id)::text)))
  WHERE (d.state = 'TX'::bpchar);


--
-- Name: VIEW v_texas_districts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_texas_districts IS 'Consolidated view of Texas districts with TEA identifiers';


--
-- Name: va_district_identifiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.va_district_identifiers (
    nces_id character varying(10) NOT NULL,
    vdoe_division_number character varying(10) NOT NULL,
    division_name_vdoe character varying(255),
    source_year character varying(10),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: va_enrollment_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.va_enrollment_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    total_enrollment numeric(10,2),
    full_time_count numeric(10,2),
    part_time_count numeric(10,2),
    data_source character varying(50) DEFAULT 'vdoe_fall_membership'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: va_special_ed_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.va_special_ed_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    sped_enrollment integer,
    data_source character varying(50) DEFAULT 'vdoe_special_ed'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: va_staff_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.va_staff_data (
    nces_id character varying(10) NOT NULL,
    year character varying(10) NOT NULL,
    teachers_fte numeric(10,2),
    administration_fte numeric(10,2),
    aides_paraprofessionals_fte numeric(10,2),
    non_instructional_fte numeric(10,2),
    data_source character varying(50) DEFAULT 'vdoe_staffing'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: bell_schedules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bell_schedules ALTER COLUMN id SET DEFAULT nextval('public.bell_schedules_id_seq'::regclass);


--
-- Name: ca_lcff_funding id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_lcff_funding ALTER COLUMN id SET DEFAULT nextval('public.ca_lcff_funding_id_seq'::regclass);


--
-- Name: ca_sped_district_environments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_sped_district_environments ALTER COLUMN id SET DEFAULT nextval('public.ca_sped_district_environments_id_seq'::regclass);


--
-- Name: data_lineage id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_lineage ALTER COLUMN id SET DEFAULT nextval('public.data_lineage_id_seq'::regclass);


--
-- Name: data_source_registry id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_source_registry ALTER COLUMN id SET DEFAULT nextval('public.data_source_registry_id_seq'::regclass);


--
-- Name: district_funding id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.district_funding ALTER COLUMN id SET DEFAULT nextval('public.district_funding_id_seq'::regclass);


--
-- Name: district_socioeconomic id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.district_socioeconomic ALTER COLUMN id SET DEFAULT nextval('public.district_socioeconomic_id_seq'::regclass);


--
-- Name: enrichment_attempts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrichment_attempts ALTER COLUMN id SET DEFAULT nextval('public.enrichment_attempts_id_seq'::regclass);


--
-- Name: enrichment_batches id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrichment_batches ALTER COLUMN id SET DEFAULT nextval('public.enrichment_batches_id_seq'::regclass);


--
-- Name: enrichment_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrichment_queue ALTER COLUMN id SET DEFAULT nextval('public.enrichment_queue_id_seq'::regclass);


--
-- Name: enrollment_by_grade id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollment_by_grade ALTER COLUMN id SET DEFAULT nextval('public.enrollment_by_grade_id_seq'::regclass);


--
-- Name: fl_district_identifiers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_district_identifiers ALTER COLUMN id SET DEFAULT nextval('public.fl_district_identifiers_id_seq'::regclass);


--
-- Name: fl_enrollment_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_enrollment_data ALTER COLUMN id SET DEFAULT nextval('public.fl_enrollment_data_id_seq'::regclass);


--
-- Name: fl_staff_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_staff_data ALTER COLUMN id SET DEFAULT nextval('public.fl_staff_data_id_seq'::regclass);


--
-- Name: lct_calculations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lct_calculations ALTER COLUMN id SET DEFAULT nextval('public.lct_calculations_id_seq'::regclass);


--
-- Name: school_schedules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_schedules ALTER COLUMN id SET DEFAULT nextval('public.school_schedules_id_seq'::regclass);


--
-- Name: sped_estimates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sped_estimates ALTER COLUMN id SET DEFAULT nextval('public.sped_estimates_id_seq'::regclass);


--
-- Name: staff_counts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_counts ALTER COLUMN id SET DEFAULT nextval('public.staff_counts_id_seq'::regclass);


--
-- Name: state_district_crosswalk id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_district_crosswalk ALTER COLUMN id SET DEFAULT nextval('public.state_district_crosswalk_id_seq'::regclass);


--
-- Name: tx_district_identifiers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_district_identifiers ALTER COLUMN id SET DEFAULT nextval('public.tx_district_identifiers_id_seq'::regclass);


--
-- Name: tx_sped_district_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_sped_district_data ALTER COLUMN id SET DEFAULT nextval('public.tx_sped_district_data_id_seq'::regclass);


--
-- Name: bell_schedules bell_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bell_schedules
    ADD CONSTRAINT bell_schedules_pkey PRIMARY KEY (id);


--
-- Name: ca_enrollment_data ca_enrollment_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_enrollment_data
    ADD CONSTRAINT ca_enrollment_data_pkey PRIMARY KEY (nces_id, year);


--
-- Name: ca_lcff_funding ca_lcff_funding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_lcff_funding
    ADD CONSTRAINT ca_lcff_funding_pkey PRIMARY KEY (id);


--
-- Name: ca_sped_district_environments ca_sped_district_environments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_sped_district_environments
    ADD CONSTRAINT ca_sped_district_environments_pkey PRIMARY KEY (id);


--
-- Name: ca_staff_data ca_staff_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_staff_data
    ADD CONSTRAINT ca_staff_data_pkey PRIMARY KEY (nces_id, year);


--
-- Name: calculation_runs calculation_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calculation_runs
    ADD CONSTRAINT calculation_runs_pkey PRIMARY KEY (run_id);


--
-- Name: data_lineage data_lineage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_lineage
    ADD CONSTRAINT data_lineage_pkey PRIMARY KEY (id);


--
-- Name: data_source_registry data_source_registry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_source_registry
    ADD CONSTRAINT data_source_registry_pkey PRIMARY KEY (id);


--
-- Name: data_source_registry data_source_registry_source_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_source_registry
    ADD CONSTRAINT data_source_registry_source_code_key UNIQUE (source_code);


--
-- Name: district_funding district_funding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.district_funding
    ADD CONSTRAINT district_funding_pkey PRIMARY KEY (id);


--
-- Name: district_socioeconomic district_socioeconomic_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.district_socioeconomic
    ADD CONSTRAINT district_socioeconomic_pkey PRIMARY KEY (id);


--
-- Name: districts districts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.districts
    ADD CONSTRAINT districts_pkey PRIMARY KEY (nces_id);


--
-- Name: enrichment_attempts enrichment_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrichment_attempts
    ADD CONSTRAINT enrichment_attempts_pkey PRIMARY KEY (id);


--
-- Name: enrichment_batches enrichment_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrichment_batches
    ADD CONSTRAINT enrichment_batches_pkey PRIMARY KEY (id);


--
-- Name: enrichment_queue enrichment_queue_district_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrichment_queue
    ADD CONSTRAINT enrichment_queue_district_id_key UNIQUE (district_id);


--
-- Name: enrichment_queue enrichment_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrichment_queue
    ADD CONSTRAINT enrichment_queue_pkey PRIMARY KEY (id);


--
-- Name: enrollment_by_grade enrollment_by_grade_district_id_source_year_data_source_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollment_by_grade
    ADD CONSTRAINT enrollment_by_grade_district_id_source_year_data_source_key UNIQUE (district_id, source_year, data_source);


--
-- Name: enrollment_by_grade enrollment_by_grade_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollment_by_grade
    ADD CONSTRAINT enrollment_by_grade_pkey PRIMARY KEY (id);


--
-- Name: fl_district_identifiers fl_district_identifiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_district_identifiers
    ADD CONSTRAINT fl_district_identifiers_pkey PRIMARY KEY (id);


--
-- Name: fl_enrollment_data fl_enrollment_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_enrollment_data
    ADD CONSTRAINT fl_enrollment_data_pkey PRIMARY KEY (id);


--
-- Name: fl_staff_data fl_staff_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_staff_data
    ADD CONSTRAINT fl_staff_data_pkey PRIMARY KEY (id);


--
-- Name: il_district_identifiers il_district_identifiers_isbe_rcdts_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.il_district_identifiers
    ADD CONSTRAINT il_district_identifiers_isbe_rcdts_key UNIQUE (isbe_rcdts);


--
-- Name: il_district_identifiers il_district_identifiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.il_district_identifiers
    ADD CONSTRAINT il_district_identifiers_pkey PRIMARY KEY (nces_id);


--
-- Name: il_enrollment_data il_enrollment_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.il_enrollment_data
    ADD CONSTRAINT il_enrollment_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: il_staff_data il_staff_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.il_staff_data
    ADD CONSTRAINT il_staff_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: lct_calculations lct_calculations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lct_calculations
    ADD CONSTRAINT lct_calculations_pkey PRIMARY KEY (id);


--
-- Name: ma_district_identifiers ma_district_identifiers_dese_district_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ma_district_identifiers
    ADD CONSTRAINT ma_district_identifiers_dese_district_code_key UNIQUE (dese_district_code);


--
-- Name: ma_district_identifiers ma_district_identifiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ma_district_identifiers
    ADD CONSTRAINT ma_district_identifiers_pkey PRIMARY KEY (nces_id);


--
-- Name: ma_enrollment_data ma_enrollment_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ma_enrollment_data
    ADD CONSTRAINT ma_enrollment_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: ma_staff_data ma_staff_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ma_staff_data
    ADD CONSTRAINT ma_staff_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: mi_district_identifiers mi_district_identifiers_mde_district_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mi_district_identifiers
    ADD CONSTRAINT mi_district_identifiers_mde_district_code_key UNIQUE (mde_district_code);


--
-- Name: mi_district_identifiers mi_district_identifiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mi_district_identifiers
    ADD CONSTRAINT mi_district_identifiers_pkey PRIMARY KEY (nces_id);


--
-- Name: mi_enrollment_data mi_enrollment_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mi_enrollment_data
    ADD CONSTRAINT mi_enrollment_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: mi_special_ed_data mi_special_ed_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mi_special_ed_data
    ADD CONSTRAINT mi_special_ed_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: mi_staff_data mi_staff_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mi_staff_data
    ADD CONSTRAINT mi_staff_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: ny_district_identifiers ny_district_identifiers_nysed_district_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ny_district_identifiers
    ADD CONSTRAINT ny_district_identifiers_nysed_district_id_key UNIQUE (nysed_district_id);


--
-- Name: ny_district_identifiers ny_district_identifiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ny_district_identifiers
    ADD CONSTRAINT ny_district_identifiers_pkey PRIMARY KEY (nces_id);


--
-- Name: ny_enrollment_data ny_enrollment_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ny_enrollment_data
    ADD CONSTRAINT ny_enrollment_data_pkey PRIMARY KEY (nces_id, year, subgroup, data_source);


--
-- Name: ny_staff_data ny_staff_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ny_staff_data
    ADD CONSTRAINT ny_staff_data_pkey PRIMARY KEY (nces_id, year, staff_category, data_source);


--
-- Name: pa_district_identifiers pa_district_identifiers_pde_aun_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pa_district_identifiers
    ADD CONSTRAINT pa_district_identifiers_pde_aun_key UNIQUE (pde_aun);


--
-- Name: pa_district_identifiers pa_district_identifiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pa_district_identifiers
    ADD CONSTRAINT pa_district_identifiers_pkey PRIMARY KEY (nces_id);


--
-- Name: pa_enrollment_data pa_enrollment_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pa_enrollment_data
    ADD CONSTRAINT pa_enrollment_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: pa_staff_data pa_staff_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pa_staff_data
    ADD CONSTRAINT pa_staff_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: school_schedules school_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_schedules
    ADD CONSTRAINT school_schedules_pkey PRIMARY KEY (id);


--
-- Name: sped_estimates sped_estimates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sped_estimates
    ADD CONSTRAINT sped_estimates_pkey PRIMARY KEY (id);


--
-- Name: sped_lea_baseline sped_lea_baseline_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sped_lea_baseline
    ADD CONSTRAINT sped_lea_baseline_pkey PRIMARY KEY (lea_id);


--
-- Name: sped_state_baseline sped_state_baseline_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sped_state_baseline
    ADD CONSTRAINT sped_state_baseline_pkey PRIMARY KEY (state);


--
-- Name: staff_counts staff_counts_district_id_source_year_data_source_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_counts
    ADD CONSTRAINT staff_counts_district_id_source_year_data_source_key UNIQUE (district_id, source_year, data_source);


--
-- Name: staff_counts_effective staff_counts_effective_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_counts_effective
    ADD CONSTRAINT staff_counts_effective_pkey PRIMARY KEY (district_id, effective_year);


--
-- Name: staff_counts staff_counts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_counts
    ADD CONSTRAINT staff_counts_pkey PRIMARY KEY (id);


--
-- Name: state_district_crosswalk state_district_crosswalk_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_district_crosswalk
    ADD CONSTRAINT state_district_crosswalk_pkey PRIMARY KEY (id);


--
-- Name: state_requirements state_requirements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_requirements
    ADD CONSTRAINT state_requirements_pkey PRIMARY KEY (state);


--
-- Name: tx_district_identifiers tx_district_identifiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_district_identifiers
    ADD CONSTRAINT tx_district_identifiers_pkey PRIMARY KEY (id);


--
-- Name: tx_enrollment_data tx_enrollment_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_enrollment_data
    ADD CONSTRAINT tx_enrollment_data_pkey PRIMARY KEY (nces_id, year);


--
-- Name: tx_sped_district_data tx_sped_district_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_sped_district_data
    ADD CONSTRAINT tx_sped_district_data_pkey PRIMARY KEY (id);


--
-- Name: tx_staff_data tx_staff_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_staff_data
    ADD CONSTRAINT tx_staff_data_pkey PRIMARY KEY (nces_id, year);


--
-- Name: bell_schedules uq_bell_schedule; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bell_schedules
    ADD CONSTRAINT uq_bell_schedule UNIQUE (district_id, year, grade_level);


--
-- Name: ca_lcff_funding uq_ca_lcff_funding; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_lcff_funding
    ADD CONSTRAINT uq_ca_lcff_funding UNIQUE (nces_id, year);


--
-- Name: ca_sped_district_environments uq_ca_sped_environment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_sped_district_environments
    ADD CONSTRAINT uq_ca_sped_environment UNIQUE (nces_id, year);


--
-- Name: state_district_crosswalk uq_crosswalk_nces_system; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_district_crosswalk
    ADD CONSTRAINT uq_crosswalk_nces_system UNIQUE (nces_id, id_system);


--
-- Name: state_district_crosswalk uq_crosswalk_state_id_system; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_district_crosswalk
    ADD CONSTRAINT uq_crosswalk_state_id_system UNIQUE (state, state_district_id, id_system);


--
-- Name: district_funding uq_district_funding; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.district_funding
    ADD CONSTRAINT uq_district_funding UNIQUE (nces_id, year, data_source);


--
-- Name: district_socioeconomic uq_district_socioeconomic; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.district_socioeconomic
    ADD CONSTRAINT uq_district_socioeconomic UNIQUE (nces_id, year, poverty_indicator_type, data_source);


--
-- Name: fl_enrollment_data uq_fl_enrollment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_enrollment_data
    ADD CONSTRAINT uq_fl_enrollment UNIQUE (nces_id, year, data_source);


--
-- Name: fl_district_identifiers uq_fl_fldoe_district_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_district_identifiers
    ADD CONSTRAINT uq_fl_fldoe_district_no UNIQUE (fldoe_district_no);


--
-- Name: fl_district_identifiers uq_fl_nces_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_district_identifiers
    ADD CONSTRAINT uq_fl_nces_id UNIQUE (nces_id);


--
-- Name: fl_staff_data uq_fl_staff; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_staff_data
    ADD CONSTRAINT uq_fl_staff UNIQUE (nces_id, year, data_source);


--
-- Name: lct_calculations uq_lct_calculation_v2; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lct_calculations
    ADD CONSTRAINT uq_lct_calculation_v2 UNIQUE (district_id, year, grade_level, staff_scope);


--
-- Name: sped_estimates uq_sped_estimate; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sped_estimates
    ADD CONSTRAINT uq_sped_estimate UNIQUE (district_id, estimate_year);


--
-- Name: tx_district_identifiers uq_tx_nces_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_district_identifiers
    ADD CONSTRAINT uq_tx_nces_id UNIQUE (nces_id);


--
-- Name: tx_sped_district_data uq_tx_sped; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_sped_district_data
    ADD CONSTRAINT uq_tx_sped UNIQUE (nces_id, year, data_source);


--
-- Name: tx_district_identifiers uq_tx_st_leaid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_district_identifiers
    ADD CONSTRAINT uq_tx_st_leaid UNIQUE (st_leaid);


--
-- Name: tx_district_identifiers uq_tx_tea_district_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_district_identifiers
    ADD CONSTRAINT uq_tx_tea_district_no UNIQUE (tea_district_no);


--
-- Name: va_district_identifiers va_district_identifiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.va_district_identifiers
    ADD CONSTRAINT va_district_identifiers_pkey PRIMARY KEY (nces_id);


--
-- Name: va_district_identifiers va_district_identifiers_vdoe_division_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.va_district_identifiers
    ADD CONSTRAINT va_district_identifiers_vdoe_division_number_key UNIQUE (vdoe_division_number);


--
-- Name: va_enrollment_data va_enrollment_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.va_enrollment_data
    ADD CONSTRAINT va_enrollment_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: va_special_ed_data va_special_ed_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.va_special_ed_data
    ADD CONSTRAINT va_special_ed_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: va_staff_data va_staff_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.va_staff_data
    ADD CONSTRAINT va_staff_data_pkey PRIMARY KEY (nces_id, year, data_source);


--
-- Name: idx_bell_schedules_confidence; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bell_schedules_confidence ON public.bell_schedules USING btree (confidence);


--
-- Name: idx_bell_schedules_district; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bell_schedules_district ON public.bell_schedules USING btree (district_id);


--
-- Name: idx_bell_schedules_district_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bell_schedules_district_year ON public.bell_schedules USING btree (district_id, year);


--
-- Name: idx_bell_schedules_method; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bell_schedules_method ON public.bell_schedules USING btree (method);


--
-- Name: idx_bell_schedules_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bell_schedules_year ON public.bell_schedules USING btree (year);


--
-- Name: idx_ca_enrollment_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ca_enrollment_year ON public.ca_enrollment_data USING btree (year);


--
-- Name: idx_ca_staff_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ca_staff_year ON public.ca_staff_data USING btree (year);


--
-- Name: idx_districts_enrollment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_districts_enrollment ON public.districts USING btree (enrollment DESC NULLS LAST);


--
-- Name: idx_districts_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_districts_state ON public.districts USING btree (state);


--
-- Name: idx_districts_state_enrollment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_districts_state_enrollment ON public.districts USING btree (state, enrollment DESC NULLS LAST);


--
-- Name: idx_districts_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_districts_year ON public.districts USING btree (year);


--
-- Name: idx_eb_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eb_status ON public.enrichment_batches USING btree (status);


--
-- Name: idx_eb_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eb_tier ON public.enrichment_batches USING btree (tier);


--
-- Name: idx_eb_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eb_type ON public.enrichment_batches USING btree (batch_type);


--
-- Name: idx_enrichment_attempts_block_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrichment_attempts_block_type ON public.enrichment_attempts USING btree (block_type) WHERE (block_type IS NOT NULL);


--
-- Name: idx_enrichment_attempts_district; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrichment_attempts_district ON public.enrichment_attempts USING btree (district_id);


--
-- Name: idx_enrichment_attempts_district_skip; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrichment_attempts_district_skip ON public.enrichment_attempts USING btree (district_id, skip_future_attempts);


--
-- Name: idx_enrichment_attempts_skip; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrichment_attempts_skip ON public.enrichment_attempts USING btree (skip_future_attempts) WHERE (skip_future_attempts = true);


--
-- Name: idx_enrichment_attempts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrichment_attempts_status ON public.enrichment_attempts USING btree (status);


--
-- Name: idx_enrichment_attempts_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrichment_attempts_time ON public.enrichment_attempts USING btree (attempted_at DESC);


--
-- Name: idx_enrichment_queue_security_blocked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrichment_queue_security_blocked ON public.enrichment_queue USING btree (security_blocked) WHERE (security_blocked = true);


--
-- Name: idx_enrollment_by_grade_district; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrollment_by_grade_district ON public.enrollment_by_grade USING btree (district_id);


--
-- Name: idx_eq_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eq_batch ON public.enrichment_queue USING btree (batch_id);


--
-- Name: idx_eq_batch_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eq_batch_type ON public.enrichment_queue USING btree (batch_type);


--
-- Name: idx_eq_cms; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eq_cms ON public.enrichment_queue USING btree (cms_detected);


--
-- Name: idx_eq_queued_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eq_queued_at ON public.enrichment_queue USING btree (queued_at);


--
-- Name: idx_eq_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eq_status ON public.enrichment_queue USING btree (status);


--
-- Name: idx_eq_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_eq_tier ON public.enrichment_queue USING btree (current_tier);


--
-- Name: idx_lct_data_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lct_data_tier ON public.lct_calculations USING btree (data_tier);


--
-- Name: idx_lct_district; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lct_district ON public.lct_calculations USING btree (district_id);


--
-- Name: idx_lct_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lct_run_id ON public.lct_calculations USING btree (run_id);


--
-- Name: idx_lct_staff_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lct_staff_scope ON public.lct_calculations USING btree (staff_scope);


--
-- Name: idx_lct_value; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lct_value ON public.lct_calculations USING btree (lct_value);


--
-- Name: idx_lct_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lct_year ON public.lct_calculations USING btree (year);


--
-- Name: idx_lineage_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lineage_created_at ON public.data_lineage USING btree (created_at);


--
-- Name: idx_lineage_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lineage_entity ON public.data_lineage USING btree (entity_type, entity_id);


--
-- Name: idx_lineage_operation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lineage_operation ON public.data_lineage USING btree (operation);


--
-- Name: idx_mv_districts_lct_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mv_districts_lct_nces_id ON public.mv_districts_with_lct_data USING btree (nces_id);


--
-- Name: idx_mv_districts_lct_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mv_districts_lct_state ON public.mv_districts_with_lct_data USING btree (state);


--
-- Name: idx_mv_state_enrichment_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mv_state_enrichment_state ON public.mv_state_enrichment_progress USING btree (state);


--
-- Name: idx_mv_unenriched_enrollment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mv_unenriched_enrollment ON public.mv_unenriched_districts USING btree (enrollment DESC);


--
-- Name: idx_mv_unenriched_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mv_unenriched_state ON public.mv_unenriched_districts USING btree (state);


--
-- Name: idx_mv_unenriched_state_rank; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mv_unenriched_state_rank ON public.mv_unenriched_districts USING btree (state, state_rank);


--
-- Name: idx_school_schedules_district; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_school_schedules_district ON public.school_schedules USING btree (district_id, grade_level);


--
-- Name: idx_staff_counts_district; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_staff_counts_district ON public.staff_counts USING btree (district_id);


--
-- Name: idx_staff_counts_effective_district; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_staff_counts_effective_district ON public.staff_counts_effective USING btree (district_id);


--
-- Name: idx_staff_counts_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_staff_counts_source ON public.staff_counts USING btree (data_source);


--
-- Name: idx_staff_counts_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_staff_counts_year ON public.staff_counts USING btree (source_year);


--
-- Name: idx_tx_enrollment_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tx_enrollment_year ON public.tx_enrollment_data USING btree (year);


--
-- Name: idx_tx_staff_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tx_staff_year ON public.tx_staff_data USING btree (year);


--
-- Name: ix_ca_sped_cds_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ca_sped_cds_code ON public.ca_sped_district_environments USING btree (cds_code);


--
-- Name: ix_ca_sped_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ca_sped_nces_id ON public.ca_sped_district_environments USING btree (nces_id);


--
-- Name: ix_ca_sped_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ca_sped_year ON public.ca_sped_district_environments USING btree (year);


--
-- Name: ix_crosswalk_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crosswalk_nces_id ON public.state_district_crosswalk USING btree (nces_id);


--
-- Name: ix_crosswalk_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crosswalk_state ON public.state_district_crosswalk USING btree (state);


--
-- Name: ix_crosswalk_state_district_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_crosswalk_state_district_id ON public.state_district_crosswalk USING btree (state, state_district_id);


--
-- Name: ix_districts_st_leaid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_districts_st_leaid ON public.districts USING btree (st_leaid) WHERE (st_leaid IS NOT NULL);


--
-- Name: ix_fl_enrollment_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fl_enrollment_nces_id ON public.fl_enrollment_data USING btree (nces_id);


--
-- Name: ix_fl_enrollment_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fl_enrollment_year ON public.fl_enrollment_data USING btree (year);


--
-- Name: ix_fl_fldoe_district_no; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fl_fldoe_district_no ON public.fl_district_identifiers USING btree (fldoe_district_no);


--
-- Name: ix_fl_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fl_nces_id ON public.fl_district_identifiers USING btree (nces_id);


--
-- Name: ix_fl_staff_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fl_staff_nces_id ON public.fl_staff_data USING btree (nces_id);


--
-- Name: ix_fl_staff_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fl_staff_year ON public.fl_staff_data USING btree (year);


--
-- Name: ix_funding_data_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_funding_data_source ON public.district_funding USING btree (data_source);


--
-- Name: ix_funding_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_funding_nces_id ON public.district_funding USING btree (nces_id);


--
-- Name: ix_funding_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_funding_state ON public.district_funding USING btree (state);


--
-- Name: ix_funding_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_funding_year ON public.district_funding USING btree (year);


--
-- Name: ix_lcff_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_lcff_nces_id ON public.ca_lcff_funding USING btree (nces_id);


--
-- Name: ix_lcff_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_lcff_year ON public.ca_lcff_funding USING btree (year);


--
-- Name: ix_socioeconomic_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_socioeconomic_nces_id ON public.district_socioeconomic USING btree (nces_id);


--
-- Name: ix_socioeconomic_poverty_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_socioeconomic_poverty_type ON public.district_socioeconomic USING btree (poverty_indicator_type);


--
-- Name: ix_socioeconomic_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_socioeconomic_state ON public.district_socioeconomic USING btree (state);


--
-- Name: ix_socioeconomic_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_socioeconomic_year ON public.district_socioeconomic USING btree (year);


--
-- Name: ix_tx_district_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tx_district_type ON public.tx_district_identifiers USING btree (tea_district_type);


--
-- Name: ix_tx_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tx_nces_id ON public.tx_district_identifiers USING btree (nces_id);


--
-- Name: ix_tx_sped_nces_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tx_sped_nces_id ON public.tx_sped_district_data USING btree (nces_id);


--
-- Name: ix_tx_sped_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tx_sped_year ON public.tx_sped_district_data USING btree (year);


--
-- Name: ix_tx_st_leaid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tx_st_leaid ON public.tx_district_identifiers USING btree (st_leaid);


--
-- Name: ix_tx_tea_district_no; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tx_tea_district_no ON public.tx_district_identifiers USING btree (tea_district_no);


--
-- Name: lct_calculations trg_lct_temporal_validation; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_lct_temporal_validation BEFORE INSERT OR UPDATE ON public.lct_calculations FOR EACH ROW EXECUTE FUNCTION public.validate_lct_temporal();


--
-- Name: bell_schedules update_bell_schedules_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_bell_schedules_updated_at BEFORE UPDATE ON public.bell_schedules FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: districts update_districts_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_districts_updated_at BEFORE UPDATE ON public.districts FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: state_requirements update_state_requirements_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_state_requirements_updated_at BEFORE UPDATE ON public.state_requirements FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: bell_schedules bell_schedules_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bell_schedules
    ADD CONSTRAINT bell_schedules_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.districts(nces_id);


--
-- Name: ca_enrollment_data ca_enrollment_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_enrollment_data
    ADD CONSTRAINT ca_enrollment_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: ca_lcff_funding ca_lcff_funding_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_lcff_funding
    ADD CONSTRAINT ca_lcff_funding_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: ca_sped_district_environments ca_sped_district_environments_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_sped_district_environments
    ADD CONSTRAINT ca_sped_district_environments_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: ca_staff_data ca_staff_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ca_staff_data
    ADD CONSTRAINT ca_staff_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: district_funding district_funding_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.district_funding
    ADD CONSTRAINT district_funding_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: district_socioeconomic district_socioeconomic_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.district_socioeconomic
    ADD CONSTRAINT district_socioeconomic_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: enrichment_attempts enrichment_attempts_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrichment_attempts
    ADD CONSTRAINT enrichment_attempts_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: enrichment_queue enrichment_queue_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrichment_queue
    ADD CONSTRAINT enrichment_queue_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: enrollment_by_grade enrollment_by_grade_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollment_by_grade
    ADD CONSTRAINT enrollment_by_grade_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: fl_district_identifiers fl_district_identifiers_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_district_identifiers
    ADD CONSTRAINT fl_district_identifiers_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: fl_enrollment_data fl_enrollment_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_enrollment_data
    ADD CONSTRAINT fl_enrollment_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: fl_staff_data fl_staff_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fl_staff_data
    ADD CONSTRAINT fl_staff_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: il_district_identifiers il_district_identifiers_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.il_district_identifiers
    ADD CONSTRAINT il_district_identifiers_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: il_enrollment_data il_enrollment_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.il_enrollment_data
    ADD CONSTRAINT il_enrollment_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: il_staff_data il_staff_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.il_staff_data
    ADD CONSTRAINT il_staff_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: lct_calculations lct_calculations_bell_schedule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lct_calculations
    ADD CONSTRAINT lct_calculations_bell_schedule_id_fkey FOREIGN KEY (bell_schedule_id) REFERENCES public.bell_schedules(id);


--
-- Name: lct_calculations lct_calculations_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lct_calculations
    ADD CONSTRAINT lct_calculations_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: ma_district_identifiers ma_district_identifiers_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ma_district_identifiers
    ADD CONSTRAINT ma_district_identifiers_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: ma_enrollment_data ma_enrollment_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ma_enrollment_data
    ADD CONSTRAINT ma_enrollment_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: ma_staff_data ma_staff_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ma_staff_data
    ADD CONSTRAINT ma_staff_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: mi_district_identifiers mi_district_identifiers_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mi_district_identifiers
    ADD CONSTRAINT mi_district_identifiers_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: mi_enrollment_data mi_enrollment_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mi_enrollment_data
    ADD CONSTRAINT mi_enrollment_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: mi_special_ed_data mi_special_ed_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mi_special_ed_data
    ADD CONSTRAINT mi_special_ed_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: mi_staff_data mi_staff_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mi_staff_data
    ADD CONSTRAINT mi_staff_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: ny_district_identifiers ny_district_identifiers_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ny_district_identifiers
    ADD CONSTRAINT ny_district_identifiers_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: ny_enrollment_data ny_enrollment_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ny_enrollment_data
    ADD CONSTRAINT ny_enrollment_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: ny_staff_data ny_staff_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ny_staff_data
    ADD CONSTRAINT ny_staff_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: pa_district_identifiers pa_district_identifiers_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pa_district_identifiers
    ADD CONSTRAINT pa_district_identifiers_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: pa_enrollment_data pa_enrollment_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pa_enrollment_data
    ADD CONSTRAINT pa_enrollment_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: pa_staff_data pa_staff_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pa_staff_data
    ADD CONSTRAINT pa_staff_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: school_schedules school_schedules_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_schedules
    ADD CONSTRAINT school_schedules_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.districts(nces_id);


--
-- Name: sped_estimates sped_estimates_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sped_estimates
    ADD CONSTRAINT sped_estimates_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: staff_counts staff_counts_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_counts
    ADD CONSTRAINT staff_counts_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: staff_counts_effective staff_counts_effective_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_counts_effective
    ADD CONSTRAINT staff_counts_effective_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: state_district_crosswalk state_district_crosswalk_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_district_crosswalk
    ADD CONSTRAINT state_district_crosswalk_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: tx_district_identifiers tx_district_identifiers_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_district_identifiers
    ADD CONSTRAINT tx_district_identifiers_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: tx_enrollment_data tx_enrollment_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_enrollment_data
    ADD CONSTRAINT tx_enrollment_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: tx_sped_district_data tx_sped_district_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_sped_district_data
    ADD CONSTRAINT tx_sped_district_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id) ON DELETE CASCADE;


--
-- Name: tx_staff_data tx_staff_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tx_staff_data
    ADD CONSTRAINT tx_staff_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: va_district_identifiers va_district_identifiers_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.va_district_identifiers
    ADD CONSTRAINT va_district_identifiers_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: va_enrollment_data va_enrollment_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.va_enrollment_data
    ADD CONSTRAINT va_enrollment_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: va_special_ed_data va_special_ed_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.va_special_ed_data
    ADD CONSTRAINT va_special_ed_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- Name: va_staff_data va_staff_data_nces_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.va_staff_data
    ADD CONSTRAINT va_staff_data_nces_id_fkey FOREIGN KEY (nces_id) REFERENCES public.districts(nces_id);


--
-- PostgreSQL database dump complete
--

\unrestrict CD0bk9qnDbPwTYsFaGLURipdHwhg8t3JS0cKKBXX9Vs8AgqRn46K9NgQzRM8l9Y

