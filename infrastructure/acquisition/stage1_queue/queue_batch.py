"""Stage 1 (Queue) of the bell-schedule acquisition pipeline.

Builds a batch of districts plus, per district, the per-band school lists to target --
the structured input Stage 2 (Discover) and Stage 3 (Capture) consume. See
docs/ACQUISITION_PIPELINE.md (Stage 1 section) and docs/diagrams/acquisition_pipeline_flow.md
for the full design and rationale; this docstring covers usage only.

Pre-queue exclusion filters (live, recomputed every run -- never a frozen list):
  1. Not operating (LEA SY_STATUS_TEXT != "Open")
  2. CTC / shared-service entity (districts.is_shared_service_entity, METHODOLOGY.md Rule 6)
  3. Grade-span integrity (LEA-level claimed band with zero school-level coverage, Rule 7)
  4. Already attempted -- reached Stage 3 (Capture) or beyond, any outcome, per
     district_status.json. A district that only reached Stage 1/2 (queued/searched but
     never actually captured) stays eligible for redraw -- see
     district_status.ATTEMPTED_THRESHOLD_STAGE.

Stratified sampling: enrollment quartiles (priority axis) + state (tiebreak).
Per-band school selection: cap 12/band, most-constrained-first cross-band overlap
minimization, seeded random sample when over cap.

Usage: queue_batch.py <batch_number> [--n 12] [--year 2024_25] [--dry-run]
Writes data/acquisition/queue/batch_NNNNN.json (5-digit, e.g. batch_00001.json --
covers the unlikely case of needing one batch per individual US school district);
records queued districts in
data/acquisition/status/district_status.json (skipped on --dry-run).
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import school_sampling as S
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
import district_status as DS
from discover import host_of

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, EnrollmentByGrade

CAP = 12
QUARTILES = 4
OUT_DIR = Path("data/acquisition/queue")
BANDS = ("elementary", "middle", "high")


def load_ctc_ids() -> set:
    with session_scope() as session:
        return {d.nces_id for d in session.query(District).filter(District.is_shared_service_entity == True).all()}


def load_enrollment() -> dict:
    """district_id -> most recent non-null/non-zero enrollment_k12, across all source years."""
    with session_scope() as session:
        rows = session.query(
            EnrollmentByGrade.district_id, EnrollmentByGrade.source_year, EnrollmentByGrade.enrollment_k12
        ).all()
    by_district = defaultdict(list)
    for did, year, enr in rows:
        by_district[did].append((year, enr))
    out = {}
    for did, vals in by_district.items():
        vals.sort(key=lambda v: v[0], reverse=True)
        for _, enr in vals:
            if enr and enr > 0:
                out[did] = int(enr)  # Integer column can still surface as Decimal via the DB driver
                break
    return out


def eligible_pool(year: str, registry: dict) -> tuple[dict, dict, list]:
    """Apply all pre-queue exclusion filters; return (pool, school_index, grade_span_gap_excluded)."""
    lea = S.lea_info(year)
    sch_idx = S.school_index(year)
    ctc_ids = load_ctc_ids()
    enrollment = load_enrollment()

    pool = {}
    gap_excluded = []
    for did, info in lea.items():
        if info["status"] != "Open":
            continue
        if did in ctc_ids:
            continue
        if DS.already_attempted(registry, did):
            continue
        claimed = info["claimed_bands"]
        covered = {b for b in claimed if sch_idx.get(did, {}).get(b)}
        gap = claimed - covered
        if gap:
            gap_excluded.append({"district_id": did, "name": info["name"], "state": info["state"], "gap_bands": sorted(gap)})
            continue
        enr = enrollment.get(did)
        if not enr:
            continue
        pool[did] = {**info, "enrollment_k12": enr}
    return pool, sch_idx, gap_excluded


def stratified_pick(pool: dict, batch_id: str, n: int = 12, k: int = QUARTILES) -> list:
    """Enrollment quartiles (priority axis) + state tiebreak (secondary), seeded by batch_id."""
    ordered = sorted(pool.keys(), key=lambda did: pool[did]["enrollment_k12"])
    total = len(ordered)
    if total == 0:
        return []
    buckets = [set() for _ in range(k)]
    for i, did in enumerate(ordered):
        buckets[min(i * k // total, k - 1)].add(did)

    rng = random.Random(batch_id)
    used_states: set = set()
    picked: list = []
    remaining_all = set(pool.keys())

    def take_one(candidate_set: set):
        cands = list(candidate_set)
        if not cands:
            return None
        rng.shuffle(cands)
        cands.sort(key=lambda did: pool[did]["state"] in used_states)
        chosen = cands[0]
        candidate_set.discard(chosen)
        remaining_all.discard(chosen)
        used_states.add(pool[chosen]["state"])
        picked.append(chosen)
        return chosen

    per_bucket = n // k
    for bset in buckets:
        for _ in range(per_bucket):
            take_one(bset)

    while len(picked) < n and remaining_all:
        take_one(remaining_all)

    return picked[:n]


def select_schools(batch_id: str, district_id: str, district_school_index: dict, cap: int = CAP):
    """Most-constrained-first band processing with claim-then-exclude-then-fallback
    (cross-band overlap minimization, see ACQUISITION_PIPELINE.md Stage 1)."""
    bands_present = [b for b in BANDS if district_school_index.get(b)]
    order = sorted(bands_present, key=lambda b: len(district_school_index[b]))
    claimed: set = set()
    result = {}
    for b in order:
        cands = district_school_index[b]
        unclaimed = [c for c in cands if c["school_id"] not in claimed]
        rng = random.Random(f"{batch_id}:{district_id}:{b}")
        if len(unclaimed) >= cap:
            picked = rng.sample(unclaimed, cap)
        else:
            picked = list(unclaimed)
            need = cap - len(picked)
            reusable = [c for c in cands if c["school_id"] in claimed]
            if need > 0 and reusable:
                picked += rng.sample(reusable, min(need, len(reusable)))
        result[b] = {
            "n_candidates": len(cands),
            "n_unclaimed_at_selection": len(unclaimed),
            "n_selected": len(picked),
            "schools": picked,
        }
        claimed |= {c["school_id"] for c in picked}
    return order, result


def main():
    ap = argparse.ArgumentParser(description="Stage 1 (Queue): build a batch for the acquisition pipeline")
    ap.add_argument("batch", type=int)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--year", default="2024_25")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    batch_id = f"batch_{a.batch:05d}"
    registry = DS.load()

    pool, sch_idx, gap_excluded = eligible_pool(a.year, registry)
    level_counts = S.school_level_counts(a.year)   # did -> {total, by_level} (the topology denominator)
    print(f"Eligible pool: {len(pool):,} districts (excluded {len(gap_excluded)} for grade-span gap)")
    if gap_excluded:
        for g in gap_excluded[:10]:
            print(f"  grade-span gap: [{g['state']}] {g['name']} ({g['district_id']}) -- missing {g['gap_bands']}")
        if len(gap_excluded) > 10:
            print(f"  ... and {len(gap_excluded) - 10} more")

    picked_ids = stratified_pick(pool, batch_id, n=a.n)
    print(f"{batch_id}: picked {len(picked_ids)} districts")

    districts_out = []
    for did in picked_ids:
        info = pool[did]
        web = info["website"] or ""
        domain = host_of(web if "//" in web else "http://" + web) if web else ""
        order, schools_by_band = select_schools(batch_id, did, sch_idx.get(did, {}))
        districts_out.append({
            "district_id": did,
            "name": info["name"],
            "state": info["state"],
            "domain": domain,
            "enrollment_k12": info["enrollment_k12"],
            "lea_claimed_bands": sorted(info["claimed_bands"]),
            "nces_school_counts": level_counts.get(did, {"total": 0, "by_level": {}}),
            "band_processing_order": order,
            "schools_by_band": schools_by_band,
        })
        print(f"  [{info['state']}] {info['name'][:40]:40} enr={info['enrollment_k12']:>7,} "
              + " ".join(f"{b[:4]}={schools_by_band[b]['n_selected']}/{schools_by_band[b]['n_candidates']}" for b in order))

    batch_doc = {
        "batch_id": batch_id,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n": len(districts_out),
        "nces_year": a.year,
        "nces_school_counts_criteria": ("count of ccd_sch schools meeting our eligibility (open, "
            "regular, non-virtual, not standalone-preschool), grouped by the RAW ccd_sch LEVEL "
            "field. The topology denominator -- NOT ccd_lea's reported figure. total == the distinct "
            "school count used for band selection."),
        "stratification": {
            "priority": ["enrollment", "state"],
            "method": "enrollment quartiles over current eligible pool, 3 districts/quartile, seeded shuffle preferring unused state, top up from adjacent quartile if short",
        },
        "school_cap_per_band": CAP,
        "school_selection_when_over_cap": (
            "process bands most-constrained-first (ascending by candidate-pool size) within each "
            "district; each band samples from candidates not yet claimed by an earlier-processed "
            "band first, only reusing an already-claimed (multi-band) school if the unclaimed pool "
            "can't fill the cap. Seed = f'{batch_id}:{district_id}:{band}'. No approval field needed "
            "-- CP-A review is out-of-band."
        ),
        "districts": districts_out,
    }

    if a.dry_run:
        print("\nDRY RUN -- not written, status registry not updated")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{batch_id}.json"
    out_path.write_text(json.dumps(batch_doc, indent=2))
    print(f"\nWrote {out_path}")

    for d in districts_out:
        DS.record_stage(
            registry, d["district_id"], d["name"], d["state"],
            stage=1, stage_name="queue", outcome="queued", batch_id=batch_id,
        )
    DS.save(registry)
    print(f"Recorded {len(districts_out)} districts in {DS.STATUS_FILE}")


if __name__ == "__main__":
    main()
