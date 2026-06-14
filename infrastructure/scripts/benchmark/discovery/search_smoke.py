"""Discovery search layer — 3 API paths (Claude WebSearch path handled via subagent).
For each district, query each tool, return candidate URLs. Dedupe + cross-tool agreement.
Reads keys from env (PERPLEXITY_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY)."""
import os, json, sys, re
from urllib.parse import urlparse

def _norm(u):  # normalize for dedupe
    try:
        p = urlparse(u); return (p.netloc.lower().lstrip("www."), p.path.rstrip("/")).__str__()
    except Exception: return u

def perplexity_search(q, k=6):
    from perplexity import Perplexity
    r = Perplexity().search.create(query=q, max_results=k)
    return [getattr(it, "url", "") for it in (r.results or []) if getattr(it, "url", "")]

def google_grounding(q, k=6):
    import requests
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    resp = client.models.generate_content(
        model="gemini-2.5-flash", contents=q,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
    gm = resp.candidates[0].grounding_metadata
    out = []
    for c in (getattr(gm, "grounding_chunks", None) or [])[:k]:
        uri = getattr(getattr(c, "web", None), "uri", "") or ""
        if not uri: continue
        try:  # resolve vertexaisearch redirect -> real URL
            out.append(requests.get(uri, allow_redirects=True, timeout=15).url)
        except Exception:
            out.append(uri)
    return out

def openrouter_search(q, k=6):
    import openai
    c = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY"))
    r = c.chat.completions.create(model="openai/gpt-4o-mini-search-preview",
        messages=[{"role": "user", "content": q}], max_tokens=500,
        extra_body={"plugins": [{"id": "web"}]})
    ann = getattr(r.choices[0].message, "annotations", None) or []
    urls = []
    for a in ann:
        ad = a if isinstance(a, dict) else a.model_dump()
        u = (ad.get("url_citation") or {}).get("url") or ad.get("url")
        if u: urls.append(u)
    return urls[:k]

TOOLS = {"perplexity": perplexity_search, "google": google_grounding, "openrouter": openrouter_search}

def main():
    man = json.load(open("data/benchmark/ground_truth_manifest.json"))["districts"]
    ids = sys.argv[1].split(",") if len(sys.argv) > 1 else ["1000200", "5605302", "0200600"]
    by = {d["district_id"]: d for d in man}
    for did in ids:
        d = by[did]; q = f'{d["district_name"]} {d["state"]} school bell schedule start and end times'
        print(f"\n================ {did} {d['district_name']} ({d['state']}) ================")
        union = {}
        for tool, fn in TOOLS.items():
            try:
                urls = fn(q)
            except Exception as e:
                print(f"  [{tool}] ERR {type(e).__name__}: {str(e)[:110]}"); continue
            print(f"  [{tool}] {len(urls)} urls")
            for u in urls:
                print("       ", u[:95]); union.setdefault(_norm(u), {"url": u, "tools": set()})["tools"].add(tool)
        multi = [v for v in union.values() if len(v["tools"]) > 1]
        print(f"  >>> {len(union)} unique URLs; {len(multi)} found by >1 tool (cross-tool agreement):")
        for v in multi: print(f"       [{','.join(sorted(v['tools']))}] {v['url'][:80]}")

if __name__ == "__main__":
    main()
