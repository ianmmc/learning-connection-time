# Archived: docs/claude-instructions/ modular-briefing system (superseded 2026-06-27)

These four files were the **pre-June-2026 modular Claude briefing**: `CLAUDE_CORE.md` (an older copy of
the root `CLAUDE.md`) plus three on-demand appendices (`REFERENCE` / `WORKFLOWS` / `DATA`). They predated
the acquisition pipeline and the governance re-architecture, so they were heavily **Crawlee / Ollama /
FastAPI-era** (retired) and had become a confounding factor — the root `CLAUDE.md` "Load Additional
Context" table still pointed at them.

**Superseded by (current homes):**
- **Core briefing** → root `CLAUDE.md`.
- **History** → `docs/PROJECT_HISTORY.md`.
- **Dev workflow / structure / commands / conventions** → `docs/GETTING_STARTED.md` (+ `docs/DATABASE_SETUP.md`).
- **Data architecture / SEA integrations / ID crosswalk / complex districts** → `docs/SEA_INTEGRATION_GUIDE.md`
  (which already contained CLAUDE_DATA's "unique" content) + `docs/DATA_SOURCES.md` + `docs/METHODOLOGY.md`.

**Salvaged before archiving (2026-06-27):** file-naming + Python/git conventions and the
`rebuild_database` / `reset_database` orchestrator commands → `docs/GETTING_STARTED.md`. CLAUDE_DATA had
nothing unique to salvage (all in SEA_INTEGRATION_GUIDE). CLAUDE_CORE was a pure stale duplicate.
