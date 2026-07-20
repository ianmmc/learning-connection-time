-- Migration: scope_all recompute, NaN-safe
-- Date: July 20, 2026
-- Purpose: 023's scope_all recompute summed component columns filtering only
-- NULL — but several component columns carry literal numeric 'NaN' values
-- (written by pre-safe_sum-era imports; the Python calculate_scopes() filters
-- them with math.isnan, which is why Python-written scope_all was clean).
-- 15,265 rows got a NaN scope_all from 023. Recompute excluding NaN, matching
-- calculate_scopes() semantics exactly: skip NULL and NaN; all-missing -> NULL.

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
    WHERE v IS NOT NULL AND v <> 'NaN'::numeric
);
