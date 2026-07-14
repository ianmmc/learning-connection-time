"""Compatibility shim — the school-year vocabulary moved to `infrastructure.utilities.school_year`
(2026-07-14) so the acquisition pipeline can import it without breaching the acquisition↛database
import contract (pyproject `[tool.importlinter]`): it is calendar vocabulary, not database access.
Existing LCT-layer imports keep working through this re-export; new code should import from
`infrastructure.utilities.school_year` directly.
"""
from infrastructure.utilities.school_year import (  # noqa: F401
    ACCEPTABLE_BELL_YEARS,
    COVID_EXCLUDED_YEARS,
    CURRENT_SCHOOL_YEAR,
    DB_CHECK_MINUTES_MAX,
    DB_CHECK_MINUTES_MIN,
    GROSS_MINUTES_MAX,
    GROSS_MINUTES_MIN,
    MAX_BLEND_SPAN,
    NCES_PRIMARY_YEAR,
    PRE_COVID_FALLBACK_YEAR,
    SPED_BASELINE_YEAR,
    current_school_year,
    is_acceptable_data_year,
    is_covid_year,
    plausible_gross_minutes,
    start_year,
    within_blend_window,
    year_span,
)
