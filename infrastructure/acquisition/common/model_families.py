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


# Per-model WINDOWS (#714/#709, REQ-174) — total context and max completion tokens, the inputs to
# per-call output sizing (`openrouter.call`'s clamp). Fetched from the public OpenRouter catalog
# (GET /api/v1/models: `context_length`, `top_provider.max_completion_tokens`) 2026-08-16; refresh
# with:  curl -s https://openrouter.ai/api/v1/models | jq '.data[]|{id,context_length,
# top_provider}'.  Checked in rather than fetched at runtime: sizing must be deterministic and
# test-visible (commandment #1), and the roster only changes via council-lab PRs anyway.
# max_out None = the provider declares no separate completion cap (bounded by context alone).
# The 2026-08-16 fetch falsified MAX_TOKENS_CEILING's premise for THREE of these (mistral-small
# 16,384 completion AND 32,768 TOTAL context; the low-cost-text judge qwen3-235b 16,384) — the
# Orange/Memphis 400s (#714/#709). `tests/test_model_windows.py` pins this dict's key-set to
# FAMILY's, so a model can't join the catalog without its windows. #809: the hand-refreshed
# snapshot needs a DETECTOR for the staleness it accepts (the premise above went stale silently
# once already) — `tests/test_model_windows_integration.py` re-fetches nightly/locally and fails
# with "refresh the catalog" on any value drift. Bump MODEL_WINDOWS_FETCHED with every refresh.
MODEL_WINDOWS_FETCHED = "2026-08-16"
MODEL_WINDOWS = {
    "google/gemini-2.5-flash": {"context": 1_048_576, "max_out": 65_535},
    "google/gemini-2.5-flash-lite": {"context": 1_048_576, "max_out": 65_535},
    "mistralai/mistral-small-24b-instruct-2501": {"context": 32_768, "max_out": 16_384},
    "mistralai/mistral-large-2512": {"context": 262_144, "max_out": None},
    "deepseek/deepseek-v3.2": {"context": 163_840, "max_out": 65_536},
    "qwen/qwen3-235b-a22b-2507": {"context": 262_144, "max_out": 16_384},
    "qwen/qwen3-vl-235b-a22b-instruct": {"context": 262_144, "max_out": 32_768},
}

# Completion-side safety margin: the request's own overhead + tokenizer-estimate error. Small on
# purpose — the prompt estimate (chars/3) already overestimates.
WINDOW_MARGIN_TOKENS = 512


def usable_output(model_id: str, est_prompt_tokens: int) -> "int | None":
    """The most completion tokens a call to `model_id` can legally request given its estimated
    prompt: min(max_out, context − prompt − margin). None for an uncatalogued model (test fakes,
    a model mid-adoption) — the caller keeps legacy sizing, so nothing outside the curated roster
    changes behavior. May return <= 0: the prompt alone (nearly) fills the window — the caller's
    pre-flight refusal case (#714)."""
    w = MODEL_WINDOWS.get(model_id)
    if not w:
        return None
    cap = w["context"] - int(est_prompt_tokens) - WINDOW_MARGIN_TOKENS
    if w["max_out"] is not None:
        cap = min(cap, w["max_out"])
    return cap

# The two ways a model's window can make a rep's read structurally incomplete (#709/#793). They live
# HERE, in the base layer, because both the producer (process_governance.stage7_run.council_degraded,
# which classifies) and the consumer (stage7_extract.requests, which words the remedy) need the same
# vocabulary, and the layering contract forbids the lower one importing the higher. Shared constant,
# never a literal repeated across files (the #755 lesson).
DEGRADED_REFUSED = "context_refused"     # the voter never answered — its window rejected the request
DEGRADED_TRUNCATED = "window_truncated"  # the voter answered PARTIALLY — some rows are missing
DEGRADED_LOOPED = "degenerate_repetition"  # #812: the voter answered with ONE row over and over

# #810: the precedence ("a refusal outranks a truncation — no answer at all is the stronger
# statement about the council") is ONE rule in ONE place, next to the constants it orders. Both
# consumers call `strongest_kind` rather than re-expressing the order in their own idiom — the #798
# defect was exactly two sites defaulting an absent `kinds` in opposite directions.
# #812 slots LOOPED between them: a loop's row volume tells you about the LOOP, not the document
# (Stroudsburg's 2-distinct loops did land their surviving rows in consensus), but unlike a refusal
# the model did answer. It outranks TRUNCATED because when a call is both, the loop is the CAUSE and
# the truncation merely the symptom of max_tokens stopping it; reporting "truncated" would point a
# human at document size when the document is fine. The two are correlated, NOT coextensive (#814):
# 5 of the corpus's 6 loops truncated; New Haven 0626910's looped with no truncation signal at all
# (ok=True, finish_reason=None) and read as a clean 420-fact extraction until this detector existed
# — a loop needs no ceiling to be a loop.
DEGRADED_PRECEDENCE = (DEGRADED_REFUSED, DEGRADED_LOOPED, DEGRADED_TRUNCATED)   # strongest first


def strongest_kind(kinds) -> str:
    """The strongest degradation kind present in `kinds` (an iterable of kind strings, or a
    {model: kind} dict whose values are read). A marker with an absent/empty `kinds` — receipts
    written between #709 and #793, or a hand-built marker — defaults to the STRONGEST
    (`context_refused`): under-claiming a refusal as a truncation invites 'that was the whole
    roster', the exact misdirection #793 exists to prevent. An unknown kind string also defaults
    strongest, for the same fail-honest reason."""
    vals = set(kinds.values() if isinstance(kinds, dict) else (kinds or ()))
    for k in DEGRADED_PRECEDENCE:
        if k in vals:
            return k
    return DEGRADED_PRECEDENCE[0]

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
