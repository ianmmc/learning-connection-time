"""The `_PRECIOUS_ALTERS` <-> model-DDL parity contract.

`common/db.init_precious_schema()` builds a governance schema two different ways depending on the DB
it finds:

  * **migrated DB** (Ian's local, any long-lived deployment) — the table already exists, so
    `create_all()` skips it and the raw `ALTER TABLE ... ADD COLUMN` in `_PRECIOUS_ALTERS` is what
    actually adds the column, carrying whatever `NOT NULL` / `DEFAULT` that string declares;
  * **fresh DB** (CI's Postgres service container, a new clone) — `create_all()` creates the table
    from the MODEL, and the `ADD COLUMN IF NOT EXISTS` is then a no-op.

So a column whose ALTER says `NOT NULL DEFAULT x` but whose model carries only an ORM-side `default=`
(which emits no DDL default) is `NOT NULL` with **no server default** on a fresh DB. Every raw
`text()` INSERT omitting that column then fails NOT NULL — **on fresh DBs only**. That is invisible
locally and red on CI, which is exactly how #618's `dispatch_type` shipped (PR #641: 352 govdb tests
green locally, 1 failed + 4 errors on CI).

This is a DB-free metadata check on purpose: it runs in the main suite, so the class is caught before
the `govdb` job ever spins a Postgres container.
"""
import re

import pytest

# Import every module that registers a PRECIOUS model on Base.metadata. Without these the metadata is
# empty and the parity check below would pass vacuously — the count assertion at the end is what makes
# a future import regression fail loudly instead of silently disarming this test.
import infrastructure.acquisition.stage1_queue.models  # noqa: F401
import infrastructure.acquisition.stage5_filter.models  # noqa: F401
import infrastructure.acquisition.stage6_handoff.models  # noqa: F401
import infrastructure.acquisition.stage6_handoff.draft_models  # noqa: F401
import infrastructure.acquisition.stage7_extract.models  # noqa: F401
import infrastructure.acquisition.stage8_aggregate.models  # noqa: F401
from infrastructure.acquisition.common import calibration  # noqa: F401
from infrastructure.acquisition.common import gate_mode  # noqa: F401
from infrastructure.acquisition.common import db as gdb

# `ALTER TABLE <t> ADD COLUMN [IF NOT EXISTS] <c> <type> [NOT NULL] [DEFAULT <literal>]`
_ALTER_ADD_COLUMN = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+\w+"
    r"(?P<notnull>\s+NOT\s+NULL)?(?:\s+DEFAULT\s+(?P<default>\S+))?",
    re.IGNORECASE)


def _alters_declaring_a_default():
    """Every ALTER that gives the column a server-side DEFAULT — with or without NOT NULL.

    Both shapes trap a fresh DB, for the same underlying reason (an ORM `default=` emits no DDL):
      * `NOT NULL DEFAULT x` — fresh DB gets NOT NULL, no default (#618 dispatch_type);
      * `DEFAULT x` alone, over a model that is NOT NULL — same outcome (#164 discovery_scope).
    """
    for ddl in gdb._PRECIOUS_ALTERS:
        m = _ALTER_ADD_COLUMN.search(ddl if isinstance(ddl, str) else "")
        if m and m.group("default"):
            yield m.group(1), m.group(2), m.group("default"), bool(m.group("notnull"))


def test_every_defaulted_alter_has_a_matching_model_server_default():
    """A migrated DB and a fresh DB must agree on the server-side default."""
    checked = 0
    for table, column, literal, alter_says_not_null in _alters_declaring_a_default():
        tbl = gdb.Base.metadata.tables.get(table)
        assert tbl is not None, (
            f"_PRECIOUS_ALTERS touches `{table}` but no imported model registers it — either add the "
            f"registration import to this test or the ALTER targets a table create_all() never makes.")
        col = tbl.c.get(column)
        assert col is not None, f"`{table}.{column}` is ALTERed in but absent from the model."

        assert col.server_default is not None, (
            f"`{table}.{column}`: the ALTER declares `DEFAULT {literal}` but the model has no "
            f"server_default, so a fresh create_all() DB gets no default at all. An ORM `default=` is "
            f"not enough — it never reaches the DDL, and raw text() INSERTs bypass it. Add "
            f"`server_default=...` alongside the ORM default (the `run_kind` precedent).")
        if alter_says_not_null:
            assert col.nullable is False, (
                f"`{table}.{column}`: the ALTER declares NOT NULL, the model does not. A fresh DB "
                f"would accept NULLs that a migrated DB rejects.")
        checked += 1

    # Falsification guard: if the regex, the import set, or _PRECIOUS_ALTERS drifts such that nothing
    # matches, this test would pass while checking nothing. The known population at 2026-07-26 is
    # extraction.run_kind, extraction.n_reps_skipped, handoff.dispatch_type,
    # dispatch_draft.dispatch_type, batch.discovery_scope. Raise this floor when more are added;
    # never lower it silently.
    assert checked >= 5, f"parity check inspected only {checked} columns — the detector has gone blind"


@pytest.mark.parametrize("table,column", [("handoff", "dispatch_type"),
                                          ("dispatch_draft", "dispatch_type")])
def test_dispatch_type_server_default_is_production(table, column):
    """#618 (epic #617) regression pin: the two columns that actually broke CI on PR #641."""
    col = gdb.Base.metadata.tables[table].c[column]
    assert col.nullable is False
    assert col.server_default is not None
    assert "production" in str(col.server_default.arg)
