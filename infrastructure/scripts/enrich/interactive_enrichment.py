#!/usr/bin/env python3
"""
Interactive Bell Schedule Enrichment Tool

Streamlined CLI for efficient bell schedule collection during state campaigns.
Reduces context switching and tool calls by automating common operations.

Features:
- Auto-query next district in state campaign
- Pre-populate search queries
- Single-command data entry
- Auto-commit to database
- Progress tracking

Usage:
    python interactive_enrichment.py --state WI
    python interactive_enrichment.py --state WI --mode state-campaign
    python interactive_enrichment.py --district 5560580

Reference: docs/BELL_SCHEDULE_OPERATIONS_GUIDE.md
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, BellSchedule
from infrastructure.database.queries import (
    get_district_by_id,
    get_next_enrichment_candidates,
    get_state_campaign_progress,
    add_bell_schedule,
    get_enrichment_summary,
)
from infrastructure.database.enrichment_tracking import (
    should_skip_district,
    mark_district_skip,
    get_districts_to_skip,
)


def print_header(text: str):
    """Print formatted header."""
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def print_district_info(district: District, rank: int = 0):
    """Print district information."""
    rank_str = f"[Rank #{rank}] " if rank else ""
    print(f"\n{rank_str}{district.name} ({district.state})")
    print(f"  NCES ID: {district.nces_id}")
    print(f"  Enrollment: {district.enrollment:,}" if district.enrollment else "  Enrollment: N/A")


def generate_search_query(district: District, year: str = "2025-26") -> str:
    """Generate search query for bell schedule."""
    return f'"{district.name}" bell schedule {year}'


def prompt_minutes(prompt: str, default: Optional[int] = None) -> Optional[int]:
    """Prompt for instructional minutes."""
    default_str = f" [{default}]" if default else ""
    while True:
        value = input(f"  {prompt}{default_str}: ").strip()

        if not value:
            return default

        if value.lower() in ('s', 'skip', '-'):
            return None

        if value.lower() in ('b', 'blocked'):
            return -1  # Special marker for blocked

        try:
            minutes = int(value)
            if 100 <= minutes <= 600:
                return minutes
            print("    ⚠ Minutes should be between 100 and 600")
        except ValueError:
            print("    ⚠ Enter a number, 's' to skip, or 'b' for blocked")


def prompt_time(prompt: str) -> Optional[str]:
    """Prompt for time value."""
    value = input(f"  {prompt}: ").strip()
    return value if value else None


def collect_schedule_data(
    district: District,
    year: str = "2025-26",
) -> Optional[Dict]:
    """
    Interactively collect bell schedule data for a district.

    Returns schedule data dict or None if skipped/blocked.
    """
    print(f"\n📋 Collecting schedule data for {district.name}...")
    print(f"   Year: {year}")
    print("   Enter 's' to skip a level, 'b' if blocked by firewall")
    print()

    schedules = {}
    levels = ["elementary", "middle", "high"]

    for level in levels:
        print(f"\n  {level.upper()}:")
        minutes = prompt_minutes("Instructional minutes")

        if minutes == -1:
            # Blocked by firewall
            return {"blocked": True, "district_id": district.nces_id}

        if minutes is None:
            continue

        # Collect additional details
        start_time = prompt_time("Start time (e.g., 8:00 AM)")
        end_time = prompt_time("End time (e.g., 3:00 PM)")

        schedules[level] = {
            "instructional_minutes": minutes,
            "start_time": start_time,
            "end_time": end_time,
        }

    if not schedules:
        print("  ⚠ No data collected")
        return None

    # Prompt for source URL
    print()
    source_url = input("  Source URL (optional): ").strip()

    # Add source to all levels
    if source_url:
        for level in schedules:
            schedules[level]["source_urls"] = [source_url]

    return schedules


def save_schedule(
    session,
    district: District,
    schedules: Dict,
    year: str = "2025-26",
    method: str = "human_provided",
) -> bool:
    """Save collected schedules to database."""
    try:
        for level, data in schedules.items():
            if level == "blocked":
                continue

            add_bell_schedule(
                session,
                district_id=district.nces_id,
                year=year,
                grade_level=level,
                instructional_minutes=data["instructional_minutes"],
                start_time=data.get("start_time"),
                end_time=data.get("end_time"),
                source_urls=data.get("source_urls", []),
                confidence="high",
                method=method,
                created_by="interactive_enrichment",
            )

        session.commit()
        print(f"  ✓ Saved {len(schedules)} schedule(s) to database")
        return True

    except Exception as e:
        session.rollback()
        print(f"  ✗ Error saving: {e}")
        return False


def run_state_campaign(state: str, year: str = "2025-26", target: int = 3):
    """
    Run enrichment campaign for a state.

    Attempts enrichment for top districts until target is reached.
    """
    print_header(f"State Campaign: {state.upper()}")

    with session_scope() as session:
        # Get current progress
        progress = get_state_campaign_progress(session, year)
        state_progress = next(
            (p for p in progress if p["state"] == state.upper()),
            {"enriched": 0, "total_districts": 0}
        )

        current = state_progress["enriched"]
        print(f"Current progress: {current}/{target} districts enriched")

        if current >= target:
            print(f"✓ State campaign already complete!")
            return

        # Get candidates
        candidates = get_next_enrichment_candidates(session, state, year, limit=9)

        if not candidates:
            print("⚠ No candidates found")
            return

        print(f"\nFound {len(candidates)} candidates (ranks 1-9 by enrollment)")

        successful = 0
        skipped_count = 0
        for i, district in enumerate(candidates, 1):
            if current + successful >= target:
                print(f"\n✓ Target reached: {current + successful}/{target}")
                break

            # Check if district should be skipped
            if should_skip_district(session, district.nces_id):
                print(f"\n⚠ Skipping {district.name} - flagged from previous failures")
                skipped_count += 1
                continue

            print_district_info(district, rank=i)
            print(f"\n  Search query: {generate_search_query(district, year)}")

            # Prompt for action
            action = input("\n  [E]nrich, [S]kip, [B]locked, [Q]uit? ").strip().lower()

            if action == 'q':
                print("\nExiting campaign...")
                break

            if action == 'b':
                try:
                    mark_district_skip(session, district.nces_id, 'manual_user_blocked')
                    print("  → Marked as blocked and flagged to skip future attempts")
                except Exception as e:
                    print(f"  ⚠ Failed to mark as blocked: {e}")
                continue

            if action == 's':
                print("  → Skipped")
                continue

            if action == 'e' or action == '':
                schedules = collect_schedule_data(district, year)

                if schedules and not schedules.get("blocked"):
                    if save_schedule(session, district, schedules, year):
                        successful += 1
                        print(f"\n  Progress: {current + successful}/{target}")

        # Final summary
        print_header("Campaign Summary")
        print(f"State: {state.upper()}")
        print(f"Districts enriched this session: {successful}")
        print(f"Total enriched: {current + successful}/{target}")

        if current + successful >= target:
            print("✓ STATE CAMPAIGN COMPLETE")
        else:
            print(f"  Remaining: {target - current - successful}")


def run_single_district(district_id: str, year: str = "2025-26"):
    """Enrich a single district by ID."""
    print_header("Single District Enrichment")

    with session_scope() as session:
        district = get_district_by_id(session, district_id)

        if not district:
            print(f"✗ District {district_id} not found")
            return

        # Check if district should be skipped
        if should_skip_district(session, district.nces_id):
            print(f"\n⚠ WARNING: This district is flagged from previous failures")
            print("  Reason: Security blocks, repeated 404s, or manual flag")
            proceed = input("\n  Proceed anyway? [y/N]: ").strip().lower()
            if proceed != 'y':
                print("  → Skipped")
                return

        print_district_info(district)
        print(f"\nSearch query: {generate_search_query(district, year)}")

        schedules = collect_schedule_data(district, year)

        if schedules and not schedules.get("blocked"):
            save_schedule(session, district, schedules, year)


def show_campaign_status():
    """Show overall campaign status."""
    print_header("Enrichment Campaign Status")

    with session_scope() as session:
        summary = get_enrichment_summary(session, "2024-25")
        progress = get_state_campaign_progress(session, "2024-25")

        print(f"\nTotal enriched districts: {summary['enriched_districts']}")
        print(f"States represented: {summary['states_represented']}")
        print(f"Enrichment rate: {summary['enrichment_rate']:.2f}%")

        # States needing work
        incomplete = [p for p in progress if not p["complete"]]
        complete = [p for p in progress if p["complete"]]

        print(f"\nStates complete (≥3): {len(complete)}")
        print(f"States incomplete: {len(incomplete)}")

        if incomplete:
            print("\nTop 10 incomplete states by enrollment:")
            for p in sorted(incomplete, key=lambda x: -x["total_enrollment"])[:10]:
                print(f"  {p['state']}: {p['enriched']}/3 ({p['total_enrollment']:,} total enrollment)")


def main():
    parser = argparse.ArgumentParser(
        description="Interactive bell schedule enrichment tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run state campaign for Wisconsin
  python interactive_enrichment.py --state WI

  # Enrich a single district
  python interactive_enrichment.py --district 5560580

  # Show campaign status
  python interactive_enrichment.py --status
        """
    )
    parser.add_argument("--state", help="State code for campaign mode")
    parser.add_argument("--district", help="District NCES ID for single enrichment")
    parser.add_argument("--year", default="2025-26", help="School year (default: 2025-26)")
    parser.add_argument("--target", type=int, default=3, help="Target per state (default: 3)")
    parser.add_argument("--status", action="store_true", help="Show campaign status")
    args = parser.parse_args()

    if args.status:
        show_campaign_status()
    elif args.district:
        run_single_district(args.district, args.year)
    elif args.state:
        run_state_campaign(args.state, args.year, args.target)
    else:
        parser.print_help()
        print("\n⚠ Specify --state, --district, or --status")


if __name__ == "__main__":
    main()
