"""Canonical model-family buckets for the OpenRouter roster — the single source of truth.

Cross-family diversity is a pipeline invariant (REQ-056): a council's two voters must be different
families and the judge a third, and per-school consensus only counts agreement *across* families.
That rule is enforced in two places that must NOT import each other — Stage 6's council validator
(`stage6_handoff.councils`) and the Stage 7/8 consensus (`stage8_aggregate.aggregate`) — so the map
lives HERE in `common`, the one layer both may import.

Keyed by the FULL OpenRouter model id (`google/gemini-2.5-flash-lite`). Unified on full ids
2026-07-02 (Ian): there had been two drifting maps — this one (full id) and a short-name copy in
`aggregate.py` whose `family()` silently did nothing for the full ids the live path actually passes,
so cross-family counting only worked by the accident that distinct ids are distinct strings.
"""

# Family buckets, keyed by FULL OpenRouter model id. The provider prefix is usually the family
# (two Google Geminis are one family); an uncatalogued id falls back to its (alias-normalized) prefix.
FAMILY = {
    "google/gemini-2.5-flash": "google",
    "google/gemini-2.5-flash-lite": "google",
    "mistralai/mistral-small-24b-instruct-2501": "mistral",
    "mistralai/mistral-large-2512": "mistral",
    "deepseek/deepseek-v3.2": "deepseek",
    "qwen/qwen3-235b-a22b-2507": "qwen",
}

# Provider-prefix aliases for the fallback: OpenRouter's prefix is sometimes NOT the family bucket we
# catalog under ("mistralai/..." models are family "mistral"). Without this a catalogued Mistral
# voter + an uncatalogued `mistralai/*` voter would resolve to "mistral" vs "mistralai" and slip past
# the cross-family rule (issue #36).
FAMILY_ALIAS = {"mistralai": "mistral"}


def family_of(model_id: str) -> str:
    """The model's family bucket — the explicit map first, else the (alias-normalized) provider prefix."""
    if model_id in FAMILY:
        return FAMILY[model_id]
    prefix = model_id.split("/", 1)[0]
    return FAMILY_ALIAS.get(prefix, prefix)
