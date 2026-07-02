"""Stage 6 OpenRouter request assembly (REQ-101, slice 7) — the dispatch plumbing UP TO the seam.

plan_requests() turns a frozen handoff into the deterministic first-pass plan: one call per
(sent rep × routed council × VOTER model), each carrying its per-model prompt id. build_request()
materializes the actual OpenRouter chat request given the rep's content — the last step before the
paid POST, which is Stage 7. Pure (no network, no DB, no disk): assembling != sending.
"""
from infrastructure.acquisition.stage6_handoff import requests as RQ
from infrastructure.acquisition.stage6_handoff import prompts as P

HANDOFF = {
    "handoff_hash": "h1",
    "councils": {
        "low-cost-text": {"id": "low-cost-text", "voters": ["google/gemini-2.5-flash-lite",
                          "mistralai/mistral-small-24b-instruct-2501"], "judge": "qwen/qwen3-235b-a22b-2507",
                          "prompts": {"default": "stage6.extract.v1"}},
        "image": {"id": "image", "voters": ["google/gemini-2.5-flash", "mistralai/mistral-large-2512"],
                  "judge": "deepseek/deepseek-v3.2", "prompts": {"default": "stage6.extract.vision.v1"}},
    },
    "districts": [{
        "district_id": "0100810",
        "records": [
            {"rec_key": "a", "decision": "send",
             "reps": [{"file": "t.txt", "kind": "text", "pages": [2, 3], "councils": ["low-cost-text"]}]},
            {"rec_key": "b", "decision": "send",
             "reps": [{"file": "p.png", "kind": "image", "councils": ["image"]}]},
            {"rec_key": "z", "decision": "reject", "reps": []},
        ],
    }],
}


def test_plan_is_one_call_per_rep_council_voter_and_excludes_judge():
    plan = RQ.plan_requests(HANDOFF)
    # 2 sent reps × 2 voters each = 4 voter calls; the reject contributes none; no judge calls
    assert len(plan) == 4
    assert all(c["role"] == "voter" for c in plan)
    text_models = {c["model"] for c in plan if c["rec_key"] == "a"}
    assert text_models == {"google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"}
    assert "qwen/qwen3-235b-a22b-2507" not in {c["model"] for c in plan}   # judge not in first pass


def test_plan_carries_routing_context_and_prompt_id():
    plan = RQ.plan_requests(HANDOFF)
    a = next(c for c in plan if c["rec_key"] == "a")
    assert a["district_id"] == "0100810" and a["council_id"] == "low-cost-text"
    assert a["file"] == "t.txt" and a["kind"] == "text" and a["prompt_id"] == "stage6.extract.v1"
    b = next(c for c in plan if c["rec_key"] == "b")
    assert b["prompt_id"] == "stage6.extract.vision.v1"
    # issue #38: the harvest-pages hint rides the plan (None when the rep has no page scoping)
    assert a["pages"] == [2, 3]
    assert b["pages"] is None


def test_build_request_text():
    planned = {"model": "m/x", "kind": "text", "prompt_id": "stage6.extract.v1"}
    req = RQ.build_request(planned, "08:00 to 14:30 Lincoln High")
    assert req["model"] == "m/x"
    assert req["messages"][0]["role"] == "system"
    assert "START and END" in req["messages"][0]["content"]   # the real extraction prompt
    assert req["messages"][1] == {"role": "user", "content": "08:00 to 14:30 Lincoln High"}


def test_build_request_image_uses_image_url():
    planned = {"model": "m/v", "kind": "image", "prompt_id": "stage6.extract.vision.v1"}
    req = RQ.build_request(planned, "data:image/png;base64,AAAA")
    user = req["messages"][1]
    assert user["role"] == "user"
    assert user["content"][0]["type"] == "image_url"
    assert user["content"][0]["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_select_prompt_id_prefers_per_model_override():
    council = {"prompts": {"default": "stage6.extract.v1", "m/special": "stage6.extract.vision.v1"}}
    assert P.select_prompt_id(council, "m/special") == "stage6.extract.vision.v1"
    assert P.select_prompt_id(council, "m/other") == "stage6.extract.v1"


def test_prompt_registry_has_both_variants_and_reads_times_only():
    assert set(P.SYSTEM_PROMPTS) >= {"stage6.extract.v1", "stage6.extract.vision.v1"}
    # REQ-054 invariant: the council reads TIMES and returns start/end facts — never computes minutes
    for body in P.SYSTEM_PROMPTS.values():
        assert "start_time" in body and "end_time" in body
        assert "minutes" not in body.lower()
