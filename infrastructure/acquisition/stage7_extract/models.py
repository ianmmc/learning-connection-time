"""Stage 7 precious DB models: the council-extraction results (REQ-117).

`extraction` = one council run over one district's reps from one frozen handoff (its telemetry rollup
+ a pointer to the on-disk receipt). `school_fact` = the per-school consensus outcomes that run
produced — `accepted` rows carry the agreed start/end/gross, `unresolved` rows carry the per-model
disagreement for gate@7 review. Both are PRECIOUS (paid output — never in the Stage-5 ingest drop
list; rebuildable from the receipt if ever needed) and live in the GOVERNANCE DB, never the LCT DB —
Stage 9 (non-benchmark only) is the sole promoter to `bell_schedules`, so benchmark stays walled off.

Registered on the governance `Base`; created via `init_precious_schema()` once the app (or the
Stage-7 persist path) imports this module.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Extraction(gdb.Base):
    """One Stage-7 council run over one district (from one frozen handoff). Append-only history — a
    re-run is a new row, so `what did we extract on date X` stays recoverable (like re-dispatch)."""
    __tablename__ = "extraction"

    extraction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    handoff_hash: Mapped[str] = mapped_column(String, index=True)   # the dispatch this ran against
    district_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)
    created_by: Mapped[str] = mapped_column(String, default="auto:stage7")
    # telemetry rollup (per-model per-call detail lives in the disk receipt)
    n_reps: Mapped[int] = mapped_column(Integer, default=0)
    n_calls: Mapped[int] = mapped_column(Integer, default=0)
    n_judge_calls: Mapped[int] = mapped_column(Integer, default=0)
    n_errors: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    n_accepted: Mapped[int] = mapped_column(Integer, default=0)
    n_unresolved: Mapped[int] = mapped_column(Integer, default=0)
    receipt_path: Mapped[str | None] = mapped_column(String, nullable=True)


class SchoolFact(gdb.Base):
    """A per-school consensus outcome from a Stage-7 run. One row per (extraction, band, school)."""
    __tablename__ = "school_fact"

    fact_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extraction_id: Mapped[int] = mapped_column(ForeignKey("extraction.extraction_id"), index=True)
    district_id: Mapped[str] = mapped_column(String, index=True)
    band: Mapped[str] = mapped_column(String)                       # elementary | middle | high
    school: Mapped[str] = mapped_column(String)                     # normalized school key
    status: Mapped[str] = mapped_column(String)                     # accepted | unresolved
    # accepted:
    start_time: Mapped[str | None] = mapped_column(String, nullable=True)     # HH:MM
    end_time: Mapped[str | None] = mapped_column(String, nullable=True)
    gross_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # deterministic end-start
    method: Mapped[str | None] = mapped_column(String, nullable=True)          # council_agree | judge | <reason>
    models_json: Mapped[str | None] = mapped_column(Text, nullable=True)       # consensus models (accepted)
    # unresolved: the per-model disagreement (starts/ends by model) or an implausible-gross note
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # provenance + review
    rec_key: Mapped[str | None] = mapped_column(String, nullable=True)         # source rep
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    human_determination: Mapped[str] = mapped_column(String, default="")       # gate@7/gate@8 verification
    created_at: Mapped[str] = mapped_column(String, default=utcnow)
