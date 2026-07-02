# Archived: Crawlee/Ollama-era enrichment scripts (2026-07-01)

Dead-but-armed scripts retired per issue #28 (fable review §3.1 M-9). All were verified
import-dead via grimp (`find_modules_that_directly_import` → nothing live) before the move;
the full fast suite passed unchanged after it.

| script | why archived |
|---|---|
| `run_batch_pipeline.py` | Fed by the retired `:8000` Ollama API; **deleted ALL bell rows for a district (every year/method, incl. human_provided) before re-import** — a landmine if step 1 were ever "fixed". |
| `retry_failed_districts.py` | Only caller of run_batch_pipeline. |
| `calculate_minutes.py` | Deducted lunch (NET minutes) — violates the gross bell-to-bell standard (REQ-055, issue #15); wrote net values as `automated_enrichment`. |
| `pipeline_import_bell_schedules.py` / `pipeline_verify_enrichment.py` | Crawlee-pipeline importers for calculate_minutes output; reported success even when the commit raised. |
| `ollama_selector.py` | Retired local-LLM URL ranking. |
| `regex_extract_times.py` | Assumed PM for bare hours < 7 (a 6:45 AM start became 18:45); fabricated `elementary` as a default grade level. |
| `import_bell_schedules_from_pdfs.py` | Crashed on insert with pre-schema field names (`school_year=`). |

Kept live (not moved): `content_parser.py` (imported by `import_manual_bell_schedules.py`) and
`interactive_enrichment.py` — note content_parser's own `_calculate_minutes` lunch deduction is
tracked for fixing under issue #26/#19 (the W5 bell-schedule seam work), not archived.

Restore point: this directory + git history. Companion archive: `crawlee-ollama-era-superseded-20260625/`.
