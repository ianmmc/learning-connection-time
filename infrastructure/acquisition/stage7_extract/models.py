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

from sqlalchemy import String, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common.timeutil import utcnow  # noqa: F401 (re-export: default=utcnow + external .utcnow callers)




class Extraction(gdb.Base):
    """One Stage-7 council run over one district (from one frozen handoff). Append-only history — a
    re-run is a new row, so `what did we extract on date X` stays recoverable (like re-dispatch)."""
    __tablename__ = "extraction"

    extraction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    handoff_hash: Mapped[str] = mapped_column(String, index=True)   # the dispatch this ran against
    district_id: Mapped[str] = mapped_column(String, index=True)
    # 'production' (default) vs 'probe' (a council-variant A/B, e.g. image_handoff_variant's vision
    # probe). The gate@7 console shows ONLY production; a probe is an experiment, not a review surface.
    # First-class discriminator (#148) — replaces the fragile `handoff_hash NOT LIKE '%-image'` string
    # match, which silently let any OTHER variant suffix (`-vision2`, …) shadow production runs.
    run_kind: Mapped[str] = mapped_column(String, default="production", server_default="production",
                                          nullable=False, index=True)
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


class ExtractionRequest(gdb.Base):
    """A request-more-evidence directive emitted by the deterministic detector (`requests.py`) after a
    run — the 7→6/3/2/1 back-edge to route. The derived fields (altitude/route/target/band/reason) are
    regenerable from the extraction result; the REVIEW fields (status/reviewed_by/note) are the precious
    gate@7 human decision. Natural key for idempotent re-detection: (handoff_hash, target, altitude,
    route, band). Persisted on a re-detect only if absent — an existing row keeps its review status."""
    __tablename__ = "extraction_request"

    request_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    district_id: Mapped[str] = mapped_column(String, index=True)
    handoff_hash: Mapped[str] = mapped_column(String, index=True)
    altitude: Mapped[str] = mapped_column(String)          # representation | url | district
    route: Mapped[str] = mapped_column(String)             # 7->6 | 7->3 | 7->2 | 7->1
    target: Mapped[str] = mapped_column(String)            # rec_key (rep/url) or district_id
    band: Mapped[str | None] = mapped_column(String, nullable=True)
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="pending")   # pending|approved|rejected|executed
    created_at: Mapped[str] = mapped_column(String, default=utcnow)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Execution lineage (REQ-118): set when an APPROVED directive is executed — the follow-up
    # batch_id (7->2/7->3/7->1) or the new dispatch handoff_hash (7->6) it fired. Gives idempotency
    # (an 'executed' row is never re-fired) + traceability from the directive to the work it created.
    executed_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    executed_at: Mapped[str | None] = mapped_column(String, nullable=True)
