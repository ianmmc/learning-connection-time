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

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from infrastructure.acquisition.common import paths

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT = 90               # with stream=True this bounds connect/read GAPS, not total duration
# 2000 silently beheaded big multi-school replies (Appoquinimink's 19 schools already ran 827 out-
# tokens; Cleveland's flier carries 93 schools) — the parser salvages the head and the tail schools
# vanish with no error. 16k clears every roster size we've seen while staying inside all six council
# models' completion windows; `finish_reason == "length"` (now captured) is the tripwire if not.
DEFAULT_MAX_TOKENS = 16000
DEFAULT_TEMPERATURE = 0.1
BILLING_AUTH_STATUS = {401, 402}   # key/balance — every later call fails identically → halt

# App attribution (optional per the docs; identifies the app on openrouter.ai rankings/activity).
ATTRIBUTION_HEADERS = {
    "HTTP-Referer": "https://github.com/ianmmc/learning-connection-time",
    "X-Title": "Learning Connection Time",
}


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
    error_kind: Optional[str] = None   # 'transient' | 'other' (billing/auth raises instead)
    finish_reason: Optional[str] = None  # 'stop' | 'length' (TRUNCATED) | 'error' | ...
    generation_id: Optional[str] = None  # OpenRouter gen-... id (chunk.id) — the handle for
    #                                      GET /api/v1/generation (fallback cost/stats + support)

    @property
    def truncated(self) -> bool:
        """The reply was cut by max_tokens — the tail of a multi-school JSON is GONE (the salvage
        parser keeps the head silently, so this flag is the only honest signal)."""
        return self.finish_reason == "length"


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


def call(request_body: dict, *, api_key: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT,
         max_tokens: int = DEFAULT_MAX_TOKENS, temperature: float = DEFAULT_TEMPERATURE) -> CallResult:
    """Execute one OpenRouter chat completion over an SSE STREAM. `request_body` is a
    `stage6_handoff.requests` body ({model, messages}); temperature/max_tokens/usage-telemetry/
    stream are layered on here. Deltas are accumulated to the full content (the caller still sees
    one complete reply); `usage` (native tokens + cost) is read from the final chunk; a mid-stream
    error event ends the call as non-ok but KEEPS the partial content. Returns a `CallResult`;
    raises `BillingAuthError` on 401/402."""
    import openai

    model = request_body.get("model", "?")
    key = resolve_key(api_key)
    if not key:
        return CallResult(model=model, ok=False, error="no OPENROUTER_API_KEY", error_kind="other")

    client = openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key, timeout=timeout,
                           default_headers=ATTRIBUTION_HEADERS)
    body = {"temperature": temperature, "max_tokens": max_tokens, **request_body,
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
        return CallResult(model=model, ok=False, content="".join(parts), latency_ms=_ms(t0),
                          error=str(e), error_kind="transient", generation_id=gen_id)
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
