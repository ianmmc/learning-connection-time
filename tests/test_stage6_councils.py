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


def test_family_of_uncatalogued_mistralai_normalizes_to_mistral():
    # issue #36: the raw prefix "mistralai" is NOT the family bucket name — the alias map folds it
    # into "mistral" so an uncatalogued Mistral id can never read as a distinct family
    assert councils.family_of("mistralai/mistral-medium-3") == "mistral"
    assert councils.family_of("mistralai/anything-new") == councils.family_of("mistralai/mistral-large-2512")


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


def test_two_mistral_voters_one_uncatalogued_rejected():
    # the #36 adversarial case: a catalogued Mistral voter + an UNCATALOGUED mistralai/* voter are
    # the same family — validation must FAIL (via the catalog check; the alias fallback is the
    # second line of defense), never pass as "mistral" vs "mistralai"
    cfg = _cfg(["mistralai/mistral-large-2512", "mistralai/mistral-medium-uncatalogued"],
               "qwen/qwen3-235b-a22b-2507")
    with pytest.raises(councils.ConfigError):
        councils.validate(cfg)


def test_uncatalogued_model_id_rejected():
    # configs are curated: any member not in the FAMILY catalog fails fast at validation
    cfg = _cfg(["google/gemini-2.5-flash-lite", "anthropic/claude-x"],
               "qwen/qwen3-235b-a22b-2507")
    with pytest.raises(councils.ConfigError, match="FAMILY catalog"):
        councils.validate(cfg)
    cfg = _cfg(["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"],
               "openai/gpt-x")   # uncatalogued judge
    with pytest.raises(councils.ConfigError, match="FAMILY catalog"):
        councils.validate(cfg)


def test_judge_required():
    cfg = _cfg(["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"], None)
    with pytest.raises(councils.ConfigError, match="judge"):
        councils.validate(cfg)


def test_config_missing_id_rejected_at_validate():
    """#358: council_configs is bound only to the generic knob_entries envelope schema, which does
    NOT constrain an entry's value shape — so a config with no `id` passes schema validation, then
    load_configs' `cfg[\"id\"]` KeyErrors. validate() must require a non-empty string id up front so
    the failure is a clear ConfigError at config-load, not a KeyError deeper in."""
    cfg = _cfg(["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"],
               "qwen/qwen3-235b-a22b-2507")
    del cfg["id"]
    with pytest.raises(councils.ConfigError, match="id"):
        councils.validate(cfg)
    cfg2 = _cfg(["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"],
                "qwen/qwen3-235b-a22b-2507", cid="")
    with pytest.raises(councils.ConfigError, match="id"):
        councils.validate(cfg2)


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


# --------------------------- the vision guard (#82) ---------------------------
def _img_cfg(voters, judge, cid="img"):
    return {"id": cid, "name": cid, "voters": list(voters), "judge": judge,
            "input_kinds": ["image"], "prompts": {"default": "stage6.extract.vision.v1"}}


def test_image_council_with_text_only_judge_rejected():
    # the #82 bug: a text-only judge on an image council 404s on every image call — must fail at load
    cfg = _img_cfg(["google/gemini-2.5-flash", "mistralai/mistral-large-2512"],
                   "deepseek/deepseek-v3.2")   # deepseek is text-only
    with pytest.raises(councils.ConfigError, match="vision-capable"):
        councils.validate(cfg)


def test_image_council_with_text_only_voter_rejected():
    cfg = _img_cfg(["google/gemini-2.5-flash", "qwen/qwen3-235b-a22b-2507"],   # qwen3 (text) is a voter
                   "mistralai/mistral-large-2512")
    with pytest.raises(councils.ConfigError, match="vision-capable"):
        councils.validate(cfg)


def test_valid_image_council_passes():
    # the #82 FIX composition: Google + Mistral vision voters -> Qwen-VL vision judge (all distinct)
    cfg = _img_cfg(["google/gemini-2.5-flash", "mistralai/mistral-large-2512"],
                   "qwen/qwen3-vl-235b-a22b-instruct")
    councils.validate(cfg)   # must not raise


def test_text_council_not_subject_to_vision_guard():
    # a text council may (and does) use text-only members — the guard only fires on input_kinds image
    cfg = {"id": "t", "name": "t", "input_kinds": ["text"],
           "voters": ["google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"],
           "judge": "qwen/qwen3-235b-a22b-2507", "prompts": {"default": "stage6.extract.v1"}}
    councils.validate(cfg)   # text-only judge on a text council is fine


def test_is_vision_capable_catalog():
    from infrastructure.acquisition.common import model_families as MF
    assert MF.is_vision_capable("qwen/qwen3-vl-235b-a22b-instruct") is True
    assert MF.is_vision_capable("google/gemini-2.5-flash") is True
    assert MF.is_vision_capable("deepseek/deepseek-v3.2") is False       # text-only (the #82 model)
    assert MF.is_vision_capable("qwen/qwen3-235b-a22b-2507") is False     # text reasoning model, not VL
    assert MF.is_vision_capable("some/uncatalogued-model") is False       # conservative default
