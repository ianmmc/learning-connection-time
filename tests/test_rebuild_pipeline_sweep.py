"""WP-6 sweep fixes over the rebuild-pipeline step scripts (epics #479/#480).

- #305/#306 reset_database.create_backup passes the full (driver-stripped)
  connection URL to pg_dump
- #426 truncate_all_tables fails loud + atomic (no per-table swallow)
- #466 rebuild threshold is the named EXPECTED_MIN_DISTRICTS constant
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCreateBackupConnection:
    def test_full_url_reaches_pg_dump_with_driver_stripped(self, tmp_path):
        from infrastructure.scripts import reset_database as rd

        fake_url = 'postgresql+psycopg2://user:pw@dbhost:5433/lct?sslmode=require'
        completed = MagicMock()
        with patch.object(rd, 'get_database_url', return_value=fake_url), \
             patch.object(rd.subprocess, 'run', return_value=completed) as run:
            # stat() the produced file path fails on the fake run — tolerate
            try:
                rd.create_backup(tmp_path)
            except FileNotFoundError:
                pass
        cmd = run.call_args[0][0]
        # -d carries the whole libpq URI (host/port/password/sslmode), with
        # the SQLAlchemy "+psycopg2" suffix stripped (issues #305/#306)
        d_arg = cmd[cmd.index('-d') + 1]
        assert d_arg == 'postgresql://user:pw@dbhost:5433/lct?sslmode=require'


class TestTruncateFailLoud:
    def test_error_rolls_back_and_raises(self):
        from infrastructure.scripts.reset_database import truncate_all_tables

        engine = MagicMock()
        conn = engine.connect.return_value.__enter__.return_value
        trans = conn.begin.return_value
        conn.execute.side_effect = RuntimeError('boom')

        with pytest.raises(RuntimeError):
            truncate_all_tables(engine, existing_tables={'districts'}, verbose=False)
        trans.rollback.assert_called_once()
        trans.commit.assert_not_called()


class TestRebuildThresholdConstant:
    def test_named_constant_exists(self):
        from infrastructure.scripts.rebuild_database import EXPECTED_MIN_DISTRICTS
        assert EXPECTED_MIN_DISTRICTS == 17000

    def test_no_inline_literal_left(self):
        src = Path('infrastructure/scripts/rebuild_database.py').read_text()
        assert 'counts.get("districts", 0) < 17000' not in src


class TestPhase2bDryRun:
    def test_dry_run_short_circuits_before_subprocess(self):
        """Max-effort review: phase_2b_classifications hardcoded
        dry_run=False to run_script(), so a top-level --dry-run still spawned
        the real apply_ctc_classification.py subprocess (real CSV read, real
        DB query) instead of just printing the command like every other
        phase. run_script's own dry_run branch must fire."""
        from infrastructure.scripts import rebuild_database as rd

        with patch.object(rd, 'run_script', return_value=True) as run_script:
            rd.phase_2b_classifications(dry_run=True, year='2024-25')

        assert run_script.call_args.kwargs.get('dry_run') is True \
            or (len(run_script.call_args.args) >= 3 and run_script.call_args.args[2] is True)
