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
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from infrastructure.acquisition.common import paths

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT = 90
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TEMPERATURE = 0.1
BILLING_AUTH_STATUS = {401, 402}   # key/balance — every later call fails identically → halt


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
    """Execute one OpenRouter chat completion. `request_body` is a `stage6_handoff.requests`
    body ({model, messages}); temperature/max_tokens/usage-telemetry are layered on here.
    Returns a `CallResult`; raises `BillingAuthError` on 401/402."""
    import openai

    model = request_body.get("model", "?")
    key = resolve_key(api_key)
    if not key:
        return CallResult(model=model, ok=False, error="no OPENROUTER_API_KEY", error_kind="other")

    client = openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key, timeout=timeout)
    body = {"temperature": temperature, "max_tokens": max_tokens, **request_body,
            "extra_body": {"usage": {"include": True}}}
    t0 = time.monotonic()
    try:
        resp = client.chat.completions.create(**body)
    except openai.APIStatusError as e:
        status = getattr(e, "status_code", None)
        if status in BILLING_AUTH_STATUS:
            raise BillingAuthError(f"{model}: HTTP {status} — {e}") from e
        return CallResult(model=model, ok=False, latency_ms=_ms(t0), error=str(e), error_kind="transient")
    except (openai.APITimeoutError, openai.APIConnectionError) as e:
        return CallResult(model=model, ok=False, latency_ms=_ms(t0), error=str(e), error_kind="transient")
    except Exception as e:  # noqa: BLE001 — any other SDK/parse error is a per-call miss, not a halt
        return CallResult(model=model, ok=False, latency_ms=_ms(t0), error=str(e), error_kind="other")

    content = (resp.choices[0].message.content or "") if resp.choices else ""
    usage = getattr(resp, "usage", None)
    return CallResult(
        model=model, ok=True, content=content,
        prompt_tokens=(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0,
        completion_tokens=(getattr(usage, "completion_tokens", 0) or 0) if usage else 0,
        cost_usd=_usage_cost(usage), latency_ms=_ms(t0))
