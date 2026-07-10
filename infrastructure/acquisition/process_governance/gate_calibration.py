"""Wiring-layer translation: console gate actions → calibration records (REQ-121 / issue #210).

Lives in process_governance, NOT in `common/calibration` — mapping the console's decision vocabulary
(a labeled target shape, a dispatch click) into the calibration vocabulary (accept/reject/escalate) is
the WIRING layer's job; `common/` must not carry app wording (#217 review). These are pure builders of the
calibration-record dict; the gate handler calls `calibration.record_calibration(sess, rec)` to persist it
on the SAME session/transaction as the gate's existing write, so the audit row commits atomically.

The three human-supervision gates each get a hook:
  - gate@5 (label): the CALIBRATION-VALUABLE gate — the record's tier is what auto WOULD do to it
    unlabeled (release.decide's tier gate), so `agreed` carries real signal, including the survivorship
    case (tier-D reject that the human labels a target = a false negative auto would have made).
  - gate@6 (dispatch): weak by construction — accept-only (a skipped district is the absence of a row,
    not a reject) and auto is near-tautological (dispatch keys off n_send). Logged for completeness.
  - gate@7 (extract-request review): the human approves/rejects a request-more-evidence DIRECTIVE the
    deterministic detector proposed; the continuous proxy is the district's council agreement ratio
    (n_accepted / (n_accepted + n_unresolved)) — does low council agreement predict the human overriding?
NOTE (Ian, 2026-07-10): approving the council's extracted TIMES (school_fact.human_determination) is a
**gate@8 / Stage-8** activity, NOT gate@7 — Stage 8 is not built yet (#88/#89), so that hook is deferred
to when it lands, and is out of scope for the gate@5/6/7 wiring.
"""
from infrastructure.acquisition.common import calibration as CAL
from infrastructure.acquisition.stage5_filter.build_signals import TARGET_LABELS, NONTARGET_PRIMARIES

# The record's tier IS auto's recommendation for an unlabeled record (release.decide's tier gate,
# release.py): A → send (accept), B/C → hold (escalate → agreed=None, the human-in-the-loop region),
# D → reject. This is what the human's label is being compared against.
_TIER_TO_AUTO = {"A": "accept", "B": "escalate", "C": "escalate", "D": "reject"}


def gate5_label_record(*, rec_key, district_id, tier, sort_score, primary_label, status,
                       state=None, batch_type=None, created_at):
    """A calibration record for a gate@5 human label — or None when there is no terminal decision to log:
    an unlabeled status, a missing primary_label, or an off-vocabulary label (neither a target shape nor a
    terminal non-target). The proxy is the combiner's continuous `sort_score`; `agreed` is computed by
    calibration.agreement against the tier-derived auto recommendation."""
    if status == "unlabeled" or not primary_label:
        return None
    if primary_label in TARGET_LABELS:
        human = "accept"
    elif primary_label in NONTARGET_PRIMARIES:
        human = "reject"
    else:
        return None                      # an off-axis label is not a clean accept/reject data point
    return CAL.build_record(
        "gate@5", rec_key, district_id=district_id, proxy_name="sort_score", proxy_value=sort_score,
        human_decision=human, auto_recommendation=_TIER_TO_AUTO.get(tier),
        slices={"state": state, "batch_type": batch_type}, created_at=created_at)


def gate6_dispatch_record(*, handoff_hash, district_id, n_send, state=None, batch_type=None, created_at):
    """A calibration record for a gate@6 district dispatch. Accept-only by construction (a dispatched
    district is a human 'accept'; a skipped one leaves no row — a documented #210 limitation), and auto is
    near-tautologically 'accept' when n_send>0 — low calibration value, logged for a forward-accruing
    record. item_id is handoff-scoped so re-dispatches of the same district are distinct rows."""
    return CAL.build_record(
        "gate@6", f"{handoff_hash}:{district_id}", district_id=district_id,
        proxy_name="n_send", proxy_value=float(n_send),
        human_decision="accept", auto_recommendation="accept" if n_send > 0 else "reject",
        slices={"state": state, "batch_type": batch_type}, created_at=created_at)


def gate7_request_record(*, request_id, district_id, status, n_accepted, n_unresolved,
                         band=None, state=None, run_kind=None, batch_type=None, created_at):
    """A calibration record for a gate@7 request-more-evidence review — or None for a non-terminal status
    (a 'pending' reopen). The human approves/rejects a DIRECTIVE the deterministic detector proposed (auto
    'accept' = the directive exists), and the continuous proxy is the district extraction's council
    agreement ratio n_accepted/(n_accepted+n_unresolved) — the calibration question is whether low council
    agreement predicts the human overriding the directive. school_level = the request's band."""
    human = {"approved": "accept", "rejected": "reject"}.get(status)
    if human is None:
        return None
    denom = (n_accepted or 0) + (n_unresolved or 0)
    agreement_ratio = (n_accepted / denom) if denom else None
    return CAL.build_record(
        "gate@7", f"request:{request_id}", district_id=district_id, proxy_name="council_agreement",
        proxy_value=agreement_ratio, human_decision=human, auto_recommendation="accept",
        slices={"state": state, "run_kind": run_kind, "batch_type": batch_type, "school_level": band},
        created_at=created_at)
