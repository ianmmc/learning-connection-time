"""Issue #178: tests must NEVER write the four git-tracked precious-state backups — the pre-commit
hook sweeps them into every commit, so test-driven exporter side effects pollute unrelated commits
(and a rolled-back fixture can leave a backup CONTRADICTING the DB). The invariant is enforced once,
at `paths.guard_tracked_backup()` (the exporters' shared path-resolution moment), not per test.

These tests run UNDER pytest by construction, so the guard's redirect branch is live here."""
import tempfile
from pathlib import Path

import pytest

from infrastructure.acquisition.common import paths


def test_tracked_backups_cover_all_precious_files():
    """The guarded set is exactly the pre-commit hook's PRECIOUS_BACKUPS sweep list."""
    assert paths.TRACKED_BACKUPS == {
        paths.STATUS_FILE, paths.LABELS_JSON, paths.CLUSTER_SPLITS_JSON, paths.FOLLOWUP_FLAGS_JSON,
        paths.GATE_MODE_JSON, paths.STAGE8_APPROVALS_JSON, paths.BAND_EXCLUSIONS_JSON,
        paths.HUMAN_ADDED_FACTS_JSON, paths.SLOT_ASSIGNMENTS_JSON}


def test_guard_redirects_tracked_files_under_pytest():
    for tracked in paths.TRACKED_BACKUPS:
        out = paths.guard_tracked_backup(tracked)
        assert out != tracked                                    # never the tracked file itself
        assert paths.REPO_ROOT not in out.parents                # never inside the repo
        assert out.name == tracked.name                          # still identifiable in quarantine
        assert Path(tempfile.gettempdir()) in out.parents


def test_guard_passes_explicit_test_paths_through(tmp_path):
    """A test that deliberately exercises an exporter passes its own tmp `out=` — untouched."""
    mine = tmp_path / "labels.json"
    assert paths.guard_tracked_backup(mine) == mine


def test_guard_is_inert_outside_pytest(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert paths.guard_tracked_backup(paths.STATUS_FILE) == paths.STATUS_FILE


def test_all_exporters_route_through_the_guard():
    """Wiring check: every precious-backup exporter resolves its write target via the guard, so a
    future exporter edit can't silently drop the #178 protection."""
    import inspect

    from infrastructure.acquisition.common import district_status as DS
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    from infrastructure.acquisition.process_governance import server

    for fn in (DS.export_status, BS.export_labels, BS.export_splits,
               server._backup_followups, server._backup_gate_mode, server._backup_stage8_approvals,
               server._backup_band_exclusions, server._backup_human_added,
               server._backup_slot_assignments):
        assert "guard_tracked_backup" in inspect.getsource(fn), (
            f"{fn.__module__}.{fn.__name__} writes a tracked precious backup without the #178 guard")


@pytest.mark.govdb
def test_export_status_under_pytest_never_touches_the_tracked_file(gov_session):
    """End-to-end: calling the real exporter with its DEFAULT target during a test writes the
    quarantine copy and leaves the tracked district_status.json byte-identical."""
    from infrastructure.acquisition.common import district_status as DS

    tracked = paths.STATUS_FILE
    before = tracked.read_bytes() if tracked.exists() else None
    DS.export_status(gov_session)                                # default out → tracked → quarantined
    after = tracked.read_bytes() if tracked.exists() else None
    assert before == after                                       # tracked backup untouched
    q = Path(tempfile.gettempdir()) / "lct-test-quarantine" / tracked.name
    assert q.exists()                                            # the write landed in quarantine
