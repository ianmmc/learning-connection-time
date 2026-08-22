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
import math

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
MODEL_WINDOWS_FETCHED = "2026-08-22"
MODEL_WINDOWS = {
    "google/gemini-2.5-flash": {"context": 1_048_576, "max_out": 65_535},
    "google/gemini-2.5-flash-lite": {"context": 1_048_576, "max_out": 65_535},
    "mistralai/mistral-small-24b-instruct-2501": {"context": 32_768, "max_out": 16_384},
    "mistralai/mistral-large-2512": {"context": 262_144, "max_out": None},
    # 2026-08-22 refresh: max_out 65_536 -> 163_840, now EQUAL to its context — DeepSeek
    # dropped the separate completion cap. Recorded as the provider states it (163_840),
    # not as None: `None` means "declares no cap", and this declares one that happens to
    # be non-binding. Effect on sizing is one-directional and safe — the clamp
    # min(context - prompt - margin, max_out) now always binds on the context term, so a
    # long extraction truncates less. No spend increase: output is billed per token
    # EMITTED, not per max_tokens requested; a truncated extraction is the wasteful case.
    "deepseek/deepseek-v3.2": {"context": 163_840, "max_out": 163_840},
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


# ── Output/prompt sizing (#822) ───────────────────────────────────────────────────────────────
# These moved here from `stage7_extract/openrouter.py`, which still re-exports every name so its
# callers are unchanged. The move is forced by the layering contract, not taste: stages 1-8 are
# INDEPENDENT of each other, so Stage 6 (which must decide at dispatch whether a council can serve a
# rep) may not import Stage 7. `common` is the one layer both may read — the same reason FAMILY
# lives here. Keeping a second copy in Stage 6 is the implemented-twice-drifts class (#798/#810/
# #799/#816, and #834's two slice predicates); one copy is the only real lock.
#
# Output-token model (EXTRACTION_TOKEN_SIZING_2026-07-06.md, 840 real calls): reply length is
# roster-bound at ~47 completion tokens/school (flat, no verbosity noise) and each school
# contributes ~2 clock times, so schools ≈ n_times/2 and output ≈ schools × 47.
_TOKENS_PER_SCHOOL = 47
_TIMES_PER_SCHOOL = 2
_SIZING_HEADROOM = 1.5            # grade-band splitting (a K-12 campus emits >1 row/school) + long names
# chars-per-token divisor for the prompt ESTIMATE — deliberately low (overestimates tokens) so a
# clamp errs toward a smaller max_tokens, never toward a provider 400.
_EST_CHARS_PER_TOKEN = 3
# #805: an image part carries NO text but is real prompt-side context at the provider (tiled at
# ~hundreds-to-low-thousands of tokens each). A crude constant beats the zero it replaced — zero
# made the clamp and the pre-flight refusal INERT for the whole vision tier.
IMAGE_PART_EST_TOKENS = 1600
# The FLOOR (small reps, ~86% of traffic): every roster we've seen fits 16k, so a small rep is never
# sized below this. The CEILING is the largest max_tokens any call may request.
DEFAULT_MAX_TOKENS = 16000
MAX_TOKENS_CEILING = 32000
# Below this much usable output the call is refused pre-flight at zero spend (#714).
MIN_USEFUL_OUTPUT = 1024


def estimate_output_tokens(n_times: "int | None") -> "int | None":
    """The rep's UNCLAMPED completion-token NEED. `None` when `n_times` is None — un-assessable,
    which is emphatically not zero (see `rep_overflow`).

    Deliberately NOT clamped, unlike `size_max_tokens`. The two answer different questions ("how
    much would this rep need?" vs "how much may we ask for?") and #822's review found that
    conflating them makes the image council's ceiling unreachable: the clamp tops out at 32,000
    while that council's ceiling is 32,768, so an image overflow could never be detected and the
    issue's "0 records exceed the image council" would have been true by construction rather than
    by measurement. A need estimate that cannot exceed the thing it is compared against is not a
    measurement."""
    if n_times is None:
        return None
    if not n_times:
        return 0
    return math.ceil(n_times / _TIMES_PER_SCHOOL * _TOKENS_PER_SCHOOL * _SIZING_HEADROOM)


def size_max_tokens(n_times: "int | None") -> int:
    """What a call may REQUEST as `max_tokens`: the raw need clamped to [floor, ceiling] (#180).
    A big roster is sized right on the FIRST call instead of truncating then paying the prompt again
    on the #169 retry; a small rep stays at the 16k floor (never sized DOWN, so nothing that fit
    before can newly truncate). `n_times` None/0 (image/scan reps whose times aren't text-countable)
    → the floor, where the #169 retry is the backstop.

    NB `max_tokens` is only a ceiling — OpenRouter bills ACTUAL completion tokens, so sizing higher
    costs nothing unless the model uses the room (the tail we WANT); the saving is the eliminated
    duplicate PROMPT charge of the retry."""
    est = estimate_output_tokens(n_times)
    if not est:
        return DEFAULT_MAX_TOKENS
    return max(DEFAULT_MAX_TOKENS, min(est, MAX_TOKENS_CEILING))


def estimate_prompt_tokens(n_chars: "int | None", n_images: int = 0) -> int:
    """Conservative prompt-size estimate: TOTAL prompt chars/3 (real English runs ~3.5-4
    chars/token, so this OVERestimates) plus a flat per-image constant. `n_chars` is EVERY text
    char that will be in the request — the system prompt included, not the rep content alone
    (#846: the content-only form was 400-1,000 tokens optimistic against mistral-small's 32,768
    context, enough to say "fits" for a rep the live call then clamps or refuses). A None `n_chars`
    counts 0 CHARS — callers that care about un-assessability must check `n_times`, which is the
    signal that actually goes missing on a binary rep."""
    return math.ceil((n_chars or 0) / _EST_CHARS_PER_TOKEN) + int(n_images) * IMAGE_PART_EST_TOKENS


def rep_prompt_size(content_chars: "int | None", system_chars: int, kind: str) -> tuple:
    """(total text chars, image parts) of the request a rep WILL become — the one construction of
    the estimator's inputs, shared by Stage 6 (which knows the rep only as a signal row) and Stage
    7 (which measures the assembled body and must agree). A text rep sends its content inline as
    chars; an image rep sends ONE image part and its content contributes no chars — the base64
    length is not tokens (#805). System prompt chars ride on both."""
    if kind == "image":
        return int(system_chars or 0), 1
    return int(system_chars or 0) + int(content_chars or 0), 0


def council_members(council_cfg: dict) -> list:
    """A council's three serving models: both voters plus the judge. The judge counts — a call the
    judge cannot serve is a call the COUNCIL cannot serve, even though `council_degraded` only ever
    *marks* voters (REQ-056 shape: 2 cross-family voters → a third-family judge)."""
    return list((council_cfg or {}).get("voters") or []) + \
        ([(council_cfg or {}).get("judge")] if (council_cfg or {}).get("judge") else [])


def council_ceiling(council_cfg: dict, est_prompt_tokens: int) -> "int | None":
    """The most completion tokens this COUNCIL can serve: the weakest member's `usable_output` at
    the same prompt estimate (#822 P2). `None` if the council has no members, or if ANY member is
    uncatalogued — an unmeasured model's ceiling is unknown, and treating unknown as infinite is
    how a structurally impossible call records a clean zero."""
    members = council_members(council_cfg)
    if not members:
        return None
    caps = [usable_output(m, est_prompt_tokens) for m in members]
    if any(c is None for c in caps):
        return None
    return min(caps)


def rep_overflow(council_cfg: dict, n_chars: "int | None", n_times: "int | None",
                 kind: str = "text", system_chars: int = 0) -> "bool | None":
    """Does this rep's estimated output exceed its assigned council's ceiling?

    `n_chars` is the rep's CONTENT size; `system_chars` is the system prompt the caller will send
    with it (#846 — the caller supplies it because the prompt registry lives in Stage 6, which the
    base layer may not import). `kind` selects the request shape via `rep_prompt_size`.

    TRI-STATE, and the third state is the point (#822):
      True  — overflows: the council's weakest member cannot emit what this rep needs.
      False — fits.
      None  — UN-ASSESSABLE: no `n_times` (every binary/image rep — `representation.n_times` is
              NULL for them), or a council member outside the catalog.

    `None` must never be folded into `False` by a caller. Image reps carry no countable times, so
    scoring them "fits" would report the vision tier as clean when it was merely unmeasured — and
    the vision tier is exactly where the higher-ceiling remedy routing (#823) lives, so a False
    there would bias the very population epic #80 is meant to choose among."""
    est = estimate_output_tokens(n_times)
    if est is None:
        return None
    total_chars, n_images = rep_prompt_size(n_chars, system_chars, kind)
    ceiling = council_ceiling(council_cfg, estimate_prompt_tokens(total_chars, n_images))
    if ceiling is None:
        return None
    return est > ceiling


# The two ways a model's window can make a rep's read structurally incomplete (#709/#793). They live
# HERE, in the base layer, because both the producer (process_governance.stage7_run.council_degraded,
# which classifies) and the consumer (stage7_extract.requests, which words the remedy) need the same
# vocabulary, and the layering contract forbids the lower one importing the higher. Shared constant,
# never a literal repeated across files (the #755 lesson).
DEGRADED_REFUSED = "context_refused"     # the voter never answered — its window rejected the request
DEGRADED_TRUNCATED = "window_truncated"  # the voter answered PARTIALLY — some rows are missing
DEGRADED_LOOPED = "degenerate_repetition"  # #812: the voter answered with ONE row over and over
# #822: the rep's ESTIMATED output exceeds the assigned council's ceiling (its weakest member's
# `usable_output`). Unlike the three above — each a fact about a call that was actually made — this
# is knowable PRE-FLIGHT, from content size + council membership alone, before a cent is spent.
DEGRADED_OVERFLOW = "output_overflow"

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

# #822 puts OVERFLOW at the head: it is the CAUSE the other three are symptoms of. A council that
# structurally cannot emit the rep's output will then refuse, or truncate, or loop — reporting the
# symptom would point a human at the model's behavior when the dispatch decision is what was wrong.
# Same causal-strength logic that slotted LOOPED ahead of TRUNCATED (#812).
DEGRADED_PRECEDENCE = (DEGRADED_OVERFLOW, DEGRADED_REFUSED, DEGRADED_LOOPED, DEGRADED_TRUNCATED)

# The fallback for an absent/empty/unknown `kinds`, pinned to a NAMED kind rather than to
# DEGRADED_PRECEDENCE[0]. It used to be the head of the tuple, which silently coupled a
# CLASSIFICATION default to an ORDERING decision: #822's reorder would have retroactively relabelled
# every #709–#793-era receipt (and every hand-built marker) as an `output_overflow` — a pre-flight
# claim about dispatch that those receipts never made, about reps that may well fit fine. The
# default belongs to the fail-honest argument below, not to whatever happens to sort first.
DEGRADED_DEFAULT = DEGRADED_REFUSED


def rep_degraded_kinds(rep: dict) -> set:
    """EVERY degradation kind a rep carries, from BOTH sources: the per-call `council_degraded`
    marker (REFUSED/LOOPED/TRUNCATED — facts about calls that were made) and the pre-flight
    `overflow` verdict (a fact about the dispatch decision). The ONE projection every consumer
    reads — the live success path, the live failure path, the #716 replay, telemetry, and
    `detect_requests` (#843/#845/#847/#848: four sites each folding the two sources by hand was
    the implemented-twice-drifts class one layer up; two of them disagreed at review).
    An overflow verdict of None (un-assessable) contributes nothing: it is not a kind, it is the
    absence of an assessment, and the caller counts it separately.

    A `council_degraded` marker PRESENT but carrying no `kinds` (a receipt written between #709
    and #793) is still a degradation — the marker's presence is the fact, the kinds a refinement —
    and it contributes DEGRADED_DEFAULT (#798: never vacuously worded as a truncation)."""
    marker = (rep or {}).get("council_degraded")
    kinds = set((marker or {}).get("kinds", {}).values())
    if marker and not kinds:
        kinds.add(DEGRADED_DEFAULT)
    if (rep or {}).get("overflow") is True:
        kinds.add(DEGRADED_OVERFLOW)
    return kinds


def strongest_kind(kinds) -> str:
    """The strongest degradation kind present in `kinds` (an iterable of kind strings, or a
    {model: kind} dict whose values are read). A marker with an absent/empty `kinds` — receipts
    written between #709 and #793, or a hand-built marker — defaults to DEGRADED_DEFAULT
    (`context_refused`): under-claiming a refusal as a truncation invites 'that was the whole
    roster', the exact misdirection #793 exists to prevent. An unknown kind string also defaults
    that way, for the same fail-honest reason."""
    vals = set(kinds.values() if isinstance(kinds, dict) else (kinds or ()))
    for k in DEGRADED_PRECEDENCE:
        if k in vals:
            return k
    return DEGRADED_DEFAULT


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
