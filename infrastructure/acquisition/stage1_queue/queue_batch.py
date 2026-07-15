"""Stage 1 (Queue) of the bell-schedule acquisition pipeline.

Builds a batch of districts plus, per district, the per-band school lists to target --
the structured input Stage 2 (Discover) and Stage 3 (Capture) consume. See
docs/ACQUISITION_PIPELINE.md (Stage 1 section, incl. the flow diagram)
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
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.acquisition.common import school_sampling as S

from infrastructure.acquisition.common import district_status as DS

from infrastructure.acquisition.common import paths  # noqa: E402  (single source of truth for runtime-state locations — REQ-087)
from infrastructure.acquisition.common import db as gdb  # noqa: E402  (governance DB = the batch working store — REQ-102/103)
from infrastructure.acquisition.common.discover import domain_of, is_scoping_domain
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE

project_root = Path(__file__).parent.parent.parent.parent
from infrastructure.database.connection import session_scope
from infrastructure.database.models import District, EnrollmentByGrade

CAP = 12
QUARTILES = 4
OUT_DIR = paths.QUEUE_DIR
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


def build_batch(year: str, n: int, batch_id: str, registry: dict) -> tuple[dict, list, list, int]:
    """Pure batch construction: apply the pre-queue exclusions, stratified-pick, select per-band
    schools, and assemble the batch_doc. Does NO I/O -- no file write, no registry mutation, no
    printing (it only READS the registry, via eligible_pool's already-attempted filter). The caller
    (CLI main() or the gate@1 console 'create' action) persists via persist_batch().

    Returns (batch_doc, gap_excluded, domain_excluded, n_eligible)."""
    pool, sch_idx, gap_excluded = eligible_pool(year, registry)
    # #229 pre-flight guard: refuse any district whose NCES WEBSITE yields no usable scoping domain.
    # A blank/junk domain flips Stage 2 into its UNSCOPED, national-scope branch, which for common
    # school names pulls same-named schools nationwide into the candidate set (the Millard cross-
    # district contamination, #227). No usable alternate domain source exists, so this is a hard
    # refusal, not a fallback -- the district is dropped from the pool and reported, exactly like the
    # grade-span-gap exclusion, so a first-run batch of record never carries an unscoped district.
    # Benchmark (batch_00000) is exempt by structure: it calls eligible_pool directly (own build path)
    # and never routes through here.
    domain_excluded = []
    for did in list(pool):
        if not is_scoping_domain(domain_of(pool[did]["website"])):
            info = pool.pop(did)
            domain_excluded.append({"district_id": did, "name": info["name"],
                                    "state": info["state"], "website": info["website"]})
    level_counts = S.school_level_counts(year)   # did -> {total, by_level} (the topology denominator)
    picked_ids = stratified_pick(pool, batch_id, n=n)

    districts_out = []
    for did in picked_ids:
        info = pool[did]
        domain = domain_of(info["website"])
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

    batch_doc = {
        "batch_id": batch_id,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n": len(districts_out),
        "nces_year": year,
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
        # #229: carried in the doc (-> Batch.meta_json -> to_view/receipt) so the refusals stay
        # visible at gate@1 across reloads and in the audit receipt, not only in the create response.
        "domain_excluded": domain_excluded,
        "districts": districts_out,
    }
    return batch_doc, gap_excluded, domain_excluded, len(pool)


def build_followup_batch(year: str, batch_id: str, targets: dict, *,
                         attempted_by_did: dict = None, seed_urls_by_did: dict = None,
                         preferred_by_did: dict = None) -> tuple[dict, list]:
    """Build a TARGETED follow-up batch (batch_type='follow-up') from explicit district×band targets —
    the Stage-1 landing point for the request-more-evidence back-edges 7->2/7->3/7->1 (governance §11d:
    any NEW capture/discovery routes through a reviewable Stage-1 batch, never straight to discovery).

    UNLIKE build_batch this is NOT stratified and deliberately RE-INCLUDES already-attempted districts —
    a follow-up re-targets *unsatisfied bands* on districts that have already been through the pipeline,
    so the eligible_pool exclusions (already-attempted, enrollment floor) do NOT apply here. It reuses
    the SAME per-band school selection (`select_schools`, same seed/logic) as build_batch, just over a
    school index restricted to the target bands. Does NO I/O (reads NCES via school_sampling only); the
    caller persists via persist_batch(..., batch_type='follow-up'). build_batch is untouched — the
    first-run flow does not route through here.

    targets: {district_id: [band, ...]} — the bands to re-target per district (order preserved). A band
    with no school-level coverage in the NCES index is dropped; a district with no usable target band is
    skipped (reported).

    Follow-up shaping (epic #163):
      * attempted_by_did {district_id: {school_id, ...}} (#162): per target band, PREFER the NCES
        schools NOT yet attempted (a band came up empty — try schools we haven't discovered/captured).
        If a band has untried schools, select over those and tag `query_strategy='new_schools'`; if
        the untried set is empty (small district, all schools already tried), fall back to the full
        set and tag `query_strategy='widen_queries'` — the signal Stage 2 reads to run the
        differentiated SERP query set (#160) instead of the default. (Rendering stays in Stage 2:
        the stages are independent layers — Stage 1 must not import Stage 2's query renderer.)
      * preferred_by_did {district_id: {band: [school_id, ...]}} (#499 REQ-150): the band's
        UNFILLED SLOTS from the live gate@8 projection — schools the roster expects but no accepted
        fact has ever matched. When present for a band, selection restricts to those slots FIRST
        (the sharpening of #162: a school tried-but-never-attributed is still a gap — 'attempted'
        must not deprioritize it). query_strategy: 'new_schools' if any preferred slot is untried,
        else 'widen_queries' (every unfilled slot was already tried — differentiated queries are
        the remaining lever). Absent/empty -> the #162 untried logic below, unchanged.
      * seed_urls_by_did {district_id: [url, ...]} (#161): explicit URLs to capture (from 7->3
        recapture directives) — carried onto the district entry for Stage 3 to capture directly,
        skipping discovery. Dormant plumbing today (no producer of target_urls yet, per Ian) but wired.

    Returns (batch_doc, skipped) where skipped = [{district_id, reason}]."""
    attempted_by_did = attempted_by_did or {}
    seed_urls_by_did = seed_urls_by_did or {}
    preferred_by_did = preferred_by_did or {}
    lea = S.lea_info(year)
    sch_idx = S.school_index(year)
    level_counts = S.school_level_counts(year)
    enrollment = load_enrollment()

    districts_out, skipped = [], []
    for did in targets:                         # preserve caller order (attention-sorted upstream)
        info = lea.get(did)
        if not info:
            skipped.append({"district_id": did, "reason": "not in NCES lea_info for the year"})
            continue
        # #229 guard applies here too: a 7->2 rediscover for a blank/junk-domain district would run
        # UNSCOPED national-scope discovery. lea_info is NCES (not the batch_district row), so a
        # genuinely domain-less district stays domain-less across follow-ups -- skip rather than
        # contaminate. (Millard's #227 remediation re-runs its EXISTING batch with a hand-set domain,
        # not through here, so this guard does not block that path.)
        domain = domain_of(info["website"])
        if not is_scoping_domain(domain):
            skipped.append({"district_id": did, "reason": "no usable scoping domain -- would run UNSCOPED discovery (#229)"})
            continue
        dsi = sch_idx.get(did, {})
        want = [b for b in BANDS if b in set(targets[did]) and dsi.get(b)]   # normalize + drop empties
        if not want:
            skipped.append({"district_id": did, "reason": "no school-level coverage for the target bands"})
            continue
        # #162: per band prefer UNTRIED schools; fall back to the full set (and widen queries) when
        # every eligible school has already been attempted.
        attempted = attempted_by_did.get(did, set())
        preferred = preferred_by_did.get(did, {})
        restricted, query_strategy = {}, {}
        for b in want:
            # #499 REQ-150: unfilled slots first — the roster's own gap list beats the attempted
            # heuristic (tried-but-never-attributed is still a gap).
            pref_ids = set(preferred.get(b) or ())
            pref = [c for c in dsi[b] if c["school_id"] in pref_ids]
            if pref:
                restricted[b] = pref
                query_strategy[b] = ("new_schools"
                                     if any(c["school_id"] not in attempted for c in pref)
                                     else "widen_queries")
                continue
            untried = [c for c in dsi[b] if c["school_id"] not in attempted]
            if untried:
                restricted[b] = untried
                query_strategy[b] = "new_schools"
            else:
                restricted[b] = dsi[b]
                query_strategy[b] = "widen_queries"    # -> Stage 2 differentiated_queries (#160)
        order, schools_by_band = select_schools(batch_id, did, restricted)
        for b in schools_by_band:                          # #162/#160: the per-band signal Stage 2 reads
            schools_by_band[b]["query_strategy"] = query_strategy.get(b)
        districts_out.append({
            "district_id": did,
            "name": info["name"],
            "state": info["state"],
            "domain": domain,
            "enrollment_k12": enrollment.get(did),   # may be None for a follow-up; not a filter here
            "lea_claimed_bands": sorted(info["claimed_bands"]),
            "nces_school_counts": level_counts.get(did, {"total": 0, "by_level": {}}),
            "band_processing_order": order,
            "schools_by_band": schools_by_band,
            "seed_urls": seed_urls_by_did.get(did, []),    # explicit 7->3 recapture URLs (#161)
        })

    batch_doc = {
        "batch_id": batch_id,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n": len(districts_out),
        "nces_year": year,
        "districts": districts_out,
    }
    return batch_doc, skipped


def persist_batch(batch_doc: dict, registry: dict, *, batch_type: str = "first-run",
                  actor: str = "cli") -> Path:
    """Persist a freshly-built batch: write the DB WORKING STORE (batch_store rows) + regenerate the
    receipt batch_NNNNN.json from those rows + record one stage=1 'queued' state_event per district.
    Shared by the CLI and the gate@1 console 'create' action -- the single place a batch becomes
    durable + tracked. Requires the governance DB (Docker), same precondition as DS.save(). Mutates
    `registry` (caller loaded it via DS.load())."""
    batch_id = batch_doc["batch_id"]
    gdb.init_precious_schema()   # ensure the batch tables exist (idempotent; never drops)
    with gdb.session_scope() as sess:
        BSTORE.create_batch(sess, batch_doc, batch_type=batch_type, actor=actor)
        out_path = BSTORE.write_receipt(sess, batch_id)   # receipt regenerated FROM the rows
    for d in batch_doc["districts"]:
        DS.record_stage(
            registry, d["district_id"], d["name"], d["state"],
            stage=1, stage_name="queue", outcome="queued", batch_id=batch_id,
        )
    DS.save(registry)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Stage 1 (Queue): build a batch for the acquisition pipeline")
    ap.add_argument("batch", type=int)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--year", default="2024_25")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    batch_id = f"batch_{a.batch:05d}"
    registry = DS.load()

    batch_doc, gap_excluded, domain_excluded, n_eligible = build_batch(a.year, a.n, batch_id, registry)

    print(f"Eligible pool: {n_eligible:,} districts (excluded {len(gap_excluded)} for grade-span gap, "
          f"{len(domain_excluded)} for blank/unusable NCES domain)")

    def _print_excluded(items, detail):
        """First 10 + '... and N more' — shared by every exclusion report (one shape, N reasons)."""
        for x in items[:10]:
            print(f"  {detail(x)}")
        if len(items) > 10:
            print(f"  ... and {len(items) - 10} more")

    _print_excluded(gap_excluded,
                    lambda g: f"grade-span gap: [{g['state']}] {g['name']} ({g['district_id']}) -- missing {g['gap_bands']}")
    _print_excluded(domain_excluded,
                    lambda e: f"blank/unusable domain: [{e['state']}] {e['name']} ({e['district_id']}) -- website={e['website']!r}")

    print(f"{batch_id}: picked {len(batch_doc['districts'])} districts")
    for d in batch_doc["districts"]:
        sbb = d["schools_by_band"]
        print(f"  [{d['state']}] {d['name'][:40]:40} enr={d['enrollment_k12']:>7,} "
              + " ".join(f"{b[:4]}={sbb[b]['n_selected']}/{sbb[b]['n_candidates']}" for b in d["band_processing_order"]))

    if a.dry_run:
        print("\nDRY RUN -- not written, status registry not updated")
        return

    out_path = persist_batch(batch_doc, registry)
    print(f"\nWrote {out_path}")
    print(f"Recorded {len(batch_doc['districts'])} districts in {DS.STATUS_FILE}")


if __name__ == "__main__":
    main()
