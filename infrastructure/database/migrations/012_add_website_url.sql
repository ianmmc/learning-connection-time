-- Migration 012: Add website_url to districts table
-- Created: 2026-01-23
-- Description: Adds website URL field from NCES CCD data for enrichment pipeline

-- Add website_url column
ALTER TABLE districts ADD COLUMN IF NOT EXISTS website_url VARCHAR(500);

-- Add index for districts with URLs (for enrichment queries)
CREATE INDEX IF NOT EXISTS ix_districts_website_url ON districts(website_url) WHERE website_url IS NOT NULL;

-- Add comment
COMMENT ON COLUMN districts.website_url IS 'Official district website URL from NCES CCD data';
