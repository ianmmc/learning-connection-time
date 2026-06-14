"""Discovery v2: domain-scoped search (Perplexity param + OpenRouter site:) + smart URL gate.
District domain from NCES LEA file. Google dropped (grounding can't site-restrict).
Writes candidates.json (gated-in) + rejected.json (gated-out, for transparency). Usage: discover.py [ids]"""
import os, json, sys, csv
from pathlib import Path
from urllib.parse import urlparse

OUT=Path("data/benchmark_results/discovery")
NCES="data/raw/federal/nces-ccd/2023_24/ccd_lea_029_2324_w_1a_073124.csv"
CMS_HOSTS=("finalsite.net","echalksites.com","sites.google.com","drive.google.com","docs.google.com","schoolwires.net","schoolwires.com","blackboard.com")
NEWS_AGG=("patch.com","niche.com","greatschools.org","wikipedia.org","news12.com","sweetwaternow.com","firststateupdate.com","facebook.com","instagram.com")

def host_of(url):
    try: return urlparse(url).netloc.lower().split(":")[0].replace("www.","")
    except Exception: return ""

def district_host(website):  # NCES website -> bare host (gate suffix), e.g. www.sweetwater1.org -> sweetwater1.org
    return host_of(website if "//" in website else "http://"+website)

def load_domains():
    out={}
    with open(NCES, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            out[row.get("LEAID","").zfill(7)] = district_host(row.get("WEBSITE","") or "")
    return out

def gate(url, dhost, slug):
    h=host_of(url)
    if not h: return False,"no-host"
    if h==dhost or h.endswith("."+dhost): return True,"on-domain"            # district domain or subdomain
    if any(h.endswith(c) for c in CMS_HOSTS) and slug and slug in url.lower(): return True,"cms-slug"
    if any(h.endswith(n) for n in NEWS_AGG): return False,"news/aggregator"
    return False,"off-district"

def perplexity_search(q, dhost, k=8):
    from perplexity import Perplexity
    r=Perplexity().search.create(query=q, max_results=k, search_domain_filter=[dhost])
    return [getattr(it,"url","") for it in (r.results or []) if getattr(it,"url","")]

def openrouter_search(q, dhost, k=8):
    import openai
    c=openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY"))
    r=c.chat.completions.create(model="openai/gpt-4o-mini-search-preview",
        messages=[{"role":"user","content":f"{q} site:{dhost}"}], max_tokens=500, extra_body={"plugins":[{"id":"web"}]})
    ann=getattr(r.choices[0].message,"annotations",None) or []
    out=[]
    for a in ann:
        ad=a if isinstance(a,dict) else a.model_dump()
        u=(ad.get("url_citation") or {}).get("url") or ad.get("url")
        if u: out.append(u)
    return out[:k]

def main():
    man={d["district_id"]:d for d in json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]}
    dom=load_domains()
    ids=sys.argv[1].split(",") if len(sys.argv)>1 else ["1000200","5605302","0200600"]
    for did in ids:
        d=man[did]; dhost=dom.get(did,"") ; slug=dhost.split(".")[0] if dhost else ""
        q=f'{d["district_name"]} {d["state"]} school bell schedule start and end times'
        kept={}; rej=[]
        for tool,fn in [("perplexity",perplexity_search),("openrouter",openrouter_search)]:
            if not dhost: break
            try: urls=fn(q,dhost)
            except Exception as e: print(f"  [{did}/{tool}] ERR {str(e)[:80]}"); urls=[]
            for u in urls:
                ok,why=gate(u,dhost,slug)
                if ok:
                    n=host_of(u)+urlparse(u).path.rstrip("/")
                    kept.setdefault(n,{"url":u,"tools":[],"gate":why})
                    if tool not in kept[n]["tools"]: kept[n]["tools"].append(tool)
                else: rej.append({"url":u,"tool":tool,"why":why})
        dd=OUT/did; dd.mkdir(parents=True,exist_ok=True)
        (dd/"candidates.json").write_text(json.dumps({"district_id":did,"name":d["district_name"],"state":d["state"],
            "domain":dhost,"query":q,"candidates":list(kept.values())},indent=2))
        (dd/"rejected.json").write_text(json.dumps(rej,indent=2))
        print(f"{did} {d['district_name'][:26]:26} dom={dhost:22} kept={len(kept):2} rejected={len(rej)}")
        for v in list(kept.values())[:6]: print(f"      [{','.join(v['tools'])}/{v['gate']}] {v['url'][:74]}")

if __name__=="__main__": main()
