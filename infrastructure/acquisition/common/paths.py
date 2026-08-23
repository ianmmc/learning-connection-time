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
import json
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
HANDOFFS_DIR = ACQUISITION / "handoffs"                 # immutable Stage-6 dispatch receipts
                                                        # (stage6_handoff.handoff.DEFAULT_ROOT is
                                                        # this; base-layer readers use it directly
                                                        # rather than importing a stage package)

# Derived per-record harvest slices (Stage-5 ingest output; regenerable). Deliberately under
# acquisition/, NOT under raw/ — data/raw is write-once Stage-3 output (Critical Rule 5; issue #58).
HARVEST_SLICES_DIR = ACQUISITION / "harvest_slices"

# Stage 4's isolated-subprocess stderr logs (issue #608): camelot's native PDFium/OpenCV backend can
# segfault, which bypasses Python's exception handling entirely — the console runs each batch's Stage 4
# job in its own OS process so a crash there can't take down the server, and captures that process's
# stderr (tracebacks, camelot/pdfminer warnings) here for post-crash forensics. Ephemeral/regenerable,
# not a precious backup.
PROCESS_LOGS_DIR = ACQUISITION / "process_logs"

STAGE5_DIR = ACQUISITION / "stage5_review"
# (The retired SQLite review.db cache lived here pre-REQ-103; the working store is now the isolated
# governance Postgres DB — see common/db.py. The precious JSON backups below remain.)
LABELS_JSON = STAGE5_DIR / "labels.json"                # precious, version-controlled
CLUSTER_SPLITS_JSON = STAGE5_DIR / "cluster_splits.json"  # precious, version-controlled
FOLLOWUP_FLAGS_JSON = STAGE5_DIR / "followup_flags.json"  # precious, version-controlled (issue #57)
GATE_MODE_JSON = STATUS_DIR / "gate_modes.json"         # precious, version-controlled (per-gate manual/auto, #104)
STAGE8_APPROVALS_JSON = STATUS_DIR / "stage8_approvals.json"  # precious, version-controlled (gate@8 decisions, #89)
BAND_EXCLUSIONS_JSON = STATUS_DIR / "band_exclusions.json"   # precious, version-controlled (gate@8 exclude-from-band, #257)
HUMAN_ADDED_FACTS_JSON = STATUS_DIR / "human_added_facts.json"  # precious, version-controlled (gate@8 human-add, #474)
SLOT_ASSIGNMENTS_JSON = STATUS_DIR / "slot_assignments.json"  # precious, version-controlled (gate@8 slot dispositions, #499 REQ-145)
DISCOVERED_DOMAINS_JSON = STATUS_DIR / "discovered_domains.json"  # precious, version-controlled (#164 human-confirmed domains)
DISCOVERED_DOMAIN_DECISIONS_JSON = STATUS_DIR / "discovered_domain_decisions.json"  # precious (#572 proposal decisions — the training corpus)
DISCOVERY_POLICY_JSON = STATUS_DIR / "discovery_policy.json"      # precious, version-controlled (#164 scope-policy events)
SCORECARDS_DIR = STAGE5_DIR / "scorecards"              # harness output (config-vs-labels metrics)

# --- config-as-data (versioned tunables; near code, intentionally NOT under DATA_ROOT) ---
CONFIG_DIR = Path(__file__).resolve().parent / "config"

# Gitignored local secrets (API keys) -- repo-anchored so importers resolve it identically
# regardless of launch CWD (issue #31; the same bug class RAW_CAPTURES already fixed).
SECRETS_FILE = REPO_ROOT / "config" / "secrets.local.json"


def data_root_is_default() -> bool:
    """True when DATA_ROOT is the in-repo default (no LCT_DATA_ROOT override active)."""
    return DATA_ROOT == (REPO_ROOT / "data")


# --- test-run quarantine for the tracked precious backups (issue #178) ---
# The four git-tracked precious-state backups are swept into every commit by the pre-commit hook, so a
# test run that regenerates one (govdb tests drive real server endpoints, whose exporters fire as a
# side effect) pollutes whatever commit comes next with fixture churn — and can leave the backup
# CONTRADICTING the DB after the fixture's cleanup. The invariant is global ("no test run ever writes a
# tracked backup"), so it is enforced HERE, once, at the exporters' shared path-resolution moment —
# not re-implemented per test via monkeypatching (the epic-#133 lesson).
TRACKED_BACKUPS = frozenset({STATUS_FILE, LABELS_JSON, CLUSTER_SPLITS_JSON, FOLLOWUP_FLAGS_JSON, GATE_MODE_JSON,
                             STAGE8_APPROVALS_JSON, BAND_EXCLUSIONS_JSON, HUMAN_ADDED_FACTS_JSON,
                             DISCOVERED_DOMAINS_JSON, DISCOVERED_DOMAIN_DECISIONS_JSON,
                             DISCOVERY_POLICY_JSON, SLOT_ASSIGNMENTS_JSON})
_quarantine_noted: set = set()


def guard_tracked_backup(out: Path) -> Path:
    """The write target for a precious-backup export: `out` itself normally, else a quarantine dir
    under the system tmp. Explicit non-tracked paths (tests that pass their own tmp `out=`) pass
    through untouched.

    TWO causes of the same harm — a tracked twin regenerated from state that is not the real world:
      * under pytest (PYTEST_CURRENT_TEST is set for the whole test process, inherited by its
        threads/subprocesses) — issue #178;
      * connected to a NON-CANONICAL governance DB (#822) — a `TEMPLATE governance` clone used for
        scratch console verification, or an empty probe DB. Cloning the DB does NOT isolate these
        files: they live on disk, and every exporter rebuilds them WHOLESALE from the connected
        DB's log. A scratch server on an empty DB would blank 175 districts of tracked state.
        Found the hard way — a #822 verification run wrote a `draft_add_district` event for a
        district into `district_status.json` while pointed at a clone.
    Redirecting (rather than raising) keeps scratch verification working end-to-end, which is the
    behavior that makes the guard something people leave on."""
    if out not in TRACKED_BACKUPS:
        return out
    reason = None
    if "PYTEST_CURRENT_TEST" in os.environ:
        reason = "test run (#178)"
    else:
        from infrastructure.acquisition.common import db as _db   # local: db must not import paths
        if not _db.is_canonical_target():
            reason = (f"NON-CANONICAL governance DB "
                      f"'{_db.governance_url().rstrip('/').rsplit('/', 1)[-1]}' (#822)")
    if reason is None:
        return out
    import tempfile
    q = Path(tempfile.gettempdir()) / "lct-test-quarantine" / out.name
    q.parent.mkdir(parents=True, exist_ok=True)
    if out.name not in _quarantine_noted:      # note once per file per process, not per write
        _quarantine_noted.add(out.name)
        print(f"[paths] {reason} — {out.name} export quarantined to {q}", flush=True)
    return q


def atomic_write_json(path: Path, doc: dict | list) -> None:
    """Crash-safe JSON write: serialize to a sibling temp file, then os.replace() -- a reader
    never sees a partially-written file, only the old version or the new one. THE single home
    for the tmp+replace pattern (#265 review; #554 consolidated district_status/batch_store/
    benchmark_batch, #561 the remaining six sites) -- any future change to the pattern
    (e.g. fsync-before-replace) lands here, nowhere else."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2))
    os.replace(tmp, path)
