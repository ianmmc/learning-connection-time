# `batch_00044` Stage-5 ingest strand — measurement and recovery (2026-08-25)

Paired script: `2026-08-25-batch44-ingest-recovery-measure.py` (rerunnable, read-only, imports the
live `status_for_batch` / `stage2_complete` / `RAW_DIR`).

## The question asked

*"To get Huntington and Adair unstuck, do we need #916 fixed?"*

**Answer: no.** #916 is a recurrence fix, not a recovery prerequisite.

## What was measured

Against the live governance DB, using the production predicate rather than a re-implementation:

```
H4.status_for_batch('batch_00044')["rollup"]
→ total 8 · done 8 · resolved 8 · todo 0 · failed 0
  awaiting_capture 0 · awaiting_discovery 0
```

- **No district had a `failed`-latest capture event** — all 8 read `captured_all`/`captured_partial`
  from the 2026-08-24 14:32 recapture. So #670's failed-latest veto was **not** firing.
- **`stage5_ingest_deferred` events = 0.** The batch-wide deferral chain that #916 describes is real
  *as code*, but `batch_00044` is not its instance.
- The ingest gate (`server.py:1974`, `resolved < total`) was therefore **already open**.

The strand was quantified as a coverage gap between Stage 4's output and Stage 5's store:

| district | processed.json URLs | `record` URLs | never ingested | extra in `record` |
|---|---|---|---|---|
| `2905790` ADAIR | 45 | 32 | **13** | 0 |
| `4824000` HUNTINGTON | 37 | 25 | **12** | 0 |

Zero in the reverse direction — the pre-existing rows were an older ingest; the 08-24 work never
landed.

## The finding the question surfaced (→ #921)

The prescribed remedy — "`batch_00044` → Stage 4 → Run" — **was never executable.** The two
conditions are mutually exclusive by construction:

| state | Run control (`stage4.js:77-87`) | ingest (`server.py:1974`) |
|---|---|---|
| `resolved < total` | available | **defers** |
| `resolved == total` | **withdrawn** | would fire |

`_ingest_stage5_if_complete` is reachable *only* from the tail of a Stage-4 run
(`run_stage4_with_ingest`); a grep of `process_governance/static/*.js` and of `server.py`'s routes
finds no other trigger. A batch can only be ingested by passing *through* the transition inside one
run. Miss that window and there is no console path back. Filed as **#921** (epic #706).

This is the shape `stage4_process/headless.py:159-161` names for #671 — *"the false `done` also
removed the means of correcting it"* — except here the `done` is **genuine**.

## Recovery taken

Full `build_signals --assert-floor` re-ingest (Ian's call, 2026-08-25), **not** a bespoke
`ingest_batch` invocation. Rationale: a one-off batch-scoped call would leave districts scored under
different vintages coexisting in one store; the full path keeps a single scoring vintage corpus-wide
and is the already-documented, already-exercised procedure (`GETTING_STARTED.md` §3a).

**Result: PASS.** All 8 districts at 0 missing / 0 extra; ADAIR 45/45, HUNTINGTON 37/37. Every
district carries a fresh `stage5_filter.<stamp>` receipt from the release tail.

`batch_00044` still shows **0 `stage=5` events, and that is expected** — the CLI bypasses
`_ingest_stage5_if_complete`'s bookkeeping, the only writer of that marker. The gap is #921's
remaining scope, not a failed recovery. The script asserts this explicitly (C4) so a later reader
cannot misread it.

## Two corrections to this measurement, recorded rather than silently fixed

1. **`filtered.json` was a bad check.** An earlier pass reported it MISSING for all 8 districts and
   I nearly read that as a finding. It is not: **REQ-164 retired the fixed filename** in favour of a
   datetime-stamped receipt written through the shared `common/receipts.py::write_receipt`
   (`release.py:567`), and nothing reads it as pipeline input anyway (Stage 6 reads the release
   projection from gov_db). The tell was that it was missing for `4843560` too — a district that had
   already reached Stage 9. C3 now globs the receipt the production writer actually emits and scores
   its mtime against `processed.json`, so "the release tail ran" is genuinely falsifiable. *Standing
   rule violated and restored: import the production predicate, never approximate it (#879).*
2. **The first row-count verification of the `pg_dump` was garbage** — an `awk` terminator that never
   matched `\.`, so each table's count ran into the next (reported `cluster_split` 5194 against a
   live 0). Replaced with a parser that tracks `COPY … FROM stdin;` blocks. Both dumps were fine;
   only the checker was broken. *A measurement that cannot fail is not a verdict — and neither is one
   that cannot succeed.*

## Incidental finding — 81 orphaned human labels, NOT caused by this run

Checked because the run reported `2866 labeled` against a pre-run `label` table of 4818 rows. That
gap turned out to be benign (label rows are seeded per record — 5449 attached rows == 5449 records —
so only 2865 carry a `primary_label`). But the check surfaced something else:

| | |
|---|---|
| `label` rows total | 5642 |
| attached to a live record | 5449 |
| **orphaned** (`rec_key` has no record) | **193** |
| …carrying real human work | **81** — all `primary_label='unusable'`, all with `facets_json` |

**All 81 belong to one district: `3173740` Millard Public Schools** (195 label rows, 2 live records).
Its last events include `security_block_reclassified` at **2026-07-20T14:51:59Z** — the WAF
one-attempt rule (Critical Rule #3) — which collapsed its record set. The labels predate that.

**Today's re-ingest did not cause this**, and that is falsifiable rather than asserted: Millard's
`stage5_filter` receipt hash is `-056930fc` on 2026-08-18, 08-19 **and** today's 20260826T034731Z
run — identical content fingerprint across all three, so this ingest reproduced its Stage-5 state
exactly. The orphaning is a month old and stable.

**Open question, not yet filed:** nothing surfaces orphaned labels. They accumulate silently; if a
district's records return under the same `rec_key` the labels reattach (fine), and if they never do,
the human work is dead weight nobody can see. `0 restored from labels.json` in the run output is
about the JSON-backup path, and says nothing about attachment. A standing orphan count would be
cheap. Flagged for Ian, 2026-08-25.

## Grain finding (feeds #96 / #921)

Stage-5 state is **district**-scoped, not batch-scoped — measured:

| | |
|---|---|
| districts ever in a batch | 172 |
| in >1 batch | **73 (42%)**, mean 1.61, max 6 (`4843560`) |
| `record` has a batch column | **no** — keyed on `district_id` |
| `label` keyed on | `rec_key` |

`ingest_batch(district_ids: list)` already takes district IDs and loops `ingest_district` per
district; the name is the only batch-shaped thing about it. "Re-ingest a batch" is therefore a
misleading label on a district-grained operation — and with 42% of districts in more than one batch,
re-ingesting two different batches can mean re-ingesting the same rows twice. **District is the
correct unit; a batch is a *selector* that expands to districts.**

## Rerun

```bash
python3 docs/technical-notes/production-quality-control-research/2026-08-25-batch44-ingest-recovery-measure.py [batch_id]
```

Exit 0 = PASS, 1 = coverage/receipt failure, 2 = NOTHING MEASURED (a district could not be resolved
— never a green zero on an empty sweep).
