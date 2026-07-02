"""Discovery v3: domain-scoped search (Perplexity param + OpenRouter site:) + smart URL gate,
with an unscoped fallback for districts whose NCES WEBSITE is blank. Ranks candidates
(schedule-keyword URLs + multi-tool agreement first) and caps per district. Google dropped.
Writes candidates.json (gated, ranked, capped) + rejected.json. Usage: discover.py [ids] [cap]"""
import os, json, sys, csv, time
from urllib.parse import urlparse

from infrastructure.acquisition.common import config_loader  # noqa: E402  (config-as-data layer — REQ-088)
from infrastructure.acquisition.common import paths  # noqa: E402  (repo-anchored locations — REQ-087)

# Repo-anchored, never CWD-relative (issue #31): this module is imported by the governance server
# and the Stage-2 runners, which may be launched from any directory — a bare Path("config/...")
# silently resolves against the launch CWD (the exact bug class paths.py exists to end).
OUT=paths.ACQUISITION / "discovery"
NCES=paths.DATA_ROOT / "raw/federal/nces-ccd/2023_24/ccd_lea_029_2324_w_1a_073124.csv"
# Trusted K-12 CMS / content-host SUFFIXES -- now the shared config-as-data knob `cms_hosts`
# (single source of truth with capture_discovery.mjs; no more hand-syncing). LOAD-BEARING in
# gate(): an off-domain candidate whose host ends with one of these AND contains the district
# slug is kept. Governance + per-entry provenance live in the config file. REQ-089.
CMS_HOSTS=tuple(config_loader.values("cms_hosts"))
NEWS_AGG=("patch.com","niche.com","greatschools.org","wikipedia.org","news12.com","facebook.com","instagram.com","twitter.com","x.com","yelp.com","usnews.com","schooldigger.com","publicschoolreview.com")
SCHED_KW=("bell","schedule","hours","start-time","start_time","daily-schedule","times","school-day","schoolday")

def host_of(url):
    try: return urlparse(url).netloc.lower().split(":")[0].replace("www.","")
    except Exception: return ""

def load_domains():
    out={}
    with open(NCES, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            w=row.get("WEBSITE","") or ""
            out[row.get("LEAID","").zfill(7)] = host_of(w if "//" in w else "http://"+w) if w else ""
    return out

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
    return True,"unscoped"   # no NCES domain: keep non-news results; relevance gate sorts it out

def perplexity_search(q, dhost, k=10):
    from perplexity import Perplexity
    kw={"query":q,"max_results":k}
    if dhost: kw["search_domain_filter"]=[dhost]
    r=Perplexity().search.create(**kw)
    return [getattr(it,"url","") for it in (r.results or []) if getattr(it,"url","")]

SECRETS_FILE = paths.SECRETS_FILE   # repo-anchored (issue #31), never CWD-relative

def _openrouter_key():
    """OPENROUTER_API_KEY isn't auto-loaded from .env or secrets.local.json -- and in any
    execution environment where each shell command starts fresh (no persisted env across
    calls), an `export` done once is silently gone by the next call. Fall back to reading
    the key directly from secrets.local.json rather than depending on that export having
    survived. Returns the value directly -- deliberately does NOT set os.environ, since
    that would make the key visible to every later subprocess this process spawns for no
    functional benefit (the one caller uses the return value directly)."""
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        return json.loads(SECRETS_FILE.read_text()).get("OPENROUTER_API_KEY")
    except Exception:
        return None

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

def openrouter_search(q, dhost, k=10):
    import openai
    c=openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=_openrouter_key())
    query=f"{q} site:{dhost}" if dhost else q
    try:
        r=c.chat.completions.create(model="openai/gpt-4o-mini-search-preview",
            messages=[{"role":"user","content":query}], max_tokens=600, extra_body={"plugins":[{"id":"web"}]})
    except openai.APIStatusError as e:
        if e.status_code in BILLING_AUTH_STATUS_CODES:
            # SystemExit, not a plain Exception -- callers that do `except Exception` (e.g.
            # discover_stage2.run_wave2's per-school degradation) must NOT catch this; it has
            # to propagate and halt the whole run, the same as a reconcile() CONTROL FAILURE.
            raise SystemExit(
                f"CONTROL FAILURE: OpenRouter returned HTTP {e.status_code} -- this is a "
                f"billing/auth failure, not 'no results found'. Every remaining "
                f"Wave 2 call would fail identically. Stopping the entire run -- check the "
                f"account balance / API key before re-running. ({str(e)[:200]})"
            )
        raise   # 429/5xx/etc propagate as the plain APIStatusError -- transient, caller degrades
    ann=getattr(r.choices[0].message,"annotations",None) or []
    out=[]
    for a in ann:
        ad=a if isinstance(a,dict) else a.model_dump()
        u=(ad.get("url_citation") or {}).get("url") or ad.get("url")
        if u: out.append(u)
    return out[:k]

def _secret(name):
    """A secret from env or the gitignored secrets file (same fallback rationale as _openrouter_key)."""
    return os.getenv(name) or (json.loads(SECRETS_FILE.read_text()).get(name)
                               if SECRETS_FILE.exists() else None)


def serper_search(q, dhost, k=10, _sleep=time.sleep):
    """Serper.dev Google SERP -- domain-scoped via `site:`, returns organic result URLs. The Stage 2
    Wave-1 UPTIME FAILOVER (banked credits; ~$0.001/query). Measured 100% recall on the 53-school
    known-positive set. Billing/auth (401/402) -> SystemExit halt, same control-failure stance as
    openrouter_search (every later call would fail identically). A 429 is TRANSIENT (issue #29):
    one short sleep + single retry, then TransientProviderError (a plain exception -- the caller
    degrades that school, the run continues)."""
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
perplexity_search.provider_name = "perplexity"
openrouter_search.provider_name = "openrouter"
serper_search.provider_name = "serper"
brightdata_search.provider_name = "brightdata"


def rank_key(c):
    return (any(k in c["url"].lower() for k in SCHED_KW), len(c["tools"]))

def main():
    man={d["district_id"]:d for d in json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]}
    dom=load_domains()
    ids=sys.argv[1].split(",") if len(sys.argv)>1 else ["1000200","5605302","0200600"]
    cap=int(sys.argv[2]) if len(sys.argv)>2 else 8
    for did in ids:
        d=man[did]; dhost=dom.get(did,""); scoped=bool(dhost); slug=dhost.split(".")[0] if dhost else ""
        q=f'{d["district_name"]} {d["state"]} school bell schedule start and end times'
        kept={}; rej=[]
        for tool,fn in [("perplexity",perplexity_search),("openrouter",openrouter_search)]:
            try: urls=fn(q,dhost)
            except Exception as e: print(f"  [{did}/{tool}] ERR {str(e)[:80]}"); urls=[]
            for u in urls:
                ok,why=gate(u,dhost,slug,scoped)
                if ok:
                    n=host_of(u)+urlparse(u).path.rstrip("/")
                    kept.setdefault(n,{"url":u,"tools":[],"gate":why})
                    if tool not in kept[n]["tools"]: kept[n]["tools"].append(tool)
                else: rej.append({"url":u,"tool":tool,"why":why})
        ranked=sorted(kept.values(), key=rank_key, reverse=True)[:cap]
        dd=OUT/did; dd.mkdir(parents=True,exist_ok=True)
        (dd/"candidates.json").write_text(json.dumps({"district_id":did,"name":d["district_name"],"state":d["state"],
            "domain":dhost,"scoped":scoped,"query":q,"candidates":ranked},indent=2))
        (dd/"rejected.json").write_text(json.dumps(rej,indent=2))
        print(f"{did} {d['district_name'][:24]:24} dom={(dhost or '(none/unscoped)'):22} kept={len(ranked):2}/{len(kept):2} rej={len(rej)}")

if __name__=="__main__": main()
