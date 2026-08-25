# #670 — a capture timeout is a LOUD failure: findings + plan (2026-08-24)

Status: plan approved (Ian, 2026-08-24). Implementation log appended at the bottom as work lands.

## Why this exists

#670's Orange County instance (`1201440`, `batch_00031`): the capture subprocess was killed by
the Python backstop (`TimeoutExpired`), a `failed` state_event was written — and the district
rendered a clean `done` because a fully-populated `captures.json` was on disk and
`status_for_batch` consults disk before gov_db. #671 retired this for REDO batches only
(`completed_by_batch` refuses to count `failed`); ordinary/first-run batches — including the
imminent batches 46-57, 34 districts — still carry the masked-timeout defect.

This work was scoped by reconciling #670 against #622/#623 (epic #723) so nothing built here is
rewritten by the inversion later. Frame set by Ian during planning: **gov_db is the source of
truth; the per-district JSON files are receipts/evidence only (REQ-164 line 4286, REQ-171).
Resolving #670 means the timeout is a loud failure in gov_db — not a smarter comparison of JSON
files.**

## Findings that shaped the scope (3-agent code exploration, 2026-08-24)

1. **The loud-failure signal already exists in gov_db.** `TimeoutExpired` →
   `stage3_capture/headless.py` `_dispatch_and_finish`'s except path writes
   `('capture','failed', note='TimeoutExpired: …')`. The defect is pure precedence:
   `captured = {disk existence}` (headless.py `status_for_batch`) is computed first and the
   `failed_caps` branch is reachable only `if did not in captured`.
2. **A veto, not an inversion.** Full done-marker inversion to gov_db (ordinary batches
   included) is #622's job and is genuinely hard: only 28/147 stage-3 and 0/128 stage-4
   completion events carry a `batch_id` (historical corpus predates the #647 stamp), so
   DB-keying ordinary-batch done-ness withdraws genuine completions — the measured #885 trap.
   The veto (`failed`-latest subtracts from `captured`) is strictly-withdrawing, needs no new
   `state_event` SQL (reuses the existing latest-event `DISTINCT ON` query, which passes the
   one-home fitness rule because it filters on `district_id`, not `batch_id`), and survives
   #622 as a behavioral pin.
3. **Stage 4 likely carries the twin bug.** `stage4_process/headless.py`'s comment still
   asserts "Process FAILURES leave NO processed.json" — the exact claim #670 falsified at
   Stage 3. Same shape: `processed` = disk existence, `failed_procs` consulted only when not in
   `processed`. To be tested first, fixed if red.
4. **Completeness (was this capture everything it intended?) belongs in gov_db.** Node knows
   intended (`meta.candidates.length`) and achieved at the end of `runCapture`; today those
   counts are run-global and only printed. They travel to Python over the subprocess stdout
   channel (`CAPTURE_SUMMARY {json}` tagged line — the ordinary IPC return path, not a receipt
   read) and are stamped onto the stage-3 outcome state_event. `captures.json` stays the one
   sanctioned Node→Python handoff (REQ-164 criterion 6) and is untouched (bare array, fixed
   name). On a clean deadline Node already pads `not_attempted (capture deadline reached)`
   records (ok=false) → `captured_partial`; the summary makes the same fact queryable.
5. **The #623 Node receipt writer is deferred (Ian's call, 2026-08-24).** With counts in
   gov_db the disk receipt is a pure audit mirror — and Node writing it at capture time would
   put a receipt AHEAD of the outcome-event commit, against REQ-164's commit-before-receipt
   ordering. #623 designs that properly alongside the `captures.json` rename it exists for; its
   resolver half re-homes to #622 (only needed once `candidates.json` is renamed).

## Acceptance properties (falsifiable)

- P1 (Stage 3 veto): a district on an ORDINARY batch with a populated `captures.json` and a
  latest `('capture','failed', 'TimeoutExpired…')` event renders `timed_out` and is retriable.
  The test seeding exactly this state MUST FAIL against pre-fix `main`.
- P2 (non-regression): `test_647_an_ordinary_batch_still_uses_the_disk_rule` stays green
  UNCHANGED — no events ⇒ no veto ⇒ disk asserts done (protects the historical corpus from
  re-pay, the #885 lesson).
- P3 (Stage 4 twin): the analogous seeded state at Stage 4 surfaces the failure; whether the
  pre-fix code passes it is itself a finding (the comment claims it cannot happen).
- P4 (counts in gov_db): after a capture run, the stage-3 outcome state_event carries
  intended / planned-this-run / achieved-ok / achieved-failed / not-attempted /
  records-written; "was this capture complete" is answerable from `state_event` with no file
  read.
- P5 (loud mismatch): a missing `CAPTURE_SUMMARY` stdout line, or records-written ≠
  `len(captures.json)`, raises in `_capture_one` → the existing `failed` event path → P1's
  veto surfaces it.
- P6 (one construction): the summary object is built by ONE Node function used for both the
  stdout line and any future receipt (implemented-twice-drifts countermeasure); pinned.
- P7 (receipts stay write-only): no module under `infrastructure/` outside
  `common/receipts.py` calls `latest_receipt`/`iter_receipts` (true today; pinned so it stays
  true).

## Out of scope (stays with #622/#623)

Renaming the four fixed-name artifacts; done-marker inversion; the Node receipt
writer/resolver; a district-grain done predicate; `_prior_doc` aside-vs-receipt glob collision;
`remediation_receipt` retirement; `write_processed` atomicity; arch-manifest Node-producer
scanning.

## Measurement

`2026-08-24-failed-latest-veto-measure.py` (this directory): read-only, imports the live
`status_for_batch`; counts live districts with a `failed`-latest event AND an existing artifact
per stage/batch-type (the veto's blast radius); asserts strictly-withdrawing; explicit
`NOTHING MEASURED` on an empty sweep. Re-run `2026-08-22-batch-done-predicate-measure.py`
afterward (its C1 invariant must hold).

## Implementation log

- **2026-08-24, all properties landed, all falsifiers ran red-then-green.**
  - P1: `test_670_failed_latest_event_vetoes_disk_done_on_an_ordinary_batch` failed on pre-fix
    `main` (`'done' == 'timed_out'`), green after the veto (`stage3_capture/headless.py`:
    `failed_caps` computed first, `captured -= set(failed_caps)`, still the ONE variable).
  - P3: the Stage-4 twin was REAL — the seeded test failed pre-fix (`'done' == 'failed'`).
    Fixed with the same veto on BOTH sets (own done-ness + the upstream capture gate →
    `awaiting_capture`); the false "leave NO processed.json" comment corrected.
  - P4/P5: Node `captureSummary()` (one construction site, exported) + the `CAPTURE_SUMMARY`
    stdout line emitted only after a successful manifest write; `_capture_one` raises on a
    missing line or an n_records/manifest mismatch; `finish_district(summary=)` stamps
    `fingerprints_json.capture_summary` onto the stage-3 completion event.
  - P2/P6/P7: the ordinary-batch disk-rule test green UNCHANGED; source pins (one emission site,
    emitted-after-writeVersioned); the AST receipts-write-only pin in `tests/test_receipts.py`.
  - **Measurement** (`2026-08-24-failed-latest-veto-measure.py`): C1 population **0 at merge** —
    NOT a hollow zero: Ian's same-day remediation re-runs had drained it (Orange County, Broward,
    Cleveland all carry successful latest outcomes; sanity-checked against raw DB/disk counts:
    119/119 disk-done districts have capture events). C2 replayed 460 district×batch×stage rows
    across 58 batches through the LIVE `status_for_batch`: 0 violations, 0 newly-asserted `done`
    (strictly-withdrawing holds). C3 measured 0 — every disk-done district HAS a completion event;
    the historical gap was the `batch_id` STAMP, not the event log, so the no-events guard is
    belt-and-braces and latest-event-wins is the operative protection. The #671 measurement
    (`2026-08-22-batch-done-predicate-measure.py`) re-run: its C1 invariant HOLDS (135 pairs, 0
    newly-asserted).
  - **Live smoke**: a real Node capture run (scratch root, one neutral URL) printed
    `CAPTURE_SUMMARY {"dir":"999_smoke","intended":1,...,"n_records":1,...}` matching the manifest.
  - Suites: DB-free 2490 pass (+5), govdb 409 (+2), npm 105 (+5), lint-imports 4/0, flake8 0,
    arch-manifest 20/20, ledger hygiene 18/18 (REQ-189 added).
