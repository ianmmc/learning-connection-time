"""Stage 6 precious DB models: the pre-freeze DRAFT dispatch working store.

A `DispatchDraft` is a mutable, reopenable container a human builds up (add/remove districts, set
per-representation council overrides, toggle verified-only) before freezing it into an immutable
`handoff_<hash>_<ts>.json` (see `handoff.py`/`models.py`'s `Handoff`). This mirrors `stage1_queue`'s
`Batch`/`BatchDistrict` pattern: normalized rows (not a JSON blob) so edits are real row ops, soft-reject
(`included`) never hard-delete.

Representations themselves are NOT persisted here — they're derived live from Stage 5's `record` rows
on every read (via `stage6_dispatch.district_release_input`), so a draft's district row only stores which
council a human chose to OVERRIDE for a given representation key, keyed exactly like
`stage6_handoff/package.py`'s `overrides` dict already expects (`{"<rec_key>::<file>": council_id}`).
An override whose rep no longer exists in the live release decision is simply inert at read time — never
an error (see `stage6_draft_store.py`).

PRECIOUS (never in the Stage-5 ingest drop list); rebuildable is not applicable (this IS the working
store for in-progress drafts). Registered on the governance `Base` — the caller (`process_governance/
server.py`, alongside its existing `Handoff` import) must import this module before
`init_precious_schema()` runs, or these tables silently never get created (the #217 `calibration_event`
lesson).
"""

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common.timeutil import utcnow


class DispatchDraft(gdb.Base):
    __tablename__ = "dispatch_draft"

    draft_id: Mapped[str] = mapped_column(String, primary_key=True)        # e.g. draft_00007
    status: Mapped[str] = mapped_column(String, default="draft")           # draft | dispatched | abandoned
    verified_only: Mapped[bool] = mapped_column(Boolean, default=False)     # per-draft training-grade mode
    created_at: Mapped[str] = mapped_column(String, default=utcnow)
    created_by: Mapped[str] = mapped_column(String, default="human")
    # set together, atomically, at freeze (stage6_draft_store.freeze_draft)
    dispatched_at: Mapped[str | None] = mapped_column(String, nullable=True)
    dispatched_by: Mapped[str | None] = mapped_column(String, nullable=True)
    handoff_hash: Mapped[str | None] = mapped_column(String, nullable=True)   # join key back to `handoff`
    abandoned_at: Mapped[str | None] = mapped_column(String, nullable=True)
    abandoned_by: Mapped[str | None] = mapped_column(String, nullable=True)
    abandon_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # room for future per-draft settings (§3E auto-mode flag, §3G recency preference) without a migration
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


class DispatchDraftDistrict(gdb.Base):
    __tablename__ = "dispatch_draft_district"

    draft_id: Mapped[str] = mapped_column(String, primary_key=True)
    district_id: Mapped[str] = mapped_column(String, primary_key=True)
    ord: Mapped[int] = mapped_column(Integer, default=0)                   # add-order, stable list rendering
    included: Mapped[bool] = mapped_column(Boolean, default=True)          # soft-remove flag (never hard-delete)
    # {"<rec_key>::<file>": council_id} — scoped to this district's own rec_keys (rec_key embeds the
    # district_id as a literal prefix, so no cross-district key collision is possible when merging).
    overrides_json: Mapped[dict] = mapped_column(JSON, default=dict)
