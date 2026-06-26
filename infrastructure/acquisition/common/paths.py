"""Single source of truth for acquisition-pipeline filesystem locations (REQ-087).

All *generated runtime state* lives under ``DATA_ROOT`` (default ``<repo>/data``) so the whole
tree can be relocated — e.g. to an external drive — by setting ``LCT_DATA_ROOT`` once, instead
of hunting down hardcoded ``data/acquisition/...`` string literals scattered across the code.

Split of concerns (see the 2026-06-25 reorg discussion):
  * runtime state (batches, the status registry, the Stage-5 review DB) -> under ``DATA_ROOT``,
    consolidated and relocatable, gitignored (precious JSON backups are git-included by exception).
  * raw captures -> under ``DATA_ROOT`` too (the biggest tree; relocates as one unit).
  * config / tunables (versioned input) -> ``CONFIG_DIR``, *near code*, NOT under ``DATA_ROOT``.

Import locations from here; do not re-hardcode them.
"""
import os
from pathlib import Path

# this file: infrastructure/acquisition/common/paths.py  -> parents[3] == repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# One knob to relocate every runtime artifact (env override; absolute or repo-relative).
DATA_ROOT = Path(os.environ.get("LCT_DATA_ROOT") or (REPO_ROOT / "data")).expanduser()

# --- raw captured artifacts (write-once; Stage 3 output) ---
RAW_CAPTURES = DATA_ROOT / "raw" / "lea-website-captures"

# --- acquisition runtime state ---
ACQUISITION = DATA_ROOT / "acquisition"
QUEUE_DIR = ACQUISITION / "queue"                       # Stage 1 batch_*.json
STATUS_DIR = ACQUISITION / "status"
STATUS_FILE = STATUS_DIR / "district_status.json"       # cross-stage registry

STAGE5_DIR = ACQUISITION / "stage5_review"
REVIEW_DB = STAGE5_DIR / "review.db"                     # regenerable SQLite cache
LABELS_JSON = STAGE5_DIR / "labels.json"                # precious, version-controlled
CLUSTER_SPLITS_JSON = STAGE5_DIR / "cluster_splits.json"  # precious, version-controlled

# --- config-as-data (versioned tunables; near code, intentionally NOT under DATA_ROOT) ---
CONFIG_DIR = Path(__file__).resolve().parent / "config"


def data_root_is_default() -> bool:
    """True when DATA_ROOT is the in-repo default (no LCT_DATA_ROOT override active)."""
    return DATA_ROOT == (REPO_ROOT / "data")
