"""Stage-4 reconcile + file-consistency tests — PURE (tmp_path + in-memory registry only; no NCES
data, no Postgres), so they run in the default DB-free suite / CI.

Moved out of tests/test_acquisition_stages.py (pytestmark=integration) as the root-cause fix for
issue #166: these tests drifted silently — 2-value unpacks after reconcile() grew a 3rd return
(quarantined, #78), and SystemExit expectations after missing-file handling became per-district
quarantine — precisely because the integration module never runs in CI, so a green pipeline said
nothing about them. Pure tests must live where CI executes them."""
import json

import pytest

from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.stage4_process import process_stage4 as P4


def _write_discovery(d, district_id="9999999", name="Test Process District", state="ZZ",
                     domain="testprocess.example"):
    """Stage 4 pulls district_id/name/state from discovery.json, same as capture_stage3.py
    pulls them rather than re-deriving -- process_stage4.find_districts() requires it
    alongside captures.json."""
    (d / "discovery.json").write_text(json.dumps({
        "district_id": district_id, "name": name, "state": state, "domain": domain,
        "batch_id": "batch_00099", "generated_at": "2026-06-23T00:00:00Z", "schools": [],
    }))


class TestProcessStage4FileConsistency:
    def test_passes_when_every_referenced_file_exists(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        rec_dir = d / "captures" / "abc123"
        rec_dir.mkdir(parents=True)
        (rec_dir / "page.txt").write_text("hello")
        captures = [{"url": "https://x/1", "hash": "abc123", "ok": True, "files": {"txt": "page.txt"}}]
        (d / "captures.json").write_text(json.dumps(captures))
        district = P4.find_districts(tmp_path)[0]
        assert P4.check_file_consistency(district) == []

    def test_missing_referenced_file_is_reported_not_raised(self, tmp_path):
        """check_file_consistency RETURNS the problems (#78) — it never raises; reconcile() uses the
        list to QUARANTINE the district. (Pre-#78 this was a CONTROL-FAILURE SystemExit; the test
        had drifted and kept asserting the raise — #166.)"""
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        rec_dir = d / "captures" / "abc123"
        rec_dir.mkdir(parents=True)
        # page.txt deliberately NOT written -- captures.json claims it exists.
        captures = [{"url": "https://x/1", "hash": "abc123", "ok": True, "files": {"txt": "page.txt"}}]
        (d / "captures.json").write_text(json.dumps(captures))
        district = P4.find_districts(tmp_path)[0]
        problems = P4.check_file_consistency(district)
        assert len(problems) == 1
        assert "page.txt" in problems[0]

    def test_ok_false_records_are_exempt(self, tmp_path):
        """files: {} by design for a capture failure -- not an inconsistency."""
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        captures = [{"url": "https://x/1", "hash": "abc123", "ok": False, "err": "needs_oauth_reauth", "files": {}}]
        (d / "captures.json").write_text(json.dumps(captures))
        district = P4.find_districts(tmp_path)[0]
        assert P4.check_file_consistency(district) == []


class TestProcessStage4Reconcile:
    def test_district_with_no_disk_artifact_and_no_registry_entry_is_todo(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        (d / "captures.json").write_text("[]")
        districts = P4.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        todo, skipped, quarantined = P4.reconcile(districts, registry)
        assert [x["district_id"] for x in todo] == ["9999999"]
        assert skipped == []
        assert quarantined == []

    def test_disk_ahead_of_registry_reconciles_up_and_skips(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        (d / "captures.json").write_text("[]")
        (d / "processed.json").write_text("[]")
        districts = P4.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        todo, skipped, quarantined = P4.reconcile(districts, registry)
        assert todo == []
        assert [x["district_id"] for x in skipped] == ["9999999"]
        assert quarantined == []
        assert registry["districts"]["9999999"]["furthest_stage"] == 4

    def test_registry_ahead_of_disk_halts_the_entire_run(self, tmp_path):
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        (d / "captures.json").write_text("[]")
        districts = P4.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        DS.record_stage(registry, "9999999", "Test Process District", "ZZ",
                         stage=4, stage_name="process", outcome="processed_all")
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            P4.reconcile(districts, registry)

    def test_missing_referenced_file_quarantines_the_district(self, tmp_path):
        """The file-existence check fires inside reconcile() too (#78): a district whose captures.json
        claims a file not on disk is QUARANTINED (excluded from the run with its problems attached),
        NOT run-halted -- one inconsistent district must not abort the whole batch."""
        d = tmp_path / "9999999_test_process_district"
        d.mkdir()
        _write_discovery(d)
        rec_dir = d / "captures" / "abc123"
        rec_dir.mkdir(parents=True)
        captures = [{"url": "https://x/1", "hash": "abc123", "ok": True, "files": {"txt": "page.txt"}}]
        (d / "captures.json").write_text(json.dumps(captures))
        districts = P4.find_districts(tmp_path)
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        todo, skipped, quarantined = P4.reconcile(districts, registry)
        assert todo == [] and skipped == []
        assert [x["district_id"] for x in quarantined] == ["9999999"]
        assert quarantined[0]["inconsistency"]   # the specific problem(s) attached for the report
