# Wiped: legacy bell_schedules rows (2026-07-02)

142 rows / 65 districts from the pre-pipeline enrichment-campaign era, wiped per Ian's
2026-07-01 decision (issue #19 backfill question). These districts never reached Stage 3+,
so they remain fully eligible for the acquisition pipeline (Stages 1-9), which is how they
will be re-enriched with honestly-labeled gross_bell_to_bell data.

> **CORRECTION (2026-07-02).** The original audit said reconstruction was "impossible — zero
> pipeline capture dirs, manual_import_files gone." True of `data/raw/`, but WRONG overall:
> the hand-collected sources were **migrated to the archive** and survive at
> `data/archive/gt-benchmark-20260622T152627Z/raw_bell_schedule_pdfs/` (361MB, 64 district
> dirs — covering **62 of these 65**), with per-district metadata.json provenance sidecars.
> The wipe decision stands on its own merits (pipeline-fresh, honest provenance); the 27
> curated-GT districts were subsequently injected as **batch_00000** from their frozen
> curation artifacts (`stage1_queue/benchmark_batch.py`), and the archived sources make the
> remaining districts retrofittable the same way if ever needed.

`bell_schedules_legacy_backup_20260702.json` is the complete pre-wipe export. 103 of the 142
rows carry `source_urls` — usable as Stage-2 discovery seeds for these districts.

Method mix at wipe time: human_provided 81 · web_scraping 24 · automated_enrichment 22 ·
pdf_extraction 15. All rows had minutes_basis NULL (unlabeled legacy, migration 019).
