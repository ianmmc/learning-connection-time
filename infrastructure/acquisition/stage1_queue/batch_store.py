"""Stage 1 (Queue) batch working-store operations (REQ-102).

The governance DB is the working store; `batch_NNNNN.json` is the receipt regenerated from rows. Every
function takes a Session and does NOT commit — the caller controls the transaction (the console wraps
in `gdb.session_scope`; tests use the rolling-back `gov_session` fixture). The gate@1 edit operations
(reject district / reject school / add school) are soft flips of `included` / row inserts, so nothing
is ever destroyed — the full proposed batch stays auditable.
"""
from sqlalchemy import select, text

from infrastructure.acquisition.common import batch_types as BT
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import paths
import infrastructure.acquisition.common.school_sampling as S
from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict, BatchSchool, utcnow

BANDS = ("elementary", "middle", "high")
_META_KEYS = ("nces_school_counts_criteria", "stratification", "school_cap_per_band",
              "school_selection_when_over_cap", "benchmark", "domain_excluded",   # #229 refusals persist
              "scope_draw",   # #164 PR 3b: the geo_interleaved draw + weights (audit trail)
              "targeted")     # #572 path-4: the dev/manual district-targeted draw record
_SCHOOL_FIELDS = ("school_id", "name", "is_charter", "level", "gslo", "gshi")


# ---------------------------------------------------------------- create (doc -> rows)
def create_batch(sess, batch_doc: dict, *, batch_type: str = "first-run",
                 redo_attempted: bool | None = None, actor: str) -> None:
    """Write a freshly-built batch_doc into the working store (one Batch + BatchDistrict/BatchSchool
    rows). A multi-band school collapses to ONE BatchSchool row carrying all its bands. Flushes so the
    rows are visible to a same-transaction to_receipt_doc().

    `batch_type` is VALIDATED here (#617 Phase 2c) — this is the one chokepoint every composer (CLI,
    console, the 5->1/7->1 escalation builders, the benchmark injector) passes through, so a typo can
    no longer mint a fourth type that silently gets first-run behavior at all five redo-lever sites.

    `redo_attempted` is the DECLARED redo lever (common/batch_types). None = undeclared, which reads
    back through the historical `batch_type == 'follow-up'` fallback — the deliberate default, so
    nothing composed before this existed changes behavior."""
    BT.validate_batch_type(batch_type)
    bid = batch_doc["batch_id"]
    existing = sess.get(Batch, bid)
    if existing is not None and existing.status == "reserving":
        # Upgrade the id reservation (reserve_next_batch, issue #46) to the real draft row in place.
        existing.batch_type = batch_type
        existing.redo_attempted = redo_attempted
        existing.status = "draft"
        existing.discovery_scope = batch_doc.get("discovery_scope", "domain")   # #164 scope-pure axis
        existing.nces_year = batch_doc.get("nces_year", "")
        existing.created_at = batch_doc.get("created") or utcnow()
        existing.created_by = actor
        existing.meta_json = {k: batch_doc[k] for k in _META_KEYS if k in batch_doc}
    elif existing is not None:
        # #264: a non-reserving batch already owns this id (e.g. a CLI-supplied number that
        # collides with a draft) -- refuse cleanly instead of dying on the PK IntegrityError
        # at flush. The console path never hits this (reserve_next_batch is race-safe).
        raise BatchLocked(f"{bid} already exists ({existing.status}); pick another id or "
                          f"reopen/abandon the existing batch")
    else:
        sess.add(Batch(
            batch_id=bid, batch_type=batch_type, redo_attempted=redo_attempted, status="draft",
            discovery_scope=batch_doc.get("discovery_scope", "domain"),   # #164 scope-pure axis
            nces_year=batch_doc.get("nces_year", ""),
            created_at=batch_doc.get("created") or utcnow(), created_by=actor,
            meta_json={k: batch_doc[k] for k in _META_KEYS if k in batch_doc},
        ))
    for i, d in enumerate(batch_doc["districts"]):
        sbb = d.get("schools_by_band", {})
        order = d.get("band_processing_order") or list(sbb.keys())
        # follow-up shaping travels in the EXISTING per-band JSON (no migration): query_strategy is
        # persisted alongside the selection facts and reconstructed into schools_by_band by _district_doc
        # (#160/#162). seed_urls (per-district, #161) rides the additive followup_json column.
        band_meta = {b: {k: sbb[b].get(k)
                         for k in ("n_candidates", "n_unclaimed_at_selection", "n_selected", "query_strategy")}
                     for b in sbb}
        seed_urls = d.get("seed_urls") or []
        sess.add(BatchDistrict(
            batch_id=bid, district_id=d["district_id"], ord=i, name=d["name"], state=d["state"],
            domain=d.get("domain", ""), enrollment_k12=d.get("enrollment_k12"),
            lea_claimed_bands=d.get("lea_claimed_bands", []),
            nces_school_counts=d.get("nces_school_counts", {}),
            band_processing_order=order, band_meta=band_meta, included=True,
            followup_json=({"seed_urls": seed_urls} if seed_urls else None),
            domain_source=d.get("domain_source"),          # #164 dual-source audit trail
            geo_json=d.get("geo"),                         # #164 geo render tokens {city, zip}
        ))
        by_school: dict = {}
        for b in order:
            for s in sbb.get(b, {}).get("schools", []):
                row = by_school.setdefault(s["school_id"], {**s, "bands": []})
                if b not in row["bands"]:
                    row["bands"].append(b)
        for sid, s in by_school.items():
            sess.add(BatchSchool(
                batch_id=bid, district_id=d["district_id"], school_id=sid,
                name=s.get("name", ""), is_charter=s.get("is_charter"), level=s.get("level"),
                gslo=s.get("gslo"), gshi=s.get("gshi"), bands=s["bands"], included=True, source="stratified",
            ))
    sess.flush()


# ---------------------------------------------------------------- serialize (rows -> doc)
def _bands_for_district(d: BatchDistrict, schools: list) -> list:
    """band_processing_order, plus any extra band an added school introduced (kept stable)."""
    order = list(d.band_processing_order or [])
    for s in schools:
        for b in (s.bands or []):
            if b not in order:
                order.append(b)
    return order


def _district_doc(sess, d: BatchDistrict, *, included_only: bool, with_flags: bool) -> dict:
    q = select(BatchSchool).where(BatchSchool.batch_id == d.batch_id,
                                  BatchSchool.district_id == d.district_id)
    if included_only:
        q = q.where(BatchSchool.included.is_(True))
    schools = list(sess.scalars(q))
    bmeta = d.band_meta or {}
    sbb = {}
    for b in _bands_for_district(d, schools):
        band_schools = sorted((s for s in schools if b in (s.bands or [])), key=lambda s: s.school_id)
        meta = bmeta.get(b, {})
        sbb[b] = {
            "n_candidates": meta.get("n_candidates"),
            "n_unclaimed_at_selection": meta.get("n_unclaimed_at_selection"),
            "n_selected": sum(1 for s in band_schools if s.included),   # LIVE
            "schools": [_school_dict(s, with_flags) for s in band_schools],
        }
        if meta.get("query_strategy"):                     # follow-up widen/new-schools signal (#160)
            sbb[b]["query_strategy"] = meta["query_strategy"]
    doc = {
        "district_id": d.district_id, "name": d.name, "state": d.state, "domain": d.domain,
        "enrollment_k12": d.enrollment_k12, "lea_claimed_bands": d.lea_claimed_bands,
        "nces_school_counts": d.nces_school_counts, "band_processing_order": d.band_processing_order,
        "schools_by_band": sbb,
    }
    seed_urls = (d.followup_json or {}).get("seed_urls")   # 7->3 recapture URLs (#161)
    if seed_urls:
        doc["seed_urls"] = seed_urls
    if d.domain_source:                                    # #164 dual-source audit trail
        doc["domain_source"] = d.domain_source
    if d.geo_json:                                         # #164 geo render tokens {city, zip}
        doc["geo"] = d.geo_json
    if with_flags:
        doc["included"] = d.included
    return doc


def _school_dict(s: BatchSchool, with_flags: bool) -> dict:
    out = {"school_id": s.school_id, "name": s.name, "is_charter": s.is_charter,
           "level": s.level, "gslo": s.gslo, "gshi": s.gshi}
    # #222: computed at view time (pure over the name, never stored) so a token-list tuning
    # applies retroactively. Only present when non-empty — a gate@1 reviewer's attention cue
    # for facility-named schools NCES mis-codes as Regular (flag, never hard-exclude).
    flags = S.facility_name_flags(s.name)
    if flags:
        out["review_flags"] = flags
    if with_flags:
        out["included"] = s.included
        out["source"] = s.source
    return out


def _ordered_districts(sess, batch_id: str, *, included_only: bool) -> list:
    q = select(BatchDistrict).where(BatchDistrict.batch_id == batch_id)
    if included_only:
        q = q.where(BatchDistrict.included.is_(True))
    return list(sess.scalars(q.order_by(BatchDistrict.ord)))


def _batch_doc(sess, b: Batch) -> dict:
    """The canonical batch_doc projection (INCLUDED rows only, original shape) for an
    already-fetched Batch row — the shared core of to_receipt_doc and to_working_doc.
    meta_json is spread FIRST so the explicit fields always win: a stray meta key named
    "n"/"nces_year"/... can never silently shadow a computed field (#555 review)."""
    districts = [_district_doc(sess, d, included_only=True, with_flags=False)
                for d in _ordered_districts(sess, b.batch_id, included_only=True)]
    doc = {
        **(b.meta_json or {}),
        "batch_id": b.batch_id, "batch_type": b.batch_type,
        "discovery_scope": b.discovery_scope or "domain",   # #164 (pre-column rows read as domain)
        "created": b.created_at,
        "n": len(districts), "nces_year": b.nces_year, "districts": districts,
    }
    # #617 Phase 2c: the DECLARED redo lever travels to the Stage-2/3/4 runners, which read this doc
    # from the DB (to_working_doc) or the regenerated receipt. OMITTED when undeclared, so every
    # existing receipt regenerates byte-identically and `batch_types.redoes_attempted` falls back.
    if b.redo_attempted is not None:
        doc["redo_attempted"] = b.redo_attempted
    return doc


def to_receipt_doc(sess, batch_id: str) -> dict:
    """The canonical batch_doc (INCLUDED rows only, original shape) — what the receipt file holds.
    DELIBERATELY carries no lifecycle status: batch_guard relies on the receipt being status-free
    (a CLI loader must re-check status against the DB, never trust a file) — status-needing
    consumers use to_working_doc. Raises KeyError if the batch is unknown."""
    b = sess.get(Batch, batch_id)
    if b is None:
        raise KeyError(batch_id)
    return _batch_doc(sess, b)


def to_working_doc(sess, batch_id: str) -> dict | None:
    """The canonical batch_doc + live `batch_status`, for the console's DB batch resolve
    (server._batch_from_db → the Stage 2/3/4 runners; #526). Kept separate from to_receipt_doc
    so status never leaks into the on-disk receipt file (see its docstring), and built off ONE
    Batch fetch (#555 review: the first cut fetched the row twice). None if the batch is
    unknown — no KeyError, so a caller can't confuse "no such batch" with a row-shape bug."""
    b = sess.get(Batch, batch_id)
    if b is None:
        return None
    return {**_batch_doc(sess, b), "batch_status": b.status}


def to_view(sess, batch_id: str) -> dict:
    """The gate@1 review payload — lifecycle fields + ALL rows (included AND soft-rejected) with their
    flags, so the human sees what was proposed and what they've dropped."""
    b = sess.get(Batch, batch_id)
    if b is None:
        raise KeyError(batch_id)
    districts = [_district_doc(sess, d, included_only=False, with_flags=True)
                for d in _ordered_districts(sess, batch_id, included_only=False)]
    return {
        **(b.meta_json or {}),   # spread first — explicit fields below always win (#555 review)
        "batch_id": b.batch_id, "batch_type": b.batch_type, "status": b.status,
        # #617 Phase 2c: the gate@1 reviewer must see whether approving this batch RE-RUNS districts
        # that already reached a later stage (real spend + a merge into their prior round), not infer
        # it from the type. Resolved through the same fallback the runners use, never the raw column.
        "redo_attempted": BT.redoes_attempted({"batch_type": b.batch_type,
                                               "redo_attempted": b.redo_attempted}),
        "discovery_scope": b.discovery_scope or "domain",   # #164
        "nces_year": b.nces_year, "created_at": b.created_at, "created_by": b.created_by,
        "approved_at": b.approved_at, "approved_by": b.approved_by,
        "abandoned_at": b.abandoned_at, "abandoned_by": b.abandoned_by, "abandon_reason": b.abandon_reason,
        "n_included": sum(1 for d in districts if d["included"]),
        "districts": districts,
    }


def _batch_progress(sess) -> dict:
    """Per-batch district-progress counts for the stage-contextual left-pane fraction. Derived from
    the state-event log SCOPED TO THE BATCH (#339) — `current_state` is one global row per district,
    so joining it attributed a district's first-run progress to every later batch containing it (a
    freshly-created follow-up batch showed discovered/captured/processed = total before its own
    discovery ran). `discovered/captured/processed` = districts whose max stage reached 2/3/4 *within
    this batch's events*; `flagged` = districts whose latest stage event in this batch is
    `manual_flag_all` (no links — terminal at Stage 2, never captured). Events predating the
    batch_id column show as no-progress in old batches — honest, and those batches are long done.
    Best-effort → {} if the table isn't present yet.

    NOTE for the next batch-scoped consumer: `current_state` is a GLOBAL one-row-per-district
    view by design — joining it per-batch is exactly the #339 bug this query fixed. If a second
    consumer ever needs per-batch progress, extract THIS subquery into a shared batch-scoped
    projection (a `current_state_by_batch` view or helper) rather than copy-pasting the SQL or
    re-joining current_state."""
    try:
        rows = sess.execute(text("""
            SELECT bd.batch_id,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE bp.max_stage >= 2) AS discovered,
                   COUNT(*) FILTER (WHERE bp.max_stage >= 3) AS captured,
                   COUNT(*) FILTER (WHERE bp.max_stage >= 4) AS processed,
                   COUNT(*) FILTER (WHERE bp.last_outcome = 'manual_flag_all') AS flagged
            FROM batch_district bd
            LEFT JOIN (
                SELECT DISTINCT ON (batch_id, district_id)
                       batch_id, district_id,
                       MAX(stage) OVER (PARTITION BY batch_id, district_id) AS max_stage,
                       outcome AS last_outcome
                FROM state_event
                WHERE batch_id IS NOT NULL AND stage IS NOT NULL
                ORDER BY batch_id, district_id, event_id DESC
            ) bp ON bp.batch_id = bd.batch_id AND bp.district_id = bd.district_id
            WHERE bd.included IS TRUE
            GROUP BY bd.batch_id""")).mappings()
        return {r["batch_id"]: {"total": r["total"], "discovered": r["discovered"],
                                "captured": r["captured"], "processed": r["processed"],
                                "flagged": r["flagged"]} for r in rows}
    except Exception:
        return {}


def list_batches(sess) -> list:
    """Batch lifecycle rows for the queue list (n_districts = currently-included count). Each row also
    carries per-stage PROGRESS counts (`progress`) so each stage view's left pane can show a
    stage-contextual fraction (e.g. captured+flagged / total) instead of the stale gate@1 status."""
    progress = _batch_progress(sess)
    # #338: one grouped count for every batch, not a COUNT query per batch (N+1).
    # DELIBERATE REDUNDANCY (review-confirmed): this count provably equals
    # progress[bid]["total"], but it must stay an independent query — _batch_progress is
    # best-effort (`except → {}`), and n_districts has to survive that degrade. Do NOT
    # "simplify" this into progress.get(bid, {}).get("total") — that reintroduces the
    # n_districts=0-on-progress-failure regression.
    counts = {r["batch_id"]: r["n"] for r in sess.execute(text(
        "SELECT batch_id, COUNT(*) AS n FROM batch_district "
        "WHERE included IS TRUE GROUP BY batch_id")).mappings()}
    out = []
    for b in sess.scalars(select(Batch).order_by(Batch.batch_id)):
        n = counts.get(b.batch_id, 0)
        out.append({"batch_id": b.batch_id, "batch_type": b.batch_type, "status": b.status,
                    "discovery_scope": b.discovery_scope or "domain",   # #572 left-pane badge
                    "nces_year": b.nces_year, "n_districts": n, "created_at": b.created_at,
                    "created_by": b.created_by, "approved_at": b.approved_at, "approved_by": b.approved_by,
                    "abandoned_at": b.abandoned_at, "abandoned_by": b.abandoned_by,
                    "abandon_reason": b.abandon_reason, "progress": progress.get(b.batch_id)})
    return out


def followup_rounds(sess, district_ids: list) -> dict:
    """#164 ladder position, DERIVED from batch history (never a stored counter): per district,
    how many EVER-APPROVED follow-up batches contain it, split by discovery scope. Only
    first_approved_at counts — a draft/abandoned compose never advances the ladder.
    Returns {district_id: {"domain": n, "geo": n}}."""
    out = {did: {"domain": 0, "geo": 0} for did in district_ids}
    if not district_ids:
        return out
    rows = sess.execute(text(
        """SELECT bd.district_id, COALESCE(b.discovery_scope, 'domain') AS scope, COUNT(*) AS n
           FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id
           WHERE bd.district_id = ANY(:dids) AND b.batch_type = 'follow-up'
             AND b.first_approved_at IS NOT NULL AND bd.included
           GROUP BY bd.district_id, COALESCE(b.discovery_scope, 'domain')"""),
        {"dids": list(district_ids)}).mappings()
    for r in rows:
        if r["scope"] in ("domain", "geo"):
            out[r["district_id"]][r["scope"]] = int(r["n"])
    return out


# #164/#575 review: the ONE geo-escalation exhaustion threshold, shared by BOTH escalation
# composers (5->1 zero-yield in stage5_followup.py, 7->1 scope-split in stage7_execute.py) so a
# district's exhaustion status can never depend on which composer reaches it first (the bug: 7->1
# used to exhaust at geo>=1 while 5->1 offered a "geo+widened" rung at geo==1, disagreeing for any
# district sitting at exactly one approved geo round).
GEO_LADDER_EXHAUSTED_AT = 2


def geo_ladder_exhausted(rounds_row: dict) -> bool:
    """True once a district has used its full geo-escalation ladder (>=GEO_LADDER_EXHAUSTED_AT
    ever-approved geo rounds: one standard + one widened attempt). `rounds_row` is one entry of
    `followup_rounds()`'s per-district dict, e.g. `rounds[district_id]`."""
    return rounds_row["geo"] >= GEO_LADDER_EXHAUSTED_AT


# ---------------------------------------------------------------- receipt (rows -> file)
def write_receipt(sess, batch_id: str):
    """Regenerate batch_NNNNN.json from the rows — the auditable receipt always reflects the working
    store. Overwrites in place during draft (the DB is authoritative; the receipt is the snapshot)."""
    doc = to_receipt_doc(sess, batch_id)
    paths.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = paths.QUEUE_DIR / f"{batch_id}.json"
    paths.atomic_write_json(out_path, doc)   # atomic (issue #50): a crash mid-write must never
                                             # leave a truncated receipt behind
    return out_path


# ---------------------------------------------------------------- gate@1 edits (soft) + lifecycle
class BatchLocked(Exception):
    """Raised when an edit is attempted on an already-approved batch (re-open to draft first)."""


def _require_draft(b: Batch) -> None:
    if b is None:
        raise KeyError("batch")
    if b.status != "draft":
        raise BatchLocked(f"{b.batch_id} is {b.status}; re-open to draft before editing")


def reject_district(sess, batch_id: str, district_id: str) -> None:
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    d = sess.get(BatchDistrict, (batch_id, district_id))
    if d is None:
        raise KeyError(district_id)
    d.included = False
    sess.flush()


def reject_school(sess, batch_id: str, district_id: str, school_id: str) -> None:
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    s = sess.get(BatchSchool, (batch_id, district_id, school_id))
    if s is None:
        raise KeyError(school_id)
    s.included = False
    sess.flush()


def restore_district(sess, batch_id: str, district_id: str) -> None:
    """Reverse a reject_district (set included back to True) — keeps gate@1 editing reversible during
    draft so a mis-reject isn't a dead end."""
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    d = sess.get(BatchDistrict, (batch_id, district_id))
    if d is None:
        raise KeyError(district_id)
    d.included = True
    sess.flush()


def restore_school(sess, batch_id: str, district_id: str, school_id: str) -> None:
    """Reverse a reject_school. (A genuinely NEW school is added via add_school instead.)"""
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    s = sess.get(BatchSchool, (batch_id, district_id, school_id))
    if s is None:
        raise KeyError(school_id)
    s.included = True
    sess.flush()


def add_school(sess, batch_id: str, district_id: str, school: dict, bands: list) -> None:
    """Add a school to a district's targeting (story 31). `school` carries the NCES fields
    (school_id/name/level/gslo/gshi/is_charter) the caller pulled from the eligible pool; `bands` is
    which band(s) to target it in. Re-including a previously-rejected row is also an add."""
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    sid = school["school_id"]
    existing = sess.get(BatchSchool, (batch_id, district_id, sid))
    if existing is not None:
        existing.included = True
        existing.bands = sorted(set((existing.bands or []) + bands))
    else:
        sess.add(BatchSchool(
            batch_id=batch_id, district_id=district_id, school_id=sid, name=school.get("name", ""),
            is_charter=school.get("is_charter"), level=school.get("level"), gslo=school.get("gslo"),
            gshi=school.get("gshi"), bands=list(bands), included=True, source="manual_add"))
    sess.flush()


def approve_batch(sess, batch_id: str, actor: str) -> None:
    """gate@1 approval — the batch-level transition (the unit that advances to discovery)."""
    b = sess.get(Batch, batch_id)
    if b is None:
        raise KeyError(batch_id)
    if b.status != "draft":
        raise BatchLocked(f"{batch_id} is already {b.status}")
    b.status = "approved"
    b.approved_at = utcnow()
    b.approved_by = actor
    if b.first_approved_at is None:      # #168: durable ever-approved stamp — set once, survives reopen
        b.first_approved_at = b.approved_at
    sess.flush()


def reopen_batch(sess, batch_id: str, actor: str) -> None:
    """Re-open an approved batch back to draft for further editing (clears the approval stamp).
    An `abandoned` batch is TERMINAL — reopen refuses it (#168) so it can't be silently resurrected;
    recovering one is a deliberate un-abandon, not an incidental reopen."""
    b = sess.get(Batch, batch_id)
    if b is None:
        raise KeyError(batch_id)
    if b.status == "abandoned":
        raise BatchLocked(f"{batch_id} is abandoned (terminal); cannot re-open")
    b.status = "draft"
    b.approved_at = None
    b.approved_by = None
    sess.flush()


def abandon_batch(sess, batch_id: str, actor: str, reason: str = "") -> None:
    """gate@1 abandon — retire a NEVER-APPROVED draft to a TERMINAL `abandoned` status (#168).

    NEVER-APPROVED BY DESIGN (the invariant lives here, in the method that owns the transition, so no
    entry point can bypass it). `_attempted_schools` (stage7_execute) excludes both `draft` and
    `abandoned` from the already-attempted set on the premise that neither ever ran discovery. That
    premise holds only if `abandoned` implies never-approved: an approved batch commits its schools to
    discovery (they count as attempted the moment it's approved), so abandoning one — even after a
    reopen-to-draft — would drop those schools back out of the attempted set and re-queue them, the
    exact #162 poison this status was added to avoid. We gate on the DURABLE `first_approved_at`, not
    the reopen-clearable `status`/`approved_at`: reopen->abandon on a once-approved batch is refused."""
    b = sess.get(Batch, batch_id)
    if b is None:
        raise KeyError(batch_id)
    if b.first_approved_at is not None:
        raise BatchLocked(f"{batch_id} was approved (its schools are committed as attempted); cannot "
                          "abandon — a superseded approved batch stays approved, it is not retired")
    if b.status != "draft":
        raise BatchLocked(f"{batch_id} is {b.status}; only a never-approved draft can be abandoned")
    b.status = "abandoned"
    b.abandoned_at = utcnow()
    b.abandoned_by = actor
    b.abandon_reason = reason or None
    sess.flush()


# ---------------------------------------------------------------- next id (DB rows + on-disk receipts)
def reserve_next_batch(sess, *, actor: str) -> str:
    """Reserve the next batch id UP FRONT by inserting a placeholder row (status='reserving') — the
    fix for the duplicate-id race (issue #46): the console's create path spends 10-20s in build_batch
    between computing the number and persisting, during which a second create used to compute the SAME
    number. The caller commits this in its own short transaction BEFORE the slow build; create_batch
    then upgrades the placeholder to the real draft row. A concurrent reserve of the same number fails
    fast on the PK (IntegrityError) instead of 20s later. On a failed build the caller should
    release_reservation() so the number isn't burned by a dead placeholder."""
    bid = f"batch_{next_batch_number(sess):05d}"
    sess.add(Batch(batch_id=bid, batch_type="first-run", status="reserving",
                   nces_year="", created_at=utcnow(), created_by=actor, meta_json={}))
    sess.flush()
    return bid


def release_reservation(sess, batch_id: str) -> None:
    """Delete a placeholder reservation after a failed build (only if it's still just a reservation)."""
    b = sess.get(Batch, batch_id)
    if b is not None and b.status == "reserving":
        sess.delete(b)
        sess.flush()


def next_batch_number(sess) -> int:
    """The next free batch number, considering BOTH the DB batch rows and any batch_*.json receipts on
    disk (a hand-run CLI batch may exist as a file before it's a row)."""
    nums = []
    for (bid,) in sess.execute(select(Batch.batch_id)):
        if bid.startswith("batch_") and bid[6:].isdigit():
            nums.append(int(bid[6:]))
    if paths.QUEUE_DIR.exists():
        for p in paths.QUEUE_DIR.glob("batch_*.json"):
            stem = p.stem[6:]
            if stem.isdigit():
                nums.append(int(stem))
    return (max(nums) + 1) if nums else 1
