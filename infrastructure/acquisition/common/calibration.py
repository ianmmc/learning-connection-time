#!/usr/bin/env python3
"""Gate-decision calibration log — the certifiable shadow-mode meter (REQ-121, issue #210).

The instrument half of the manual→auto transition (epic #209). Every time a human works a gate, we ALSO
record a **certifiable shadow-mode record**: the system's continuous confidence proxy for that item, the
human's final decision, whether they agreed with what auto *currently* would have done, the slice keys we
must certify the worst of, and whether the human saw the confidence (a blinded, automation-bias-free
subsample). Months of these rows ARE the calibration corpus — "when the system said θ, the human agreed
X%" — that later justifies a per-gate auto threshold. Build the meter NOW; set thresholds LATER: rule of
three (3/n) forces it — you cannot certify a 1% error ceiling without ~300 clean audited items in a gate's
accept region, and calibration data accrues only forward in time (the #108 facet-accrual lesson).

This module is the base-layer meter (cross-gate, like `district_status.StateEvent`): a precious
item-grained `calibration_event` table + the PURE record-building and post-hoc θ-sweep the log must enable.
Explicit NON-GOALS (deferred, governance-blocked): θ selection, the auto-escalation policy, per-gate α/δ
targets. This is ONLY the instrument. Design authority: PIPELINE_GOVERNANCE_AND_STATE.md §11b;
production-quality-control-research/FINDINGS-AND-DECISIONS.md §0/§3.

Live wiring (calling `record_calibration` from the gate@5/6/7 handlers so the corpus starts accruing) is a
separate, console-touching step — it lands under human inspection, per the ramp-up model.
"""
from sqlalchemy import Boolean, Float, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.acquisition.common import db as gdb  # noqa: E402

# Canonical decision vocabulary. The human's final action and what auto *currently* would do are compared
# in the SAME vocabulary so `agreed` is well-defined. 'escalate' is auto-only (it means "auto would defer
# to a human"); 'modified' is human-only (accepted the item but changed its output — NOT an auto-agreement).
# DELIBERATELY no console-synonym map here (#217 review): translating UI wording ("approved"/"send"/"hold")
# into this vocabulary is the WIRING layer's job (process_governance, next to the strings it owns) — a
# synonym table in common/ is app vocabulary leaking below the layering boundary, invisible to the import
# graph, drifting silently when a button is relabeled.
_HUMAN_DECISIONS = frozenset({"accept", "reject", "modified"})
_AUTO_RECOMMENDATIONS = frozenset({"accept", "reject", "escalate"})
_ROLE_VOCAB = {"human": _HUMAN_DECISIONS, "auto": _AUTO_RECOMMENDATIONS,
               "any": _HUMAN_DECISIONS | _AUTO_RECOMMENDATIONS}
# The slice keys we certify the WORST of — we cannot reconstruct a slice we did not log.
SLICE_KEYS = ("state", "capture_path", "batch_type", "run_kind", "school_level")


class CalibrationEvent(gdb.Base):
    """PRECIOUS, append-only, ITEM-grained shadow-mode record (one row per human gate action). Distinct
    grain from `state_event` (per-district lifecycle) — gate@5 acts on records, gate@7 on extractions — so
    it is a sibling table, written in the same gate-action path, never a column on state_event."""
    __tablename__ = "calibration_event"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gate: Mapped[str] = mapped_column(String, index=True)            # 'gate@5' | 'gate@6' | 'gate@7'
    item_id: Mapped[str] = mapped_column(String, index=True)         # rec_key / handoff / extraction id
    district_id: Mapped[str | None] = mapped_column(String, index=True)
    proxy_name: Mapped[str] = mapped_column(String)                  # 'sort_score' | 'n_send' | 'council_agreement' | …
    proxy_value: Mapped[float | None] = mapped_column(Float)         # the CONTINUOUS confidence (not a bucket) — sweepable post-hoc
    human_decision: Mapped[str] = mapped_column(String)             # accept | reject | modified, or the raw string verbatim (the ground-truth label)
    auto_recommendation: Mapped[str | None] = mapped_column(String)  # accept | reject | escalate, or the raw string verbatim (what auto would do)
    agreed: Mapped[bool | None] = mapped_column(Boolean)             # human matched auto's terminal action; None when auto would escalate
    # server_default (not an ORM default): the one write path is a raw text() INSERT that bypasses ORM
    # defaults entirely, so the omit-it-and-get-False contract must live in the DDL to be true (#217 review).
    blinded: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))   # human did NOT see the confidence
    # slice keys (certify the worst slice; nullable — not every gate knows every slice)
    state: Mapped[str | None] = mapped_column(String)
    capture_path: Mapped[str | None] = mapped_column(String)        # 'text' | 'vision'
    batch_type: Mapped[str | None] = mapped_column(String)
    run_kind: Mapped[str | None] = mapped_column(String)
    school_level: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


# ----------------------------- pure core (no DB) -----------------------------
def normalize_decision(d, role="any"):
    """Canonicalize a raw decision string (case/whitespace) into the vocabulary for `role` ('human' /
    'auto' / 'any'); None/unknown → None (logged as-is by build_record, never guessed). Role-scoped
    membership enforces the documented split (#217 review): 'escalate' is NOT a valid human decision and
    'modified' is NOT a valid auto recommendation — the union check silently accepted both."""
    if not d:
        return None
    k = str(d).strip().lower()
    return k if k in _ROLE_VOCAB[role] else None


def agreement(human_decision, auto_recommendation):
    """Did the human match what auto CURRENTLY would have done? Only defined where auto would act
    unilaterally (accept/reject) — the region a future auto-gate would own. When auto would ESCALATE (defer
    to the human), there is no auto terminal decision to agree with → None (this is already the
    human-in-the-loop region, not a calibration data point for unilateral auto). A human 'modified' is an
    accept-with-changes → it agrees with auto 'accept' only if the item was accepted, but since 'modified'
    signals the auto OUTPUT was wrong, it is treated as disagreement with a unilateral auto-accept."""
    h = normalize_decision(human_decision, role="human")
    a = normalize_decision(auto_recommendation, role="auto")
    if a not in ("accept", "reject"):        # escalate / unknown → not a unilateral-auto data point
        return None
    if h is None:
        return None
    if h == "modified":                      # accepted but auto's output needed fixing → auto was not right
        return False
    return h == a


def build_record(gate, item_id, *, district_id=None, proxy_name, proxy_value,
                 human_decision, auto_recommendation=None, slices=None, blinded=False, created_at):
    """Assemble one calibration record (a dict in the table's shape) and compute `agreed`. `slices` is a
    dict over SLICE_KEYS (unknown keys ignored, missing → None). Pure — the writer persists it.

    Unrecognized decision strings are preserved VERBATIM on both fields symmetrically (#217 review: the
    auto side used to collapse to None, making a typo'd recommendation indistinguishable from 'auto never
    weighed in' — an audit-trail loss); a missing human_decision raises — it is the ground-truth label the
    whole corpus exists for, and `None or str(None)` used to smuggle the literal string 'None' past the
    NOT NULL constraint as fake data."""
    if human_decision is None:
        raise ValueError("human_decision is required — it is the ground-truth label of the calibration record")
    slices = slices or {}
    rec = {
        "gate": gate, "item_id": item_id, "district_id": district_id,
        "proxy_name": proxy_name, "proxy_value": proxy_value,
        "human_decision": normalize_decision(human_decision, role="human") or str(human_decision),
        "auto_recommendation": (normalize_decision(auto_recommendation, role="auto") or str(auto_recommendation))
                               if auto_recommendation is not None else None,
        "agreed": agreement(human_decision, auto_recommendation),
        "blinded": bool(blinded), "created_at": created_at,
    }
    for k in SLICE_KEYS:
        rec[k] = slices.get(k)
    return rec


def sweep_worst_slice(records, thetas, *, direction="high_accept", slice_key=None):
    """The certification math the log ENABLES (read-only; does NOT choose θ — the caller supplies the grid).
    For each candidate θ, replay what a unilateral auto-gate at θ would have decided from each record's
    CONTINUOUS `proxy_value`, count where it disagrees with the human's decision, and report the overall
    error rate + the WORST slice (highest error rate) along `slice_key`. `direction`:
      'high_accept' → auto accepts when proxy_value >= θ (higher proxy = more confident target);
      'low_accept'  → auto accepts when proxy_value <= θ.
    Records with a None proxy_value are skipped (can't place them). Returns [{theta, n, errors, error_rate,
    worst_slice}] — the post-hoc sweep the issue requires the schema to support. `direction` is VALIDATED
    (#217 review): a one-character typo used to fall silently into the low_accept branch and INVERT the
    entire certification read (error_rate 0.0 → 1.0 on the same data) — in the math that licenses a gate's
    autonomy, that must be a loud error, never a quiet wrong answer."""
    if direction not in ("high_accept", "low_accept"):
        raise ValueError(f"direction must be 'high_accept' or 'low_accept' (got {direction!r})")
    usable = [r for r in records if r.get("proxy_value") is not None
              and normalize_decision(r.get("human_decision"), role="human") is not None]
    out = []
    for theta in thetas:
        rows = []
        for r in usable:
            auto_accept = (r["proxy_value"] >= theta) if direction == "high_accept" else (r["proxy_value"] <= theta)
            human_accept = normalize_decision(r["human_decision"], role="human") == "accept"   # 'modified' = not a clean auto-accept
            rows.append((auto_accept != human_accept, r.get(slice_key) if slice_key else None))
        n = len(rows)
        errors = sum(1 for err, _ in rows if err)
        entry = {"theta": theta, "n": n, "errors": errors,
                 "error_rate": (errors / n) if n else None, "worst_slice": None}
        if slice_key and n:
            by_slice = {}
            for err, sv in rows:
                b = by_slice.setdefault(sv, [0, 0])
                b[0] += 1
                b[1] += 1 if err else 0
            worst = max(by_slice.items(), key=lambda kv: (kv[1][1] / kv[1][0], kv[1][0]))
            entry["worst_slice"] = {"value": worst[0], "n": worst[1][0], "errors": worst[1][1],
                                    "error_rate": worst[1][1] / worst[1][0]}
        out.append(entry)
    return out


# ----------------------------- writer (the live-wiring entry point) -----------------------------
_INSERT = text(
    """INSERT INTO calibration_event
         (gate, item_id, district_id, proxy_name, proxy_value, human_decision, auto_recommendation,
          agreed, blinded, state, capture_path, batch_type, run_kind, school_level, created_at)
       VALUES
         (:gate, :item_id, :district_id, :proxy_name, :proxy_value, :human_decision, :auto_recommendation,
          :agreed, :blinded, :state, :capture_path, :batch_type, :run_kind, :school_level, :created_at)""")


def record_calibration(sess, record):
    """Append one calibration record (from build_record) on the given session. The gate@5/6/7 handlers
    call this alongside their existing state_event write; it is idempotent-agnostic (append-only log)."""
    sess.execute(_INSERT, record)
