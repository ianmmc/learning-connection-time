"""REQ-119 — external-AI service calls MUST stream results (SSE), never a single blocking read.

Rationale: a non-streaming completion on a long generation (a big hub district returns a long
single-shot JSON) idle-times-out on the connection — a silent, load-bearing failure mode during
automatic processing AT SCALE. Streaming's keep-alive chunks hold the connection open, deltas arrive
incrementally, and a mid-stream failure yields a partial + a structured error instead of a dropped
socket. The contract is provider-agnostic: OpenRouter today, any alternative API swapped in later must
present the same streaming `call()`.

Two layers of guard: (1) BEHAVIORAL — the live client streams, accumulates many chunks incrementally,
and survives keep-alive gaps; (2) a SOURCE guard — no OpenAI-SDK chat-completion call anywhere in the
acquisition code runs un-streamed, unconditionally (the one-time deprecated-path allowlist emptied and
was removed when its only entry, openrouter_search, was deleted — #87)."""
import ast
from pathlib import Path

import pytest

from infrastructure.acquisition.stage7_extract import openrouter as OR


# ---- minimal fakes for the OpenAI SDK streaming-chunk shape ----
# The OpenAI-SDK streaming fakes live in ONE place now (#147), aliased to this file's private names.
from openai_fakes import Chunk as _Chunk, Choice as _Choice, Usage as _Usage  # noqa: E402
import openai_fakes as _F  # noqa: E402


def _patch(monkeypatch, chunks):
    return _F.patch(monkeypatch, OR, chunks)


BODY = {"model": "google/gemini-2.5-flash-lite", "messages": [{"role": "user", "content": "x"}]}


# --------------------------- behavioral: the live client streams ---------------------------
@pytest.mark.parametrize("max_tokens,temperature", [(16000, 0.1), (600, 0.0), (32000, 0.7)])
def test_live_client_ALWAYS_streams(monkeypatch, max_tokens, temperature):
    # no argument combination turns streaming off — the flag is not caller-controllable to False
    cap = _patch(monkeypatch, [_Chunk([_Choice("hi", "stop")], _Usage(1, 1, 0.0))])
    OR.call(BODY, max_tokens=max_tokens, temperature=temperature)
    assert cap["stream"] is True
    assert cap["extra_body"] == {"usage": {"include": True}}   # native token+cost telemetry requested


def test_streams_many_chunks_incrementally(monkeypatch):
    # 60 content deltas reassembled IN ORDER — proves chunk-by-chunk accumulation, not one blocking read
    pieces = [f"[{i}]" for i in range(60)]
    chunks = [_Chunk([_Choice(p)]) for p in pieces]
    chunks.append(_Chunk([_Choice(None, "stop")], _Usage(10, 60, 0.001)))
    _patch(monkeypatch, chunks)
    res = OR.call(BODY)
    assert res.ok and res.content == "".join(pieces)
    assert res.completion_tokens == 60


def test_tolerates_keepalive_and_empty_chunks(monkeypatch):
    # OpenRouter interleaves keep-alive/empty chunks to hold the socket open on a long generation —
    # they must not break accumulation or drop content (the whole point of streaming at scale)
    chunks = [
        _Chunk([_Choice("a")]),
        _Chunk(),                       # keep-alive: no choices at all
        _Chunk([_Choice(None)]),        # a choice with an empty (None) delta
        _Chunk([_Choice("b")]),
        _Chunk([_Choice("", None)]),    # empty-string delta
        _Chunk([_Choice("c", "stop")], _Usage(5, 3, 0.0002)),
    ]
    _patch(monkeypatch, chunks)
    res = OR.call(BODY)
    assert res.ok and res.content == "abc" and res.finish_reason == "stop"


def test_usage_and_finish_read_after_a_long_stream(monkeypatch):
    # telemetry lands on the FINAL chunk after all content — not a property of a blocking response
    chunks = [_Chunk([_Choice(str(i))], id=None) for i in range(40)]
    chunks.append(_Chunk([_Choice(None, "length")], _Usage(200, 16000, 0.02), id="gen-final"))
    _patch(monkeypatch, chunks)
    # Dispatch AT the escalated ceiling so the #169/#182 truncation-retry doesn't fire here — this test
    # is about reading usage/finish from a long single stream, not the retry (which its own tests cover).
    res = OR.call(BODY, max_tokens=OR.MAX_TOKENS_CEILING)
    assert res.truncated and res.finish_reason == "length"     # the silent-tail-loss tripwire
    assert res.generation_id == "gen-final" and res.completion_tokens == 16000


# --------------------------- source guard: no un-streamed completion calls ---------------------------
# Any un-streamed OpenAI-SDK chat-completion call in acquisition is an unconditional failure (REQ-119).
# (The deprecated-path allowlist this guard once carried was removed with its only entry,
# openrouter_search — #87. If a legitimate exemption ever reappears, re-introduce it deliberately.)
_ACQ = Path(__file__).resolve().parents[1] / "infrastructure" / "acquisition"


def _streams(fn_src: str) -> bool:
    flat = fn_src.replace(" ", "")
    return "stream=True" in flat or '"stream":True' in flat or "'stream':True" in flat


def test_no_nonstreaming_llm_completion_calls_in_acquisition():
    offenders = []
    for py in _ACQ.rglob("*.py"):
        src = py.read_text()
        if "chat.completions.create" not in src:
            continue
        rel = str(py.relative_to(_ACQ)).replace("\\", "/")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fn_src = ast.get_source_segment(src, node) or ""
            if "chat.completions.create" in fn_src and not _streams(fn_src):
                offenders.append(f"{rel}::{node.name}")
    assert not offenders, (
        "un-streamed OpenAI-SDK chat-completion call(s) found — external-AI calls must stream (REQ-119): "
        + ", ".join(offenders))


def test_the_live_extraction_client_is_the_streaming_one():
    # anchor the guard: the live paid surface (the council extraction client) streams
    import inspect
    assert _streams(inspect.getsource(OR.call))
