# Stage 2 — Discover: present state & decision log

> **Authority:** Stage 2's purpose, I/O, the deterministic SERP cascade (providers, failover, gating,
> provenance), and the console surface — what the code does today.
> **Audience:** anyone building on or debugging Stage 2; anyone tracing why a school's candidates are
> missing, mislabeled, or come from an unexpected provider.
> **Companions:** `ACQUISITION_PIPELINE.md` §2 (the slim map + flow diagram),
> `PIPELINE_GOVERNANCE_AND_STATE.md` (§3 state_event, §7a cost framing, §11 gates/console).
> Stage 1's note for the upstream contract; Stage 3's for the downstream one.
> **Update this when:** Stage 2's code behavior changes. Design turns and superseded approaches (incl.
> the retired agent-wave architecture) belong in §5 (Decision log), not here.

**Status: BUILT + run live.** Fully deterministic — **no agent in the Wave-1 loop.** Produces, per
district, `data/raw/lea-website-captures/<id>_<slug>/discovery.json` (audit trail) + `candidates.json`
(capture-ready URL list). The `stage2-discover` skill (the retired agent-wave orchestrator) is **obsolete**.

**Current status (2026-07-28):** epic #617's three #620 redo batches (`batch_00030/31/32`, 25
`batch_00000` districts, `redo_attempted=true`) have completed Stage 2 cleanly — every district landed a
`found_all` outcome per the reconcile/status machinery, feeding Stage 3. A real defect in the geo
derivation ladder surfaced on a live production district during this window — **issue #672 (open, epic
#128)**, not yet fixed: see §2f.

**Code:** `common/discover.py` (`brightdata_search`, `serper_search`, `domain_of`, `is_scoping_domain`,
the gate — the retired `openrouter_search`/`perplexity_search` were deleted 2026-07-06, #87);
`stage2_discover/discover_stage2.py` (`build_roster`, `run_wave1(search_fn)`, `run_wave2(search_fn)`,
`flatten`, gate/residual/write/registry); `stage2_discover/headless.py`
(`brightdata_then_serper` — Wave-1 + failover, `_wave2_claude`, `discover_district`, sequential
`run_batch`). The console drives it via `process_governance/server.py` `/api/discover/*` +
`static/stage2.js`. Still DB-free (no LCT-DB import).

---

## 0. Receipt from prior stage / Handoff to next stage

**Receipt from prior stage:** Stage 1's `gate@1`-approved batch (never the NCES CSVs — `build_roster()`
reads only `domain` and `schools_by_band` from the batch; re-deriving band membership would silently
discard every Stage 1 gate@1 fix). **Mechanism (#526, closed 2026-07-18):** the console/autoflow resolves
the batch **from the governance DB** via `server._batch_from_db` → `batch_store.to_receipt_doc` (the
canonical included-only batch_doc) and passes the dict into `headless.run_batch(batch)` — the same
contract as Stages 3/4. `load_batch_any` (`QUEUE_DIR/<batch_id>.json`) remains for the **CLI/offline
path only**, enforced by the `cli_only_loaders` fitness function in `arch-manifest.json` (any
`load_batch_any` reference inside `process_governance/` fails the suite).

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

`discover_stage2.py`'s legacy `reconcile`/`roster`/`finish` CLI subcommands are still live code (not
deleted) and remain the only path that still exercises the *original* agent-in-the-loop Wave-1
contract (`merge_wave1`, `validate_wave1_result` — the subagent-returns-strict-JSON handoff described
in §5's 2026-06-23 entries). They're superseded for routine use by `headless.py`'s deterministic
`run_batch`, but not removed.

### 2c. Gate, flatten, provenance
- **Gate** (`discover_stage2.gate_urls`, per-school) — the single gating chokepoint every Wave 1/Wave 2
  URL passes through, regardless of which path fed it: **first**, `is_scoping_domain(domain)` — a real
  dotted hostname, non-blank, no whitespace. If the domain fails that check, `gate_urls` **fails closed**:
  every URL for that district is rejected outright, reason `"no-scoping-domain — unscoped discovery
  refused (#229)"`, before `common.discover.gate()` is ever called. This is defense-in-depth against a
  blank/junk domain reaching Stage 2 through *any* path (a Stage-1 admission-guard gap, a manual DB edit,
  a future batch builder, a remediation script) — not just Stage 1's own admission check. Only for a
  domain that **passes** `is_scoping_domain` does `gate_urls` fall into `gate()`'s on-domain/CMS-slug/news
  logic: reject no-host and news/aggregator hosts always; keep only **on-domain** URLs or a **CMS-slug**
  match (host ends with an approved `cms_hosts` suffix on a **dot boundary** — `h == suffix or
  h.endswith("." + suffix)` — **and** the URL contains the district slug); reject off-district otherwise.
  The dot-boundary check matters: a naive suffix match would reject `halifax.com` as the news host
  `x.com`, or accept `evilschoolwires.com` as the CMS vendor `schoolwires.com`. `cms_hosts` is
  human-curated config-as-data, school-district vendors only (never general CDNs). `gate()` itself still
  carries an unscoped fallback (`return True, "unscoped"` for a blank domain, keep any non-news result) —
  that branch is still used directly by Stage 1/benchmark code elsewhere, but for a genuinely blank/junk
  domain reaching Stage 2, `gate_urls`'s pre-check now short-circuits before `gate()`'s unscoped branch is
  ever reached (§5's 2026-07-11/12 entry).
- **`flatten()`** dedups all kept URLs across schools by normalized URL, collapsing a shared hub page into
  one capture target listing all its schools. Each candidate's `tools[]` records the **true serving
  provider** per URL — `"brightdata"` / `"serper"` (whichever the Wave-1 cascade actually used) or
  `"claude_websearch"` (Wave 2). Preferred source is the **per-URL** `provider` key `run_wave1` stamps
  onto each gated entry (`provider_by_url`, #341) — so a widen-strategy school whose queries failed over
  mid-set still attributes each URL to whichever provider actually served *it*; the per-school scalar
  `wave1_provider`/`wave2_provider` is only a fallback for rows lacking that key (pre-#341 batches, the
  legacy agent-handoff `merge_wave1` path). *(Backfill note: batches discovered before this fix (≤
  batch_00007) carry the retired labels `"claude"` (really Bright Data/Serper) and `"openrouter"`
  (really Claude WebSearch) — not backfilled by script; pre-fix vintage rows are simply mislabeled.)*
- **Outcomes:** per-school `found` (any kept URL) else `manual_flag`; per-district `found_all` /
  `manual_flag_all` / `found_partial`.
- **`write_discovery()`** — **two separate atomic writes, deliberately ordered**: `candidates.json` first,
  `discovery.json` last (#265) — `discovery.json`'s existence is the "done" marker, so a crash between the
  two writes leaves the district looking *not done* (re-runnable) rather than done-with-no-capture-plan.
  Each existing file is independently renamed aside with a UTC timestamp before a redo (`if
  disc_path.exists() or cand_path.exists()`, each gated on its own presence, not a single check covering
  both — never overwritten, `data/raw/` is write-once in spirit). Both writes go through the shared
  `paths.atomic_write_json` helper (the tmp-file+`os.replace` pattern also used by `district_status.py` and
  `batch_store.write_receipt`).
- **`finish_district()`** — one registry write per district, at completion only.

### 2c-bis. Widened queries for follow-up rediscovery (foundation, #160/epic #163)

`build_roster()` reads an optional per-band `query_strategy` field off the batch. A band flagged
`"widen_queries"` (its untried schools already exhausted the default query in a prior round) gets each
school's `queries` list extended past the single default `query_for()` string with
`differentiated_queries()` — a config-driven set of materially different phrasings
(`common/config/stage2_query_templates.json`, e.g. `"{school} {state} bell schedule filetype:pdf"`,
`"{school} {state} student handbook daily schedule"`) rendered per school and composed with the same
domain scoping every SERP call already applies (`site:{domain}` appended by the provider). The rationale
for casting a *wider* query set rather than just re-running the same query again: a 7→2 rediscovery round
wants maximum recall in one cheap SERP pass, and different phrasings surface different pages within the
same Google index (unlike Wave 2's Claude WebSearch, which earns its keep from a *different* index).

`run_wave1()` runs **every** query in a school's `queries` list (not just the default) and unions the
returned URLs with order-preserving dedup — a widen-strategy school can accumulate hits across several
differently-phrased searches into one candidate set. The per-school scalar `wave1_provider` is still
**last-query-wins** (not a per-query breakdown), but this is no longer lossy where it matters: `tools[]`
in `flatten()`'s output prefers each URL's own `provider` key (`provider_by_url`, #341 — see §2c), so a
widen-strategy school's mid-set failover doesn't lose per-URL attribution even though the scalar field
does.

**Failed-vs-empty query accounting (#523/#524):** `run_wave1`'s per-query exception handler sets
`qurls = None` (not `[]`) so a **failed** query is distinguishable from one that **ran and found
nothing**. The provider-append condition (`if qurls is not None and provider not in providers`) means a
failed query can never appear in `wave1_providers` or overwrite the scalar `provider`, while a
legitimate empty-but-successful answer still counts as that provider having served the school — "found
nothing" is service, not failure.

This machinery is **foundation only** (epic #163's own framing): first-run and plain `new_schools`
follow-up bands still get the single default query; nothing yet sets `query_strategy=="widen_queries"`
on a live batch. It ships tested and wired so a later follow-up-builder chunk can flip it on without a
Stage-2 code change.

### 2d. Paths, reconciliation, concurrency
- **Secrets and data paths are anchored to `paths.REPO_ROOT`**, not CWD-relative — `SECRETS_FILE`
  (`config/secrets.local.json`, load-bearing for the live providers) and the NCES/discovery-output paths.
  A server launched off repo-root used to silently degrade every provider call to an auth failure.
- **Reconciliation** (before any searching): filesystem is authoritative. Disk-yes/registry-behind
  reconciles up and skips; disk-yes/registry-yes skips; disk-no/registry-says-done is a **hard
  `SystemExit`** (control failure — registry ahead of disk signals lost data or a bad migration,
  affecting potentially more than one district); disk-no/registry-behind is `todo`. **Redo batches
  (`redoes_attempted(batch)` true — §2e) are the sanctioned exception** — every included district is
  `todo` regardless of disk state; the registry-ahead-of-disk control-failure check still applies
  unchanged.
- **`run_batch` is sequential** — one registry writer, no race; providers are fast enough at batch scale
  (parallelize via Bright Data's unlimited concurrency later, at full-corpus scale). Before touching the
  batch at all, `run_batch()` and the legacy CLI's `finish` subcommand both call `batch_guard.
  assert_runnable()` — a **terminal abandoned batch refuses to run** (#168/#206): without this guard, an
  abandoned batch's schools could silently re-enter the discovery funnel while still excluded from the
  attempted-set accounting (#162).
- **Topology classification is deliberately not done at Stage 2** — not enough signal from search results
  alone before any page content is read; `flatten()`'s URL-dedup already captures the practical benefit
  (a hub page collapses to one capture target regardless of a topology label). Stage 5 reconstructs a
  *labeled* topology downstream from captured content + the NCES denominator.

### 2e. Redo batches: redo-and-merge, not replace (#174; redo-eligibility axis: #617/#619)

A redo batch (a 7→1/7→2/7→3 directive, or a benchmark A/B re-run — see below) needs materially different
Stage-2 behavior than a first run, because its whole purpose is to re-discover districts Stage 2 already
finished:

- **Redo-eligibility is a DECLARED batch attribute, not a `batch_type` derivation** — `common/
  batch_types.py::redoes_attempted(batch)` reads the batch's own `redo_attempted` field when present;
  only when it's absent/NULL (every pre-#617 batch row and receipt) does it fall back to the historical
  `batch_type == "follow-up"` check, byte-identical to the old behavior for those batches. This
  supersedes the older framing (deriving redo from `batch_type` alone) that this section used to
  describe: deriving it would have made a `benchmark` batch on `batch_00000` re-run discovery over the
  27 curated-GT districts and, via `merge=True`, fold fresh SERP candidates into their FROZEN `gt://`
  candidate sets — that corpus is fixed (CLAUDE.md). A `follow-up`-typed batch still redoes by default
  (`default_redo_attempted`); a `benchmark`-typed batch redoes only when its composer explicitly
  declares `redo_attempted=True` (the real Stages-2/3/4 A/B harness case), never implicitly.
- **`reconcile()`'s redo carve-out:** the "disk already has `discovery.json` → skip" rule is *disabled*
  whenever `redoes_attempted(batch)` is true — every included district is `todo`, unconditionally,
  because a redo batch exists precisely to redo discovery for districts already discovered. The
  registry-ahead-of-disk control-failure check still applies unchanged (a redo district silently
  missing its prior `discovery.json` is exactly as alarming as in a first run).
- **Crash-tolerant prior-state recovery (#265, review-deepened):** merging needs the prior round's
  manifests, but a crashed merge=True retry can leave the two files in an inconsistent state — e.g. an
  orphaned `candidates.json` with no `discovery.json` from a partial write. `_prior_doc(d, live, stem)`
  reads each prior manifest **independently**: the live file if present, else the newest timestamped
  aside (`<stem>.<ts>.json`, sorted lexicographically since `fs_stamp()` is sortable), else `{}`. The
  old code gated reading *both* manifests on a single `disc_path.exists()` check, so this exact
  orphaned-candidates state silently dropped the prior round's candidates on retry; recovering each
  manifest on its own presence check fixes that.
- **`write_discovery(..., merge=True)`'s union semantics:** the redo does not replace the prior round's
  manifests — it merges with them, because Stage 5's ingest reads only the current on-disk manifests
  (per-district delete + rebuild), so a slice-only manifest would erase the district's existing records
  and orphan their gate@5 labels at the next ingest. Concretely: `discovery.json` schools are **per-school
  latest-wins with carryover** — a re-queried school's new entry replaces its old one, but a school not
  re-queried this round survives verbatim, so the roster stays complete. `candidates.json` is the old
  list plus this round's new URLs, deduped by normalized URL; only the **new** round's candidates get an
  inline `batch_id` stamp (the old ones keep their original provenance unstamped), giving round-level
  provenance without touching untouched entries.
- Both `discover_district()` (headless) and the legacy CLI's `finish` subcommand pass
  `merge=BT.redoes_attempted(batch)` through to `finish_district()`/`write_discovery()` — the merge
  decision is made once, off the batch's declared redo-eligibility, not re-derived per call site.
- **Confirmed on live campaign data (epic #617, the #620 redo batches, 2026-07):** the union semantics
  above hold in production, not just in the fixture suite — a re-discovered district's candidate set is
  the OLD list plus the new round's, never a fresh replacement. Worcester (`2513230`) kept its 8
  `gt://`-sourced candidates (Stage 3's `capture_discovery.mjs::seedFromPriorCaptures` carries prior
  capture records forward verbatim, including `benchmark_gt`-sourced ones — the downstream half of this
  same union contract) alongside the newly-discovered candidates its redo added, giving a mixed-provenance
  candidate set rather than the redo silently displacing the frozen GT-sourced entries.

### 2f. Geo derivation is share-based, not count-based — widening is NOT monotonic in recall (#672, open)

`apply_geo_derivation`/`discover.derive_domain` (§2c, decision log 2026-07-19) requires the winning host
to clear `DERIVE_MIN_SHARE` (40%) of the RAW result tally **and** `DERIVE_MIN_SCHOOLS` (3) — a
**share**-based threshold over whatever the geo query set returns, not a count-based one. Stage 1's
5→1 geo-escalation ladder (`stage1_queue/batch_store.py::geo_ladder_exhausted`,
`queue_batch.py::force_widen_dids`) has two rungs — the standard geo vocabulary, then a widened
vocabulary if standard fails to derive — on the assumption that a bigger result set can only help. **That
assumption is false when the extra results are noise, not signal**, because widening the denominator can
push a real host's *share* below threshold even though its raw hit count didn't drop. Measured on a real
production district, Wyandanch UFSD NY (`3631800`, issue #672, filed 2026-07-28): the standard rung
produced 25 gate-eligible results with the district's own domain at exactly 0.400 share — derivation
succeeded, 10 candidates kept; the widened rung produced 95 gate-eligible results (3.8x more) but the same
domain's share dropped to 0.179 as the wider vocabulary pulled in far more noise than signal — derivation
failed (`below threshold`), and because `gate_urls` fail-closes on a blank/undetermined domain, every raw
URL from the widened round was refused. The widened round's top host by raw count
was `core-docs.s3.us-east-1.amazonaws.com` (a school-CMS vendor's document bucket, 16 hits across all 4
schools), outranking the district's own domain — S3 buckets are deliberately excluded from `cms_hosts`
(policy, not a bug), so that host could never have derived regardless of share. That pattern is not an
aside: it is #871 seen from this angle (§2g).

**2026-08-21 — #672 re-measured, and three of its claims did not survive**
(`production-quality-control-research/2026-08-21-geo-ladder-regression-measure.py`, rerunnable):

- **"All 109 raw URLs were discarded" overstates the harm ~36x.** `candidates.json` is a UNION across
  rungs (`write_discovery` merges), so a refusing rung cannot un-plan what an earlier rung found. Of
  Wyandanch's 109 raw hits (94 distinct, 15 distinct on-domain), **12 were already in the capture plan
  and 3 were not**. The district holds 18 candidates → 18 captures → 18 records → 18 labels: it was
  fully captured, processed, and human-labeled. Quote the *not-in-any-capture-plan* column as the harm,
  never the raw count.
- **"Wyandanch's ladder terminated" is false as of #719.** Live predicates today return
  `usable_scoping_domains → ('wyandanch.k12.ny.us','nces')` and `ladder_exhausted → False`; the composer
  routes it to `domain+widened`. The district is not stuck.
- **The regression is general, not a Wyandanch curiosity, but must be classified before it is totalled.**
  10 of 56 consecutive rung pairs kept fewer candidates than their predecessor: **8** are #719's own
  evidence set (a geo rung composed for a domain-having district — no longer composable), **1** is
  `0101920` `batch_00013→00026` (322→309, domain-scoped, no derivation involved at all), and **1** is the
  mechanism #719 did *not* fix — a rung that derives a host followed by a widened rung that dilutes the
  same host below threshold. Counting all 10 as #672's would overstate it ~4x.

**Corpus-wide cost, and it is not small: 164 on-domain URLs are in no capture plan** (Cedar Rapids 51 ·
New Haven CT 29 · Little Rock 26 · Washoe 26 · New Haven Unified 23 · Wyandanch 3 · Union Hill 3 ·
Sweetwater 3), including `cleveland.crschools.us/families-resources/handbook`,
`alicesmith.washoeschools.net/our-school/bell-schedule` and `rsjh.sweetwater1.org/handbooks`. These are
#719-era losses; #719 stops the recurrence but does not recover the URLs. Re-running those districts on
the `domain+widened` rung they now route to is the recovery path (a gate@1 action, Ian's call).

**Resolution (2026-08-21).** *Criterion 1* — a rung that keeps fewer candidates than its predecessor now
records it: `discover_stage2.rung_regression()` writes a `rung_regression` block into `discovery.json`
and appends a durable `state_event` note beside #734's derivation-failure trace. Scoped to the schools
the rung RE-QUERIED, because a follow-up merge unions the prior round in and a whole-document comparison
could never regress — that would be a measurement that cannot fail. Detection only: it records that the
rung did worse, it does not change what the rung kept. *Criterion 3* was already delivered by #734 (the
cause note) and is pinned by `tests/test_stage2_headless.py`; note it has fired **zero** times on real
data because it postdates every geo run to date. *Criterion 2* is **re-scoped, not implemented** — see
below. Tests: `tests/test_stage2_rung_regression.py`.

**Criterion 2 re-scoped (Ian, 2026-08-21).** As written — "a district with a confirmed domain of record
does not lose on-domain results to a failed geo derivation" — it is vacuous at the routing layer since
#719: such a district never enters geo. The only non-vacuous residue was whether a later geo rung should
gate against the previous rung's DERIVED-but-unconfirmed host. **Ian's call: adopting a domain no human
has confirmed is a cost the ramp-up model accepts** (CLAUDE.md's high-supervision-first posture eases
gates toward auto as reliability is proven; a derived host is produced by the same deterministic rule a
human would be confirming). It is therefore not a blocker — but it buys 3 URLs on the one district that
exhibits the mechanism, so it is not worth implementing on its own. The real harm that rung did was to
the STATUS layer, and that is what a fix should target: the district's last stage-2 event reads
`manual_flag_all`, and `candidates.json`'s top-level `domain` is blanked to `''` (the field Stage 3/4
status views read), on a district with 18 labeled records.

### 2g. Geo escalation means TWO things, and only one of them is built (#871, open)

**The intent, on the record (Ian, 2026-08-21).** Escalating a district that HAS a known domain but
INSUFFICIENT schedule signal into a geo-constrained search is *deliberate*, and the reason is **reach**,
not name disambiguation: bell schedules are frequently PDFs or Word documents parked on a CDN or a Google
Drive, **off the district's own domain**. A geo-anchored query is how those get found. This intent had
never been written down, which is the root cause of everything below — §2c/§2f described geo purely as
the domain-DISCOVERY path for domain-less districts, and #719 reasonably read it that way.

So `discovery_scope: "geo"` currently carries two unrelated jobs:

1. **Disambiguate** a common school name nationally for a district with no usable domain (the Millard
   class) — *built, and the only one the code serves.*
2. **Reach off-domain documents** for a district that has a domain but little on-domain signal —
   *intended, never built.*

**The gap.** `gate_urls` / `gate` have exactly two outcomes in a geo run and neither keeps an off-domain
document: derivation fails → every URL refused `no-scoping-domain` (#229 fail-closed); derivation
succeeds → only `on-domain` + `cms-slug` kept, so a CDN or Drive URL is refused `off-district`. The
`cms-slug` branch looks like the escape hatch and is not — it requires the district slug to appear
literally in the URL, and a real Drive URL is an opaque file ID. Measured against the live gate:

```
(False, 'off-district')  https://drive.google.com/file/d/1AbC_xyz/view
(True,  'cms-slug')      https://drive.google.com/wyandanch/bell.pdf
```

`drive.google.com` and `docs.google.com` are IN `CMS_HOSTS` and are still unreachable: the whitelist
admits the host, the slug rule then rejects every URL that host actually serves. Generic CDNs and S3 are
excluded from `CMS_HOSTS` outright (deliberate policy, never a general host/CDN) — which is why
Wyandanch's `core-docs.s3…` top host in §2f could never have helped.

**Interaction with #719 — do NOT read this as a revert.** #719 made geo unrepresentable for a
domain-having district, i.e. exactly the population job 2 is about. That was correct *given the gate as
it stands*: such a round refuses 100% of results and spends SERP budget for nothing (70 schools / 6
batches / 0 resolved). The capability is now blocked twice — routing will not compose it, and the gate
would refuse it if it did. Restoring job 2 means making a geo round able to KEEP an off-domain document
first; only then is routing a domain-having district into it worth anything. Sequencing, not reversal.

Tracked as **#871** (epic #128), which carries the open design questions: admit document-SHAPED
off-domain URLs (`.pdf`/`.doc`/`.docx`) on a geo-anchored query; give `cms-slug` a second satisfier for
opaque document hosts; or split job 2 into its own scope (`discovery_scope: "asset"`) rather than
overloading `geo`. Whether that re-opens the #227 national-contamination class is the question to settle
first — #227 was about keeping whole unscoped SITES, and this is narrower.

**Seed-URL injection (dormant, #161):** `write_discovery()` also injects any `seed_urls` present on the
district entry straight into `candidates.json` (tool `seed_7to3`, deduped by normalized URL against
whatever discovery already produced) — pre-specified capture targets carried on a 7→3 recapture
directive, bypassing discovery entirely so Stage 3 captures them through the ordinary candidates.json
pipe. No current producer sets `seed_urls` on a batch; the plumbing is wired ahead of a future judge-fed
producer.

---

## 3. Console surface

Stage 2 is **ungated** — the console surfaces it as **status/observability** only: per-district outcome,
Wave-1 vs. Wave-2 found counts, the deduped candidate count, and `manual_flag` schools needing eventual
human follow-up. The reviewer's first real decision point on this batch's discovery output is `gate@5`.

**`headless.status_for_batch()` / `rollup()`** are the functions actually backing this view. Lifecycle
(`todo`/`done`) is read from disk — a district is `done` iff its `discovery.json` exists, the
authoritative data source — while the metrics (per-district Wave-1/Wave-2 found counts, the
`manual_flag` school list, deduped candidate count, outcome) come from the DB's `discovery_school`/
`candidate` cache tables, upserted by the Stage-2 finish hook (`common.cache_ingest.cache_discovery`,
per-district DELETE-then-UPSERT, so a re-discovery's stale rows never linger). **Self-healing:**
`status_for_batch()` itself backfills the cache inline for any district that's `done` on disk but missing
from `discovery_school` (e.g. a district discovered before the cache hook existed), so the view repairs
itself on first read rather than needing a backfill script. `rollup()` reduces the per-district rows to
the batch-level header counts (total/done/todo, found_all/found_partial/manual_flag_all, manual_flag
school count).

**Live progress via a job-feed event stream:** `run_batch()` takes an `on_event(kind, payload)` callback
and emits `reconciled` (todo/skipped district lists), `dispatched` (per district, before it runs),
`completed` (per district, with outcome), and `failed` (per district, with error) — the mechanism the
console's job feed consumes to show a run in flight rather than only a post-hoc status page. A failed
district's exception prints its full traceback to job stdout (#452) before the bounded 200-char note is
persisted to the registry — the persisted note stays short, but a deep failure's location is still
findable. Per-district registry writes during a run use `DS.save(registry, export=False)`, deferring the
full `district_status.json` regeneration (an O(N²) cost over a run, #49) to exactly one `DS.export()`
call at the very end, in a `finally` — so a crash mid-run still leaves the backup file current with
whatever events actually committed.

**Shared UI labels + left-pane progress:** `static/outcomes.js` (`outcomeBadge`, `progressBadge`) — the
same elements Stage 3/4 use, so a label rename is one edit. The active batch's chip live-syncs to the
header during a run.

**User stories (not yet built):**
- Review search-query templates and propose new ones. (tracked: #102)

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
- **Geo ladder's widened rung can defeat a share-based derivation the standard rung already held** (#672,
  open, §2f) — a real production case (Wyandanch UFSD, `3631800`) where widening tripled the raw result
  count but dropped the winning host's share below `min_share`, discarding candidates the standard rung
  had already found and used. Open question: whether the fix is a count-based fallback, a per-rung
  minimum floor, re-gating against the standard rung's derivation before falling back to the widened
  one's, or something else — not yet decided.

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
`docs/research/SERP_API_PROVIDER_COMPARISON_2026-06.md`. Live result: batch_00002's Bright Data Wave-1
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

**2026-07-11 — a district with an empty NCES website runs UNSCOPED discovery, and common school names
collide nationwide (#227, root-caused).** Found in the batch_00013 shakedown: Millard Public Schools (NE)
is the only district in the batch with `domain=''` (NCES `website` column blank,
`queue_batch.py`'s `domain = host_of(web) if web else ""`), which flipped `discover.py`'s `gate()` to its
unscoped branch (`return True, "unscoped"` — keeps any non-news result when there's no domain to scope
to). For common school names ("Reagan", "Russell", "North") the unscoped Google SERP pulled same-named
schools from OTHER districts nationwide (102 distinct hosts over 147 captures; only 44 on the real
`mpsomaha.org`). All 11 scoped districts in the same batch were clean (0 off-domain discovered) — this
was specifically the unscoped-fallback path, not a general discovery-quality problem. Millard's 44
legitimate captures were still valid; the contamination was confined to gate@5 labeling (STAGE5 change
log, #228) and quarantined from dispatch pending a fix.

**2026-07-12 — #229 shipped: refuse a non-scoping domain at the source, plus Stage 2's own
defense-in-depth (PR #242).** Two layers, not one: (1) Stage 1's `build_batch` now refuses/flags a
blank-or-junk NCES `website` cell at batch-creation time, using the new `common.discover.domain_of()` +
`is_scoping_domain()` helpers (`domain_of` normalizes a raw NCES `WEBSITE` cell to a bare host or `''`;
`is_scoping_domain` validates whether that host can actually scope discovery — rejects blank, `N/A`→`n`,
`none`, and address-like junk like `375 LEE ST`→`375 lee st`, requires a dotted hostname with no
whitespace) — so a Millard-shaped district should no longer reach Stage 2 with an unscoped domain in the
first place. (2) **Stage 2 does not merely trust that upstream guard** — `discover_stage2.gate_urls()`
(§2c) independently calls `is_scoping_domain(domain)` and fails closed, rejecting every URL with reason
`"no-scoping-domain — unscoped discovery refused (#229)"` before `gate()`'s old unscoped branch is ever
reached. The two-layer design is deliberate: Stage 1's admission guard prevents the common case, but
Stage 2's own chokepoint means a blank/junk domain arriving by any *other* path (a manual DB edit, a
future batch builder, a remediation script) still can't silently reopen the same nationwide-collision
failure mode — the run visibly yields nothing for that district instead. Shipped alongside #228
(a console reset-labels button) and the Millard remediation itself, all in commit 7655277/PR #242.

**2026-07-18/19 — epic #111 Phase 1 correctness sweep (PR #549, #265/#341/#452/#523/#524): crash-tolerant
merge, true per-URL provenance, and a stale docstring corrected.** The merge-retry crash gap (#265): a
crashed `merge=True` redo could leave an orphaned `candidates.json` with no `discovery.json`, and the old
single `disc_path.exists()` gate covering both manifests silently dropped the prior round's candidates on
retry — fixed by `_prior_doc` reading each manifest independently, live-or-newest-aside-or-empty (§2e).
Wave-1 provenance (#341): `flatten()` now prefers each URL's own `provider` key over the per-school
scalar, so a widen-strategy school's mid-set failover keeps per-URL attribution (§2c); paired with #523's
`None`-vs-`[]` fix distinguishing a failed query from one that ran and found nothing (§2c-bis). #452:
a failed district's full traceback now prints to job stdout before the bounded persisted note, so a deep
failure's location stays findable (§3). #524 corrected `discover_stage2.py`'s own module docstring, which
had kept describing the retired agent-in-the-loop framing as current years after the deterministic SERP
cascade replaced it — this doc's own "known code-level inconsistency" callout about that docstring is now
resolved and removed. See §2c/§2c-bis/§2e/§3 for the present-state description.

**2026-07-18 — #526: the console/autoflow batch read moved off the on-disk receipt onto the governance
DB — the "JSON is never the transport between stages" invariant now holds for every stage.**
`headless.run_batch` takes the resolved batch **dict** (the Stage-3/4 contract) instead of a
batch_id/receipt ref; the console (`/api/discover/*`) and autoflow resolve it via
`server._batch_from_db`, now rebased on `batch_store.to_receipt_doc` (the canonical INCLUDED-only
batch_doc) + `batch_status`. The rebase matters beyond symmetry: the old `to_view` basis filtered
districts but **not schools**, so gate@1-rejected schools survived in `schools_by_band` — harmless for
Stages 3/4 (which never read schools), roster-poisoning for Stage 2 (which builds its roster from it);
a govdb regression test pins this. `load_batch_any` survives strictly as the CLI/offline receipt
loader, enforced by the new `cli_only_loaders` fitness function in `arch-manifest.json` (#124): any
reference to it under `process_governance/` fails the suite, so the receipt-as-transport edge can't
quietly return.

**2026-07-19 — #164 PR 2: the geo discovery run (epic #111 Phase 5).** For a batch with
`discovery_scope: "geo"` (a BATCH axis — scope-pure by construction): `build_roster(geo=True)`
renders the SAME vocabulary geo-scoped (`geo_queries`: city/zip tokens, widened per query_strategy,
no `site:` — the provider gets a blank dhost); wave 1 runs un-scoped and lands FAIL-CLOSED
(`gate_urls`' blank-domain refusal — the honest interim state); `apply_geo_derivation` then tallies
the RAW result hosts across all schools (news/aggregators excluded), derives the family-merged
majority host (`discover.derive_domain`, ≥40% share ∧ ≥3 distinct schools), and on success RE-GATES
every school's raw URLs through the normal scoped gate (per-URL provider attribution preserved);
wave 2 runs domain-scoped against the derived host, and NEVER runs without one (an unscoped wave 2
would be the #227 class). No derivation → everything stays refused → the district honestly resolves
manual_flag. The `geo_discovery` receipt block (raw + merged tallies, thresholds, outcome, the
derived-host PROPOSAL awaiting human confirmation) lands in discovery.json. Millard 3173740 is the
fixture acceptance (tests/test_discovery_geo_wiring.py); the LIVE run is a gate@1 action. REQ-157.

**2026-07-20 — #572 follow-up: the remediation receipt sanctions a registry-ahead-of-disk redo.**
`reconcile`'s CONTROL FAILURE halt (registry says Stage 2+ but discovery.json missing) now stands
down when the district has an on-disk decontamination restore point
(`data/acquisition/remediation/<district_id>_<ts>/`) — remediate_contamination deliberately
removes artifacts while preserving state history, so registry-ahead-of-disk is that path's
receipted end state, and the district rediscovers fresh (the live case: Millard NE's geo redo in
batch_00021 halted on exactly this). A missing discovery.json with NO receipt still halts the run.
**Now time-bound** (`REMEDIATION_RECEIPT_MAX_AGE_DAYS=30`, #575 narrowing): a receipt older than 30
days no longer excuses the halt, and the check is not stage-scoped — a receipt from ANY stage's
remediation excuses a desync at ANY OTHER stage for the same district. Full mechanism (now the
canonical explanation): `PIPELINE_GOVERNANCE_AND_STATE.md` §11l.
The 5→1 zero-yield modal also gained human-readable district names (`names` in the composer result).

**2026-07-20 — #572: the discovered-domain proposal card + decision corpus.** A GEO batch's Stage-2
readout now renders the derivation per district (host, share, schools, top tally from the
`geo_discovery` receipt) with **Confirm / Reject (reason required)** — placed at the END of Stage 2
deliberately: the evidence is this run's tally, and the decision governs FUTURE domain-scoped
composition, never this batch's own capture (which proceeds on the re-gated candidates regardless).
Both decisions append to the new PRECIOUS `discovered_domain_decision` table (git twin
`discovered_domain_decisions.json`) with the tally as evidence — the training corpus for the future
auto-confirmation (a gate_mode ramp-up candidate; rejections are the negative class). Confirm
additionally upserts the operative `discovered_domain` row (unchanged semantics). First live
proposal: Millard NE → mpsomaha.org, 78.3%/21 schools (batch_00021).

**2026-07-20 — #118/REQ-160 shipped: Stage-2 discovery-tool attribution (the measurement-harness
pattern extended upstream).** `process_governance/attribution.py`'s `stage2_attribution()` answers
which DISCOVERY tool earns its keep: per discovery TOOL, candidates proposed → canonical records →
human-labeled TARGET, over the same human-labeled corpus the Stage-5 harness scores. Attribution
joins each canonical record back to the `candidate` plan row for its (district, url) and that row's
`tools_json` (which SERP provider(s) proposed the URL — `"brightdata"`/`"serper"`/`"claude_websearch"`,
§2c); a record with no plan row falls back to its capture `source` (`emergent`/`manual`/`benchmark_gt`).
Live at `GET /api/attribution` (`server.py`), rendered via the shared `attributionPanel()`
(`static/outcomes.js`) mounted on both `static/stage2.js` and `static/stage4.js` (Stage 4's own
`stage4_attribution()` is the processing-tool counterpart, out of scope for this doc). First card:
emergent one-hop is the highest-yield non-GT discovery source, 38.1% labeled-target rate.

**2026-07-26 — epic #617/#619/#662: redo-eligibility became a DECLARED batch attribute
(`redo_attempted`), no longer derived from `batch_type=="follow-up"` alone.** §2e's merge/todo
carve-out now reads `common/batch_types.py::redoes_attempted(batch)`: a `follow-up`-typed batch still
redoes by default, but a `benchmark`-typed batch (e.g. `batch_00000`) only redoes when its composer
explicitly declares it — the point being to let a real Stages-2/3/4 A/B harness re-run benchmark
districts without accidentally reopening `batch_00000`'s frozen `gt://` candidate sets to silent
`merge=True` mutation any time a benchmark batch happened to exist. Pre-#617 batch rows/receipts (no
`redo_attempted` field) fall back to the historical `batch_type=="follow-up"` rule, byte-identical
behavior. Full epic context: `docs/technical-notes/learning-loop-reports/
2026-07-25-epic617-benchmark-model-findings.md`, CLAUDE.md's "Current status" section.

**2026-07-28 — #672 filed: the geo derivation ladder's widened rung is not monotonically better than
its standard rung, and can discard candidates the standard rung already held (epic #128, open).** See
§2f for the mechanism and the Wyandanch UFSD (`3631800`) measurement. Not yet fixed; this is a defect
against §2c/2026-07-19's derivation design, not a new design decision — logged here per this doc's own
"design turns and superseded approaches belong in the decision log" convention, and cross-referenced
from §2f/§4 rather than re-litigated in three places.
