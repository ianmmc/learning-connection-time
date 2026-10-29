"""#948 / #958 / #949 — Stage 7's error paths, exercised through the REAL SDK over scripted SSE bodies.

The suite's stream fakes (`openai_fakes.Chunk`) yield objects the SDK never yields, so three paths were
green without ever running: a transport failure while iterating (openai >= 3.14 wraps it in
APIConnectionError/APITimeoutError), OpenRouter's mid-stream error EVENT (raised as a bare APIError, never
yielded), and a 400 whose context wording is outside error.message (openai >= 3.38 puts only the message in
str(e)). Everything here goes through `openrouter.call` with a genuine client over httpx2.MockTransport."""
import pytest

from infrastructure.acquisition.stage7_extract import openrouter as OR
import openai_fakes as F

BODY = {"model": "fake/model", "messages": [{"role": "user", "content": "x"}]}
CONTEXT = "This endpoint's maximum context length is 4096 tokens. However, you requested about 9000 tokens."
OK_STREAM = F.sse(F.chunk("hello "), F.chunk("world", finish_reason="stop",
                                            usage={"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.001}), "[DONE]")


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(OR, "TRANSIENT_BACKOFF_S", ())


def test_stream_through_the_real_sdk_is_parsed_by_the_real_sdk(monkeypatch):
    calls = F.patch_real_stream(monkeypatch, OR, [OK_STREAM])
    res = OR.call(BODY)
    assert res.ok and res.content == "hello world" and res.completion_tokens == 2 and len(calls) == 1


@pytest.mark.parametrize("fail_with", ["read", "timeout"])
def test_948_transport_failure_before_any_output_is_transient_and_retried(monkeypatch, fail_with):
    calls = F.patch_real_stream(monkeypatch, OR, [OK_STREAM], fail_after=(0, 0), fail_with=fail_with)
    res = OR.call(BODY)
    assert res.ok and res.transient_retries == 1 and len(calls) == 2       # retried once, then recovered


@pytest.mark.parametrize("fail_with,cause", [("read", "ReadError"), ("timeout", "ReadTimeout")])
def test_948_transport_failure_after_partial_output_is_a_per_call_miss_not_a_retry(monkeypatch, fail_with, cause):
    """After partial output the generation was billed; #711 keeps neither its cost nor every generation id,
    so re-sending would bill again invisibly. Stays what it was before openai 3.14 wrapped it: 'other'."""
    calls = F.patch_real_stream(monkeypatch, OR, [OK_STREAM], fail_after=(0, 1), fail_with=fail_with)
    res = OR.call(BODY)
    assert not res.ok and res.error_kind == "other" and len(calls) == 1
    assert res.content == "hello " and res.generation_id == "gen-test-123"   # partial kept, id kept
    assert cause in res.error                                                # the cause, not just 'Connection error.'


def test_958_mid_stream_error_event_is_classified_by_the_one_rule(monkeypatch):
    """OpenRouter's error EVENT on an HTTP-200 stream: raised by the SDK as a bare APIError (never yielded).
    Context wording -> 'context' (structural, not retried); partial content kept; 'mid-stream:' prefix."""
    body = F.sse(F.chunk("partial "), F.chunk(error={"message": CONTEXT, "code": 400}, finish_reason="error"), "[DONE]")
    calls = F.patch_real_stream(monkeypatch, OR, [body])
    res = OR.call(BODY)
    assert not res.ok and res.error_kind == "context" and len(calls) == 1
    assert res.content == "partial " and res.error.startswith("mid-stream: ") and "4096" in res.error


def test_958_mid_stream_error_event_without_context_wording_is_transient_and_retried(monkeypatch):
    body = F.sse(F.chunk("partial "), F.chunk(error={"message": "upstream hiccup", "code": 502}, finish_reason="error"), "[DONE]")
    calls = F.patch_real_stream(monkeypatch, OR, [body, OK_STREAM])
    res = OR.call(BODY)
    assert res.ok and res.transient_retries == 1 and len(calls) == 2 and res.content == "hello world"


@pytest.mark.parametrize("shape,body", [
    ("openrouter wrapper, text in metadata.raw", {"error": {"message": "Provider returned error", "code": 400,
                                                             "metadata": {"raw": CONTEXT, "provider_name": "DeepInfra"}}}),
    ("bare {error: text}", {"error": CONTEXT}),
    ("{detail: text}", {"detail": CONTEXT}),
    ("non-JSON HTML body", f"<html><body>400 Bad Request: {CONTEXT}</body></html>"),
])
def test_949_context_wording_outside_error_message_still_classifies_context(monkeypatch, shape, body):
    """openai >= 3.38 puts only error.message in str(e); the classifier must read the body too. Measured
    through the installed SDK whichever version it is — on <3.38 str(e) carried the body, on >=3.38 only
    `_error_detail` does — so this holds on both sides of the change."""
    e = F.sdk_error(status=400, body=body)
    detail = OR._error_detail(e)
    assert OR.classify_error(e.status_code, detail) == "context", (shape, detail)
    assert CONTEXT in detail                                        # the provider's text is PERSISTED, not lost


def test_949_a_status_error_through_call_persists_the_upstream_detail(monkeypatch):
    import openai
    err = F.sdk_error(status=400, body={"error": {"message": "Provider returned error", "code": 400,
                                                  "metadata": {"raw": CONTEXT}}})
    calls = F.patch_real_stream(monkeypatch, OR, [OK_STREAM])

    class _Boom:
        def __init__(self, **kw):
            import types
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
                create=lambda **b: (_ for _ in ()).throw(err)))
    monkeypatch.setattr(openai, "OpenAI", _Boom)
    res = OR.call(BODY)
    assert not res.ok and res.error_kind == "context" and "DeepInfra" not in res.error and "4096" in res.error


def test_949_error_detail_appends_the_body_when_str_lacks_it_and_the_cause_when_hidden():
    """Version-independent half of #949/#948: on openai < 3.38 str(e) still carries the body, so the
    parametrized test above cannot fail there. This one feeds `_error_detail` the >= 3.38 / >= 3.14 shapes
    directly: a message-only str(e) with the body on `.body`, and a bare 'Connection error.' with the
    transport cause on `__cause__`."""
    class _StatusLike(Exception):
        body = {"error": {"message": "Provider returned error", "metadata": {"raw": CONTEXT}}}

        def __str__(self):
            return "Provider returned error"

    detail = OR._error_detail(_StatusLike())
    assert detail.startswith("Provider returned error | ") and CONTEXT in detail
    assert OR.classify_error(400, detail) == "context"

    class _ConnLike(Exception):
        def __str__(self):
            return "Connection error."
    e = _ConnLike()
    e.__cause__ = ConnectionResetError("connection reset by peer")
    assert OR._error_detail(e) == "Connection error. | ConnectionResetError: connection reset by peer"
