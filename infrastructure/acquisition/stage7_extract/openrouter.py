"""Stage 7 — the paid OpenRouter chat client (REQ-117).

One model call in, raw content + telemetry out. Parsing (`parse.py`), consensus, and the run
orchestration (`process_governance/stage7_run.py`) live elsewhere — this module only knows how to
POST a chat completion and report what came back. Common-only imports (independent stage).

This is the pipeline's second (and last) paid surface, after Stage-2 discovery. Like the Stage-2
reliability harness it is gated on a key being present — callers check `has_key()` and skip when
absent, so the DB-free test suite never issues a paid call. 401/402 (bad key / exhausted balance)
raises `BillingAuthError` — every later call would fail identically, so the run must halt, not
degrade (mirrors `common.discover`'s BILLING_AUTH split); transient errors (429/5xx/timeout) come
back as a non-ok `CallResult` for the caller to retry or record.

Calls are made with **SSE streaming** (`stream: true` — openrouter.ai/docs/api/reference/streaming;
reviewed against the docs 2026-07-03): OpenRouter's keep-alive comments prevent idle-connection
timeouts on long generations (a big hub district's JSON is a long single read non-streaming), a
mid-stream failure yields a structured error event (`finish_reason: "error"`) with the partial
content instead of a dropped connection, and the SDK's iterator handles SSE parsing. `usage`
telemetry (native token counts + cost, via `usage: {include: true}`) arrives on the FINAL chunk.
`finish_reason` is captured on every call — `"length"` marks a **silently truncated** reply (the
Orange `MAX_TEXT_LEN` lesson, output-side): the salvage parser would quietly keep only the head of
the JSON, so truncation must be visible, never inferred. Cancellation caveat: aborting a stream
stops billing on DeepSeek but NOT Google/Mistral — a killed run still pays for in-flight calls.
"""
from __future__ import annotations

import functools
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Optional

from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common.model_families import usable_output

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT = 90               # with stream=True this bounds connect/read GAPS, not total duration
# The FLOOR (small reps, ~86% of traffic): every roster we've seen fits 16k, so a small rep is never
# sized below this. 2000 once silently beheaded big multi-school replies (Appoquinimink's 19 schools
# ran 827 out-tokens; Cleveland's flier carries 93) — the salvage parser keeps the head and the tail
# schools vanish with no error, so `finish_reason == "length"` (captured) is the tripwire.
DEFAULT_MAX_TOKENS = 16000
# The hard CEILING — inside all six council models' completion windows. ONE constant shared by two
# mechanisms so they can never disagree (#187):
#   • #180 pre-sizing: `size_max_tokens(n_times)` clamps UP to here, so a big roster is sized right on
#     the FIRST call (no truncate-then-retry double prompt-charge);
#   • #169 retry: a truncated reply is re-run ONCE at here to recover the dropped tail — but only when
#     the call was BELOW here. A call already sent AT the ceiling that still truncates gets no retry
#     (nowhere higher to go within the model windows — >680 schools, never observed in 840 calls);
#     `finish_reason == "length"` persists so the incompleteness stays visible.
MAX_TOKENS_CEILING = 32000
# Output-token model (docs/technical-notes/.../EXTRACTION_TOKEN_SIZING_2026-07-06.md, 840 real calls):
# reply length is roster-bound, ~47 completion tokens/school (flat, no verbosity noise); each school
# contributes ~2 clock times (start+end). So schools ≈ n_times/2 and output ≈ schools × 47.
# NB: stage6_handoff/cost.py carries a SECOND output-per-school encoding (per-model fitted
# `output_tokens_per_school`, and its `_n_schools` proxies n_times 1:1, not /2). It's dead today
# (#192 — n_times never reaches handoff reps); when #192 revives it, unify with these constants so
# the gate@6 cost preview and this runtime sizing can't disagree about the same rep.
_TOKENS_PER_SCHOOL = 47
_TIMES_PER_SCHOOL = 2
_SIZING_HEADROOM = 1.5             # grade-band splitting (a K-12 campus emits >1 row/school) + long names
DEFAULT_TEMPERATURE = 0.1
BILLING_AUTH_STATUS = {401, 402}   # key/balance — every later call fails identically → halt
# #714 (REQ-174): per-model window accounting. The 2026-08-16 OpenRouter fetch falsified the
# ceiling's "inside all six models' completion windows" premise for THREE catalogued models
# (mistral-small: 16,384 completion AND 32,768 TOTAL context — so an at-ceiling request with any
# real prompt was auto-400'd; the low-cost-text judge qwen3-235b: 16,384). Every call now clamps
# to `usable_output(model, est_prompt)`; when even that leaves less than MIN_USEFUL_OUTPUT the
# call is REFUSED pre-flight at zero spend (error_kind='context') — the spend-conservative
# direction, and the honest one: a doomed call recorded as a clean zero was #709's silent
# single-family degradation.
MIN_USEFUL_OUTPUT = 1024
# chars-per-token divisor for the pre-flight prompt ESTIMATE — deliberately low (overestimates
# tokens) so the clamp errs toward smaller max_tokens, never toward a provider 400.
_EST_CHARS_PER_TOKEN = 3
# Provider 400 messages that mean the CONTEXT WINDOW was exceeded (structural, not transient):
# OpenRouter/Mistral: "This endpoint's maximum context length is 32768 tokens. However, you
# requested ...". Matched case-insensitively on stable substrings, not exact text.
CONTEXT_ERROR_MARKERS = ("maximum context length", "context length", "context window")

# App attribution (optional per the docs; identifies the app on openrouter.ai rankings/activity).
ATTRIBUTION_HEADERS = {
    "HTTP-Referer": "https://github.com/ianmmc/learning-connection-time",
    "X-Title": "Learning Connection Time",
}


def _est_prompt_tokens(request_body: dict) -> int:
    """Conservative prompt-size estimate for the pre-flight window clamp (#714): total message
    content chars / 3 (real English runs ~3.5-4 chars/token, so this OVERestimates — the clamp
    errs small, never toward a 400). Image parts (list content) count their textual pieces only;
    the base64 payload is not completion-window-relevant the way text tokens are, and the image
    models' windows dwarf the margin anyway."""
    total = 0
    for m in request_body.get("messages") or []:
        c = m.get("content")
        if isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):                      # multimodal parts
            for part in c:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total += len(part["text"])
    return math.ceil(total / _EST_CHARS_PER_TOKEN)


def size_max_tokens(n_times: Optional[int]) -> int:
    """Pre-size a call's `max_tokens` from the rep's clock-time count (#180): output ≈ schools × 47
    and schools ≈ n_times / 2, so a big roster is sized right on the FIRST call instead of truncating
    then paying the prompt again on the #169 retry. Clamped to [floor, ceiling] — a small rep stays at
    the 16k floor (never sized DOWN, so nothing that fit before can newly truncate). `n_times` None/0
    (image/scan reps whose times aren't text-countable, or a rep with no times) → the floor, where the
    #169 retry is the backstop for the residual we genuinely can't predict.

    NB: `max_tokens` is only a ceiling — OpenRouter bills ACTUAL completion tokens, so sizing higher
    costs nothing unless the model uses the room (the tail we WANT); the saving is the eliminated
    duplicate PROMPT charge of the retry."""
    if not n_times:
        return DEFAULT_MAX_TOKENS
    est = math.ceil(n_times / _TIMES_PER_SCHOOL * _TOKENS_PER_SCHOOL * _SIZING_HEADROOM)
    return max(DEFAULT_MAX_TOKENS, min(est, MAX_TOKENS_CEILING))


class BillingAuthError(RuntimeError):
    """HTTP 401/402 — bad/revoked key or exhausted balance. Halts the run (not a per-call miss)."""


@dataclass
class CallResult:
    """One model call's outcome + telemetry (the cost lab consumes tokens/cost later)."""
    model: str
    ok: bool
    content: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Optional[float] = None
    latency_ms: int = 0
    error: Optional[str] = None
    error_kind: Optional[str] = None   # 'transient' | 'context' (structural: the model window
    #                                    cannot take this request — #709/#714) | 'other'
    #                                    (billing/auth raises instead)
    finish_reason: Optional[str] = None  # 'stop' | 'length' (TRUNCATED) | 'error' | ...
    generation_id: Optional[str] = None  # OpenRouter gen-... id (chunk.id) — the handle for
    #                                      GET /api/v1/generation (fallback cost/stats + support)
    truncation_retried: bool = False     # #169: this call was re-run once at MAX_TOKENS_CEILING
    #                                      after a first truncated reply (recovery attempt; the tail)

    @property
    def truncated(self) -> bool:
        """The reply was cut by max_tokens — the tail of a multi-school JSON is GONE (the salvage
        parser keeps the head silently, so this flag is the only honest signal)."""
        return self.finish_reason == "length"


@functools.lru_cache(maxsize=8)
def _client(api_key: str, timeout: int):
    """The OpenAI SDK client, CACHED per (key, timeout) so consecutive calls in a batch reuse ONE
    httpx connection pool instead of a fresh TLS handshake each call (#148: ~30-60s/batch of pure
    handshake). The client is safe to reuse across calls. Tests that swap `openai.OpenAI` for a fake
    rely on the autouse `_reset_openrouter_client_cache` conftest fixture clearing this each test —
    else a prior test's cached fake client would be served (same (key, timeout))."""
    import openai
    return openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key, timeout=timeout,
                         default_headers=ATTRIBUTION_HEADERS)


def resolve_key(explicit: Optional[str] = None) -> Optional[str]:
    """Env first, then the repo-anchored secrets file (same resolution as `common.discover`).
    Never sets os.environ — the return value is used directly, so the key never leaks to
    subprocesses this process might spawn."""
    if explicit:
        return explicit
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        return json.loads(paths.SECRETS_FILE.read_text()).get("OPENROUTER_API_KEY")
    except Exception:
        return None


def has_key() -> bool:
    return bool(resolve_key())


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _usage_cost(usage) -> Optional[float]:
    """OpenRouter returns generation cost in `usage.cost` when the request asks for it
    (`usage:{include:true}`). The OpenAI SDK types don't declare that field, so it lands in
    `model_extra`; check both."""
    if usage is None:
        return None
    c = getattr(usage, "cost", None)
    if c is not None:
        return c
    extra = getattr(usage, "model_extra", None) or {}
    return extra.get("cost")


def _sum_cost(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Sum two optional generation costs, preserving None only when BOTH are unknown — so a billed
    call summed with a cost-less one still reflects the billed spend (#182)."""
    if a is None and b is None:
        return None
    return (a or 0.0) + (b or 0.0)


def call(request_body: dict, *, api_key: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT,
         max_tokens: int = DEFAULT_MAX_TOKENS, temperature: float = DEFAULT_TEMPERATURE) -> CallResult:
    """Execute one OpenRouter chat completion over an SSE STREAM. `request_body` is a
    `stage6_handoff.requests` body ({model, messages}); temperature/max_tokens/usage-telemetry/
    stream are layered on here. Deltas are accumulated to the full content (the caller still sees
    one complete reply); `usage` (native tokens + cost) is read from the final chunk; a mid-stream
    error event ends the call as non-ok but KEEPS the partial content. Callers pre-size `max_tokens`
    from the rep (see `size_max_tokens`, #180); a truncated reply (`finish_reason == "length"`) below
    the ceiling is still retried ONCE at `MAX_TOKENS_CEILING` to recover the dropped tail (#169).
    Returns a `CallResult`; raises `BillingAuthError` on 401/402."""
    import openai

    model = request_body.get("model", "?")
    key = resolve_key(api_key)
    if not key:
        return CallResult(model=model, ok=False, error="no OPENROUTER_API_KEY", error_kind="other")

    # #714 (REQ-174): per-model window accounting. Clamp the sized max_tokens to what THIS model
    # can legally take given its estimated prompt; refuse pre-flight (zero spend) when the window
    # leaves no useful room. `usable_output` is None for uncatalogued models (test fakes, a model
    # mid-adoption): legacy behavior, byte-identical.
    cap = usable_output(model, _est_prompt_tokens(request_body))
    if cap is not None and cap < MIN_USEFUL_OUTPUT:
        return CallResult(
            model=model, ok=False, error_kind="context",
            error=(f"pre-flight: window cannot take this request (usable output {cap} < "
                   f"{MIN_USEFUL_OUTPUT} after prompt) — council-degraded, re-route (#714)"))
    if cap is not None and max_tokens > cap:
        max_tokens = cap

    client = _client(key, timeout)

    def _stream_once(mt: int) -> CallResult:
        body = {"temperature": temperature, "max_tokens": mt, **request_body,
                "stream": True, "extra_body": {"usage": {"include": True}}}
        t0 = time.monotonic()
        parts: list = []
        finish = usage = mid_err = gen_id = None
        try:
            stream = client.chat.completions.create(**body)
            for chunk in stream:
                gen_id = gen_id or getattr(chunk, "id", None)     # the gen-... generation id
                u = getattr(chunk, "usage", None)
                if u is not None:
                    usage = u                                     # the final chunk carries usage
                err = (getattr(chunk, "model_extra", None) or {}).get("error")
                if err:                                           # mid-stream error event (docs: the
                    mid_err = err                                 # stream terminates after it)
                for ch in (chunk.choices or []):
                    delta = getattr(ch, "delta", None)
                    if delta is not None and getattr(delta, "content", None):
                        parts.append(delta.content)
                    if getattr(ch, "finish_reason", None):
                        finish = ch.finish_reason
        except openai.APIStatusError as e:
            status = getattr(e, "status_code", None)
            if status in BILLING_AUTH_STATUS:
                raise BillingAuthError(f"{model}: HTTP {status} — {e}") from e
            # #709: a context-window 400 is STRUCTURAL — retrying the identical request fails
            # identically, and a voter lost to it makes cross-family consensus impossible by
            # construction. Classified apart from 'transient' so the rep can be marked degraded.
            msg = str(e)
            kind = ("context" if status == 400
                    and any(mk in msg.lower() for mk in CONTEXT_ERROR_MARKERS) else "transient")
            return CallResult(model=model, ok=False, content="".join(parts), latency_ms=_ms(t0),
                              error=msg, error_kind=kind, generation_id=gen_id)
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            return CallResult(model=model, ok=False, content="".join(parts), latency_ms=_ms(t0),
                              error=str(e), error_kind="transient", generation_id=gen_id)
        except Exception as e:  # noqa: BLE001 — any other SDK/parse error is a per-call miss, not a halt
            return CallResult(model=model, ok=False, content="".join(parts), latency_ms=_ms(t0),
                              error=str(e), error_kind="other", generation_id=gen_id)

        common = dict(
            model=model, content="".join(parts),
            prompt_tokens=(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0,
            completion_tokens=(getattr(usage, "completion_tokens", 0) or 0) if usage else 0,
            cost_usd=_usage_cost(usage), latency_ms=_ms(t0), finish_reason=finish,
            generation_id=gen_id)
        if mid_err or finish == "error":
            msg = (mid_err or {}).get("message") if isinstance(mid_err, dict) else str(mid_err or "stream error")
            return CallResult(ok=False, error=f"mid-stream: {msg}", error_kind="transient", **common)
        return CallResult(ok=True, **common)

    res = _stream_once(max_tokens)
    # #169: a truncated reply silently drops the tail schools — retry ONCE at the ceiling to recover
    # them. Keep the retry's CONTENT when it SUCCEEDED (fully recovered, or at least a longer head — a
    # still-truncated reply is ok=True with finish_reason "length", so the ⚠ flag persists); a retry
    # that ERRORED keeps the first attempt's salvaged head. Either branch: BOTH attempts were real
    # billed calls, so their cost/tokens/latency are SUMMED onto the returned result — the budget
    # governor (REQ-051) must see true spend, not just the surviving call's (#182).
    # #187: the retry escalates to the ceiling and only when the call was BELOW it — a rep pre-sized
    # AT the ceiling that still truncates gets no (futile) retry, and the ⚠ flag stays.
    # #714: the retry target is per-model too — min(MAX_TOKENS_CEILING, cap). Without the clamp the
    # retry itself would 400 on the very models whose windows caused the truncation.
    retry_ceiling = min(MAX_TOKENS_CEILING, cap) if cap is not None else MAX_TOKENS_CEILING
    if not (res.truncated and max_tokens < retry_ceiling):
        return res
    retry = _stream_once(retry_ceiling)
    keep = retry if retry.ok else res                 # recovered tail vs. salvaged head
    keep.truncation_retried = True
    keep.prompt_tokens = (res.prompt_tokens or 0) + (retry.prompt_tokens or 0)
    keep.completion_tokens = (res.completion_tokens or 0) + (retry.completion_tokens or 0)
    keep.cost_usd = _sum_cost(res.cost_usd, retry.cost_usd)
    keep.latency_ms = res.latency_ms + retry.latency_ms
    return keep
