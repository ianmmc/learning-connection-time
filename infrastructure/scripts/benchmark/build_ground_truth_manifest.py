#!/usr/bin/env python3
"""
build_ground_truth_manifest.py - Assemble the benchmark ground-truth manifest from the DB.

The 42 `human_provided` bell_schedules rows (grade-band start/end times, human-collected)
are a far larger and more diverse ground-truth set than the 6 hand-typed ground_truth.json
files. This script promotes them into a single benchmark manifest, mapping each district to
its source documents on disk and tagging the input modality (pdf/html/image/office).

Output: data/benchmark/ground_truth_manifest.json

Each district entry is scorer-compatible (score_extraction.py): grade-band schedules with
school_name=null (the LCT-relevant granularity). Districts with no source documents on disk
are excluded (can't benchmark extraction without an input).

Usage:
    python infrastructure/scripts/benchmark/build_ground_truth_manifest.py
"""

from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from infrastructure.database.connection import session_scope
from infrastructure.api.services.extraction_service import ExtractionService

_NORM = ExtractionService()._normalize_time  # same normalization the extractors use

CORPUS = PROJECT_ROOT / "data" / "raw" / "bell_schedule_pdfs"
OUT = PROJECT_ROOT / "data" / "benchmark" / "ground_truth_manifest.json"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif"}
HTML_EXTS = {".html", ".htm", ".mhtml"}
OFFICE_EXTS = {".docx", ".doc", ".xlsx", ".xls"}


def find_source_dir(district_id: str) -> Path | None:
    matches = glob.glob(str(CORPUS / "*" / f"{district_id}_*"))
    return Path(matches[0]) if matches else None


def modality_tags(source_dir: Path) -> dict:
    """Inventory input file types in the district's active/ (and dir) to tag modality."""
    files = glob.glob(str(source_dir / "active" / "*")) + glob.glob(str(source_dir / "*"))
    files = [f for f in files if os.path.isfile(f)]
    ext_counts: dict[str, int] = {}
    for f in files:
        e = os.path.splitext(f)[1].lower()
        ext_counts[e] = ext_counts.get(e, 0) + 1
    tags = set()
    for e in ext_counts:
        if e == ".pdf":
            tags.add("pdf")
        elif e in IMAGE_EXTS:
            tags.add("image")
        elif e in HTML_EXTS:
            tags.add("html")
        elif e in OFFICE_EXTS:
            tags.add("office")
        elif e == ".txt":
            tags.add("text")
    has_txt = any(os.path.basename(os.path.dirname(f)) == "active" and f.endswith(".txt") for f in files)
    return {"tags": sorted(tags), "ext_counts": ext_counts, "has_active_txt": has_txt}


def main() -> int:
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT b.district_id, d.name, d.state, b.grade_level,
                   b.start_time, b.end_time, b.instructional_minutes
            FROM bell_schedules b JOIN districts d ON d.nces_id = b.district_id
            WHERE b.method = 'human_provided'
              AND b.start_time IS NOT NULL AND b.end_time IS NOT NULL
            ORDER BY d.state, b.district_id, b.grade_level
        """)).fetchall()

    by_district: dict[str, dict] = {}
    norm_failures = []
    for did, name, state, grade, start, end, mins in rows:
        d = by_district.setdefault(did, {
            "district_id": did, "district_name": name, "state": state, "schedules": [],
        })
        ns, ne = _NORM(str(start)), _NORM(str(end))  # 24-hour HH:MM, AM/PM-aware
        if ns is None or ne is None:
            norm_failures.append((did, grade, str(start), str(end)))
            continue  # unscoreable (e.g. "Varies") — drop from ground truth
        d["schedules"].append({
            "grade_level": grade,
            "start_time": ns,
            "end_time": ne,
            "raw_start_time": str(start),
            "raw_end_time": str(end),
            "instructional_minutes": mins,
            "school_name": None,  # grade-band ground truth (LCT granularity)
        })

    districts = []
    skipped_no_source = []
    skipped_no_gt = []
    for did, d in by_district.items():
        if not d["schedules"]:
            skipped_no_gt.append(did)  # all schedules were unscoreable (e.g. LA "Varies")
            continue
        src = find_source_dir(did)
        if src is None:
            skipped_no_source.append(did)
            continue
        mod = modality_tags(src)
        d["source_dir"] = str(src.relative_to(PROJECT_ROOT))
        d["modality"] = mod["tags"]
        d["ext_counts"] = mod["ext_counts"]
        d["has_active_txt"] = mod["has_active_txt"]
        d["expected_grade_levels"] = sorted({s["grade_level"] for s in d["schedules"]})
        districts.append(d)

    districts.sort(key=lambda x: (x["state"], x["district_id"]))
    manifest = {
        "generated": datetime.utcnow().isoformat(),
        "source": "db:bell_schedules.method=human_provided",
        "granularity": "grade_band",
        "note": "Grade-band start/end times (school_name=null). Districts without on-disk "
                "source documents are excluded.",
        "district_count": len(districts),
        "skipped_no_source": skipped_no_source,
        "time_normalization_failures": norm_failures,
        "districts": districts,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=2))

    # Summary
    from collections import Counter
    states = Counter(d["state"] for d in districts)
    mod_counter = Counter(t for d in districts for t in d["modality"])
    print(f"Wrote {OUT.relative_to(PROJECT_ROOT)}")
    print(f"  districts: {len(districts)}  (skipped, no source on disk: {skipped_no_source})")
    print(f"  states ({len(states)}): {dict(sorted(states.items()))}")
    print(f"  modality coverage: {dict(mod_counter)}")
    print(f"  grade-band schedule rows: {sum(len(d['schedules']) for d in districts)}")
    print(f"  time normalization failures: {len(norm_failures)} {norm_failures[:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
