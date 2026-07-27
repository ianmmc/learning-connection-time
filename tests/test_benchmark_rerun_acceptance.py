"""epic #617 / #662 — THE acceptance test: a district with benchmark history, re-run honestly.

This is the property the epic has claimed since §7a of the findings report and has never once been
executable: seed a district whose only prior facts came from injected curated-GT representations,
run it again over ordinary discovered representations, and assert the fresh work reaches production.

It is written as one test PER LAYER, because for most of this epic the layers did not agree and the
whole point of #662 is that the disagreement was invisible:

  layer                       before #662                          after
  --------------------------  -----------------------------------  ----------------------------
  gate@8 review queue         the DISTRICT, over all history       admits the re-run
  merge_fact_runs             all production facts, earliest-wins  the FRESH fact wins
  Stage 9's write wall        THIS receipt's write-bearing reps    admits (unchanged — it was right)

Only the third moved when #619 re-keyed the wall from district identity to provenance: #619 changed
the GRAIN (district -> provenance) but not the SCOPE ("ever" -> "this run"). #662 closed the other
two, decided by Ian 2026-07-26 as (c) + (b):

  (c) the historical harness extractions are reclassified out of `run_kind='production'` — they ran
      the council over INJECTED reps and were never release data. One change drops them from the
      queue predicate, the closing-argument pool, and the wall at once. That is what the first two
      tests below now assert, by seeding the old run the way the migration leaves it.
  (b) `merge_fact_runs` gains a PROVENANCE axis ahead of the year axis, so honest production work
      supersedes an injected artifact for the same school. Post-(c) nothing in production can reach
      that path (gate@6 refuses a production freeze holding an injected rep, #644), so it is defence
      in depth — the merge's correctness no longer depends on that guard being perfect. Tested
      directly, at the bottom of this file.

The two front-layer tests were STRICT xfails until the fix landed; git history holds them failing.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.maintenance import reclassify_benchmark_extractions as RCLS
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


def _seed_rep_only(s, rec_key, hash_, source):
    """A representation with no run behind it — for constructing a MIXED extraction by hand."""
    s.execute(text("INSERT INTO record (rec_key, district_id, url, hash, tier) "
                   "VALUES (:k, :d, :u, :h, 'A') ON CONFLICT (rec_key) DO NOTHING"),
              {"k": rec_key, "d": DID, "u": f"http://x/{hash_}", "h": hash_})
    s.execute(text("INSERT INTO capture (district_id, hash, url, ok, kind, source) "
                   "VALUES (:d, :h, :u, 1, 'html', :s) "
                   "ON CONFLICT (district_id, hash) DO UPDATE SET source = EXCLUDED.source"),
              {"d": DID, "h": hash_, "u": f"http://x/{hash_}", "s": source})
    s.flush()


def _seed_the_rerun(s, monkeypatch=None, *, migrate=True):
    """The whole scenario: the benchmark-vintage run, then the honest re-run over a fresh rep, and
    then #662's migration — the real sequence, not a simulation of its outcome.

    Both runs are seeded `run_kind='production'` with a `production` dispatch, because that IS the
    shape of the batch_00000 history: those extractions predate run_kind (#148) and its
    `DEFAULT 'production'` swept them in. Nothing about them was ever stamped benchmark; the old run
    is benchmark WORK only by virtue of its representations (arm 2).

    `migrate=True` then runs `reclassify_benchmark_extractions` for real, so these tests exercise the
    migration rather than assuming it. `migrate=False` is the pre-fix state, for the (b) tests that
    need an injected fact to survive INTO the production pool.
    """
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    BS.ensure_signal_schema(s)
    CI.ensure_cache_schema(s)
    old = _run(s, rec_key=OLD_REC, hash_=OLD_HASH, source=BM.BENCHMARK_CAPTURE_SOURCE, gross=400)
    new = _run(s, rec_key=NEW_REC, hash_=NEW_HASH, source="discovered", gross=420)
    if migrate:
        # never write receipts into the real captures tree from a test; the receipt CONTENT has its
        # own test below.
        monkeypatch.setattr(RCLS, "_write_receipts", lambda sess, clean: [])
        summary = RCLS.reclassify(s, apply=True)
        # The govdb fixture runs against the REAL governance DB inside a rolled-back transaction, so
        # this sweep legitimately also picks up the live historical rows. Assert the PROPERTY, not a
        # count that depends on when you run it: the injected run is swept, the honest one never is.
        assert summary["applied"]
        assert old[0] in summary["extraction_ids"], "the injected run must be reclassified"
        assert new[0] not in summary["extraction_ids"], (
            "the FRESH production run must never be swept — that would re-wall the district")
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
def test_the_rerun_district_reaches_the_gate8_queue(gov_session, monkeypatch):
    """gate@8 is the ONLY door to a Stage-9 write, so this is the first thing that had to give.

    The queue applies `NOT IS_BENCHMARK_PROVENANCE_SQL` (server.py::aggregate_districts), whose both
    arms are scoped to `run_kind='production'`. Before #662 the old harness extraction WAS production,
    so arm 2 saw its benchmark_gt capture and the EXISTS fired forever — `extraction`/`school_fact`
    are append-only ("a re-run is a new row"), so no fresh run could ever retract it. Reclassifying
    that extraction takes it out of the predicate's scope entirely.

    The queue's other clauses (quiesced request loop, n_accepted > 0) are not under test here; the
    provenance fragment alone is what refused.
    """
    gdb.init_precious_schema()
    s = gov_session
    _seed_the_rerun(s, monkeypatch)
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
def test_the_closing_argument_is_built_on_the_fresh_facts(gov_session, monkeypatch):
    """Even granted the queue, the number gate@8 would approve was the OLD one.

    `merge_fact_runs` is fill-gaps-never-overwrite by design (REQ-122 — a thin follow-up must not
    knock out a solid earlier extraction, the Brownsville 7->0 case) and the earliest run wins. That
    rule is right for two honest runs and was wrong here: the earlier run is not merely older, it is
    a DIFFERENT KIND of work. It could not be beaten on the year axis either, because that axis
    compares only two KNOWN years and 957 of 957 injected facts carry none.

    Post-(c) the injected run is not in the pool at all — `closing_argument` selects
    `WHERE e.run_kind = 'production'`. The merge never sees it, which is why (c) is the cheaper half
    of the fix. (b) covers the case where one slips in anyway; see the bottom of this file.
    """
    gdb.init_precious_schema()
    s = gov_session
    (_old_eid, _old_fid), (_new_eid, new_fid) = _seed_the_rerun(s, monkeypatch)

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
    (_old_eid, old_fid), (_new_eid, new_fid) = _seed_the_rerun(s, migrate=False)

    assert BM.is_benchmark_provenance(s, rec_keys=[NEW_REC], fact_ids=[new_fid]) is False
    # and the wall still holds where it should: a receipt carrying the injected rep is refused
    assert BM.is_benchmark_provenance(s, rec_keys=[OLD_REC], fact_ids=[old_fid]) is True


@govdb
def test_the_three_layers_now_agree(gov_session, monkeypatch):
    """The finding, inverted. Asked about the SAME district in the SAME state, the queue and the
    receipt-scoped wall must give the SAME answer about fresh work — that they did not was #662.

    This is the assertion §10.20 says had never been checkable: every prior measurement of "the
    grains agree" was taken in the pre-#620 state, which is the one state where the layers cannot
    disagree. Here they are asked about a district that has actually been re-run.
    """
    gdb.init_precious_schema()
    s = gov_session
    (_old_eid, _old_fid), (_new_eid, new_fid) = _seed_the_rerun(s, monkeypatch)
    s.execute(text("CREATE TEMP TABLE zz_split (district_id text) ON COMMIT DROP"))
    s.execute(text("INSERT INTO zz_split VALUES (:d)"), {"d": DID})

    queue_refuses = bool(s.execute(text(
        f"SELECT 1 FROM zz_split p "
        f"WHERE {BM.IS_BENCHMARK_PROVENANCE_SQL.format(alias='p')}")).first())
    wall_refuses = BM.is_benchmark_provenance(s, rec_keys=[NEW_REC], fact_ids=[new_fid])

    assert queue_refuses is False and wall_refuses is False, (
        "the district-scoped queue and the receipt-scoped wall disagree about the same fresh work — "
        "one of them is asking the wrong question (#662)")


# ------------------ (b): provenance precedence in the merge, defence in depth ------------------
# Post-(c) nothing in production reaches this path — the historical harness runs are reclassified out
# of the pool, and gate@6 REFUSES a production freeze holding an injected rep (#618/#644). So this is
# the merge's own guarantee, deliberately independent of that guard being perfect: a future injection
# mechanism (a new GT corpus, a different `capture.source`) would otherwise re-create #662 silently.
# It is constructible directly, which is the standard §10.19 sets — do not justify a rule by a future
# case without building the case.


def test_honest_work_supersedes_an_injected_fact_for_the_same_school():
    """The axis runs BEFORE the year axis on purpose. An injected `gt://` artifact carries a
    deliberately-older curated year and was never release data, so it must lose whatever either side's
    year says — and it cannot be beaten on the year axis anyway, since 957 of 957 carry none."""
    old = {"fact_id": 1, "extraction_id": 1, "band": "elementary", "school": "oak",
           "status": "accepted", "school_year": None, "gross_minutes": 400,
           "benchmark_provenance": True}
    fresh = {"fact_id": 2, "extraction_id": 2, "band": "elementary", "school": "oak",
             "status": "accepted", "school_year": None, "gross_minutes": 420,
             "benchmark_provenance": False}
    accepted, _unresolved, superseded = merge_fact_runs([old, fresh], with_superseded=True)

    assert [f["fact_id"] for f in accepted] == [2]
    assert [f["fact_id"] for f in superseded] == [1], (
        "the losing row must be KEPT and surfaced, never silently dropped — no-silent-caps")


def test_provenance_beats_a_NEWER_year_on_the_injected_side():
    """The ordering of the two axes, pinned. If the year axis ran first, an injected artifact that
    happens to print a recent year would beat honest work — which is exactly backwards."""
    old = {"fact_id": 1, "extraction_id": 1, "band": "high", "school": "oak", "status": "accepted",
           "school_year": "2025-26", "gross_minutes": 400, "benchmark_provenance": True}
    fresh = {"fact_id": 2, "extraction_id": 2, "band": "high", "school": "oak", "status": "accepted",
             "school_year": "2023-24", "gross_minutes": 420, "benchmark_provenance": False}
    accepted, _u = merge_fact_runs([old, fresh])
    assert [f["fact_id"] for f in accepted] == [2]


def test_an_all_injected_group_is_left_alone_not_emptied():
    """A school covered ONLY by injected evidence keeps its fact rather than vanishing from the band.
    Dropping it would silently shrink the sample, and the Stage-9 wall — which reads the receipt's
    write-bearing reps — is the layer that must refuse that write, loudly and as a whole."""
    a = {"fact_id": 1, "extraction_id": 1, "band": "high", "school": "oak", "status": "accepted",
         "school_year": None, "gross_minutes": 400, "benchmark_provenance": True}
    accepted, _u = merge_fact_runs([a])
    assert [f["fact_id"] for f in accepted] == [1]


def test_the_axis_is_inert_for_callers_that_do_not_set_the_key():
    """Every pre-#662 caller passes rows with no `benchmark_provenance` key at all. They must merge
    byte-identically to before — this axis is additive, never a behaviour change for honest work."""
    rows = [{"fact_id": 1, "extraction_id": 1, "band": "high", "school": "oak", "status": "accepted",
             "school_year": None, "gross_minutes": 400},
            {"fact_id": 2, "extraction_id": 2, "band": "high", "school": "oak", "status": "accepted",
             "school_year": None, "gross_minutes": 420}]
    accepted, _u = merge_fact_runs(rows)
    assert [f["fact_id"] for f in accepted] == [1]      # earliest-run wins, exactly as before


# ------------------------------- the migration's own guarantees -------------------------------

@govdb
def test_the_migration_refuses_a_mixed_extraction_rather_than_guessing(gov_session):
    """`extraction.run_kind` is a coarser unit than the per-fact representation that triggers this, so
    an extraction holding BOTH injected and discovered facts cannot be reclassified without dropping
    genuine work. It REFUSES, naming the rows — REQ-169's refuse-don't-coerce criterion, the same
    posture as gate@6's freeze guard. (No such extraction exists today: measured 0 of 30.)"""
    gdb.init_precious_schema()
    s = gov_session
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    BS.ensure_signal_schema(s)
    CI.ensure_cache_schema(s)
    eid, _fid = _run(s, rec_key=OLD_REC, hash_=OLD_HASH, source=BM.BENCHMARK_CAPTURE_SOURCE, gross=400)
    _seed_rep_only(s, NEW_REC, NEW_HASH, "discovered")
    s.execute(text(                                     # a second, DISCOVERED fact on the SAME run
        "INSERT INTO school_fact (extraction_id, district_id, band, school, status, rec_key, "
        "gross_minutes, created_at, human_determination) VALUES (:e, :d, 'high', 'elm', 'accepted', "
        ":k, 420, 'now', '')"), {"e": eid, "d": DID, "k": NEW_REC})
    s.flush()

    with pytest.raises(ValueError, match="REFUSING"):
        RCLS.reclassify(s, apply=True)
    assert s.execute(text("SELECT run_kind FROM extraction WHERE extraction_id = :e"),
                     {"e": eid}).scalar() == "production", "a refused run must not be half-migrated"


@govdb
def test_the_migration_is_idempotent(gov_session, monkeypatch):
    """Re-running finds nothing: the rows are no longer `production`, so the candidate query is empty.
    A migration that is not safe to run twice is a migration nobody dares run once."""
    gdb.init_precious_schema()
    s = gov_session
    _seed_the_rerun(s, monkeypatch)                     # already applies it once
    again = RCLS.reclassify(s, apply=True)
    assert again["n_clean"] == 0 and again["applied"] is False


@govdb
def test_reclassify_groups_extraction_ids_by_district_without_a_requery(gov_session, monkeypatch):
    """Review finding: `main()`'s per-district printout used to re-run the full 4-table-JOIN candidate
    query once per district — O(N) redundant scans of already-computed data — and did it only on the
    branch that never fires on --apply (the run that matters), so the one live production run's
    breakdown never printed at all. `reclassify()` now returns the grouping directly."""
    gdb.init_precious_schema()
    s = gov_session
    (_old_eid, _old_fid), _new = _seed_the_rerun(s, migrate=False)
    summary = RCLS.reclassify(s, apply=False)
    assert summary["extraction_ids_by_district"].get(DID) == [_old_eid]
    assert summary["districts"] == sorted(summary["extraction_ids_by_district"])


@govdb
def test_the_receipt_names_every_row_and_its_prior_value(gov_session, monkeypatch):
    """The restore point. Commandment #1 is auditability, and the working convention is a manifest
    before a destructive op — so the receipt must carry enough to reconstruct the change without the
    DB: which extraction, from which handoff, what its run_kind WAS, and how many facts it held."""
    gdb.init_precious_schema()
    s = gov_session
    captured = {}
    monkeypatch.setattr(RCLS.RCPT, "write_receipt",
                        lambda did, name, base, payload, **k: captured.setdefault(did, payload) or "/x")
    _seed_the_rerun(s, migrate=False)
    RCLS.reclassify(s, apply=True)

    r = captured[DID]
    assert r["from_run_kind"] == "production" and r["to_run_kind"] == RCLS.RUN_KIND_BENCHMARK
    assert r["issue"] == "#662"
    ex = r["extractions"][0]
    assert ex["prior_run_kind"] == "production" and ex["n_other_facts"] == 0
    assert ex["n_injected_facts"] >= 1 and ex["extraction_id"] and ex["handoff_hash"]
