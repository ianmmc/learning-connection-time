"""Stage 8 precious DB model: the gate@8 approval record (STAGE8_AGGREGATE_DESIGN_2026-06 §2b/§2c/§2e).

`stage8_approval` = one human decision on a district's whole closing argument — the attorney's-closing-
argument verdict. Commit grain is PER-DISTRICT, all-or-nothing (§2e): LCT is a district-level metric, so a
band is never published alone. Each row FREEZES the closing argument it acted on (`receipt_json`, self-
contained + offline-auditable, the immutable-handoff discipline) + a `facts_fingerprint` so a later
re-extraction that changes the picture makes the approval detectably stale. A re-decision after a back-edge
round is a NEW row — history is append-only, never rewritten.

PRECIOUS (a human governance decision — never in the Stage-5 ingest drop list; git-backed to
`stage8_approvals.json`), governance DB only. Registered on the governance `Base`; created via
`init_precious_schema()` once the app (or the Stage-8 path) imports this module.
"""
from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common.timeutil import utcnow


class Stage8Approval(gdb.Base):
    """One gate@8 decision on a district. `disposition`: 'approved' (Stage 9 may write all bands) or
    'sent_back' (a band is unsatisfied / the picture was rejected → an 8→1/8→6 back-edge; a reason is
    required). Append-only: the LATEST row per district is the live decision."""
    __tablename__ = "stage8_approval"

    approval_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    district_id: Mapped[str] = mapped_column(String, index=True)
    disposition: Mapped[str] = mapped_column(String)                 # approved | sent_back
    actor: Mapped[str] = mapped_column(String)                       # 'ian' | 'auto:...'
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # required for sent_back; optional note on approve
    facts_fingerprint: Mapped[str] = mapped_column(String)          # closing_argument.fingerprint() at decision time
    receipt_json: Mapped[str] = mapped_column(Text)                 # the frozen closing-argument snapshot
    created_at: Mapped[str] = mapped_column(String, default=utcnow)


# newest-decision-per-district lookup (the console badge + Stage-9 eligibility both hit this)
Index("ix_stage8_approval_latest", Stage8Approval.district_id, Stage8Approval.approval_id.desc())
