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
    """A secret from env or the gitignored secrets file (repo-anchored, never CWD-relative)."""
    return os.getenv(name) or (json.loads(SECRETS_FILE.read_text()).get(name)
                               if SECRETS_FILE.exists() else None)


def serper_search(q, dhost, k=10, _sleep=time.sleep):
    """Serper.dev Google SERP -- domain-scoped via `site:`, returns organic result URLs. The Stage 2
    Wave-1 UPTIME FAILOVER (banked credits; ~$0.001/query). Measured 100% recall on the 53-school
    known-positive set. Billing/auth (401/402) -> SystemExit halt (every later call would fail
    identically). A 429 is TRANSIENT (issue #29): one short sleep + single retry, then
    TransientProviderError (a plain exception -- the caller degrades that school, the run continues)."""
    import requests

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
