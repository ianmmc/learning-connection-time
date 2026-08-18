"""Issue #178: tests must NEVER write the four git-tracked precious-state backups — the pre-commit
hook sweeps them into every commit, so test-driven exporter side effects pollute unrelated commits
(and a rolled-back fixture can leave a backup CONTRADICTING the DB). The invariant is enforced once,
at `paths.guard_tracked_backup()` (the exporters' shared path-resolution moment), not per test.

These tests run UNDER pytest by construction, so the guard's redirect branch is live here.

#822 added a SECOND cause of the same harm, and the TestNonCanonicalDb822 class below covers it:
a process connected to a non-canonical governance DB (a `TEMPLATE governance` clone used for
scratch console verification, an empty probe DB). Cloning the DB does not isolate these files —
they live on disk, and every exporter rebuilds them WHOLESALE from the connected DB's log."""
import tempfile
from pathlib import Path

import pytest

from infrastructure.acquisition.common import paths


def test_tracked_backups_cover_all_precious_files():
    """The guarded set is exactly the pre-commit hook's PRECIOUS_BACKUPS sweep list."""
    assert paths.TRACKED_BACKUPS == {
        paths.STATUS_FILE, paths.LABELS_JSON, paths.CLUSTER_SPLITS_JSON, paths.FOLLOWUP_FLAGS_JSON,
        paths.GATE_MODE_JSON, paths.STAGE8_APPROVALS_JSON, paths.BAND_EXCLUSIONS_JSON,
        paths.HUMAN_ADDED_FACTS_JSON, paths.SLOT_ASSIGNMENTS_JSON,
        paths.DISCOVERED_DOMAINS_JSON, paths.DISCOVERED_DOMAIN_DECISIONS_JSON,
        paths.DISCOVERY_POLICY_JSON}


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

    for fn in (DS.export_status, BS.export_labels, BS.export_splits):
        assert "guard_tracked_backup" in inspect.getsource(fn), (
            f"{fn.__module__}.{fn.__name__} writes a tracked precious backup without the #178 guard")
    # server.py's table exporters route through the ONE shared body (epic-#499 review round:
    # six hand-copied twins meant a pattern fix could miss one) — the guard lives in the helper,
    # and every wrapper must call it.
    assert "guard_tracked_backup" in inspect.getsource(server._backup_precious_table)
    for fn in (server._backup_followups, server._backup_gate_mode, server._backup_stage8_approvals,
               server._backup_band_exclusions, server._backup_human_added,
               server._backup_slot_assignments, server._backup_discovered_domains,
               server._backup_discovery_policy):
        assert "_backup_precious_table" in inspect.getsource(fn), (
            f"{fn.__module__}.{fn.__name__} bypasses the shared #178-guarded exporter body")


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


class TestNonCanonicalDb822:
    """#822: the tracked twins must be regenerated ONLY from the canonical governance DB.

    Found the hard way. A #822 console verification cloned the governance DB (`TEMPLATE
    governance`) so the real one was untouched, then created a gate@6 draft against the clone —
    and `district_status.json`, a file on disk that knows nothing about which DB you chose, was
    regenerated from the clone's event log and picked up a `draft_add_district` event for district
    1201440 with actor `verify822`. The #178 guard did not fire because that server was not pytest.

    The stakes are larger than a stray event: every exporter rebuilds its file WHOLESALE, so a
    scratch server on an EMPTY governance DB writes `{}` over the lot. Measured 2026-08-18: the
    tracked file held 175 districts; an empty-DB export produced 0."""

    def _outside_pytest(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)   # isolate the #822 cause from #178

    def test_canonical_db_passes_through(self, monkeypatch):
        self._outside_pytest(monkeypatch)
        monkeypatch.delenv("GOVERNANCE_DATABASE_URL", raising=False)
        monkeypatch.setenv("GOVERNANCE_DB_NAME", "governance")
        assert paths.guard_tracked_backup(paths.STATUS_FILE) == paths.STATUS_FILE

    def test_the_actual_leak_a_template_clone_is_quarantined(self, monkeypatch):
        """The exact configuration that leaked: a scratch server on `gov_822_scratch`."""
        self._outside_pytest(monkeypatch)
        monkeypatch.delenv("GOVERNANCE_DATABASE_URL", raising=False)
        monkeypatch.setenv("GOVERNANCE_DB_NAME", "gov_822_scratch")
        out = paths.guard_tracked_backup(paths.STATUS_FILE)
        assert out != paths.STATUS_FILE
        assert paths.REPO_ROOT not in out.parents
        assert out.name == paths.STATUS_FILE.name

    def test_every_tracked_file_is_covered_not_just_district_status(self, monkeypatch):
        """The leak hit district_status.json, but all twelve twins share the exporter pattern."""
        self._outside_pytest(monkeypatch)
        monkeypatch.delenv("GOVERNANCE_DATABASE_URL", raising=False)
        monkeypatch.setenv("GOVERNANCE_DB_NAME", "gov_scratch")
        for tracked in paths.TRACKED_BACKUPS:
            assert paths.guard_tracked_backup(tracked) != tracked, tracked.name

    def test_a_full_url_override_to_another_db_is_also_caught(self, monkeypatch):
        """The guard reads the RESOLVED url, so the GOVERNANCE_DATABASE_URL path (cloud/prod
        override) cannot bypass it — the check is not a special case of the env-var branch."""
        self._outside_pytest(monkeypatch)
        monkeypatch.setenv("GOVERNANCE_DATABASE_URL",
                           "postgresql://u:p@remote.example:5432/some_other_db")
        assert paths.guard_tracked_backup(paths.STATUS_FILE) != paths.STATUS_FILE
        monkeypatch.setenv("GOVERNANCE_DATABASE_URL",
                           "postgresql://u:p@remote.example:5432/governance")
        assert paths.guard_tracked_backup(paths.STATUS_FILE) == paths.STATUS_FILE

    def test_is_canonical_target_is_the_one_definition(self, monkeypatch):
        """Canonical identity is defined once in db.py; paths asks rather than re-deriving it from
        the env vars (a second copy is the implemented-twice-drifts class)."""
        import inspect
        from infrastructure.acquisition.common import db as gdb
        self._outside_pytest(monkeypatch)
        monkeypatch.delenv("GOVERNANCE_DATABASE_URL", raising=False)
        monkeypatch.setenv("GOVERNANCE_DB_NAME", "governance")
        assert gdb.is_canonical_target() is True
        monkeypatch.setenv("GOVERNANCE_DB_NAME", "clone")
        assert gdb.is_canonical_target() is False
        src = inspect.getsource(paths.guard_tracked_backup)
        assert "is_canonical_target" in src
        assert "GOVERNANCE_DB_NAME" not in src      # paths must NOT re-derive the identity
