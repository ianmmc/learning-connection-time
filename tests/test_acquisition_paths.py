"""REQ-087 — the acquisition paths module is the single source of truth for runtime-state
locations, with a configurable DATA_ROOT and config kept near code (not under DATA_ROOT)."""
import importlib
import sys
from pathlib import Path

import pytest

_PATHS_MOD = "infrastructure.acquisition.common.paths"


@pytest.fixture
def fresh_paths(monkeypatch):
    """Import (or re-import) paths.py with the current environment applied. At teardown, drop the
    (possibly DATA_ROOT-overridden) module from sys.modules so it never LEAKS a tmp-rooted paths into
    later tests/code that read paths.RAW_CAPTURES/DATA_ROOT — it gets lazily re-imported with the
    real (env-reverted) environment on next use."""
    def _load():
        monkeypatch.delitem(sys.modules, _PATHS_MOD, raising=False)
        return importlib.import_module(_PATHS_MOD)
    yield _load
    sys.modules.pop(_PATHS_MOD, None)


def test_default_data_root_is_repo_data(monkeypatch, fresh_paths):
    monkeypatch.delenv("LCT_DATA_ROOT", raising=False)
    p = fresh_paths()
    assert p.DATA_ROOT == p.REPO_ROOT / "data"
    assert p.data_root_is_default() is True


def test_runtime_state_lives_under_data_root(monkeypatch, fresh_paths):
    monkeypatch.delenv("LCT_DATA_ROOT", raising=False)
    p = fresh_paths()
    for loc in (p.RAW_CAPTURES, p.QUEUE_DIR, p.STATUS_FILE,
                p.LABELS_JSON, p.CLUSTER_SPLITS_JSON):
        assert str(loc).startswith(str(p.DATA_ROOT)), f"{loc} not under DATA_ROOT"


def test_runtime_paths_match_current_layout(monkeypatch, fresh_paths):
    """Behavior-preserving: the resolved relative paths are exactly today's on-disk layout."""
    monkeypatch.delenv("LCT_DATA_ROOT", raising=False)
    p = fresh_paths()
    rel = lambda x: str(x.relative_to(p.REPO_ROOT))
    assert rel(p.LABELS_JSON) == "data/acquisition/stage5_review/labels.json"
    assert rel(p.CLUSTER_SPLITS_JSON) == "data/acquisition/stage5_review/cluster_splits.json"
    assert rel(p.QUEUE_DIR) == "data/acquisition/queue"
    assert rel(p.STATUS_FILE) == "data/acquisition/status/district_status.json"
    assert rel(p.RAW_CAPTURES) == "data/raw/lea-website-captures"


def test_config_dir_is_near_code_not_under_data_root(monkeypatch, fresh_paths):
    """Config (versioned tunables) lives by the code, deliberately NOT under DATA_ROOT."""
    monkeypatch.delenv("LCT_DATA_ROOT", raising=False)
    p = fresh_paths()
    assert not str(p.CONFIG_DIR).startswith(str(p.DATA_ROOT))
    # config lives next to paths.py (the common/ package dir), not under DATA_ROOT
    assert p.CONFIG_DIR == Path(p.__file__).resolve().parent / "config"


def test_data_root_env_override_relocates_everything(monkeypatch, tmp_path, fresh_paths):
    monkeypatch.setenv("LCT_DATA_ROOT", str(tmp_path))
    p = fresh_paths()
    assert p.DATA_ROOT == tmp_path
    assert p.data_root_is_default() is False
    assert p.RAW_CAPTURES == tmp_path / "raw" / "lea-website-captures"
    # config does NOT follow DATA_ROOT
    assert not str(p.CONFIG_DIR).startswith(str(tmp_path))
