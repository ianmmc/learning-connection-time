"""Discovery v3: domain-scoped search (Perplexity param + OpenRouter site:) + smart URL gate,
with an unscoped fallback for districts whose NCES WEBSITE is blank. Ranks candidates
(schedule-keyword URLs + multi-tool agreement first) and caps per district. Google dropped.
Writes candidates.json (gated, ranked, capped) + rejected.json. Usage: discover.py [ids] [cap]"""
import os, json, sys, csv
from pathlib import Path
from urllib.parse import urlparse

OUT=Path("data/benchmark_results/discovery")
NCES="data/raw/federal/nces-ccd/2023_24/ccd_lea_029_2324_w_1a_073124.csv"
CMS_HOSTS=("finalsite.net","echalksites.com","sites.google.com","drive.google.com","docs.google.com","schoolwires.net","schoolwires.com","blackboard.com")
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

def gate(url, dhost, slug, scoped):
    h=host_of(url)
    if not h: return False,"no-host"
    if any(h.endswith(n) for n in NEWS_AGG): return False,"news/aggregator"
    if scoped:
        if h==dhost or h.endswith("."+dhost): return True,"on-domain"
        if any(h.endswith(c) for c in CMS_HOSTS) and slug and slug in url.lower(): return True,"cms-slug"
        return False,"off-district"
    return True,"unscoped"   # no NCES domain: keep non-news results; relevance gate sorts it out

def perplexity_search(q, dhost, k=10):
    from perplexity import Perplexity
    kw={"query":q,"max_results":k}
    if dhost: kw["search_domain_filter"]=[dhost]
    r=Perplexity().search.create(**kw)
    return [getattr(it,"url","") for it in (r.results or []) if getattr(it,"url","")]

def openrouter_search(q, dhost, k=10):
    import openai
    c=openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY"))
    query=f"{q} site:{dhost}" if dhost else q
    r=c.chat.completions.create(model="openai/gpt-4o-mini-search-preview",
        messages=[{"role":"user","content":query}], max_tokens=600, extra_body={"plugins":[{"id":"web"}]})
    ann=getattr(r.choices[0].message,"annotations",None) or []
    out=[]
    for a in ann:
        ad=a if isinstance(a,dict) else a.model_dump()
        u=(ad.get("url_citation") or {}).get("url") or ad.get("url")
        if u: out.append(u)
    return out[:k]

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
