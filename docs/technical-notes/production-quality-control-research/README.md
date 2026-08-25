# Production quality-control research — measurement scripts

Every `*-measure.py` here is **rerunnable, read-only, and imports the LIVE production functions**
rather than re-spelling their logic. That last rule is not stylistic: a script that approximates the
predicate it measures is evidence about a predicate that doesn't exist (#879 — a bare `endswith`
counted North Little Rock as on-domain for Little Rock, and published a wrong corpus figure).

## How to use these

`ls *-measure.py` is the index — do not keep a hand-maintained list anywhere, it drifts.
**Each script's module docstring carries its own check-map (C1 / C2 / …) and its findings.** Run the
script and read its docstring; never trust a summary of it elsewhere, including this file.

```bash
python3 docs/technical-notes/production-quality-control-research/<script>-measure.py
```

## The rules these scripts encode

- **A measurement that cannot fail is not a verdict.** Every script prints an explicit
  `NOTHING MEASURED` verdict rather than a green zero on an empty sweep — an empty sweep is usually
  a wrong-path bug, not a clean bill of health.
- **Score on the axis that decides the question**, and measure the COMBINED effect rather than
  summing per-item numbers.
- **A PROXY must have the property under test** (#873).
- **Blast radius is part of the fix** — when a measurement motivates a change, commit the script,
  not the recollection (#865/#870), and re-run it after the fix lands.

## Standing watchdogs (arms that must stay at zero / must be re-run)

These are the checks whose *value is in re-running them*, not in their historical result:

| script | watchdog |
|---|---|
| `2026-08-22-batch-done-predicate` | C5's cross-batch window must stay 0 rows |
| `2026-08-24-failed-latest-veto` | C2 must stay 0 violations / 0 newly-asserted `done` |
| `2026-08-21-read-timing-split` | C5 is #873's `login_wall` watchdog; the corpus property clears only on RE-CAPTURE, so `NOTHING MEASURED` is the honest state until then |
| `2026-08-19-chrome-first-send` | C3 is #863's watchdog |
| `2026-08-23-leftpane-vs-stageview` | re-run BEFORE fixing #888 — the corpus moves under it (31 disagreements at filing, 27 the next day) |
| `2026-08-18-segment-main-alternate` | re-run after a re-ingest; S1 should report 0 NULL |
| `2026-08-21-geo-ladder-regression` | quote the plan-aware column, never the raw count |
| `2026-08-23-tool-redundancy` | verdicts are REDUNDANCY, never speedup, until #890 lands timing |
