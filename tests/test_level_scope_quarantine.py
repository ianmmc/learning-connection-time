"""#1017 phase-1 quarantine of teachers_elementary / teachers_secondary (REQ-190; PR #1024 review #1025-#1032).

The caveat has ONE home (infrastructure/utilities/lct_scopes.py); every presenter labels through it; the
token rides on every level-scope row so the stored data and the exports carry the caveat, not only the
reports; the QA report neither ranks nor outlier-lists the quarantined scopes, and does not count the
token as a district QA note. DB-free: the calc's generate_qa_report and the sign-off preview's main() are
driven with in-memory frames / a monkeypatched sample(); the MCP server (its `mcp` dependency is not
installed in the test env) is pinned by source.
"""
import ast
import re
from pathlib import Path

import pandas as pd

from infrastructure.scripts.analyze import calculate_lct_variants as clv
from infrastructure.scripts.analyze import per_grade_lct_sample as pgls
from infrastructure.utilities import lct_scopes as ls

REPO = Path(__file__).resolve().parents[1]
HOME = REPO / "infrastructure/utilities/lct_scopes.py"
PRESENTERS = [
    REPO / "infrastructure/scripts/analyze/calculate_lct_variants.py",
    REPO / "infrastructure/scripts/analyze/per_grade_lct_sample.py",
    REPO / "infrastructure/database/mcp_server_postgres.py",
]
MCP = PRESENTERS[2]


def _row(scope, lct, notes="", did="d1"):
    return {"district_id": did, "district_name": did.upper(), "state": "XX",
            "staff_scope": scope, "lct_value": lct, "level_lct_notes": notes}


def _summary(**means):
    return pd.DataFrame([{"staff_scope": s, "districts": 1, "mean": m, "median": m, "min": m, "max": m}
                         for s, m in means.items()])


def _report(rows, summary=None):
    df = pd.DataFrame(rows)
    return clv.generate_qa_report(df, df, summary if summary is not None else _summary(teachers_only=20.0),
                                  "ts", "2024-25")


class TestOneHome:

    def test_calc_re_exports_the_home_objects(self):
        assert clv.QUARANTINED_SCOPES is ls.QUARANTINED_SCOPES
        assert clv.LEVEL_SPLIT_CAVEAT is ls.LEVEL_SPLIT_CAVEAT
        assert set(ls.TEACHER_LEVEL_SCOPES) == {"teachers_elementary", "teachers_secondary"}
        assert ls.quarantine_caption("teachers_elementary") == ls.LEVEL_SPLIT_CAVEAT
        assert ls.quarantine_caption("teachers_only") is None
        assert "#1017" in ls.LEVEL_SPLIT_CAVEAT

    def test_no_production_module_spells_the_caveat_itself(self):
        """A second spelling is the drift: the caveat text appears in exactly one infrastructure module."""
        needle = "follows state practice (#1017)"
        hits = sorted(str(p.relative_to(REPO)) for p in (REPO / "infrastructure").rglob("*.py")
                      if needle in p.read_text(encoding="utf-8"))
        assert hits == [str(HOME.relative_to(REPO))], hits

    def test_every_presenter_imports_the_home(self):
        for path in PRESENTERS:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            sources = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            assert "infrastructure.utilities.lct_scopes" in sources, path.name


class TestToken:

    def test_token_only_on_quarantined_scopes(self):
        assert ls.with_quarantine_token("teachers_elementary", "") == ls.QUARANTINE_TOKEN
        assert ls.with_quarantine_token("teachers_secondary", None) == ls.QUARANTINE_TOKEN
        assert ls.with_quarantine_token("teachers_only", "") == ""
        assert ls.with_quarantine_token("teachers_only", "WARN_LCT_LOW") == "WARN_LCT_LOW"

    def test_token_leads_the_note_and_is_idempotent(self):
        once = ls.with_quarantine_token("teachers_elementary", "Secondary enrollment but no secondary teachers")
        assert once == f"{ls.QUARANTINE_TOKEN}; Secondary enrollment but no secondary teachers"
        assert ls.with_quarantine_token("teachers_elementary", once) == once
        assert ls.with_quarantine_token("teachers_elementary", ls.QUARANTINE_TOKEN) == ls.QUARANTINE_TOKEN

    def test_data_quality_notes_strips_only_the_token(self):
        assert ls.data_quality_notes(ls.QUARANTINE_TOKEN) == ""
        assert ls.data_quality_notes(f"{ls.QUARANTINE_TOKEN}; WARN_LCT_LOW") == "WARN_LCT_LOW"
        assert ls.data_quality_notes("ERR_VOLATILE; WARN_LCT_LOW") == "ERR_VOLATILE; WARN_LCT_LOW"
        assert ls.data_quality_notes(None) == ""

    def test_safeguard_flags_append_after_the_token(self):
        """apply_data_safeguards joins its flags onto the existing note; the token must stay at the head."""
        df = pd.DataFrame([{**_row("teachers_elementary", 1.0, ls.QUARANTINE_TOKEN),
                            "staff_count": 10.0, "enrollment": 1000, "enrollment_type": "elementary_k5"}])
        out, counts = clv.apply_data_safeguards(df)
        note = out.loc[0, "level_lct_notes"]
        assert note.startswith(ls.QUARANTINE_TOKEN + "; ")
        assert "WARN_LCT_LOW" in note
        assert ls.QUARANTINE_TOKEN not in counts   # not a safeguard (REQ-012 keeps its seven)


class TestQaReport:

    def test_scope_summary_entry_carries_the_caveat(self):
        r = _report([_row("teachers_only", 20.0)],
                    _summary(teachers_only=20.0, teachers_elementary=30.0, teachers_secondary=15.0))
        assert r["scope_summary"]["teachers_elementary"]["caveat"] == ls.LEVEL_SPLIT_CAVEAT
        assert r["scope_summary"]["teachers_secondary"]["caveat"] == ls.LEVEL_SPLIT_CAVEAT
        assert "caveat" not in r["scope_summary"]["teachers_only"]

    def test_outliers_exclude_the_quarantined_scopes(self):
        rows = [_row("teachers_elementary", 1.0, did="lvl"), _row("teachers_secondary", 300.0, did="lvl2"),
                _row("teachers_only", 1.0, did="base")]
        r = _report(rows)
        scopes = {o["scope"] for o in r["outliers"]}
        assert scopes == {"teachers_only"}, r["outliers"]

    def test_districts_with_notes_does_not_count_the_token(self):
        r = _report([_row("teachers_elementary", 20.0, ls.QUARANTINE_TOKEN, did="a"),
                     _row("teachers_only", 20.0, "", did="a")])
        assert r["data_quality"]["districts_with_qa_notes"] == 0
        r = _report([_row("teachers_elementary", 20.0, f"{ls.QUARANTINE_TOKEN}; WARN_LCT_LOW", did="a")])
        assert r["data_quality"]["districts_with_qa_notes"] == 1


class TestSignOffPreview:

    def test_caveat_prints_above_the_table_and_marks_the_lct_columns(self, monkeypatch, capsys):
        row = {"district_id": "0100810", "name": "Coffee County", "state": "AL",
               "legacy_sec_min": 437, "legacy_source": "x", "per_grade_sec_min": 437, "source": "per_grade_bell",
               "legacy_sec_lct": 21.71, "per_grade_sec_lct": 21.71, "denom_refreshed": False}
        monkeypatch.setattr(pgls, "sample", lambda limit=None: [row])
        assert pgls.main(argv=[]) == 0
        lines = capsys.readouterr().out.splitlines()
        caveat_at = next(i for i, l in enumerate(lines) if l.startswith("[Q]") and ls.LEVEL_SPLIT_CAVEAT in l)
        header_at = next(i for i, l in enumerate(lines) if "legacy_lct[Q]" in l and "pg_lct[Q]" in l)
        assert caveat_at < header_at
        assert any("0100810" in l and "21.71" in l for l in lines[header_at + 1:])


class TestMcpServer:
    """Pinned by source: the `mcp` package is not installed in the test environment."""

    def test_description_stops_advertising_the_level_scopes_as_ordinary(self):
        text = MCP.read_text(encoding="utf-8")
        desc = re.search(r'"description": "LCT scope served here: ([^"]*)"', text)
        assert desc, "query_lct_summary scope description not found"
        assert "QUARANTINED" in desc.group(1)
        assert not re.search(r'"description": "LCT scope \(teachers_only, teachers_elementary', text)

    def test_summary_guards_with_the_caption_before_querying(self):
        text = MCP.read_text(encoding="utf-8")
        assert text.index("caveat = quarantine_caption(scope)") < text.index(
            "get_lct_summary_by_scope(session, scope, year)")
