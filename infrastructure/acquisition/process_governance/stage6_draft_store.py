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

from infrastructure.acquisition.process_governance import stage6_dispatch as H6
from infrastructure.acquisition.stage6_handoff import handoff as HND
from infrastructure.acquisition.stage6_handoff.draft_models import DispatchDraft, DispatchDraftDistrict, utcnow


class DraftLocked(Exception):
    """Raised when an edit/freeze/abandon is attempted on a draft that isn't in the right lifecycle state."""


def _require_draft(d: DispatchDraft) -> None:
    if d is None:
        raise KeyError("draft")
    if d.status != "draft":
        raise DraftLocked(f"{d.draft_id} is {d.status}; only a draft can be edited")


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
    """Create an empty draft — instant (no 10-20s build step like Stage 1's batch draw), so no
    reservation-race concern; a plain INSERT inside the caller's transaction suffices."""
    draft_id = f"draft_{next_draft_number(sess):05d}"
    sess.add(DispatchDraft(draft_id=draft_id, status="draft", verified_only=False,
                           created_at=utcnow(), created_by=actor, meta_json={}))
    sess.flush()
    return draft_id


def abandon_draft(sess, draft_id: str, actor: str, reason: str = "") -> None:
    d = sess.get(DispatchDraft, draft_id)
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
    d = sess.get(DispatchDraft, draft_id)
    _require_draft(d)
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
    d = sess.get(DispatchDraft, draft_id)
    _require_draft(d)
    row = sess.get(DispatchDraftDistrict, (draft_id, district_id))
    if row is None:
        raise KeyError(district_id)
    row.included = False
    sess.flush()


def restore_district(sess, draft_id: str, district_id: str) -> None:
    d = sess.get(DispatchDraft, draft_id)
    _require_draft(d)
    row = sess.get(DispatchDraftDistrict, (draft_id, district_id))
    if row is None:
        raise KeyError(district_id)
    row.included = True
    sess.flush()


def set_override(sess, draft_id: str, district_id: str, rec_key: str, file: str, council_id: str) -> None:
    """Set a per-representation council override, scoped to `district_id`'s own overrides_json (rec_key
    embeds the district_id as a literal prefix, so this can never collide with another district's key
    when overrides are later merged at freeze time)."""
    d = sess.get(DispatchDraft, draft_id)
    _require_draft(d)
    row = sess.get(DispatchDraftDistrict, (draft_id, district_id))
    if row is None:
        raise KeyError(district_id)
    key = f"{rec_key}::{file}"
    row.overrides_json = {**(row.overrides_json or {}), key: council_id}
    sess.flush()


def clear_override(sess, draft_id: str, district_id: str, rec_key: str, file: str) -> None:
    d = sess.get(DispatchDraft, draft_id)
    _require_draft(d)
    row = sess.get(DispatchDraftDistrict, (draft_id, district_id))
    if row is None:
        raise KeyError(district_id)
    key = f"{rec_key}::{file}"
    ov = dict(row.overrides_json or {})
    ov.pop(key, None)
    row.overrides_json = ov
    sess.flush()


def set_verified_only(sess, draft_id: str, verified_only: bool) -> None:
    d = sess.get(DispatchDraft, draft_id)
    _require_draft(d)
    d.verified_only = bool(verified_only)
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
                                       verified_only=d.verified_only) if included_ids else \
        {"districts": [], "cost": {"total_usd": 0.0, "n_reps": 0, "provenance": "unknown"},
         "verified_only": d.verified_only}
    return {
        "draft_id": d.draft_id, "status": d.status, "verified_only": d.verified_only,
        "created_at": d.created_at, "created_by": d.created_by,
        "dispatched_at": d.dispatched_at, "dispatched_by": d.dispatched_by,
        "handoff_hash": d.handoff_hash,
        "abandoned_at": d.abandoned_at, "abandoned_by": d.abandoned_by, "abandon_reason": d.abandon_reason,
        "districts": [{"district_id": r.district_id, "included": r.included,
                       "overrides": r.overrides_json or {}} for r in all_rows],
        "package": package,
        "preview_identity": HND.package_identity(package),
    }


def list_dispatch_rows(sess) -> list[dict]:
    """Combined left-pane rows: every draft (draft/abandoned) + every dispatched handoff, the latter
    tagged with an origin flag computed by LEFT JOIN against dispatch_draft.handoff_hash — a handoff with
    NO matching row was frozen directly (today: only the Stage 7->6 back-edge does this), so it reads as
    `from_draft=False` with no new column on the immutable `handoff` table. Origin-agnostic: any future
    direct-freeze caller besides 7->6 is correctly badged too, with no code change needed."""
    from sqlalchemy import text as _text

    draft_rows = []
    for d in sess.scalars(select(DispatchDraft).where(
            DispatchDraft.status.in_(("draft", "abandoned"))).order_by(DispatchDraft.created_at.desc())):
        n = len(list(sess.scalars(select(DispatchDraftDistrict.district_id).where(
            DispatchDraftDistrict.draft_id == d.draft_id, DispatchDraftDistrict.included.is_(True)))))
        draft_rows.append({
            "kind": "draft", "draft_id": d.draft_id, "status": d.status,
            "verified_only": d.verified_only, "n_districts": n,
            "created_at": d.created_at, "created_by": d.created_by,
            "abandoned_at": d.abandoned_at, "abandon_reason": d.abandon_reason,
        })

    handoff_rows = []
    for r in sess.execute(_text("""
        SELECT h.handoff_id, h.handoff_hash, h.created_at, h.created_by, h.status,
               h.n_districts, h.n_reps, h.total_usd, h.cost_provenance,
               (dd.draft_id IS NOT NULL) AS from_draft
        FROM handoff h
        LEFT JOIN dispatch_draft dd ON dd.handoff_hash = h.handoff_hash AND dd.status = 'dispatched'
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
    Sets the draft's lifecycle fields IN THE SAME transaction as the freeze (the caller's session), so a
    crash between the two is impossible — the draft flips to 'dispatched' atomically with the handoff
    row + state events `dispatch_handoff` itself already writes.

    Staleness (issue #37, relocated not reinvented): if `expected_identity` is given, rebuild the package
    the same way `to_view` did and compare BEFORE freezing — a stale identity 409s exactly as today's
    `/api/handoff/dispatch` does."""
    d = sess.get(DispatchDraft, draft_id)
    _require_draft(d)
    all_rows = _all_districts(sess, draft_id)
    included = [r for r in all_rows if r.included]
    included_ids = [r.district_id for r in included]
    overrides = _merged_overrides(included)
    if expected_identity:
        pkg = H6.build_handoff_package(sess, included_ids, overrides=overrides,
                                       verified_only=d.verified_only)
        if HND.package_identity(pkg) != expected_identity:
            raise ValueError("release changed since you last opened this draft — reload before freezing")
    doc, path = H6.dispatch_handoff(sess, included_ids, created_by=actor, overrides=overrides,
                                    verified_only=d.verified_only)
    d.status = "dispatched"
    d.dispatched_at = utcnow()
    d.dispatched_by = actor
    d.handoff_hash = doc["handoff_hash"]
    sess.flush()
    return doc
