# EDFacts FS059 (Staff FTE): the passages the band-scope Pre-K rule rests on

> **Status: RESEARCH PROVENANCE.** These are verbatim excerpts, not the design. The design that uses them is
> `docs/technical-notes/production-quality-control-research/2026-11-01-school-file-band-scopes-plan.md`
> ("Pre-K without a school key"). They replace three binary .docx specs (#1111). The four passages below are
> **word-for-word identical in all three versions** (checked 2026-11-04 by text-extracting each spec with
> `pandoc -t plain`), so the specs differ only in passages this project does not rely on.

## The specs

| School year | File | Bytes | sha256 | Source |
|---|---|---|---|---|
| SY 2023-24 | `fs059-20-3.docx` (v20.3) | 189,037 | `4e4e8b34ea1d1be931abb4466b945be536b23637aec7d3ffaffd544ec9028bd7` | EDFacts file specifications, SY 2023-24: https://www.ed.gov/data/edfacts-initiative/edfacts-resources/edfacts-file-specifications/edfacts-file-specifications-sy-2023-24 |
| SY 2024-25 | `fs059-21-0-110182.docx` (v21.0) | 188,969 | `92d8088c1249be4e14ed822eb406547b57a5f8eaf3259cc80815a7105211c4ba` | https://www.ed.gov/media/document/fs059-21-0-110182.docx |
| SY 2025-26 | `edfacts-dg528-dg644-staff-fte-v220-fs059-22-0-112797.docx` (v22.0) | 185,866 | `14fada8a52cac4e188d60ad693527f5cb3a990d328ca33ba90436395c6cda92e` | https://www.ed.gov/media/document/edfacts-dg528-dg644-staff-fte-v220-fs059-22-0-112797.docx |

ed.gov refuses automated downloads (HTTP 403), so the files were downloaded by hand (Ian, 2026-11-03). They
are not tracked here; re-download and compare the sha256 to confirm the bytes.

## The passages

**1. School teacher FTE includes Pre-K teachers** (section "Teachers (FTE) (DG644) – School Level"):

> How do Staff FTE (DG528) teacher counts in the SEA and LEA levels relate to the Teachers (FTE) (DG644)
> counts in the school level?
>
> The teachers reported for SEA and LEA levels using the following permitted values should also be
> reported at the school level for Teachers (FTE) DG644:
> - Pre-Kindergarten teachers (PKTCH)
> - Kindergarten teachers (KGTCH)
> - Elementary teachers (ELMTCH)
> - …

**2. Reportable programs are excluded from the school level** (table "Education units included", school
column):

> Schools other than reportable programs that were operational on October 1.

**3. A teacher of both Pre-K and kindergarten is split** (section "Staff FTE (DG528)"):

> If a teacher teaches both prekindergarten and kindergarten, his/her total FTE should be proportionally
> divided between those two teacher categories (PKTCH and KGTCH) based on the time spent with each.

**4. Undistinguished Pre-K/K records are split proportionally:**

> If the staff records do not distinguish between prekindergarten teachers (PKTCH) and kindergarten
> teachers (KGTCH), the total FTE for these two should be divided proportionally between them.

Passages 3 and 4 are why separate Pre-K and kindergarten FTE totals cannot show whether teachers are
blended (#1105).
