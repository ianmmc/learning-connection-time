"""REQ-174 (#714/#709) — per-model window accounting: the catalog, the clamp, the pre-flight
refusal, the structural-400 classification, and the council-degraded marker.

Values pinned here are the 2026-08-16 OpenRouter fetch recorded in MODEL_WINDOWS; the findings
report (2026-08-16-714-709-context-accounting.md) carries the refresh command. The live cases:
Orange 1201440 (both voters zeroed) and Memphis 4700148 (mistral 400) — the numbers in the
mistral tests are those receipts' verbatim shapes.
"""
import pytest

from infrastructure.acquisition.common.model_families import (
    DEGRADED_REFUSED, DEGRADED_TRUNCATED, FAMILY, MODEL_WINDOWS, WINDOW_MARGIN_TOKENS,
    usable_output)
from infrastructure.acquisition.stage7_extract import openrouter as OR
from infrastructure.acquisition.process_governance.stage7_run import council_degraded

MISTRAL = "mistralai/mistral-small-24b-instruct-2501"
GEMINI = "google/gemini-2.5-flash-lite"


def test_windows_catalog_parity_with_family():
    """A model cannot join the FAMILY catalog without its windows: councils.validate() forces
    catalog membership, and this pin forces the windows to ride along — the drift that made
    MAX_TOKENS_CEILING's premise silently false for three models cannot recur."""
    assert set(MODEL_WINDOWS) == set(FAMILY)
    for m, w in MODEL_WINDOWS.items():
        assert w["context"] > 0
        assert w["max_out"] is None or 0 < w["max_out"] <= w["context"]


def test_usable_output_shapes():
    # mistral-small: completion cap binds for small prompts; context binds for big ones
    assert usable_output(MISTRAL, 1000) == 16384                       # max_out is the binder
    assert usable_output(MISTRAL, 30000) == 32768 - 30000 - WINDOW_MARGIN_TOKENS
    # gemini: huge window — the caller's own ceiling is the binder, not the model
    assert usable_output(GEMINI, 4487) == 65535
    # uncatalogued (test fakes, mid-adoption models): None -> caller keeps legacy behavior
    assert usable_output("fake/model", 1000) is None


def _fake_400(monkeypatch, message):
    """Wire a fake OpenAI client whose stream raises APIStatusError(message) — the httpx-backed
    construction test_stage7_openrouter.py's 402 fake established."""
    import httpx
    import openai

    resp = httpx.Response(400, request=httpx.Request("POST", "https://openrouter.ai/x"),
                          text=message)
    err = openai.APIStatusError(message, response=resp, body=None)

    class _Completions:
        def create(self, **kw):
            raise err

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, *a, **k):
            self.chat = _Chat()

    monkeypatch.setattr(openai, "OpenAI", _Client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def _body(model, content):
    return {"model": model, "messages": [{"role": "user", "content": content}]}


class TestCallClamp:
    def test_p1_orange_shape_clamps_below_the_400(self, monkeypatch):
        """The filed #714 case: a 1,020-time rep sized to 32,000 against mistral-small
        (context 32,768 TOTAL). The request must clamp to the model's usable window —
        the sent max_tokens can never reproduce prompt + 32,000 > 32,768."""
        sent = {}
        import openai

        class _Completions:
            def create(self, **kw):
                sent.update(kw)
                raise openai.APITimeoutError(request=None)   # stop after capturing the body

        class _Chat:
            completions = _Completions()

        class _Client:
            def __init__(self, *a, **k):
                self.chat = _Chat()

        monkeypatch.setattr(openai, "OpenAI", _Client)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        mt = OR.size_max_tokens(1020)                        # the Orange sizing: 32,000
        assert mt == 32000
        OR.call(_body(MISTRAL, "x" * 13000), max_tokens=mt)  # ~4.3k est prompt tokens
        assert sent["max_tokens"] <= 16384                   # the completion cap binds
        est = OR._est_prompt_tokens(_body(MISTRAL, "x" * 13000))
        assert est + sent["max_tokens"] <= 32768             # the 400 shape is unrepresentable

    def test_p2_preflight_refusal_costs_nothing(self, monkeypatch):
        """A prompt that (nearly) fills the window refuses BEFORE the network: no client is
        even constructed."""
        import openai

        def _boom(*a, **k):
            raise AssertionError("client constructed — pre-flight refusal must not reach the network")

        monkeypatch.setattr(openai, "OpenAI", _boom)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        res = OR.call(_body(MISTRAL, "x" * 105000))          # ~35k est tokens > 32,768 context
        assert not res.ok and res.error_kind == "context"
        assert res.cost_usd is None and res.prompt_tokens == 0

    def test_p3_provider_context_400_classifies_structural(self, monkeypatch):
        """The Memphis/Orange 400 body classifies error_kind='context', not 'transient'."""
        _fake_400(monkeypatch,
                  "Error code: 400 - This endpoint's maximum context length is 32768 tokens. "
                  "However, you requested about 36487 tokens.")
        res = OR.call(_body(MISTRAL, "small prompt"))
        assert not res.ok and res.error_kind == "context"

    def test_p3_other_400_stays_transient(self, monkeypatch):
        _fake_400(monkeypatch, "Error code: 400 - invalid role in message 3")
        res = OR.call(_body(MISTRAL, "small prompt"))
        assert not res.ok and res.error_kind == "transient"

    def test_p7_unknown_model_is_untouched(self, monkeypatch):
        """Test fakes / uncatalogued models keep legacy behavior exactly — no clamp, no refusal."""
        sent = {}
        import openai

        class _Completions:
            def create(self, **kw):
                sent.update(kw)
                raise openai.APITimeoutError(request=None)

        class _Chat:
            completions = _Completions()

        class _Client:
            def __init__(self, *a, **k):
                self.chat = _Chat()

        monkeypatch.setattr(openai, "OpenAI", _Client)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        OR.call(_body("fake/model", "x" * 500000), max_tokens=32000)
        assert sent["max_tokens"] == 32000


class TestCouncilDegraded:
    def test_p4_voter_context_dropout_marks_degraded(self):
        calls = [
            {"model": GEMINI, "role": "voter", "ok": True, "error": None, "n_facts": 0},
            {"model": MISTRAL, "role": "voter", "ok": False, "error_kind": "context",
             "error": "pre-flight: window cannot take this request"},
        ]
        d = council_degraded(calls)
        assert d and d["models"] == [MISTRAL]

    def test_p4_legacy_receipt_derives_from_error_text(self):
        """Receipts written before error_kind existed (Memphis 3004896917ca's verbatim error)
        derive the same marker — the #716 replay backfills honesty at zero spend."""
        calls = [
            {"model": GEMINI, "role": "voter", "ok": True, "error": None},
            {"model": MISTRAL, "role": "voter", "ok": False,
             "error": "Error code: 400 - This endpoint's maximum context length is 32768 tokens. "
                      "However, you requested about 36487 tokens (4487 of text input)."},
        ]
        d = council_degraded(calls)
        assert d and d["models"] == [MISTRAL]

    def test_transient_and_judge_failures_do_not_mark(self):
        assert council_degraded([
            {"model": MISTRAL, "role": "voter", "ok": False, "error_kind": "transient",
             "error": "timeout"},
            {"model": "q", "role": "judge", "ok": False, "error_kind": "context",
             "error": "maximum context length"},
        ]) is None
        assert council_degraded([]) is None

    def test_p4_refusal_is_kinded(self):
        d = council_degraded([{"model": MISTRAL, "role": "voter", "ok": False,
                               "error_kind": "context", "error": "pre-flight"}])
        assert d["kinds"] == {MISTRAL: DEGRADED_REFUSED}


class TestTruncationDegrades793:
    """#793: a truncated voter reply is the SECOND window failure — the model answered partway and
    the tail schools are gone. Before this, `finish_reason == 'length'` reached a console line and a
    counter and nothing else, so a partial roster read as a complete one."""

    def test_p1_clamped_truncation_marks_degraded(self):
        """The exact shape #792's clamp produces on Orange: max_tokens clamped to the model's cap,
        the reply succeeds but truncates, and no retry headroom is left. Before #793 this returned
        None — the clamp turned a loud 400 into a silent partial."""
        calls = [
            {"model": GEMINI, "role": "voter", "ok": True, "error": None, "n_facts": 179},
            {"model": MISTRAL, "role": "voter", "ok": True, "error": None, "n_facts": 90,
             "finish_reason": "length", "completion_tokens": 16384, "truncation_retried": False},
        ]
        d = council_degraded(calls)
        assert d and d["models"] == [MISTRAL]
        assert d["kinds"] == {MISTRAL: DEGRADED_TRUNCATED}
        assert "truncated" in d["reasons"][MISTRAL].lower()

    def test_p2_recovered_retry_is_not_degradation(self):
        """#169 retried the truncation and the reply came back COMPLETE — recovery is not
        degradation, and marking it would cry wolf on the mechanism that saved us."""
        assert council_degraded([
            {"model": GEMINI, "role": "voter", "ok": True, "error": None, "n_facts": 200},
            {"model": MISTRAL, "role": "voter", "ok": True, "error": None, "n_facts": 200,
             "finish_reason": "stop", "truncation_retried": True},
        ]) is None

    def test_p3_judge_truncation_does_not_mark(self):
        """Same rule as #709: voters carry REQ-056 consensus, the judge does not."""
        assert council_degraded([
            {"model": GEMINI, "role": "voter", "ok": True, "n_facts": 12, "finish_reason": "stop"},
            {"model": "qwen/qwen3-235b-a22b-2507", "role": "judge", "ok": True, "n_facts": 3,
             "finish_reason": "length"},
        ]) is None

    def test_p4_legacy_receipts_backfill_at_zero_spend(self):
        """Baldwin 0100270 (355 facts kept) and Stroudsburg 4222860 (420) — the verbatim shapes
        sitting in shipped receipts today. `finish_reason` has always been stored, so the #716
        replay derives the marker with no new model spend."""
        for did, kept, toks in (("0100270", 355, 16000), ("4222860", 420, 16000)):
            d = council_degraded([
                {"model": GEMINI, "role": "voter", "ok": True, "error": None, "n_facts": kept,
                 "finish_reason": "length", "completion_tokens": toks},
                {"model": MISTRAL, "role": "voter", "ok": True, "error": None, "n_facts": kept,
                 "finish_reason": "stop"},
            ])
            assert d and d["kinds"] == {GEMINI: DEGRADED_TRUNCATED}, did
            assert str(kept) in d["reasons"][GEMINI]

    def test_refusal_outranks_truncation_for_one_model(self):
        """A model recorded in BOTH states reports the refusal — no answer at all is the stronger
        statement, and the two must never both claim the same model."""
        d = council_degraded([
            {"model": MISTRAL, "role": "voter", "ok": False, "error_kind": "context",
             "error": "pre-flight"},
            {"model": MISTRAL, "role": "voter", "ok": True, "n_facts": 5, "finish_reason": "length"},
        ])
        assert d["kinds"] == {MISTRAL: DEGRADED_REFUSED}

    def test_both_voters_truncated_marks_both(self):
        d = council_degraded([
            {"model": GEMINI, "role": "voter", "ok": True, "n_facts": 90, "finish_reason": "length"},
            {"model": MISTRAL, "role": "voter", "ok": True, "n_facts": 40, "finish_reason": "length"},
        ])
        assert d["models"] == sorted([GEMINI, MISTRAL])
        assert set(d["kinds"].values()) == {DEGRADED_TRUNCATED}
