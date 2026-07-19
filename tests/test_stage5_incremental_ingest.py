"""Incremental, batch-scoped Stage-5 ingest (the Stage-4 -> Stage-5 handoff).

`ingest_district` is the shared per-district unit of both the full `ingest()` and the incremental
`ingest_batch()`. Its two load-bearing incremental guarantees are tested here against the real
governance Postgres via CONNECTION-SCOPED TEMP tables (the gov_session fixture), so nothing touches
real governance data (safe even while the console is open):
  1. ISOLATION  — ingesting district B does not disturb district A's rows (the whole point of going
     incremental instead of the global DROP+rebuild).
  2. IDEMPOTENCY — re-ingesting the same district replaces its rows in place (no duplicates), and a
     human label on that district survives the re-ingest (the precious label table is never deleted).
"""
import json

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.stage5_filter import build_signals as BS

# #201: all 3 tests hit the governance DB via gov_session (CONNECTION-SCOPED TEMP tables) — mark govdb so
# they run in CI's governance-db job and are excluded from the DB-free job (was leaking as a skip).
pytestmark = pytest.mark.govdb

USABLE_TXT = "School begins at 8:20 AM and dismisses at 3:20 PM. " * 6  # > 120 printable chars


def _create_temp_schema(sess):
    """The derived signal tables + cache tables + a minimal precious-label table, all as connection-
    scoped TEMP (auto-dropped, invisible to other connections). The signal DDL is lifted verbatim from
    the production list so the test can't drift from the real schema."""
    for ddl in BS._SIGNAL_CREATE_DDL:
        sess.execute(text(ddl.strip().replace("CREATE TABLE IF NOT EXISTS ", "CREATE TEMP TABLE ", 1)))
    for ddl in CI.CACHE_DDL:
        sess.execute(text(ddl.strip().replace("CREATE TABLE IF NOT EXISTS ", "CREATE TEMP TABLE ", 1)))
    sess.execute(text("CREATE TEMP TABLE label (rec_key text PRIMARY KEY, status text DEFAULT 'unlabeled', "
                      "facets_json text)"))   # facets_json: read by the #109 human-page-range slice pass


def _seed(root, did, *, n_records=1):
    """A Stage-4-complete district dir: discovery + captures + processed + a usable page.txt per record."""
    d = root / f"{did}_d{did}"
    d.mkdir(parents=True)
    (d / "discovery.json").write_text(json.dumps(
        {"district_id": did, "name": f"D{did}", "state": "AK", "schools": []}))
    caps, procs = [], []
    for i in range(n_records):
        h = f"h{i}"
        rdir = d / "captures" / h
        rdir.mkdir(parents=True)
        (rdir / "page.txt").write_text(USABLE_TXT)
        caps.append({"hash": h, "url": f"http://{did}.org/{h}", "ok": True, "kind": "html",
                     "files": {"txt": "page.txt"}})
        procs.append({"hash": h, "url": f"http://{did}.org/{h}", "usable": True,
                      "texts": [{"source": "txt", "text_file": "page.txt", "n_chars": len(USABLE_TXT),
                                 "n_times": 2, "usable": True}]})
    (d / "captures.json").write_text(json.dumps(caps))
    (d / "processed.json").write_text(json.dumps(procs))
    return d


def _ingest(sess, ddir):
    return BS.ingest_district(sess, ddir, splits=set(), batches={}, nces={})


def _record_count(sess, did):
    return sess.execute(text("SELECT COUNT(*) FROM record WHERE district_id=:d"), {"d": did}).scalar()


def test_ingest_district_isolation(gov_session, tmp_path):
    """Ingesting B leaves A's rows untouched — the incremental guarantee that prior batches survive."""
    _create_temp_schema(gov_session)
    a = _seed(tmp_path, "111", n_records=2)
    b = _seed(tmp_path, "222", n_records=1)
    assert _ingest(gov_session, a) == "111"
    assert _record_count(gov_session, "111") == 2
    assert _ingest(gov_session, b) == "222"
    # B's ingest must not have disturbed A
    assert _record_count(gov_session, "111") == 2
    assert _record_count(gov_session, "222") == 1
    assert gov_session.execute(text("SELECT COUNT(*) FROM district")).scalar() == 2


def test_reingest_is_idempotent_and_preserves_labels(gov_session, tmp_path):
    """Re-ingesting a district replaces its rows in place (no dupes), and a human label survives."""
    _create_temp_schema(gov_session)
    a = _seed(tmp_path, "111", n_records=2)
    _ingest(gov_session, a)
    assert _record_count(gov_session, "111") == 2
    rep_before = gov_session.execute(text("SELECT COUNT(*) FROM representation")).scalar()

    # a human labels one of the records (precious; lives in the label table)
    rk = gov_session.execute(text("SELECT rec_key FROM record WHERE district_id='111' LIMIT 1")).scalar()
    gov_session.execute(text("UPDATE label SET status='labeled' WHERE rec_key=:rk"), {"rk": rk})

    # re-ingest the SAME district -> rows replaced, not duplicated
    _ingest(gov_session, a)
    assert _record_count(gov_session, "111") == 2                       # not 4
    assert gov_session.execute(text("SELECT COUNT(*) FROM representation")).scalar() == rep_before
    # the label was NOT wiped by the re-ingest (delete_district_signal_rows never touches `label`)
    assert gov_session.execute(text("SELECT status FROM label WHERE rec_key=:rk"), {"rk": rk}).scalar() == "labeled"


def test_delete_scopes_to_one_district(gov_session, tmp_path):
    """delete_district_signal_rows removes only the named district's rows."""
    _create_temp_schema(gov_session)
    _ingest(gov_session, _seed(tmp_path, "111"))
    _ingest(gov_session, _seed(tmp_path, "222"))
    BS.delete_district_signal_rows(gov_session, "111")
    assert _record_count(gov_session, "111") == 0
    assert _record_count(gov_session, "222") == 1     # untouched
