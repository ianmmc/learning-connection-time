# Process Governance App (currently the Stage 5 / CP-B review surface)

A local, single-user app for the Stage 5 filter-development exercise and the operational
**Checkpoint B** surface. It ingests the Stage 3/4 output for every captured URL, computes
**deterministic signals** (no AI at runtime), tiers + weakly-categorizes each record, and presents
a 3-column review UI where a human assigns ground-truth labels. Those labels are the data we mine
to define the real Stage 5 filters. (It is slated to grow into the cross-stage governance console —
CP-A queue · CP-B release · CP-C write — but today it is the Stage-5 review/label surface.)

> **Backed by the isolated `governance` Postgres DB (REQ-103), not a SQLite file.** The DB lives in
> the `lct_postgres` Docker container (separate DB + user from the production LCT tables). **Docker
> must be up.** Connection: `infrastructure/acquisition/common/db.py`.

Design rationale: `docs/technical-notes/STAGE5_FILTER_DESIGN_2026-06.md`;
DB setup: `docs/DATABASE_SETUP.md` → "Two databases".

## What it does
- **`stage5_filter/build_signals.py`** — walks `data/raw/lea-website-captures/<district>/`, reads
  `captures.json` (Stage 3) + `processed.json` (Stage 4), and writes the **governance Postgres**
  with, per record: deterministic signals (time counts, in-window times, proximity pairs,
  before/after-5pm, positive/negative keywords, instructional-time phrase, table presence,
  roster-school-name hits, visual/text gap, **per-page time counts** for multi-page PDFs), a
  likelihood **tier** (A–D), a weak **category hypothesis**, **content-hash dedup**
  (`duplicate_of`), and a per-district **topology hypothesis** (hub / per_school / unknown). It also
  caches the raw per-stage artifacts (`discovery_school`/`candidate`/`capture`/`processed_doc`, REQ-103c).
- **`process_governance/server.py`** — FastAPI app serving the review UI, the record/label API, and
  the captured files for inspection.

## Run it
```bash
# 0. Postgres up (the governance DB lives in the lct_postgres container)
docker-compose up -d

# 1. (re)build the governance DB from whatever is on disk under data/raw/lea-website-captures/
python3 -m infrastructure.acquisition.stage5_filter.build_signals

# 2. start the console
python3 -m infrastructure.acquisition.process_governance.server   # -> http://127.0.0.1:8005
#   (or: uvicorn infrastructure.acquisition.process_governance.server:app --reload --port 8005)
```
(Requires the editable install — `pip install -e .` — done once, REQ-098.) Open
<http://127.0.0.1:8005>. Left column: districts → records (by likelihood tier). Center: every
representation, **visual first** (screenshot/PDF), then extracted text. Right: the **objective
signals** and your label controls (radios + checkboxes + note, autosaved).

## Key behaviors
- **No AI at runtime** — all tiering/scoring is deterministic. The only judgment is yours.
- **The script's category guess is hidden until you label** a record — keeps your judgment
  independent (the whole point of collecting a human yardstick). It's revealed after you label so
  you can see agreement/disagreement.
- **Labels survive re-ingest.** `build_signals.py` drops and rebuilds the regenerable tables
  (districts/records/representations/signals + the cross-stage cache) every run, but **never**
  touches the precious `label` / `cluster_split` tables. So you can refine the signal heuristics and
  re-ingest without losing a single hand-entered judgment (labels key on `district_id:hash`).
- **Labels are continuously backed up — automatically, no remembering.** The governance Postgres DB
  is not version-controlled, so it is **not** the backup. Instead:
  - The server **exports every label to `data/acquisition/stage5_review/labels.json` on each
    save** (atomic write). That JSON **is** tracked in git (the gitignore re-includes it) and is
    the durable source of truth. The instant you label, it's safe on disk in a tracked file.
  - `build_signals.py` **re-imports `labels.json` on ingest**, restoring every label. So the DB is
    fully regenerable: signals from disk + labels from JSON. Wipe the governance DB, re-run
    `build_signals.py`, and your labels come back. (Same pattern as `district_status.json` for the
    `state_event` log, REQ-099.)
  - **Getting `labels.json` into commits:** it shows up in `git status` whenever you've labeled —
    just commit it. To make even that automatic, add this to `.git/hooks/pre-commit` (left to you,
    since it's a local, per-machine file that auto-stages on your behalf):
    ```bash
    S5_LABELS="data/acquisition/stage5_review/labels.json"
    if [ -f "$S5_LABELS" ] && ! git diff --quiet -- "$S5_LABELS" 2>/dev/null; then
      git add "$S5_LABELS"; echo "Auto-staged $S5_LABELS"
    fi
    ```
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
