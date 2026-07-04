"""Stage 6 handoff-package assembly (REQ-101, slice 4).

Turns a per-district release decision (the Stage-5 records, each carrying its `send` reps + the signals
routing needs) into the in-memory handoff package: every send rep routed to its council(s) and priced.
PURE (dicts in/out) — the DB read of the release decision + the app-layer wiring (so stage6 never
imports stage5) come in slice 5. Uses the SHIPPED councils + bootstrap cost model, so the dollar
assertions are exact (flat bootstrap): clean text -> 0.00102, image -> 0.004755.
"""
import math

import pytest

from infrastructure.acquisition.stage6_handoff import councils, cost, handoff, package
from infrastructure.acquisition.stage6_handoff import requests as RQ

COUNCILS = councils.load_configs()
COST_MODEL = cost.load_cost_model()

CLEAN_TEXT = 0.00050 + 0.00022 + 0.5 * 0.00060   # low-cost-text voters + 0.5*judge = 0.00102
# image judge swapped deepseek-v3.2 (0.00102) -> qwen3-vl-235b-a22b-instruct (0.00085) for #82:
IMAGE = 0.00168 + 0.00265 + 0.5 * 0.00085         # image voters + 0.5*judge = 0.004755


def _rec(rec_key, decision, send, signals=None, reason="r"):
    return {"rec_key": rec_key, "url": f"http://x/{rec_key}", "decision": decision,
            "reason": reason, "signals": signals or {}, "send": send}


def test_clean_text_record_routes_and_prices_to_low_cost_text():
    rec = _rec("a", "send", [{"file": "t.txt", "kind": "text", "n_chars": 1000, "n_times": 5}],
               signals={"visual_text_gap": False})
    out = package.assemble_record(rec, COUNCILS, COST_MODEL)
    assert out["decision"] == "send"
    assert len(out["reps"]) == 1
    rep = out["reps"][0]
    assert rep["councils"] == ["low-cost-text"]
    assert rep["fidelity_suspect"] is False
    assert math.isclose(rep["est_usd"], CLEAN_TEXT, rel_tol=1e-9)


def test_image_record_routes_to_image_council():
    rec = _rec("b", "send", [{"file": "p.png", "kind": "image"}])
    rep = package.assemble_record(rec, COUNCILS, COST_MODEL)["reps"][0]
    assert rep["councils"] == ["image"]
    assert math.isclose(rep["est_usd"], IMAGE, rel_tol=1e-9)


def test_low_fidelity_text_routes_to_vision_and_is_suspect():
    rec = _rec("c", "send", [{"file": "t.txt", "kind": "text", "n_chars": 800}],
               signals={"visual_text_gap": True})
    rep = package.assemble_record(rec, COUNCILS, COST_MODEL)["reps"][0]
    assert rep["councils"] == ["image"]
    assert rep["fidelity_suspect"] is True
    assert math.isclose(rep["est_usd"], IMAGE, rel_tol=1e-9)


def test_reject_record_has_no_reps_but_is_recorded():
    rec = _rec("d", "reject", [], reason="non-target:board")
    out = package.assemble_record(rec, COUNCILS, COST_MODEL)
    assert out["decision"] == "reject"
    assert out["reason"] == "non-target:board"
    assert out["reps"] == []


def test_district_rollup_counts_and_sums():
    recs = [
        _rec("a", "send", [{"file": "t.txt", "kind": "text", "n_chars": 1000, "n_times": 5}]),
        _rec("b", "send", [{"file": "p.png", "kind": "image"}]),
        _rec("d", "reject", []),
    ]
    block = package.assemble_district({"district_id": "0100810"}, recs, COUNCILS, COST_MODEL)
    assert block["district_id"] == "0100810"
    assert block["n_send_reps"] == 2          # the reject contributes no reps
    assert math.isclose(block["est_usd"], CLEAN_TEXT + IMAGE, rel_tol=1e-9)


def test_package_totals_across_districts_and_carries_provenance():
    d1 = ({"district_id": "0100810"},
          [_rec("a", "send", [{"file": "t.txt", "kind": "text", "n_chars": 1000}])])
    d2 = ({"district_id": "0101410"},
          [_rec("b", "send", [{"file": "p.png", "kind": "image"}])])
    pkg = package.assemble_package([d1, d2], COUNCILS, COST_MODEL)
    assert len(pkg["districts"]) == 2
    assert pkg["cost"]["n_reps"] == 2
    assert math.isclose(pkg["cost"]["total_usd"], CLEAN_TEXT + IMAGE, rel_tol=1e-9)
    assert pkg["cost"]["provenance"] == "bootstrap"
    assert "generated_at" in pkg


def test_override_routes_a_rep_to_the_chosen_council():
    # gate@6 manual override: a text rep normally -> low-cost-text; override sends it to image.
    rec = _rec("a", "send", [{"file": "t.txt", "kind": "text", "n_chars": 1000, "n_times": 5}],
               signals={"visual_text_gap": False})
    overrides = {"a::t.txt": "image"}
    rep = package.assemble_record(rec, COUNCILS, COST_MODEL, overrides)["reps"][0]
    assert rep["councils"] == ["image"]
    assert rep["route_reason"] == "override:image"
    assert math.isclose(rep["est_usd"], IMAGE, rel_tol=1e-9)


def test_unknown_override_council_refuses():
    # issue #54: a stale/unknown override must FAIL the assembly loudly (naming the council id),
    # never silently fall back to auto-routing a paid call
    rec = _rec("a", "send", [{"file": "t.txt", "kind": "text", "n_chars": 1000}])
    with pytest.raises(ValueError, match="no-such"):
        package.assemble_record(rec, COUNCILS, COST_MODEL, {"a::t.txt": "no-such"})


def test_pages_survive_assemble_freeze_and_plan():
    # issue #38: the harvest-pages hint on a handbook send must reach Stage 7 —
    # assemble_record -> the frozen handoff doc (incl. identity) -> plan_requests
    rec = _rec("a", "send", [{"file": "handbook.pdf", "kind": "pdf", "pages": [4, 9]}])
    out = package.assemble_record(rec, COUNCILS, COST_MODEL)
    assert out["reps"][0]["pages"] == [4, 9]

    pkg = package.assemble_package([({"district_id": "0100810"}, [rec])], COUNCILS, COST_MODEL)
    doc = handoff.freeze(pkg, COUNCILS, {"0100810": {"config": "c", "labels": "l", "data": "d"}})
    frozen_rep = doc["districts"][0]["records"][0]["reps"][0]
    assert frozen_rep["pages"] == [4, 9]
    # pages are part of the content identity: dropping them is a DIFFERENT dispatch
    rec_np = _rec("a", "send", [{"file": "handbook.pdf", "kind": "pdf"}])
    pkg_np = package.assemble_package([({"district_id": "0100810"}, [rec_np])], COUNCILS, COST_MODEL)
    doc_np = handoff.freeze(pkg_np, COUNCILS, {"0100810": {"config": "c", "labels": "l", "data": "d"}})
    assert doc_np["handoff_hash"] != doc["handoff_hash"]

    plan = RQ.plan_requests(doc)
    assert plan and all(c["pages"] == [4, 9] for c in plan)
