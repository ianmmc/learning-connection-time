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
