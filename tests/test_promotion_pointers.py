"""#213 / epic #209 Phase 2 — safe-promotion pointer machinery for Stage-5 config artifacts.

The executable spec of promotion-as-pointer-swap over immutable artifacts: promote repoints @champion and
retains the prior one as @fallback; rollback repoints to the most-recent fallback; a prior champion's
artifact is NEVER deleted inside its retention window. Pure state-machine tests (no I/O) + the file store
(tmp dir) + the atomic DB swap (govdb). Mirrors the pure-core-first discipline."""
import json

import pytest
from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import promotion_pointers as PP  # noqa: E402


# ----------------------------- pure state-machine -----------------------------
def test_initial_state_has_a_champion_and_nothing_else():
    s = PP.initial_state("v1", retention_cycles=3)
    assert s["champion"] == "v1" and s["challenger"] is None and s["fallbacks"] == []
    assert s["retention_cycles"] == 3


def test_initial_state_rejects_a_zero_retention_window():
    with pytest.raises(ValueError):
        PP.initial_state("v1", retention_cycles=0)   # a 0-cycle window could delete a rollback target at once


def test_set_challenger_requires_a_different_version():
    s = PP.initial_state("v1")
    assert PP.set_challenger(s, "v2")["challenger"] == "v2"
    with pytest.raises(ValueError):
        PP.set_challenger(s, "v1")                    # identical to champion -> nothing to evaluate


def test_promote_swaps_champion_and_retains_the_prior_as_fallback():
    s = PP.initial_state("v1")
    s = PP.set_challenger(s, "v2")
    s2 = PP.promote(s, "v2", cycle=5)
    assert s2["champion"] == "v2"
    assert s2["challenger"] is None                   # cleared on promote
    assert s2["fallbacks"] == [{"version": "v1", "demoted_at_cycle": 5}]


def test_promote_is_immutable_and_rejects_promoting_the_current_champion():
    s = PP.initial_state("v1")
    with pytest.raises(ValueError):
        PP.promote(s, "v1", cycle=1)                  # already champion
    # the input state object is never mutated
    PP.promote(PP.set_challenger(s, "v2"), "v2", cycle=1)
    assert s["champion"] == "v1" and s["fallbacks"] == []


def test_rollback_returns_to_the_most_recent_fallback():
    s = PP.initial_state("v1")
    s = PP.promote(PP.set_challenger(s, "v2"), "v2", cycle=1)
    s = PP.promote(PP.set_challenger(s, "v3"), "v3", cycle=2)
    # fallbacks are [v1@1, v2@2]; rollback goes to v2 (undo the last promote)
    r = PP.rollback(s, cycle=3)
    assert r["champion"] == "v2"
    assert [f["version"] for f in r["fallbacks"]] == ["v1"]   # v2 consumed; v1 still retained


def test_rollback_raises_when_there_is_no_fallback():
    with pytest.raises(ValueError):
        PP.rollback(PP.initial_state("v1"), cycle=1)


def test_evictable_reports_only_fallbacks_past_the_retention_window():
    s = PP.initial_state("v1", retention_cycles=3)
    s = PP.promote(PP.set_challenger(s, "v2"), "v2", cycle=0)   # v1 demoted at cycle 0
    s = PP.promote(PP.set_challenger(s, "v3"), "v3", cycle=2)   # v2 demoted at cycle 2
    # at cycle 3: v1 (age 3 >= 3) is evictable; v2 (age 1) is not
    assert PP.evictable(s, cycle=3) == ["v1"]
    assert PP.evictable(s, cycle=2) == []              # nothing has aged out yet


def test_prune_is_the_only_path_that_drops_fallbacks_and_returns_deletable_versions():
    s = PP.initial_state("v1", retention_cycles=2)
    s = PP.promote(PP.set_challenger(s, "v2"), "v2", cycle=0)   # v1 @0
    s = PP.promote(PP.set_challenger(s, "v3"), "v3", cycle=1)   # v2 @1
    pruned, evicted = PP.prune(s, cycle=3)             # v1 age 3>=2 out; v2 age 2>=2 out
    assert set(evicted) == {"v1", "v2"}
    assert pruned["fallbacks"] == []
    # a fallback still in-window survives prune
    s2 = PP.promote(PP.set_challenger(PP.initial_state("a", retention_cycles=5), "b"), "b", cycle=10)
    kept, ev = PP.prune(s2, cycle=11)                  # age 1 < 5
    assert ev == [] and [f["version"] for f in kept["fallbacks"]] == ["a"]


def test_active_versions_is_the_never_delete_set():
    s = PP.initial_state("v1")
    s = PP.promote(PP.set_challenger(s, "v2"), "v2", cycle=1)
    s = PP.set_challenger(s, "v3")
    assert PP.active_versions(s) == {"v1", "v2", "v3"}   # champion + all fallbacks + challenger


def test_active_versions_keeps_a_falsy_but_set_challenger():
    # PR #220 review (the issue-#63 discipline): the never-delete set must use `is not None`, never
    # truthiness — a falsy-but-set challenger silently omitted here is exactly what would let a cleanup
    # delete an artifact a live pointer still references.
    s = {**PP.initial_state("v1"), "challenger": ""}
    assert "" in PP.active_versions(s)
    s2 = {**PP.initial_state("v1"), "challenger": None}   # genuinely unset stays excluded
    assert PP.active_versions(s2) == {"v1"}


def test_config_pointer_model_enforces_the_singleton_at_the_db_level():
    # PR #220 review: the singleton was an application convention only (_SINGLETON_ID threaded through
    # load/save); the model now carries a CHECK (id = 1) so a raw-SQL writer can't create a second row.
    from sqlalchemy import CheckConstraint
    from infrastructure.acquisition.stage5_filter.models import ConfigPointer
    checks = [c for c in ConfigPointer.__table__.constraints if isinstance(c, CheckConstraint)]
    assert any("id = 1" in str(c.sqltext) for c in checks)


# ----------------------------- artifact file store (tmp dir) -----------------------------
def test_write_artifact_is_idempotent_and_content_addressed(tmp_path):
    art = {"version": "abc123", "detector_params": {"x": 1}, "knobs": {}}
    p1 = PP.write_artifact(art, config_dir=tmp_path)
    assert p1.name == "abc123.json" and p1.exists()
    p2 = PP.write_artifact(art, config_dir=tmp_path)   # same version again -> idempotent, same path
    assert p1 == p2
    assert PP.read_artifact("abc123", config_dir=tmp_path)["detector_params"] == {"x": 1}


def test_write_artifact_refuses_a_corrupted_on_disk_version(tmp_path):
    # a file named for one version whose content claims another = immutability broken -> raise on rewrite.
    d = PP.artifacts_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "abc123.json").write_text(json.dumps({"version": "DIFFERENT"}))
    with pytest.raises(ValueError, match="immutability"):
        PP.write_artifact({"version": "abc123", "knobs": {}}, config_dir=tmp_path)


# ----------------------------- pointer state in the governance DB (atomic swap) -----------------------------
@pytest.mark.govdb
def test_pointer_state_round_trips_atomically_through_the_singleton_row(gov_session):
    con = gov_session
    con.execute(text("""CREATE TEMP TABLE config_pointer (id integer PRIMARY KEY, state_json text,
        updated_at text)"""))
    assert PP.load_state(con) is None                  # nothing initialized yet
    s = PP.initial_state("v1", retention_cycles=3)
    PP.save_state(con, s, updated_at="2026-07-10T00:00:00Z")
    assert PP.load_state(con) == s
    # a promote is one atomic upsert of the whole state (the swap)
    s2 = PP.promote(PP.set_challenger(s, "v2"), "v2", cycle=1)
    PP.save_state(con, s2, updated_at="2026-07-10T01:00:00Z")
    loaded = PP.load_state(con)
    assert loaded["champion"] == "v2"
    assert loaded["fallbacks"] == [{"version": "v1", "demoted_at_cycle": 1}]
