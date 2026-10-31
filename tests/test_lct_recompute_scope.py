"""#628: the LCT recompute can be scoped to a few districts (--districts) and can run dry (--dry-run).

DB-free. The honest end-to-end evidence (full run vs scoped run on a scratch DB, row diff) is a
measurement recorded on the issue branch; these tests pin the pieces that make it true:

- argument handling (`parse_district_ids`, `build_parser`),
- the scoping logic (`scope_staff_records`, `lct_clear_criteria` — the delete's WHERE clause is the
  whole "every other district stays byte-identical" guarantee),
- the dry-run wiring (`main(["--dry-run"])` touches no write path and tracks no run).
"""
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from sqlalchemy.dialects import postgresql

from infrastructure.scripts.analyze import calculate_lct_variants as clv


def _sql(criteria):
    return [str(c.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
            for c in criteria]


class TestParseDistrictIds:
    def test_space_and_comma_separated_are_equivalent(self):
        assert clv.parse_district_ids(["0600153", "3600049,4200018"]) == ["0600153", "3600049", "4200018"]

    def test_dedupes_preserving_first_seen_order(self):
        assert clv.parse_district_ids(["b1", "a1", "b1"]) == ["b1", "a1"]

    def test_leading_zeros_survive(self):
        # NCES ids are strings; an int round-trip would turn 0600153 into 600153 and match nothing
        assert clv.parse_district_ids(["0600153"]) == ["0600153"]

    @pytest.mark.parametrize("raw", [[], [""], [" , "]])
    def test_empty_is_an_error_not_a_silent_full_run(self, raw):
        with pytest.raises(ValueError, match="at least one"):
            clv.parse_district_ids(raw)

    @pytest.mark.parametrize("bad", ["06 00153", "06;DROP", "12345678901", "a/b"])
    def test_malformed_id_is_rejected(self, bad):
        with pytest.raises(ValueError, match="not a valid district id"):
            clv.parse_district_ids([bad])


class TestParser:
    def test_defaults_are_the_full_writing_run(self):
        a = clv.build_parser().parse_args([])
        assert a.districts is None and a.dry_run is False

    def test_districts_flag_collects_ids(self):
        a = clv.build_parser().parse_args(["--districts", "0600153", "3600049", "--dry-run"])
        assert a.districts == ["0600153", "3600049"] and a.dry_run is True

    def test_districts_flag_without_ids_is_a_usage_error(self):
        with pytest.raises(SystemExit):
            clv.build_parser().parse_args(["--districts"])


class TestScopeStaffRecords:
    STAFF = {"d1": ("r1", "2024-25"), "d2": ("r2", "2024-25"), "d3": ("r3", "2024-25"),
             "ss": ("rss", "2024-25")}

    def test_none_is_the_full_corpus_minus_shared_service(self):
        assert clv.scope_staff_records(self.STAFF, {"ss"}, None) == ["r1", "r2", "r3"]

    def test_scope_keeps_only_the_named_districts_in_corpus_order(self):
        assert clv.scope_staff_records(self.STAFF, {"ss"}, ["d3", "d1"]) == ["r1", "r3"]

    def test_scope_cannot_resurrect_a_shared_service_entity(self):
        # a scoped run must give exactly the rows a full run gives that district: none
        assert clv.scope_staff_records(self.STAFF, {"ss"}, ["ss", "d2"]) == ["r2"]

    def test_unknown_ids_select_nothing(self):
        assert clv.scope_staff_records(self.STAFF, set(), ["zz"]) == []


class TestClearCriteria:
    def test_full_blended_clears_everything(self):
        assert clv.lct_clear_criteria() == []

    def test_target_year_clears_only_that_year_issue_297(self):
        assert _sql(clv.lct_clear_criteria(year="2023-24")) == ["lct_calculations.year = '2023-24'"]

    def test_scoped_blended_deletes_only_the_named_districts_across_all_years(self):
        # blended rows carry mixed staff_years, so the district — not the year — is the key
        assert _sql(clv.lct_clear_criteria(district_ids=["d1", "d2"])) == [
            "lct_calculations.district_id IN ('d1', 'd2')"]

    def test_scoped_target_year_is_the_intersection(self):
        assert _sql(clv.lct_clear_criteria(year="2023-24", district_ids=["d1"])) == [
            "lct_calculations.year = '2023-24'", "lct_calculations.district_id IN ('d1')"]

    def test_run_id_still_wins_over_year(self):
        assert _sql(clv.lct_clear_criteria(run_id="R", year="2023-24")) == ["lct_calculations.run_id = 'R'"]

    def test_empty_scope_is_refused_rather_than_widening_to_a_full_clear(self):
        # [] is falsy: `if district_ids:` would delete the WHOLE table. Never.
        with pytest.raises(ValueError, match="empty"):
            clv.lct_clear_criteria(district_ids=[])

    def test_clear_applies_the_criteria_to_the_delete(self):
        session = MagicMock()
        q = session.query.return_value
        q.filter.return_value.delete.return_value = 7
        assert clv.clear_lct_calculations(session, district_ids=["d1"]) == 7
        (clause,), _ = q.filter.call_args
        assert "district_id IN ('d1')" in _sql([clause])[0]

    def test_clear_with_no_criteria_deletes_the_unfiltered_table(self):
        session = MagicMock()
        session.query.return_value.delete.return_value = 3
        assert clv.clear_lct_calculations(session) == 3
        session.query.return_value.filter.assert_not_called()


class TestResolveOutputDir:
    def test_explicit_dir_always_wins(self, tmp_path):
        assert clv.resolve_output_dir(tmp_path, partial=True) == tmp_path
        assert clv.resolve_output_dir(tmp_path, partial=False) == tmp_path

    def test_full_run_defaults_to_the_corpus_directory(self):
        assert clv.resolve_output_dir(None, partial=False).name == "lct-calculations"

    def test_scoped_or_dry_run_default_away_from_the_corpus_report_directory(self):
        # README/METHODOLOGY point at lct_qa_report_*.json there as the CURRENT corpus-wide report
        d = clv.resolve_output_dir(None, partial=True)
        assert d.name == "partial" and d.parent.name == "lct-calculations"


class TestExportFrameFromRecords:
    """The dry-run frame must equal what a real run reads BACK from the table: values pass through the
    column types they would be stored in (lct_value NUMERIC(10,4), instructional_staff NUMERIC(10,2))."""

    REC = {"district_id": "d1", "district_name": "D One", "state": "CA", "staff_scope": "teachers_only",
           "lct_value": 18.123456, "instructional_minutes": 360, "instructional_minutes_source": "bell_schedule",
           "instructional_minutes_year": "2024-25", "staff_count": 249.999, "staff_source": "nces",
           "staff_year": "2024-25", "enrollment": 5000, "enrollment_type": "k12", "level_lct_notes": None}

    def test_numeric_columns_are_quantized_like_the_database(self):
        df = clv.export_frame_from_records([self.REC])
        assert df.loc[0, "lct_value"] == 18.1235
        assert df.loc[0, "staff_count"] == 250.0

    def test_half_up_like_postgres_not_bankers(self):
        df = clv.export_frame_from_records([{**self.REC, "lct_value": 0.00005, "staff_count": 0.125}])
        assert df.loc[0, "lct_value"] == 0.0001 and df.loc[0, "staff_count"] == 0.13

    def test_missing_notes_become_empty_string_like_the_db_export(self):
        assert clv.export_frame_from_records([self.REC]).loc[0, "level_lct_notes"] == ""

    def test_nan_passes_through_like_the_nan_numeric_the_writer_stores(self):
        df = clv.export_frame_from_records([{**self.REC, "lct_value": float("nan")}])
        assert pd.isna(df.loc[0, "lct_value"])

    def test_same_columns_as_the_database_export(self):
        assert list(clv.export_frame_from_records([self.REC]).columns) == clv.EXPORT_COLUMNS


class TestDryRunTouchesNoWritePath:
    """main(['--dry-run']) with a stubbed compute: the session must see no add/delete/commit-bearing
    call, no run is started, and output lands only in --output-dir."""

    def _frame(self):
        rows = []
        for did, name in (("d1", "One"), ("d2", "Two")):
            for scope, staff in (("teachers_only", 50.0), ("teachers_core", 55.0), ("instructional", 70.0),
                                 ("instructional_plus_support", 80.0), ("all", 90.0)):
                rows.append({"district_id": did, "district_name": name, "state": "CA", "staff_scope": scope,
                             "lct_value": 360 * staff / 1000, "instructional_minutes": 360,
                             "instructional_minutes_source": "bell_schedule",
                             "instructional_minutes_year": "2024-25", "staff_count": staff,
                             "staff_source": "nces", "staff_year": "2024-25", "enrollment": 1000,
                             "enrollment_type": "k12", "enrollment_year": "2024-25", "level_lct_notes": ""})
        return pd.DataFrame(rows)

    @pytest.fixture
    def wired(self, monkeypatch):
        session = MagicMock()
        @contextmanager
        def scope():
            yield session
        monkeypatch.setattr(clv, "session_scope", scope)
        monkeypatch.setattr(clv, "calculate_all_variants",
                            lambda *a, **k: (self._frame(), "2024-25", "2024-25"))
        monkeypatch.setattr(clv, "find_unknown_districts", lambda s, ids: [])
        run = MagicMock(run_id="RUN1")
        start_run = MagicMock(return_value=run)
        monkeypatch.setattr(clv.CalculationRun, "start_run", start_run)
        write = MagicMock()
        monkeypatch.setattr(clv, "write_calculations_to_db", write)
        clear = MagicMock(return_value=0)
        monkeypatch.setattr(clv, "clear_lct_calculations", clear)
        return SimpleNamespace(session=session, start_run=start_run, write=write, clear=clear)

    def test_dry_run_writes_nothing_and_tracks_nothing(self, wired, tmp_path):
        clv.main(["--dry-run", "--output-dir", str(tmp_path)])
        wired.write.assert_not_called()
        wired.clear.assert_not_called()
        wired.start_run.assert_not_called()
        wired.session.add.assert_not_called()
        wired.session.delete.assert_not_called()
        # the guarantee does not rest on the absence of calls alone: the transaction is read-only
        executed = [str(c.args[0]) for c in wired.session.execute.call_args_list]
        assert any("READ ONLY" in e for e in executed)

    def test_dry_run_still_emits_the_report_files_in_output_dir_only(self, wired, tmp_path):
        clv.main(["--dry-run", "--output-dir", str(tmp_path)])
        names = sorted(p.name for p in tmp_path.iterdir())
        for prefix in ("lct_all_variants_", "lct_variants_summary_", "lct_variants_by_state_",
                       "lct_variants_report_", "lct_qa_report_"):
            assert any(n.startswith(prefix) for n in names), prefix
        qa = json.loads(next(p for p in tmp_path.iterdir() if p.name.startswith("lct_qa_report_")).read_text())
        assert qa["metadata"]["dry_run"] is True
        assert qa["data_quality"]["total_calculations"] == 10

    def test_dry_run_outputs_are_tagged_so_a_glob_for_the_corpus_report_cannot_pick_them_up(self, wired, tmp_path):
        clv.main(["--dry-run", "--output-dir", str(tmp_path)])
        assert all("dryrun_" in p.name for p in tmp_path.iterdir() if p.suffix in (".csv", ".txt", ".json"))

    @pytest.fixture
    def scoped_wired(self, wired, monkeypatch):
        # export_lct_from_db reads the table back; stand in with the frame a real write would give
        frame = clv.export_frame_from_records(clv.db_records(self._frame(), keep_numeric_nan=True))
        monkeypatch.setattr(clv, "export_lct_from_db", lambda s, run_id, out, ts, ys="":
                            clv._write_export_csvs(frame.copy(), out, ts, ys))
        wired.write.return_value = 10
        return wired

    def test_scoped_run_clears_and_writes_only_the_scope_under_its_own_run_type(self, scoped_wired, tmp_path):
        clv.main(["--districts", "d1,d2", "--output-dir", str(tmp_path)])
        _, kw = scoped_wired.clear.call_args
        assert kw["district_ids"] == ["d1", "d2"]
        scoped_wired.write.assert_called_once()
        assert scoped_wired.start_run.call_args.kwargs["run_type"] == "scoped"

    def test_full_run_is_still_a_full_run(self, scoped_wired, tmp_path):
        clv.main(["--output-dir", str(tmp_path)])
        _, kw = scoped_wired.clear.call_args
        assert kw["district_ids"] is None
        assert scoped_wired.start_run.call_args.kwargs["run_type"] == "full"

    def test_scoped_outputs_are_tagged_and_the_qa_report_says_it_is_partial(self, scoped_wired, tmp_path):
        clv.main(["--districts", "d1", "d2", "--no-track", "--output-dir", str(tmp_path)])
        assert all("scoped_" in p.name for p in tmp_path.iterdir() if p.suffix in (".csv", ".txt", ".json"))
        qa = json.loads(next(p for p in tmp_path.iterdir() if p.name.startswith("lct_qa_report_")).read_text())
        assert qa["metadata"]["scope"] == {"districts": ["d1", "d2"]}

    def test_unknown_district_ids_abort_before_anything_is_computed_or_written(self, wired, monkeypatch, tmp_path):
        monkeypatch.setattr(clv, "find_unknown_districts", lambda s, ids: ["zz"])
        with pytest.raises(SystemExit) as e:
            clv.main(["--districts", "zz", "--output-dir", str(tmp_path)])
        assert e.value.code == 2
        wired.write.assert_not_called()
        wired.clear.assert_not_called()


class TestEmptyScopedRunStillClears:
    """#1013: a scoped run in which no requested district yields rows must still delete their stale rows —
    a full run would leave them none."""

    def test_scoped_empty_result_clears_the_requested_districts_then_exits(self, monkeypatch, tmp_path):
        session = MagicMock()
        @contextmanager
        def scope():
            yield session
        monkeypatch.setattr(clv, "session_scope", scope)
        monkeypatch.setattr(clv, "calculate_all_variants", lambda *a, **k: (pd.DataFrame(), "2024-25", "2024-25"))
        monkeypatch.setattr(clv, "find_unknown_districts", lambda s, ids: [])
        monkeypatch.setattr(clv.CalculationRun, "start_run", MagicMock(return_value=MagicMock(run_id="R")))
        clear = MagicMock(return_value=5)
        monkeypatch.setattr(clv, "clear_lct_calculations", clear)
        with pytest.raises(SystemExit) as e:
            clv.main(["--districts", "d1", "--output-dir", str(tmp_path)])
        assert e.value.code == 1
        assert clear.call_args.kwargs["district_ids"] == ["d1"]
        session.commit.assert_called()

    @pytest.mark.parametrize("argv", [["--dry-run", "--districts", "d1"], []])
    def test_dry_run_and_full_run_do_not_clear_on_an_empty_result(self, monkeypatch, tmp_path, argv):
        session = MagicMock()
        @contextmanager
        def scope():
            yield session
        monkeypatch.setattr(clv, "session_scope", scope)
        monkeypatch.setattr(clv, "calculate_all_variants", lambda *a, **k: (pd.DataFrame(), "2024-25", "2024-25"))
        monkeypatch.setattr(clv, "find_unknown_districts", lambda s, ids: [])
        monkeypatch.setattr(clv.CalculationRun, "start_run", MagicMock(return_value=MagicMock(run_id="R")))
        clear = MagicMock(return_value=5)
        monkeypatch.setattr(clv, "clear_lct_calculations", clear)
        with pytest.raises(SystemExit):
            clv.main([*argv, "--output-dir", str(tmp_path)])
        clear.assert_not_called()


class TestSpedScopeMinutes:
    """#1009: the SPED scopes window the baseline's ratio years at read time, as staff/enrollment are."""
    RATIO = ["2024-25", "2024-25", "2024-25", "2023-24", "2024-25"]   # staff, enrollment, estimate, ratio years

    def test_bell_year_out_of_window_only_with_the_ratio_years_falls_back_to_statutory(self, monkeypatch):
        statutory = (360, "state_requirement", None)
        monkeypatch.setattr(clv, "get_statutory_minutes", lambda s, st, band: statutory)
        base = (410, "bell_schedule", "2026-27")   # the base scopes keep it: 2024-25..2026-27 is span 2
        assert clv.sped_scope_minutes(None, "CA", base, self.RATIO) == statutory

    def test_coherent_bell_year_is_kept(self, monkeypatch):
        monkeypatch.setattr(clv, "get_statutory_minutes", lambda *a: pytest.fail("no fallback expected"))
        base = (410, "bell_schedule", "2025-26")
        assert clv.sped_scope_minutes(None, "CA", base, self.RATIO) == base

    def test_statutory_base_has_no_year_and_passes_through(self, monkeypatch):
        monkeypatch.setattr(clv, "get_statutory_minutes", lambda *a: pytest.fail("no fallback expected"))
        base = (360, "default", None)
        assert clv.sped_scope_minutes(None, "CA", base, self.RATIO) == base
