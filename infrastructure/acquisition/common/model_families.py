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
    "qwen/qwen3-vl-235b-a22b-instruct": "qwen",   # the vision judge for the image council (#82 fix)
}

# Per-model VISION capability — a curated ALLOWLIST (a model is treated as vision-capable only if it is
# listed here). It exists because GitHub #82 shipped a TEXT-ONLY judge (deepseek-v3.2) into the `image`
# council, where every judge call 404'd ("No endpoints found that support image input") — invisible
# until run against real image reps. `councils.validate()` now uses this to refuse an image-input
# council whose voters/judge aren't all vision-capable. Membership is grounded in the council research
# (models-and-council-composition/) + empirical confirmation (mistral-large-2512 + gemini-2.5-flash read
# image reps in the batch_00000 run; deepseek-v3.2 404'd). DeepSeek is the notable text-only family
# (input_modalities == ["text"]) and can never be a vision member.
VISION_CAPABLE = {
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
    "mistralai/mistral-large-2512",
    "qwen/qwen3-vl-235b-a22b-instruct",
}


def is_vision_capable(model_id: str) -> bool:
    """True only if `model_id` is a known vision-capable model (the curated VISION_CAPABLE allowlist).
    Conservative by design: an uncatalogued id is treated as NOT vision-capable, so a model must be
    proven vision-capable before it can serve on an image-input council (the #82 guard)."""
    return model_id in VISION_CAPABLE

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
