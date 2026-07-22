"""_run_stage4_subprocess (issue #608) — the console's isolated-subprocess wrapper around Stage 4.

Two layers:
  * Pure logic (no real subprocess): fakes `subprocess.Popen` to drive every branch of the
    `[kind] {...}` line-parsing / exit-code interpretation — the new code this fix actually added, and
    the most bug-prone part of it (a wrong branch here silently swallows or mislabels a real crash).
  * One real end-to-end smoke test (govdb-marked, skips if Docker is down) that spawns the ACTUAL
    `headless.py` CLI subprocess against a trivial (district-less) batch, proving the whole plumbing —
    temp batch-file handoff, stdout streaming, stderr log file, cleanup — actually works together.
"""
import pytest


class _FakeProc:
    """Stands in for subprocess.Popen's return value: an iterable `.stdout` of lines + `.wait()`."""

    def __init__(self, lines, returncode):
        self.stdout = iter(lines)
        self._returncode = returncode

    def wait(self):
        return self._returncode


@pytest.fixture
def server(monkeypatch, tmp_path):
    from infrastructure.acquisition.process_governance import server as srv
    monkeypatch.setattr(srv.paths, "PROCESS_LOGS_DIR", tmp_path / "process_logs")
    return srv


def _patch_popen(monkeypatch, server, lines, returncode):
    calls = {}

    def fake_popen(cmd, **kw):
        calls["cmd"] = cmd
        return _FakeProc(lines, returncode)

    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    return calls


BATCH = {"batch_id": "batch_00099", "districts": []}


class TestSuccessPath:
    def test_streams_events_and_returns_summary(self, server, monkeypatch):
        lines = [
            '[dispatched] {"district_id": "111"}\n',
            '[completed] {"district_id": "111", "outcome": "processed_all"}\n',
            '[summary] {"batch_id": "batch_00099", "todo": 1, "skipped": 0, "results": []}\n',
        ]
        _patch_popen(monkeypatch, server, lines, 0)
        events = []
        summary = server._run_stage4_subprocess(BATCH, actor="ian", on_event=lambda k, p: events.append((k, p)))
        assert summary == {"batch_id": "batch_00099", "todo": 1, "skipped": 0, "results": []}
        assert events == [("dispatched", {"district_id": "111"}),
                          ("completed", {"district_id": "111", "outcome": "processed_all"})]

    def test_cmd_uses_batch_file_not_stdin(self, server, monkeypatch):
        lines = ['[summary] {"ok": true}\n']
        calls = _patch_popen(monkeypatch, server, lines, 0)
        server._run_stage4_subprocess(BATCH, actor="ian", on_event=None)
        cmd = calls["cmd"]
        assert "--batch-file" in cmd
        assert "run" in cmd and BATCH["batch_id"] in cmd
        assert "--actor" in cmd and "ian" in cmd

    def test_batch_temp_file_is_cleaned_up(self, server, monkeypatch):
        written_paths = []
        orig_mkstemp = server.tempfile.mkstemp

        def spying_mkstemp(*a, **k):
            fd, p = orig_mkstemp(*a, **k)
            written_paths.append(p)
            return fd, p

        monkeypatch.setattr(server.tempfile, "mkstemp", spying_mkstemp)
        _patch_popen(monkeypatch, server, ['[summary] {"ok": true}\n'], 0)
        server._run_stage4_subprocess(BATCH, actor="ian", on_event=None)
        assert written_paths and not server.os.path.exists(written_paths[0])

    def test_malformed_lines_are_ignored_not_crashing(self, server, monkeypatch):
        lines = [
            "UserWarning: No tables found in table area (...)\n",   # stray native-tool noise
            "not even bracketed\n",
            '[summary] {"ok": true}\n',
        ]
        _patch_popen(monkeypatch, server, lines, 0)
        assert server._run_stage4_subprocess(BATCH, actor="ian", on_event=None) == {"ok": True}

    def test_log_file_created_under_process_logs_dir(self, server, monkeypatch):
        _patch_popen(monkeypatch, server, ['[summary] {"ok": true}\n'], 0)
        server._run_stage4_subprocess(BATCH, actor="ian", on_event=None)
        logs = list(server.paths.PROCESS_LOGS_DIR.glob(f"stage4_{BATCH['batch_id']}_*.log"))
        assert len(logs) == 1


class TestFailurePaths:
    def test_control_failure_raises_systemexit(self, server, monkeypatch):
        lines = ['[control_failure] {"detail": "batch batch_00099 is abandoned (terminal)"}\n']
        _patch_popen(monkeypatch, server, lines, 1)
        with pytest.raises(SystemExit, match="abandoned"):
            server._run_stage4_subprocess(BATCH, actor="ian", on_event=None)

    def test_error_raises_runtimeerror(self, server, monkeypatch):
        lines = ['[error] {"detail": "RuntimeError: boom"}\n']
        _patch_popen(monkeypatch, server, lines, 1)
        with pytest.raises(RuntimeError, match="boom"):
            server._run_stage4_subprocess(BATCH, actor="ian", on_event=None)

    def test_signal_kill_raises_runtimeerror_naming_the_signal(self, server, monkeypatch):
        """The #608 case: camelot/PDFium segfaults mid-run — the child never gets to print anything,
        and subprocess.wait() reports the negative-signal returncode Python uses for a killed child."""
        _patch_popen(monkeypatch, server, [], -11)   # SIGSEGV
        with pytest.raises(RuntimeError, match="SIGSEGV"):
            server._run_stage4_subprocess(BATCH, actor="ian", on_event=None)

    def test_missing_summary_with_clean_exit_raises(self, server, monkeypatch):
        _patch_popen(monkeypatch, server, ['[dispatched] {"district_id": "111"}\n'], 0)
        with pytest.raises(RuntimeError, match="no summary"):
            server._run_stage4_subprocess(BATCH, actor="ian", on_event=None)

    def test_batch_temp_file_cleaned_up_even_on_failure(self, server, monkeypatch):
        written_paths = []
        orig_mkstemp = server.tempfile.mkstemp

        def spying_mkstemp(*a, **k):
            fd, p = orig_mkstemp(*a, **k)
            written_paths.append(p)
            return fd, p

        monkeypatch.setattr(server.tempfile, "mkstemp", spying_mkstemp)
        _patch_popen(monkeypatch, server, [], -11)
        with pytest.raises(RuntimeError):
            server._run_stage4_subprocess(BATCH, actor="ian", on_event=None)
        assert written_paths and not server.os.path.exists(written_paths[0])


@pytest.mark.integration
@pytest.mark.govdb
class TestRealSubprocessRoundTrip:
    """No Popen faking — actually spawns `python -m ...headless run ...`. batch_guard.assert_runnable
    is a no-op for a batch_id the DB has never seen, and an empty districts[] list needs no on-disk
    captures, so this needs Docker (governance Postgres) but no seeded rows."""

    def test_empty_batch_round_trips_cleanly(self, tmp_path, monkeypatch):
        from infrastructure.acquisition.common import db as gdb
        try:
            gdb.get_engine().connect().close()
        except Exception as e:
            pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
        from infrastructure.acquisition.process_governance import server
        monkeypatch.setattr(server.paths, "PROCESS_LOGS_DIR", tmp_path / "process_logs")
        events = []
        summary = server._run_stage4_subprocess(
            {"batch_id": "batch_zz608smoke", "districts": []},
            actor="ian-test", on_event=lambda k, p: events.append((k, p)))
        assert summary["batch_id"] == "batch_zz608smoke"
        assert summary["todo"] == 0
        logs = list((tmp_path / "process_logs").glob("stage4_batch_zz608smoke_*.log"))
        assert len(logs) == 1
