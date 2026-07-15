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

from sqlalchemy import String, Integer, Float, Text, ForeignKey, Index
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
    # Deliberately UNindexed, like every other _PRECIOUS_ALTERS column: the raw ALTER migration can't
    # add a model-side index, so index=True would silently diverge fresh vs migrated DBs — and the
    # console filter matches nearly every row, so an index buys nothing.
    run_kind: Mapped[str] = mapped_column(String, default="production", server_default="production",
                                          nullable=False)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)
    created_by: Mapped[str] = mapped_column(String, default="auto:stage7")
    # telemetry rollup (per-model per-call detail lives in the disk receipt)
    n_reps: Mapped[int] = mapped_column(Integer, default=0)
    # #120: reps left unsent by the mode-stability early-exit (detail in the disk receipt's
    # skipped_reps/early_exit). Deliberately UNindexed, like every _PRECIOUS_ALTERS column.
    n_reps_skipped: Mapped[int] = mapped_column(Integer, default=0, server_default="0",
                                                nullable=False)
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
    # v2 council evidence (STAGE8 §2a.6): {model: {quote, locus, stated_minutes, stated_minutes_quote}} —
    # the verbatim source span(s) the consensus times were read from + any explicitly-stated minutes
    # (path 2). NULL for pre-v2 rows (going-forward only; no backfill — a re-read is a paid re-extraction).
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # v3 council readings (#254): the school year as STATED on the page ("YYYY-YY", the consensus of
    # the models that read one — null on disagreement or when unstated) and the page's own stated
    # scope ("multiple" when ANY model read a group-of-schools scope, else NULL). NULL for pre-v3
    # rows (going-forward only; no backfill — a re-read is a paid re-extraction; the evidence_json
    # precedent). Deliberately UNindexed like every _PRECIOUS_ALTERS column (see run_kind above).
    school_year: Mapped[str | None] = mapped_column(String, nullable=True)
    applies_to: Mapped[str | None] = mapped_column(String, nullable=True)
    # v4 council reading (#499 REQ-148): the page's own VERBATIM campus list when the schedule
    # covers a group — sorted union across models (JSON list). NULL pre-v4; same no-backfill rule.
    campus_names_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    gate@7 human decision. Dedup identity (#234, two-layered): same handoff any status, OR any handoff
    while still OPEN (pending/approved). Persisted on a re-detect only if absent — an existing row keeps
    its review status. No DB unique constraint backs the check-then-insert (the conditional identity +
    NULL band make one impractical on the live table); the writer serializes per district via a pg
    advisory xact lock instead, and ix_extraction_request_ask serves the natural-key lookup."""
    __tablename__ = "extraction_request"
    __table_args__ = (Index("ix_extraction_request_ask", "district_id", "target", "altitude", "route"),)

    request_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    district_id: Mapped[str] = mapped_column(String, index=True)
    handoff_hash: Mapped[str] = mapped_column(String, index=True)
    altitude: Mapped[str] = mapped_column(String)          # representation | url | district
    route: Mapped[str] = mapped_column(String)             # 7->6 | 7->3 | 7->2 | 7->1
    target: Mapped[str] = mapped_column(String)            # rec_key (rep/url) or district_id
    band: Mapped[str | None] = mapped_column(String, nullable=True)
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="pending")   # pending|approved|rejected|executed|withdrawn (#233)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Execution lineage (REQ-118): set when an APPROVED directive is executed — the follow-up
    # batch_id (7->2/7->3/7->1) or the new dispatch handoff_hash (7->6) it fired. Gives idempotency
    # (an 'executed' row is never re-fired) + traceability from the directive to the work it created.
    executed_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    executed_at: Mapped[str | None] = mapped_column(String, nullable=True)
