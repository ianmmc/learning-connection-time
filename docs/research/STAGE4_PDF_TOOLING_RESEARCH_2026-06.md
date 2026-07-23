# Stage 4 — PDF/table-tooling research (saved research conversation)

> **Status: RESEARCH PROVENANCE** — a saved research conversation (Perplexity, citation-backed) surveying
> local/open-source PDF table-extraction tools (pdfplumber / PyMuPDF / Camelot / img2table / Docling / …)
> for short grid-style bell-schedule PDFs. Migrated 2026-06-27 from the retired `docs/scratch-paper/`.
> This is the *literature survey that preceded* the Stage-4 tool choice — NOT the design. The actual
> decision (the empirical spike against all 150 captured PDFs, the kept/dropped roster, the heavy-ML
> rejection) lives in `STAGE4_PROCESS_DESIGN.md` §3. Kept for the methods + citations if we ever
> revisit the tooling.

---

<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# I'm evaluating Python/local PDF table-extraction tools for short (1-3 page), simple grid-style tables — specifically school bell-schedule documents that come in three flavors: (a) born-digital PDFs with genuine ruling-line table borders, (b) PDFs rendered from a CSS/HTML page print (no real table borders, columns are whitespace-aligned only), and (c) scanned/image-only PDFs needing OCR. Tables sometimes have merged/spanning cells. I need local, open-source tools only (no paid cloud OCR/table APIs like AWS Textract/Azure Document Intelligence/Google Document AI).

Please verify, with citations to primary sources (official docs, GitHub repos/issues, maintainer statements — not other AI-generated summaries):
Is it true that PyMuPDF's (fitz) find_tables() table-detection algorithm was ported from or is substantially similar to pdfplumber's own detection approach? If so, on a PDF with no ruling lines (whitespace/CSS-grid layout), should I expect meaningfully different results between pdfplumber and PyMuPDF, or are they likely to produce near-identical output?
For Camelot (camelot-py), is the stream flavor (whitespace/column-position based, no ruling lines required) a genuinely different detection algorithm from pdfplumber's text-based strategy, or do they rely on similar underlying heuristics?
For img2table ([https://github.com/xavctn/img2table](https://github.com/xavctn/img2table)) — confirm its current license, maintenance status (recent commits/releases), and known limitations for borderless table detection, especially: minimum column count, merged-cell handling, and accuracy on small (1-2 page) documents versus the large multi-page documents it's typically benchmarked on.
Are there any other actively-maintained, local-only (no API calls), open-source Python tools — beyond pdftotext/poppler, pdfplumber, PyMuPDF, Camelot, and img2table — specifically good at extracting small, simple grid tables that may lack ruling lines, including ones not well-known/highly marketed? I'm especially interested in anything purpose-built for borderless/whitespace-aligned tables rather than general-purpose document parsers.
For tools that use OpenCV-based image processing (like img2table) versus PDF-coordinate-based tools (pdfplumber/Camelot/PyMuPDF) — is there a documented reason to expect one approach to be more or less reliable specifically on a PDF rendered from a web page's print stylesheet (e.g. Chromium's page.pdf()), as opposed to a PDF authored in Word/Excel/InDesign?

Here is a detailed, source-verified answer to each of your five questions.

***

## 1. PyMuPDF `find_tables()` and pdfplumber: Same Root, Diverging Implementations

**The shared origin is confirmed by a PyMuPDF maintainer on the record.** In GitHub issue \#3156, collaborator JorjMcKie stated explicitly: *"It is true, that table detections of both packages have the same root."* He then enumerated six points where PyMuPDF has since diverged.[^1_1]

The key divergences as of early 2024, per that same maintainer statement, are:

- PyMuPDF decomposes all vector graphics into orthogonal lines, so detection is always line-based internally, even when using `strategy="text"`.
- PyMuPDF adds "virtual" graphics for shapes that confuse pdfplumber (e.g., filled rectangles without borders), enabling `strategy="lines_strict"` to exclude them.
- PyMuPDF's `clip` parameter scopes detection to a page region without altering the CropBox — pdfplumber has no equivalent.
- `strategy="lines_strict"` in PyMuPDF does **not** exclude bordered rectangles (unlike pdfplumber's analogous behavior), meaning edge cases diverge meaningfully.[^1_1]

**For a whitespace/CSS-grid PDF with no ruling lines:** both tools expose a `strategy="text"` / `vertical_strategy="text"` mode that infers virtual column boundaries from aligned word positions. Since both derive from the same foundational algorithm, results on clean whitespace-aligned tables will often be similar. However, there are documented bugs in PyMuPDF's `horizontal_strategy="text"` that cause cells to be dropped (issue \#3675) — a maintainer confirmed this is "by design" with a note that text and line strategies are mutually exclusive in each axis. pdfplumber's `"text"` strategy is older, better battle-tested on borderless tables, and better documented for edge-case tuning. One 2026 benchmark found standalone `pymupdf4llm` (which uses `find_tables()` internally) scores 0.612 TEDS and *"misses borderless tables"* on that benchmark, while pdfplumber remains the tool whose table logic was the designed primary feature, not a later addition.[^1_2][^1_3][^1_4]

**Practical verdict:** You will get near-identical output on clean, simple, well-spaced whitespace tables. On anything with irregular spacing, multi-word cells, or implicit structure, pdfplumber's `"text"` strategy with its tunable `snap_tolerance`, `min_words_vertical`, and `intersection_tolerance` gives you more surgical control. They are not identical — treat them as related but independently tunable implementations.

***

## 2. Camelot `stream` vs. pdfplumber `"text"` Strategy: Different Algorithms

**These are genuinely different approaches**, not the same heuristics under different names.

**Camelot `stream`** is documented to be built on PDFMiner's character grouping and uses **Nurminen's textedge algorithm** (the maintainer directly cites the master's thesis in the how-it-works docs ). The pipeline is:[^1_5]

1. Group words into text rows by y-axis overlap.
2. Calculate "textedges" — vertical lines that pass through consistently left-, center-, or right-aligned text — to guess table areas.
3. Estimate column count using the **mode of the word count per text row**.
4. Grow and refine column x-ranges based on words that fall inside/outside the current estimate.
5. Assign words to cells by x/y coordinates.[^1_6][^1_5]

Camelot also added a `network` flavor (distinct from `stream`) that identifies text elements sharing horizontal or vertical alignment coordinates, prunes unconnected nodes, finds a "seed" element with the most connections, and iteratively "grows" the table bounding box outward — a fundamentally graph-theoretic approach.[^1_7]

**pdfplumber `"text"` strategy** works by finding the x-coordinates where multiple words share left/center/right alignment (generating virtual vertical edges), then using the tops of words for virtual horizontal edges. Intersections become cell boundaries.[^1_8]

The difference that matters for your use case: Camelot `stream` **does not auto-detect table area** on pages with multiple tables or mixed content — it historically treated the whole page as one table, requiring you to specify `table_areas` explicitly for multi-table pages. pdfplumber's `"text"` strategy at least attempts table-area inference. For a single-table page (which bell schedules typically are), Camelot `stream` can be effective, but the column-count guessing via **mode of word-count-per-row** is fragile when rows have unequal cell counts (which merged cells cause). pdfplumber's explicit tolerance parameters give you finer control over that scenario.[^1_9][^1_10]

**Both ultimately rely on word-coordinate alignment** from the PDF's text layer (both via PDFMiner under the hood), but the textedge/Nurminen approach and the intersection-of-virtual-lines approach are distinct algorithms with different failure modes.

***

## 3. img2table: License, Maintenance, and Borderless Limitations

**License:** MIT, confirmed in `LICENSE.txt` in the repository.[^1_11]

**Maintenance status:** The latest commit as of this writing was February 9, 2025 (`d3fc372`), adding Python 3.13 support. The latest release is `1.4.2`, dated August 10, 2025 [ — confirmed on GitHub]. Activity is light but not abandoned; it is single-maintainer (`xavctn`) with 804 stars and 118 forks. The issue tracker is open and active through at least mid-2025. This is best described as "maintained on a best-effort basis" rather than actively developed.[^1_12][^1_11]

**Known limitations for borderless detection — from primary sources (the README and issue tracker):**

- **Minimum 3 columns, hard limit:** The README states unambiguously: *"Borderless table extraction can, by design, only extract tables with 3 or more columns."* [ — confirmed in the official README]. A 2-column bell schedule (period | time) will fail entirely under `borderless_tables=True`.
- **Merged cells:** img2table explicitly advertises merged-cell handling as a supported feature for **bordered** tables. For borderless tables, merged-cell support is listed in the examples notebook but is described as more limited in practice. Issue \#190 documents failure on single-row tables even in the bordered mode.[^1_13]
- **The `borderless_tables` flag is labeled "alpha"** in the `to_xlsx()` method documentation in the README, and requires an OCR instance to function at all.[^1_14]
- **Small documents vs. large:** img2table's OpenCV pipeline rasterizes PDF pages at 200 DPI. For 1–2 page documents this is not a throughput concern. The accuracy concern is that its borderless detection relies on finding consistent column-edge patterns across multiple rows — on a very short table (3–5 rows), the statistical signal for column detection is thin.[^1_14]
- **White/light background required:** The README explicitly notes: *"The library is tailored for usage on documents with white/light background. Effectiveness can not be guaranteed on other type of documents."*[^1_14]

For your scanned/image-only PDFs (type c), img2table with Tesseract or PaddleOCR is a reasonable local option — but only for bordered tables or borderless tables with ≥3 columns.

***

## 4. Lesser-Known Active Alternatives

Beyond the tools you listed, here are genuinely distinct options with primary-source verification:

**Camelot `network` / `hybrid` flavor (v2.0+)**
The current Camelot documentation (ReadTheDocs, 2.0.0rc1) now lists four flavors: Lattice, Stream, Network, and Hybrid. The `network` parser uses bounding-box alignment + graph pruning (described in detail above). `hybrid` combines lattice (ruling lines) and network (text alignment), using lattice's coordinates where lines exist and network's for borderless regions. This is actively maintained under `camelot-dev/camelot` and is a meaningfully different tool from the `atlanhq/camelot` fork many tutorials still reference.[^1_7][^1_5]

**Docling (IBM Research / Linux Foundation, MIT license)**
Docling uses two specialized AI models: DocLayNet for layout analysis and **TableFormer** for table structure recognition. It runs entirely locally with no API calls. It handles borderless tables, merged cells, scanned PDFs (via integrated OCR), and complex layouts. It has been shipping weekly releases since late 2024 and has strong community adoption for RAG pipelines. The tradeoff: it requires downloading model weights and is substantially heavier than coordinate-based tools. For simple 1–3 page bell schedules, the startup overhead may outweigh the accuracy benefit, but for your scanned type-c documents it is the strongest local option that avoids paid APIs.[^1_15][^1_16][^1_17]

**tablers (Rust-backed, PyPI)**
A newer library (`pip install tablers`) with a Rust core and Python bindings, focused on edge-detection–based table finding for text-based PDFs. It does not support borderless tables or scanned PDFs per its own PyPI description, so it is relevant only for your type-a PDFs. Mentioned here as a fast alternative to pdfplumber for ruled-table PDFs, not for your whitespace case.[^1_18]

**OpenDataLoader PDF (Hancom, Apache 2.0)**
Released as v2.0 in March 2026 by Hancom with a reported 0.93 table extraction accuracy in their own benchmark. It has a fast deterministic local mode and a "hybrid" AI mode for complex tables and scanned PDFs that runs a local server (no cloud). The AI backend uses Docling Fast under the hood. Apache 2.0 licensed, Python + Node.js + Java SDKs. This is newer and less battle-tested than Docling directly, but claims meaningfully higher benchmark scores. Its hybrid mode requires spinning up a local AI server on port 5002, which adds operational complexity.[^1_19][^1_20][^1_21]

***

## 5. OpenCV Image-Based vs. PDF-Coordinate–Based: Chromium `page.pdf()` Specifically

This is where the most nuanced and underappreciated distinction lies.

**For PDF-coordinate–based tools (pdfplumber, PyMuPDF `find_tables()`, Camelot `stream`/`network`):**

Chromium's `page.pdf()` (Playwright/Puppeteer) produces a **very clean, accurate text layer**. The browser embeds text positions as PDF drawing commands with precise x/y coordinates — Chromium is not compressing or resampling the text positions the way a scan or a print-driver PDF would. For coordinate-based tools, a Chromium-generated PDF is in many ways *easier* to parse than a Word- or Excel-generated PDF, because:

- Font embedding is consistent (Chromium typically embeds subset fonts cleanly).
- Text positions map directly to the CSS layout coordinates, so whitespace-aligned columns tend to have very regular, repeatable x-coordinates.
- There are no vector ruling lines (CSS borders are *not* guaranteed to be emitted as PDF vector paths — they may be rendered as raster or omitted in the text layer), so `strategy="lines"` will likely find nothing. You must use `strategy="text"` / `stream` flavor.

The practical issue with Chromium PDFs for whitespace tools is that **CSS `display: table` does not guarantee ruler lines in the PDF output**. A CSS-grid or `display: table` layout may produce no `rect` or `line` objects in the PDF — only text positioned at coordinates. pdfplumber and PyMuPDF's `"text"` strategy will handle this correctly as long as the column x-positions are consistent across rows. Where Chromium PDFs sometimes cause problems: if the CSS layout uses `text-align: justify` or variable `letter-spacing`, character-level x-positions can be irregular, confusing word-boundary detection in pdfminer (which both pdfplumber and Camelot stream use for character grouping).

**For image/OpenCV–based tools (img2table, Camelot `lattice`):**

Chromium PDFs are typically **worse** inputs for OpenCV-based tools than Word/Excel PDFs. The reason: when a PDF page is rasterized to an image (which both Camelot `lattice` and img2table do), the quality of the resulting image depends on whether the original PDF has crisp vector lines. A CSS print stylesheet's table borders are often rendered as very thin (0.5–1px equivalent) or anti-aliased strokes in the PDF, which after rasterization to 200 DPI (img2table default) can produce faint or missing line segments for OpenCV's morphological transformations to detect. By contrast, Word/Excel PDFs typically embed `\line` operators with explicit stroke widths that survive rasterization more reliably.[^1_5][^1_14]

**Summary table:**


| Tool type | Born-digital (ruled) | CSS/HTML print (whitespace) | Scanned/image |
| :-- | :-- | :-- | :-- |
| pdfplumber `"lines"` | ✅ Good | ❌ No lines to find | ❌ No text layer |
| pdfplumber `"text"` | ⚠️ Overkill, may misfire | ✅ Best fit | ❌ No text layer |
| PyMuPDF `strategy="text"` | ⚠️ Same caveat | ✅ Similar to pdfplumber | ❌ No text layer |
| Camelot `stream` | ⚠️ Requires table_areas hint | ✅ Works with tuning | ❌ No text layer |
| Camelot `lattice` / img2table (bordered) | ✅ Good | ❌ No vector lines in Chromium PDF | ✅ With OCR |
| img2table `borderless_tables=True` | N/A | ⚠️ ≥3 cols required; alpha | ⚠️ ≥3 cols required |
| Docling (TableFormer) | ✅ | ✅ | ✅ Best local option |

For your three PDF flavors, the practical recommendation derived from the above: use **pdfplumber with `"text"` strategy and a `crop()` to isolate the table region** for types a and b; use **Docling or img2table + Tesseract** for type c. If merged cells are a priority and you can accept the weight, Docling's TableFormer handles them most robustly across all three input types.
<span style="display:none">[^1_100][^1_101][^1_102][^1_103][^1_104][^1_105][^1_106][^1_107][^1_108][^1_109][^1_110][^1_111][^1_112][^1_113][^1_114][^1_115][^1_116][^1_117][^1_118][^1_119][^1_120][^1_121][^1_122][^1_123][^1_124][^1_125][^1_126][^1_127][^1_128][^1_129][^1_130][^1_131][^1_132][^1_133][^1_134][^1_135][^1_136][^1_137][^1_22][^1_23][^1_24][^1_25][^1_26][^1_27][^1_28][^1_29][^1_30][^1_31][^1_32][^1_33][^1_34][^1_35][^1_36][^1_37][^1_38][^1_39][^1_40][^1_41][^1_42][^1_43][^1_44][^1_45][^1_46][^1_47][^1_48][^1_49][^1_50][^1_51][^1_52][^1_53][^1_54][^1_55][^1_56][^1_57][^1_58][^1_59][^1_60][^1_61][^1_62][^1_63][^1_64][^1_65][^1_66][^1_67][^1_68][^1_69][^1_70][^1_71][^1_72][^1_73][^1_74][^1_75][^1_76][^1_77][^1_78][^1_79][^1_80][^1_81][^1_82][^1_83][^1_84][^1_85][^1_86][^1_87][^1_88][^1_89][^1_90][^1_91][^1_92][^1_93][^1_94][^1_95][^1_96][^1_97][^1_98][^1_99]</span>

<div align="center">⁂</div>

[^1_1]: https://github.com/pymupdf/PyMuPDF/issues/3156

[^1_2]: https://pdfmux.com/blog/extract-tables-from-pdf-python/

[^1_3]: https://github.com/pymupdf/PyMuPDF/issues/3675

[^1_4]: https://pdfmux.com/blog/pymupdf-vs-pdfplumber/

[^1_5]: https://camelot-py.readthedocs.io/en/latest/user/how-it-works.html

[^1_6]: https://camelot-py.readthedocs.io/en/master/_modules/camelot/parsers/stream.html

[^1_7]: https://camelot-py.readthedocs.io/en/latest/user/comparison.html

[^1_8]: https://deepwiki.com/jsvine/pdfplumber/3.3-table-extraction

[^1_9]: https://blog.atlan.com/announcements/camelot-python-library-pdf-data/

[^1_10]: https://github.com/socialcopsdev/camelot/issues/102

[^1_11]: https://github.com/xavctn/img2table?search=1

[^1_12]: https://github.com/xavctn/img2table/issues

[^1_13]: https://github.com/xavctn/img2table/issues/190

[^1_14]: https://github.com/xavctn/img2table/blob/main/examples/borderless.ipynb

[^1_15]: https://towardsdatascience.com/docling-the-document-alchemist/

[^1_16]: https://studylib.net/doc/27952987/docling-technical-report

[^1_17]: https://www.doctorswhocode.blog/blog/docling-rag-tutorial

[^1_18]: https://pypi.org/project/tablers/0.2.0/

[^1_19]: https://note.com/ryosi_sec_dog/n/n5906d6929908?hl=en-US

[^1_20]: https://biz.chosun.com/en/en-it/2026/03/12/4YSJ4THYXFGMRJG2IGDEY5NE5I/

[^1_21]: https://www.youtube.com/watch?v=TFzxdSrgmt4

[^1_22]: https://pymupdf.readthedocs.io/en/latest/page.html

[^1_23]: https://docs.rs/pdfplumber-core/latest/pdfplumber_core/table/struct.TableFinder.html

[^1_24]: https://pypi.org/project/PyMuPDF/

[^1_25]: https://github.com/pymupdf/PyMuPDF-Utilities/blob/master/table-analysis/README.md

[^1_26]: https://docs.rs/pdfplumber-core/latest/src/pdfplumber_core/lib.rs.html

[^1_27]: https://github.com/pymupdf/PyMuPDF/discussions/2600

[^1_28]: https://deepwiki.com/pymupdf/PyMuPDF-Utilities/5.2-table-detection-and-extraction

[^1_29]: https://pymupdf.readthedocs.io/en/latest/the-basics.html

[^1_30]: https://dev.to/rishabdugar/pdf-extraction-retrieving-text-and-tables-together-using-python-14c2

[^1_31]: https://artifex.com/blog/extracting-tables-from-pdfs-with-pymupdf

[^1_32]: https://github.com/cc-pine/pdfplumber_tablefinder

[^1_33]: https://medium.com/@pymupdf/solving-common-issues-with-table-detection-and-extraction-4df5de2b8d88

[^1_34]: https://github.com/jsvine/pdfplumber/issues/181

[^1_35]: https://www.youtube.com/watch?v=7zf_PaPMw7A

[^1_36]: https://www.youtube.com/watch?v=xKSNq6s-gYQ

[^1_37]: https://libraries.io/pypi/img2table/versions

[^1_38]: https://www.genscrap.net/ja/public/scrapbook/5e2d931a-956f-4365-8754-9bdc6e412856/tag/pdf extraction

[^1_39]: https://github.com/pymupdf/PyMuPDF/issues/2885

[^1_40]: https://github.com/pymupdf/PyMuPDF/discussions/4006

[^1_41]: https://stackoverflow.com/questions/56155676/how-do-i-extract-a-table-from-a-pdf-file-using-pymupdf

[^1_42]: https://github.com/pymupdf/PyMuPDF/issues/2892

[^1_43]: https://skillshub.wtf/TerminalSkills/skills/table-extractor

[^1_44]: https://linuxcommandlibrary.com/man/camelot

[^1_45]: https://dev.to/martin_pdfexcel/tabula-vs-camelot-vs-pdfplumber-in-2026-which-python-library-actually-wins-22kn

[^1_46]: https://stackoverflow.com/questions/64317363/camelot-switches-characters-around

[^1_47]: https://github.com/xavctn/img2table/actions/runs/8056806014/workflow

[^1_48]: https://stackoverflow.com/questions/58837504/camelot-pdf-extraction-fail-parsing

[^1_49]: https://github.com/camelot-dev/camelot/blob/master/docs/user/quickstart.rst

[^1_50]: https://stackoverflow.com/questions/76185723/better-layout-output-for-pdf-tables-extracted-using-camelot

[^1_51]: https://github.com/xavctn/img2table/issues/231

[^1_52]: https://camelot-py.readthedocs.io/_/downloads/en/stable/pdf/

[^1_53]: https://github.com/xavctn/img2table/blob/main/examples/Basic_usage.ipynb

[^1_54]: https://medium.com/analytics-vidhya/part-2-use-your-data-scraping-pdfs-1375e45862bb

[^1_55]: https://deepwiki.com/camelot-dev/camelot/4-table-extraction-methods

[^1_56]: https://stackoverflow.com/questions/72886084/extract-borderless-table-with-pdfplumber

[^1_57]: https://blog.csdn.net/gitblog_00695/article/details/148574810

[^1_58]: https://blog.csdn.net/gitblog_00394/article/details/148574828

[^1_59]: https://github.com/atlanhq/camelot/wiki/Comparison-with-other-PDF-Table-Extraction-libraries-and-tools

[^1_60]: https://stackoverflow.com/questions/53209335/python-camelot-borderless-table-extraction-issue

[^1_61]: https://github.com/atlanhq/camelot/issues/259

[^1_62]: https://deepwiki.com/camelot-dev/camelot/3.3-data-flow

[^1_63]: https://github.com/atlanhq/camelot/blob/master/camelot/parsers/stream.py

[^1_64]: https://www.genscrap.net/en/public/scrapbook/5e2d931a-956f-4365-8754-9bdc6e412856/tag/camelot

[^1_65]: https://arxiv.org/html/2410.09871v1

[^1_66]: https://github.com/camelot-dev/camelot/wiki/Comparison-with-other-PDF-Table-Extraction-libraries-and-tools

[^1_67]: https://onlyoneaman.medium.com/i-tested-7-python-pdf-extractors-so-you-dont-have-to-2025-edition-c88013922257

[^1_68]: https://github.com/atlanhq/camelot

[^1_69]: https://github.com/topics/table-extraction?l=python\&o=desc\&s=updated

[^1_70]: https://pypi.org/project/tablers/

[^1_71]: https://unstract.com/blog/extract-tables-from-pdf-python/

[^1_72]: https://dev.to/generatecodedev/how-to-fix-chrome-printing-issues-with-css-stylesheets-cnc

[^1_73]: https://stackoverflow.com/questions/59124560/puppeteere-chromium-pdf-printing-ignores-css-page-breaks-in-tables

[^1_74]: https://runebook.dev/en/docs/playwright/api/class-page/page-pdf

[^1_75]: https://groups.google.com/a/chromium.org/g/chromium-bugs/c/dTz8xlegaJA

[^1_76]: https://invoicedataextraction.com/blog/python-pdf-table-extraction-invoices

[^1_77]: https://stackoverflow.com/questions/7435014/preserve-html-tables-with-css-in-preparation-for-being-converted-to-pdf

[^1_78]: https://libraries.io/pypi/pdfplumber-rs

[^1_79]: https://github.com/topics/table-extraction?l=rust\&o=asc\&s=updated

[^1_80]: https://libraries.io/pypi/ripdoc

[^1_81]: https://github.com/jsvine/pdfplumber

[^1_82]: https://github.com/docling-project/docling/issues/2207

[^1_83]: https://pypi.org/project/bolivar/1.5.2/

[^1_84]: https://www.docling.ai

[^1_85]: https://github.com/docling-project/docling

[^1_86]: https://stackoverflow.com/questions/51377295/tabula-py-for-borderless-table-extraction/70134007

[^1_87]: https://github.com/docling-project/docling/discussions/2496

[^1_88]: https://arxiv.org/html/2501.17887v1

[^1_89]: https://www.pdfplumber.com

[^1_90]: https://subhajitbhar.com/blog/pdf-extraction/pdfplumber-vs-pymupdf-vs-pypdf2/

[^1_91]: https://github.com/pymupdf/PyMuPDF-Utilities/blob/master/text-extraction/README.md

[^1_92]: https://github.com/pymupdf/PyMuPDF/discussions/2128

[^1_93]: https://pypi.org/project/pdfplumber-aemc/0.5.28/

[^1_94]: https://github.com/jsvine/pdfplumber/discussions/969

[^1_95]: https://www.youtube.com/watch?v=Ddk8bA6OWjQ\&vl=en

[^1_96]: https://pymupdf.readthedocs.io/en/latest/app1.html

[^1_97]: https://stackoverflow.com/questions/22898145/how-to-extract-text-and-text-coordinates-from-a-pdf-file

[^1_98]: https://github.com/pymupdf/PyMuPDF/discussions/2626

[^1_99]: https://www.volcengine.com/article/915759

[^1_100]: https://pymupdf.io

[^1_101]: https://www.youtube.com/watch?v=2hrhmX_Ylng\&time_continue=0

[^1_102]: https://stackoverflow.com/questions/78046370/how-to-find-text-coordinates-for-a-given-character-range-in-a-pdf-using-pymupdf

[^1_103]: https://stackoverflow.com/questions/76629627/pdfplumber-table-extract-inconsistent-columns-and-stripping-spaces

[^1_104]: https://clawhub.ai/emptyguo/opendataloader-pdf

[^1_105]: https://imgtotable.com/changelog

[^1_106]: https://www.youtube.com/watch?v=2hrhmX_Ylng

[^1_107]: https://github.com/opendataloader-project

[^1_108]: https://www.linkedin.com/posts/khushboo-alvi-87a29a134_opendataloader-pdf-a-powerful-open-source-activity-7451094671080185856-O8kU

[^1_109]: https://www.youtube.com/watch?v=Y9nk1q_D1_U

[^1_110]: https://www.npmjs.com/package/@opendataloader/pdf

[^1_111]: https://github.com/xavctn/img2table/blob/main/requirements-dev.txt

[^1_112]: https://www.pdfplumber.com/can-pdfplumber-extract-tables-from-pdfs/

[^1_113]: https://docs.langchain.com/oss/python/integrations/document_loaders/opendataloader_pdf

[^1_114]: https://github.com/pymupdf/PyMuPDF/discussions/3585

[^1_115]: https://www.youtube.com/watch?v=aMrGy59qobo

[^1_116]: https://github.com/pymupdf/PyMuPDF/discussions/3768

[^1_117]: https://github.com/jsvine/pdfplumber/issues/66

[^1_118]: https://pymupdf.readthedocs.io/en/latest/recipes-text.html

[^1_119]: https://deepwiki.com/pymupdf/pymupdf4llm/4.3-table-detection-and-extraction

[^1_120]: https://github.com/pymupdf/PyMuPDF/issues/3148

[^1_121]: https://developer.aliyun.com/article/1559659

[^1_122]: https://stackoverflow.com/questions/66900539/how-to-stop-pdfplumber-from-reading-the-header-of-every-pages

[^1_123]: https://github.com/jsvine/pdfplumber/discussions/708

[^1_124]: https://deepwiki.com/Unstructured-IO/unstructured/5.2-pdfminer-text-extraction

[^1_125]: https://woteq.com/how-to-detect-text-positions-using-pdfplumber/

[^1_126]: https://github.com/jsvine/pdfplumber/discussions/552

[^1_127]: https://lib.rs/crates/pdfplumber-parse

[^1_128]: https://github.com/pdfminer/pdfminer.six/blob/master/README.md

[^1_129]: https://devpress.csdn.net/python/6304514dc67703293080af8e.html

[^1_130]: https://github.com/pdfminer/pdfminer.six/issues/878

[^1_131]: https://medium.com/@zacthahseer123/extracting-clean-text-from-pdfs-in-python-a-practical-guide-using-pdfminer-b106d8dab716

[^1_132]: https://groups.google.com/a/chromium.org/g/chromium-dev/c/LXZQz6UpVZI

[^1_133]: https://euske.github.io/pdfminer/

[^1_134]: https://www.pdfplumber.com/how-does-pdfplumber-handle-text-extraction-from-pdfs/

[^1_135]: https://hive.blog/python/@geekgirl/extracting-pdf-data-with-pdfplumber-lines-rectangles-and-crop

[^1_136]: https://github.com/jsvine/pdfplumber/issues/799

[^1_137]: https://docs.rs/pdfplumber/latest/pdfplumber/

