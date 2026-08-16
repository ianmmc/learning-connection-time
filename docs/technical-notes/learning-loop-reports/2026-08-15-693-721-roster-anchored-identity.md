# #693/#721 — roster-anchored school identity: findings & design

> **Authority:** the exploration record and implementation plan for #693 (name-axis false splits)
> and #721 (band-axis false splits), produced 2026-08-15 as Tranche C step 1 of the #620-campaign
> fix queue. This is a **point-in-time findings report**, not a living design note — where it
> disagrees with `STAGE8_AGGREGATE_DESIGN.md` / `STAGE7_EXTRACT_DESIGN.md` after implementation
> lands, **those are authoritative and this is history**.
> **Audience:** whoever implements or reviews the fix; the Council Lab (both issues live under
> epic #80 — `n_unresolved` is a lab headline metric and is currently polluted by these defects);
> future work touching `norm_school`, the consensus grouping key, or slot-spine coverage.
> **Companions:** GitHub #693, #721 (the defects) · #707 (the existing degenerate-name resolution
> this design extends) · #681 (the false-AGREEMENT sibling both fixes must not reproduce) · #245
> (the degenerate-name guard) · #694 (slot-spine follow-ups — a beneficiary) · #716 (the
> zero-spend re-aggregation replay that makes this fix retroactive) · `common/school_match.py`
> (REQ-117, the one-home identity key) · `STAGE8_AGGREGATE_DESIGN.md`.
> **Update this when:** never, except to append to §9 (the implementation log) as phases land, and
> to correct a §1–§8 claim that implementation *disproved* — marked, not silently rewritten.

---

## 1. Both defects reproduce exactly as filed — with one correction

Measured live against the governance DB (3,476 `school_fact` rows; 2,566 accepted / 910
unresolved; 161 extractions, 83 districts), 2026-08-15:

- **Cleveland `3904378` ext 6561 (#693):** `lincoln west science health` (accepted, judge, 420)
  vs `lincoln west science and health` (unresolved) — **both models read 08:35–15:35**. A pure
  spelling split promoted to a fact disagreement.
- **Essex Westford `5000395` ext 6562 (#693):** every accepted school is an acronym
  (`adl fms ofle sum wes ems cte oehs`, all judge-rescued singletons), every unresolved is
  spelled out (`founders memorial`, `qoees`, `ohia`).
- **Washoe `3200480` ext 7696 (#721):** `gerlach k 12` fragments into a `high` singleton
  (accepted via judge) and a `middle` singleton (unresolved). Ext 80 shows the same school ALSO
  name-split (`gerlach k12` vs `gerlach k12 hs`) — the two axes co-occur.
- **Correction to #693's second example:** `x hannah gibbons` / `hannah gibbons` is a real
  name-split but the times do NOT agree — judge accepted 08:40–15:40 (420) while mistral read
  09:10–15:40 (390). Merging it surfaces a genuine 30-minute start disagreement; it is not an
  automatic agreement like the Lincoln-West pair.

## 2. The finding that overturns #721's proposed fix (measure-first, instance six)

#721's option 1 — *"group on `normalized_school_name` alone; treat `grade_level` as a per-model
attribute"* — would cause a **mass false-merge**. `norm_school` strips level words by design
(REQ-117: `Marion High School` == `Marion`), so distinct schools in the same district collapse to
one key: `APOPKA ELEMENTARY / MIDDLE / HIGH` → all `apopka`; `Essex Elementary / Middle / High` →
all `essex`. **The band in the grouping key is currently the only thing keeping these real schools
apart.**

Classifying all 125 same-name/different-band groups (≥1 unresolved member) against the NCES
roster:

| class | groups | unresolved rows | districts | name-only grouping would… |
|---|---|---|---|---|
| `level_collapse` — distinct roster schools sharing a norm key | **35** | 60 | 12 | **fuse real schools** (#681 mass-produced) |
| `not_in_roster` — extracted name matches no roster entry | 75 | 153 | 33 | unknown; unsafe |
| `true_multiband` — ONE roster school serving 2+ bands | **11** | 18 | 8 | correctly merge (Gerlach, Nathan Hale, Daniel E Morgan…) |
| `single_band_roster` — school rostered in exactly one band | 4 | 17 | 4 | — |

Option 1 breaks 35 groups to fix 11. **The roster is the discriminator** — and it is already
threaded to the consensus boundary (`consensus_context_for_district`, built for #707).

## 3. What each #693 fix shape is measurably worth

Over the 1,828 distinct (district, school-key) pairs in `school_fact` (991 already exact-match the
roster):

| rule | uniquely resolves | ambiguous | verdict |
|---|---|---|---|
| stopword widening (`and`, leading initial) | 4 pairs corpus-wide | — | near-worthless beyond the filed anecdotes; do NOT touch `norm_school` |
| acronym **computed on the full name** (level words kept: `Essex Middle School`→`ems`) | 20 | 0 | clean; resolves Essex end-to-end |
| token-set-equal (`everett meredith` ↔ `Meredith (Everett) Middle School`) | 17 | 0 | clean |
| key ⊂ roster tokens, unique | 166 | 4 | good WITH the uniqueness guard |
| grade-span-token strip (`kinston k12` → `Kinston School`) | found late; in-band re-measure in §9 | — | safe: `k12/k8/jrsr/prek…` never distinguish same-band schools |
| roster ⊂ key tokens | 136 | 12 | **REJECT** — manufactures `regular day bell schedule`→*Bell Middle*, `appoquinimink preschool full`→*Appoquinimink High* |

Two instrument lessons that are now design constraints: the acronym rule undercounts 5× if
computed on the stripped key (4 vs 20 — it must see the level words), and the loosest rule is
value-negative. **Ambiguity is sacred:** 16 keys match 2+ distinct roster schools (`rhodes` →
*Rhodes College and Career* + *Rhodes School of Environmental Studies*) and must stay split —
that is #681's defect wearing a resolver's clothes.

## 4. The URL-in-lieu proposal (Ian, 2026-08-15), measured

Proposal: after best-effort roster matching fails, screen for excluded school types, then use the
school's subdomain (or its branch of the district URL) as a **domain-validated name-in-lieu**.

Over the 651 unmatched (district, key) pairs (after exact + safe loosened rules):

| population | n | implication |
|---|---|---|
| excluded-type screen hits (preschool/ECC/adult/alternative) | 26 | the screen catches real cases (`dr mayo eclc`, `bucks hill pre k`, `gulfstream early learning center`) |
| source rep **1:1** with the school | **61 (9%)** | URL can serve as identity; token corroborates the name in 18 (Apptegy `/o/jcibpc`, subdomain acronyms `rjs.matsuk12.us`) |
| source rep is a **hub doc** (2–63 schools/document) | **590 (91%)** | the URL names the *document*, not any school — per-school domain-validation impossible by construction |

So the proposal works exactly where scoped — dedicated subdomain / school branch — but that
topology covers ~9% of the unmatched population, and some of those URLs are CDN-asset
(`files-backend.thrillshare.com`) or `gt://` paths carrying no school identity. For the hub-doc
majority the auditable name-in-lieu must be **the extracted name itself**, held as identity with
the document URL attached as provenance (already on the row: `rec_key` → `record.url`).

**The Kinston lesson:** several "unmatched" keys are recoverable — `kinston k12` / `zion chapel
k12` ARE this district's rostered schools (`Kinston School`, `Zion Chapel High School`), missed
only for a glued-on grade-span token. The terminal unmatched population is smaller than 651; the
ladder's rung 2 shrinks it before rungs 4–5 ever run.

## 5. The design: one resolution ladder, both axes

Identity resolution runs at the consensus boundary (`consensus_school_facts`), band-scoped
against the roster the context already carries, extended to carry `school_id` per slot. Every
non-exact resolution is **method-marked and gate@8-visible**; `norm_school` itself is untouched
(no persisted-key migration, no fingerprint risk).

1. **Exact** — `norm_school(name)` matches a roster school **in the claimed band** → that
   identity.
2. **Safe loosened rules**, in order, each requiring a UNIQUE roster hit in the claimed band:
   grade-span strip → acronym-on-full-name → token-set-equal → key⊂roster-tokens. Marked with the
   rule that fired.
3. **Ambiguous** (2+ distinct roster schools by the first rule that hits) → NO resolution; keep
   split; flag for gate@8.
4. **Unmatched → exclusion screen** (`facility_name_flags` + preschool/EC/alternative/virtual
   patterns): a hit routes the fact to `unresolved` with an explicit reason — auditable, never a
   silent drop, and kept off roster slots and band modes.
5. **Unmatched, screened clean → name-in-lieu**: the extracted name stands as identity, marked
   `roster_unmatched`; where the rep is 1:1 with the school AND its URL carries a corroborating
   school-distinctive token, additionally marked `url_validated` with the slug. Counts in the
   band mode, visible at gate@8, **never fills a roster slot** (stops #694 re-chasing schools
   already extracted under unmatchable names).

**Band axis (#721), riding the same ladder** — after name resolution, same-identity groups across
bands are adjudicated by the roster's own placement (`school_id` across `slot_recs`):

- **Roster-confirmed multiband** (one `school_id` rostered in 2+ bands — Gerlach): pool the
  cross-band votes for time consensus; emit the fact for each band the school is rostered in
  *and* at least one voter claimed; marked `band_adjudication=roster_multiband`. No vote is
  minted for an unclaimed band.
- **Single-band rostered** school claimed in a wrong band: votes merge into the roster band,
  marked `band_adjudication=roster_band`.
- **Unmatched name, cross-band singletons**: one visible `unresolved` row with reason
  `band_disagreement` (#721's option 3 — the strict auditability improvement), per-model votes
  and claimed bands in `detail_json`.
- **`level_collapse` names are never band-merged** — they resolve to different `school_id`s at
  rung 1/2 and stay distinct by construction.

## 6. Persistence & retroactivity

- Marking rides a new nullable `school_fact.identity_json` column (v5 of the additive-column
  precedent: v2 `evidence_json`, v3 `school_year/applies_to`, v4 `campus_names_json`): declared
  in BOTH `models.py` and `_PRECIOUS_ALTERS` (the PR #641 double-DDL invariant; verified against
  a THROWAWAY governance DB), no backfill, going-forward.
- The fix lands inside the deterministic half replayed by the #716 re-aggregation path
  (`consensus_context_for_district` is the shared mechanism), so **every existing false split is
  recoverable from stored receipts at zero model spend** — Cleveland, Essex, Washoe first, then
  corpus-wide as gate@8 re-review capacity allows.

## 7. What must NOT change (the guard-rails)

- The **level-collapse pin**: Apopka/Essex/Prince-Edward-style districts must keep one fact per
  real school. This is the regression a future "just merge on name" change would break; it gets
  a named test.
- The **#245 degenerate-name guard** and the **#707 resolution paths** (`band_referent`,
  `roster_unique`) are upstream of this ladder and keep their exact semantics — bare `es/ms/hs`
  keys stay #707's problem, not rung 2's.
- **The judge cannot mint an identity** (the #707 rule generalizes): resolution changes GROUPING
  only; a judge-rescued singleton whose name resolves gains the marking but still needs the same
  consensus it needs today.
- **Ambiguity keeps the split** — a resolver that guesses between two roster schools is #681.

## 8. Acceptance properties (falsifiable; each becomes a test)

- **P1 (must fail pre-fix):** Cleveland's `lincoln west science [and] health` pair → ONE group,
  one accepted fact, marked resolved.
- **P2:** `x hannah gibbons` + `hannah gibbons` → one group whose 30-min start disagreement is
  then adjudicated by the normal council path (NOT auto-accepted).
- **P3:** Essex acronym/spelled-out forms group together via acronym-on-full-name.
- **P4 (must fail pre-fix):** Gerlach's identical rows differing only in band → an accepted fact
  with band adjudicated by roster, or an explicit `band_disagreement` row — never two silent
  singletons.
- **P5 (the pin):** an Apopka-style level-collapse district: three bands' facts stay three
  distinct schools; no cross-band merge.
- **P6:** `rhodes` with 2+ roster candidates stays unresolved-ambiguous; no guess.
- **P7:** an excluded-type name (`* early learning center`) routes to `unresolved` with the
  explicit screen reason; never accepted, never silently dropped.
- **P8:** an unmatched clean name survives as an accepted fact marked `roster_unmatched` and
  fills no slot.
- **P9:** #707's degenerate paths and #245's guard byte-identical behavior on their existing
  pinned cases (the current test suite must stay green untouched).
- **P10 (corpus, reported in the PR):** re-run of the §2/§3 measurements post-fix — false splits
  resolved vs. schools wrongly merged, target 0 of the latter against the roster + GT corpus.

## 9. Implementation log

**Phase 1 (2026-08-15) — the resolver (`resolve_school_identity`, `common/school_match.py`) +
pins (`tests/test_school_identity.py`).** Corpus validation against real rosters corrected the
design three ways before any consensus wiring:

- **§5's "norm_school untouched" was half-wrong.** The Cleveland split's root cause is a
  normalizer ASYMMETRY — `&` was punctuation-dropped while `and` was a kept token, so the same
  conjunction normalized two ways by typography. `and` is now in `_GENERIC` (measured first: 0
  collisions across all 83 corpus districts' rosters). The §3 "stopword widening is
  near-worthless" claim stands for reach (4 pairs) but the asymmetry made this one strictly
  correct to fix at the normalizer.
- **Grade-span stripping must require digits.** Bare `prek`/`pk` marks an excluded-grade
  *program*, not a span — `bucks hill prek` was fusing into Bucks Hill Elementary in the first
  validation run; it now stays unmatched for the rung-4 screen. (`k12`, `k 8`, `pk 8` still
  strip.)
- **Forms compose with rules.** `x hannah gibbons` needs leading-initial-strip *then*
  token-subset, because the real roster name is `Hannah Gibbons-Nottingham Elementary School` —
  a naive fixture with `Hannah Gibbons School` passed while production failed. Test fixtures now
  pin the real ccd_sch names.

Corpus numbers post-fix (2,082 distinct (district, band, key)): 1,121 exact · 292 resolved
non-exact (184 token_subset, 28 acronym, 28+13 grade_span, 19 token_set, 1 leading_initial
composite) · 11 ambiguous kept split · 677 unmatched (rungs 4–5's population) · **0 wrong
merges** · 26 in-extraction #693 merges · 48 cross-band #721 groups.

**Collateral find:** `project_slots` consumed persisted `SlotAssignment.norm_school_fact` keys
WITHOUT re-normalizing through the current function — the school_match self-healing contract
(merge_fact_runs, #237) was wired into some readers of the set but not this one (the recurring
"guard wired into one member of a set" class). 0 live rows affected by today's `and` change, but
any future stopword change would have silently detached stored human dispositions. Fixed at
intake + pinned (`test_stored_disposition_key_self_heals_across_normalizer_change`).
