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


def test_prompt_registry_has_variants_and_never_computes_minutes():
    assert set(P.SYSTEM_PROMPTS) >= {"stage6.extract.v1", "stage6.extract.vision.v1",
                                     "stage6.extract.v2", "stage6.extract.vision.v2",
                                     "stage6.extract.v3", "stage6.extract.vision.v3"}
    # REQ-054 invariant: deterministic code computes gross = end - start; the council reads TIMES and
    # returns start/end facts, and is NEVER told to compute minutes. v2 (STAGE8 §2a.6) may READ an
    # explicitly-STATED minutes number (path 2 — reading, not computing), but must guard it so the model
    # never calculates one from the times.
    for pid, body in P.SYSTEM_PROMPTS.items():
        b = body.lower()
        assert "start_time" in body and "end_time" in body
        assert "calculate" not in b or "never calculate" in b, f"{pid} instructs calculating"
        if "minutes" in b:   # only v2+ mentions minutes, and only for the STATED-number path
            assert "never calculate it from the times" in b, \
                f"{pid} mentions minutes without the REQ-054 no-compute guard"


def test_v3_prompts_forbid_year_inference_from_context():
    # REQ-141 (2026-07-15 audit sweep): school_year is a READING, never an inference — mirrors the
    # never-computes-minutes guard above for the #254 v3 fields. A future v4 that dropped or weakened
    # this clause (e.g. "infer the year from the page's publish date" for convenience) must fail here,
    # not surface as a silent Santa-Fe-class regression months later.
    v3_prompts = {pid: body for pid, body in P.SYSTEM_PROMPTS.items() if pid.endswith(".v3")}
    assert v3_prompts, "no v3 prompts registered — REQ-141 has nothing to guard"
    for pid, body in v3_prompts.items():
        b = body.lower()
        assert "school_year" in b, f"{pid} is a v3 prompt but doesn't mention school_year"
        assert "do not infer" in b or "do not infer it" in b, \
            f"{pid} mentions school_year without the no-inference guard"
        assert "url" in b and "domain" in b and "date" in b, \
            f"{pid}'s no-inference guard doesn't name all three forbidden inference sources"
        assert "null is the correct answer" in b or "null" in b, \
            f"{pid} doesn't say null is the honest answer when no year is stated"
