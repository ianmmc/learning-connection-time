# Stage 2 — Discover: present state & decision log

> **Authority:** Stage 2's purpose, I/O, the deterministic SERP cascade (providers, failover, gating,
> provenance), and the console surface — what the code does today.
> **Audience:** anyone building on or debugging Stage 2; anyone tracing why a school's candidates are
> missing, mislabeled, or come from an unexpected provider.
> **Companions:** `ACQUISITION_PIPELINE.md` §2 (the slim map + flow diagram),
> `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` (§3 state_event, §7a cost framing, §11 gates/console).
> Stage 1's note for the upstream contract; Stage 3's for the downstream one.
> **Update this when:** Stage 2's code behavior changes. Design turns and superseded approaches (incl.
> the retired agent-wave architecture) belong in §5 (Decision log), not here.

**Status: BUILT + run live.** Fully deterministic — **no agent in the Wave-1 loop.** Produces, per
district, `data/raw/lea-website-captures/<id>_<slug>/discovery.json` (audit trail) + `candidates.json`
(capture-ready URL list). The `stage2-discover` skill (the retired agent-wave orchestrator) is **obsolete**.

**Code:** `common/discover.py` (`brightdata_search`, `serper_search`, the gate — the retired
`openrouter_search`/`perplexity_search` were deleted 2026-07-06, #87);
`stage2_discover/discover_stage2.py` (`build_roster`, `run_wave1(search_fn)`, `run_wave2(search_fn)`,
`flatten`, gate/residual/write/registry); `stage2_discover/headless.py`
(`brightdata_then_serper` — Wave-1 + failover, `_wave2_claude`, `discover_district`, sequential
`run_batch`). The console drives it via `process_governance/server.py` `/api/discover/*` +
`static/stage2.js`. Still DB-free (no LCT-DB import).

---

## 0. Receipt from prior stage / Handoff to next stage

**Receipt from prior stage:** Stage 1's `gate@1`-approved batch, read directly from the governance DB
working store (never the NCES CSVs — `build_roster()` reads only `domain` and `schools_by_band` from the
batch; re-deriving band membership would silently discard every Stage 1 gate@1 fix).

**Handoff to next stage:** `candidates.json` per district (the deduped, capture-ready URL list, each
candidate carrying its `schools[]` map and `tools[]` provenance) is Stage 3's input, read via
`find_districts()`. Stage 2 is **ungated** — nothing blocks the handoff; Stage 3 can start as soon as
`discovery.json`/`candidates.json` exist on disk (or the DB cache is warm).

---

## 1. Purpose & I/O

Discovery is a **recall** problem: find *a* bell-schedule page per targeted school (Capture/Filter verify
it later), so search runs in cost-ascending waves and stops once a district is satisfied — we do **not**
run every provider on every district.

- **Input — read, never recompute:** the `gate@1`-approved batch. Per district, `build_roster()` reads
  only `domain` and `schools_by_band` (school_id/name/bands). **This is Stage 2's single load-bearing
  invariant** — never re-derive band membership from raw NCES CSVs.
- **Output — `data/raw/lea-website-captures/<id>_<slug>/`, written once per district atomically:**
  - `discovery.json` — the full per-school audit trail: every targeted school (found or flagged), its
    query, raw Wave-1/Wave-2 URLs, each URL's gate decision, the per-school outcome, and which provider
    actually served each URL (§2c).
  - `candidates.json` — the flattened, deduped, capture-ready URL list; the only artifact carrying the
    URL→school map Stage 3/5 consume.
- **Location rationale:** `data/acquisition/` holds our own process state (queue, registry); `data/raw/`
  holds evidence pulled from the outside world — CLAUDE.md's "never modify `data/raw/`" write-once rule
  covers discovery output. Slug is for human readability only; the `district_id` prefix disambiguates.
- **Gate:** **none.** Stages 2/3/4 are ungated (governance §11); the next human gate is `gate@5` (Filter).

---

## 2. The design (settled) — the deterministic SERP cascade

**Fully deterministic, no agent in the loop.** Decided from a five-provider bake-off on a 53-school
known-positive set (`data/acquisition/diagnostics/`) — the underlying **INDEX predicts recall**: raw
Google providers (Bright Data, Serper, OpenRouter's wrapper) cluster near 100%; own-index providers
(Perplexity 43%) crater on long-tail K-12 domains. Full bake-off numbers in §5's decision log.

### 2a. Wave 1 — Bright Data primary, Serper failover
`headless.brightdata_then_serper(query, domain)`: try `discover.brightdata_search` (real Google,
`site:`-scoped, 5,000/mo recurring free tier) first. Bright Data's recurring free tier is preferred over
Serper's one-time credit bank as the primary — ride the renewable tier, keep the bank as backup.

**Failover triggers on any Bright Data infrastructure failure**, not just billing/auth: a network
timeout, connection error, HTTP 5xx, or a malformed ("zone returned non-JSON") response all fail over to
`serper_search` for that school — the actual outage case the failover exists for. Only a **billing/auth
failure on BOTH providers** (HTTP 401/402) halts the run (`SystemExit`, `BILLING_AUTH_STATUS_CODES =
{401, 402}`) — every remaining call would fail identically. **HTTP 429 is transient, not terminal:**
Bright Data's 429 fails over to Serper immediately; Serper's own 429 gets one sleep-and-retry before
degrading to a per-school failure (never a run halt).

### 2b. Wave 2 — Claude WebSearch on the genuine residual
`residual_schools`: schools with **zero kept** candidates after gating go to
`headless._wave2_claude(district, residual, domain)` — one `claude -p` WebSearch call (no
`--json-schema`; that mode flakes on Haiku), a *different* index than Google, a speculative "why not try"
tier. Degrades per-school to `manual_flag` on failure/timeout, never halts. **If the residual is empty,
Wave 2 is skipped entirely** — no call at all, not merely a no-op scope. `run_wave2`'s `search_fn` is a
**required** parameter (no default) — the retired `openrouter_search` default ($27/1K, wraps Google) is
unreachable; the CLI `finish` subcommand refuses on a nonempty residual and points at the console/headless
path instead.

### 2c. Gate, flatten, provenance
- **Gate** (`gate_urls` → `common.discover.gate`, per-school): reject no-host and news/aggregator hosts
  always; when the district has a domain (scoped), keep only **on-domain** URLs or a **CMS-slug** match
  (host ends with an approved `cms_hosts` suffix on a **dot boundary** — `h == suffix or
  h.endswith("." + suffix)` — **and** the URL contains the district slug); reject off-district otherwise.
  The dot-boundary check matters: a naive suffix match would reject `halifax.com` as the news host
  `x.com`, or accept `evilschoolwires.com` as the CMS vendor `schoolwires.com`. No domain → unscoped, keep
  any non-news result. `cms_hosts` is human-curated config-as-data, school-district vendors only (never
  general CDNs).
- **`flatten()`** dedups all kept URLs across schools by normalized URL, collapsing a shared hub page into
  one capture target listing all its schools. Each candidate's `tools[]` records the **true serving
  provider** per URL — `"brightdata"` / `"serper"` (whichever the Wave-1 cascade actually used) or
  `"claude_websearch"` (Wave 2) — read from the per-school `wave1_provider`/`wave2_provider` fields the
  cascade sets. *(Backfill note: batches discovered before this fix (≤ batch_00007) carry the retired
  labels `"claude"` (really Bright Data/Serper) and `"openrouter"` (really Claude WebSearch) — not
  backfilled by script; pre-fix vintage rows are simply mislabeled.)*
- **Outcomes:** per-school `found` (any kept URL) else `manual_flag`; per-district `found_all` /
  `manual_flag_all` / `found_partial`.
- **`write_discovery()`** — single atomic write of both files; an existing `discovery.json` is renamed
  aside with a UTC timestamp before a redo (never overwritten — `data/raw/` is write-once in spirit).
- **`finish_district()`** — one registry write per district, at completion only.

### 2d. Paths, reconciliation, concurrency
- **Secrets and data paths are anchored to `paths.REPO_ROOT`**, not CWD-relative — `SECRETS_FILE`
  (`config/secrets.local.json`, load-bearing for the live providers) and the NCES/discovery-output paths.
  A server launched off repo-root used to silently degrade every provider call to an auth failure.
- **Reconciliation** (before any searching): filesystem is authoritative. Disk-yes/registry-behind
  reconciles up and skips; disk-yes/registry-yes skips; disk-no/registry-says-done is a **hard
  `SystemExit`** (control failure — registry ahead of disk signals lost data or a bad migration,
  affecting potentially more than one district); disk-no/registry-behind is `todo`.
- **`run_batch` is sequential** — one registry writer, no race; providers are fast enough at batch scale
  (parallelize via Bright Data's unlimited concurrency later, at full-corpus scale).
- **Topology classification is deliberately not done at Stage 2** — not enough signal from search results
  alone before any page content is read; `flatten()`'s URL-dedup already captures the practical benefit
  (a hub page collapses to one capture target regardless of a topology label). Stage 5 reconstructs a
  *labeled* topology downstream from captured content + the NCES denominator.

---

## 3. Console surface

Stage 2 is **ungated** — the console surfaces it as **status/observability** only: per-district outcome,
Wave-1 vs. Wave-2 found counts, the deduped candidate count, and `manual_flag` schools needing eventual
human follow-up. The reviewer's first real decision point on this batch's discovery output is `gate@5`.

**Reads the DB `discovery_school` cache**, not `discovery.json` off disk — the Stage-2 finish hook
(`common.cache_ingest.cache_discovery`) upserts each district's funnel on completion (per-district
DELETE-then-UPSERT, so a re-discovery's stale rows never linger). Self-healing: a district discovered
before the cache hook existed gets ingested on first console view.

**Shared UI labels + left-pane progress:** `static/outcomes.js` (`outcomeBadge`, `progressBadge`) — the
same elements Stage 3/4 use, so a label rename is one edit. The active batch's chip live-syncs to the
header during a run.

**User stories (not yet built):**
- Review search-query templates and propose new ones. (tracked: #102)
- Insights into how effective combinations of search services + queries are at yielding bell-schedule
  representations by the end of Stage 5 (the measurement-harness pattern extended upstream — attribute
  each target-labeled record back to its discovery tool via `candidate_tools_json`). (tracked: #118)

---

## 4. Open decisions

- **Wave-cascade vs. always-run-both, and how many providers** — the first live run split 6/12
  Wave-1-only vs. 6/12 needing Wave 2 (zero mixed). Once Capture/Extraction give *page-quality* signal
  (not just presence), revisit whether to run providers unconditionally rather than stopping at the first
  wave that returns anything.
- **Is Claude Wave-2 worth it? — lean is yes.** batch_00002 recovered 0/2 residuals; batch_00005's Claude
  WebSearch Wave-2 recovered a page Bright Data/Serper (the Google index) did NOT find — the different
  index earning its keep. Watch for the pattern to recur across more batches before calling it load-bearing.
- **Serper-on-Bright-Data-misses** — Bright Data's one recorded miss (Monkton) WAS recovered by Serper
  (same index, ~99% overlap, not byte-identical). Once real-batch misses accumulate, test whether
  Serper-on-misses earns a Wave-1.5 residual-recall role vs. its current failover-only role.
- **Bing via Bright Data** available (`--engine`) but empty on our Google-tuned zone; ~1–3% marginal per
  the research — available if needed, not pursued.
- **Wave-1 subagent under-reporting on large rosters** (historical, from the retired agent-wave design —
  §5) — no longer applicable now that Wave 1 is deterministic, but worth remembering if an agent step is
  ever reintroduced.

---

## 5. Decision log (chronological)

_Includes the full retired agent-wave design (2026-06-23 through 2026-06-26) — Stage 2's ORIGINAL
architecture, superseded 2026-06-28 by the deterministic SERP cascade above. `gate@1` was "CP-A", `gate@5`
"CP-B" at the time of writing. Code has since moved from `infrastructure/acquisition/discovery/` to
`infrastructure/acquisition/stage2_discover/` — paths below reflect the original location._

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

**2026-06-23 — Wave 2 must be conditional on a residual existing, not an unconditional step in the chain.** The first diagram pass drew `D_W1 -> D_GATE -> D_W2 -> D_FLATTEN` as a straight line, which silently implied Wave 2 always runs — contradicting the prose ("only on schools Wave 1 left unsatisfied") and wasting an OpenRouter call whenever Wave 1 + gating already satisfied every school in a district. **Fix:** added an explicit `D_RESIDUAL` decision node after gating — any school with zero kept candidates after gating routes to Wave 2 (scoped strictly to those schools); zero residual skips Wave 2 entirely and goes straight to flatten/dedup.

**2026-06-23 — Stage 2's deterministic half built and unit-tested (REQ-068–072), plus the orchestration skill `.claude/skills/stage2-discover/SKILL.md`.** Resolved before coding: the subagent's strict-JSON result must echo `domain` at the district level, not just `district_id` — `validate_wave1_result()` fails loud on either mismatch, since a wrong-domain result silently accepted would contaminate `discovery.json`. Skill written explicitly (not deferred) because conversational nuance cannot be assumed to survive across sessions. All deterministic logic unit-tested against synthetic fixtures. Found and fixed a pre-existing YAML syntax error in REQ-066's `notes` field (a stray closing quote had silently orphaned a paragraph for an unknown number of sessions — the same defect class that later broke the whole REQUIREMENTS.yaml file, fable review issue #7).

**2026-06-23 — review of `SKILL.md` itself caught two problems in the subagent's instructions (not code bugs).** Concurrency softened into a "ramp to 3-4" suggestion when it was supposed to be a hard 2 — corrected to a hard cap, no self-directed ramping. The Wave-1 prompt put `school_id` prominently next to each query in a way that risked a subagent reading the ID as part of the literal search text (an NCES ID in a WebSearch query returns NCES/SEA database pages, not the district's own site) — restructured with an explicit instruction never to include identifiers in the literal query.

**2026-06-23 — Stage 2's first live run: all 12 `batch_00001` districts through Wave 1/Wave 2.** Every district landed `found_all`. Confirmed live: dedup-by-normalized-URL collapses a real shared hub page (ROY ELEMENTARY and ROY HIGH both resolved to the identical URL). **New finding: a Wave-1 subagent can silently under-report on a large roster by applying its own relevance judgment instead of mechanically reporting what WebSearch returned** — Pittsylvania County (18 schools) came back with every school's `urls` empty despite the subagent's own prose revealing it had found pages it judged "not good enough." This inverts the intended failure mode (the brief's "do not guess URLs" was meant to stop invented URLs, not stop reporting real ones). The built-in fallback compensated (the resulting residual correctly triggered Wave 2, landing `found_all` anyway) — not fixed in the prompt at the time; moot once Wave 1 became deterministic.

**2026-06-23 — billing/auth failure fix: `discover.openrouter_search()` was silently treating an exhausted OpenRouter balance the same as "found nothing."** `run_wave2`'s `except Exception` caught *any* failure including an HTTP 402, degrading it to `urls=[]` — indistinguishable from a genuine empty result, and silently repeatable for every remaining residual school once the balance ran out. Fixed to raise `SystemExit` for HTTP 401/402/429 specifically — a control failure, same treatment as a reconcile-stage disk/registry mismatch. *(This 401/402/429-together grouping was itself refined 2026-07-02 — see the failover-hardening entry below: 429 is transient, not terminal.)*

**2026-06-26 — headless + pluggable-provider reframe designed (REQ-104).** Retired the "Python can't spawn the subagent, so an agent must be in the loop" framing: Stage 2 would shell out to `claude -p` per district (a full headless agent, subscription-billed, schedulable overnight), with search providers as a pluggable layer behind a common candidate-URL contract. The wave/gate/residual logic stayed unchanged in the design.

**2026-06-28 — the deterministic SERP cascade decided and built (REQ-104), retiring the agent-wave design above.** The `claude -p` headless runner was built first per the 2026-06-26 design; a smoke test then surfaced that Claude's `--json-schema` structured-output mode flakes on Haiku (`error_max_structured_output_retries`, worse with more effort) — dropping `--json-schema` and parsing free text fixed it. That detour prompted a real five-provider bake-off on a known-positive corpus (batch_00001's 53 schools), each gated exactly as the pipeline does:

| Provider | Index | Recall | Sched-prec | Latency | $/53 | Verdict |
|---|---|---|---|---|---|---|
| **Serper** | raw Google | 100% | 75.5% | 0.87s | $0.05 | **Wave-1 failover** |
| **Bright Data** | raw Google | 98.1% | 77.4% | 4.46s | $0.08 | **Wave-1 primary** |
| OpenRouter gpt-4o-mini-search | OpenAI/Google | 100% | 75% | 3.6s | $1.43 | retired ($27/1K wraps Google) |
| Claude CLI WebSearch (no-schema) | Claude | 66% | 60% | 17.6s | quota | → **Wave-2 residual only** |
| subagent Wave-1 (baseline) | Claude | 47% | — | — | quota | retired |
| Perplexity Search | own index | 43% | 15% | 0.47s | $0.27 | retired (zero long-tail coverage) |

**Load-bearing lesson: the underlying INDEX predicts recall.** Raw-Google providers cluster at the top;
own-index providers crater — Perplexity's 30 misses ALL had `raw_urls=0` (no index entry for small
district domains). Google's own Custom Search API was ruled out separately (shutting down Jan 2027,
50-domain cap). Provider survey + two Perplexity Deep Research reports:
`docs/technical-notes/SERP_API_PROVIDER_COMPARISON.md`. Live result: batch_00002's Bright Data Wave-1
found 28/30 schools; the 2 residuals invoked Claude Wave-2 and recovered 0 (both genuine no-page cases).
Wave-2 timeout lowered 420s → 75s (the diagnostic harness keeps 420s; only the live sequential path was
over-budgeted).

**2026-07-02 — failover hardening, true provenance, anchored paths, dot-boundary gate (fable review
issues #29/#30/#31/#34/#41).** The as-built cascade above already looked robust but had four real gaps,
found by adversarial review:
1. **Failover only fired on billing/auth (401/402/429), not on the outages it was meant for** — a
   network timeout, 5xx, or malformed response from Bright Data propagated as a plain exception that
   `run_wave1` silently degraded to zero URLs per school, indistinguishable from "nothing found." Fixed:
   `brightdata_then_serper` now fails over on `requests.RequestException`/`RuntimeError`/5xx too; 429
   split out as transient (retry/failover) from 401/402 (halt).
2. **Wave provenance was mislabeled** — `flatten()` still tagged results with the retired architecture's
   names (`"claude"` for what Bright Data/Serper actually served, `"openrouter"` for what Claude WebSearch
   served), corrupting `candidate_tools_json` downstream in Stage 5. Fixed to thread the real
   `wave1_provider`/`wave2_provider` through; pre-fix batches (≤ batch_00007) are documented as mislabeled,
   not backfilled.
3. **`SECRETS_FILE` and discovery output paths were CWD-relative** — a server launched off repo-root
   silently sent `Bearer None` to every provider. Anchored to `paths.REPO_ROOT`.
4. **The host gate's suffix match lacked a dot boundary** — `h.endswith(n)` let `halifax.com` collide
   with the news-host `x.com`, and let `evilschoolwires.com` pass as the CMS vendor `schoolwires.com`.
   Fixed to `h == n or h.endswith("." + n)`.

Also: `run_wave2`'s `search_fn` parameter lost its retired-`openrouter_search` default (now required); the
CLI `finish` subcommand refuses on a nonempty residual rather than silently using the retired provider.
