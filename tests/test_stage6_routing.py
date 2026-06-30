"""Stage 6 per-representation routing (REQ-101, slice 2).

Maps one representation (its kind + the record's signals) to the council(s) it should go to,
with the capture-fidelity gate (STAGE6_HANDOFF_DESIGN §3B, the New Haven false-consensus lesson):
a low-fidelity text capture routes to the VISION council and is marked fidelity_suspect so Stage 7
never auto-accepts it on 2-voter agreement. Pure (dicts in, dict out) — no DB, no stage imports.
"""
from infrastructure.acquisition.stage6_handoff import routing

# the id->config registry routing reads `input_kinds` from (data-driven, not hardcoded ids)
COUNCILS = {"low-cost-text": {"id": "low-cost-text", "input_kinds": ["text"]},
            "image": {"id": "image", "input_kinds": ["image"]}}


def test_image_rep_routes_to_vision_council():
    r = routing.route({"file": "p.png", "kind": "image"}, {}, COUNCILS)
    assert r["councils"] == ["image"]
    assert r["fidelity_suspect"] is False


def test_clean_text_routes_to_low_cost_text():
    r = routing.route({"file": "extracted.txt", "kind": "text"}, {"visual_text_gap": False}, COUNCILS)
    assert r["councils"] == ["low-cost-text"]
    assert r["fidelity_suspect"] is False


def test_low_fidelity_text_routes_to_vision_and_is_suspect():
    # visual content, thin text -> the New Haven gate: read the picture, never auto-accept
    r = routing.route({"file": "extracted.txt", "kind": "text"}, {"visual_text_gap": True}, COUNCILS)
    assert r["councils"] == ["image"]
    assert r["fidelity_suspect"] is True
    assert "fidelity" in r["reason"] or "visual" in r["reason"]


def test_low_fidelity_pdf_also_routes_to_vision():
    r = routing.route({"file": "doc.pdf", "kind": "pdf", "pages": [3]}, {"visual_text_gap": True}, COUNCILS)
    assert r["councils"] == ["image"]
    assert r["fidelity_suspect"] is True


def test_clean_pdf_routes_to_text_council():
    r = routing.route({"file": "doc.pdf", "kind": "pdf"}, {"visual_text_gap": False}, COUNCILS)
    assert r["councils"] == ["low-cost-text"]
    assert r["fidelity_suspect"] is False


def test_routes_by_input_kinds_not_hardcoded_ids():
    # a renamed text council (different id) still gets clean text, purely via input_kinds
    renamed = {"text-council-v2": {"id": "text-council-v2", "input_kinds": ["text"]},
               "vision-v2": {"id": "vision-v2", "input_kinds": ["image"]}}
    assert routing.route({"kind": "text"}, {}, renamed)["councils"] == ["text-council-v2"]
    assert routing.route({"kind": "image"}, {}, renamed)["councils"] == ["vision-v2"]


def test_councils_is_always_a_list_many_to_many_ready():
    r = routing.route({"file": "p.png", "kind": "image"}, {}, COUNCILS)
    assert isinstance(r["councils"], list)


def test_degrades_when_vision_council_unavailable_but_stays_suspect():
    # no image-reading council configured: a low-fidelity rep can't reach vision, but must NOT silently
    # auto-accept — it stays flagged so the judge/human still catches it.
    r = routing.route({"file": "extracted.txt", "kind": "text"}, {"visual_text_gap": True},
                      {"low-cost-text": {"input_kinds": ["text"]}})
    assert r["fidelity_suspect"] is True
    assert "low-cost-text" in r["councils"]


def test_is_low_fidelity_helper():
    assert routing.is_low_fidelity({"visual_text_gap": True}) is True
    assert routing.is_low_fidelity({"visual_text_gap": False}) is False
    assert routing.is_low_fidelity({}) is False
    assert routing.is_low_fidelity(None) is False
