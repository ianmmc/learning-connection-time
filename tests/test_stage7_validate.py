"""Stage 7 GT validator (REQ-117, slice 4) — pure scoring, no network/DB. Synthetic run + GT."""
from infrastructure.acquisition.stage7_extract import validate as V


GT = {
    "D1": {"district_id": "D1", "proposal": {
        "elementary": {"_derived_band_gross": 400,
                       "schools": [{"school": "Brick Mill ES/ECC", "gross": 400}]},
        "middle": {"_derived_band_gross": 400, "schools": []},
        "high": {"_derived_band_gross": 395, "schools": [{"school": "essex", "gross": 395}]},
    }},
}


def _run():
    return {"handoff_hash": "h", "districts": {"D1": {
        "district_id": "D1",
        "bands": {
            "elementary": {"gross_minutes": 400},   # hit (== GT 400)
            "middle": {"gross_minutes": 390},        # extra vs GT middle? GT middle=400 -> within 15 -> hit
            "high": {"gross_minutes": 420},          # miss (GT 395, diff 25)
        },
        "accepted": [
            {"band": "elementary", "school": "brick mill esecc", "gross": 400},  # matches GT, hit
            {"band": "high", "school": "essex", "gross": 420},                    # matches GT, miss (395)
            {"band": "elementary", "school": "unknown school", "gross": 410},     # no GT match
        ],
    }}}


def test_band_scoring_hit_miss():
    card = V.score_district(_run()["districts"]["D1"], GT["D1"])
    bands = {b["band"]: b for b in card["bands"]}
    assert bands["elementary"]["status"] == "hit"
    assert bands["high"]["status"] == "miss" and bands["high"]["our"] == 420 and bands["high"]["gt"] == 395
    assert bands["middle"]["status"] == "hit"   # 390 within 15 of 400


def test_band_gap_and_extra():
    # GT has elementary; run omits it -> gap. Run has a band GT lacks -> extra.
    gt = {"D2": {"district_id": "D2", "proposal": {
        "elementary": {"_derived_band_gross": 400, "schools": []}}}}
    run = {"districts": {"D2": {"bands": {"middle": {"gross_minutes": 405}}, "accepted": []}}}
    card = V.score_district(run["districts"]["D2"], gt["D2"])
    st = {b["band"]: b["status"] for b in card["bands"]}
    assert st["elementary"] == "gap" and st["middle"] == "extra"


def test_school_matching_by_shared_norm():
    card = V.score_district(_run()["districts"]["D1"], GT["D1"])
    schools = {s["school"]: s for s in card["schools"]}
    # 'brick mill esecc' matches GT 'Brick Mill ES/ECC' via shared norm_school
    assert schools["brick mill esecc"]["matched"] and schools["brick mill esecc"]["hit"]
    assert schools["essex"]["matched"] and not schools["essex"]["hit"]     # 420 vs 395
    assert not schools["unknown school"]["matched"]


def test_score_run_aggregate():
    card = V.score_run(_run(), GT)
    # bands compared = elementary(hit) + middle(hit) + high(miss) = 3 compared, 2 hit
    assert card["bands"]["compared"] == 3 and card["bands"]["hit"] == 2
    assert card["bands"]["pct"] == round(200 / 3, 1)
    # schools: 2 matched (brick mill, essex), 1 hit
    assert card["schools"]["matched"] == 2 and card["schools"]["hit"] == 1
    assert card["schools"]["total"] == 3


def test_missing_district_skipped():
    run = {"districts": {"ZZ": {"bands": {}, "accepted": []}}}
    assert V.score_run(run, GT)["cards"] == []
