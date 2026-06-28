# Stage 2 — Discover: design & decision log

> **Status: BUILT + run live (2026-06-23)** against all 12 `batch_00001` districts (12/12 `found_all`);
> billing/auth failure handling hardened the same day. Produces, per district,
> `data/raw/lea-website-captures/<id>_<slug>/discovery.json` (audit trail) + `candidates.json`
> (capture-ready URL list) — the input Stage 3 (Capture) consumes.
>
> **What this note is:** for the already-built Stages 1–4 the **code is authoritative**; this note is a
> **narrative of what the code currently does — to inform the console**, not a redesign. §1–§5 describe
> current behavior (verified against the script 2026-06-27); §6 is the historical decision log.
>
> **Code (grimp-confirmed dependency set, 2026-06-27):** `stage2_discover/discover_stage2.py` imports
> exactly `common.district_status` (the registry / `state_event` cache) and `common.discover`
> (`host_of`, `gate`, `openrouter_search`; `discover.py` in turn pulls `cms_hosts` from
> `common.config_loader`). **It does NOT import the LCT database layer** — Stage 2 is one of the ungated,
> DB-free middle stages (contrast Stage 1, which reads the LCT DB). Nothing imports `discover_stage2`
> back — it is a CLI entrypoint, driven by the orchestration **skill**, not a library.

**Companions:** `ACQUISITION_PIPELINE.md` §2 (the slim map), `acquisition_pipeline_flow.md` (the visual),
`.claude/skills/stage2-discover/SKILL.md` (the executable orchestration procedure — Wave 1 dispatch),
`PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` (§3 state_event, §7a discovery-is-≈free cost framing,
§11 gates / batch types). Stage 1's note for the upstream contract; Stage 3's for the downstream one.

---

## 1. Purpose & I/O

Discovery is a **recall** problem: find *a* bell-schedule page per targeted school (Capture/Extraction
verify it later), so search runs in **cost-ascending waves** and stops once a district is satisfied — we
do **not** run every provider on every district.

- **Input — read, never recompute:** `data/acquisition/queue/batch_NNNNN.json`, the `gate@1`-approved
  Stage 1 batch. Per district, `build_roster()` reads only `domain` and `schools_by_band`
  (school_id/name/bands) straight from the batch. **Stage 2 must never re-derive band membership from raw
  NCES CSVs** — that would silently discard every Stage 1 `gate@1` fix (dilution, CTC, virtual, grade-13,
  `recursive_band_groups()`, the 12/band cap, cross-band dedup). This is the single load-bearing
  invariant of the stage (see the module docstring and SKILL §invariant 1).
- **Output — `data/raw/lea-website-captures/<id>_<slug>/`, written once per district atomically:**
  - `discovery.json` — the full per-school **audit trail**: every targeted school (found *or* flagged),
    its query, raw Wave-1 URLs, raw Wave-2 URLs (where invoked), each URL's gate decision
    (kept/rejected + reason), and the per-school `outcome`.
  - `candidates.json` — the flattened, deduped, **capture-ready** URL list (schools with nothing found
    naturally drop out), the only artifact carrying the URL→school map Stage 3/5 consume.
- **Location rationale:** `data/acquisition/` holds our own process state (queue, registry); `data/raw/`
  holds evidence pulled from the outside world (NCES downloads, now also search results) — so CLAUDE.md's
  **"never modify `data/raw/`"** write-once rule covers discovery output. Slug is for human readability
  only (`slugify()`, ≤40 chars); the `district_id` prefix is the real disambiguator (`lea_dir()`).
- **Gate:** **none.** Stages 2/3/4 are ungated (governance §11); the next human gate is `gate@5` (Filter).

---

## 2. The design (settled)

### 2a. Orchestration model — agent-in-the-loop, deterministic-script-for-everything-else
Wave 1 needs a web-search agent that `discover_stage2.py` cannot spawn itself, so the stage is driven by
the **`stage2-discover` skill**, not run as one script. The split is deliberate and absolute:
- **Wave 1 (the only agent step)** — one **Haiku WebSearch subagent per district** (never multiple
  districts per subagent — avoids context collision), looping over that district's schools. The subagent
  **only** runs WebSearch and returns **one strict, machine-parseable JSON block** keyed by `school_id`
  — never prose for the orchestrator to hand-transcribe (the "don't nest one probabilistic process inside
  another's interpretation" principle, applied to Wave 1's own handoff). Subagents never write to
  `data/raw/`.
- **Everything else is deterministic Python** in `discover_stage2.py` (`reconcile` → `roster` →
  `finish`): reconciliation, gating, the residual check, conditional Wave 2, flatten/dedup, the atomic
  write, and the single registry write-back. No agent judgment anywhere past Wave 1.

The three CLI subcommands: `reconcile <batch>` (run first, whole batch), `roster <batch> <did>` (emit one
district's per-school search list for the subagent brief), `finish <batch> <did> <wave1.json>` (the whole
deterministic tail for one district).

### 2b. Reconciliation — the filesystem is authoritative
Before any searching, `reconcile()` checks every district in the batch against disk
(`discovery.json` exists?) vs. the registry (`furthest_stage >= 2`?):
- **disk yes, registry behind** → reconcile the registry *up* (`outcome="reconciled_from_disk"`), skip —
  already done, never auto-redo (same "don't silently retry" stance as Stage 1's `already_attempted`).
- **disk yes, registry yes** → skip.
- **disk no, registry says done** → **`SystemExit` CONTROL FAILURE: halt the entire run.** A registry
  ahead of disk signals lost data / wrong path / bad migration that could affect more than one district;
  continuing risks propagating it. Not a per-district skip.
- **disk no, registry behind** → `todo` (needs Wave 1).

### 2c. Wave 1 → gate → residual → conditional Wave 2
1. **Wave 1** (subagent) returns raw URLs per `school_id`. `validate_wave1_result()` fails loud
   (`SystemExit`) unless the result **echoes both `district_id` and `domain`** — the NCES seed and the
   fruit must travel together; a wrong-district result silently accepted would contaminate
   `discovery.json`.
2. **Gate** (`gate_urls` → `common.discover.gate`, per-school): reject no-host and news/aggregator hosts
   always; when the district has a domain (scoped), keep only **on-domain** URLs (`h == dhost` or a
   subdomain) **or** a **CMS-slug** match (host ends with an approved `cms_hosts` suffix **and** the URL
   contains the district slug); reject off-district otherwise. No domain → unscoped, keep any non-news
   result. `cms_hosts` is the shared config-as-data knob (REQ-089), human-curated, school-district
   vendors only (never general CDNs — `amazonaws.com` deliberately excluded; see Stage 3's note).
3. **Residual** (`residual_schools`): schools with **zero kept** candidates after gating. **If the
   residual is empty, Wave 2 is skipped entirely** — no OpenRouter call at all, not merely a no-op scope.
4. **Wave 2** (`run_wave2` → `openrouter_search`, `gpt-4o-mini-search`, `site:<domain>`-scoped) runs
   **only** over residual schools. It degrades **per-school** on a normal error (logged, treated as zero
   URLs) — but a **billing/auth failure (HTTP 401/402/429)** raises `SystemExit`, NOT a caught exception:
   every remaining call would fail identically, so it halts the whole run like a reconcile CONTROL
   FAILURE (`BILLING_AUTH_STATUS_CODES`). Its URLs are gated by the same `gate()`.

### 2d. Flatten, outcomes, write
- **`flatten()`** dedups all kept URLs across schools by **normalized URL** (`host + path.rstrip('/')`),
  collapsing a shared hub page into one capture target listing all its schools — this is *why* topology
  classification could be dropped (§2e). Records which tool(s) (`claude`/`openrouter`) surfaced each.
- **Outcomes:** per-school `school_outcome` = `found` (any kept Wave-1 or Wave-2 URL) else `manual_flag`;
  per-district `district_outcome` = `found_all` / `manual_flag_all` / `found_partial`. `manual_flag` is an
  expected recorded outcome (neither provider found anything), not a bug — tracked via the registry
  (REQ-072), never a separate flagged-list file.
- **`write_discovery()`** is a single atomic write of both files. An existing `discovery.json` (only ever
  from a deliberate, manual redo) is **renamed aside with a UTC timestamp** before the new write —
  `data/raw/` is write-once in spirit; redo is versioned, never an overwrite.
- **`finish_district()`** does the one registry write per district, at completion only (no interim
  "started" marker — there's nothing to reconcile against a half-finished state).

### 2e. Topology classification — dropped, deliberately
There isn't enough signal to label a district `hub`/`per_school`/`none` from search results alone, before
any page content is read. The cost is small: `flatten()`'s URL-dedup already collapses a hub page into one
shared target regardless of any label. Only the *future* possibility of using known topology to refine
Stage 2's own queries is deferred — and the raw per-school audit trail in `discovery.json` survives for
that later analysis. (Stage 5 reconstructs a *labeled* topology downstream from captured content + the
NCES denominator.)

### 2f. Concurrency
Hard cap of **2 concurrent subagents** (SKILL §inputs) — fixed, not a per-run judgment call; raising it
is a deliberate skill edit. Watch for API rate-limit signals (429s, degraded/empty WebSearch) even at 2
and drop to one at a time. No authoritative Claude-Code concurrency ceiling exists (a third-party blog's
claimed cap could not be verified); the real constraints are account-wide RPM/ITPM/OTPM and WebSearch's
own `too_many_requests`.

### 2g. Status registry → `state_event` (REQ-099)
Same as every stage: `district_status.record_stage()` (stage=2, `discover`) writes one event; the
Postgres `state_event` append-log is canonical, `district_status.json` the regenerable backup. The
orchestrating script is the only writer — never a subagent (would race on the shared file).

---

## 3. The headless + pluggable-provider reframe (2026-06-26, DESIGNED — not yet built)

The §2a "Python can't spawn the subagent, so a skill drives Wave 1" framing is **slated to be retired**,
but the change is **not in the code yet** (REQ-104):
- **Headless execution:** the orchestrator shells out to the Claude Code CLI per district
  (`claude -p "<prompt>" --model haiku --output-format json --allowedTools "WebSearch"`) — **each
  invocation a full headless agent, not a subagent** — so no interactive chat is required and the stage
  becomes schedulable (e.g. overnight, subscription-billed). The wave/gate/residual logic is unchanged.
- **Pluggable providers:** Wave 1 = Claude CLI WebSearch (≈free), Wave 2 = OpenRouter
  `gpt-4o-mini-search` (paid), behind a common "given a school, return candidate URLs as JSON" contract,
  so a new provider (Bright Data, Brave Search API, a new cheap OR web-search model) slots in without
  touching gating/flatten/dedup.
- **Cost framing (governance §7a):** discovery is ≈free; Stage 7 extraction is the paid stage — which
  argues for *aggressive* recall here.

Until built, the live stage is the §2 skill+subagent model.

---

## 4. Console surface

Stage 2 is **ungated** — there is no `gate@2`, so the console surfaces Stage 2 as **status/observability**
only: per-district outcome (`found_all`/`found_partial`/`manual_flag_all`), Wave-1-only vs. Wave-2-invoked
counts, and the list of `manual_flag` schools needing eventual human follow-up. The reviewer's first
real decision point on this batch's discovery output is `gate@5` (Filter), after Capture + Local
processing.

**User stories (APGA, seed; migrated 2026-06-27):**
- As a user, I want to **review search-query templates** and **propose new ones.**
- As a user, I want to see **what a given search service is processing right now** — which district + query
  (search service = Claude CLI WebSearch, OpenRouter `gpt-4o-mini-search`, future Bright Data / Brave /
  Google Search API). *(RELAXED 2026-06-27 → "what just happened" via the event-log projection; the live
  per-query view is deferred — governance §11c/§11f.)*
- As a user, I want **insights into how effective combinations of search services + queries are at yielding
  bell-schedule representations by the end of Stage 5** — the measurement-harness pattern extended upstream
  (attribute each target-labeled record back to its discovery tool via `candidate_tools_json`; governance §11f).

---

## 5. Open decisions
- **Headless conversion (REQ-104)** — build the §3 `claude -p` execution path + the pluggable-provider
  layer; retire the subagent-in-the-loop skill mechanism. Designed, not built.
- **Wave-cascade vs. always-run-both, and how many providers** — the first live run split 6/12
  Wave-1-only vs. 6/12 needing Wave 2 (zero mixed). Once Capture/Extraction give *page-quality* signal
  (not just presence), revisit whether to run providers unconditionally rather than stopping at the first
  wave that returns anything. Deliberately deferred (`ACQUISITION_PIPELINE.md` Open #7).
- **Wave-1 subagent under-reporting on large rosters** — Pittsylvania County (18 schools) returned all
  schools empty because the subagent applied its own relevance judgment instead of mechanically reporting
  what WebSearch returned (the fallback Wave 2 recovered it to `found_all`). One data point; not yet
  fixed in the prompt — does it correlate with roster size? (§6, 2026-06-23 first-live-run entry.) The
  headless reframe is the natural place to address the prompt.

---

## 6. Decision log (chronological — moved here from the flow diagram, 2026-06-27)

_The turn-by-turn record of how Stage 2 was designed, built, and hardened. Preserved verbatim from
`acquisition_pipeline_flow.md`'s decision log; `gate@1` was "CP-A", `gate@5` "CP-B" at the time of
writing (see governance §11 for the current gate model). Note: the code has since been promoted from
`infrastructure/acquisition/discovery/` to `infrastructure/acquisition/stage2_discover/` — paths below
reflect the original location._

**2026-06-23 — Stage 2 (Discovery) designed in full, via extended back-and-forth before any code was written.** Superseded both pre-existing discovery scripts: `discover.py` (district-level, Perplexity+OpenRouter, reads the old `ground_truth_manifest.json`) and `per_school_run.py` (per-school, but rebuilds its own roster from raw NCES CSV via plain `bands_for()`, bypassing Stage 1's batch entirely and re-introducing the exact dilution/CTC/virtual bugs Stage 1 just fixed). Both `.claude/skills/per-school-acquire*` skills built on top of them are likewise obsolete (confirmed by the user explicitly, not inferred). Key decisions, each arrived at by tracing a concrete failure mode rather than asserting a default:
- **Input is `batch_NNNNN.json`, read directly — never recomputed.** `schools_by_band` already carries everything Stage 2 needs (domain, school_id/name/level/gslo/gshi); re-deriving it from CSV would throw away every Stage 1 CP-A fix.
- **Topology classification (hub/per_school/none) dropped.** Not enough signal to classify reliably from search results alone, before any page content has been read. Cost is small: URL-dedup-by-normalized-URL already collapses a hub page into one shared capture target regardless of topology label, so the practical efficiency isn't lost — only the *future* possibility (CP-B results informing better Stage 2 queries, eventually a hypothesis for the Step 7 council) is deferred, not lost, since the raw per-school audit trail survives for that later analysis.
- **Output relocated from `data/acquisition/discovery/` (the original instinct, matching old `discover.py`'s precedent) to `data/raw/lea-website-captures/<district_id>_<slug>/`.** Reasoning surfaced mid-discussion: `data/acquisition/` is our own pipeline's process state (queue, registry); discovered URLs and captured pages are evidence pulled from the outside world, the same category as the NCES downloads already living under `data/raw/` — and CLAUDE.md's existing "never modify files in `data/raw/`" rule turns out to already cover this case once framed correctly. Kept as ONE directory per district (not flattened to prefixed filenames) specifically because Stage 3 will add heavier, multi-file capture artifacts (screenshots, PDFs, OCR text) that want a natural per-district home.
- **Filesystem is authoritative; the registry is a cache of it, reconciled from it, never the reverse.** The existence of `discovery.json` is the real "Stage 2 done" fact. Before any searching, a reconciliation pass checks every district in the batch against disk: registry-behind-disk reconciles up (skip, already done); **registry-ahead-of-disk (registry claims done, file doesn't exist) is a hard stop of the entire run** — not a per-district skip — since it signals a possible control failure (lost data, wrong path, bad migration) that could affect more than the one district, and continuing under a possibly-compromised assumption risks propagating it.
- **Redo is versioned, never an overwrite, and always a deliberate manual override** — consistent with `data/raw/`'s write-once spirit and Stage 1's "don't silently retry failures" principle. Stage 2 never auto-retries a district with an existing `discovery.json`.
- **Registry write-back happens once per district, at actual completion, only from the single-threaded orchestrating script** — never from a subagent directly (would race on the shared JSON file under concurrent dispatch). An earlier "start + end" two-write proposal was dropped once the filesystem-is-truth model made an interim "in progress" marker pointless — there's no half-written `discovery.json` to reconcile against if a run crashes mid-district.
- **Wave 1's own subagent→orchestrator handoff must also be strictly machine-parseable** — extending the "don't nest one probabilistic process inside another's interpretation" principle (originally raised about keeping Wave 2 script-driven) to Wave 1 itself: the Haiku subagent returns one fenced JSON block per the agreed schema, not prose for the orchestrating agent to read and hand-transcribe.
- **Concurrency:** researched via the `claude-code-guide` agent; a third-party blog's claimed hard Claude-Code concurrency ceiling could not be verified against official docs and was explicitly flagged as untrustworthy rather than repeated as fact. Settled on starting at 2 concurrent subagents (ramp to 3-4 once stable), watching for API rate-limit signals rather than targeting a fixed number, since no authoritative ceiling exists to target.
- `discovery.json` must list every school in the targeted roster, found or flagged — completeness, not just success, is the audit bar.

**2026-06-23 — Wave 2 must be conditional on a residual existing, not an unconditional step in the chain.** The first diagram pass drew `D_W1 -> D_GATE -> D_W2 -> D_FLATTEN` as a straight line, which silently implied Wave 2 always runs — contradicting the prose ("only on schools Wave 1 left unsatisfied") and wasting an OpenRouter call whenever Wave 1 + gating already satisfied every school in a district. **Fix:** added an explicit `D_RESIDUAL` decision node after gating — any school with zero kept candidates after gating routes to Wave 2 (scoped strictly to those schools); zero residual skips Wave 2 entirely and goes straight to flatten/dedup. `ACQUISITION_PIPELINE.md`'s Stage 2 prose updated to state the skip explicitly rather than leave it implied by "only on residual schools."

**2026-06-23 — Stage 2's deterministic half built and unit-tested: `infrastructure/acquisition/discovery/discover_stage2.py` (REQ-068–072), plus the orchestration skill `.claude/skills/stage2-discover/SKILL.md`.** Prompted directly by the user asking whether enough was settled to start a first-draft implementation — answer was "mostly," with a few literal schemas (the subagent's strict JSON contract, `discovery.json`/`candidates.json` field names) that had only been discussed conceptually, never pinned. Resolved before coding:
- **The subagent's strict-JSON result must echo `domain` at the district level, not just `district_id`** — "so it's easy to see both the original seed and the fruit from the tree" (the user's framing). `validate_wave1_result()` fails loud (`SystemExit`) on either mismatch, since a wrong-domain result silently accepted would contaminate `discovery.json` with another district's URLs.
- **Skill written explicitly now, not deferred** — the user's call, specifically because "conversational nuance" (exactly the multi-turn negotiation that produced this design) cannot be assumed to survive across sessions; `.claude/skills/stage2-discover/SKILL.md` restates every invariant from this log (filesystem-is-truth, never-recompute-roster, subagent-never-writes-to-data/raw, Wave-2-is-conditional, one-registry-write-orchestrator-only) so a future session doesn't have to reconstruct them from conversation history.
- All deterministic logic (`reconcile`, `build_roster`, `gate_urls`, `validate_wave1_result`, `merge_wave1`, `residual_schools`, `run_wave2`, `flatten`, `write_discovery`, `district_outcome`) is unit-tested against synthetic fixtures — no live subagent needed to test the boundary, since the subagent's raw JSON output is exactly the kind of canned input a test can substitute.
- Found and fixed a **pre-existing YAML syntax error in REQ-066's `notes` field** while validating the new REQUIREMENTS.yaml entries parse — a stray closing quote had silently orphaned an entire paragraph (the corpus-profiling rationale) outside the string for an unknown number of sessions. `.claude/skills/per-school-acquire/` and `per-school-acquire-training/` both given explicit "OBSOLETE, use stage2-discover" headers.
- `discover_stage2.py finish` is not yet run against a real Wave-1 subagent result — only synthetic fixtures. The first real run against `batch_00001.json` will be Wave 1's actual smoke test.

**2026-06-23 — review of `SKILL.md` itself (before it has ever been run) caught two real problems, neither a code bug, both in the subagent's instructions.**
- **Concurrency softened into a "ramp to 3-4" suggestion when it was supposed to be a hard 2.** The first draft wrote 2 as a starting point with room to self-ramp once "a few districts run cleanly" — the user's correction: hard cap of 2, full stop, no self-directed ramping; raising it is a deliberate future skill edit, not a per-run judgment call.
- **The Wave-1 prompt put `school_id` first and prominently next to each query, formatted as `` `<school_id>`: query = `"<query>"` ``** — even though `discover_stage2.py`'s `query_for()` already builds the real query from the school's *name*, this presentation risked a subagent reading the school_id as part of (or instead of) the literal search text. An NCES ID in a WebSearch query returns NCES/SEA database pages, not the district's own site - exactly the kind of result that would silently contaminate `discovery.json` with garbage. **Fix:** restructured to `school_id <id> — SEARCH FOR: "<query>"`, with an explicit instruction never to include the school_id (or any identifier) in the literal WebSearch query — the ID is for output-labeling only.
- Neither of these would have shown up in `discover_stage2.py`'s unit tests (both are about how a human-written, natural-language subagent brief could be *misread*, not about the deterministic code) - a reminder that a skill's prose is also a real artifact worth reviewing before first use, not just the code it drives.

**2026-06-23 — Stage 2's first live run: all 12 `batch_00001` districts through Wave 1/Wave 2, real WebSearch and OpenRouter calls, ramped 1 -> 2 concurrent per the user's explicit pacing.** Every district landed `found_all`; registry and `data/raw/lea-website-captures/` both consistent across all 12. Walked smallest-to-largest on purpose (1 school -> 18 schools) specifically to see where it would break.
- **Confirmed live: the WebSearch-is-deferred-for-subagents fix holds up across a real run**, not just the first smoke test — every subsequent subagent successfully loaded WebSearch via the `ToolSearch(select:WebSearch)` step before searching.
- **Confirmed live: both branches of the wave-conditional design fire correctly on real data.** Wave 1 alone satisfied districts with good per-school site structure (Marion ISD, Stroudsburg, Urbana SD 116 — several with literal `bell-schedule`/`bell_schedules` URLs found directly); Wave 2 correctly picked up the residual when Wave 1 came back empty (Hoboken, Sojourner Truth, DUNSEITH 1, Mt. Abraham — all 5 of Mt. Abraham's schools in one case).
- **Confirmed live: dedup-by-normalized-URL collapses a real shared hub page.** ROY ELEMENTARY and ROY HIGH both resolved to the identical `royschools.org/classschedule` URL; `candidates.json` correctly collapsed this into one entry listing both schools.
- **New finding, not previously seen: a Wave-1 subagent can silently under-report on a large roster by applying its own relevance judgment instead of mechanically reporting what WebSearch returned.** Pittsylvania County (18 schools, the largest in the batch) came back with EVERY school's `urls` empty — but the subagent's own prose (output alongside the JSON, itself a violation of "respond with ONLY this JSON") revealed it HAD found pages (calendars, contact pages, homepages) and chose not to report them because it judged they didn't "actually contain published bell schedule information." This inverts the intended failure mode: the brief's "do not guess URLs" was meant to stop invented URLs, not stop *reporting real ones* the model decided weren't good enough — that relevance call belongs to the deterministic gate + downstream capture/extraction, never to Wave 1. **The built-in fallback compensated:** the resulting 18-school residual correctly triggered Wave 2, which independently found strong per-school subdomain candidates (calendars, handbooks) for all 18 via OpenRouter, landing `found_all` anyway. Not yet fixed in the prompt — open watch-item: does this correlate with roster size (18 was the batch's largest by a wide margin), or would it recur on a 5-school district too? One data point isn't enough to tell.

**2026-06-23 — billing/auth failure fix: `discover.openrouter_search()` was silently treating an exhausted OpenRouter pre-paid balance the same as "found nothing."** Raised by the user as a general principle for any metered API call in production ("does Ian's account carry a sufficient pre-pay balance" — the same model as how OpenRouter billing actually works): `run_wave2`'s `except Exception` caught *any* failure, including an HTTP 402, and degraded it to `urls=[]` — indistinguishable from a genuine empty search result, and silently repeatable for every remaining residual school once the balance ran out. **Fix:** `openrouter_search()` now raises `SystemExit` (not a plain `Exception`, so `run_wave2`'s except clause doesn't swallow it) for HTTP 401/402/429 specifically (`discover.BILLING_AUTH_STATUS_CODES`) — a control failure that halts the whole run, same treatment as the reconcile()-stage disk/registry mismatch. Other status-carrying errors (e.g. transient 5xx) still propagate as the original exception, not a halt. 3 new tests; REQ-070 updated in place. 889 tests passing.

**2026-06-26 — headless + pluggable-provider reframe (designed, not built; REQ-104).** A design-first architecture session retired the "Python can't spawn the subagent, so an agent must be in the loop" framing: Stage 2 will shell out to `claude -p` per district (a full headless agent, subscription-billed, schedulable overnight), with search providers as a pluggable layer behind a common candidate-URL contract. The wave/gate/residual logic is unchanged. Authority: `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §7a. See §3 of this note — the live stage remains the skill+subagent model until this is built.
