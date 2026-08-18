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

    def test_loop_check_is_data_driven_not_ok_gated(self):
        """#817 correction: live, an errored call records facts=[] (run_council parses only on
        ok), so the ungated loop check is a no-op there — the ungated form exists for call records
        AS DATA: a record that DOES carry looped facts classifies whatever its ok flag says."""
        c = self._looped_call(ok=False, error_kind="transient", error="stream reset")
        assert council_degraded([c])["kinds"] == {GEMINI: DEGRADED_LOOPED}
        # the live errored shape — no facts — is a harmless no-op, not a marker
        assert council_degraded([{"model": GEMINI, "role": "voter", "ok": False,
                                  "error_kind": "transient", "error": "stream reset",
                                  "facts": []}]) is None

    def test_816_transient_error_with_length_finish_is_not_truncated(self):
        """#816: the mid-stream-error path returns ok=False with finish_reason still populated —
        minting DEGRADED_TRUNCATED from it would re-route a URL that genuinely timed out (the
        #802 shape, one field over). Truncation stays gated on ok."""
        assert council_degraded([
            {"model": MISTRAL, "role": "voter", "ok": False, "error_kind": "transient",
             "error": "mid-stream: upstream disconnected", "finish_reason": "length",
             "facts": [], "n_facts": 0},
        ]) is None

    def test_814_untruncated_loop_still_marks(self):
        """#814: New Haven 0626910's verbatim shape — 420 rows / 1 distinct, ok=True,
        finish_reason=None. No truncation signal exists; ONLY the loop detector catches it
        (it read as a clean 420-fact extraction before #812)."""
        c = self._looped_call(model=MISTRAL)
        c["finish_reason"] = None
        d = council_degraded([c])
        assert d and d["kinds"] == {MISTRAL: DEGRADED_LOOPED}

    def test_a_judge_loop_never_marks(self):
        c = self._looped_call(model="qwen/qwen3-235b-a22b-2507")
        c["role"] = "judge"
        assert council_degraded([c]) is None

    def test_precedence_order_is_overflow_refused_looped_truncated(self):
        """#822 prepends OVERFLOW; the #812 relative order below it is unchanged."""
        from infrastructure.acquisition.common.model_families import (
            DEGRADED_OVERFLOW, DEGRADED_PRECEDENCE, strongest_kind)
        assert DEGRADED_PRECEDENCE == (
            DEGRADED_OVERFLOW, DEGRADED_REFUSED, DEGRADED_LOOPED, DEGRADED_TRUNCATED)
        assert strongest_kind([DEGRADED_TRUNCATED, DEGRADED_LOOPED]) == DEGRADED_LOOPED
        assert strongest_kind([DEGRADED_LOOPED, DEGRADED_REFUSED]) == DEGRADED_REFUSED


class TestOperatorSurfaces815:
    """#815: the operator-facing telemetry applies the SAME loop-vs-truncation precedence as the
    classifier — gate@7's human reads these lines to pick a re-route, and 'TRUNCATED, check tail
    loss' about a loop points them at document size when the document is fine."""

    def _mk(self, **c):
        base = {"model": GEMINI, "role": "voter", "ok": True, "error": None, "n_facts": 1,
                "prompt_tokens": 10, "completion_tokens": 20, "cost_usd": 0.001,
                "facts": [{"school_name": "MCTI", "grade_level": "high",
                           "start_time": "07:30", "end_time": "14:20"}]}
        base.update(c)
        return base

    def test_looped_call_counts_looped_not_truncated(self):
        from infrastructure.acquisition.process_governance.stage7_run import _rollup_tel
        rep = {"calls": [self._mk(finish_reason="length", max_tokens_sent=16384,
                                  degenerate_repetition={"n_rows": 420, "n_distinct": 1,
                                                         "ratio": 0.0024})]}
        t = _rollup_tel([rep])
        assert t["looped"] == 1
        assert t["truncated"] == 0
        assert t["truncated_caps"] == []            # the cap list is for GENUINE truncations

    def test_genuine_truncation_still_counts_truncated(self):
        from infrastructure.acquisition.process_governance.stage7_run import _rollup_tel
        rep = {"calls": [self._mk(finish_reason="length", max_tokens_sent=16384)]}
        # 1 distinct fact, finish=length, no loop marker -> a real truncation
        t = _rollup_tel([rep])
        assert t["truncated"] == 1 and t["looped"] == 0
        assert t["truncated_caps"] == [16384]

    def test_legacy_receipt_rows_derive_the_loop_in_rollup(self):
        """A legacy receipt has no stored marker — the rollup re-derives from raw facts, same
        fallback as the classifier, so replay-viewed telemetry matches too."""
        from infrastructure.acquisition.process_governance.stage7_run import _rollup_tel
        fact = {"school_name": "MCTI", "grade_level": "high",
                "start_time": "07:30", "end_time": "14:20"}
        rep = {"calls": [self._mk(finish_reason="length", n_facts=420,
                                  facts=[dict(fact) for _ in range(420)])]}
        t = _rollup_tel([rep])
        assert t["looped"] == 1 and t["truncated"] == 0


def test_818_raw_row_count_always_rides_the_call_record():
    """#818: n_rows_raw is the pre-dedupe emitted-row count — the #794 ground-truth quantity —
    recorded on EVERY call, sub-threshold duplicates included (the 7-identical-row case would
    otherwise be unrecoverable from the receipt)."""
    from infrastructure.acquisition.process_governance.stage7_run import _call_record
    from infrastructure.acquisition.stage7_extract.openrouter import CallResult
    res = CallResult(model=GEMINI, ok=True)
    fact = {"school_name": "MCTI", "grade_level": "high",
            "start_time": "07:30", "end_time": "14:20"}
    rec = _call_record(GEMINI, "voter", res, [dict(fact) for _ in range(7)])
    assert rec["n_rows_raw"] == 7 and rec["n_facts"] == 1     # sub-threshold: no loop marker,
    assert "degenerate_repetition" not in rec                 # but the raw count survives


class TestOverflowDegrades822:
    """#822 — a rep whose estimated OUTPUT exceeds its assigned council's ceiling is degraded
    pre-flight, before a cent is spent, and can never record as a clean zero.

    Distinct from the three kinds above: those are facts about a call that was MADE (it refused, it
    truncated, it looped). Overflow is a fact about the dispatch DECISION, computable from content
    size plus council membership alone. `n_times`/`n_chars` below are the live `representation`
    values for the four records the issue pins (read 2026-08-18)."""

    # (rec_key, n_chars, n_times) — the smallest-n_times usable text rep of each pinned record.
    NO_FITTING_REP = [
        ("4700148:8d0058ac10", 109259, 658),   # Memphis
        ("1200180:52b4f372cd", 12555, 477),    # Broward
        ("0100270:e1ecbe7cfe", 15414, 626),    # Baldwin
        ("3501110:ed61346ff2", 16773, 545),
    ]

    def _text_council(self):
        from infrastructure.acquisition.stage6_handoff import councils as C6
        return C6.load_configs()["low-cost-text"]

    def test_p1_the_four_no_fitting_rep_records_overflow(self):
        """P1 — must fail before this feature existed: each pinned record's text rep needs more
        completion tokens than the low-cost-text council's weakest member can emit."""
        from infrastructure.acquisition.common.model_families import rep_overflow
        cfg = self._text_council()
        for rec_key, n_chars, n_times in self.NO_FITTING_REP:
            assert rep_overflow(cfg, n_chars, n_times) is True, f"{rec_key} should overflow"

    def test_p1_a_rep_that_fits_is_not_flagged(self):
        """The other half of P1 — the flag must discriminate, not fire on everything."""
        from infrastructure.acquisition.common.model_families import rep_overflow
        cfg = self._text_council()
        assert rep_overflow(cfg, 2360, 120) is False      # 0102370:059ddd4a31, live values
        assert rep_overflow(cfg, 4715, 136) is False      # 0200510:e089ddd8c5

    def test_p2_the_ceiling_is_the_weakest_member_including_the_judge(self):
        """P2 — a council whose JUDGE is narrower than both voters takes the judge's ceiling.
        `council_degraded` only ever MARKS voters, but a call the judge cannot serve is a call the
        council cannot serve, so capacity must count all three."""
        from infrastructure.acquisition.common.model_families import (
            council_ceiling, usable_output)
        wide_voters_narrow_judge = {
            "id": "t", "voters": ["google/gemini-2.5-flash", "mistralai/mistral-large-2512"],
            "judge": "qwen/qwen3-235b-a22b-2507"}          # max_out 16,384 — the narrowest
        assert council_ceiling(wide_voters_narrow_judge, 1000) == \
            usable_output("qwen/qwen3-235b-a22b-2507", 1000)
        assert council_ceiling(wide_voters_narrow_judge, 1000) == 16_384

    def test_p2_an_uncatalogued_member_makes_the_ceiling_unknown_not_infinite(self):
        from infrastructure.acquisition.common.model_families import council_ceiling
        cfg = {"id": "t", "voters": ["google/gemini-2.5-flash", "who/unknown-model"],
               "judge": "deepseek/deepseek-v3.2"}
        assert council_ceiling(cfg, 1000) is None

    def test_p4_the_output_estimate_has_exactly_one_implementation(self):
        """P4 — asserted by IDENTITY, not by comparing two results. Two copies that agree today are
        the implemented-twice-drifts class (#798/#810/#799/#816, #834); the only real lock is that
        there is nothing to diverge. `openrouter` re-exports `common`'s function object itself."""
        from infrastructure.acquisition.common import model_families as MF
        assert OR.size_max_tokens is MF.size_max_tokens
        assert OR.MAX_TOKENS_CEILING is MF.MAX_TOKENS_CEILING
        assert OR.MIN_USEFUL_OUTPUT is MF.MIN_USEFUL_OUTPUT
        # ...and the prompt estimate agrees across the two ways its inputs are obtained: Stage 6
        # counts chars/images off the signal row, Stage 7 walks the assembled body.
        body = {"messages": [{"role": "user", "content": "x" * 9000}]}
        assert OR._est_prompt_tokens(body) == MF.estimate_prompt_tokens(9000, 0)

    def test_an_image_rep_is_unassessable_never_false(self):
        """The finding that reshaped this issue. Image reps carry n_times NULL, so scoring them
        `False` would report the whole vision tier as fitting when it was merely unmeasured — and
        the vision tier is exactly where the higher-ceiling remedy (#823) lives."""
        from infrastructure.acquisition.common.model_families import (
            estimate_output_tokens, rep_overflow)
        cfg = self._text_council()
        assert rep_overflow(cfg, None, None) is None
        assert estimate_output_tokens(None) is None
        assert rep_overflow(cfg, None, None) is not False    # explicit: the trap this guards

    def test_the_need_estimate_is_unclamped_so_the_image_ceiling_stays_falsifiable(self):
        """`size_max_tokens` clamps to 32,000, which is BELOW the image council's 32,768 ceiling —
        so a clamped need could never exceed it and '0 records overflow the image council' would be
        true by construction. The need estimate must be able to exceed what it is compared against,
        or the comparison is not a measurement."""
        from infrastructure.acquisition.common.model_families import (
            MAX_TOKENS_CEILING, council_ceiling, estimate_output_tokens, size_max_tokens)
        from infrastructure.acquisition.stage6_handoff import councils as C6
        image_ceiling = council_ceiling(C6.load_configs()["image"], 0)
        assert MAX_TOKENS_CEILING < image_ceiling            # the trap, pinned
        assert size_max_tokens(3211) == MAX_TOKENS_CEILING   # clamped: could never exceed it
        assert estimate_output_tokens(3211) > image_ceiling  # unclamped: it can, and does

    def test_the_empty_kinds_default_survives_a_precedence_reorder(self):
        """#822 put OVERFLOW at index 0. The absent/unknown-kinds default must stay pinned to a
        NAMED kind: a legacy #709-#793 receipt carries no `kinds`, and relabelling it
        `output_overflow` would assert a dispatch-time claim it never made."""
        from infrastructure.acquisition.common.model_families import (
            DEGRADED_DEFAULT, DEGRADED_PRECEDENCE, strongest_kind)
        assert DEGRADED_DEFAULT == DEGRADED_REFUSED
        assert DEGRADED_DEFAULT is not DEGRADED_PRECEDENCE[0]
        assert strongest_kind({}) == DEGRADED_REFUSED
        assert strongest_kind(["not-a-real-kind"]) == DEGRADED_REFUSED

    def test_overflow_outranks_every_symptom_it_causes(self):
        from infrastructure.acquisition.common.model_families import (
            DEGRADED_OVERFLOW, strongest_kind)
        for symptom in (DEGRADED_REFUSED, DEGRADED_LOOPED, DEGRADED_TRUNCATED):
            assert strongest_kind([symptom, DEGRADED_OVERFLOW]) == DEGRADED_OVERFLOW


class TestReviewFindings843to849:
    """The 2026-08-18 review of PR #842 (#843–#849). Each test FAILS against the pre-fix code —
    verified by reverting — or it locks nothing. The common root of #843/#845/#847/#848: the
    "how is this rep degraded" fold was written by hand at FOUR sites (live success, live failure,
    replay, detect_requests) and two of them disagreed at review — the implemented-twice-drifts
    class one layer up. The fix is ONE fold in the base layer, `MF.rep_degraded_kinds`."""

    def test_848_the_one_fold_reads_both_sources(self):
        from infrastructure.acquisition.common.model_families import (
            DEGRADED_DEFAULT, DEGRADED_OVERFLOW, rep_degraded_kinds)
        # overflow-only rep — the case detect_requests explained as ordinary barren
        assert rep_degraded_kinds({"overflow": True}) == {DEGRADED_OVERFLOW}
        # per-call marker only
        assert rep_degraded_kinds({"council_degraded": {"kinds": {"m": DEGRADED_TRUNCATED}}}) \
            == {DEGRADED_TRUNCATED}
        # both — union, not last-write-wins
        assert rep_degraded_kinds({"overflow": True,
                                   "council_degraded": {"kinds": {"m": DEGRADED_LOOPED}}}) \
            == {DEGRADED_OVERFLOW, DEGRADED_LOOPED}
        # un-assessable is NOT a kind — it is the absence of an assessment
        assert rep_degraded_kinds({"overflow": None}) == set()
        assert rep_degraded_kinds({}) == set()
        # #798: a legacy marker with NO kinds is still a degradation, read as the default
        assert rep_degraded_kinds({"council_degraded": {"models": ["m"]}}) == {DEGRADED_DEFAULT}

    def test_848_detect_requests_explains_an_overflow_rep_as_degraded_not_barren(self):
        """Two counters describing the same population must agree: telemetry counted this rep
        degraded, `explain` called it barren."""
        from infrastructure.acquisition.stage7_extract import requests as RQ
        rep = {"rec_key": "D1:x", "file": "a.txt", "accepted": [], "overflow": True}
        explain = {}
        RQ.detect_requests({"district_id": "D1", "reps": [rep], "accepted": [
            {"band": "elementary", "school": "e", "rec_key": "D1:x"}]},
            claimed_bands=["elementary"], real_bands={"elementary"}, explain=explain)
        assert explain["suppressed_degraded_reps"] == 1

    def test_847_an_errored_rep_is_unassessable_not_absent(self):
        """The exception path must set overflow=None explicitly, so the rep lands in the tri-state's
        third arm rather than in none of the three."""
        from infrastructure.acquisition.process_governance.stage7_run import _rollup_tel
        # what the failure path produces now
        failed = {"rec_key": "D1:x", "file": "a", "calls": [], "accepted": [], "unresolved": [],
                  "error": "boom", "overflow": None}
        assert _rollup_tel([failed])["overflow_unassessable"] == 1
        # and the source itself: the failure path SETS the key
        import inspect
        from infrastructure.acquisition.process_governance import stage7_run as S7R
        src = inspect.getsource(S7R._run_district)
        assert 'failed["overflow"] = None' in src

    def test_849_failure_path_has_one_degraded_guard_not_two(self):
        import inspect
        from infrastructure.acquisition.process_governance import stage7_run as S7R
        src = inspect.getsource(S7R._run_district)
        # the failure block: from `failed = {` to `pd["reps"].append(failed)`
        blk = src[src.index("failed = {"):src.index('pd["reps"].append(failed)')]
        assert blk.count("if deg:") == 1
        assert "_stamp_degraded_kind(failed)" in blk    # ...and it uses the ONE fold

    def test_845_replay_re_derives_degraded_kind_but_keeps_the_receipts_overflow_testimony(self):
        """`degraded_kind` is a projection and is always recomputed. `overflow` is the receipt's
        own dispatch-time verdict and is NOT re-judged against today's registry (REQ-175 P7: never
        retroactively relabel). A pre-#822 receipt without the key stays without it."""
        from infrastructure.acquisition.common.model_families import DEGRADED_OVERFLOW
        from infrastructure.acquisition.process_governance.reaggregate import _rebuild_rep
        # (a) pre-#822 receipt: no overflow key, a stale degraded_kind that should NOT survive
        pre = {"rec_key": "D1:x", "file": "a", "calls": [], "degraded_kind": "output_overflow"}
        out = _rebuild_rep(pre)
        assert "overflow" not in out                       # not invented
        assert "degraded_kind" not in out                  # stale projection recomputed away
        # (b) post-#822 receipt with a stored verdict: testimony kept, kind derived FROM it
        post = {"rec_key": "D1:x", "file": "a", "calls": [], "overflow": True}
        out = _rebuild_rep(post)
        assert out["overflow"] is True
        assert out["degraded_kind"] == DEGRADED_OVERFLOW

    def test_843_replay_telemetry_carries_the_degraded_rollup(self, tmp_path, monkeypatch):
        """A replayed degraded receipt must not persist degraded_json='{}' — that inserts a
        higher extraction_id row that gate@7 reads as CLEAN, the exact clean zero #822 forbids.
        Asserted through the dry-run preview, which now surfaces the rollup the replay WILL
        persist (built by the same `_rollup_tel` the live path uses, then zero-spend-overridden)."""
        import json
        from infrastructure.acquisition.process_governance import reaggregate as RA
        rec = {"handoff_hash": "h", "district": {
            "district_id": "D1", "n_reps": 1, "accepted": [], "unresolved": [],
            "reps": [{"rec_key": "D1:x", "file": "a", "kind": "text", "council_id": "c",
                      "judged": False, "calls": [], "accepted": [], "unresolved": [],
                      "overflow": True}]}}
        p = tmp_path / "extraction_h_D1_t.json"
        p.write_text(json.dumps(rec))
        monkeypatch.setattr(RA, "_labels_for_recs", lambda k: {})
        monkeypatch.setattr(RA.S7R, "consensus_context_for_district", lambda *a, **k: None)
        out = RA.reaggregate_receipt(str(p), dry_run=True)
        assert out["degraded"] == {"n": 1, "kinds": {"output_overflow": 1}, "unassessable": 0}
        # ...and the replay's rollup IS the live rollup, not a hand-written dict
        import inspect
        assert "_rollup_tel(reps)" in inspect.getsource(RA.reaggregate_receipt)

    def test_846_dispatch_and_extraction_construct_the_same_estimator_inputs(self):
        """P4 asserted at the CALL SITES, not just the function body: Stage 6 (signal row +
        system prompt) and Stage 7 (assembled body) must yield the same prompt-token estimate for
        the same rep — text AND image."""
        from infrastructure.acquisition.common import model_families as MF
        from infrastructure.acquisition.stage6_handoff import councils as C6, package as PKG6, prompts as P6
        from infrastructure.acquisition.stage6_handoff import requests as R6
        text_cfg = C6.load_configs()["low-cost-text"]
        img_cfg = C6.load_configs()["image"]
        for cfg, kind, content in ((text_cfg, "text", "7:45 AM to 2:30 PM " * 400),
                                   (img_cfg, "image", "data:image/png;base64," + "A" * 5000)):
            model = cfg["voters"][0]
            planned = {"model": model, "prompt_id": P6.select_prompt_id(cfg, model), "kind": kind}
            body = R6.build_request(planned, content)
            stage7 = OR._est_prompt_tokens(body)                       # walks the assembled body
            n_chars = len(content) if kind == "text" else None
            tot, nimg = MF.rep_prompt_size(n_chars, PKG6.system_prompt_chars(cfg), kind)
            stage6 = MF.estimate_prompt_tokens(tot, nimg)             # from the signal row
            assert stage6 == stage7, (kind, stage6, stage7)

    def test_846_the_system_prompt_is_no_longer_omitted(self):
        """The content-only estimate was up to ~1,000 tokens optimistic on v4. Pin that the
        dispatch estimate now exceeds the content-only figure by the system prompt's share."""
        from infrastructure.acquisition.common import model_families as MF
        from infrastructure.acquisition.stage6_handoff import councils as C6, package as PKG6
        cfg = C6.load_configs()["low-cost-text"]
        sys_chars = PKG6.system_prompt_chars(cfg)
        assert sys_chars > 1000                                       # v4 is ~3k chars
        content_only = MF.estimate_prompt_tokens(30000, 0)
        tot, nimg = MF.rep_prompt_size(30000, sys_chars, "text")
        with_system = MF.estimate_prompt_tokens(tot, nimg)
        # the gap is the system prompt's token share (chars/3, ceil'd once over the total)
        assert with_system - content_only >= sys_chars // 3
        assert with_system - content_only <= -(-sys_chars // 3) + 1
