-- Migration: Add all_other_support_staff to staff_counts_effective
-- Date: July 20, 2026
-- Purpose: issue #407 — the CCD "All Other Support Staff" category existed on
-- staff_counts but had no column on staff_counts_effective, so the copy in
-- import_staff_and_enrollment.py could not carry it and calculate_scopes()'s
-- scope_all silently undercounted every district's 'all' LCT scope.
-- The column is backfilled from staff_counts by (district_id, source_year),
-- and scope_all is recomputed in the same statement set. NULL semantics match
-- the rest of the effective table (None = not reported, distinguishable from 0).

ALTER TABLE staff_counts_effective
ADD COLUMN IF NOT EXISTS all_other_support_staff NUMERIC(10, 2);

COMMENT ON COLUMN staff_counts_effective.all_other_support_staff IS
'CCD "All Other Support Staff" FTE — carried from staff_counts (issue #407); included in scope_all';

-- Backfill from the raw table for the matching vintage
UPDATE staff_counts_effective e
SET all_other_support_staff = sc.all_other_support_staff
FROM staff_counts sc
WHERE sc.district_id = e.district_id
  AND sc.source_year = e.effective_year
  AND e.all_other_support_staff IS DISTINCT FROM sc.all_other_support_staff;

-- Recompute scope_all to include the new category. Mirrors
-- StaffCountsEffective.calculate_scopes(): a reported 0 stays 0, an
-- all-missing set stays NULL (issue #65 semantics) — since scope_all was
-- already non-NULL wherever any component existed, adding one more COALESCE
-- term preserves that.
UPDATE staff_counts_effective
SET scope_all = (
    SELECT CASE WHEN COUNT(v) = 0 THEN NULL ELSE SUM(v) END
    FROM unnest(ARRAY[
        teachers_elementary, teachers_secondary, teachers_kindergarten,
        teachers_ungraded, instructional_coordinators, librarians,
        library_support, paraprofessionals, counselors_total, psychologists,
        student_support_services, lea_administrators, school_administrators,
        lea_admin_support, school_admin_support, other_staff,
        all_other_support_staff
    ]) AS v
    WHERE v IS NOT NULL
);
