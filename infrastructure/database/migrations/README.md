# Database Migrations

Numbered SQL migrations (`NNN_*.sql`) plus a **migration ledger** (`schema_migrations`
table) that records which have been applied. The ledger exists because migration
`014_add_staff_scope_to_lct.sql` once landed **half-applied** (some `ALTER`s ran,
others didn't) with no way to detect it — which silently broke LCT re-runs until
2026-06-06. See `docs/PROJECT_HISTORY.md` and `docs/PROJECT_SYNTHESIS.md`.

## Runner: `migrate.py`

```bash
# Show applied vs pending (and checksum drift)
python -m infrastructure.database.migrations.migrate status

# Apply all pending migrations (each runs atomically with its ledger record)
python -m infrastructure.database.migrations.migrate apply

# Record already-applied migrations without running them (existing DB)
python -m infrastructure.database.migrations.migrate backfill --all
```

- **Atomic:** each migration's SQL and its `schema_migrations` row commit in one
  transaction. A failure rolls back both — no more half-applies, no false ledger rows.
- **Checksums:** `status` flags `DRIFT` if an applied migration file changed since it ran.
- **Keyed by filename**, so the two `014_*` files are tracked as distinct entries.

## Writing a new migration

1. Name it `NNN_short_description.sql` with a zero-padded 3-digit prefix (next is `016_`).
2. **Do not** put `BEGIN`/`COMMIT` in the file — the runner wraps it in a transaction.
3. Prefer idempotent DDL (`ADD COLUMN IF NOT EXISTS`, `DROP CONSTRAINT IF EXISTS`).
4. Run `migrate.py apply`, then `migrate.py status` to confirm.

## Notes / known issues

- **Duplicate `014` prefix:** `014_add_security_blocking.sql` and
  `014_add_staff_scope_to_lct.sql` share a number (historical). Both are tracked;
  don't reuse `014` — continue from `016`.
- **Unnumbered legacy scripts** (`create_*.sql`, `add_self_contained_columns.sql`)
  and the `apply_*.py` one-off helpers predate the ledger and are **not** managed by
  `migrate.py`. They reflect schema already present in the database.
- The base schema lives in `infrastructure/database/schema.sql` (treated as the
  pre-`002` baseline); `infrastructure/database/models.py` is the authoritative ORM schema.
