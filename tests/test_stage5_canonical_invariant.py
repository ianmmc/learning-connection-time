"""#158 — the canonical-record invariant: a MULTI-MEMBER cluster's REPRESENTATIVE must not itself
carry duplicate_of, or release's CANONICAL_RECORD_WHERE matches NEITHER member and the whole cluster
is silently dropped from dispatch (the Marion bell-table recall loss).

Scope subtlety (the review catch): singletons ALSO carry is_cluster_rep=1 — cluster_district emits
(None, 1, 1) — and a singleton WITH duplicate_of is the legitimate shape of an unclustered exact
content-dup (suppressed while its first-seen partner is canonical). The invariant, detector, and
repair are therefore scoped to cluster_id IS NOT NULL; clearing singleton duplicate_of would wipe
content-hash dedup on every re-ingest.

Exercises the detector + repair (`build_signals.canonical_invariant_violations` /
`repair_canonical_invariant`) and the release predicate against the real governance engine via a
connection-scoped TEMP `record` table (gov_session — never touches real data). Skips if Docker is down.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.stage5_filter.release import CANONICAL_RECORD_WHERE

pytestmark = [pytest.mark.integration, pytest.mark.govdb]


def _temp_record(s):
    s.execute(text("""CREATE TEMP TABLE record (
        rec_key text PRIMARY KEY, district_id text, cluster_id text,
        is_cluster_rep integer, cluster_size integer, duplicate_of text)"""))


def _add(s, rec_key, cluster_id, is_rep, dup_of=None, size=1):
    s.execute(text("INSERT INTO record (rec_key, district_id, cluster_id, is_cluster_rep, "
                   "cluster_size, duplicate_of) VALUES (:k,'d1',:c,:r,:sz,:d)"),
              {"k": rec_key, "c": cluster_id, "r": is_rep, "sz": size, "d": dup_of})


def _canonical_keys(s):
    return {r[0] for r in s.execute(text(
        f"SELECT rec_key FROM record r WHERE {CANONICAL_RECORD_WHERE}"))}


def test_singletons_emit_is_rep_one():
    """Documents WHY the invariant must scope to multi-member clusters: cluster_district gives
    singletons (None, 1, 1) — is_cluster_rep=1 with no cluster — so 'is_rep=1 AND duplicate_of set'
    alone does NOT identify a broken cluster rep."""
    out = BS.cluster_district([("d1:solo", BS.shingles("some unique text here"), "A", 5.0)], set())
    assert out == {"d1:solo": (None, 1, 1)}


def test_inverted_cluster_flags_drop_the_whole_cluster(gov_session):
    """The bug shape: rep has duplicate_of set, the dup_of-null sibling is is_rep=0 -> NO member is
    canonical -> the cluster (its bell table) never reaches dispatch."""
    _temp_record(gov_session)
    # cluster c0: the rep points its duplicate_of at the sibling (the Marion inversion)
    _add(gov_session, "d1:rep", "d1:c0", is_rep=1, dup_of="d1:sib", size=2)
    _add(gov_session, "d1:sib", "d1:c0", is_rep=0, dup_of=None, size=2)

    assert BS.canonical_invariant_violations(gov_session) == ["d1:rep"]
    assert _canonical_keys(gov_session) == set()          # NEITHER member canonical — cluster dropped


def test_repair_restores_exactly_one_canonical_member(gov_session):
    _temp_record(gov_session)
    _add(gov_session, "d1:rep", "d1:c0", is_rep=1, dup_of="d1:sib", size=2)
    _add(gov_session, "d1:sib", "d1:c0", is_rep=0, dup_of=None, size=2)

    n = BS.repair_canonical_invariant(gov_session)
    assert n == 1
    assert BS.canonical_invariant_violations(gov_session) == []
    assert _canonical_keys(gov_session) == {"d1:rep"}     # exactly one canonical, and it's the rep


def test_singleton_exact_dup_is_not_a_violation_and_keeps_its_dedup(gov_session):
    """A singleton content-dup (cluster NULL, is_rep=1 — the shape cluster_district actually writes,
    duplicate_of -> its first-seen partner) is LEGITIMATE: not flagged, not repaired, stays
    suppressed while the partner stays canonical. The repair must never wipe this dedup edge."""
    _temp_record(gov_session)
    _add(gov_session, "d1:first", None, is_rep=1, dup_of=None)        # first-seen: canonical
    _add(gov_session, "d1:dup", None, is_rep=1, dup_of="d1:first")    # exact dup: suppressed

    assert BS.canonical_invariant_violations(gov_session) == []
    assert BS.repair_canonical_invariant(gov_session) == 0
    dup = gov_session.execute(text(
        "SELECT duplicate_of FROM record WHERE rec_key='d1:dup'")).scalar()
    assert dup == "d1:first"                              # dedup edge preserved
    assert _canonical_keys(gov_session) == {"d1:first"}   # content dispatched exactly once


def test_repair_is_idempotent_and_leaves_healthy_rows_untouched(gov_session):
    _temp_record(gov_session)
    _add(gov_session, "d1:rep", "d1:c0", is_rep=1, dup_of="d1:sib", size=2)   # broken
    _add(gov_session, "d1:sib", "d1:c0", is_rep=0, dup_of=None, size=2)
    _add(gov_session, "d1:hrep", "d1:c1", is_rep=1, dup_of=None, size=2)      # healthy cluster
    _add(gov_session, "d1:hsib", "d1:c1", is_rep=0, dup_of="d1:hrep", size=2)
    _add(gov_session, "d1:solo", None, is_rep=1, dup_of=None)                 # singleton
    _add(gov_session, "d1:dup", None, is_rep=1, dup_of="d1:solo")             # singleton exact-dup

    assert BS.repair_canonical_invariant(gov_session) == 1                    # only the broken rep
    assert BS.repair_canonical_invariant(gov_session) == 0                    # idempotent

    # every cluster + the singleton yields exactly its intended canonical; the singleton dup stays out
    assert _canonical_keys(gov_session) == {"d1:rep", "d1:hrep", "d1:solo"}
