#!/usr/bin/env python3
"""
create_ground_truth.py - Interactive helper for creating ground truth files

PURPOSE:
    Walks the user through each district's text files and prompts for manual
    transcription of bell schedule data. Writes properly formatted ground_truth.json
    files co-located with the source data.

CONTEXT:
    Part of Phase 10: Model Benchmark. Ground truth files are used by
    run_benchmark.py and score_extraction.py to evaluate model accuracy.

USAGE:
    # Create ground truth for a specific district
    python infrastructure/scripts/benchmark/create_ground_truth.py --district 4659820

    # Create ground truth for all districts with txt files
    python infrastructure/scripts/benchmark/create_ground_truth.py --all

    # List available districts
    python infrastructure/scripts/benchmark/create_ground_truth.py --list
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PDF_BASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "raw" / "bell_schedule_pdfs"


def find_district_dir(district_id: str) -> Path | None:
    """Find district directory by ID prefix."""
    for state_dir in sorted(PDF_BASE_DIR.iterdir()):
        if not state_dir.is_dir():
            continue
        for district_dir in sorted(state_dir.iterdir()):
            if district_dir.name.startswith(district_id):
                return district_dir
    return None


def find_all_districts_with_txt() -> list[Path]:
    """Find all district directories that have .txt files ready."""
    districts = []
    for state_dir in sorted(PDF_BASE_DIR.iterdir()):
        if not state_dir.is_dir():
            continue
        for district_dir in sorted(state_dir.iterdir()):
            if not district_dir.is_dir():
                continue
            txt_files = list(district_dir.rglob("active/**/*.txt"))
            if txt_files:
                districts.append(district_dir)
    return districts


def get_txt_files(district_dir: Path) -> list[Path]:
    """Get all .txt files from active/ and active/converted/ subdirs."""
    txt_files = []
    active_dir = district_dir / "active"
    if active_dir.exists():
        txt_files.extend(sorted(active_dir.rglob("*.txt")))
    return txt_files


def load_metadata(district_dir: Path) -> dict:
    """Load metadata.json if it exists."""
    meta_path = district_dir / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            return json.load(f)
    return {}


def print_separator():
    print("\n" + "=" * 80 + "\n")


def display_txt_file(filepath: Path, max_lines: int = 100):
    """Display a text file with line numbers."""
    try:
        text = filepath.read_text(errors="replace")
        lines = text.split("\n")
        print(f"\n--- {filepath.name} ({len(lines)} lines) ---")
        for i, line in enumerate(lines[:max_lines], 1):
            print(f"  {i:4d} | {line}")
        if len(lines) > max_lines:
            print(f"  ... ({len(lines) - max_lines} more lines)")
        print()
    except Exception as e:
        print(f"  Error reading file: {e}")


def prompt_schedule() -> dict | None:
    """Prompt user for a single schedule entry."""
    print("  Enter schedule data (or 'done' to finish, 'skip' to skip this file):")

    grade = input("  Grade level (elementary/middle/high/skip/done): ").strip().lower()
    if grade in ("done", "skip", ""):
        return grade if grade else "done"

    if grade not in ("elementary", "middle", "high"):
        print(f"  Invalid grade level: {grade}")
        return None

    start = input("  Start time (HH:MM 24h, e.g. 07:45): ").strip()
    end = input("  End time (HH:MM 24h, e.g. 14:35): ").strip()
    school = input("  School name (or Enter to skip): ").strip() or None
    source = input("  Source file name (or Enter to skip): ").strip() or None
    notes = input("  Notes (or Enter to skip): ").strip() or ""

    return {
        "grade_level": grade,
        "start_time": start,
        "end_time": end,
        "school_name": school,
        "source_file": source,
        "notes": notes,
    }


def create_ground_truth_for_district(district_dir: Path):
    """Interactive ground truth creation for one district."""
    metadata = load_metadata(district_dir)
    district_id = metadata.get("district_id", district_dir.name.split("_")[0])
    district_name = metadata.get("district_name", district_dir.name)
    state = metadata.get("state", district_dir.parent.name)

    gt_path = district_dir / "ground_truth.json"
    if gt_path.exists():
        overwrite = input(f"  ground_truth.json already exists for {district_name}. Overwrite? (y/N): ")
        if overwrite.lower() != "y":
            print("  Skipping.")
            return

    print_separator()
    print(f"  District: {district_name}")
    print(f"  ID: {district_id}")
    print(f"  State: {state}")
    print(f"  Directory: {district_dir}")

    txt_files = get_txt_files(district_dir)
    if not txt_files:
        print("  No .txt files found in active/. Skipping.")
        return

    print(f"\n  Found {len(txt_files)} text file(s):")
    for f in txt_files:
        print(f"    - {f.relative_to(district_dir)}")

    # Show each file
    for txt_file in txt_files:
        display_txt_file(txt_file)

    # Collect schedules
    print("\n  Now enter the bell schedule data you see in these files.")
    print("  Enter one schedule at a time. Type 'done' when finished.\n")

    schedules = []
    while True:
        print(f"  --- Schedule #{len(schedules) + 1} ---")
        result = prompt_schedule()
        if result == "done":
            break
        if result == "skip":
            continue
        if result is None:
            continue
        schedules.append(result)
        print(f"  Added: {result['grade_level']} {result['start_time']}-{result['end_time']}")

    if not schedules:
        print("  No schedules entered. Skipping ground truth creation.")
        return

    # Expected grade levels
    print("\n  Which grade levels should be extractable from these documents?")
    expected = input("  Expected (comma-separated, e.g. elementary,middle,high): ").strip()
    expected_levels = [g.strip() for g in expected.split(",") if g.strip()]

    # Missing OK
    found_levels = {s["grade_level"] for s in schedules}
    missing = set(expected_levels) - found_levels
    missing_ok = []
    if missing:
        print(f"  Missing grade levels: {missing}")
        ok = input("  Are these genuinely missing from the source? (y/N): ").strip()
        if ok.lower() == "y":
            missing_ok = list(missing)

    # False positive traps
    print("\n  Any false positive traps in the text? (e.g. 'Office hours 7:30-4:00')")
    traps = []
    while True:
        trap = input("  Trap (or Enter to finish): ").strip()
        if not trap:
            break
        traps.append(trap)

    # Build ground truth
    ground_truth = {
        "district_id": district_id,
        "district_name": district_name,
        "state": state,
        "ground_truth_date": date.today().isoformat(),
        "transcribed_by": "human",
        "schedules": schedules,
        "expected_grade_levels": expected_levels,
        "missing_grade_levels_ok": missing_ok,
        "false_positive_traps": traps,
    }

    with open(gt_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"\n  Ground truth saved to: {gt_path}")
    print(f"  Schedules: {len(schedules)}")
    print(f"  Expected grades: {expected_levels}")


def list_districts():
    """List all districts with txt files and their ground truth status."""
    districts = find_all_districts_with_txt()
    print(f"\nDistricts with .txt files ({len(districts)} total):\n")
    print(f"  {'State':<6} {'ID':<10} {'Name':<45} {'TXT':<5} {'GT?':<4}")
    print(f"  {'─' * 6} {'─' * 10} {'─' * 45} {'─' * 5} {'─' * 4}")

    for d in districts:
        metadata = load_metadata(d)
        district_id = metadata.get("district_id", d.name.split("_")[0])
        district_name = metadata.get("district_name", d.name)[:44]
        state = metadata.get("state", d.parent.name)
        txt_count = len(get_txt_files(d))
        has_gt = "✓" if (d / "ground_truth.json").exists() else ""
        print(f"  {state:<6} {district_id:<10} {district_name:<45} {txt_count:<5} {has_gt:<4}")


def main():
    parser = argparse.ArgumentParser(description="Create ground truth files for benchmark testing")
    parser.add_argument("--district", type=str, help="District ID to create ground truth for")
    parser.add_argument("--all", action="store_true", help="Create ground truth for all districts with txt files")
    parser.add_argument("--list", action="store_true", help="List available districts")
    args = parser.parse_args()

    if args.list:
        list_districts()
        return

    if args.district:
        district_dir = find_district_dir(args.district)
        if not district_dir:
            print(f"District {args.district} not found.")
            sys.exit(1)
        create_ground_truth_for_district(district_dir)
        return

    if args.all:
        districts = find_all_districts_with_txt()
        print(f"Found {len(districts)} districts with txt files.")
        for d in districts:
            create_ground_truth_for_district(d)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
