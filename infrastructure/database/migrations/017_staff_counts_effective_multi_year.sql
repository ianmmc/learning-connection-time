-- Migration 017: make staff_counts_effective multi-year (composite PK)
-- Created: 2026-06-22
-- Purpose: staff_counts_effective previously had district_id as its sole PK, so
--          re-running populate_effective_staff_counts() for a new NCES year
--          silently overwrote the prior year's row in place. Districts with a
--          real staff count in one year but a 0/null report in a newer year
--          (238 found on the 2024-25 import) lost good data with no fallback.
--          Composite PK (district_id, effective_year) lets both years coexist;
--          callers select the year explicitly (see calculate_lct_variants.py's
--          get_most_recent_staff, queries.py, merge_sea_precedence.py).

ALTER TABLE staff_counts_effective DROP CONSTRAINT IF EXISTS staff_counts_effective_pkey;

ALTER TABLE staff_counts_effective
    ADD CONSTRAINT staff_counts_effective_pkey PRIMARY KEY (district_id, effective_year);

CREATE INDEX IF NOT EXISTS idx_staff_counts_effective_district
    ON staff_counts_effective(district_id);
