"""ONE home for benchmark-provenance test seeding (#661).

PRs #641/#648 added benchmark-provenance tests in five files, and each hand-wrote the same raw SQL:
the 13-column `INSERT INTO handoff` literal in three of them, the `record` + `capture` pair in three,
the `extraction` + `school_fact` chain in two. A schema change to any of those tables — a new NOT
NULL column, a rename — meant finding every copy by hand, and missing one leaves a test that either
breaks confusingly or, worse, passes against the wrong shape. The epic's own `_PRECIOUS_ALTERS`
parity lesson (CLAUDE.md, 2026-07-26) is that class of divergence biting on CI only.

It is a plain module rather than `conftest.py` fixtures on purpose: callers need these at different
grains (some hold a session, some open their own; some want one rep, some a whole run), and a
function you call is composable in a way an injected fixture is not.

These write PRECIOUS tables, so every caller is `@govdb` and runs inside a transaction the fixture
rolls back. `ensure_schema` is idempotent and safe to call per-test.
"""
import json

from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import db as gdb

# Seeded rows use these so a stray one is obvious in a live DB and never collides with real data.
TEST_URL = "http://x/{hash}"


def ensure_schema(session):
    """The signal + cache schemas these helpers write into, on the CALLER'S session. Idempotent.

    Deliberately does NOT call `gdb.init_precious_schema()`: that opens its own connection and issues
    DDL, so calling it from inside a caller's open transaction deadlocks against the locks that
    transaction already holds (observed while consolidating these helpers — the suite hung rather
    than failed). Callers do it once, before the seeding, exactly as they always have."""
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    BS.ensure_signal_schema(session)
    CI.ensure_cache_schema(session)


def seed_rep(session, district_id, rec_key, hash_, source):
    """One representation: a `record` and the `capture` behind it, joined on (district_id, hash) —
    the real arm-2 provenance path. `source='benchmark_gt'` (BM.BENCHMARK_CAPTURE_SOURCE) is what
    makes a rep injected; anything else ('discovered') is ordinary work."""
    url = TEST_URL.format(hash=hash_)
    session.execute(text("INSERT INTO record (rec_key, district_id, url, hash, tier) "
                         "VALUES (:k, :d, :u, :h, 'A') ON CONFLICT (rec_key) DO NOTHING"),
                    {"k": rec_key, "d": district_id, "u": url, "h": hash_})
    session.execute(text("INSERT INTO capture (district_id, hash, url, ok, kind, source) "
                         "VALUES (:d, :h, :u, 1, 'html', :s) "
                         "ON CONFLICT (district_id, hash) DO UPDATE SET source = EXCLUDED.source"),
                    {"d": district_id, "h": hash_, "u": url, "s": source})
    session.flush()


def seed_handoff(session, handoff_hash, *, dispatch_type=BM.DISPATCH_PRODUCTION, status="dispatched",
                 handoff_id=None, district_ids=(), council_ids=()):
    """One `handoff` index row — arm 1's whole basis. Returns the handoff_id.

    THE column list lives here and nowhere else. It was copied five times across the suite, and
    `dispatch_type` is a _PRECIOUS_ALTERS column, so a drift here is exactly the fresh-vs-migrated
    divergence the parity test exists for — the copies that OMITTED the column were relying on a
    server_default that a fresh `create_all()` DB did not have until PR #641 fixed it."""
    hid = handoff_id or f"handoff_{handoff_hash}_t"
    session.execute(text(
        "INSERT INTO handoff (handoff_id, handoff_hash, created_at, created_by, status, path, "
        "dispatch_type, n_districts, n_reps, total_usd, cost_provenance, district_ids, council_ids) "
        "VALUES (:hid, :hh, 'now', 'zz', :st, '/zz/x.json', :dt, 1, 1, 0.0, 'zz', "
        "CAST(:di AS json), CAST(:ci AS json))"),
        {"hid": hid, "hh": handoff_hash, "st": status, "dt": dispatch_type,
         "di": json.dumps(list(district_ids)), "ci": json.dumps(list(council_ids))})
    session.flush()
    return hid


def seed_extraction(session, handoff_hash, district_id, *, run_kind="production"):
    """One `extraction` row against a handoff. Returns the extraction_id.

    `extraction` is append-only ("a re-run is a new row"), which is why several of these against one
    (handoff_hash, district_id) is a legitimate — and load-bearing — thing for a test to construct."""
    eid = session.execute(text(
        "INSERT INTO extraction (handoff_hash, district_id, run_kind, created_at, created_by, "
        "n_reps, n_calls, n_judge_calls, n_errors, prompt_tokens, completion_tokens, cost_usd, "
        "n_accepted, n_unresolved) VALUES (:hh, :d, :rk, 'now', 'zz', 1, 1, 0, 0, 0, 0, 0.0, 1, 0) "
        "RETURNING extraction_id"), {"hh": handoff_hash, "d": district_id, "rk": run_kind}).scalar()
    session.flush()
    return eid


def seed_fact(session, extraction_id, district_id, rec_key, *, band="elementary", school="oak",
              status="accepted", gross_minutes=None, school_year=None):
    """One `school_fact`. Returns the fact_id.

    `school_year` defaults to NULL because that is the measured state of the real corpus (957 of 957
    accepted benchmark facts carry no parsed year, #662) — a test that wants the #254 year-supersede
    rule to engage must say so explicitly, rather than getting it by a convenient default."""
    fid = session.execute(text(
        "INSERT INTO school_fact (extraction_id, district_id, band, school, status, rec_key, "
        "gross_minutes, school_year, created_at, human_determination) "
        "VALUES (:e, :d, :b, :s, :st, :k, :g, :y, 'now', '') RETURNING fact_id"),
        {"e": extraction_id, "d": district_id, "b": band, "s": school, "st": status, "k": rec_key,
         "g": gross_minutes, "y": school_year}).scalar()
    session.flush()
    return fid


def seed_run(session, district_id, *, rec_key, hash_, source, dispatch_type=BM.DISPATCH_PRODUCTION,
             run_kind="production", handoff_hash=None, gross_minutes=None, school_year=None,
             band="elementary", school="oak"):
    """A whole run over one rep: rep -> handoff -> extraction -> accepted fact.

    Returns `(extraction_id, fact_id)`. This is the shape almost every provenance test wants; the
    per-table helpers above are for the ones that need to vary one link (two runs against the same
    handoff, a handoff with no extraction, a fact with no capture behind it)."""
    seed_rep(session, district_id, rec_key, hash_, source)
    hh = handoff_hash or f"zzh{hash_}"
    seed_handoff(session, hh, dispatch_type=dispatch_type)
    eid = seed_extraction(session, hh, district_id, run_kind=run_kind)
    fid = seed_fact(session, eid, district_id, rec_key, band=band, school=school,
                    gross_minutes=gross_minutes, school_year=school_year)
    return eid, fid
