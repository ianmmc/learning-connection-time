"""#694 — Stage-7 follow-up detection on the school-slot spine, not the per-band boolean.

The asymmetry the issue measured (#692): Stage 8 projects facts onto per-school slots while
Stage 7's district altitude asked only 'does the band have ≥1 fact' — so Cleveland's middle band
(1 of 12 schools heard from) raised nothing. These tests pin the refactor: detection consumes the
gate@8 slot projection via the pure `slot_gap_summary`, pursues a band until it is SATISFIED
(REQ-149) or out of open unfilled slots, names the specific unfilled schools, honors human slot
dispositions, and bounds span-only (#696) targets to MODE_CHECK_MAX assumption checks.

Hermetic: closing-argument-shaped dicts (and the real `slot_spine.project_slots` where the test is
about disposition flow). No DB, no CCD files.
"""
from infrastructure.acquisition.common import slot_spine as SP
from infrastructure.acquisition.stage7_extract import requests as RQ


def _result(district_id="3904378", reps=None, accepted=None):
    return {"district_id": district_id, "reps": reps or [], "accepted": accepted or [],
            "unresolved": [], "bands": {}}


def _slot(sid, name, filled=False):
    return {"school_id": sid, "roster_school": name, "norm_key": name.lower(),
            "gslo": "06", "gshi": "08", "is_charter": "", "roster_source": "level_clean",
            "slot_state": "filled" if filled else "unfilled",
            "match": {"norm_school_fact": name.lower(), "confidence": "matched",
                      "basis": ["exact_name"]} if filled else None}


def _ca(band, slots, *, satisfied=False, assignments=None):
    n_filled = sum(1 for s in slots if s["slot_state"] == "filled")
    ns = {"slot_assignments": assignments} if assignments else {}
    return {"district_id": "D", "negative_space": ns,
            "bands": {band: {"satisfied": {"satisfied": satisfied}}} if n_filled else {},
            "slot_projection": {band: {"slots": slots, "extras": [],
                                       "stats": {"n_slots": len(slots), "n_filled": n_filled,
                                                 "n_projected": 0,
                                                 "n_unfilled": len(slots) - n_filled}}}}


def _cleveland_middle():
    """The #692 measurement's shape: 12 roster slots, exactly 1 heard from, mode nowhere near
    reliable — the population the band-boolean detector structurally could not see."""
    slots = [_slot(f"3904378000{i:02d}", f"MS {i:02d}", filled=(i == 0)) for i in range(12)]
    return _ca("middle", slots, satisfied=False)


# ------------------------- the acceptance case: Cleveland raises, named -------------------------
def test_cleveland_shape_partial_band_raises_followup_naming_unfilled_schools():
    """#694 AC 1 (fails against the pre-#694 detector): middle has a fact ('covered'), so the
    boolean gate skips it — but 11 of 12 slots are open and the band is unsatisfied, so the
    slot-grain gate emits a 7->2 NAMING the unfilled schools."""
    gaps = RQ.slot_gap_summary(_cleveland_middle(),
                               pool_by_band={"middle": {f"3904378000{i:02d}" for i in range(12)}})
    res = _result(accepted=[{"band": "middle", "school": "MS 00"}])
    # pre-#694 behavior, pinned as the contrast: covered -> silent
    assert [r for r in RQ.detect_requests(res, claimed_bands=["middle"], real_bands={"middle"},
                                          covered_bands={"middle"})
            if r["altitude"] == "district"] == []
    reqs = RQ.detect_requests(res, claimed_bands=["middle"], real_bands={"middle"},
                              covered_bands={"middle"}, slot_gaps=gaps)
    band_reqs = [r for r in reqs if r["altitude"] == "district"]
    assert len(band_reqs) == 1
    r = band_reqs[0]
    assert r["route"] == "7->2" and r["band"] == "middle"
    assert len(r["params"]["unfilled_schools"]) == 11                  # named, not counted
    assert {"school_id": "390437800001", "name": "MS 01"} in r["params"]["unfilled_schools"]
    assert r["params"]["n_slots"] == 12 and r["params"]["n_filled"] == 1
    assert "1 of 12 roster slots filled" in r["reason"] and "not satisfied" in r["reason"]


def test_satisfied_band_raises_nothing_and_suppresses_barren_reps():
    """#694 AC 2 (the Fairbanks pin): a band SATISFIED via REQ-149 (reliable plurality) raises no
    follow-up even with open unfilled slots — and with every target band done, barren-rep remedies
    are suppressed too (#170/#176 at slot grain)."""
    slots = [_slot(f"020060000{i:03d}", f"MS {i:03d}", filled=(i < 4)) for i in range(12)]
    gaps = RQ.slot_gap_summary(_ca("middle", slots, satisfied=True))
    res = _result(district_id="0200600",
                  reps=[{"rec_key": "0200600:x", "file": "a.txt", "accepted": []}],
                  accepted=[{"band": "middle", "school": "MS 000"}])
    reqs = RQ.detect_requests(
        res, claimed_bands=["middle"], real_bands={"middle"}, covered_bands={"middle"},
        slot_gaps=gaps,
        alternates_by_rec={"0200600:x": [{"file": "b.png", "kind": "image", "n_times": None}]})
    assert reqs == []


def test_covered_but_unsatisfied_band_keeps_barren_rep_remedies_alive():
    """#694: the slot-grain gate deliberately WIDENS the barren-rep window — a band with facts but
    open gaps keeps its 7->6 (reps in hand are the cheap evidence to try first), and the 7->2 is
    DEFERred behind it (#159), preferring re-reads over new discovery."""
    gaps = RQ.slot_gap_summary(_cleveland_middle())
    res = _result(reps=[{"rec_key": "3904378:hub", "file": "page.txt", "accepted": []}],
                  accepted=[{"band": "middle", "school": "MS 00"}])
    reqs = RQ.detect_requests(
        res, claimed_bands=["middle"], real_bands={"middle"}, covered_bands={"middle"},
        slot_gaps=gaps,
        alternates_by_rec={"3904378:hub": [{"file": "page.pdf.txt", "kind": "text", "n_times": 40}]})
    assert "7->6" in {r["route"] for r in reqs}                      # the in-hand rep re-read
    band = next(r for r in reqs if r["altitude"] == "district")
    assert band["params"]["pending_alt_reps"] == 1 and "DEFER" in band["reason"]


# ------------------------- human dispositions are live inputs (AC 3) -------------------------
def test_reject_dispositioned_slot_generates_no_followup():
    """#694 AC 3a: a slot the human marked `reject` is excluded from targets — when it was the
    band's ONLY open slot, the band reads done and nothing is emitted."""
    slots = [_slot("390437800000", "MS 00", filled=True), _slot("390437800001", "MS 01")]
    asg = [{"band": "middle", "roster_school_id": "390437800001",
            "norm_school_fact": "bogus fact", "disposition": "reject",
            "school": "MS 01", "reason": "not this school", "actor": "ian"}]
    gaps = RQ.slot_gap_summary(_ca("middle", slots, assignments=asg))
    assert gaps["middle"]["n_rejected"] == 1 and gaps["middle"]["unfilled"] == []
    res = _result(accepted=[{"band": "middle", "school": "MS 00"}])
    reqs = RQ.detect_requests(res, claimed_bands=["middle"], real_bands={"middle"},
                              covered_bands={"middle"}, slot_gaps=gaps)
    assert [r for r in reqs if r["altitude"] == "district"] == []


def test_confirm_extra_counts_as_filled_via_the_real_projection():
    """#694 AC 3b, through the REAL `slot_spine.project_slots` (the one-home module): a
    `confirm_extra` becomes a filled human-confirmed slot, so it is never re-chased; the roster's
    genuinely-unheard slot still is."""
    rosters = {"middle": {"total": 2, "slot_recs": [
        {"school_id": "X1", "name": "Jones Middle", "is_charter": "", "gslo": "06", "gshi": "08",
         "level": "Middle", "effective_band": "middle", "source": "level_clean"},
        {"school_id": "X2", "name": "Smith Middle", "is_charter": "", "gslo": "06", "gshi": "08",
         "level": "Middle", "effective_band": "middle", "source": "level_clean"}]}}
    asg = [{"band": "middle", "roster_school_id": "", "norm_school_fact": "annex",
            "disposition": "confirm_extra", "school": "Annex School", "reason": "NCES missed it",
            "actor": "ian", "created_at": "t"}]
    proj = SP.project_slots(rosters, {"middle": [{"school": "Annex School", "rec_key": "D:a"}]},
                            assignments=asg)
    ca = {"district_id": "D", "bands": {}, "negative_space": {"slot_assignments": asg},
          "slot_projection": proj}
    gaps = RQ.slot_gap_summary(ca)
    assert gaps["middle"]["n_filled"] == 1                            # the human-confirmed slot
    names = {u["name"] for u in gaps["middle"]["unfilled"]}
    assert names == {"Jones Middle", "Smith Middle"}                  # never the confirmed extra


# ------------------------- #696: the bounded span-only mode-check class -------------------------
def test_span_only_slots_capped_at_mode_check_max():
    """#694 x #696: unfilled slots OUTSIDE the Stage-1 pool (span-only K-8s) are named only as a
    bounded assumption-check sample — MODE_CHECK_MAX of them, lowest school_id, distinct from the
    pool pursuit list — never a band-filling campaign."""
    slots = ([_slot(f"P{i}", f"MS {i}", filled=(i == 0)) for i in range(4)]        # the pool
             + [_slot(f"K{i}", f"K8 {i}") for i in range(8)])                       # span-only
    gaps = RQ.slot_gap_summary(_ca("middle", slots),
                               pool_by_band={"middle": {f"P{i}" for i in range(4)}})
    res = _result(accepted=[{"band": "middle", "school": "MS 0"}])
    r = next(r for r in RQ.detect_requests(res, claimed_bands=["middle"], real_bands={"middle"},
                                           covered_bands={"middle"}, slot_gaps=gaps)
             if r["altitude"] == "district")
    assert [u["name"] for u in r["params"]["unfilled_schools"]] == ["MS 1", "MS 2", "MS 3"]
    assert [u["school_id"] for u in r["params"]["mode_check_schools"]] == ["K0", "K1"]
    assert len(r["params"]["mode_check_schools"]) == RQ.MODE_CHECK_MAX
    assert "#696" in r["reason"] and "assumption-check" in r["reason"]


def test_pool_unknown_means_no_span_capping():
    """Honest degradation: with no Stage-1 pool for the band, every slot counts as in-pool —
    nothing is silently demoted to the capped class without evidence for it."""
    gaps = RQ.slot_gap_summary(_cleveland_middle())                   # no pool_by_band
    assert all(u["in_pool"] for u in gaps["middle"]["unfilled"])


def test_known_empty_pool_is_all_span_only_and_capped():
    """#703 review: a KNOWN-empty pool (band present in the snapshot, zero schools — Stage 1
    selected nothing for it) is NOT 'unknown': every unfilled slot is outside-pool and the #696
    MODE_CHECK_MAX cap applies. `if pool` (truthiness) collapsed the two — the #702
    absence-vs-empty bug class, one level down."""
    gaps = RQ.slot_gap_summary(_cleveland_middle(), pool_by_band={"middle": set()})
    assert all(not u["in_pool"] for u in gaps["middle"]["unfilled"])
    res = _result(accepted=[{"band": "middle", "school": "MS 00"}])
    r = next(r for r in RQ.detect_requests(res, claimed_bands=["middle"], real_bands={"middle"},
                                           covered_bands={"middle"}, slot_gaps=gaps)
             if r["altitude"] == "district")
    assert r["params"]["unfilled_schools"] == []
    assert len(r["params"]["mode_check_schools"]) == RQ.MODE_CHECK_MAX


def test_stage1_pool_ids_distinguishes_empty_from_absent():
    """The ONE shared pool-membership extraction (#703 review): band with an empty schools list ->
    empty set (KNOWN empty); band absent from the snapshot -> absent from the result (unknown)."""
    from infrastructure.acquisition.common import school_sampling as SS
    pools = SS.stage1_pool_ids({"middle": {"schools": []},
                                "high": {"schools": [{"school_id": "X1"}, {"school_id": None}]}})
    assert pools == {"middle": set(), "high": {"X1"}}
    assert "elementary" not in pools


def test_under_shaped_slot_gaps_degrades_never_keyerrors():
    """#703 review (reproduced pre-fix as a live KeyError): detect_requests must tolerate a
    slot_gaps entry carrying only the keys band_done itself accepts (satisfied/unfilled) —
    an under-shaped input degrades (n_slots/n_filled read 0), never crashes the district's
    detection pass."""
    sg = {"middle": {"satisfied": False,
                     "unfilled": [{"school_id": "a", "name": "A Middle", "in_pool": True}]}}
    res = _result(accepted=[{"band": "middle", "school": "MS 00"}])
    r = next(r for r in RQ.detect_requests(res, claimed_bands=["middle"], real_bands={"middle"},
                                           covered_bands={"middle"}, slot_gaps=sg)
             if r["altitude"] == "district")
    assert r["params"]["n_slots"] == 0 and r["params"]["n_filled"] == 0
    assert r["params"]["unfilled_schools"] == [{"school_id": "a", "name": "A Middle"}]


def test_slot_gaps_for_district_reads_the_shared_ca_cache():
    """#703 review: detect + withdraw (and compose's _gather) share one closing-argument load per
    district via ca_cache — a cache hit must serve the summary without touching the session at
    all (session=None would explode on any DB read)."""
    from infrastructure.acquisition.process_governance import stage7_run as R7
    out = R7._slot_gaps_for_district(None, "3904378", {}, ca_cache={"3904378": _cleveland_middle()})
    assert out["middle"]["n_slots"] == 12 and len(out["middle"]["unfilled"]) == 11


# ------------------------- fitness + degradation -------------------------
def test_band_done_is_the_one_shared_predicate():
    """Emission (detect) and withdrawal (#233) both read `band_done` — slot grain when the band's
    state is known, the covered boolean otherwise. A band missing from the summary falls back."""
    gaps = {"middle": {"satisfied": False,
                       "unfilled": [{"school_id": "a", "name": "A", "in_pool": True}]}}
    assert not RQ.band_done("middle", {"middle"}, gaps)     # covered but NOT done at slot grain
    assert RQ.band_done("middle", {"middle"},
                        {"middle": {"satisfied": True, "unfilled": [{"school_id": "a"}]}})
    assert RQ.band_done("middle", {"middle"}, {"middle": {"satisfied": False, "unfilled": []}})
    assert RQ.band_done("high", {"high"}, gaps)             # band absent -> the legacy boolean
    assert not RQ.band_done("high", set(), gaps)


def test_zero_slot_band_is_omitted_not_done():
    """A projection band with NO roster slots (facts landed as extras — CCD holds nothing for the
    district) carries no slot knowledge: it must be OMITTED from the summary (falling back to the
    covered boolean), never read as 'done because the unfilled list is empty' — absence of data as
    completion, the #702 empty-pool bug class."""
    ca = {"district_id": "D", "bands": {},
          "slot_projection": {"high": {"slots": [], "extras": [{"norm_school_fact": "hs"}],
                                       "stats": {"n_slots": 0, "n_filled": 0, "n_projected": 0,
                                                 "n_unfilled": 0}}}}
    assert RQ.slot_gap_summary(ca) == {}
    assert not RQ.band_done("high", set(), RQ.slot_gap_summary(ca))   # falls back: not covered


def test_summary_none_without_projection_and_detector_falls_back():
    """No slot projection (no live roster) -> summary None -> the detector is EXACTLY the pre-#694
    boolean; every legacy pin in test_stage7_requests.py runs through this path."""
    assert RQ.slot_gap_summary({"district_id": "D", "bands": {}}) is None
    res = _result(accepted=[{"band": "middle", "school": "m"}])
    reqs = RQ.detect_requests(res, claimed_bands=["middle"], real_bands={"middle"},
                              covered_bands={"middle"}, slot_gaps=None)
    assert reqs == []


def test_compose_and_detect_share_the_unfilled_predicate():
    """The one-home fitness (#694 AC 5): `open_unfilled_slots` is the single 'truly unheard'
    predicate — an ambiguous slot (unfilled BUT holding a match awaiting a human) is excluded on
    both sides, and stage7_execute._unfilled_slots_now must route through it (source pin)."""
    from pathlib import Path
    amb = _slot("A1", "Ambig Middle")
    amb["match"] = {"norm_school_fact": "ambig middle", "confidence": "ambiguous",
                    "basis": ["exact_name"], "candidates": []}
    p = {"slots": [amb, _slot("A2", "Open Middle")]}
    assert [s["school_id"] for s in RQ.open_unfilled_slots(p)] == ["A2"]
    src = (Path(__file__).resolve().parent.parent
           / "infrastructure/acquisition/process_governance/stage7_execute.py").read_text()
    assert "RQ.open_unfilled_slots(" in src
