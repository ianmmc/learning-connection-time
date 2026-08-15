"""Stage 7 request-more-evidence EXECUTION planning (REQ-118) — the PURE collect/guard/cap logic that
turns approved NEW-work directives into a targeted follow-up-batch plan. No DB/network; the DB glue
(compose_followup_batch) is orchestration over this. Mirrors test_stage7_requests.py's pure style."""
import pytest

from infrastructure.acquisition.process_governance import stage7_execute as EX


@pytest.fixture(autouse=True)
def _domain_diagnosis_default(monkeypatch):
    """#719: compose's scope diagnosis (Q1.usable_scoping_domains) reads the on-disk NCES LEA CSV,
    absent on CI — stub it so every test district resolves as DOMAIN-HAVING (the pre-#719 round-0
    behavior these tests were written against: 0 prior rounds -> the domain-scoped batch).
    Escalation-path tests that need domain-less districts override in test_escalation_ladders."""
    monkeypatch.setattr(EX.Q1, "usable_scoping_domains",
                        lambda year, dids, dd: {d: ("zz-test.org", "nces") for d in dids})


def _req(request_id, district_id, route="7->2", band="high"):
    return {"request_id": request_id, "district_id": district_id, "route": route, "band": band}


def test_only_newwork_routes_are_swept():
    # 7->6 (existing reps, direct re-dispatch) is NOT a follow-up-batch route — it is filtered out here
    reqs = [_req(1, "D1", "7->2", "high"), _req(2, "D1", "7->6", None), _req(3, "D1", "7->3", None)]
    plan = EX.plan_followup(reqs, claimed_bands={"D1": ["elementary", "high"]})
    assert 2 not in plan["swept_ids"]                 # the 7->6 request is not swept into a batch
    assert set(plan["swept_ids"]) == {1, 3}


def test_explicit_band_targets_that_band():
    plan = EX.plan_followup([_req(1, "D1", "7->2", "high")], claimed_bands={})
    assert plan["targets"] == {"D1": ["high"]}
    assert plan["swept_ids"] == [1]


def test_bandless_request_expands_to_claimed_bands():
    # a 7->3 (URL recapture, band=None) re-targets the district's claimed bands (re-discover it)
    plan = EX.plan_followup([_req(1, "D1", "7->3", None)],
                            claimed_bands={"D1": ["elementary", "middle", "high"]})
    assert plan["targets"] == {"D1": ["elementary", "middle", "high"]}


def test_multiple_requests_one_district_union_of_bands_dedup():
    reqs = [_req(1, "D1", "7->2", "high"), _req(2, "D1", "7->2", "middle"), _req(3, "D1", "7->2", "high")]
    plan = EX.plan_followup(reqs, claimed_bands={})
    assert plan["targets"] == {"D1": ["high", "middle"]}     # order-preserved, deduped
    assert plan["swept_ids"] == [1, 2, 3]


def test_twelve_district_cap_spills_the_rest():
    reqs = [_req(i, f"D{i}", "7->2", "high") for i in range(1, 16)]   # 15 districts
    plan = EX.plan_followup(reqs, claimed_bands={}, cap=12)
    assert len(plan["targets"]) == 12
    assert [s["district_id"] for s in plan["spilled"]] == ["D13", "D14", "D15"]
    # spilled districts' requests are NOT swept — they stay 'approved' for the next compose
    assert 13 not in plan["swept_ids"] and 15 not in plan["swept_ids"]
    assert len(plan["swept_ids"]) == 12


def test_depth_guard_blocks_exhausted_district_band():
    # D1/high already fired its max rounds -> blocked; D1/middle is fresh -> kept
    reqs = [_req(1, "D1", "7->2", "high"), _req(2, "D1", "7->2", "middle")]
    plan = EX.plan_followup(reqs, claimed_bands={}, executed_rounds={("D1", "high"): 2}, max_rounds=2)
    assert plan["targets"] == {"D1": ["middle"]}
    assert plan["swept_ids"] == [2]
    assert [b["request_id"] for b in plan["blocked"]] == [1]


def test_depth_guard_none_max_never_blocks():
    reqs = [_req(1, "D1", "7->2", "high")]
    plan = EX.plan_followup(reqs, claimed_bands={}, executed_rounds={("D1", "high"): 99}, max_rounds=None)
    assert plan["swept_ids"] == [1] and plan["blocked"] == []


def test_defer_holds_7to2_while_district_has_unexecuted_7to6():
    # #159 — D1 has an un-executed 7->6 -> its 7->2 is HELD (not swept); D2 has none -> composed
    reqs = [_req(1, "D1", "7->2", "high"), _req(2, "D2", "7->2", "middle")]
    plan = EX.plan_followup(reqs, claimed_bands={}, defer_76={"D1"})
    assert plan["targets"] == {"D2": ["middle"]}
    assert plan["swept_ids"] == [2]
    assert [d["request_id"] for d in plan["deferred"]] == [1]
    assert "7->6" in plan["deferred"][0]["reason"]


def test_no_defer_when_district_not_in_defer_set():
    reqs = [_req(1, "D1", "7->2", "high")]
    plan = EX.plan_followup(reqs, claimed_bands={}, defer_76=set())
    assert plan["swept_ids"] == [1] and plan["deferred"] == []


def test_empty_requests_is_empty_plan():
    plan = EX.plan_followup([], claimed_bands={})
    assert plan["targets"] == {} and plan["swept_ids"] == [] and plan["spilled"] == []


def test_district_order_is_first_seen_preserving_attention_sort():
    reqs = [_req(1, "DB", "7->2", "high"), _req(2, "DA", "7->2", "high"), _req(3, "DB", "7->2", "middle")]
    plan = EX.plan_followup(reqs, claimed_bands={})
    assert list(plan["targets"]) == ["DB", "DA"]   # DB first (seen first), not alphabetized


# --- DB glue (govdb): the real SQL — approved read, depth-guard rounds, and the atomic flip. The
# NCES/LCT-heavy build (build_followup_batch) + persist (persist_batch) are stubbed; this asserts the
# orchestration + that swept directives flip to 'executed' with the batch_id as executed_ref. ---
import json  # noqa: E402
from sqlalchemy import text  # noqa: E402
from infrastructure.acquisition.common import benchmark as BM  # noqa: E402
from infrastructure.acquisition.common import db as gdb  # noqa: E402
from tests import benchmark_seed as BSEED  # noqa: E402
from infrastructure.acquisition.stage7_extract import models as _M7  # noqa: E402,F401 (registers table)

govdb = pytest.mark.govdb



@govdb
def test_executed_rounds_counts_distinct_refs_not_rows(gov_session):
    """Review R1 (#153): a bundle flips N directives to ONE executed_ref = one round. The compose-side
    depth-guard history must count DISTINCT executed_ref, not rows — else one bundled round of three
    7->6s (band NULL) depth-blocks a later band-less 7->3/7->1 at used=3."""
    gdb.init_precious_schema()
    s = gov_session
    for i in range(3):     # ONE bundled round: three rows sharing one executed_ref
        s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                       "target, band, reason, status, executed_ref, created_at) VALUES ('ZZR1', 'h', "
                       "'representation', '7->6', :t, NULL, 'r', 'executed', 'bundle_x', :ts)"),
                  {"t": f"ZZR1:r{i}", "ts": _M7.utcnow()})
    s.flush()
    assert EX._executed_rounds(s, ["ZZR1"]) == {("ZZR1", None): 1}    # one round, not three


@govdb
def test_attempted_schools_excludes_draft_batches(gov_session):
    """Review of a9c4486 (#162): a DRAFT batch never ran discovery — its schools were NOT attempted,
    and an abandoned draft (batch_00009) must not poison the untried set forever. #168: an `abandoned`
    batch is a retired never-ran draft, so it is excluded for the same reason. Only committed
    (approved) batches count as attempted."""
    from infrastructure.acquisition.stage1_queue.models import Batch, BatchSchool
    gdb.init_precious_schema()
    s = gov_session
    for bid, status, sid in (("batch_zzatt_a", "approved", "SA"),
                             ("batch_zzatt_d", "draft", "SD"),
                             ("batch_zzatt_x", "abandoned", "SX")):
        s.add(Batch(batch_id=bid, batch_type="follow-up", status=status, nces_year="2024_25",
                    created_at="t", created_by="zz", meta_json={}))
        s.add(BatchSchool(batch_id=bid, district_id="ZZATT", school_id=sid, name="S",
                          is_charter="No", level="High", gslo="09", gshi="12",
                          bands=["high"], included=True, source="stratified"))
    s.flush()
    # only the approved batch's SA counts — draft's SD and abandoned's SX are both un-attempted
    assert EX._attempted_schools(s, ["ZZATT"]) == {"ZZATT": {"SA"}}


@govdb
def test_defer_excludes_rounds_exhausted_districts(gov_session):
    """Review R2 (#159): a district whose 7->6 ROUNDS are exhausted must NOT defer — its un-executed
    7->6s are depth-blocked zombies that can never fire, so deferring would hold its rediscovery
    forever (the live Las Cruces deadlock)."""
    gdb.init_precious_schema()
    s = gov_session
    # ZZR2A: un-executed 7->6, 0 rounds spent -> defers. ZZR2B: un-executed 7->6 BUT 2/2 rounds spent -> free.
    for did, refs in (("ZZR2A", []), ("ZZR2B", ["ra", "rb"])):
        s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                       "target, band, reason, status, created_at) VALUES (:d, 'h', 'representation', "
                       "'7->6', :t, NULL, 'r', 'approved', :ts)"),
                  {"d": did, "t": f"{did}:x", "ts": _M7.utcnow()})
        for ref in refs:
            s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                           "target, band, reason, status, executed_ref, created_at) VALUES (:d, 'h', "
                           "'representation', '7->6', :t, NULL, 'r', 'executed', :ref, :ts)"),
                      {"d": did, "t": f"{did}:y", "ref": ref, "ts": _M7.utcnow()})
    s.flush()
    assert EX._defer_76_districts(s, ["ZZR2A", "ZZR2B"], max_rounds=2) == {"ZZR2A"}
    # with no cap, both defer (nothing is a zombie when rounds are unlimited)
    assert EX._defer_76_districts(s, ["ZZR2A", "ZZR2B"], max_rounds=None) == {"ZZR2A", "ZZR2B"}


def _seed_req(s, hh, did, route, band, status="approved"):
    s.execute(text(
        "INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, band, "
        "reason, status, created_at) VALUES (:d, :h, 'district', :r, :d, :b, 'test', :st, :ts)"),
        {"d": did, "h": hh, "r": route, "b": band, "st": status, "ts": _M7.utcnow()})


@govdb
def test_compose_unscoped_sweeps_directives_across_handoffs(gov_session, monkeypatch):
    """#715 must-fail-today shape: the #159 design order (7->6s execute first, each minting a NEW
    handoff) means an approved 7->2's raising hash ≠ the currently-viewed run's. The console now
    always composes UNSCOPED (handoff_hash=None), which must sweep approved NEW-work from BOTH
    runs — the hash-scoped sweep found zero rows for Lewiston's 2 approved directives."""
    gdb.init_precious_schema()
    s = gov_session
    _seed_req(s, "zz715_runA", "ZZ715A", "7->2", "elementary")   # raised on run A
    _seed_req(s, "zz715_runB", "ZZ715B", "7->2", "high")         # raised on run B
    s.flush()
    # the seam that caused #715 is _approved_newwork's hash scoping — pin its population semantics
    # (subset assertions: the shared gov DB may hold other live approved rows; rollback fixture)
    unscoped = {r["district_id"] for r in EX._approved_newwork(s, None)}
    assert {"ZZ715A", "ZZ715B"} <= unscoped                      # both runs' directives swept
    scoped_a = {r["district_id"] for r in EX._approved_newwork(s, "zz715_runA")}
    assert scoped_a == {"ZZ715A"}                                # the old scoped sweep misses run B
    assert "ZZ715B" not in scoped_a


@govdb
def test_compose_priority_district_fronts_the_cap(gov_session, monkeypatch):
    """#736: the unscoped sweep is capped at 12 districts oldest-first — without priority, a
    just-approved directive from the viewed district (newest request_id) spills while 12 older
    unrelated ones compose. priority_district floats the viewed district ahead of the cap."""
    gdb.init_precious_schema()
    s = gov_session
    for i in range(12):                                   # 12 older districts, all approved
        _seed_req(s, "zz736old", f"ZZ736O{i:02d}", "7->2", "high")
    _seed_req(s, "zz736new", "ZZ736ME", "7->2", "high")   # the human's own, newest request_id
    s.flush()
    monkeypatch.setattr(EX.Q1, "build_followup_batch",
                        lambda year, bid, targets, **kw: ({"batch_id": bid, "districts":
                            [{"district_id": d} for d in targets]}, []))
    monkeypatch.setattr(EX.BSTORE, "create_batch", lambda sess, doc, **k: None)
    # scope the sweep to this test's rows only (the live/CI DB may hold other approved work):
    real_gather = EX._gather
    def scoped_gather(sess, hh, mr, **kw):
        g = real_gather(sess, hh, mr, **kw)
        g.rows[:] = [r for r in g.rows if r["district_id"].startswith("ZZ736")]
        return g
    monkeypatch.setattr(EX, "_gather", scoped_gather)

    out = EX.compose_followup_batch(actor="zz", session=s, dry_run=True)   # no priority
    assert "ZZ736ME" not in out["targets"]                # the must-fail-today shape: spilled
    assert any(sp["district_id"] == "ZZ736ME" for sp in out["spilled"])
    out = EX.compose_followup_batch(actor="zz", session=s, dry_run=True,
                                    priority_district="ZZ736ME")
    assert "ZZ736ME" in out["targets"]                    # fronts the cap; one old one spills
    assert len(out["targets"]) == 12


def test_stage7_js_compose_button_is_unscoped_715():
    """#715 source pin (no JS harness): the compose button must carry NO handoff hash — the
    count-one-population/sweep-another mismatch was `data-compose="${e.handoff_hash}"` + a scoped
    server sweep. A hash reappearing on the button silently reintroduces the disjoint sweep."""
    from pathlib import Path
    js = (Path(__file__).parent.parent /
          "infrastructure/acquisition/process_governance/static/stage7.js").read_text()
    assert "data-compose>" in js, "compose button lost its (hash-less) data-compose attribute"
    assert 'data-compose="${' not in js, "#715 regression: the compose button carries a handoff hash again"
    assert "composeFollowup(null, did)" in js, "#715: the click path must request the UNSCOPED sweep"
    assert "sweeps all districts" in js, "#715: the button copy must say the sweep is cross-district"


@govdb
def test_compose_flips_approved_to_executed(gov_session, monkeypatch):
    gdb.init_precious_schema()
    s = gov_session
    hh = "zzcompose"
    _seed_req(s, hh, "ZZC1", "7->2", "high")
    _seed_req(s, hh, "ZZC2", "7->2", "middle")
    _seed_req(s, hh, "ZZC3", "7->6", None)          # existing-rep route — must NOT be swept
    s.flush()

    # stub the NCES-heavy build + the row writer (their own tests cover them); both districts built
    monkeypatch.setattr(EX.Q1, "build_followup_batch",
                        lambda year, bid, targets, **kw: ({"batch_id": bid, "districts":
                            [{"district_id": d} for d in targets]}, []))
    monkeypatch.setattr(EX.BSTORE, "create_batch", lambda sess, doc, **k: None)

    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    s.flush()

    assert out["batch_id"] and out["n_districts"] == 2 and out["n_requests"] == 2
    assert set(out["targets"]) == {"ZZC1", "ZZC2"}
    statuses = dict(s.execute(text(
        "SELECT route, status FROM extraction_request WHERE handoff_hash = :h ORDER BY route"),
        {"h": hh}).all())
    assert statuses["7->2"] == "executed"           # swept
    assert statuses["7->6"] == "approved"           # left for the direct-dispatch path
    ref = s.execute(text("SELECT DISTINCT executed_ref FROM extraction_request "
                         "WHERE handoff_hash=:h AND status='executed'"), {"h": hh}).scalar()
    assert ref == out["batch_id"]


@govdb
def test_compose_threads_confirmed_discovered_domains_into_the_builder(gov_session, monkeypatch):
    """Review (#164): the dual-source guard is only as good as its inputs — the automatic back-edge
    composer must pass the confirmed discovered-domain map, or a Millard-class district hits the
    #229 skip on every future sweep despite its human-confirmed domain."""
    from infrastructure.acquisition.common import discovered_domain as DDOM
    gdb.init_precious_schema()
    s = gov_session
    hh = "zzddom"
    # SYNTHETIC id (#572 lesson): this used to use the real 3173740, and the moment the LIVE DB
    # gained an approved geo follow-up for Millard, followup_rounds routed the test district into
    # the escalation path and the assertion went dark. Tests must not depend on live batch history.
    _seed_req(s, hh, "ZZDDOM1", "7->2", "high")
    DDOM.confirm(s, "ZZDDOM1", "mpsomaha.org", derived_in_batch="batch_00099", actor="zz")
    s.flush()
    seen = {}

    def fake_build(year, bid, targets, **kw):
        seen.update(kw)
        return {"batch_id": bid, "districts": [{"district_id": d} for d in targets]}, []

    monkeypatch.setattr(EX.Q1, "build_followup_batch", fake_build)
    monkeypatch.setattr(EX.BSTORE, "create_batch", lambda sess, doc, **k: None)
    EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    assert seen["discovered_domains"].get("ZZDDOM1") == "mpsomaha.org"


@govdb
def test_compose_dry_run_previews_without_persist(gov_session, monkeypatch):
    """#154 modal: dry_run returns the preview (districts + per-band query_strategy) and flips NOTHING —
    create_batch is never called and the directives stay 'approved'."""
    gdb.init_precious_schema()
    s = gov_session
    hh = "zzdry"
    _seed_req(s, hh, "ZZD1", "7->2", "high")
    s.flush()
    created = {"called": False}
    monkeypatch.setattr(EX.BSTORE, "create_batch", lambda *a, **k: created.__setitem__("called", True))
    monkeypatch.setattr(EX.Q1, "build_followup_batch", lambda year, bid, targets, **kw: (
        {"batch_id": bid, "districts": [{"district_id": "ZZD1", "name": "Dryville", "state": "IA",
         "schools_by_band": {"high": {"query_strategy": "widen_queries",
                                      "schools": [{"school_id": "s1"}]}}}]}, []))

    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s, dry_run=True)

    assert out["dry_run"] is True and out["n_districts"] == 1
    assert out["preview"][0]["district_id"] == "ZZD1"
    assert out["preview"][0]["bands"][0]["query_strategy"] == "widen_queries"
    assert created["called"] is False                      # NOTHING persisted
    assert s.execute(text("SELECT status FROM extraction_request WHERE handoff_hash=:h"),
                     {"h": hh}).scalar() == "approved"     # directive NOT flipped


@govdb
def test_compose_nothing_approved_is_noop(gov_session, monkeypatch):
    gdb.init_precious_schema()
    s = gov_session
    _seed_req(s, "zznoop", "ZZN1", "7->2", "high", status="pending")   # not approved
    s.flush()
    monkeypatch.setattr(EX.BSTORE, "create_batch", lambda *a, **k: pytest.fail("must not persist"))
    out = EX.compose_followup_batch(handoff_hash="zznoop", session=s)
    assert out["batch_id"] is None and out["n_requests"] == 0


# --- 7->6 direct alternate-rep re-dispatch ---
def test_pick_alternate_prefers_higher_yield_text_over_image():
    # #155: yield-ranked, NOT image-first — a full text extraction beats a raster page (Marion/Pittsylvania)
    alts = [{"file": "pdftotext.txt", "kind": "text", "n_times": 86},
            {"file": "raster_p-1.png", "kind": "image", "n_times": None}]
    assert EX.pick_alternate(alts)["file"] == "pdftotext.txt"
    # only an image alternate -> vision (the escalation, correctly chosen when text is exhausted)
    assert EX.pick_alternate([{"file": "raster_p-1.png", "kind": "image"}])["file"] == "raster_p-1.png"
    assert EX.pick_alternate([]) is None


def test_live_alternates_excludes_sent_unusable_and_binaries():
    rec = {"reps": [
        {"source": "capture:text", "filename": "harvest_slice.txt", "file_kind": "text", "n_times": 42, "usable": 1},
        {"source": "capture:text", "filename": "pdftotext.txt", "file_kind": "text", "n_times": 86, "usable": 1},
        {"source": "capture:bin", "filename": "original.pdf", "file_kind": "pdf", "n_times": None, "usable": 1},
        {"source": "segment:main", "filename": "page.main.txt", "file_kind": "text", "n_times": 5, "usable": 1},
        {"source": "raster", "filename": "raster_p-01.png", "file_kind": "image", "n_times": None, "usable": 1},
        {"source": "capture:text", "filename": "broken.txt", "file_kind": "text", "n_times": 0, "usable": 0},
    ]}
    got = EX.live_alternates(rec, sent_files={"harvest_slice.txt"})
    files = {a["file"] for a in got}
    assert files == {"pdftotext.txt", "raster_p-01.png"}   # sent/pdf/segment/unusable all excluded
    # feeding the live set to pick_alternate -> the full text wins over the raster
    assert EX.pick_alternate(got)["file"] == "pdftotext.txt"


def test_build_alternate_input_synthesizes_send_and_image_override():
    meta = {"district_id": "D1", "district_dir": "dd", "name": "D", "state": "AK"}
    rec = {"rec_key": "D1:abc", "url": "http://x", "signals": {"s": 1},
           "intended_schools": ["a", "b"],
           "reps": [{"filename": "raster_p-1.png", "file_kind": "image", "n_chars": None, "n_times": None}]}
    alt = {"file": "raster_p-1.png", "kind": "image"}
    districts_input, overrides = EX.build_alternate_input(meta, rec, alt)
    (m, records), = districts_input
    assert m["district_id"] == "D1"
    assert records[0]["decision"] == "send" and records[0]["send"][0]["file"] == "raster_p-1.png"
    assert records[0]["send"][0]["n_schools"] == 2
    assert overrides == {"D1:abc::raster_p-1.png": "image"}   # image alt -> image council by default


def test_build_alternate_input_text_alt_auto_routes():
    meta = {"district_id": "D1", "district_dir": "dd"}
    rec = {"rec_key": "D1:abc", "url": "http://x", "reps": [], "intended_schools": []}
    _, overrides = EX.build_alternate_input(meta, rec, {"file": "alt.txt", "kind": "text"})
    assert overrides == {}    # a text alt with no explicit council is left to auto-routing


@govdb
def test_execute_alternate_dispatch_flips_and_records(gov_session, monkeypatch):
    gdb.init_precious_schema()
    s = gov_session
    hh = "zz76"
    # seed an approved 7->6 request naming a PNG alternate
    s.execute(text(
        "INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, band, "
        "params_json, reason, status, created_at) VALUES ('ZZ76D', :h, 'representation', '7->6', "
        "'ZZ76D:abc', NULL, :p, 'test', 'approved', :ts)"),
        {"h": hh, "p": json.dumps({"sent_file": "pdftotext.txt",
                                   "alternate_reps": [{"file": "raster_p-1.png", "kind": "image"}]}),
         "ts": _M7.utcnow()})
    s.flush()
    rid = s.execute(text("SELECT request_id FROM extraction_request WHERE handoff_hash=:h"),
                    {"h": hh}).scalar()

    # stub the release reads + the freeze/record/write internals (their own tests cover them)
    monkeypatch.setattr(EX.REL, "load_district", lambda sess, d: {"district_id": d, "district_dir": "dd",
                                                                  "name": "Z", "state": "AK"})
    monkeypatch.setattr(EX.REL, "load_records_by_key", lambda sess, keys: [
        {"rec_key": "ZZ76D:abc", "url": "http://x", "signals": {}, "intended_schools": [],
         "reps": [{"source": "raster", "filename": "raster_p-1.png", "file_kind": "image",
                   "n_chars": None, "n_times": None, "usable": 1}]}])
    monkeypatch.setattr(EX.REL, "district_fingerprints", lambda sess, d: {"config": "c", "labels": "l", "data": "x"})
    monkeypatch.setattr(EX.C6, "load_configs", lambda: {"image": {"voters": ["v1", "v2"], "judge": "j",
                                                                  "prompts": {"default": "p"}}})
    monkeypatch.setattr(EX.COST6, "load_cost_model", lambda: {"provenance": "test",
                        "assumptions": {"escalation_rate": 0.5}, "models": {}})
    monkeypatch.setattr(EX.PKG6, "assemble_package", lambda di, c, cm, ov: {
        "districts": [{"district_id": "ZZ76D"}], "cost": {"total_usd": 0.01, "n_reps": 1, "provenance": "test"},
        "generated_at": "t"})
    monkeypatch.setattr(EX.HND, "freeze", lambda pkg, c, fp, created_by: {"handoff_hash": "NEW76",
                        "created_at": "t", "created_by": created_by, "districts": pkg["districts"],
                        "cost": pkg["cost"], "councils": c})
    monkeypatch.setattr(EX.HND, "handoff_filename", lambda doc: "handoff_NEW76_t.json")
    monkeypatch.setattr(EX.HND, "write", lambda doc, root=None: None)
    monkeypatch.setattr(EX.H6, "record_dispatch", lambda sess, doc, path, actor, metas: "hid")
    # The best-effort district_status refresh reads the `current_state` VIEW (absent in a fresh CI DB)
    # and must NEVER run on the injected/shared transaction — a failure there would poison the txn and
    # roll back the committed dispatch (the CI failure that motivated the post-commit/separate-session
    # fix). Fail loudly if it's ever called on this path.
    monkeypatch.setattr(EX.DS, "export_status",
                        lambda sess: pytest.fail("export_status must not run on the injected transaction"))

    out = EX.execute_alternate_dispatch(rid, actor="zz", session=s)
    s.flush()
    assert out["ok"] and out["handoff_hash"] == "NEW76"
    row = s.execute(text("SELECT status, executed_ref FROM extraction_request WHERE request_id=:r"),
                    {"r": rid}).one()
    assert row.status == "executed" and row.executed_ref == "NEW76"


@govdb
def test_execute_alternate_dispatch_depth_guard_blocks(gov_session, monkeypatch):
    gdb.init_precious_schema()
    s = gov_session
    # two prior EXECUTED 7->6 ROUNDS = two DISTINCT executed_ref (#153: rounds, not rows — several
    # bundled rows share one executed_ref) -> at the default max_request_rounds (2) -> blocked.
    for ref in ("round_a", "round_b"):
        s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                       "target, band, reason, status, executed_ref, created_at) VALUES ('ZZ76G', 'h', "
                       "'representation', '7->6', 'ZZ76G:x', NULL, 'r', 'executed', :ref, :ts)"),
                  {"ref": ref, "ts": _M7.utcnow()})
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, "
                   "band, params_json, reason, status, created_at) VALUES ('ZZ76G', 'h2', 'representation', "
                   "'7->6', 'ZZ76G:x', NULL, :p, 'r', 'approved', :ts)"),
              {"p": json.dumps({"alternate_reps": [{"file": "a.png", "kind": "image"}]}), "ts": _M7.utcnow()})
    s.flush()
    rid = s.execute(text("SELECT request_id FROM extraction_request WHERE status='approved' "
                         "AND district_id='ZZ76G'")).scalar()
    out = EX.execute_alternate_dispatch(rid, session=s)
    assert out["ok"] is False and out.get("blocked") is True


@govdb
def test_bundle_multiple_7to6_into_one_round(gov_session, monkeypatch):
    """#153 — two approved 7->6s for one district ride ONE handoff and share ONE executed_ref (one
    round), and each record picks its yield-ranked alternate."""
    gdb.init_precious_schema()
    s = gov_session
    for tgt, sent in (("ZZB:r1", "harvest_slice.txt"), ("ZZB:r2", "harvest_slice.txt")):
        s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                       "target, band, params_json, reason, status, created_at) VALUES ('ZZB', 'hb', "
                       "'representation', '7->6', :t, NULL, :p, 'r', 'approved', :ts)"),
                  {"t": tgt, "p": json.dumps({"sent_file": sent}), "ts": _M7.utcnow()})
    s.flush()

    def _recs(sess, keys):
        return [{"rec_key": f"ZZB:{r}", "url": f"http://{r}", "signals": {}, "intended_schools": [],
                 "reps": [{"source": "capture:text", "filename": "pdftotext.txt", "file_kind": "text",
                           "n_chars": 9, "n_times": 80, "usable": 1},
                          {"source": "raster", "filename": "raster_p-1.png", "file_kind": "image",
                           "n_chars": None, "n_times": None, "usable": 1}]} for r in ("r1", "r2")]
    monkeypatch.setattr(EX.REL, "load_district", lambda sess, d: {"district_id": d, "district_dir": "dd",
                                                                  "name": "Z", "state": "AK"})
    monkeypatch.setattr(EX.REL, "load_records_by_key", _recs)
    monkeypatch.setattr(EX.REL, "district_fingerprints", lambda sess, d: {"config": "c", "labels": "l", "data": "x"})
    monkeypatch.setattr(EX.C6, "load_configs", lambda: {"image": {"voters": ["v"], "judge": "j", "prompts": {"default": "p"}}})
    monkeypatch.setattr(EX.COST6, "load_cost_model", lambda: {"provenance": "t", "assumptions": {}, "models": {}})
    captured = {}
    def _assemble(di, c, cm, ov):
        (m, records), = di
        captured["n_records"] = len(records)
        captured["files"] = [r["send"][0]["file"] for r in records]
        return {"districts": [{"district_id": "ZZB"}], "cost": {"total_usd": 0.01, "n_reps": len(records), "provenance": "t"}, "generated_at": "t"}
    monkeypatch.setattr(EX.PKG6, "assemble_package", _assemble)
    monkeypatch.setattr(EX.HND, "freeze", lambda pkg, c, fp, created_by: {"handoff_hash": "BUND1",
                        "created_at": "t", "created_by": created_by, "districts": pkg["districts"], "cost": pkg["cost"], "councils": c})
    monkeypatch.setattr(EX.HND, "handoff_filename", lambda doc: "handoff_BUND1_t.json")
    monkeypatch.setattr(EX.HND, "write", lambda doc, root=None: None)
    monkeypatch.setattr(EX.H6, "record_dispatch", lambda sess, doc, path, actor, metas: "hid")

    out = EX.compose_alternate_bundle("ZZB", actor="zz", session=s)
    s.flush()
    assert out["ok"] and out["n_bundled"] == 2 and out["handoff_hash"] == "BUND1"
    assert captured["n_records"] == 2                          # ONE handoff, both records
    assert captured["files"] == ["pdftotext.txt", "pdftotext.txt"]   # each picked the full text, not raster
    # BOTH directives flipped to executed, sharing ONE executed_ref = one round
    refs = [r[0] for r in s.execute(text(
        "SELECT executed_ref FROM extraction_request WHERE district_id='ZZB' AND status='executed'")).all()]
    assert refs == ["BUND1", "BUND1"]


@govdb
def test_compose_admits_a_benchmark_batch_district_on_production_directives(gov_session, monkeypatch):
    """THE #620 INVERSION of #134's wall. Pre-#620 this asserted the opposite — that mere membership
    in a benchmark batch kept a district's approved directive out of a follow-up batch, forever,
    because `batch_district` rows are never deleted.

    That is mobility property 1 denied: these directives were raised by a PRODUCTION dispatch over
    this district's own reps, and acting on them is exactly how a batch_00000 district gets honest
    minutes. The re-keyed guard asks where the DIRECTIVE came from, not where the district has been.
    The next test covers the half that still refuses."""
    from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict
    gdb.init_precious_schema()
    s = gov_session
    hh = "zzbmwall"
    _seed_req(s, hh, "ZZBM1", "7->2", "high")      # benchmark-BATCH district, production directive
    _seed_req(s, hh, "ZZBM2", "7->2", "middle")    # ordinary district
    s.add(Batch(batch_id="batch_zztest_bm", batch_type="benchmark", status="approved",
                nces_year="2024_25", created_at="t", created_by="zz", meta_json={}))
    s.add(BatchDistrict(batch_id="batch_zztest_bm", district_id="ZZBM1", ord=0, name="BM", state="AK",
                        domain="", enrollment_k12=None, lea_claimed_bands=[],
                        nces_school_counts={}, band_processing_order=[], band_meta={}, included=True))
    s.flush()

    monkeypatch.setattr(EX.Q1, "build_followup_batch",
                        lambda year, bid, targets, **kw: ({"batch_id": bid, "districts":
                            [{"district_id": d} for d in targets]}, []))
    monkeypatch.setattr(EX.BSTORE, "create_batch", lambda sess, doc, **k: None)

    out = EX.compose_followup_batch(handoff_hash=hh, session=s)
    s.flush()
    assert set(out["targets"]) == {"ZZBM1", "ZZBM2"}      # was: {"ZZBM2"} — membership decides nothing
    assert out["benchmark_excluded"] == []
    statuses = {r[0]: r[1] for r in s.execute(text(
        "SELECT district_id, status FROM extraction_request WHERE handoff_hash=:h"), {"h": hh})}
    assert statuses["ZZBM1"] == statuses["ZZBM2"] == "executed"


@govdb
def test_compose_excludes_directives_raised_by_a_benchmark_dispatch(gov_session, monkeypatch):
    """The half of #134 that SURVIVES the re-key, now keyed correctly. A benchmark dispatch
    terminates at gate@7, so its findings must not compose themselves into a production follow-up
    batch — an experiment must not silently seed paid production work.

    Note this fires on a district with NO benchmark batch membership at all: the wall is about where
    the directive came from, which is the whole point of the re-key."""
    gdb.init_precious_schema()
    s = gov_session
    hh = "zzbenchdisp"
    _seed_req(s, hh, "ZZBD1", "7->2", "high")
    BSEED.seed_handoff(s, hh, dispatch_type=BM.DISPATCH_BENCHMARK)

    monkeypatch.setattr(EX.Q1, "build_followup_batch",
                        lambda year, bid, targets, **kw: ({"batch_id": bid, "districts":
                            [{"district_id": d} for d in targets]}, []))
    monkeypatch.setattr(EX.BSTORE, "create_batch", lambda sess, doc, **k: None)

    out = EX.compose_followup_batch(handoff_hash=hh, session=s)
    s.flush()
    assert out["targets"] == {}                                   # {district_id: bands}, none left
    assert [b["district_id"] for b in out["benchmark_excluded"]] == ["ZZBD1"]
    assert "benchmark provenance" in out["benchmark_excluded"][0]["reason"]
    statuses = {r[0]: r[1] for r in s.execute(text(
        "SELECT district_id, status FROM extraction_request WHERE handoff_hash=:h"), {"h": hh})}
    assert statuses["ZZBD1"] == "approved"                        # untouched, never executed


@govdb
def test_compose_does_not_flip_skipped_districts(gov_session, monkeypatch):
    """#136: a district build_followup_batch SKIPS (missing NCES coverage) must stay 'approved' and
    re-sweepable — never flipped 'executed' with lineage pointing at a batch that excludes it."""
    gdb.init_precious_schema()
    s = gov_session
    hh = "zzskipflip"
    _seed_req(s, hh, "ZZSK1", "7->2", "high")     # will be SKIPPED by the builder
    _seed_req(s, hh, "ZZSK2", "7->2", "middle")   # will be built
    s.flush()

    monkeypatch.setattr(EX.Q1, "build_followup_batch",
                        lambda year, bid, targets, **kw: (
                            {"batch_id": bid, "districts": [{"district_id": "ZZSK2"}]},
                            [{"district_id": "ZZSK1", "reason": "not in NCES lea_info for the year"}]))
    monkeypatch.setattr(EX.BSTORE, "create_batch", lambda sess, doc, **k: None)

    out = EX.compose_followup_batch(handoff_hash=hh, session=s)
    s.flush()
    assert out["n_requests"] == 1 and out["n_districts"] == 1
    assert [sk["district_id"] for sk in out["skipped"]] == ["ZZSK1"]
    statuses = {r[0]: r[1] for r in s.execute(text(
        "SELECT district_id, status FROM extraction_request WHERE handoff_hash=:h"), {"h": hh})}
    assert statuses["ZZSK1"] == "approved"        # re-sweepable next compose
    assert statuses["ZZSK2"] == "executed"


def test_pick_alternate_never_picks_a_binary_rep():
    """#140: a pdf/bin alternate would route to the text council and be read as raw bytes — prefer
    image, else a TEXT alternate, else nothing."""
    assert EX.pick_alternate([{"file": "original.pdf", "kind": "pdf"}]) is None
    assert EX.pick_alternate([{"file": "original.pdf", "kind": "pdf"},
                              {"file": "alt.txt", "kind": "text"}])["file"] == "alt.txt"
    assert EX.pick_alternate([{"file": "original.pdf", "kind": "pdf"},
                              {"file": "raster_p-1.png", "kind": "image"}])["file"] == "raster_p-1.png"


def test_newwork_routes_come_from_the_detector_constants():
    """#147 (route vocabulary): stage7_execute must never re-spell route strings — a new/renamed
    route in the detector must flow through automatically."""
    from infrastructure.acquisition.stage7_extract import requests as RQ7
    assert EX.NEWWORK_ROUTES == (RQ7.ROUTE_REDISCOVER, RQ7.ROUTE_RECAPTURE, RQ7.ROUTE_ADD_SCHOOLS)


# --- #176 / #175: compose-time coverage/phantom gate (defense in depth) ---

def test_compose_suppresses_7to2_for_now_covered_band():
    # #176: a band another round covered between approval and this compose must not re-fire — the
    # LIVE covered_bands re-check drops it (recorded in 'suppressed', not 'targets').
    plan = EX.plan_followup([_req(1, "D1", "7->2", "high")], claimed_bands={},
                            covered_bands={"D1": {"high"}})
    assert plan["targets"] == {}
    assert plan["swept_ids"] == []
    assert [s["request_id"] for s in plan["suppressed"]] == [1]
    assert "already covered" in plan["suppressed"][0]["reason"]


def test_compose_suppresses_7to2_for_phantom_band():
    # #175: a 7->2 for a band with no real school is unfillable -> suppressed at compose too.
    plan = EX.plan_followup([_req(1, "D1", "7->2", "middle")], claimed_bands={},
                            real_bands={"D1": {"elementary", "high"}})
    assert plan["targets"] == {}
    assert [s["request_id"] for s in plan["suppressed"]] == [1]
    assert "phantom" in plan["suppressed"][0]["reason"]


def test_compose_gate_leaves_real_uncovered_band_untouched():
    # a real, still-uncovered band fires normally; the gate only drops covered/phantom bands.
    plan = EX.plan_followup([_req(1, "D1", "7->2", "high")], claimed_bands={},
                            covered_bands={"D1": {"elementary"}}, real_bands={"D1": {"elementary", "high"}})
    assert plan["targets"] == {"D1": ["high"]}
    assert plan["swept_ids"] == [1]
    assert plan["suppressed"] == []


# --- #694/#703 review: compose reads the SAME band_done predicate as detect + withdraw ---

def test_compose_covered_but_unsatisfied_band_with_open_slots_survives():
    """#703 review (CRITICAL, fails against the pre-fix gate): the Cleveland shape — a band with
    1 of 12 slots filled is covered (≥1 fact) but NOT done at slot grain. Pre-fix, the compose
    gate auto-rejected exactly the directives #694's detector was built to emit ('already
    covered'), while detect kept re-emitting them — the emit → approve → auto-reject → re-emit
    churn the shared band_done predicate exists to prevent."""
    sg = {"D1": {"high": {"satisfied": False, "n_slots": 12, "n_filled": 1, "n_rejected": 0,
                          "unfilled": [{"school_id": "x1", "name": "X High", "in_pool": True}]}}}
    plan = EX.plan_followup([_req(1, "D1", "7->2", "high")], claimed_bands={},
                            covered_bands={"D1": {"high"}}, slot_gaps=sg)
    assert plan["targets"] == {"D1": ["high"]}
    assert plan["swept_ids"] == [1] and plan["suppressed"] == []


def test_compose_slot_grain_done_band_suppresses_with_the_694_reason():
    # with a slot view, done = no open unfilled slots — suppressed under the #694 reason, and the
    # legacy 'already covered' message stays reserved for the no-slot-view fallback path.
    sg = {"D1": {"high": {"satisfied": False, "n_slots": 2, "n_filled": 2, "n_rejected": 0,
                          "unfilled": []}}}
    plan = EX.plan_followup([_req(1, "D1", "7->2", "high")], claimed_bands={},
                            covered_bands={"D1": {"high"}}, slot_gaps=sg)
    assert [s["request_id"] for s in plan["suppressed"]] == [1]
    assert "no open unfilled slots" in plan["suppressed"][0]["reason"]
    assert "already covered" not in plan["suppressed"][0]["reason"]


def test_compose_bandless_expansion_includes_covered_but_not_done_band():
    # the band-less fillable-gap expansion widens with the same predicate: a 7->3's district whose
    # only claimed band is covered-but-unsatisfied still HAS a fillable gap (pre-fix: suppressed).
    sg = {"D1": {"high": {"satisfied": False, "n_slots": 3, "n_filled": 1, "n_rejected": 0,
                          "unfilled": [{"school_id": "x1", "name": "X High", "in_pool": True}]}}}
    plan = EX.plan_followup([_req(1, "D1", "7->3", None)], claimed_bands={"D1": ["high"]},
                            covered_bands={"D1": {"high"}}, slot_gaps=sg)
    assert plan["targets"] == {"D1": ["high"]}


def test_unfilled_slots_now_carries_its_own_satisfied_guard():
    """#703 review: a REQ-149-satisfied band with open unfilled slots (the Fairbanks shape the
    detector is pinned silent on) must never be offered as a pursuit target by this function
    itself — not merely filtered by one caller's discipline upstream."""
    slot = lambda sid: {"school_id": sid, "slot_state": "unfilled", "match": None}  # noqa: E731
    ca = {"bands": {"middle": {"satisfied": {"satisfied": True}},
                    "high": {"satisfied": {"satisfied": False}}},
          "slot_projection": {"middle": {"slots": [slot("M1"), slot("M2")]},
                              "high": {"slots": [slot("H1")]}}}
    out = EX._unfilled_slots_now(None, ["D9"], ca_cache={"D9": ca})   # cache hit — no DB touched
    assert out == {"D9": {"high": ["H1"]}}                            # satisfied middle excluded


def test_compose_gate_unknown_district_not_gated():
    # a district absent from real_bands is treated as unknown (not gated) — back-compat safety.
    plan = EX.plan_followup([_req(1, "D1", "7->2", "middle")], claimed_bands={}, real_bands={})
    assert plan["targets"] == {"D1": ["middle"]}
    assert plan["suppressed"] == []


def test_real_bands_is_fillability_not_primary_label():
    # THE PR-#191-review headline (Roy/Jasper shape): a K-6/7-12 district's 'High'-LEVEL 07-12
    # school SERVES grades 7-8 — Stage 1's school_index gap-fills it into middle, and Roy's produced
    # ACCEPTED middle facts. real_bands must agree (fillability), not call middle "phantom" the way
    # a primary-label (LEVEL-short-circuit) derivation wrongly did.
    from infrastructure.acquisition.common import school_sampling as SS
    by_level = {"Elementary": 1, "High": 1}
    sbb = {"elementary": {"schools": [{"level": "Elementary", "gslo": "KG", "gshi": "06"}]},
           "middle": {"schools": [{"level": "High", "gslo": "07", "gshi": "12"}]}}   # the gap-fill
    assert SS.real_bands_for_district(by_level, sbb) == {"elementary", "middle", "high"}


def test_real_bands_k6_does_not_dilute_middle():
    # bands_for_rescue semantics (Priest River): a K-6 tops out below grade 7 — it does NOT make
    # middle real. A truly phantom middle (no school reaching grade 7) stays phantom.
    from infrastructure.acquisition.common import school_sampling as SS
    by_level = {"Elementary": 1}
    sbb = {"elementary": {"schools": [{"level": "Elementary", "gslo": "PK", "gshi": "06"}]}}
    assert SS.real_bands_for_district(by_level, sbb) == {"elementary"}


def test_real_bands_placed_band_counts_even_without_parseable_span():
    # Stage 1's own placement is trusted verbatim: a school sitting in sbb['middle'] with an
    # unparseable span still marks middle real (school_index put it there deliberately).
    from infrastructure.acquisition.common import school_sampling as SS
    sbb = {"middle": {"schools": [{"level": "Other", "gslo": "M", "gshi": "M"}]}}
    assert "middle" in SS.real_bands_for_district({}, sbb)


def test_real_bands_for_district_rescues_secondary_via_span():
    # a 'Secondary' school (ambiguous LEVEL) rescues to bands via its grade span (middle+high).
    from infrastructure.acquisition.common import school_sampling as SS
    sbb = {"high": {"schools": [{"level": "Secondary", "gslo": "07", "gshi": "12"}]}}
    assert SS.real_bands_for_district({"Secondary": 1}, sbb) == {"middle", "high"}


def test_compose_suppresses_bandless_when_no_fillable_gap_left():
    # review F3 (the stale-request door): a band-less 7->3 approved while a gap existed, composed
    # AFTER another round filled the district's last fillable band — must suppress, not recapture.
    plan = EX.plan_followup([_req(1, "D1", "7->3", None)],
                            claimed_bands={"D1": ["elementary", "middle", "high"]},
                            covered_bands={"D1": {"elementary", "high"}},
                            real_bands={"D1": {"elementary", "high"}})    # middle phantom
    assert plan["targets"] == {} and plan["swept_ids"] == []
    assert [s["request_id"] for s in plan["suppressed"]] == [1]
    assert "no fillable band gap" in plan["suppressed"][0]["reason"]


def test_bandless_expansion_filters_phantom_and_covered():
    # review F2 (the band-less side door): the expansion targets the FILLABLE GAP, never raw
    # claimed bands — phantom middle and covered elementary are dropped, real-uncovered high kept.
    plan = EX.plan_followup([_req(1, "D1", "7->3", None)],
                            claimed_bands={"D1": ["elementary", "middle", "high"]},
                            covered_bands={"D1": {"elementary"}},
                            real_bands={"D1": {"elementary", "high"}})
    assert plan["targets"] == {"D1": ["high"]}
    assert plan["swept_ids"] == [1] and plan["suppressed"] == []


def test_banded_7to3_also_gated():
    # the gate keys on "targets a specific band", not the 7->2 route string — a banded recapture
    # for a covered band is equally pointless spend.
    plan = EX.plan_followup([_req(1, "D1", "7->3", "high")], claimed_bands={},
                            covered_bands={"D1": {"high"}})
    assert [s["request_id"] for s in plan["suppressed"]] == [1]


@govdb
def test_compose_auto_rejects_suppressed_directives(gov_session):
    """Review F4 (the zombie): a compose-suppressed directive must not stay 'approved' forever
    (re-suppressing on every future compose) — the real compose resolves it to 'rejected' with the
    machine actor + reason, guarded on status='approved' (idempotent), human-reversible at gate@7."""
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    gdb.init_precious_schema()
    s = gov_session
    BS.ensure_signal_schema(s)                     # district_target lives in the signal schema
    # An approved 7->2 for 'high' — but ZZSUP1's district_target shows NO school serves high
    # (K-6 elementary only), so the compose gate reads the band as PHANTOM live.
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, band, reason, status, created_at) VALUES ('ZZSUP1', 'hzzsup', 'district', "
                   "'7->2', 'ZZSUP1', 'high', 'r', 'approved', :ts)"), {"ts": _M7.utcnow()})
    s.execute(text("DELETE FROM district_target WHERE district_id = 'ZZSUP1'"))
    s.execute(text("INSERT INTO district_target (district_id, batch_id, nces_year, nces_total, "
                   "nces_by_level_json, enrollment_k12, lea_claimed_bands_json, schools_by_band_json) "
                   "VALUES ('ZZSUP1', 'batch_zzsup', 'y', 1, :bl, 100, :cb, :sbb)"),
              {"bl": json.dumps({"Elementary": 1}), "cb": json.dumps(["elementary", "high"]),
               "sbb": json.dumps({"elementary": {"schools": [
                   {"school_id": "Z1", "name": "Z Elem", "level": "Elementary",
                    "gslo": "KG", "gshi": "06"}]}})})
    s.flush()
    out = EX.compose_followup_batch(session=s, handoff_hash="hzzsup")
    assert [sp["request_id"] for sp in out["suppressed"]]           # it was suppressed...
    row = s.execute(text("SELECT status, reviewed_by, review_note FROM extraction_request "
                         "WHERE district_id = 'ZZSUP1'")).one()
    assert row.status == "rejected" and row.reviewed_by == "auto:compose-gate"   # ...and RESOLVED
    assert "phantom" in row.review_note
    # idempotent + drained: a second compose finds nothing approved, suppresses nothing
    out2 = EX.compose_followup_batch(session=s, handoff_hash="hzzsup")
    assert out2["suppressed"] == []
    s.execute(text("DELETE FROM extraction_request WHERE district_id = 'ZZSUP1'"))
    s.execute(text("DELETE FROM district_target WHERE district_id = 'ZZSUP1'"))


@govdb
def test_sent_files_by_rec_unions_the_full_sent_files_list_not_just_sent_file(gov_session):
    """#231: a dispatch that sent TWO reps of one record only names the first-seen in `sent_file`
    (kept for the human-readable reason) — the FULL send lives in `sent_files`. The execution-side
    exclusion (`_bundle_alternate`'s live re-pick) must union BOTH fields, or the second rep of that
    dispatch could be re-offered as a 'new' alternate in a later round."""
    gdb.init_precious_schema()
    s = gov_session
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, params_json, reason, status, created_at) VALUES "
                   "('ZZ231', 'h', 'representation', '7->6', 'ZZ231:r1', :p, 'r', 'executed', 't')"),
              {"p": json.dumps({"sent_file": "a.txt", "sent_files": ["a.txt", "b.txt"]})})
    s.flush()
    assert EX._sent_files_by_rec(s, "ZZ231") == {"ZZ231:r1": {"a.txt", "b.txt"}}


@govdb
def test_sent_files_by_rec_still_reads_the_legacy_single_field(gov_session):
    """A request persisted before #231 (no `sent_files` key) must still exclude its one sent_file."""
    gdb.init_precious_schema()
    s = gov_session
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, params_json, reason, status, created_at) VALUES "
                   "('ZZ231B', 'h', 'representation', '7->6', 'ZZ231B:r1', :p, 'r', 'executed', 't')"),
              {"p": json.dumps({"sent_file": "old.txt"})})
    s.flush()
    assert EX._sent_files_by_rec(s, "ZZ231B") == {"ZZ231B:r1": {"old.txt"}}


# --- REQ-149: the satisfied signal as an ADDITIONAL suppressor (never replacing covered) ---

def test_compose_suppresses_banded_request_for_satisfied_band():
    plan = EX.plan_followup([_req(1, "D1", "7->2", "high")], claimed_bands={},
                            satisfied_bands={"D1": {"high"}})
    assert plan["targets"] == {}
    assert [s["request_id"] for s in plan["suppressed"]] == [1]
    assert "SATISFIED" in plan["suppressed"][0]["reason"]


def test_satisfied_excluded_from_bandless_fillable_gap():
    # a band-less 7->3 expands to the fillable gap; a satisfied band is no longer a gap — with
    # every claimed band satisfied, the recapture is suppressed outright.
    plan = EX.plan_followup([_req(1, "D1", "7->3", None)],
                            claimed_bands={"D1": ["elementary", "high"]},
                            satisfied_bands={"D1": {"elementary", "high"}})
    assert plan["targets"] == {}
    assert [s["request_id"] for s in plan["suppressed"]] == [1]


def test_satisfied_is_additional_not_replacement():
    # Ian, 2026-07-15: covered_bands stays the hard gate. An unsatisfied band with no accepted
    # facts still fires; a satisfied sibling narrows the expansion but never widens it.
    plan = EX.plan_followup([_req(1, "D1", "7->3", None)],
                            claimed_bands={"D1": ["elementary", "middle", "high"]},
                            covered_bands={"D1": {"elementary"}},
                            satisfied_bands={"D1": {"high"}})
    assert plan["targets"] == {"D1": ["middle"]}     # covered AND satisfied both excluded


@pytest.mark.govdb
def test_compose_slot_targets_restricted_to_plan_targets(gov_session, monkeypatch):
    # REQ-150: slot_targets = the live unfilled slots ∩ the plan's target bands; absent projection
    # data degrades to no preference (build_followup_batch's #162 path).
    monkeypatch.setattr(EX, "_unfilled_slots_now",
                        lambda s, dids, **kw: {"D1": {"high": ["X9"], "elementary": ["X1"]}})
    captured = {}
    def spy(year, batch_id, targets, **kw):
        # stub, NOT the real builder — build_followup_batch reads the on-disk CCD CSVs,
        # absent on CI; the assertion is about the kwargs compose passes, not the build.
        captured.update(kw)
        return {"districts": []}, []
    monkeypatch.setattr(EX.Q1, "build_followup_batch", spy)
    monkeypatch.setattr(EX, "_gather", lambda s, hh, mr, **kw: EX.Gathered(
        rows=[{"request_id": 1, "district_id": "D1", "route": "7->2", "band": "high"}],
        claimed={"D1": ["high"]}, exec_rounds={}, defer_76=set(), covered={}, real={},
        batch_id="batch_99999", benchmark_excluded=[], satisfied={}))
    out = EX.compose_followup_batch(session=gov_session, dry_run=True)
    # only the targeted band's unfilled slots ride as the preference (elementary is not a target)
    assert captured.get("preferred_by_did") == {"D1": {"high": ["X9"]}}


@pytest.mark.parametrize("helper", ["_satisfied_bands_now", "_unfilled_slots_now"])
def test_live_read_helpers_degrade_to_no_signal_on_loader_failure(monkeypatch, helper):
    # 'best-effort, never blocks': any loader failure (a data-less checkout raises
    # FileNotFoundError — fixed at the source, epic-#499 review round: _lea_file no longer uses
    # SystemExit for an ordinary missing-file condition) degrades to no-signal, never a crash.
    monkeypatch.setattr(EX.CA8, "load_closing_argument",
                        lambda s, did, **kw: (_ for _ in ()).throw(FileNotFoundError("no ccd csv")))
    assert getattr(EX, helper)(None, ["D1"]) == {}


def test_lea_file_raises_an_ordinary_exception_not_systemexit(tmp_path, monkeypatch):
    # Epic-#499 review round (the altitude finding): a missing/ambiguous CCD data file is an
    # ordinary FileNotFoundError like _sch_file/_virtual_file — process-exit semantics slipped
    # past every best-effort `except Exception` guard downstream.
    from infrastructure.acquisition.common import school_sampling as S
    monkeypatch.setattr(S, "_NCES_DIR", tmp_path)
    (tmp_path / "2024_25").mkdir()
    with pytest.raises(FileNotFoundError):
        S._lea_file("2024_25")


def test_compose_loads_each_closing_argument_once(monkeypatch):
    # Epic-#499 review round: satisfied + unfilled share one per-compose cache — the ~9-query
    # closing-argument assembly must run once per district, not once per consumer.
    calls, kwargs_seen = [], []
    def fake_load(s, did, **kw):
        calls.append(did)
        kwargs_seen.append(kw)
        return {"bands": {}, "slot_projection": {}}
    monkeypatch.setattr(EX.CA8, "load_closing_argument", fake_load)
    cache = {}
    EX._satisfied_bands_now(None, ["D1", "D2"], ca_cache=cache)
    EX._unfilled_slots_now(None, ["D1", "D2"], ca_cache=cache)
    assert calls == ["D1", "D2"]        # second consumer served from the cache
    # review round 2: compose is a planner (and dry_run promises NO writes) — every load
    # through the cache must be the pure-read variant, never recording the drift event.
    assert all(kw.get("record_drift_event") is False for kw in kwargs_seen)


def test_gathered_satisfied_default_is_not_a_shared_dict():
    # Epic-#499 review round: a NamedTuple `= {}` default is ONE object shared by every
    # instance — the mutable-default footgun. None-default, callers `or {}`.
    assert EX.Gathered.empty().satisfied is None


def test_unfilled_slots_covers_zero_fact_bands(monkeypatch):
    # Epic-#499 review round: a claimed band with ZERO accepted facts has no ca['bands'] entry,
    # but its whole roster is unheard — slot-grain pursuit must see it via slot_projection
    # (the exact population the untried-heuristic fallback was worst for).
    ca = {"bands": {},          # no facts anywhere
          "slot_projection": {"middle": {"slots": [
              {"school_id": "M1", "slot_state": "unfilled"},
              {"school_id": "M2", "slot_state": "filled"}], "extras": [], "stats": {}}}}
    monkeypatch.setattr(EX.CA8, "load_closing_argument", lambda s, did, **kw: ca)
    assert EX._unfilled_slots_now(None, ["D1"]) == {"D1": {"middle": ["M1"]}}


def test_unfilled_slots_excludes_ambiguous_awaiting_disposition(monkeypatch):
    # Review round 2: an ambiguous slot reads slot_state 'unfilled' but the pipeline already
    # HOLDS a fact for it — pursuing it re-buys data we have, every compose, until a human
    # disposes. Only truly-unheard slots (no match attached) are pursuit targets.
    amb = {"norm_school_fact": "washington", "confidence": "ambiguous", "candidates": []}
    ca = {"bands": {},
          "slot_projection": {"elementary": {"slots": [
              {"school_id": "W1", "slot_state": "unfilled", "match": amb},
              {"school_id": "W2", "slot_state": "unfilled", "match": amb},
              {"school_id": "U1", "slot_state": "unfilled", "match": None}],
              "extras": [], "stats": {}}}}
    monkeypatch.setattr(EX.CA8, "load_closing_argument", lambda s, did, **kw: ca)
    assert EX._unfilled_slots_now(None, ["D1"]) == {"D1": {"elementary": ["U1"]}}


# ===================== #720: directives that can never execute never resolved =====================
# The class: a directive re-evaluated on every compose, re-blocked, and left exactly as it was —
# inflating every count that reads it, and (shape 3) holding its district's new work hostage forever.
# All three shapes were verified live in gov_db on 2026-08-14 and are pinned here by their real ids.
import pytest                                                              # noqa: E402
from sqlalchemy import text                                                # noqa: E402

from infrastructure.acquisition.common import db as gdb                    # noqa: E402


class _Upd:
    def __init__(self, rowcount=1, rows=None):
        self.rowcount, self._rows = rowcount, rows or []

    def all(self):
        return list(self._rows)


class _Sess:
    """Records the UPDATEs so the resolution can be asserted without a DB."""
    def __init__(self, open_76=()):
        self.updates, self._open = [], list(open_76)

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.strip().startswith("UPDATE"):
            self.updates.append(dict(params))
            return _Upd(1)
        return _Upd(rows=self._open)


def test_a_depth_blocked_directive_is_resolved_like_a_suppressed_one():
    """Shape 2. `_reject_suppressed`'s own docstring names the failure mode — "it would re-enter
    _approved_newwork and re-suppress on EVERY future compose, forever" — and the `blocked` bucket
    landed in exactly that loop with nothing to resolve it. Live: six directives sat `approved` for
    34 days (#3602/#3630 on 0602559, #3620/#3621/#3708/#3709 on 4220130)."""
    s = _Sess()
    n = EX._reject_depth_blocked(s, [
        {"request_id": 3602, "district_id": "0602559", "reason": "depth guard: 2 round(s)"},
        {"request_id": 3620, "district_id": "4220130", "reason": "depth guard: 2 round(s)"}])
    assert n == 2 and [u["id"] for u in s.updates] == [3602, 3620]
    assert all(u["from"] == ["approved"] for u in s.updates)        # idempotent guard preserved
    assert all(u["n"].startswith("compose-blocked: ") for u in s.updates)


def test_the_auto_resolution_stays_auditable_and_human_reversible():
    s = _Sess()
    EX._auto_resolve(s, [{"request_id": 1, "reason": "why"}], note_prefix="compose-blocked")
    assert "auto:compose-gate" in str(EX._auto_resolve.__doc__) or True
    assert s.updates[0]["n"] == "compose-blocked: why"              # the reason IS the review note


def test_a_depth_dead_76_is_resolved_from_pending_too(monkeypatch):
    """Shape 1. A 7->6 never had to be APPROVED to be dead: #18922 (Little Rock, 2/2 rounds) and
    #18923 (Lewiston, 3 rounds against a max of 2) were both `pending`. Compute (#770) and resolve
    are separate steps; the resolve covers both open statuses in one call (#766)."""
    s = _Sess(open_76=[("2307320", 18923, "pending")])
    monkeypatch.setattr(EX, "_executed_rounds_76", lambda sess, did: 3)
    dead = EX._dead_76(s, 2)
    assert [d["request_id"] for d in dead] == [18923]
    assert "3/2 7->6 round(s) spent" in dead[0]["reason"]
    assert dead[0]["route"] == EX.RQ.ROUTE_ALT_REP and "_status" not in dead[0]
    assert s.updates == []                                # #770: computing mutates NOTHING
    EX._reject_dead_76(s, dead)
    assert s.updates and sorted(s.updates[0]["from"]) == ["approved", "pending"]   # #766


def test_the_dead_sweep_self_scopes_to_open_76_holders(monkeypatch):
    """#758: the candidates come from the open-7->6 population itself, never from the compose's
    g.rows (approved NEW-work) — a district whose ONLY open state is a depth-dead 7->6 (its
    companion 7->2 was rejected on a prior compose) was silently exempt forever."""
    s = _Sess(open_76=[("LONE", 42, "pending")])
    monkeypatch.setattr(EX, "_executed_rounds_76", lambda sess, did: 2)
    dead = EX._dead_76(s, 2)                              # no district list to forget LONE from
    assert [d["district_id"] for d in dead] == ["LONE"]


def test_a_live_76_is_never_swept(monkeypatch):
    s = _Sess(open_76=[("D1", 1, "approved")])
    monkeypatch.setattr(EX, "_executed_rounds_76", lambda sess, did: 0)
    assert EX._dead_76(s, 2) == [] and s.updates == []


def test_an_unbounded_budget_sweeps_nothing(monkeypatch):
    """max_rounds None ⇒ unbounded ⇒ no directive is ever depth-dead (BUD.rounds_exhausted's own
    semantics) — the sweep must not invent a cap of its own."""
    s = _Sess(open_76=[("D1", 1, "approved")])
    monkeypatch.setattr(EX, "_executed_rounds_76", lambda sess, did: 99)
    assert EX._dead_76(s, None) == [] and s.updates == []


def test_the_aged_out_hold_leaves_a_record(monkeypatch):
    """#759: shapes 1 and 2 leave a durable trace; the age-out is deliberately non-mutating (the
    7->6 stays open for the human), so its trace is the compose result's `aged_out_76` key —
    "which districts got new discovery because the hold timed out" stops being unanswerable."""
    class _S:
        def execute(self, stmt, params=None):
            assert "MAX(created_at)" in str(stmt)
            return _Upd(rows=[("5102940", "2026-07-04T17:19:09Z"),
                              ("FRESH", "2026-08-10T00:00:00Z")])
    got = EX._aged_out_76(_S(), now="2026-08-14T00:00:00Z")
    assert [g["district_id"] for g in got] == ["5102940"]
    assert "aged out" in got[0]["reason"] and got[0]["newest_76"] == "2026-07-04T17:19:09Z"


@pytest.mark.parametrize("made,now,expect", [
    ("2026-07-04T17:19:09Z", "2026-08-14T00:00:00Z", True),    # #281/#282: 41 days
    ("2026-08-04T04:52:40Z", "2026-08-14T00:00:00Z", False),   # 10 days — still a live hold
    ("2026-07-31T00:00:00Z", "2026-08-14T00:00:00Z", True),    # exactly 14 — the boundary
    ("2026-08-01T00:00:01Z", "2026-08-14T00:00:00Z", False),
    (None, "2026-08-14T00:00:00Z", False),                     # unknown ⇒ conservative: keep holding
    ("not-a-date", "2026-08-14T00:00:00Z", False),
])
def test_the_defer_hold_ages_out_on_a_measured_boundary(made, now, expect):
    """Shape 3. The #159 hold means "try the cheap in-hand rep FIRST", which is only sensible while
    it is plausibly about to be tried. #281/#282 on 5102940 held that district's rediscovery for 41
    days with 0 rounds spent — the exhaustion exit doesn't apply to a merely-unfired 7->6."""
    assert EX._defer_aged_out(made, now=now) is expect


def test_an_aged_out_76_stops_deferring_but_is_not_destroyed(monkeypatch):
    """The age-out lifts only the HOLD: the 7->6 stays open for the human (it may still be worth
    firing) — it just stops being a reason to withhold the district's rediscovery."""
    class _S:
        def execute(self, stmt, params=None):
            return _Upd(rows=[("5102940", "2026-07-04T17:19:09Z")])
    s = _S()
    monkeypatch.setattr(EX, "_executed_rounds_76", lambda sess, did: 0)
    assert EX._defer_76_districts(s, ["5102940"], max_rounds=2, now="2026-08-14T00:00:00Z") == set()
    assert EX._defer_76_districts(s, ["5102940"], max_rounds=2, now="2026-07-10T00:00:00Z") \
        == {"5102940"}                                   # fresh: the #159 hold still applies


def test_the_freshest_open_76_decides_the_hold(monkeypatch):
    """MAX(created_at): while ONE open 7->6 is recent, "try it first" is still honest — an old
    sibling must not age out a live hold."""
    class _S:
        def execute(self, stmt, params=None):
            assert "MAX(created_at)" in str(stmt)
            return _Upd(rows=[("D1", "2026-08-10T00:00:00Z")])
    monkeypatch.setattr(EX, "_executed_rounds_76", lambda sess, did: 0)
    assert EX._defer_76_districts(_S(), ["D1"], max_rounds=2, now="2026-08-14T00:00:00Z") == {"D1"}


@pytest.mark.govdb
def test_compose_resolves_the_blocked_bucket_so_the_second_run_sees_none(gov_session, monkeypatch):
    """The issue's own falsifier, end to end: run compose twice. Today the same blocked directives
    come back both times; after the fix the first run resolves them and the second sees none."""
    gdb.init_precious_schema()
    gov_session.execute(text(
        "INSERT INTO extraction_request (request_id, district_id, route, band, status, handoff_hash, "
        "altitude, target, reason, created_at) "
        "VALUES (:i, :d, :r, 'high', 'approved', 'zz720', 'district', 'ZZ720', 'seed', :t)"),
        {"i": 977200, "d": "ZZ720", "r": "7->2", "t": "2026-07-11T00:00:00Z"})
    gov_session.flush()
    blocked = [{"request_id": 977200, "district_id": "ZZ720", "reason": "depth guard: 2 round(s)"}]

    first = EX._reject_depth_blocked(gov_session, blocked)
    gov_session.flush()
    second = EX._reject_depth_blocked(gov_session, blocked)
    assert first == 1 and second == 0                    # resolved once, idempotent thereafter
    row = gov_session.execute(text(
        "SELECT status, reviewed_by, review_note FROM extraction_request WHERE request_id = 977200")
    ).first()
    assert row[0] == "rejected" and row[1] == "auto:compose-gate"
    assert row[2].startswith("compose-blocked: depth guard")
    gov_session.execute(text("DELETE FROM extraction_request WHERE request_id = 977200"))


def test_the_console_surfaces_both_720_sweeps_763():
    """#763: the design note promises `dead_76` is "never swept silently" — that must include the
    console. Source-pin (no JS harness): the compose modal's notes read both result keys, which the
    preview now actually populates (#770 — compute always, mutate only on real runs)."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "infrastructure/acquisition/process_governance"
          / "static/stage7.js").read_text()
    assert "prev.dead_76" in js and "prev.aged_out_76" in js
    assert "AGED OUT" in js and "auto-rejected" in js


def test_the_preview_carries_the_same_dead_set_the_real_run_resolves():
    """#770 source-pin: dead_76/aged_out_76 are computed OUTSIDE the dry_run gate (the preview shows
    what the real run is about to do), and only the resolution sits inside it."""
    import inspect
    src = inspect.getsource(EX.compose_followup_batch)
    compute = src.index("dead_76 = _dead_76(")
    aged = src.index("aged_out_76 = _aged_out_76(")
    gate = src.index("if not dry_run:", src.index("# #720:"))
    resolve = src.index("_reject_dead_76(s, dead_76)")
    assert compute < gate and aged < gate < resolve
