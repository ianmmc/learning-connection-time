---
name: checkpoint
description: Save resumable project state before ending a session, a context reset, or after a milestone — the symmetric partner to /catchup. Refresh CLAUDE.md's "Current Status" + "Next session (RESUME HERE)" as a succinct present-state snapshot, triage durable decisions to their proper homes (PROJECT_HISTORY.md / REQUIREMENTS.yaml / design notes) so CLAUDE.md stays a snapshot and not a log, verify the resume-essentials, and commit. Use at session end, before /clear or a context reset, or after completing a requirement/milestone.
---

# /checkpoint — Save Resumable State

The save-state counterpart to `/catchup` (which *reloads* state). Run it at a **checkpoint cadence** —
end of a work session, before a context reset / `/clear`, or after completing a milestone/requirement —
**not on every commit** (that churns the block and bloats history, and a hook can't supply the judgment).
The goal: if the machine crashes or context resets right now, a fresh session resumes swiftly and
correctly from the last commit.

## The bloat guard (read first)

CLAUDE.md's **Current Status** + **RESUME HERE** are a *succinct, overwritten present-state snapshot* —
"where am I, what's next, the essentials to resume." They are **NOT a log.** Anything worth keeping as a
durable record goes to its proper home, so CLAUDE.md never accretes:

- **Decisions / lessons / rationale (high-level)** → `docs/PROJECT_HISTORY.md` — one ADR-style entry, *not* one per fix.
- **Granular per-requirement status** → `docs/REQUIREMENTS.yaml`.
- **Per-stage mechanics + evolution** → the stage design notes (`docs/technical-notes/STAGE*_DESIGN_*.md`) / the flow-diagram decision log.
- **Architecture / governance** → the governance authority doc (`docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`).

## Instructions

When the user runs this skill, perform these steps in order:

1. **Survey what changed since the last checkpoint.**
   ```bash
   git status --short
   git log --oneline -10
   ```
   Identify the commits + any uncommitted work since the RESUME block was last refreshed.

2. **Triage durable items to their proper home (the bloat guard).** For anything from this session worth
   persisting beyond a snapshot, add/update the right doc per the table above — **not** CLAUDE.md. If
   nothing rises to "durable," skip (most sessions add little to PROJECT_HISTORY).

3. **Rewrite CLAUDE.md "Current Status" + "Next session (RESUME HERE — <today>)" as a fresh snapshot**
   (overwrite, don't append). In a few tight lines it must answer:
   - **Where we are** — the last milestone completed (+ commit hash if useful).
   - **What's next** — the immediate next task + the planned sequence after it.
   - **Resume-essentials** — the few commands/preconditions to pick up swiftly (e.g. `pip install -e .`,
     Docker up, `lint-imports` / `pytest -q` to verify, where precious state lives). Keep it tight; link to detail.
   Set the RESUME date to today.

4. **Sanity-check the resume-essentials are current** — the verify commands actually run, the named
   files/flags/tools still exist. A stale RESUME is worse than none.

5. **Commit, and offer to push** (so the snapshot is the recovery point). Conventional message, e.g.
   `docs(CLAUDE.md): checkpoint — <one-line state>`.

6. **Report** the new RESUME summary back in 2–3 lines.

## Notes
- **Cadence, not frequency:** checkpoint at boundaries/milestones; trivial intermediate commits don't need it.
- **Crash-resilience:** milestone commits carry a current RESUME, so a crash loses only the small
  post-milestone delta (recoverable from the diff). An optional non-blocking pre-commit *reminder* hook
  can nudge when the RESUME date is stale — but **this skill is the actual updater**, never a hook.
- **Pairs with `/catchup`:** `/catchup` at session start reloads; `/checkpoint` at session end saves.
