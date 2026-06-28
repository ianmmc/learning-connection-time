# scratch-paper — collaborative, NON-authoritative

> **2026-06-27: this directory is GITIGNORED — its contents are disposable and NOT version-controlled**
> (only this README is tracked). **If it's not disposable, it shouldn't be in here** — promote durable
> records to the canonical docs (`docs/technical-notes/STAGE*_DESIGN_*.md`, `docs/METHODOLOGY.md`,
> `docs/PROJECT_HISTORY.md`, etc.) rather than letting them live here. The batch of records that had
> accreted here was migrated out into the per-stage design notes / METHODOLOGY on this date.

This directory is a **shared whiteboard** for charting things out during collaboration. It has more
persistence than chat context (survives within a session, on local disk), but it is **explicitly not a
source of truth** and is no longer committed.

## What this means
- **Not authoritative.** Nothing here decides anything. The canonical docs are `docs/ACQUISITION_PIPELINE.md`,
  `docs/METHODOLOGY.md`, `docs/TERMINOLOGY.md`, `docs/REQUIREMENTS.yaml`, `docs/PROJECT_HISTORY.md`, etc.
- **Exploratory / in-flux.** Files here may be half-formed, contradictory, or stale. If something here
  conflicts with a canonical doc, the canonical doc wins.
- **Promotion is explicit.** Content moves from here into the authoritative docs **only when the human
  says "this is decided."** Claude will not cite scratch-paper as settled, won't propagate it into
  canonical docs unprompted, and won't treat a contradiction here as a change of plan.

## Diagrams — how to chart things Claude can interpret
Two supported formats (both committed here):

1. **Mermaid code-fences in `.md`** — *preferred for pipeline/flow sketches.* Plain text, clean git
   diffs, renders in GitHub natively, and Claude reads the source directly. Author at
   [mermaid.live](https://mermaid.live) or by hand; for in-VS-Code preview add a Mermaid preview
   extension (e.g. "Markdown Preview Mermaid Support"). Example:
   ```mermaid
   flowchart TD
       Q[1. Queue] --> CPA{CP-A: targeting OK?}
       CPA -->|approve| D[2. Discover]
   ```
2. **draw.io `.drawio.svg`** — for freeform drag-boxes-and-arrows layouts. Use the
   "Draw.io Integration" VS Code extension (publisher `hediet`); create a `*.drawio.svg` file and edit
   it visually in-place. It renders as an image *and* embeds editable diagram XML, so Claude can read
   the diagram from the committed file. (Note: drawing tools don't cleanly *export* Mermaid — these two
   lanes are separate; pick by goal.)

**pandas is unrelated** to diagrams (it's a Python data-analysis library) — ignore any association.

## Convention
- Date or label files so it's clear what's current vs. abandoned.
- A `WIP`/`DRAFT` marker at the top of a file is helpful but not required (the whole directory is WIP).
