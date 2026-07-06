"""Issue #174 regression: a follow-up batch is a sanctioned REDO — Stage 2/3/4 reconcile must not
skip its districts just because the prior round's manifests exist on disk, and the redo must MERGE
with the prior round (union manifests) rather than replace it, because Stage 5's ingest reads ONLY
the current manifests (per-district delete + rebuild): a slice-only manifest would erase the
district's existing records and orphan their gate@5 labels.

Found live: batch_00010 (the first real 7->2 compose) auto-flowed 2->3->4 reporting success while
discovering nothing — reconcile skipped all 4 districts on 'discovery.json exists'."""
import json

import pytest

from infrastructure.acquisition.stage2_discover import discover_stage2 as D2
from infrastructure.acquisition.stage3_capture import capture_stage3 as C3
from infrastructure.acquisition.stage4_process import process_stage4 as C4


def _reg(*dids_stage):
    return {"districts": {did: {"furthest_stage": st} for did, st in dids_stage}}


def _batch(batch_type, *districts):
    return {"batch_id": "batch_test", "batch_type": batch_type,
            "districts": [{"district_id": did, "name": name, "state": "ZZ"}
                          for did, name in districts]}


# ---------------------------------------------------------------- Stage 2 reconcile
class TestStage2Reconcile:
    def _mkdisc(self, tmp_path, monkeypatch, did, name):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        d = D2.lea_dir(did, name)
        d.mkdir(parents=True)
        (d / "discovery.json").write_text("{}")

    def test_first_run_still_skips_done_district(self, tmp_path, monkeypatch):
        self._mkdisc(tmp_path, monkeypatch, "0000001", "Alpha")
        todo, skipped = D2.reconcile(_batch("first-run", ("0000001", "Alpha")),
                                     _reg(("0000001", 2)))
        assert [d["district_id"] for d in skipped] == ["0000001"] and todo == []

    def test_followup_redoes_done_district(self, tmp_path, monkeypatch):
        self._mkdisc(tmp_path, monkeypatch, "0000001", "Alpha")
        todo, skipped = D2.reconcile(_batch("follow-up", ("0000001", "Alpha")),
                                     _reg(("0000001", 2)))
        assert [d["district_id"] for d in todo] == ["0000001"] and skipped == []

    def test_followup_control_failure_still_halts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)   # no discovery.json on disk
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            D2.reconcile(_batch("follow-up", ("0000001", "Alpha")), _reg(("0000001", 2)))


# ---------------------------------------------------------------- Stage 2 write_discovery merge
def _roster_row(school_id, school, url):
    return {"school_id": school_id, "school": school, "bands": ["middle"],
            "query": f"{school} ZZ bell schedule start and end times",
            "wave1_raw_urls": [url], "wave1_provider": "brightdata",
            "wave1_gated": [{"url": url, "kept": True}],
            "wave2_invoked": False, "wave2_raw_urls": [], "wave2_provider": None,
            "wave2_gated": []}


class TestWriteDiscoveryMerge:
    def _seed_prior_round(self, tmp_path, monkeypatch):
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path)
        d = D2.lea_dir("0000001", "Alpha")
        d.mkdir(parents=True)
        (d / "discovery.json").write_text(json.dumps({
            "district_id": "0000001", "batch_id": "batch_first",
            "schools": [
                {"school_id": "S_E", "school": "Alpha Elementary", "outcome": "found"},
                {"school_id": "S_M", "school": "Alpha Middle", "outcome": "manual_flag"},
            ]}))
        (d / "candidates.json").write_text(json.dumps({
            "district_id": "0000001",
            "candidates": [{"url": "https://alpha.org/bell", "schools": ["Alpha Elementary"],
                            "tools": ["brightdata"]}]}))
        return d

    def test_merge_unions_schools_and_candidates(self, tmp_path, monkeypatch):
        d = self._seed_prior_round(tmp_path, monkeypatch)
        district = {"district_id": "0000001", "name": "Alpha", "state": "ZZ", "domain": "alpha.org"}
        # the follow-up re-queries ONLY the gapped middle school, finding a new URL
        roster = [_roster_row("S_M", "Alpha Middle", "https://alpha.org/ms-schedule")]
        D2.write_discovery(district, roster, "batch_followup", merge=True)

        disc = json.loads((d / "discovery.json").read_text())
        by_id = {s["school_id"]: s for s in disc["schools"]}
        assert set(by_id) == {"S_E", "S_M"}                      # union — S_E carried over verbatim
        assert by_id["S_E"]["outcome"] == "found"
        assert by_id["S_M"]["outcome"] == "found"                # replaced by the new attempt
        assert disc["batch_id"] == "batch_followup"

        cands = json.loads((d / "candidates.json").read_text())["candidates"]
        urls = [c["url"] for c in cands]
        assert urls == ["https://alpha.org/bell", "https://alpha.org/ms-schedule"]  # old first, verbatim
        assert "batch_id" not in cands[0]                        # prior entry unstamped
        assert cands[1]["batch_id"] == "batch_followup"          # inline round provenance
        # prior round preserved as timestamped asides
        assert list(d.glob("discovery.2*.json")) and list(d.glob("candidates.2*.json"))

    def test_merge_dedups_recycled_url(self, tmp_path, monkeypatch):
        d = self._seed_prior_round(tmp_path, monkeypatch)
        district = {"district_id": "0000001", "name": "Alpha", "state": "ZZ", "domain": "alpha.org"}
        # the widened queries re-surface the ALREADY-known URL — it must not duplicate
        roster = [_roster_row("S_M", "Alpha Middle", "https://alpha.org/bell")]
        D2.write_discovery(district, roster, "batch_followup", merge=True)
        cands = json.loads((d / "candidates.json").read_text())["candidates"]
        assert [c["url"] for c in cands] == ["https://alpha.org/bell"]

    def test_no_merge_replaces_as_before(self, tmp_path, monkeypatch):
        d = self._seed_prior_round(tmp_path, monkeypatch)
        district = {"district_id": "0000001", "name": "Alpha", "state": "ZZ", "domain": "alpha.org"}
        roster = [_roster_row("S_M", "Alpha Middle", "https://alpha.org/ms-schedule")]
        D2.write_discovery(district, roster, "batch_manual_redo")   # merge=False (default)
        disc = json.loads((d / "discovery.json").read_text())
        assert [s["school_id"] for s in disc["schools"]] == ["S_M"]   # this round only
        cands = json.loads((d / "candidates.json").read_text())["candidates"]
        assert [c["url"] for c in cands] == ["https://alpha.org/ms-schedule"]


# ---------------------------------------------------------------- Stage 3 / Stage 4 reconcile
class TestStage34Redo:
    def _district(self, tmp_path, did, name, files=()):
        d = tmp_path / f"{did}_{name.lower()}"
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            (d / f).write_text("[]")
        return {"district_id": did, "name": name, "state": "ZZ", "dir": d}

    def test_stage3_redo_puts_done_district_in_todo(self, tmp_path):
        d = self._district(tmp_path, "0000001", "Alpha", files=("captures.json",))
        todo, skipped = C3.reconcile([d], _reg(("0000001", 3)), redo=True)
        assert todo == [d] and skipped == []
        todo, skipped = C3.reconcile([d], _reg(("0000001", 3)))          # first-run unchanged
        assert todo == [] and skipped == [d]

    def test_stage3_control_failure_still_halts_under_redo(self, tmp_path):
        d = self._district(tmp_path, "0000001", "Alpha")                  # no captures.json
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            C3.reconcile([d], _reg(("0000001", 3)), redo=True)

    def test_stage4_redo_puts_done_district_in_todo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(C4, "check_file_consistency", lambda d: [])
        d = self._district(tmp_path, "0000001", "Alpha", files=("processed.json",))
        todo, skipped, quarantined = C4.reconcile([d], _reg(("0000001", 4)), redo=True)
        assert todo == [d] and skipped == [] and quarantined == []
        todo, skipped, quarantined = C4.reconcile([d], _reg(("0000001", 4)))   # first-run unchanged
        assert todo == [] and skipped == [d] and quarantined == []

    def test_stage4_redo_still_quarantines_inconsistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(C4, "check_file_consistency", lambda d: ["phantom file"])
        d = self._district(tmp_path, "0000001", "Alpha", files=("processed.json",))
        todo, skipped, quarantined = C4.reconcile([d], _reg(("0000001", 4)), redo=True)
        assert todo == [] and quarantined == [d]
