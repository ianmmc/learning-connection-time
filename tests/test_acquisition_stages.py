"""Tests for acquisition stages: sampling/band-classifier (built), topology + waves
(skip stubs until live-wired), GT re-derivation process (REQ-057/058/059); Stage 1 Queue --
exclusion filters, stratified sampling, per-band school selection, LEVEL-primary band
classification, district status registry (REQ-061/062/063/064/065/066/067, built 2026-06-22)."""
import json
import pytest

from infrastructure.acquisition.common import school_sampling as S
from infrastructure.acquisition.stage8_aggregate import aggregate as A
from infrastructure.acquisition.stage1_queue import queue_batch as Q
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.stage2_discover import discover_stage2 as D2
from infrastructure.acquisition.common import discover as DISC
from infrastructure.acquisition.stage3_capture import capture_stage3 as C3
from infrastructure.acquisition.stage4_process import process_stage4 as P4

# This module exercises the live acquisition pipeline against the local NCES CCD dataset (large raw data
# NOT committed to the repo) and, for the CTC class, the LCT Postgres DB — both local-only resources. So
# the whole module is `integration`: it runs locally (`pytest -q`) and is excluded from CI
# (`-m "not integration"`), matching the workflow policy. (A later split could return the pure-logic
# sampling/band-classifier tests to CI in a resource-free module.)
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- REQ-058 sampling
class TestSampling:
    def test_band_classifier_grade_span(self):
        """Grade span -> bands; a K-8 covers elementary AND middle, a 9-12 only high."""
        assert S.bands_for("KG", "05") == {"elementary"}
        assert S.bands_for("06", "08") == {"middle"}
        assert S.bands_for("09", "12") == {"high"}
        assert S.bands_for("KG", "08") == {"elementary", "middle"}   # K-8 spans two
        assert S.bands_for("PK", "12") == {"elementary", "middle", "high"}
        assert S.bands_for("M", "M") == set()                         # ungraded -> no band

    def test_sample_size_censuses_small(self):
        """95/+-5 finite-population: small N is censused; large N capped well below N."""
        assert S.sample_size(1) == 1
        assert S.sample_size(3) == 3
        assert S.sample_size(30) >= 27          # near-census
        assert S.sample_size(900) < 300         # large districts sampled, not censused
        assert S.sample_size(0) == 0


class TestWaves:
    @pytest.mark.skip(reason="live wave orchestration needs the agent (Claude WebSearch subagent); not script-wired - REQ-058")
    def test_wave_order_no_perplexity(self):
        # When wired: assert discovery uses claude -> openrouter only, stop-when-found, no perplexity call.
        ...


# ---------------------------------------------------------------- REQ-057 topology
class TestTopology:
    @pytest.mark.skip(reason="live Haiku topology classification not yet wired; hand labels exist in CURATION_RECONCILED.json - REQ-057")
    def test_topology_label_recorded(self):
        # When wired: assert claude_urls.json carries topology in {hub, per_school, none}.
        ...


# ---------------------------------------------------------------- REQ-060 charter tagging
class TestCharter:
    def test_charter_lookup_from_nces(self):
        """Fairbanks AK (0200600) has known charter schools in its NCES roster -> tagged 'Yes'."""
        look = S.charter_lookup("0200600")
        assert look, "expected NCES schools for Fairbanks"
        assert "Yes" in look.values() and "No" in look.values()   # both present (charters + traditional)

    def test_unmatched_school_is_unknown(self):
        """A school name not in the LEA roster resolves to 'unknown' (caller default), never excluded."""
        look = S.charter_lookup("0200600")
        assert look.get("this school does not exist anywhere", "unknown") == "unknown"


# ---------------------------------------------------------------- REQ-059 GT process
class TestGTProcess:
    def test_band_rederived_from_confirmed_schools(self):
        """The band value is re-derived deterministically from per-school facts (REQ-056),
        not asserted by a model. Mirrors the in-place re-derive used on gt_proposals.json."""
        schools = [
            {"school": "a", "start_time": "08:50", "end_time": "15:10"},  # 380
            {"school": "b", "start_time": "08:50", "end_time": "15:10"},  # 380
            {"school": "c", "start_time": "08:25", "end_time": "14:55"},  # 390
        ]
        grosses = []
        for s in schools:
            st = A._to_min(s["start_time"]); en = A._to_min(s["end_time"])
            grosses.append(en - st)
        val, method = A.aggregate_band(grosses)
        assert val == 380 and method == "modal"   # mode of {380,380,390}, computed in code


# ---------------------------------------------------------------- REQ-061 CTC/shared-service exclusion
@pytest.mark.integration
class TestCTCExclusion:
    def test_known_ctc_flagged(self):
        """Pima County JTED (AZ) -- a real CTC the original name-pattern sweep missed
        ('JTED' doesn't spell 'technical'), caught by the LEA_TYPE_TEXT blanket rule
        (Specialized public school district). Found via a real acquisition batch."""
        from infrastructure.database.connection import session_scope
        from infrastructure.database.models import District
        with session_scope() as session:
            d = session.query(District).filter(District.nces_id == "0400752").first()
            assert d is not None
            assert d.is_shared_service_entity is True

    def test_charter_with_career_branding_not_flagged(self):
        """California Innovative Career Academy District -- an independent charter LEA
        with career/tech branding; must be tagged per REQ-060, never excluded as a CTC."""
        from infrastructure.database.connection import session_scope
        from infrastructure.database.models import District
        with session_scope() as session:
            d = session.query(District).filter(District.nces_id == "0602509").first()
            assert d is not None
            assert d.is_shared_service_entity is False


# ---------------------------------------------------------------- REQ-062 pre-queue district filters
@pytest.mark.integration
@pytest.mark.slow
class TestPreQueueExclusion:
    def test_grade_span_gap_excludes_phantom_lea(self):
        """Alabama Youth Services claims KG-12 at LEA level but has zero schools listed
        anywhere in ccd_sch_029 (not even closed ones) -- a real data-integrity gap
        (Rule 7), not a bug. Must be excluded from the eligible pool."""
        registry = {"districts": {}}   # pre-queue-filter tests: attempt-state is irrelevant (REQ-099 made load() DB-backed)
        pool, _, gap_excluded = Q.eligible_pool("2024_25", registry)
        gap_ids = {g["district_id"] for g in gap_excluded}
        assert "0100002" in gap_ids
        assert "0100002" not in pool

    def test_healthy_district_is_eligible(self):
        """Fairbanks (a normal, fully-graded, non-CTC, operating district) must pass
        every pre-queue filter and appear in the eligible pool."""
        registry = {"districts": {}}   # pre-queue-filter tests: attempt-state is irrelevant (REQ-099 made load() DB-backed)
        pool, _, _ = Q.eligible_pool("2024_25", registry)
        assert "0200600" in pool

    def test_stage1_only_district_stays_eligible_for_redraw(self):
        """A district that only reached Stage 1 (queued, never captured) must remain in
        the eligible pool -- excluding on ANY recorded stage silently dropped every
        district from a never-captured batch on re-queue after a queue-time bug fix
        (found 2026-06-22). Only Stage 3 (Capture)+ represents a real attempt."""
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        DS.record_stage(registry, "0200600", "Fairbanks", "AK", stage=1, stage_name="queue", outcome="queued")
        pool, _, _ = Q.eligible_pool("2024_25", registry)
        assert "0200600" in pool

    def test_captured_district_is_excluded_from_redraw(self):
        """A district that reached Stage 3 (Capture) is a real attempt -- it must be
        excluded from the eligible pool regardless of outcome."""
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        DS.record_stage(registry, "0200600", "Fairbanks", "AK", stage=3, stage_name="capture", outcome="captured")
        pool, _, _ = Q.eligible_pool("2024_25", registry)
        assert "0200600" not in pool


# ---------------------------------------------------------------- REQ-102 build_batch callable (gate@1 console + CLI share it)
class TestBuildBatch:
    """build_batch() is the pure batch-construction callable the gate@1 console 'create'
    action and the CLI both invoke (the §7a-B 'orchestration = functions' model). It must
    assemble a well-formed batch_doc and do NO I/O (no file write, no registry mutation) --
    persist_batch() is the only place side effects happen."""

    BAND_KEYS = {"district_id", "name", "state", "domain", "enrollment_k12",
                 "lea_claimed_bands", "nces_school_counts", "band_processing_order", "schools_by_band"}

    def test_assembles_valid_doc_without_io(self):
        registry = {"districts": {}}
        bid = "batch_test_build_batch"
        batch_doc, gap_excluded, n_eligible = Q.build_batch("2024_25", n=6, batch_id=bid, registry=registry)

        # shape
        assert batch_doc["batch_id"] == bid
        assert batch_doc["nces_year"] == "2024_25"
        assert batch_doc["school_cap_per_band"] == Q.CAP
        assert 0 < batch_doc["n"] == len(batch_doc["districts"]) <= 6
        for d in batch_doc["districts"]:
            assert self.BAND_KEYS <= set(d), f"missing keys: {self.BAND_KEYS - set(d)}"
            assert set(d["schools_by_band"]) <= set(Q.BANDS)
        assert isinstance(gap_excluded, list)
        assert n_eligible > 0

        # purity: no batch file written, registry untouched (build_batch only READS the registry)
        assert not (Q.OUT_DIR / f"{bid}.json").exists(), "build_batch must not write the batch file"
        assert registry == {"districts": {}}, "build_batch must not mutate the registry"

    def test_reproducible_district_selection(self):
        """Same batch_id + same registry must select the identical districts (seeded) --
        batches are logged and repeatable, not silently random."""
        reg = {"districts": {}}
        a, _, _ = Q.build_batch("2024_25", n=6, batch_id="batch_test_bb_repro", registry=reg)
        b, _, _ = Q.build_batch("2024_25", n=6, batch_id="batch_test_bb_repro", registry=reg)
        assert [d["district_id"] for d in a["districts"]] == [d["district_id"] for d in b["districts"]]


# ---------------------------------------------------------------- REQ-063 enrollment-quartile sampling
class TestStratifiedSampling:
    def test_spans_enrollment_range_no_duplicates(self):
        """12 picks from a synthetic 40-district pool should span the enrollment range
        (not cluster in one quartile) and never repeat a district."""
        states = ["AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID"]
        pool = {f"D{i:03d}": {"enrollment_k12": (i + 1) * 100, "state": states[i % len(states)]} for i in range(40)}
        picked = Q.stratified_pick(pool, "batch_test", n=12)
        assert len(picked) == 12
        assert len(set(picked)) == 12
        enrollments = sorted(pool[d]["enrollment_k12"] for d in picked)
        assert enrollments[0] < 1000 and enrollments[-1] > 3000

    def test_reproducible_with_same_seed(self):
        """Same pool + same batch_id must yield the identical pick -- batches are
        logged and repeatable, not silently random."""
        pool = {f"D{i:03d}": {"enrollment_k12": (i + 1) * 50, "state": "ZZ"} for i in range(20)}
        a = Q.stratified_pick(pool, "batch_repro", n=8)
        b = Q.stratified_pick(pool, "batch_repro", n=8)
        assert a == b

    def test_tops_up_when_pool_smaller_than_n(self):
        """A pool with fewer eligible districts than the batch target returns everything
        available rather than erroring or padding with duplicates."""
        pool = {f"D{i:03d}": {"enrollment_k12": 100, "state": "ZZ"} for i in range(5)}
        picked = Q.stratified_pick(pool, "batch_small", n=12)
        assert len(picked) == 5


# ---------------------------------------------------------------- REQ-064 per-band school selection
class TestPerBandSchoolSelection:
    def test_most_constrained_first_minimizes_overlap(self):
        """Mirrors the real Fairbanks validation: a school shared between two bands is
        only reused when the unclaimed pool can't fill the cap, and the most-constrained
        (fewest-candidate) band processes first."""
        shared_id = "shared1"
        idx = {
            "high": [{"school_id": shared_id}] + [{"school_id": f"h{i}"} for i in range(8)],  # 9 total
            "middle": [{"school_id": shared_id}] + [{"school_id": f"m{i}"} for i in range(10)],  # 11 total
            "elementary": [{"school_id": f"e{i}"} for i in range(23)],  # 23 total, over cap
        }
        order, result = Q.select_schools("batch_test", "D001", idx, cap=12)

        assert order[0] == "high"  # fewest candidates (9) -> most constrained -> first
        assert result["high"]["n_selected"] == 9  # under cap, full census
        assert shared_id in {s["school_id"] for s in result["high"]["schools"]}

        # middle: 11 total, 1 already claimed by high -> 10 unclaimed, needs the cap (12)
        # but only has 11 total candidates -> selects all 11, including the forced reuse
        assert result["middle"]["n_selected"] == 11
        assert shared_id in {s["school_id"] for s in result["middle"]["schools"]}

        # elementary: no overlap with anything, capped at 12 of its 23 candidates
        assert result["elementary"]["n_selected"] == 12
        assert shared_id not in {s["school_id"] for s in result["elementary"]["schools"]}

    def test_seeded_sample_is_reproducible(self):
        idx = {"elementary": [{"school_id": f"e{i}"} for i in range(20)]}
        _, r1 = Q.select_schools("batch_x", "D002", idx, cap=12)
        _, r2 = Q.select_schools("batch_x", "D002", idx, cap=12)
        assert r1["elementary"]["schools"] == r2["elementary"]["schools"]


# ------------------------------------------------------- REQ-065 school-level eligibility filtering
class TestSchoolEligibilityFiltering:
    def test_alternative_school_excluded(self):
        """Olympic Peninsula HomeConnection (SCH_TYPE_TEXT=Alternative School, a homeschool-
        umbrella program) must not appear anywhere in Crescent SD's candidate index."""
        idx = S.school_index("2024_25")
        ids = {s["school_id"] for band in idx.get("5301830", {}).values() for s in band}
        assert "530183002942" not in ids

    def test_career_technical_school_excluded(self):
        """Jackson County Vocational Center (SCH_TYPE_TEXT=Career and Technical School) --
        a school-level CTC invisible to the LEA-level Rule 6 exclusion -- must not appear."""
        idx = S.school_index("2024_25")
        ids = {s["school_id"] for band in idx.get("2802160", {}).values() for s in band}
        assert "280216001051" not in ids

    def test_standalone_preschool_excluded(self):
        """Lake Preschool (GSLO=GSHI=PK, no K+ grades) must not appear in Gunnison
        Watershed's elementary candidates."""
        idx = S.school_index("2024_25")
        ids = {s["school_id"] for band in idx.get("0804470", {}).values() for s in band}
        assert "080447001689" not in ids


# ------------------------------------------------------- REQ-066 LEVEL-primary band classification
class TestLevelPrimaryBandClassification:
    def test_grade_13_counts_as_high(self):
        """Grade 13 is a real, sanctioned NCES code (some states use it for a
        continuation/extra-year high school program) -- must count as high, not vanish."""
        assert S.bands_for("09", "13") == {"high"}

    def test_dilution_fixed_fayette_county(self):
        """Connersville Middle School must be the ONLY middle candidate in Fayette
        County IN -- the district's 5 K-6 elementary schools must NOT also dilute the
        pool just because grade 6 clips the middle boundary."""
        idx = S.school_index("2024_25")
        names = {s["name"] for s in idx.get("1803510", {}).get("middle", [])}
        assert names == {"Connersville Middle School"}

    def test_no_middle_level_school_rescues_via_grade_range(self):
        """Calhan CO has no school literally labeled Middle (only a K-5 Elementary and a
        06-12 'High'-labeled combined secondary) -- the secondary must still be rescued
        into the middle band via grade-range fallback, or Rule 7 would false-positive."""
        idx = S.school_index("2024_25")
        names = {s["name"] for s in idx.get("0802730", {}).get("middle", [])}
        assert "Calhan Secondary School" in names

    def test_misnamed_elementary_with_middle_level_goes_to_middle_only(self):
        """Hammarskjold Upper Elementary is named like an elementary school but NCES
        LEVEL is actually Middle (grades 5-6) -- LEVEL wins: excluded from elementary,
        included in middle."""
        idx = S.school_index("2024_25")
        elem_names = {s["name"] for s in idx.get("3404110", {}).get("elementary", [])}
        middle_names = {s["name"] for s in idx.get("3404110", {}).get("middle", [])}
        assert "Hammarskjold Upper Elementary School" not in elem_names
        assert "Hammarskjold Upper Elementary School" in middle_names

    def test_two_segment_partition_middle_high_merge(self):
        """Jasper Co. MO has exactly 2 schools forming a clean partition: KG-06 elementary,
        07-12 high. recursive_band_groups() resolves this as elem={KG-06}, middle+high
        merged into the secondary (07-12) -- the elementary must NOT also appear in middle
        just because grade 6 lives in its building."""
        idx = S.school_index("2024_25")
        middle_names = {s["name"] for s in idx.get("2916140", {}).get("middle", [])}
        assert middle_names == {"Jasper Co. High School"}

    def test_redundant_overlapping_spans_keep_any_overlap_fallback(self):
        """Breathitt County KY's elementary spans are genuinely redundant/overlapping
        (PK-02, 03-06, AND PK-06, where PK-06 subsumes the other two) -- not a clean
        ascending partition, so recursive_band_groups() returns None and the conservative
        any-overlap rescue (bands_for_rescue()) applies. Sebastian and Highland-Turner
        Elementary both top out at grade 6 -- pure elementary, same distinction the
        West Bonner fix established -- so middle's sole representative is Breathitt
        County High School (07-12), which actually reaches grade 7."""
        idx = S.school_index("2024_25")
        middle_names = {s["name"] for s in idx.get("2100690", {}).get("middle", [])}
        assert middle_names == {"Breathitt County High School"}

    def test_identical_span_multi_building_partition_now_resolved(self):
        """Northern Tioga PA has 3 elementaries all spanning the IDENTICAL KG-06 and 2
        secondaries both spanning the IDENTICAL 07-12 -- collapsed to distinct spans, this
        is the SAME clean 2-segment shape as Jasper Co. (just multiple buildings per side),
        so it now gets the same fix: both elementaries must be excluded from middle, both
        secondaries must represent middle+high. Earlier in this project's history this
        district was incorrectly believed to need different treatment from Jasper Co. --
        recursive_band_groups() correctly treats them identically."""
        idx = S.school_index("2024_25")
        middle_names = {s["name"] for s in idx.get("4217730", {}).get("middle", [])}
        assert middle_names == {"Cowanesque Valley JSHS", "Williamson SHS"}

    def test_ambiguous_level_school_spanning_full_range_gets_all_bands(self):
        """Universal Academy MI is a single KG-12 school with LEVEL=Other (ambiguous) --
        with no other schools to form a multi-segment partition, it must represent all
        three bands, the same as if it had been resolved as a trivial N=1 case."""
        idx = S.school_index("2024_25")
        for band in ("elementary", "middle", "high"):
            names = {s["name"] for s in idx.get("2600237", {}).get(band, [])}
            assert names == {"Universal Academy"}

    def test_ambiguous_school_joins_already_populated_band(self):
        """Aledo ISD TX has a clean LEVEL=High main campus (10-12) PLUS a LEVEL=Secondary
        (ambiguous) 9th-grade campus (09-09) -- the recursive grouping places both in high.
        The ambiguous campus must NOT be dropped just because high already had a LEVEL-clean
        school; a LEVEL-clean school, by contrast, must never be added to an extra band this
        way (that would reintroduce the original dilution bug)."""
        idx = S.school_index("2024_25")
        high_names = {s["name"] for s in idx.get("4807780", {}).get("high", [])}
        assert high_names == {"ALEDO H S", "DON R DANIEL NINTH GRADE CAMPUS"}

    def test_k8_feeder_district_has_no_high_band(self):
        """Lemont-Bromberek CSD 113A IL is a real K-8 feeder district (no high school of its
        own -- students attend a separate high school district). The lone segment remaining
        after elementary (06-08) must resolve to middle alone, not be forced into
        middle+high just because it's the last segment -- there's nothing for high here."""
        idx = S.school_index("2024_25")
        middle_names = {s["name"] for s in idx.get("1707290", {}).get("middle", [])}
        high_names = {s["name"] for s in idx.get("1707290", {}).get("high", [])}
        assert middle_names == {"Old Quarry Middle Sch"}
        assert high_names == set()

    def test_lone_secondary_segment_does_not_join_elementary(self):
        """The Bridge Academy (CT) is a single LEVEL=High, 07-12 school -- the district's
        only segment. The old position-based rule put segment[0] in elementary
        unconditionally whenever no leading <=6-top run existed (designed for a K-12
        'Other'-LEVEL school where that's correct); here it wrongly pulled a 07-12 HIGH
        school into the elementary candidate pool just because it was first. The
        per-segment overlap check must check the segment's own span, not its position --
        07-12 doesn't start in elementary's range, so elementary must be empty."""
        idx = S.school_index("2024_25")
        for band in ("elementary", "middle", "high"):
            names = {s["name"] for s in idx.get("0900015", {}).get(band, [])}
            if band == "elementary":
                assert names == set()
            else:
                assert names == {"The Bridge Academy"}

    def test_trailing_segment_stays_middle_not_high_by_position(self):
        """Sequoia Union Elementary (CA) has a LEVEL=Elementary KG-07 school and a
        LEVEL=Middle 08-08 school (confusingly named '...Elementary' despite its LEVEL).
        The old rule treated everything after an elem+middle-merged leading segment as
        unconditionally 'high'; the 08-08 segment doesn't reach grade 9, so it must
        resolve to middle, not be pulled into the high band just for coming last."""
        idx = S.school_index("2024_25")
        middle_names = {s["name"] for s in idx.get("0636360", {}).get("middle", [])}
        high_names = {s["name"] for s in idx.get("0636360", {}).get("high", [])}
        assert middle_names == {"Sequoia Union Elementary"}
        assert high_names == set()

    def test_pk08_elementary_does_not_over_claim_into_trailing_high(self):
        """Quitman County (GA) has a LEVEL=Elementary PK-08 school (covers elementary AND
        middle) followed by a LEVEL=High 09-12 school. The 09-12 high school must NOT also
        be pulled into middle just because it immediately follows a middle-covering
        segment -- middle's sole representative is the PK-08 elementary, not the high
        school."""
        idx = S.school_index("2024_25")
        middle_names = {s["name"] for s in idx.get("1304290", {}).get("middle", [])}
        high_names = {s["name"] for s in idx.get("1304290", {}).get("high", [])}
        assert middle_names == {"Quitman County Elementary"}
        assert high_names == {"Quitman County High School"}


# --------------------------------------------------- REQ-065 (extended) early-childhood exclusion
class TestEarlyChildhoodExclusion:
    def test_pk_kg_only_center_excluded(self):
        """Clinton County Early Childhood Center (GSLO=PK, GSHI=KG, no grade 1+) must not
        appear in Clinton County's elementary candidates -- same rationale as standalone
        preschools (Lake Preschool, GSHI=PK), extended to GSHI=KG."""
        idx = S.school_index("2024_25")
        ids = {s["school_id"] for band in idx.get("2101260", {}).values() for s in band}
        assert "210126002228" not in ids

    def test_normal_k5_school_not_excluded(self):
        """A normal K-5 (or similar) elementary that merely OFFERS PK alongside K-5 must
        still count normally -- the exclusion is narrowly about a school whose HIGHEST
        grade is still PK or KG, not any PK/KG-serving school."""
        idx = S.school_index("2024_25")
        names = {s["name"] for s in idx.get("2101260", {}).get("elementary", [])}
        assert "Albany Elementary School" in names


# -------------------------------------------------------------------- virtual school exclusion
class TestVirtualSchoolExclusion:
    def test_exclusively_virtual_school_excluded(self):
        """Virginia Connections Academy (a Pearson-operated full-virtual school, NCES
        VIRTUAL_TEXT='Exclusively virtual') has no real in-person bell-to-bell day -- must
        not appear in Scott County VA's candidate pool for any band."""
        idx = S.school_index("2024_25")
        ids = {s["school_id"] for band in idx.get("5103480", {}).values() for s in band}
        assert "510348003096" not in ids

    def test_supplemental_virtual_school_not_excluded(self):
        """A normal in-person school that merely OFFERS a supplemental virtual option
        (NCES VIRTUAL_TEXT='Supplemental Virtual') still has a real bell schedule and must
        NOT be excluded -- only majority/exclusively-virtual schools are."""
        idx = S.school_index("2024_25")
        names = {s["name"] for s in idx.get("0200120", {}).get("elementary", [])}
        assert "Dillingham Elementary" in names


# -------------------------------------------------------------------- REQ-066 any-overlap rescue
class TestAnyOverlapRescueMiddleBoundary:
    def test_grade6_topping_school_not_rescued_into_middle(self):
        """West Bonner County ID has a genuinely messy, non-clean-partition shape (3
        overlapping/redundant elementary spans: PK-06, PK-06, PK-07). IDAHO HILL and
        PRIEST RIVER ELEMENTARY (both PK-06) must NOT be rescued into middle just because
        grade 6 sits in BANDS['middle']'s nominal 6-8 range -- they top out at 6, the same
        'pure elementary' distinction recursive_band_groups() already makes for clean
        partitions. PRIEST LAKE ELEMENTARY (PK-07) and PRIEST RIVER LAMANNA HIGH (07-12)
        DO reach grade 7 and correctly remain in middle."""
        idx = S.school_index("2024_25")
        middle_names = {s["name"] for s in idx.get("1600001", {}).get("middle", [])}
        assert middle_names == {"PRIEST LAKE ELEMENTARY SCHOOL", "PRIEST RIVER LAMANNA HIGH"}


# ---------------------------------------------------------------- REQ-067 district status registry
class TestDistrictStatusRegistry:
    def test_record_and_check_attempted(self):
        """already_attempted() only fires once a district reaches Stage 3 (Capture) --
        Stage 1 (queue) alone is not a real, costly attempt (found 2026-06-22: excluding
        on ANY stage silently dropped every district from a never-captured batch on
        re-queue, masking a queue-time bug fix instead of demonstrating it)."""
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        assert not DS.already_attempted(registry, "0200600")
        DS.record_stage(registry, "0200600", "Fairbanks", "AK", stage=1, stage_name="queue",
                         outcome="queued", batch_id="batch_00001")
        assert registry["districts"]["0200600"]["furthest_stage"] == 1
        assert len(registry["districts"]["0200600"]["history"]) == 1
        assert not DS.already_attempted(registry, "0200600")  # Stage 1 only -- still eligible for redraw
        DS.record_stage(registry, "0200600", "Fairbanks", "AK", stage=3, stage_name="capture",
                         outcome="captured")
        assert DS.already_attempted(registry, "0200600")  # Stage 3 reached -- now excluded

    def test_history_accumulates_across_stages(self):
        """Pre-queue exclusions are deliberately never recorded here -- this test only
        covers districts that entered the pipeline, per ACQUISITION_PIPELINE.md Stage 1."""
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        DS.record_stage(registry, "0200600", "Fairbanks", "AK", stage=1, stage_name="queue", outcome="queued")
        DS.record_stage(registry, "0200600", "Fairbanks", "AK", stage=2, stage_name="discover",
                         outcome="found_hub", topology="hub")
        d = registry["districts"]["0200600"]
        assert d["furthest_stage"] == 2
        assert d["topology"] == "hub"
        assert len(d["history"]) == 2


# ------------------------------------------------------------------------ Stage 2 (Discover)
def _synthetic_district():
    """A synthetic batch-file district entry: one elementary-only school, one school
    spanning BOTH middle and high (to exercise build_roster's per-school_id dedup)."""
    return {
        "district_id": "9999999", "name": "Test Schools District", "state": "ZZ",
        "domain": "testschools.example",
        "schools_by_band": {
            "elementary": {"schools": [
                {"school_id": "9999999001", "name": "Test Elementary", "level": "Elementary"}
            ]},
            "middle": {"schools": [
                {"school_id": "9999999002", "name": "Test MS/HS", "level": "Secondary"}
            ]},
            "high": {"schools": [
                {"school_id": "9999999002", "name": "Test MS/HS", "level": "Secondary"}
            ]},
        },
    }


class TestSlugAndDir:
    def test_slugify_collapses_punctuation(self):
        assert D2.slugify("Mt. Abraham Unified School District #61!!") == "mt_abraham_unified_school_district_61"

    def test_slugify_truncates_long_names(self):
        slug = D2.slugify("NEW YORK CITY GEOGRAPHIC DISTRICT #14 - A VERY LONG DISTRICT NAME")
        assert len(slug) <= 40

    def test_lea_dir_prefixes_district_id(self):
        assert D2.lea_dir("2600992", "Blue Water Middle College") == \
            D2.RAW_DIR / "2600992_blue_water_middle_college"

    def test_raw_dir_is_repo_anchored_not_cwd_relative(self):
        """RAW_DIR must be an absolute, repo-anchored path -- the governance server reads the
        same discovery.json/candidates.json and must agree on the location regardless of the
        launch directory (the gate@1 create 500'd on exactly this CWD-relative bug class).
        Asserts the STRUCTURE (absolute + the data/raw/lea-website-captures suffix) rather than
        identity with paths.RAW_CAPTURES, which other tests legitimately repoint to a tmp DATA_ROOT."""
        assert D2.RAW_DIR.is_absolute()
        assert D2.RAW_DIR.parts[-3:] == ("data", "raw", "lea-website-captures")


class TestRosterBuilding:
    def test_multi_band_school_dedups_to_one_row_with_both_bands(self):
        roster = D2.build_roster(_synthetic_district())
        by_id = {r["school_id"]: r for r in roster}
        assert len(roster) == 2
        assert sorted(by_id["9999999002"]["bands"]) == ["high", "middle"]
        assert by_id["9999999001"]["bands"] == ["elementary"]

    def test_query_includes_school_and_state_not_district_or_year(self):
        roster = D2.build_roster(_synthetic_district())
        q = next(r["query"] for r in roster if r["school_id"] == "9999999001")
        assert q == "Test Elementary ZZ bell schedule start and end times"


class TestReconcile:
    def test_district_with_no_disk_artifact_and_no_registry_entry_is_todo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        batch = {"batch_id": "batch_00099", "districts": [_synthetic_district()]}
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        todo, skipped = D2.reconcile(batch, registry)
        assert [d["district_id"] for d in todo] == ["9999999"]
        assert skipped == []

    def test_disk_ahead_of_registry_reconciles_up_and_skips(self, tmp_path, monkeypatch):
        """Found 2026-06-23 design session: a district can complete Stage 2 (discovery.json
        written) without the registry ever having been told -- the filesystem is the real
        fact, so the registry must catch up to it, not the other way around."""
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        d = _synthetic_district()
        D2.lea_dir(d["district_id"], d["name"]).mkdir(parents=True)
        (D2.lea_dir(d["district_id"], d["name"]) / "discovery.json").write_text("{}")
        batch = {"batch_id": "batch_00099", "districts": [d]}
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        todo, skipped = D2.reconcile(batch, registry)
        assert todo == []
        assert [x["district_id"] for x in skipped] == ["9999999"]
        assert registry["districts"]["9999999"]["furthest_stage"] == 2

    def test_registry_ahead_of_disk_halts_the_entire_run(self, tmp_path, monkeypatch):
        """The converse drift: registry claims Stage 2 done but the file doesn't exist.
        This is a control failure (lost data, wrong path, bad migration), not routine
        drift -- must stop everything rather than silently resample or silently trust."""
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        d = _synthetic_district()
        batch = {"batch_id": "batch_00099", "districts": [d]}
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        DS.record_stage(registry, d["district_id"], d["name"], d["state"],
                         stage=2, stage_name="discover", outcome="found_all")
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            D2.reconcile(batch, registry)


class TestWave1Handoff:
    def test_matching_district_id_and_domain_passes(self):
        d = _synthetic_district()
        raw = {"district_id": "9999999", "domain": "testschools.example", "schools": []}
        assert D2.validate_wave1_result(raw, d) is raw

    def test_mismatched_district_id_fails_loud(self):
        d = _synthetic_district()
        raw = {"district_id": "0000000", "domain": "testschools.example", "schools": []}
        with pytest.raises(SystemExit, match="district_id mismatch"):
            D2.validate_wave1_result(raw, d)

    def test_mismatched_domain_fails_loud(self):
        """The domain echo is the whole point of carrying the NCES seed alongside the
        subagent's findings -- a mismatch here means the subagent searched the wrong
        site, and that must never be silently accepted into discovery.json."""
        d = _synthetic_district()
        raw = {"district_id": "9999999", "domain": "wrongsite.example", "schools": []}
        with pytest.raises(SystemExit, match="domain mismatch"):
            D2.validate_wave1_result(raw, d)

    def test_merge_attaches_urls_by_school_id_missing_school_gets_empty(self):
        roster = D2.build_roster(_synthetic_district())
        raw = {"district_id": "9999999", "domain": "testschools.example",
               "schools": [{"school_id": "9999999001", "urls": ["https://testschools.example/elem-bell.pdf"]}]}
        merged = D2.merge_wave1(roster, raw, "testschools.example")
        by_id = {r["school_id"]: r for r in merged}
        assert by_id["9999999001"]["wave1_raw_urls"] == ["https://testschools.example/elem-bell.pdf"]
        assert by_id["9999999001"]["wave1_gated"][0]["kept"] is True
        assert by_id["9999999002"]["wave1_raw_urls"] == []
        assert by_id["9999999002"]["wave1_gated"] == []


class TestResidualAndWave2Gating:
    def test_school_with_kept_wave1_candidate_is_not_residual(self):
        roster = [{"school": "A", "wave1_gated": [{"url": "u", "kept": True, "reason": "on-domain"}]}]
        assert D2.residual_schools(roster) == []

    def test_school_with_zero_kept_candidates_is_residual(self):
        roster = [{"school": "A", "wave1_gated": [{"url": "u", "kept": False, "reason": "off-district"}]},
                  {"school": "B", "wave1_gated": []}]
        assert len(D2.residual_schools(roster)) == 2


def _api_status_error(status_code):
    import openai, httpx
    resp = httpx.Response(status_code, request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    return openai.APIStatusError(f"HTTP {status_code}", response=resp, body=None)


class TestOpenRouterBillingFailure:
    """A billing/auth/rate-limit failure means the call was never really attempted -- every
    later Wave 2 call would fail identically, so it must never be silently treated the same
    as 'the search legitimately found nothing' (found 2026-06-23: any exception, including a
    402 insufficient-balance error, was being caught generically and degraded to urls=[])."""

    def test_billing_status_code_raises_system_exit(self, monkeypatch):
        import openai as openai_module

        class FakeCompletions:
            def create(self, **kwargs):
                raise _api_status_error(402)

        class FakeClient:
            def __init__(self, **kwargs):
                self.chat = type("C", (), {"completions": FakeCompletions()})()

        monkeypatch.setattr(openai_module, "OpenAI", FakeClient)
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            DISC.openrouter_search("query", "example.org")

    def test_non_billing_status_code_propagates_as_plain_exception(self, monkeypatch):
        """A 500 (transient server error) is NOT a billing/auth signal -- it must propagate
        as the original APIStatusError, not SystemExit, so callers can still distinguish
        'OpenRouter itself errored' from 'CONTROL FAILURE, halt everything' if they choose to."""
        import openai as openai_module

        class FakeCompletions:
            def create(self, **kwargs):
                raise _api_status_error(500)

        class FakeClient:
            def __init__(self, **kwargs):
                self.chat = type("C", (), {"completions": FakeCompletions()})()

        monkeypatch.setattr(openai_module, "OpenAI", FakeClient)
        with pytest.raises(openai_module.APIStatusError):
            DISC.openrouter_search("query", "example.org")

    def test_429_is_transient_not_a_halt(self, monkeypatch):
        """Issue #29: 429 was split out of the billing/auth halt set -- a rate-limit is
        transient, so it propagates as the plain APIStatusError (per-school degrade)."""
        import openai as openai_module

        class FakeCompletions:
            def create(self, **kwargs):
                raise _api_status_error(429)

        class FakeClient:
            def __init__(self, **kwargs):
                self.chat = type("C", (), {"completions": FakeCompletions()})()

        monkeypatch.setattr(openai_module, "OpenAI", FakeClient)
        with pytest.raises(openai_module.APIStatusError):
            DISC.openrouter_search("query", "example.org")

    def test_run_wave2_requires_an_explicit_provider(self):
        """Issue #41: the old default (the retired openrouter_search, ~$27/1K) is gone --
        search_fn is a required parameter, so no code path can reach the paid provider silently."""
        import inspect
        param = inspect.signature(D2.run_wave2).parameters["search_fn"]
        assert param.default is inspect.Parameter.empty

    def test_run_wave2_does_not_swallow_a_billing_system_exit(self):
        """run_wave2's `except Exception` must not catch a billing-failure SystemExit --
        SystemExit isn't an Exception subclass, so it propagates. The provider is injected via the
        `search_fn` parameter (the SERP-cascade refactor, REQ-104, made it a parameter): a default-arg
        is bound at import time, so monkeypatching the module-level openrouter_search would NOT reach
        run_wave2's already-bound default -- passing search_fn explicitly is the correct injection."""
        def fake_openrouter_search(q, dhost, k=10):
            raise SystemExit("CONTROL FAILURE: simulated billing failure")
        residual = [{"school": "A", "query": "q", "wave1_gated": [], "wave2_invoked": False,
                     "wave2_raw_urls": [], "wave2_gated": []}]
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            D2.run_wave2(residual, "example.org", search_fn=fake_openrouter_search)


def _fake_response(status_code, payload=None, text=""):
    class R:
        def __init__(self):
            self.status_code = status_code
            self.text = text or (json.dumps(payload) if payload is not None else "")

        def json(self):
            if payload is None:
                raise ValueError("no JSON")
            return payload

        def raise_for_status(self):
            if status_code >= 400:
                import requests
                raise requests.HTTPError(f"HTTP {status_code}")
    return R()


class TestSerpProviderFailureSemantics:
    """Issue #29: 401/402 = billing/auth -> SystemExit halt (every later call fails identically);
    429 = transient -> TransientProviderError / retry, never a whole-run halt; 5xx propagates as
    requests.HTTPError. All HTTP is mocked via requests.post."""

    def test_brightdata_401_halts(self, monkeypatch):
        import requests
        monkeypatch.setattr(requests, "post", lambda *a, **k: _fake_response(401, text="bad key"))
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            DISC.brightdata_search("q", "example.org")

    def test_brightdata_429_raises_transient_not_systemexit(self, monkeypatch):
        import requests
        monkeypatch.setattr(requests, "post", lambda *a, **k: _fake_response(429, text="slow down"))
        with pytest.raises(DISC.TransientProviderError):
            DISC.brightdata_search("q", "example.org")

    def test_brightdata_5xx_propagates_as_requests_error(self, monkeypatch):
        import requests
        monkeypatch.setattr(requests, "post", lambda *a, **k: _fake_response(502))
        with pytest.raises(requests.HTTPError):
            DISC.brightdata_search("q", "example.org")

    def test_brightdata_nonjson_zone_raises_transient(self, monkeypatch):
        import requests
        monkeypatch.setattr(requests, "post", lambda *a, **k: _fake_response(200, payload=None, text="<html>"))
        with pytest.raises(DISC.TransientProviderError, match="non-JSON"):
            DISC.brightdata_search("q", "example.org")

    def test_serper_402_halts(self, monkeypatch):
        import requests
        monkeypatch.setattr(requests, "post", lambda *a, **k: _fake_response(402, text="no credits"))
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            DISC.serper_search("q", "example.org", _sleep=lambda s: None)

    def test_serper_429_retries_once_then_succeeds(self, monkeypatch):
        import requests
        responses = [_fake_response(429, text="slow down"),
                     _fake_response(200, payload={"organic": [{"link": "https://example.org/bell"}]})]
        slept = []
        monkeypatch.setattr(requests, "post", lambda *a, **k: responses.pop(0))
        urls = DISC.serper_search("q", "example.org", _sleep=slept.append)
        assert urls == ["https://example.org/bell"]
        assert len(slept) == 1          # one short sleep, one retry -- not a retry framework

    def test_serper_429_twice_raises_transient_not_systemexit(self, monkeypatch):
        import requests
        monkeypatch.setattr(requests, "post", lambda *a, **k: _fake_response(429, text="still limited"))
        with pytest.raises(DISC.TransientProviderError, match="429"):
            DISC.serper_search("q", "example.org", _sleep=lambda s: None)


class TestDiscoveryGate:
    """gate() decides keep/reject for a discovered URL. CMS_HOSTS is load-bearing here:
    an off-domain URL on a known school-CMS host is KEPT only when the district slug is in
    the URL. Regression coverage for the 2026-06-24 CMS_HOSTS additions, which changed
    discovery recall (human-approved per ACQUISITION_PIPELINE.md Open decision #8)."""

    def test_on_domain_url_is_kept(self):
        ok, why = DISC.gate("https://www.marion-isd.org/o/vms/page/school-hours", "marion-isd.org", "marion-isd", True)
        assert ok and why == "on-domain"

    def test_news_aggregator_is_rejected(self):
        ok, why = DISC.gate("https://www.greatschools.org/x/marion", "marion-isd.org", "marion-isd", True)
        assert not ok and why == "news/aggregator"

    def test_off_domain_non_cms_is_rejected(self):
        ok, why = DISC.gate("https://example.com/marion-isd/bell", "marion-isd.org", "marion-isd", True)
        assert not ok and why == "off-district"

    def test_newly_added_vendor_host_with_slug_is_kept(self):
        """A SharpSchool/Apptegy/Educational-Networks URL that names the district is now
        kept (was 'off-district' before the 2026-06-24 additions)."""
        for host in ("district5.sharpschool.com", "cmsv2-assets.apptegy.net", "x.educationalnetworks.net"):
            ok, why = DISC.gate(f"https://{host}/district5/bell-schedule", "district5.org", "district5", True)
            assert ok and why == "cms-slug", f"{host} should be kept via cms-slug"

    def test_cms_host_without_slug_is_rejected(self):
        """The slug guard still holds -- a CMS host that does NOT name this district is
        rejected, so the whitelist can't pull in some OTHER district's content."""
        ok, why = DISC.gate("https://other.sharpschool.com/somewhere/bell", "district5.org", "district5", True)
        assert not ok and why == "off-district"

    # ---- issue #34: suffix matching needs a dot boundary ----

    def test_halifax_com_is_not_rejected_as_x_com(self):
        """halifax.com endswith x.com (a NEWS_AGG entry) -- without a dot boundary a district
        hosted on halifax.com was rejected as a news/aggregator."""
        ok, why = DISC.gate("https://halifax.com/bell-schedule", "halifax.com", "halifax", True)
        assert ok and why == "on-domain"

    def test_x_com_itself_still_rejected(self):
        ok, why = DISC.gate("https://x.com/district5/status/1", "district5.org", "district5", True)
        assert not ok and why == "news/aggregator"

    def test_subdomain_of_news_host_still_rejected(self):
        ok, why = DISC.gate("https://sub.x.com/district5/bell", "district5.org", "district5", True)
        assert not ok and why == "news/aggregator"

    def test_evil_lookalike_of_cms_host_is_not_cms_matched(self):
        """evilschoolwires.com endswith schoolwires.com but is NOT the vendor -- the dot
        boundary keeps the CMS whitelist from matching lookalike registrations."""
        ok, why = DISC.gate("https://evilschoolwires.com/district5/bell", "district5.org", "district5", True)
        assert not ok and why == "off-district"

    def test_real_cms_subdomain_still_cms_matched(self):
        ok, why = DISC.gate("https://district5.schoolwires.com/bell", "district5.org", "district5", True)
        assert ok and why == "cms-slug"


class TestOutcomeRollup:
    def test_found_all_when_every_school_resolved(self):
        roster = [{"wave1_gated": [{"kept": True}], "wave2_gated": []},
                  {"wave1_gated": [], "wave2_gated": [{"kept": True}]}]
        assert D2.district_outcome(roster) == "found_all"

    def test_manual_flag_all_when_nothing_found(self):
        roster = [{"wave1_gated": [{"kept": False}], "wave2_gated": [{"kept": False}]}]
        assert D2.district_outcome(roster) == "manual_flag_all"

    def test_found_partial_when_mixed(self):
        roster = [{"wave1_gated": [{"kept": True}], "wave2_gated": []},
                  {"wave1_gated": [{"kept": False}], "wave2_gated": [{"kept": False}]}]
        assert D2.district_outcome(roster) == "found_partial"


class TestFlatten:
    def test_dedups_a_hub_page_shared_by_two_schools(self):
        """Independent of any topology label -- normalized-URL dedup alone collapses a hub
        page into one shared capture target, which is why dropping topology classification
        doesn't cost the 'capture the hub once' efficiency (see ACQUISITION_PIPELINE.md)."""
        roster = [
            {"school": "Elem A", "wave1_provider": "brightdata", "wave1_gated": [{"url": "https://d.example/hub", "kept": True, "reason": "on-domain"}], "wave2_gated": []},
            {"school": "Middle B", "wave1_provider": "brightdata", "wave1_gated": [{"url": "https://d.example/hub?x=1", "kept": True, "reason": "on-domain"}], "wave2_gated": []},
        ]
        cands = D2.flatten(roster)
        assert len(cands) == 1
        assert sorted(cands[0]["schools"]) == ["Elem A", "Middle B"]
        assert cands[0]["tools"] == ["brightdata"]

    def test_rejected_candidates_excluded(self):
        roster = [{"school": "A", "wave1_gated": [{"url": "https://wrong.example/x", "kept": False, "reason": "off-district"}], "wave2_gated": []}]
        assert D2.flatten(roster) == []

    def test_wave2_tool_tagged_separately_from_wave1(self):
        """Issue #30: tools[] carries the REAL serving provider per wave, not the retired
        claude/openrouter architecture labels."""
        roster = [{"school": "A", "wave1_provider": "brightdata", "wave1_gated": [],
                   "wave2_provider": "claude_websearch",
                   "wave2_gated": [{"url": "https://d.example/x", "kept": True, "reason": "on-domain"}]}]
        cands = D2.flatten(roster)
        assert cands[0]["tools"] == ["claude_websearch"]

    def test_wave1_serper_failover_provenance_survives_flatten(self):
        roster = [{"school": "A", "wave1_provider": "serper",
                   "wave1_gated": [{"url": "https://d.example/x", "kept": True, "reason": "on-domain"}],
                   "wave2_gated": []}]
        assert D2.flatten(roster)[0]["tools"] == ["serper"]

    def test_legacy_roster_without_provider_fields_does_not_crash(self):
        """Pre-fix rosters (no wave*_provider) flatten with an honest 'unknown' label rather
        than resurrecting the retired claude/openrouter names (backfill NOTE in flatten())."""
        roster = [{"school": "A", "wave1_gated": [{"url": "https://d.example/x", "kept": True, "reason": "on-domain"}], "wave2_gated": []}]
        assert D2.flatten(roster)[0]["tools"] == ["unknown_wave1"]


class TestWriteDiscovery:
    def test_writes_discovery_and_candidates_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        d = _synthetic_district()
        roster = D2.merge_wave1(D2.build_roster(d),
                                 {"district_id": "9999999", "domain": "testschools.example", "schools": []},
                                 "testschools.example")
        out_dir = D2.write_discovery(d, roster, "batch_00099")
        assert (out_dir / "discovery.json").exists()
        assert (out_dir / "candidates.json").exists()
        doc = json.loads((out_dir / "discovery.json").read_text())
        assert len(doc["schools"]) == 2
        assert all(s["outcome"] == "manual_flag" for s in doc["schools"])

    def test_redo_versions_the_old_file_instead_of_overwriting(self, tmp_path, monkeypatch):
        """data/raw/ is write-once in spirit -- a redo must never destroy the prior
        attempt's audit trail, per CLAUDE.md's 'never modify data/raw/' rule."""
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        d = _synthetic_district()
        empty_raw = {"district_id": "9999999", "domain": "testschools.example", "schools": []}
        roster1 = D2.merge_wave1(D2.build_roster(d), empty_raw, "testschools.example")
        out_dir = D2.write_discovery(d, roster1, "batch_00099")
        roster2 = D2.merge_wave1(D2.build_roster(d), empty_raw, "testschools.example")
        D2.write_discovery(d, roster2, "batch_00100")
        versioned = list(out_dir.glob("discovery.*.json"))
        assert len(versioned) == 1
        assert (out_dir / "discovery.json").exists()  # the new one, not destroyed


# ------------------------------------------------------------------------ Stage 3 (Capture)
def _write_stage2_outputs(d, district_id="8888888", name="Test Capture District", state="ZZ", domain="testcapture.example"):
    """A district directory with the discovery.json + candidates.json Stage 2 would have
    produced -- capture_stage3.find_districts() requires both before treating a district
    as Stage 3's concern."""
    (d / "discovery.json").write_text(json.dumps({
        "district_id": district_id, "name": name, "state": state, "domain": domain,
        "batch_id": "batch_00099", "generated_at": "2026-06-23T00:00:00Z", "schools": [],
    }))
    (d / "candidates.json").write_text(json.dumps({
        "district_id": district_id, "name": name, "domain": domain, "candidates": [],
    }))


class TestCaptureStage3FindDistricts:
    def test_finds_district_with_both_files(self, tmp_path):
        d = tmp_path / "8888888_test_capture_district"
        d.mkdir()
        _write_stage2_outputs(d)
        found = C3.find_districts(tmp_path)
        assert len(found) == 1
        assert found[0]["district_id"] == "8888888"
        assert found[0]["state"] == "ZZ"

    def test_excludes_district_missing_candidates_json(self, tmp_path):
        """A district only as far as discovery.json (e.g. Stage 2 ran but produced zero
        candidates for some reason) is not yet Stage 3's concern."""
        d = tmp_path / "8888888_test_capture_district"
        d.mkdir()
        (d / "discovery.json").write_text(json.dumps({
            "district_id": "8888888", "name": "X", "state": "ZZ", "domain": "", "schools": [],
        }))
        assert C3.find_districts(tmp_path) == []

    def test_empty_root_returns_empty_list(self, tmp_path):
        assert C3.find_districts(tmp_path / "does_not_exist") == []


class TestCaptureStage3Reconcile:
    def test_district_with_no_disk_artifact_and_no_registry_entry_is_todo(self, tmp_path):
        d = tmp_path / "8888888_test_capture_district"
        d.mkdir()
        _write_stage2_outputs(d)
        districts = C3.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        todo, skipped = C3.reconcile(districts, registry)
        assert [x["district_id"] for x in todo] == ["8888888"]
        assert skipped == []

    def test_disk_ahead_of_registry_reconciles_up_and_skips(self, tmp_path):
        """Found during Stage 2's build, applies identically here: a district can complete
        Stage 3 (captures.json written) without the registry ever having been told -- the
        filesystem is the real fact, so the registry must catch up to it."""
        d = tmp_path / "8888888_test_capture_district"
        d.mkdir()
        _write_stage2_outputs(d)
        (d / "captures.json").write_text("[]")
        districts = C3.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        todo, skipped = C3.reconcile(districts, registry)
        assert todo == []
        assert [x["district_id"] for x in skipped] == ["8888888"]
        assert registry["districts"]["8888888"]["furthest_stage"] == 3

    def test_registry_ahead_of_disk_halts_the_entire_run(self, tmp_path):
        """The converse drift: registry claims Stage 3 done but captures.json doesn't
        exist. A control failure, not routine drift -- must stop everything."""
        d = tmp_path / "8888888_test_capture_district"
        d.mkdir()
        _write_stage2_outputs(d)
        districts = C3.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        DS.record_stage(registry, "8888888", "Test Capture District", "ZZ",
                         stage=3, stage_name="capture", outcome="captured_all")
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            C3.reconcile(districts, registry)


class TestCaptureStage3OutcomeRollup:
    def test_captured_all_when_every_candidate_ok(self):
        assert C3.compute_outcome([{"ok": True}, {"ok": True}]) == ("captured_all", "")

    def test_capture_failed_all_when_nothing_ok(self):
        outcome, notes = C3.compute_outcome([{"ok": False, "err": "needs_oauth_reauth"}])
        assert outcome == "capture_failed_all"
        assert "needs_oauth_reauth" in notes

    def test_captured_partial_when_mixed(self):
        outcome, _ = C3.compute_outcome([{"ok": True}, {"ok": False, "err": "timeout"}])
        assert outcome == "captured_partial"

    def test_missing_err_field_does_not_crash(self):
        """A capture failure with no err string set (shouldn't normally happen, but a
        missing field must not blow up outcome computation) is summarized as 'unknown'."""
        outcome, notes = C3.compute_outcome([{"ok": False}])
        assert outcome == "capture_failed_all"
        assert "unknown" in notes


class TestCaptureStage3Finish:
    def test_finish_reads_captures_json_and_writes_registry(self, tmp_path):
        d = tmp_path / "8888888_test_capture_district"
        d.mkdir()
        _write_stage2_outputs(d)
        (d / "captures.json").write_text(json.dumps([
            {"url": "https://testcapture.example/a", "ok": True},
            {"url": "https://testcapture.example/b", "ok": False, "err": "needs_oauth_reauth"},
        ]))
        district = C3.find_districts(tmp_path)[0]
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        outcome = C3.finish_district(district, registry)
        assert outcome == "captured_partial"
        rec = registry["districts"]["8888888"]
        assert rec["furthest_stage"] == 3
        assert rec["outcome"] == "captured_partial"
        assert "needs_oauth_reauth" in rec["notes"]


# ---------------------------------------------------------------- Stage 4 (Local processing)
def _write_discovery(d, district_id="9999999", name="Test Process District", state="ZZ", domain="testprocess.example"):
    """Stage 4 pulls district_id/name/state from discovery.json, same as capture_stage3.py
    pulls them rather than re-deriving -- process_stage4.find_districts() requires it
    alongside captures.json."""
    (d / "discovery.json").write_text(json.dumps({
        "district_id": district_id, "name": name, "state": state, "domain": domain,
        "batch_id": "batch_00099", "generated_at": "2026-06-23T00:00:00Z", "schools": [],
    }))


def _make_pdf(path, text):
    """A tiny REAL pdf with extractable text, generated with PyMuPDF -- not mocked, so the
    actual pdftotext/pdfplumber/camelot calls run for real against real bytes. PyMuPDF is
    only a test-fixture convenience here, not a Stage 4 production dependency (it was
    dropped from the kept tool roster, REQ-083)."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def _make_image(path, text):
    """A tiny REAL image with legible drawn text, for a genuine (not mocked) Tesseract
    OCR pass."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (800, 200), color="white")
    d = ImageDraw.Draw(img)
    d.text((20, 60), text, fill="black")
    img.save(str(path))


class TestProcessStage4FindDistricts:
    def test_finds_district_with_both_files(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        (d / "captures.json").write_text("[]")
        found = P4.find_districts(tmp_path)
        assert len(found) == 1
        assert found[0]["district_id"] == "9999999"
        assert found[0]["state"] == "ZZ"

    def test_excludes_district_missing_captures_json(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        assert P4.find_districts(tmp_path) == []

    def test_empty_root_returns_empty_list(self, tmp_path):
        assert P4.find_districts(tmp_path / "does_not_exist") == []


class TestProcessStage4FileConsistency:
    def test_passes_when_every_referenced_file_exists(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        rec_dir = d / "captures" / "abc123"
        rec_dir.mkdir(parents=True)
        (rec_dir / "page.txt").write_text("hello")
        captures = [{"url": "https://x/1", "hash": "abc123", "ok": True, "files": {"txt": "page.txt"}}]
        (d / "captures.json").write_text(json.dumps(captures))
        district = P4.find_districts(tmp_path)[0]
        P4.check_file_consistency(district)  # must not raise

    def test_halts_on_missing_referenced_file(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        rec_dir = d / "captures" / "abc123"
        rec_dir.mkdir(parents=True)
        # page.txt deliberately NOT written -- captures.json claims it exists.
        captures = [{"url": "https://x/1", "hash": "abc123", "ok": True, "files": {"txt": "page.txt"}}]
        (d / "captures.json").write_text(json.dumps(captures))
        district = P4.find_districts(tmp_path)[0]
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            P4.check_file_consistency(district)

    def test_ok_false_records_are_exempt(self, tmp_path):
        """files: {} by design for a capture failure -- not an inconsistency."""
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        captures = [{"url": "https://x/1", "hash": "abc123", "ok": False, "err": "needs_oauth_reauth", "files": {}}]
        (d / "captures.json").write_text(json.dumps(captures))
        district = P4.find_districts(tmp_path)[0]
        P4.check_file_consistency(district)  # must not raise


class TestProcessStage4Reconcile:
    def test_district_with_no_disk_artifact_and_no_registry_entry_is_todo(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        (d / "captures.json").write_text("[]")
        districts = P4.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        todo, skipped = P4.reconcile(districts, registry)
        assert [x["district_id"] for x in todo] == ["9999999"]
        assert skipped == []

    def test_disk_ahead_of_registry_reconciles_up_and_skips(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        (d / "captures.json").write_text("[]")
        (d / "processed.json").write_text("[]")
        districts = P4.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        todo, skipped = P4.reconcile(districts, registry)
        assert todo == []
        assert [x["district_id"] for x in skipped] == ["9999999"]
        assert registry["districts"]["9999999"]["furthest_stage"] == 4

    def test_registry_ahead_of_disk_halts_the_entire_run(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        (d / "captures.json").write_text("[]")
        districts = P4.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        DS.record_stage(registry, "9999999", "Test Process District", "ZZ",
                         stage=4, stage_name="process", outcome="processed_all")
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            P4.reconcile(districts, registry)

    def test_missing_referenced_file_halts_before_registry_comparison(self, tmp_path):
        """The file-existence check fires inside reconcile() too, not just standalone --
        a structural problem must be caught even on a district that would otherwise look
        like ordinary 'todo' work."""
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        rec_dir = d / "captures" / "abc123"
        rec_dir.mkdir(parents=True)
        captures = [{"url": "https://x/1", "hash": "abc123", "ok": True, "files": {"txt": "page.txt"}}]
        (d / "captures.json").write_text(json.dumps(captures))
        districts = P4.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            P4.reconcile(districts, registry)


class TestUsableTextBar:
    def test_short_text_is_not_usable(self):
        assert P4.is_usable("too short") is False

    def test_empty_text_is_not_usable(self):
        assert P4.is_usable("") is False
        assert P4.is_usable(None) is False

    def test_long_readable_text_is_usable(self):
        assert P4.is_usable("School Hours: 8:00 AM to 3:15 PM. " * 5) is True

    def test_garbled_low_printable_ratio_is_not_usable(self):
        garbled = "\x00\x01\x02\x03" * 40  # long enough on length alone, but not printable
        assert P4.is_usable(garbled) is False


class TestMarkdownRendering:
    def test_basic_table_gets_header_and_separator_row(self):
        md = P4._rows_to_markdown([["Period", "Time"], ["1", "8:00 AM"]])
        lines = md.splitlines()
        assert lines[0] == "| Period | Time |"
        assert lines[1] == "| --- | --- |"
        assert lines[2] == "| 1 | 8:00 AM |"

    def test_empty_rows_returns_empty_string(self):
        assert P4._rows_to_markdown([]) == ""

    def test_none_cells_become_empty_string(self):
        md = P4._rows_to_markdown([["A", None], ["1", "2"]])
        assert "| A |  |" == md.splitlines()[0]

    def test_ragged_rows_are_padded_to_max_width(self):
        md = P4._rows_to_markdown([["A", "B", "C"], ["1"]])
        lines = md.splitlines()
        assert lines[2] == "| 1 |  |  |"


class TestProcessStage4OutcomeRollup:
    def test_processed_all_when_every_record_usable(self):
        assert P4.compute_outcome([{"usable": True}, {"usable": True}]) == "processed_all"

    def test_no_usable_text_any_when_none_usable(self):
        assert P4.compute_outcome([{"usable": False}, {"usable": False}]) == "no_usable_text_any"

    def test_processed_partial_when_mixed(self):
        assert P4.compute_outcome([{"usable": True}, {"usable": False}]) == "processed_partial"

    def test_empty_list_is_no_usable_text_any(self):
        assert P4.compute_outcome([]) == "no_usable_text_any"


class TestProcessStage4RecordProcessing:
    """Real tool invocations against real (small, generated) fixtures -- not mocked, so
    pdftotext/pdfplumber/camelot/tesseract actually run, closing the gap Stage 3's own
    browser-driving logic left open (REQ-079)."""

    def test_pdf_only_record_runs_all_four_pdf_tools_plus_raster_ocr(self, tmp_path):
        rec_dir = tmp_path / "captures" / "abc123"
        rec_dir.mkdir(parents=True)
        _make_pdf(rec_dir / "original.pdf", "School Hours\nStart: 8:00 AM\nEnd: 3:15 PM")
        rec = {"url": "https://x/1", "hash": "abc123", "ok": True, "files": {"bin": "original.pdf"}}
        out = P4.process_record(rec, rec_dir)
        sources = {t["source"] for t in out["texts"]}
        assert sources == {"pdftotext", "pdfplumber_lines", "camelot_stream", "camelot_hybrid", "tesseract_raster"}
        pdftotext_entry = next(t for t in out["texts"] if t["source"] == "pdftotext")
        assert pdftotext_entry["usable"] is False  # short fixture text, below the 120-char bar -- still an entry, just not usable
        assert (rec_dir / "pdftotext.txt").exists()
        assert (rec_dir / "tesseract_raster.txt").exists()
        assert any(rec_dir.glob("raster_p*.png")), "rasterized pages must be persisted, not discarded"

    def test_existing_txt_is_referenced_not_rewritten(self, tmp_path):
        rec_dir = tmp_path / "captures" / "def456"
        rec_dir.mkdir(parents=True)
        original = "School Hours: 8:00 AM to 3:15 PM. " * 5
        (rec_dir / "page.txt").write_text(original)
        rec = {"url": "https://x/2", "hash": "def456", "ok": True, "files": {"txt": "page.txt"}}
        out = P4.process_record(rec, rec_dir)
        txt_entry = next(t for t in out["texts"] if t["source"] == "txt")
        assert txt_entry["text_file"] == "page.txt"
        assert txt_entry["usable"] is True
        assert (rec_dir / "page.txt").read_text() == original  # never rewritten

    def test_existing_png_only_gets_tesseract_screenshot_only(self, tmp_path):
        rec_dir = tmp_path / "captures" / "ghi789"
        rec_dir.mkdir(parents=True)
        _make_image(rec_dir / "page.png", "School Hours 8:00 AM to 3:15 PM")
        rec = {"url": "https://x/3", "hash": "ghi789", "ok": True, "files": {"png": "page.png"}}
        out = P4.process_record(rec, rec_dir)
        sources = {t["source"] for t in out["texts"]}
        assert sources == {"tesseract_screenshot"}
        assert (rec_dir / "tesseract_screenshot.txt").exists()

    def test_direct_image_download_gets_tesseract_image(self, tmp_path):
        rec_dir = tmp_path / "captures" / "jkl012"
        rec_dir.mkdir(parents=True)
        _make_image(rec_dir / "original.png", "Bell Schedule 8:00 AM")
        rec = {"url": "https://x/4", "hash": "jkl012", "ok": True, "files": {"bin": "original.png"}}
        out = P4.process_record(rec, rec_dir)
        sources = {t["source"] for t in out["texts"]}
        assert sources == {"tesseract_image"}

    def test_corrupt_pdf_is_caught_per_tool_not_raised(self, tmp_path):
        """A malformed file shouldn't crash the whole record -- each tool's failure is
        caught and recorded as an error entry, same completeness-over-success principle
        as discovery.json."""
        rec_dir = tmp_path / "captures" / "mno345"
        rec_dir.mkdir(parents=True)
        (rec_dir / "original.pdf").write_bytes(b"this is not a real pdf")
        rec = {"url": "https://x/5", "hash": "mno345", "ok": True, "files": {"bin": "original.pdf"}}
        out = P4.process_record(rec, rec_dir)  # must not raise
        assert len(out["texts"]) > 0
        assert all(t["usable"] is False for t in out["texts"])
        assert out["usable"] is False

    def test_html_kind_record_with_pdf_and_png_gets_two_separate_ocr_entries(self, tmp_path):
        """page.png (screenshot) and the PDF's own rasterization are kept as separate OCR
        inputs, since print-CSS reflow can differ from the on-screen render."""
        rec_dir = tmp_path / "captures" / "pqr678"
        rec_dir.mkdir(parents=True)
        _make_pdf(rec_dir / "page.pdf", "School Hours\nStart: 8:00 AM\nEnd: 3:15 PM")
        _make_image(rec_dir / "page.png", "School Hours 8:00 AM to 3:15 PM")
        (rec_dir / "page.txt").write_text("School Hours: 8:00 AM to 3:15 PM. " * 5)
        rec = {"url": "https://x/6", "hash": "pqr678", "ok": True,
               "files": {"pdf": "page.pdf", "png": "page.png", "txt": "page.txt"}}
        out = P4.process_record(rec, rec_dir)
        sources = {t["source"] for t in out["texts"]}
        assert {"tesseract_screenshot", "tesseract_raster"} <= sources
        assert "txt" in sources
        assert out["usable"] is True  # the long .txt entry alone clears the bar


class TestProcessStage4WriteProcessed:
    def test_first_write_creates_the_file(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        district = {"dir": d}
        path = P4.write_processed(district, [{"url": "https://x/1", "usable": True}])
        assert path == d / "processed.json"
        assert json.loads(path.read_text()) == [{"url": "https://x/1", "usable": True}]

    def test_second_write_renames_the_first_aside_with_a_timestamp(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        district = {"dir": d}
        P4.write_processed(district, [{"url": "https://x/1"}])
        P4.write_processed(district, [{"url": "https://x/2"}])
        versioned = list(d.glob("processed.*.json"))
        assert len(versioned) == 1
        assert json.loads((d / "processed.json").read_text()) == [{"url": "https://x/2"}]
        assert json.loads(versioned[0].read_text()) == [{"url": "https://x/1"}]


class TestProcessStage4Finish:
    def test_finish_processes_real_record_and_writes_registry(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        rec_dir = d / "captures" / "abc123"
        rec_dir.mkdir(parents=True)
        (rec_dir / "page.txt").write_text("School Hours: 8:00 AM to 3:15 PM. " * 5)
        captures = [{"url": "https://x/1", "hash": "abc123", "ok": True, "files": {"txt": "page.txt"}}]
        (d / "captures.json").write_text(json.dumps(captures))
        district = P4.find_districts(tmp_path)[0]
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        outcome = P4.finish_district(district, registry)
        assert outcome == "processed_all"
        assert (d / "processed.json").exists()
        rec = registry["districts"]["9999999"]
        assert rec["furthest_stage"] == 4
        assert rec["outcome"] == "processed_all"
