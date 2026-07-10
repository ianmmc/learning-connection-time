#!/usr/bin/env python3
"""Safe-promotion pointer machinery for Stage-5 config artifacts (#213, epic #209 Phase 2).

Promotion & rollback are **pointer swaps over immutable artifacts**, not redeploys. Mutable labels —
`@champion` (the live config), `@challenger` (a candidate under evaluation), `@fallback` (retained prior
champions) — point at immutable, content-addressed `config_artifact` versions. Promoting = repoint
champion; rolling back = repoint champion at the most-recent fallback. Because artifacts are immutable and
retained for a stability window, rollback is exact and cheap.

**Split of storage (the 2026-07-10 decision).** The immutable artifacts live in git under
`CONFIG_DIR/promotion/artifacts/<version>.json` (git = the audit trail, near code, matches how configs are
versioned); the pointer STATE lives in the governance DB as a singleton row, so a swap is one atomic
transaction (DB-is-working-store). This module holds both shells + the pure state-machine between them.

**Retention discipline (never delete inside the window).** Each promote pushes the old champion onto
`fallbacks` tagged with the cycle it was demoted. `evictable` REPORTS fallbacks past `retention_cycles`;
`prune` is the ONLY path that removes them from the state (and hands back the versions whose artifact files
may finally be deleted) — so a prior champion's artifact is never deleted until its window has closed.
Rollback is always available while any fallback remains.

**Ships DORMANT** (the #208/#211 pattern). The pipeline still reads `CONFIG_DIR` directly; nothing loads
the champion pointer to drive live scoring yet — that wiring (and the console toggle) is gated on the
unbuilt gate-mode persistence, tracked in the guardrail-activation checklist (#219). This module builds
the machinery; Step 5's flow composes it with the #212 gate + #213 artifact, still advisory.

PURE state-machine + a thin DB/file shell, mirroring the codebase's pure-core-first discipline. Design
authority: STAGE5_FILTER_DESIGN §5c (to be written); issue #213; FINDINGS-AND-DECISIONS §2.
"""
import json
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import paths  # noqa: E402

DEFAULT_RETENTION_CYCLES = 3   # keep a demoted champion as @fallback for this many re-ingest cycles
_SINGLETON_ID = 1              # config_pointer is a single-row table


# ----------------------------- pure state-machine (testable, no I/O) -----------------------------
def initial_state(champion_version, *, retention_cycles=DEFAULT_RETENTION_CYCLES):
    """The starting pointer state: a champion, no challenger, no fallbacks yet."""
    if retention_cycles < 1:
        raise ValueError(f"retention_cycles must be >= 1 (got {retention_cycles}) — a window of 0 would "
                         "let a rollback target be deleted immediately")
    return {"champion": champion_version, "challenger": None, "fallbacks": [],
            "retention_cycles": retention_cycles}


def set_challenger(state, version):
    """Point @challenger at a candidate version. It must differ from the current champion (there is nothing
    to evaluate against an identical config). Returns a NEW state (never mutates the input)."""
    if version == state["champion"]:
        raise ValueError(f"challenger {version} is already the champion — nothing to evaluate")
    return {**state, "challenger": version}


def promote(state, version, *, cycle):
    """Promote `version` to @champion (the #212 gate has already said yes — this is actuation only). The old
    champion is pushed onto @fallbacks tagged with `cycle`; @challenger is cleared. Raises if `version` is
    already the champion (nothing to promote). Returns a NEW state."""
    if version == state["champion"]:
        raise ValueError(f"{version} is already the champion")
    fallbacks = list(state["fallbacks"]) + [{"version": state["champion"], "demoted_at_cycle": cycle}]
    return {**state, "champion": version, "challenger": None, "fallbacks": fallbacks}


def rollback(state, *, cycle=None):  # noqa: ARG001  (cycle kept for a symmetric call signature / audit)
    """Revert @champion to the MOST-RECENT @fallback (undo the last promote). That fallback is consumed
    (popped); the rolled-back-from champion drops out of the active pointers — its artifact stays on disk,
    just unreferenced. Raises if there is no fallback to return to. Returns a NEW state."""
    if not state["fallbacks"]:
        raise ValueError("no fallback to roll back to — @champion is the only version")
    fallbacks = list(state["fallbacks"])
    target = fallbacks.pop()                       # most-recent demoted champion
    return {**state, "champion": target["version"], "challenger": None, "fallbacks": fallbacks}


def evictable(state, *, cycle):
    """Fallback versions whose retention window has closed (cycle − demoted_at_cycle >= retention_cycles) —
    REPORT only; deletion happens solely through `prune`, and never inside the window."""
    n = state["retention_cycles"]
    return [f["version"] for f in state["fallbacks"] if cycle - f["demoted_at_cycle"] >= n]


def prune(state, *, cycle):
    """The deliberate maintenance step: drop past-window fallbacks from the state and return
    (new_state, evicted_versions) — the artifact files the caller may now delete. The ONLY path to
    deletion, and only past the retention window. A fallback still inside its window is kept."""
    n = state["retention_cycles"]
    keep, evicted = [], []
    for f in state["fallbacks"]:
        (evicted if cycle - f["demoted_at_cycle"] >= n else keep).append(f)
    new_state = {**state, "fallbacks": keep}
    return new_state, [f["version"] for f in evicted]


def active_versions(state):
    """Every version any pointer references (champion + challenger + all fallbacks) — the NEVER-DELETE set.
    A caller cleaning up artifact files must intersect its on-disk versions against this and keep all of it."""
    vs = {state["champion"]}
    if state.get("challenger"):
        vs.add(state["challenger"])
    vs |= {f["version"] for f in state["fallbacks"]}
    return vs


# ----------------------------- I/O shell: immutable artifact files (git, under CONFIG_DIR) -----------------------------
def artifacts_dir(config_dir=None):
    return Path(config_dir or paths.CONFIG_DIR) / "promotion" / "artifacts"


def artifact_path(version, config_dir=None):
    return artifacts_dir(config_dir) / f"{version}.json"


def write_artifact(artifact, config_dir=None):
    """Freeze an artifact to `CONFIG_DIR/promotion/artifacts/<version>.json`. The filename IS the content
    fingerprint, so writing the same version twice is idempotent; a pre-existing file whose stored version
    disagrees with its filename is corruption and raises (immutability guard). Returns the path."""
    p = artifact_path(artifact["version"], config_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        existing = json.loads(p.read_text())
        if existing.get("version") != artifact["version"]:
            raise ValueError(f"artifact file {p.name} holds version {existing.get('version')} — "
                             "on-disk immutability violated")
        return p                                   # already frozen; idempotent
    p.write_text(json.dumps(artifact, indent=2, sort_keys=True))
    return p


def read_artifact(version, config_dir=None):
    """Load a frozen artifact by version. Raises FileNotFoundError if it was never written / already pruned."""
    return json.loads(artifact_path(version, config_dir).read_text())


# ----------------------------- I/O shell: pointer state (governance DB, atomic single-row swap) -----------------------------
def load_state(con):
    """Read the singleton pointer state, or None if promotion has never been initialized."""
    row = con.execute(text("SELECT state_json FROM config_pointer WHERE id = :i"),
                      {"i": _SINGLETON_ID}).scalar()
    return json.loads(row) if row else None


def save_state(con, state, *, updated_at=None):
    """Upsert the singleton pointer state in one statement — the atomic swap. The whole state moves at once,
    so champion/challenger/fallbacks can never be observed half-updated."""
    con.execute(text(
        """INSERT INTO config_pointer (id, state_json, updated_at) VALUES (:i, :s, :u)
           ON CONFLICT (id) DO UPDATE SET state_json = EXCLUDED.state_json, updated_at = EXCLUDED.updated_at"""),
        {"i": _SINGLETON_ID, "s": json.dumps(state), "u": updated_at})
    return state
