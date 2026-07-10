"""Shared batch-runnability guard (#168 review) — the single boundary that stops any stage entry point
(console OR headless CLI) running on a terminal `abandoned` batch. Runs against the isolated governance
Postgres via the rolling-back `gov_session` fixture (skips if Docker is down)."""
import pytest

from infrastructure.acquisition.common import batch_guard as BG
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage1_queue import models  # noqa: F401 (registers the batch table)
from infrastructure.acquisition.stage1_queue.models import Batch

govdb = pytest.mark.govdb


@pytest.fixture
def sess(gov_session):
    gdb.init_precious_schema()
    return gov_session


def _batch(sess, bid, status):
    sess.add(Batch(batch_id=bid, batch_type="first-run", status=status, nces_year="2024_25",
                   created_at="t", created_by="t", meta_json={}))
    sess.flush()


@govdb
def test_assert_runnable_halts_on_abandoned(sess):
    _batch(sess, "batch_zzguard_ab", "abandoned")
    with pytest.raises(SystemExit):
        BG.assert_runnable(sess, "batch_zzguard_ab")


@govdb
def test_assert_runnable_allows_runnable_and_unknown(sess):
    for st in ("draft", "approved", "reserving"):
        _batch(sess, f"batch_zzguard_{st}", st)
        BG.assert_runnable(sess, f"batch_zzguard_{st}")   # no raise
    # an id this DB has never seen (a receipt-only dev batch) stays runnable — the guard only blocks a
    # KNOWN abandoned row, it doesn't require every runnable batch to be in the DB.
    BG.assert_runnable(sess, "batch_zzguard_never_seen")


# ---- district-grain twin (#206 review): the Stage-3/4 per-district CLIs anchor on discovery.json ----
def _district_dir(tmp_path, batch_id):
    d = tmp_path / "9999999_test_district"
    d.mkdir()
    (d / "discovery.json").write_text(f'{{"district_id": "9999999", "batch_id": "{batch_id}"}}')
    return d


@govdb
def test_assert_district_runnable_halts_when_producing_batch_abandoned(sess, tmp_path):
    _batch(sess, "batch_zzguard_dab", "abandoned")
    with pytest.raises(SystemExit):
        BG.assert_district_runnable(sess, _district_dir(tmp_path, "batch_zzguard_dab"))


@govdb
def test_assert_district_runnable_allows_live_batch_and_no_claim(sess, tmp_path):
    _batch(sess, "batch_zzguard_dok", "approved")
    BG.assert_district_runnable(sess, _district_dir(tmp_path, "batch_zzguard_dok"))   # no raise
    # no discovery.json at all -> no batch claim -> runnable (pre-batch dev data)
    bare = tmp_path / "bare_dir"
    bare.mkdir()
    BG.assert_district_runnable(sess, bare)
    # discovery.json without a batch_id -> no claim -> runnable
    nb = tmp_path / "no_batch_dir"
    nb.mkdir()
    (nb / "discovery.json").write_text('{"district_id": "9999998"}')
    BG.assert_district_runnable(sess, nb)
