"""#696 — the three band relations are DISTINCT and each consumer reads the one it declares.

Canonical statement: common/school_sampling.py module docstring. The relations:
  1. PLACEMENT  (school -> ONE band)   school_index()             -> Stage-1 pool / spine
  2. SERVICE    (school -> EVERY band) band_rosters_for_district() -> #253 denominator / slots
  3. GRADE OWN. (grade  -> ONE band)   per_grade                   -> the Stage-9 write

Hermetic (no CCD files, no DB): the shared loader `_district_schools` is monkeypatched with a
Fairbanks-shaped mini district — one PK-08 'Elementary' K-8 plus one 06-08 'Middle' school.
"""
from pathlib import Path

from infrastructure.acquisition.common import school_sampling as SS
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA
from infrastructure.acquisition.stage9_incorporate import per_grade as PG

DID = "0200600"


def _school(sid, name, level, gslo, gshi):
    eff = SS.effective_level_band(level, gslo, gshi)
    return {"school_id": sid, "name": name, "is_charter": "No", "level": level,
            "gslo": gslo, "gshi": gshi, "effective_band": eff,
            "level_overridden": eff != SS.LEVEL_BAND.get(level.strip())}


def _patch_loader(monkeypatch):
    schools = [_school("020060000002", "Ladd Elementary", "Elementary", "PK", "08"),
               _school("020060000275", "Ryan Middle School", "Middle", "06", "08")]
    monkeypatch.setattr(SS, "_district_schools", lambda year: {DID: schools})
    monkeypatch.setattr(SS, "latest_nces_year", lambda: "2024_25")


def test_relation1_placement_is_single_band_but_relation2_roster_serves_both(monkeypatch):
    """THE #696 asymmetry, pinned: the K-8 is PLACED in elementary only (anti-dilution), yet
    SERVES middle in the fillability roster — so middle's pool is 1 school while its denominator
    is 2, and neither number is wrong. (Fairbanks at full scale: pool 4, denominator 12.)"""
    _patch_loader(monkeypatch)
    idx = SS.school_index("2024_25")[DID]
    assert [s["name"] for s in idx["elementary"]] == ["Ladd Elementary"]
    assert [s["name"] for s in idx["middle"]] == ["Ryan Middle School"]   # K-8 NOT placed here

    rosters = SS.band_rosters_for_district(DID, year="2024_25")
    mid = rosters["middle"]
    assert mid["total"] == 2                                               # both SERVE middle
    assert mid["by_source"] == {"level_clean": 1, "grade_span": 1, "level_override": 0}
    assert {r["school_id"] for r in mid["slot_recs"]} == {"020060000002", "020060000275"}


def test_relation3_every_grade_has_exactly_one_canonical_owner():
    owners = {g: PG._canon_band(g) for g in PG.GRADE_TOKENS}
    assert all(b in ("elementary", "middle", "high") for b in owners.values())
    assert owners["06"] == "middle" and owners["05"] == "elementary" and owners["09"] == "high"


# ---------------------- gate@8: the gap is surfaced, not inferable ----------------------
def _fact(band, school, gross):
    start_m, end_m = 8 * 60, 8 * 60 + gross
    import json
    return {"band": band, "school": school, "status": "accepted", "extraction_id": 1,
            "start_time": f"{start_m//60:02d}:{start_m%60:02d}",
            "end_time": f"{end_m//60:02d}:{end_m%60:02d}", "gross_minutes": gross,
            "method": "council_agree", "models_json": json.dumps(["m1", "m2"]),
            "rec_key": f"D:{school}"}


def _rosters_fairbanks_shape():
    """Middle: 4 level_clean (the Stage-1 pool) + 8 grade_span K-8s outside it = 12."""
    pool = [f"02006000{i:04d}" for i in range(4)]
    spanners = [f"02006001{i:04d}" for i in range(8)]
    recs = ([{"school_id": s, "name": f"MS {s[-2:]}", "is_charter": "", "gslo": "06", "gshi": "08",
              "level": "Middle", "effective_band": "middle", "source": "level_clean"} for s in pool]
            + [{"school_id": s, "name": f"K8 {s[-2:]}", "is_charter": "", "gslo": "PK", "gshi": "08",
                "level": "Elementary", "effective_band": "elementary", "source": "grade_span"}
               for s in spanners])
    return {"middle": {"total": 12,
                       "by_source": {"level_clean": 4, "grade_span": 8, "level_override": 0},
                       "schools": [r["name"] for r in recs], "slot_recs": recs},
            "_year": "2024_25"}, pool


def test_n_outside_pool_is_relation2_minus_relation1_and_coverage_stays_honest():
    rosters, pool = _rosters_fairbanks_shape()
    sbb = {"middle": {"schools": [{"school_id": s, "name": f"MS {s[-2:]}"} for s in pool]}}
    acc = [_fact("middle", f"MS {s[-2:]}", 375) for s in pool]
    out = CA.build_closing_argument(
        "D", merged_accepted=acc, merged_unresolved=[], nces_total=30,
        nces_by_level={"Middle": 4}, schools_by_band=sbb, band_rosters=rosters)
    s = out["bands"]["middle"]["sampling"]
    assert s["n_outside_pool"] == 8                     # the 8 K-8s the pipeline never seeks here
    assert s["n_total"] == 12 and s["n_sampled"] == 4
    assert s["coverage"] == round(4 / 12, 3)            # #253's denominator stands — the Santa Fe
    assert s["coverage"] <= 1.0                         # 200%-coverage lie must never come back


def test_n_outside_pool_none_when_either_side_is_unavailable():
    acc = [_fact("middle", "north", 410)]
    # no live roster -> None (a clean-LEVEL fallback denominator has no slot identity to compare)
    out = CA.build_closing_argument(
        "D", merged_accepted=acc, merged_unresolved=[], nces_total=5,
        nces_by_level={"Middle": 2}, schools_by_band={})
    assert out["bands"]["middle"]["sampling"]["n_outside_pool"] is None
    # roster present but NO Stage-1 pool data at all (schools_by_band=None) -> None, not "all outside"
    rosters, _ = _rosters_fairbanks_shape()
    out2 = CA.build_closing_argument(
        "D", merged_accepted=acc, merged_unresolved=[], nces_total=5,
        nces_by_level={"Middle": 2}, schools_by_band=None, band_rosters=rosters)
    assert out2["bands"]["middle"]["sampling"]["n_outside_pool"] is None


def test_gate8_console_renders_the_pool_gap():
    """The UI-visibility rule (static-source pin, the #691 pattern): the structural cap must be an
    explicit note keyed on the server-computed n_outside_pool — a reviewer must be able to tell
    'structurally unreachable' from 'we searched and missed' without reading reason strings."""
    js = (Path(__file__).resolve().parent.parent
          / "infrastructure/acquisition/process_governance/static/stage8.js").read_text()
    assert 'data-feat="pool-gap"' in js
    assert "n_outside_pool" in js                       # renders the server's number, never re-derives
    assert "structurally capped" in js
