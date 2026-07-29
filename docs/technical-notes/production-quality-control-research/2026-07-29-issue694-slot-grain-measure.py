"""#694 corpus measurement — district-altitude follow-up detection, band-boolean vs slot-grain.

Read-only replay (the #691 measurement pattern): for every district with ≥1 production accepted
fact, assemble the REAL detector inputs (`stage7_run._district_request_inputs`, which now carries
the #694 slot-gap summary) and run the pure detector twice — once with `slot_gaps=None` (the
pre-#694 boolean) and once with the slot view — diffing the district-altitude output. Nothing is
persisted; `detect_requests` is pure and the session only reads.

Run:  python3 docs/technical-notes/production-quality-control-research/2026-07-29-issue694-slot-grain-measure.py
"""
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import stage7_run as R7
from infrastructure.acquisition.stage7_extract import requests as RQ

# Stage-2 SERP cost basis (ACQUISITION_PIPELINE.md §Stage 2 cost reframe, 2026-07)
COST_PER_QUERY = (0.001, 0.0015)


def main():
    gdb.init_precious_schema()
    with gdb.session_scope() as s:
        dids = [d for (d,) in s.execute(text(
            "SELECT DISTINCT f.district_id FROM school_fact f "
            "JOIN extraction e ON e.extraction_id = f.extraction_id "
            "WHERE f.status = 'accepted' AND e.run_kind = 'production' "
            "ORDER BY f.district_id")).all()]
        print(f"districts with production accepted facts: {len(dids)}\n")
        n_affected = n_new_dirs = n_named = n_mode_check = n_no_slot_view = 0
        for did in dids:
            result = {"district_id": did, "reps": [], "accepted": [], "unresolved": []}
            claimed, band_schools, alts, covered, real_bands, sg = \
                R7._district_request_inputs(s, result)
            if not sg:
                n_no_slot_view += 1
            old = [r for r in RQ.detect_requests(
                result, claimed_bands=claimed, band_schools=band_schools,
                covered_bands=covered, real_bands=real_bands)
                if r["altitude"] == "district"]
            new = [r for r in RQ.detect_requests(
                result, claimed_bands=claimed, band_schools=band_schools,
                covered_bands=covered, real_bands=real_bands, slot_gaps=sg)
                if r["altitude"] == "district"]
            old_bands = {r["band"] for r in old}
            added = [r for r in new if r["band"] not in old_bands]
            if not added:
                continue
            n_affected += 1
            n_new_dirs += len(added)
            name = s.execute(text("SELECT name FROM district WHERE district_id = :d"),
                             {"d": did}).scalar() or "?"
            for r in added:
                uf = r["params"].get("unfilled_schools") or []
                mc = r["params"].get("mode_check_schools") or []
                n_named += len(uf)
                n_mode_check += len(mc)
                print(f"  {did} {name[:34]:<34} {r['band']:<10} "
                      f"filled {r['params'].get('n_filled')}/{r['params'].get('n_slots')}"
                      f"  pursue {len(uf)}  mode-check {len(mc)}")
        q = n_named + n_mode_check
        print(f"\nTOTALS: {n_affected}/{len(dids)} districts gain {n_new_dirs} new "
              f"district-altitude directive(s); {n_named} pool schools named to pursue "
              f"+ {n_mode_check} span-only mode-check targets")
        print(f"no slot view (fallback to boolean, unchanged): {n_no_slot_view} districts")
        print(f"est. Stage-2 spend IF every named school gets one targeted query: "
              f"${q * COST_PER_QUERY[0]:.2f}-${q * COST_PER_QUERY[1]:.2f} "
              f"({q} queries @ $0.001-0.0015) — gate@7 approval still fronts every directive")


if __name__ == "__main__":
    main()
