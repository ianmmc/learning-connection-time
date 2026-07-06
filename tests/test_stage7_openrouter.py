"""Stage 7 OpenRouter client (REQ-117): the SSE-streaming call path, SDK fully mocked — no network.
Covers delta accumulation, usage-from-final-chunk (tokens + cost), finish_reason capture, the
`length`-truncation flag (the silent-tail-loss tripwire), the mid-stream error event, and the
401/402 BillingAuthError halt. Reviewed against openrouter.ai/docs/api/reference/{overview,streaming}."""
import types

import pytest

from infrastructure.acquisition.stage7_extract import openrouter as OR


# ---- tiny fakes for the OpenAI SDK's streaming chunk shape ----
class _Delta:
    def __init__(self, content=None):
        self.content = content


class _Choice:
    def __init__(self, content=None, finish_reason=None):
        self.delta = _Delta(content)
        self.finish_reason = finish_reason


class _Usage:
    def __init__(self, p, c, cost):
        self.prompt_tokens = p
        self.completion_tokens = c
        self.cost = cost
        self.model_extra = {}


class _Chunk:
    def __init__(self, choices=(), usage=None, error=None, id="gen-test-123"):
        self.choices = list(choices)
        self.usage = usage
        self.id = id
        self.model_extra = {"error": error} if error else {}


def _client_returning(chunks):
    """A fake openai.OpenAI whose chat.completions.create yields `chunks` (captures the body)."""
    captured = {}

    class _Completions:
        @staticmethod
        def create(**body):
            captured.update(body)
            return iter(chunks)

    class _Client:
        def __init__(self, **kw):
            captured["client_kwargs"] = kw
            self.chat = types.SimpleNamespace(completions=_Completions())

    return _Client, captured


def _patch(monkeypatch, chunks):
    Client, captured = _client_returning(chunks)
    import openai
    monkeypatch.setattr(openai, "OpenAI", Client)
    monkeypatch.setattr(OR, "resolve_key", lambda explicit=None: "sk-test")
    return captured


BODY = {"model": "google/gemini-2.5-flash-lite", "messages": [{"role": "user", "content": "x"}]}


def test_stream_accumulates_deltas_and_reads_final_usage(monkeypatch):
    captured = _patch(monkeypatch, [
        _Chunk([_Choice('{"schedules":[')]),
        _Chunk([_Choice('{"school_name":"A"}]}', finish_reason="stop")]),
        _Chunk([], usage=_Usage(100, 40, 0.00012)),          # final usage chunk, empty choices
    ])
    res = OR.call(BODY)
    assert res.ok and res.content == '{"schedules":[{"school_name":"A"}]}'
    assert res.finish_reason == "stop" and not res.truncated
    assert (res.prompt_tokens, res.completion_tokens, res.cost_usd) == (100, 40, 0.00012)
    assert res.generation_id == "gen-test-123"   # the /api/v1/generation audit handle
    # the request actually asked for a stream + usage accounting + attribution headers
    assert captured["stream"] is True
    assert captured["extra_body"] == {"usage": {"include": True}}
    assert captured["client_kwargs"]["default_headers"] == OR.ATTRIBUTION_HEADERS


def _patch_sequence(monkeypatch, batches):
    """Fake OpenAI whose create() serves batches[i] on the i-th call (a chunk list to yield, or an
    Exception to raise) — for exercising the #169 truncation RETRY, which makes a second call."""
    calls = []

    class _Completions:
        @staticmethod
        def create(**body):
            calls.append(dict(body))
            item = batches[len(calls) - 1]
            if isinstance(item, Exception):
                raise item
            return iter(item)

    class _Client:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(completions=_Completions())

    import openai
    monkeypatch.setattr(openai, "OpenAI", _Client)
    monkeypatch.setattr(OR, "resolve_key", lambda explicit=None: "sk-test")
    return calls


def _truncated_batch():
    return [_Chunk([_Choice('{"schedules":[{"school_name":"A"}', finish_reason="length")]),
            _Chunk([], usage=_Usage(500, 16000, 0.006))]


def test_length_finish_flags_truncation(monkeypatch):
    """A `length` finish flags truncation; with the #169 retry the SAME (still-truncated) mock reply
    on the second call leaves the flag set and records the retry attempt."""
    calls = _patch_sequence(monkeypatch, [_truncated_batch(), _truncated_batch()])
    res = OR.call(BODY)
    assert res.ok and res.truncated and res.finish_reason == "length"
    assert res.truncation_retried is True and len(calls) == 2


def test_truncation_retries_once_at_higher_ceiling_and_recovers(monkeypatch):
    """#169: a truncated reply triggers ONE retry at ESCALATED_MAX_TOKENS; when the retry completes,
    the recovered tail schools are returned and the truncation flag clears."""
    recovered = [_Chunk([_Choice('{"schedules":[{"school_name":"A"},{"school_name":"B"}]}',
                                  finish_reason="stop")]),
                 _Chunk([], usage=_Usage(500, 900, 0.001))]
    calls = _patch_sequence(monkeypatch, [_truncated_batch(), recovered])
    res = OR.call(BODY)
    assert res.ok and not res.truncated and res.finish_reason == "stop"
    assert res.truncation_retried is True
    assert '"school_name":"B"' in res.content               # the previously-dropped tail, recovered
    assert len(calls) == 2                                  # exactly one retry
    assert calls[0]["max_tokens"] == OR.DEFAULT_MAX_TOKENS
    assert calls[1]["max_tokens"] == OR.ESCALATED_MAX_TOKENS


def test_failed_retry_keeps_the_salvaged_head(monkeypatch):
    """If the retry itself ERRORS (transient), don't discard the first attempt's salvaged head —
    return the original content, flagged as retried."""
    import openai
    import httpx
    timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://openrouter.ai/x"))
    calls = _patch_sequence(monkeypatch, [_truncated_batch(), timeout])
    res = OR.call(BODY)
    assert res.truncated and res.truncation_retried is True and len(calls) == 2
    assert '"school_name":"A"' in res.content               # the first attempt's head survives


def test_no_retry_when_already_at_escalated_ceiling(monkeypatch):
    """No infinite escalation: a call already made at ESCALATED_MAX_TOKENS that still truncates is not
    retried again."""
    calls = _patch_sequence(monkeypatch, [_truncated_batch()])
    res = OR.call(BODY, max_tokens=OR.ESCALATED_MAX_TOKENS)
    assert res.truncated and res.truncation_retried is False and len(calls) == 1


def test_no_retry_when_not_truncated(monkeypatch):
    """A clean (finish_reason=stop) reply makes exactly one call — the retry is truncation-only."""
    calls = _patch_sequence(monkeypatch, [[
        _Chunk([_Choice('{"schedules":[]}', finish_reason="stop")]),
        _Chunk([], usage=_Usage(100, 40, 0.0001)),
    ]])
    res = OR.call(BODY)
    assert res.ok and not res.truncated and res.truncation_retried is False and len(calls) == 1


def test_mid_stream_error_keeps_partial_content(monkeypatch):
    _patch(monkeypatch, [
        _Chunk([_Choice('{"schedules":[{"school_name":"A"}')]),
        _Chunk([_Choice("", finish_reason="error")], error={"code": "server_error",
                                                            "message": "Provider disconnected"}),
    ])
    res = OR.call(BODY)
    assert not res.ok and res.error_kind == "transient"
    assert "Provider disconnected" in res.error
    assert '"school_name":"A"' in res.content     # the partial survives for salvage/debugging


def test_billing_auth_raises(monkeypatch):
    import httpx
    import openai

    resp402 = httpx.Response(402, request=httpx.Request("POST", "https://openrouter.ai/x"),
                             text="Payment Required")
    err = openai.APIStatusError("Payment Required", response=resp402, body=None)

    class _Boom:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
                create=lambda **b: (_ for _ in ()).throw(err)))

    monkeypatch.setattr(openai, "OpenAI", _Boom)
    monkeypatch.setattr(OR, "resolve_key", lambda explicit=None: "sk-test")
    with pytest.raises(OR.BillingAuthError):
        OR.call(BODY)


def test_missing_key_is_non_ok_not_raise(monkeypatch):
    monkeypatch.setattr(OR, "resolve_key", lambda explicit=None: None)
    res = OR.call(BODY)
    assert not res.ok and "OPENROUTER_API_KEY" in res.error
