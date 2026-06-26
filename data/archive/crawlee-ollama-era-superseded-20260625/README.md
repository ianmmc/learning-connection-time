# Archived: Crawlee + Ollama acquisition era (superseded 2026-06-25)

This directory holds the retired **Crawlee HTTP-scraper + local-Ollama** exploration, archived
when the live pipeline became the stage-based `infrastructure/acquisition/` design (Stages 1–9)
and local Ollama was removed in favor of paid-cloud extraction. **Nothing here is imported by any
live code** — verified by reference audit before the move (no importers in
`infrastructure/acquisition`, `infrastructure/scripts`, `infrastructure/database`, or `tests/`).

Kept reversible (`git mv`, history preserved). Restore with `git mv` back if ever needed.

## Contents

| Archived path | Was | Read/used only by |
|---|---|---|
| `infrastructure-api/` | the FastAPI app (`main.py`, `routes/`, `services/`: `ollama_service`, `crawlee_client`, `patterns_service`, `extraction_service`, `queue_service`, `ollama_launcher`) | nothing live |
| `data-config/` | `prompts/url_ranking.yaml` (`phi3:mini`), `prompts/pdf_triage.yaml`, `crawlee_patterns.json`, `extraction_rules.json` | only `infrastructure-api/services` |
| `scraper-src/` | the Crawlee TS server (`server.ts`, `scraper.ts`, `capturer.ts`, `mapper.ts`, `discovery.ts`, `jobManager.ts`, `queue.ts`, `pool.ts`, `logger.ts`, `types.ts`) | the retired `:3000` HTTP service |
| `scraper-test-crawlee.ts`, `scraper-probe_acquisition.mjs` | Crawlee test + a probe importing the dead `dist/mapper.js` | nothing live |
| `scraper-Dockerfile`, `scraper-docker-compose.yml` | built/ran the Crawlee `:3000` server | the dropped root `docker-compose` `scraper` service |
| `scraper-tsconfig.json`, `scraper-package-lock.json` | TS build config + the Crawlee dependency lock | the dead TS build |

(The Crawlee `dist/` compiled output and `storage/` runtime dir were gitignored/regenerable and
were deleted rather than archived.)

## What stayed LIVE (not archived)

- `infrastructure/scraper/capture_discovery.mjs`, `capture_drive.mjs` + their `*.test.mjs` — the
  live **Stage 3** Playwright capture (need only `playwright` + Node built-ins).
- `infrastructure/scraper/package.json` was trimmed to playwright-only; `README.md` rewritten.
- Root `docker-compose.yml` had its dead `scraper` service removed (`postgres` kept).

## Known stale reference (harmless)

`infrastructure/scripts/enrich/calculate_minutes.py` has a `# Related: extraction_service.py`
*comment* (no import) that now points into this archive.
