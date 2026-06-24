# Stage 5 Review App

A local, single-user labeling tool for the Stage 5 filter-development exercise (and a candidate
for the operational **Checkpoint B** surface). It ingests the Stage 3/4 output for every
captured URL, computes **deterministic signals** (no AI at runtime), tiers + weakly-categorizes
each record, and presents a 3-column review UI where a human assigns ground-truth labels. Those
labels are the data we mine to define the real Stage 5 filters.

Design rationale: `docs/technical-notes/STAGE5_FILTER_DESIGN_2026-06.md`.

## What it does
- **`build_signals.py`** — walks `data/raw/lea-website-captures/<district>/`, reads
  `captures.json` (Stage 3) + `processed.json` (Stage 4), and writes a SQLite DB with, per record:
  deterministic signals (time counts, in-window times, proximity pairs, before/after-5pm,
  positive/negative keywords, instructional-time phrase, table presence, roster-school-name hits,
  visual/text gap, **per-page time counts** for multi-page PDFs), a likelihood **tier** (A–D), a
  weak **category hypothesis**, **content-hash dedup** (`duplicate_of`), and a per-district
  **topology hypothesis** (hub / per_school / unknown).
- **`server.py`** — FastAPI app serving the review UI, the record/label API, and the captured
  files for inspection.

## Run it
```bash
# 1. (re)build the signals DB from whatever is on disk under data/raw/lea-website-captures/
python3 infrastructure/acquisition/stage5_filter/review_app/build_signals.py

# 2. start the local server
cd infrastructure/acquisition/stage5_filter/review_app
python3 server.py            # -> http://127.0.0.1:8005
#   (or: uvicorn server:app --reload --port 8005)
```
Open <http://127.0.0.1:8005>. Left column: districts → records (by likelihood tier). Center:
every representation, **visual first** (screenshot/PDF), then extracted text. Right: the
**objective signals** and your label controls (radios + checkboxes + note, autosaved).

## Key behaviors
- **No AI at runtime** — all tiering/scoring is deterministic. The only judgment is yours.
- **The script's category guess is hidden until you label** a record — keeps your judgment
  independent (the whole point of collecting a human yardstick). It's revealed after you label so
  you can see agreement/disagreement.
- **Labels survive re-ingest.** `build_signals.py` drops and rebuilds the regenerable tables
  (districts/records/representations/signals) every run, but **never** touches the `label` table.
  So you can refine the signal heuristics and re-ingest without losing a single hand-entered
  judgment (labels key on `district_id:hash`).
- **Batch-aware + accumulating.** The `captures/` directory accumulates districts across batches;
  each ingest rebuilds the full record set from disk and groups by `batch_id`. This is what lets
  the same tool serve successive batches (and, potentially, Checkpoint B itself).
- **Dedup.** Byte-identical captures (e.g. a shortlink + its resolved CDN URL) are detected by
  content hash; the non-canonical ones are flagged `duplicate_of` and link to the canonical so
  you label the bytes once.

## Known limitations (v1 — refine with the labels, not by blind tuning)
- **Topology is the noisiest hypothesis.** The `roster_school_names_hit` signal is polluted by CMS
  school-switcher navigation (an Apptegy/SharpSchool page's nav lists every school), which can
  false-positive `hub`. Treat the topology chip as a guess to confirm/correct, not a fact.
- The **category hypothesis** is deliberately weak (keyword/structure heuristics). Your
  corrections to it are the training signal; don't trust it.

## Design system
The UI is styled with the **MMM Design System** (claude.ai/design) — its color/typography/spacing
tokens are vendored under `static/tokens/`. Built as vanilla HTML/JS (no build step); the brand
comes through the token CSS.
