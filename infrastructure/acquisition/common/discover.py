"""Shared discovery helpers + the Stage-2 Wave-1 SERP providers.

Two things live here, both imported across stages (so they sit in `common/` — stages must not
import each other, the import-linter layering contract):
  - **URL helpers** used by Stage 1 (benchmark_batch) and Stage 2 (discover_stage2): `host_of`,
    `slugify`, and the smart-`gate()` domain/CMS/news filter.
  - **Wave-1 SERP providers** the Stage-2 runner cascades over: `brightdata_search` (primary,
    real-Google, recurring free tier) → `serper_search` (uptime failover). Billing/auth (401/402)
    halts the run; a 429 is transient (issue #29) → failover / per-school degrade.

(The retired Perplexity/OpenRouter AI-search providers were removed in #87.)"""
import os, json, re, time
from urllib.parse import urlparse

from infrastructure.acquisition.common import config_loader  # noqa: E402  (config-as-data layer — REQ-088)
from infrastructure.acquisition.common import paths  # noqa: E402  (repo-anchored locations — REQ-087)

# Trusted K-12 CMS / content-host SUFFIXES -- the shared config-as-data knob `cms_hosts`
# (single source of truth with capture_discovery.mjs; no more hand-syncing). LOAD-BEARING in
# gate(): an off-domain candidate whose host ends with one of these AND contains the district
# slug is kept. Governance + per-entry provenance live in the config file. REQ-089.
CMS_HOSTS=tuple(config_loader.values("cms_hosts"))
NEWS_AGG=("patch.com","niche.com","greatschools.org","wikipedia.org","news12.com","facebook.com","instagram.com","twitter.com","x.com","yelp.com","usnews.com","schooldigger.com","publicschoolreview.com")

def host_of(url):
    try: return urlparse(url).netloc.lower().split(":")[0].replace("www.","")
    except Exception: return ""

def domain_of(website: str) -> str:
    """Normalize a raw NCES CCD `WEBSITE` cell to a bare host, or '' if blank. Centralizes the
    prefix-then-host_of dance Stage 1 used inline in three places (queue_batch build_batch /
    build_followup_batch, benchmark_batch). NOTE: a non-blank-but-junk cell can still normalize to a
    non-empty nonsense host (`http://N/A` -> 'n', `http://none` -> 'none', `http://375 LEE ST` ->
    '375 lee st') -- validate the result with is_scoping_domain(), never truthiness alone."""
    web = (website or "").strip()
    if not web:
        return ""
    return host_of(web if "//" in web else "http://" + web)

def is_scoping_domain(host: str) -> bool:
    """True iff `host` can actually scope Stage-2 discovery: a real dotted hostname with no
    whitespace. Rejects blank, the junk tail the raw NCES `WEBSITE` column carries (2,409 blank
    cells plus `N/A`->'n', 'none', address-like '375 lee st'), and any bare label with no TLD dot.
    A host that fails this flips Stage 2 to its UNSCOPED, national-scope branch (gate() line ~50),
    which for common school names pulls same-named schools nationwide into the district's candidate
    set -- the Millard cross-district contamination (#227). The Stage-1 admission guard (#229).

    Deliberately lenient in one direction: a dotted-but-bogus host ('n.a', 'x.y') still passes. That
    fails SAFE -- it SCOPES discovery to a nonexistent domain (which just yields nothing), it does NOT
    reopen the unscoped-national failure mode -- so we accept the rare wasted scoped run rather than
    risk rejecting a legitimate short/IP/IDN host."""
    h = (host or "").strip()
    return bool(h) and "." in h and not any(c.isspace() for c in h)

def slugify(name: str, maxlen: int = 40) -> str:
    """lowercase, non-alphanumeric -> underscore, collapsed, truncated. district_id is the
    real disambiguator (see stage2_discover.discover_stage2.lea_dir()) -- this is for human
    readability only. Shared by stage1_queue (benchmark_batch) and stage2_discover -- lives in
    common/ because stages must not import each other (import-linter layering contract)."""
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s[:maxlen].rstrip("_")

def _host_matches(h, suffix):
    """True iff host `h` IS `suffix` or is a subdomain of it -- dot-boundary matching (issue #34).
    A bare endswith() lets halifax.com match x.com and evilschoolwires.com match schoolwires.com."""
    return h == suffix or h.endswith("." + suffix)

# #164: the derive-and-re-gate thresholds for a GEO-scoped discovery run. The majority host must
# carry >=40% of the gate-eligible (non-news) results AND appear for >=3 distinct schools' queries;
# below that the run keeps NOTHING and resolves manual_flag — never unscoped-keep-all (the #227
# contamination class). Conservative on purpose; tune by measurement (#118 attribution).
DERIVE_MIN_SHARE = 0.40
DERIVE_MIN_SCHOOLS = 3


def _merge_host_family(host_tally: dict) -> dict:
    """Fold a raw host tally into domain families before derivation (#568 review): SERP results
    routinely mix `www.X`, `X`, and building subdomains (`hs.X`), and counting them as separate
    keys splits the district's own majority (the exact Millard shape #164 rescues). Two merges,
    both conservative: (1) a leading `www.` is stripped; (2) a host folds into an OBSERVED
    dot-boundary ancestor in the tally (hs.mpsomaha.org -> mpsomaha.org only when mpsomaha.org
    itself appeared). Deliberately NO registrable-domain guessing — an eTLD+1 heuristic without a
    public-suffix list collapses pcs.k12.va.us into k12.va.us, which would derive a whole state's
    host. Sibling subdomains with no observed ancestor stay split (fails toward manual_flag,
    never a wrong derivation); revisit with measurement (#118)."""
    merged: dict = {}
    def _add(host, v):
        slot = merged.setdefault(host, {"n": 0, "schools": set()})
        slot["n"] += v.get("n", 0)
        slot["schools"].update(v.get("schools", ()))
    stripped = {}
    for h, v in host_tally.items():
        _h = h[4:] if h.startswith("www.") else h
        if _h in stripped:
            stripped[_h] = {"n": stripped[_h].get("n", 0) + v.get("n", 0),
                            "schools": set(stripped[_h].get("schools", ())) | set(v.get("schools", ()))}
        else:
            stripped[_h] = {"n": v.get("n", 0), "schools": set(v.get("schools", ()))}
    hosts_by_len = sorted(stripped, key=lambda h: h.count("."))   # ancestors first
    for h in hosts_by_len:
        parent = next((a for a in hosts_by_len if a != h and _host_matches(h, a) and a in merged), None)
        _add(parent or h, stripped[h])
    return merged


def derive_domain(host_tally: dict) -> tuple:
    """The #164 majority-host derivation, pure over a geo run's result tally.

    `host_tally`: RAW host -> {"n": result_count, "schools": iterable of school_ids whose queries
    produced it} — news/aggregator hosts already excluded by the caller (they never scope), no
    other normalization required: hosts are family-merged here (_merge_host_family) before the
    thresholds apply. Returns (derived_host | None, receipt); the receipt carries the RAW and
    merged tallies + thresholds for the discovery.json receipt and the discovered_domain
    proposal — the auditor sees exactly why the host was (or wasn't) derived."""
    raw_tally = {h: {"n": v.get("n", 0), "n_schools": len(set(v.get("schools", ())))}
                 for h, v in sorted(host_tally.items(), key=lambda kv: -kv[1].get("n", 0))}
    host_tally = _merge_host_family(host_tally)
    total = sum(v.get("n", 0) for v in host_tally.values())
    receipt = {"total_results": total, "min_share": DERIVE_MIN_SHARE, "min_schools": DERIVE_MIN_SCHOOLS,
               "raw_tally": raw_tally,
               "tally": {h: {"n": v.get("n", 0), "n_schools": len(set(v.get("schools", ())))}
                         for h, v in sorted(host_tally.items(), key=lambda kv: -kv[1].get("n", 0))}}
    if not total:
        return None, {**receipt, "outcome": "no results"}
    top_host, top = max(host_tally.items(), key=lambda kv: (kv[1].get("n", 0), kv[0]))
    share = top.get("n", 0) / total
    n_schools = len(set(top.get("schools", ())))
    if share >= DERIVE_MIN_SHARE and n_schools >= DERIVE_MIN_SCHOOLS and is_scoping_domain(top_host):
        return top_host, {**receipt, "outcome": "derived", "derived_host": top_host,
                          "share": round(share, 3), "n_schools": n_schools}
    return None, {**receipt, "outcome": "below threshold", "top_host": top_host,
                  "share": round(share, 3), "n_schools": n_schools}


def gate(url, dhost, slug, scoped):
    h=host_of(url)
    if not h: return False,"no-host"
    if any(_host_matches(h, n) for n in NEWS_AGG): return False,"news/aggregator"
    if scoped:
        if h==dhost or h.endswith("."+dhost): return True,"on-domain"
        if any(_host_matches(h, c) for c in CMS_HOSTS) and slug and slug in url.lower(): return True,"cms-slug"
        return False,"off-district"
    return True,"unscoped"   # no NCES domain: keep non-news results; Stage-5 signal scoring sorts it out

SECRETS_FILE = paths.SECRETS_FILE   # repo-anchored (issue #31), never CWD-relative

# HTTP statuses that mean "this call was never really attempted" (bad/revoked key, exhausted
# pre-paid balance) -- every later call would fail identically, so this must never be treated
# the same as "the search legitimately found nothing" (see BILLING_AUTH_STATUS_CODES usage
# below). 429 was SPLIT OUT (issue #29): a rate-limit is TRANSIENT -- later calls recover --
# so it must trigger failover/degrade, never a whole-run halt.
BILLING_AUTH_STATUS_CODES = {401, 402}


class TransientProviderError(RuntimeError):
    """A provider failure that is transient/infrastructural (429 rate-limit, non-JSON body, ...):
    the RIGHT reaction is failover (Wave 1: Bright Data -> Serper) or per-school degradation,
    NOT the SystemExit whole-run halt reserved for billing/auth (401/402). Issue #29."""


def _secret(name):
    """A secret from env or the gitignored secrets file (repo-anchored, never CWD-relative).
    Returns None when absent -- _require_secrets() (#328) is the pre-flight that names a
    missing key BEFORE any network call. A MALFORMED secrets file halts here with its own
    message (not a bare JSONDecodeError)."""
    if os.getenv(name):
        return os.getenv(name)
    if not SECRETS_FILE.exists():
        return None
    try:
        return json.loads(SECRETS_FILE.read_text()).get(name)
    except json.JSONDecodeError as e:
        raise SystemExit(f"CONTROL FAILURE: malformed secrets file {SECRETS_FILE}: {e}") from e


def _require_secrets(*names):
    """Pre-flight secret check (#328, review-deepened): validate BEFORE the HTTP call, the same
    shape as stage7's openrouter has_key()/resolve_key(). Replaces the first draft's reactive
    _auth_hint (a message patch at the 401 site), which (a) spent a real network round-trip to
    discover a missing key and (b) could itself raise the malformed-secrets SystemExit
    mid-f-string, masking the original billing/auth status+body. A missing key now halts with
    its own precise message before any request; a genuine 401/402 after this passes IS
    billing/auth, so the halt message needs no hint. In the Wave-1 cascade a Bright Data
    pre-flight halt is caught like any billing halt and fails over to Serper."""
    missing = [n for n in names if not _secret(n)]
    if missing:
        raise SystemExit(f"CONTROL FAILURE: {', '.join(missing)} not set "
                         f"(env or {SECRETS_FILE}) -- a missing key, not a billing problem; "
                         f"no request was sent.")


def serper_search(q, dhost, k=10, _sleep=time.sleep):
    """Serper.dev Google SERP -- domain-scoped via `site:`, returns organic result URLs. The Stage 2
    Wave-1 UPTIME FAILOVER (banked credits; ~$0.001/query). Measured 100% recall on the 53-school
    known-positive set. Billing/auth (401/402) -> SystemExit halt (every later call would fail
    identically). A 429 is TRANSIENT (issue #29): one short sleep + single retry, then
    TransientProviderError (a plain exception -- the caller degrades that school, the run continues)."""
    import requests
    _require_secrets("SERPER_API_KEY")

    def _post():
        return requests.post("https://google.serper.dev/search",
                             headers={"X-API-KEY": _secret("SERPER_API_KEY"), "Content-Type": "application/json"},
                             json={"q": f"{q} site:{dhost}" if dhost else q, "num": k, "gl": "us"},
                             timeout=30)

    r = _post()
    if r.status_code == 429:
        _sleep(2)
        r = _post()
        if r.status_code == 429:
            raise TransientProviderError(f"Serper HTTP 429 (rate-limited) after one retry -- "
                                         f"degrading, not halting. {r.text[:160]}")
    if r.status_code in BILLING_AUTH_STATUS_CODES:
        raise SystemExit(f"CONTROL FAILURE: Serper HTTP {r.status_code} (billing/auth) -- "
                         f"halting the run. {r.text[:160]}")
    r.raise_for_status()
    return [o["link"] for o in r.json().get("organic", []) if o.get("link")][:k]


def brightdata_search(q, dhost, k=10):
    """Bright Data SERP API (Google) -- domain-scoped via `site:`, structured JSON via brd_json. The
    Stage 2 PRIMARY Wave-1 provider (5,000/mo RECURRING free tier; ~$0.0015/query above it). Measured
    98% recall on the 53-school set. Needs BRIGHTDATA_API_KEY + a SERP-API-type zone in
    BRIGHTDATA_SERP_ZONE (a residential-proxy zone returns HTML/empty -> the TransientProviderError
    below). Billing/auth (401/402) -> SystemExit; a 429 is TRANSIENT (issue #29) and raises
    TransientProviderError so the Wave-1 cascade fails over to Serper instead of halting."""
    import requests
    from urllib.parse import quote_plus
    _require_secrets("BRIGHTDATA_API_KEY", "BRIGHTDATA_SERP_ZONE")
    qq = f"{q} site:{dhost}" if dhost else q
    gurl = f"https://www.google.com/search?q={quote_plus(qq)}&hl=en&gl=us&brd_json=1"
    r = requests.post("https://api.brightdata.com/request",
                      headers={"Authorization": f"Bearer {_secret('BRIGHTDATA_API_KEY')}",
                               "Content-Type": "application/json"},
                      json={"zone": _secret("BRIGHTDATA_SERP_ZONE"), "url": gurl, "format": "raw"},
                      timeout=60)
    if r.status_code in BILLING_AUTH_STATUS_CODES:
        raise SystemExit(f"CONTROL FAILURE: Bright Data HTTP {r.status_code} (billing/auth) -- "
                         f"halting the run. {r.text[:160]}")
    if r.status_code == 429:
        raise TransientProviderError(f"Bright Data HTTP 429 (rate-limited) -- transient, "
                                     f"failover to Serper. {r.text[:160]}")
    r.raise_for_status()
    try:
        body = r.json()
        if isinstance(body, str):
            body = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        raise TransientProviderError(f"Bright Data returned non-JSON (is BRIGHTDATA_SERP_ZONE a SERP "
                                     f"API zone? got: {r.text[:120]!r})")
    org = body.get("organic") or body.get("organic_results") or []
    return [(o.get("link") or o.get("url")) for o in org if (o.get("link") or o.get("url"))][:k]


# Canonical provenance names (issue #30): Stage 2's flatten() records WHICH provider actually
# served each kept URL into candidates.json `tools[]` (-> DB cache -> Stage-5 candidate_tools_json),
# so the names must be the real providers, not the retired claude/openrouter wave labels.
serper_search.provider_name = "serper"
brightdata_search.provider_name = "brightdata"
