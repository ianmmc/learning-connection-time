#!/usr/bin/env python3
"""End-to-end Stage-5 config promotion flow: shadow → gate → swap → record (#213, epic #209 Phase 2).

Composes the Phase-2 pieces into one advisory flow, still gate-manual (nothing auto-promotes):
  1. `shadow_evaluate` — classify the champion→challenger change (semver level), run the RIGHT shadow +
     gate for that level, and return a decision.
  2. `actuate` — on a promote decision, freeze both artifacts to git + swap the @champion pointer in the DB
     (dormant: nothing reads the pointer to drive live scoring yet — the pipeline still reads CONFIG_DIR).
  3. `record_episode` — append the tuning-ledger episode carrying the non-inferiority verdict.

**Why the shadow differs by change level (a real, load-bearing constraint).** `frontier.gate` re-scores the
stored labeled signals under candidate detector PARAMS — cheap, exact, no re-ingest, no cash. But the knob
JSON files (keyword lists) are baked into the stored signals at INGEST time, so a knob change is invisible
to an in-memory re-score: evaluating it that way would silently score the challenger with the CHAMPION's
knobs. So:
  * **patch** (a detector-param value moved — exactly what the `frontier` grid tunes): the cheap in-memory
    #212 gate is valid and runs here.
  * **minor / major** (a knob doc or a structural key changed): needs a full re-ingest shadow (regenerate
    signals under the challenger knobs, then gate) — heavier, DB-touching, human-initiated. This flow does
    NOT fake it with the cheap path; it returns a decision flagged `needs_reingest_shadow` and does not
    promote. The re-ingest shadow is deferred (knob changes are human-curated + rare; the automated tuning
    path is detector-params). Tracked for when knob auto-tuning arrives.

Design authority: STAGE5_FILTER_DESIGN §5c; issue #213; FINDINGS-AND-DECISIONS §2. PURE-ish composition
(the evaluate step is side-effect-free; actuate/record are the I/O shells)."""
from infrastructure.acquisition.stage5_filter import config_artifact as CA  # noqa: E402
from infrastructure.acquisition.stage5_filter import frontier as FR  # noqa: E402
from infrastructure.acquisition.stage5_filter import promotion_gate as PG  # noqa: E402
from infrastructure.acquisition.stage5_filter import promotion_pointers as PP  # noqa: E402
from infrastructure.acquisition.stage5_filter import tuning_ledger as TL  # noqa: E402


def shadow_evaluate(champion, challenger, records, *, margin, alpha=PG.DEFAULT_ALPHA, seed=0,
                    n_resamples=PG.DEFAULT_N_RESAMPLES):
    """Classify the change, run the level-appropriate shadow + gate, return a decision dict:
    {change_type, requires_full_gate, shadow, promote, verdict?, reasons}. `records` is the frontier
    load_labeled shape. `margin` (Δ) is required by the #212 gate. Side-effect-free — it neither writes
    artifacts nor touches the pointer; `actuate` does that only on promote."""
    change_type = CA.classify_change(champion, challenger)
    base = {"change_type": change_type, "requires_full_gate": CA.requires_full_gate(change_type),
            "champion_version": champion["version"], "challenger_version": challenger["version"]}

    if change_type == "none":
        return {**base, "shadow": "none", "promote": False, "verdict": None,
                "reasons": ["challenger is byte-identical to champion — nothing to promote"]}

    if change_type in ("minor", "major"):
        # A knob / structural change is invisible to the in-memory re-score (knobs are baked into the stored
        # signals). Refuse to fake it — route to the deferred full re-ingest shadow. Not a promote.
        return {**base, "shadow": "needs_reingest_shadow", "promote": False, "verdict": None,
                "reasons": [f"{change_type} change touches knob docs / structure — needs a full re-ingest "
                            "shadow (regenerate signals under the challenger knobs) before the #212 gate; "
                            "the cheap in-memory gate would score the challenger with the champion's knobs. "
                            "Deferred (knob auto-tuning not built)."]}

    # patch: a detector-param value moved — the cheap in-memory gate is exact and valid.
    verdict = FR.gate(records, champion["detector_params"], challenger["detector_params"],
                      margin=margin, seed=seed, n_resamples=n_resamples)
    return {**base, "shadow": "in_memory_rescore", "promote": bool(verdict["promote"]),
            "verdict": verdict, "reasons": verdict["reasons"]}


def actuate(con, champion, challenger, decision, *, cycle, updated_at=None, config_dir=None):
    """On a PROMOTE decision, freeze both artifacts to git + atomically swap the @champion pointer in the
    DB. Guards: refuses a non-promote decision, and refuses if the two artifacts were validated against
    different GT versions (a cross-GT promotion is not a valid comparison — verify_on_load's twin). Returns
    the new pointer state. DORMANT: writing the pointer is bookkeeping — nothing reads it to drive live
    scoring yet (that wiring is gated on gate-mode persistence, #219)."""
    if not decision.get("promote"):
        raise ValueError("actuate called on a non-promote decision — evaluate must promote first")
    if champion["gt_version"] != challenger["gt_version"]:
        raise ValueError(f"GT mismatch: champion validated against {champion['gt_version']}, challenger "
                         f"against {challenger['gt_version']} — re-validate both against one GT before promoting")

    PP.write_artifact(champion, config_dir)
    PP.write_artifact(challenger, config_dir)
    state = PP.load_state(con) or PP.initial_state(champion["version"])
    if state["champion"] != champion["version"]:
        raise ValueError(f"stale promotion: live @champion is {state['champion']}, not the evaluated "
                         f"champion {champion['version']} — re-evaluate against the current champion")
    state = PP.set_challenger(state, challenger["version"])
    state = PP.promote(state, challenger["version"], cycle=cycle)
    PP.save_state(con, state, updated_at=updated_at)
    return state


def record_episode(before_scorecard, after_scorecard, decision, *, knobs_touched, rationale, decided_by,
                   ledger_path=None):
    """Append a tuning-ledger episode carrying the #212 verdict summary (when the patch gate ran). The
    durable record that a promotion happened, with its group-aware non-inferiority evidence beside the
    scorecard deltas."""
    verdict = decision.get("verdict")
    summary = PG.verdict_summary(verdict) if verdict else None
    episode = TL.build_episode(before_scorecard, after_scorecard, knobs_touched=knobs_touched,
                               rationale=rationale, decided_by=decided_by, promotion_gate=summary)
    TL.append_episode(episode, ledger_path)
    return episode
