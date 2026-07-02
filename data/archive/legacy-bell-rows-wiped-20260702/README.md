# Wiped: legacy bell_schedules rows (2026-07-02)

142 rows / 65 districts from the pre-pipeline enrichment-campaign era, wiped per Ian's
2026-07-01 decision (issue #19 backfill question): reconstruction into Stage-4-ready form was
audited and found IMPOSSIBLE — zero of the 65 districts have pipeline capture dirs, and
data/raw/manual_import_files/ no longer exists on disk. These districts never reached
Stage 3+, so they remain fully eligible for the acquisition pipeline (Stages 1-9), which is
how they will be re-enriched with honestly-labeled gross_bell_to_bell data.

`bell_schedules_legacy_backup_20260702.json` is the complete pre-wipe export. 103 of the 142
rows carry `source_urls` — usable as Stage-2 discovery seeds for these districts.

Method mix at wipe time: human_provided 81 · web_scraping 24 · automated_enrichment 22 ·
pdf_extraction 15. All rows had minutes_basis NULL (unlabeled legacy, migration 019).
