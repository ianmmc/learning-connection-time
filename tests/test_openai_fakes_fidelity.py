"""#933 — the Stage-7 error fixtures are the SDK's OWN exceptions, never hand-built proxies.

Under openai 3 the suite stayed green while every fixture built its errors from httpx-1 objects the SDK can no
longer produce: duck typing hid it, so the tests measured our classifier against something that never happens.
These pins make that drift fail loudly — including on the NEXT SDK major, because they read the installed SDK
rather than naming a transport library."""
import ast
import typing
from pathlib import Path

import openai
import pytest

from infrastructure.acquisition.stage7_extract import openrouter as OR
from openai_fakes import sdk_error

TESTS = Path(__file__).parent


def _sdk_response_type():
    """The response class the INSTALLED SDK's APIStatusError is typed against (httpx2 under openai 3)."""
    return typing.get_type_hints(openai.APIStatusError.__init__)["response"]


@pytest.mark.parametrize("status,cls", [
    (400, openai.BadRequestError),
    (402, openai.APIStatusError),
    (429, openai.RateLimitError),
    (500, openai.InternalServerError),
])
def test_status_errors_are_the_sdks_own(status, cls):
    e = sdk_error(status=status, message="boom")
    assert isinstance(e, cls) and e.status_code == status
    assert isinstance(e.response, _sdk_response_type())


def test_transport_failures_are_the_sdks_own():
    assert isinstance(sdk_error(timeout=True), openai.APITimeoutError)
    e = sdk_error(connect=True)
    assert isinstance(e, openai.APIConnectionError) and not isinstance(e, openai.APITimeoutError)


@pytest.mark.parametrize("status,message,kind", [
    (400, "This endpoint's maximum context length is 32768 tokens.", "context"),
    (400, "Requested tokens exceed the context window", "context"),
    (400, "invalid model id", "transient"),
    (500, "upstream error; maximum context length is 32768", "transient"),   # #709: status gates it
])
def test_classifier_on_the_sdks_real_error_text(status, message, kind):
    """The production classifier fed exactly what openrouter.call feeds it on the APIStatusError branch —
    the GENUINE SDK's status_code + str(e) (its own 'Error code: 400 - {...}' framing), not a hand-written
    imitation of that format."""
    e = sdk_error(status=status, message=message)
    assert OR.classify_error(e.status_code, str(e)) == kind


def test_no_test_hand_builds_an_sdk_error():
    """Every SDK error a test raises comes from `openai_fakes.sdk_error`. A direct construction — `openai.X(...)`,
    `from openai import X; X(...)`, or an alias of either — is the drift this issue fixed (#958 widened it
    beyond the literal `openai.<X>Error(...)` form, and to subdirectories)."""
    offenders = []
    for path in TESTS.rglob("*.py"):
        if path.name == "openai_fakes.py":
            continue
        tree = ast.parse(path.read_text())
        from_openai = {}                                   # local name -> openai attribute
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "openai":
                for alias in node.names:
                    from_openai[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "openai":
                        from_openai[alias.asname or alias.name] = "<module>"
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                    and from_openai.get(f.value.id) == "<module>" and f.attr.endswith("Error"):
                offenders.append(f"{path.relative_to(TESTS)}:{node.lineno} {f.value.id}.{f.attr}(...)")
            elif isinstance(f, ast.Name) and from_openai.get(f.id, "").endswith("Error"):
                offenders.append(f"{path.relative_to(TESTS)}:{node.lineno} {f.id}(...) [from openai import {from_openai[f.id]}]")
    assert not offenders, "use openai_fakes.sdk_error instead:\n  " + "\n  ".join(offenders)
