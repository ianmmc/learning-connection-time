"""Stage 6 council-config loader + the diversity validator (REQ-101, slice 1).

The validator encodes the council-research family-diversity constraint as a HARD rule
(LLM_COUNCIL_RESEARCH_2026-06 §2/§3/§6, STAGE6_HANDOFF_DESIGN §3A): a config is valid only if the
2 voters are different families AND the judge is a third family. These tests are the first thing
written for Stage 6 — the validator is the spec.
"""
import pytest

from infrastructure.acquisition.stage6_handoff import councils


# --------------------------- family resolution ---------------------------
def test_family_of_known_ids():
    assert councils.family_of("google/gemini-2.5-flash") == "google"
    assert councils.family_of("google/gemini-2.5-flash-lite") == "google"   # both Google
    assert councils.family_of("mistralai/mistral-large-2512") == "mistral"
    assert councils.family_of("deepseek/deepseek-v3.2") == "deepseek"
    assert councils.family_of("qwen/qwen3-235b-a22b-2507") == "qwen"


def test_family_of_unknown_falls_back_to_provider_prefix():
    # an id we haven't catalogued still resolves to its provider as a family proxy
    assert councils.family_of("anthropic/claude-x") == "anthropic"


# --------------------------- the diversity validator ---------------------------
def _cfg(voters, judge, cid="t", prompts={"default": "stage6.extract.v1"}):
    return {"id": cid, "name": cid, "voters": list(voters), "judge": judge,
            "input_kinds": ["text"], "prompts": prompts}


def test_valid_cross_family_config_passes():
    cfg = _cfg(["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"],
               "qwen/qwen3-235b-a22b-2507")
    councils.validate(cfg)   # must not raise


def test_same_family_voters_rejected():
    cfg = _cfg(["google/gemini-2.5-flash", "google/gemini-2.5-flash-lite"],
               "qwen/qwen3-235b-a22b-2507")
    with pytest.raises(councils.ConfigError, match="famil"):
        councils.validate(cfg)


def test_judge_sharing_a_voter_family_rejected():
    cfg = _cfg(["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"],
               "mistralai/mistral-large-2512")   # judge is Mistral, collides with voter 2
    with pytest.raises(councils.ConfigError, match="judge"):
        councils.validate(cfg)


def test_must_have_exactly_two_voters():
    with pytest.raises(councils.ConfigError, match="two voters"):
        councils.validate(_cfg(["google/gemini-2.5-flash-lite"], "qwen/qwen3-235b-a22b-2507"))
    with pytest.raises(councils.ConfigError, match="two voters"):
        councils.validate(_cfg(
            ["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501",
             "deepseek/deepseek-v3.2"], "qwen/qwen3-235b-a22b-2507"))


def test_judge_required():
    cfg = _cfg(["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"], None)
    with pytest.raises(councils.ConfigError, match="judge"):
        councils.validate(cfg)


def test_missing_prompt_rejected():
    # family-valid but no prompts -> would KeyError at request assembly (Stage 7); caught at load.
    cfg = _cfg(["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"],
               "qwen/qwen3-235b-a22b-2507", prompts={})
    with pytest.raises(councils.ConfigError, match="prompt"):
        councils.validate(cfg)


def test_unknown_prompt_id_rejected():
    cfg = _cfg(["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"],
               "qwen/qwen3-235b-a22b-2507", prompts={"default": "no-such-prompt"})
    with pytest.raises(councils.ConfigError, match="prompt"):
        councils.validate(cfg)


# --------------------------- the shipped seed configs ---------------------------
def test_seed_configs_load_and_are_valid():
    cfgs = councils.load_configs()   # loads + validates every shipped config; raises if any is invalid
    assert set(cfgs) >= {"low-cost-text", "image"}
    low = cfgs["low-cost-text"]
    assert len(low["voters"]) == 2
    # both seeds satisfy the diversity rule (validated on load) — spot-check the families differ
    fams = {councils.family_of(m) for m in low["voters"]} | {councils.family_of(low["judge"])}
    assert len(fams) == 3


def test_get_by_id():
    assert councils.get("image")["id"] == "image"
    with pytest.raises(KeyError):
        councils.get("no-such-config")
