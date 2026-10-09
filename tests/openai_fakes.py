"""Shared fakes for the OpenAI SDK's streaming chunk shape (issue #147).

`openrouter.call` drives the SDK's `chat.completions.create(stream=True)` iterator; these stub the
delta/choice/usage/chunk objects + the client so the call path is testable with no network. Previously
duplicated across test_stage7_openrouter.py and test_streaming_contract.py and already DRIFTING (the
`Usage` signature and `Chunk`'s mid-stream-error support diverged) — one home so they can't.

Test modules alias these to their existing private names, e.g. `from openai_fakes import Chunk as
_Chunk`, and wrap `patch`/`patch_sequence` to bind their module's `OR`."""
import types

import httpx2
import openai

# The REAL client class, captured at import: many tests monkeypatch `openai.OpenAI` with a fake, and
# `sdk_error` must still drive the genuine SDK.
_REAL_OPENAI = openai.OpenAI


def sdk_error(*, status=None, message="", timeout=False, connect=False):
    """The exception the REAL SDK raises for this HTTP outcome (#933) — never a hand-built one.

    Drives a genuine `openai.OpenAI` over an `httpx2.MockTransport` and returns what it raises, so the
    exception class (e.g. `BadRequestError`, not bare `APIStatusError`), the response type the SDK
    actually uses, and `str(e)`'s format are all the SDK's own. Hand-built errors passed with httpx-1
    objects under openai 3 — green tests whose proxy had lost the property under test.
    `status` + `message` -> an OpenRouter-shaped error body; `timeout`/`connect` -> transport failures."""
    def handler(request):
        if timeout:
            raise httpx2.ReadTimeout("timed out", request=request)
        if connect:
            raise httpx2.ConnectError("connection refused", request=request)
        return httpx2.Response(status, json={"error": {"message": message, "code": status}})

    client = _REAL_OPENAI(base_url="https://openrouter.ai/api/v1", api_key="sk-test", max_retries=0,
                          http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    try:
        client.chat.completions.create(model="fake/model", messages=[{"role": "user", "content": "x"}],
                                       stream=True)
    except openai.APIError as e:
        return e
    raise AssertionError("the SDK raised nothing for this outcome")


class Delta:
    def __init__(self, content=None):
        self.content = content


class Choice:
    def __init__(self, content=None, finish_reason=None):
        self.delta = Delta(content)
        self.finish_reason = finish_reason


class Usage:
    def __init__(self, p=0, c=0, cost=None):
        self.prompt_tokens = p
        self.completion_tokens = c
        self.cost = cost
        self.model_extra = {}


class Chunk:
    def __init__(self, choices=(), usage=None, error=None, id="gen-test-123"):
        self.choices = list(choices)
        self.usage = usage
        self.id = id
        self.model_extra = {"error": error} if error else {}


def client_returning(chunks):
    """A fake openai.OpenAI whose chat.completions.create yields `chunks` (captures the request body
    + client kwargs under `client_kwargs`)."""
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


def patch(monkeypatch, OR, chunks):
    """Monkeypatch openai.OpenAI to serve `chunks` and stub `OR.resolve_key`. Returns captured body."""
    Client, captured = client_returning(chunks)
    import openai
    monkeypatch.setattr(openai, "OpenAI", Client)
    monkeypatch.setattr(OR, "resolve_key", lambda explicit=None: "sk-test")
    return captured


def patch_sequence(monkeypatch, OR, batches):
    """Fake whose create() serves batches[i] on the i-th call (a chunk list to yield, or an Exception
    to raise) — for the #169 truncation RETRY, which makes a second call. Returns the per-call bodies."""
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
