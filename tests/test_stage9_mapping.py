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


# ----------------------------- #626 human-vouched + vintage -----------------------------
def test_band_human_vouched_detects_note_only_override():
    # Dickinson's case: a note-only human_override (no times) is still a human vouch.
    assert P.band_human_vouched({"schools": [
        {"school": "a", "human_override": {"reason": "I'm approving", "actor": "ian"}}]}) is True
    assert P.band_human_vouched({"schools": [{"school": "a", "human_added": {"reason": "cited"}}]}) is True
    assert P.band_human_vouched({"schools": [{"school": "a", "override_applied": True}]}) is True
    assert P.band_human_vouched({"schools": [{"school": "a"}]}) is False
    # an override on an EXCLUDED (struck-through) school is not a vouch for the value
    assert P.band_human_vouched({"schools": [
        {"school": "a", "excluded": {"reason": "x"}, "human_override": {"reason": "y"}}]}) is False


def test_vouched_flag_flows_onto_bandwrite():
    receipt = {"bands": {"middle": {
        "gross_minutes": 426, "start_time": None, "end_time": None, "method": "mean_tiebreak",
        "sampling": {}, "schools": [
            {"school": "dickinson", "gross": 426, "human_override": {"reason": "approving"}},
            {"school": "hagen", "gross": 425, "human_override": {"reason": "closed school"}}]}}}
    w = MAP.plan_writes(receipt)[0]
    assert w.human_vouched is True


def test_626_part2_vintage_tracks_the_value_source_not_a_losing_sample():
    # Dickinson middle: value 426 == dickinson's gross (URL has no year); hagen (425) carries a
    # 2016-17 URL. The band's vintage must come from the REPRESENTATIVE (value's source), so hagen's
    # stale URL year is NOT inherited — the band falls through to current-year.
    from infrastructure.utilities.school_year import is_acceptable_data_year, current_school_year
    band = {"gross_minutes": 426, "schools": [
        {"school": "dickinson", "gross": 426, "school_year": None,
         "evidence": {"url": "https://d.k12.nd.us/families/back-to-school"}},
        {"school": "hagen", "gross": 425, "school_year": None,
         "evidence": {"url": "https://d.k12.nd.us/docs/2015-2016/2016-17-HJH-HBook.pdf"}}]}
    year, basis = P.resolve_schedule_year(band, P.collect_source_urls(band))
    assert (year, basis) == (current_school_year(), "default_current")
    assert is_acceptable_data_year(year)


def test_626_part2_representative_url_year_is_kept_when_it_is_the_value_source():
    # Mirror guard: when the REPRESENTATIVE school's own URL carries the year, it IS used (the fix
    # narrows WHICH url sources the year, it doesn't suppress a legitimate representative vintage).
    band = {"gross_minutes": 420, "schools": [
        {"school": "oak", "gross": 420, "school_year": None,
         "evidence": {"url": "https://d.org/2023-24/bell.pdf"}},
        {"school": "elm", "gross": 400, "school_year": None,
         "evidence": {"url": "https://d.org/2016-17/old.pdf"}}]}
    year, basis = P.resolve_schedule_year(band, P.collect_source_urls(band))
    assert (year, basis) == ("2023-24", "content_url")


# ----------------------------- #632 excluded schools & vintage -----------------------------
def test_632_excluded_school_year_does_not_hijack_band_consensus():
    """#632: a struck/excluded school was removed from the band's VALUE, so its stated school_year
    must not enter the precedence-1 band-consensus vintage. Included school states no year; the
    excluded one states 2016-17 → the band falls through to current, never 2016-17."""
    from infrastructure.utilities.school_year import current_school_year
    band = {"gross_minutes": 420, "schools": [
        {"school": "central ms", "gross": 420, "school_year": None,
         "evidence": {"url": "https://d.org/bells"}},
        {"school": "old jh", "gross": 425, "school_year": "2016-17",
         "evidence": {"url": "https://d.org/2016-17/old.pdf"}, "excluded": {"reason": "closed"}}]}
    year, basis = P.resolve_schedule_year(band, P.collect_source_urls(band))
    assert (year, basis) == (current_school_year(), "default_current")


def test_632_excluded_school_url_not_a_source():
    """collect_source_urls' docstring always said INCLUDED schools; #632 made the code enforce it."""
    band = {"schools": [
        {"school": "a", "evidence": {"url": "https://d.org/live"}},
        {"school": "b", "evidence": {"url": "https://d.org/struck"}, "excluded": {"reason": "x"}}]}
    assert P.collect_source_urls(band) == ["https://d.org/live"]


def test_632_included_school_years_still_reach_consensus():
    """Mirror guard: included schools' stated years still form the precedence-1 consensus."""
    band = {"gross_minutes": 400, "schools": [
        {"school": "a", "gross": 400, "school_year": "2024-25"},
        {"school": "b", "gross": 400, "school_year": "2024-25"},
        {"school": "c", "gross": 405, "school_year": "2016-17",
         "excluded": {"reason": "closed"}}]}
    assert P.resolve_schedule_year(band) == ("2024-25", "band_consensus")


# ----------------------------- #631 mapping version -----------------------------
def test_631_mapping_version_exists_and_rides_the_ledger():
    """#631: the idempotency key is (facts fingerprint, MAPPING_VERSION). The constant must exist,
    and ledger.record_incorporation must persist whatever `mapper` it is given so a plain re-run
    after a mapper fix re-writes (source-pinned; the DB round-trip is covered by the govdb suite)."""
    assert isinstance(MAP.MAPPING_VERSION, int) and MAP.MAPPING_VERSION >= 1
    import inspect
    from infrastructure.acquisition.stage9_incorporate import ledger as LG
    assert '"mapper": mapper' in inspect.getsource(LG.record_incorporation)
    from infrastructure.acquisition.stage9_incorporate import incorporate as INC
    src = inspect.getsource(INC.incorporate_district)
    assert 'inc.get("mapper") == MAP.MAPPING_VERSION' in src


# ----------------------------- #638 shared HH:MM parser -----------------------------
def test_638_one_hhmm_parser():
    """#638: aggregate._to_min and provenance's times_consistent both resolve to the ONE
    timeutil.hhmm_to_min (no third private copy)."""
    from infrastructure.acquisition.common.timeutil import hhmm_to_min
    from infrastructure.acquisition.stage8_aggregate import aggregate as AGG
    assert AGG._to_min is hhmm_to_min
    assert hhmm_to_min("07:40") == 460 and hhmm_to_min(None) is None
    assert hhmm_to_min("7:40") == 460 and hhmm_to_min("garbage") is None
    # times_consistent semantics unchanged through the swap
    assert P.times_consistent("07:25", "14:20", 415) is True
    assert P.times_consistent("07:25", "14:20", 425) is False


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
