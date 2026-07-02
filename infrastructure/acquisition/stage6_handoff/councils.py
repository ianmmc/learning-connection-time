"""Stage 6 council-config registry + the diversity validator (REQ-101).

A *council* is the unit Stage 7 dispatches a representation to: 2 cross-family **voters** that
agree-or-escalate, plus 1 third-family **judge** that re-reads the page on a disagreement (the
cascade template — council research §2-4: judge > extra voter; cross-family agreement only).

Configs live in the versioned config-as-data layer (`common/config/council_configs.json`), read via
the shared `config_loader` (so the Node half reads the same file). The **family-diversity constraint**
is enforced HERE, on load (LLM_COUNCIL_RESEARCH_2026-06 §2/§3/§6, STAGE6_DISPATCH_DESIGN §3A): the two
voters must be different families and the judge a third. An invalid config fails fast.

This module imports only `common` — it stays independent of the other stages (import-linter contract).
"""
from infrastructure.acquisition.common import config_loader
from infrastructure.acquisition.stage6_handoff import prompts as P

KNOB = "council_configs"

# Model family buckets for our OpenRouter roster. The provider prefix IS the family for this set
# (two Google Geminis are one family), so an uncatalogued id falls back to its provider prefix.
FAMILY = {
    "google/gemini-2.5-flash": "google",
    "google/gemini-2.5-flash-lite": "google",
    "mistralai/mistral-small-24b-instruct-2501": "mistral",
    "mistralai/mistral-large-2512": "mistral",
    "deepseek/deepseek-v3.2": "deepseek",
    "qwen/qwen3-235b-a22b-2507": "qwen",
}
# Provider-prefix aliases for the fallback: OpenRouter's prefix is sometimes NOT the family bucket
# name we catalog under ("mistralai/..." models are family "mistral"). Without this, a catalogued
# Mistral voter + an uncatalogued mistralai/* voter would resolve to "mistral" vs "mistralai" and
# slip past the diversity rule (issue #36).
FAMILY_ALIAS = {"mistralai": "mistral"}


class ConfigError(ValueError):
    """A council config violates the diversity constraint (or is malformed)."""


def family_of(model_id: str) -> str:
    """The model's family bucket — explicit map first, else the (alias-normalized) provider prefix."""
    if model_id in FAMILY:
        return FAMILY[model_id]
    prefix = model_id.split("/", 1)[0]
    return FAMILY_ALIAS.get(prefix, prefix)


def validate(cfg: dict) -> None:
    """Raise ConfigError unless `cfg` is a well-formed cross-family council (2 distinct-family
    voters + a third-family judge). The first thing Stage 6 enforces; the spec lives in the tests."""
    cid = cfg.get("id", "<no-id>")
    voters = cfg.get("voters") or []
    if len(voters) != 2:
        raise ConfigError(f"council '{cid}': must have exactly two voters, got {len(voters)}")
    judge = cfg.get("judge")
    if not judge:
        raise ConfigError(f"council '{cid}': a judge is required (the third family)")
    # Configs are CURATED: every member must be in the FAMILY catalog. A prefix fallback is only a
    # display convenience (family_of) — letting an uncatalogued id through validation would let a
    # mis-bucketed prefix defeat the cross-family rule (REQ-056), so fail fast here instead.
    for m in voters + [judge]:
        if m not in FAMILY:
            raise ConfigError(
                f"council '{cid}': model '{m}' is not in the FAMILY catalog — add it to "
                f"councils.FAMILY (with its family bucket) before using it in a council config")
    vf = [family_of(v) for v in voters]
    if vf[0] == vf[1]:
        raise ConfigError(
            f"council '{cid}': the two voters must be different families "
            f"(both are '{vf[0]}': {voters[0]}, {voters[1]})")
    jf = family_of(judge)
    if jf in vf:
        raise ConfigError(
            f"council '{cid}': the judge must be a third family distinct from both voters "
            f"(judge '{judge}' is '{jf}', which collides with a voter)")
    # Every voter AND the judge must resolve to a KNOWN prompt — else request assembly (Stage 7,
    # the expensive moment) would KeyError on SYSTEM_PROMPTS[None]. Validate it here at config-load.
    for m in voters + [judge]:
        pid = P.select_prompt_id(cfg, m)
        if pid not in P.SYSTEM_PROMPTS:
            raise ConfigError(
                f"council '{cid}': no usable prompt for model '{m}' (resolved prompt_id={pid!r}); "
                f"add a `prompts.default` (or per-model entry) naming a known prompt")


def load_configs() -> dict:
    """All shipped council configs, keyed by id, each VALIDATED (raises ConfigError if any is invalid)."""
    out = {}
    for cfg in config_loader.values(KNOB):
        validate(cfg)
        cid = cfg["id"]
        if cid in out:
            raise ConfigError(f"duplicate council id '{cid}'")
        out[cid] = cfg
    return out


def get(config_id: str) -> dict:
    """One validated council config by id. Raises KeyError if absent."""
    return load_configs()[config_id]
