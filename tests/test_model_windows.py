"""REQ-174 (#714/#709) — per-model window accounting: the catalog, the clamp, the pre-flight
refusal, the structural-400 classification, and the council-degraded marker.

Values pinned here are the 2026-08-16 OpenRouter fetch recorded in MODEL_WINDOWS; the findings
report (2026-08-16-714-709-context-accounting.md) carries the refresh command. The live cases:
Orange 1201440 (both voters zeroed) and Memphis 4700148 (mistral 400) — the numbers in the
mistral tests are those receipts' verbatim shapes.
"""
import pytest

from infrastructure.acquisition.common.model_families import (
    DEGRADED_LOOPED, DEGRADED_REFUSED, DEGRADED_TRUNCATED, FAMILY, MODEL_WINDOWS,
    WINDOW_MARGIN_TOKENS, usable_output)
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
        # #811: the clamp is fully determined for this input — min(16_384, 32_768 - 4_334 - 512)
        # = 16_384 exactly. `<=` passed for every OVER-aggressive regression too (a doubled
        # margin, a clamp to MIN_USEFUL_OUTPUT, a clamp to 0) — each of which under-sizes and
        # truncates the roster, #793's own harm, silently. Pin the value AND the invariant.
        assert sent["max_tokens"] == 16384                   # the completion cap binds, exactly
        est = OR._est_prompt_tokens(_body(MISTRAL, "x" * 13000))
        assert est + sent["max_tokens"] <= 32768             # the 400 shape is unrepresentable

    def test_p1_context_term_binds_exactly(self, monkeypatch):
        """#811's second half: a prompt big enough that the CONTEXT term of the min() binds, not
        max_out — pinned exactly, so neither term of the clamp can be dropped unnoticed (the old
        assertion would have survived removing the context term entirely)."""
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
        body = _body(MISTRAL, "x" * 90000)                   # exactly 30,000 est tokens
        assert OR._est_prompt_tokens(body) == 30000
        OR.call(body, max_tokens=32000)
        assert sent["max_tokens"] == 32768 - 30000 - WINDOW_MARGIN_TOKENS   # context binds: 2,256

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

    def test_802_present_transient_error_kind_is_authoritative(self):
        """#802: the text markers are the FALLBACK for legacy receipts, never an override — a call
        authoritatively classified 'transient' whose message merely echoes window metadata (a
        timeout string quoting request params) must NOT mark the council degraded."""
        assert council_degraded([
            {"model": MISTRAL, "role": "voter", "ok": False, "error_kind": "transient",
             "error": "upstream timeout while streaming (model context window: 32768)"},
        ]) is None
        # and the fallback still works when error_kind is ABSENT (a legacy receipt)
        d = council_degraded([
            {"model": MISTRAL, "role": "voter", "ok": False,
             "error": "maximum context length is 32768 tokens"},
        ])
        assert d and d["kinds"] == {MISTRAL: DEGRADED_REFUSED}


class TestClassifyAndEstimate:
    def test_803_midstream_context_error_classifies_structural(self, monkeypatch):
        """#803: a provider that rejects on context AFTER the stream opens (mid-stream SSE error
        event) classifies 'context' via the same ONE rule as the HTTP-400 branch."""
        import os
        from types import SimpleNamespace as NS
        import openai

        def _chunks():
            yield NS(id="gen-1", usage=None,
                     model_extra={"error": {"message": "maximum context length exceeded"}},
                     choices=[])

        class _C:
            def create(self, **kw):
                return _chunks()

        class _Client:
            def __init__(self, *a, **k):
                self.chat = NS(completions=_C())

        monkeypatch.setattr(openai, "OpenAI", _Client)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        res = OR.call(_body(MISTRAL, "small"))
        assert not res.ok and res.error_kind == "context"

    def test_803_midstream_ordinary_error_stays_transient(self, monkeypatch):
        from types import SimpleNamespace as NS
        import openai

        def _chunks():
            yield NS(id="gen-1", usage=None,
                     model_extra={"error": {"message": "upstream disconnected"}}, choices=[])

        class _C:
            def create(self, **kw):
                return _chunks()

        class _Client:
            def __init__(self, *a, **k):
                self.chat = NS(completions=_C())

        monkeypatch.setattr(openai, "OpenAI", _Client)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        res = OR.call(_body(MISTRAL, "small"))
        assert not res.ok and res.error_kind == "transient"

    def test_classify_error_gates_http_status_on_400(self):
        """A 500 whose message echoes window metadata stays transient; only a 400 (or a
        status-less mid-stream event) can classify structural."""
        assert OR.classify_error(500, "maximum context length is 32768") == "transient"
        assert OR.classify_error(400, "maximum context length is 32768") == "context"
        assert OR.classify_error(None, "maximum context length is 32768") == "context"
        assert OR.classify_error(400, "invalid role in message 3") == "transient"

    def test_805_image_parts_cost_prompt_tokens(self):
        """#805: an image part is real prompt-side context — counting it zero made the clamp and
        pre-flight refusal inert for the whole vision tier."""
        text_only = _body(MISTRAL, "x" * 3000)
        with_img = {"model": MISTRAL, "messages": [{"role": "user", "content": [
            {"type": "text", "text": "x" * 3000},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ]}]}
        base = OR._est_prompt_tokens(text_only)
        assert OR._est_prompt_tokens(with_img) == base + OR.IMAGE_PART_EST_TOKENS

    def test_805_many_images_can_trip_preflight(self, monkeypatch):
        """Enough image parts must be able to fill a small window — the refusal fires with no
        client ever constructed (the vision-shaped case #805 said nothing tested)."""
        import openai

        def _boom(*a, **k):
            raise AssertionError("client constructed — image prompt should refuse pre-flight")

        monkeypatch.setattr(openai, "OpenAI", _boom)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        n = (MODEL_WINDOWS[MISTRAL]["context"] // OR.IMAGE_PART_EST_TOKENS) + 1
        body = {"model": MISTRAL, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}] * n}]}
        res = OR.call(body)
        assert not res.ok and res.error_kind == "context"

    def test_806_preflight_refusal_is_not_billed(self, monkeypatch):
        import openai
        monkeypatch.setattr(openai, "OpenAI",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no client")))
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        res = OR.call(_body(MISTRAL, "x" * 105000))
        assert not res.ok and res.error_kind == "context"
        assert res.was_billed is False
        # a provider 400 DID reach the provider — was_billed stays True (latency > 0)
        billed = OR.CallResult(model=MISTRAL, ok=False, error_kind="context",
                               error="400", latency_ms=120)
        assert billed.was_billed is True

    def test_801_max_tokens_sent_rides_the_result(self, monkeypatch):
        """#801: the run log reports the ceiling ACTUALLY sent (per-model), not the global
        constant — the value must ride the CallResult for the call record to carry it."""
        from types import SimpleNamespace as NS
        import openai

        def _chunks():
            yield NS(id="g", usage=NS(prompt_tokens=10, completion_tokens=16384, cost=0.01),
                     model_extra={},
                     choices=[NS(delta=NS(content="x"), finish_reason="length")])

        class _C:
            def create(self, **kw):
                return _chunks()

        class _Client:
            def __init__(self, *a, **k):
                self.chat = NS(completions=_C())

        monkeypatch.setattr(openai, "OpenAI", _Client)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        res = OR.call(_body(MISTRAL, "x" * 13000), max_tokens=32000)
        assert res.max_tokens_sent == 16384         # the clamp's cap, not the requested 32,000


class TestStrongestKind:
    def test_precedence_and_defaults(self):
        from infrastructure.acquisition.common.model_families import strongest_kind
        assert strongest_kind([DEGRADED_TRUNCATED]) == DEGRADED_TRUNCATED
        assert strongest_kind([DEGRADED_TRUNCATED, DEGRADED_REFUSED]) == DEGRADED_REFUSED
        assert strongest_kind({"m": DEGRADED_TRUNCATED}) == DEGRADED_TRUNCATED
        # #798: absent/empty kinds (receipts between #709 and #793) default to the STRONGEST —
        # under-claiming a refusal as a truncation is the misdirection #793 exists to prevent
        assert strongest_kind({}) == DEGRADED_REFUSED
        assert strongest_kind(None) == DEGRADED_REFUSED
        assert strongest_kind(["some_future_kind"]) == DEGRADED_REFUSED


class TestLoopDegrades812:
    """#812: a repetition loop is a THIRD degradation shape — the voter answered with one row over
    and over. It outranks the truncation that stopped it (the loop is the cause, the truncation the
    symptom), so a human is pointed at the read and not at document size."""

    def _looped_call(self, model=GEMINI, rows=420, **kw):
        fact = {"school_name": "MCTI", "grade_level": "high",
                "start_time": "07:30", "end_time": "14:20"}
        return {"model": model, "role": "voter", "ok": True, "error": None, "n_facts": rows,
                "facts": [dict(fact) for _ in range(rows)], "finish_reason": "length", **kw}

    def test_p1_loop_marks_and_outranks_its_truncation(self):
        d = council_degraded([
            {"model": MISTRAL, "role": "voter", "ok": True, "n_facts": 12, "finish_reason": "stop"},
            self._looped_call(),
        ])
        assert d and d["kinds"] == {GEMINI: DEGRADED_LOOPED}      # not window_truncated
        assert "repetition loop" in d["reasons"][GEMINI]

    def test_p2_legacy_receipt_derives_the_loop_at_zero_spend(self):
        """Old receipts store the RAW 420 rows and carry no marker — the classifier re-derives it
        from `facts`, so the #716 replay backfills Stroudsburg/Baldwin without a model call."""
        c = self._looped_call()
        c.pop("degenerate_repetition", None)
        assert council_degraded([c])["kinds"] == {GEMINI: DEGRADED_LOOPED}

    def test_new_receipt_uses_the_stored_marker_over_deduped_facts(self):
        """New receipts store DEDUPED facts (1 row) plus the marker — the stored marker must win,
        or a looped rep would read clean the moment de-duplication started working."""
        c = {"model": GEMINI, "role": "voter", "ok": True, "n_facts": 1,
             "facts": [{"school_name": "MCTI", "grade_level": "high",
                        "start_time": "07:30", "end_time": "14:20"}],
             "finish_reason": "length",
             "degenerate_repetition": {"n_rows": 420, "n_distinct": 1, "ratio": 0.0024}}
        assert council_degraded([c])["kinds"] == {GEMINI: DEGRADED_LOOPED}

    def test_refusal_still_outranks_a_loop(self):
        d = council_degraded([
            {"model": MISTRAL, "role": "voter", "ok": False, "error_kind": "context",
             "error": "pre-flight"},
            self._looped_call(model=MISTRAL),
        ])
        assert d["kinds"] == {MISTRAL: DEGRADED_REFUSED}

    def test_a_looped_then_errored_call_is_still_a_loop(self):
        """The salvage parser keeps partial content on a failed call, so a loop that then errored
        transiently must still classify — the `ok` gate must not hide it."""
        c = self._looped_call(ok=False, error_kind="transient", error="stream reset")
        assert council_degraded([c])["kinds"] == {GEMINI: DEGRADED_LOOPED}

    def test_a_judge_loop_never_marks(self):
        c = self._looped_call(model="qwen/qwen3-235b-a22b-2507")
        c["role"] = "judge"
        assert council_degraded([c]) is None

    def test_precedence_order_is_refused_looped_truncated(self):
        from infrastructure.acquisition.common.model_families import (
            DEGRADED_PRECEDENCE, strongest_kind)
        assert DEGRADED_PRECEDENCE == (DEGRADED_REFUSED, DEGRADED_LOOPED, DEGRADED_TRUNCATED)
        assert strongest_kind([DEGRADED_TRUNCATED, DEGRADED_LOOPED]) == DEGRADED_LOOPED
        assert strongest_kind([DEGRADED_LOOPED, DEGRADED_REFUSED]) == DEGRADED_REFUSED
