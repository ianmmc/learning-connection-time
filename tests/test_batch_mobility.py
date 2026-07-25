"""#617 Phase 2c — batch mobility: the DECLARED redo lever and the operator-reachable targeted composer.

MOBILITY PROPERTIES 1 AND 2 (Ian's acceptance criteria for epic #617):
  1. a district that has been in a BENCHMARK batch can later run in a FOLLOW-UP batch
  2. a district that has been in a first-run/FOLLOW-UP batch can later run in a BENCHMARK batch

Both were blocked by the same two things, and both are tested here:
  * NO COMPOSER could express either. `build_batch` (the only path `POST /api/queue/create` reached)
    applies `eligible_pool`'s already-attempted exclusion, which drops every district at
    `furthest_stage >= 3` — i.e. exactly the districts these properties are about.
    `build_followup_batch` bypasses that exclusion but was reachable only from the 5->1 / 7->1
    escalation back-edges.
  * THE REDO LEVER was `batch_type == "follow-up"` at five separate sites, so a benchmark batch got
    first-run behavior and skipped every already-attempted district even once composed.

The lever is now DECLARED on the batch, not derived from its type — see common/batch_types for why
that distinction protects the FROZEN gt:// artifacts, and `test_an_undeclared_benchmark_batch_does_
not_redo` for the regression it pins.
"""
import json
from pathlib import Path

import pytest

from infrastructure.acquisition.common import batch_types as BT
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue import queue_batch as Q1
from infrastructure.acquisition.stage4_process import process_stage4 as P4

govdb = pytest.mark.govdb


# --------------------------------------------------------------- the lever itself (pure)

def test_a_declared_redo_wins_over_the_type():
    """Declaration is the whole point: the type is a label, the flag is the decision."""
    assert BT.redoes_attempted({"batch_type": BT.BENCHMARK, "redo_attempted": True}) is True
    assert BT.redoes_attempted({"batch_type": BT.FOLLOW_UP, "redo_attempted": False}) is False
    assert BT.redoes_attempted({"batch_type": BT.FIRST_RUN, "redo_attempted": True}) is True


def test_an_undeclared_batch_falls_back_to_the_historical_follow_up_rule():
    """Every batch row and on-disk receipt predating this column declares nothing. The fallback is
    what makes Phase 2c a no-op on all 30 existing batches — no backfill, no behavior change."""
    assert BT.redoes_attempted({"batch_type": BT.FOLLOW_UP}) is True
    assert BT.redoes_attempted({"batch_type": BT.FIRST_RUN}) is False
    assert BT.redoes_attempted({"batch_type": BT.FOLLOW_UP, "redo_attempted": None}) is True
    assert BT.redoes_attempted({}) is False              # a doc with no type at all


def test_an_undeclared_benchmark_batch_does_not_redo():
    """THE REASON the lever is declared rather than derived, and the most consequential assertion in
    this file.

    All 27 batch_00000 districts hold FROZEN `discovery.json` / `candidates.json` carrying their
    hand-verified `gt://` artifacts — the FIXED yardstick. Had "benchmark batches redo" been derived
    from the type, one Stage-2 run on batch_00000 (an approved batch, one console click) would have
    re-run discovery over all 27 and, because redo also drives `merge=`, folded fresh SERP candidates
    into those frozen candidate sets. `inject_district`'s write-once guard only covers the INITIAL
    injection, so nothing else would have stopped it.

    A NEWLY composed benchmark batch declares redo=True and does re-run — that is property 2, and it
    is a different batch with different artifacts."""
    assert BT.redoes_attempted({"batch_id": "batch_00000", "batch_type": BT.BENCHMARK}) is False
    # ...while a composer-declared benchmark batch does redo:
    assert BT.default_redo_attempted(BT.BENCHMARK) is True


def test_an_invalid_batch_type_raises_rather_than_getting_first_run_behavior():
    """Unvalidated, a typo'd type matched none of the five `== "follow-up"` comparisons and silently
    got first-run behavior everywhere. `dispatch_type` (#618) validated from day one; this axis
    finally does too."""
    with pytest.raises(ValueError, match="batch_type must be one of"):
        BT.validate_batch_type("followup")
    with pytest.raises(ValueError):
        BT.validate_batch_type(None)
    assert BT.validate_batch_type(BT.BENCHMARK) == BT.BENCHMARK


# --------------------------------------------- the lever reaches the stages (fitness function)

# The five sites that derived redo/merge/todo behavior from a `batch_type` string comparison before
# Phase 2c. Any of them reverting to a literal comparison silently un-fixes property 2 — a benchmark
# batch would skip every already-attempted district again, with no test failing anywhere else.
_LEVER_SITES = [
    "infrastructure/acquisition/stage2_discover/discover_stage2.py",
    "infrastructure/acquisition/stage2_discover/headless.py",
    "infrastructure/acquisition/stage3_capture/headless.py",
    "infrastructure/acquisition/stage4_process/headless.py",
]


@pytest.mark.parametrize("relpath", _LEVER_SITES)
def test_no_stage_re_derives_the_redo_lever_from_a_batch_type_literal(relpath):
    src = (Path(__file__).resolve().parent.parent / relpath).read_text()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert 'batch_type") ==' not in code and "batch_type'] ==" not in code, (
        f"{relpath} compares batch_type directly — route the decision through "
        f"common/batch_types.redoes_attempted so a declared flag and a third batch type both work")
    assert "BT.redoes_attempted(" in code


def test_the_detector_catches_the_real_pre_phase2c_source():
    """A fitness function nobody has falsified is decoration (the #617 Phase-2a lesson). This is the
    exact expression all five sites carried before Phase 2c — the detector must reject it."""
    removed = 'redo=batch.get("batch_type") == "follow-up")'
    code = "\n".join(ln for ln in removed.splitlines() if not ln.lstrip().startswith("#"))
    assert 'batch_type") ==' in code


# --------------------------------------------------- composition: properties 1 and 2 (pure NCES stub)

def _sch(sid, band):
    return {"school_id": sid, "name": f"{sid} School", "level": band.capitalize(),
            "gslo": "09", "gshi": "12", "is_charter": "No", "bands": [band]}


@pytest.fixture
def nces(monkeypatch):
    """Synthetic NCES for one district, D1 — no NCES files, no DB."""
    idx = {"D1": {"elementary": [_sch("e1", "elementary")], "high": [_sch("h1", "high")]}}
    monkeypatch.setattr(Q1.S, "lea_info", lambda y: {
        "D1": {"name": "Testville", "state": "IA", "website": "test.org", "status": "Open",
               "claimed_bands": {"elementary", "high"}}})
    monkeypatch.setattr(Q1.S, "school_index", lambda y: idx)
    monkeypatch.setattr(Q1.S, "school_level_counts", lambda y: {"D1": {"total": 2, "by_level": {}}})
    monkeypatch.setattr(Q1, "load_enrollment", lambda: {"D1": 5000})
    monkeypatch.setattr(Q1, "load_ctc_ids", lambda: set())
    return idx


def _attempted_registry():
    """D1 has been all the way through the pipeline — the state that makes both properties hard."""
    return {"districts": {"D1": {"furthest_stage": 7, "name": "Testville", "state": "IA"}}}


def test_the_drawn_composer_still_refuses_an_already_attempted_district(nces):
    """The baseline that makes the next two tests meaningful: `build_batch` drops D1, so routing
    every batch type through it (the pre-Phase-2c endpoint) could never express either property."""
    doc, _gap, _dom, _n = Q1.build_batch("2024_25", 12, "batch_00099", _attempted_registry())
    assert doc["districts"] == []


def test_mobility_1_a_benchmark_batch_district_composes_a_targeted_follow_up_batch(nces):
    """PROPERTY 1. D1 stands in for a batch_00000 district: already at furthest_stage 7, so the drawn
    composer above refuses it. The targeted composer admits it, and the follow-up declares redo — so
    Stages 2/3/4 actually re-run rather than skipping on its on-disk artifacts."""
    targets = Q1.all_bands_targets("2024_25", ["D1"])
    assert targets == {"D1": ["elementary", "high"]}      # every covered band, BANDS order
    doc, skipped = Q1.build_followup_batch("2024_25", "batch_00099", targets)
    assert [d["district_id"] for d in doc["districts"]] == ["D1"] and skipped == []
    assert BT.redoes_attempted({**doc, "batch_type": BT.FOLLOW_UP,
                                "redo_attempted": BT.default_redo_attempted(BT.FOLLOW_UP)}) is True


def test_mobility_2_an_attempted_district_composes_a_benchmark_batch_and_redoes(nces):
    """PROPERTY 2, the one that failed hardest before: BOTH blockers had to go. The same targeted
    composer serves benchmark (only `batch_type` at persist differs), and the declared lever is what
    makes the composed batch actually re-run — without it the batch would compose and then skip
    every district at reconcile."""
    doc, skipped = Q1.build_followup_batch(
        "2024_25", "batch_00099", Q1.all_bands_targets("2024_25", ["D1"]))
    assert [d["district_id"] for d in doc["districts"]] == ["D1"] and skipped == []
    batch = {**doc, "batch_type": BT.BENCHMARK,
             "redo_attempted": BT.default_redo_attempted(BT.BENCHMARK)}
    assert BT.redoes_attempted(batch) is True


def test_all_bands_targets_drops_a_band_with_no_school_level_coverage(nces):
    """`middle` is claimed by nobody in the stub index — a target band with no coverage would be
    dropped by build_followup_batch anyway, but emitting it would make the composed batch's stated
    intent disagree with what it selected."""
    assert "middle" not in Q1.all_bands_targets("2024_25", ["D1"])["D1"]


# ------------------------------------------- the lever composes with reconcile (pure, tmp_path)

def _processed_district(tmp_path, did="D1"):
    d = tmp_path / f"{did}_testville"
    (d / "captures").mkdir(parents=True)
    (d / "discovery.json").write_text(json.dumps(
        {"district_id": did, "name": "Testville", "state": "IA", "domain": "test.org",
         "batch_id": "batch_00098", "schools": []}))
    (d / "captures.json").write_text(json.dumps([]))
    (d / "processed.json").write_text(json.dumps([]))
    return P4.find_districts(tmp_path)


@pytest.mark.parametrize("batch,expect_todo", [
    ({"batch_type": BT.BENCHMARK}, False),                              # batch_00000: frozen, skipped
    ({"batch_type": BT.BENCHMARK, "redo_attempted": True}, True),       # a composed benchmark batch
    ({"batch_type": BT.FOLLOW_UP}, True),                               # pre-#617 rows, unchanged
    ({"batch_type": BT.FIRST_RUN}, False),
])
def test_the_declared_lever_decides_whether_a_processed_district_re_runs(tmp_path, batch, expect_todo):
    """End of the chain: the batch dict the runners hold -> redoes_attempted -> reconcile's `redo`.
    A district with processed.json on disk is skipped or re-run purely on the declaration."""
    districts = _processed_district(tmp_path)
    registry = _attempted_registry()
    todo, skipped, quarantined = P4.reconcile(districts, registry,
                                              redo=BT.redoes_attempted(batch))
    assert quarantined == []
    assert bool(todo) is expect_todo and bool(skipped) is not expect_todo


# ---------------------------------------------------- persistence round-trip (govdb)

@govdb
def test_the_declaration_survives_the_db_round_trip_to_the_runners(gov_session):
    """The runners read their batch dict from `to_working_doc` (console) or the regenerated receipt
    (CLI) — both built by `_batch_doc`. A declaration that does not survive that projection is a
    declaration the stages never see."""
    gdb.init_precious_schema()
    doc = {"batch_id": "batch_zzbm1", "nces_year": "2024_25", "created": "t", "districts": []}
    BSTORE.create_batch(gov_session, doc, batch_type=BT.BENCHMARK,
                        redo_attempted=True, actor="zz")
    out = BSTORE.to_receipt_doc(gov_session, "batch_zzbm1")
    assert out["batch_type"] == BT.BENCHMARK and out["redo_attempted"] is True
    assert BT.redoes_attempted(out) is True


@govdb
def test_an_undeclared_batch_omits_the_key_so_existing_receipts_are_unchanged(gov_session):
    """Omitted, not `null`: every pre-#617 receipt regenerates byte-identically, and the reader takes
    its historical fallback rather than reading a value nobody wrote."""
    gdb.init_precious_schema()
    doc = {"batch_id": "batch_zzbm2", "nces_year": "2024_25", "created": "t", "districts": []}
    BSTORE.create_batch(gov_session, doc, batch_type=BT.FOLLOW_UP, actor="zz")
    out = BSTORE.to_receipt_doc(gov_session, "batch_zzbm2")
    assert "redo_attempted" not in out
    assert BT.redoes_attempted(out) is True          # ...and still redoes, via the fallback


@govdb
def test_the_gate1_view_resolves_the_lever_for_the_human(gov_session):
    """A gate@1 reviewer approves real spend — whether the batch RE-RUNS districts that already have
    artifacts must be on the review payload, resolved (never the raw nullable column)."""
    gdb.init_precious_schema()
    for bid, btype, declared in (("batch_zzbm3", BT.BENCHMARK, None),
                                 ("batch_zzbm4", BT.BENCHMARK, True)):
        BSTORE.create_batch(gov_session,
                            {"batch_id": bid, "nces_year": "2024_25", "created": "t", "districts": []},
                            batch_type=btype, redo_attempted=declared, actor="zz")
    assert BSTORE.to_view(gov_session, "batch_zzbm3")["redo_attempted"] is False
    assert BSTORE.to_view(gov_session, "batch_zzbm4")["redo_attempted"] is True


# ------------------------------------------------- console visibility (the UI-visibility rule)
# Static-source pins: no JS harness in this repo (a documented deferral), so the regression guard is
# that the markers exist. Without the type control the operator path for properties 1 and 2 is
# curl-only; without the warning a human approves a real-spend re-run with no notice that it is one.

def test_gate1_console_offers_the_targeted_batch_types_and_warns_about_the_re_run():
    js = (Path(__file__).resolve().parent.parent
          / "infrastructure/acquisition/process_governance/static/gate1.js").read_text()
    assert 'data-feat="q-create-type"' in js
    assert 'name="q-btype"' in js
    for value in ('value="first-run"', 'value="follow-up"', 'value="benchmark"'):
        assert value in js
    assert 'data-feat="q-create-redo-warn"' in js
    assert "RE-RUNS discovery, capture and processing" in js
    assert "gate@5" in js                      # the benchmark terminus, stated where the human picks


@govdb
def test_create_batch_refuses_an_unknown_batch_type(gov_session):
    """`create_batch` is the ONE chokepoint every composer passes through (CLI, console, the 5->1 and
    7->1 escalation builders, the benchmark injector), so validating here covers all of them."""
    gdb.init_precious_schema()
    with pytest.raises(ValueError, match="batch_type must be one of"):
        BSTORE.create_batch(gov_session,
                            {"batch_id": "batch_zzbm5", "nces_year": "2024_25", "created": "t",
                             "districts": []},
                            batch_type="benchmarks", actor="zz")
