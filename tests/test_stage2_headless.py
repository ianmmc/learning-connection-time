"""Stage 2 headless Wave-1 runner (REQ-104) — the `claude -p` discovery path.

DB-free by construction: the live subprocess is injected via `_run` (a fake CompletedProcess) and
the registry is monkeypatched to an in-memory dict, so nothing here needs Docker or makes a live
WebSearch/OpenRouter call. The deterministic tail is exercised through real discover_stage2 code
(merge/gate/residual/flatten/write) against a tmp RAW_DIR.
"""
import json
import subprocess
import types

import jsonschema
import pytest

from infrastructure.acquisition.stage2_discover import headless as H
from infrastructure.acquisition.stage2_discover import discover_stage2 as D2
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths


def _district(did="9999999", domain="testschools.example"):
    return {
        "district_id": did, "name": "Test Schools District", "state": "ZZ", "domain": domain,
        "schools_by_band": {
            "elementary": {"schools": [{"school_id": f"{did}001", "name": "Test Elementary", "level": "Elementary"}]},
            "high": {"schools": [{"school_id": f"{did}002", "name": "Test High", "level": "High"}]},
        },
    }


def _fake_run(stdout="", returncode=0, stderr="", capture=None):
    """Build a subprocess.run stand-in returning a canned CompletedProcess and (optionally) recording
    the call args into `capture` (a dict) for assertions."""
    def run(cmd, **kwargs):
        if capture is not None:
            capture["cmd"], capture["kwargs"] = cmd, kwargs
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    return run


def _envelope(payload):
    """A success envelope with --json-schema output on the confirmed `structured_output` key."""
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "result": "Done.", "structured_output": payload, "permission_denials": []})


def _seq_run(stdouts, returncodes=None):
    """subprocess.run stand-in that returns each canned (stdout, returncode) in sequence -- to
    exercise the retry loop."""
    rcs = returncodes or [0] * len(stdouts)
    calls = {"n": 0}

    def run(cmd, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return subprocess.CompletedProcess(cmd, rcs[i], stdout=stdouts[i], stderr="")
    run.calls = calls
    return run


# --------------------------------------------------------------------------- prompt
class TestPrompt:
    def test_includes_toolsearch_step_and_no_id_in_query_guard(self):
        d = _district()
        roster = D2.build_roster(d)
        p = H.build_wave1_prompt(d, roster)
        assert 'select:WebSearch' in p          # the deferred-tool load step (a real fix, not optional)
        assert "Do NOT include the school_id" in p
        assert "Do not guess URLs" in p

    def test_scoped_domain_sets_allowed_domains(self):
        p = H.build_wave1_prompt(_district(domain="foo.k12.tx.us"), [])
        assert '["foo.k12.tx.us"]' in p

    def test_no_domain_searches_unscoped(self):
        p = H.build_wave1_prompt(_district(domain=""), [])
        assert "search unscoped" in p
        assert "allowed_domains" not in p

    def test_every_school_listed_with_name_built_query_not_id(self):
        d = _district()
        roster = D2.build_roster(d)
        p = H.build_wave1_prompt(d, roster)
        for r in roster:
            assert f"school_id {r['school_id']}" in p        # id is a label...
            assert r["query"] in p                            # ...but the query is name-built
        # the school_id must never appear *inside* a SEARCH FOR quoted query
        for line in p.splitlines():
            if "SEARCH FOR:" in line:
                assert "9999999" not in line.split("SEARCH FOR:")[1]


# --------------------------------------------------------------------------- schema
class TestSchema:
    def test_schema_is_valid_and_accepts_a_good_payload(self):
        jsonschema.Draft202012Validator.check_schema(H.WAVE1_SCHEMA)
        good = {"district_id": "9999999", "domain": "testschools.example",
                "schools": [{"school_id": "9999999001", "urls": ["https://x/y"]},
                            {"school_id": "9999999002", "urls": []}]}
        jsonschema.validate(good, H.WAVE1_SCHEMA)

    def test_schema_rejects_missing_district_seed(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"schools": []}, H.WAVE1_SCHEMA)


# --------------------------------------------------------------------------- envelope parsing
class TestExtractPayload:
    def test_result_as_json_string(self):
        env = {"is_error": False, "result": json.dumps({"district_id": "D", "domain": "", "schools": []})}
        assert H._extract_result_payload(env)["district_id"] == "D"

    def test_result_as_fenced_json(self):
        env = {"is_error": False, "result": "```json\n{\"district_id\": \"D\", \"domain\": \"\", \"schools\": []}\n```"}
        assert H._extract_result_payload(env)["district_id"] == "D"

    def test_structured_output_key_preferred(self):
        env = {"is_error": False, "structured_output": {"district_id": "D2", "domain": "", "schools": []},
               "result": "ignored"}
        assert H._extract_result_payload(env)["district_id"] == "D2"

    def test_is_error_raises(self):
        with pytest.raises(RuntimeError):
            H._extract_result_payload({"is_error": True, "result": "quota exceeded"})


# --------------------------------------------------------------------------- CLI subprocess
class TestRunClaudeCli:
    def test_builds_expected_command_and_pipes_prompt_on_stdin(self):
        cap = {}
        payload = {"district_id": "9999999", "domain": "testschools.example", "schools": []}
        out = H.run_claude_cli("THE PROMPT", _run=_fake_run(_envelope(payload), capture=cap))
        assert out == payload
        cmd, kw = cap["cmd"], cap["kwargs"]
        assert cmd[:2] == ["claude", "-p"]
        assert "--allowedTools" in cmd and cmd[cmd.index("--allowedTools") + 1] == "WebSearch"
        assert "--json-schema" in cmd
        assert cmd[cmd.index("--output-format") + 1] == "json"
        assert "--strict-mcp-config" in cmd and "--disable-slash-commands" in cmd
        assert kw["input"] == "THE PROMPT"                       # prompt on stdin, not argv
        assert kw["cwd"] == str(paths.REPO_ROOT)                 # repo-anchored, never CWD

    def test_nonzero_exit_with_non_json_raises_after_retries(self):
        with pytest.raises(RuntimeError, match="exit 1"):
            H.run_claude_cli("p", _run=_fake_run("", returncode=1, stderr="boom"))

    def test_non_json_stdout_raises(self):
        with pytest.raises(RuntimeError, match="non-JSON"):
            H.run_claude_cli("p", _run=_fake_run("not json at all"))

    def test_retries_then_succeeds_on_structured_output_flake(self):
        """The observed live flake: subtype error_max_structured_output_retries (exit 1, valid JSON
        error envelope). One re-invocation recovers it."""
        flake = json.dumps({"type": "result", "subtype": H.STRUCTURED_RETRY_SUBTYPE,
                            "is_error": True, "errors": ["Failed to provide valid structured output"]})
        payload = {"district_id": "D", "domain": "", "schools": []}
        run = _seq_run([flake, _envelope(payload)], returncodes=[1, 0])
        assert H.run_claude_cli("p", retries=1, _run=run) == payload
        assert run.calls["n"] == 2          # retried exactly once

    def test_structured_flake_exhausts_retries_and_raises(self):
        flake = json.dumps({"subtype": H.STRUCTURED_RETRY_SUBTYPE, "is_error": True, "errors": ["x"]})
        with pytest.raises(RuntimeError, match="failed after 2 attempt"):
            H.run_claude_cli("p", retries=1, _run=_seq_run([flake, flake], returncodes=[1, 1]))

    def test_genuine_error_raises_immediately_without_burning_retries(self):
        err = json.dumps({"subtype": "error_during_execution", "is_error": True,
                          "errors": ["auth failed"]})
        run = _seq_run([err, _envelope({"district_id": "D", "domain": "", "schools": []})])
        with pytest.raises(RuntimeError, match="error_during_execution"):
            H.run_claude_cli("p", retries=1, _run=run)
        assert run.calls["n"] == 1          # did NOT retry a genuine (non-flaky) error

    def test_websearch_denial_raises(self):
        env = json.dumps({"subtype": "success", "is_error": False, "structured_output": {},
                          "permission_denials": [{"tool_name": "WebSearch", "reason": "not allowed"}]})
        with pytest.raises(RuntimeError, match="denied WebSearch"):
            H.run_claude_cli("p", _run=_fake_run(env))


# --------------------------------------------------------------------------- finish tail (real D2)
class TestFinishFromWave1:
    def test_on_domain_urls_write_discovery_and_yield_found_all(self, tmp_path, monkeypatch):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        d = _district()
        raw = {"district_id": "9999999", "domain": "testschools.example", "schools": [
            {"school_id": "9999999001", "urls": ["https://testschools.example/elem/bell"]},
            {"school_id": "9999999002", "urls": ["https://testschools.example/high/bell"]}]}
        registry = {"schema_version": 2, "districts": {}, "_events": []}
        outcome = H.finish_from_wave1({"batch_id": "batch_00099"}, d, raw, registry)
        assert outcome == "found_all"
        disc = D2.lea_dir("9999999", d["name"]) / "discovery.json"
        assert disc.exists()
        assert registry["_events"], "finish_district must buffer a stage event"

    def test_seed_mismatch_halts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        raw = {"district_id": "WRONG", "domain": "testschools.example", "schools": []}
        with pytest.raises(SystemExit):
            H.finish_from_wave1({"batch_id": "b"}, _district(), raw, {"districts": {}, "_events": []})


# --------------------------------------------------------------------------- Wave-1 failover
class TestWave1Failover:
    """Issue #29 failover matrix: ANY Bright Data infrastructure failure (billing SystemExit,
    429/non-JSON TransientProviderError, network timeout/ConnectionError/5xx) fails over to Serper;
    the hard halt is reserved for Serper ALSO failing on billing/auth. Returns (provider, urls)
    so run_wave1 can record true provenance (issue #30)."""

    def test_brightdata_primary_used_when_healthy(self, monkeypatch):
        from infrastructure.acquisition.common import discover as DISC
        monkeypatch.setattr(DISC, "brightdata_search", lambda q, d: ["https://bd/ok"])
        monkeypatch.setattr(DISC, "serper_search", lambda q, d: pytest.fail("serper must not run"))
        assert H.brightdata_then_serper("q", "d.org") == ("brightdata", ["https://bd/ok"])

    def test_serper_failover_on_brightdata_billing_systemexit(self, monkeypatch):
        from infrastructure.acquisition.common import discover as DISC
        def bd(q, d): raise SystemExit("Bright Data out of credits")
        monkeypatch.setattr(DISC, "brightdata_search", bd)
        monkeypatch.setattr(DISC, "serper_search", lambda q, d: ["https://serper/failover"])
        assert H.brightdata_then_serper("q", "d.org") == ("serper", ["https://serper/failover"])

    def test_serper_failover_on_brightdata_network_timeout(self, monkeypatch):
        """The issue #29 outage case: a requests timeout used to propagate as a plain exception
        that run_wave1 swallowed into urls=[] -- Serper never fired. Now it fails over."""
        import requests as requests_module
        from infrastructure.acquisition.common import discover as DISC
        def bd(q, d): raise requests_module.ConnectTimeout("connect timed out")
        monkeypatch.setattr(DISC, "brightdata_search", bd)
        monkeypatch.setattr(DISC, "serper_search", lambda q, d: ["https://serper/failover"])
        assert H.brightdata_then_serper("q", "d.org") == ("serper", ["https://serper/failover"])

    def test_serper_failover_on_brightdata_5xx(self, monkeypatch):
        import requests as requests_module
        from infrastructure.acquisition.common import discover as DISC
        def bd(q, d): raise requests_module.HTTPError("502 Server Error")
        monkeypatch.setattr(DISC, "brightdata_search", bd)
        monkeypatch.setattr(DISC, "serper_search", lambda q, d: ["https://serper/failover"])
        assert H.brightdata_then_serper("q", "d.org") == ("serper", ["https://serper/failover"])

    def test_serper_failover_on_brightdata_nonjson_zone_runtimeerror(self, monkeypatch):
        from infrastructure.acquisition.common import discover as DISC
        def bd(q, d): raise DISC.TransientProviderError("Bright Data returned non-JSON")
        monkeypatch.setattr(DISC, "brightdata_search", bd)
        monkeypatch.setattr(DISC, "serper_search", lambda q, d: ["https://serper/failover"])
        assert H.brightdata_then_serper("q", "d.org") == ("serper", ["https://serper/failover"])

    def test_serper_billing_failure_propagates_halt(self, monkeypatch):
        from infrastructure.acquisition.common import discover as DISC
        def boom(q, d): raise SystemExit("exhausted")
        monkeypatch.setattr(DISC, "brightdata_search", boom)
        monkeypatch.setattr(DISC, "serper_search", boom)
        with pytest.raises(SystemExit):
            H.brightdata_then_serper("q", "d.org")   # both Google providers gone -> halt

    def test_serper_transient_failure_propagates_as_plain_exception(self, monkeypatch):
        """A transient Serper failure after a Bright Data outage is a per-school degrade
        (run_wave1 catches plain exceptions), NOT a whole-run halt."""
        from infrastructure.acquisition.common import discover as DISC
        monkeypatch.setattr(DISC, "brightdata_search",
                            lambda q, d: (_ for _ in ()).throw(SystemExit("bd down")))
        def serper(q, d): raise DISC.TransientProviderError("Serper HTTP 429 after one retry")
        monkeypatch.setattr(DISC, "serper_search", serper)
        with pytest.raises(DISC.TransientProviderError):
            H.brightdata_then_serper("q", "d.org")

    def test_run_wave1_records_serving_provider(self, monkeypatch):
        """Provenance end-to-end (issue #30): the tuple from the cascade lands in
        wave1_provider, and flatten() emits it as the candidate's tool."""
        from infrastructure.acquisition.common import discover as DISC
        monkeypatch.setattr(DISC, "brightdata_search",
                            lambda q, d: (_ for _ in ()).throw(SystemExit("bd down")))
        monkeypatch.setattr(DISC, "serper_search", lambda q, d: [f"https://{d}/bell"])
        roster = D2.build_roster(_district())
        D2.run_wave1(roster, "testschools.example", H.brightdata_then_serper)
        assert all(r["wave1_provider"] == "serper" for r in roster)
        cands = D2.flatten(roster)
        assert cands and all(c["tools"] == ["serper"] for c in cands)


# --------------------------------------------------------------------------- Wave-2 (Claude, residual)
class TestWave2Claude:
    def test_maps_claude_urls_onto_residual_and_gates(self):
        d = _district()
        residual = D2.build_roster(d)   # both schools, treated as residual
        env = _envelope({"district_id": "9999999", "domain": "testschools.example",
                         "schools": [{"school_id": "9999999001", "urls": ["https://testschools.example/elem/bell"]},
                                     {"school_id": "9999999002", "urls": ["https://off-domain.com/x"]}]})
        H._wave2_claude(d, residual, "testschools.example", _run=_fake_run(env))
        by_id = {r["school_id"]: r for r in residual}
        assert any(g["kept"] for g in by_id["9999999001"]["wave2_gated"])    # on-domain kept
        assert not any(g["kept"] for g in by_id["9999999002"]["wave2_gated"])  # off-domain gated out
        assert all(r["wave2_invoked"] for r in residual)
        # issue #30: Wave-2 candidates are labeled with the real provider, not "openrouter"
        assert all(r["wave2_provider"] == "claude_websearch" for r in residual)
        cands = D2.flatten([{**r, "wave1_gated": r.get("wave1_gated", [])} for r in residual])
        assert any(c["tools"] == ["claude_websearch"] for c in cands)

    def test_claude_failure_degrades_to_manual_flag_not_halt(self):
        d = _district()
        residual = D2.build_roster(d)
        H._wave2_claude(d, residual, "testschools.example", _run=_fake_run("not json", returncode=1))
        # no crash; residual got no kept urls -> stays manual_flag
        assert all(r["wave2_raw_urls"] == [] for r in residual)


# --------------------------------------------------------------------------- orchestration
@pytest.fixture
def inmem_registry(monkeypatch):
    """Swap DS.load/DS.save for an in-memory registry so run_batch needs no Postgres."""
    reg = {"schema_version": 2, "districts": {}, "_events": []}
    monkeypatch.setattr(DS, "load", lambda: reg)
    monkeypatch.setattr(DS, "save", lambda r, **kw: len(r.get("_events", [])))
    monkeypatch.setattr(DS, "export", lambda: 0)   # run-end export (issue #49) — no Postgres in tests
    # the #168 abandon guard opens its own DB session — no-op it so the runner needs no Postgres
    monkeypatch.setattr(H.BG, "assert_runnable", lambda *a, **k: None)
    return reg


def _on_domain_search(district_domain):
    """A fake Wave-1 search_fn: returns one on-domain URL per query (so every school is 'found')."""
    return lambda query, domain: [f"https://{domain}/{abs(hash(query)) % 1000}"] if domain else []


class TestRunBatch:
    def _batch(self):
        return {"batch_id": "batch_00099", "districts": [_district("1111111"), _district("2222222")]}

    def test_all_districts_found_no_wave2(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        wave2_calls = []
        events = []
        summary = H.run_batch(self._batch(),
                              wave1_search=lambda q, dom: [f"https://{dom}/x"] if dom else [],
                              wave2_runner=lambda *a: wave2_calls.append(a),
                              on_event=lambda k, p: events.append((k, p.get("district_id"))))
        assert summary["todo"] == 2
        assert {r["outcome"] for r in summary["results"]} == {"found_all"}
        assert wave2_calls == []                                  # Wave 1 satisfied all -> no residual
        assert ("dispatched", "1111111") in events and ("completed", "2222222") in events
        assert (D2.lea_dir("1111111", "Test Schools District") / "discovery.json").exists()

    def test_residual_triggers_wave2_runner(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        wave2_seen = []
        # Wave 1 finds nothing -> every school is residual -> wave2_runner fires per district
        H.run_batch(self._batch(), wave1_search=lambda q, dom: [],
                    wave2_runner=lambda district, residual, domain: wave2_seen.append(district["district_id"]))
        assert sorted(wave2_seen) == ["1111111", "2222222"]

    def test_district_error_is_isolated(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        def w2(district, residual, domain):
            if district["district_id"] == "1111111":
                raise RuntimeError("boom")
        summary = H.run_batch(self._batch(), wave1_search=lambda q, dom: [], wave2_runner=w2)
        by_id = {r["district_id"]: r for r in summary["results"]}
        assert by_id["1111111"]["outcome"] == "error"
        assert by_id["2222222"]["outcome"] != "error"            # one failure doesn't abort the batch
        assert any(e.get("event_type") == "failed" for e in inmem_registry["_events"])

    def test_billing_systemexit_halts_whole_run(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        def w1(q, dom): raise SystemExit("both providers exhausted")
        with pytest.raises(SystemExit):
            H.run_batch(self._batch(), wave1_search=w1)

    def test_already_on_disk_is_skipped_not_redone(self, tmp_path, monkeypatch, inmem_registry):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        done = D2.lea_dir("1111111", "Test Schools District")
        done.mkdir(parents=True)
        (done / "discovery.json").write_text("{}")
        searched = []
        summary = H.run_batch(self._batch(),
                              wave1_search=lambda q, dom: searched.append(dom) or ([f"https://{dom}/x"] if dom else []),
                              wave2_runner=lambda *a: None)
        assert summary["todo"] == 1 and summary["skipped"] == 1
        assert "testschools.example" in searched   # only the todo district was searched (both share domain)


# ------------------ #620: a redo batch's Stage-2 status is BATCH-scoped ------------------
@pytest.mark.govdb
def test_620_a_redo_batch_reports_todo_until_it_has_run(gov_session, monkeypatch, tmp_path):
    """THE BUG #620 HIT IN PRODUCTION. `discovery.json` existing means "discovered at some point",
    which is the wrong question for a batch whose PURPOSE is re-discovering districts that already
    have artifacts. Every district read `done`, the rollup read `todo: 0`, and stage2.js REPLACES the
    Run control with "All districts discovered." when `todo === 0` — so a deliberate redo could not be
    started from the console at all, while `reconcile` would happily have processed every district.

    The view and the run disagreed about "done", and the view won because it owns the button."""
    from sqlalchemy import text
    from infrastructure.acquisition.common import db as gdb
    from infrastructure.acquisition.stage2_discover import headless as H2
    gdb.init_precious_schema()
    s = gov_session
    monkeypatch.setattr(H2.gdb, "session_scope", lambda: __import__("contextlib").nullcontext(s))

    did, name = "ZZ620A", "Redo Test District"
    ddir = tmp_path / "ZZ620A_Redo"
    ddir.mkdir(parents=True)
    (ddir / "discovery.json").write_text("{}")           # prior round's artifact exists on disk
    monkeypatch.setattr(H2.D2, "lea_dir", lambda d, n: ddir)

    batch = {"batch_id": "batch_zz620", "batch_type": "follow-up", "redo_attempted": True,
             "districts": [{"district_id": did, "name": name, "state": "ZZ", "domain": "x.org"}]}

    rows = H2.status_for_batch(batch)
    assert rows[0]["status"] == "todo"                   # was "done" — the button-hiding bug
    assert H2.rollup(rows)["todo"] == 1                  # what stage2.js gates the Run control on

    # …and once THIS batch has actually dispatched it, it flips to done.
    # #655: the marker is the `dispatched` event, via the SAME shared helper Stages 3/4 use
    # (DS.dispatched_by_batch) rather than the hand-rolled "any stage=2 event" twin this test
    # originally pinned. Stage 2's completion events are not universally stamped — 12 of 147
    # `found_all` rows carry no batch_id — while all 126 `dispatched` rows do.
    s.execute(text("INSERT INTO state_event (district_id, stage_name, event_type, "
                   "batch_id, created_at, actor) VALUES (:d, 'discover', 'dispatched', "
                   ":b, 'now', 'zz')"), {"d": did, "b": "batch_zz620"})
    s.flush()
    assert H2.status_for_batch(batch)[0]["status"] == "done"


@pytest.mark.govdb
def test_620_an_ordinary_batch_still_uses_the_disk_rule(gov_session, monkeypatch, tmp_path):
    """The fix is scoped to declared redo batches: a first-run batch keeps the byte-for-byte disk
    rule, so the 19 pre-existing non-redo batches are untouched. A district discovered before the
    batch_id-stamped state_event era has no attributable event, and must not regress to `todo`."""
    import contextlib
    from infrastructure.acquisition.common import db as gdb
    from infrastructure.acquisition.stage2_discover import headless as H2
    gdb.init_precious_schema()
    monkeypatch.setattr(H2.gdb, "session_scope", lambda: contextlib.nullcontext(gov_session))

    did = "ZZ620B"
    ddir = tmp_path / "ZZ620B_Ordinary"
    ddir.mkdir(parents=True)
    (ddir / "discovery.json").write_text("{}")
    monkeypatch.setattr(H2.D2, "lea_dir", lambda d, n: ddir)

    batch = {"batch_id": "batch_zz620b", "batch_type": "first-run",
             "districts": [{"district_id": did, "name": "Ordinary", "state": "ZZ", "domain": "y.org"}]}
    assert H2.status_for_batch(batch)[0]["status"] == "done"   # disk rule, no state_event needed
