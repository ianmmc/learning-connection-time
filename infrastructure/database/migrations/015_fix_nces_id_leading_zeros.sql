-- Migration 015: Fix NCES ID leading zeros
-- Date: 2026-01-24
-- Purpose: Standardize NCES IDs to 7-digit format with leading zeros
--
-- The NCES standard uses 7-digit LEA IDs. Some IDs were imported without
-- leading zeros (e.g., "100005" instead of "0100005"), causing matching
-- issues with source data.

-- Step 1: Create temporary mapping table
CREATE TEMP TABLE nces_id_mapping AS
SELECT
    nces_id AS old_id,
    LPAD(nces_id, 7, '0') AS new_id
FROM districts
WHERE LENGTH(nces_id) < 7;

-- Check how many will be updated
DO $$
DECLARE
    update_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO update_count FROM nces_id_mapping;
    RAISE NOTICE 'Will update % NCES IDs', update_count;
END $$;

-- Step 2: Update all referencing tables first (in alphabetical order)
-- Using explicit transaction to ensure atomicity

BEGIN;

-- bell_schedules
UPDATE bell_schedules bs
SET district_id = m.new_id
FROM nces_id_mapping m
WHERE bs.district_id = m.old_id;

-- ca_enrollment_data
UPDATE ca_enrollment_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- ca_lcff_funding
UPDATE ca_lcff_funding t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- ca_sped_district_environments
UPDATE ca_sped_district_environments t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- ca_staff_data
UPDATE ca_staff_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- district_funding
UPDATE district_funding t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- district_socioeconomic
UPDATE district_socioeconomic t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- enrichment_attempts
UPDATE enrichment_attempts t
SET district_id = m.new_id
FROM nces_id_mapping m
WHERE t.district_id = m.old_id;

-- enrichment_queue
UPDATE enrichment_queue t
SET district_id = m.new_id
FROM nces_id_mapping m
WHERE t.district_id = m.old_id;

-- enrollment_by_grade
UPDATE enrollment_by_grade t
SET district_id = m.new_id
FROM nces_id_mapping m
WHERE t.district_id = m.old_id;

-- fl_district_identifiers
UPDATE fl_district_identifiers t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- fl_enrollment_data
UPDATE fl_enrollment_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- fl_staff_data
UPDATE fl_staff_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- il_district_identifiers
UPDATE il_district_identifiers t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- il_enrollment_data
UPDATE il_enrollment_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- il_staff_data
UPDATE il_staff_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- lct_calculations
UPDATE lct_calculations t
SET district_id = m.new_id
FROM nces_id_mapping m
WHERE t.district_id = m.old_id;

-- ma_district_identifiers
UPDATE ma_district_identifiers t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- ma_enrollment_data
UPDATE ma_enrollment_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- ma_staff_data
UPDATE ma_staff_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- mi_district_identifiers
UPDATE mi_district_identifiers t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- mi_enrollment_data
UPDATE mi_enrollment_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- mi_special_ed_data
UPDATE mi_special_ed_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- mi_staff_data
UPDATE mi_staff_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- ny_district_identifiers
UPDATE ny_district_identifiers t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- ny_enrollment_data
UPDATE ny_enrollment_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- ny_staff_data
UPDATE ny_staff_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- pa_district_identifiers
UPDATE pa_district_identifiers t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- pa_enrollment_data
UPDATE pa_enrollment_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- pa_staff_data
UPDATE pa_staff_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- sped_estimates
UPDATE sped_estimates t
SET district_id = m.new_id
FROM nces_id_mapping m
WHERE t.district_id = m.old_id;

-- staff_counts
UPDATE staff_counts t
SET district_id = m.new_id
FROM nces_id_mapping m
WHERE t.district_id = m.old_id;

-- staff_counts_effective
UPDATE staff_counts_effective t
SET district_id = m.new_id
FROM nces_id_mapping m
WHERE t.district_id = m.old_id;

-- state_district_crosswalk
UPDATE state_district_crosswalk t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- tx_district_identifiers
UPDATE tx_district_identifiers t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- tx_enrollment_data
UPDATE tx_enrollment_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- tx_sped_district_data
UPDATE tx_sped_district_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- tx_staff_data
UPDATE tx_staff_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- va_district_identifiers
UPDATE va_district_identifiers t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- va_enrollment_data
UPDATE va_enrollment_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- va_special_ed_data
UPDATE va_special_ed_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- va_staff_data
UPDATE va_staff_data t
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE t.nces_id = m.old_id;

-- Step 3: Update the districts table (primary key)
UPDATE districts d
SET nces_id = m.new_id
FROM nces_id_mapping m
WHERE d.nces_id = m.old_id;

COMMIT;

-- Verify the fix
DO $$
DECLARE
    short_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO short_count
    FROM districts
    WHERE LENGTH(nces_id) < 7;

    IF short_count > 0 THEN
        RAISE EXCEPTION 'Migration incomplete: % districts still have short NCES IDs', short_count;
    ELSE
        RAISE NOTICE 'Success: All NCES IDs are now 7 digits';
    END IF;
END $$;
