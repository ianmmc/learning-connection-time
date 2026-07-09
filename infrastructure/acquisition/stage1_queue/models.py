"""Stage 1 (Queue) governance-DB models — the batch working store (REQ-102).

The governance DB is the WORKING STORE for a batch; `data/acquisition/queue/batch_NNNNN.json` is the
auditable RECEIPT, regenerated from these rows on every change (governance §7a-A — the JSON shifted
from a data-transmission vehicle to a receipt). These are PRECIOUS tables: created by
`gdb.init_precious_schema()`, NEVER in the Stage-5 ingest's REBUILD_DDL drop list, so a re-ingest can't
wipe a queued/approved batch. Per-stage models live with their stage (governance §7).

Normalized (not a JSON blob) so the gate@1 edit operations are real row ops and the cross-batch
queries the user stories need (a district in multiple batches; per-batch yields) fall out:
  batch            — lifecycle (draft -> approved; draft -> abandoned) + actor/timestamps + prose meta
  batch_district   — one row per district in the batch; `included` is the soft-reject flag
  batch_school     — one row per (district, school); `bands` lists every band it's selected into;
                     `included` soft-rejects; `source` distinguishes stratified picks from manual adds
"""

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common.timeutil import utcnow  # noqa: F401 (re-export: default=utcnow + external .utcnow callers)




class Batch(gdb.Base):
    __tablename__ = "batch"

    batch_id: Mapped[str] = mapped_column(String, primary_key=True)        # e.g. batch_00002
    batch_type: Mapped[str] = mapped_column(String, default="first-run")   # first-run | follow-up
    status: Mapped[str] = mapped_column(String, default="draft")           # draft | approved | abandoned | reserving
    nces_year: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)
    created_by: Mapped[str] = mapped_column(String)
    approved_at: Mapped[str | None] = mapped_column(String, nullable=True)   # CURRENT approval (cleared by reopen)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # #168 review: the DURABLE "was ever approved" stamp — set on the FIRST approve, NEVER cleared by
    # reopen. This is the honest discriminator for "were this batch's schools committed to discovery
    # (= attempted)?", which `approved_at` can't answer after a reopen. abandon is gated on it so an
    # already-approved batch can't be laundered into the terminal `abandoned` status via reopen->abandon
    # and drop its schools out of the attempted-set (the #162 poison). Additive via _PRECIOUS_ALTERS.
    first_approved_at: Mapped[str | None] = mapped_column(String, nullable=True)
    # #168: retire a superseded, never-approved DRAFT to a terminal `abandoned` status without flipping
    # it to a non-draft value that would count its schools as attempted (the #162 poison). Additive
    # columns via common/db.py _PRECIOUS_ALTERS; only set on the draft->abandoned transition.
    abandoned_at: Mapped[str | None] = mapped_column(String, nullable=True)
    abandoned_by: Mapped[str | None] = mapped_column(String, nullable=True)
    abandon_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # batch-level prose carried through to the receipt (stratification method, denominator criteria,
    # cap, over-cap selection rule) — descriptive, not queried.
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)


class BatchDistrict(gdb.Base):
    __tablename__ = "batch_district"

    batch_id: Mapped[str] = mapped_column(String, primary_key=True)
    district_id: Mapped[str] = mapped_column(String, primary_key=True)
    ord: Mapped[int] = mapped_column(Integer, default=0)                   # stratified-pick order (stable receipt)
    name: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String)
    domain: Mapped[str] = mapped_column(String, default="")
    enrollment_k12: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lea_claimed_bands: Mapped[list] = mapped_column(JSON, default=list)
    nces_school_counts: Mapped[dict] = mapped_column(JSON, default=dict)   # {total, by_level}
    band_processing_order: Mapped[list] = mapped_column(JSON, default=list)
    # per-band selection-time facts {band: {n_candidates, n_unclaimed_at_selection, n_selected}}.
    # n_candidates / n_unclaimed_at_selection are historical (selection time); the LIVE n_selected is
    # recomputed from included batch_school rows when the receipt/view is built.
    band_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    included: Mapped[bool] = mapped_column(Boolean, default=True)          # soft-reject (gate@1 edit)
    # follow-up shaping (#161): per-district {"seed_urls": [...]} for a 7->3 recapture directive.
    # Nullable (only follow-up batches set it); additive column via common/db.py _PRECIOUS_ALTERS.
    followup_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BatchSchool(gdb.Base):
    __tablename__ = "batch_school"

    batch_id: Mapped[str] = mapped_column(String, primary_key=True)
    district_id: Mapped[str] = mapped_column(String, primary_key=True)
    school_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    is_charter: Mapped[str | None] = mapped_column(String, nullable=True)
    level: Mapped[str | None] = mapped_column(String, nullable=True)
    gslo: Mapped[str | None] = mapped_column(String, nullable=True)
    gshi: Mapped[str | None] = mapped_column(String, nullable=True)
    bands: Mapped[list] = mapped_column(JSON, default=list)                # every band it's selected into
    included: Mapped[bool] = mapped_column(Boolean, default=True)          # soft-reject (gate@1 edit)
    source: Mapped[str] = mapped_column(String, default="stratified")      # stratified | manual_add
