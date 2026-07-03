"""Stage 7 GT validation (REQ-117, slice 4) — score council output against the curated ground truth.

Turns "matches GT" into a measured number, two grains:
  - per-BAND: our modal band gross vs GT `_derived_band_gross` (hit within TOL); also flags a `gap`
    (GT covers a band we didn't extract) and `extra` (we extracted a band GT doesn't cover).
  - per-SCHOOL: our accepted fact vs the matched GT school (by the SHARED `norm_school`, so matching
    can't drift from consensus), hit within TOL.
Pure — takes a run-result dict (`run_council`'s output) + a loaded GT; no network/DB. batch_00000
exists for exactly this scoring (STAGE7_EXTRACT_DESIGN); benchmark output is measured here, never
Stage-9-written.
"""
import json
from pathlib import Path

from infrastructure.acquisition.common.school_match import norm_school

TOL = 15
BANDS = ("elementary", "middle", "high")


def load_gt(path) -> dict:
    """{district_id: gt_entry} from a `gt_proposals.json` (a list of curated districts)."""
    data = json.loads(Path(path).read_text())
    rows = data if isinstance(data, list) else data.get("proposals", [])
    return {d["district_id"]: d for d in rows}


def _within(a, b, tol=TOL) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def _band_status(our, gt, tol=TOL) -> str:
    if our is None and gt is None:
        return "neither"
    if our is None:
        return "gap"       # GT covers this band; we produced nothing
    if gt is None:
        return "extra"     # we produced a band GT doesn't cover
    return "hit" if _within(our, gt, tol) else "miss"


def score_district(result: dict, gt_entry: dict, tol=TOL) -> dict:
    """Per-band + per-school scorecard for one district (`result` = one entry of run['districts'])."""
    prop = gt_entry.get("proposal") or {}
    our_bands = result.get("bands") or {}
    bands = []
    for band in BANDS:
        our = (our_bands.get(band) or {}).get("gross_minutes")
        gt = (prop.get(band) or {}).get("_derived_band_gross")
        bands.append({"band": band, "our": our, "gt": gt, "status": _band_status(our, gt, tol)})

    gt_schools = {(band, norm_school(s["school"])): s.get("gross")
                  for band, b in prop.items() for s in (b.get("schools") or [])}
    schools = []
    for f in result.get("accepted", []):
        gtg = gt_schools.get((f["band"], norm_school(f["school"])))
        schools.append({"band": f["band"], "school": f["school"], "our": f["gross"], "gt": gtg,
                        "matched": gtg is not None, "hit": _within(f["gross"], gtg, tol)})
    return {"district_id": gt_entry.get("district_id"), "bands": bands, "schools": schools}


def score_run(result: dict, gt: dict, tol=TOL) -> dict:
    """Aggregate scorecard over every district in a run result that has a GT entry."""
    cards = [score_district(result["districts"][did], gt[did], tol)
             for did in result.get("districts", {}) if did in gt]
    allb = [b for c in cards for b in c["bands"]]
    alls = [s for c in cards for s in c["schools"]]
    band_cmp = [b for b in allb if b["status"] in ("hit", "miss")]
    band_hit = [b for b in band_cmp if b["status"] == "hit"]
    matched = [s for s in alls if s["matched"]]
    sch_hit = [s for s in matched if s["hit"]]
    return {
        "cards": cards,
        "bands": {"hit": len(band_hit), "compared": len(band_cmp),
                  "gap": sum(1 for b in allb if b["status"] == "gap"),
                  "extra": sum(1 for b in allb if b["status"] == "extra"),
                  "pct": round(100 * len(band_hit) / len(band_cmp), 1) if band_cmp else None},
        "schools": {"hit": len(sch_hit), "matched": len(matched), "total": len(alls),
                    "pct": round(100 * len(sch_hit) / len(matched), 1) if matched else None},
    }
