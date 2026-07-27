"""ONE fitness function over the ONE-HOME class (epic #617, the generalization it missed).

The epic diagnosed a rule mirrored across five sites, consolidated it into `common/benchmark.py`, and
wrote a bespoke fitness test so the copies could not grow back. Then, in the same PRs, it introduced
three MORE rules and hand-copied every one of them — `dispatch_type` normalization at 8 sites, the
`redo_attempted` lever bypassed at 2, batch-scoped done-ness with a hand-rolled twin (#650/#658/#655).
None was caught, because the guard that existed protected one specific rule rather than the class.

So the declaration moves here. Adding a consolidated rule to `common/` means adding a row to `RULES`,
and the row is the review surface — the same posture `arch-manifest.json` takes for cross-boundary
edges (#124). A rule with no row is a rule with no guard, and that is now a visible omission rather
than an invisible one.

WHAT A ROW ASSERTS: the `home` file defines the rule, and no file in `scope` re-spells it. The
`forbid` pattern is matched against NORMALIZED source (adjacent string literals joined, whitespace
collapsed), because these rules are usually SQL spread across several source lines — a naive
line-by-line scan misses exactly the copies that matter, which is how the original five hid.

DELIBERATELY NOT ENFORCED HERE: whether the home's implementation is correct. That is what the
per-rule tests are for. This asks only "is there one of it".
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ACQ = REPO / "infrastructure" / "acquisition"
TESTS = REPO / "tests"

_JOINED_LITERALS = re.compile(r"[\"']\s*[\"']")          # "…" "…" (incl. across newlines) -> one string


def _normalize(src: str) -> str:
    """Collapse adjacent string literals + whitespace so a multi-line SQL string reads as one line."""
    return re.sub(r"\s+", " ", _JOINED_LITERALS.sub("", src))


RULES = [
    {
        "rule": "the benchmark district-membership predicate",
        "home": ACQ / "common" / "benchmark.py",
        "scope": sorted(ACQ.rglob("*.py")),
        # quotes around 'benchmark' are OPTIONAL: joining adjacent literals can consume the value's
        # own closing quote. `batch_district` within 300 chars keeps it specific — prose that merely
        # mentions batch_type won't trip it.
        "forbid": re.compile(r"batch_district\b.{0,300}?batch_type\s*=\s*'?benchmark", re.S),
        "why": "#621/#617 — five hand-maintained copies, one of which keyed the batch_00000 LITERAL "
               "and so would have silently lost a SECOND benchmark batch",
        "removed": {
            "stage7_execute._benchmark_district_ids": '''
    rows = session.execute(text(
        "SELECT DISTINCT bd.district_id FROM batch_district bd "
        "JOIN batch b ON b.batch_id = bd.batch_id "
        "WHERE b.batch_type = 'benchmark' AND bd.district_id = ANY(:d)"),
        {"d": list(district_ids)})''',
            "incorporate._is_benchmark_district": '''
        return bool(gs.execute(text(
            "SELECT 1 FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id "
            "WHERE b.batch_type = 'benchmark' AND bd.district_id = :d LIMIT 1"),
            {"d": district_id}).first())''',
            "backfill_receipts.load_benchmark_ids": '''
    rows = session.execute(text(
        "SELECT DISTINCT bd.district_id FROM batch_district bd "
        "JOIN batch b ON b.batch_id = bd.batch_id WHERE b.batch_type = 'benchmark'"))''',
            "server.IS_BENCHMARK_SQL": '''
IS_BENCHMARK_SQL = """EXISTS (SELECT 1 FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id
                              WHERE bd.district_id = {alias}.district_id
                                AND b.batch_type = 'benchmark')"""''',
        },
    },
    {
        "rule": "the dispatch_type read-path default",
        "home": ACQ / "common" / "benchmark.py",
        "scope": sorted(ACQ.rglob("*.py")),
        "forbid": re.compile(r"""dispatch_type["']\s*\)\s*or\s+\w*\.?DISPATCH_PRODUCTION"""),
        "why": "#650 — 8 inline copies across 4 files, INTRODUCED by this epic. The freeze refusal "
               "and the mode-stability gate are two of them and must never disagree about the same "
               "doc's effective type. Home: effective_dispatch_type / is_benchmark_dispatch",
        "removed": {
            "server.handoff_dispatch":
                'dispatch_type = payload.get("dispatch_type") or BM.DISPATCH_PRODUCTION   # #618',
            "server.dispatch view payload":
                '"dispatch_type": doc.get("dispatch_type") or BM.DISPATCH_PRODUCTION,',
            "stage6_dispatch.assert_dispatch_type_allowed":
                'if (package.get("dispatch_type") or BM.DISPATCH_PRODUCTION) == BM.DISPATCH_BENCHMARK:',
            "stage6_dispatch.insert_handoff_row":
                'dispatch_type=doc.get("dispatch_type") or BM.DISPATCH_PRODUCTION))',
            "handoff._identity":
                '"dispatch_type": package.get("dispatch_type") or DISPATCH_PRODUCTION}',
            "stage7_run._early_exit_enabled":
                'and (doc.get("dispatch_type") or BM.DISPATCH_PRODUCTION) != BM.DISPATCH_BENCHMARK',
        },
    },
    {
        "rule": "the redo_attempted composer default",
        "home": ACQ / "common" / "batch_types.py",
        "scope": sorted(ACQ.rglob("*.py")),
        "forbid": re.compile(r"redo_attempted\s*=\s*(True|False)\b"),
        "why": "#658 — two composers hardcoded the literal instead of calling "
               "default_redo_attempted(). They agree with the helper today; the drift risk is that "
               "nothing connects them to it. Deriving this lever from batch_type was rejected "
               "outright (it would re-run discovery over the FROZEN gt:// candidate sets)",
        "removed": {
            "stage7_execute.compose_followup_batch":
                'BSTORE.create_batch(s, c["doc"], batch_type="follow-up", redo_attempted=True, actor=actor)',
            "stage5_followup geo composer":
                'BSTORE.create_batch(s, doc, batch_type="follow-up", redo_attempted=True, actor=actor)',
        },
    },
    {
        "rule": "batch-scoped stage done-ness",
        "home": ACQ / "common" / "district_status.py",
        "scope": sorted(ACQ.rglob("*.py")),
        "forbid": re.compile(r"FROM state_event\b.{0,200}?batch_id\s*=\s*:", re.S | re.I),
        "why": "#647/#655 — Stage 2 hand-rolled a twin of dispatched_by_batch while Stages 3 and 4 "
               "shared it. Three near-simultaneous fixes, one shared helper used twice and one "
               "private copy. Home: dispatched_by_batch",
        "removed": {
            "stage2_discover.headless.status_for_batch": '''
            done_ids = [r[0] for r in con.execute(
                text("SELECT DISTINCT district_id FROM state_event WHERE stage = 2 "
                     "AND batch_id = :b AND district_id = ANY(:ids)"),
                {"b": batch["batch_id"], "ids": ids})]''',
        },
    },
    {
        "rule": "the precious `handoff` INSERT column list (test seeding)",
        "home": TESTS / "benchmark_seed.py",
        "scope": sorted(TESTS.glob("*.py")),
        "forbid": re.compile(r"INSERT INTO handoff\b", re.I),
        "why": "#661 — copied in five test files, two of which OMITTED dispatch_type and so leaned "
               "on a server_default that a fresh create_all() DB did not have until PR #641. That "
               "is the _PRECIOUS_ALTERS parity failure, reproduced in the suite meant to catch it",
        "removed": {
            "test_benchmark_predicate._seed_prov": '''
    s.execute(text(
        "INSERT INTO handoff (handoff_id, handoff_hash, created_at, created_by, status, path, "
        "dispatch_type, n_districts, n_reps, total_usd, cost_provenance, district_ids, council_ids) "
        "VALUES (:hid, :hh, 'now', 'zz', 'dispatched', '/zz/x.json', :dt, 1, 1, 0.0, 'zz', "
        "'[]', '[]')"), {"hid": f"handoff_{hh}_t", "hh": hh, "dt": dispatch_type})''',
            "test_extract_run_api._seed_handoff (omitted dispatch_type)": '''
    con.execute(text(
        "INSERT INTO handoff (handoff_hash, handoff_id, created_at, created_by, status, path, "
        "n_districts, n_reps, total_usd, cost_provenance, district_ids, council_ids) VALUES "
        "(:h, :hid, '2026-07-05T00:00:00Z', 'zz', :st, '/tmp/none.json', 1, 1, 0.0, 'test', "
        "CAST(:d AS json), CAST(:c AS json))"))''',
        },
    },
    {
        "rule": "the benchmark-provenance arm 1 SQL (handoff.dispatch_type)",
        "home": ACQ / "common" / "benchmark.py",
        "scope": sorted(ACQ.rglob("*.py")),
        # Anchored on FROM/JOIN <table>, which is what makes it SQL-specific. A bare table name is
        # not enough: `handoff` is ordinary vocabulary in this codebase's prose, and the first draft
        # fired on stage6_dispatch's operator error string. See `not_copies`.
        "forbid": re.compile(r"(?:FROM|JOIN)\s+handoff\b.{0,200}?dispatch_type\s*=\s*'benchmark", re.S),
        "why": "#619 — the write wall, the gate@8 queue and the request-execution guards all ask "
               "this; five hand-copies is how the MEMBERSHIP rule reached the state #617 cleaned up",
        "removed": {
            "a plausible hand-inline at a call site": '''
    rows = s.execute(text(
        "SELECT 1 FROM extraction e JOIN handoff h ON h.handoff_hash = e.handoff_hash "
        "WHERE h.dispatch_type = 'benchmark' AND e.district_id = :d"), {"d": did})''',
        },
        "not_copies": {
            "prose": "An explicit `dispatch_type='benchmark'` always passes: the Council Lab opt-in.",
            "operator error string":
                '''f"Deselect those records, or set dispatch_type='benchmark' to run this "''',
        },
    },
    {
        "rule": "the benchmark-provenance arm 2 SQL (capture.source)",
        "home": ACQ / "common" / "benchmark.py",
        "scope": sorted(ACQ.rglob("*.py")),
        "forbid": re.compile(r"(?:FROM|JOIN)\s+capture\b.{0,200}?source\s*=\s*'benchmark_gt", re.S),
        "why": "#619 — the arm that sees an injected rep inside a genuine production dispatch, which "
               "arm 1 structurally cannot. Referencing the CONSTANTS (BM.BENCHMARK_CAPTURE_SOURCE) "
               "is the sanctioned way to ask in Python; re-inlining the SQL is what can drift",
        "removed": {
            "a plausible hand-inline at a call site": '''
    rows = s.execute(text(
        "SELECT r.rec_key FROM record r JOIN capture c ON c.district_id = r.district_id "
        "AND c.hash = r.hash WHERE c.source = 'benchmark_gt'"))''',
        },
        "not_copies": {
            "dotted attr in prose": "(`capture.source='benchmark_gt'`), which is real and mixed "
                                    "after a #620 re-run",
        },
    },
]


@pytest.mark.parametrize("spec", RULES, ids=[r["rule"] for r in RULES])
def test_a_consolidated_rule_has_exactly_one_home(spec):
    """No file in `scope` other than `home` may re-spell the rule."""
    assert spec["home"].exists(), f"declared home is missing: {spec['home']}"
    # THIS file is exempt from every rule: it spells each pattern out by definition, and a detector
    # that flags its own declaration can never be satisfied.
    exempt = {spec["home"], Path(__file__).resolve()}
    offenders = [
        str(p.relative_to(REPO)) for p in spec["scope"]
        if p.resolve() not in exempt and spec["forbid"].search(_normalize(p.read_text(encoding="utf-8")))
    ]
    assert not offenders, (
        f"{spec['rule']} is re-spelled outside {spec['home'].relative_to(REPO)}:\n  "
        + "\n  ".join(offenders)
        + f"\n\nWhy this rule has one home: {spec['why']}\n"
        + "Call the shared helper. If the copy is genuinely a different rule, it needs a different "
          "name — not a second spelling of this one.")


@pytest.mark.parametrize(
    "rule,name", [(s["rule"], n) for s in RULES for n in sorted(s.get("removed", {}))],
    ids=[f"{s['rule']}::{n}" for s in RULES for n in sorted(s.get("removed", {}))])
def test_the_detector_catches_the_copies_that_actually_existed(rule, name):
    """A fitness function nobody has falsified is decoration.

    Every string here is a copy that was REALLY in this repo and was really removed — the four the
    epic consolidated, plus the ten it introduced and #650/#655/#658/#661 removed. Embedded as
    literals rather than fetched with `git show <ref>:<path>` on purpose: a ref lookup silently stops
    testing anything once the ref moves past the consolidation, and breaks in a shallow CI clone.

    This caught two real defects while the first detector was being written: a line-by-line scan
    missed the copies whose SQL spans adjacent string literals, and the literal-joining normalizer
    then ate the closing quote of `'benchmark'` where it abutted the enclosing string's quote."""
    spec = next(s for s in RULES if s["rule"] == rule)
    assert spec["forbid"].search(_normalize(spec["removed"][name])), (
        f"the detector for {rule!r} does not catch the known copy from {name} — it would not catch "
        f"a new one either")


@pytest.mark.parametrize(
    "rule,name", [(s["rule"], n) for s in RULES for n in sorted(s.get("not_copies", {}))],
    ids=[f"{s['rule']}::{n}" for s in RULES for n in sorted(s.get("not_copies", {}))])
def test_the_detector_does_not_fire_on_a_mere_mention(rule, name):
    """The other polarity, and the one that decides whether anyone keeps the guard. Every string here
    is verbatim from this codebase — a docstring, an operator error message, a dotted attribute in
    prose — and every one of them tripped an earlier draft of these patterns. A display string that
    MENTIONS the rule is not a second copy of it, and a detector that cries wolf gets disabled."""
    spec = next(s for s in RULES if s["rule"] == rule)
    assert not spec["forbid"].search(_normalize(spec["not_copies"][name])), (
        f"the detector for {rule!r} fires on {name}, which is a mention rather than a copy")


def test_every_rule_declares_a_falsification_corpus():
    """A row with no `removed` entries is an unfalsified detector, which is how a pattern that
    matches nothing passes forever. Adding a rule means producing at least one copy it must catch."""
    unfalsified = [s["rule"] for s in RULES if not s.get("removed")]
    assert not unfalsified, f"these rules have no falsification corpus: {unfalsified}"


def test_every_declared_home_actually_matches_its_own_pattern():
    """A row whose `forbid` pattern no longer matches its own home is a DEAD guard: the rule was
    renamed or rewritten and the detector silently stopped detecting anything. This is the failure
    mode a one-sided fitness function cannot see — it would keep passing forever.

    Both polarities, the discipline the epic's own predicate test established: prove the detector
    fires where the rule lives, not only that it stays silent everywhere else."""
    dead = [s["rule"] for s in RULES
            if not s["forbid"].search(_normalize(s["home"].read_text(encoding="utf-8")))]
    assert not dead, (
        f"these detectors no longer match their own home, so they guard nothing: {dead}. "
        f"The rule moved or was rewritten — update the pattern, or drop the row if the rule is gone.")


def test_the_declaration_covers_every_rule_common_claims_to_own():
    """A cheap completeness check on the DECLARATION itself: every module under `common/` whose
    docstring claims to be the one home for something should appear as a `home` here.

    Not a proof of completeness — a module can own several rules and declare one. It catches the
    specific omission this epic made: shipping a new consolidated rule in `common/` and giving it no
    guard at all, while a sibling rule right beside it had one."""
    claimants = {p for p in (ACQ / "common").glob("*.py")
                 if re.search(r"\bONE home\b|\bTHE (definition|`?\w+`? axis)\b",
                              p.read_text(encoding="utf-8")[:2000])}
    declared = {s["home"] for s in RULES}
    missing = sorted(str(p.relative_to(REPO)) for p in claimants - declared)
    assert not missing, (
        f"these common/ modules claim to be a single home but declare no one-home rule in RULES: "
        f"{missing}. Add a row (with a `forbid` pattern that matches the module itself), or soften "
        f"the docstring claim.")
