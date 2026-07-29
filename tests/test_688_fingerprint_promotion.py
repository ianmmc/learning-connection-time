"""#688 — the Stage-3 fingerprint promotion (REQ-115) must survive the two capture-row shapes.

The defect: `cms_hint_of`/`embed_hosts_of` read `fingerprint_json` (the DB column name) off the
DISK captures.json rows the ingest call site hands them (key: `fingerprint`, a nested dict) —
always absent, so `signals_json.cms_hint` was None on all 3,559 records while 2,653 capture
fingerprints held real vendor hints. Invisible because None is a legal value (a genuinely unknown
CMS) and nothing asserted corpus-level non-nullness.

Pins: (a) both accessors accept BOTH shapes; (b) the corpus seam itself
(`assert_fingerprint_promotion`, run inside every full ingest: fingerprints-with-hints > 0 ⇒
records-with-hints > 0) aborts a broken ingest before commit.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import build_signals as BS


# ---------------------- the accessors: disk shape (the ingest caller) ----------------------
def test_cms_hint_reads_the_disk_row_shape():
    # the shape ingest_district actually hands the accessor — FAILED before #688
    assert BS.cms_hint_of({"fingerprint": {"cms_hint": "finalsite.net"}}) == "finalsite.net"


def test_embed_hosts_reads_the_disk_row_shape():
    assert BS.embed_hosts_of({"fingerprint": {"embed_hosts": ["social", "calendar"]}}) == \
        ["social", "calendar"]


# ---------------------- the accessors: DB shape (fingerprint_json, a JSON string) ----------------------
def test_cms_hint_still_reads_the_db_row_shape():
    assert BS.cms_hint_of({"fingerprint_json": '{"cms_hint": "edlioschool.com"}'}) == "edlioschool.com"


def test_embed_hosts_still_reads_the_db_row_shape():
    assert BS.embed_hosts_of({"fingerprint_json": '{"embed_hosts": ["doc-viewer"]}'}) == ["doc-viewer"]


def test_accessors_are_none_and_empty_on_absent_or_malformed():
    for cap in ({}, {"fingerprint": None}, {"fingerprint_json": None},
                {"fingerprint_json": "not json"}, {"fingerprint_json": "null"}):
        assert BS.cms_hint_of(cap) is None
        assert BS.embed_hosts_of(cap) == []


# ---------------------- the corpus seam (govdb: TEMP tables shadow the real ones) ----------------------
govdb = pytest.mark.govdb

_TEMP_DDL = (
    "CREATE TEMP TABLE capture (hash TEXT PRIMARY KEY, fingerprint_json TEXT)",
    "CREATE TEMP TABLE record (rec_key TEXT PRIMARY KEY, signals_json TEXT)",
)


def _seed(sess, cap_fp, rec_sig):
    for ddl in _TEMP_DDL:
        sess.execute(text(ddl))
    if cap_fp is not None:
        sess.execute(text("INSERT INTO capture VALUES ('h1', :f)"), {"f": cap_fp})
    if rec_sig is not None:
        sess.execute(text("INSERT INTO record VALUES ('r1', :s)"), {"s": rec_sig})


@govdb
def test_dead_promotion_aborts_the_ingest(gov_session):
    """Hinted fingerprints + zero hinted records = the #688 defect — SystemExit BEFORE commit
    (the assert_floor discipline)."""
    _seed(gov_session, '{"cms_hint": "apptegy.net"}', '{"n_times_in_window": 4}')
    with pytest.raises(SystemExit, match="promotion is DEAD"):
        BS.assert_fingerprint_promotion(gov_session)


@govdb
def test_live_promotion_passes_and_reports_counts(gov_session):
    _seed(gov_session, '{"cms_hint": "apptegy.net"}', '{"cms_hint": "apptegy.net"}')
    assert BS.assert_fingerprint_promotion(gov_session) == (1, 1)


@govdb
def test_hintless_corpus_passes_vacuously(gov_session):
    """No fingerprint carries a hint (a pre-REQ-115 corpus) — nothing to promote, nothing to assert."""
    _seed(gov_session, '{"final_host": "x"}', '{"n_times_in_window": 4}')
    assert BS.assert_fingerprint_promotion(gov_session) == (0, 0)
