#!/usr/bin/env python3
"""
run_batch_pipeline.py - Run full enrichment pipeline on multiple districts

PURPOSE:
    Processes a batch of districts through the complete Phase 8 enrichment pipeline:
    1. Ollama extraction (via FastAPI endpoint)
    2. calculate_minutes.py
    3. Database import (with existing record deletion)
    4. Verification

USAGE:
    python infrastructure/scripts/enrich/run_batch_pipeline.py
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import requests

# Configuration for resource-friendly execution
INTER_DISTRICT_DELAY = 30  # seconds between districts for memory cleanup
REQUEST_TIMEOUT = 180  # 3 minutes for Ollama extraction

# Base directories
PDF_BASE_DIR = project_root / "data" / "raw" / "bell_schedule_pdfs"
SCRIPTS_DIR = project_root / "infrastructure" / "scripts" / "enrich"

# Target districts to process
DISTRICTS = [
    {"nces_id": "4666270", "state": "SD", "name": "Sioux Falls School District 49-5"},
    {"nces_id": "4659820", "state": "SD", "name": "Rapid City Area School District 51-4"},
    {"nces_id": "1302280", "state": "GA", "name": "Fulton County"},
    {"nces_id": "0804800", "state": "CO", "name": "Jefferson County R-1"},
    {"nces_id": "0803360", "state": "CO", "name": "Denver Public Schools"},
    {"nces_id": "0634320", "state": "CA", "name": "San Diego Unified"},
    {"nces_id": "0626910", "state": "CA", "name": "New Haven Unified"},
    {"nces_id": "0614550", "state": "CA", "name": "Fresno Unified"},
    {"nces_id": "0634410", "state": "CA", "name": "San Francisco Unified"},
    {"nces_id": "1914700", "state": "IA", "name": "Iowa City Comm School District"},
]


def find_district_dir(nces_id: str, state: str) -> Path:
    """Find the district directory by NCES ID."""
    state_dir = PDF_BASE_DIR / state
    if not state_dir.exists():
        return None
    for d in state_dir.iterdir():
        if d.is_dir() and d.name.startswith(nces_id):
            return d
    return None


def find_txt_files(district_dir: Path) -> list:
    """Find all text files in active or converted subdirectories."""
    txt_files = []

    # Check active/converted first (most common location)
    converted_dir = district_dir / "active" / "converted"
    if converted_dir.exists():
        txt_files.extend(converted_dir.glob("*.txt"))

    # Check active directly
    active_dir = district_dir / "active"
    if active_dir.exists():
        txt_files.extend([f for f in active_dir.glob("*.txt") if f.parent == active_dir])

    return list(txt_files)


def run_extraction(district: dict) -> dict:
    """Run Ollama extraction via FastAPI endpoint."""
    print(f"\n  [1/4] Running Ollama extraction (llama3.1:8b)...")

    try:
        response = requests.post(
            "http://localhost:8000/enrich/extract",
            json={
                "district_id": district["nces_id"],
                "district_name": district["name"],
                "state": district["state"],
            },
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 200:
            result = response.json()
            print(f"       Extracted {result.get('schedules_extracted', 0)} schedules")
            return result
        else:
            print(f"       ERROR: {response.status_code} - {response.text[:200]}")
            return {"success": False, "error": response.text}
    except requests.exceptions.Timeout:
        print(f"       ERROR: Request timed out after {REQUEST_TIMEOUT}s")
        return {"success": False, "error": f"Timeout after {REQUEST_TIMEOUT}s"}
    except Exception as e:
        print(f"       ERROR: {e}")
        return {"success": False, "error": str(e)}


def run_calculate_minutes(district_dir: Path) -> bool:
    """Run calculate_minutes.py on extraction result."""
    print(f"  [2/4] Calculating instructional minutes...")

    extraction_file = district_dir / "extraction_result.json"
    output_file = district_dir / "enrichment_ready.json"

    if not extraction_file.exists():
        print(f"       ERROR: extraction_result.json not found")
        return False

    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "calculate_minutes.py"),
        "--input", str(extraction_file),
        "--output", str(output_file),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(project_root))

    if result.returncode == 0:
        print(f"       Success - output: {output_file.name}")
        return True
    else:
        print(f"       ERROR: {result.stderr[:200]}")
        return False


def delete_existing_records(nces_id: str) -> int:
    """Delete existing bell schedule records for a district."""
    print(f"  [3/4] Deleting existing records...")

    from infrastructure.database.connection import session_scope
    from infrastructure.database.models import BellSchedule

    with session_scope() as session:
        deleted = session.query(BellSchedule).filter_by(district_id=nces_id).delete()
        session.commit()
        print(f"       Deleted {deleted} existing records")
        return deleted


def run_import(district_dir: Path) -> dict:
    """Run pipeline_import_bell_schedules.py."""
    print(f"  [4/4] Importing to database...")

    enrichment_file = district_dir / "enrichment_ready.json"

    if not enrichment_file.exists():
        print(f"       ERROR: enrichment_ready.json not found")
        return {"success": False, "error": "enrichment_ready.json not found"}

    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "pipeline_import_bell_schedules.py"),
        "--input", str(enrichment_file),
    ]

    env = {"PYTHONPATH": str(project_root)}
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(project_root), env={**dict(__import__('os').environ), **env})

    if result.returncode == 0:
        # Parse output for record count
        lines = result.stdout.strip().split("\n")
        for line in lines:
            if "created" in line.lower() or "imported" in line.lower():
                print(f"       {line}")
        return {"success": True, "output": result.stdout}
    else:
        print(f"       ERROR: {result.stderr[:200]}")
        return {"success": False, "error": result.stderr}


def process_district(district: dict) -> dict:
    """Process a single district through the full pipeline."""
    print(f"\n{'='*60}")
    print(f"Processing: {district['name']} ({district['nces_id']})")
    print(f"{'='*60}")

    result = {
        "nces_id": district["nces_id"],
        "name": district["name"],
        "state": district["state"],
        "success": False,
        "extraction": None,
        "minutes_calculated": False,
        "records_deleted": 0,
        "import_result": None,
    }

    # Find district directory
    district_dir = find_district_dir(district["nces_id"], district["state"])
    if not district_dir:
        print(f"  ERROR: District directory not found")
        result["error"] = "Directory not found"
        return result

    result["directory"] = str(district_dir)

    # Check for text files
    txt_files = find_txt_files(district_dir)
    if not txt_files:
        print(f"  ERROR: No text files found")
        result["error"] = "No text files"
        return result

    print(f"  Found {len(txt_files)} text file(s)")

    # Step 1: Ollama extraction
    extraction = run_extraction(district)
    result["extraction"] = extraction
    if not extraction.get("success"):
        result["error"] = "Extraction failed"
        return result

    # Step 2: Calculate minutes
    if run_calculate_minutes(district_dir):
        result["minutes_calculated"] = True
    else:
        result["error"] = "Minutes calculation failed"
        return result

    # Step 3: Delete existing records
    result["records_deleted"] = delete_existing_records(district["nces_id"])

    # Step 4: Import new records
    import_result = run_import(district_dir)
    result["import_result"] = import_result

    if import_result.get("success"):
        result["success"] = True
    else:
        result["error"] = "Import failed"

    return result


def main():
    """Main entry point."""
    # Set low priority for resource-friendly execution
    try:
        os.nice(10)  # Lower priority (higher nice value = lower priority)
        print("Running at low priority (nice +10)")
    except (OSError, AttributeError):
        print("Could not set low priority (requires Unix)")

    print("=" * 60)
    print("BATCH ENRICHMENT PIPELINE")
    print(f"Processing {len(DISTRICTS)} districts")
    print(f"Inter-district delay: {INTER_DISTRICT_DELAY}s")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    results = []
    success_count = 0

    for i, district in enumerate(DISTRICTS):
        result = process_district(district)
        results.append(result)
        if result["success"]:
            success_count += 1

        # Add delay between districts for memory cleanup (skip after last)
        if i < len(DISTRICTS) - 1:
            print(f"\n  Waiting {INTER_DISTRICT_DELAY}s before next district...")
            time.sleep(INTER_DISTRICT_DELAY)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total districts: {len(DISTRICTS)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {len(DISTRICTS) - success_count}")

    # Save results
    output_file = project_root / "data" / "batch_pipeline_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "districts_processed": len(DISTRICTS),
            "successful": success_count,
            "results": results,
        }, f, indent=2)

    print(f"\nResults saved to: {output_file}")

    # Print failed districts
    failed = [r for r in results if not r["success"]]
    if failed:
        print("\nFailed districts:")
        for r in failed:
            print(f"  - {r['name']}: {r.get('error', 'Unknown error')}")

    return success_count == len(DISTRICTS)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
