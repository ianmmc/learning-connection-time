"""Stage 9 mapping/provenance — PURE unit tests (no DB, no marker).

Receipts are minted by the real closing_argument.build_closing_argument so the mapping is exercised
against production receipt shapes, not hand-rolled fixtures.
"""
import json

from infrastructure.acquisition.stage8_aggregate import closing_argument as CA
from infrastructure.acquisition.stage9_incorporate import mapping as MAP
from infrastructure.acquisition.stage9_incorporate import provenance as P


def _end(gross):
    return f"{8 + gross // 60:02d}:{gross % 60:02d}"


def _fact(band, school, gross, *, school_year=None, rec_key=None):
    return {"band": band, "school": school, "status": "accepted", "extraction_id": 1,
            "start_time": "08:00", "end_time": _end(gross), "gross_minutes": gross,
            "method": "council_agree", "models_json": json.dumps(["m1", "m2"]),
            "rec_key": rec_key or f"rk:{school}", "school_year": school_year}


def _ca(district_id="9999001", *, accepted, nces_by_level, evidence_by_reckey=None):
    return CA.build_closing_argument(
        district_id, merged_accepted=accepted, merged_unresolved=[],
        nces_total=sum(nces_by_level.values()), nces_by_level=nces_by_level,
        schools_by_band={}, evidence_by_reckey=evidence_by_reckey)


# ----------------------------- council mapping -----------------------------
def test_council_band_maps_to_bell_row():
    ca = _ca(accepted=[_fact("elementary", "oak", 420, school_year="2024-25")],
             nces_by_level={"Elementary": 3})
    writes = MAP.plan_writes(ca, fingerprint="fp123", approval_id=7, actor="ian")
    assert len(writes) == 1
    w = writes[0]
    assert w.grade_level == "elementary"
    assert w.method == "council_extraction" and w.minutes_basis == "gross_bell_to_bell"
    assert w.minutes == 420 and w.start_time == "08:00"
    assert not w.needs_statutory_minutes
    # #95: raw_import carries the re-verify anchors
    assert w.raw_import["facts_fingerprint"] == "fp123"
    assert w.raw_import["approval_id"] == 7
    assert w.raw_import["receipt_band"]["gross_minutes"] == 420
    # notes is machine-parseable JSON
    assert json.loads(w.notes)["stage"] == 9


def test_all_three_bands_written_faithfully():
    ca = _ca(accepted=[_fact("elementary", "oak", 400), _fact("middle", "pine", 430),
                       _fact("high", "elm", 450)],
             nces_by_level={"Elementary": 1, "Middle": 1, "High": 1})
    writes = MAP.plan_writes(ca)
    by_band = {w.grade_level: w for w in writes}
    assert set(by_band) == {"elementary", "middle", "high"}
    # minutes untouched per band — no blending at the write
    assert by_band["elementary"].minutes == 400
    assert by_band["middle"].minutes == 430
    assert by_band["high"].minutes == 450
    assert all(w.method == "council_extraction" for w in writes)


# ----------------------------- #627 frozen mean_tiebreak heal -----------------------------
def test_times_consistent_helper():
    assert P.times_consistent("07:25", "14:20", 415) is True     # span == gross
    assert P.times_consistent("07:25", "14:20", 425) is False    # synthetic mean != span
    assert P.times_consistent(None, "14:20", 425) is True        # absent time -> nothing to contradict
    assert P.times_consistent("07:25", "14:20", None) is True    # no gross -> nothing to contradict


def test_frozen_mean_tiebreak_band_drops_inconsistent_times():
    """#627: a receipt frozen BEFORE the aggregate.py fix carries a mean_tiebreak band with a
    synthetic gross (425) but one school's real times (07:25-14:20, span 415). plan_writes must
    drop those times so the write is minutes-only and passes Stage 9's bell_schedules cross-check;
    the authoritative approved value (425) and the original synthetic band survive."""
    receipt = {"bands": {"middle": {
        "gross_minutes": 425, "start_time": "07:25", "end_time": "14:20", "method": "mean_tiebreak",
        "sampling": {"n_sampled": 2, "n_total": 2, "coverage": 1.0},
        "schools": [{"school": "midview", "start_time": "07:25", "end_time": "14:20", "gross": 415},
                    {"school": "midview east", "start_time": "07:20", "end_time": "14:35", "gross": 435}]}}}
    w = MAP.plan_writes(receipt)[0]
    assert w.minutes == 425
    assert w.start_time is None and w.end_time is None       # inconsistent times dropped
    assert w.raw_import["receipt_band"]["start_time"] == "07:25"   # original band preserved for audit


def test_frozen_modal_band_keeps_consistent_times():
    """Guard the scope: a modal band whose stored times ARE consistent (span == gross) is untouched."""
    receipt = {"bands": {"high": {
        "gross_minutes": 415, "start_time": "07:40", "end_time": "14:35", "method": "modal",
        "sampling": {"n_sampled": 2, "n_total": 2, "coverage": 1.0}, "schools": []}}}
    w = MAP.plan_writes(receipt)[0]
    assert w.minutes == 415 and w.start_time == "07:40" and w.end_time == "14:35"


# ----------------------------- statutory fallback (#94) -----------------------------
def test_unsatisfied_band_maps_to_statutory():
    # High is CLAIMED (NCES has High schools) but has no accepted facts -> unsatisfied.
    ca = _ca(accepted=[_fact("elementary", "oak", 420)],
             nces_by_level={"Elementary": 3, "High": 2})
    assert "high" in ca["negative_space"]["unsatisfied_bands"]
    writes = MAP.plan_writes(ca, fingerprint="fpX", approval_id=1)
    by_band = {w.grade_level: w for w in writes}
    assert by_band["elementary"].method == "council_extraction"
    hi = by_band["high"]
    assert hi.method == "statutory_fallback" and hi.minutes_basis == "statutory"
    assert hi.needs_statutory_minutes and hi.minutes is None      # resolved in the I/O layer
    assert hi.confidence == "low"
    assert hi.statutory_reason in {"no_accepted_facts", "recoverable_sibling_facts"}
    notes = json.loads(hi.notes)
    assert notes["fallback"] is True and notes["reason"] == hi.statutory_reason
    assert hi.raw_import["fallback"] is True


# ----------------------------- year resolution (#582 basis) -----------------------------
def test_year_resolution_consensus():
    band = {"schools": [{"school_year": "2024-25"}, {"school_year": "2024-25"},
                        {"school_year": "2023-24"}]}
    year, basis = P.resolve_schedule_year(band)
    assert (year, basis) == ("2024-25", "band_consensus")


def test_year_resolution_covid_skipped_falls_to_default():
    band = {"schools": [{"school_year": "2020-21"}]}   # COVID — unacceptable, skipped
    year, basis = P.resolve_schedule_year(band)
    assert basis == "default_current"
    from infrastructure.utilities.school_year import is_acceptable_data_year
    assert is_acceptable_data_year(year)               # a real, non-COVID key coordinate


def test_year_resolution_no_signal_is_default_current():
    year, basis = P.resolve_schedule_year({"schools": []})
    assert basis == "default_current"


# ----------------------------- provenance helpers -----------------------------
def test_source_urls_dedup():
    ev = {"rk:oak": {"url": "https://d.org/bell"}, "rk:pine": {"url": "https://d.org/bell"},
          "rk:elm": {"url": "https://d.org/other"}}
    ca = _ca(accepted=[_fact("elementary", "oak", 400, rec_key="rk:oak"),
                       _fact("elementary", "pine", 400, rec_key="rk:pine"),
                       _fact("elementary", "elm", 400, rec_key="rk:elm")],
             nces_by_level={"Elementary": 3}, evidence_by_reckey=ev)
    urls = P.collect_source_urls(ca["bands"]["elementary"])
    assert urls == ["https://d.org/bell", "https://d.org/other"]   # deduped, order-stable


def test_band_confidence_buckets():
    assert P.band_confidence({"coverage": 0.8, "plurality_share": 0.9}) == "high"
    assert P.band_confidence({"coverage": 0.3, "plurality_share": 0.5}) == "medium"
    assert P.band_confidence({"coverage": 0.1, "plurality_share": 1.0}) == "low"
    assert P.band_confidence({"coverage": None, "plurality_share": None}) == "low"


def test_band_grade_span_from_slot_projection():
    # band_grade_span reads the frozen slot_projection (roster-side spans), not the fact side.
    receipt = {"slot_projection": {"middle": {"slots": [
        {"school_id": "S1", "gslo": "06", "gshi": "08", "roster_source": "level_clean"},
        {"school_id": "S2", "gslo": "07", "gshi": "09", "roster_source": "grade_span"},
        {"school_id": "S3", "gslo": None, "gshi": None, "roster_source": "x"},   # no span -> dropped
    ]}}}
    span = P.band_grade_span(receipt, "middle")
    assert span["basis"] == "unhashed (live roster at incorporation)"
    assert span["source"] == "slot_projection"
    assert [s["school_id"] for s in span["slot_spans"]] == ["S1", "S2"]
    assert span["slot_spans"][0]["gslo"] == "06" and span["slot_spans"][0]["gshi"] == "08"


def test_band_grade_span_absent_projection_is_empty():
    span = P.band_grade_span({"bands": {}}, "high")   # no slot_projection (CCD files absent)
    assert span["slot_spans"] == []


# ----------------------------- CLI _load_ids (#607 review: comment filter) -----------------------------
def test_load_ids_ignores_indented_comments(tmp_path):
    from infrastructure.acquisition.stage9_incorporate.__main__ import _load_ids
    f = tmp_path / "ids.txt"
    f.write_text("0100810\n  # an indented comment\n# top comment\n\n  3620580  \n")
    assert _load_ids(str(f)) == ["0100810", "3620580"]
