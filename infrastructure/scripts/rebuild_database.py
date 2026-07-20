#!/usr/bin/env python3
"""
Master Orchestrator: Rebuild Database from Raw Sources

This script performs a complete database rebuild from verified raw data.
It coordinates all import scripts in the correct order with verification gates.

Phases:
1. Reset database (preserve schema)
2. Load foundation tables (state requirements)
3. Load districts from NCES CCD
4. Load staff counts and enrollment
5. Load SPED baseline data
6. Apply SPED estimates
7. Import bell schedules (if available)
8. Calculate LCT variants

Usage:
    python infrastructure/scripts/rebuild_database.py [--phase N] [--skip-reset] [--dry-run]

Options:
    --phase N       Start from phase N (1-8)
    --skip-reset    Skip database reset (for incremental runs)
    --skip-lct      Skip LCT calculation
    --dry-run       Preview without making changes
    --sample N      Limit records for testing

Author: Claude (AI Assistant)
Date: January 24, 2026
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope, get_engine
from infrastructure.database.school_year import NCES_PRIMARY_YEAR
from sqlalchemy import text

# Sanity floor for the Phase-2 checkpoint: the CCD universe under our criteria
# has held ~17.8k LEAs for years. Re-check against the live count when a new
# CCD vintage is ingested (the same data event that bumps NCES_PRIMARY_YEAR) —
# a hardcoded inline literal went stale unnoticed (issue #466).
EXPECTED_MIN_DISTRICTS = 17000


# Script paths (relative to project root)
SCRIPTS = {
    "reset": "infrastructure/scripts/reset_database.py",
    "import_all": "infrastructure/database/migrations/import_all_data.py",
    "import_district_urls": "infrastructure/scripts/import_district_urls.py",
    "apply_ctc": "infrastructure/database/migrations/apply_ctc_classification.py",
    "import_staff_enrollment": "infrastructure/database/migrations/import_staff_and_enrollment.py",
    "import_sped_baseline": "infrastructure/database/migrations/import_sped_baseline.py",
    "apply_sped_estimates": "infrastructure/database/migrations/apply_sped_estimates.py",
    "import_ca_lcff": "infrastructure/database/migrations/import_ca_lcff.py",
    "import_ca_frpm": "infrastructure/database/migrations/import_ca_frpm.py",
    "import_ca_sped": "infrastructure/database/migrations/import_ca_sped.py",
    "import_manual_schedules": "infrastructure/scripts/enrich/import_manual_bell_schedules.py",
    "calculate_lct": "infrastructure/scripts/analyze/calculate_lct_variants.py",
}


def run_script(script_path: str, args: list = None, dry_run: bool = False) -> bool:
    """
    Run a Python script and return success/failure.

    Args:
        script_path: Path to script relative to project root
        args: Additional command line arguments
        dry_run: If True, print command but don't execute

    Returns:
        True if successful, False otherwise
    """
    full_path = project_root / script_path
    cmd = ["python3", str(full_path)]
    if args:
        cmd.extend(args)

    print(f"\n{'DRY RUN: ' if dry_run else ''}Running: {' '.join(cmd)}")

    if dry_run:
        return True

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Error running {script_path}: {e}")
        return False
    except FileNotFoundError:
        print(f"Script not found: {full_path}")
        return False


def verify_table_counts(session, expected: dict = None) -> dict:
    """Get current table counts."""
    tables = [
        "districts", "state_district_crosswalk", "state_requirements",
        "staff_counts", "staff_counts_effective",
        "enrollment_by_grade", "sped_state_baseline", "sped_lea_baseline",
        "sped_estimates", "bell_schedules", "lct_calculations"
    ]

    counts = {}
    for table in tables:
        try:
            result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = result.scalar()
        except Exception:
            counts[table] = "N/A"

    return counts


def print_counts(counts: dict, phase: str = ""):
    """Print table counts in a readable format."""
    print(f"\n{'=' * 50}")
    print(f"DATABASE STATUS{' - After ' + phase if phase else ''}")
    print("=" * 50)
    for table, count in counts.items():
        if isinstance(count, int):
            print(f"  {table}: {count:,}")
        else:
            print(f"  {table}: {count}")


def phase_1_reset(dry_run: bool = False) -> bool:
    """Phase 1: Reset database (preserve schema)."""
    print("\n" + "=" * 60)
    print("PHASE 1: RESET DATABASE")
    print("=" * 60)

    return run_script(SCRIPTS["reset"], ["--force", "--no-backup"], dry_run=dry_run)


def phase_2_foundation(dry_run: bool = False) -> bool:
    """Phase 2: Load foundation tables (state requirements, districts)."""
    print("\n" + "=" * 60)
    print("PHASE 2: LOAD FOUNDATION DATA")
    print("=" * 60)

    # import_all_data handles state requirements, districts, crosswalk
    args = []
    if dry_run:
        args.append("--dry-run")

    if not run_script(SCRIPTS["import_all"], args, dry_run=False):  # Script handles dry-run internally
        return False

    # Verify the crosswalk actually came back (issue #16: TRUNCATE districts CASCADE wipes
    # state_district_crosswalk — "the single source of truth for all state mappings" — and a
    # rebuild that silently skips its re-import must fail loudly here, not months later).
    if not dry_run:
        with session_scope() as session:
            n = session.execute(text("SELECT COUNT(*) FROM state_district_crosswalk")).scalar()
        if not n:
            print("ERROR: state_district_crosswalk is EMPTY after phase 2 — the crosswalk "
                  "re-import did not run. Halting the rebuild (Rule #6: verify, don't trust).")
            return False
        print(f"  Crosswalk verified: {n} entries")

    # Import district website URLs and grade spans from NCES CCD
    print("\nImporting district URLs and grade spans...")
    url_args = []
    if dry_run:
        url_args.append("--dry-run")
    return run_script(SCRIPTS["import_district_urls"], url_args, dry_run=dry_run)


def phase_2b_classifications(dry_run: bool = False, year: str = NCES_PRIMARY_YEAR) -> bool:
    """Phase 2b: Re-apply district classifications lost by the reset.

    apply_ctc_classification sets is_shared_service_entity / is_career_
    technical_center (METHODOLOGY Rule 6 — CTCs are excluded from bell-schedule
    and LCT populations). import_all_data never carries these flags, so a
    rebuild without this phase silently dropped the exclusion (issue #589)."""
    print("\n" + "=" * 60)
    print("PHASE 2b: RE-APPLY DISTRICT CLASSIFICATIONS (Rule 6 CTC)")
    print("=" * 60)

    args = ["--year", year.replace("-", "_")]  # apply_ctc expects the NCES dir form (2024_25)
    if dry_run:
        args.append("--dry-run")
    # Unlike phase_2_foundation's import_all (which handles --dry-run
    # internally and so is called with dry_run=False here), apply_ctc has no
    # internal no-op path other than the --dry-run flag itself — passing
    # dry_run=False through run_script() previously spawned the real
    # subprocess (real CSV read, real DB query) under a top-level --dry-run,
    # unlike every other phase (found in max-effort review). Every other
    # phase's dry_run flows straight through to run_script's own
    # `if dry_run: return True` short-circuit; match that here.
    return run_script(SCRIPTS["apply_ctc"], args, dry_run=dry_run)


def phase_3_staff_enrollment(dry_run: bool = False, year: str = NCES_PRIMARY_YEAR) -> bool:
    """Phase 3: Load staff counts and enrollment."""
    print("\n" + "=" * 60)
    print("PHASE 3: LOAD STAFF COUNTS AND ENROLLMENT")
    print("=" * 60)

    args = ["--year", year]
    return run_script(SCRIPTS["import_staff_enrollment"], args, dry_run=dry_run)


def phase_3b_state_layers(dry_run: bool = False) -> bool:
    """Phase 3b: Re-import the state Phase-2 layers lost by the reset.

    The CA actual-data layer (SPED environments, FRPM, LCFF) feeds the
    documented CA-actual > federal-estimate SPED precedence; the 2026-07
    rebuild dropped these tables because no phase re-imported them
    (issue #594 — sev:critical, the already-fired sibling of #589)."""
    print("\n" + "=" * 60)
    print("PHASE 3b: RE-IMPORT STATE PHASE-2 LAYERS (CA)")
    print("=" * 60)

    for key in ("import_ca_sped", "import_ca_frpm", "import_ca_lcff"):
        if not run_script(SCRIPTS[key], [], dry_run=dry_run):
            return False
    return True


def phase_4_sped_baseline(dry_run: bool = False, sample: int = None) -> bool:
    """Phase 4: Load SPED baseline data."""
    print("\n" + "=" * 60)
    print("PHASE 4: LOAD SPED BASELINE DATA")
    print("=" * 60)

    args = []
    if sample:
        args.extend(["--sample", str(sample)])

    return run_script(SCRIPTS["import_sped_baseline"], args, dry_run=dry_run)


def phase_5_sped_estimates(dry_run: bool = False) -> bool:
    """Phase 5: Apply SPED estimates."""
    print("\n" + "=" * 60)
    print("PHASE 5: APPLY SPED ESTIMATES")
    print("=" * 60)

    # Check if script exists
    script_path = project_root / SCRIPTS["apply_sped_estimates"]
    if not script_path.exists():
        print(f"Script not found: {SCRIPTS['apply_sped_estimates']}")
        print("Skipping SPED estimates (script may need to be created)")
        return True  # Don't fail the whole rebuild

    return run_script(SCRIPTS["apply_sped_estimates"], dry_run=dry_run)


def phase_6_bell_schedules(dry_run: bool = False) -> bool:
    """Phase 6: Import bell schedules."""
    print("\n" + "=" * 60)
    print("PHASE 6: IMPORT BELL SCHEDULES")
    print("=" * 60)

    # Check if script exists
    script_path = project_root / SCRIPTS["import_manual_schedules"]
    if not script_path.exists():
        print(f"Script not found: {SCRIPTS['import_manual_schedules']}")
        print("Skipping manual bell schedule import")
        return True  # Don't fail the whole rebuild

    return run_script(SCRIPTS["import_manual_schedules"], dry_run=dry_run)


def phase_7_calculate_lct(dry_run: bool = False) -> bool:
    """Phase 7: Calculate LCT variants."""
    print("\n" + "=" * 60)
    print("PHASE 7: CALCULATE LCT VARIANTS")
    print("=" * 60)

    return run_script(SCRIPTS["calculate_lct"], dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild database from raw sources"
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3, 4, 5, 6, 7],
        help="Start from specific phase"
    )
    parser.add_argument(
        "--skip-reset",
        action="store_true",
        help="Skip database reset (for incremental runs)"
    )
    parser.add_argument(
        "--skip-lct",
        action="store_true",
        help="Skip LCT calculation"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without making changes"
    )
    parser.add_argument(
        "--sample",
        type=int,
        help="Limit records for testing (affects SPED baseline)"
    )
    parser.add_argument(
        "--year",
        default="2023-24",
        help="School year for staff/enrollment data"
    )

    args = parser.parse_args()

    start_phase = args.phase or 1

    print("=" * 60)
    print("DATABASE REBUILD ORCHESTRATOR")
    print("=" * 60)
    print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"Starting from phase: {start_phase}")
    print(f"Dry run: {args.dry_run}")
    print(f"Skip reset: {args.skip_reset}")
    print(f"Skip LCT: {args.skip_lct}")

    # Show initial state
    with session_scope() as session:
        counts = verify_table_counts(session)
        print_counts(counts, "Initial State")

    success = True
    phases_completed = []

    # Phase 1: Reset
    if start_phase <= 1 and not args.skip_reset:
        if not phase_1_reset(args.dry_run):
            print("\nERROR: Phase 1 (Reset) failed")
            success = False
        else:
            phases_completed.append("1-Reset")

    # Phase 2: Foundation
    if success and start_phase <= 2:
        if not phase_2_foundation(args.dry_run):
            print("\nERROR: Phase 2 (Foundation) failed")
            success = False
        else:
            phases_completed.append("2-Foundation")

            # Verify checkpoint
            if not args.dry_run:
                with session_scope() as session:
                    counts = verify_table_counts(session)
                    if counts.get("districts", 0) < EXPECTED_MIN_DISTRICTS:
                        print(
                            f"\nWARNING: Expected at least {EXPECTED_MIN_DISTRICTS:,} "
                            f"districts, got {counts.get('districts', 0):,}"
                        )
                    print_counts(counts, "Phase 2")

    # Phase 2b: Classifications (Rule-6 CTC flags — issue #589)
    if success and start_phase <= 2:
        if not phase_2b_classifications(args.dry_run, args.year):
            print("\nERROR: Phase 2b (Classifications) failed")
            success = False
        else:
            phases_completed.append("2b-Classifications")

    # Phase 3: Staff/Enrollment
    if success and start_phase <= 3:
        if not phase_3_staff_enrollment(args.dry_run, args.year):
            print("\nERROR: Phase 3 (Staff/Enrollment) failed")
            success = False
        else:
            phases_completed.append("3-Staff/Enrollment")

            # Verify checkpoint
            if not args.dry_run:
                with session_scope() as session:
                    counts = verify_table_counts(session)
                    print_counts(counts, "Phase 3")

    # Phase 3b: State Phase-2 layers (CA actual data — issue #594)
    if success and start_phase <= 3:
        if not phase_3b_state_layers(args.dry_run):
            print("\nERROR: Phase 3b (State layers) failed")
            success = False
        else:
            phases_completed.append("3b-StateLayers")

    # Phase 4: SPED Baseline
    if success and start_phase <= 4:
        if not phase_4_sped_baseline(args.dry_run, args.sample):
            print("\nERROR: Phase 4 (SPED Baseline) failed")
            success = False
        else:
            phases_completed.append("4-SPED Baseline")

            # Verify checkpoint
            if not args.dry_run:
                with session_scope() as session:
                    counts = verify_table_counts(session)
                    print_counts(counts, "Phase 4")

    # Phase 5: SPED Estimates
    if success and start_phase <= 5:
        if not phase_5_sped_estimates(args.dry_run):
            print("\nERROR: Phase 5 (SPED Estimates) failed")
            success = False
        else:
            phases_completed.append("5-SPED Estimates")

            # Verify checkpoint
            if not args.dry_run:
                with session_scope() as session:
                    counts = verify_table_counts(session)
                    print_counts(counts, "Phase 5")

    # Phase 6: Bell Schedules
    if success and start_phase <= 6:
        if not phase_6_bell_schedules(args.dry_run):
            print("\nERROR: Phase 6 (Bell Schedules) failed")
            success = False
        else:
            phases_completed.append("6-Bell Schedules")

            # Verify checkpoint
            if not args.dry_run:
                with session_scope() as session:
                    counts = verify_table_counts(session)
                    print_counts(counts, "Phase 6")

    # Phase 7: Calculate LCT
    if success and start_phase <= 7 and not args.skip_lct:
        if not phase_7_calculate_lct(args.dry_run):
            print("\nERROR: Phase 7 (LCT Calculation) failed")
            success = False
        else:
            phases_completed.append("7-LCT Calculation")

    # Final summary
    print("\n" + "=" * 60)
    print("REBUILD SUMMARY")
    print("=" * 60)
    print(f"Completed: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"Phases completed: {', '.join(phases_completed) if phases_completed else 'None'}")
    print(f"Status: {'SUCCESS' if success else 'FAILED'}")

    if not args.dry_run:
        with session_scope() as session:
            counts = verify_table_counts(session)
            print_counts(counts, "Final State")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
