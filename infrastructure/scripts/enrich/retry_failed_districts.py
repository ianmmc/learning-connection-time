#!/usr/bin/env python3
"""
retry_failed_districts.py - Re-run pipeline on previously failed districts

Runs at low priority with delays between districts for resource-friendly execution.
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Import from main pipeline script
from infrastructure.scripts.enrich.run_batch_pipeline import (
    process_district,
    INTER_DISTRICT_DELAY,
)

import json
from datetime import datetime

# Districts that failed in the first run
FAILED_DISTRICTS = [
    {"nces_id": "4659820", "state": "SD", "name": "Rapid City Area School District 51-4"},
    {"nces_id": "0803360", "state": "CO", "name": "Denver Public Schools"},
    {"nces_id": "0626910", "state": "CA", "name": "New Haven Unified"},
    {"nces_id": "0614550", "state": "CA", "name": "Fresno Unified"},
    {"nces_id": "0634410", "state": "CA", "name": "San Francisco Unified"},
]


def main():
    """Retry failed districts."""
    # Set low priority
    try:
        os.nice(10)
        print("Running at low priority (nice +10)")
    except (OSError, AttributeError):
        pass

    print("=" * 60)
    print("RETRY FAILED DISTRICTS")
    print(f"Processing {len(FAILED_DISTRICTS)} districts")
    print(f"Inter-district delay: {INTER_DISTRICT_DELAY}s")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    results = []
    success_count = 0

    for i, district in enumerate(FAILED_DISTRICTS):
        result = process_district(district)
        results.append(result)
        if result["success"]:
            success_count += 1

        # Add delay between districts (skip after last)
        if i < len(FAILED_DISTRICTS) - 1:
            print(f"\n  Waiting {INTER_DISTRICT_DELAY}s before next district...")
            time.sleep(INTER_DISTRICT_DELAY)

    # Summary
    print("\n" + "=" * 60)
    print("RETRY SUMMARY")
    print("=" * 60)
    print(f"Total retried: {len(FAILED_DISTRICTS)}")
    print(f"Successful: {success_count}")
    print(f"Still failing: {len(FAILED_DISTRICTS) - success_count}")

    # Save results
    output_file = project_root / "data" / "retry_pipeline_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "districts_retried": len(FAILED_DISTRICTS),
            "successful": success_count,
            "results": results,
        }, f, indent=2)

    print(f"\nResults saved to: {output_file}")

    return success_count == len(FAILED_DISTRICTS)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
