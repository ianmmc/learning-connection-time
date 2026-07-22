#!/usr/bin/env python3
"""
LEDGER NOTE (2026-07-02, issue #21): this is a DATA backfill — it backfills districts.is_shared_service_entity / is_career_technical_center (Rule 6) — NOT a schema migration; it deliberately does not write schema_migrations. All DDL lives in the numbered NNN_*.sql files (migrate.py status = the ledger).

Backfill is_career_technical_center / is_shared_service_entity for CTCs.

METHODOLOGY.md Rule 6 calls for excluding career/technical centers and other
shared-service entities (CTCs, BOCES, cooperatives) from national LCT
calculations, since they serve students part-time from multiple home
districts, inflating teacher-to-student ratios. The schema columns
(is_career_technical_center, is_shared_service_entity) have existed since
the Rule 6 design (PA_CTC_DATA_DISCREPANCY.md), but the
backfill was never actually run -- both columns were False/0 for every
district until 2026-06-22, and calculate_lct_variants.py's exclusion filter
(on is_shared_service_entity) had consequently never excluded anything.

Candidate selection (expanded 2026-06-22 after Pima County JTED slipped
through the original name-only sweep into a real acquisition-queue batch):

1. Name matches career/technical/vocational/JTED/CTED (the documented Rule 6
   pattern, extended to catch acronym-named entities like Arizona's Joint/
   Career Technical Education Districts that don't literally spell out
   "technical").
2. NCES LEA_TYPE_TEXT in BLANKET_EXCLUDE_LEA_TYPES -- "Specialized public
   school district" / "Service agency" / "State operated agency". These
   buckets are NOT clean CTC-only buckets: e.g. "Specialized public school
   district" also contains full-time, full-span (PK-12) state schools (deaf/
   blind institutes, fine-arts academies, cyber/STEM schools) that are NOT
   part-time multi-district CTCs and don't share Rule 6's ratio-inflation
   rationale. ACCEPTED TRADE-OFF (explicit, not silent): blanket-excluding
   these three LEA_TYPE_TEXT buckets sweeps those legitimate full-time
   special-purpose schools out too. Decided acceptable for now because (a)
   the categories are small relative to the ~19K-LEA corpus, (b) most genuine
   members ARE CTC-pattern, and (c) building a more surgical name/grade-span
   classifier to rescue the minority of legitimate special-purpose schools is
   a separate, deferred piece of work -- not worth blocking on today. See
   METHODOLOGY.md Rule 6 for the full writeup.

Either condition (1) or (2) flags a candidate UNLESS NCES LEA_TYPE_TEXT
contains "charter" -- charter LEAs with career/tech branding (e.g.
"California Innovative Career Academy District") are tagged per REQ-060,
never excluded. Charter is its own disjoint LEA_TYPE_TEXT bucket
("Independent charter district"), so this only ever matters for condition
(1) matches, never condition (2).

Sets BOTH columns True for matched districts, since calculate_lct_variants.py
checks is_shared_service_entity while the originally documented fix only
proposed is_career_technical_center -- two different columns for the same
real-world entities. Idempotent / safe to re-run: only ever sets True, never
reverts a prior match, so expanding the criteria and re-running just adds
more flagged districts on top of what's already flagged.

Usage:
    python apply_ctc_classification.py [--year 2024_25] [--dry-run]
"""

import argparse
import csv
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, DataLineage

NAME_KEYWORDS = ["career", "technical", "vocational", "jted", "cted"]
BLANKET_EXCLUDE_LEA_TYPES = {
    "Specialized public school district",
    "Service agency",
    "State operated agency",
}


def load_lea_types(year: str) -> dict:
    """district_id (zero-padded LEAID) -> LEA_TYPE_TEXT, from the LEA directory file."""
    data_dir = project_root / "data" / "raw" / "federal" / "nces-ccd" / year
    matches = sorted(data_dir.glob("ccd_lea_029_*.csv"))
    if len(matches) != 1:
        print(f"Error: expected exactly one ccd_lea_029_*.csv in {data_dir}, found {matches}")
        sys.exit(1)

    lea_types = {}
    with open(matches[0], encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            did = row.get("LEAID", "").zfill(7)
            lea_types[did] = row.get("LEA_TYPE_TEXT", "")
    return lea_types


def main():
    parser = argparse.ArgumentParser(description="Backfill CTC/shared-service-entity classification")
    parser.add_argument("--year", default="2024_25", help="NCES year directory (e.g. 2024_25)")
    parser.add_argument("--dry-run", action="store_true", help="Report matches without writing")
    args = parser.parse_args()

    lea_types = load_lea_types(args.year)

    with session_scope() as session:
        all_districts = session.query(District).all()

        charter_skipped = []
        ctc_matched = []
        districts_by_id = {d.nces_id: d for d in all_districts}
        for d in all_districts:
            lea_type = lea_types.get(d.nces_id, "")
            if "charter" in lea_type.lower():
                if any(kw in d.name.lower() for kw in NAME_KEYWORDS):
                    charter_skipped.append((d.nces_id, d.name, d.state, lea_type))
                continue

            name_match = any(kw in d.name.lower() for kw in NAME_KEYWORDS)
            type_match = lea_type in BLANKET_EXCLUDE_LEA_TYPES
            if name_match or type_match:
                ctc_matched.append((d.nces_id, d.name, d.state, lea_type, "name" if name_match else "lea_type"))

        print(f"Charter LEAs skipped (REQ-060, tagged not excluded): {len(charter_skipped)}")
        print(f"CTC/shared-service matches to flag: {len(ctc_matched)}")
        print()

        if args.dry_run:
            print("DRY RUN -- no changes written")
            for did, name, state, lea_type, reason in ctc_matched:
                print(f"  [{state}] {name} ({did}) -- {lea_type} (matched via {reason})")
            return

        # Reuse the objects already loaded above — a per-match re-query issued
        # ~N redundant SELECTs (issue #457)
        for did, name, state, lea_type, reason in ctc_matched:
            d = districts_by_id[did]
            d.is_career_technical_center = True
            d.is_shared_service_entity = True

        DataLineage.log(
            session,
            entity_type="district_classification",
            entity_id="bulk_ctc_backfill",
            operation="update",
            source_file=f"data/raw/federal/nces-ccd/{args.year}/ccd_lea_029_*.csv",
            details={
                "rule": "METHODOLOGY.md Rule 6",
                "matched_and_flagged": len(ctc_matched),
                "charter_skipped_req060": len(charter_skipped),
                "name_keywords": NAME_KEYWORDS,
                "blanket_excluded_lea_types": sorted(BLANKET_EXCLUDE_LEA_TYPES),
                "disambiguator": "LEA_TYPE_TEXT NOT ILIKE '%charter%'",
            },
            created_by="apply_ctc_classification",
        )
        session.commit()
        print(f"Flagged {len(ctc_matched)} districts as career_technical_center + shared_service_entity.")


if __name__ == "__main__":
    main()
