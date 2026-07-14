"""The model roster for the cross-family review — finders, judges, rotation, and pricing.

Pricing is captured here as a static snapshot (per-1M-token USD, pulled live from the OpenRouter
models API on 2026-07-13) for two jobs only: the pre-run budget ESTIMATE and the spend-guard's
per-call reservation. **Actual spend is always taken from OpenRouter's own `usage.cost`** on each
reply (see `finder.py`/`council.py`) — the numbers here never decide what we were billed, only what
we predict before the call. If OpenRouter renames or reprices a model, the run still bills correctly;
only the estimate drifts. Model ids are validated against the live API in `run.py --preflight`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Model:
    id: str            # full OpenRouter id
    family: str        # coarse family bucket (diversity is per-family, not per-id)
    in_per_m: float    # USD / 1M prompt tokens (snapshot 2026-07-13)
    out_per_m: float   # USD / 1M completion tokens

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return prompt_tokens / 1e6 * self.in_per_m + completion_tokens / 1e6 * self.out_per_m


# ── The 10 finders — one comprehensive pass each, every finder over every shard ────────────────────
# Six of Ian's seven families + four added for Western-family breadth (OpenAI/xAI/Mistral/Meta).
# Each is the code-strongest cheap option in its family (rationale: the 2026-07-13 discussion).
# The OpenAI slot is gpt-4.1-mini (a `std`, non-reasoning model), NOT a GPT-5-series one: reasoning
# models drown as FINDERS. gpt-5.1-codex-mini burned its whole budget thinking on a big shard and
# returned empty content ($ billed, 0 findings) — same failure as glm below. gpt-4.1-mini emits reliably.
#
# z-ai/glm-4.7-flash was DROPPED after the smoke test (2026-07-13): it streams reasoning in a separate
# channel the shared streaming client (stage7_extract.openrouter) doesn't capture, and burns the whole
# token budget there — returning EMPTY content (finish_reason "length", $ billed, 0 findings) at both
# 16k and 32k. Disabling reasoning needs a `reasoning:{enabled:false}` param the SDK only accepts via
# `extra_body`, which that hardcoded client can't forward — an invasive change to extraction-critical
# code for one finder. Ian pre-approved dropping to 10; the nine other families keep the diversity.
FINDERS: list[Model] = [
    Model("deepseek/deepseek-v4-flash",        "deepseek", 0.090, 0.180),
    Model("moonshotai/kimi-k2.5",              "moonshot", 0.375, 2.025),
    Model("qwen/qwen3.7-plus",                 "qwen",     0.320, 1.280),
    Model("xiaomi/mimo-v2.5-pro",              "xiaomi",   0.435, 0.870),
    Model("minimax/minimax-m2.7",              "minimax",  0.240, 0.960),
    Model("google/gemini-2.5-flash-lite",      "google",   0.100, 0.400),
    Model("openai/gpt-4.1-mini",               "openai",   0.400, 1.600),
    Model("x-ai/grok-build-0.1",               "x-ai",     1.000, 2.000),
    Model("mistralai/devstral-2512",           "mistral",  0.400, 2.000),
    Model("meta-llama/llama-4-maverick",       "meta",     0.200, 0.800),
]

# ── The 3-model judge council — cross-family cascade with ROTATING roles ───────────────────────────
# Two voters adjudicate each candidate; a third breaks a split. Which model plays which role rotates
# per-candidate (config = candidate_index % 3) so no model is permanently the tie-breaker (that would
# hand it outsized power). Rotation is deterministic on a stable candidate order → auditable + re-runnable.
# Reasoning models are fine AS JUDGES (small input + a terse verdict → they emit within budget; the
# 2026-07-13 smoke confirmed all three return real verdicts, unlike a reasoning FINDER which drowns).
# The openai slot is gpt-5.6-luna, not gpt-5.1: newer and cheaper (1.0/6.0 vs 1.25/10.0), and judge
# output is where the per-Mtok completion price bites (~40% less on the $/out that dominates council cost).
JUDGES: dict[str, Model] = {
    "gemini":   Model("google/gemini-2.5-pro",   "google",   1.250, 10.000),
    "gpt":      Model("openai/gpt-5.6-luna",     "openai",   1.000,  6.000),
    "deepseek": Model("deepseek/deepseek-v4-pro", "deepseek", 0.435, 0.870),
}

# Each config is (voter_a, voter_b, tiebreaker) by judge key. All three keys appear once per config;
# across the three configs each model is a voter twice and tie-breaker once (balanced influence).
ROTATION: list[tuple[str, str, str]] = [
    ("gemini",   "deepseek", "gpt"),      # i % 3 == 0
    ("gemini",   "gpt",      "deepseek"),  # i % 3 == 1
    ("deepseek", "gpt",      "gemini"),    # i % 3 == 2
]


def rotation_for(index: int) -> tuple[Model, Model, Model]:
    """(voter_a, voter_b, tiebreaker) Models for candidate `index`, rotating deterministically."""
    a, b, t = ROTATION[index % len(ROTATION)]
    return JUDGES[a], JUDGES[b], JUDGES[t]


# Cross-family sanity: the two voters in every rotation config must be different families, and the
# tie-breaker a third — the same rule councils.validate() enforces for extraction (REQ-056). Asserted
# at import so a bad edit to JUDGES/ROTATION fails fast rather than silently voting same-family.
def _assert_cross_family() -> None:
    for a, b, t in ROTATION:
        fams = {JUDGES[a].family, JUDGES[b].family, JUDGES[t].family}
        if len(fams) != 3:
            raise AssertionError(f"rotation config {(a, b, t)} is not three distinct families: {fams}")


_assert_cross_family()
