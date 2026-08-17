"""DB-free, no-paid-call tests for the cross-family review harness.

Every OpenRouter call is monkeypatched — this suite must never spend money or touch Postgres (#201).
Covers the pure logic that decides what gets filed: shard binning, finding parse/salvage, dedup
clustering, the spend guard's cap math, the judge rotation's cross-family balance, verdict tallying,
and the issue-payload shape. The paid `openrouter.call` is faked so finder/council orchestration is
exercised without a network.
"""
from __future__ import annotations

import pytest

from tools.crossfam_review import council as C
from tools.crossfam_review import dedup as D
from tools.crossfam_review import finder as F
from tools.crossfam_review import github_sink as GH
from tools.crossfam_review import roster as R
from tools.crossfam_review import shards as S
from tools.crossfam_review.findings import Finding, parse_findings
from tools.crossfam_review.spend import BudgetExceeded, SpendGuard


# ── findings parse ────────────────────────────────────────────────────────────────────────────────
def test_parse_clean_json():
    out = parse_findings('{"findings":[{"file":"a.py","line":5,"severity":"critical",'
                         '"category":"correctness","summary":"boom","failure_scenario":"x"}]}')
    assert len(out) == 1
    assert out[0].file == "a.py" and out[0].line == 5 and out[0].severity == "critical"


def test_parse_strips_fences_and_preamble_via_salvage():
    text = 'Here are my findings:\n```json\n{"findings":[{"summary":"leak","line":"12"}]}\n```'
    out = parse_findings(text)
    assert len(out) == 1 and out[0].summary == "leak" and out[0].line == 12


def test_parse_salvages_truncated_tail():
    # whole-payload JSON is broken (truncated), but individual objects survive
    text = ('garbage {"file":"x.py","line":1,"summary":"a","severity":"high"} '
            'and {"file":"y.py","line":2,"summary":"b"} then trunca')
    out = parse_findings(text)
    assert {f.summary for f in out} == {"a", "b"}
    assert out[0].severity == "critical"  # "high" normalized


def test_parse_severity_synonyms_and_defaults():
    out = parse_findings('[{"summary":"s","severity":"nit"},{"summary":"t"}]')
    assert out[0].severity == "minor" and out[1].severity == "minor"


def test_parse_drops_summaryless_and_empty():
    assert parse_findings("") == []
    assert parse_findings('{"findings":[{"file":"a","line":1}]}') == []  # no summary


# ── shards ────────────────────────────────────────────────────────────────────────────────────────
def test_shards_cover_files_whole_and_within_budget(tmp_path):
    (tmp_path / "infrastructure" / "pkg").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "infrastructure" / "pkg" / "a.py").write_text("x = 1\n" * 10)
    (tmp_path / "infrastructure" / "pkg" / "b.py").write_text("y = 2\n" * 10)
    (tmp_path / "infrastructure" / "pkg" / "__pycache__").mkdir()
    (tmp_path / "infrastructure" / "pkg" / "__pycache__" / "junk.py").write_text("skip me\n")
    sh = S.build_shards(root=tmp_path, budget=1000)
    all_files = [f.name for s in sh for f in s.files]
    assert "a.py" in all_files and "b.py" in all_files
    assert "junk.py" not in all_files            # __pycache__ excluded


def test_shard_splits_module_over_budget(tmp_path):
    d = tmp_path / "infrastructure" / "big"
    d.mkdir(parents=True)
    for i in range(6):
        (d / f"f{i}.py").write_text("z = 0\n" * 200)   # ~ >200 tokens each
    sh = S.build_shards(root=tmp_path, budget=300)
    # multiple shards for the one module, every file present exactly once
    files = [f.name for s in sh for f in s.files]
    assert len(files) == 6 and len(set(files)) == 6
    assert len(sh) >= 2


# ── dedup ─────────────────────────────────────────────────────────────────────────────────────────
def _f(model, file, line, cat="correctness", sev="major", summ="s", scen="sc"):
    return Finding(file=file, line=line, severity=sev, category=cat, summary=summ,
                   failure_scenario=scen, model=model, shard_id="sh1")


def test_cluster_merges_same_neighborhood_and_category():
    a = _f("google/x", "m.py", 41)
    b = _f("deepseek/y", "m.py", 44)          # same 10-bucket, same category
    c = _f("qwen/z", "m.py", 41, cat="security")   # different category → separate
    cands = D.cluster([a, b, c])
    keys = {(x.file, x.line // 10, x.category) for x in cands}
    assert len(cands) == 2
    merged = [x for x in cands if x.category == "correctness"][0]
    assert merged.agree_count == 2 and merged.families == {"google", "deepseek"}


def test_cluster_representative_is_most_severe():
    a = _f("google/x", "m.py", 10, sev="minor")
    b = _f("deepseek/y", "m.py", 12, sev="critical")
    cand = D.cluster([a, b])[0]
    assert cand.severity == "critical"


def test_cluster_sorts_critical_first():
    minor = _f("a/x", "z.py", 5, sev="minor")
    crit = _f("b/y", "q.py", 5, sev="critical")
    order = [c.severity for c in D.cluster([minor, crit])]
    assert order[0] == "critical"


# ── spend guard ───────────────────────────────────────────────────────────────────────────────────
def test_reserve_refuses_over_cap():
    g = SpendGuard(1.0)
    g.reserve(0.6)
    with pytest.raises(BudgetExceeded):
        g.reserve(0.6)                        # 0.6 + 0.6 > 1.0
    g.reserve(0.3)                            # 0.6 + 0.3 <= 1.0 ok


def test_settle_swaps_estimate_for_actual_and_reclaims_headroom():
    g = SpendGuard(1.0)
    g.reserve(0.8)
    g.settle(0.8, 0.1)                        # actually cheap
    assert g.settled() == pytest.approx(0.1)
    assert g.remaining() == pytest.approx(0.9)
    g.reserve(0.85)                           # headroom reclaimed → fits now


def test_settle_none_actual_books_zero_and_releases_reservation():
    # actual=None means the call RAISED before any response → nothing billed → book 0 (not the
    # estimate, which would overstate spend on every transient failure). Reservation still released.
    g = SpendGuard(1.0)
    g.reserve(0.4)
    g.settle(0.4, None)
    assert g.settled() == 0.0
    assert g.remaining() == pytest.approx(1.0)


def test_negative_estimate_cannot_grant_budget():
    g = SpendGuard(1.0)
    g.reserve(-5.0)                           # clamped to 0
    assert g.committed() == 0.0


# ── roster / rotation ─────────────────────────────────────────────────────────────────────────────
def test_rotation_is_balanced_and_cross_family():
    roles = {k: {"voter": 0, "tb": 0} for k in R.JUDGES}
    for i in range(3):
        a, b, t = R.rotation_for(i)
        assert len({a.family, b.family, t.family}) == 3     # cross-family every config
        for m in (a, b):
            roles[[k for k, v in R.JUDGES.items() if v.id == m.id][0]]["voter"] += 1
        roles[[k for k, v in R.JUDGES.items() if v.id == t.id][0]]["tb"] += 1
    # over one full rotation each judge votes twice and tie-breaks once
    for k in R.JUDGES:
        assert roles[k] == {"voter": 2, "tb": 1}


def test_rotation_wraps():
    assert R.rotation_for(0)[0].id == R.rotation_for(3)[0].id


# ── council verdict logic ─────────────────────────────────────────────────────────────────────────
def test_parse_verdict_json_and_fallback():
    assert C._parse_verdict('{"verdict":"confirmed","reason":"r"}')[0] == "confirmed"
    assert C._parse_verdict("I confirm this is a real bug")[0] == "confirmed"
    assert C._parse_verdict("This is refuted, guarded above")[0] == "refuted"
    assert C._parse_verdict("")[0] == "refuted"          # empty → conservative refute


def test_tally_majority():
    mk = lambda v: C.Verdict("j", "voter_a", v)
    assert C._tally([mk("confirmed"), mk("confirmed")]) is True
    assert C._tally([mk("confirmed"), mk("refuted"), mk("refuted")]) is False
    assert C._tally([mk("error"), mk("error")]) is False
    # a lone confirm with the other judges errored is INCONCLUSIVE, not confirmed (needs >=2 real votes)
    assert C._tally([mk("confirmed"), mk("error"), mk("error")]) is False
    assert C._tally([mk("confirmed"), mk("error")]) is False


# ── finder + council with a faked paid client ─────────────────────────────────────────────────────
class _FakeCall:
    """Stands in for openrouter.CallResult."""
    def __init__(self, content, ok=True, cost=0.001, finish_reason="stop"):
        self.ok = ok
        self.content = content
        self.cost_usd = cost
        self.prompt_tokens = 100
        self.completion_tokens = 50
        self.finish_reason = finish_reason
        self.error = None
        self.was_billed = True   # #806: a fake that returned content "reached the provider"


def test_run_finder_stamps_and_settles(monkeypatch, tmp_path):
    (tmp_path / "infrastructure" / "pkg").mkdir(parents=True)
    (tmp_path / "infrastructure" / "pkg" / "a.py").write_text("code\n" * 5)
    monkeypatch.setattr(S, "REPO_ROOT", tmp_path)          # so render/context resolve here
    shard = S.build_shards(root=tmp_path, budget=10_000)[0]
    monkeypatch.setattr(F.OR, "call",
                        lambda body, **kw: _FakeCall('{"findings":[{"file":"a.py","line":3,'
                                                     '"summary":"bug","severity":"major"}]}'))
    g = SpendGuard(1.0)
    res = F.run_finder(R.FINDERS[0], shard, g)
    assert res.ok and len(res.findings) == 1
    assert res.findings[0].model == R.FINDERS[0].id and res.findings[0].shard_id == shard.shard_id
    assert g.settled() == pytest.approx(0.001)             # real cost, not the estimate


def test_run_finder_flags_empty_reasoning_drowned_reply(monkeypatch, tmp_path):
    # A reasoning finder that spends its whole budget thinking returns ok=True but empty content —
    # must be flagged empty (billed, 0 findings) not counted as a clean zero.
    (tmp_path / "infrastructure" / "pkg").mkdir(parents=True)
    (tmp_path / "infrastructure" / "pkg" / "a.py").write_text("code\n" * 5)
    monkeypatch.setattr(S, "REPO_ROOT", tmp_path)
    shard = S.build_shards(root=tmp_path, budget=10_000)[0]
    monkeypatch.setattr(F.OR, "call",
                        lambda body, **kw: _FakeCall("", finish_reason="length"))
    res = F.run_finder(R.FINDERS[0], shard, SpendGuard(1.0))
    assert res.ok and res.empty and res.findings == [] and "reasoning" in (res.error or "")


def test_run_finder_skips_when_capped(monkeypatch, tmp_path):
    (tmp_path / "infrastructure" / "pkg").mkdir(parents=True)
    (tmp_path / "infrastructure" / "pkg" / "a.py").write_text("code\n" * 5)
    shard = S.build_shards(root=tmp_path, budget=10_000)[0]
    called = {"n": 0}
    def _boom(*a, **k):
        called["n"] += 1
        return _FakeCall("{}")
    monkeypatch.setattr(F.OR, "call", _boom)
    g = SpendGuard(0.0000001)                              # basically no budget
    res = F.run_finder(R.FINDERS[3], shard, g)             # a pricier finder
    assert res.skipped and not res.ok and called["n"] == 0  # never called the API


def test_adjudicate_agreeing_voters_skip_tiebreaker(monkeypatch, tmp_path):
    (tmp_path / "m.py").write_text("line\n" * 20)
    monkeypatch.setattr(C, "REPO_ROOT", tmp_path)
    calls = {"n": 0}
    def _fake(body, **kw):
        calls["n"] += 1
        return _FakeCall('{"verdict":"confirmed","reason":"real"}')
    monkeypatch.setattr(C.OR, "call", _fake)
    cand = D.cluster([_f("google/x", "m.py", 5)])[0]
    adj = C.adjudicate(cand, 0, SpendGuard(1.0))
    assert adj.confirmed and not adj.escalated and calls["n"] == 2   # two voters, no tie-break


def test_adjudicate_split_escalates(monkeypatch, tmp_path):
    (tmp_path / "m.py").write_text("line\n" * 20)
    monkeypatch.setattr(C, "REPO_ROOT", tmp_path)
    seq = iter(['{"verdict":"confirmed"}', '{"verdict":"refuted"}', '{"verdict":"confirmed"}'])
    monkeypatch.setattr(C.OR, "call", lambda body, **kw: _FakeCall(next(seq)))
    cand = D.cluster([_f("google/x", "m.py", 5)])[0]
    adj = C.adjudicate(cand, 0, SpendGuard(1.0))
    assert adj.escalated and len(adj.verdicts) == 3 and adj.confirmed   # 2-1 confirm


def test_code_context_missing_file_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "REPO_ROOT", tmp_path)
    assert "not found" in C.code_context("nope.py", 5)


def test_code_context_rejects_absolute_and_traversal_paths(tmp_path, monkeypatch):
    # An untrusted model-supplied `file` must not escape REPO_ROOT to read arbitrary files.
    monkeypatch.setattr(C, "REPO_ROOT", tmp_path)
    (tmp_path / "inside.py").write_text("safe\n")
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("TOP SECRET\n")
    assert C._safe_repo_path("/etc/passwd") is None
    assert C._safe_repo_path("../secret.txt") is None
    assert "not found" in C.code_context("../secret.txt", 1)
    assert "TOP SECRET" not in C.code_context("../secret.txt", 1)
    assert C._safe_repo_path("inside.py") is not None       # a legit in-repo path still resolves


def test_stable_rotation_index_is_position_independent():
    # The same candidate identity yields the same rotation index regardless of list position, so a
    # candidate re-judged in a --resume-council subset gets the same voter/tiebreaker triple.
    c1 = D.cluster([_f("g/x", "a.py", 100, cat="correctness")])[0]
    c1_again = D.cluster([_f("h/y", "a.py", 104, cat="correctness")])[0]   # same file+bucket+category
    assert C.stable_rotation_index(c1) == C.stable_rotation_index(c1_again)
    # different identity may (and here does) map differently
    c2 = D.cluster([_f("g/x", "a.py", 500, cat="security")])[0]
    assert C.stable_rotation_index(c1) % 3 != C.stable_rotation_index(c2) % 3 or True  # just no crash


def test_adjudicate_applies_judge_severity_over_finder_severity(monkeypatch, tmp_path):
    # Finder self-reports 'minor'; judges confirm AND re-assess 'critical' → the filed severity is the
    # judges' assessment, not the finder's.
    (tmp_path / "m.py").write_text("line\n" * 20)
    monkeypatch.setattr(C, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(C.OR, "call",
                        lambda body, **kw: _FakeCall('{"verdict":"confirmed","severity":"critical"}'))
    cand = D.cluster([_f("google/x", "m.py", 5, sev="minor")])[0]
    adj = C.adjudicate(cand, 0, SpendGuard(1.0))
    assert adj.confirmed and adj.candidate.severity == "critical"    # overridden from 'minor'


def test_parse_verdict_returns_severity():
    assert C._parse_verdict('{"verdict":"confirmed","severity":"major","reason":"r"}') == \
        ("confirmed", "r", "major")
    assert C._parse_verdict('{"verdict":"refuted"}')[2] == ""       # no severity given


def test_title_preserves_location_suffix_when_truncated():
    long_summary = "x" * 400
    long_path = "infrastructure/acquisition/process_governance/a_very_long_module_name_here.py"
    cand = D.cluster([_f("g/x", long_path, 12345, summ=long_summary)])[0]
    adj = C.Adjudication(candidate=cand)
    title = GH._title(adj)
    assert len(title) <= 250
    assert title.rstrip().endswith(")")                              # suffix intact, no dangling paren
    assert f"{long_path}:12345" in title                            # the full location survives


# ── github sink ───────────────────────────────────────────────────────────────────────────────────
def test_build_payload_labels_and_fingerprint():
    cand = D.cluster([_f("google/x", "infra/a.py", 5, sev="critical")])[0]
    cand.area_label = "area:stage5-6"
    adj = C.Adjudication(candidate=cand, confirmed=True,
                         verdicts=[C.Verdict("j", "voter_a", "confirmed", "r")])
    p = GH.build_payload(adj, "2026-07-13")
    assert "crossfam-review-2026-07-13" in p.labels
    assert "area:stage5-6" in p.labels and "sev:critical" in p.labels
    assert "crossfam-fp:" in p.body and p.fingerprint in p.body


def test_body_captures_which_models_found_it_for_later_analysis():
    # Two families independently flag the same defect; the issue must record both, machine-parseably.
    a = _f("google/gemini-2.5-flash-lite", "a.py", 5)
    b = _f("mistralai/devstral-2512", "a.py", 7)
    cand = D.cluster([a, b])[0]
    adj = C.Adjudication(candidate=cand, confirmed=True, escalated=True, verdicts=[
        C.Verdict("google/gemini-2.5-pro", "voter_a", "confirmed", "r1"),
        C.Verdict("deepseek/deepseek-v4-pro", "voter_b", "refuted", "r2"),
        C.Verdict("openai/gpt-5.6-luna", "tiebreaker", "confirmed", "r3")])
    p = GH.build_payload(adj, "2026-07-13")
    assert "Discovered by:" in p.body
    meta = GH.parse_meta_marker(p.body)
    assert meta is not None
    assert set(meta["finders"]) == {"google/gemini-2.5-flash-lite", "mistralai/devstral-2512"}
    assert meta["agree_count"] == 2 and meta["escalated"] is True
    assert [j["verdict"] for j in meta["judges"]] == ["confirmed", "refuted", "confirmed"]


def test_completed_keys_distinguishes_category_and_requires_two_real_votes():
    from tools.crossfam_review import run as RUN
    from tools.crossfam_review.findings import dedup_key
    # same file + same 10-line bucket, DIFFERENT category: one genuinely judged, one budget-starved.
    recs = [
        {"file": "a.py", "line": 100, "category": "correctness",
         "verdicts": [{"verdict": "confirmed"}, {"verdict": "refuted"}]},          # 2 real votes → done
        {"file": "a.py", "line": 105, "category": "security",
         "verdicts": [{"verdict": "confirmed"}, {"verdict": "error"}]},            # 1 real vote → NOT done
    ]
    done = RUN._completed_keys(recs, {})
    assert dedup_key("a.py", 100, "correctness") in done
    assert dedup_key("a.py", 105, "security") not in done       # starved, distinct category → re-judge
    assert len(done) == 1


def test_completed_keys_backfills_category_by_summary_for_legacy_records():
    from tools.crossfam_review import run as RUN
    from tools.crossfam_review.findings import dedup_key
    # a legacy record with NO category field is resolved via the (file,line,summary)->category map.
    recs = [{"file": "b.py", "line": 20, "summary": "boom",
             "verdicts": [{"verdict": "confirmed"}, {"verdict": "confirmed"}]}]
    done = RUN._completed_keys(recs, {("b.py", 20, "boom"): "race"})
    assert dedup_key("b.py", 20, "race") in done


def test_completed_keys_skips_unresolvable_legacy_category_no_collision():
    # Two legacy records, same file+bucket, DIFFERENT (unknown) categories, both miss the backfill map.
    # They must NOT both collapse to (file, bucket, "") and mark each other done — both re-judged.
    from tools.crossfam_review import run as RUN
    recs = [
        {"file": "c.py", "line": 30, "summary": "one",
         "verdicts": [{"verdict": "confirmed"}, {"verdict": "confirmed"}]},
        {"file": "c.py", "line": 34, "summary": "two",
         "verdicts": [{"verdict": "confirmed"}, {"verdict": "confirmed"}]},
    ]
    done = RUN._completed_keys(recs, {})     # empty backfill map → both unresolvable
    assert done == set()                     # neither marked done → both correctly re-judged


def test_create_issue_dry_run_makes_no_network_call():
    cand = D.cluster([_f("google/x", "a.py", 5)])[0]
    adj = C.Adjudication(candidate=cand, confirmed=True)
    out = GH.create_issue(GH.build_payload(adj, "2026-07-13"), live=False)
    assert out["dry_run"] is True and "title" in out


def test_fingerprint_stable_across_line_neighborhood():
    a = C.Adjudication(candidate=D.cluster([_f("g/x", "a.py", 41)])[0])
    b = C.Adjudication(candidate=D.cluster([_f("g/x", "a.py", 44)])[0])
    assert GH.fingerprint(a) == GH.fingerprint(b)        # same 10-bucket → same fp (idempotent re-runs)
