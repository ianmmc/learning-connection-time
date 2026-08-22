"""The spec ledger's own fitness functions.

#808 established the first one: the ledger must not silently lose content to YAML's duplicate-key
rule. The rest were added 2026-08-21 after a manual audit found things a comment had asked for but
nothing enforced — and the audit's own edits then REPRODUCED #808's bug (an insert next to an
existing `tests: []` created a duplicate key, and last-write-wins took the empty one). A rule that
lives only in a header comment is a rule that drifts; these are the same rules, executable.

What each class guards, and why it earned a test rather than a comment:

  TestNoDuplicateKeys      #808. A duplicate mapping key silently discards content.
  TestVocabulary           The header declared SIX status values and said "do not invent more".
                           Two more (`approved`, `in_progress`) crept back in anyway.
  TestEvidence             `status: tested` was claimed by 16 requirements that named no test.
                           NB the rule is ONE-DIRECTIONAL on purpose — see the class docstring.
  TestCrossReferences      REQ-257 was cited in the ledger AND in production code. No such
                           requirement exists; the real one is REQ-133, whose github_issue is #257.
                           An issue number was written as a REQ id and nothing noticed.
  TestTestReferencesResolve  528 references, all sound at the time of writing, with nothing
                           stopping a rename from orphaning them.
  TestFreshness            last_updated said 2026-07-16 while requirements carried later dates.
"""
import pathlib
import re

import pytest
import yaml

LEDGER = pathlib.Path(__file__).resolve().parents[1] / "docs" / "REQUIREMENTS.yaml"
REPO = LEDGER.parents[1]
TESTS_DIR = pathlib.Path(__file__).resolve().parent

STATUSES = {"proposed", "accepted", "tested", "superseded", "retired"}
TYPES = {"functional", "non-functional", "constraint", "process", "principle", "architectural"}
PRIORITIES = {"must", "should"}
REQUIRED = ("id", "description", "type", "priority", "status", "acceptance_criteria")

REQ_ID_RE = re.compile(r"\bREQ-(\d{3})\b")


class _DuplicateKey(Exception):
    pass


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that REJECTS duplicate mapping keys instead of last-write-wins."""


def _no_dupes(loader, node, deep=False):
    seen = set()
    for k, _ in node.value:
        key = loader.construct_object(k, deep=deep)
        if key in seen:
            raise _DuplicateKey(f"duplicate key {key!r} at line {k.start_mark.line + 1}")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dupes)


@pytest.fixture(scope="module")
def ledger():
    return yaml.safe_load(LEDGER.read_text())


@pytest.fixture(scope="module")
def reqs(ledger):
    return ledger["requirements"]


def _listify(v):
    if not v:
        return []
    return v if isinstance(v, list) else [v]


def _parse_ref(ref):
    """A tests: entry -> (path, [symbols]). Trailing prose after '(' or an em dash is a
    description, not part of the path — the ledger uses both forms."""
    s = re.sub(r"\s*[(—].*$", "", str(ref)).strip()
    parts = [p.strip() for p in s.split("::")]
    return parts[0], [p.strip() for p in parts[1:] if p.strip()]


class TestNoDuplicateKeys:
    def test_ledger_has_no_duplicate_mapping_keys(self):
        """#808 — and the 2026-08-21 audit re-created this exact bug while editing, which is the
        best argument there is for keeping it executable."""
        try:
            yaml.load(LEDGER.read_text(), Loader=_StrictLoader)
        except _DuplicateKey as e:
            pytest.fail(f"REQUIREMENTS.yaml has a duplicate key — content is being silently "
                        f"discarded by yaml.safe_load: {e}")

    def test_req174_notes_survive_parse(self, reqs):
        """The specific casualty: REQ-174's #793 narrative must be reachable THROUGH a parser, not
        just present as raw text."""
        r = next(x for x in reqs if x["id"] == "REQ-174")
        assert "#793" in str(r.get("notes", "")), "REQ-174's notes lost the #793 narrative again"


class TestVocabulary:
    """The header declares the closed sets. This makes 'do not invent more' enforceable."""

    def test_status_values_are_the_declared_five(self, reqs):
        bad = {r["id"]: r["status"] for r in reqs if r["status"] not in STATUSES}
        assert not bad, (f"status outside the declared vocabulary {sorted(STATUSES)}: {bad}. "
                         "`approved` and `in_progress` were exactly this, twice.")

    def test_type_values_are_the_declared_set(self, reqs):
        bad = {r["id"]: r["type"] for r in reqs if r["type"] not in TYPES}
        assert not bad, f"type outside the declared vocabulary {sorted(TYPES)}: {bad}"

    def test_priority_values_are_closed(self, reqs):
        bad = {r["id"]: r["priority"] for r in reqs if r["priority"] not in PRIORITIES}
        assert not bad, f"priority outside {sorted(PRIORITIES)}: {bad}"

    def test_every_requirement_carries_the_required_fields(self, reqs):
        bad = {r.get("id", "<no id>"): [k for k in REQUIRED if not r.get(k)] for r in reqs}
        bad = {k: v for k, v in bad.items() if v}
        assert not bad, f"missing required fields: {bad}"

    def test_ids_are_unique_and_contiguous(self, reqs):
        nums = [int(r["id"].split("-")[1]) for r in reqs]
        dupes = {n for n in nums if nums.count(n) > 1}
        assert not dupes, f"duplicate REQ ids: {sorted(dupes)}"
        missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
        assert not missing, (f"gaps in the REQ sequence: {missing}. A gap is usually a lost entry — "
                             "retire or supersede in place, never delete.")


class TestEvidence:
    """`status: tested` must be CITEABLE.

    ONE-DIRECTIONAL BY DESIGN. `tested` implies evidence; carrying evidence does NOT imply `tested`.
    REQ-169 is mid-build on an open epic (#617) and legitimately has tests for the finished half — a
    two-way rule would relabel it as done, which is the mistake this rule exists to prevent.
    """

    def test_tested_requirements_cite_evidence(self, reqs):
        bad = [r["id"] for r in reqs
               if r["status"] == "tested"
               and not r.get("tests") and not r.get("enforced_by")
               and r["type"] != "principle"]
        assert not bad, (f"status 'tested' with no tests: and no enforced_by: {bad}. Either cite "
                         "the evidence, delegate with enforced_by (the umbrella pattern), or drop "
                         "the status to 'accepted'.")

    def test_a_principle_is_exempt_but_says_how_it_is_realized(self, reqs):
        """A commandment is not falsifiable by a unit test, but it must still point somewhere."""
        bad = [r["id"] for r in reqs
               if r["type"] == "principle" and r["status"] == "tested"
               and not r.get("enforced_by") and not r.get("tests") and not r.get("notes")]
        assert not bad, f"principle with no enforced_by, tests, or explanatory notes: {bad}"

    def test_superseded_carries_a_forwarding_address(self, reqs):
        bad = [r["id"] for r in reqs if r["status"] == "superseded" and not r.get("superseded_by")]
        assert not bad, f"superseded without superseded_by (the forwarding address): {bad}"

    def test_retired_carries_a_reason(self, reqs):
        bad = [r["id"] for r in reqs if r["status"] == "retired" and not r.get("retired_reason")]
        assert not bad, f"retired without retired_reason: {bad}"


class TestCrossReferences:
    """REQ-257 was cited in the ledger and in server.py. There is no REQ-257."""

    def test_no_requirement_cites_a_nonexistent_req(self, reqs):
        known = {r["id"] for r in reqs}
        bad = {}
        for r in reqs:
            for cited in REQ_ID_RE.findall(yaml.safe_dump(r, allow_unicode=True)):
                rid = f"REQ-{cited}"
                if rid not in known:
                    bad.setdefault(r["id"], set()).add(rid)
        assert not bad, (f"ledger cites REQ ids that do not exist: "
                         f"{ {k: sorted(v) for k, v in bad.items()} }. The REQ-257 case was an "
                         "ISSUE number written as a REQ id.")

    def test_production_code_cites_no_nonexistent_req(self, reqs):
        """The REQ-257 typo reached server.py. Source comments are a real citation surface."""
        known = {r["id"] for r in reqs}
        bad = {}
        for path in (REPO / "infrastructure").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for cited in set(REQ_ID_RE.findall(path.read_text(errors="ignore"))):
                rid = f"REQ-{cited}"
                if rid not in known:
                    bad.setdefault(str(path.relative_to(REPO)), set()).add(rid)
        assert not bad, (f"production code cites REQ ids absent from the ledger: "
                         f"{ {k: sorted(v) for k, v in bad.items()} }")

    def test_enforced_by_req_ids_exist(self, reqs):
        """enforced_by mixes REQ ids, test paths and tool names; only the REQ ids are checkable."""
        known = {r["id"] for r in reqs}
        bad = {r["id"]: [e for e in _listify(r.get("enforced_by"))
                         if str(e).startswith("REQ-") and str(e) not in known]
               for r in reqs}
        bad = {k: v for k, v in bad.items() if v}
        assert not bad, f"enforced_by names REQ ids that do not exist: {bad}"

    def test_superseded_by_req_ids_exist(self, reqs):
        known = {r["id"] for r in reqs}
        bad = {r["id"]: [e for e in _listify(r.get("superseded_by")) if str(e) not in known]
               for r in reqs}
        bad = {k: v for k, v in bad.items() if v}
        assert not bad, f"superseded_by names REQ ids that do not exist: {bad}"


class TestTestReferencesResolve:
    """A citation that no longer names a real test is a `tested` claim with nothing behind it.

    Symbol lookup is deliberately two-stage. Strict file-local matching alone produces FALSE
    failures on two legitimate forms the ledger already uses: an INHERITED test (REQ-027 cites
    tests/test_california_integration.py::TestDistrictCrosswalk::test_crosswalk_has_entries, which
    pytest collects fine — the method is defined on the SEACrosswalkTests base in another module),
    and a GLOB (REQ-175 cites test_822_*). So: require the file, then require the symbol to be
    defined in that file OR anywhere under tests/. That still catches the real risk — a test
    renamed or deleted out from under a citation — without failing on inheritance.
    """

    @staticmethod
    def _all_test_source():
        return "\n".join(p.read_text(errors="ignore") for p in TESTS_DIR.rglob("*.py"))

    def test_every_cited_test_file_exists(self, reqs):
        bad = {}
        for r in reqs:
            for ref in _listify(r.get("tests")):
                path, _ = _parse_ref(ref)
                if path.endswith((".py", ".mjs", ".js")) and not (REPO / path).exists():
                    bad.setdefault(r["id"], []).append(path)
        assert not bad, f"cited test files that do not exist: {bad}"

    def test_every_cited_symbol_exists(self, reqs):
        corpus = self._all_test_source()
        cache = {}
        bad = {}
        for r in reqs:
            for ref in _listify(r.get("tests")):
                path, syms = _parse_ref(ref)
                if not path.endswith((".py", ".mjs", ".js")):
                    continue
                fp = REPO / path
                if not fp.exists():
                    continue                      # covered by the file test above
                body = cache.setdefault(path, fp.read_text(errors="ignore"))
                for sym in syms:
                    stem = sym.rstrip("*")
                    pat = rf"(def|class)\s+{re.escape(stem)}"
                    if not sym.endswith("*"):
                        pat += r"\b"
                    if re.search(pat, body) or re.search(pat, corpus):
                        continue
                    bad.setdefault(r["id"], []).append(ref)
                    break
        assert not bad, (f"cited test symbols that no longer exist: {bad}. A rename orphaned a "
                         "citation — update the ledger or restore the test.")


class TestFreshness:
    """last_updated read 2026-07-16 while requirements carried August dates.

    Compared against the ledger's OWN newest `updated:` rather than against git: self-contained,
    no subprocess, and it cannot go flaky on an uncommitted working tree.
    """

    def test_last_updated_is_not_behind_the_newest_requirement(self, ledger, reqs):
        file_stamp = str(ledger["last_updated"])[:10]
        newest = max((str(r.get("updated") or r.get("created") or "")[:10] for r in reqs),
                     default="")
        assert newest <= file_stamp, (
            f"last_updated ({file_stamp}) is older than the newest requirement's updated date "
            f"({newest}). Bump the file header when you touch an entry.")
