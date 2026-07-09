"""Stage 7 OpenRouter client (REQ-117): the SSE-streaming call path, SDK fully mocked — no network.
Covers delta accumulation, usage-from-final-chunk (tokens + cost), finish_reason capture, the
`length`-truncation flag (the silent-tail-loss tripwire), the mid-stream error event, and the
401/402 BillingAuthError halt. Reviewed against openrouter.ai/docs/api/reference/{overview,streaming}."""
import types

import pytest

from infrastructure.acquisition.stage7_extract import openrouter as OR
# The OpenAI-SDK streaming fakes live in ONE place now (#147); aliased to the private names the tests
# below use. `_patch`/`_patch_sequence` bind this module's OR.
from openai_fakes import Chunk as _Chunk, Choice as _Choice, Usage as _Usage
import openai_fakes as _F


def _patch(monkeypatch, chunks):
    return _F.patch(monkeypatch, OR, chunks)


def _patch_sequence(monkeypatch, batches):
    return _F.patch_sequence(monkeypatch, OR, batches)


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
    """#169: a truncated reply triggers ONE retry at MAX_TOKENS_CEILING; when the retry completes,
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
    assert calls[1]["max_tokens"] == OR.MAX_TOKENS_CEILING


def test_truncation_retry_sums_both_billed_attempts_cost(monkeypatch):
    """#182: the truncated first call AND the recovering retry are BOTH real billed calls — the
    returned result's cost/tokens are the SUM, so the REQ-051 budget governor sees true spend (not
    just the surviving call's, which would ~86%-undercount exactly the largest districts)."""
    recovered = [_Chunk([_Choice('{"schedules":[{"school_name":"A"},{"school_name":"B"}]}',
                                  finish_reason="stop")]),
                 _Chunk([], usage=_Usage(500, 900, 0.001))]
    _patch_sequence(monkeypatch, [_truncated_batch(), recovered])   # first: (500, 16000, $0.006)
    res = OR.call(BODY)
    assert res.cost_usd == pytest.approx(0.007)             # 0.006 (truncated) + 0.001 (retry)
    assert res.prompt_tokens == 1000                        # 500 + 500
    assert res.completion_tokens == 16900                   # 16000 + 900


def test_failed_retry_keeps_the_salvaged_head(monkeypatch):
    """If the retry itself ERRORS (transient), don't discard the first attempt's salvaged head —
    return the original content, flagged as retried, with the first (billed) attempt's cost intact."""
    import openai
    import httpx
    timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://openrouter.ai/x"))
    calls = _patch_sequence(monkeypatch, [_truncated_batch(), timeout])
    res = OR.call(BODY)
    assert res.truncated and res.truncation_retried is True and len(calls) == 2
    assert '"school_name":"A"' in res.content               # the first attempt's head survives
    assert res.cost_usd == pytest.approx(0.006)             # #182: the billed first attempt's $ kept
                                                            #       (the errored retry adds no usage)


def test_no_retry_when_already_at_escalated_ceiling(monkeypatch):
    """No infinite escalation: a call already made at MAX_TOKENS_CEILING that still truncates is not
    retried again."""
    calls = _patch_sequence(monkeypatch, [_truncated_batch()])
    res = OR.call(BODY, max_tokens=OR.MAX_TOKENS_CEILING)
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


# --- #180: n_times-based max_tokens pre-sizing ---

def test_size_max_tokens_floors_small_and_unknown_reps():
    # small/unknown reps (86% of traffic) stay at the 16k FLOOR — never sized down, so nothing that
    # fit before can newly truncate. None (image/scan) and 0 (no times) also floor.
    assert OR.size_max_tokens(None) == OR.DEFAULT_MAX_TOKENS
    assert OR.size_max_tokens(0) == OR.DEFAULT_MAX_TOKENS
    assert OR.size_max_tokens(2) == OR.DEFAULT_MAX_TOKENS       # a 1-school rep: est ~71, floored
    assert OR.size_max_tokens(400) == OR.DEFAULT_MAX_TOKENS     # 200 schools ≈ 14.1k est, still ≤ floor


def test_size_max_tokens_scales_big_rosters_and_clamps_to_ceiling():
    # a genuinely big roster is sized UP; nothing exceeds the shared ceiling (which the retry escalates
    # to — #187: one constant, no drift).
    assert OR.DEFAULT_MAX_TOKENS < OR.size_max_tokens(1000) <= OR.MAX_TOKENS_CEILING
    assert OR.size_max_tokens(100000) == OR.MAX_TOKENS_CEILING   # absurd roster clamps, never overflows


def test_size_max_tokens_covers_the_known_truncations():
    # MEASURED before/after (docs EXTRACTION_TOKEN_SIZING): the 3 real truncations would size correctly
    # on the FIRST call. n_times ≈ schools × 2; the sized cap must exceed their real output (~47/school).
    for schools, real_out in [(355, 355 * 47), (420, 420 * 47)]:   # Baldwin, Stroudsburg
        sized = OR.size_max_tokens(schools * 2)
        assert sized >= real_out, f"{schools} schools: sized {sized} < needed {real_out}"
        assert sized <= OR.MAX_TOKENS_CEILING


def test_content_n_times_counts_text_reps_only(monkeypatch):
    # sizing's input: the SAME time-count Stage 5 stores, recomputed from the resolved content. Text
    # reps count; image reps (data/URL content) don't -> None -> floor + the retry backstop.
    from infrastructure.acquisition.process_governance import stage7_run as R7
    txt = "First bell 8:00 AM dismissal 3:15 PM; MS 7:45 AM to 2:50 PM"
    n = R7._content_n_times("text", txt)
    assert n and n >= 2                                          # counted real clock times
    assert R7._content_n_times("image", "data:image/png;base64,AAAA") is None
    assert R7._content_n_times("text", None) is None            # defensive: non-str content
