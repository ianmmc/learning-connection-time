"""Stage 6 (Dispatch) DRAFT working-store operations.

Mirrors `stage1_queue/batch_store.py`'s contract exactly: every function takes a Session and does NOT
commit — the caller controls the transaction (the console wraps in `gdb.session_scope`; tests use the
rolling-back `gov_session` fixture). Edits are soft (`included` flips / JSON-column merges), so nothing
is ever destroyed.

A draft persists WHICH districts are in it and WHICH council overrides a human chose — never the
representations themselves, which are derived live from the Stage-5 release decision on every read
(`stage6_dispatch.build_handoff_package`/`district_release_input`). This keeps a draft from shadowing
that live derivation: if a Stage-5 label changes and a rep disappears from the current send-list, a
stale override entry simply never gets looked up again — inert, never an error (see `freeze_draft`).

Two-terminal-state lifecycle (simpler than `Batch`'s): `draft` -> `dispatched` (via freeze, one-way — a
frozen handoff is immutable so there's nothing to reopen) or `draft` -> `abandoned` (terminal, always
safe on a `draft`-status row — nothing external depends on a draft until it freezes).
"""
from sqlalchemy import select

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.process_governance import stage6_dispatch as H6
from infrastructure.acquisition.stage6_handoff import handoff as HND
from infrastructure.acquisition.stage6_handoff.draft_models import DispatchDraft, DispatchDraftDistrict, utcnow
from infrastructure.acquisition.stage7_extract import requests as RQ7  # ROUTE_ALT_REP — never re-spell '7->6'


class DraftLocked(Exception):
    """Raised when an edit/freeze/abandon is attempted on a draft that isn't in the right lifecycle state."""


def _require_draft(d: DispatchDraft) -> None:
    if d is None:
        raise KeyError("draft")
    if d.status != "draft":
        raise DraftLocked(f"{d.draft_id} is {d.status}; only a draft can be edited")


def _locked_draft(sess, draft_id: str) -> DispatchDraft:
    """Load the draft row FOR UPDATE and require `draft` status. Every mutator (edits, abandon,
    freeze) goes through this: without the row lock, two concurrent requests (double-click, two tabs)
    could BOTH pass the status check before either commits — worst case two freezes building two
    different handoffs from the same draft. With it, the second blocks on the lock, then sees the
    first's committed status flip and fails cleanly as DraftLocked (409)."""
    d = sess.get(DispatchDraft, draft_id, with_for_update=True)
    _require_draft(d)
    return d


# ---------------------------------------------------------------- create / lifecycle
def next_draft_number(sess) -> int:
    """The next free draft number. Drafts have no on-disk receipt (unlike Stage-1 batches), so this
    only needs to consider DB rows."""
    nums = []
    for (did,) in sess.execute(select(DispatchDraft.draft_id)):
        if did.startswith("draft_") and did[6:].isdigit():
            nums.append(int(did[6:]))
    return (max(nums) + 1) if nums else 1


def create_draft(sess, *, actor: str) -> str:
    """Create an empty draft — instant (no 10-20s build step like Stage 1's batch draw). The advisory
    xact-lock serializes concurrent creates (double-click, two tabs): without it, both could read the
    same next_draft_number and collide on the PK INSERT — an unhandled IntegrityError 500. Released
    automatically at commit/rollback; scope is this one allocation, so contention is a non-issue."""
    from sqlalchemy import text as _text
    sess.execute(_text("SELECT pg_advisory_xact_lock(hashtext('dispatch_draft:create'))"))
    draft_id = f"draft_{next_draft_number(sess):05d}"
    sess.add(DispatchDraft(draft_id=draft_id, status="draft", verified_only=False,
                           dispatch_type=BM.DISPATCH_PRODUCTION,
                           created_at=utcnow(), created_by=actor, meta_json={}))
    sess.flush()
    return draft_id


def abandon_draft(sess, draft_id: str, actor: str, reason: str = "") -> None:
    d = sess.get(DispatchDraft, draft_id, with_for_update=True)   # same race guard as _locked_draft
    if d is None:
        raise KeyError(draft_id)
    if d.status != "draft":
        raise DraftLocked(f"{draft_id} is {d.status}; only a draft can be abandoned")
    d.status = "abandoned"
    d.abandoned_at = utcnow()
    d.abandoned_by = actor
    d.abandon_reason = reason or None
    sess.flush()


# ---------------------------------------------------------------- edits (soft)
def add_district(sess, draft_id: str, district_id: str, meta: dict | None = None) -> None:
    """Add a district to the draft (or restore + no-op if already present+included). `meta` is
    currently unused (districts are re-derived live from the release decision on every read) — accepted
    for forward-compatible call-site symmetry with add_school's shape, not persisted."""
    _locked_draft(sess, draft_id)
    existing = sess.get(DispatchDraftDistrict, (draft_id, district_id))
    if existing is not None:
        existing.included = True
        sess.flush()
        return
    ord_ = len(list(sess.scalars(select(DispatchDraftDistrict.district_id).where(
        DispatchDraftDistrict.draft_id == draft_id))))
    sess.add(DispatchDraftDistrict(draft_id=draft_id, district_id=district_id, ord=ord_,
                                   included=True, overrides_json={}))
    sess.flush()


def remove_district(sess, draft_id: str, district_id: str) -> None:
    """Soft-remove (never hard-delete) — mirrors batch_store's reject_district."""
    _locked_draft(sess, draft_id)
    row = sess.get(DispatchDraftDistrict, (draft_id, district_id))
    if row is None:
        raise KeyError(district_id)
    row.included = False
    sess.flush()


def restore_district(sess, draft_id: str, district_id: str) -> None:
    _locked_draft(sess, draft_id)
    row = sess.get(DispatchDraftDistrict, (draft_id, district_id))
    if row is None:
        raise KeyError(district_id)
    row.included = True
    sess.flush()


def set_override(sess, draft_id: str, district_id: str, rec_key: str, file: str, council_id: str) -> None:
    """Set a per-representation council override, scoped to `district_id`'s own overrides_json (rec_key
    embeds the district_id as a literal prefix, so this can never collide with another district's key
    when overrides are later merged at freeze time)."""
    _locked_draft(sess, draft_id)
    row = sess.get(DispatchDraftDistrict, (draft_id, district_id))
    if row is None:
        raise KeyError(district_id)
    key = f"{rec_key}::{file}"
    row.overrides_json = {**(row.overrides_json or {}), key: council_id}
    sess.flush()


def clear_override(sess, draft_id: str, district_id: str, rec_key: str, file: str) -> None:
    _locked_draft(sess, draft_id)
    row = sess.get(DispatchDraftDistrict, (draft_id, district_id))
    if row is None:
        raise KeyError(district_id)
    key = f"{rec_key}::{file}"
    ov = dict(row.overrides_json or {})
    ov.pop(key, None)
    row.overrides_json = ov
    sess.flush()


def set_verified_only(sess, draft_id: str, verified_only: bool) -> None:
    d = _locked_draft(sess, draft_id)
    d.verified_only = bool(verified_only)
    sess.flush()


def set_dispatch_type(sess, draft_id: str, dispatch_type: str) -> None:
    """The gate@6 human's explicit dispatch-type choice (#618) — the Council Lab opt-in that lets a
    production-rep draft run as a benchmark A/B. Validated, so a typo raises here rather than minting
    a third type that would silently satisfy neither terminus. Setting it does NOT re-check rep
    provenance: benchmark is always allowed, and switching BACK to production is re-checked at freeze
    by assert_dispatch_type_allowed (a draft can legitimately sit in a refusing state while the human
    decides which reps to deselect)."""
    d = _locked_draft(sess, draft_id)
    d.dispatch_type = BM.validate_dispatch_type(dispatch_type)
    sess.flush()


# ---------------------------------------------------------------- read
def _included_districts(sess, draft_id: str) -> list[DispatchDraftDistrict]:
    return list(sess.scalars(select(DispatchDraftDistrict).where(
        DispatchDraftDistrict.draft_id == draft_id, DispatchDraftDistrict.included.is_(True))
        .order_by(DispatchDraftDistrict.ord)))


def _all_districts(sess, draft_id: str) -> list[DispatchDraftDistrict]:
    return list(sess.scalars(select(DispatchDraftDistrict).where(
        DispatchDraftDistrict.draft_id == draft_id).order_by(DispatchDraftDistrict.ord)))


def _merged_overrides(rows: list[DispatchDraftDistrict]) -> dict:
    """Flatten every included district's overrides_json into one dict — safe from cross-district
    collision (rec_key embeds the district_id, verified in the design plan)."""
    out: dict = {}
    for r in rows:
        out.update(r.overrides_json or {})
    return out


def to_view(sess, draft_id: str) -> dict:
    """The gate@6 draft-detail payload: lifecycle fields + ALL districts (included AND soft-removed,
    with flags) + a FRESH priced package (H6.build_handoff_package, recomputed on every read — the price
    is never a stale cached number) + a `preview_identity` staleness token for the freeze step."""
    d = sess.get(DispatchDraft, draft_id)
    if d is None:
        raise KeyError(draft_id)
    all_rows = _all_districts(sess, draft_id)
    included_ids = [r.district_id for r in all_rows if r.included]
    overrides = _merged_overrides([r for r in all_rows if r.included])
    package = H6.build_handoff_package(sess, included_ids, overrides=overrides,
                                       verified_only=d.verified_only,
                                       dispatch_type=d.dispatch_type) if included_ids else \
        {"districts": [], "cost": {"total_usd": 0.0, "n_reps": 0, "provenance": "unknown"},
         "verified_only": d.verified_only, "dispatch_type": d.dispatch_type}
    # build_handoff_package SILENTLY drops a district whose release input is gone (removed from the
    # signals store after it was added to the draft) — unlike freeze-time dispatch_handoff, which
    # tracks `skipped`. Surface the gap here so the console can warn instead of showing two
    # quietly-disagreeing district counts (the draft's own rows vs the priced package).
    pkg_ids = {pd["district_id"] for pd in package["districts"]}
    missing_from_release = [i for i in included_ids if i not in pkg_ids]
    # #618: the reps that would REFUSE this freeze as a production dispatch. Reported (not raised)
    # for the same reason missing_from_release is: the console must be able to render the draft and
    # show the human what to deselect. dispatch_handoff raises at the irreversible step.
    benchmark_reps = H6.benchmark_reps_in_package(sess, package)
    return {
        "draft_id": d.draft_id, "status": d.status, "verified_only": d.verified_only,
        "dispatch_type": d.dispatch_type,
        "created_at": d.created_at, "created_by": d.created_by,
        "dispatched_at": d.dispatched_at, "dispatched_by": d.dispatched_by,
        "handoff_hash": d.handoff_hash,
        "abandoned_at": d.abandoned_at, "abandoned_by": d.abandoned_by, "abandon_reason": d.abandon_reason,
        "districts": [{"district_id": r.district_id, "included": r.included,
                       "overrides": r.overrides_json or {}} for r in all_rows],
        "package": package,
        "missing_from_release": missing_from_release,
        "benchmark_reps": benchmark_reps,
        "preview_identity": HND.package_identity(package),
    }


# A dispatch's origin is DERIVED from receipts on every read, never stored — the most auditable form
# (commandment #1: origin is a re-derivable function of the record an outsider can recompute, not a
# stored assertion that can drift). Three deterministic cases, in precedence order:
#   'draft'   — a dispatched `dispatch_draft` row points at this handoff (the console draft flow).
#   'stage7'  — some back-edge-route `extraction_request`'s `executed_ref` IS this handoff's hash: the
#               back-edge recorded that it produced this handoff (a receipt, not an inference-from-absence).
#   'console' — neither: a first-run / follow-up-batch console dispatch, including all pre-draft history.
# These are mutually exclusive in practice (a 7->6 handoff never gets a draft, and vice-versa); the
# precedence only guards a theoretical overlap. `col` is always a trusted literal (a column ref or a
# bound-param name), never user input — safe to interpolate.
def _origin_case(col: str) -> str:
    return (
        f"CASE "
        f"WHEN EXISTS (SELECT 1 FROM dispatch_draft dd "
        f"            WHERE dd.handoff_hash = {col} AND dd.status = 'dispatched') THEN 'draft' "
        f"WHEN EXISTS (SELECT 1 FROM extraction_request er "
        # the route is the RQ7 CONSTANT, never a re-spelled literal (server.py's is_alt_rep sets the
        # precedent): a renamed back-edge route flows through automatically instead of silently
        # degrading every future back-edge handoff to 'console'.
        f"            WHERE er.executed_ref = {col} AND er.route = '{RQ7.ROUTE_ALT_REP}') THEN 'stage7' "
        f"ELSE 'console' END")


def classify_origin(sess, handoff_hash: str) -> str:
    """The single-handoff form of `_origin_case`, for the detail endpoint — same rule, one row."""
    from sqlalchemy import text as _text
    return sess.execute(_text(f"SELECT {_origin_case(':hh')}"), {"hh": handoff_hash}).scalar()


def list_dispatch_rows(sess) -> list[dict]:
    """Combined left-pane rows: every draft (draft/abandoned) + every dispatched handoff, the latter
    tagged with a DERIVED `origin` ('draft' | 'stage7' | 'console'), computed live from receipts via
    `_origin_case` — no stored column on the immutable `handoff` table, no backfill. See `_origin_case`
    for the rule and why deriving (vs stamping) is the more auditable choice."""
    from sqlalchemy import text as _text

    draft_rows = []
    for d in sess.scalars(select(DispatchDraft).where(
            DispatchDraft.status.in_(("draft", "abandoned"))).order_by(DispatchDraft.created_at.desc())):
        n = len(list(sess.scalars(select(DispatchDraftDistrict.district_id).where(
            DispatchDraftDistrict.draft_id == d.draft_id, DispatchDraftDistrict.included.is_(True)))))
        draft_rows.append({
            "kind": "draft", "draft_id": d.draft_id, "status": d.status,
            "verified_only": d.verified_only, "dispatch_type": d.dispatch_type, "n_districts": n,
            "created_at": d.created_at, "created_by": d.created_by,
            "abandoned_at": d.abandoned_at, "abandon_reason": d.abandon_reason,
        })

    handoff_rows = []
    for r in sess.execute(_text(f"""
        SELECT h.handoff_id, h.handoff_hash, h.created_at, h.created_by, h.status,
               h.n_districts, h.n_reps, h.total_usd, h.cost_provenance, h.dispatch_type,
               {_origin_case('h.handoff_hash')} AS origin
        FROM handoff h
        ORDER BY h.created_at DESC""")).mappings():
        d = dict(r)
        d["kind"] = "handoff"
        d["n_extracted"] = sess.execute(_text(
            "SELECT COUNT(*) FROM extraction WHERE handoff_hash = :h"), {"h": r["handoff_hash"]}).scalar()
        handoff_rows.append(d)

    return draft_rows + handoff_rows


# ---------------------------------------------------------------- freeze (thin wrapper — reuse, don't reinvent)
def freeze_draft(sess, draft_id: str, actor: str, expected_identity: str | None = None) -> dict:
    """Freeze a draft into an immutable handoff, reusing `stage6_dispatch.dispatch_handoff` UNCHANGED —
    this function only supplies the trigger (a persisted draft_id) instead of an ephemeral selection.
    Sets the draft's lifecycle fields IN THE SAME transaction as the freeze (the caller's session): the
    DB side commits atomically — the draft can never read 'dispatched' without the handoff row + state
    events, or vice versa. The DISK side is dispatch_handoff's deliberate #143 ordering (DB statements
    first, file write last, so a file-write failure rolls the DB back cleanly); the residual window is
    the reverse: if the file write succeeds but the outer commit then fails, an orphaned handoff file
    remains on disk and an identical re-freeze 409s on HND.write's FileExistsError until the orphan is
    deleted by hand. Narrow, detectable (a 409 with no matching `handoff` row), accepted.

    Staleness (issue #37, relocated not reinvented): if `expected_identity` is given, rebuild the package
    the same way `to_view` did and compare BEFORE freezing — a stale identity 409s exactly as today's
    `/api/handoff/dispatch` does."""
    d = _locked_draft(sess, draft_id)
    all_rows = _all_districts(sess, draft_id)
    included = [r for r in all_rows if r.included]
    included_ids = [r.district_id for r in included]
    overrides = _merged_overrides(included)
    # ONE assembly, checked and then frozen — the draft-flow twin of the fix in /api/handoff/dispatch
    # (#659). Checking build A and freezing build B let a change between them slip past the gate.
    bundle = None
    if expected_identity:
        bundle = H6.release_bundle(sess, included_ids, overrides=overrides,
                                   verified_only=d.verified_only, dispatch_type=d.dispatch_type)
        if HND.package_identity(bundle.package) != expected_identity:
            raise ValueError("release changed since you last opened this draft — "
                             "reload before freezing")
    doc, path = H6.dispatch_handoff(sess, included_ids, created_by=actor, overrides=overrides,
                                    verified_only=d.verified_only, dispatch_type=d.dispatch_type,
                                    bundle=bundle)
    d.status = "dispatched"
    d.dispatched_at = utcnow()
    d.dispatched_by = actor
    d.handoff_hash = doc["handoff_hash"]
    sess.flush()
    return doc
