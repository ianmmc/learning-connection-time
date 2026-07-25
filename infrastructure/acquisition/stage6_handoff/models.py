"""Stage 6 precious DB model: the `handoff` index row (REQ-101).

The immutable `handoff_<hash>_<ts>.json` file (see `handoff.py`) is the content-of-record for a
dispatch; this row is the queryable INDEX over those files — so the console can list/track handoffs
(status, cost, district/council summary) without scanning the dir. PRECIOUS (never in the Stage-5
ingest drop list); rebuildable from the files if ever needed. Registered on the governance `Base`
(create via `init_precious_schema()` once the app imports this module).
"""

from sqlalchemy import String, Integer, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common.timeutil import utcnow  # noqa: F401 (re-export: default=utcnow + external .utcnow callers)




class Handoff(gdb.Base):
    __tablename__ = "handoff"

    handoff_id: Mapped[str] = mapped_column(String, primary_key=True)   # handoff_<hash>_<ts> (file stem)
    handoff_hash: Mapped[str] = mapped_column(String)                   # the price-independent content hash
    created_at: Mapped[str] = mapped_column(String, default=utcnow)
    created_by: Mapped[str] = mapped_column(String, default="human")
    status: Mapped[str] = mapped_column(String, default="dispatched")   # draft | approved | dispatched (gate@6)
    path: Mapped[str] = mapped_column(String)                           # the immutable file path
    n_districts: Mapped[int] = mapped_column(Integer, default=0)
    n_reps: Mapped[int] = mapped_column(Integer, default=0)
    total_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_provenance: Mapped[str] = mapped_column(String, default="unknown")
    # #618: production | benchmark — the FROZEN dispatch's type, mirroring the draft it came from.
    # Also folded into handoff._identity, so the same reps dispatched benchmark vs production are
    # hash-distinct artifacts (the `verified_only` precedent).
    dispatch_type: Mapped[str] = mapped_column(String, default="production")
    district_ids: Mapped[list] = mapped_column(JSON, default=list)
    council_ids: Mapped[list] = mapped_column(JSON, default=list)
