"""Stage 9 — Incorporate.

The sanctioned write that carries an approved gate@8 per-band determination across the DB boundary
from the acquisition **governance** DB into the **LCT production** DB (`bell_schedules`), where the
minutes supersede statutory time for districts the pipeline succeeded on. It is the one place
acquisition code reaches into `infrastructure.database` (the import-linter exception, other than
Stage 1's read). See docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE9_INCORPORATE_DESIGN.md
and epic #92 (sub-issues #93 write, #94 never-fabricate, #95 provenance).

Module split mirrors closing_argument.py's PURE/IO discipline so the cross-DB hole stays one file wide:
  - provenance.py  — PURE: year resolution, confidence, provenance/notes builders, band grade-span.
  - mapping.py     — PURE: frozen receipt -> list[BandWrite]. No DB import.
  - ledger.py      — governance-side stamp only (the 'incorporated' state_event + idempotency read).
  - incorporate.py — the I/O orchestrator; the ONLY module importing infrastructure.database.
"""
