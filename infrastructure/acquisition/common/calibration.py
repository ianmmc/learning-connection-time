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
targets. This is ONLY the instrument. Design authority: PIPELINE_GOVERNANCE_AND_STATE_2026-06.md §11b;
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
_HUMAN_DECISIONS = {"accept", "reject", "modified"}
_AUTO_RECOMMENDATIONS = {"accept", "reject", "escalate"}
_DECISION_SYNONYMS = {
    "approve": "accept", "approved": "accept", "send": "accept", "sent": "accept", "release": "accept",
    "released": "accept", "keep": "accept", "suppress": "reject", "suppressed": "reject", "drop": "reject",
    "dropped": "reject", "skip": "reject", "edit": "modified", "edited": "modified", "override": "modified",
    "flag": "escalate", "review": "escalate", "hold": "escalate", "defer": "escalate",
}
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
    human_decision: Mapped[str] = mapped_column(String)             # accept | reject | modified  (the ground-truth label)
    auto_recommendation: Mapped[str | None] = mapped_column(String)  # accept | reject | escalate  (what auto CURRENTLY would do)
    agreed: Mapped[bool | None] = mapped_column(Boolean)             # human matched auto's terminal action; None when auto would escalate
    blinded: Mapped[bool] = mapped_column(Boolean, default=False)    # human did NOT see the confidence (automation-bias-free subsample)
    # slice keys (certify the worst slice; nullable — not every gate knows every slice)
    state: Mapped[str | None] = mapped_column(String)
    capture_path: Mapped[str | None] = mapped_column(String)        # 'text' | 'vision'
    batch_type: Mapped[str | None] = mapped_column(String)
    run_kind: Mapped[str | None] = mapped_column(String)
    school_level: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


# ----------------------------- pure core (no DB) -----------------------------
def normalize_decision(d):
    """Canonicalize a raw decision string into the shared vocabulary; None/unknown → None (logged as-is,
    never guessed). Case/whitespace-insensitive, with the common console synonyms mapped."""
    if not d:
        return None
    k = str(d).strip().lower()
    k = _DECISION_SYNONYMS.get(k, k)
    return k if k in (_HUMAN_DECISIONS | _AUTO_RECOMMENDATIONS) else None


def agreement(human_decision, auto_recommendation):
    """Did the human match what auto CURRENTLY would have done? Only defined where auto would act
    unilaterally (accept/reject) — the region a future auto-gate would own. When auto would ESCALATE (defer
    to the human), there is no auto terminal decision to agree with → None (this is already the
    human-in-the-loop region, not a calibration data point for unilateral auto). A human 'modified' is an
    accept-with-changes → it agrees with auto 'accept' only if the item was accepted, but since 'modified'
    signals the auto OUTPUT was wrong, it is treated as disagreement with a unilateral auto-accept."""
    h = normalize_decision(human_decision)
    a = normalize_decision(auto_recommendation)
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
    dict over SLICE_KEYS (unknown keys ignored, missing → None). Pure — the writer persists it."""
    slices = slices or {}
    rec = {
        "gate": gate, "item_id": item_id, "district_id": district_id,
        "proxy_name": proxy_name, "proxy_value": proxy_value,
        "human_decision": normalize_decision(human_decision) or str(human_decision),
        "auto_recommendation": normalize_decision(auto_recommendation) if auto_recommendation else None,
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
    worst_slice}] — the post-hoc sweep the issue requires the schema to support."""
    usable = [r for r in records if r.get("proxy_value") is not None
              and normalize_decision(r.get("human_decision")) in ("accept", "reject", "modified")]
    out = []
    for theta in thetas:
        rows = []
        for r in usable:
            auto_accept = (r["proxy_value"] >= theta) if direction == "high_accept" else (r["proxy_value"] <= theta)
            human_accept = normalize_decision(r["human_decision"]) == "accept"   # 'modified' counts as not a clean auto-accept
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
