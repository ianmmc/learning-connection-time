"""epic #617 / #662 — THE acceptance test: a district with benchmark history, re-run honestly.

This is the property the epic has claimed since §7a of the findings report and has never once been
executable: seed a district whose only prior facts came from injected curated-GT representations,
run it again over ordinary discovered representations, and assert the fresh work reaches production.

It is deliberately written as THREE tests, one per layer, because the layers do not agree and the
whole point of #662 is that the disagreement was invisible:

  layer                       grain today                          verdict
  --------------------------  -----------------------------------  ----------------------------
  gate@8 review queue         the DISTRICT, over all history       REFUSES forever    (xfail)
  merge_fact_runs             all production facts, earliest-wins  OLD fact wins      (xfail)
  Stage 9's write wall        THIS receipt's write-bearing reps    admits             (passes)

Only the third moved when #619 re-keyed the wall from district identity to provenance. #619 changed
the GRAIN (district -> provenance) but not the SCOPE ("ever" -> "this run"), and the two layers in
front of the wall are still scoped to all of history — so an honestly re-run district still cannot
incorporate. See findings report §10.20 and §11.4.

The two xfails are `strict=True` ON PURPOSE. When #662's supersession mechanism lands they become
XPASS, which pytest reports as a FAILURE — the fix cannot land quietly, and the markers cannot be
left behind. Do not relax them to non-strict; the whole defect class this epic keeps re-learning is
"a guard measured green in the one state where it could not fail" (§10.19).
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage8_aggregate.aggregate import merge_fact_runs

govdb = pytest.mark.govdb

DID = "ZZRERUN"
OLD_REC, OLD_HASH = "ZZRERUN:gt", "zzrerungt"      # the injected curated-GT PDF
NEW_REC, NEW_HASH = "ZZRERUN:web", "zzrerunweb"    # an ordinary discovered bell-schedule page


def _run(s, *, rec_key, hash_, source, gross, dispatch_type=BM.DISPATCH_PRODUCTION):
    """One honest production run over one representation: record + capture (the provenance chain),
    a dispatched handoff, an extraction, and one accepted fact. Returns (extraction_id, fact_id).

    `school_year` is left NULL on both runs, which is not a shortcut — it is the measured state of
    the corpus: 957 of 957 accepted benchmark facts carry no parsed year (#662), which is precisely
    why merge_fact_runs' year-supersede rule never engages on the real data.
    """
    s.execute(text("INSERT INTO record (rec_key, district_id, url, hash, tier) "
                   "VALUES (:k, :d, :u, :h, 'A') ON CONFLICT (rec_key) DO NOTHING"),
              {"k": rec_key, "d": DID, "u": f"http://x/{hash_}", "h": hash_})
    s.execute(text("INSERT INTO capture (district_id, hash, url, ok, kind, source) "
                   "VALUES (:d, :h, :u, 1, 'html', :s) "
                   "ON CONFLICT (district_id, hash) DO UPDATE SET source = EXCLUDED.source"),
              {"d": DID, "h": hash_, "u": f"http://x/{hash_}", "s": source})
    hh = f"zzh{hash_}"
    s.execute(text(
        "INSERT INTO handoff (handoff_id, handoff_hash, created_at, created_by, status, path, "
        "dispatch_type, n_districts, n_reps, total_usd, cost_provenance, district_ids, council_ids) "
        "VALUES (:hid, :hh, 'now', 'zz', 'dispatched', '/zz/x.json', :dt, 1, 1, 0.0, 'zz', "
        "'[]', '[]')"), {"hid": f"handoff_{hh}_t", "hh": hh, "dt": dispatch_type})
    eid = s.execute(text(
        "INSERT INTO extraction (handoff_hash, district_id, run_kind, created_at, created_by, "
        "n_reps, n_calls, n_judge_calls, n_errors, prompt_tokens, completion_tokens, cost_usd, "
        "n_accepted, n_unresolved) VALUES (:hh, :d, 'production', 'now', 'zz', 1, 1, 0, 0, 0, 0, "
        "0.0, 1, 0) RETURNING extraction_id"), {"hh": hh, "d": DID}).scalar()
    fid = s.execute(text(
        "INSERT INTO school_fact (extraction_id, district_id, band, school, status, rec_key, "
        "gross_minutes, created_at, human_determination) VALUES (:e, :d, 'elementary', 'oak', "
        "'accepted', :k, :g, 'now', '') RETURNING fact_id"),
        {"e": eid, "d": DID, "k": rec_key, "g": gross}).scalar()
    s.flush()
    return eid, fid


def _seed_the_rerun(s):
    """The whole scenario: the benchmark-vintage run, then the honest re-run over a fresh rep.

    Both dispatches are `production` — that is the real shape of the batch_00000 history. The old
    run is benchmark WORK only by virtue of its representations (arm 2), never by a stamp.
    """
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    BS.ensure_signal_schema(s)
    CI.ensure_cache_schema(s)
    old = _run(s, rec_key=OLD_REC, hash_=OLD_HASH, source=BM.BENCHMARK_CAPTURE_SOURCE, gross=400)
    new = _run(s, rec_key=NEW_REC, hash_=NEW_HASH, source="discovered", gross=420)
    return old, new


def _production_facts(s):
    """Exactly the query closing_argument._band_claims runs (stage8_aggregate/closing_argument.py):
    every production fact for the district, pooled, with no notion of which run is current."""
    return [dict(r._mapping) for r in s.execute(text("""
        SELECT f.*, e.run_kind FROM school_fact f
          JOIN extraction e ON e.extraction_id = f.extraction_id
         WHERE f.district_id = :d AND e.run_kind = 'production'
         ORDER BY f.extraction_id, f.fact_id"""), {"d": DID}).all()]


# ------------------------------- layer 1: the gate@8 review queue -------------------------------

@govdb
@pytest.mark.xfail(strict=True, reason="#662: the gate@8 queue predicate is district-scoped over "
                                       "ALL history, so a benchmark-history district is refused "
                                       "the queue forever and the Stage-9 fix stays unreachable")
def test_the_rerun_district_reaches_the_gate8_queue(gov_session):
    """gate@8 is the ONLY door to a Stage-9 write, so this is the first thing that must give.

    The queue applies `NOT IS_BENCHMARK_PROVENANCE_SQL` (server.py::aggregate_districts). Asked of
    THIS district it is permanently true: arm 2 sees the old benchmark_gt capture behind a fact that
    `extraction`/`school_fact` — both append-only, "a re-run is a new row" — can never retract.

    The queue's other clauses (quiesced request loop, n_accepted > 0) are not under test here; the
    provenance fragment alone is what refuses, and it is the fragment #619 installed.
    """
    gdb.init_precious_schema()
    s = gov_session
    _seed_the_rerun(s)
    s.execute(text("CREATE TEMP TABLE zz_queue (district_id text) ON COMMIT DROP"))
    s.execute(text("INSERT INTO zz_queue VALUES (:d)"), {"d": DID})

    admitted = {r[0] for r in s.execute(text(
        f"SELECT district_id FROM zz_queue p "
        f"WHERE NOT {BM.IS_BENCHMARK_PROVENANCE_SQL.format(alias='p')}"))}
    assert admitted == {DID}, (
        "a district whose fresh production run used ordinary discovered reps must reach gate@8; "
        "its benchmark past is a property of the OLD work, not of the district")


# ---------------------------- layer 2: what the closing argument reads ----------------------------

@govdb
@pytest.mark.xfail(strict=True, reason="#662: merge_fact_runs pools every production fact and the "
                                       "earliest run wins; with school_year NULL on both (957/957 "
                                       "of the real corpus) the year-supersede rule never engages, "
                                       "so the injected benchmark fact beats the fresh one")
def test_the_closing_argument_is_built_on_the_fresh_facts(gov_session):
    """Even granted the queue, the number gate@8 would approve is the OLD one.

    `merge_fact_runs` is fill-gaps-never-overwrite by design (REQ-122 — a thin follow-up must not
    knock out a solid earlier extraction, the Brownsville 7->0 case). That rule is right for two
    honest runs and wrong here: the earlier run is not merely older, it is a DIFFERENT KIND of work.
    Provenance is the distinction the merge cannot currently see — which is the mechanism #662 asks
    Ian to choose (reclassify the historical run_kind, and/or teach the merge provenance precedence).
    """
    gdb.init_precious_schema()
    s = gov_session
    (_old_eid, _old_fid), (_new_eid, new_fid) = _seed_the_rerun(s)

    accepted, _unresolved = merge_fact_runs(_production_facts(s))
    assert [f["fact_id"] for f in accepted] == [new_fid], (
        "the surviving fact for (elementary, oak) must be the fresh run's; a benchmark-provenance "
        "fact must never outrank honestly-sourced minutes for the same school")
    assert accepted[0]["gross_minutes"] == 420


# ------------------------------- layer 3: Stage 9's own write wall -------------------------------

@govdb
def test_stage9_admits_a_receipt_whose_write_bearing_reps_are_fresh(gov_session):
    """The one layer that is already correct — #619's two-arm predicate, asked receipt-scoped.

    Stage 9 passes the APPROVED receipt's write-bearing schools (`bands[*].schools[*].rec_key` /
    `fact_id`, incorporate.py::_is_benchmark_receipt), so it asks about THIS run's evidence and
    nothing else. It admits, and would admit today — which is exactly why the epic measured green:
    every prior measurement was taken before a re-run existed to disagree about (§10.20).
    """
    gdb.init_precious_schema()
    s = gov_session
    (_old_eid, old_fid), (_new_eid, new_fid) = _seed_the_rerun(s)

    assert BM.is_benchmark_provenance(s, rec_keys=[NEW_REC], fact_ids=[new_fid]) is False
    # and the wall still holds where it should: a receipt carrying the injected rep is refused
    assert BM.is_benchmark_provenance(s, rec_keys=[OLD_REC], fact_ids=[old_fid]) is True


@govdb
def test_the_three_layers_disagree_which_is_the_defect(gov_session):
    """The finding itself, pinned: asked about the SAME district in the SAME state, the write wall
    says admit and the queue says refuse. Whatever mechanism #662 lands, it must collapse this — and
    when it does, this test's `queue_refuses` assertion is what has to be inverted, deliberately.
    """
    gdb.init_precious_schema()
    s = gov_session
    (_old_eid, _old_fid), (_new_eid, new_fid) = _seed_the_rerun(s)
    s.execute(text("CREATE TEMP TABLE zz_split (district_id text) ON COMMIT DROP"))
    s.execute(text("INSERT INTO zz_split VALUES (:d)"), {"d": DID})

    queue_refuses = bool(s.execute(text(
        f"SELECT 1 FROM zz_split p "
        f"WHERE {BM.IS_BENCHMARK_PROVENANCE_SQL.format(alias='p')}")).first())
    wall_refuses = BM.is_benchmark_provenance(s, rec_keys=[NEW_REC], fact_ids=[new_fid])

    assert queue_refuses is True and wall_refuses is False, (
        "#662: the district-scoped queue and the receipt-scoped wall must not disagree about the "
        "same fresh work — one of them is asking the wrong question")
