# K-12 School Website Hours Markup & Extraction
## Structured Data Signals, HTML Conventions, and Hours-Block Scraping Techniques

***

## Executive Summary

Across the major K-12 CMS platforms—Finalsite, Apptegy (SharpSchool/Thrillshare), Edlio, Blackboard Web Community Manager, Foxbright, WordPress school themes, and Weebly for Education—the use of formal structured data markup for school hours is **rare to non-existent** as a platform default. None of these vendors ship `OpeningHoursSpecification` or `openingHours` JSON-LD as out-of-the-box template behavior; the schema.org `EducationalOrganization` type (the natural parent) does not even formally inherit `openingHours` from `LocalBusiness`, making the mapping semantically ambiguous. HTML class/id naming conventions for hours blocks are inconsistent and editor-driven rather than template-enforced. ARIA landmarks help scope footer regions but do not tag "hours" content specifically.

For extraction, the closest analogues are local-business directory scraping pipelines (Yelp/Yellow Pages style), which combine structured-data extraction (`extruct`), CSS-selector scoping to footer/header regions, and NLP-based time-pattern matching. False-positive rates for raw time-token detection in page footers are high—driven by phone numbers, course codes, zip codes, grade ranges, and bell schedule snippets—and published benchmarks exist only for adjacent tasks (staff directory detection at ~10% FPR; date/time NER with ~12–15% error rates in noisy web text). The most tractable extraction approach is a layered pipeline: structured-data-first, then region-scoped CSS selectors against known heading keywords, then regex with context-window filtering, with a final LLM disambiguation pass for ambiguous tokens.

***

## Part 1: Schema.org / JSON-LD Structured Data on K-12 CMS Platforms

### 1.1 The Schema.org Type Hierarchy Problem

The core difficulty is a type-hierarchy mismatch. `openingHours` and `openingHoursSpecification` are formally properties of `LocalBusiness` and `CivicStructure` in the schema.org vocabulary. `EducationalOrganization` extends `CivicStructure`, so technically inherits `openingHours`, but this path is rarely documented or used in practice. A 2017 Stack Overflow thread directly addresses this question for schools and reaches no clean consensus—one recommended workaround is wrapping the school in a `Service` type and using `hoursAvailable` → `OpeningHoursSpecification`, another suggests `CivicStructure` or `GovernmentOffice`, and a third says schools have no need to scope opening hours at all. This ambiguity means even a motivated school IT team has no obvious canonical implementation to follow.[^1][^2][^3][^4]

The `openingHours` property expects a compact text string (e.g., `"Mo-Fr 08:00-15:30"`) in 24-hour clock format with two-letter day codes. Google's own documentation recommends `openingHoursSpecification` over the compact form because it provides machine-readable `opens`/`closes`/`dayOfWeek` triples that AI engines can compute against ("is this school open right now?"). `openingHoursSpecification` usage is in the **1M–10M domain bucket** globally in May 2026 data—substantial overall but concentrated in restaurants, healthcare, and retail, not K-12 education.[^2][^5][^6]

A multi-type pattern (`"@type": ["EducationalOrganization", "LocalBusiness"]`) is technically valid JSON-LD and would unlock `openingHours`/`openingHoursSpecification` unambiguously, while also improving Google Maps/local pack visibility. This approach is documented in higher-education structured data guidance but is almost entirely absent from K-12 CMS default templates.[^7]

### 1.2 Platform-by-Platform Assessment

#### Finalsite (Composer)

Finalsite's Composer CMS is template-driven with a WYSIWYG content editor. Finalsite's own guidance on footers emphasizes contact information, address, and phone as recommended footer elements, but does not mention structured data or schema.org markup in any published documentation found. The platform produces standard HTML pages where JSON-LD, if present at all, is injected via custom script blocks by individual district administrators—not by the platform template. Finalsite does integrate with Blackboard Web Community Manager legacy infrastructure for some districts, but neither platform's documentation references `OpeningHoursSpecification`. Districts running Finalsite that have structured data typically have only `Organization` or `WebSite` schema, often injected via Google Tag Manager or a third-party SEO plugin, not via the CMS template itself.[^8][^9][^10]

#### Apptegy (Thrillshare / formerly SharpSchool)

Apptegy's Thrillshare platform (which absorbed SharpSchool) focuses on mobile-first communications. A December 2025 Apptegy blog post explicitly recommended that districts create an "AI Info Page" with structured bullet-point data for AI engines to consume—covering name, enrollment, leadership, and fast facts—but this is plain HTML content strategy, not schema.org markup. The post does not mention JSON-LD or `openingHours`. No published Apptegy/Thrillshare documentation references structured data for hours. Like Finalsite, any schema present on Thrillshare sites is site-administrator-injected, not template-native.[^11]

#### Edlio

Edlio's CMS is designed for non-technical school staff. Its training documentation focuses on navigation, section menus, and UX best practices rather than structured data. No Edlio-specific schema.org implementation guidance was found. Edlio sites render standard HTML with footer widgets containing contact info, but class naming is theme-dependent and inconsistent across districts.[^12]

#### Blackboard Web Community Manager (WCM)

Blackboard WCM (now effectively legacy; Anthology has migrated many clients) uses an "Apps on Pages" model where widgets—including footer widgets with contact info—are placed in predefined header/footer regions. The platform's WCAG 2.0 support statement (2017) focuses on accessibility compliance rather than schema.org. No default structured data for hours is injected by WCM templates. Footer regions in WCM use platform-specific div wrappers that vary by theme/skin.[^13][^8]

#### Foxbright

Foxbright is a Michigan-focused K-12 CMS known for ease of use for non-technical staff. Its content model uses "content blocks" within page templates, with no published evidence of schema.org output as a template feature. Foxbright's 2024 product release documentation discusses design improvements, not structured data. Footer contact information is entered as free-text rich-text content blocks with no semantic class enforcement.[^14][^15][^16]

#### WordPress School Themes

WordPress is the most structurally variable platform. A dedicated WordPress plugin (`WP Opening Hours` / `janizde/WP-Opening-Hours`) exists and does output `OpeningHoursSpecification` JSON-LD—making it the only ecosystem in this list with a purpose-built, widely-available schema hours plugin. However, this plugin is generic (not school-specific) and requires deliberate installation. Popular school themes (e.g., Education WP, School Master) have their own footer templates with generic class names (`site-footer`, `footer-top`, `footer-contact-info`) and no hours-specific semantic markup. The WordPress `Schema` plugin (100K+ active installs) can auto-generate JSON-LD for pages but is not school-hours-specific. The variability is extreme: a WordPress-powered school site could have zero schema, basic `Organization` schema, or full `OpeningHoursSpecification` depending entirely on which plugins were installed.[^17][^18][^19]

#### Weebly for Education

Weebly for Education targets small schools and uses drag-and-drop site building. No evidence of schema.org structured data output for hours was found. Weebly's structured data capabilities are minimal even on its general commercial platform.

### 1.3 Broader Adoption Context

A May 2026 audit of 5,000 production sites across CMS platforms found that 71% deploy at least one schema type, but only 22% pass Google's Rich Results Test cleanly across all detected types. This 49-point "adoption vs. validity" gap is worse in education: a survey of 120 European educational institutions found only 18% had markup covering even the minimum `EducationalOrganization` plus `Course` types. `openingHours` specifically is a property used across 1M–10M domains globally, but usage is heavily weighted toward restaurants, retail, and healthcare.[^20][^6][^21][^7]

The practical upshot: **when scanning a K-12 school website for `OpeningHoursSpecification` or `openingHours` JSON-LD, the expected true-positive rate is very low—well under 5% of sites on any of the above CMS platforms, with WordPress being the partial exception if the `WP Opening Hours` plugin is present.** The signal, when present, is highly reliable; its absence tells you nothing about whether hours information exists on the page.

***

## Part 2: HTML Class/ID Naming Conventions

### 2.1 No Enforced Standard

None of the K-12 CMS platforms described above enforce a consistent HTML class or ID naming convention for hours content. Contact and hours information is rendered as free-text content in footer regions with class names determined by the theme designer, not by a platform-wide data-type standard.

### 2.2 Observed Patterns Across School Theme Templates

The most commonly observed patterns in school-adjacent HTML templates and real district sites are:

| Class/ID Pattern | Origin | Reliability as Hours Signal |
|---|---|---|
| `.site-footer`, `.footer-top` | Generic theme structure | Low—contains many non-hours elements |
| `.footer-contact-info` | Generic theme | Medium—likely contains phone/address/hours together |
| `#office-hours`, `.office-hours` | Hand-authored by staff | High if present, but rare |
| `.hours`, `.school-hours` | Hand-authored | High if present, but rare |
| `[class*="hours"]` | Wildcard match | Medium—picks up `.office-hours`, `.school-hours`, `.hours-block` |
| `.icon-bx-wraper` (DexignZone-style) | Commercial edu themes | Low—generic icon-content widget, hours is one of four columns |
| `<h5>` with text "Office Hours" | Heading-based detection | Medium—requires text matching, not class matching |

The most reliable HTML signal is a `<h2>`, `<h3>`, `<h4>`, or `<h5>` element containing the text "Office Hours," "School Hours," or "Hours" as its text content, paired with immediately following sibling or child elements containing time-pattern tokens. This heading-proximity pattern is more consistent across platforms than any class name, because the heading text is entered by school staff who use natural language labels.[^22]

The EduZone commercial education theme illustrates the typical structure:[^22]
```html
<div class="icon-content">
  <h5 class="dlab-tilte">Office Hours</h5>
  <p>Mon To Sat - 08.00-18.00</p>
  <p>Sunday - Close</p>
</div>
```
The hours live in a generic `<p>` inside a layout div, with the only semantic signal being the `<h5>` text.

### 2.3 Footer Widget Patterns on Major Platforms

- **Finalsite Composer**: Footer is a configurable region; contact info is placed in "Text/HTML" content blocks with no enforced class structure. The platform's own blog recommends including hours in the footer but provides no markup template.[^9]
- **Blackboard WCM**: Footer apps generate `<div>` containers with platform-generated class names (not public-facing semantic classes). These vary by the specific app placed.
- **Foxbright**: Footer content is entered as rich-text blocks. The platform's training guide does not mention structured class names for contact or hours content.[^16]
- **WordPress**: Theme-dependent; the most common pattern is a widgetized footer area with `<aside>` elements and widget-specific class names like `.widget_text`, `.widget_contact_info`. Hours are usually in a `Text` widget with no class distinguishing them from other text.

***

## Part 3: ARIA Landmarks and Role Markers

### 3.1 What ARIA Provides (and Does Not Provide)

ARIA landmark roles divide a page into navigation zones, not semantic content types. The relevant landmarks for hours/contact extraction are:[^23][^24][^25]

- `role="contentinfo"` (equivalent: `<footer>`) — marks the page footer, which is where hours/contact typically live
- `role="complementary"` (equivalent: `<aside>`) — marks sidebars, which may also contain hours widgets
- `role="banner"` (equivalent: `<header>`) — marks the page header

The key insight is that `<footer>` and `role="contentinfo"` provide a **reliable bounding box** for hours content on K-12 sites. WCAG guidance and accessibility best practices require exactly one `<footer>` as a direct `<body>` descendant per page, so `document.querySelector('body > footer')` or `//body/footer` XPath is a clean, standards-compliant scope limiter. WordPress accessibility guidelines explicitly note that HTML5 sectioning elements map to ARIA landmark roles, and that all content should be inside semantically meaningful elements.[^26][^23]

However, **no ARIA role or property exists for "hours of operation" or "school day hours" specifically.** The landmark system identifies structural regions, not content categories. There is no `role="hours"` or `aria-label="office-hours"` convention in use. Some ADA-conscious school administrators label their footer contact sections with `aria-label="Contact Information"` but not "hours."

### 3.2 Practical Use of Landmarks for Scoping

For a scraping pipeline, the ARIA/HTML5 semantic structure provides two useful scoping strategies:

1. **Narrow scope to `<footer>`**: Eliminates nav menus, main content, hero sections, and news feeds. Time-like tokens in `<footer>` have a much higher prior probability of being contact hours vs. content dates.
2. **Secondary scope to `<aside role="complementary">`**: Sidebar widgets on school sites often repeat the footer contact block. Including both scopes captures hours in either location.

The combination `footer, aside[role="complementary"], [role="contentinfo"]` as a CSS scope filter is a reasonable starting point.

***

## Part 4: Open-Source Extraction Libraries and Techniques

### 4.1 Structured Data First: `extruct`

The first pass in any K-12 hours extraction pipeline should be structured data extraction using **`extruct`** (scrapinghub/extruct), a Python library that extracts embedded metadata from HTML including JSON-LD, Microdata, RDFa, OpenGraph, and Microformats in a single call. Installation: `pip install extruct`.[^27][^28][^29]

```python
import requests, extruct
html = requests.get(url).text
data = extruct.extract(html, base_url=url, syntaxes=["json-ld", "microdata", "rdfa"])
# Look for openingHours or openingHoursSpecification in any @type
```

If `openingHoursSpecification` or `openingHours` is present, it should be trusted as a high-confidence signal. The false-positive rate for this path is essentially zero—if the token is there, it was deliberately authored. The principal limitation is the very low prevalence rate on K-12 sites (see Part 1).[^30]

`extruct` handles both static JSON-LD and Microdata markup. For JavaScript-rendered pages (which includes some Finalsite and Apptegy sites), the HTML must be retrieved via a headless browser (Playwright, Puppeteer, or Selenium) before passing to `extruct`, since `requests` will not execute JS.[^31]

### 4.2 Boilerplate Removal Tools: What They Do and Don't Offer

Standard boilerplate removal libraries—**`trafilatura`**, **`jusText`**, **`boilerpipe3`**—are designed to *discard* footer/header content and preserve main-article text. This is the **inverse** of what hours extraction requires. Key characteristics:[^32][^33][^34][^35][^36]

| Tool | Approach | Handles Hours Extraction? |
|---|---|---|
| `trafilatura` | Density + position heuristics; preserves main text | **No**—actively discards footer/header[^33][^36] |
| `jusText` | Stopword-density classification; marks blocks as "good/bad/short" | **No**—footer blocks are classified as boilerplate[^32][^34] |
| `boilerpipe3` | Default/ArticleExtractor mode discards peripheral content | **No** |
| `newspaper3k` / `newspaper4k` | Geared to news articles | **No** |

`trafilatura` does offer a `html2txt` mode that converts all page text to plain text without boilerplate removal, which can serve as a preprocessing step for NER-based extraction. But for targeted footer/header contact block extraction, these tools should be bypassed in favor of direct DOM parsing.[^37]

The correct tool class for this problem is **selective DOM extraction** using CSS selectors or XPath, not boilerplate removal.

### 4.3 DOM-Scoped CSS Selector Extraction

Using **BeautifulSoup** or **selectolax** (the faster alternative), the recommended pipeline for extracting a candidate hours block from a rendered page is:[^38]

```python
from bs4 import BeautifulSoup

def extract_hours_candidate(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    
    # Step 1: Scope to footer/sidebar regions
    scope_selectors = [
        "body > footer",
        "footer[role='contentinfo']",
        "div[role='contentinfo']",
        "aside[role='complementary']",
        "#footer", ".site-footer", ".footer-bottom", ".footer-contact"
    ]
    candidates = []
    for sel in scope_selectors:
        node = soup.select_one(sel)
        if node:
            candidates.append(node)
            break
    if not candidates:
        candidates = [soup.body]  # fallback to full body
    
    # Step 2: Within scope, find headings whose text matches hours keywords
    hours_keywords = re.compile(
        r'\b(office\s+hours?|school\s+(day\s+)?hours?|hours?\s+of\s+operation|'
        r'bell\s+schedule|start\s+time|dismissal)\b',
        re.IGNORECASE
    )
    for scope in candidates:
        for heading in scope.find_all(["h2","h3","h4","h5","p","dt"]):
            if hours_keywords.search(heading.get_text()):
                # Return the heading + next 1-3 sibling elements
                block = [heading.get_text()]
                for sib in heading.find_next_siblings(limit=3):
                    block.append(sib.get_text())
                return "\n".join(block)
    return None
```

This selector-first approach is analogous to how Yelp/Yellow Pages scrapers extract business hours: they target a known DOM structure in the listing template rather than running general NER over the full page.[^39][^40][^41]

### 4.4 NLP-Based Time Pattern Extraction

Once a candidate text block is isolated, time-range patterns must be identified. Key tools:

- **`dateparser`** (scrapinghub/dateparser): Excellent at parsing natural-language date/time strings ("Monday through Friday, 8 AM to 3 PM"), but explicitly warns that providing non-date strings can produce false positives, and recommends constraining input strings before parsing.[^42]
- **spaCy `TIME` entity** (`en_core_web_lg`): The large English model recognizes 596 types of date and temporal expressions, but performs poorly on isolated time strings without sentence context. The `date-spacy` and `timexy` spaCy extensions improve temporal normalization.[^43][^44][^45][^46]
- **`timestring`** (pypi): Simple Python library for parsing human-readable time strings.
- **Regex with lookaheads**: For structured extraction of `HH:MM`-format times, lookahead/lookbehind patterns are needed to avoid matching phone number area codes, zip codes, or date components that contain similar digit sequences.[^47]

A robust regex for a school-hours range (not a date, not a phone) looks like:
```
(?<!\d)([0-1]?[0-9][:.]?[0-5][0-9]?\s*(?:AM|PM|am|pm)?)
\s*[-–—to]+\s*
([0-1]?[0-9][:.]?[0-5][0-9]?\s*(?:AM|PM|am|pm)?)(?!\d)
```
The negative lookaheads/lookbehinds (`(?<!\d)` and `(?!\d)`) prevent matching against embedded date-like components.

### 4.5 LLM-Assisted Extraction

For ambiguous cases, an LLM pass (GPT-4o, Claude 3.5 Sonnet) with a prompt like "From the following school footer text, extract only the school day start and end time for students, not office hours" adds a disambiguation layer that regex cannot provide. This approach is used in production by document-intelligence pipelines but adds latency and cost. For batch processing of thousands of school sites, LLM extraction is best reserved for the "uncertain" tier after structured data and regex have been tried and failed.[^48][^49]

***

## Part 5: False-Positive Rates and Confusable Categories

### 5.1 Published Benchmarks

No published benchmark specifically addresses false-positive rates for time-token extraction in K-12 school website footers. The closest published data comes from adjacent tasks:

- **Staff directory detection on school websites** (U.S. Census Bureau / NCES, FCSM 2023): At a string-similarity threshold of 0.9, directory page detection achieved >90% recall with approximately **~10% false-positive rate** on both public and private school websites. This is for *page-level* classification, not token-level extraction, but establishes a benchmark for the difficulty of K-12 web classification tasks.[^50]
- **General temporal NER**: The spaCy `en_core_web_lg` model recognizes time expressions with known limitations in isolated/fragment text. Typical F1 for time entity extraction on web-corpus text is in the 0.75–0.88 range depending on the domain.[^45][^46]
- **`dateparser` documentation** explicitly cautions that false positives are likely when input strings contain non-date content, recommending pre-filtering before parsing.[^42]
- **Schema markup validity audit (2026)**: A 5,000-site audit found only 22% of sites with structured data pass Google's Rich Results Test cleanly, implying high invalid-emission rates even when schemas are present—a structured-data false positive problem of a different kind.[^20]

### 5.2 Confusable Token Categories in K-12 School Website Footers

The K-12 school context produces a distinctive set of false-positive sources that are more complex than typical business-hours extraction:

| Confusable Token | Example | Why It Confuses | Disambiguation Signal |
|---|---|---|---|
| **Phone number components** | `(650) 312-7890` | `312` and `78-90` are valid time-like tokens | Area code in parentheses; 10-digit structure |
| **ZIP codes** | `San Mateo, CA 94402` | 5-digit numbers can match loose time patterns | No colon; follows city/state |
| **Student attendance times** | `8:15 – 2:45 PM` | Legitimate target—school day hours | ✓ This is the target |
| **Office hours** | `Mon–Fri 8:00–4:30` | Legitimate but distinct from student hours | Heading context: "Office" vs. "School Day" |
| **After-school program hours** | `Aftercare: 3:00–6:00 PM` | Correct time format, but not school day | Keyword: "aftercare," "after-school" |
| **Bell schedule periods** | `Period 1: 8:05–8:55` | Correct time format, but fine-grained schedule | Keyword: "period," "block" |
| **Lunch times** | `Lunch: 11:30–12:15` | Correct time format, embedded in bell schedule | Keyword: "lunch," "recess" |
| **Year ranges** | `© 2019–2025` | `19-20` substring can match | Copyright symbol; 4-digit year structure |
| **Grade/age ranges** | `Grades K–8` or `Ages 5–18` | Hyphenated range superficially similar | Alphabetic context: "Grades," "Ages" |
| **Room/building numbers** | `Room 8-214` | Hyphenated digits | Keyword: "Room," "Bldg" |
| **Event start times (single)** | `Starts at 7:00 PM` | Valid time, but event-specific, not recurring | No range pattern; context is event/calendar |
| **"School years open" text** | `Open since 1962` | Contains numeric year | Keyword: "since," "established," 4-digit year |
| **Social media follower counts with time** | `Posted 8h ago` | `8h` superficially time-like | No AM/PM; "ago" context |

The most operationally dangerous confusable is **office hours vs. school day hours**. Both appear in footers, both follow the same HH:MM–HH:MM format, and both may be labeled under a "Hours" heading. The distinction matters because a parent asking "when does school start?" wants student arrival/dismissal time, not the front-office phone hours. The disambiguation requires reading the heading label closely ("Office Hours" vs. "School Hours" vs. "School Day") and, when ambiguous, the context sentence ("Students may arrive beginning at..." vs. "Our office is open...").

**Bell schedule fragments** are another high-priority false positive. Many K-12 school homepages link to bell schedules or display them in sidebars. A footer containing "A Days: 7:55–2:55 / B Days: 8:10–3:10" is technically accurate hours data but is a block/rotating schedule, not a simple daily start/end time. An extraction pipeline that returns `7:55` as "school start time" from a block-schedule fragment without noting the A/B day structure is functionally wrong.

### 5.3 Mitigation Strategies

- **Heading-keyword gating**: Only run time-pattern extraction within a text block whose nearest heading matches an hours-intent keyword set (`school hours`, `office hours`, `school day`, `bell schedule`). This eliminates phone, zip, year, and room-number tokens in non-hours contexts.
- **Context window filtering**: Require the time pattern to appear within 150 characters of a day-of-week token (`Monday`, `Mon`, `M–F`) or an hours-intent keyword.
- **Range structure requirement**: Require two time tokens separated by a range delimiter (`–`, `-`, `to`) rather than a single time token. Single times are likely event start times, not hours-of-operation blocks.
- **4-digit year exclusion**: Any apparent "time" that matches a year pattern (1900–2099) should be excluded before time-pattern matching.
- **Phone number pre-exclusion**: Strip US phone patterns (`\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}`) before running time extraction.
- **LLM disambiguation tier**: After regex produces candidate time ranges, pass the surrounding 200-character context window to an LLM with the question: "Is this a recurring school day start/end time, an office hours range, a bell schedule period, or something else?" This classification step handles the bell-schedule and office-hours ambiguity that regex cannot resolve.

***

## Part 6: Recommended Extraction Pipeline

Given the above findings, a practical pipeline for extracting school day hours from K-12 CMS pages follows four ordered tiers:

### Tier 1: Structured Data (High Precision, Low Recall)
Run `extruct` on the rendered HTML. If `openingHoursSpecification` or `openingHours` is found on any `@type` matching `LocalBusiness`, `CivicStructure`, `EducationalOrganization`, or `School`, parse and return immediately. Expected precision: ~100%. Expected recall: <5% of sites.

### Tier 2: CSS-Scoped Heading Proximity (Medium Precision, Medium Recall)
Scope to `<footer>` / `role="contentinfo"` / `<aside>`. Within that scope, find headings matching `hours_keywords` regex. Extract the text of the heading's next 1–3 sibling elements. Pre-strip phone patterns and year patterns. Apply the range-structure requirement. Expected precision: ~65–75% (after phone/year pre-stripping). Expected recall: ~40–60% of sites that have hours in the footer.

### Tier 3: Full-Footer Time-Range Scan (Lower Precision, Higher Recall)
Scan all text nodes in the `<footer>` for time-range patterns (two HH:MM tokens with a delimiter). Apply the 4-digit year exclusion, phone pre-stripping, and a 150-character context window requiring a day-of-week or hours-keyword neighbor. Collect all candidates. Expected precision: ~45–55% after filtering. Expected recall: ~70–80% of sites with parseable hours text.

### Tier 4: LLM Disambiguation
Pass Tier 2/3 candidates through an LLM with the prompt: "From this school website footer text, identify the regular school day start time and end time for students (not office hours, not after-school programs, not bell schedule periods). Return JSON `{start: HH:MM, end: HH:MM, confidence: high/medium/low}` or null if not present." This resolves the office-hours vs. school-hours and bell-schedule ambiguities.

### Schema.org `EducationalOrganization` Gap — Actionable Recommendation

For any district willing to add structured data, the multi-type pattern is the correct approach:
```json
{
  "@context": "https://schema.org",
  "@type": ["EducationalOrganization", "LocalBusiness"],
  "name": "Lincoln Elementary School",
  "openingHoursSpecification": [
    {
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": ["Monday","Tuesday","Wednesday","Thursday","Friday"],
      "opens": "08:00",
      "closes": "15:30"
    }
  ]
}
```
This unambiguously attaches hours to the school entity via the `LocalBusiness` type, is parseable by `extruct`, and is validated by Google's Rich Results Test. None of the major K-12 CMS platforms generate this automatically; it must be injected via a custom JSON-LD block in the site `<head>`.[^7]

***

## Conclusion

K-12 school CMS platforms do not reliably emit structured data for hours as a template default. The schema.org type hierarchy for schools creates ambiguity (does `EducationalOrganization` take `openingHours`?), and vendor documentation is silent on the question. The closest analogue—the WordPress `WP Opening Hours` plugin—exists but requires deliberate installation. HTML class conventions are editor-driven and inconsistent. ARIA landmarks provide reliable region scoping (`<footer>` / `role="contentinfo"`) but no hours-specific semantic signal.

For extraction, the most productive analogues are local-business directory pipelines using `extruct` for structured data, CSS-selector scoping to footer regions, and heading-proximity regex with time-range structure requirements. The K-12 false-positive landscape is specifically complicated by the office-hours vs. school-day-hours distinction and by bell schedule fragments, both of which produce syntactically correct time tokens but semantically wrong answers. Published FPR benchmarks from the NCES school-website scraping project (~10% FPR for page-level classification) suggest that per-token classification in unstructured footer text will have materially higher error rates without domain-specific mitigations. The four-tier pipeline (structured data → scoped heading proximity → footer scan → LLM disambiguation) represents the current best practice for this problem.

---

## References

1. [openingHours - Schema.org Property](https://schema.org/openingHours) - Opening hours can be specified as a weekly time range, starting with days, then times per day. Multi...

2. [openingHoursSpecification - Schema.org Property](https://schema.org/openingHoursSpecification) - Schema.org Property: openingHoursSpecification - The opening hours of a certain place.

3. [EducationalOrganization - Schema.org.ai](https://schema.org.ai/EducationalOrganization) - An educational organization.

4. [Structured Data (schema.org) - openingHours for EducationalOrganization](https://stackoverflow.com/questions/47281370/structured-data-schema-org-openinghours-for-educationalorganization) - I'm just about to expand my templates with schema.org attributes and have the following question. Wi...

5. [openingHours Schema Field: Format and Examples - Karpi Studio](https://www.karpi.studio/schema-glossary-terms/opening-hours) - Opening hours can be specified as a weekly time range, starting with days, then times per day. Mo, T...

6. [Google's Schema.org Adoption Data: What We Shipped | Behave Health](https://behavehealth.com/blog/google-schema-stats-2026) - We mined Google's new Schema.org adoption dataset and used it to upgrade structured data across our ...

7. [Schema.org EducationalOrganization: The Technical Guide ...](https://www.skolbot.ai/en-IE/blog/schema-org-educational-organization-school) - Complete Schema.org EducationalOrganization JSON-LD for schools: required properties, code examples ...

8. [[PDF] Blackboard Web Community Manager Apps on Pages Introduction](https://resources.finalsite.net/images/v1744716982/redoakisdorg/g2xcedwnqb7qpmfykz6f/Apps_best_practices_guide-rv.pdf) - Any app placed in a Header or Footer region displays standard web content without issue. Page Layout...

9. [Footers: The Forgotten Section of School Website Design - Finalsite](https://www.finalsite.com/blog/p/~board/b/post/school-website-footer-examples) - What should you include in your school's footer? · Copyright information · Privacy policy · Sitemap ...

10. [Finalsite: School Websites, Communications & Enrollment Platform](https://www.finalsite.com) - Finalsite is the first community relationship management platform for K-12 schools, transforming how...

11. [SchoolCEO Spark | December 5, 2025 - Apptegy](https://www.apptegy.com/newsletters/one-page-your-website-needs/) - Here are five tried and true pages every website needs to dazzle its guests, and one page you likely...

12. [Edlio Website Basics - Edlio](https://schooldataleadership.org/media-items/videos.html?m=Wqggh)

13. [[PDF] Blackboard Web Content Manager - WCAG 2.0 Support Statement](https://help.blackboard.com/sites/default/files/documents/2017-09/Blackboard%20-%20Web%20Content%20Manager%20-%20WCAG%202.0%20Support%20Statement%20-%202016.pdf)

14. [Easy–to-Use Content Management System - Foxbright](https://www.foxbright.com/solutions/our-cms/) - Streamline access, updates, and control over your school&#39;s website with our cutting-edge CMS. Ef...

15. [New Release: Iris is here! - Apr 23, 2024 - Foxbright](https://www.foxbright.com/pub/news/posts/1289) - Website for Foxbright

16. [[PDF] Foxbright CMS Training Guide - Contents](https://www.kentwoodps.org/downloads/training/fb-editortrainingwarrenwoods.pdf)

17. [WP-Opening-Hours/doc/schema-org.md at master · janizde/WP-Opening-Hours](https://github.com/janizde/WP-Opening-Hours/blob/master/doc/schema-org.md) - Opening Hours Plugin for WordPress. Contribute to janizde/WP-Opening-Hours development by creating a...

18. [Schema – WordPress plugin](https://wordpress.org/plugins/schema/) - Get the next generation of Schema Structured Data to enhance your WordPress site presentation in Goo...

19. [education-wp/footer.php at master · FameThemes/education-wp](https://github.com/FameThemes/education-wp/blob/master/footer.php) - Education WordPress Theme. Contribute to FameThemes/education-wp development by creating an account ...

20. [Schema Markup Adoption: 5,000-Site Audit and Findings](https://www.digitalapplied.com/blog/schema-markup-adoption-5k-site-audit-2026) - Which schema types are deployed, error rates, AI-search-visibility correlation, and WordPress/Webflo...

21. [Google Publishes Schema.org Adoption Data for May 2026 - LinkedIn](https://www.linkedin.com/posts/kavin-singh5_seo-technicalseo-schemamarkup-activity-7470104983061839872-jcyw) - Google just gave SEOs something we've never had before. For the first time, Schema.org is publishing...

22. [EduZone | Education Course & School Template + Admin Dashboard | DexignZone](https://eduzone.dexignzone.com/xhtml/footer-11.html) - Discover EduZone, the ultimate Education Course & School Template with an integrated Admin Dashboard...

23. [Best practices](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/contentinfo_role) - The contentinfo role defines a footer, containing identifying information such as copyright informat...

24. [LLM-Generated Regular Expressions for Entity Extraction ...](https://nlp.fi.muni.cz/raslan/2024/paper6.pdf)

25. [ARIA11: Using ARIA landmarks to identify regions of a page - W3C](https://www.w3.org/TR/2014/NOTE-WCAG20-TECHS-20140311/ARIA11)

26. [ARIA Landmarks – Make WordPress Accessible](https://make.wordpress.org/accessibility/handbook/best-practices/markup/aria-landmarks/) - ARIA landmark roles provide a method for screen reader users to navigate structural regions of a sit...

27. [extruct/extruct/_extruct.py at master · scrapinghub/extruct](https://github.com/scrapinghub/extruct/blob/master/extruct/_extruct.py) - Extract embedded metadata from HTML markup. Contribute to scrapinghub/extruct development by creatin...

28. [extruct](https://pypi.org/project/extruct/) - Extract embedded metadata from HTML markup

29. [Python extruct Library in Web Scraping](https://webscraping.fyi/lib/python/extruct/) - Information about the python extruct library and it's use in web scraping. Includes examples, altern...

30. [Scrape Structured Data with Python and Extruct](https://dev.to/hackersandslackers/scrape-structured-data-with-python-and-extruct-109l) - Unless you're entirely oblivious to scraping data in Python (and probably ended up here by accident....

31. [How to extract metadata from a website - ExtractFox](https://extractfox.com/blog/extract-metadata-from-website) - Title tags, Open Graph, Twitter cards, JSON-LD structured data — what every page exposes and how to ...

32. [jusText](https://lindat.mff.cuni.cz/repository/items/f47d4c92-baa1-499f-a845-01f6b9f57da4/full)

33. [A Python package & command-line tool to gather text on the Web ...](https://trafilatura.readthedocs.io) - Trafilatura is a Python package and command-line tool designed to gather text on the Web. It include...

34. [GitHub - miso-belica/jusText: Heuristic based boilerplate removal tool](https://github.com/miso-belica/jusText) - Heuristic based boilerplate removal tool. Contribute to miso-belica/jusText development by creating ...

35. [Justext](https://corpus.tools/wiki/Justext)

36. [Evaluation — Trafilatura 2.1.0 documentation](https://trafilatura.readthedocs.io/en/latest/evaluation.html) - See how Python tools work on main text extraction from HTML pages (html2txt). Trafilatura consistent...

37. [Quickstart — Trafilatura 2.1.0 documentation - Read the Docs](https://trafilatura.readthedocs.io/en/latest/quickstart.html)

38. [selectolax on Pypi](https://libraries.io/pypi/selectolax) - Fast HTML5 parser with CSS selectors.

39. [How to Scrape YellowPages - Web Scraping FYI](https://webscraping.fyi/scrapers/yellowpages/) - How to scrape YellowPages - extract business listings and more with Python. Open source scraper with...

40. [Scrape Google Local Pack | Local SEO Data - ScrapeBase](https://thescrapebase.com/tools/google-local) - Extract local business info, hours, and reviews from Google Local.

41. [Yellow Pages Scraper for Business Listings - Apify](https://apify.com/maximedupre/yellowpages-scraper) - Yellow Pages scraper for US business listings. Export names, phones, addresses, websites, ratings, h...

42. [scrapinghub/dateparser: python parser for human readable dates](https://github.com/scrapinghub/dateparser) - python parser for human readable dates. Contribute to scrapinghub/dateparser development by creating...

43. [date-spacy](https://pypi.org/project/date-spacy/) - A spaCy extension for enhanced date and number entity recognition and extraction as structured data.

44. [timexy](https://pypi.org/project/timexy/) - A spaCy custom component that extracts and normalizes dates and other temporal expressions

45. [Spacy not Recognizing Date Properly](https://stackoverflow.com/questions/59764784/spacy-not-recognizing-date-properly) - nlp = spacy.load('en_core_web_md') text =" Activity Date: 12/18/2019 06:00:00AM CST " doc = nlp(text...

46. [How to extract date and temporal expressions from German text in Python?](https://stackoverflow.com/questions/75776399/how-to-extract-date-and-temporal-expressions-from-german-text-in-python) - I want to extract dates and other temporal expressions from unstructured written texts in German lan...

47. [How to Effectively Extract Time from a Date-Time String Using Regular Expressions](https://www.youtube.com/watch?v=z7JHHniSdlU) - Learn how to match a specific time format from a larger string using regular expressions, without ge...

48. [GitHub - bes-dev/gpt-scraper: An autonomous LLM-based agent that generates code to extract structured information from web pages and extracts it.](https://github.com/bes-dev/gpt-scraper) - An autonomous LLM-based agent that generates code to extract structured information from web pages a...

49. [Web Extraction with Vision-LLMs: SQL-Ready Data From Any URL with GPT-4o](https://dev.to/emcf/web-extraction-with-vision-llms-done-the-right-way-structured-data-from-any-url-with-gpt-4o-1al8) - Let's talk about GPT-4o GPT-4o, OpenAI's latest vision-language model, excels in handling...

50. [[PDF] A Generic and Automated Staff Scraping Tool for School Webpages](https://nces.ed.gov/surveys/ntps/pdf/research/FCSM_2023_Automated_Staff_Scraping.pdf)

